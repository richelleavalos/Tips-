/**
 * Núcleo visual y de interacción del panel administrativo de TIPS.
 *
 * Este módulo monta el shell compartido de todas las vistas del administrador:
 * navegación lateral, barra superior, identidad de sesión, alertas, búsqueda,
 * modales y notificaciones. La lógica de cada pantalla vive en admin-pages.js
 * o admin-aux-pages.js para mantener responsabilidades claras.
 */
(() => {
  "use strict";

  const $ = (selector, context = document) => context.querySelector(selector);
  const $$ = (selector, context = document) => [...context.querySelectorAll(selector)];

  /** Escapa contenido dinámico antes de insertarlo en plantillas HTML. */
  const esc = value => {
    const node = document.createElement("div");
    node.textContent = String(value ?? "");
    return node.innerHTML;
  };

  /** Formatea enteros expresados en centavos como moneda USD. */
  const usd = cents => new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format((Number(cents) || 0) / 100);

  let csrf = "";

  /**
   * Cliente HTTP mínimo del panel.
   * Agrega automáticamente CSRF en mutaciones y normaliza errores JSON.
   */
  async function api(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = { Accept: "application/json", ...(options.headers || {}) };

    if (method !== "GET") {
      if (!csrf) {
        const tokenResponse = await fetch("/api/csrf", { credentials: "same-origin" });
        const tokenData = await tokenResponse.json();
        csrf = tokenData.csrf_token;
      }
      headers["X-CSRF-Token"] = csrf;
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      method,
      headers,
    });
    const data = await response.json().catch(() => ({ error: "Respuesta inválida." }));

    if (!response.ok) {
      const error = new Error(data.error || "Ocurrió un error.");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  /** Muestra feedback no intrusivo para operaciones administrativas. */
  function toast(message, type = "ok") {
    let stack = $("[data-admin-toast-stack]");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "admin-toast-stack";
      stack.dataset.adminToastStack = "";
      document.body.append(stack);
    }
    const item = document.createElement("div");
    item.className = `admin-toast${type === "error" ? " error" : ""}`;
    item.textContent = message;
    stack.append(item);
    setTimeout(() => item.remove(), 3300);
  }

  /**
   * Iconografía lineal embebida para evitar dependencias externas y mantener
   * el panel consistente con la estética minimalista de la marca.
   */
  function icon(name) {
    const paths = {
      home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10.5V20h13v-9.5"/><path d="M9 20v-6h6v6"/>',
      orders: '<path d="M6 4h12l1 16H5L6 4Z"/><path d="M9 8a3 3 0 0 0 6 0"/>',
      products: '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4.5 7.8 7.5 4.3 7.5-4.3"/><path d="M12 12v9"/>',
      inventory: '<path d="M4 20V10"/><path d="M9 20V4"/><path d="M14 20v-7"/><path d="M19 20V7"/><path d="M2 20h20"/>',
      clients: '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-4 2.5-6 6-6s6 2 6 6"/><path d="M15 15c3 0 5 1.7 5 5"/>',
      portfolio: '<rect x="3" y="4" width="18" height="16" rx="1"/><circle cx="8" cy="9" r="1.5"/><path d="m4 17 5-5 3 3 2-2 6 5"/>',
      promo: '<path d="m4 20 16-16"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>',
      quote: '<path d="M6 3h9l4 4v14H6V3Z"/><path d="M14 3v5h5"/><path d="M9 12h6M9 16h6"/>',
      sales: '<path d="M4 18 10 12l4 3 6-8"/><path d="M15 7h5v5"/>',
      reports: '<path d="M4 20V9M10 20V4M16 20v-7M22 20H2"/>',
      settings: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14.2 3h-4.4l-.4 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2l.4 2.6h4.4l.4-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c0-.4.1-.8.1-1.2Z"/>',
      users: '<circle cx="12" cy="8" r="3"/><path d="M5 21c0-5 2.8-7 7-7s7 2 7 7"/>',
      account: '<circle cx="12" cy="8" r="3"/><path d="M5 21c0-5 2.8-7 7-7s7 2 7 7"/>',
      logout: '<path d="M10 5H5v14h5"/><path d="M14 8l4 4-4 4M18 12H9"/>',
      search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
    };
    return `<svg class="admin-svg" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.home}</svg>`;
  }

  /** Crea un enlace de navegación con estado activo accesible. */
  function navItem([key, href, iconName, text], active) {
    return `<a class="${active === key ? "active" : ""}" href="${href}"${active === key ? ' aria-current="page"' : ""}>${icon(iconName)}<span>${esc(text)}</span></a>`;
  }

  /** Construye la navegación lateral compartida por todas las vistas admin. */
  function navMarkup(active) {
    const primary = [
      ["dashboard", "index.html", "home", "Resumen"],
      ["pedidos", "pedidos.html", "orders", "Pedidos"],
      ["productos", "productos.html", "products", "Productos"],
      ["inventario", "inventario.html", "inventory", "Inventario"],
      ["clientes", "clientes.html", "clients", "Clientes"],
      ["proyectos", "proyectos.html", "portfolio", "Portafolio"],
      ["promociones", "promociones.html", "promo", "Promociones"],
      ["cotizaciones", "cotizaciones.html", "quote", "Cotizaciones"],
      ["ventas", "ventas.html", "sales", "Ventas"],
      ["reportes", "reportes.html", "reports", "Reportes"],
    ];
    const secondary = [
      ["configuracion", "configuracion.html", "settings", "Configuración"],
      ["usuarios", "usuarios.html", "users", "Usuarios"],
      ["cuenta", "cuenta.html", "account", "Mi cuenta"],
    ];

    return `
      <a class="admin-side-brand" href="index.html" aria-label="TIPS Administración">
        <span class="admin-brand-word">TIPS</span>
        <span class="admin-brand-lines">ARQUITECTURA<br>OBJETOS<br>INTERIORES</span>
      </a>
      <nav class="admin-nav-scroll" aria-label="Administración">
        <div class="admin-nav-list admin-nav-primary">${primary.map(item => navItem(item, active)).join("")}</div>
        <div class="admin-nav-separator"></div>
        <div class="admin-nav-list admin-nav-secondary">${secondary.map(item => navItem(item, active)).join("")}</div>
      </nav>
      <div class="admin-side-foot">
        <div class="admin-side-identity">
          <span class="admin-avatar admin-avatar-side" data-admin-side-avatar>A</span>
          <span><strong data-admin-side-name>Administrador</strong><small data-admin-side-email></small></span>
        </div>
        <button type="button" data-admin-logout>${icon("logout")}<span>Cerrar sesión</span></button>
      </div>`;
  }

  /** Monta sidebar, topbar y eventos globales de la aplicación administrativa. */
  function mountShell() {
    const page = document.body.dataset.adminPage || "dashboard";
    const sidebar = $("[data-admin-sidebar]");
    if (sidebar) sidebar.innerHTML = navMarkup(page);

    const top = $("[data-admin-top]");
    if (top) {
      top.innerHTML = `
        <div class="admin-top-left">
          <button class="admin-mobile-menu" type="button" data-admin-menu aria-label="Abrir menú">☰</button>
          <form class="admin-global-search" data-admin-global-search role="search">
            ${icon("search")}
            <input type="search" name="search" placeholder="Buscar productos, pedidos, clientes..." aria-label="Buscar en administración">
          </form>
        </div>
        <div class="admin-top-actions">
          <button class="admin-icon admin-bell" type="button" data-admin-alerts aria-label="Alertas">${icon("bell")}<span class="admin-count hidden" data-admin-alert-count>0</span></button>
          <button class="admin-profile-button" type="button" data-admin-profile>
            <span class="admin-avatar" data-admin-avatar>A</span>
            <span class="admin-profile-copy"><strong data-admin-profile-name>Administrador</strong><small>Administración</small></span>
            <span class="admin-chevron">⌄</span>
          </button>
        </div>
        <div class="admin-popover" data-admin-popover>
          <div class="identity"><strong data-admin-pop-name>Administrador</strong><small data-admin-pop-email></small></div>
          <a href="cuenta.html">Mi cuenta admin</a>
          <button type="button" data-admin-pop-logout>Cerrar sesión</button>
        </div>
        <div class="admin-alert-popover" data-admin-alert-popover>
          <div class="admin-alert-popover-head"><strong>Alertas</strong><button type="button" data-admin-alert-close>×</button></div>
          <div data-admin-alert-list></div>
        </div>`;
    }

    $("[data-admin-menu]")?.addEventListener("click", () => document.body.classList.toggle("admin-menu-open"));

    document.addEventListener("click", event => {
      const clickedOutsideMenu = !event.target.closest(".admin-side") && !event.target.closest("[data-admin-menu]");
      if (window.innerWidth <= 760 && document.body.classList.contains("admin-menu-open") && clickedOutsideMenu) {
        document.body.classList.remove("admin-menu-open");
      }
    });

    const profileButton = $("[data-admin-profile]");
    const popover = $("[data-admin-popover]");
    profileButton?.addEventListener("click", event => {
      event.stopPropagation();
      $("[data-admin-alert-popover]")?.classList.remove("open");
      popover?.classList.toggle("open");
    });

    document.addEventListener("click", event => {
      if (!event.target.closest("[data-admin-popover]") && !event.target.closest("[data-admin-profile]")) {
        popover?.classList.remove("open");
      }
    });

    /** La búsqueda global abre Productos con el término ya aplicado. */
    $("[data-admin-global-search]")?.addEventListener("submit", event => {
      event.preventDefault();
      const query = new FormData(event.currentTarget).get("search")?.trim();
      if (query) location.href = `productos.html?search=${encodeURIComponent(query)}`;
    });

    $$("[data-admin-logout],[data-admin-pop-logout]").forEach(button => button.addEventListener("click", logout));
  }

  /** Cierra la sesión administrativa y vuelve al acceso de cuenta. */
  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
    } catch {
      // Aunque el servidor ya no tenga sesión, la navegación local debe continuar.
    }
    location.href = "/cuenta.html";
  }

  /** Sincroniza nombre, correo e inicial del administrador en todo el shell. */
  function setIdentity(user) {
    if (!user) return;
    const name = user.display_name || "Administrador";
    const email = user.email || "";
    const initial = (name || email || "A").trim().charAt(0).toUpperCase();

    ["[data-admin-avatar]", "[data-admin-side-avatar]"].forEach(selector => {
      const element = $(selector);
      if (element) element.textContent = initial;
    });
    ["[data-admin-profile-name]", "[data-admin-pop-name]", "[data-admin-side-name]"].forEach(selector => {
      const element = $(selector);
      if (element) element.textContent = name;
    });
    ["[data-admin-pop-email]", "[data-admin-side-email]"].forEach(selector => {
      const element = $(selector);
      if (element) element.textContent = email;
    });
  }

  /** Renderiza el listado emergente de alertas del negocio. */
  function renderAlertPopover(alerts) {
    const panel = $("[data-admin-alert-popover]");
    const list = $("[data-admin-alert-list]");
    if (!panel || !list) return;

    list.innerHTML = alerts.length
      ? alerts.map(item => `<a class="admin-alert-popover-item" href="${item.view === "quotes" ? "cotizaciones.html" : item.view === "orders" ? "pedidos.html" : "inventario.html"}"><span class="dot ${esc(item.level)}"></span><div><strong>${esc(item.title)}</strong><small>${esc(item.message)}</small></div></a>`).join("")
      : '<div class="admin-alert-popover-empty"><strong>Todo al día</strong><small>No hay alertas pendientes.</small></div>';

    const button = $("[data-admin-alerts]");
    button?.addEventListener("click", event => {
      event.stopPropagation();
      $("[data-admin-popover]")?.classList.remove("open");
      panel.classList.toggle("open");
    });
    $("[data-admin-alert-close]")?.addEventListener("click", () => panel.classList.remove("open"));
    document.addEventListener("click", event => {
      if (!event.target.closest("[data-admin-alert-popover]") && !event.target.closest("[data-admin-alerts]")) {
        panel.classList.remove("open");
      }
    });
  }

  /** Carga las métricas base y actualiza badge, identidad y alertas. */
  async function loadAlerts() {
    try {
      const data = await api("/api/admin/overview");
      setIdentity(data.user);
      const alerts = data.alerts || [];
      const count = alerts.reduce((sum, item) => sum + Number(item.count || 0), 0);
      const badge = $("[data-admin-alert-count]");
      if (badge) {
        badge.textContent = count;
        badge.classList.toggle("hidden", !count);
      }
      renderAlertPopover(alerts);
      return data;
    } catch (error) {
      if (error.status === 401 || error.status === 403) showAuth();
      throw error;
    }
  }

  /** Presenta una pantalla coherente cuando el visitante no es administrador. */
  function showAuth() {
    const main = $("[data-admin-main]");
    if (!main) return;
    main.innerHTML = `<section class="admin-auth-block"><div class="admin-auth-brand">TIPS</div><p class="admin-kicker">ÁREA ADMINISTRATIVA</p><h2>Acceso administrativo requerido</h2><p>Esta ruta pertenece exclusivamente a administradores.</p><a class="admin-btn primary" href="/cuenta.html">Iniciar sesión →</a></section>`;
  }

  /** Abre un modal reutilizable para formularios de edición del panel. */
  function modal(content, title = "Editar", wide = false) {
    const layer = document.createElement("div");
    layer.className = "admin-modal-layer open";
    layer.setAttribute("role", "presentation");
    layer.innerHTML = `<section class="admin-modal${wide ? " wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><header class="admin-modal-head"><h2>${esc(title)}</h2><button class="admin-modal-close" type="button" aria-label="Cerrar">×</button></header><div class="admin-modal-body">${content}</div></section>`;
    document.body.append(layer);
    document.body.classList.add("admin-overlay-open");

    const onKeyDown = event => {
      if (event.key === "Escape") close();
    };
    const close = () => {
      document.removeEventListener("keydown", onKeyDown);
      layer.remove();
      if (!document.querySelector(".admin-modal-layer.open")) {
        document.body.classList.remove("admin-overlay-open");
      }
    };

    layer.querySelector(".admin-modal-close").addEventListener("click", close);
    layer.addEventListener("click", event => { if (event.target === layer) close(); });
    document.addEventListener("keydown", onKeyDown);
    requestAnimationFrame(() => layer.querySelector(".admin-modal-close")?.focus());
    return { layer, close, body: layer.querySelector(".admin-modal-body") };
  }

  /**
   * Inicializa la cabecera editorial de cada vista y reserva el área donde su
   * controlador insertará contenido dinámico.
   */
  function setPageTitle(title, subtitle = "") {
    const main = $("[data-admin-main]");
    if (!main) return null;
    main.innerHTML = `<div class="admin-page-head"><div><p class="admin-kicker">ADMINISTRACIÓN TIPS</p><h1>${esc(title)}</h1><p class="admin-page-subtitle">${esc(subtitle)}</p></div><div class="admin-actions-row" data-page-actions></div></div><section data-page-content><div class="admin-skeleton tall"></div></section>`;
    document.title = `${title} | Tips Admin`;
    return main;
  }

  mountShell();
  window.TipsAdmin = {
    $,
    $$,
    esc,
    usd,
    api,
    toast,
    modal,
    setIdentity,
    loadAlerts,
    showAuth,
    setPageTitle,
  };
})();
