/** TIPS v6 UI foundation: skeleton global reference-counted + state helpers. */
(() => {
  "use strict";
  let pending = 0;
  let timer = null;

  function ensureLayer() {
    let layer = document.getElementById("tips-global-loading");
    if (layer) return layer;
    layer = document.createElement("div");
    layer.id = "tips-global-loading";
    layer.className = "tips-loading-layer";
    layer.setAttribute("aria-hidden", "true");
    layer.innerHTML = `
      <div class="tips-loading-shell" aria-label="Cargando contenido">
        <div class="tips-loading-head">
          <div class="tips-loading-line wide"></div>
          <div class="tips-loading-badge tips-skeleton"></div>
        </div>
        <div class="tips-loading-grid">
          <div class="tips-loading-card"><div class="tips-loading-line"></div><div class="tips-loading-line"></div></div>
          <div class="tips-loading-card"><div class="tips-loading-line"></div><div class="tips-loading-line"></div></div>
          <div class="tips-loading-card"><div class="tips-loading-line"></div><div class="tips-loading-line"></div></div>
        </div>
      </div>`;
    document.body.append(layer);
    return layer;
  }

  function begin() {
    pending += 1;
    const layer = ensureLayer();
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (pending > 0) {
        layer.classList.add("is-visible");
        layer.setAttribute("aria-hidden", "false");
        document.documentElement.setAttribute("aria-busy", "true");
      }
    }, 90);
  }

  function end() {
    pending = Math.max(0, pending - 1);
    if (pending !== 0) return;
    clearTimeout(timer);
    const layer = document.getElementById("tips-global-loading");
    layer?.classList.remove("is-visible");
    layer?.setAttribute("aria-hidden", "true");
    document.documentElement.removeAttribute("aria-busy");
  }

  function setState(container, state, title, description = "") {
    if (!container) return;
    container.innerHTML = `<div class="tips-state" data-state="${state}"><strong></strong><p></p></div>`;
    container.querySelector("strong").textContent = title;
    container.querySelector("p").textContent = description;
  }

  window.TipsLoading = { begin, end };
  window.TipsState = { set: setState };

  // Toda lectura/mutación iniciada con fetch comparte el mismo skeleton.
  // Así ninguna vista queda vacía o cambia de posición mientras espera al backend.
  if (!window.__tipsFetchWrapped && typeof window.fetch === "function") {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      begin();
      try { return await nativeFetch(...args); }
      finally { end(); }
    };
    window.__tipsFetchWrapped = true;
  }
})();
