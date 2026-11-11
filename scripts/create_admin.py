"""Comando interactivo para crear o actualizar una cuenta administradora.

El script usa las mismas clases de configuración, persistencia y seguridad que
la aplicación. De esta forma no duplica reglas sensibles como el hash de
contraseñas o el manejo de transacciones.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
import re
import sys

# Al ejecutar ``python scripts/create_admin.py`` Python toma ``scripts/`` como
# directorio inicial de importación. Añadimos la raíz para que ``backend`` se
# resuelva igual en Windows, macOS y Linux.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import Settings
from backend.database import DatabaseManager
from backend.security import PasswordHasher
from backend.server import TipsRequestHandler

EMAIL_RE = re.compile(r"^[^@\s]{1,120}@[^@\s]{1,180}\.[^@\s]{2,40}$")


class AdminAccountCreator:
    """Orquesta la creación segura de administradores desde la terminal."""

    def __init__(self, settings: Settings) -> None:
        """Prepara los servicios reutilizados por el comando interactivo."""
        self.settings = settings
        self.database = DatabaseManager(settings)
        self.passwords = PasswordHasher()

    @staticmethod
    def _now() -> str:
        """Devuelve una marca UTC consistente con el resto de la aplicación."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _read_identity() -> tuple[str, str]:
        """Solicita y valida correo y nombre visible antes de tocar la base."""
        email = input("Correo: ").strip().lower()
        name = input("Nombre visible: ").strip()
        if not EMAIL_RE.match(email):
            raise SystemExit("Correo inválido.")
        if len(name) < 2:
            raise SystemExit("El nombre visible debe tener al menos 2 caracteres.")
        return email, name

    def run(self, *, root: bool = False) -> None:
        """Ejecuta el flujo interactivo y persiste la cuenta de forma atómica."""
        self.database.initialize()
        role = "superadmin" if root else "admin"
        print("Crear / actualizar " + ("cuenta raíz" if root else "administrador de Tips"))
        email, name = self._read_identity()
        password = getpass("Contraseña (mínimo 12 caracteres): ")
        password_hash = self.passwords.hash(password)
        stamp = self._now()

        with self.database.transaction() as db:
            existing = db.execute("SELECT id,role FROM users WHERE email=?", (email,)).fetchone()
            if root:
                other_root = db.execute("SELECT 1 FROM users WHERE role='superadmin' AND email<>?", (email,)).fetchone()
                if other_root:
                    raise SystemExit("Ya existe una cuenta raíz. Usa su correo para actualizarla.")
            elif existing and existing["role"] == "superadmin":
                raise SystemExit("Para actualizar la cuenta raíz usa --root.")
            if existing:
                db.execute(
                    """UPDATE users
                    SET password_hash=?,display_name=?,role=?,is_active=1,must_change_password=0,
                        failed_login_count=0,locked_until=NULL,updated_at=?
                    WHERE id=?""",
                    (password_hash, name, role, stamp, existing["id"]),
                )
                db.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (stamp, existing["id"]))
                TipsRequestHandler._invalidate_recovery(db, existing["id"])
                message = "Cuenta actualizada correctamente."
            else:
                db.execute(
                    """INSERT INTO users(
                        email,password_hash,display_name,role,is_active,created_at,updated_at
                    ) VALUES(?,?,?,?,1,?,?)""",
                    (email, password_hash, name, role, stamp, stamp),
                )
                message = "Administrador creado correctamente."

        print(message)
        print("Ahora inicia el servidor con: python app.py")
        print("Luego entra a: http://127.0.0.1:8000/cuenta.html")


def main() -> None:
    """Crea el objeto del comando usando la configuración actual y lo ejecuta."""
    parser = argparse.ArgumentParser(description="Provisiona una cuenta administrativa de TIPS.")
    parser.add_argument("--root", action="store_true", help="Crea o actualiza la cuenta raíz.")
    AdminAccountCreator(Settings.load()).run(root=parser.parse_args().root)


if __name__ == "__main__":
    main()
