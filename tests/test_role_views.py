import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

from backend.config import Settings
from backend.database import initialize, transaction
from backend.runtime import create_server
from backend.security import hash_password


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RoleViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            "test", "127.0.0.1", 0, Path(self.tmp.name) / "tips.db",
            ("http://127.0.0.1",), "test-secret-key-with-enough-entropy",
            False, 3600, 1048576, 500,
        )
        initialize(self.settings)
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with transaction(self.settings) as db:
            db.execute(
                "INSERT INTO users(email,password_hash,display_name,role,is_active,created_at,updated_at) VALUES(?,?,?,'admin',1,?,?)",
                ("admin@example.com", hash_password("AdminSeguro123!"), "Admin Tips", stamp, stamp),
            )
            db.execute(
                "INSERT INTO product_images(product_id,path,alt_text,sort_order,created_at) VALUES(1,'assets/uploads/products/1/demo.webp','Demo',0,?)",
                (stamp,),
            )
        self.server = create_server(self.settings)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.tmp.cleanup()

    def opener(self):
        return build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())

    def get_json(self, opener, path):
        with opener.open(self.base + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, opener, path, payload, csrf):
        request = Request(self.base + path, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
        with opener.open(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def redirect_location(self, opener, path):
        try:
            opener.open(self.base + path, timeout=5)
        except HTTPError as exc:
            self.assertEqual(exc.code, 303)
            return exc.headers["Location"]
        self.fail("Se esperaba redirección")

    def login(self, opener, email, password):
        _, token = self.get_json(opener, "/api/csrf")
        return self.post_json(opener, "/api/auth/login", {"email": email, "password": password}, token["csrf_token"])

    def test_private_views_are_isolated_by_role(self):
        guest = self.opener()
        self.assertTrue(self.redirect_location(guest, "/admin/").startswith("/cuenta.html"))
        self.assertTrue(self.redirect_location(guest, "/user/").startswith("/cuenta.html"))

        user = self.opener()
        _, token = self.get_json(user, "/api/csrf")
        status, _ = self.post_json(user, "/api/auth/register", {"display_name": "Cliente", "email": "cliente@example.com", "password": "ClienteSeguro123!"}, token["csrf_token"])
        self.assertEqual(status, 201)
        self.assertEqual(self.redirect_location(user, "/admin/"), "/user/")
        with user.open(self.base + "/user/", timeout=5) as response:
            self.assertEqual(response.status, 200)

        admin = self.opener()
        status, login = self.login(admin, "admin@example.com", "AdminSeguro123!")
        self.assertEqual(status, 200)
        self.assertEqual(login["user"]["role"], "admin")
        self.assertEqual(self.redirect_location(admin, "/user/"), "/admin/")
        with admin.open(self.base + "/admin/", timeout=5) as response:
            self.assertEqual(response.status, 200)

        for public_path in ("/", "/index.html", "/tienda.html", "/cuenta.html"):
            self.assertEqual(self.redirect_location(admin, public_path), "/admin/")

    def test_product_images_are_returned_as_root_urls(self):
        opener = self.opener()
        status, data = self.get_json(opener, "/api/products")
        self.assertEqual(status, 200)
        first = next(item for item in data["items"] if item["id"] == 1)
        self.assertEqual(first["primary_image"], "/assets/uploads/products/1/demo.webp")

    def test_public_views_keep_their_urls_after_reorganization(self):
        opener = self.opener()
        for path in ("/", "/index.html", "/tienda.html", "/arquitectura.html", "/contacto.html", "/checkout.html", "/merchandise.html", "/proyecto.html", "/cuenta.html"):
            with opener.open(self.base + path, timeout=5) as response:
                self.assertEqual(response.status, 200, path)
                self.assertIn("text/html", response.headers.get("Content-Type", ""), path)

        with self.assertRaises(HTTPError) as direct_public:
            opener.open(self.base + "/public/index.html", timeout=5)
        self.assertEqual(direct_public.exception.code, 404)

    def test_legacy_private_view_urls_redirect_without_legacy_files(self):
        guest = self.opener()
        self.assertEqual(self.redirect_location(guest, "/admin.html"), "/admin/")
        self.assertTrue(self.redirect_location(guest, "/perfil.html").startswith("/cuenta.html"))


if __name__ == "__main__":
    unittest.main()
