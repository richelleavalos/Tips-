import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

from backend.config import BASE_DIR, Settings
from backend.database import DEMO_PASSWORD, initialize, transaction
from backend.runtime import create_server
from backend.security import FieldCipher, TotpManager, hash_password, verify_password


class V63UsersAndCartTests(unittest.TestCase):
    def settings_for(self, folder: str) -> Settings:
        return Settings(
            "test", "127.0.0.1", 0, Path(folder) / "tips.db",
            ("http://127.0.0.1",), "test-secret-key-with-enough-entropy",
            False, 3600, 1048576, 500,
        )

    def test_demo_users_cover_roles_and_twenty_test_clients(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = self.settings_for(folder)
            initialize(settings)
            with settings.database_path.open("rb"):
                pass
            import sqlite3
            db = sqlite3.connect(settings.database_path)
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT email,password_hash,role FROM users ORDER BY email").fetchall()
            by_email = {row["email"]: row for row in rows}
            self.assertEqual(by_email["root@demo.com"]["role"], "superadmin")
            self.assertEqual(by_email["admin@demo.com"]["role"], "admin")
            self.assertEqual(by_email["usuario@demo.com"]["role"], "user")
            client_rows = [row for row in rows if row["email"].startswith("cliente") and row["email"].endswith("@demo.com")]
            self.assertEqual(len(client_rows), 20)
            self.assertTrue(all(row["role"] == "user" for row in client_rows))
            self.assertTrue(verify_password(DEMO_PASSWORD, by_email["usuario@demo.com"]["password_hash"]))
            db.close()

    def test_root_can_create_user_and_admin_with_forced_password_change(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = self.settings_for(folder)
            initialize(settings)
            stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            secret = TotpManager.new_secret()
            with transaction(settings) as db:
                protected = FieldCipher(settings.field_encryption_key).encrypt(secret, aad="user-2fa")
                db.execute(
                    "UPDATE users SET password_hash=?,must_change_password=0,two_factor_secret_encrypted=?,two_factor_enabled=1,updated_at=? WHERE email='root@demo.com'",
                    (hash_password("RootSeguro2026!"), protected, stamp),
                )

            server = create_server(settings)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with opener.open(base + "/api/csrf", timeout=5) as response:
                    csrf = json.loads(response.read().decode())["csrf_token"]

                def post(path, payload):
                    request = Request(
                        base + path,
                        data=json.dumps(payload).encode(),
                        method="POST",
                        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
                    )
                    with opener.open(request, timeout=5) as response:
                        return response.status, json.loads(response.read().decode())

                status, login = post("/api/auth/login", {"email": "root@demo.com", "password": "RootSeguro2026!"})
                self.assertEqual(status, 200)
                self.assertTrue(login["two_factor_required"])
                status, login = post("/api/auth/2fa/verify-login", {"challenge_token": login["challenge_token"], "code": TotpManager().code(secret)})
                self.assertEqual(status, 200)
                self.assertEqual(login["user"]["role"], "superadmin")
                csrf = login["csrf_token"]

                for role, email in (("user", "creado.user@example.com"), ("admin", "creado.admin@example.com")):
                    status, created = post("/api/admin/users/create", {
                        "display_name": f"Creado {role}", "email": email,
                        "role": role, "temporary_password": "TemporalSeguro2026!",
                    })
                    self.assertEqual(status, 201)
                    self.assertEqual(created["user"]["role"], role)
                    self.assertTrue(created["user"]["must_change_password"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_public_bag_uses_one_stable_drawer_contract(self):
        app = (BASE_DIR / "frontend/usuario/js/app.js").read_text(encoding="utf-8")
        css = (BASE_DIR / "frontend/usuario/css/public.css").read_text(encoding="utf-8")
        self.assertIn("async openCartDrawer()", app)
        self.assertIn('button.setAttribute("aria-expanded", "true")', app)
        self.assertIn('.cart-drawer.is-open .cart-panel', css)
        self.assertIn('.cart-loading', css)
        for name in ("index.html", "tienda.html", "arquitectura.html"):
            html = (BASE_DIR / "frontend/usuario/vistas/publicas" / name).read_text(encoding="utf-8")
            self.assertIn('type="button" data-cart-open', html, name)
            self.assertIn('aria-controls="tips-cart-drawer"', html, name)
            self.assertIn('id="tips-cart-drawer"', html, name)
            self.assertRegex(html, r'app\.js\?v=6\.\d+', name)


if __name__ == "__main__":
    unittest.main()
