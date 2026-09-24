/**
 * Código de la experiencia del usuario/cliente: profile menu. No contiene responsabilidades exclusivas del administrador.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const $ = (s, c = document) => c.querySelector(s);
  let csrf = "";
  async function api(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (method !== "GET") {
      if (!csrf) {
        const r = await fetch("/api/csrf", { credentials: "same-origin" });
        csrf = (await r.json()).csrf_token;
      }
      headers["X-CSRF-Token"] = csrf;
      headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, { credentials: "same-origin", ...options, method, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "No se pudo completar la acción.");
    return data;
  }

  function findSlot() {
    let slot = $("[data-profile-slot]");
    if (slot) return slot;
    const actions = $(".header-actions");
    if (!actions) return null;
    const old = actions.querySelector('a[href="cuenta.html"],a[href="/cuenta.html"]');
    if (old) {
      slot = document.createElement("span");
      slot.dataset.profileSlot = "";
      old.replaceWith(slot);
      return slot;
    }
    return null;
  }

  async function mount() {
    const slot = findSlot();
    if (!slot) return;
    let result;
    try { result = await api("/api/auth/me"); } catch { return; }
    slot.classList.remove("profile-slot-loading");
    if (!result.authenticated) {
      slot.innerHTML = '<a class="login-shortcut" href="/cuenta.html" aria-label="Iniciar sesión"><span class="login-shortcut-full">Iniciar sesión</span><span class="login-shortcut-compact" aria-hidden="true">Entrar</span></a>';
      return;
    }
    const user = result.user;
    const initial = (user.display_name || user.email || "U").trim().charAt(0).toUpperCase();
    const accountHref = user.role === "admin" ? "/admin/cuenta.html" : "/user/";
    slot.innerHTML = `<div class="user-menu"><button class="user-menu-trigger" type="button" aria-expanded="false"><span class="user-avatar">${initial}</span><span>${escapeHtml(user.display_name || "Mi cuenta")}</span><span>⌄</span></button><div class="user-menu-panel"><div class="user-menu-identity"><strong>${escapeHtml(user.display_name || "Usuario")}</strong><small>${escapeHtml(user.email || "")}</small></div><a href="${accountHref}">Mi cuenta</a>${user.role === "admin" ? '<a href="/admin/">Administración</a>' : '<a href="/user/pedidos.html">Mis pedidos</a>'}<button type="button" data-profile-logout>Cerrar sesión</button></div></div>`;
    const menu = $(".user-menu", slot), trigger = $(".user-menu-trigger", slot);
    trigger.addEventListener("click", event => {
      event.stopPropagation();
      const open = menu.classList.toggle("open");
      trigger.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", event => {
      if (!event.target.closest(".user-menu")) {
        menu.classList.remove("open");
        trigger.setAttribute("aria-expanded", "false");
      }
    });
    $("[data-profile-logout]", slot).addEventListener("click", async () => {
      try { await api("/api/auth/logout", { method: "POST", body: "{}" }); } finally { location.href = "/index.html"; }
    });
  }

  function escapeHtml(value) {
    const node = document.createElement("div");
    node.textContent = String(value ?? "");
    return node.innerHTML;
  }
  mount();
})();
