/**
 * Código de la experiencia del usuario/cliente: client ui. No contiene responsabilidades exclusivas del administrador.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const $ = (s, c = document) => c.querySelector(s), $$ = (s, c = document) => [...c.querySelectorAll(s)];
  let products = [];
  const byId = new Map();
  const mediaSrc = path => path ? (String(path).startsWith("/") ? String(path) : "/" + String(path).replace(/^\/+/, "")) : "";

  function enhanceStoreHeader() {
    if (document.body.dataset.page !== "store") return;
    const main = $(".store-main");
    if (main && !$(".client-trust-row", main)) {
      const title = $(".store-title-row", main);
      title?.insertAdjacentHTML("afterend", '<div class="client-trust-row"><span><b>✓</b> Precios en USD</span><span><b>✓</b> Stock visible</span><span><b>✓</b> Personalización según producto</span><span><b>✓</b> Carrito siempre disponible</span></div>');
    }
    const results = $(".catalog-results");
    if (results && !$(".client-store-help", results)) {
      results.insertAdjacentHTML("afterbegin", '<div class="client-store-help"><strong>Elige una pieza y abre sus detalles.</strong><span>Ahí podrás revisar precio, disponibilidad y cantidad antes de agregarla.</span></div>');
    }
  }

  function replaceProductVisual(node, product) {
    if (!node || !product?.primary_image || node.classList.contains("has-real-image")) return;
    node.classList.add("has-real-image");
    const img = document.createElement("img");
    img.className = "product-real-image";
    img.src = mediaSrc(product.primary_image);
    img.alt = product.primary_image_alt || product.name || "Producto Tips";
    img.loading = "lazy";
    img.decoding = "async";
    node.replaceChildren(img);
  }

  function enhanceCards() {
    $$('[data-product]').forEach(button => {
      const product = byId.get(Number(button.dataset.product));
      replaceProductVisual($(".product-placeholder", button), product);
      const info = $(".shop-info", button);
      if (info && !$(".client-card-hint", info)) info.insertAdjacentHTML("beforeend", '<span class="client-card-hint">Ver detalles</span>');
    });
    $$(".mini-product").forEach(card => {
      const title = $("h3", card)?.textContent?.trim();
      const product = products.find(p => p.name === title);
      replaceProductVisual($(".product-placeholder", card), product);
    });
    const modal = $("[data-product-modal]");
    if (modal?.classList.contains("is-open")) {
      const title = $("[data-modal-title]", modal)?.textContent?.trim();
      const product = products.find(p => p.name === title);
      const visual = $("[data-modal-visual]", modal);
      if (visual && product?.primary_image) {
        visual.classList.add("has-real-image");
        let img = $("img", visual);
        if (!img) {
          img = document.createElement("img");
          img.className = "product-real-image";
          visual.append(img);
        }
        img.src = mediaSrc(product.primary_image);
        img.alt = product.primary_image_alt || product.name;
      }
    }
  }

  function enhanceCart() {
    $$(".cart-footer").forEach(footer => {
      if (!$(".cart-guidance", footer)) footer.insertAdjacentHTML("beforeend", '<div class="cart-guidance">Revisa tu selección antes de continuar al checkout.</div>');
    });
  }

  async function loadProducts() {
    try {
      const response = await fetch("/api/products", { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const data = await response.json();
      products = data.items || [];
      products.forEach(p => byId.set(Number(p.id), p));
      enhanceCards();
    } catch {}
  }

  enhanceStoreHeader();
  enhanceCart();
  loadProducts();
  const observer = new MutationObserver(() => { enhanceCards(); enhanceCart(); });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
})();
