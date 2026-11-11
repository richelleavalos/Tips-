/** Flujos de seguridad TIPS v6: contraseña temporal, 2FA y recuperación. */
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
          const token = await r.json();
          csrf = token.csrf_token;
        }
        headers["X-CSRF-Token"] = csrf;
        headers["Content-Type"] = "application/json";
      }
      const response = await fetch(path, { credentials: "same-origin", ...options, method, headers });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.error || "No se pudo completar la acción.");
        error.status = response.status;
        throw error;
      }
    return data;
  }

  function msg(node, value, state = "") {
    if (!node) return;
    node.textContent = value;
    if (state) node.dataset.state = state; else delete node.dataset.state;
  }

  async function initPasswordChange() {
    const form = $("[data-change-password]");
    if (!form) return false;
    const message = $("[data-security-message]");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const current = String(data.get("current_password") || "");
      const next = String(data.get("new_password") || "");
      const confirm = String(data.get("confirm_password") || "");
      if (next !== confirm) { msg(message, "Las contraseñas nuevas no coinciden.", "error"); return; }
      const button = $("button[type=submit]", form);
      button.disabled = true;
      msg(message, "Protegiendo tu cuenta…");
      try {
        const result = await api("/api/account/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
        msg(message, "Contraseña actualizada correctamente.", "success");
        location.replace(new URLSearchParams(location.search).get("next") === "/checkout.html" ? "/checkout.html" : "/");
      } catch (error) {
        msg(message, error.message, "error");
      } finally { button.disabled = false; }
    });
    return true;
  }

  async function initTwoFactor() {
    const form = $("[data-setup-2fa]");
    if (!form) return false;
    const secretNode = $("[data-2fa-secret]");
    const uriNode = $("[data-2fa-uri]");
    const message = $("[data-security-message]");
    try {
      const setup = await api("/api/auth/2fa/setup");
      if (setup.enabled) { location.replace("/admin/"); return true; }
      secretNode.textContent = setup.secret || "";
      uriNode.value = setup.provisioning_uri || "";
    } catch (error) {
      msg(message, error.message, "error");
      return true;
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const code = String(new FormData(form).get("code") || "").replace(/\s/g, "");
      const button = $("button[type=submit]", form);
      button.disabled = true;
      try {
        await api("/api/auth/2fa/enable", { method: "POST", body: JSON.stringify({ code }) });
        msg(message, "2FA activado. Tu panel ya está protegido.", "success");
        location.replace("/admin/");
      } catch (error) { msg(message, error.message, "error"); }
      finally { button.disabled = false; }
    });
    return true;
  }

  async function initReset() {
    const requestForm = $("[data-reset-request]");
    const confirmForm = $("[data-reset-confirm]");
    const privateToken=new URLSearchParams(location.hash.slice(1)).get('token');
    if(privateToken && confirmForm) { confirmForm.hidden=false; confirmForm.querySelector('[name=token]').value=privateToken; history.replaceState(null,'',location.pathname); }
    if (!requestForm || !confirmForm) return false;
    const message = $("[data-security-message]");
    requestForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const email = String(new FormData(requestForm).get("email") || "");
      try {
        const result = await api("/api/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email }) });
        msg(message, result.message || "Si la cuenta existe, se generó una recuperación.", "success");
        if (result.development_token) {
          $("[name=token]", confirmForm).value = result.development_token;
          confirmForm.hidden = false;
          $("[data-dev-reset-note]").hidden = false;
        }
      } catch (error) { msg(message, error.message, "error"); }
    });
    confirmForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(confirmForm);
      const password = String(data.get("new_password") || "");
      const confirm = String(data.get("confirm_password") || "");
      if (password !== confirm) { msg(message, "Las contraseñas no coinciden.", "error"); return; }
      try {
        await api("/api/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token: String(data.get("token") || ""), new_password: password }) });
        msg(message, "Contraseña actualizada. Ya puedes iniciar sesión.", "success");
        setTimeout(() => location.replace("/cuenta.html"), 650);
      } catch (error) { msg(message, error.message, "error"); }
    });
    return true;
  }

  document.addEventListener("DOMContentLoaded", async () => {
    if (await initPasswordChange()) return;
    if (await initTwoFactor()) return;
    await initReset();
  });
})();
