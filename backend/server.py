"""Servidor HTTP base de Tips: rutas públicas, autenticación, carrito, sesiones y utilidades de respuesta."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
import ipaddress
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlparse

from .config import BASE_DIR, Settings
from .database import connect, transaction
from .frontend_paths import ASSET_ROUTES, VIEW_ROUTES
from .security import (
    FieldCipher, RateLimiter, create_csrf_token, hash_password, is_allowed_origin,
    new_session_token, new_totp_secret, security_headers, session_token_hash, token_digest,
    totp_uri, validate_search_term, verify_csrf_token, verify_password, verify_totp
)

PUBLIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".avif"}
PRIVATE_TOP_LEVEL = {"backend", "data", "sql", "tests", "scripts", ".git", ".github"}
SESSION_COOKIE = "tips_session"
EMAIL_RE = re.compile(r"^[^@\s]{1,120}@[^@\s]{1,180}\.[^@\s]{2,40}$")
ERROR_DIR = BASE_DIR / "frontend" / "global" / "errors"


class SessionChangedError(Exception):
    """La sesión cambió mientras se estaba autenticando la solicitud."""


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clave JSON duplicada")
        result[key] = value
    return result


def finite_json_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Número JSON no finito")
    return number


def bounded_json_integer(value):
    number = int(value)
    if not -(2**63) <= number < 2**63:
        raise ValueError("Entero JSON fuera de rango")
    return number


def utc_now() -> datetime:
    """Devuelve la hora actual en UTC para persistencia y comparaciones de sesión."""
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Normaliza una fecha UTC al formato ISO usado por SQLite."""
    return dt.replace(microsecond=0).isoformat()


