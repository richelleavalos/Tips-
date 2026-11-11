"""Configuración central de TIPS.

Los secretos operativos se leen exclusivamente desde variables de entorno. En
producción no se generan claves efímeras: la aplicación falla de forma segura
si falta una clave requerida.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import secrets

BASE_DIR = Path(__file__).resolve().parent.parent


class EnvironmentReader:
    """Lee variables de entorno y aplica conversiones seguras y consistentes."""

    TRUE_VALUES = {"1", "true", "yes", "on", "si", "sí"}

    @staticmethod
    def text(name: str, default: str | None = None) -> str | None:
        value = os.getenv(name)
        return default if value is None else value

    @classmethod
    def boolean(cls, name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in cls.TRUE_VALUES

    @staticmethod
    def integer(name: str, default: int, minimum: int, maximum: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} debe ser un número entero.") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} debe estar entre {minimum} y {maximum}.")
        return value

    @staticmethod
    def origins() -> tuple[str, ...]:
        raw = os.getenv(
            "TIPS_ALLOWED_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000",
        )
        return tuple(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable consumida por todos los componentes de TIPS.

    Los últimos campos tienen valores por defecto para mantener compatibilidad
    con pruebas y scripts de versiones anteriores que construían ``Settings``
    por posición.
    """

    environment: str
    host: str
    port: int
    database_path: Path
    allowed_origins: tuple[str, ...]
    secret_key: str
    secure_cookies: bool
    session_ttl_seconds: int
    max_request_bytes: int
    rate_limit_per_minute: int
    field_encryption_key: str = "tips-development-field-key-change-me"
    payment_webhook_secret: str = "tips-development-sandbox-webhook-secret"
    payment_provider: str = "sandbox"
    inventory_reservation_minutes: int = 15
    password_reset_minutes: int = 30
    two_factor_challenge_minutes: int = 5

    @classmethod
    def load(cls) -> "Settings":
        reader = EnvironmentReader()
        environment = (reader.text("TIPS_ENV", "development") or "development").strip().lower()
        supplied_secret = reader.text("TIPS_SECRET_KEY")
        supplied_field_key = reader.text("TIPS_FIELD_ENCRYPTION_KEY")
        supplied_webhook_secret = reader.text("TIPS_PAYMENT_WEBHOOK_SECRET")

        if environment == "production":
            missing = [
                name for name, value in (
                    ("TIPS_SECRET_KEY", supplied_secret),
                    ("TIPS_FIELD_ENCRYPTION_KEY", supplied_field_key),
                ) if not value
            ]
            if missing:
                raise RuntimeError("Faltan secretos obligatorios en producción: " + ", ".join(missing))

        database_raw = reader.text("TIPS_DB_PATH")
        database_path = Path(database_raw).expanduser() if database_raw else BASE_DIR / "data" / "tips.db"
        if not database_path.is_absolute():
            database_path = BASE_DIR / database_path

        return cls(
            environment=environment,
            host=reader.text("TIPS_HOST", "127.0.0.1") or "127.0.0.1",
            port=reader.integer("TIPS_PORT", 8000, 1, 65535),
            database_path=database_path,
            allowed_origins=reader.origins(),
            secret_key=supplied_secret or secrets.token_urlsafe(48),
            secure_cookies=reader.boolean("TIPS_SECURE_COOKIES", environment == "production"),
            session_ttl_seconds=reader.integer("TIPS_SESSION_TTL_SECONDS", 28800, 900, 2592000),
            max_request_bytes=reader.integer("TIPS_MAX_REQUEST_BYTES", 1048576, 16384, 10485760),
            rate_limit_per_minute=reader.integer("TIPS_RATE_LIMIT_PER_MINUTE", 120, 10, 10000),
            field_encryption_key=supplied_field_key or "tips-development-field-key-change-me",
            payment_webhook_secret=supplied_webhook_secret or "tips-development-sandbox-webhook-secret",
            payment_provider=(reader.text("TIPS_PAYMENT_PROVIDER", "sandbox") or "sandbox").strip().lower(),
            inventory_reservation_minutes=reader.integer("TIPS_INVENTORY_RESERVATION_MINUTES", 15, 5, 120),
            password_reset_minutes=reader.integer("TIPS_PASSWORD_RESET_MINUTES", 30, 5, 180),
            two_factor_challenge_minutes=reader.integer("TIPS_2FA_CHALLENGE_MINUTES", 5, 1, 30),
        )
