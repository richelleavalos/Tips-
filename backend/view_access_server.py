"""Control de acceso a vistas HTML según sesión y rol de usuario."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import quote

from .scalable_server import TipsScalableRequestHandler

PUBLIC_VIEW_PATHS = {
    "/", "/index.html", "/tienda.html", "/arquitectura.html", "/contacto.html",
    "/checkout.html", "/merchandise.html", "/proyecto.html", "/cuenta.html", "/recuperar.html",
}
SECURITY_VIEW_PATHS = {"/change-password.html", "/setup-2fa.html"}


class TipsRoleViewRequestHandler(TipsScalableRequestHandler):
    """Control de acceso para las vistas privadas por rol.

    /admin/* pertenece exclusivamente al rol admin.
    /user/* pertenece exclusivamente al rol user.
    Una sesión admin permanece confinada al panel administrativo.
    """

    def _redirect_view(self, location: str) -> None:
        """Envía una redirección 303 sin almacenar la respuesta en caché."""
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _role_home(self, user: dict[str, object] | None) -> str:
        """Devuelve la página inicial correspondiente al rol autenticado."""
        if not user:
            return "/cuenta.html"
        return "/admin/" if user.get("role") in {"admin", "superadmin"} else "/user/"

    def _serve_public(self, requested_path: str) -> None:
        """Protege vistas privadas por rol antes de delegar el servido físico del recurso."""
        path = requested_path or "/"
        if path == "/arquitectura.html":
            self._redirect_view("/servicios-de-diseno.html")
            return

        # Los recursos estáticos no heredan redirecciones de seguridad de la vista.
        # Si una sesión necesita cambiar contraseña/activar 2FA, su CSS/JS debe
        # poder cargarse para renderizar esa pantalla correctamente.
        if path.startswith(("/frontend/", "/assets/")):
            super()._serve_public(path)
            return

        if path == "/admin.html":
            self._redirect_view("/admin/")
            return
        if path == "/perfil.html":
            self._redirect_view(self._role_home(self._current_user()))
            return
        if path == "/admin":
            self._redirect_view("/admin/")
            return
        if path == "/user":
            self._redirect_view("/user/")
            return

        user = self._current_user()

        # La contraseña temporal bloquea toda navegación autenticada hasta ser reemplazada.
        if user and user.get("must_change_password") and path != "/change-password.html":
            self._redirect_view("/change-password.html")
            return
        if path == "/change-password.html" and not user:
            self._redirect_view("/cuenta.html")
            return

        # 2FA dejó de ser un requisito de acceso en v6.4. La vista se conserva
        # como opción de seguridad para administradores que quieran activarla,
        # pero nunca bloquea ni redirige automáticamente al panel.
        if path == "/setup-2fa.html":
            if not user:
                self._redirect_view("/cuenta.html")
                return
            if user.get("role") not in {"admin", "superadmin"}:
                self._redirect_view("/user/")
                return
            if user.get("two_factor_enabled"):
                self._redirect_view("/admin/")
                return

        if path in PUBLIC_VIEW_PATHS and user and user.get("role") in {"admin", "superadmin"}:
            self._redirect_view("/admin/")
            return

        required_role: str | None = None
        if path == "/admin/" or path.startswith("/admin/"):
            required_role = "admin"
        elif path == "/user/" or path.startswith("/user/"):
            required_role = "user"

        if required_role:
            user = user or self._current_user()
            if not user:
                next_path = quote(path, safe="/")
                self._redirect_view(f"/cuenta.html?next={next_path}")
                return
            allowed = user.get("role") in {"admin", "superadmin"} if required_role == "admin" else user.get("role") == "user"
            if not allowed:
                self._redirect_view(self._role_home(user))
                return

        super()._serve_public(path)
