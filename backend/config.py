"""Configuración central de Tips.

Todas las variables de entorno se interpretan aquí para evitar conversiones y
valores por defecto dispersos por el proyecto. ``Settings`` es inmutable y
representa la configuración efectiva; ``EnvironmentReader`` contiene las
reglas para leer y validar el entorno del proceso.
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
        """Devuelve una variable textual sin imponer reglas de negocio adicionales."""
        value = os.getenv(name)
        return default if value is None else value

    @classmethod
    def boolean(cls, name: str, default: bool = False) -> bool:
        """Interpreta valores habituales de verdad como un booleano de Python."""
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in cls.TRUE_VALUES

    @staticmethod
    def integer(name: str, default: int, minimum: int, maximum: int) -> int:
        """Lee un entero y garantiza que permanezca dentro del rango permitido."""
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
        """Normaliza la lista de orígenes autorizados para CORS."""
        raw = os.getenv(
            "TIPS_ALLOWED_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000",
        )
        return tuple(origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable que consumen todos los componentes de Tips."""

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

    @classmethod
    def load(cls) -> "Settings":
        """Construye y valida la configuración a partir del entorno del proceso."""
        reader = EnvironmentReader()
        environment = (reader.text("TIPS_ENV", "development") or "development").strip().lower()
        supplied_secret = reader.text("TIPS_SECRET_KEY")
        if environment == "production" and not supplied_secret:
            raise RuntimeError("TIPS_SECRET_KEY es obligatorio en producción.")

        # Una ruta relativa se interpreta respecto de la raíz del proyecto para
        # que ejecutar app.py desde otra carpeta no cambie el archivo utilizado.
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
            # En desarrollo se genera una clave efímera; producción exige una
            # clave estable mediante TIPS_SECRET_KEY para no invalidar sesiones.
            secret_key=supplied_secret or secrets.token_urlsafe(48),
            secure_cookies=reader.boolean("TIPS_SECURE_COOKIES", environment == "production"),
            session_ttl_seconds=reader.integer("TIPS_SESSION_TTL_SECONDS", 28800, 900, 2592000),
            max_request_bytes=reader.integer("TIPS_MAX_REQUEST_BYTES", 1048576, 16384, 10485760),
            rate_limit_per_minute=reader.integer("TIPS_RATE_LIMIT_PER_MINUTE", 120, 10, 10000),
        )
