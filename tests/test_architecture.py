"""Pruebas de la arquitectura orientada a objetos introducida en el refactor."""

from pathlib import Path
import tempfile
import unittest

from backend.application import TipsApplication
from backend.config import Settings
from backend.database import DatabaseManager
from backend.security import CsrfProtection, PasswordHasher, SessionTokenManager


class ArchitectureTests(unittest.TestCase):
    """Comprueba los servicios base sin depender de una base real del proyecto."""

    def setUp(self) -> None:
        """Crea configuración aislada para evitar modificar ``data/tips.db``."""
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            "test",
            "127.0.0.1",
            0,
            Path(self.tmp.name) / "tips.db",
            ("http://127.0.0.1",),
            "test-secret-key-with-enough-entropy",
            False,
            3600,
            1048576,
            500,
        )

    def tearDown(self) -> None:
        """Elimina la base temporal creada durante cada prueba."""
        self.tmp.cleanup()

    def test_database_manager_initializes_and_queries(self) -> None:
        """Verifica que DatabaseManager concentre inicialización y lecturas."""
        database = DatabaseManager(self.settings)
        database.initialize()
        rows = database.fetch_all("SELECT name FROM categories ORDER BY id LIMIT 1")
        self.assertEqual(len(rows), 1)
        self.assertIn("name", rows[0])

    def test_security_objects_keep_existing_contracts(self) -> None:
        """Verifica hashes, tokens de sesión y protección CSRF orientados a objetos."""
        passwords = PasswordHasher()
        encoded = passwords.hash("ArquitecturaSegura123!")
        self.assertTrue(passwords.verify("ArquitecturaSegura123!", encoded))
        self.assertFalse(passwords.verify("incorrecta", encoded))

        session = SessionTokenManager.create()
        self.assertEqual(len(SessionTokenManager.digest(session)), 64)

        csrf = CsrfProtection("secret")
        token = csrf.create(session, now=100)
        self.assertTrue(csrf.verify(token, session, now=101))
        self.assertFalse(csrf.verify(token, "otra-sesion", now=101))

    def test_application_prepares_server_without_starting_it(self) -> None:
        """Comprueba que TipsApplication coordine base y servidor sin ejecutar el loop."""
        application = TipsApplication(self.settings)
        server = application.prepare()
        self.assertEqual(server.server_address[0], "127.0.0.1")
        application.close()


if __name__ == "__main__":
    unittest.main()
