"""Capa HTTP administrativa de Tips para configuración, catálogo, pedidos, usuarios y auditoría."""

from __future__ import annotations

from http import HTTPStatus
from http.server import ThreadingHTTPServer
import json
import re
from typing import Any

from .config import Settings
from .database import connect, transaction
from .security import RateLimiter
from .server import TipsRequestHandler, iso, utc_now

SETTING_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ORDER_STATUSES = {"pending", "paid", "processing", "ready", "shipped", "completed", "cancelled", "refunded"}
QUOTE_STATUSES = {"new", "contacted", "qualified", "closed", "archived"}
STOCK_STATUSES = {"available", "low", "out", "made_to_order"}
LOGO_VARIANTS = {"orange", "green", "black", "brown"}
USER_ROLES = {"user", "admin"}


class TipsAdminRequestHandler(TipsRequestHandler):
    """Encapsula la responsabilidad de TipsAdminRequestHandler dentro de la arquitectura de Tips."""
    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        """Despacha las rutas GET que pertenecen a esta capa y delega el resto a la clase padre."""
        if path == "/api/site-settings":
            self._site_settings(public_only=True)
            return
        if path.startswith("/api/admin/"):
            user = self._require_admin()
            if not user:
                return
            routes = {
                "/api/admin/overview": lambda: self._admin_overview_full(user),
                "/api/admin/settings": lambda: self._admin_settings(user),
                "/api/admin/products": lambda: self._admin_products(user),
                "/api/admin/projects": lambda: self._admin_projects(user),
                "/api/admin/orders": lambda: self._admin_orders(user),
                "/api/admin/quotes": lambda: self._admin_quotes(user),
                "/api/admin/users": lambda: self._admin_users(user),
                "/api/admin/promotions": lambda: self._admin_promotions(user),
            }
            handler = routes.get(path)
            if handler:
                handler()
                return
        super()._handle_api_get(path, query)

    def _handle_api_post(self, path: str) -> None:
        """Despacha las rutas POST que pertenecen a esta capa y delega el resto a la clase padre."""
        if path.startswith("/api/admin/"):
            user = self._require_admin()
            if not user:
                return
            data = self._read_json()
            if data is None:
                return
            routes = {
                "/api/admin/settings/save": lambda: self._save_setting(user, data),
                "/api/admin/products/update": lambda: self._update_product(user, data),
                "/api/admin/projects/update": lambda: self._update_project(user, data),
                "/api/admin/orders/update": lambda: self._update_order(user, data),
                "/api/admin/quotes/update": lambda: self._update_quote(user, data),
                "/api/admin/promotions/save": lambda: self._save_promotion(user, data),
                "/api/admin/users/update": lambda: self._update_user(user, data),
            }
            handler = routes.get(path)
            if handler:
                handler()
                return
            self._json({"error": "Ruta administrativa no encontrada."}, HTTPStatus.NOT_FOUND)
            return
        super()._handle_api_post(path)

    def _site_settings(self, *, public_only: bool) -> None:
        """Lee la configuración del sitio y convierte el JSON persistido en estructuras Python."""
        sql = "SELECT key,value_json FROM site_settings"
        if public_only:
            sql += " WHERE is_public=1"
        sql += " ORDER BY key"
        with connect(self.settings) as db:
            rows = db.execute(sql).fetchall()
        values: dict[str, Any] = {}
        for row in rows:
            try:
                values[row["key"]] = json.loads(row["value_json"])
            except json.JSONDecodeError:
                values[row["key"]] = None
        self._json({"settings": values})

    def _admin_overview_full(self, user: dict[str, object]) -> None:
        """Construye las métricas, alertas y listados resumidos del dashboard administrativo."""
        with connect(self.settings) as db:
            metrics = {
                "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                "products": db.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0],
                "quotes": db.execute("SELECT COUNT(*) FROM quote_requests").fetchone()[0],
                "projects": db.execute("SELECT COUNT(*) FROM portfolio_projects").fetchone()[0],
                "users": db.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0],
                "sales_cents": db.execute("SELECT COALESCE(SUM(total_cents),0) FROM orders WHERE status IN('paid','processing','ready','shipped','completed')").fetchone()[0],
            }
            new_quotes = db.execute("SELECT COUNT(*) FROM quote_requests WHERE status='new'").fetchone()[0]
            active_orders = db.execute("SELECT COUNT(*) FROM orders WHERE status IN('paid','processing','ready')").fetchone()[0]
            low_stock = db.execute(
                "SELECT COUNT(*) FROM product_variants v JOIN products p ON p.id=v.product_id WHERE p.is_active=1 AND v.is_active=1 AND v.stock_quantity IS NOT NULL AND v.stock_quantity<=5"
            ).fetchone()[0]
            orders = db.execute("SELECT id,public_id,customer_name,status,total_cents,created_at FROM orders ORDER BY id DESC LIMIT 8").fetchall()
            quotes = db.execute("SELECT id,name,project_type,status,created_at FROM quote_requests ORDER BY id DESC LIMIT 8").fetchall()
            products = db.execute(
                """SELECT p.id,p.name,p.base_price_cents,p.stock_status,p.is_active,c.name AS category_name,
                (SELECT v.stock_quantity FROM product_variants v WHERE v.product_id=p.id AND v.is_active=1 ORDER BY v.id LIMIT 1) AS stock_quantity
                FROM products p LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.sort_order,p.name LIMIT 50"""
            ).fetchall()
        alerts: list[dict[str, Any]] = []
        if new_quotes:
            alerts.append({"level": "info", "title": "Cotizaciones nuevas", "message": f"Hay {new_quotes} solicitud(es) esperando revisión.", "view": "quotes", "count": new_quotes})
        if low_stock:
            alerts.append({"level": "warning", "title": "Inventario bajo", "message": f"Hay {low_stock} variante(s) con 5 unidades o menos.", "view": "inventory", "count": low_stock})
        if active_orders:
            alerts.append({"level": "success", "title": "Pedidos por atender", "message": f"Hay {active_orders} pedido(s) en preparación o listos para gestión.", "view": "orders", "count": active_orders})
        self._json({
            "user": user,
            "metrics": metrics,
            "alerts": alerts,
            "orders": [dict(r) for r in orders],
            "quotes": [dict(r) for r in quotes],
            "products": [dict(r) for r in products],
        })

    def _admin_settings(self, user: dict[str, object]) -> None:
        """Devuelve todas las configuraciones editables para el panel administrativo."""
        with connect(self.settings) as db:
            rows = db.execute("SELECT key,value_json,is_public,updated_at FROM site_settings ORDER BY key").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["value"] = json.loads(item.pop("value_json"))
            except json.JSONDecodeError:
                item["value"] = None
                item.pop("value_json", None)
            items.append(item)
        self._json({"user": user, "items": items})

    def _admin_products(self, user: dict[str, object]) -> None:
        """Devuelve el catálogo requerido por las pantallas administrativas."""
        with connect(self.settings) as db:
            rows = db.execute(
                """SELECT p.id,p.name,p.slug,p.description,p.base_price_cents,p.currency,p.stock_status,p.is_active,c.name AS category_name,
                (SELECT v.id FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS variant_id,
                (SELECT v.option_summary FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS option_summary,
                (SELECT v.stock_quantity FROM product_variants v WHERE v.product_id=p.id ORDER BY v.id LIMIT 1) AS stock_quantity
                FROM products p LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.sort_order,p.name"""
            ).fetchall()
        self._json({"user": user, "items": [dict(r) for r in rows]})

    def _admin_projects(self, user: dict[str, object]) -> None:
        """Devuelve los proyectos de portafolio para su gestión administrativa."""
        with connect(self.settings) as db:
            rows = db.execute(
                "SELECT id,title,slug,category,summary,description,location,completed_year,is_published,sort_order FROM portfolio_projects ORDER BY sort_order,id DESC"
            ).fetchall()
        self._json({"user": user, "items": [dict(r) for r in rows]})

    def _admin_orders(self, user: dict[str, object]) -> None:
        """Devuelve los pedidos recientes con sus datos operativos."""
        with connect(self.settings) as db:
            rows = db.execute(
                "SELECT id,public_id,email,customer_name,phone,status,currency,total_cents,shipping_address_json,created_at,updated_at FROM orders ORDER BY id DESC LIMIT 200"
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["shipping_address"] = json.loads(item.pop("shipping_address_json") or "{}")
            except json.JSONDecodeError:
                item["shipping_address"] = {}
                item.pop("shipping_address_json", None)
            items.append(item)
        self._json({"user": user, "items": items})

    def _admin_quotes(self, user: dict[str, object]) -> None:
        """Devuelve las solicitudes de cotización registradas en el sistema."""
        with connect(self.settings) as db:
            rows = db.execute(
                "SELECT id,name,contact,project_type,message,status,internal_notes,created_at,updated_at FROM quote_requests ORDER BY id DESC LIMIT 200"
            ).fetchall()
        self._json({"user": user, "items": [dict(r) for r in rows]})

    def _admin_users(self, user: dict[str, object]) -> None:
        """Devuelve las cuentas administrables y sus estados actuales."""
        with connect(self.settings) as db:
            rows = db.execute(
                "SELECT id,email,display_name,role,is_active,failed_login_count,locked_until,created_at,updated_at FROM users ORDER BY created_at DESC LIMIT 300"
            ).fetchall()
        self._json({"user": user, "items": [dict(r) for r in rows]})

    def _admin_promotions(self, user: dict[str, object]) -> None:
        """Devuelve las promociones configuradas en la tienda."""
        with connect(self.settings) as db:
            rows = db.execute(
                "SELECT id,code,name,discount_type,discount_value,starts_at,ends_at,is_active,created_at FROM promotions ORDER BY id DESC LIMIT 200"
            ).fetchall()
        self._json({"user": user, "items": [dict(r) for r in rows]})

    def _save_setting(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Valida y persiste una configuración editable del sitio."""
        key = str(data.get("key", "")).strip().lower()
        value = data.get("value")
        is_public = bool(data.get("is_public", True))
        if not SETTING_KEY_RE.fullmatch(key):
            self._json({"error": "Clave de configuración inválida."}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(value, dict):
            self._json({"error": "La configuración debe ser un objeto."}, HTTPStatus.BAD_REQUEST)
            return
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 12_000:
            self._json({"error": "La configuración es demasiado grande."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        if key == "theme":
            for color_key in ("primary", "accent", "secondary", "surface"):
                if color_key in value and not HEX_COLOR_RE.fullmatch(str(value[color_key])):
                    self._json({"error": f"Color inválido: {color_key}."}, HTTPStatus.BAD_REQUEST)
                    return
            if "logo_variant" in value and str(value["logo_variant"]) not in LOGO_VARIANTS:
                self._json({"error": "Variante de logo inválida."}, HTTPStatus.BAD_REQUEST)
                return
        with transaction(self.settings) as db:
            db.execute(
                """INSERT INTO site_settings(key,value_json,is_public,updated_by,updated_at) VALUES(?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,is_public=excluded.is_public,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (key, encoded, int(is_public), user["id"], iso(utc_now())),
            )
            self._audit(db, user, "update", "site_setting", key, {"key": key})
        self._json({"ok": True, "key": key, "value": value})

    def _update_product(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Valida y actualiza datos de un producto y su variante principal."""
        product_id = data.get("id")
        if not isinstance(product_id, int):
            self._json({"error": "Producto inválido."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            current = db.execute("SELECT id,name,description,base_price_cents,stock_status,is_active FROM products WHERE id=?", (product_id,)).fetchone()
            if not current:
                self._json({"error": "Producto no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            name = str(data.get("name", current["name"])).strip()
            description = str(data.get("description", current["description"])).strip()
            price = data.get("base_price_cents", current["base_price_cents"])
            status = str(data.get("stock_status", current["stock_status"]))
            active = int(bool(data.get("is_active", current["is_active"])))
            stock = data.get("stock_quantity")
            if not 2 <= len(name) <= 180 or len(description) > 5000 or not isinstance(price, int) or price < 0 or status not in STOCK_STATUSES:
                self._json({"error": "Revisa nombre, descripción, precio y estado."}, HTTPStatus.BAD_REQUEST)
                return
            if stock is not None and (not isinstance(stock, int) or stock < 0 or stock > 1_000_000):
                self._json({"error": "Cantidad de inventario inválida."}, HTTPStatus.BAD_REQUEST)
                return
            stamp = iso(utc_now())
            db.execute(
                "UPDATE products SET name=?,description=?,base_price_cents=?,stock_status=?,is_active=?,updated_at=? WHERE id=?",
                (name, description, price, status, active, stamp, product_id),
            )
            if "stock_quantity" in data:
                variant = db.execute("SELECT id,stock_quantity FROM product_variants WHERE product_id=? ORDER BY id LIMIT 1", (product_id,)).fetchone()
                if variant:
                    old_stock = variant["stock_quantity"]
                    db.execute("UPDATE product_variants SET stock_quantity=?,updated_at=? WHERE id=?", (stock, stamp, variant["id"]))
                    if stock is not None and old_stock is not None and stock != old_stock:
                        db.execute(
                            "INSERT INTO inventory_movements(variant_id,delta,reason,created_by,created_at) VALUES(?,?,'ajuste administrativo',?,?)",
                            (variant["id"], stock - old_stock, user["id"], stamp),
                        )
            self._audit(db, user, "update", "product", str(product_id), {"name": name})
        self._json({"ok": True, "id": product_id})

    def _update_project(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Valida y actualiza un proyecto del portafolio."""
        project_id = data.get("id")
        if not isinstance(project_id, int):
            self._json({"error": "Proyecto inválido."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            current = db.execute("SELECT * FROM portfolio_projects WHERE id=?", (project_id,)).fetchone()
            if not current:
                self._json({"error": "Proyecto no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            title = str(data.get("title", current["title"])).strip()
            category = str(data.get("category", current["category"])).strip()
            summary = str(data.get("summary", current["summary"])).strip()
            description = str(data.get("description", current["description"])).strip()
            location = str(data.get("location", current["location"] or "")).strip()
            year = data.get("completed_year", current["completed_year"])
            published = int(bool(data.get("is_published", current["is_published"])))
            if not 2 <= len(title) <= 180 or not 2 <= len(category) <= 80 or len(summary) > 1000 or len(description) > 8000:
                self._json({"error": "Revisa los datos del proyecto."}, HTTPStatus.BAD_REQUEST)
                return
            if year not in (None, "") and (not isinstance(year, int) or year < 1900 or year > 2200):
                self._json({"error": "Año de proyecto inválido."}, HTTPStatus.BAD_REQUEST)
                return
            db.execute(
                "UPDATE portfolio_projects SET title=?,category=?,summary=?,description=?,location=?,completed_year=?,is_published=?,updated_at=? WHERE id=?",
                (title, category, summary, description, location, year or None, published, iso(utc_now()), project_id),
            )
            self._audit(db, user, "update", "portfolio_project", str(project_id), {"title": title})
        self._json({"ok": True, "id": project_id})

    def _update_order(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Cambia el estado operativo de un pedido existente."""
        order_id = data.get("id")
        status = str(data.get("status", "")).strip()
        if not isinstance(order_id, int) or status not in ORDER_STATUSES:
            self._json({"error": "Pedido o estado inválido."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            exists = db.execute("SELECT id,public_id FROM orders WHERE id=?", (order_id,)).fetchone()
            if not exists:
                self._json({"error": "Pedido no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            db.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?", (status, iso(utc_now()), order_id))
            self._audit(db, user, "update_status", "order", str(order_id), {"status": status, "public_id": exists["public_id"]})
        self._json({"ok": True, "id": order_id, "status": status})

    def _update_quote(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Cambia el estado de seguimiento de una cotización."""
        quote_id = data.get("id")
        status = str(data.get("status", "")).strip()
        notes = str(data.get("internal_notes", "")).strip()
        if not isinstance(quote_id, int) or status not in QUOTE_STATUSES or len(notes) > 3000:
            self._json({"error": "Cotización, estado o notas inválidas."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            exists = db.execute("SELECT id FROM quote_requests WHERE id=?", (quote_id,)).fetchone()
            if not exists:
                self._json({"error": "Cotización no encontrada."}, HTTPStatus.NOT_FOUND)
                return
            db.execute("UPDATE quote_requests SET status=?,internal_notes=?,updated_at=? WHERE id=?", (status, notes, iso(utc_now()), quote_id))
            self._audit(db, user, "update_status", "quote_request", str(quote_id), {"status": status})
        self._json({"ok": True, "id": quote_id, "status": status})

    def _save_promotion(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Crea o actualiza una promoción después de validar su contenido."""
        promotion_id = data.get("id")
        code = str(data.get("code", "")).strip().upper() or None
        name = str(data.get("name", "")).strip()
        discount_type = str(data.get("discount_type", "percent")).strip()
        discount_value = data.get("discount_value", 0)
        starts_at = str(data.get("starts_at", "")).strip() or None
        ends_at = str(data.get("ends_at", "")).strip() or None
        is_active = int(bool(data.get("is_active", True)))
        if not 2 <= len(name) <= 160 or discount_type not in {"percent", "fixed"} or not isinstance(discount_value, int) or discount_value < 0:
            self._json({"error": "Datos de promoción inválidos."}, HTTPStatus.BAD_REQUEST)
            return
        if code and (len(code) > 40 or not re.fullmatch(r"[A-Z0-9_-]+", code)):
            self._json({"error": "Código promocional inválido."}, HTTPStatus.BAD_REQUEST)
            return
        try:
            with transaction(self.settings) as db:
                if isinstance(promotion_id, int):
                    exists = db.execute("SELECT id FROM promotions WHERE id=?", (promotion_id,)).fetchone()
                    if not exists:
                        self._json({"error": "Promoción no encontrada."}, HTTPStatus.NOT_FOUND)
                        return
                    db.execute(
                        "UPDATE promotions SET code=?,name=?,discount_type=?,discount_value=?,starts_at=?,ends_at=?,is_active=? WHERE id=?",
                        (code, name, discount_type, discount_value, starts_at, ends_at, is_active, promotion_id),
                    )
                    entity_id = promotion_id
                else:
                    cur = db.execute(
                        "INSERT INTO promotions(code,name,discount_type,discount_value,starts_at,ends_at,is_active) VALUES(?,?,?,?,?,?,?)",
                        (code, name, discount_type, discount_value, starts_at, ends_at, is_active),
                    )
                    entity_id = cur.lastrowid
                self._audit(db, user, "save", "promotion", str(entity_id), {"name": name})
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                self._json({"error": "Ese código promocional ya existe."}, HTTPStatus.CONFLICT)
                return
            raise
        self._json({"ok": True, "id": entity_id})

    def _update_user(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Actualiza rol o estado de una cuenta con controles administrativos."""
        target_id = data.get("id")
        role = str(data.get("role", "")).strip()
        is_active = int(bool(data.get("is_active", True)))
        if not isinstance(target_id, int) or role not in USER_ROLES:
            self._json({"error": "Usuario o rol inválido."}, HTTPStatus.BAD_REQUEST)
            return
        if target_id == user["id"] and (role != "admin" or not is_active):
            self._json({"error": "No puedes quitar tus propios permisos administrativos ni desactivar tu cuenta desde aquí."}, HTTPStatus.CONFLICT)
            return
        with transaction(self.settings) as db:
            target = db.execute("SELECT id,role,is_active FROM users WHERE id=?", (target_id,)).fetchone()
            if not target:
                self._json({"error": "Usuario no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            if target["role"] == "admin" and (role != "admin" or not is_active):
                active_admins = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
                if active_admins <= 1:
                    self._json({"error": "Debe permanecer al menos un administrador activo."}, HTTPStatus.CONFLICT)
                    return
            db.execute("UPDATE users SET role=?,is_active=?,updated_at=? WHERE id=?", (role, is_active, iso(utc_now()), target_id))
            self._audit(db, user, "update", "user", str(target_id), {"role": role, "is_active": is_active})
        self._json({"ok": True, "id": target_id})

    def _audit(self, db: Any, user: dict[str, object], action: str, entity_type: str, entity_id: str, metadata: dict[str, Any]) -> None:
        """Registra una acción sensible en el historial de auditoría."""
        db.execute(
            "INSERT INTO audit_logs(actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
            (user["id"], action, entity_type, entity_id, json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), iso(utc_now())),
        )


def create_server(settings: Settings) -> ThreadingHTTPServer:
    """Crea un servidor HTTP multihilo configurando settings y rate limiter en el handler."""
    handler = type("ConfiguredTipsAdminRequestHandler", (TipsAdminRequestHandler,), {
        "settings": settings,
        "rate_limiter": RateLimiter(settings.rate_limit_per_minute),
    })
    return ThreadingHTTPServer((settings.host, settings.port), handler)
