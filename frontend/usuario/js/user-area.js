/**
 * Código de la experiencia del usuario/cliente: user area. No contiene responsabilidades exclusivas del administrador.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const $ = (s, c = document) => c.querySelector(s);
  const $$ = (s, c = document) => [...c.querySelectorAll(s)];
  const page = document.body.dataset.userPage || "resumen";
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
    if (!response.ok) {
      const error = new Error(data.error || "No se pudo completar la acción.");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function esc(value) {
    const node = document.createElement("div");
    node.textContent = String(value ?? "");
    return node.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  const money = cents => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format((Number(cents) || 0) / 100);

  function feedback(node, text, state = "info") {
    node.textContent = text;
    node.dataset.state = state;
  }

  async function submit(form, message, pending, action) {
    if (form.dataset.submitting === "true") return;
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    const button = $('button:not([type="button"]):not([type="reset"])', form);
    const label = button.textContent;
    button.disabled = true;
    button.textContent = pending;
    feedback(message, pending);
    try {
      await action();
    } catch (error) {
      feedback(message, error.message, "error");
    } finally {
      delete form.dataset.submitting;
      form.removeAttribute("aria-busy");
      button.disabled = false;
      button.textContent = label;
    }
  }

  function shell(user) {
    const side = $("[data-user-side]");
    const nav = [
      ["resumen", "/user/", "⌂", "Resumen"],
      ["datos", "/user/datos.html", "○", "Datos personales"],
      ["pedidos", "/user/pedidos.html", "▤", "Mis pedidos"],
      ["seguridad", "/user/seguridad.html", "◇", "Seguridad"],
    ];
    side.innerHTML = `<button class="user-mobile-menu user-menu-close" type="button" data-user-menu-close aria-label="Cerrar menú">×</button><a class="user-brand" href="/index.html"><img src="/assets/logos/tips-logo-black.svg" alt="Tips"><div><strong>Tips</strong><small>Mi cuenta</small></div></a><div class="user-side-label">Tu espacio</div><nav class="user-nav" aria-label="Mi cuenta">${nav.map(([key, href, icon, label]) => `<a class="${page === key ? "active" : ""}" ${page === key ? 'aria-current="page"' : ""} href="${href}"><span class="ico" aria-hidden="true">${icon}</span>${label}</a>`).join("")}</nav><div class="user-side-foot"><a href="/tienda.html">← Volver a la tienda</a><button type="button" data-user-logout>Cerrar sesión</button><p class="user-message" role="status" aria-live="polite" data-user-logout-message></p></div>`;
    $("[data-user-top]").innerHTML = `<div class="user-top-identity"><button class="user-mobile-menu" type="button" data-user-menu aria-controls="user-navigation" aria-expanded="false" aria-label="Abrir menú">☰</button><strong data-user-name>${esc(user.display_name)}</strong></div><a href="/index.html">Ver sitio público</a>`;
    $("[data-user-logout]").addEventListener("click", logout);
    setupMenu();
  }

  function setupMenu() {
    const side = $("[data-user-side]");
    const stage = $(".user-stage");
    const toggle = $("[data-user-menu]");
    const backdrop = $("[data-user-backdrop]");
    const mobile = window.matchMedia("(max-width: 760px)");
    let opened = false;
    function setOpen(value, restoreFocus = true) {
      opened = value && mobile.matches;
      document.body.classList.toggle("user-menu-open", opened);
      toggle.setAttribute("aria-expanded", String(opened));
      backdrop.hidden = !opened;
      stage.inert = opened;
      side.inert = mobile.matches && !opened;
      if (opened) requestAnimationFrame(() => { if (opened) $("[data-user-menu-close]").focus(); });
      else if (restoreFocus && mobile.matches) toggle.focus();
    }
    toggle.onclick = () => setOpen(!opened);
    $("[data-user-menu-close]").onclick = () => setOpen(false);
    backdrop.onclick = () => setOpen(false);
    $$("a", side).forEach(link => link.addEventListener("click", () => setOpen(false, false)));
    document.onkeydown = event => {
      if (!opened) return;
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
      if (event.key !== "Tab") return;
      const links = $$('a[href],button:not([disabled])', side);
      const first = links[0], last = links[links.length - 1];
      if (!side.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    mobile.onchange = () => {
      const focusedInSide = side.contains(document.activeElement);
      setOpen(false, false);
      if (mobile.matches && focusedInSide) toggle.focus();
      else if (!mobile.matches && document.activeElement === toggle) $('a[aria-current="page"]', side).focus();
    };
    setOpen(false, false);
  }

  async function logout() {
    const button = $("[data-user-logout]");
    if (button.disabled) return;
    button.disabled = true;
    try {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
      location.href = "/index.html";
    } catch (error) {
      feedback($("[data-user-logout-message]"), error.message, "error");
      button.disabled = false;
    }
  }

  function head(title, subtitle) {
    $("[data-user-main]").innerHTML = `<div class="user-head"><div><p>${esc(subtitle)}</p><h1>${esc(title)}</h1></div></div><section data-user-content></section>`;
    return $("[data-user-content]");
  }

  function renderOverview(data) {
    const root = head("Mi espacio", "TU CUENTA TIPS");
    const orders = data.recent_orders || [];
    const firstName = String(data.user.display_name || "").trim().split(/\s+/)[0] || "bienvenido";
    root.innerHTML = `
      <section class="user-dashboard-hero">
        <div class="user-dashboard-hero-copy">
          <p class="user-kicker">BIENVENIDO DE NUEVO</p>
          <h2>Hola, ${esc(firstName)}.<br><em>Todo en un solo lugar.</em></h2>
          <p>Revisa tus pedidos, mantén tus datos al día y continúa explorando piezas para tus espacios.</p>
          <a class="user-btn primary" href="/tienda.html">Explorar tienda →</a>
        </div>
        <div class="user-dashboard-hero-image" role="img" aria-label="Interior cálido de TIPS">
          <span>Tu espacio,<br>siempre contigo.</span>
        </div>
      </section>
      <section class="user-grid-3 user-dashboard-stats" aria-label="Resumen de cuenta">
        <article class="user-stat"><span>Pedidos recientes</span><strong>${orders.length}</strong><small>Últimas compras visibles</small></article>
        <article class="user-stat"><span>Estado de cuenta</span><strong>Activa</strong><small>Acceso disponible</small></article>
        <article class="user-stat"><span>Correo</span><strong class="user-stat-email">${esc(data.user.email)}</strong><small>Contacto principal</small></article>
      </section>
      <section class="user-dashboard-grid user-section">
        <article class="user-card user-dashboard-profile">
          <div class="user-card-heading"><div><p class="user-kicker">PERFIL</p><h2>Tu información</h2></div><a class="user-text-link" href="/user/datos.html">Editar →</a></div>
          <p>Mantén tus datos actualizados para que futuras compras sean más rápidas.</p>
          <div class="user-avatar-card"><div class="user-avatar-large">${esc((data.user.display_name || "U").charAt(0).toUpperCase())}</div><div><strong>${esc(data.user.display_name)}</strong><small>${esc(data.user.email)}</small></div></div>
        </article>
        <article class="user-card user-dashboard-security">
          <div class="user-card-heading"><div><p class="user-kicker">ACCESO</p><h2>Seguridad</h2></div><a class="user-text-link" href="/user/seguridad.html">Revisar →</a></div>
          <p>Actualiza tu contraseña y controla el estado de tu cuenta.</p>
          <div class="user-security-mark" aria-hidden="true">◇</div>
        </article>
        <article class="user-card user-dashboard-orders">
          <div class="user-card-heading"><div><p class="user-kicker">ACTIVIDAD</p><h2>Último pedido</h2></div><a class="user-text-link" href="/user/pedidos.html">Ver todos →</a></div>
          ${orderList(orders.slice(0, 1))}
        </article>
      </section>`;
  }

  function renderData(data) {
    const root = head("Datos personales", "Cambia tu nombre o correo de forma segura.");
    root.innerHTML = `<article class="user-card"><form class="user-form" data-user-profile-form><label class="user-field"><span>Nombre</span><input name="display_name" minlength="2" maxlength="120" autocomplete="name" required value="${esc(data.user.display_name)}"></label><label class="user-field"><span>Correo</span><input name="email" type="email" maxlength="180" autocomplete="email" required value="${esc(data.user.email)}"></label><label class="user-field"><span>Contraseña actual</span><input name="current_password" type="password" autocomplete="current-password" aria-describedby="email-password-help"><small id="email-password-help">Solo es necesaria si cambias el correo.</small></label><div><button class="user-btn primary">Guardar cambios</button></div><p class="user-message" role="status" aria-live="polite" aria-atomic="true" data-user-profile-message></p></form></article>`;
    const form = $("[data-user-profile-form]");
    let savedEmail = data.user.email;
    form.elements.email.oninput = () => {
      form.elements.current_password.required = form.elements.email.value.trim().toLowerCase() !== savedEmail;
    };
    form.onsubmit = async event => {
      event.preventDefault();
      const fd = new FormData(form), message = $("[data-user-profile-message]");
      await submit(form, message, "Guardando…", async () => {
        const result = await api("/api/account/profile", { method: "POST", body: JSON.stringify({ display_name: fd.get("display_name"), email: fd.get("email"), current_password: fd.get("current_password") }) });
        savedEmail = result.user.email;
        form.elements.display_name.value = result.user.display_name;
        form.elements.email.value = savedEmail;
        form.elements.current_password.value = "";
        form.elements.current_password.required = false;
        $("[data-user-name]").textContent = result.user.display_name;
        feedback(message, "Cambios guardados correctamente.", "success");
      });
    };
  }

  const orderLabels = {
    pending: "Pendiente", paid: "Pagado", processing: "En preparación",
    ready: "Listo", shipped: "Enviado", completed: "Completado",
    cancelled: "Cancelado", refunded: "Reembolsado",
  };
  function orderDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Fecha no disponible" : new Intl.DateTimeFormat("es-SV", { day: "numeric", month: "short", year: "numeric" }).format(date);
  }
  function orderList(orders) {
    return orders.length ? orders.map(order => `<div class="user-order"><div><strong>${esc(order.public_id)}</strong><small>${esc(orderDate(order.created_at))}</small></div><span class="user-chip">${esc(orderLabels[order.status] || order.status)}</span><strong>${money(order.total_cents)}</strong></div>`).join("") : '<div class="user-empty"><strong>Aún no tienes pedidos.</strong><p>Cuando completes una compra aparecerá aquí.</p><a class="user-btn primary" href="/tienda.html">Explorar la tienda</a></div>';
  }
  function renderOrders(data) {
    const root = head("Mis pedidos", "Tus últimas 5 compras, con su estado y total.");
    root.innerHTML = `<article class="user-card">${orderList(data.recent_orders || [])}</article>`;
  }

  function renderSecurity() {
    const root = head("Seguridad", "Protege tu acceso y controla el estado de tu cuenta.");
    root.innerHTML = `<div class="user-grid"><article class="user-card"><h2>Cambiar contraseña</h2><p>Al cambiarla, las otras sesiones activas se cerrarán.</p><form class="user-form" data-user-password-form><label class="user-field"><span>Contraseña actual</span><input type="password" name="current_password" autocomplete="current-password" required></label><label class="user-field"><span>Nueva contraseña</span><input type="password" name="new_password" minlength="12" autocomplete="new-password" aria-describedby="password-help" required><small id="password-help">Usa al menos 12 caracteres.</small></label><label class="user-field"><span>Confirmar nueva contraseña</span><input type="password" name="confirm_password" minlength="12" autocomplete="new-password" required></label><button class="user-btn primary">Actualizar contraseña</button><p class="user-message" role="status" aria-live="polite" aria-atomic="true" data-user-password-message></p></form></article><article class="user-card user-danger"><h2>Desactivar cuenta</h2><p>Tu cuenta dejará de poder iniciar sesión. Tus pedidos existentes se conservan como registro transaccional.</p><form class="user-form" data-user-deactivate-form><label class="user-field"><span>Contraseña actual</span><input type="password" name="current_password" autocomplete="current-password" required></label><label class="user-field"><span>Escribe DESACTIVAR</span><input name="confirmation" required autocomplete="off"></label><button class="user-btn danger">Desactivar mi cuenta</button><p class="user-message" role="status" aria-live="polite" aria-atomic="true" data-user-deactivate-message></p></form></article></div>`;
    $("[data-user-password-form]").onsubmit = async event => {
      event.preventDefault();
      // Keep the form reference: currentTarget is cleared after an await.
      const form = event.currentTarget, fd = new FormData(form), message = $("[data-user-password-message]");
      if (fd.get("new_password") !== fd.get("confirm_password")) {
        feedback(message, "Las contraseñas no coinciden.", "error");
        form.elements.confirm_password.focus();
        return;
      }
      await submit(form, message, "Actualizando…", async () => {
        await api("/api/account/password", { method: "POST", body: JSON.stringify({ current_password: fd.get("current_password"), new_password: fd.get("new_password") }) });
        form.reset();
        feedback(message, "Contraseña actualizada. Las otras sesiones se cerraron.", "success");
      });
    };
    $("[data-user-deactivate-form]").onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget, fd = new FormData(form), message = $("[data-user-deactivate-message]");
      if (form.dataset.submitting === "true") return;
      if (String(fd.get("confirmation")).trim().toUpperCase() !== "DESACTIVAR") {
        feedback(message, "Escribe DESACTIVAR para continuar.", "error");
        form.elements.confirmation.focus();
        return;
      }
      if (!confirm("¿Seguro que quieres desactivar tu cuenta?")) return;
      await submit(form, message, "Desactivando…", async () => {
        await api("/api/account/deactivate", { method: "POST", body: JSON.stringify({ current_password: fd.get("current_password"), confirmation: fd.get("confirmation") }) });
        location.href = "/index.html";
      });
    };
  }

  async function boot() {
    const main = $("[data-user-main]");
    main.setAttribute("aria-busy", "true");
    try {
      const data = await api("/api/account");
      if (data.user.role !== "user") { location.href = "/admin/"; return; }
      shell(data.user);
      ({ resumen: renderOverview, datos: renderData, pedidos: renderOrders, seguridad: renderSecurity }[page] || renderOverview)(data);
    } catch (error) {
      if (error.status === 401) location.href = "/cuenta.html?next=" + encodeURIComponent(location.pathname);
      else {
        main.innerHTML = `<div class="user-card user-empty" role="alert"><strong>No pudimos cargar tu cuenta.</strong><p>${esc(error.message)}</p><button class="user-btn primary" type="button" data-user-retry>Volver a intentar</button> <a class="user-btn" href="/tienda.html">Ir a la tienda</a></div>`;
        $("[data-user-retry]").onclick = () => {
          $("[data-user-retry]").disabled = true;
          boot();
        };
      }
    } finally {
      main.removeAttribute("aria-busy");
    }
  }
  boot();
})();
