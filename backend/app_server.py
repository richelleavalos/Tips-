"""Capa HTTP de aplicación para cuenta de cliente, catálogo enriquecido e imágenes de producto."""

from __future__ import annotations

import base64
import binascii
from http import HTTPStatus
import json
from pathlib import Path
import re
import secrets
import unicodedata
from typing import Any

from .admin_server import TipsAdminRequestHandler
from .config import BASE_DIR
from .database import connect, transaction
from .security import hash_password, session_token_hash, validate_search_term, verify_password
from .server import EMAIL_RE, SESSION_COOKIE, iso, utc_now

MAX_PRODUCT_IMAGES = 5
MAX_IMAGE_BYTES = 700_000
UPLOAD_ROOT = BASE_DIR / "assets" / "uploads" / "products"


def _slugify(value: str) -> str:
    """Convierte texto libre en un slug estable y apto para URL."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug[:120] or f"producto-{secrets.token_hex(3)}"


def _detect_image(raw: bytes) -> tuple[str, str] | None:
    """Detecta formatos de imagen permitidos usando su firma binaria real."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


class TipsAppRequestHandler(TipsAdminRequestHandler):
    """Capa de aplicación para cuenta de cliente y medios configurables."""

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        """Despacha las rutas GET que pertenecen a esta capa y delega el resto a la clase padre."""
        if path == "/api/account":
            user = self._current_user()
            if not user:
                self._json({"error": "Autenticación requerida."}, HTTPStatus.UNAUTHORIZED)
                return
            self._account_details(user)
            return
        if path == "/api/products":
            self._get_products_with_images(query)
            return
        if path.startswith("/api/products/"):
            self._get_product_detail_with_images(path.rsplit("/", 1)[-1])
            return
        if path == "/api/admin/products/images":
            user = self._require_admin()
            if not user:
                return
            self._admin_product_images(query)
            return
        super()._handle_api_get(path, query)

    def _handle_api_post(self, path: str) -> None:
        """Despacha las rutas POST que pertenecen a esta capa y delega el resto a la clase padre."""
        account_routes = {
            "/api/account/profile": self._update_account_profile,
            "/api/account/password": self._change_account_password,
            "/api/account/deactivate": self._deactivate_account,
        }
        if path in account_routes:
            user = self._current_user()
            if not user:
                self._json({"error": "Autenticación requerida."}, HTTPStatus.UNAUTHORIZED)
                return
            data = self._read_json()
            if data is None:
                return
            account_routes[path](user, data)
            return

        admin_routes = {
            "/api/admin/products/create": self._create_product,
            "/api/admin/products/images/add": self._add_product_image,
            "/api/admin/products/images/update": self._update_product_image,
            "/api/admin/products/images/delete": self._delete_product_image,
        }
        if path in admin_routes:
            user = self._require_admin()
            if not user:
                return
            data = self._read_json()
            if data is None:
                return
            admin_routes[path](user, data)
            return

        super()._handle_api_post(path)

    def _get_products_with_images(self, query: dict[str, list[str]]) -> None:
        """Lista productos públicos incluyendo su imagen principal."""
        try:
            search = validate_search_term(query.get("search", [""])[0])
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        category = query.get("category", [""])[0].strip()
        sql = """SELECT p.id,p.name,p.slug,p.description,p.base_price_cents,p.currency,p.stock_status,
                    c.name AS category_name,c.slug AS category_slug,
                    (SELECT v.id FROM product_variants v WHERE v.product_id=p.id AND v.is_active=1 ORDER BY v.id LIMIT 1) AS first_variant_id,
                    (SELECT v.stock_quantity FROM product_variants v WHERE v.product_id=p.id AND v.is_active=1 ORDER BY v.id LIMIT 1) AS stock_quantity,
                    (SELECT pi.path FROM product_images pi WHERE pi.product_id=p.id ORDER BY pi.sort_order,pi.id LIMIT 1) AS primary_image,
                    (SELECT pi.alt_text FROM product_images pi WHERE pi.product_id=p.id ORDER BY pi.sort_order,pi.id LIMIT 1) AS primary_image_alt
                 FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.is_active=1"""
        params: list[object] = []
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " AND (p.name LIKE ? ESCAPE '\\' OR p.description LIKE ? ESCAPE '\\')"
            params += [f"%{escaped}%", f"%{escaped}%"]
        if category:
            sql += " AND c.slug=?"
            params.append(category)
        sql += " ORDER BY p.sort_order,p.name LIMIT 100"
        with connect(self.settings) as db:
            rows = db.execute(sql, tuple(params)).fetchall()
        self._json({"items": [dict(row) for row in rows]})

    def _get_product_detail_with_images(self, raw_id: str) -> None:
        """Construye el detalle de producto con variantes, imágenes y personalizaciones."""
        try:
            product_id = int(raw_id)
        except ValueError:
            self._json({"error": "Producto inválido."}, HTTPStatus.BAD_REQUEST)
            return
        with connect(self.settings) as db:
            product = db.execute(
                """SELECT p.id,p.name,p.slug,p.description,p.base_price_cents,p.currency,p.stock_status,c.name AS category_name
                FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=? AND p.is_active=1""",
                (product_id,),
            ).fetchone()
            if not product:
                self._json({"error": "Producto no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            variants = db.execute(
                "SELECT id,sku,option_summary,price_cents,stock_quantity FROM product_variants WHERE product_id=? AND is_active=1 ORDER BY id",
                (product_id,),
            ).fetchall()
            images = db.execute(
                "SELECT id,path,alt_text,sort_order FROM product_images WHERE product_id=? ORDER BY sort_order,id",
                (product_id,),
            ).fetchall()
            customizations = db.execute(
                """SELECT c.id,c.name,c.input_type,c.is_required,cv.id AS value_id,cv.label,cv.price_delta_cents
                FROM product_customizations pc JOIN customizations c ON c.id=pc.customization_id
                LEFT JOIN customization_values cv ON cv.customization_id=c.id AND cv.is_active=1
                WHERE pc.product_id=? AND c.is_active=1 ORDER BY pc.sort_order,c.id,cv.id""",
                (product_id,),
            ).fetchall()
        payload = dict(product)
        payload["variants"] = [dict(row) for row in variants]
        payload["images"] = [dict(row) for row in images]
        grouped: dict[int, dict[str, Any]] = {}
        for row in customizations:
            cid = row["id"]
            grouped.setdefault(cid, {"id": cid, "name": row["name"], "input_type": row["input_type"], "is_required": row["is_required"], "values": []})
            if row["value_id"] is not None:
                grouped[cid]["values"].append({"id": row["value_id"], "label": row["label"], "price_delta_cents": row["price_delta_cents"]})
        payload["customizations"] = list(grouped.values())
        self._json(payload)

    def _account_details(self, user: dict[str, object]) -> None:
        """Devuelve el perfil del usuario autenticado y sus pedidos recientes."""
        with connect(self.settings) as db:
            row = db.execute(
                "SELECT id,email,display_name,role,is_active,created_at,updated_at,password_hash FROM users WHERE id=?",
                (user["id"],),
            ).fetchone()
            orders = db.execute(
                "SELECT public_id,status,total_cents,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5",
                (user["id"],),
            ).fetchall()
        self._json({
            "user": {
                "id": row["id"], "email": row["email"], "display_name": row["display_name"],
                "role": row["role"], "created_at": row["created_at"], "has_password": bool(row["password_hash"]),
            },
            "recent_orders": [dict(order) for order in orders],
        })

    def _update_account_profile(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Valida y actualiza nombre y correo de la cuenta autenticada."""
        display_name = str(data.get("display_name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        current_password = str(data.get("current_password", ""))
        if not 2 <= len(display_name) <= 120 or not EMAIL_RE.match(email):
            self._json({"error": "Revisa tu nombre y correo."}, HTTPStatus.BAD_REQUEST)
            return
        try:
            with transaction(self.settings) as db:
                current = db.execute("SELECT email,password_hash FROM users WHERE id=? AND is_active=1", (user["id"],)).fetchone()
                if not current:
                    self._json({"error": "Cuenta no disponible."}, HTTPStatus.NOT_FOUND)
                    return
                if email != current["email"]:
                    if not current["password_hash"] or not verify_password(current_password, current["password_hash"]):
                        self._json({"error": "Confirma tu contraseña actual para cambiar el correo."}, HTTPStatus.UNAUTHORIZED)
                        return
                db.execute("UPDATE users SET display_name=?,email=?,updated_at=? WHERE id=?", (display_name, email, iso(utc_now()), user["id"]))
                self._audit(db, user, "self_update", "user", str(user["id"]), {"email_changed": email != current["email"]})
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                self._json({"error": "Ese correo ya está asociado a otra cuenta."}, HTTPStatus.CONFLICT)
                return
            raise
        self._json({"ok": True, "user": {"id": user["id"], "display_name": display_name, "email": email, "role": user["role"]}})

    def _change_account_password(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Verifica la clave actual y guarda una contraseña nueva de forma segura."""
        current_password = str(data.get("current_password", ""))
        new_password = str(data.get("new_password", ""))
        with transaction(self.settings) as db:
            current = db.execute("SELECT password_hash FROM users WHERE id=? AND is_active=1", (user["id"],)).fetchone()
            if not current or not current["password_hash"] or not verify_password(current_password, current["password_hash"]):
                self._json({"error": "La contraseña actual no es correcta."}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                encoded = hash_password(new_password)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            db.execute("UPDATE users SET password_hash=?,updated_at=? WHERE id=?", (encoded, iso(utc_now()), user["id"]))
            raw = self._read_session_cookie()
            if raw:
                db.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND token_hash<>? AND revoked_at IS NULL", (iso(utc_now()), user["id"], session_token_hash(raw)))
            self._audit(db, user, "password_change", "user", str(user["id"]), {})
        self._json({"ok": True})

    def _deactivate_account(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Desactiva la cuenta actual y revoca todas sus sesiones abiertas."""
        current_password = str(data.get("current_password", ""))
        confirmation = str(data.get("confirmation", "")).strip().upper()
        if confirmation != "DESACTIVAR":
            self._json({"error": "Escribe DESACTIVAR para confirmar."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            current = db.execute("SELECT password_hash,role FROM users WHERE id=? AND is_active=1", (user["id"],)).fetchone()
            if not current or not current["password_hash"] or not verify_password(current_password, current["password_hash"]):
                self._json({"error": "La contraseña actual no es correcta."}, HTTPStatus.UNAUTHORIZED)
                return
            if current["role"] == "admin":
                active_admins = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
                if active_admins <= 1:
                    self._json({"error": "No puedes desactivar la última cuenta administradora activa."}, HTTPStatus.CONFLICT)
                    return
            stamp = iso(utc_now())
            db.execute("UPDATE users SET is_active=0,updated_at=? WHERE id=?", (stamp, user["id"]))
            db.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (stamp, user["id"]))
            self._audit(db, user, "deactivate", "user", str(user["id"]), {})
        self._pending_set_cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        self._json({"ok": True})

    def _admin_products(self, user: dict[str, object]) -> None:
        """Devuelve el catálogo requerido por las pantallas administrativas."""
        with connect(self.settings) as db:
            rows = db.execute(
                """SELECT p.id,p.name,p.slug,p.description,p.base_price_cents,p.currency,p.stock_status,p.is_active,p.category_id,c.name AS category_name,
                (SELECT v.id FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS variant_id,
                (SELECT v.sku FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS sku,
                (SELECT v.option_summary FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS option_summary,
                (SELECT v.stock_quantity FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS stock_quantity,
                (SELECT COUNT(*) FROM product_images pi WHERE pi.product_id=p.id) AS image_count,
                (SELECT pi.path FROM product_images pi WHERE pi.product_id=p.id ORDER BY pi.sort_order,pi.id LIMIT 1) AS primary_image
                FROM products p LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.sort_order,p.name"""
            ).fetchall()
        self._json({"user": user, "items": [dict(row) for row in rows]})

    def _create_product(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Crea un producto y su variante inicial dentro de una sola transacción."""
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        price = data.get("base_price_cents")
        stock = data.get("stock_quantity", 0)
        category_id = data.get("category_id")
        option_summary = str(data.get("option_summary", "Estándar")).strip()[:120]
        if not 2 <= len(name) <= 180 or len(description) > 5000 or not isinstance(price, int) or price < 0:
            self._json({"error": "Revisa nombre, descripción y precio."}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(stock, int) or stock < 0 or stock > 1_000_000:
            self._json({"error": "Inventario inválido."}, HTTPStatus.BAD_REQUEST)
            return
        if category_id is not None and not isinstance(category_id, int):
            self._json({"error": "Categoría inválida."}, HTTPStatus.BAD_REQUEST)
            return
        stamp = iso(utc_now())
        with transaction(self.settings) as db:
            if category_id is not None and not db.execute("SELECT id FROM categories WHERE id=? AND is_active=1", (category_id,)).fetchone():
                self._json({"error": "Categoría no encontrada."}, HTTPStatus.BAD_REQUEST)
                return
            base_slug = _slugify(name)
            slug = base_slug
            suffix = 2
            while db.execute("SELECT 1 FROM products WHERE slug=?", (slug,)).fetchone():
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            cursor = db.execute(
                "INSERT INTO products(category_id,name,slug,description,base_price_cents,currency,stock_status,is_active,created_at,updated_at) VALUES(?,?,?,?,?,'USD','available',1,?,?)",
                (category_id, name, slug, description, price, stamp, stamp),
            )
            product_id = cursor.lastrowid
            sku = f"TIPS-{product_id:04d}-{secrets.token_hex(2).upper()}"
            db.execute(
                "INSERT INTO product_variants(product_id,sku,option_summary,price_cents,stock_quantity,is_active,created_at,updated_at) VALUES(?,?,?,NULL,?,1,?,?)",
                (product_id, sku, option_summary or "Estándar", stock, stamp, stamp),
            )
            self._audit(db, user, "create", "product", str(product_id), {"name": name})
        self._json({"ok": True, "id": product_id, "slug": slug}, HTTPStatus.CREATED)

    def _admin_product_images(self, query: dict[str, list[str]]) -> None:
        """Lista las imágenes configuradas para un producto."""
        raw_id = query.get("product_id", [""])[0]
        try:
            product_id = int(raw_id)
        except ValueError:
            self._json({"error": "Producto inválido."}, HTTPStatus.BAD_REQUEST)
            return
        with connect(self.settings) as db:
            product = db.execute("SELECT id,name FROM products WHERE id=?", (product_id,)).fetchone()
            if not product:
                self._json({"error": "Producto no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            rows = db.execute("SELECT id,path,alt_text,sort_order FROM product_images WHERE product_id=? ORDER BY sort_order,id", (product_id,)).fetchall()
        self._json({"product": dict(product), "items": [dict(row) for row in rows], "max_images": MAX_PRODUCT_IMAGES})

    def _add_product_image(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Valida, almacena y registra una imagen nueva de producto."""
        product_id = data.get("product_id")
        alt_text = str(data.get("alt_text", "")).strip()
        encoded = str(data.get("data_base64", "")).strip()
        if not isinstance(product_id, int) or len(alt_text) > 180 or not encoded:
            self._json({"error": "Imagen o producto inválido."}, HTTPStatus.BAD_REQUEST)
            return
        if encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[-1]
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            self._json({"error": "La imagen no tiene un formato válido."}, HTTPStatus.BAD_REQUEST)
            return
        detected = _detect_image(raw)
        if not detected or len(raw) > MAX_IMAGE_BYTES:
            self._json({"error": "Usa JPG, PNG o WebP. La imagen optimizada debe pesar menos de 700 KB."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        mime, extension = detected
        target_dir = UPLOAD_ROOT / str(product_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{secrets.token_hex(12)}{extension}"
        target = target_dir / filename
        relative = target.relative_to(BASE_DIR).as_posix()
        try:
            with transaction(self.settings) as db:
                product = db.execute("SELECT id,name FROM products WHERE id=?", (product_id,)).fetchone()
                if not product:
                    self._json({"error": "Producto no encontrado."}, HTTPStatus.NOT_FOUND)
                    return
                count = db.execute("SELECT COUNT(*) FROM product_images WHERE product_id=?", (product_id,)).fetchone()[0]
                if count >= MAX_PRODUCT_IMAGES:
                    self._json({"error": f"Cada producto puede tener un máximo de {MAX_PRODUCT_IMAGES} imágenes."}, HTTPStatus.CONFLICT)
                    return
                target.write_bytes(raw)
                sort_order = db.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM product_images WHERE product_id=?", (product_id,)).fetchone()[0]
                cursor = db.execute(
                    "INSERT INTO product_images(product_id,path,alt_text,sort_order,created_at) VALUES(?,?,?,?,?)",
                    (product_id, relative, alt_text or product["name"], sort_order, iso(utc_now())),
                )
                image_id = cursor.lastrowid
                self._audit(db, user, "create", "product_image", str(image_id), {"product_id": product_id, "mime": mime})
        except Exception:
            if target.exists():
                target.unlink(missing_ok=True)
            raise
        self._json({"ok": True, "id": image_id, "path": relative, "alt_text": alt_text, "sort_order": sort_order}, HTTPStatus.CREATED)

    def _update_product_image(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Actualiza texto alternativo y orden de una imagen existente."""
        image_id = data.get("id")
        alt_text = str(data.get("alt_text", "")).strip()
        sort_order = data.get("sort_order", 0)
        if not isinstance(image_id, int) or len(alt_text) > 180 or not isinstance(sort_order, int) or not 0 <= sort_order <= 100:
            self._json({"error": "Datos de imagen inválidos."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            image = db.execute("SELECT id,product_id FROM product_images WHERE id=?", (image_id,)).fetchone()
            if not image:
                self._json({"error": "Imagen no encontrada."}, HTTPStatus.NOT_FOUND)
                return
            db.execute("UPDATE product_images SET alt_text=?,sort_order=? WHERE id=?", (alt_text, sort_order, image_id))
            self._audit(db, user, "update", "product_image", str(image_id), {"product_id": image["product_id"]})
        self._json({"ok": True})

    def _delete_product_image(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Elimina de forma coordinada el registro y archivo de una imagen."""
        image_id = data.get("id")
        if not isinstance(image_id, int):
            self._json({"error": "Imagen inválida."}, HTTPStatus.BAD_REQUEST)
            return
        path_to_delete: Path | None = None
        with transaction(self.settings) as db:
            image = db.execute("SELECT id,product_id,path FROM product_images WHERE id=?", (image_id,)).fetchone()
            if not image:
                self._json({"error": "Imagen no encontrada."}, HTTPStatus.NOT_FOUND)
                return
            db.execute("DELETE FROM product_images WHERE id=?", (image_id,))
            self._audit(db, user, "delete", "product_image", str(image_id), {"product_id": image["product_id"]})
            candidate = (BASE_DIR / image["path"]).resolve()
            try:
                candidate.relative_to(UPLOAD_ROOT.resolve())
                path_to_delete = candidate
            except ValueError:
                path_to_delete = None
        if path_to_delete and path_to_delete.is_file():
            path_to_delete.unlink(missing_ok=True)
        self._json({"ok": True})
