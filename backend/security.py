"""Servicios criptográficos y defensas HTTP de TIPS.

- Contraseñas: PBKDF2-HMAC-SHA256 con salt aleatorio (no reversible).
- Datos sensibles recuperables: AES-256-GCM (Rijndael/AES autenticado).
- 2FA: TOTP RFC 6238 compatible con aplicaciones autenticadoras.
- Sesiones/reset/challenges: tokens aleatorios persistidos únicamente por digest.
"""

from __future__ import annotations

from collections import defaultdict, deque
import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
from typing import Deque
from urllib.parse import quote

from .dependencies import ensure_cryptography

ensure_cryptography()
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PBKDF2_ITERATIONS = 600_000
CSRF_MAX_AGE_SECONDS = 7200
ENCRYPTED_PREFIX = "enc:v1:"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class PasswordHasher:
    """Crea y verifica hashes PBKDF2-HMAC-SHA256 con salt individual."""

    def __init__(self, iterations: int = PBKDF2_ITERATIONS) -> None:
        if not 100_000 <= iterations <= 2_000_000:
            raise ValueError("Las iteraciones PBKDF2 deben estar entre 100000 y 2000000.")
        self.iterations = iterations

    def _hash_unchecked(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, self.iterations)
        return f"pbkdf2_sha256${self.iterations}${_b64encode(salt)}${_b64encode(digest)}"

    def hash(self, password: str) -> str:
        if len(password) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres.")
        return self._hash_unchecked(password)

    def hash_bootstrap(self, password: str) -> str:
        """Hash reservado para la credencial temporal del superadmin.

        La contraseña temporal solicitada para el bootstrap es más corta que la
        política normal. Nunca se permite usar este método para registros o
        cambios de contraseña y el usuario queda bloqueado hasta reemplazarla.
        """
        if not password:
            raise ValueError("La contraseña temporal no puede estar vacía.")
        return self._hash_unchecked(password)

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_raw)
            if not 100_000 <= iterations <= 2_000_000:
                return False
            salt, expected = _b64decode(salt_raw), _b64decode(digest_raw)
        except (ValueError, TypeError):
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return hmac.compare_digest(candidate, expected)


class FieldCipher:
    """Cifra texto con AES-256-GCM y autenticación de integridad."""

    def __init__(self, key_material: str) -> None:
        if not key_material:
            raise ValueError("Se requiere material de clave para cifrar campos.")
        self._key = hashlib.sha256(key_material.encode("utf-8")).digest()
        self._aes = AESGCM(self._key)

    def encrypt(self, value: str | None, *, aad: str = "tips-field-v1") -> str | None:
        if value is None or value == "":
            return value
        if value.startswith(ENCRYPTED_PREFIX):
            return value
        nonce = secrets.token_bytes(12)
        ciphertext = self._aes.encrypt(nonce, value.encode("utf-8"), aad.encode("utf-8"))
        return ENCRYPTED_PREFIX + _b64encode(nonce + ciphertext)

    def decrypt(self, value: str | None, *, aad: str = "tips-field-v1") -> str | None:
        if value is None or value == "" or not value.startswith(ENCRYPTED_PREFIX):
            # Compatibilidad progresiva con datos existentes sin cifrar.
            return value
        raw = _b64decode(value[len(ENCRYPTED_PREFIX):])
        if len(raw) < 13:
            raise ValueError("Dato cifrado inválido.")
        nonce, ciphertext = raw[:12], raw[12:]
        return self._aes.decrypt(nonce, ciphertext, aad.encode("utf-8")).decode("utf-8")


class TotpManager:
    """TOTP SHA-1 de 6 dígitos compatible con RFC 6238."""

    period = 30
    digits = 6

    @staticmethod
    def new_secret() -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_secret(secret: str) -> bytes:
        normalized = secret.strip().replace(" ", "").upper()
        return base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=True)

    def code(self, secret: str, at_time: int | None = None) -> str:
        timestamp = int(time.time() if at_time is None else at_time)
        counter = timestamp // self.period
        digest = hmac.new(self._decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** self.digits)
        return f"{number:0{self.digits}d}"

    def verify(self, secret: str, code: str, at_time: int | None = None, window: int = 1) -> bool:
        candidate = str(code).strip()
        if not candidate.isascii() or not candidate.isdigit() or len(candidate) != self.digits:
            return False
        timestamp = int(time.time() if at_time is None else at_time)
        return any(hmac.compare_digest(self.code(secret, timestamp + offset * self.period), candidate) for offset in range(-window, window + 1))

    @staticmethod
    def provisioning_uri(secret: str, email: str, issuer: str = "TIPS") -> str:
        label = quote(f"{issuer}:{email}")
        return f"otpauth://totp/{label}?secret={quote(secret)}&issuer={quote(issuer)}&digits=6&period=30"


