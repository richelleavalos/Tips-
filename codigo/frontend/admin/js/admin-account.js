/**
 * Código de la experiencia administrativa: admin account. Mantiene esta responsabilidad aislada del frontend de cliente.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const A = window.TipsAdmin;
  if (!A || document.body.dataset.adminPage !== "cuenta") return;
  const { $, esc, api, toast, setPageTitle, loadAlerts, setIdentity } = A;

  async function boot() {
    setPageTitle("Mi cuenta admin", "Tus datos y seguridad, sin salir del panel administrativo.");
    try {
      const overview = await loadAlerts();
      setIdentity(overview.user);
      const data = await api("/api/account");
      if (data.user.role !== "admin") { location.href = "/user/"; return; }
      const root = $("[data-page-content]");
      root.innerHTML = `<div class="admin-grid-2"><section class="admin-card"><div class="admin-card-head"><div><h2>Datos de la cuenta</h2><p>Nombre y correo del administrador.</p></div></div><form data-admin-account-profile><div class="admin-form-grid"><div class="admin-field full"><span>Nombre</span><input name="display_name" required maxlength="120" value="${esc(data.user.display_name)}"></div><div class="admin-field full"><span>Correo</span><input name="email" type="email" required maxlength="180" value="${esc(data.user.email)}"></div><div class="admin-field full"><span>Contraseña actual</span><input name="current_password" type="password" autocomplete="current-password"><small>Necesaria solo si cambias el correo.</small></div></div><div class="appearance-actions"><button class="admin-btn primary">Guardar datos</button></div></form></section><section class="admin-card"><div class="admin-card-head"><div><h2>Cambiar contraseña</h2><p>Cierra las otras sesiones activas.</p></div></div><form data-admin-account-password><div class="admin-form-grid"><div class="admin-field full"><span>Contraseña actual</span><input name="current_password" type="password" required></div><div class="admin-field full"><span>Nueva contraseña</span><input name="new_password" type="password" minlength="12" required></div><div class="admin-field full"><span>Confirmar nueva contraseña</span><input name="confirm_password" type="password" minlength="12" required></div></div><div class="appearance-actions"><button class="admin-btn primary">Actualizar contraseña</button></div></form></section></div><section class="admin-card" style="margin-top:16px;border-color:#ead1ce"><div class="admin-card-head"><div><h2 style="color:var(--a-danger)">Desactivar cuenta administrativa</h2><p>Solo se permite si existe otro administrador activo.</p></div></div><div class="admin-role-note">Por seguridad, el sistema nunca permitirá desactivar la última cuenta admin activa.</div><form data-admin-account-deactivate style="margin-top:14px"><div class="admin-form-grid"><div class="admin-field"><span>Contraseña actual</span><input name="current_password" type="password" required></div><div class="admin-field"><span>Escribe DESACTIVAR</span><input name="confirmation" required></div></div><div class="appearance-actions"><button class="admin-btn danger">Desactivar esta cuenta</button></div></form></section>`;

      $("[data-admin-account-profile]").onsubmit = async event => {
        event.preventDefault(); const fd = new FormData(event.currentTarget);
        try { await api("/api/account/profile", { method: "POST", body: JSON.stringify({ display_name: fd.get("display_name"), email: fd.get("email"), current_password: fd.get("current_password") }) }); toast("Datos actualizados."); event.currentTarget.elements.current_password.value = ""; } catch (error) { toast(error.message, "error"); }
      };
      $("[data-admin-account-password]").onsubmit = async event => {
        event.preventDefault(); const fd = new FormData(event.currentTarget);
        if (fd.get("new_password") !== fd.get("confirm_password")) { toast("Las contraseñas no coinciden.", "error"); return; }
        try { await api("/api/account/password", { method: "POST", body: JSON.stringify({ current_password: fd.get("current_password"), new_password: fd.get("new_password") }) }); toast("Contraseña actualizada."); event.currentTarget.reset(); } catch (error) { toast(error.message, "error"); }
      };
      $("[data-admin-account-deactivate]").onsubmit = async event => {
        event.preventDefault(); const fd = new FormData(event.currentTarget);
        if (String(fd.get("confirmation")).trim().toUpperCase() !== "DESACTIVAR") { toast("Escribe DESACTIVAR para continuar.", "error"); return; }
        if (!confirm("¿Seguro que quieres desactivar esta cuenta admin?")) return;
        try { await api("/api/account/deactivate", { method: "POST", body: JSON.stringify({ current_password: fd.get("current_password"), confirmation: fd.get("confirmation") }) }); location.href = "/cuenta.html"; } catch (error) { toast(error.message, "error"); }
      };
    } catch (error) {
      if (error.status !== 401 && error.status !== 403) toast(error.message, "error");
    }
  }
  boot();
})();
