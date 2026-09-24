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
    const labels = { available: "Disponible", low: "Bajo", out: "Agotado", made_to_order: "Bajo pedido", pending: "Pendiente", paid: "Pagado", processing: "Preparando", ready: "Listo", shipped: "Enviado", completed: "Completado", cancelled: "Cancelado", refunded: "Reembolsado", new: "Nueva", contacted: "Contactada", qualified: "Calificada", closed: "Cerrada", archived: "Archivada" };
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

  async function products() {
    const [data, categories] = await Promise.all([api("/api/admin/products"), api("/api/categories")]);
    setIdentity(data.user);
    actions().innerHTML = `<button class="admin-btn primary" type="button" data-new-product>+ Nuevo producto</button>`;
    content().innerHTML = `<div class="admin-toolbar"><label class="admin-search"><input type="search" data-product-search placeholder="Buscar producto..."></label><span>${data.items.length} productos</span></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Producto</th><th>Categoría</th><th>Precio</th><th>Stock</th><th>Imágenes</th><th>Estado</th><th></th></tr></thead><tbody data-products-body></tbody></table></div>`;
    const draw = () => {
      const q = $("[data-product-search]").value.trim().toLowerCase();
      const list = data.items.filter(p => !q || `${p.name} ${p.category_name || ""} ${p.sku || ""}`.toLowerCase().includes(q));
      $("[data-products-body]").innerHTML = list.map(p => `<tr><td><div class="admin-product-cell">${p.primary_image ? `<img class="admin-thumb" src="../${esc(p.primary_image)}" alt="">` : '<div class="admin-thumb"></div>'}<div><strong>${esc(p.name)}</strong><small>${esc(p.sku || p.slug)}</small></div></div></td><td>${esc(p.category_name || "Sin categoría")}</td><td>${usd(p.base_price_cents)}</td><td>${p.stock_quantity ?? "—"}</td><td><button class="admin-btn small" data-images="${p.id}">${p.image_count || 0}/5 imágenes</button></td><td><span class="admin-chip ${p.is_active ? "" : "off"}">${p.is_active ? esc(statusLabel(p.stock_status)) : "Oculto"}</span></td><td><button class="admin-btn small" data-edit-product="${p.id}">Editar</button></td></tr>`).join("") || '<tr><td colspan="7"><div class="admin-empty">No hay coincidencias.</div></td></tr>';
      $$('[data-edit-product]').forEach(b => b.onclick = () => editProduct(data.items.find(p => p.id === +b.dataset.editProduct), categories.items, data));
      $$('[data-images]').forEach(b => b.onclick = () => imageManager(+b.dataset.images, data));
    };
    const initialSearch = new URLSearchParams(location.search).get("search") || "";
    $("[data-product-search]").value = initialSearch;
    $("[data-product-search]").oninput = draw;
    $("[data-new-product]").onclick = () => newProduct(categories.items);
    draw();
  }

  function productFields(p, categories) {
    return `<div class="admin-form-grid"><div class="admin-field full"><span>Nombre</span><input name="name" required maxlength="180" value="${esc(p?.name || "")}"></div><div class="admin-field"><span>Categoría</span><select name="category_id"><option value="">Sin categoría</option>${categories.map(c => `<option value="${c.id}" ${p?.category_id === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div><div class="admin-field"><span>Precio USD</span><input name="price" type="number" min="0" step="0.01" value="${p ? (p.base_price_cents / 100).toFixed(2) : "0.00"}"></div><div class="admin-field"><span>Inventario</span><input name="stock" type="number" min="0" step="1" value="${p?.stock_quantity ?? 0}"></div><div class="admin-field"><span>Estado de stock</span><select name="stock_status"><option value="available">Disponible</option><option value="low">Bajo</option><option value="out">Agotado</option><option value="made_to_order">Bajo pedido</option></select></div><div class="admin-field full"><span>Descripción</span><textarea name="description" maxlength="5000">${esc(p?.description || "")}</textarea></div>${p ? '<div class="admin-field full"><label><input type="checkbox" name="is_active" '+(p.is_active ? 'checked' : '')+'> Visible en la tienda</label></div>' : ''}</div><div class="admin-modal-foot"><button class="admin-btn" type="button" data-cancel>Cancelar</button><button class="admin-btn primary" type="submit">Guardar</button></div>`;
  }

  function editProduct(product, categories, data) {
    const m = modal(`<form data-product-form>${productFields(product, categories)}</form>`, `Editar ${product.name}`);
    const form = $("[data-product-form]", m.body);
    form.elements.stock_status.value = product.stock_status;
    $("[data-cancel]", m.layer).onclick = m.close;
    form.onsubmit = async event => {
      event.preventDefault();
      const f = new FormData(form);
      try {
        await api("/api/admin/products/update", { method: "POST", body: JSON.stringify({ id: product.id, name: f.get("name"), description: f.get("description"), base_price_cents: Math.round(Number(f.get("price")) * 100), stock_quantity: asInt(f.get("stock")), stock_status: f.get("stock_status"), is_active: form.elements.is_active.checked }) });
        toast("Producto actualizado."); m.close(); products();
      } catch (e) { toast(e.message, "error"); }
    };
  }

  function newProduct(categories) {
    const m = modal(`<form data-product-form>${productFields(null, categories)}</form>`, "Nuevo producto");
    const form = $("[data-product-form]", m.body);
    $("[data-cancel]", m.layer).onclick = m.close;
    form.onsubmit = async event => {
      event.preventDefault(); const f = new FormData(form);
      try {
        const result = await api("/api/admin/products/create", { method: "POST", body: JSON.stringify({ name: f.get("name"), category_id: f.get("category_id") ? +f.get("category_id") : null, description: f.get("description"), base_price_cents: Math.round(Number(f.get("price")) * 100), stock_quantity: asInt(f.get("stock")) }) });
        toast("Producto creado. Ahora puedes agregar sus imágenes."); m.close(); await products(); setTimeout(() => imageManager(result.id), 120);
      } catch (e) { toast(e.message, "error"); }
    };
  }

  async function compressImage(file) {
    if (!file.type.startsWith("image/")) throw new Error("Selecciona una imagen JPG, PNG o WebP.");
    const bitmap = await createImageBitmap(file);
    const max = 1400;
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas"); canvas.width = Math.max(1, Math.round(bitmap.width * scale)); canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d"); ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height); bitmap.close();
    let quality = .84; let blob;
    do { blob = await new Promise(resolve => canvas.toBlob(resolve, "image/webp", quality)); quality -= .08; } while (blob && blob.size > 650000 && quality >= .44);
    if (!blob || blob.size > 700000) throw new Error("No pudimos optimizar la imagen por debajo de 700 KB.");
    return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",", 2)[1]); reader.onerror = reject; reader.readAsDataURL(blob); });
  }

  async function imageManager(productId) {
    try {
      const data = await api(`/api/admin/products/images?product_id=${productId}`);
      const m = modal(`<div class="image-upload"><input id="product-image-file" type="file" accept="image/jpeg,image/png,image/webp"><label for="product-image-file"><strong>+ Agregar imagen</strong><small>JPG, PNG o WebP · se optimiza automáticamente · máximo 5</small></label></div><div class="image-manager-grid" data-images-grid style="margin-top:14px"></div>`, `Imágenes · ${data.product.name}`, true);
      const drawImages = items => {
        $("[data-images-grid]", m.body).innerHTML = items.map((img, index) => `<article class="image-item"><img src="../${esc(img.path)}" alt="${esc(img.alt_text)}"><div class="image-item-fields"><div class="admin-field"><span>Texto alternativo</span><input value="${esc(img.alt_text)}" data-alt="${img.id}"></div><div class="image-item-row"><button class="admin-btn small" data-save-image="${img.id}" data-sort="${index}">Guardar</button><button class="admin-btn small danger" data-delete-image="${img.id}">Eliminar</button></div></div></article>`).join("") || '<div class="admin-empty"><strong>Aún no hay imágenes</strong>Agrega entre 1 y 5 fotografías del producto.</div>';
        $$('[data-save-image]', m.body).forEach(b => b.onclick = async () => { try { await api("/api/admin/products/images/update", { method: "POST", body: JSON.stringify({ id: +b.dataset.saveImage, alt_text: $(`[data-alt="${b.dataset.saveImage}"]`, m.body).value, sort_order: +b.dataset.sort }) }); toast("Imagen actualizada."); } catch(e){ toast(e.message,"error"); } });
        $$('[data-delete-image]', m.body).forEach(b => b.onclick = async () => { if (!confirm("¿Eliminar esta imagen?")) return; try { await api("/api/admin/products/images/delete", { method: "POST", body: JSON.stringify({ id: +b.dataset.deleteImage }) }); toast("Imagen eliminada."); const fresh = await api(`/api/admin/products/images?product_id=${productId}`); drawImages(fresh.items); } catch(e){toast(e.message,"error");} });
      };
      drawImages(data.items);
      $("#product-image-file", m.body).onchange = async event => {
        const file = event.target.files?.[0]; if (!file) return;
        if (data.items.length >= data.max_images) { toast("Este producto ya tiene 5 imágenes.", "error"); return; }
        try { toast("Optimizando imagen..."); const encoded = await compressImage(file); await api("/api/admin/products/images/add", { method: "POST", body: JSON.stringify({ product_id: productId, alt_text: data.product.name, data_base64: encoded }) }); toast("Imagen agregada."); const fresh = await api(`/api/admin/products/images?product_id=${productId}`); data.items = fresh.items; drawImages(fresh.items); event.target.value = ""; } catch(e){ toast(e.message,"error"); }
      };
    } catch(e){ toast(e.message,"error"); }
  }

  async function projects() {
    const data = await api("/api/admin/projects"); setIdentity(data.user);
    content().innerHTML = `<div class="admin-toolbar"><label class="admin-search"><input data-project-search placeholder="Buscar proyecto..."></label><span>${data.items.length} proyectos</span></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Proyecto</th><th>Categoría</th><th>Ubicación</th><th>Año</th><th>Publicación</th><th></th></tr></thead><tbody data-projects-body></tbody></table></div>`;
    const draw = () => { const q=$("[data-project-search]").value.toLowerCase(); const list=data.items.filter(p=>!q||`${p.title} ${p.category} ${p.location||""}`.toLowerCase().includes(q)); $("[data-projects-body]").innerHTML=list.map(p=>`<tr><td><strong>${esc(p.title)}</strong><br><small>${esc(p.summary)}</small></td><td>${esc(p.category)}</td><td>${esc(p.location||"—")}</td><td>${p.completed_year||"—"}</td><td><span class="admin-chip ${p.is_published?"":"off"}">${p.is_published?"Publicado":"Oculto"}</span></td><td><button class="admin-btn small" data-edit-project="${p.id}">Editar</button></td></tr>`).join(""); $$('[data-edit-project]').forEach(b=>b.onclick=()=>editProject(data.items.find(p=>p.id===+b.dataset.editProject))); };
    $("[data-project-search]").oninput=draw; draw();
  }

  function editProject(p){ const m=modal(`<form data-project-form><div class="admin-form-grid"><div class="admin-field full"><span>Título</span><input name="title" value="${esc(p.title)}"></div><div class="admin-field"><span>Categoría</span><input name="category" value="${esc(p.category)}"></div><div class="admin-field"><span>Ubicación</span><input name="location" value="${esc(p.location||"")}"></div><div class="admin-field"><span>Año</span><input type="number" name="year" value="${p.completed_year||""}"></div><div class="admin-field"><label><input type="checkbox" name="published" ${p.is_published?"checked":""}> Publicado</label></div><div class="admin-field full"><span>Resumen</span><textarea name="summary">${esc(p.summary)}</textarea></div><div class="admin-field full"><span>Descripción</span><textarea name="description">${esc(p.description)}</textarea></div></div><div class="admin-modal-foot"><button class="admin-btn" type="button" data-cancel>Cancelar</button><button class="admin-btn primary">Guardar</button></div></form>`,`Editar ${p.title}`); const form=$("[data-project-form]",m.body); $("[data-cancel]",m.layer).onclick=m.close; form.onsubmit=async e=>{e.preventDefault();const f=new FormData(form);try{await api("/api/admin/projects/update",{method:"POST",body:JSON.stringify({id:p.id,title:f.get("title"),category:f.get("category"),location:f.get("location"),completed_year:f.get("year")?+f.get("year"):null,summary:f.get("summary"),description:f.get("description"),is_published:form.elements.published.checked})});toast("Proyecto actualizado.");m.close();projects()}catch(x){toast(x.message,"error")}}; }

  async function orders(){const data=await api("/api/admin/orders");setIdentity(data.user);content().innerHTML=`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Pedido</th><th>Cliente</th><th>Contacto</th><th>Total</th><th>Estado</th></tr></thead><tbody>${data.items.map(o=>`<tr><td><strong>${esc(o.public_id)}</strong><br><small>${esc(o.created_at)}</small></td><td>${esc(o.customer_name)}</td><td>${esc(o.email||"")}<br>${esc(o.phone||"")}</td><td>${usd(o.total_cents)}</td><td><select data-order-status="${o.id}">${["pending","paid","processing","ready","shipped","completed","cancelled","refunded"].map(s=>`<option value="${s}" ${o.status===s?"selected":""}>${statusLabel(s)}</option>`).join("")}</select></td></tr>`).join("")||'<tr><td colspan="5">Sin pedidos.</td></tr>'}</tbody></table></div>`;$$('[data-order-status]').forEach(s=>s.onchange=async()=>{try{await api("/api/admin/orders/update",{method:"POST",body:JSON.stringify({id:+s.dataset.orderStatus,status:s.value})});toast("Estado del pedido actualizado.")}catch(e){toast(e.message,"error")}})}

  async function quotes(){const data=await api("/api/admin/quotes");setIdentity(data.user);content().innerHTML=`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Persona</th><th>Proyecto</th><th>Mensaje</th><th>Estado</th><th></th></tr></thead><tbody>${data.items.map(q=>`<tr><td><strong>${esc(q.name)}</strong><br><small>${esc(q.contact)}</small></td><td>${esc(q.project_type)}</td><td>${esc(String(q.message).slice(0,90))}${String(q.message).length>90?"…":""}</td><td><span class="admin-chip">${statusLabel(q.status)}</span></td><td><button class="admin-btn small" data-quote="${q.id}">Gestionar</button></td></tr>`).join("")||'<tr><td colspan="5">Sin cotizaciones.</td></tr>'}</tbody></table></div>`;$$('[data-quote]').forEach(b=>b.onclick=()=>editQuote(data.items.find(q=>q.id===+b.dataset.quote)))}
  function editQuote(q){const m=modal(`<div class="admin-card" style="padding:14px;margin-bottom:12px"><strong>${esc(q.name)}</strong><p>${esc(q.message)}</p><small>${esc(q.contact)}</small></div><form data-quote-form><div class="admin-form-grid"><div class="admin-field"><span>Estado</span><select name="status">${["new","contacted","qualified","closed","archived"].map(s=>`<option value="${s}" ${q.status===s?"selected":""}>${statusLabel(s)}</option>`).join("")}</select></div><div class="admin-field full"><span>Notas internas</span><textarea name="notes">${esc(q.internal_notes||"")}</textarea></div></div><div class="admin-modal-foot"><button class="admin-btn primary">Guardar seguimiento</button></div></form>`,`Cotización · ${q.name}`);$("[data-quote-form]",m.body).onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await api("/api/admin/quotes/update",{method:"POST",body:JSON.stringify({id:q.id,status:f.get("status"),internal_notes:f.get("notes")})});toast("Cotización actualizada.");m.close();quotes()}catch(x){toast(x.message,"error")}}}

  async function clients(){const [usersData,ordersData]=await Promise.all([api("/api/admin/users"),api("/api/admin/orders")]);setIdentity(usersData.user);const buyers=usersData.items.filter(u=>u.role==="user");const stats=new Map();ordersData.items.forEach(o=>{const key=(o.email||"").toLowerCase();const s=stats.get(key)||{orders:0,total:0};s.orders++;s.total+=o.total_cents;stats.set(key,s)});content().innerHTML=`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Cliente</th><th>Estado</th><th>Pedidos</th><th>Valor total</th><th>Desde</th></tr></thead><tbody>${buyers.map(u=>{const s=stats.get(u.email.toLowerCase())||{orders:0,total:0};return `<tr><td><strong>${esc(u.display_name)}</strong><br><small>${esc(u.email)}</small></td><td><span class="admin-chip ${u.is_active?"":"off"}">${u.is_active?"Activo":"Desactivado"}</span></td><td>${s.orders}</td><td>${usd(s.total)}</td><td>${esc(String(u.created_at).slice(0,10))}</td></tr>`}).join("")||'<tr><td colspan="5">Sin clientes registrados.</td></tr>'}</tbody></table></div>`}

  async function promotions(){const data=await api("/api/admin/promotions");setIdentity(data.user);actions().innerHTML='<button class="admin-btn primary" data-new-promo>+ Nueva promoción</button>';content().innerHTML=`<div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Promoción</th><th>Código</th><th>Descuento</th><th>Estado</th><th></th></tr></thead><tbody>${data.items.map(p=>`<tr><td><strong>${esc(p.name)}</strong></td><td>${esc(p.code||"—")}</td><td>${p.discount_type==="percent"?p.discount_value+"%":usd(p.discount_value)}</td><td><span class="admin-chip ${p.is_active?"":"off"}">${p.is_active?"Activa":"Inactiva"}</span></td><td><button class="admin-btn small" data-promo="${p.id}">Editar</button></td></tr>`).join("")||'<tr><td colspan="5">Sin promociones.</td></tr>'}</tbody></table></div>`;$("[data-new-promo]").onclick=()=>editPromo(null);$$('[data-promo]').forEach(b=>b.onclick=()=>editPromo(data.items.find(p=>p.id===+b.dataset.promo)))}
  function editPromo(p){const m=modal(`<form data-promo-form><div class="admin-form-grid"><div class="admin-field"><span>Nombre</span><input name="name" value="${esc(p?.name||"")}" required></div><div class="admin-field"><span>Código</span><input name="code" value="${esc(p?.code||"")}"></div><div class="admin-field"><span>Tipo</span><select name="type"><option value="percent" ${p?.discount_type==="percent"?"selected":""}>Porcentaje</option><option value="fixed" ${p?.discount_type==="fixed"?"selected":""}>Monto fijo</option></select></div><div class="admin-field"><span>Valor</span><input name="value" type="number" min="0" value="${p?.discount_value||0}"></div><div class="admin-field full"><label><input type="checkbox" name="active" ${p?.is_active!==0?"checked":""}> Promoción activa</label></div></div><div class="admin-modal-foot"><button class="admin-btn primary">Guardar</button></div></form>`,p?`Editar ${p.name}`:"Nueva promoción");$("[data-promo-form]",m.body).onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await api("/api/admin/promotions/save",{method:"POST",body:JSON.stringify({id:p?.id,code:f.get("code"),name:f.get("name"),discount_type:f.get("type"),discount_value:asInt(f.get("value")),is_active:e.currentTarget.elements.active.checked})});toast("Promoción guardada.");m.close();promotions()}catch(x){toast(x.message,"error")}}}

  async function users(){const data=await api("/api/admin/users");setIdentity(data.user);content().innerHTML=`<div class="admin-table-wrap"><table class="admin-table admin-users-table"><thead><tr><th>Usuario</th><th>Rol de acceso</th><th>Estado de cuenta</th><th>Acciones</th></tr></thead><tbody>${data.items.map(u=>`<tr><td><strong>${esc(u.display_name)}</strong><br><small>${esc(u.email)}</small></td><td><label class="admin-control-label" for="user-role-${u.id}">Permisos</label><select class="admin-user-select" id="user-role-${u.id}" data-user-role="${u.id}" aria-label="Rol de ${esc(u.display_name)}"><option value="user" ${u.role==="user"?"selected":""}>Cliente</option><option value="admin" ${u.role==="admin"?"selected":""}>Administrador</option></select></td><td><label class="admin-status-toggle"><input type="checkbox" data-user-active="${u.id}" ${u.is_active?"checked":""}><span class="admin-status-track" aria-hidden="true"></span><span class="admin-status-copy"><strong>${u.is_active?"Cuenta activa":"Cuenta inactiva"}</strong><small>${u.is_active?"Puede iniciar sesión":"Acceso bloqueado"}</small></span></label></td><td><button class="admin-btn primary small" data-save-user="${u.id}">Guardar cambios</button></td></tr>`).join("")||'<tr><td colspan="4"><div class="admin-empty">No hay usuarios registrados.</div></td></tr>'}</tbody></table></div>`;$$('[data-user-active]').forEach(input=>input.onchange=()=>{const copy=input.closest('.admin-status-toggle').querySelector('.admin-status-copy');copy.innerHTML=`<strong>${input.checked?"Cuenta activa":"Cuenta inactiva"}</strong><small>${input.checked?"Puede iniciar sesión":"Acceso bloqueado"}</small>`});$$('[data-save-user]').forEach(b=>b.onclick=async()=>{const id=+b.dataset.saveUser;b.disabled=true;try{await api("/api/admin/users/update",{method:"POST",body:JSON.stringify({id,role:$(`[data-user-role="${id}"]`).value,is_active:$(`[data-user-active="${id}"]`).checked})});toast("Usuario actualizado.")}catch(e){toast(e.message,"error")}finally{b.disabled=false}})}

  async function settings(){const data=await api("/api/admin/settings");setIdentity(data.user);const map=Object.fromEntries(data.items.map(i=>[i.key,i.value||{}]));const theme=map.theme||{},home=map.home||{},contact=map.contact||{};content().innerHTML=`<div class="admin-grid-2"><section class="admin-card"><div class="admin-card-head"><div><h2>Contenido de inicio</h2><p>Textos principales del sitio público.</p></div></div><form data-home-settings><div class="admin-form-grid"><div class="admin-field full"><span>Frase superior</span><input name="eyebrow" value="${esc(home.eyebrow||"")}"></div><div class="admin-field"><span>Título</span><input name="title" value="${esc(home.title||"")}"></div><div class="admin-field"><span>Palabra destacada</span><input name="highlight" value="${esc(home.highlight||"")}"></div><div class="admin-field full"><span>Descripción</span><textarea name="description">${esc(home.description||"")}</textarea></div><div class="admin-field"><span>Botón principal</span><input name="primary_cta" value="${esc(home.primary_cta||"")}"></div><div class="admin-field"><span>Botón tienda</span><input name="secondary_cta" value="${esc(home.secondary_cta||"")}"></div></div><div style="margin-top:14px"><button class="admin-btn primary">Guardar contenido</button></div></form></section><section><div class="admin-card"><div class="admin-card-head"><div><h2>Apariencia</h2><p>Colores y variante del logo.</p></div></div><form data-theme-settings><div class="admin-form-grid"><div class="admin-field"><span>Principal</span><input type="color" name="primary" value="${esc(theme.primary||"#173d2b")}"></div><div class="admin-field"><span>Acento</span><input type="color" name="accent" value="${esc(theme.accent||"#ef7d22")}"></div><div class="admin-field"><span>Secundario</span><input type="color" name="secondary" value="${esc(theme.secondary||"#825334")}"></div><div class="admin-field"><span>Fondo</span><input type="color" name="surface" value="${esc(theme.surface||"#f7f7f2")}"></div><div class="admin-field full"><span>Logo</span><select name="logo_variant">${["orange","green","black","brown"].map(v=>`<option ${theme.logo_variant===v?"selected":""}>${v}</option>`).join("")}</select></div></div><div style="margin-top:14px"><button class="admin-btn primary">Guardar apariencia</button></div></form></div><div class="admin-card"><div class="admin-card-head"><div><h2>Contacto</h2><p>Datos visibles para clientes.</p></div></div><form data-contact-settings><div class="admin-form-grid"><div class="admin-field full"><span>Ubicación</span><input name="location" value="${esc(contact.location||"")}"></div><div class="admin-field full"><span>Email</span><input name="email" type="email" value="${esc(contact.email||"")}"></div><div class="admin-field full"><span>WhatsApp</span><input name="whatsapp" value="${esc(contact.whatsapp||"")}"></div></div><div style="margin-top:14px"><button class="admin-btn primary">Guardar contacto</button></div></form></div></section></div>`;
    const save=(selector,key)=>{$(selector).onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget),value=Object.fromEntries(f.entries());try{await api("/api/admin/settings/save",{method:"POST",body:JSON.stringify({key,value,is_public:true})});toast("Configuración guardada.")}catch(x){toast(x.message,"error")}}};save("[data-home-settings]","home");save("[data-theme-settings]","theme");save("[data-contact-settings]","contact");
  }

  async function boot(){const [title,subtitle]=titles[page]||titles.dashboard;setPageTitle(title,subtitle);try{const overview=await loadAlerts();const handlers={dashboard:()=>dashboard(overview),productos:products,proyectos:projects,pedidos:orders,cotizaciones:quotes,clientes:clients,promociones:promotions,usuarios:users,configuracion:settings};await (handlers[page]||handlers.dashboard)()}catch(e){if(e.status!==401&&e.status!==403){toast(e.message,"error");content()&&(content().innerHTML=`<div class="admin-empty"><strong>No se pudo cargar esta sección.</strong>${esc(e.message)}</div>`)}else showAuth()}}
  boot();
})();
