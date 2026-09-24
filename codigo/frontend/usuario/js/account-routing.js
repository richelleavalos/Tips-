/**
 * Código de la experiencia del usuario/cliente: account routing. No contiene responsabilidades exclusivas del administrador.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  let routing = false;
  async function routeAuthenticatedUser() {
    if (routing) return;
    try {
      const response = await fetch("/api/auth/me", { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.authenticated || !data.user) return;
      routing = true;
      location.href = data.user.role === "admin" ? "/admin/" : "/user/";
    } catch {}
  }
  routeAuthenticatedUser();
  document.addEventListener("submit", () => window.setTimeout(routeAuthenticatedUser, 650));
})();
