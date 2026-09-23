/**
 * Código de la experiencia administrativa: admin config. Mantiene esta responsabilidad aislada del frontend de cliente.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const A = window.TipsAdmin;
  if (!A || document.body.dataset.adminPage !== "configuracion") return;
  const { $, $$, esc, api, toast, setPageTitle, loadAlerts, setIdentity } = A;

  const defaults = {
    primary: "#173d2b",
    accent: "#ef7d22",
    secondary: "#825334",
    surface: "#f7f7f2",
    logo_variant: "orange",
  };
  const logoNames = { orange: "Naranja", green: "Verde", black: "Negro", brown: "Café" };

  function colorControl(name, label, value) {
    return `<label class="color-field-wrap"><span>${esc(label)}</span><div class="color-field"><input type="color" name="${name}" value="${esc(value)}" data-color-picker="${name}"><input type="text" value="${esc(value)}" maxlength="7" data-color-text="${name}" aria-label="Código ${esc(label)}"></div></label>`;
  }

  function logoCards(selected) {
    return Object.keys(logoNames).map(variant => `<label class="${selected === variant ? "is-selected" : ""}" data-logo-card="${variant}"><img src="/assets/logos/tips-logo-${variant}.svg" alt="Logo Tips ${logoNames[variant]}"><span class="logo-meta"><input type="radio" name="logo_variant" value="${variant}" ${selected === variant ? "checked" : ""}>${logoNames[variant]}</span></label>`).join("");
  }

  function bindThemePreview(form) {
    const preview = $("[data-theme-preview]");
    const logo = $("[data-preview-logo]");
    const update = () => {
      const fd = new FormData(form);
      preview.style.setProperty("--preview-primary", String(fd.get("primary") || defaults.primary));
      preview.style.setProperty("--preview-accent", String(fd.get("accent") || defaults.accent));
      preview.style.setProperty("--preview-secondary", String(fd.get("secondary") || defaults.secondary));
      preview.style.setProperty("--preview-surface", String(fd.get("surface") || defaults.surface));
      const variant = String(fd.get("logo_variant") || defaults.logo_variant);
      logo.src = `/assets/logos/tips-logo-${variant}.svg`;
      $$('[data-logo-card]', form).forEach(card => card.classList.toggle("is-selected", card.dataset.logoCard === variant));
    };
    $$('[data-color-picker]', form).forEach(input => input.addEventListener("input", () => {
      const text = $(`[data-color-text="${input.dataset.colorPicker}"]`, form);
      if (text) text.value = input.value.toUpperCase();
      update();
    }));
    $$('[data-color-text]', form).forEach(input => input.addEventListener("input", () => {
      const value = input.value.trim();
      if (/^#[0-9a-fA-F]{6}$/.test(value)) {
        const picker = $(`[data-color-picker="${input.dataset.colorText}"]`, form);
        if (picker) picker.value = value;
        update();
      }
    }));
    $$('input[name="logo_variant"]', form).forEach(input => input.addEventListener("change", update));
    update();
  }

  async function saveObject(key, value) {
    await api("/api/admin/settings/save", { method: "POST", body: JSON.stringify({ key, value, is_public: true }) });
  }

  async function boot() {
    setPageTitle("Apariencia y sitio", "Identidad visual y contenido configurable de Tips.");
    try {
      const overview = await loadAlerts();
      setIdentity(overview.user);
      const data = await api("/api/admin/settings");
      const map = Object.fromEntries(data.items.map(item => [item.key, item.value || {}]));
      const theme = { ...defaults, ...(map.theme || {}) };
      const home = map.home || {};
      const contact = map.contact || {};
      const root = $("[data-page-content]");
      root.innerHTML = `<div class="appearance-layout"><section class="appearance-card"><h2>Paleta de colores</h2><p>Como en la versión anterior: selector visual y código HEX editable.</p><form data-theme-form><div class="color-grid">${colorControl("primary", "Verde principal", theme.primary)}${colorControl("accent", "Acento naranja", theme.accent)}${colorControl("secondary", "Café secundario", theme.secondary)}${colorControl("surface", "Fondo", theme.surface)}</div><div style="margin-top:22px"><h2>Logotipo</h2><p style="color:var(--a-muted);font-size:.74rem">Elige visualmente una de las versiones oficiales.</p><div class="logo-choice">${logoCards(theme.logo_variant)}</div></div><div class="appearance-actions"><button class="admin-btn primary" type="submit">Guardar apariencia</button></div></form></section><aside class="appearance-card"><h2>Vista previa</h2><p>Los cambios se previsualizan antes de guardarse.</p><div class="theme-preview" data-theme-preview><img data-preview-logo src="/assets/logos/tips-logo-${esc(theme.logo_variant)}.svg" alt="Vista previa del logo"><small>Arquitectura · diseño · productos</small><h3>Tips que inspiran</h3><p>Una muestra rápida de cómo conviven la paleta y el logotipo.</p></div></aside></div><div class="config-section-grid" style="margin-top:16px"><section class="appearance-card"><h2>Contenido del inicio</h2><p>Textos principales visibles para clientes.</p><form data-home-form><div class="admin-form-grid"><div class="admin-field full"><span>Frase superior</span><input name="eyebrow" value="${esc(home.eyebrow || "")}"></div><div class="admin-field"><span>Título</span><input name="title" value="${esc(home.title || "")}"></div><div class="admin-field"><span>Palabra destacada</span><input name="highlight" value="${esc(home.highlight || "")}"></div><div class="admin-field full"><span>Descripción</span><textarea name="description">${esc(home.description || "")}</textarea></div><div class="admin-field"><span>Botón principal</span><input name="primary_cta" value="${esc(home.primary_cta || "")}"></div><div class="admin-field"><span>Botón tienda</span><input name="secondary_cta" value="${esc(home.secondary_cta || "")}"></div></div><div class="appearance-actions"><button class="admin-btn primary">Guardar contenido</button></div></form></section><section class="appearance-card"><h2>Contacto</h2><p>Datos visibles para clientes.</p><form data-contact-form><div class="admin-form-grid"><div class="admin-field full"><span>Ubicación</span><input name="location" value="${esc(contact.location || "")}"></div><div class="admin-field"><span>Correo</span><input name="email" type="email" value="${esc(contact.email || "")}"></div><div class="admin-field"><span>WhatsApp</span><input name="whatsapp" value="${esc(contact.whatsapp || "")}"></div><div class="admin-field"><span>Instagram</span><input name="instagram" value="${esc(contact.instagram || "")}"></div><div class="admin-field"><span>Facebook</span><input name="facebook" value="${esc(contact.facebook || "")}"></div></div><div class="appearance-actions"><button class="admin-btn primary">Guardar contacto</button></div></form></section></div>`;

      const themeForm = $("[data-theme-form]");
      bindThemePreview(themeForm);
      themeForm.onsubmit = async event => {
        event.preventDefault();
        const fd = new FormData(themeForm);
        const value = Object.fromEntries(fd.entries());
        if (![value.primary, value.accent, value.secondary, value.surface].every(v => /^#[0-9a-fA-F]{6}$/.test(String(v)))) {
          toast("Revisa los códigos de color.", "error"); return;
        }
        try { await saveObject("theme", value); toast("Apariencia actualizada."); } catch (error) { toast(error.message, "error"); }
      };
      $("[data-home-form]").onsubmit = async event => {
        event.preventDefault();
        try { await saveObject("home", Object.fromEntries(new FormData(event.currentTarget).entries())); toast("Contenido guardado."); } catch (error) { toast(error.message, "error"); }
      };
      $("[data-contact-form]").onsubmit = async event => {
        event.preventDefault();
        try { await saveObject("contact", Object.fromEntries(new FormData(event.currentTarget).entries())); toast("Contacto guardado."); } catch (error) { toast(error.message, "error"); }
      };
    } catch (error) {
      if (error.status !== 401 && error.status !== 403) toast(error.message, "error");
    }
  }
  boot();
})();
