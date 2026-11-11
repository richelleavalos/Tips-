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
  const productImage = product => product?.primary_image
    ? "/" + String(product.primary_image).replace(/^\/+/, "") : "";

  const productVisualAttrs = product => product?.primary_image
    ? 'class="product-placeholder has-real-image"'
    : 'class="product-placeholder"';

  function projectPhotoPath(value) {
    const url = new URL("/" + String(value || "").replace(/^\/+/, ""), location.origin);
    return url.origin === location.origin && url.pathname.startsWith("/assets/") ? url.pathname : "";
  }

  function projectCover(project) {
    const src = projectPhotoPath(project.cover_path);
    return src
      ? `<img src="${escapeHtml(src)}" alt="${escapeHtml(project.cover_alt || project.title)}" loading="lazy" decoding="async">`
      : '<span class="project-no-photo">Imagen no disponible</span>';
  }

  const productPhoto=(product,lazy=true)=>product?.primary_image
    ? `<img class="product-real-image" src="${escapeHtml(productImage(product))}" alt="${escapeHtml(product.primary_image_alt||product.name)}" ${lazy?'loading="lazy"':''} decoding="async">` : "";

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
      if (data.csrf_token) this.csrfToken = data.csrf_token;
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
      this.cartLoaded = false;
      this.cartOpening = false;
    }

    /** Activa comportamientos globales y luego inicializa la vista actual. */
    async init() {
      this.bindNavigation();
      this.bindCartDrawer();
      this.bindProductModal();
      this.bindQuoteForm();
      this.bindCheckoutForm();

      const cartReady=this.loadCart();

      const page = document.body.dataset.page;
      if (page === "home") await this.loadHome();
      if (page === "store") await this.loadStore();
      if (page === "architecture") await this.loadArchitecture();
      if (page === "project") await this.loadProject();
      if (page === "account") await this.loadAccount();
      await cartReady;
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
        this.cartLoaded = true;
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
                <div class="cart-item-thumb">${productImage(item)?`<img src="${escapeHtml(productImage(item))}" alt="${escapeHtml(item.primary_image_alt||item.name)}" width="64" height="72">`:""}</div>
                <div>
                  <h3>${escapeHtml(item.name)}</h3>
                  <small>${escapeHtml(item.option_summary || "Estándar")} · Cant. ${item.quantity}</small>
                  <div>
                    <button aria-label="Reducir cantidad de ${escapeHtml(item.name)}" data-dec="${item.id}">−</button>
                    <button aria-label="Aumentar cantidad de ${escapeHtml(item.name)}" data-inc="${item.id}">+</button>
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

    /** Abre la bolsa de forma estable, visible de inmediato y luego refresca datos. */
    async openCartDrawer() {
      if (!this.cartDrawer) return;
      this.cartDrawer.classList.add("is-open");
      this.cartDrawer.setAttribute("aria-hidden", "false");
      $$('[data-cart-open]').forEach((button) => button.setAttribute("aria-expanded", "true"));
      document.body.classList.add("no-scroll");
      if (this.cartOpening) return;
      this.cartOpening = true;
      this.cartDrawer.classList.add("is-loading");
      const container = $("[data-cart-items]", this.cartDrawer);
      if (!this.cartLoaded && container) {
        container.innerHTML = '<div class="cart-loading" aria-label="Cargando bolsa"><span></span><span></span><span></span></div>';
      }
      try {
        await this.loadCart();
      } finally {
        this.cartOpening = false;
        this.cartDrawer.classList.remove("is-loading");
        $("[data-cart-close]", this.cartDrawer)?.focus();
      }
    }

    /** Abre y cierra el panel lateral de la bolsa desde cualquier página pública. */
    bindCartDrawer() {
      $$('[data-cart-open]').forEach((button) => {
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          void this.openCartDrawer();
        });
      });
      $("[data-cart-close]", this.cartDrawer || document)?.addEventListener("click", () => this.closeCartDrawer());
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
      this.cartDrawer?.classList.remove("is-open", "is-loading");
      this.cartDrawer?.setAttribute("aria-hidden", "true");
      $$('[data-cart-open]').forEach((button) => button.setAttribute("aria-expanded", "false"));
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
              <div class="project-art">${projectCover(project)}</div>
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
              <div ${productVisualAttrs(product)}>${productPhoto(product)}</div>
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
            <div ${productVisualAttrs(product)}>${productPhoto(product)}</div>
            <div class="shop-info">
              <small>${escapeHtml(product.category_name)}</small>
              <h3>${escapeHtml(product.name)}</h3>
              <strong>Desde ${formatUsd(product.base_price_cents)}</strong><span class="client-card-hint">Ver detalles</span>
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
    async openProductModal(productId) {
      this.activeProduct = this.products.find((product) => Number(product.id) === productId);
      if (!this.activeProduct) return;
      $("[data-modal-title]").textContent = this.activeProduct.name;
      $("[data-modal-description]").textContent = this.activeProduct.description;
      $("[data-modal-price]").textContent = `Desde ${formatUsd(this.activeProduct.base_price_cents)}`;
      const modalVisual = $("[data-modal-visual]");
      modalVisual.innerHTML=productPhoto(this.activeProduct,false);
      modalVisual.classList.toggle("has-real-image",Boolean(this.activeProduct.primary_image));
      modalVisual.dataset.tone = productTone(productId);
      $("[data-modal-qty]").value = 1;
      $("[data-modal-message]").textContent = "";
      const layer = $("[data-product-modal]");
      layer.dataset.productId=String(productId);
      layer.classList.add("is-open");
      layer.setAttribute("aria-hidden", "false");
      document.body.classList.add("no-scroll");
      $("[data-modal-close]", layer)?.focus();
      const add=$("[data-modal-add]");add.disabled=true;
      let options=$("[data-modal-options]");
      if(!options){options=document.createElement("div");options.dataset.modalOptions="";add.before(options);}
      options.textContent="Cargando opciones…";
      try {
        const detail=await this.api.request('/api/products/'+productId);
        if(Number(this.activeProduct.id)!==productId)return;
        options.innerHTML=`<label>Variante<select data-modal-variant>${detail.variants.map(v=>`<option value="${v.id}" data-price="${v.price_cents??detail.base_price_cents}">${escapeHtml(v.option_summary||v.sku)} · ${v.stock_quantity===null?'Por encargo':v.stock_quantity+' disponibles'}</option>`).join('')}</select></label>${detail.customizations.map(c=>`<label>${escapeHtml(c.name)}${c.is_required?' *':''}<select data-customization data-required="${c.is_required}"><option value="">Seleccionar</option>${c.values.map(v=>`<option value="${v.id}" data-price="${v.price_delta_cents}">${escapeHtml(v.label)} (${formatUsd(v.price_delta_cents)})</option>`).join('')}</select></label>`).join('')}`;
        const price=()=>{const v=$('[data-modal-variant] option:checked');const extras=$$('[data-customization] option:checked').reduce((sum,o)=>sum+Number(o.dataset.price||0),0);$('[data-modal-price]').textContent=formatUsd(Number(v?.dataset.price||0)+extras);};options.addEventListener('change',price);price();add.disabled=!detail.variants.length;
      }catch(e){options.textContent=e.message;}
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
        const button=$("[data-modal-add]");
        if(button.disabled)return;
        if($$('[data-customization]').some(select=>select.dataset.required==='1'&&!select.value)){message.textContent='Completa las personalizaciones obligatorias.';return;}
        button.disabled=true;
        try {
          this.cart = await this.api.request("/api/cart/items", {
            method: "POST",
            body: JSON.stringify({
              variant_id: Number($("[data-modal-variant]").value),
              quantity: Math.max(1, Math.min(25, Number($("[data-modal-qty]").value))),
              customization_value_ids: $$('[data-customization]').map(s=>Number(s.value)).filter(Boolean),
            }),
          });
          this.renderCart();
          message.textContent = "Agregado al carrito.";
          setTimeout(() => {
            this.closeProductModal();
            void this.openCartDrawer();
          }, 180);
        } catch (error) {
          message.textContent = error.message;
        } finally { button.disabled=false; }
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
          button.onclick = () => (window.TipsMotion?.change || (fn=>fn()))(() => {
            $$("[data-project-filter]").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            this.renderPortfolio(button.dataset.projectFilter);
          });
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
            <div class="portfolio-art">${projectCover(project)}</div>
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
        for(const [selector,id] of [["[data-project-prev]",project.previous_id],["[data-project-next]",project.next_id]]){
          const link=$(selector);if(id){link.href=`/proyecto.html?id=${Number(id)}`;link.hidden=false;}
        }
        const visual=$("[data-project-visual]"),thumbs=$("[data-project-thumbs]");
        const images = Array.isArray(project.images) ? project.images.filter(image => projectPhotoPath(image.path)) : [];
        const show=index=>{
          const picture=images[index];const image=document.createElement("img");image.src=projectPhotoPath(picture.path);image.alt=picture.alt_text||project.title;visual.replaceChildren(image);
          const caption = $("[data-project-image-caption]");
          caption.hidden = !image.src.includes("/assets/portfolio/");
          [...thumbs.children].forEach((button,i)=>{button.classList.toggle("active",i===index);button.setAttribute("aria-pressed",String(i===index));});
        };
        if(images.length){
          for(const [index,picture] of images.entries()){
            const button=document.createElement("button");button.type="button";button.setAttribute("aria-label",`Ver foto ${index+1}: ${picture.alt_text||project.title}`);
            const image=document.createElement("img");image.src=projectPhotoPath(picture.path);image.alt="";button.append(image);
            button.onclick=()=>(window.TipsMotion?.change||(fn=>fn()))(()=>show(index));thumbs.append(button);
          }
          thumbs.hidden=images.length<2;show(0);
        }
      } catch (error) {
        root.innerHTML = `<div class="empty-state"><strong>Proyecto no encontrado.</strong><p>${escapeHtml(error.message)}</p></div>`;
      }
    }

    /** Envía el formulario de cotización y abre su confirmación visual. */
    bindQuoteForm() {
      // Formulario de diseño gestionado por design-form.js (borradores y cargas reanudables).
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

      const query = new URLSearchParams(location.search);
      const resumeCheckout = query.get("next") === "/checkout.html";
      const showMode = mode => {
        const registering = mode === "register";
        document.body.dataset.authMode = mode;
        $("[data-auth-eyebrow]").textContent = registering ? "Tu cuenta TIPS" : "Bienvenido de nuevo";
        $("[data-auth-heading]").textContent = registering ? "Crea tu cuenta" : "Inicia sesión";
        $("[data-auth-lead]").textContent = resumeCheckout
          ? "Tu borrador está guardado. Después podrás revisarlo y confirmar el pedido."
          : registering ? "Guarda y consulta tus pedidos desde tu cuenta." : "Accede a tus pedidos y solicitudes de diseño.";
        $$("[data-auth-tab]").forEach(button => {
          const selected = button.dataset.authTab === mode;
          button.classList.toggle("active", selected);
          button.setAttribute("aria-pressed", String(selected));
        });
        $$("[data-auth-form]").forEach(form => form.classList.toggle("hidden", form.dataset.authForm !== mode));
      };
      showMode("login");
      $$("[data-auth-tab]").forEach(button => {
        button.onclick = () => (window.TipsMotion?.change || (update => update()))(() => showMode(button.dataset.authTab));
      });
      if (resumeCheckout) {
        this.api.request("/api/checkout/draft").then(({draft}) => {
          const login = $('[data-auth-form="login"]');
          const register = $('[data-auth-form="register"]');
          for (const [field, value] of Object.entries({
            display_name: draft.customer_name, email: draft.email, phone: draft.phone, country_code: draft.country_code
          })) {
            if (value && (field === "country_code" || !register.elements[field].value)) register.elements[field].value = value;
          }
          if (draft.email && !login.elements.email.value) login.elements.email.value = draft.email;
          if (draft.phone) register.elements.phone.dispatchEvent(new Event("input"));
        }).catch(() => {});
      }

      $$("[data-auth-form]").forEach((form) => {
        form.onsubmit = async (event) => {
          event.preventDefault();
          const type = form.dataset.authForm;
          const data = new FormData(form);
          const message = $(`[data-${type}-message]`);
          const payload = type === "register"
            ? { display_name: data.get("display_name"), email: data.get("email"), password: data.get("password"), phone: data.get("phone"), country_code: data.get("country_code") }
            : { email: data.get("email"), password: data.get("password") };
          try {
            const response = await this.api.request(`/api/auth/${type}`, {
              method: "POST",
              body: JSON.stringify(payload),
            });
            if (response.two_factor_required) {
              form.classList.add("hidden");
              $(".auth-tabs")?.classList.add("hidden");
              const twoFactorForm = $("[data-auth-2fa]");
              twoFactorForm.classList.remove("hidden");
              twoFactorForm.dataset.challengeToken = response.challenge_token;
              $("[name=code]", twoFactorForm)?.focus();
              return;
            }
            this.showAuthenticatedUser(response.user);
          } catch (error) {
            message.textContent = error.message;
          }
        };
      });

      $("[data-auth-2fa]")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const message = $("[data-2fa-login-message]");
        try {
          const response = await this.api.request("/api/auth/2fa/verify-login", {
            method: "POST",
            body: JSON.stringify({
              challenge_token: form.dataset.challengeToken || "",
              code: String(new FormData(form).get("code") || "").replace(/\s/g, ""),
            }),
          });
          this.showAuthenticatedUser(response.user);
        } catch (error) {
          message.textContent = error.message;
        }
      });

      $("[data-logout]")?.addEventListener("click", async () => {
        await this.api.request("/api/auth/logout", { method: "POST", body: "{}" });
        location.reload();
      });
    }

    /** Redirige por rol o muestra el resumen de una sesión autenticada. */
    showAuthenticatedUser(user) {
      if (user?.role) {
        const resume = user.role === "user" && new URLSearchParams(location.search).get("next") === "/checkout.html";
        if (user.must_change_password) {
          location.replace(resume ? "/change-password.html?next=%2Fcheckout.html" : "/change-password.html");
          return;
        }
        location.replace(resume ? "/checkout.html" : ["admin", "superadmin"].includes(user.role) ? "/admin/" : "/user/");
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
              <div class="summary-thumb">${productImage(item)?`<img src="${escapeHtml(productImage(item))}" alt="${escapeHtml(item.primary_image_alt||item.name)}" width="60" height="60">`:""}</div>
              <div><strong>${escapeHtml(item.name)}</strong><div>Cant. ${item.quantity}</div></div>
              <strong>${formatUsd(item.line_total_cents)}</strong>
            </div>`).join("")
        : '<div class="cart-empty"><p>No hay productos en el carrito.</p><a class="btn ghost" href="/tienda.html">Explorar productos →</a></div>';
      const submit=$("[data-checkout-form] [type=submit]");
      if(submit) submit.disabled = !this.cart.items.length || submit.form.dataset.ready !== "true";
      $$("[data-summary-subtotal],[data-summary-total]").forEach((node) => {
        node.textContent = formatUsd(this.cart.subtotal_cents);
      });
    }

    /** Envía el checkout de demostración y muestra el pedido confirmado. */
    bindCheckoutForm() {
      const form = $("[data-checkout-form]");
      if (!form) return;
      let key = sessionStorage.getItem("tips-order-key") || crypto.randomUUID();
      sessionStorage.setItem("tips-order-key", key);
      const button = form.querySelector('[type="submit"]');
      const message = $("[data-checkout-message]");
      let customer = false;
      let ready = false;
      Promise.all([
        this.api.request("/api/auth/me"),
        this.api.request("/api/checkout/draft"),
      ]).then(async ([auth, {draft}]) => {
        customer = auth.user?.role === "user";
        let fields = draft;
        if (draft.idempotency_key) {
          key = draft.idempotency_key;
          sessionStorage.setItem("tips-order-key", key);
          message.textContent = "Borrador recuperado. Revisa los datos antes de confirmar.";
        } else if (customer) {
          const {user} = await this.api.request("/api/account");
          fields = {customer_name: user.display_name, email: user.email, country_code: user.country_code, phone: user.phone};
        }
        for (const [name, value] of Object.entries(fields)) {
          if (form.elements[name] && value) form.elements[name].value = value;
        }
        form.elements.phone.dispatchEvent(new Event("input"));
        button.textContent = customer ? "Confirmar solicitud →" : "Guardar y continuar →";
        ready = true;
        form.dataset.ready = "true";
        this.renderCheckout();
      }).catch(() => { message.textContent = "No pudimos cargar el pedido. Recarga la página para continuar."; });
      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!ready || button.disabled) return;
        const data = new FormData(form);
        const payload = Object.fromEntries(data);
        payload.idempotency_key = key;
        button.disabled = true;
        message.textContent = "Guardando tu solicitud…";
        try {
          if (!customer) {
            await this.api.request("/api/checkout/draft", {method:"POST",body:JSON.stringify(payload)});
            location.assign("/cuenta.html?next=%2Fcheckout.html");
            return;
          }
          const order = await this.api.request("/api/checkout/create", {method:"POST",body:JSON.stringify(payload)});
          $("[data-order-id]").textContent = order.public_id;
          $("[data-order-total]").textContent = formatUsd(order.total_cents);
          const link = $("[data-tracking-link]");
          link.href = order.tracking_url;
          $("[data-order-success]").classList.add("is-open");
          $("[data-order-success]").setAttribute("aria-hidden","false");
          this.cart = {items:[],subtotal_cents:0}; this.renderCart();
          sessionStorage.removeItem("tips-order-key");
          message.textContent = "Pedido guardado correctamente.";
          form.reset();
        } catch (error) { message.textContent = error.message; button.disabled=false; }
      });
    }
  }

  new TipsClientApp().init();
})();
