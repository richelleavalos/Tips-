"""Reglas de estado de pedidos de TIPS."""

from __future__ import annotations


class InvalidOrderTransition(ValueError):
    pass


class OrderStateMachine:
    """Evita combinaciones de estado imposibles y separa pago de operación."""

    ALLOWED = {
        "pending_payment": {"paid", "payment_failed", "cancelled", "expired"},
        "payment_failed": {"pending_payment", "cancelled"},
        "paid": {"processing", "cancelled", "refunded"},
        "processing": {"ready", "cancelled", "refunded"},
        "ready": {"shipped", "completed", "cancelled", "refunded"},
        "shipped": {"completed", "refunded"},
        "completed": {"refunded"},
        "cancelled": set(),
        "expired": set(),
        "refunded": set(),
    }

    PAYMENT_CONTROLLED = {"paid", "payment_failed", "refunded", "expired"}

    @classmethod
    def validate(cls, current: str, target: str, *, payment_event: bool = False) -> None:
        if current == target:
            return
        if target not in cls.ALLOWED.get(current, set()):
            raise InvalidOrderTransition(f"No se puede cambiar un pedido de {current} a {target}.")
        if not payment_event and target in cls.PAYMENT_CONTROLLED:
            raise InvalidOrderTransition("Ese estado solo puede establecerlo el flujo de pagos.")
