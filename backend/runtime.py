"""Composición HTTP de TIPS 6.5 y recálculo de precios de catálogo."""
from __future__ import annotations
import json
from http.server import ThreadingHTTPServer
from .view_access_server import TipsRoleViewRequestHandler
from .config import Settings
from .security import RateLimiter

class RuntimeTipsRequestHandler(TipsRoleViewRequestHandler):
    """La capa operacional se monta en create_server sin proveedores de pago."""

    def _repriced_cart_items(self, db: object, cart_id: int) -> list[dict[str, object]]:
        """Recalcula precios usando la base de datos; nunca confía en el JS ni en snapshots antiguos."""
        rows = db.execute(
            """SELECT ci.id,ci.variant_id,ci.quantity,ci.customization_json,
                      p.id AS product_id,p.name,p.base_price_cents,p.currency,p.is_active AS product_active,
                      v.sku,v.price_cents,v.stock_quantity,v.is_active AS variant_active
               FROM cart_items ci
               JOIN product_variants v ON v.id=ci.variant_id
               JOIN products p ON p.id=v.product_id
               WHERE ci.cart_id=? ORDER BY ci.id""",
            (cart_id,),
        ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            if not row["product_active"] or not row["variant_active"]:
                raise ValueError(f"{row['name']} ya no está disponible.")
            try:
                snapshot = json.loads(row["customization_json"] or "[]")
            except json.JSONDecodeError:
                snapshot = []
            ids = [entry.get("id") for entry in snapshot if isinstance(entry, dict) and isinstance(entry.get("id"), int)]
            from .operations import validate_options
            validate_options(db, row["product_id"], ids)
            adjustment = 0
            fresh_snapshot = []
            if ids:
                marks = ",".join("?" for _ in ids)
                options = db.execute(
                    f"""SELECT cv.id,cv.label,cv.price_delta_cents,c.name
                        FROM customization_values cv
                        JOIN customizations c ON c.id=cv.customization_id
                        JOIN product_customizations pc ON pc.customization_id=c.id
                        WHERE pc.product_id=? AND cv.id IN ({marks}) AND c.is_active=1 AND cv.is_active=1""",
                    (row["product_id"], *ids),
                ).fetchall()
                if len(options) != len(set(ids)):
                    raise ValueError(f"Una personalización de {row['name']} ya no está disponible.")
                for option in options:
                    adjustment += option["price_delta_cents"]
                    fresh_snapshot.append({"id": option["id"], "grupo": option["name"], "opcion": option["label"], "ajuste_centavos": option["price_delta_cents"]})
            unit = (row["price_cents"] if row["price_cents"] is not None else row["base_price_cents"]) + adjustment
            result.append({
                "id": row["id"], "variant_id": row["variant_id"], "quantity": row["quantity"], "name": row["name"],
                "sku": row["sku"], "stock_quantity": row["stock_quantity"], "unit_price_cents": unit,
                "customization_json": json.dumps(fresh_snapshot, ensure_ascii=False, separators=(",", ":")),
            })
        return result


def create_server(settings: Settings) -> ThreadingHTTPServer:
    from .operations import OperationsHandler
    handler = type(
        "ConfiguredRuntimeTipsRequestHandler",
        (OperationsHandler,),
        {"settings": settings, "rate_limiter": RateLimiter(settings.rate_limit_per_minute), "sensitive_rate_limiter": RateLimiter(min(10, settings.rate_limit_per_minute))},
    )
    return ThreadingHTTPServer((settings.host, settings.port), handler)
