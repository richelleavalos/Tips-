import unittest
from backend.security import RateLimiter,create_csrf_token,hash_password,verify_csrf_token,verify_password

class SecurityTests(unittest.TestCase):
    def test_password_hash_roundtrip(self):
        encoded=hash_password('Una-contrasena-muy-segura-2026'); self.assertTrue(verify_password('Una-contrasena-muy-segura-2026',encoded)); self.assertFalse(verify_password('incorrecta',encoded))
    def test_csrf_roundtrip_and_expiration(self):
        token=create_csrf_token('session-token','secret',now=1000); self.assertTrue(verify_csrf_token(token,'session-token','secret',now=1001)); self.assertFalse(verify_csrf_token(token,'otra-session','secret',now=1001)); self.assertFalse(verify_csrf_token(token,'session-token','secret',now=8201))
    def test_rate_limiter(self):
        limiter=RateLimiter(2,60); self.assertTrue(limiter.allow('ip',now=0)); self.assertTrue(limiter.allow('ip',now=1)); self.assertFalse(limiter.allow('ip',now=2)); self.assertTrue(limiter.allow('ip',now=61))

if __name__=='__main__': unittest.main()
