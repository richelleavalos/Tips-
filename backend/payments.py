"""Capa desacoplada de pagos, webhooks, reembolsos y reservas de inventario."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any

from .config import Settings
from .orders import OrderStateMachine


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class PaymentIntent:
    provider: str
    provider_payment_id: str
    status: str
    client_payload: dict[str, Any]


class PaymentProvider:
    """Contrato mínimo para conectar una pasarela real sin tocar checkout/órdenes."""

    name = "base"

    def create_payment(self, *, order_public_id: str, amount_cents: int, currency: str, idempotency_key: str) -> PaymentIntent:
        raise NotImplementedError

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        raise NotImplementedError

    def parse_webhook(self, raw_body: bytes) -> dict[str, Any]:
        raise NotImplementedError

    def refund(self, *, provider_payment_id: str, amount_cents: int, reason: str) -> dict[str, Any]:
        raise NotImplementedError


class SandboxPaymentProvider(PaymentProvider):
    """Proveedor local que reproduce el contrato de una pasarela con firma HMAC."""

    name = "sandbox"

    def __init__(self, webhook_secret: str) -> None:
        self.webhook_secret = webhook_secret.encode("utf-8")

    def create_payment(self, *, order_public_id: str, amount_cents: int, currency: str, idempotency_key: str) -> PaymentIntent:
        payment_id = f"sbx_{secrets.token_hex(10)}"
        return PaymentIntent(
            provider=self.name,
            provider_payment_id=payment_id,
            status="pending",
            client_payload={
                "mode": "sandbox",
                "payment_id": payment_id,
                "order": order_public_id,
                "amount_cents": amount_cents,
                "currency": currency,
            },
        )

    def sign(self, raw_body: bytes) -> str:
        return hmac.new(self.webhook_secret, raw_body, hashlib.sha256).hexdigest()

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        if not signature:
            return False
        return hmac.compare_digest(self.sign(raw_body), signature.strip().lower())

    def parse_webhook(self, raw_body: bytes) -> dict[str, Any]:
        data = json.loads(raw_body.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Webhook inválido.")
        required = {"event_id", "event_type", "payment_id"}
        if not required.issubset(data):
            raise ValueError("Webhook incompleto.")
        return data

    def simulated_event(self, payment_id: str, *, succeeded: bool = True) -> tuple[bytes, str]:
        payload = {
            "event_id": f"evt_{secrets.token_hex(10)}",
            "event_type": "payment.succeeded" if succeeded else "payment.failed",
            "payment_id": payment_id,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return raw, self.sign(raw)

    def refund(self, *, provider_payment_id: str, amount_cents: int, reason: str) -> dict[str, Any]:
        return {"provider_refund_id": f"rfd_{secrets.token_hex(10)}", "status": "succeeded", "amount_cents": amount_cents, "reason": reason}


def provider_for(settings: Settings) -> PaymentProvider:
    # v6 incluye sandbox. Un proveedor real solo necesita implementar el contrato.
    if settings.payment_provider != "sandbox":
        raise RuntimeError(f"Proveedor de pago no configurado: {settings.payment_provider}")
    return SandboxPaymentProvider(settings.payment_webhook_secret)


class PaymentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = provider_for(settings)

    @staticmethod
    def _release_reserved_inventory(db: Any, order_id: int, *, final_status: str = "released") -> None:
        rows = db.execute(
            "SELECT id,variant_id,quantity FROM inventory_reservations WHERE order_id=? AND status='reserved'",
            (order_id,),
        ).fetchall()
        now = utc_iso()
        for row in rows:
            db.execute("UPDATE product_variants SET stock_quantity=stock_quantity+?,updated_at=? WHERE id=? AND stock_quantity IS NOT NULL", (row["quantity"], now, row["variant_id"]))
            db.execute("UPDATE inventory_reservations SET status=?,updated_at=? WHERE id=?", (final_status, now, row["id"]))
            db.execute("INSERT INTO inventory_movements(variant_id,delta,reason,reference_type,reference_id,created_at) VALUES(?,?,'liberación de reserva','order',?,?)", (row["variant_id"], row["quantity"], order_id, now))

    def release_expired(self, db: Any, now: str | None = None) -> int:
        now = now or utc_iso()
        orders = db.execute(
            "SELECT DISTINCT order_id FROM inventory_reservations WHERE status='reserved' AND expires_at<=?",
            (now,),
        ).fetchall()
        count = 0
        for row in orders:
            order = db.execute("SELECT status FROM orders WHERE id=?", (row["order_id"],)).fetchone()
            if order and order["status"] == "pending_payment":
                self._release_reserved_inventory(db, row["order_id"], final_status="expired")
                db.execute("UPDATE orders SET status='expired',updated_at=? WHERE id=?", (now, row["order_id"]))
                db.execute("UPDATE payments SET status='cancelled',updated_at=? WHERE order_id=? AND status='pending'", (now, row["order_id"]))
                count += 1
        return count

    def handle_webhook(self, db: Any, raw_body: bytes, signature: str) -> dict[str, Any]:
        if not self.provider.verify_webhook(raw_body, signature):
            raise PermissionError("Firma de webhook inválida.")
        event = self.provider.parse_webhook(raw_body)
        now = utc_iso()

        duplicate = db.execute(
            "SELECT id FROM payment_webhook_events WHERE provider=? AND event_id=?",
            (self.provider.name, str(event["event_id"])),
        ).fetchone()
        if duplicate:
            return {"ok": True, "duplicate": True}

        payment = db.execute(
            "SELECT id,order_id,status,amount_cents FROM payments WHERE provider=? AND provider_payment_id=?",
            (self.provider.name, str(event["payment_id"])),
        ).fetchone()
        if not payment:
            raise LookupError("Pago no encontrado.")

        db.execute(
            "INSERT INTO payment_webhook_events(provider,event_id,event_type,payload_json,processed_at) VALUES(?,?,?,?,?)",
            (self.provider.name, str(event["event_id"]), str(event["event_type"]), raw_body.decode("utf-8"), now),
        )

        event_type = str(event["event_type"])
        order = db.execute("SELECT id,status FROM orders WHERE id=?", (payment["order_id"],)).fetchone()
        if not order:
            raise LookupError("Pedido asociado no encontrado.")

        if event_type == "payment.succeeded":
            if payment["status"] != "paid":
                OrderStateMachine.validate(order["status"], "paid", payment_event=True)
                db.execute("UPDATE payments SET status='paid',updated_at=? WHERE id=?", (now, payment["id"]))
                db.execute("UPDATE orders SET status='paid',updated_at=? WHERE id=?", (now, order["id"]))
                db.execute("UPDATE inventory_reservations SET status='consumed',updated_at=? WHERE order_id=? AND status='reserved'", (now, order["id"]))
        elif event_type == "payment.failed":
            if payment["status"] == "pending" and order["status"] == "pending_payment":
                OrderStateMachine.validate(order["status"], "payment_failed", payment_event=True)
                db.execute("UPDATE payments SET status='failed',updated_at=? WHERE id=?", (now, payment["id"]))
                db.execute("UPDATE orders SET status='payment_failed',updated_at=? WHERE id=?", (now, order["id"]))
                self._release_reserved_inventory(db, order["id"])
        else:
            # Evento válido pero todavía no soportado: queda persistido de forma idempotente.
            return {"ok": True, "ignored": True, "event_type": event_type}

        db.execute(
            "INSERT INTO payment_attempts(payment_id,status,provider_reference,payload_json,created_at) VALUES(?,?,?,?,?)",
            (payment["id"], "paid" if event_type == "payment.succeeded" else "failed", str(event["event_id"]), raw_body.decode("utf-8"), now),
        )
        return {"ok": True, "duplicate": False, "status": "paid" if event_type == "payment.succeeded" else "failed", "order_id": order["id"]}

    def refund(self, db: Any, payment_id: int, amount_cents: int | None, reason: str) -> dict[str, Any]:
        payment = db.execute(
            "SELECT p.*,o.status AS order_status FROM payments p JOIN orders o ON o.id=p.order_id WHERE p.id=?",
            (payment_id,),
        ).fetchone()
        if not payment or payment["status"] not in {"paid", "partially_refunded"}:
            raise ValueError("Solo se pueden reembolsar pagos confirmados.")
        existing_refunded = db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM refunds WHERE payment_id=? AND status='succeeded'", (payment_id,)).fetchone()[0]
        remaining = payment["amount_cents"] - existing_refunded
        amount = remaining if amount_cents is None else amount_cents
        if not isinstance(amount, int) or amount <= 0 or amount > remaining:
            raise ValueError("Monto de reembolso inválido.")

        result = self.provider.refund(provider_payment_id=payment["provider_payment_id"], amount_cents=amount, reason=reason)
        now = utc_iso()
        db.execute(
            "INSERT INTO refunds(payment_id,provider_refund_id,status,amount_cents,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (payment_id, result["provider_refund_id"], result["status"], amount, reason[:500], now, now),
        )
        total_refunded = existing_refunded + amount
        if total_refunded >= payment["amount_cents"]:
            OrderStateMachine.validate(payment["order_status"], "refunded", payment_event=True)
            db.execute("UPDATE payments SET status='refunded',updated_at=? WHERE id=?", (now, payment_id))
            db.execute("UPDATE orders SET status='refunded',updated_at=? WHERE id=?", (now, payment["order_id"]))
            # Devuelve inventario una sola vez al completar el reembolso total.
            rows = db.execute("SELECT variant_id,quantity FROM inventory_reservations WHERE order_id=? AND status='consumed'", (payment["order_id"],)).fetchall()
            for row in rows:
                db.execute("UPDATE product_variants SET stock_quantity=stock_quantity+?,updated_at=? WHERE id=? AND stock_quantity IS NOT NULL", (row["quantity"], now, row["variant_id"]))
                db.execute("INSERT INTO inventory_movements(variant_id,delta,reason,reference_type,reference_id,created_at) VALUES(?,?,'reembolso','order',?,?)", (row["variant_id"], row["quantity"], payment["order_id"], now))
            db.execute("UPDATE inventory_reservations SET status='released',updated_at=? WHERE order_id=? AND status='consumed'", (now, payment["order_id"]))
        else:
            db.execute("UPDATE payments SET status='partially_refunded',updated_at=? WHERE id=?", (now, payment_id))
        return {"ok": True, "refund_id": result["provider_refund_id"], "amount_cents": amount, "payment_status": "refunded" if total_refunded >= payment["amount_cents"] else "partially_refunded"}
