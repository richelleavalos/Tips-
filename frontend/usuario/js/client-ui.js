/**
 * Código de la experiencia del usuario/cliente: client ui. No contiene responsabilidades exclusivas del administrador.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const $ = (s, c = document) => c.querySelector(s), $$ = (s, c = document) => [...c.querySelectorAll(s)];
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

  function enhanceCart() {
    $$(".cart-footer").forEach(footer => {
      if (!$(".cart-guidance", footer)) footer.insertAdjacentHTML("beforeend", '<div class="cart-guidance">Revisa tu selección antes de confirmar el pedido.</div>');
    });
  }

  enhanceStoreHeader();
  enhanceCart();
})();
