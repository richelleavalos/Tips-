/**
 * Código de la experiencia administrativa: admin product payload. Mantiene esta responsabilidad aislada del frontend de cliente.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const admin = window.TipsAdmin;
  if (!admin) return;
  const originalApi = admin.api;
  const relativeMedia = value => value ? String(value).replace(/^\/+/, "") : value;

  admin.api = async function(path, options = {}) {
    if ((path === "/api/admin/products/create" || path === "/api/admin/products/update") && options.body) {
      try {
        const payload = JSON.parse(options.body);
        const form = document.querySelector("[data-product-form]");
        if (form) {
          const category = form.elements.category_id?.value;
          payload.category_id = category ? Number(category) : null;
          if (form.elements.stock_status?.value) payload.stock_status = form.elements.stock_status.value;
          if (form.elements.option_summary?.value) payload.option_summary = form.elements.option_summary.value;
          options = { ...options, body: JSON.stringify(payload) };
        }
      } catch {}
    }

    const data = await originalApi(path, options);
    if (path === "/api/admin/products" && Array.isArray(data.items)) {
      data.items.forEach(item => { item.primary_image = relativeMedia(item.primary_image); });
    }
    if (path.startsWith("/api/admin/products/images") && Array.isArray(data.items)) {
      data.items.forEach(item => { item.path = relativeMedia(item.path); });
    }
    if (path === "/api/admin/products/images/add" && data.path) data.path = relativeMedia(data.path);
    return data;
  };
})();
