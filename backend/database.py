"""Infraestructura de persistencia SQLite de Tips.

Este módulo concentra la creación de conexiones, las transacciones y la
inicialización del esquema. La clase :class:`DatabaseManager` es la interfaz
orientada a objetos recomendada. Las funciones del final se conservan como
adaptadores pequeños para no romper código existente mientras el proyecto
migra gradualmente a la nueva arquitectura.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
from typing import Any, Iterator

from .config import BASE_DIR, Settings

SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"
SEED_PATH = BASE_DIR / "sql" / "seed.sql"

# Configuración inicial que debe existir incluso cuando la base se crea vacía.
DEFAULT_SITE_SETTINGS: dict[str, tuple[dict[str, Any], int]] = {
    "theme": ({
        "primary": "#173d2b",
        "accent": "#ef7d22",
        "secondary": "#825334",
        "surface": "#f7f7f2",
        "logo_variant": "orange",
    }, 1),
    "brand": ({
        "name": "Tips",
        "currency": "USD",
        "country": "SV",
    }, 1),
    "home": ({
        "eyebrow": "Arquitectura · objetos · interiores",
        "title": "TIPS QUE",
        "highlight": "INSPIRAN",
        "description": "Ideas y soluciones para diseñar mejores espacios, crear objetos útiles y convertir cada proyecto en una experiencia clara y personal.",
        "primary_cta": "Explorar Tips",
        "secondary_cta": "Ver productos",
    }, 1),
    "contact": ({
        "location": "San Salvador, El Salvador",
        "email": "",
        "whatsapp": "",
        "instagram": "",
        "facebook": "",
    }, 1),
}


class ClosingConnection(sqlite3.Connection):
    """Conexión SQLite que siempre libera el archivo al salir de ``with``."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """Finaliza la transacción de SQLite y cierra el descriptor de archivo."""
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class DatabaseManager:
    """Administra todo el acceso básico a la base SQLite de una instancia Tips.

    La clase guarda ``Settings`` una sola vez y ofrece operaciones explícitas
    para conexión, transacción, inicialización y consultas de lectura. Esto
    evita repetir configuración de SQLite por todo el proyecto y facilita
    sustituir la infraestructura en el futuro sin tocar la lógica de negocio.
    """

    def __init__(self, settings: Settings) -> None:
        """Asocia el administrador con la configuración de la aplicación."""
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        """Abre una conexión configurada con seguridad e integridad referencial."""
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.settings.database_path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row

        # Estas opciones se aplican a cada conexión porque SQLite las mantiene
        # por conexión, no globalmente para todo el proceso.
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Ejecuta un bloque atómico con commit o rollback automático."""
        connection = self.connect()
        try:
            # BEGIN IMMEDIATE reserva la escritura temprano y reduce estados
            # intermedios ambiguos cuando varias peticiones escriben a la vez.
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Crea el esquema y carga datos base únicamente cuando corresponda."""
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema)

            # Los datos demo se insertan solo en una base sin productos para no
            # sobrescribir información creada por usuarios o administradores.
            count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if count == 0 and SEED_PATH.exists():
                connection.executescript(SEED_PATH.read_text(encoding="utf-8"))

            # INSERT OR IGNORE conserva cualquier personalización ya guardada.
            for key, (value, is_public) in DEFAULT_SITE_SETTINGS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO site_settings(key,value_json,is_public) VALUES(?,?,?)",
                    (key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), is_public),
                )

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Ejecuta una consulta de lectura y devuelve filas como diccionarios."""
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Adaptadores de compatibilidad
# ---------------------------------------------------------------------------
# El backend histórico importa estas funciones directamente. Mantenerlas
# permite adoptar DatabaseManager por etapas sin una migración riesgosa de
# todos los handlers en un solo cambio.

def connect(settings: Settings) -> sqlite3.Connection:
    """Compatibilidad: abre una conexión mediante :class:`DatabaseManager`."""
    return DatabaseManager(settings).connect()


@contextmanager
def transaction(settings: Settings) -> Iterator[sqlite3.Connection]:
    """Compatibilidad: crea una transacción administrada para ``settings``."""
    with DatabaseManager(settings).transaction() as connection:
        yield connection


def initialize(settings: Settings) -> None:
    """Compatibilidad: inicializa la base configurada para la aplicación."""
    DatabaseManager(settings).initialize()


def fetch_all(settings: Settings, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Compatibilidad: ejecuta una consulta de lectura y devuelve diccionarios."""
    return DatabaseManager(settings).fetch_all(query, params)
