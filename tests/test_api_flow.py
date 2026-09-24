import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

from backend.config import Settings
from backend.database import initialize
from backend.runtime import create_server


class ApiFlowTests(unittest.TestCase):
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
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
            },
        )
        with self.opener.open(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_customer_can_register_add_product_and_complete_demo_checkout(self):
        status, products = self.get_json("/api/products")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(products["items"]), 8)
        first = products["items"][0]
        self.assertIsInstance(first["first_variant_id"], int)
        self.assertIn("primary_image", first)

        status, portfolio = self.get_json("/api/portfolio")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(portfolio["items"]), 6)

        status, csrf_payload = self.get_json("/api/csrf")
        self.assertEqual(status, 200)
        csrf = csrf_payload["csrf_token"]

        status, registration = self.post_json(
            "/api/auth/register",
            {
                "display_name": "Cliente Prueba",
                "email": "cliente@example.com",
                "password": "UnaClaveSegura123!",
            },
            csrf,
        )
        self.assertEqual(status, 201)
        self.assertEqual(registration["user"]["role"], "user")

        status, cart = self.post_json(
            "/api/cart/items",
            {
                "variant_id": first["first_variant_id"],
                "quantity": 2,
                "customization_value_ids": [],
            },
            csrf,
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 2)

        status, order = self.post_json(
            "/api/checkout/mock",
            {
                "customer_name": "Cliente Prueba",
                "email": "cliente@example.com",
                "phone": "+503 7000-0000",
                "shipping_address": {
                    "address": "Colonia de prueba, casa 1",
                    "city": "San Salvador",
                    "region": "San Salvador",
                    "country": "SV",
                    "notes": "Orden automática de prueba",
                },
            },
            csrf,
        )
        self.assertEqual(status, 201)
        self.assertEqual(order["status"], "paid")
        self.assertEqual(order["payment_provider"], "mock")
        self.assertTrue(order["public_id"].startswith("TIPS-"))

        status, final_cart = self.get_json("/api/cart")
        self.assertEqual(status, 200)
        self.assertEqual(final_cart["items"], [])

    def test_customer_can_manage_profile_password_and_deactivate_account(self):
        _, csrf_payload = self.get_json("/api/csrf")
        csrf = csrf_payload["csrf_token"]
        status, _ = self.post_json(
            "/api/auth/register",
            {"display_name": "Cliente Perfil", "email": "perfil@example.com", "password": "ClaveInicial123!"},
            csrf,
        )
        self.assertEqual(status, 201)

        status, account = self.get_json("/api/account")
        self.assertEqual(status, 200)
        self.assertEqual(account["user"]["display_name"], "Cliente Perfil")
        self.assertTrue(account["user"]["has_password"])

        status, updated = self.post_json(
            "/api/account/profile",
            {"display_name": "Cliente Actualizado", "email": "perfil@example.com", "current_password": ""},
            csrf,
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["user"]["display_name"], "Cliente Actualizado")

        status, password = self.post_json(
            "/api/account/password",
            {"current_password": "ClaveInicial123!", "new_password": "ClaveNuevaSegura456!"},
            csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(password["ok"])

        status, deactivated = self.post_json(
            "/api/account/deactivate",
            {"current_password": "ClaveNuevaSegura456!", "confirmation": "DESACTIVAR"},
            csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(deactivated["ok"])


if __name__ == "__main__":
    unittest.main()