class TipsRequestHandler(SimpleHTTPRequestHandler):
    """Encapsula la responsabilidad de TipsRequestHandler dentro de la arquitectura de Tips."""
    server_version = "Tips"
    sys_version = ""
    settings: Settings
    rate_limiter: RateLimiter
    sensitive_rate_limiter: RateLimiter

    def end_headers(self) -> None:
        """Añade cabeceras de seguridad y caché antes de cerrar los encabezados HTTP."""
        for key, value in security_headers().items():
            self.send_header(key, value)
        self.send_header("Cache-Control", getattr(self, "_cache_control", "no-store"))
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
        """Enruta GET y convierte fallos inesperados en una respuesta controlada."""
        try:
            if not self._rate_limit():
                return
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api_get(parsed.path, parse_qs(parsed.query))
                return
            self._serve_public(parsed.path)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._unexpected_error()

    def do_HEAD(self) -> None:
        # SimpleHTTPRequestHandler resolvería la ruta contra el directorio de
        # trabajo. HEAD debe usar el mismo acceso a vistas y recursos que GET.
        if not self._rate_limit():
            return
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
            return
        self._serve_public(path)

    def do_POST(self) -> None:
        """Enruta POST; los webhooks se autentican por firma y no por CSRF."""
        try:
            if not self._rate_limit():
                return
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if path.startswith("/api/payments/webhook/"):
                self._handle_payment_webhook(path)
                return
            if not self._validate_mutation_request():
                return
            self._handle_api_post(path)
        except SessionChangedError:
            self._json({"error": "La sesión cambió. Recarga la página e inténtalo de nuevo."}, HTTPStatus.CONFLICT)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._unexpected_error()

    def _handle_payment_webhook(self, path: str) -> None:
        """Punto de extensión para la capa de pagos efectiva."""
        self._json({"error": "Webhook no disponible."}, HTTPStatus.NOT_FOUND)

    def _rate_limit(self) -> bool:
        """Aplica el límite de solicitudes por IP y ruta."""
        client_ip = self.client_address[0]
        trusted={value.strip() for value in os.getenv("TIPS_TRUSTED_PROXIES","").split(",") if value.strip()}
        if client_ip in trusted and self.headers.get("CF-Connecting-IP"):
            try:client_ip=str(ipaddress.ip_address(self.headers["CF-Connecting-IP"]))
            except ValueError:pass
        path = urlparse(self.path).path
        limit_key = f"{client_ip}:{path}"
        sensitive_paths = {
            "/api/auth/login", "/api/auth/register", "/api/auth/password-reset/request",
            "/api/auth/password-reset/confirm", "/api/auth/2fa/verify-login", "/api/auth/2fa/enable",
            "/api/checkout/create", "/api/payments/sandbox/complete",
        }
        limiter = self.sensitive_rate_limiter if path in sensitive_paths else self.rate_limiter
        if limiter.allow(limit_key):
            return True
        if path.startswith("/api/"):
            self._json({"error": "Demasiadas solicitudes. Intenta de nuevo en un momento."}, HTTPStatus.TOO_MANY_REQUESTS)
        else:
            self.send_error(HTTPStatus.TOO_MANY_REQUESTS)
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
                    """SELECT p.id,p.title,p.slug,p.category,p.summary,p.location,p.completed_year,
                      cover.path AS cover_path, cover.alt_text AS cover_alt
                    FROM portfolio_projects p
                    LEFT JOIN portfolio_images cover ON cover.id=(
                        SELECT i.id FROM portfolio_images i WHERE i.project_id=p.id ORDER BY i.sort_order,i.id LIMIT 1
                    )
                    WHERE p.is_published=1 ORDER BY p.sort_order,p.id DESC LIMIT 100"""
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
        if path == "/api/auth/2fa/setup":
            self._two_factor_setup()
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
        if path == "/api/auth/2fa/verify-login":
            self._verify_two_factor_login(data)
            return
        if path == "/api/auth/2fa/enable":
            self._enable_two_factor(data)
            return
        if path == "/api/auth/password-reset/request":
            self._request_password_reset(data)
            return
        if path == "/api/auth/password-reset/confirm":
            self._confirm_password_reset(data)
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
            images = db.execute("SELECT path,alt_text FROM portfolio_images WHERE project_id=? ORDER BY sort_order,id", (project_id,)).fetchall()
            project_ids = [item[0] for item in db.execute("SELECT id FROM portfolio_projects WHERE is_published=1 ORDER BY sort_order,id")]
        if not row:
            self._json({"error": "Proyecto no encontrado."}, HTTPStatus.NOT_FOUND)
            return
        payload = dict(row)
        index = project_ids.index(project_id)
        payload.update(images=[dict(image) for image in images], previous_id=project_ids[index-1] if index else None,
                       next_id=project_ids[index+1] if index+1 < len(project_ids) else None)
        try:
            payload["specifications"] = json.loads(payload.pop("specifications_json") or "{}")
        except json.JSONDecodeError:
            payload["specifications"] = {}
        self._json(payload)

    def _register(self, data: dict[str, object]) -> None:
        """Crea una cuenta de cliente y conserva el carrito invitado."""
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
                    "INSERT INTO users(email,password_hash,display_name,role,must_change_password,two_factor_enabled,is_active,created_at,updated_at) VALUES(?,?,?,'user',0,0,1,?,?)",
                    (email, password_hash, display_name, now, now),
                )
                user_id = cur.lastrowid
                rotated_token = self._bind_session_to_user(db, token, user_id)
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                self._json({"error": "Ya existe una cuenta con ese correo."}, HTTPStatus.CONFLICT)
                return
            raise
        self._authenticated_json({"user": {"id": user_id, "email": email, "display_name": display_name, "role": "user", "must_change_password": False, "two_factor_enabled": False}}, rotated_token, HTTPStatus.CREATED)

    def _login(self, data: dict[str, object]) -> None:
        """Valida contraseña, fuerza 2FA cuando está activo y protege fuerza bruta."""
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not EMAIL_RE.match(email) or not password:
            self._json({"error": "Credenciales inválidas."}, HTTPStatus.UNAUTHORIZED)
            return
        now = utc_now()
        token = self._ensure_session()
        with transaction(self.settings) as db:
            user = db.execute(
                "SELECT id,email,password_hash,display_name,role,must_change_password,two_factor_enabled,is_active,failed_login_count,locked_until FROM users WHERE email=?",
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

            if user["two_factor_enabled"]:
                challenge = new_session_token()
                expires = iso(now + timedelta(minutes=self.settings.two_factor_challenge_minutes))
                db.execute("DELETE FROM auth_challenges WHERE user_id=? AND purpose='login_2fa'", (user["id"],))
                db.execute(
                    "INSERT INTO auth_challenges(user_id,challenge_hash,purpose,created_at,expires_at) VALUES(?,?,'login_2fa',?,?)",
                    (user["id"], token_digest(challenge + ":" + token), iso(now), expires),
                )
                self._json({"two_factor_required": True, "challenge_token": challenge})
                return

            rotated_token = self._bind_session_to_user(db, token, user["id"])
            payload = self._user_payload(user)
        self._authenticated_json({"user": payload, "two_factor_setup_required": False}, rotated_token)

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
        cipher = FieldCipher(self.settings.field_encryption_key)
        with transaction(self.settings) as db:
            cur = db.execute(
                "INSERT INTO quote_requests(name,contact,project_type,message,status,created_at) VALUES(?,?,?,?,'new',?)",
                (values["name"], cipher.encrypt(values["contact"], aad="quote-contact"), values["project_type"], cipher.encrypt(values["message"], aad="quote-message"), iso(utc_now())),
            )
            quote_id = cur.lastrowid
        self._json({"id": quote_id, "status": "received"}, HTTPStatus.CREATED)

    def _add_cart_item(self, data: dict[str, object]) -> None:
        """Valida variante, cantidad y personalizaciones antes de agregar al carrito."""
        variant_id, quantity = data.get("variant_id"), data.get("quantity", 1)
        customization_ids = data.get("customization_value_ids", [])
        if type(variant_id) is not int or type(quantity) is not int or not 1 <= quantity <= 25:
            self._json({"error": "Producto o cantidad inválida."}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(customization_ids, list) or len(customization_ids) > 100 or any(type(i) is not int for i in customization_ids):
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
            from .operations import validate_options
            try:
                validate_options(db, variant["product_id"], customization_ids)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            unit = (variant["price_cents"] if variant["price_cents"] is not None else variant["base_price_cents"]) + adjustment
            cart = db.execute("SELECT id FROM carts WHERE session_id=? AND status='active'", (session["id"],)).fetchone()
            if cart:
                cart_id = cart["id"]
            else:
                session_user = db.execute("SELECT user_id FROM sessions WHERE id=?", (session["id"],)).fetchone()
                cur = db.execute(
                    "INSERT INTO carts(session_id,user_id,status,currency,created_at,updated_at) VALUES(?,?,'active',?,?,?)",
                    (session["id"], session_user["user_id"] if session_user else None, variant["currency"], iso(utc_now()), iso(utc_now())),
                )
                cart_id = cur.lastrowid
            snapshot.sort(key=lambda entry: entry["id"])
            serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
            existing_total = db.execute("SELECT COALESCE(SUM(quantity),0) FROM cart_items WHERE cart_id=? AND variant_id=?", (cart_id,variant_id)).fetchone()[0]
            if variant["stock_quantity"] is not None and existing_total+quantity>variant["stock_quantity"]:
                self._json({"error":"La cantidad total supera el inventario disponible."}, HTTPStatus.CONFLICT)
                return
            same = db.execute("SELECT id,quantity FROM cart_items WHERE cart_id=? AND variant_id=? AND customization_json=?", (cart_id,variant_id,serialized)).fetchone()
            if same:
                if same["quantity"]+quantity>25:
                    self._json({"error":"Máximo 25 unidades por selección."},HTTPStatus.CONFLICT)
                    return
                db.execute("UPDATE cart_items SET quantity=quantity+?,unit_price_cents=? WHERE id=?",(quantity,unit,same["id"]))
            else:
                db.execute("INSERT INTO cart_items(cart_id,variant_id,quantity,unit_price_cents,customization_json,created_at) VALUES(?,?,?,?,?,?)",(cart_id,variant_id,quantity,unit,serialized,iso(utc_now())))
            db.execute("UPDATE carts SET updated_at=? WHERE id=?", (iso(utc_now()), cart_id))
        self._json(self._cart_payload(raw_token), HTTPStatus.CREATED)

    def _change_cart_item(self, data: dict[str, object]) -> None:
        """Incrementa, reduce o elimina una línea del carrito activo."""
        item_id = data.get("item_id")
        action = data.get("action")
        if type(item_id) is not int or action not in ("inc", "dec", "remove"):
            self._json({"error": "Operación de carrito inválida."}, HTTPStatus.BAD_REQUEST)
            return
        raw = self._ensure_session()
        with transaction(self.settings) as db:
            row = db.execute(
                """SELECT ci.id,ci.cart_id,ci.quantity,ci.variant_id,v.stock_quantity FROM cart_items ci
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
                total_qty=db.execute("SELECT SUM(quantity) FROM cart_items WHERE cart_id=? AND variant_id=?",(row["cart_id"],row["variant_id"])).fetchone()[0]+1
                if row["stock_quantity"] is not None and total_qty>row["stock_quantity"]:
                    self._json({"error":"La cantidad total supera el inventario disponible."},HTTPStatus.CONFLICT)
                    return
                if new_qty > 25 or (row["stock_quantity"] is not None and new_qty > row["stock_quantity"]):
                    self._json({"error": "No hay más unidades disponibles."}, HTTPStatus.CONFLICT)
                    return
                db.execute("UPDATE cart_items SET quantity=? WHERE id=?", (new_qty, item_id))
            else:
                db.execute("UPDATE cart_items SET quantity=? WHERE id=?", (row["quantity"] - 1, item_id))
        self._json(self._cart_payload(raw))

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
                """SELECT ci.id,ci.quantity,ci.unit_price_cents,ci.customization_json,p.name,v.sku,v.option_summary,
                (SELECT pi.path FROM product_images pi WHERE pi.product_id=p.id ORDER BY CASE WHEN pi.path LIKE 'assets/catalog/%' THEN 1 ELSE 0 END,pi.sort_order,pi.id LIMIT 1) AS primary_image,
                (SELECT pi.alt_text FROM product_images pi WHERE pi.product_id=p.id ORDER BY CASE WHEN pi.path LIKE 'assets/catalog/%' THEN 1 ELSE 0 END,pi.sort_order,pi.id LIMIT 1) AS primary_image_alt
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

    @staticmethod
    def _user_payload(row: object) -> dict[str, object]:
        return {
            "id": row["id"], "email": row["email"], "display_name": row["display_name"], "role": row["role"],
            "must_change_password": bool(row["must_change_password"]), "two_factor_enabled": bool(row["two_factor_enabled"]),
        }

    def _current_user(self) -> dict[str, object] | None:
        """Obtiene usuario activo e incluye flags de seguridad obligatorios."""
        raw = self._read_session_cookie()
        if not raw:
            return None
        with connect(self.settings) as db:
            row = db.execute(
                """SELECT u.id,u.email,u.display_name,u.role,u.must_change_password,u.two_factor_enabled
                FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.revoked_at IS NULL AND u.is_active=1 AND s.expires_at>?""",
                (session_token_hash(raw), iso(utc_now())),
            ).fetchone()
        return self._user_payload(row) if row else None

    def _require_admin(self) -> dict[str, object] | None:
        user = self._current_user()
        if not user:
            self._json({"error": "Autenticación requerida."}, HTTPStatus.UNAUTHORIZED)
            return None
        if user["role"] not in {"admin", "superadmin"}:
            self._json({"error": "Permisos de administrador requeridos."}, HTTPStatus.FORBIDDEN)
            return None
        if user["must_change_password"]:
            self._json({"error": "Debes cambiar la contraseña temporal antes de continuar.", "code": "PASSWORD_CHANGE_REQUIRED"}, HTTPStatus.FORBIDDEN)
            return None
        return user

    def _bind_session_to_user(self, db: object, raw_token: str, user_id: int) -> str:
        now = utc_now()
        session = db.execute(
            "SELECT id,user_id FROM sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?",
            (session_token_hash(raw_token), iso(now)),
        ).fetchone()
        if not session:
            raise SessionChangedError()
        fresh_token = new_session_token()
        fresh_hash = session_token_hash(fresh_token)
        expires = iso(now + timedelta(seconds=self.settings.session_ttl_seconds))
        if session["user_id"] is None or session["user_id"] == user_id:
            session_id = session["id"]
            db.execute(
                "UPDATE sessions SET token_hash=?,user_id=?,expires_at=?,last_seen_at=? WHERE id=?",
                (fresh_hash, user_id, expires, iso(now), session_id),
            )
        else:
            # El carrito de una cuenta pertenece a esa cuenta incluso cuando
            # otra persona inicia sesión desde el mismo navegador.
            db.execute("UPDATE sessions SET revoked_at=? WHERE id=?", (iso(now), session["id"]))
            session_id = db.execute(
                "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
                (fresh_hash, user_id, iso(now), expires, iso(now)),
            ).lastrowid
        self._merge_user_carts(db, session_id, user_id)
        return fresh_token

    def _authenticated_json(self, payload, token, status=HTTPStatus.OK):
        self._set_session_cookie(token)
        payload["csrf_token"] = create_csrf_token(token, self.settings.secret_key)
        self._json(payload, status)

    def _merge_user_carts(self, db: object, session_id: int, user_id: int) -> None:
        """Fusiona carritos activos previos con el carrito de la sesión actual."""
        current = db.execute("SELECT id FROM carts WHERE session_id=? AND status='active' ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        previous = db.execute("SELECT id FROM carts WHERE user_id=? AND status='active' AND session_id<>? ORDER BY id DESC", (user_id, session_id)).fetchall()
        if not current and previous:
            target_id = previous[0]["id"]
            db.execute("UPDATE carts SET session_id=?,user_id=?,updated_at=? WHERE id=?", (session_id, user_id, iso(utc_now()), target_id))
            previous = previous[1:]
        elif current:
            target_id = current["id"]
            db.execute("UPDATE carts SET user_id=?,updated_at=? WHERE id=?", (user_id, iso(utc_now()), target_id))
        else:
            return
        for cart in previous:
            db.execute(
                "INSERT INTO cart_items(cart_id,variant_id,quantity,unit_price_cents,customization_json,created_at) SELECT ?,variant_id,quantity,unit_price_cents,customization_json,created_at FROM cart_items WHERE cart_id=?",
                (target_id, cart["id"]),
            )
            db.execute("UPDATE carts SET status='abandoned',updated_at=? WHERE id=?", (iso(utc_now()), cart["id"]))

    def _two_factor_setup(self) -> None:
        user = self._current_user()
        if not user or user["role"] not in {"admin", "superadmin"}:
            self._json({"error": "Autenticación administrativa requerida."}, HTTPStatus.FORBIDDEN)
            return
        if user["must_change_password"]:
            self._json({"error": "Cambia primero la contraseña temporal."}, HTTPStatus.FORBIDDEN)
            return
        cipher = FieldCipher(self.settings.field_encryption_key)
        with transaction(self.settings) as db:
            row = db.execute("SELECT two_factor_secret_encrypted,two_factor_enabled FROM users WHERE id=?", (user["id"],)).fetchone()
            if row["two_factor_enabled"]:
                self._json({"enabled": True})
                return
            if row["two_factor_secret_encrypted"]:
                secret = cipher.decrypt(row["two_factor_secret_encrypted"], aad="user-2fa")
            else:
                secret = new_totp_secret()
                db.execute("UPDATE users SET two_factor_secret_encrypted=?,updated_at=? WHERE id=?", (cipher.encrypt(secret, aad="user-2fa"), iso(utc_now()), user["id"]))
        self._json({"enabled": False, "secret": secret, "provisioning_uri": totp_uri(secret, str(user["email"]))})

    def _enable_two_factor(self, data: dict[str, object]) -> None:
        user = self._current_user()
        if not user or user["role"] not in {"admin", "superadmin"} or user["must_change_password"]:
            self._json({"error": "No puedes configurar 2FA en este momento."}, HTTPStatus.FORBIDDEN)
            return
        code = str(data.get("code", "")).strip()
        cipher = FieldCipher(self.settings.field_encryption_key)
        with transaction(self.settings) as db:
            row = db.execute("SELECT two_factor_secret_encrypted FROM users WHERE id=?", (user["id"],)).fetchone()
            if not row or not row["two_factor_secret_encrypted"]:
                self._json({"error": "Primero inicia la configuración de 2FA."}, HTTPStatus.CONFLICT)
                return
            secret = cipher.decrypt(row["two_factor_secret_encrypted"], aad="user-2fa")
            if not secret or not verify_totp(secret, code):
                self._json({"error": "Código de verificación inválido."}, HTTPStatus.UNAUTHORIZED)
                return
            db.execute("UPDATE users SET two_factor_enabled=1,updated_at=? WHERE id=?", (iso(utc_now()), user["id"]))
        self._json({"ok": True, "enabled": True})

    def _verify_two_factor_login(self, data: dict[str, object]) -> None:
        challenge = str(data.get("challenge_token", ""))
        code = str(data.get("code", "")).strip()
        if not challenge or not code:
            self._json({"error": "Verificación incompleta."}, HTTPStatus.BAD_REQUEST)
            return
        now = utc_now()
        cipher = FieldCipher(self.settings.field_encryption_key)
        raw_session = self._ensure_session()
        with transaction(self.settings) as db:
            row = db.execute(
                """SELECT ac.id,ac.user_id,u.email,u.display_name,u.role,u.must_change_password,u.two_factor_enabled,u.two_factor_secret_encrypted
                   FROM auth_challenges ac JOIN users u ON u.id=ac.user_id
                   WHERE ac.challenge_hash=? AND ac.purpose='login_2fa' AND ac.used_at IS NULL AND ac.expires_at>? AND u.is_active=1 AND u.two_factor_enabled=1""",
                (token_digest(challenge + ":" + raw_session), iso(now)),
            ).fetchone()
            if not row:
                self._json({"error": "La verificación expiró. Inicia sesión nuevamente."}, HTTPStatus.UNAUTHORIZED)
                return
            secret = cipher.decrypt(row["two_factor_secret_encrypted"], aad="user-2fa")
            if not secret or not verify_totp(secret, code):
                self._json({"error": "Código de verificación inválido."}, HTTPStatus.UNAUTHORIZED)
                return
            db.execute("UPDATE auth_challenges SET used_at=? WHERE id=?", (iso(now), row["id"]))
            rotated_token = self._bind_session_to_user(db, raw_session, row["user_id"])
            payload = self._user_payload(row)
        self._authenticated_json({"user": payload}, rotated_token)

    def _request_password_reset(self, data: dict[str, object]) -> None:
        email = str(data.get("email", "")).strip().lower()
        debug_token = None
        if EMAIL_RE.match(email):
            with transaction(self.settings) as db:
                user = db.execute("SELECT id FROM users WHERE email=? AND is_active=1", (email,)).fetchone()
                if user:
                    token = new_session_token()
                    now = utc_now()
                    db.execute("UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (iso(now), user["id"]))
                    db.execute(
                        "INSERT INTO password_reset_tokens(user_id,token_hash,created_at,expires_at) VALUES(?,?,?,?)",
                        (user["id"], token_digest(token), iso(now), iso(now + timedelta(minutes=self.settings.password_reset_minutes))),
                    )
                    if self.settings.environment != "production":
                        debug_token = token
        payload = {"ok": True, "message": "Si la cuenta existe, se generó un enlace de recuperación."}
        if debug_token:
            payload["development_token"] = debug_token
        self._json(payload)

    def _confirm_password_reset(self, data: dict[str, object]) -> None:
        token = str(data.get("token", ""))
        new_password = str(data.get("new_password", ""))
        try:
            encoded = hash_password(new_password)
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        now = utc_now()
        with transaction(self.settings) as db:
            row = db.execute(
                "SELECT id,user_id FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                (token_digest(token), iso(now)),
            ).fetchone()
            if not row:
                self._json({"error": "El enlace de recuperación es inválido o expiró."}, HTTPStatus.BAD_REQUEST)
                return
            self._invalidate_recovery(db, row["user_id"])
            db.execute("UPDATE users SET password_hash=?,must_change_password=0,failed_login_count=0,locked_until=NULL,updated_at=? WHERE id=?", (encoded, iso(now), row["user_id"]))
            db.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (iso(now), row["user_id"]))
        self._pending_set_cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        self._json({"ok": True})

    @staticmethod
    def _invalidate_recovery(db, user_id):
        now = iso(utc_now())
        db.execute("UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (now, user_id))
        db.execute("DELETE FROM auth_challenges WHERE user_id=?", (user_id,))
        db.execute(
            "UPDATE auth_mail_outbox SET expires_at=? WHERE sent_at IS NULL AND recipient=(SELECT email FROM users WHERE id=?)",
            (now, user_id),
        )

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
        with connect(self.settings) as db:
            row = db.execute("SELECT expires_at,revoked_at FROM sessions WHERE token_hash=?",(session_token_hash(session),)).fetchone()
        if not row or row["revoked_at"] or row["expires_at"]<=iso(utc_now()):
            self._json({"error":"La sesión caducó. Recarga la página antes de volver a enviar."},HTTPStatus.UNAUTHORIZED)
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
        self._set_session_cookie(raw)
        return raw

    def _set_session_cookie(self, token: str) -> None:
        cookie = f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={self.settings.session_ttl_seconds}"
        if self.settings.secure_cookies:
            cookie += "; Secure"
        self._pending_set_cookie = cookie

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
            data = json.loads(
                self.rfile.read(length).decode("utf-8"),
                object_pairs_hook=unique_json_object,
                parse_int=bounded_json_integer,
                parse_float=finite_json_number,
                parse_constant=finite_json_number,
            )
            # Los escapes JSON pueden contener sustitutos Unicode aislados.
            json.dumps(data, ensure_ascii=False).encode("utf-8")
        except (ValueError, UnicodeError, RecursionError):
            self._json({"error": "JSON inválido."}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(data, dict):
            self._json({"error": "El cuerpo debe ser un objeto JSON."}, HTTPStatus.BAD_REQUEST)
            return None
        return data

    def _unexpected_error(self) -> None:
        """Oculta detalles internos y conserva un identificador de soporte."""
        error_id = f"TIP-{secrets.token_hex(4).upper()}"
        if urlparse(self.path).path.startswith("/api/"):
            self._json({"error": "Ocurrió un error interno.", "error_id": error_id}, HTTPStatus.INTERNAL_SERVER_ERROR)
        else:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, explain=error_id)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """Renderiza páginas de error propias sin mostrar la plantilla cruda de Python."""
        try:
            status = HTTPStatus(code)
        except ValueError:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        template = ERROR_DIR / f"{int(status)}.html"
        if not template.is_file():
            template = ERROR_DIR / "500.html"
        error_id = explain if explain and str(explain).startswith("TIP-") else ""
        body = template.read_text(encoding="utf-8").replace("{{ERROR_ID}}", error_id).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

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
        if candidate.suffix.lower() != ".html":
            self._cache_control = "public, max-age=300"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)


def create_server(settings: Settings) -> ThreadingHTTPServer:
    """Crea un servidor HTTP multihilo configurando settings y rate limiter en el handler."""
    handler = type("ConfiguredTipsRequestHandler", (TipsRequestHandler,), {
        "settings": settings,
        "rate_limiter": RateLimiter(settings.rate_limit_per_minute),
        "sensitive_rate_limiter": RateLimiter(min(10, settings.rate_limit_per_minute)),
    })
    return ThreadingHTTPServer((settings.host, settings.port), handler)
