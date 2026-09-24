/**
 * Aplicación pública principal de Tips.
 *
 * La clase TipsClientApp coordina navegación, catálogo, carrito, portafolio,
 * autenticación y checkout. ApiClient encapsula todas las llamadas HTTP y la
 * gestión del token CSRF para que las vistas no repitan lógica de transporte.
 */
(() => {
  "use strict";

  /** Busca el primer elemento que coincide con un selector. */
  const $ = (selector, context = document) => context.querySelector(selector);

  /** Devuelve todos los elementos de un selector como un arreglo normal. */
  const $$ = (selector, context = document) => [...context.querySelectorAll(selector)];

  /** Escapa texto antes de insertarlo en fragmentos HTML generados por JavaScript. */
  const escapeHtml = (value) => {
    const node = document.createElement("div");
    node.textContent = String(value ?? "");
    return node.innerHTML;
  };

  /** Convierte centavos de dólar al formato monetario mostrado por la tienda. */
  const formatUsd = (cents) => new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format((Number(cents) || 0) / 100);

  /** Alterna tonos decorativos deterministas cuando un producto no tiene imagen. */
  const productTone = (id) => ["green", "orange", "brown"][Number(id || 0) % 3];

  /**
   * Devuelve una fotografía editorial local para productos demo conocidos.
   * Si el catálogo cambia, el producto conserva automáticamente el placeholder
   * generado por CSS, de modo que la UI nunca depende de una imagen obligatoria.
   */
  const productImage = (product) => {
    const name = String(product?.name || "").toLowerCase();
    const rules = [
      [/lámpara|lampara/, "/assets/images/editorial-products/lamp.jpg"],
      [/mochila|bolso/, "/assets/images/editorial-products/backpack.jpg"],
      [/botella|térmica|termica/, "/assets/images/editorial-products/bottle.jpg"],
      [/vela/, "/assets/images/editorial-products/candle.jpg"],
      [/zapatilla|running/, "/assets/images/editorial-products/shoes.jpg"],
    ];
    return rules.find(([pattern]) => pattern.test(name))?.[1] || "";
  };

  /** Construye atributos seguros para la superficie visual de un producto. */
  const productVisualAttrs = (product) => {
    const image = productImage(product);
    return image
      ? `class="product-placeholder editorial-product-image" data-tone="${productTone(product.id)}" style="background-image:url(${image})"`
      : `class="product-placeholder" data-tone="${productTone(product.id)}"`;
  };

  class ApiClient {
    /** Cliente HTTP mínimo con sesión de navegador y protección CSRF. */
    constructor() {
      this.csrfToken = "";
    }

    /** Obtiene un token CSRF una sola vez y lo reutiliza durante la página. */
    async ensureCsrfToken() {
      if (this.csrfToken) return this.csrfToken;
      const response = await fetch("/api/csrf", { credentials: "same-origin" });
      const payload = await response.json();
      this.csrfToken = payload.csrf_token;
      return this.csrfToken;
    }

    /** Ejecuta una solicitud JSON y transforma errores HTTP en excepciones útiles. */
    async request(path, options = {}) {
      const method = (options.method || "GET").toUpperCase();
      const headers = { Accept: "application/json", ...(options.headers || {}) };

      if (method !== "GET") {
        headers["X-CSRF-Token"] = await this.ensureCsrfToken();
        if (options.body) headers["Content-Type"] = "application/json";
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
  }

  class TipsClientApp {
    /** Coordina el estado y los comportamientos de todas las páginas del cliente. */
    constructor(apiClient = new ApiClient()) {
      this.api = apiClient;
      this.products = [];
      this.portfolio = [];
      this.activeProduct = null;
      this.cart = { items: [], subtotal_cents: 0 };
      this.cartDrawer = $("[data-cart-drawer]");
    }

    /** Activa comportamientos globales y luego inicializa la vista actual. */
    async init() {
      this.bindNavigation();
      this.bindCartDrawer();
      this.bindProductModal();
      this.bindQuoteForm();
      this.bindCheckoutForm();

      await this.loadCart();

      const page = document.body.dataset.page;
      if (page === "home") await this.loadHome();
      if (page === "store") await this.loadStore();
      if (page === "architecture") await this.loadArchitecture();
      if (page === "project") await this.loadProject();
      if (page === "account") await this.loadAccount();
    }

    // ---------------------------------------------------------------------
    // Navegación global
    // ---------------------------------------------------------------------

    /** Controla la navegación móvil y mantiene aria-expanded sincronizado. */
    bindNavigation() {
      const nav = $("[data-nav]");
      const toggle = $("[data-nav-toggle]");
      toggle?.addEventListener("click", () => {
        const opened = nav.classList.toggle("is-open");
        toggle.setAttribute("aria-expanded", String(opened));
        document.body.classList.toggle("no-scroll", opened);
      });
      $$("[data-nav] a").forEach((link) => link.addEventListener("click", () => {
        nav?.classList.remove("is-open");
        document.body.classList.remove("no-scroll");
      }));
    }

    // ---------------------------------------------------------------------
    // Carrito
    // ---------------------------------------------------------------------

    /** Descarga el carrito de la sesión actual y actualiza todas sus vistas. */
    async loadCart() {
      try {
        const response = await this.api.request("/api/cart");
        this.cart = {
          items: Array.isArray(response.items) ? response.items : [],
          subtotal_cents: Number(response.subtotal_cents) || 0,
          currency: response.currency || "USD",
        };
        this.renderCart();
      } catch (error) {
        console.error(error);
        const container = $("[data-cart-items]");
        if (container) {
          container.innerHTML = '<div class="cart-empty"><strong>No pudimos cargar tu carrito.</strong><p>Cierra el panel y vuelve a intentarlo.</p></div>';
        }
        $$('[data-cart-subtotal]').forEach((node) => { node.textContent = "$0.00"; });
      }
    }

    /** Renderiza contador, subtotal, líneas del carrito y resumen de checkout. */
    renderCart() {
      const itemCount = this.cart.items.reduce((total, item) => total + item.quantity, 0);
      $$("[data-cart-count]").forEach((node) => { node.textContent = itemCount; });
      $$("[data-cart-subtotal]").forEach((node) => { node.textContent = formatUsd(this.cart.subtotal_cents); });

      const container = $("[data-cart-items]");
      if (container) {
        container.innerHTML = this.cart.items.length
          ? this.cart.items.map((item) => `
              <article class="cart-item">
                <div class="cart-item-thumb"></div>
                <div>
                  <h3>${escapeHtml(item.name)}</h3>
                  <small>${escapeHtml(item.option_summary || "Estándar")} · Cant. ${item.quantity}</small>
                  <div>
                    <button data-dec="${item.id}">−</button>
                    <button data-inc="${item.id}">+</button>
                    <button data-remove="${item.id}">Eliminar</button>
                  </div>
                </div>
                <strong>${formatUsd(item.line_total_cents)}</strong>
              </article>`).join("")
          : '<div class="cart-empty"><strong>Tu carrito está vacío.</strong><p>Agrega productos desde el catálogo.</p></div>';

        $$('[data-remove]', container).forEach((button) => {
          button.onclick = () => this.changeCart("remove", Number(button.dataset.remove));
        });
        $$('[data-inc]', container).forEach((button) => {
          button.onclick = () => this.changeCart("inc", Number(button.dataset.inc));
        });
        $$('[data-dec]', container).forEach((button) => {
          button.onclick = () => this.changeCart("dec", Number(button.dataset.dec));
        });
      }
      this.renderCheckout();
    }

    /** Aplica una acción sobre una línea del carrito y usa la respuesta como nuevo estado. */
    async changeCart(action, itemId) {
      try {
        this.cart = await this.api.request("/api/cart/items/change", {
          method: "POST",
          body: JSON.stringify({ action, item_id: itemId }),
        });
        this.renderCart();
      } catch (error) {
        alert(error.message);
      }
    }

    /** Abre y cierra el panel lateral del carrito desde cualquier página pública. */
    bindCartDrawer() {
      $$('[data-cart-open]').forEach((button) => {
        button.onclick = async () => {
          if (!this.cartDrawer) return;
          this.cartDrawer.classList.add("is-open");
          this.cartDrawer.setAttribute("aria-hidden", "false");
          document.body.classList.add("no-scroll");
          // Refresca al abrir: el drawer nunca depende de un estado antiguo.
          await this.loadCart();
          $("[data-cart-close]", this.cartDrawer)?.focus();
        };
      });
      $("[data-cart-close]")?.addEventListener("click", () => this.closeCartDrawer());
      this.cartDrawer?.addEventListener("click", (event) => {
        if (event.target === this.cartDrawer) this.closeCartDrawer();
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && this.cartDrawer?.classList.contains("is-open")) {
          this.closeCartDrawer();
        }
      });
    }

    /** Cierra el panel del carrito y devuelve el scroll a la página. */
    closeCartDrawer() {
      this.cartDrawer?.classList.remove("is-open");
      this.cartDrawer?.setAttribute("aria-hidden", "true");
      if (!$("[data-product-modal].is-open") && !$("[data-order-success].is-open")) {
        document.body.classList.remove("no-scroll");
      }
    }

    // ---------------------------------------------------------------------
    // Inicio y tienda
    // ---------------------------------------------------------------------

    /** Carga los proyectos y productos destacados de la página de inicio. */
    async loadHome() {
      try {
        const [projects, products] = await Promise.all([
          this.api.request("/api/portfolio"),
          this.api.request("/api/products"),
        ]);
        const projectContainer = $("[data-home-projects]");
        if (projectContainer) {
          projectContainer.innerHTML = projects.items.slice(0, 4).map((project) => `
            <a class="project-card" href="proyecto.html?id=${project.id}">
              <div class="project-art"></div>
              <div class="project-card-content">
                <small>${escapeHtml(project.category)}</small>
                <h3>${escapeHtml(project.title)}</h3>
              </div>
            </a>`).join("");
        }
        const productContainer = $("[data-home-products]");
        if (productContainer) {
          productContainer.innerHTML = products.items.slice(0, 5).map((product) => `
            <a class="mini-product" href="tienda.html">
              <div ${productVisualAttrs(product)}></div>
              <h3>${escapeHtml(product.name)}</h3>
              <p>${formatUsd(product.base_price_cents)}</p>
            </a>`).join("");
        }
      } catch (error) {
        console.error(error);
      }
    }

    /** Descarga catálogo/categorías y conecta los controles de filtrado. */
    async loadStore() {
      const grid = $("[data-product-grid]");
      if (!grid) return;
      try {
        const [products, categories] = await Promise.all([
          this.api.request("/api/products"),
          this.api.request("/api/categories"),
        ]);
        this.products = products.items;
        $("[data-category-filters]").innerHTML = [
          '<label><input type="radio" name="category" value="" checked> Todos</label>',
          ...categories.items.map((category) => (
            `<label><input type="radio" name="category" value="${escapeHtml(category.slug)}"> ${escapeHtml(category.name)}</label>`
          )),
        ].join("");

        $$('input[name="category"]').forEach((input) => { input.onchange = () => this.renderStore(); });
        $("[data-product-search]").oninput = () => this.renderStore();
        $("[data-stock-filter]").onchange = () => this.renderStore();
        $$("[data-sort]").forEach((select) => {
          select.onchange = (event) => {
            $$("[data-sort]").forEach((other) => { other.value = event.target.value; });
            this.renderStore();
          };
        });
        $("[data-clear-filters]").onclick = () => this.clearStoreFilters();
        $("[data-filter-toggle]")?.addEventListener("click", () => $("[data-filters]").classList.add("is-open"));
        $("[data-filter-close]")?.addEventListener("click", () => $("[data-filters]").classList.remove("is-open"));
        this.renderStore();
      } catch (error) {
        grid.innerHTML = `<div class="empty-state"><strong>No pudimos cargar el catálogo.</strong><p>${escapeHtml(error.message)}</p></div>`;
      }
    }

    /** Restablece filtros a su estado inicial y vuelve a dibujar el catálogo. */
    clearStoreFilters() {
      const allCategory = $('input[name="category"][value=""]');
      if (allCategory) allCategory.checked = true;
      $("[data-product-search]").value = "";
      $("[data-stock-filter]").checked = false;
      this.renderStore();
    }

    /** Filtra, ordena y pinta productos usando el estado actual de los controles. */
    renderStore() {
      const grid = $("[data-product-grid]");
      if (!grid) return;
      const search = $("[data-product-search]").value.trim().toLowerCase();
      const category = $('input[name="category"]:checked')?.value || "";
      const onlyStock = $("[data-stock-filter]").checked;
      const sort = $("[data-sort]").value;

      const list = this.products.filter((product) => (
        (!search || `${product.name} ${product.description}`.toLowerCase().includes(search))
        && (!category || product.category_slug === category)
        && (!onlyStock || Number(product.stock_quantity) > 0)
      ));

      if (sort === "price-asc") list.sort((a, b) => a.base_price_cents - b.base_price_cents);
      if (sort === "price-desc") list.sort((a, b) => b.base_price_cents - a.base_price_cents);
      if (sort === "name") list.sort((a, b) => a.name.localeCompare(b.name, "es"));

      $("[data-results-count]").textContent = `${list.length} producto${list.length === 1 ? "" : "s"}`;
      $("[data-empty-products]").classList.toggle("hidden", Boolean(list.length));
      grid.innerHTML = list.map((product) => `
        <article class="shop-card">
          <span class="stock-chip">${Number(product.stock_quantity) > 0 ? "Disponible" : "Bajo pedido"}</span>
          <button class="product-open" data-product="${product.id}">
            <div ${productVisualAttrs(product)}></div>
            <div class="shop-info">
              <small>${escapeHtml(product.category_name)}</small>
              <h3>${escapeHtml(product.name)}</h3>
              <strong>Desde ${formatUsd(product.base_price_cents)}</strong>
            </div>
          </button>
        </article>`).join("");
      $$('[data-product]', grid).forEach((button) => {
        button.onclick = () => this.openProductModal(Number(button.dataset.product));
      });
    }

    // ---------------------------------------------------------------------
    // Vista rápida de producto
    // ---------------------------------------------------------------------

    /** Muestra el producto seleccionado en el modal de compra rápida. */
    openProductModal(productId) {
      this.activeProduct = this.products.find((product) => Number(product.id) === productId);
      if (!this.activeProduct) return;
      $("[data-modal-title]").textContent = this.activeProduct.name;
      $("[data-modal-description]").textContent = this.activeProduct.description;
      $("[data-modal-price]").textContent = `Desde ${formatUsd(this.activeProduct.base_price_cents)}`;
      const modalVisual = $("[data-modal-visual]");
      modalVisual.dataset.tone = productTone(productId);
      const image = productImage(this.activeProduct);
      modalVisual.style.backgroundImage = image ? `url(${image})` : "";
      $("[data-modal-qty]").value = 1;
      $("[data-modal-message]").textContent = "";
      const layer = $("[data-product-modal]");
      layer.classList.add("is-open");
      layer.setAttribute("aria-hidden", "false");
      document.body.classList.add("no-scroll");
      $("[data-modal-close]", layer)?.focus();
    }

    /** Cierra el modal de producto y restaura el scroll de la página. */
    closeProductModal() {
      const layer = $("[data-product-modal]");
      layer?.classList.remove("is-open");
      layer?.setAttribute("aria-hidden", "true");
      if (!this.cartDrawer?.classList.contains("is-open")) document.body.classList.remove("no-scroll");
    }

    /** Conecta cantidad, cierre y alta al carrito dentro del modal. */
    bindProductModal() {
      $("[data-modal-close]")?.addEventListener("click", () => this.closeProductModal());
      $("[data-product-modal]")?.addEventListener("click", (event) => {
        if (event.target === $("[data-product-modal]")) this.closeProductModal();
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && $("[data-product-modal]")?.classList.contains("is-open")) {
          this.closeProductModal();
        }
      });
      $("[data-qty-minus]")?.addEventListener("click", () => {
        const input = $("[data-modal-qty]");
        input.value = Math.max(1, Number(input.value) - 1);
      });
      $("[data-qty-plus]")?.addEventListener("click", () => {
        const input = $("[data-modal-qty]");
        input.value = Math.min(25, Number(input.value) + 1);
      });
      $("[data-modal-add]")?.addEventListener("click", async () => {
        const message = $("[data-modal-message]");
        try {
          this.cart = await this.api.request("/api/cart/items", {
            method: "POST",
            body: JSON.stringify({
              variant_id: Number(this.activeProduct.first_variant_id),
              quantity: Math.max(1, Math.min(25, Number($("[data-modal-qty]").value))),
              customization_value_ids: [],
            }),
          });
          this.renderCart();
          message.textContent = "Agregado al carrito.";
          setTimeout(async () => {
            this.closeProductModal();
            if (!this.cartDrawer) return;
            this.cartDrawer.classList.add("is-open");
            this.cartDrawer.setAttribute("aria-hidden", "false");
            document.body.classList.add("no-scroll");
            await this.loadCart();
          }, 180);
        } catch (error) {
          message.textContent = error.message;
        }
      });
    }

    // ---------------------------------------------------------------------
    // Portafolio y cotizaciones
    // ---------------------------------------------------------------------

    /** Carga el portafolio y activa sus filtros por categoría. */
    async loadArchitecture() {
      try {
        this.portfolio = (await this.api.request("/api/portfolio")).items;
        this.renderPortfolio();
        $$("[data-project-filter]").forEach((button) => {
          button.onclick = () => {
            $$("[data-project-filter]").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            this.renderPortfolio(button.dataset.projectFilter);
          };
        });
      } catch (error) {
        console.error(error);
      }
    }

    /** Pinta proyectos, opcionalmente filtrados por categoría. */
    renderPortfolio(filter = "") {
      const grid = $("[data-portfolio-grid]");
      if (!grid) return;
      grid.innerHTML = this.portfolio
        .filter((project) => !filter || project.category.toLowerCase() === filter.toLowerCase())
        .map((project) => `
          <a class="portfolio-card" href="proyecto.html?id=${project.id}">
            <div class="portfolio-art"></div>
            <div class="portfolio-card-content">
              <small>${escapeHtml(project.category)} · ${escapeHtml(project.completed_year)}</small>
              <h3>${escapeHtml(project.title)}</h3>
              <p>${escapeHtml(project.summary)}</p>
            </div>
          </a>`).join("");
    }

    /** Carga el detalle del proyecto indicado en el query string. */
    async loadProject() {
      const projectId = new URLSearchParams(location.search).get("id");
      const root = $("[data-project-detail]");
      if (!root) return;
      try {
        const project = await this.api.request(`/api/portfolio/${encodeURIComponent(projectId)}`);
        $("[data-project-title]").textContent = project.title;
        $("[data-project-category]").textContent = project.category;
        $("[data-project-location]").textContent = project.location || "";
        $("[data-project-description]").textContent = project.description || project.summary;
        $("[data-fact-location]").textContent = project.location || "—";
        $("[data-fact-year]").textContent = project.completed_year || "—";
        $("[data-fact-category]").textContent = project.category || "—";
        $("[data-project-quote]").href = `contacto.html?project=${encodeURIComponent(project.title)}`;
      } catch (error) {
        root.innerHTML = `<div class="empty-state"><strong>Proyecto no encontrado.</strong><p>${escapeHtml(error.message)}</p></div>`;
      }
    }

    /** Envía el formulario de cotización y abre su confirmación visual. */
    bindQuoteForm() {
      $("[data-quote-form]")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        const message = $("[data-quote-message]");
        const projectReference = new URLSearchParams(location.search).get("project");
        let bodyMessage = String(data.get("message"));
        if (projectReference) bodyMessage = `Referencia: ${projectReference}\n\n${bodyMessage}`;
        message.textContent = "Enviando…";
        try {
          await this.api.request("/api/quotes", {
            method: "POST",
            body: JSON.stringify({
              name: data.get("name"),
              contact: data.get("contact"),
              project_type: data.get("project_type"),
              message: bodyMessage,
            }),
          });
          message.textContent = "";
          $("[data-quote-success]").classList.add("is-open");
          form.reset();
        } catch (error) {
          message.textContent = error.message;
        }
      });
      $("[data-success-close]")?.addEventListener("click", () => {
        $("[data-quote-success]").classList.remove("is-open");
      });
    }

    // ---------------------------------------------------------------------
    // Autenticación
    // ---------------------------------------------------------------------

    /** Inicializa registro/inicio de sesión y redirige cuentas ya autenticadas. */
    async loadAccount() {
      try {
        const current = await this.api.request("/api/auth/me");
        if (current.authenticated) this.showAuthenticatedUser(current.user);
      } catch (_) {
        // La pantalla de login continúa disponible aunque falle la consulta inicial.
      }

      $$("[data-auth-tab]").forEach((button) => {
        button.onclick = () => {
          $$("[data-auth-tab]").forEach((item) => item.classList.toggle("active", item === button));
          $$("[data-auth-form]").forEach((form) => {
            form.classList.toggle("hidden", form.dataset.authForm !== button.dataset.authTab);
          });
          $("[data-account-state]").classList.add("hidden");
        };
      });

      $$("[data-auth-form]").forEach((form) => {
        form.onsubmit = async (event) => {
          event.preventDefault();
          const type = form.dataset.authForm;
          const data = new FormData(form);
          const message = $(`[data-${type}-message]`);
          const payload = type === "register"
            ? { display_name: data.get("display_name"), email: data.get("email"), password: data.get("password") }
            : { email: data.get("email"), password: data.get("password") };
          try {
            const response = await this.api.request(`/api/auth/${type}`, {
              method: "POST",
              body: JSON.stringify(payload),
            });
            this.showAuthenticatedUser(response.user);
          } catch (error) {
            message.textContent = error.message;
          }
        };
      });

      $("[data-logout]")?.addEventListener("click", async () => {
        await this.api.request("/api/auth/logout", { method: "POST", body: "{}" });
        location.reload();
      });
    }

    /** Redirige por rol o muestra el resumen de una sesión autenticada. */
    showAuthenticatedUser(user) {
      if (user?.role) {
        location.replace(user.role === "admin" ? "/admin/" : "/user/");
        return;
      }
      $$("[data-auth-form]").forEach((form) => form.classList.add("hidden"));
      $(".auth-tabs")?.classList.add("hidden");
      $("[data-account-state]").classList.remove("hidden");
      $("[data-account-name]").textContent = `Hola, ${user.display_name}`;
      $("[data-account-email]").textContent = user.email;
    }

    // ---------------------------------------------------------------------
    // Checkout demo
    // ---------------------------------------------------------------------

    /** Pinta el resumen del carrito dentro de la página de checkout. */
    renderCheckout() {
      const container = $("[data-checkout-items]");
      if (!container) return;
      container.innerHTML = this.cart.items.length
        ? this.cart.items.map((item) => `
            <div class="summary-item">
              <div class="summary-thumb"></div>
              <div><strong>${escapeHtml(item.name)}</strong><div>Cant. ${item.quantity}</div></div>
              <strong>${formatUsd(item.line_total_cents)}</strong>
            </div>`).join("")
        : '<p class="cart-empty">No hay productos en el carrito.</p>';
      $$("[data-summary-subtotal],[data-summary-total]").forEach((node) => {
        node.textContent = formatUsd(this.cart.subtotal_cents);
      });
    }

    /** Envía el checkout de demostración y muestra el pedido confirmado. */
    bindCheckoutForm() {
      $("[data-checkout-form]")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const message = $("[data-checkout-message]");
        if (!this.cart.items.length) {
          message.textContent = "Agrega al menos un producto.";
          return;
        }
        const payload = {
          customer_name: data.get("customer_name"),
          email: data.get("email"),
          phone: data.get("phone"),
          shipping_address: {
            address: data.get("address"),
            city: data.get("city"),
            region: data.get("region"),
            postal_code: data.get("postal_code"),
            country: data.get("country"),
            notes: data.get("notes"),
          },
        };
        try {
          const order = await this.api.request("/api/checkout/mock", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          $("[data-order-id]").textContent = `#${order.public_id}`;
          $("[data-order-total]").textContent = formatUsd(order.total_cents);
          $("[data-order-success]").classList.add("is-open");
          this.cart = { items: [], subtotal_cents: 0 };
          this.renderCart();
        } catch (error) {
          message.textContent = error.status === 401
            ? "Inicia sesión antes de completar la compra."
            : error.message;
          if (error.status === 401) setTimeout(() => { location.href = "cuenta.html"; }, 900);
        }
      });
    }
  }

  new TipsClientApp().init();
})();