class SessionTokenManager:
    @staticmethod
    def create() -> str:
        return _b64encode(secrets.token_bytes(32))

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CsrfProtection:
    def __init__(self, secret_key: str, max_age_seconds: int = CSRF_MAX_AGE_SECONDS) -> None:
        self.secret_key = secret_key
        self.max_age_seconds = max_age_seconds

    def create(self, session_token: str, now: int | None = None) -> str:
        timestamp = int(time.time() if now is None else now)
        nonce = secrets.token_urlsafe(16)
        payload = f"{timestamp}.{nonce}"
        signature = hmac.new(self.secret_key.encode(), f"{session_token}.{payload}".encode(), hashlib.sha256).digest()
        return f"{payload}.{_b64encode(signature)}"

    def verify(self, token: str, session_token: str, now: int | None = None) -> bool:
        try:
            timestamp_raw, nonce, signature_raw = token.split(".", 2)
            timestamp = int(timestamp_raw)
            supplied = _b64decode(signature_raw)
        except (ValueError, TypeError):
            return False
        current = int(time.time() if now is None else now)
        if timestamp > current + 60 or current - timestamp > self.max_age_seconds:
            return False
        payload = f"{timestamp}.{nonce}"
        expected = hmac.new(self.secret_key.encode(), f"{session_token}.{payload}".encode(), hashlib.sha256).digest()
        return hmac.compare_digest(supplied, expected)


class SecurityPolicy:
    @staticmethod
    def headers() -> dict[str, str]:
        return {
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(self)",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        }

    @staticmethod
    def is_allowed_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
        return not origin or origin.rstrip("/") in allowed_origins

    @staticmethod
    def validate_search_term(value: str, max_length: int = 80) -> str:
        cleaned = value.strip()
        if len(cleaned) > max_length or any(ord(char) < 32 for char in cleaned):
            raise ValueError("El texto de búsqueda es inválido o demasiado largo.")
        return cleaned


class RateLimiter:
    """Limitador en memoria por clave usando ventana temporal deslizante."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(current)
            return True


_DEFAULT_PASSWORD_HASHER = PasswordHasher()
_DEFAULT_TOTP = TotpManager()


def hash_password(password: str) -> str:
    return _DEFAULT_PASSWORD_HASHER.hash(password)


def hash_bootstrap_password(password: str) -> str:
    return _DEFAULT_PASSWORD_HASHER.hash_bootstrap(password)


def verify_password(password: str, encoded: str) -> bool:
    return _DEFAULT_PASSWORD_HASHER.verify(password, encoded)


def new_session_token() -> str:
    return SessionTokenManager.create()


def token_digest(token: str) -> str:
    return SessionTokenManager.digest(token)


def session_token_hash(token: str) -> str:
    return token_digest(token)


def create_csrf_token(session_token: str, secret_key: str, now: int | None = None) -> str:
    return CsrfProtection(secret_key).create(session_token, now)


def verify_csrf_token(token: str, session_token: str, secret_key: str, *, max_age_seconds: int = CSRF_MAX_AGE_SECONDS, now: int | None = None) -> bool:
    return CsrfProtection(secret_key, max_age_seconds).verify(token, session_token, now)


def security_headers() -> dict[str, str]:
    return SecurityPolicy.headers()


def is_allowed_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
    return SecurityPolicy.is_allowed_origin(origin, allowed_origins)


def validate_search_term(value: str, max_length: int = 80) -> str:
    return SecurityPolicy.validate_search_term(value, max_length)


def new_totp_secret() -> str:
    return _DEFAULT_TOTP.new_secret()


def verify_totp(secret: str, code: str, at_time: int | None = None) -> bool:
    return _DEFAULT_TOTP.verify(secret, code, at_time)


def totp_uri(secret: str, email: str) -> str:
    return _DEFAULT_TOTP.provisioning_uri(secret, email)
