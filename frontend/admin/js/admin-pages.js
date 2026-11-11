/**
 * Código de la experiencia administrativa: admin pages. Mantiene esta responsabilidad aislada del frontend de cliente.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const A = window.TipsAdmin;
  if (!A) return;
  const { $, $$, esc, usd, api, toast, modal, setPageTitle, loadAlerts, showAuth, setIdentity } = A;
  const page = document.body.dataset.adminPage || "dashboard";
  const titles = {
    dashboard: ["Resumen", "Lo importante del negocio en un solo lugar."],
    productos: ["Productos", "Catálogo, precios, inventario e imágenes."],
    proyectos: ["Proyectos", "Portafolio de arquitectura y publicación."],
    pedidos: ["Pedidos", "Seguimiento de compras y estados."],
    cotizaciones: ["Cotizaciones", "Solicitudes de arquitectura y seguimiento."],
    clientes: ["Clientes", "Personas registradas y actividad de compra."],
    promociones: ["Promociones", "Descuentos y códigos promocionales."],
    usuarios: ["Usuarios", "Accesos, roles y estado de las cuentas."],
    configuracion: ["Configuración", "Contenido público, identidad y datos de contacto."],
  };

  function content() { return $("[data-page-content]"); }
  function actions() { return $("[data-page-actions]"); }
  function asInt(value, fallback = 0) { const n = Number(value); return Number.isFinite(n) ? Math.round(n) : fallback; }
  function statusLabel(value) {
    const labels = { available: "Disponible", low: "Bajo", out: "Agotado", made_to_order: "Bajo pedido", pending: "Pendiente", pending_payment: "Pendiente de pago", payment_failed: "Pago fallido", expired: "Expirado", paid: "Pagado", processing: "Preparando", ready: "Listo", shipped: "Enviado", completed: "Completado", cancelled: "Cancelado", refunded: "Reembolsado", new: "Nueva", contacted: "Contactada", qualified: "Calificada", closed: "Cerrada", archived: "Archivada" };
    return labels[value] || value;
  }

  /**
   * Renderiza el dashboard editorial con datos reales del negocio.
   * No inventa tendencias: métricas, stock y actividad provienen de la API.
   */
  async function dashboard(overview) {
    const d = overview || await api("/api/admin/overview");
    setIdentity(d.user);

    const orders = d.orders || [];
    const products = d.products || [];
    const lowStock = products
      .filter(product => product.stock_quantity !== null && Number(product.stock_quantity) <= 5)
      .sort((a, b) => Number(a.stock_quantity) - Number(b.stock_quantity))
      .slice(0, 5);

    const categoryCounts = new Map();
    products.forEach(product => {
      const name = product.category_name || "Otros";
      categoryCounts.set(name, (categoryCounts.get(name) || 0) + 1);
    });
    const categories = [...categoryCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    const totalCategoryProducts = categories.reduce((sum, [, count]) => sum + count, 0) || 1;

    const palette = ["#143528", "#8a6a52", "#9c9b8e", "#c8c1ad", "#eadfc8"];
    let accumulated = 0;
    const donutStops = categories.map(([, count], index) => {
      const from = accumulated;
      accumulated += (count / totalCategoryProducts) * 100;
      return `${palette[index]} ${from.toFixed(1)}% ${accumulated.toFixed(1)}%`;
    }).join(", ") || "#ded9cb 0 100%";

    const salesByDate = new Map();
    orders.forEach(order => {
      const date = String(order.created_at || "").slice(0, 10);
      if (!date) return;
      salesByDate.set(date, (salesByDate.get(date) || 0) + Number(order.total_cents || 0));
    });
    const salesValues = [...salesByDate.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-14);
    const maxSales = Math.max(...salesValues.map(([, value]) => value), 1);
    const chartBars = salesValues.length
      ? salesValues.map(([date, value]) => `<span class="admin-chart-bar" style="--bar:${Math.max(8, Math.round((value / maxSales) * 100))}%" title="${esc(date)} · ${usd(value)}"></span>`).join("")
      : Array.from({ length: 14 }, (_, index) => `<span class="admin-chart-bar is-empty" style="--bar:${8 + (index % 4) * 3}%"></span>`).join("");

    const recentOrders = orders.slice(0, 5).map(order => `
      <tr>
        <td><strong>${esc(order.public_id)}</strong></td>
        <td>${esc(order.customer_name || "Cliente")}</td>
        <td>${esc(String(order.created_at || "").replace("T", " ").slice(0, 16) || "—")}</td>
        <td>${usd(order.total_cents)}</td>
        <td><span class="admin-chip status-${esc(order.status)}">${esc(statusLabel(order.status))}</span></td>
        <td><a class="admin-row-arrow" href="pedidos.html" aria-label="Ver pedidos">→</a></td>
      </tr>`).join("") || '<tr><td colspan="6"><div class="admin-table-empty">Todavía no hay pedidos. Cuando llegue el primero aparecerá aquí.</div></td></tr>';

    const lowStockRows = lowStock.map(product => `
      <tr>
        <td><div class="admin-product-cell"><span class="admin-thumb admin-thumb-placeholder">${esc((product.name || "P").charAt(0))}</span><strong>${esc(product.name)}</strong></div></td>
        <td>${product.stock_quantity ?? "—"}</td>
        <td><span class="admin-chip warn">Bajo stock</span></td>
        <td><a class="admin-row-arrow" href="inventario.html" aria-label="Revisar inventario">→</a></td>
      </tr>`).join("") || '<tr><td colspan="4"><div class="admin-table-empty">No hay productos con stock crítico.</div></td></tr>';

    content().innerHTML = `
      <section class="admin-dashboard-hero">
        <div class="admin-dashboard-hero-copy">
          <p class="admin-kicker">BUENOS DÍAS</p>
          <h1>Todo en orden<br>para seguir creando<br>espacios <em>únicos.</em></h1>
          <p>Aquí tienes un resumen de lo más importante en TIPS.</p>
        </div>
        <div class="admin-dashboard-hero-image" role="img" aria-label="Interior cálido con objetos de diseño">
          <span>Buenas ideas<br>también se gestionan<br>con calma.</span>
        </div>
      </section>

      <section class="admin-grid-metrics admin-dashboard-metrics" aria-label="Resumen del negocio">
        <article class="admin-metric"><span class="admin-metric-icon">$</span><div><strong>${usd(d.metrics.sales_cents)}</strong><span>Ventas registradas</span><small>Órdenes válidas acumuladas</small></div></article>
        <article class="admin-metric"><span class="admin-metric-icon">□</span><div><strong>${d.metrics.orders}</strong><span>Pedidos</span><small>Histórico del sistema</small></div></article>
        <article class="admin-metric"><span class="admin-metric-icon">○</span><div><strong>${d.metrics.users ?? 0}</strong><span>Usuarios activos</span><small>Cuentas habilitadas</small></div></article>
        <article class="admin-metric admin-metric-attention"><span class="admin-metric-icon">△</span><div><strong>${lowStock.length}</strong><span>Productos con bajo stock</span><small><a href="inventario.html">Revisar ahora →</a></small></div></article>
      </section>

      <section class="admin-dashboard-grid">
        <article class="admin-card admin-dashboard-orders">
          <div class="admin-card-head"><div><h2>Pedidos recientes</h2></div><a class="admin-text-link" href="pedidos.html">Ver todos →</a></div>
          <div class="admin-table-wrap admin-table-seamless"><table class="admin-table"><thead><tr><th>#</th><th>Cliente</th><th>Fecha</th><th>Total</th><th>Estado</th><th></th></tr></thead><tbody>${recentOrders}</tbody></table></div>
        </article>

        <article class="admin-card admin-dashboard-stock">
          <div class="admin-card-head"><div><h2>Productos con bajo stock</h2></div><a class="admin-text-link" href="inventario.html">Ver todos →</a></div>
          <div class="admin-table-wrap admin-table-seamless"><table class="admin-table"><thead><tr><th>Producto</th><th>Stock</th><th>Estado</th><th></th></tr></thead><tbody>${lowStockRows}</tbody></table></div>
        </article>

        <article class="admin-card admin-dashboard-chart">
          <div class="admin-card-head"><div><h2>Ventas recientes</h2><p>${salesValues.length ? "Actividad registrada en pedidos recientes." : "Aún no hay ventas registradas."}</p></div></div>
          <div class="admin-bar-chart" aria-label="Gráfico de ventas recientes">${chartBars}</div>
          <div class="admin-chart-axis"><span>Anterior</span><span>Actual</span></div>
        </article>

        <article class="admin-card admin-dashboard-categories">
          <div class="admin-card-head"><div><h2>Catálogo por categoría</h2><p>Distribución actual de productos.</p></div></div>
          <div class="admin-category-layout">
            <div class="admin-donut" style="--donut:${donutStops}" aria-hidden="true"><span></span></div>
            <div class="admin-category-legend">${categories.map(([name, count], index) => `<div><i style="--legend:${palette[index]}"></i><span>${esc(name)}</span><strong>${Math.round((count / totalCategoryProducts) * 100)}%</strong></div>`).join("") || '<small>Sin categorías todavía.</small>'}</div>
          </div>
        </article>

        <article class="admin-editorial-card">
          <img src="/assets/images/admin-detail.jpg" alt="Detalle de mobiliario TIPS">
        </article>
      </section>`;
  }

  function mediaPath(path) {
    if (!path) return "";
    const value = String(path);
    return value.startsWith("/") ? value : `/${value.replace(/^\.\//, "")}`;
  }

  function clickableRow(attrs = "") {
    return `class="admin-row-clickable" tabindex="0" role="button" ${attrs}`;
  }

  function activateRows(selector, handler) {
    $$(selector).forEach(row => {
      const activate = event => {
        if (event.type === "keydown" && !["Enter", " "].includes(event.key)) return;
        if (event.target.closest("a,button,input,select,textarea,label")) return;
        if (event.type === "keydown") event.preventDefault();
        handler(row, event);
      };
      row.addEventListener("click", activate);
      row.addEventListener("keydown", activate);
    });
  }

  function listPanel(toolbar, table) {
    return `<section class="admin-list-panel">${toolbar || ""}${table}</section>`;
  }

  async function products() {
    const [data, categories] = await Promise.all([api("/api/admin/products"), api("/api/categories")]);
    setIdentity(data.user);
    actions().innerHTML = `<button class="admin-btn primary" type="button" data-new-product>+ Nuevo producto</button>`;
    content().innerHTML = listPanel(
      `<div class="admin-toolbar"><label class="admin-search"><input type="search" data-product-search placeholder="Buscar por nombre, categoría o SKU" aria-label="Buscar producto"></label><span class="admin-list-count">${data.items.length} productos</span></div>`,
      `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Producto</th><th>Categoría</th><th>Precio</th><th>Stock</th><th>Fotos</th><th>Estado</th><th aria-label="Abrir"></th></tr></thead><tbody data-products-body></tbody></table></div>`
    );

    const openProduct = product => editProduct(product, categories.items, data);
    const draw = () => {
      const q = $("[data-product-search]").value.trim().toLowerCase();
      const list = data.items.filter(p => !q || `${p.name} ${p.category_name || ""} ${p.sku || ""}`.toLowerCase().includes(q));
      $("[data-products-body]").innerHTML = list.map(p => `
        <tr ${clickableRow(`data-product-row="${p.id}" aria-label="Abrir ${esc(p.name)}"`)}>
          <td><div class="admin-product-cell">${p.primary_image ? `<img class="admin-thumb" src="${esc(mediaPath(p.primary_image))}" alt="">` : `<div class="admin-thumb admin-thumb-placeholder">${esc((p.name || "P").charAt(0))}</div>`}<div><strong>${esc(p.name)}</strong><small>${esc(p.sku || p.slug)}</small></div></div></td>
          <td>${esc(p.category_name || "Sin categoría")}</td>
          <td>${usd(p.base_price_cents)}</td>
          <td>${p.stock_quantity ?? "—"}</td>
          <td>${p.image_count || 0}/5</td>
          <td><span class="admin-chip ${p.is_active ? "" : "off"}">${p.is_active ? esc(statusLabel(p.stock_status)) : "Oculto"}</span></td>
          <td></td>
        </tr>`).join("") || '<tr><td colspan="7"><div class="admin-empty"><strong>Sin coincidencias</strong>Prueba con otro nombre, categoría o SKU.</div></td></tr>';
      activateRows("[data-product-row]", row => openProduct(data.items.find(p => p.id === +row.dataset.productRow)));
    };

    const params = new URLSearchParams(location.search);
    $("[data-product-search]").value = params.get("search") || "";
    $("[data-product-search]").oninput = draw;
    $("[data-new-product]").onclick = () => newProduct(categories.items);
    draw();

    const productId = Number(params.get("product"));
    if (Number.isInteger(productId) && productId > 0) {
      const product = data.items.find(p => p.id === productId);
      if (product) setTimeout(() => openProduct(product), 50);
    }
  }

  function productFields(p, categories) {
    return `<div class="admin-form-grid">
      <div class="admin-field full"><span>Nombre</span><input name="name" required maxlength="180" value="${esc(p?.name || "")}" placeholder="Nombre del producto"></div>
      <div class="admin-field"><span>Categoría</span><select name="category_id"><option value="">Sin categoría</option>${categories.map(c => `<option value="${c.id}" ${p?.category_id === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
      <div class="admin-field"><span>Precio USD</span><input name="price" type="number" min="0" step="0.01" value="${p ? (p.base_price_cents / 100).toFixed(2) : "0.00"}"></div>
      <div class="admin-field"><span>Inventario</span><input name="stock" type="number" min="0" step="1" value="${p?.stock_quantity ?? 0}"></div>
      <div class="admin-field"><span>Estado de stock</span><select name="stock_status"><option value="available">Disponible</option><option value="low">Bajo</option><option value="out">Agotado</option><option value="made_to_order">Bajo pedido</option></select></div>
      <div class="admin-field full"><span>Descripción</span><textarea name="description" maxlength="5000" placeholder="Describe materiales, medidas, acabados o características relevantes.">${esc(p?.description || "")}</textarea></div>
      ${p ? `<div class="admin-field full"><label class="admin-check-row"><input type="checkbox" name="is_active" ${p.is_active ? "checked" : ""}> Visible en la tienda</label></div>` : ""}
    </div>`;
  }

  function editProduct(product, categories) {
    const m = modal(`<form data-product-form>${productFields(product, categories)}<div class="admin-form-actions"><button class="admin-btn" type="button" data-product-images>Gestionar fotos</button><button class="admin-btn primary" type="submit">Guardar cambios</button></div></form>`, product.name);
    const form = $("[data-product-form]", m.body);
    form.elements.stock_status.value = product.stock_status;
    $("[data-product-images]", m.body).onclick = () => imageManager(product.id);
    form.onsubmit = async event => {
      event.preventDefault();
      const f = new FormData(form);
      try {
        await api("/api/admin/products/update", { method: "POST", body: JSON.stringify({
          id: product.id,
          name: f.get("name"),
          category_id: f.get("category_id") ? +f.get("category_id") : null,
          description: f.get("description"),
          base_price_cents: Math.round(Number(f.get("price")) * 100),
          stock_quantity: asInt(f.get("stock")),
          stock_status: f.get("stock_status"),
          is_active: form.elements.is_active.checked,
        }) });
        toast("Producto actualizado.");
        m.close();
        products();
      } catch (e) { toast(e.message, "error"); }
    };
  }

  function newProduct(categories) {
    const m = modal(`<form data-product-form>${productFields(null, categories)}<div class="admin-form-actions"><button class="admin-btn" type="button" data-cancel>Cancelar</button><button class="admin-btn primary" type="submit">Crear producto</button></div></form>`, "Nuevo producto");
    const form = $("[data-product-form]", m.body);
    $("[data-cancel]", m.body).onclick = m.close;
    form.onsubmit = async event => {
      event.preventDefault();
      const f = new FormData(form);
      try {
        const result = await api("/api/admin/products/create", { method: "POST", body: JSON.stringify({
          name: f.get("name"),
          category_id: f.get("category_id") ? +f.get("category_id") : null,
          description: f.get("description"),
          base_price_cents: Math.round(Number(f.get("price")) * 100),
          stock_quantity: asInt(f.get("stock")),
          stock_status: f.get("stock_status"),
        }) });
        toast("Producto creado. Puedes agregar sus fotos ahora.");
        m.close();
        await products();
        setTimeout(() => imageManager(result.id), 120);
      } catch (e) { toast(e.message, "error"); }
    };
  }

  function fileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("No pudimos leer la imagen seleccionada."));
      reader.readAsDataURL(file);
    });
  }

  async function compressImage(file) {
    if (!file || !/^image\/(jpeg|png|webp)$/i.test(file.type)) throw new Error("Selecciona una imagen JPG, PNG o WebP.");
    const dataUrl = await fileAsDataUrl(file);
    const image = await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Safari no pudo abrir esta imagen. Prueba con JPG, PNG o WebP."));
      img.src = dataUrl;
    });
    const maxSide = 1600;
    const scale = Math.min(1, maxSide / Math.max(image.naturalWidth || 1, image.naturalHeight || 1));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) throw new Error("Tu navegador no pudo preparar la imagen.");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    let quality = .86;
    let blob = null;
    while (quality >= .42) {
      blob = await new Promise(resolve => canvas.toBlob(resolve, "image/webp", quality));
      if (blob && blob.size <= 600000) break;
      quality -= .08;
    }
    if (!blob || blob.size > 600000) throw new Error("La foto es demasiado pesada para optimizarla automáticamente.");
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
      reader.onerror = () => reject(new Error("No pudimos preparar la imagen para subirla."));
      reader.readAsDataURL(blob);
    });
  }

  async function imageManager(productId) {
    try {
      const data = await api(`/api/admin/products/images?product_id=${productId}`);
      const m = modal(`
        <div class="image-upload" data-image-drop>
          <input id="product-image-file" type="file" accept="image/jpeg,image/png,image/webp" multiple>
          <label for="product-image-file">
            <span class="image-upload-icon">+</span>
            <strong>Agregar fotografías</strong>
            <small>Haz clic o arrastra aquí JPG, PNG o WebP. TIPS las optimiza automáticamente. Máximo 5 fotos por producto.</small>
          </label>
          <div class="image-upload-progress" data-image-progress aria-live="polite"></div>
        </div>
        <div class="image-manager-grid" data-images-grid></div>`,
        `Fotos · ${data.product.name}`,
        true
      );

      const grid = $("[data-images-grid]", m.body);
      const progress = $("[data-image-progress]", m.body);
      const input = $("#product-image-file", m.body);
      const drop = $("[data-image-drop]", m.body);

      const refresh = async () => {
        const fresh = await api(`/api/admin/products/images?product_id=${productId}`);
        data.items = fresh.items;
        drawImages();
      };

      const drawImages = () => {
        grid.innerHTML = data.items.map((img, index) => `
          <article class="image-item">
            <div class="image-item-media">
              ${index === 0 ? '<span class="admin-chip image-primary-badge">Principal</span>' : ""}
              <img src="${esc(mediaPath(img.path))}" alt="${esc(img.alt_text || data.product.name)}">
            </div>
            <div class="image-item-fields">
              <div class="admin-field"><span>Texto alternativo</span><input value="${esc(img.alt_text || data.product.name)}" data-alt="${img.id}" maxlength="180"></div>
              <button class="admin-btn small" type="button" data-save-image="${img.id}">Guardar texto</button><div class="image-item-row"><span class="image-position-note">Foto ${index + 1} de ${data.items.length}</span><button class="admin-btn small danger" type="button" data-delete-image="${img.id}">Eliminar</button></div>
            </div>
          </article>`).join("") || '<div class="admin-empty"><strong>Aún no hay fotografías</strong>Agrega la primera foto del producto desde el área superior.</div>';

        $$('[data-alt]', m.body).forEach(field => {
          field.addEventListener("change", async () => {
            const id = +field.dataset.alt;
            const image = data.items.find(item => item.id === id);
            if (!image) return;
            try {
              await api("/api/admin/products/images/update", { method: "POST", body: JSON.stringify({ id, alt_text: field.value.trim(), sort_order: image.sort_order }) });
              toast("Texto de la foto actualizado.");
            } catch (e) { toast(e.message, "error"); }
          });
        });
        $$('[data-save-image]', m.body).forEach(button=>button.onclick=async()=>{
          const id=Number(button.dataset.saveImage),field=$('[data-alt="'+id+'"]',m.body),image=data.items.find(item=>item.id===id);
          button.disabled=true;
          try{await api('/api/admin/products/images/update',{method:'POST',body:JSON.stringify({id,alt_text:field.value.trim(),sort_order:image.sort_order})});image.alt_text=field.value.trim();field.closest('.image-item').querySelector('img')?.setAttribute('alt',field.value.trim());toast('Texto de la foto actualizado.');button.textContent='Guardado';}
          catch(error){toast(error.message,'error');}finally{button.disabled=false;}
        });
        $$('[data-delete-image]', m.body).forEach(button => button.onclick = async () => {
          if (!confirm("¿Eliminar esta fotografía?")) return;
          button.disabled = true;
          try {
            await api("/api/admin/products/images/delete", { method: "POST", body: JSON.stringify({ id: +button.dataset.deleteImage }) });
            toast("Fotografía eliminada.");
            await refresh();
          } catch (e) { toast(e.message, "error"); button.disabled = false; }
        });
      };

      const uploadFiles = async fileList => {
        const files = [...fileList].filter(Boolean);
        if (!files.length) return;
        const remaining = data.max_images - data.items.length;
        if (remaining <= 0) { toast("Este producto ya tiene 5 fotografías.", "error"); return; }
        const selected = files.slice(0, remaining);
        if (files.length > remaining) toast(`Solo se agregarán ${remaining} foto${remaining === 1 ? "" : "s"}.`, "error");
        input.disabled = true;
        for (let index = 0; index < selected.length; index += 1) {
          const file = selected[index];
          progress.textContent = `Preparando ${index + 1} de ${selected.length}: ${file.name}`;
          try {
            const encoded = await compressImage(file);
            await api("/api/admin/products/images/add", { method: "POST", body: JSON.stringify({ product_id: productId, alt_text: data.product.name, data_base64: encoded }) });
            await refresh();
          } catch (e) {
            toast(`${file.name}: ${e.message}`, "error");
          }
        }
        progress.textContent = "";
        input.value = "";
        input.disabled = false;
        toast("Fotografías actualizadas.");
      };

      input.onchange = event => uploadFiles(event.target.files || []);
      ["dragenter", "dragover"].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.add("is-dragging"); }));
      ["dragleave", "drop"].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.remove("is-dragging"); }));
      drop.addEventListener("drop", event => uploadFiles(event.dataTransfer?.files || []));
      drawImages();
    } catch (e) { toast(e.message, "error"); }
  }

  async function projects() {
    const data = await api("/api/admin/projects");
    setIdentity(data.user);
    content().innerHTML = listPanel(
      `<div class="admin-toolbar"><label class="admin-search"><input data-project-search placeholder="Buscar proyecto" aria-label="Buscar proyecto"></label><span>${data.items.length} proyectos</span></div>`,
      `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Proyecto</th><th>Categoría</th><th>Ubicación</th><th>Año</th><th>Publicación</th><th aria-label="Abrir"></th></tr></thead><tbody data-projects-body></tbody></table></div>`
    );
    const draw = () => {
      const q = $("[data-project-search]").value.toLowerCase();
      const list = data.items.filter(p => !q || `${p.title} ${p.category} ${p.location || ""}`.toLowerCase().includes(q));
      $("[data-projects-body]").innerHTML = list.map(p => `<tr ${clickableRow(`data-project-row="${p.id}" aria-label="Abrir ${esc(p.title)}"`)}><td><strong>${esc(p.title)}</strong><br><small>${esc(p.summary)}</small></td><td>${esc(p.category)}</td><td>${esc(p.location || "—")}</td><td>${p.completed_year || "—"}</td><td><span class="admin-chip ${p.is_published ? "" : "off"}">${p.is_published ? "Publicado" : "Oculto"}</span></td><td></td></tr>`).join("") || '<tr><td colspan="6"><div class="admin-empty">Sin proyectos.</div></td></tr>';
      activateRows("[data-project-row]", row => editProject(data.items.find(p => p.id === +row.dataset.projectRow)));
    };
    $("[data-project-search]").oninput = draw;
    draw();
  }

  function editProject(p) {
    const m = modal(`<form data-project-form><div class="admin-form-grid"><div class="admin-field full"><span>Título</span><input name="title" value="${esc(p.title)}"></div><div class="admin-field"><span>Categoría</span><input name="category" value="${esc(p.category)}"></div><div class="admin-field"><span>Ubicación</span><input name="location" value="${esc(p.location || "")}"></div><div class="admin-field"><span>Año</span><input type="number" name="year" value="${p.completed_year || ""}"></div><div class="admin-field"><label class="admin-check-row"><input type="checkbox" name="published" ${p.is_published ? "checked" : ""}> Publicado en el sitio</label></div><div class="admin-field full"><span>Resumen</span><textarea name="summary">${esc(p.summary)}</textarea></div><div class="admin-field full"><span>Descripción</span><textarea name="description">${esc(p.description)}</textarea></div></div><div class="admin-form-actions"><button class="admin-btn" type="button" data-cancel>Cancelar</button><button class="admin-btn primary">Guardar cambios</button></div></form>`, p.title);
    const form = $("[data-project-form]", m.body);
    $("[data-cancel]", m.body).onclick = m.close;
    form.onsubmit = async e => {
      e.preventDefault();
      const f = new FormData(form);
      try {
        await api("/api/admin/projects/update", { method: "POST", body: JSON.stringify({ id: p.id, title: f.get("title"), category: f.get("category"), location: f.get("location"), completed_year: f.get("year") ? +f.get("year") : null, summary: f.get("summary"), description: f.get("description"), is_published: form.elements.published.checked }) });
        toast("Proyecto actualizado."); m.close(); projects();
      } catch (x) { toast(x.message, "error"); }
    };
  }

  async function orders() {
    const data = await api("/api/admin/orders");
    setIdentity(data.user);
    content().innerHTML = listPanel("", `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Pedido</th><th>Cliente</th><th>Contacto</th><th>Total</th><th>Estado</th><th aria-label="Abrir"></th></tr></thead><tbody>${data.items.map(o => `<tr ${clickableRow(`data-order-row="${o.id}" aria-label="Abrir pedido ${esc(o.public_id)}"`)}><td><strong>${esc(o.public_id)}</strong><br><small>${esc(String(o.created_at || "").replace("T", " ").slice(0,16))}</small></td><td>${esc(o.customer_name)}</td><td>${esc(o.email || "")}<br><small>${esc(o.phone || "")}</small></td><td>${usd(o.total_cents)}</td><td><span class="admin-chip status-${esc(o.status)}">${esc(statusLabel(o.status))}</span></td><td></td></tr>`).join("") || '<tr><td colspan="6"><div class="admin-empty">Sin pedidos.</div></td></tr>'}</tbody></table></div>`);
    activateRows("[data-order-row]", row => editOrder(data.items.find(o => o.id === +row.dataset.orderRow)));
    const id = Number(new URLSearchParams(location.search).get("order"));
    if (id) { const order = data.items.find(o => o.id === id); if (order) setTimeout(() => editOrder(order), 40); }
  }

  function editOrder(o) {
    const m = modal(`<div class="admin-role-note"><strong>${esc(o.customer_name || "Cliente")}</strong><br>${esc(o.email || "")}${o.phone ? ` · ${esc(o.phone)}` : ""}<br><small>Total ${usd(o.total_cents)} · ${esc(o.public_id)}</small></div><form data-order-form style="margin-top:18px"><div class="admin-form-grid"><div class="admin-field full"><span>Estado del pedido</span><select name="status">${["pending_payment","paid","payment_failed","processing","ready","shipped","completed","cancelled","expired","refunded"].map(s => `<option value="${s}" ${o.status === s ? "selected" : ""}>${statusLabel(s)}</option>`).join("")}</select></div></div><div class="admin-form-actions"><button class="admin-btn primary">Guardar estado</button></div></form>`, `Pedido ${o.public_id}`);
    $("[data-order-form]", m.body).onsubmit = async e => {
      e.preventDefault();
      try { await api("/api/admin/orders/update", { method: "POST", body: JSON.stringify({ id: o.id, status: new FormData(e.currentTarget).get("status") }) }); toast("Estado del pedido actualizado."); m.close(); orders(); }
      catch (error) { toast(error.message, "error"); }
    };
  }

  async function quotes() {
    const data = await api("/api/admin/quotes");
    setIdentity(data.user);
    content().innerHTML = listPanel("", `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Persona</th><th>Proyecto</th><th>Mensaje</th><th>Estado</th><th aria-label="Abrir"></th></tr></thead><tbody>${data.items.map(q => `<tr ${clickableRow(`data-quote-row="${q.id}" aria-label="Abrir cotización de ${esc(q.name)}"`)}><td><strong>${esc(q.name)}</strong><br><small>${esc(q.contact)}</small></td><td>${esc(q.project_type)}</td><td>${esc(String(q.message).slice(0,90))}${String(q.message).length > 90 ? "…" : ""}</td><td><span class="admin-chip">${statusLabel(q.status)}</span></td><td></td></tr>`).join("") || '<tr><td colspan="5"><div class="admin-empty">Sin cotizaciones.</div></td></tr>'}</tbody></table></div>`);
    activateRows("[data-quote-row]", row => editQuote(data.items.find(q => q.id === +row.dataset.quoteRow)));
  }

  function editQuote(q) {
    const m = modal(`<div class="admin-role-note"><strong>${esc(q.name)}</strong><p>${esc(q.message)}</p><small>${esc(q.contact)}</small></div><form data-quote-form style="margin-top:18px"><div class="admin-form-grid"><div class="admin-field"><span>Estado</span><select name="status">${["new","contacted","qualified","closed","archived"].map(s => `<option value="${s}" ${q.status === s ? "selected" : ""}>${statusLabel(s)}</option>`).join("")}</select></div><div class="admin-field full"><span>Notas internas</span><textarea name="notes">${esc(q.internal_notes || "")}</textarea></div></div><div class="admin-form-actions"><button class="admin-btn primary">Guardar seguimiento</button></div></form>`, `Cotización · ${q.name}`);
    $("[data-quote-form]", m.body).onsubmit = async e => {
      e.preventDefault(); const f = new FormData(e.currentTarget);
      try { await api("/api/admin/quotes/update", { method: "POST", body: JSON.stringify({ id: q.id, status: f.get("status"), internal_notes: f.get("notes") }) }); toast("Cotización actualizada."); m.close(); quotes(); }
      catch (x) { toast(x.message, "error"); }
    };
  }

  async function clients() {
    const usersData = await api("/api/admin/users");
    setIdentity(usersData.user);
    const buyers = usersData.items.filter(u => u.role === "user");
    const stats = new Map();
    usersData.items.forEach(u=>stats.set(u.id,{orders:u.order_count||0,total:u.order_total_cents||0}));
    content().innerHTML = listPanel("", `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Cliente</th><th>Estado</th><th>Pedidos</th><th>Valor total</th><th>Desde</th><th aria-label="Abrir"></th></tr></thead><tbody>${buyers.map(u => { const s = stats.get(u.id) || { orders: 0, total: 0 }; return `<tr ${clickableRow(`data-client-row="${u.id}" aria-label="Ver ${esc(u.display_name)}"`)}><td><strong>${esc(u.display_name)}</strong><br><small>${esc(u.email)}</small></td><td><span class="admin-chip ${u.is_active ? "" : "off"}">${u.is_active ? "Activo" : "Desactivado"}</span></td><td>${s.orders}</td><td>${usd(s.total)}</td><td>${esc(String(u.created_at).slice(0,10))}</td><td></td></tr>`; }).join("") || '<tr><td colspan="6"><div class="admin-empty">Sin clientes registrados.</div></td></tr>'}</tbody></table></div>`);
    activateRows("[data-client-row]", row => {
      const u = buyers.find(item => item.id === +row.dataset.clientRow);
      const s = stats.get(u.id) || { orders: 0, total: 0 };
      modal(`<a class="admin-btn primary" href="/admin/trabajo.html?client=${u.id}">Ver pedidos y servicios de este cliente →</a><div class="admin-form-grid"><div class="admin-field full"><span>Nombre</span><div class="admin-role-note">${esc(u.display_name)}</div></div><div class="admin-field full"><span>Correo</span><div class="admin-role-note">${esc(u.email)}</div></div><div class="admin-field"><span>Pedidos</span><div class="admin-role-note">${s.orders}</div></div><div class="admin-field"><span>Valor acumulado</span><div class="admin-role-note">${usd(s.total)}</div></div></div>`, u.display_name);
    });
  }

  async function promotions() {
    const data = await api("/api/admin/promotions");
    setIdentity(data.user);
    actions().innerHTML = '<button class="admin-btn primary" data-new-promo>+ Nueva promoción</button>';
    content().innerHTML = listPanel("", `<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Promoción</th><th>Código</th><th>Descuento</th><th>Estado</th><th aria-label="Abrir"></th></tr></thead><tbody>${data.items.map(p => `<tr ${clickableRow(`data-promo-row="${p.id}" aria-label="Abrir ${esc(p.name)}"`)}><td><strong>${esc(p.name)}</strong></td><td>${esc(p.code || "—")}</td><td>${p.discount_type === "percent" ? p.discount_value + "%" : usd(p.discount_value)}</td><td><span class="admin-chip ${p.is_active ? "" : "off"}">${p.is_active ? "Activa" : "Inactiva"}</span></td><td></td></tr>`).join("") || '<tr><td colspan="5"><div class="admin-empty">Sin promociones.</div></td></tr>'}</tbody></table></div>`);
    $("[data-new-promo]").onclick = () => editPromo(null);
    activateRows("[data-promo-row]", row => editPromo(data.items.find(p => p.id === +row.dataset.promoRow)));
  }

  function editPromo(p) {
    const m = modal(`<form data-promo-form><div class="admin-form-grid"><div class="admin-field full"><span>Nombre</span><input name="name" value="${esc(p?.name || "")}" required></div><div class="admin-field"><span>Código</span><input name="code" value="${esc(p?.code || "")}"></div><div class="admin-field"><span>Tipo</span><select name="type"><option value="percent" ${p?.discount_type === "percent" ? "selected" : ""}>Porcentaje</option><option value="fixed" ${p?.discount_type === "fixed" ? "selected" : ""}>Monto fijo</option></select></div><div class="admin-field"><span>Valor</span><input name="value" type="number" min="0" value="${p?.discount_value || 0}"></div><div class="admin-field full"><label class="admin-check-row"><input type="checkbox" name="active" ${p?.is_active !== 0 ? "checked" : ""}> Promoción activa</label></div></div><div class="admin-form-actions"><button class="admin-btn primary">Guardar promoción</button></div></form>`, p ? p.name : "Nueva promoción");
    $("[data-promo-form]", m.body).onsubmit = async e => {
      e.preventDefault(); const f = new FormData(e.currentTarget);
      try { await api("/api/admin/promotions/save", { method: "POST", body: JSON.stringify({ id: p?.id, code: f.get("code"), name: f.get("name"), discount_type: f.get("type"), discount_value: asInt(f.get("value")), is_active: e.currentTarget.elements.active.checked }) }); toast("Promoción guardada."); m.close(); promotions(); }
      catch (x) { toast(x.message, "error"); }
    };
  }

  async function users() {
    const data = await api("/api/admin/users");
    setIdentity(data.user);
    const isRoot = data.user?.role === "superadmin";
    actions().innerHTML = isRoot ? '<button class="admin-btn primary" type="button" data-new-user>+ Nuevo usuario</button>' : "";
    content().innerHTML = listPanel("", `<div class="admin-table-wrap"><table class="admin-table admin-users-table"><thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th><th>Seguridad</th><th aria-label="Abrir"></th></tr></thead><tbody>${data.items.map(u => `<tr ${clickableRow(`data-user-row="${u.id}" ${u.role === "superadmin" ? 'data-readonly="true"' : ""} aria-label="Abrir ${esc(u.display_name)}"`)}><td><strong>${esc(u.display_name)}</strong><br><small>${esc(u.email)}</small></td><td><span class="admin-chip">${u.role === "superadmin" ? "Superadmin raíz" : u.role === "admin" ? "Administrador" : "Cliente"}</span></td><td><span class="admin-chip ${u.is_active ? "" : "off"}">${u.is_active ? "Activa" : "Inactiva"}</span></td><td>${u.must_change_password ? '<span class="admin-chip warn">Cambio de clave pendiente</span>' : u.two_factor_enabled ? '<span class="admin-chip">2FA activo</span>' : u.role === "admin" ? '<span class="admin-chip">2FA opcional</span>' : '<span class="admin-chip">Lista</span>'}</td><td></td></tr>`).join("") || '<tr><td colspan="5"><div class="admin-empty">No hay usuarios registrados.</div></td></tr>'}</tbody></table></div>`);
    $("[data-new-user]")?.addEventListener("click", createUser);
    activateRows("[data-user-row]", row => editUser(data.items.find(u => u.id === +row.dataset.userRow), isRoot));
  }

  function createUser() {
    const m = modal(`<form data-create-user-form><div class="admin-form-grid"><div class="admin-field full"><span>Nombre</span><input name="display_name" autocomplete="off" maxlength="120" placeholder="Nombre del usuario" required></div><div class="admin-field full"><span>Correo</span><input name="email" type="email" autocomplete="off" placeholder="usuario@empresa.com" required></div><div class="admin-field"><span>Rol de acceso</span><select name="role"><option value="user">Cliente / usuario</option><option value="admin">Administrador</option></select></div><div class="admin-field"><span>Contraseña temporal</span><input name="temporary_password" type="password" minlength="12" autocomplete="new-password" placeholder="Mínimo 12 caracteres" required></div><div class="admin-field full"><div class="admin-role-note"><strong>Primer ingreso protegido</strong><p>La cuenta deberá cambiar esta contraseña al iniciar sesión. Después podrá entrar directamente a su panel según el rol asignado.</p></div></div></div><div class="admin-form-actions"><button class="admin-btn primary" type="submit">Crear usuario</button></div></form>`, "Nuevo usuario");
    $("[data-create-user-form]", m.body).onsubmit = async e => {
      e.preventDefault();
      const form = e.currentTarget;
      const submit = form.querySelector('button[type="submit"]');
      const f = new FormData(form);
      submit.disabled = true;
      submit.textContent = "Creando…";
      try {
        await api("/api/admin/users/create", { method: "POST", body: JSON.stringify({ display_name: f.get("display_name"), email: f.get("email"), role: f.get("role"), temporary_password: f.get("temporary_password") }) });
        toast("Usuario creado. Deberá cambiar su contraseña al ingresar.");
        m.close();
        users();
      } catch (error) {
        toast(error.message, "error");
        submit.disabled = false;
        submit.textContent = "Crear usuario";
      }
    };
  }

  function editUser(u, isRoot) {
    if (u.role === "admin" && !isRoot) {
      modal('<p class="admin-role-note">Solo la cuenta raíz puede editar otras cuentas administrativas.</p>', u.display_name);
      return;
    }
    if (u.role === "superadmin") {
      modal(`<div class="admin-role-note"><strong>Cuenta raíz protegida</strong><p>El correo ${esc(u.email)} y el rol superadmin no se pueden degradar ni desactivar desde esta interfaz.</p></div><div class="admin-form-grid" style="margin-top:18px"><div class="admin-field"><span>Estado</span><div class="admin-role-note">Cuenta protegida</div></div><div class="admin-field"><span>2FA</span><div class="admin-role-note">${u.two_factor_enabled ? "Activo" : "Opcional"}</div></div></div>`, u.display_name);
      return;
    }
    const m = modal(`<form data-user-form><div class="admin-form-grid"><div class="admin-field full"><span>Usuario</span><div class="admin-role-note"><strong>${esc(u.display_name)}</strong><br>${esc(u.email)}</div></div><div class="admin-field"><span>Rol de acceso</span><select name="role" ${isRoot ? "" : "disabled"}><option value="user" ${u.role === "user" ? "selected" : ""}>Cliente</option><option value="admin" ${u.role === "admin" ? "selected" : ""}>Administrador</option></select></div><div class="admin-field"><span>Estado de cuenta</span><select name="active"><option value="1" ${u.is_active ? "selected" : ""}>Activa</option><option value="0" ${!u.is_active ? "selected" : ""}>Inactiva</option></select></div><div class="admin-field full"><span>Seguridad</span><div class="admin-role-note">${u.two_factor_enabled ? "2FA activo" : "2FA opcional"}</div></div></div><div class="admin-form-actions"><button class="admin-btn primary">Guardar cambios</button></div></form>`, u.display_name);
    $("[data-user-form]", m.body).onsubmit = async e => {
      e.preventDefault(); const f = new FormData(e.currentTarget);
      try { await api("/api/admin/users/update", { method: "POST", body: JSON.stringify({ id: u.id, role: f.get("role") || u.role, is_active: f.get("active") === "1" }) }); toast("Usuario actualizado."); m.close(); users(); }
      catch (error) { toast(error.message, "error"); }
    };
  }

  async function settings() {
    // Compatibilidad para rutas antiguas: la página configuracion.html usa admin-config.js.
    location.href = "configuracion.html";
  }

  async function boot() {
    const [title, subtitle] = titles[page] || titles.dashboard;
    setPageTitle(title, subtitle);
    try {
      const overview = await loadAlerts();
      const handlers = { dashboard: () => dashboard(overview), productos: products, proyectos: projects, pedidos: orders, cotizaciones: quotes, clientes: clients, promociones: promotions, usuarios: users, configuracion: settings };
      await (handlers[page] || handlers.dashboard)();
    } catch (e) {
      if (e.status !== 401 && e.status !== 403) {
        toast(e.message, "error");
        content() && (content().innerHTML = `<div class="admin-empty"><strong>No se pudo cargar esta sección.</strong>${esc(e.message)}</div>`);
      } else showAuth();
    }
  }
  boot();
})();
