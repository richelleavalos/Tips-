/**
 * Código de la experiencia del usuario/cliente: site settings. No contiene responsabilidades exclusivas del administrador.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const $$ = (selector, context = document) => [...context.querySelectorAll(selector)];

  async function loadSettings() {
    try {
      const response = await fetch("/api/site-settings", { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const data = await response.json();
      const settings = data.settings || {};
      applyTheme(settings.theme || {});
      applyHome(settings.home || {});
      applyContact(settings.contact || {});
    } catch (error) {
      console.debug("Configuración pública no disponible todavía.", error);
    }
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    if (/^#[0-9a-f]{6}$/i.test(theme.primary || "")) {
      root.style.setProperty("--forest", theme.primary);
      root.style.setProperty("--green", theme.primary);
    }
    if (/^#[0-9a-f]{6}$/i.test(theme.accent || "")) root.style.setProperty("--orange", theme.accent);
    if (/^#[0-9a-f]{6}$/i.test(theme.secondary || "")) root.style.setProperty("--brown", theme.secondary);
    if (/^#[0-9a-f]{6}$/i.test(theme.surface || "")) root.style.setProperty("--paper", theme.surface);
    const variant = ["orange", "green", "black", "brown"].includes(theme.logo_variant) ? theme.logo_variant : "orange";
    $$(".brand-logo").forEach(image => { image.src = `assets/logos/tips-logo-${variant}.svg`; });
  }

  function setText(selector, value) {
    if (typeof value !== "string" || !value.trim()) return;
    $$(selector).forEach(node => { node.textContent = value; });
  }

  function applyHome(home) {
    setText("[data-site-home-eyebrow]", home.eyebrow);
    setText("[data-site-home-title]", home.title);
    setText("[data-site-home-highlight]", home.highlight);
    setText("[data-site-home-description]", home.description);
    setText("[data-site-home-primary-cta]", home.primary_cta);
    setText("[data-site-home-secondary-cta]", home.secondary_cta);
  }

  function applyContact(contact) {
    setText("[data-site-location]", contact.location);
    if (contact.email) {
      $$("[data-site-email]").forEach(node => {
        node.textContent = contact.email;
        if (node.tagName === "A") node.href = `mailto:${contact.email}`;
      });
    }
  }

  loadSettings();
})();
