"""Servicios de seguridad de Tips.

Las responsabilidades criptográficas están agrupadas en clases pequeñas para
que cada pieza tenga un propósito claro: contraseñas, sesiones, CSRF, cabeceras
y limitación de solicitudes. Se mantienen funciones adaptadoras con los nombres
históricos porque los handlers existentes todavía las consumen.
"""

from __future__ import annotations

from collections import defaultdict, deque
import base64
import hashlib
import hmac
import secrets
import threading
import time
from typing import Deque

PBKDF2_ITERATIONS = 600_000
CSRF_MAX_AGE_SECONDS = 7200


def _b64encode(raw: bytes) -> str:
    """Codifica bytes en Base64 URL-safe sin relleno innecesario."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    """Decodifica Base64 URL-safe restaurando el relleno requerido."""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class PasswordHasher:
    """Crea y verifica hashes PBKDF2-HMAC-SHA256 para contraseñas."""

    def __init__(self, iterations: int = PBKDF2_ITERATIONS) -> None:
        """Configura el costo criptográfico usado al crear hashes nuevos."""
        if not 100_000 <= iterations <= 2_000_000:
            raise ValueError("Las iteraciones PBKDF2 deben estar entre 100000 y 2000000.")
        self.iterations = iterations

    def hash(self, password: str) -> str:
        """Genera un hash con salt aleatorio; exige al menos 12 caracteres."""
        if len(password) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres.")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, self.iterations)
        return f"pbkdf2_sha256${self.iterations}${_b64encode(salt)}${_b64encode(digest)}"

    def verify(self, password: str, encoded: str) -> bool:
        """Compara una contraseña contra un hash almacenado en tiempo constante."""
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


class SessionTokenManager:
    """Genera tokens de sesión y su representación segura para almacenamiento."""

    @staticmethod
    def create() -> str:
        """Devuelve un token aleatorio apto para enviarse como cookie."""
        return _b64encode(secrets.token_bytes(32))

    @staticmethod
    def digest(token: str) -> str:
        """Convierte el token secreto en SHA-256 antes de guardarlo en SQLite."""
        return hashlib.sha256(token.encode("ascii")).hexdigest()


class CsrfProtection:
    """Firma y valida tokens CSRF vinculados a una sesión concreta."""

    def __init__(self, secret_key: str, max_age_seconds: int = CSRF_MAX_AGE_SECONDS) -> None:
        """Guarda la clave de firma y la vida máxima aceptada del token."""
        self.secret_key = secret_key
        self.max_age_seconds = max_age_seconds

    def create(self, session_token: str, now: int | None = None) -> str:
        """Crea un token CSRF firmado con timestamp y nonce aleatorio."""
        timestamp = int(time.time() if now is None else now)
        nonce = secrets.token_urlsafe(16)
        payload = f"{timestamp}.{nonce}"
        signature = hmac.new(
            self.secret_key.encode(),
            f"{session_token}.{payload}".encode(),
            hashlib.sha256,
        ).digest()
        return f"{payload}.{_b64encode(signature)}"

    def verify(self, token: str, session_token: str, now: int | None = None) -> bool:
        """Valida formato, antigüedad, sesión y firma criptográfica del token."""
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
        expected = hmac.new(
            self.secret_key.encode(),
            f"{session_token}.{payload}".encode(),
            hashlib.sha256,
        ).digest()
        return hmac.compare_digest(supplied, expected)


class SecurityPolicy:
    """Agrupa políticas HTTP y validaciones simples compartidas por el servidor."""

    @staticmethod
    def headers() -> dict[str, str]:
        """Devuelve las cabeceras defensivas aplicadas a todas las respuestas."""
        return {
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(self)",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        }

    @staticmethod
    def is_allowed_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
        """Acepta solicitudes sin Origin o procedentes de la lista configurada."""
        return not origin or origin.rstrip("/") in allowed_origins

    @staticmethod
    def validate_search_term(value: str, max_length: int = 80) -> str:
        """Normaliza una búsqueda y bloquea controles o entradas demasiado largas."""
        cleaned = value.strip()
        if len(cleaned) > max_length or any(ord(char) < 32 for char in cleaned):
            raise ValueError("El texto de búsqueda es inválido o demasiado largo.")
        return cleaned


class RateLimiter:
    """Limitador en memoria por clave usando una ventana temporal deslizante."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        """Define cuántos eventos admite cada clave dentro de la ventana."""
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Registra un evento y devuelve ``False`` cuando la clave excede el límite."""
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


# ---------------------------------------------------------------------------
# Adaptadores de compatibilidad
# ---------------------------------------------------------------------------
_DEFAULT_PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    """Compatibilidad: crea un hash usando la política de contraseñas actual."""
    return _DEFAULT_PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    """Compatibilidad: verifica una contraseña sin exponer detalles del hash."""
    return _DEFAULT_PASSWORD_HASHER.verify(password, encoded)


def new_session_token() -> str:
    """Compatibilidad: genera un token secreto para una sesión nueva."""
    return SessionTokenManager.create()


def session_token_hash(token: str) -> str:
    """Compatibilidad: obtiene el digest persistible de un token de sesión."""
    return SessionTokenManager.digest(token)


def create_csrf_token(session_token: str, secret_key: str, now: int | None = None) -> str:
    """Compatibilidad: crea un token CSRF para una sesión concreta."""
    return CsrfProtection(secret_key).create(session_token, now)


def verify_csrf_token(
    token: str,
    session_token: str,
    secret_key: str,
    *,
    max_age_seconds: int = CSRF_MAX_AGE_SECONDS,
    now: int | None = None,
) -> bool:
    """Compatibilidad: valida un token CSRF y su antigüedad máxima."""
    return CsrfProtection(secret_key, max_age_seconds).verify(token, session_token, now)


def security_headers() -> dict[str, str]:
    """Compatibilidad: devuelve las cabeceras HTTP defensivas."""
    return SecurityPolicy.headers()


def is_allowed_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
    """Compatibilidad: valida el origen de una solicitud CORS."""
    return SecurityPolicy.is_allowed_origin(origin, allowed_origins)


def validate_search_term(value: str, max_length: int = 80) -> str:
    """Compatibilidad: limpia y valida un término de búsqueda."""
    return SecurityPolicy.validate_search_term(value, max_length)
