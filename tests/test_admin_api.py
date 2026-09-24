import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

from backend.config import Settings
from backend.database import initialize, transaction
from backend.runtime import create_server
from backend.security import hash_password


class AdminApiTests(unittest.TestCase):
    def setUp(self):
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
        initialize(self.settings)
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with transaction(self.settings) as db:
            db.execute(
                "INSERT INTO users(email,password_hash,display_name,role,is_active,created_at,updated_at) VALUES(?,?,?,'admin',1,?,?)",
                ("admin@example.com", hash_password("AdminSeguro123!"), "Admin Tips", stamp, stamp),
            )
        self.server = create_server(self.settings)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def get_json(self, path):
        with self.opener.open(self.base + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload, csrf):
        request = Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
        )
        with self.opener.open(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_admin_can_edit_public_content_and_receive_dashboard_data(self):
        status, csrf_payload = self.get_json("/api/csrf")
        self.assertEqual(status, 200)
        csrf = csrf_payload["csrf_token"]

        status, login = self.post_json(
            "/api/auth/login",
            {"email": "admin@example.com", "password": "AdminSeguro123!"},
            csrf,
        )
        self.assertEqual(status, 200)
        self.assertEqual(login["user"]["role"], "admin")

        status, overview = self.get_json("/api/admin/overview")
        self.assertEqual(status, 200)
        self.assertIn("alerts", overview)
        self.assertGreaterEqual(overview["metrics"]["products"], 1)

        status, saved = self.post_json(
            "/api/admin/settings/save",
            {
                "key": "home",
                "is_public": True,
                "value": {
                    "eyebrow": "Prueba",
                    "title": "TIPS",
                    "highlight": "EDITABLE",
                    "description": "Contenido administrable",
                    "primary_cta": "Ver proyectos",
                    "secondary_cta": "Ver tienda",
                },
            },
            csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(saved["ok"])

        status, public_settings = self.get_json("/api/site-settings")
        self.assertEqual(status, 200)
        self.assertEqual(public_settings["settings"]["home"]["highlight"], "EDITABLE")


if __name__ == "__main__":
    unittest.main()
