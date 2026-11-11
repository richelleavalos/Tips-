"""Pentest reproducible de TIPS. Servidor loopback y base descartable."""
import base64
import http.client
import io
import json
import secrets
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from backend.config import Settings
from backend.database import connect, initialize
from backend.runtime import create_server
from backend.security import FieldCipher, RateLimiter, session_token_hash
from backend.server import iso, utc_now


class BrowserSession:
    def __init__(self, port, cookie=""):
        self.port = port
        self.cookie = cookie

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=12)
        try:
            connection.request(method, path, body, {"Cookie": self.cookie, **(headers or {})})
            response = connection.getresponse()
            raw = response.read()
            self.headers = response.headers
            if cookie := response.getheader("Set-Cookie"):
                self.cookie = cookie.split(";", 1)[0]
            return response.status, json.loads(raw) if raw and "application/json" in response.getheader("Content-Type", "") else raw
        finally:
            connection.close()

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, data, *, csrf=None, headers=None):
        if csrf is None:
            csrf = self.get("/api/csrf")[1]["csrf_token"]
        return self.request("POST", path, json.dumps(data), {
            "Content-Type": "application/json", "X-CSRF-Token": csrf, **(headers or {})
        })


class SecurityAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.settings = replace(Settings.load(), environment="test", host="127.0.0.1", port=0,
                               secure_cookies=False, rate_limit_per_minute=10000,
                               database_path=Path(cls.tmp.name) / "audit.db")
        initialize(cls.settings)
        cls.server = create_server(cls.settings)
        cls.handler = cls.server.RequestHandlerClass
        cls.handler.sensitive_rate_limiter = RateLimiter(10000)
        cls.handler.log_message = lambda *args: None
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)
        cls.port = cls.server.server_address[1]
        cls.admin = BrowserSession(cls.port)
        assert cls.admin.post("/api/auth/login", {"email": "admin@demo.com", "password": "TipsDemo2026!"})[0] == 200
        cls.owner, cls.uid = cls.register()
        cls.other, _ = cls.register()
        with connect(cls.settings) as db:
            cls.variant = db.execute("SELECT id FROM product_variants WHERE stock_quantity>=2 LIMIT 1").fetchone()[0]
        cls.file = cls.upload(cls.owner)
        status, result = cls.owner.post("/api/quotes", cls.quote_data(upload_ids=[cls.file]))
        assert status == 201, result
        cls.quote_id = result["id"]
        cls.token = result["tracking_url"].split("#token=")[1]
        assert cls.owner.post("/api/cart/items", {"variant_id": cls.variant, "quantity": 1})[0] == 201
        status, order = cls.owner.post("/api/checkout/create", cls.order_data())
        assert status == 201, order
        cls.order_id = order["order_id"]

    @classmethod
    def register(cls):
        client = BrowserSession(cls.port)
        email = f"audit-{secrets.token_hex(6)}@tips.test"
        status, result = client.post("/api/auth/register", {
            "display_name": "Persona de prueba", "email": email,
            "password": "AuditLocalOnly!2026", "phone": "71234567", "role": "superadmin"
        })
        assert status == 201, result
        return client, result["user"]["id"]

    @staticmethod
    def quote_data(**extra):
        return {"name": "Persona de prueba", "phone": "71234567", "project_type": "Interior",
                "message": "Descripción ficticia para una prueba de seguridad.",
                "idempotency_key": secrets.token_hex(18), **extra}

    @staticmethod
    def order_data(**extra):
        return {"customer_name": "Persona de prueba", "phone": "71234567",
                "idempotency_key": secrets.token_hex(18), **extra}

    @classmethod
    def upload(cls, client):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buffer, "PNG")
        contents = buffer.getvalue()
        status, upload = client.post("/api/ops/uploads/start", {"size": len(contents), "name": "prueba.png"})
        assert status == 200
        status, result = client.post("/api/ops/uploads/chunk", {
            "id": upload["id"], "offset": 0, "data": base64.b64encode(contents).decode()
        })
        assert status == 200 and result["completed"], result
        return upload["id"]

    def guest(self):
        return BrowserSession(self.port)

    def test_01_forced_browsing(self):
        self.assertEqual(self.guest().get("/admin/")[0], 303)

    def test_02_head_route_bypass(self):
        self.assertEqual(self.guest().request("HEAD", "/backend/server.py")[0], 404)

    def test_03_path_traversal(self):
        for path in ("/assets/../backend/server.py", "/assets/%2e%2e/backend/server.py", "/.env"):
            self.assertEqual(self.guest().get(path)[0], 404)

    def test_04_directory_listing(self):
        self.assertEqual(self.guest().get("/assets/")[0], 404)

    def test_05_verb_tampering(self):
        self.assertIn(self.guest().request("PUT", "/api/admin/users/update")[0], (405, 501))

    def test_06_missing_authentication(self):
        self.assertEqual(self.guest().get("/api/account")[0], 401)

    def test_07_vertical_role_bypass(self):
        self.assertEqual(self.owner.get("/api/admin/overview")[0], 403)

    def test_08_legacy_route_authorization(self):
        self.assertEqual(self.owner.post("/api/admin/orders/update", {"id": self.order_id})[0], 403)

    def test_09_mass_assignment(self):
        self.assertEqual(self.owner.get("/api/auth/me")[1]["user"]["role"], "user")

    def test_10_role_delegation(self):
        _, target = self.register()
        self.assertEqual(self.admin.post("/api/admin/users/update", {"id": target, "role": "admin"})[0], 403)

    def test_11_order_idor(self):
        self.assertEqual(self.other.get(f"/api/ops/detail?kind=order&id={self.order_id}")[0], 404)

    def test_12_quote_idor(self):
        self.assertEqual(self.other.get(f"/api/ops/detail?kind=quote&id={self.quote_id}")[0], 404)

    def test_13_file_idor(self):
        self.assertEqual(self.other.get(f"/api/ops/file/{self.file}?thumbnail=1")[0], 404)

    def test_14_token_record_binding(self):
        self.assertEqual(self.guest().get(f"/api/ops/detail?kind=order&id={self.order_id}&token={self.token}")[0], 404)

    def test_15_draft_isolation(self):
        self.owner.post("/api/ops/draft", {"payload": {"message": "private-marker"}})
        self.assertEqual(self.other.get("/api/ops/draft")[1]["payload"], {})

    def test_16_upload_attachment_takeover(self):
        pending = self.upload(self.owner)
        self.assertEqual(self.other.post("/api/quotes", self.quote_data(upload_ids=[pending]))[0], 400)

    def test_17_notification_object_authorization(self):
        self.owner.get("/api/ops/notifications")
        with connect(self.settings) as db:
            nid = db.execute("SELECT id FROM notifications WHERE user_id=? LIMIT 1", (self.uid,)).fetchone()[0]
        self.other.post("/api/ops/read", {"id": nid})
        with connect(self.settings) as db:
            self.assertFalse(db.execute("SELECT 1 FROM notification_reads WHERE notification_id=?", (nid,)).fetchone())

    def test_18_cross_origin_mutation(self):
        self.assertEqual(self.owner.post("/api/ops/draft", {}, headers={"Origin": "https://outside.invalid"})[0], 403)

    def test_19_csrf_missing(self):
        self.assertEqual(self.owner.post("/api/ops/draft", {}, csrf="")[0], 403)

    def test_20_csrf_cross_session(self):
        token = self.owner.get("/api/csrf")[1]["csrf_token"]
        self.assertEqual(self.other.post("/api/ops/draft", {}, csrf=token)[0], 403)

    def test_21_session_fixation_login(self):
        victim = self.guest()
        victim.get("/api/csrf")
        attacker = BrowserSession(self.port, victim.cookie)
        self.assertEqual(victim.post("/api/auth/login", {"email": "admin@demo.com", "password": "TipsDemo2026!"})[0], 200)
        self.assertFalse(attacker.get("/api/auth/me")[1]["authenticated"])

    def test_22_session_fixation_registration(self):
        victim = self.guest()
        victim.get("/api/csrf")
        attacker = BrowserSession(self.port, victim.cookie)
        self.assertEqual(victim.post("/api/auth/register", {
            "display_name": "Otra persona", "email": "fixation@tips.test",
            "password": "AuditLocalOnly!2026", "phone": "71234567"
        })[0], 201)
        self.assertFalse(attacker.get("/api/auth/me")[1]["authenticated"])

    def test_23_logout_replay(self):
        client, _ = self.register()
        replay = BrowserSession(self.port, client.cookie)
        self.assertEqual(client.post("/api/auth/logout", {})[0], 200)
        self.assertEqual(replay.get("/api/account")[0], 401)

    def test_24_expired_session(self):
        client, _ = self.register()
        with connect(self.settings) as db:
            db.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?",
                       (iso(utc_now() - timedelta(seconds=2)), session_token_hash(client.cookie.split("=", 1)[1])))
        self.assertEqual(client.get("/api/account")[0], 401)

    def test_25_cookie_flags(self):
        client = self.guest()
        client.get("/api/csrf")
        for flag in ("HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, client.headers.get("Set-Cookie"))

    def test_26_cache_sensitive_navigation(self):
        client = self.admin
        client.get("/")
        self.assertNotIn("public", ",".join(client.headers.get_all("Cache-Control", [])))
        self.assertIn("no-store", ",".join(client.headers.get_all("Cache-Control", [])))

    def test_27_clickjacking(self):
        client = self.guest()
        client.get("/")
        self.assertEqual(client.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors 'none'", client.headers.get("Content-Security-Policy"))

    def test_28_cors_preflight(self):
        client = self.guest()
        self.assertEqual(client.request("OPTIONS", "/api/account", headers={"Origin": "null"})[0], 403)
        self.assertIsNone(client.headers.get("Access-Control-Allow-Origin"))

    def test_29_sql_injection(self):
        result = self.other.get("/api/ops/records?search=" + quote("' OR 1=1 --"))
        self.assertEqual(result[0], 200)
        self.assertFalse(result[1]["items"])

    def test_30_malformed_json(self):
        token = self.owner.get("/api/csrf")[1]["csrf_token"]
        status, _ = self.owner.request("POST", "/api/ops/draft", "{", {"Content-Type":"application/json","X-CSRF-Token":token})
        self.assertEqual(status, 400)

    def test_31_duplicate_json_parameters(self):
        token = self.owner.get("/api/csrf")[1]["csrf_token"]
        status, _ = self.owner.request("POST", "/api/ops/draft", '{"payload":{},"payload":{"x":1}}',
                                       {"Content-Type":"application/json","X-CSRF-Token":token})
        self.assertEqual(status, 400)

    def test_32_out_of_range_pagination(self):
        self.assertEqual(self.owner.get("/api/ops/records?page=999999999999999999999999")[0], 400)

    def test_33_unsupported_media_type(self):
        token = self.owner.get("/api/csrf")[1]["csrf_token"]
        self.assertEqual(self.owner.request("POST", "/api/ops/draft", "{}", {"Content-Type":"text/plain","X-CSRF-Token":token})[0], 415)

    def test_34_unexpected_upload_type(self):
        data = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
        uid = self.owner.post("/api/ops/uploads/start", {"size": len(data), "name": "foto.png"})[1]["id"]
        self.assertEqual(self.owner.post("/api/ops/uploads/chunk", {"id": uid, "offset": 0, "data": base64.b64encode(data).decode()})[0], 400)

    def test_35_upload_size_limit(self):
        self.assertEqual(self.owner.post("/api/ops/uploads/start", {"size": 1 << 30})[0], 400)

    def test_36_cart_idor(self):
        self.owner.post("/api/cart/items", {"variant_id":self.variant,"quantity":1})
        item = self.owner.get("/api/cart")[1]["items"][0]
        self.assertEqual(self.other.post("/api/cart/items/change", {"action":"remove","item_id":item["id"]})[0], 404)

    def test_37_quantity_type_confusion(self):
        self.assertEqual(self.other.post("/api/cart/items", {"variant_id":self.variant,"quantity":True})[0], 400)

    def test_38_price_tampering(self):
        client, _ = self.register()
        self.assertEqual(client.post("/api/cart/items", {"variant_id":self.variant,"quantity":1,"unit_price_cents":0})[0], 201)
        subtotal = client.get("/api/cart")[1]["subtotal_cents"]
        self.assertGreater(subtotal, 0)
        status, data = client.post("/api/checkout/create", self.order_data(total_cents=0))
        self.assertEqual(status, 201)
        self.assertEqual(data["total_cents"], subtotal)

    def test_39_replay_changed_payload(self):
        data = self.quote_data()
        self.assertEqual(self.other.post("/api/quotes", data)[0], 201)
        self.assertEqual(self.other.post("/api/quotes", {**data,"message":"Otro texto válido de prueba."})[0], 409)

    def test_40_workflow_skip(self):
        self.assertEqual(self.admin.post("/api/ops/update", {"kind":"order","id":self.order_id,"version":1,"status":"completed"})[0], 400)

    def test_41_optimistic_locking(self):
        self.assertEqual(self.admin.post("/api/ops/update", {"kind":"order","id":self.order_id,"version":999,"status":"confirmed"})[0], 409)

    def test_42_receipt_bounds(self):
        self.assertEqual(self.admin.post("/api/ops/receipt", {"id":self.order_id,"amount_cents":-1,"notes":"ajuste de prueba","idempotency_key":secrets.token_hex(18)})[0], 400)

    def test_43_retired_payment_api(self):
        self.assertEqual(self.guest().post("/api/payments/sandbox/complete", {})[0], 410)

    def test_44_sensitive_fields(self):
        status, result = self.guest().get(f"/api/ops/detail?kind=quote&id={self.quote_id}&token={self.token}")
        self.assertEqual(status, 200)
        for field in ("internal_notes", "tracking_hash"):
            self.assertNotIn(field, result["record"])
        self.assertTrue(all("actor_id" not in event and "actor_name" not in event for event in result["record"]["history"]))

    def test_45_at_rest_field_protection(self):
        with connect(self.settings) as db:
            stored = db.execute("SELECT phone,message FROM quote_requests WHERE id=?", (self.quote_id,)).fetchone()
        self.assertTrue(all(value.startswith("enc:v1:") for value in stored))
        self.assertEqual(FieldCipher(self.settings.field_encryption_key).decrypt(stored[0], aad="quote-phone"), "+50371234567")

    def test_46_hostile_referrer_exposure(self):
        client = self.guest()
        client.get(f"/api/ops/detail?kind=quote&id={self.quote_id}&token={self.token}")
        self.assertEqual(client.headers.get("Referrer-Policy"), "no-referrer")

    def test_47_default_credentials_in_migrated_production(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = replace(self.settings, database_path=Path(folder) / "migration.db")
            initialize(settings)
            initialize(replace(settings, environment="production"))
            with connect(settings) as db:
                from backend.security import verify_password
                for email, password in (("root@demo.com", "123456789"), ("admin@demo.com", "TipsDemo2026!")):
                    row = db.execute("SELECT is_active,password_hash FROM users WHERE email=?", (email,)).fetchone()
                    self.assertFalse(row and row["is_active"] and verify_password(password, row["password_hash"]))


    def test_48_login_challenge_bound_to_browser(self):
        from backend.security import TotpManager
        with connect(self.settings) as db:
            uid = db.execute("SELECT id FROM users WHERE email='admin@demo.com'").fetchone()[0]
        secret = TotpManager.new_secret()
        cipher = FieldCipher(self.settings.field_encryption_key)
        with connect(self.settings) as db:
            db.execute("UPDATE users SET two_factor_enabled=1,two_factor_secret_encrypted=? WHERE id=?",
                       (cipher.encrypt(secret, aad="user-2fa"), uid))
        try:
            legitimate, replay = self.guest(), self.guest()
            status, response = legitimate.post("/api/auth/login", {"email":"admin@demo.com","password":"TipsDemo2026!"})
            self.assertEqual(status, 200)
            verification = {"challenge_token":response["challenge_token"], "code":TotpManager().code(secret)}
            self.assertEqual(replay.post("/api/auth/2fa/verify-login", verification)[0], 401)
            self.assertEqual(legitimate.post("/api/auth/2fa/verify-login", verification)[0], 200)
            self.assertEqual(legitimate.post("/api/auth/2fa/verify-login", verification)[0], 401)
        finally:
            with connect(self.settings) as db:
                db.execute("UPDATE users SET two_factor_enabled=0,two_factor_secret_encrypted=NULL WHERE id=?", (uid,))

    def test_49_password_reset_after_email_change(self):
        client, _ = self.register()
        old_email = client.get("/api/auth/me")[1]["user"]["email"]
        _, recovery = self.guest().post("/api/auth/password-reset/request", {"email":old_email})
        self.assertEqual(client.post("/api/account/profile", {
            "display_name":"Persona de prueba","email":"rotated@tips.test","phone":"71234567",
            "current_password":"AuditLocalOnly!2026",
        })[0], 200)
        self.assertEqual(self.guest().post("/api/auth/password-reset/confirm", {
            "token":recovery["development_token"],"new_password":"AuditReplacement!2026",
        })[0], 400)

    def test_50_expired_private_upload(self):
        pending = self.upload(self.owner)
        with connect(self.settings) as db:
            db.execute("UPDATE design_uploads SET expires_at=? WHERE id=?", (iso(utc_now()-timedelta(seconds=2)), pending))
        self.assertEqual(self.owner.get(f"/api/ops/file/{pending}")[0], 404)

    def test_51_cross_account_cart_switch(self):
        first, _ = self.register()
        second, _ = self.register()
        email = second.get("/api/auth/me")[1]["user"]["email"]
        self.assertEqual(first.post("/api/cart/items", {"variant_id":self.variant,"quantity":1})[0], 201)
        self.assertEqual(first.post("/api/auth/login", {"email":email,"password":"AuditLocalOnly!2026"})[0], 200)
        self.assertEqual(first.get("/api/cart")[1]["items"], [])

    def test_52_brute_force_route_throttling(self):
        original = self.handler.sensitive_rate_limiter
        self.handler.sensitive_rate_limiter = RateLimiter(10)
        try:
            client = self.guest()
            for _ in range(10):
                self.assertEqual(client.post("/api/auth/login", {"email":"unknown@tips.test","password":"invalid"})[0], 401)
            self.assertEqual(client.post("/api/auth/login", {"email":"unknown@tips.test","password":"invalid"})[0], 429)
        finally:
            self.handler.sensitive_rate_limiter = original

    def test_53_bounded_request_body(self):
        client = self.guest()
        csrf = client.get("/api/csrf")[1]["csrf_token"]
        status, _ = client.request("POST", "/api/ops/draft", "{}", {
            "Content-Type":"application/json", "Content-Length":str(self.settings.max_request_bytes+1), "X-CSRF-Token":csrf
        })
        self.assertEqual(status, 413)

    def test_54_non_finite_json(self):
        csrf = self.owner.get("/api/csrf")[1]["csrf_token"]
        status, _ = self.owner.request("POST", "/api/ops/draft", '{"payload":{"value":NaN}}',
                                       {"Content-Type":"application/json","X-CSRF-Token":csrf})
        self.assertEqual(status, 400)

    def test_55_tracking_secret_at_rest(self):
        with connect(self.settings) as db:
            responses = db.execute("SELECT response_json FROM request_keys WHERE kind='quote'").fetchall()
        self.assertTrue(responses)
        self.assertTrue(all(row[0].startswith("enc:v1:") for row in responses))

    def test_56_encoded_query_secret_in_http_logs(self):
        from contextlib import redirect_stderr
        from backend.operations import OperationsHandler
        original = self.handler.log_message
        self.handler.log_message = OperationsHandler.log_message
        try:
            logs = io.StringIO()
            with redirect_stderr(logs):
                self.guest().get(f"/api/ops/detail?kind=quote&id={self.quote_id}&%74oken={self.token}")
            self.assertNotIn(self.token, logs.getvalue())
            self.assertIn("GET /api/ops/detail", logs.getvalue())
        finally:
            self.handler.log_message = original

    def test_57_unicode_otp(self):
        from backend.security import TotpManager
        self.assertFalse(TotpManager().verify(TotpManager.new_secret(), "١٢٣٤٥٦"))

    def test_58_password_reset_after_password_change(self):
        client, _ = self.register()
        email = client.get("/api/auth/me")[1]["user"]["email"]
        _, recovery = self.guest().post("/api/auth/password-reset/request", {"email":email})
        self.assertEqual(client.post("/api/account/password", {
            "current_password":"AuditLocalOnly!2026","new_password":"AuditReplacement!2026",
        })[0], 200)
        self.assertEqual(self.guest().post("/api/auth/password-reset/confirm", {
            "token":recovery["development_token"],"new_password":"UnauthorizedNew!2026",
        })[0], 400)
