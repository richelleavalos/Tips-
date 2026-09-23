"""Servidor HTTP base de Tips: rutas públicas, autenticación, carrito, sesiones y utilidades de respuesta."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlparse

from .config import BASE_DIR, Settings
from .database import connect, transaction
from .frontend_paths import ASSET_ROUTES, VIEW_ROUTES
from .security import (
    RateLimiter, create_csrf_token, hash_password, is_allowed_origin,
    new_session_token, security_headers, session_token_hash,
    validate_search_term, verify_csrf_token, verify_password
)

PUBLIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".avif"}
PRIVATE_TOP_LEVEL = {"backend", "data", "sql", "tests", "scripts", ".git", ".github"}
SESSION_COOKIE = "tips_session"
EMAIL_RE = re.compile(r"^[^@\s]{1,120}@[^@\s]{1,180}\.[^@\s]{2,40}$")


def utc_now() -> datetime:
    """Devuelve la hora actual en UTC para persistencia y comparaciones de sesión."""
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Normaliza una fecha UTC al formato ISO usado por SQLite."""
    return dt.replace(microsecond=0).isoformat()


class TipsRequestHandler(SimpleHTTPRequestHandler):
    """Encapsula la responsabilidad de TipsRequestHandler dentro de la arquitectura de Tips."""
    server_version = "Tips"
    settings: Settings
    rate_limiter: RateLimiter

    def end_headers(self) -> None:
        """Añade cabeceras de seguridad y caché antes de cerrar los encabezados HTTP."""
        for key, value in security_headers().items():
            self.send_header(key, value)
        self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/") else "public, max-age=300")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        """Responde preflight CORS aplicando origen permitido y rate limiting."""
        if not self._rate_limit():
            return
        origin = self.headers.get("Origin")
        if not is_allowed_origin(origin, self.settings.allowed_origins):
            self._json({"error": "Origen no permitido."}, HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()

    def do_GET(self) -> None:
        """Enruta solicitudes GET hacia la API o hacia recursos públicos."""
        if not self._rate_limit():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self._serve_public(parsed.path)

    def do_POST(self) -> None:
        """Enruta solicitudes POST de API después de validar seguridad de mutación."""
        if not self._rate_limit():
            return
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
            return
        if not self._validate_mutation_request():
            return
        self._handle_api_post(path)

    def _rate_limit(self) -> bool:
        """Aplica el límite de solicitudes por IP y ruta."""
        client_ip = self.headers.get("CF-Connecting-IP") or self.client_address[0]
        path = urlparse(self.path).path
        limit_key = f"{client_ip}:{path}"
        if self.rate_limiter.allow(limit_key):
            return True
        self._json({"error": "Demasiadas solicitudes. Intenta de nuevo en un momento."}, HTTPStatus.TOO_MANY_REQUESTS)
        return False

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        """Despacha las rutas GET que pertenecen a esta capa y delega el resto a la clase padre."""
        if path == "/api/health":
            self._json({"status": "ok", "service": "tips"})
            return
        if path == "/api/csrf":
            token = self._ensure_session()
            self._json({"csrf_token": create_csrf_token(token, self.settings.secret_key)})
            return
        if path == "/api/categories":
            with connect(self.settings) as db:
                rows = db.execute("SELECT id,name,slug FROM categories WHERE is_active=1 ORDER BY sort_order,name").fetchall()
            self._json({"items": [dict(r) for r in rows]})
            return
        if path == "/api/products":
            self._get_products(query)
            return
        if path.startswith("/api/products/"):
            self._get_product_detail(path.rsplit("/", 1)[-1])
            return
        if path == "/api/portfolio":
            with connect(self.settings) as db:
                rows = db.execute(
                    """SELECT id,title,slug,category,summary,location,completed_year
                    FROM portfolio_projects WHERE is_published=1 ORDER BY sort_order,id DESC LIMIT 100"""
                ).fetchall()
            self._json({"items": [dict(r) for r in rows]})
            return
        if path.startswith("/api/portfolio/"):
            self._get_portfolio_detail(path.rsplit("/", 1)[-1])
            return
        if path == "/api/cart":
            self._json(self._cart_payload(self._ensure_session()))
            return
        if path == "/api/auth/me":
            user = self._current_user()
            self._json({"authenticated": bool(user), "user": user})
            return
        if path == "/api/admin/overview":
            user = self._require_admin()
            if not user:
                return
            self._admin_overview(user)
            return
        self._json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)

    def _handle_api_post(self, path: str) -> None:
        """Despacha las rutas POST que pertenecen a esta capa y delega el resto a la clase padre."""
        data = self._read_json()
        if data is None:
            return
        if path == "/api/auth/register":
            self._register(data)
            return
        if path == "/api/auth/login":
            self._login(data)
            return
        if path == "/api/auth/logout":
            self._logout()
            return
        if path == "/api/quotes":
            self._create_quote(data)
            return
        if path == "/api/cart/items":
            self._add_cart_item(data)
            return
        if path == "/api/cart/items/change":
            self._change_cart_item(data)
            return
        if path == "/api/checkout/mock":
            self._mock_checkout(data)
            return
        self._json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)

    def _get_products(self, query: dict[str, list[str]]) -> None:
        """Lista productos activos aplicando búsqueda y filtro de categoría."""
        try:
            search = validate_search_term(query.get("search", [""])[0])
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        category = query.get("category", [""])[0].strip()
        sql = """SELECT p.id,p.name,p.slug,p.description,p.base_price_cents,p.currency,p.stock_status,
                    c.name AS category_name,c.slug AS category_slug,
                    (SELECT v.id FROM product_variants v WHERE v.product_id=p.id AND v.is_active=1 ORDER BY v.id LIMIT 1) AS first_variant_id,
                    (SELECT v.stock_quantity FROM product_variants v WHERE v.product_id=p.id AND v.is_active=1 ORDER BY v.id LIMIT 1) AS stock_quantity
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
        self._json({"items": [dict(r) for r in rows]})

    def _get_product_detail(self, raw_id: str) -> None:
        """Devuelve variantes y personalizaciones de un producto activo."""
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
            customizations = db.execute(
                """SELECT c.id,c.name,c.input_type,c.is_required,cv.id AS value_id,cv.label,cv.price_delta_cents
                FROM product_customizations pc JOIN customizations c ON c.id=pc.customization_id
                LEFT JOIN customization_values cv ON cv.customization_id=c.id AND cv.is_active=1
                WHERE pc.product_id=? AND c.is_active=1 ORDER BY pc.sort_order,c.id,cv.id""",
                (product_id,),
            ).fetchall()
        payload = dict(product)
        payload["variants"] = [dict(v) for v in variants]
        grouped: dict[int, dict[str, object]] = {}
        for row in customizations:
            gid = row["id"]
            grouped.setdefault(gid, {"id": gid, "name": row["name"], "input_type": row["input_type"], "is_required": row["is_required"], "values": []})
            if row["value_id"] is not None:
                grouped[gid]["values"].append({"id": row["value_id"], "label": row["label"], "price_delta_cents": row["price_delta_cents"]})
        payload["customizations"] = list(grouped.values())
        self._json(payload)

    def _get_portfolio_detail(self, raw_id: str) -> None:
        """Devuelve el detalle público de un proyecto publicado."""
        try:
            project_id = int(raw_id)
        except ValueError:
            self._json({"error": "Proyecto inválido."}, HTTPStatus.BAD_REQUEST)
            return
        with connect(self.settings) as db:
            row = db.execute(
                """SELECT id,title,slug,category,summary,description,location,completed_year,specifications_json
                   FROM portfolio_projects WHERE id=? AND is_published=1""",
                (project_id,),
            ).fetchone()
        if not row:
            self._json({"error": "Proyecto no encontrado."}, HTTPStatus.NOT_FOUND)
            return
        payload = dict(row)
        try:
            payload["specifications"] = json.loads(payload.pop("specifications_json") or "{}")
        except json.JSONDecodeError:
            payload["specifications"] = {}
        self._json(payload)

    def _register(self, data: dict[str, object]) -> None:
        """Valida datos, crea una cuenta de cliente y la vincula con la sesión actual."""
        display_name = str(data.get("display_name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not 2 <= len(display_name) <= 120 or not EMAIL_RE.match(email):
            self._json({"error": "Revisa el nombre y correo."}, HTTPStatus.BAD_REQUEST)
            return
        try:
            password_hash = hash_password(password)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        now = iso(utc_now())
        token = self._ensure_session()
        try:
            with transaction(self.settings) as db:
                cur = db.execute(
                    "INSERT INTO users(email,password_hash,display_name,role,is_active,created_at,updated_at) VALUES(?,?,?,'user',1,?,?)",
                    (email, password_hash, display_name, now, now),
                )
                user_id = cur.lastrowid
                db.execute("UPDATE sessions SET user_id=? WHERE token_hash=?", (user_id, session_token_hash(token)))
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                self._json({"error": "Ya existe una cuenta con ese correo."}, HTTPStatus.CONFLICT)
                return
            raise
        self._json({"user": {"id": user_id, "email": email, "display_name": display_name, "role": "user"}}, HTTPStatus.CREATED)

    def _login(self, data: dict[str, object]) -> None:
        """Autentica credenciales, controla bloqueos y vincula la sesión al usuario."""
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not EMAIL_RE.match(email) or not password:
            self._json({"error": "Credenciales inválidas."}, HTTPStatus.UNAUTHORIZED)
            return
        now = utc_now()
        token = self._ensure_session()
        with transaction(self.settings) as db:
            user = db.execute(
                "SELECT id,email,password_hash,display_name,role,is_active,failed_login_count,locked_until FROM users WHERE email=?",
                (email,),
            ).fetchone()
            if not user or not user["password_hash"] or not user["is_active"]:
                self._json({"error": "Credenciales inválidas."}, HTTPStatus.UNAUTHORIZED)
                return
            if user["locked_until"]:
                try:
                    locked_until = datetime.fromisoformat(user["locked_until"])
                except ValueError:
                    locked_until = now
                if locked_until > now:
                    self._json({"error": "Cuenta temporalmente bloqueada. Intenta más tarde."}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
            if not verify_password(password, user["password_hash"]):
                failures = int(user["failed_login_count"]) + 1
                locked = iso(now + timedelta(minutes=15)) if failures >= 5 else None
                db.execute("UPDATE users SET failed_login_count=?,locked_until=?,updated_at=? WHERE id=?", (failures, locked, iso(now), user["id"]))
                self._json({"error": "Credenciales inválidas."}, HTTPStatus.UNAUTHORIZED)
                return
            db.execute("UPDATE users SET failed_login_count=0,locked_until=NULL,updated_at=? WHERE id=?", (iso(now), user["id"]))
            db.execute("UPDATE sessions SET user_id=?,last_seen_at=? WHERE token_hash=?", (user["id"], iso(now), session_token_hash(token)))
        self._json({"user": {"id": user["id"], "email": user["email"], "display_name": user["display_name"], "role": user["role"]}})

    def _logout(self) -> None:
        """Revoca la sesión actual y borra la cookie del navegador."""
        token = self._read_session_cookie()
        if token:
            with transaction(self.settings) as db:
                db.execute("UPDATE sessions SET revoked_at=? WHERE token_hash=?", (iso(utc_now()), session_token_hash(token)))
        self._pending_set_cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        self._json({"ok": True})

    def _create_quote(self, data: dict[str, object]) -> None:
        """Valida y guarda una solicitud pública de cotización."""
        required = ("name", "contact", "project_type", "message")
        if any(not isinstance(data.get(k), str) or not str(data[k]).strip() for k in required):
            self._json({"error": "Completa los campos obligatorios."}, HTTPStatus.BAD_REQUEST)
            return
        values = {k: str(data[k]).strip() for k in required}
        if len(values["name"]) > 120 or len(values["contact"]) > 180 or len(values["message"]) > 3000:
            self._json({"error": "Uno de los campos excede el tamaño permitido."}, HTTPStatus.BAD_REQUEST)
            return
        with transaction(self.settings) as db:
            cur = db.execute(
                "INSERT INTO quote_requests(name,contact,project_type,message,status,created_at) VALUES(?,?,?,?,'new',?)",
                (values["name"], values["contact"], values["project_type"], values["message"], iso(utc_now())),
            )
            quote_id = cur.lastrowid
        self._json({"id": quote_id, "status": "received"}, HTTPStatus.CREATED)

    def _add_cart_item(self, data: dict[str, object]) -> None:
        """Valida variante, cantidad y personalizaciones antes de agregar al carrito."""
        variant_id, quantity = data.get("variant_id"), data.get("quantity", 1)
        customization_ids = data.get("customization_value_ids", [])
        if not isinstance(variant_id, int) or not isinstance(quantity, int) or not 1 <= quantity <= 25:
            self._json({"error": "Producto o cantidad inválida."}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(customization_ids, list) or any(not isinstance(i, int) for i in customization_ids):
            self._json({"error": "Personalización inválida."}, HTTPStatus.BAD_REQUEST)
            return
        raw_token = self._ensure_session()
        token_hash = session_token_hash(raw_token)
        with transaction(self.settings) as db:
            session = db.execute("SELECT id FROM sessions WHERE token_hash=?", (token_hash,)).fetchone()
            variant = db.execute(
                """SELECT v.id,v.product_id,v.price_cents,v.stock_quantity,v.is_active,p.base_price_cents,p.currency,p.is_active AS product_active
                FROM product_variants v JOIN products p ON p.id=v.product_id WHERE v.id=?""",
                (variant_id,),
            ).fetchone()
            if not variant or not variant["is_active"] or not variant["product_active"]:
                self._json({"error": "El producto no está disponible."}, HTTPStatus.NOT_FOUND)
                return
            if variant["stock_quantity"] is not None and variant["stock_quantity"] < quantity:
                self._json({"error": "No hay suficiente inventario."}, HTTPStatus.CONFLICT)
                return
            adjustment = 0
            snapshot = []
            if customization_ids:
                marks = ",".join("?" for _ in customization_ids)
                rows = db.execute(
                    f"""SELECT cv.id,cv.label,cv.price_delta_cents,c.name FROM customization_values cv
                    JOIN customizations c ON c.id=cv.customization_id JOIN product_customizations pc ON pc.customization_id=c.id
                    WHERE pc.product_id=? AND cv.id IN ({marks}) AND c.is_active=1 AND cv.is_active=1""",
                    (variant["product_id"], *customization_ids),
                ).fetchall()
                if len(rows) != len(set(customization_ids)):
                    self._json({"error": "Una personalización no pertenece al producto."}, HTTPStatus.BAD_REQUEST)
                    return
                for row in rows:
                    adjustment += row["price_delta_cents"]
                    snapshot.append({"id": row["id"], "grupo": row["name"], "opcion": row["label"], "ajuste_centavos": row["price_delta_cents"]})
            unit = (variant["price_cents"] if variant["price_cents"] is not None else variant["base_price_cents"]) + adjustment
            cart = db.execute("SELECT id FROM carts WHERE session_id=? AND status='active'", (session["id"],)).fetchone()
            if cart:
                cart_id = cart["id"]
            else:
                cur = db.execute(
                    "INSERT INTO carts(session_id,status,currency,created_at,updated_at) VALUES(?,'active',?,?,?)",
                    (session["id"], variant["currency"], iso(utc_now()), iso(utc_now())),
                )
                cart_id = cur.lastrowid
            db.execute(
                "INSERT INTO cart_items(cart_id,variant_id,quantity,unit_price_cents,customization_json,created_at) VALUES(?,?,?,?,?,?)",
                (cart_id, variant_id, quantity, unit, json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), iso(utc_now())),
            )
            db.execute("UPDATE carts SET updated_at=? WHERE id=?", (iso(utc_now()), cart_id))
        self._json(self._cart_payload(raw_token), HTTPStatus.CREATED)

    def _change_cart_item(self, data: dict[str, object]) -> None:
        """Incrementa, reduce o elimina una línea del carrito activo."""
        item_id = data.get("item_id")
        action = data.get("action")
        if not isinstance(item_id, int) or action not in {"inc", "dec", "remove"}:
            self._json({"error": "Operación de carrito inválida."}, HTTPStatus.BAD_REQUEST)
            return
        raw = self._ensure_session()
        with transaction(self.settings) as db:
            row = db.execute(
                """SELECT ci.id,ci.quantity,ci.variant_id,v.stock_quantity FROM cart_items ci
                JOIN carts c ON c.id=ci.cart_id JOIN sessions s ON s.id=c.session_id
                JOIN product_variants v ON v.id=ci.variant_id
                WHERE ci.id=? AND c.status='active' AND s.token_hash=?""",
                (item_id, session_token_hash(raw)),
            ).fetchone()
            if not row:
                self._json({"error": "Artículo no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            if action == "remove" or (action == "dec" and row["quantity"] <= 1):
                db.execute("DELETE FROM cart_items WHERE id=?", (item_id,))
            elif action == "inc":
                new_qty = row["quantity"] + 1
                if new_qty > 25 or (row["stock_quantity"] is not None and new_qty > row["stock_quantity"]):
                    self._json({"error": "No hay más unidades disponibles."}, HTTPStatus.CONFLICT)
                    return
                db.execute("UPDATE cart_items SET quantity=? WHERE id=?", (new_qty, item_id))
            else:
                db.execute("UPDATE cart_items SET quantity=? WHERE id=?", (row["quantity"] - 1, item_id))
        self._json(self._cart_payload(raw))

    def _mock_checkout(self, data: dict[str, object]) -> None:
        """Convierte el carrito autenticado en un pedido pagado mediante el proveedor de demostración."""
        user = self._current_user()
        if not user:
            self._json({"error": "Debes iniciar sesión para completar la compra."}, HTTPStatus.UNAUTHORIZED)
            return
        customer_name = str(data.get("customer_name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        phone = str(data.get("phone", "")).strip()
        shipping = data.get("shipping_address", {})
        if not customer_name or not EMAIL_RE.match(email) or not phone or not isinstance(shipping, dict) or not str(shipping.get("address", "")).strip():
            self._json({"error": "Completa correctamente los datos de envío."}, HTTPStatus.BAD_REQUEST)
            return
        raw = self._ensure_session()
        token_hash = session_token_hash(raw)
        now = iso(utc_now())
        with transaction(self.settings) as db:
            cart = db.execute(
                """SELECT c.id,c.currency FROM carts c JOIN sessions s ON s.id=c.session_id
                WHERE s.token_hash=? AND c.status='active'""",
                (token_hash,),
            ).fetchone()
            if not cart:
                self._json({"error": "El carrito está vacío."}, HTTPStatus.BAD_REQUEST)
                return
            items = db.execute(
                """SELECT ci.id,ci.variant_id,ci.quantity,ci.unit_price_cents,ci.customization_json,
                p.name,v.sku,v.stock_quantity FROM cart_items ci JOIN product_variants v ON v.id=ci.variant_id
                JOIN products p ON p.id=v.product_id WHERE ci.cart_id=?""",
                (cart["id"],),
            ).fetchall()
            if not items:
                self._json({"error": "El carrito está vacío."}, HTTPStatus.BAD_REQUEST)
                return
            for item in items:
                if item["stock_quantity"] is not None and item["stock_quantity"] < item["quantity"]:
                    self._json({"error": f"Inventario insuficiente para {item['name']}."}, HTTPStatus.CONFLICT)
                    return
            subtotal = sum(i["quantity"] * i["unit_price_cents"] for i in items)
            public_id = f"TIPS-{utc_now().strftime('%y%m%d')}-{secrets.token_hex(2).upper()}"
            cur = db.execute(
                """INSERT INTO orders(public_id,user_id,email,customer_name,phone,status,currency,subtotal_cents,shipping_cents,discount_cents,total_cents,shipping_address_json,created_at,updated_at)
                VALUES(?,?,?,?,?,'paid',?,?,0,0,?,?,?,?)""",
                (public_id, user["id"], email, customer_name, phone, cart["currency"], subtotal, subtotal, json.dumps(shipping, ensure_ascii=False), now, now),
            )
            order_id = cur.lastrowid
            for item in items:
                db.execute(
                    """INSERT INTO order_items(order_id,variant_id,product_name,sku,quantity,unit_price_cents,customization_json)
                    VALUES(?,?,?,?,?,?,?)""",
                    (order_id, item["variant_id"], item["name"], item["sku"], item["quantity"], item["unit_price_cents"], item["customization_json"]),
                )
                if item["stock_quantity"] is not None:
                    db.execute("UPDATE product_variants SET stock_quantity=stock_quantity-?,updated_at=? WHERE id=?", (item["quantity"], now, item["variant_id"]))
                    db.execute("INSERT INTO inventory_movements(variant_id,delta,reason,reference_type,reference_id,created_at) VALUES(?,?,'venta demo','order',?,?)", (item["variant_id"], -item["quantity"], order_id, now))
            db.execute(
                """INSERT INTO payments(order_id,provider,provider_payment_id,status,amount_cents,currency,idempotency_key,provider_payload_json,created_at,updated_at)
                VALUES(?,'mock',?,'paid',?,?,?,?,?,?,?)""",
                (order_id, f"mock_{secrets.token_hex(6)}", subtotal, cart["currency"], secrets.token_urlsafe(20), '{"mode":"demo"}', now, now),
            )
            db.execute("UPDATE carts SET status='converted',updated_at=? WHERE id=?", (now, cart["id"]))
        self._json({"public_id": public_id, "total_cents": subtotal, "currency": cart["currency"], "status": "paid", "payment_provider": "mock"}, HTTPStatus.CREATED)

    def _admin_overview(self, user: dict[str, object]) -> None:
        """Construye el resumen administrativo básico usado como compatibilidad."""
        with connect(self.settings) as db:
            metrics = {
                "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                "products": db.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0],
                "quotes": db.execute("SELECT COUNT(*) FROM quote_requests").fetchone()[0],
                "sales_cents": db.execute("SELECT COALESCE(SUM(total_cents),0) FROM orders WHERE status IN('paid','processing','ready','shipped','completed')").fetchone()[0],
            }
            orders = db.execute("SELECT public_id,customer_name,status,total_cents,created_at FROM orders ORDER BY id DESC LIMIT 8").fetchall()
            quotes = db.execute("SELECT id,name,project_type,status,created_at FROM quote_requests ORDER BY id DESC LIMIT 8").fetchall()
            products = db.execute(
                """SELECT p.id,p.name,p.base_price_cents,p.stock_status,c.name AS category_name,
                (SELECT v.stock_quantity FROM product_variants v WHERE v.product_id=p.id AND v.is_active=1 ORDER BY v.id LIMIT 1) AS stock_quantity
                FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.is_active=1 ORDER BY p.sort_order,p.name LIMIT 50"""
            ).fetchall()
        self._json({"user": user, "metrics": metrics, "orders": [dict(r) for r in orders], "quotes": [dict(r) for r in quotes], "products": [dict(r) for r in products]})

    def _cart_payload(self, raw_token: str) -> dict[str, object]:
        """Construye la representación JSON del carrito activo y calcula su subtotal."""
        with connect(self.settings) as db:
            cart = db.execute(
                """SELECT c.id,c.currency FROM carts c JOIN sessions s ON s.id=c.session_id
                WHERE s.token_hash=? AND c.status='active'""",
                (session_token_hash(raw_token),),
            ).fetchone()
            if not cart:
                return {"items": [], "currency": "USD", "subtotal_cents": 0}
            rows = db.execute(
                """SELECT ci.id,ci.quantity,ci.unit_price_cents,ci.customization_json,p.name,v.sku,v.option_summary
                FROM cart_items ci JOIN product_variants v ON v.id=ci.variant_id JOIN products p ON p.id=v.product_id
                WHERE ci.cart_id=? ORDER BY ci.id DESC""",
                (cart["id"],),
            ).fetchall()
        items = []
        subtotal = 0
        for row in rows:
            item = dict(row)
            item["customizations"] = json.loads(item.pop("customization_json") or "[]")
            item["line_total_cents"] = item["quantity"] * item["unit_price_cents"]
            subtotal += item["line_total_cents"]
            items.append(item)
        return {"items": items, "currency": cart["currency"], "subtotal_cents": subtotal}

    def _current_user(self) -> dict[str, object] | None:
        """Obtiene el usuario activo vinculado a la cookie de sesión válida."""
        raw = self._read_session_cookie()
        if not raw:
            return None
        with connect(self.settings) as db:
            row = db.execute(
                """SELECT u.id,u.email,u.display_name,u.role FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.is_active=1 AND s.expires_at>?""",
                (session_token_hash(raw), iso(utc_now())),
            ).fetchone()
        return dict(row) if row else None

    def _require_admin(self) -> dict[str, object] | None:
        """Exige una sesión de administrador o responde con el error HTTP adecuado."""
        user = self._current_user()
        if not user:
            self._json({"error": "Autenticación requerida."}, HTTPStatus.UNAUTHORIZED)
            return None
        if user["role"] != "admin":
            self._json({"error": "Permisos de administrador requeridos."}, HTTPStatus.FORBIDDEN)
            return None
        return user

    def _validate_mutation_request(self) -> bool:
        """Valida origen y token CSRF antes de aceptar operaciones de escritura."""
        origin = self.headers.get("Origin")
        if not is_allowed_origin(origin, self.settings.allowed_origins):
            self._json({"error": "Origen no permitido."}, HTTPStatus.FORBIDDEN)
            return False
        session = self._read_session_cookie()
        csrf = self.headers.get("X-CSRF-Token")
        if not session or not csrf or not verify_csrf_token(csrf, session, self.settings.secret_key):
            self._json({"error": "Token CSRF inválido o vencido."}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def _ensure_session(self) -> str:
        """Reutiliza una sesión válida o crea una nueva cookie y registro de sesión."""
        raw = self._read_session_cookie()
        now = utc_now()
        if raw:
            with connect(self.settings) as db:
                row = db.execute("SELECT expires_at,revoked_at FROM sessions WHERE token_hash=?", (session_token_hash(raw),)).fetchone()
            if row and not row["revoked_at"]:
                try:
                    expires = datetime.fromisoformat(row["expires_at"])
                except ValueError:
                    expires = now - timedelta(seconds=1)
                if expires > now:
                    return raw
        raw = new_session_token()
        expires = now + timedelta(seconds=self.settings.session_ttl_seconds)
        with transaction(self.settings) as db:
            db.execute(
                "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at) VALUES(?,NULL,?,?,?)",
                (session_token_hash(raw), iso(now), iso(expires), iso(now)),
            )
        cookie = f"{SESSION_COOKIE}={raw}; Path=/; HttpOnly; SameSite=Lax; Max-Age={self.settings.session_ttl_seconds}"
        if self.settings.secure_cookies:
            cookie += "; Secure"
        self._pending_set_cookie = cookie
        return raw

    def _read_session_cookie(self) -> str | None:
        """Extrae de forma segura el token de sesión desde la cabecera Cookie."""
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _read_json(self) -> dict[str, object] | None:
        """Lee y valida un cuerpo JSON respetando Content-Type y tamaño máximo."""
        if self.headers.get_content_type() != "application/json":
            self._json({"error": "Content-Type debe ser application/json."}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json({"error": "Content-Length inválido."}, HTTPStatus.BAD_REQUEST)
            return None
        if length <= 0 or length > self.settings.max_request_bytes:
            self._json({"error": "Tamaño de solicitud inválido."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json({"error": "JSON inválido."}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(data, dict):
            self._json({"error": "El cuerpo debe ser un objeto JSON."}, HTTPStatus.BAD_REQUEST)
            return None
        return data

    def _json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        """Serializa una respuesta JSON, aplica CORS y envía cookies pendientes."""
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        origin = self.headers.get("Origin")
        if origin and is_allowed_origin(origin, self.settings.allowed_origins):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        pending = getattr(self, "_pending_set_cookie", None)
        if pending:
            self.send_header("Set-Cookie", pending)
            self._pending_set_cookie = None
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_public(self, requested_path: str) -> None:
        """Protege vistas privadas por rol antes de delegar el servido físico del recurso."""
        mapped_path = VIEW_ROUTES.get(requested_path) or ASSET_ROUTES.get(requested_path)
        relative = requested_path.lstrip("/")
        candidate = (BASE_DIR / (mapped_path or relative)).resolve()
        try:
            resolved = candidate.relative_to(BASE_DIR)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        first = resolved.parts[0] if resolved.parts else ""
        if first in PRIVATE_TOP_LEVEL or first.startswith("."):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not mapped_path and (not relative or first in {"frontend", "public", "admin", "user"}):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.is_file() or candidate.suffix.lower() not in PUBLIC_EXTENSIONS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def create_server(settings: Settings) -> ThreadingHTTPServer:
    """Crea un servidor HTTP multihilo configurando settings y rate limiter en el handler."""
    handler = type("ConfiguredTipsRequestHandler", (TipsRequestHandler,), {
        "settings": settings,
        "rate_limiter": RateLimiter(settings.rate_limit_per_minute),
    })
    return ThreadingHTTPServer((settings.host, settings.port), handler)
