import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from backend.config import Settings
from backend.database import connect, initialize, transaction
from backend.payments import PaymentService, SandboxPaymentProvider
from backend.runtime import create_server
from backend.security import FieldCipher, TotpManager, verify_password


class V6SecurityPaymentTests(unittest.TestCase):
    def make_settings(self, tmp: str) -> Settings:
        return Settings(
            "test", "127.0.0.1", 0, Path(tmp) / "tips.db",
            ("http://127.0.0.1",), "v6-test-secret-key-with-enough-entropy",
            False, 3600, 1048576, 500,
            "v6-field-key", "v6-webhook-secret", "sandbox", 15, 30, 5,
        )

    def test_root_bootstrap_is_hashed_and_never_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(tmp)
            initialize(settings)
            with transaction(settings) as db:
                row = db.execute(
                    "SELECT id,email,password_hash,role,must_change_password FROM users WHERE email='root@demo.com'"
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["role"], "superadmin")
                self.assertEqual(row["must_change_password"], 1)
                self.assertNotEqual(row["password_hash"], "123456789")
                self.assertTrue(verify_password("123456789", row["password_hash"]))
                db.execute("UPDATE users SET password_hash='custom-hash-sentinel',must_change_password=0 WHERE id=?", (row["id"],))
            initialize(settings)
            with connect(settings) as db:
                row = db.execute("SELECT password_hash,must_change_password,role FROM users WHERE email='root@demo.com'").fetchone()
                self.assertEqual(row["password_hash"], "custom-hash-sentinel")
                self.assertEqual(row["must_change_password"], 0)
                self.assertEqual(row["role"], "superadmin")

    def test_field_cipher_is_authenticated_and_not_plaintext(self):
        cipher = FieldCipher("field-key-test")
        protected = cipher.encrypt("+503 7000-0000", aad="order-phone")
        self.assertTrue(protected.startswith("enc:v1:"))
        self.assertNotIn("7000-0000", protected)
        self.assertEqual(cipher.decrypt(protected, aad="order-phone"), "+503 7000-0000")
        with self.assertRaises(Exception):
            cipher.decrypt(protected, aad="wrong-aad")

    def test_signed_webhook_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(tmp)
            initialize(settings)
            service = PaymentService(settings)
            self.assertIsInstance(service.provider, SandboxPaymentProvider)
            with transaction(settings) as db:
                now = "2026-09-28T12:00:00+00:00"
                cur = db.execute(
                    """INSERT INTO orders(public_id,email,customer_name,status,currency,subtotal_cents,shipping_cents,discount_cents,total_cents,shipping_address_json,created_at,updated_at)
                       VALUES('TIPS-IDEMP','idemp@example.com','Prueba','pending_payment','USD',1000,0,0,1000,'{}',?,?)""",
                    (now, now),
                )
                order_id = cur.lastrowid
                pcur = db.execute(
                    """INSERT INTO payments(order_id,provider,provider_payment_id,status,amount_cents,currency,idempotency_key,created_at,updated_at)
                       VALUES(?, 'sandbox', 'pay_idempotent', 'pending', 1000, 'USD', 'idem-key', ?, ?)""",
                    (order_id, now, now),
                )
                payment_id = pcur.lastrowid
                raw, signature = service.provider.simulated_event("pay_idempotent", succeeded=True)
                first = service.handle_webhook(db, raw, signature)
                second = service.handle_webhook(db, raw, signature)
                self.assertFalse(first["duplicate"])
                self.assertTrue(second["duplicate"])
                self.assertEqual(db.execute("SELECT status FROM payments WHERE id=?", (payment_id,)).fetchone()[0], "paid")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM payment_webhook_events").fetchone()[0], 1)

    def test_root_must_change_password_then_enable_two_factor(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(tmp)
            initialize(settings)
            server = create_server(settings)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            try:
                def get_json(path):
                    with opener.open(base + path, timeout=5) as response:
                        return response.status, json.loads(response.read().decode())

                def post_json(path, payload, csrf):
                    request = Request(base + path, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
                    with opener.open(request, timeout=5) as response:
                        return response.status, json.loads(response.read().decode())

                _, csrf_data = get_json("/api/csrf")
                csrf = csrf_data["csrf_token"]
                status, login = post_json("/api/auth/login", {"email": "root@demo.com", "password": "123456789"}, csrf)
                self.assertEqual(status, 200)
                self.assertTrue(login["user"]["must_change_password"])
                csrf = login["csrf_token"]

                # Un visitante recibe la plantilla propia y el código HTTP correcto, no la página cruda de SimpleHTTP.
                guest = build_opener(HTTPCookieProcessor(CookieJar()))
                with self.assertRaises(HTTPError) as raised:
                    guest.open(base + "/ruta-que-no-existe", timeout=5)
                self.assertEqual(raised.exception.code, 404)
                body = raised.exception.read().decode("utf-8")
                self.assertIn("Esta página no existe", body)
                self.assertNotIn("Error response", body)

                status, changed = post_json("/api/account/password", {"current_password": "123456789", "new_password": "NuevaClaveRoot123!"}, csrf)
                self.assertEqual(status, 200)
                self.assertFalse(changed["two_factor_setup_required"])

                _, setup = get_json("/api/auth/2fa/setup")
                secret = setup["secret"]
                code = TotpManager().code(secret)
                status, enabled = post_json("/api/auth/2fa/enable", {"code": code}, csrf)
                self.assertEqual(status, 200)
                self.assertTrue(enabled["enabled"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
