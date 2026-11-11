"""Persistencia SQLite y migraciones idempotentes de TIPS."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Iterator

from .config import BASE_DIR, Settings
from .security import FieldCipher, hash_bootstrap_password, hash_password, verify_password

SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"
SEED_PATH = BASE_DIR / "sql" / "seed.sql"
SUPERADMIN_EMAIL = "root@demo.com"
SUPERADMIN_INITIAL_PASSWORD = "123456789"
DEMO_PASSWORD = "TipsDemo2026!"
DEMO_ADMIN_EMAIL = "admin@demo.com"
DEMO_USER_EMAIL = "usuario@demo.com"
DEMO_CLIENT_NAMES = (
    "Ana Martínez", "Carlos Hernández", "Daniela López", "Diego Ramírez", "Elena Rivera",
    "Fernando Castillo", "Gabriela Flores", "Hugo Mendoza", "Isabel Torres", "Javier Cruz",
    "Karla Mejía", "Luis Pineda", "Mariana Rivas", "Nicolás Romero", "Olivia Chávez",
    "Pablo Aguilar", "Renata Molina", "Samuel Vásquez", "Valeria Campos", "William Herrera",
)

DEFAULT_SITE_SETTINGS: dict[str, tuple[dict[str, Any], int]] = {
    "theme": ({"primary": "#173d2b", "accent": "#ef7d22", "secondary": "#825334", "surface": "#f7f7f2", "logo_variant": "orange"}, 1),
    "brand": ({"name": "Tips", "currency": "USD", "country": "SV"}, 1),
    "home": ({
        "eyebrow": "Servicios de diseño · objetos · interiores", "title": "TIPS QUE", "highlight": "INSPIRAN",
        "description": "Ideas y soluciones para diseñar mejores espacios, crear objetos útiles y convertir cada proyecto en una experiencia clara y personal.",
        "primary_cta": "Explorar Tips", "secondary_cta": "Ver productos",
    }, 1),
    "contact": ({"location": "San Salvador, El Salvador", "email": "", "whatsapp": "", "instagram": "", "facebook": ""}, 1),
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class DatabaseManager:
    """Administra conexión, transacciones, esquema, migraciones y datos base."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.settings.database_path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute("SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?", (table,)).fetchone() is not None

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _table_sql(connection: sqlite3.Connection, table: str) -> str:
        row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return (row["sql"] or "") if row else ""

    def _migrate_users(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, "users"):
            return
        sql = self._table_sql(connection, "users")
        columns = self._columns(connection, "users")
        needs_rebuild = "superadmin" not in sql or "must_change_password" not in columns or "two_factor_enabled" not in columns
        if not needs_rebuild:
            return

        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE IF EXISTS users_v6_new")
        connection.execute(
            """CREATE TABLE users_v6_new(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN('user','admin','superadmin')),
                must_change_password INTEGER NOT NULL DEFAULT 0 CHECK(must_change_password IN(0,1)),
                two_factor_secret_encrypted TEXT,
                two_factor_enabled INTEGER NOT NULL DEFAULT 0 CHECK(two_factor_enabled IN(0,1)),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN(0,1)),
                failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK(failed_login_count>=0),
                locked_until TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        # Las columnas nuevas reciben defaults seguros. El rol histórico admin se conserva.
        connection.execute(
            """INSERT INTO users_v6_new(
                id,email,password_hash,display_name,role,must_change_password,two_factor_secret_encrypted,
                two_factor_enabled,is_active,failed_login_count,locked_until,created_at,updated_at
            )
            SELECT id,email,password_hash,display_name,
                   CASE WHEN role IN('user','admin') THEN role ELSE 'user' END,
                   0,two_factor_secret_encrypted,0,is_active,failed_login_count,locked_until,created_at,updated_at
            FROM users"""
        )
        connection.execute("DROP TABLE users")
        connection.execute("ALTER TABLE users_v6_new RENAME TO users")
        connection.execute("PRAGMA foreign_keys = ON")
        # Un salto de esquema de autenticación invalida sesiones heredadas una sola vez.
        # Evita que cookies emitidas por una versión anterior sigan autenticadas tras
        # incorporar cambio obligatorio de contraseña y soporte opcional de 2FA administrativo.
        if self._table_exists(connection, "sessions") and "revoked_at" in self._columns(connection, "sessions"):
            connection.execute("UPDATE sessions SET revoked_at=COALESCE(revoked_at, ?)", (_iso_now(),))

    def _migrate_orders(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, "orders"):
            return
        sql = self._table_sql(connection, "orders")
        if "pending_payment" in sql and "payment_failed" in sql and "expired" in sql:
            return
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE IF EXISTS orders_v6_new")
        connection.execute(
            """CREATE TABLE orders_v6_new(
                id INTEGER PRIMARY KEY AUTOINCREMENT,public_id TEXT NOT NULL UNIQUE,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                email TEXT,customer_name TEXT NOT NULL,phone TEXT,
                status TEXT NOT NULL CHECK(status IN('pending_payment','paid','payment_failed','processing','ready','shipped','completed','cancelled','expired','refunded')),
                currency TEXT NOT NULL DEFAULT 'USD' CHECK(length(currency)=3),subtotal_cents INTEGER NOT NULL CHECK(subtotal_cents>=0),
                shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK(shipping_cents>=0),discount_cents INTEGER NOT NULL DEFAULT 0 CHECK(discount_cents>=0),
                total_cents INTEGER NOT NULL CHECK(total_cents>=0),shipping_address_json TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """INSERT INTO orders_v6_new(id,public_id,user_id,email,customer_name,phone,status,currency,subtotal_cents,shipping_cents,discount_cents,total_cents,shipping_address_json,created_at,updated_at)
               SELECT id,public_id,user_id,email,customer_name,phone,
                      CASE WHEN status='pending' THEN 'pending_payment' ELSE status END,
                      currency,subtotal_cents,shipping_cents,discount_cents,total_cents,shipping_address_json,created_at,updated_at
               FROM orders"""
        )
        connection.execute("DROP TABLE orders")
        connection.execute("ALTER TABLE orders_v6_new RENAME TO orders")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id,created_at)")
        connection.execute("PRAGMA foreign_keys = ON")

    def _migrate_additive_columns(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, "carts"):
            return
        cart_columns = self._columns(connection, "carts")
        if "user_id" not in cart_columns:
            connection.execute("ALTER TABLE carts ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_carts_user_status ON carts(user_id,status)")

    def _migrate(self, connection: sqlite3.Connection) -> None:
        # Rebuilds primero; el resto del esquema se vuelve a ejecutar después para
        # crear índices/tablas que dependan de las estructuras nuevas.
        self._migrate_users(connection)
        self._migrate_orders(connection)
        self._migrate_additive_columns(connection)

    def _encrypt_legacy_sensitive_fields(self, connection: sqlite3.Connection) -> None:
        """Cifra datos sensibles heredados de v5 de forma idempotente.

        ``FieldCipher.encrypt`` reconoce el prefijo v1 y no vuelve a cifrar un
        valor ya protegido. Así una base existente puede migrarse en cada
        arranque sin duplicar capas criptográficas.
        """
        cipher = FieldCipher(self.settings.field_encryption_key)
        if self._table_exists(connection, "users"):
            for row in connection.execute("SELECT id,two_factor_secret_encrypted FROM users WHERE two_factor_secret_encrypted IS NOT NULL AND two_factor_secret_encrypted<>''").fetchall():
                protected = cipher.encrypt(row["two_factor_secret_encrypted"], aad="user-2fa")
                if protected != row["two_factor_secret_encrypted"]:
                    connection.execute("UPDATE users SET two_factor_secret_encrypted=? WHERE id=?", (protected, row["id"]))
        if self._table_exists(connection, "quote_requests"):
            for row in connection.execute("SELECT id,contact,message,internal_notes FROM quote_requests").fetchall():
                contact = cipher.encrypt(row["contact"], aad="quote-contact")
                message = cipher.encrypt(row["message"], aad="quote-message")
                notes = cipher.encrypt(row["internal_notes"], aad="quote-notes")
                if (contact, message, notes) != (row["contact"], row["message"], row["internal_notes"]):
                    connection.execute("UPDATE quote_requests SET contact=?,message=?,internal_notes=? WHERE id=?", (contact, message, notes, row["id"]))
        if self._table_exists(connection, "orders"):
            for row in connection.execute("SELECT id,phone,shipping_address_json FROM orders").fetchall():
                phone = cipher.encrypt(row["phone"], aad="order-phone")
                address = cipher.encrypt(row["shipping_address_json"], aad="order-shipping")
                if (phone, address) != (row["phone"], row["shipping_address_json"]):
                    connection.execute("UPDATE orders SET phone=?,shipping_address_json=? WHERE id=?", (phone, address, row["id"]))

    def _ensure_superadmin(self, connection: sqlite3.Connection) -> None:
        """Garantiza root@demo.com sin restaurar la contraseña tras un cambio."""
        now = _iso_now()
        row = connection.execute(
            "SELECT id,password_hash,must_change_password,role FROM users WHERE email=? COLLATE NOCASE",
            (SUPERADMIN_EMAIL,),
        ).fetchone()
        if row:
            if row["role"] != "superadmin":
                raise RuntimeError("El correo reservado para la cuenta raíz ya pertenece a otra cuenta.")
            # Siempre conserva el rol y activación; jamás resetea una contraseña ya existente.
            if row["password_hash"]:
                connection.execute(
                    "UPDATE users SET role='superadmin',is_active=1,updated_at=? WHERE id=?",
                    (now, row["id"]),
                )
            else:
                connection.execute(
                    "UPDATE users SET password_hash=?,role='superadmin',must_change_password=1,is_active=1,updated_at=? WHERE id=?",
                    (hash_bootstrap_password(SUPERADMIN_INITIAL_PASSWORD), now, row["id"]),
                )
            return
        connection.execute(
            """INSERT INTO users(email,password_hash,display_name,role,must_change_password,two_factor_enabled,is_active,failed_login_count,created_at,updated_at)
               VALUES(?,?,?,'superadmin',1,0,1,0,?,?)""",
            (SUPERADMIN_EMAIL, hash_bootstrap_password(SUPERADMIN_INITIAL_PASSWORD), "Superadmin", now, now),
        )

    def _disable_known_demo_credentials(self, connection: sqlite3.Connection) -> None:
        """Desactiva credenciales de demostración intactas en bases migradas."""
        accounts = {SUPERADMIN_EMAIL: SUPERADMIN_INITIAL_PASSWORD, DEMO_ADMIN_EMAIL: DEMO_PASSWORD,
                    DEMO_USER_EMAIL: DEMO_PASSWORD}
        accounts.update({f"cliente{index:02d}@demo.com": DEMO_PASSWORD
                         for index in range(1, len(DEMO_CLIENT_NAMES) + 1)})
        placeholders = ",".join("?" for _ in accounts)
        rows = connection.execute(
            f"SELECT id,email,password_hash FROM users WHERE is_active=1 AND lower(email) IN ({placeholders})",
            tuple(accounts),
        ).fetchall()
        for row in rows:
            if not row["password_hash"] or not verify_password(accounts[row["email"].lower()], row["password_hash"]):
                continue
            connection.execute("UPDATE users SET is_active=0 WHERE id=?", (row["id"],))
            connection.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (_iso_now(), row["id"]))

    def _disable_packaged_sample_accounts(self, connection: sqlite3.Connection) -> None:
        sample_users = """SELECT id FROM users
                          WHERE email GLOB 'muestra-[0-9][0-9][0-9]@tips.test'"""
        connection.execute(f"UPDATE users SET is_active=0 WHERE id IN ({sample_users})")
        connection.execute(
            f"UPDATE sessions SET revoked_at=? WHERE revoked_at IS NULL AND user_id IN ({sample_users})",
            (_iso_now(),),
        )

    def _ensure_demo_users(self, connection: sqlite3.Connection) -> None:
        """Inserta cuentas demo idempotentes para probar todos los roles y listados.

        Las cuentas demo usan una contraseña conocida únicamente porque esta
        distribución está orientada a demostración/local. Nunca se reescribe
        una cuenta existente: cualquier cambio hecho desde el panel se conserva.
        """
        now = _iso_now()
        demo_rows = [
            (DEMO_USER_EMAIL, "Usuario Demo", "user"),
            (DEMO_ADMIN_EMAIL, "Administrador Demo", "admin"),
        ]
        demo_rows.extend(
            (f"cliente{index:02d}@demo.com", name, "user")
            for index, name in enumerate(DEMO_CLIENT_NAMES, start=1)
        )
        missing = [
            row for row in demo_rows
            if connection.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (row[0],)).fetchone() is None
        ]
        if not missing:
            return
        # Una sola derivación PBKDF2 por inicialización evita multiplicar el costo
        # de arranque. Estas cuentas son datos demo y comparten deliberadamente
        # la misma contraseña temporal de pruebas.
        demo_password_hash = hash_password(DEMO_PASSWORD)
        for email, display_name, role in missing:
            exists = connection.execute(
                "SELECT id FROM users WHERE email=? COLLATE NOCASE",
                (email,),
            ).fetchone()
            if exists:
                continue
            connection.execute(
                """INSERT INTO users(
                    email,password_hash,display_name,role,must_change_password,
                    two_factor_enabled,is_active,failed_login_count,created_at,updated_at
                ) VALUES(?,?,?,?,0,0,1,0,?,?)""",
                (email, demo_password_hash, display_name, role, now, now),
            )

    @staticmethod
    def _ensure_catalog_images(connection: sqlite3.Connection) -> None:
        """Add catalog artwork only when a known product has no uploaded photo."""
        manifest = BASE_DIR / "assets/catalog/product-images.json"
        if not manifest.is_file():
            return
        for item in json.loads(manifest.read_text(encoding="utf-8")):
            path = str(item["path"])
            if not path.startswith("assets/catalog/") or not (BASE_DIR / path).is_file():
                continue
            connection.execute(
                """INSERT INTO product_images(product_id,path,alt_text,sort_order,created_at)
                SELECT id,?,?,0,? FROM products WHERE slug=? AND NOT EXISTS
                (SELECT 1 FROM product_images WHERE product_id=products.id)""",
                (path, item["alt"], _iso_now(), item["slug"]),
            )

    @staticmethod
    def _ensure_portfolio_images(connection: sqlite3.Connection) -> None:
        """Complete the built-in portfolio while preserving project photographs."""
        manifest = BASE_DIR / "assets/portfolio/project-images.json"
        if not manifest.is_file():
            return
        for item in json.loads(manifest.read_text(encoding="utf-8")):
            path = item["path"]
            if not (BASE_DIR / path).is_file():
                continue
            connection.execute(
                """INSERT INTO portfolio_images(project_id,path,alt_text,sort_order)
                   SELECT p.id,?,?,0 FROM portfolio_projects p
                   WHERE p.slug=? AND NOT EXISTS
                         (SELECT 1 FROM portfolio_images i WHERE i.project_id=p.id)""",
                (path, item["alt"], item["slug"]),
            )

    def initialize(self) -> None:
        # Copia consistente de SQLite antes de la primera migración 6.5.
        # La copia respeta WAL y no modifica ni reemplaza la base de origen.
        if self.settings.database_path.exists():
            import os
            with self.connect() as source:
                upgraded = self._table_exists(source, "schema_versions") and source.execute("SELECT 1 FROM schema_versions WHERE version='6.5'").fetchone()
                if not upgraded and self._table_exists(source,"users"):
                    backup_path = self.settings.database_path.with_name(self.settings.database_path.name + ".pre-v65.bak")
                    if not backup_path.exists():
                        with sqlite3.connect(backup_path) as backup:
                            source.backup(backup)
                        os.chmod(backup_path,0o600)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connect() as connection:
            # En una base histórica se migran primero las tablas que necesitan
            # nuevas columnas/checks; así el esquema v6 puede crear sus índices.
            if self._table_exists(connection, "users"):
                self._migrate(connection)
            connection.executescript(schema)

            count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if count == 0 and SEED_PATH.exists():
                connection.executescript(SEED_PATH.read_text(encoding="utf-8"))

            for key, (value, is_public) in DEFAULT_SITE_SETTINGS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO site_settings(key,value_json,is_public) VALUES(?,?,?)",
                    (key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), is_public),
                )
            self._ensure_catalog_images(connection)
            self._ensure_portfolio_images(connection)
            self._encrypt_legacy_sensitive_fields(connection)
            if self.settings.environment != "production":
                self._ensure_superadmin(connection)
                self._ensure_demo_users(connection)
            else:
                self._disable_known_demo_credentials(connection)
                self._disable_packaged_sample_accounts(connection)
            from .operations import migrate
            migrate(connection)
            cipher = FieldCipher(self.settings.field_encryption_key)
            with self.transaction() as db:
                rows = db.execute("SELECT owner,request_key,kind,response_json FROM request_keys WHERE response_json NOT LIKE 'enc:v1:%'")
                for row in rows:
                    db.execute(
                        "UPDATE request_keys SET response_json=? WHERE owner=? AND request_key=? AND kind=?",
                        (cipher.encrypt(row["response_json"], aad="request-response"), row["owner"], row["request_key"], row["kind"]),
                    )

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def connect(settings: Settings) -> sqlite3.Connection:
    return DatabaseManager(settings).connect()


@contextmanager
def transaction(settings: Settings) -> Iterator[sqlite3.Connection]:
    with DatabaseManager(settings).transaction() as connection:
        yield connection


def initialize(settings: Settings) -> None:
    DatabaseManager(settings).initialize()


def fetch_all(settings: Settings, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return DatabaseManager(settings).fetch_all(query, params)
