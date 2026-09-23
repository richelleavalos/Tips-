"""Composición final del servidor ejecutable y checkout de demostración."""

from __future__ import annotations

from http import HTTPStatus
from http.server import ThreadingHTTPServer
import json
import secrets

from .view_access_server import TipsRoleViewRequestHandler
from .config import Settings
from .database import transaction
from .security import RateLimiter, session_token_hash
from .server import EMAIL_RE, iso, utc_now


class RuntimeTipsRequestHandler(TipsRoleViewRequestHandler):
    """Handler efectivo de la aplicación.

    Mantiene las rutas, defensas, herramientas administrativas, gestión de cuenta,
    medios configurables, módulos escalables, vistas protegidas por rol y checkout demo.
    """

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

        if (
            not customer_name
            or not EMAIL_RE.match(email)
            or not phone
            or not isinstance(shipping, dict)
            or not str(shipping.get("address", "")).strip()
        ):
            self._json({"error": "Completa correctamente los datos de envío."}, HTTPStatus.BAD_REQUEST)
            return

        raw = self._ensure_session()
        token_hash = session_token_hash(raw)
        now = iso(utc_now())

        with transaction(self.settings) as db:
            cart = db.execute(
                """SELECT c.id,c.currency
                FROM carts c
                JOIN sessions s ON s.id=c.session_id
                WHERE s.token_hash=? AND c.status='active'""",
                (token_hash,),
            ).fetchone()
            if not cart:
                self._json({"error": "El carrito está vacío."}, HTTPStatus.BAD_REQUEST)
                return

            items = db.execute(
                """SELECT ci.id,ci.variant_id,ci.quantity,ci.unit_price_cents,ci.customization_json,
                p.name,v.sku,v.stock_quantity
                FROM cart_items ci
                JOIN product_variants v ON v.id=ci.variant_id
                JOIN products p ON p.id=v.product_id
                WHERE ci.cart_id=?""",
                (cart["id"],),
            ).fetchall()
            if not items:
                self._json({"error": "El carrito está vacío."}, HTTPStatus.BAD_REQUEST)
                return

            for item in items:
                if item["stock_quantity"] is not None and item["stock_quantity"] < item["quantity"]:
                    self._json(
                        {"error": f"Inventario insuficiente para {item['name']}."},
                        HTTPStatus.CONFLICT,
                    )
                    return

            subtotal = sum(item["quantity"] * item["unit_price_cents"] for item in items)
            public_id = f"TIPS-{utc_now().strftime('%y%m%d')}-{secrets.token_hex(2).upper()}"

            cursor = db.execute(
                """INSERT INTO orders(
                    public_id,user_id,email,customer_name,phone,status,currency,
                    subtotal_cents,shipping_cents,discount_cents,total_cents,
                    shipping_address_json,created_at,updated_at
                ) VALUES(?,?,?,?,?,'paid',?,?,0,0,?,?,?,?)""",
                (
                    public_id,
                    user["id"],
                    email,
                    customer_name,
                    phone,
                    cart["currency"],
                    subtotal,
                    subtotal,
                    json.dumps(shipping, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            order_id = cursor.lastrowid

            for item in items:
                db.execute(
                    """INSERT INTO order_items(
                        order_id,variant_id,product_name,sku,quantity,unit_price_cents,customization_json
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        order_id,
                        item["variant_id"],
                        item["name"],
                        item["sku"],
                        item["quantity"],
                        item["unit_price_cents"],
                        item["customization_json"],
                    ),
                )
                if item["stock_quantity"] is not None:
                    db.execute(
                        "UPDATE product_variants SET stock_quantity=stock_quantity-?,updated_at=? WHERE id=?",
                        (item["quantity"], now, item["variant_id"]),
                    )
                    db.execute(
                        """INSERT INTO inventory_movements(
                            variant_id,delta,reason,reference_type,reference_id,created_at
                        ) VALUES(?,?,'venta demo','order',?,?)""",
                        (item["variant_id"], -item["quantity"], order_id, now),
                    )

            db.execute(
                """INSERT INTO payments(
                    order_id,provider,provider_payment_id,status,amount_cents,currency,
                    idempotency_key,provider_payload_json,created_at,updated_at
                ) VALUES(?,'mock',?,'paid',?,?,?,?,?,?)""",
                (
                    order_id,
                    f"mock_{secrets.token_hex(6)}",
                    subtotal,
                    cart["currency"],
                    secrets.token_urlsafe(20),
                    '{"mode":"demo"}',
                    now,
                    now,
                ),
            )
            db.execute(
                "UPDATE carts SET status='converted',updated_at=? WHERE id=?",
                (now, cart["id"]),
            )

        self._json(
            {
                "public_id": public_id,
                "total_cents": subtotal,
                "currency": cart["currency"],
                "status": "paid",
                "payment_provider": "mock",
            },
            HTTPStatus.CREATED,
        )


def create_server(settings: Settings) -> ThreadingHTTPServer:
    """Crea un servidor HTTP multihilo configurando settings y rate limiter en el handler."""
    handler = type(
        "ConfiguredRuntimeTipsRequestHandler",
        (RuntimeTipsRequestHandler,),
        {
            "settings": settings,
            "rate_limiter": RateLimiter(settings.rate_limit_per_minute),
        },
    )
    return ThreadingHTTPServer((settings.host, settings.port), handler)
