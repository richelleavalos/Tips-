"""Extensiones del catálogo que preparan el backend para más variantes, metadatos e imágenes."""

from __future__ import annotations

from http import HTTPStatus
import secrets

from .app_server import TipsAppRequestHandler, MAX_PRODUCT_IMAGES, _slugify
from .database import connect, transaction
from .security import validate_search_term
from .server import iso, utc_now

STOCK_STATUSES = {"available", "low", "out", "made_to_order"}


def media_url(path: str | None) -> str | None:
    """Normaliza una ruta de medio para devolverla como URL absoluta desde la raíz web."""
    if not path:
        return None
    return "/" + str(path).lstrip("/")


class TipsScalableRequestHandler(TipsAppRequestHandler):
    """Extensiones orientadas a módulos escalables del panel."""

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
        items = []
        for row in rows:
            item = dict(row)
            item["primary_image"] = media_url(item.get("primary_image"))
            items.append(item)
        self._json({"items": items})

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
        items = []
        for row in rows:
            item = dict(row)
            item["primary_image"] = media_url(item.get("primary_image"))
            items.append(item)
        self._json({"user": user, "items": items})

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
        items = []
        for row in rows:
            item = dict(row)
            item["path"] = media_url(item.get("path"))
            items.append(item)
        self._json({"product": dict(product), "items": items, "max_images": MAX_PRODUCT_IMAGES})

    def _create_product(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Crea un producto y su variante inicial dentro de una sola transacción."""
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        price = data.get("base_price_cents")
        stock = data.get("stock_quantity", 0)
        category_id = data.get("category_id")
        status = str(data.get("stock_status", "available")).strip()
        option_summary = str(data.get("option_summary", "Estándar")).strip()[:120]

        if not 2 <= len(name) <= 180 or len(description) > 5000:
            self._json({"error": "Revisa el nombre y la descripción."}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(price, int) or price < 0 or price > 1_000_000_000:
            self._json({"error": "Precio inválido."}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(stock, int) or stock < 0 or stock > 1_000_000:
            self._json({"error": "Inventario inválido."}, HTTPStatus.BAD_REQUEST)
            return
        if status not in STOCK_STATUSES:
            self._json({"error": "Estado de inventario inválido."}, HTTPStatus.BAD_REQUEST)
            return
        if category_id is not None and not isinstance(category_id, int):
            self._json({"error": "Categoría inválida."}, HTTPStatus.BAD_REQUEST)
            return

        stamp = iso(utc_now())
        with transaction(self.settings) as db:
            if category_id is not None:
                category = db.execute("SELECT id FROM categories WHERE id=? AND is_active=1", (category_id,)).fetchone()
                if not category:
                    self._json({"error": "Categoría no encontrada."}, HTTPStatus.BAD_REQUEST)
                    return

            base_slug = _slugify(name)
            slug = base_slug
            suffix = 2
            while db.execute("SELECT 1 FROM products WHERE slug=?", (slug,)).fetchone():
                slug = f"{base_slug}-{suffix}"
                suffix += 1

            cursor = db.execute(
                """INSERT INTO products(
                    category_id,name,slug,description,base_price_cents,currency,stock_status,is_active,created_at,updated_at
                ) VALUES(?,?,?,?,?,'USD',?,1,?,?)""",
                (category_id, name, slug, description, price, status, stamp, stamp),
            )
            product_id = cursor.lastrowid
            sku = f"TIPS-{product_id:04d}-{secrets.token_hex(2).upper()}"
            db.execute(
                """INSERT INTO product_variants(
                    product_id,sku,option_summary,price_cents,stock_quantity,is_active,created_at,updated_at
                ) VALUES(?,?,?,NULL,?,1,?,?)""",
                (product_id, sku, option_summary or "Estándar", stock, stamp, stamp),
            )
            self._audit(
                db,
                user,
                "create",
                "product",
                str(product_id),
                {"name": name, "category_id": category_id, "stock_status": status},
            )

        self._json({"ok": True, "id": product_id, "slug": slug}, HTTPStatus.CREATED)

    def _update_product(self, user: dict[str, object], data: dict[str, object]) -> None:
        """Valida y actualiza datos de un producto y su variante principal."""
        product_id = data.get("id")
        if not isinstance(product_id, int):
            self._json({"error": "Producto inválido."}, HTTPStatus.BAD_REQUEST)
            return

        with transaction(self.settings) as db:
            current = db.execute(
                "SELECT id,name,description,base_price_cents,stock_status,is_active,category_id FROM products WHERE id=?",
                (product_id,),
            ).fetchone()
            if not current:
                self._json({"error": "Producto no encontrado."}, HTTPStatus.NOT_FOUND)
                return

            name = str(data.get("name", current["name"])).strip()
            description = str(data.get("description", current["description"])).strip()
            price = data.get("base_price_cents", current["base_price_cents"])
            status = str(data.get("stock_status", current["stock_status"])).strip()
            active = int(bool(data.get("is_active", current["is_active"])))
            stock = data.get("stock_quantity")
            category_id = data.get("category_id", current["category_id"])

            if not 2 <= len(name) <= 180 or len(description) > 5000:
                self._json({"error": "Revisa el nombre y la descripción."}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(price, int) or price < 0 or price > 1_000_000_000:
                self._json({"error": "Precio inválido."}, HTTPStatus.BAD_REQUEST)
                return
            if status not in STOCK_STATUSES:
                self._json({"error": "Estado de inventario inválido."}, HTTPStatus.BAD_REQUEST)
                return
            if stock is not None and (not isinstance(stock, int) or stock < 0 or stock > 1_000_000):
                self._json({"error": "Cantidad de inventario inválida."}, HTTPStatus.BAD_REQUEST)
                return
            if category_id is not None and not isinstance(category_id, int):
                self._json({"error": "Categoría inválida."}, HTTPStatus.BAD_REQUEST)
                return
            if category_id is not None:
                category = db.execute("SELECT id FROM categories WHERE id=? AND is_active=1", (category_id,)).fetchone()
                if not category:
                    self._json({"error": "La categoría seleccionada no existe o está inactiva."}, HTTPStatus.BAD_REQUEST)
                    return

            stamp = iso(utc_now())
            db.execute(
                "UPDATE products SET category_id=?,name=?,description=?,base_price_cents=?,stock_status=?,is_active=?,updated_at=? WHERE id=?",
                (category_id, name, description, price, status, active, stamp, product_id),
            )

            if "stock_quantity" in data:
                variant = db.execute(
                    "SELECT id,stock_quantity FROM product_variants WHERE product_id=? ORDER BY id LIMIT 1",
                    (product_id,),
                ).fetchone()
                if variant:
                    old_stock = variant["stock_quantity"]
                    db.execute(
                        "UPDATE product_variants SET stock_quantity=?,updated_at=? WHERE id=?",
                        (stock, stamp, variant["id"]),
                    )
                    if stock is not None and old_stock is not None and stock != old_stock:
                        db.execute(
                            "INSERT INTO inventory_movements(variant_id,delta,reason,created_by,created_at) VALUES(?,?,'ajuste administrativo',?,?)",
                            (variant["id"], stock - old_stock, user["id"], stamp),
                        )

            self._audit(
                db,
                user,
                "update",
                "product",
                str(product_id),
                {"name": name, "category_id": category_id, "stock_status": status},
            )

        self._json({"ok": True, "id": product_id})
