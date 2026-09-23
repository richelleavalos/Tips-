/**
 * Código de la experiencia administrativa: admin aux pages. Mantiene esta responsabilidad aislada del frontend de cliente.
 * Las secciones internas conservan nombres descriptivos para facilitar mantenimiento y revisión.
 */
(() => {
  "use strict";
  const A = window.TipsAdmin;
  if (!A) return;
  const { $, esc, usd, api, toast, setPageTitle, loadAlerts, setIdentity, showAuth } = A;
  const page = document.body.dataset.adminPage;
  const content = () => $("[data-page-content]");

  async function sales() {
    setPageTitle("Ventas", "Lectura rápida de ingresos y pedidos pagados.");
    const [overview, orders] = await Promise.all([loadAlerts(), api("/api/admin/orders")]);
    setIdentity(orders.user);
    const valid = orders.items.filter(o => ["paid","processing","ready","shipped","completed"].includes(o.status));
    const total = valid.reduce((sum,o)=>sum+Number(o.total_cents||0),0);
    const average = valid.length ? Math.round(total/valid.length) : 0;
    content().innerHTML = `<div class="admin-grid-metrics"><article class="admin-metric"><span>Ventas acumuladas</span><strong>${usd(total)}</strong><small>Pedidos válidos</small></article><article class="admin-metric"><span>Transacciones</span><strong>${valid.length}</strong><small>Pagadas o procesadas</small></article><article class="admin-metric"><span>Ticket promedio</span><strong>${usd(average)}</strong><small>Por pedido</small></article><article class="admin-metric"><span>Total pedidos</span><strong>${overview.metrics.orders}</strong><small>Todos los estados</small></article></div><div class="admin-card"><div class="admin-card-head"><div><h2>Ventas recientes</h2><p>Últimos pedidos con valor comercial.</p></div></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Pedido</th><th>Cliente</th><th>Estado</th><th>Total</th><th>Fecha</th></tr></thead><tbody>${valid.map(o=>`<tr><td>${esc(o.public_id)}</td><td>${esc(o.customer_name)}</td><td><span class="admin-chip">${esc(o.status)}</span></td><td>${usd(o.total_cents)}</td><td>${esc(String(o.created_at).slice(0,10))}</td></tr>`).join("")||'<tr><td colspan="5">Aún no hay ventas registradas.</td></tr>'}</tbody></table></div></div>`;
  }

  async function inventory() {
    setPageTitle("Inventario", "Stock disponible y productos que necesitan atención.");
    await loadAlerts();
    const data = await api("/api/admin/products"); setIdentity(data.user);
    const low = data.items.filter(p => p.stock_quantity != null && Number(p.stock_quantity) <= 5);
    const totalUnits = data.items.reduce((sum,p)=>sum+Number(p.stock_quantity||0),0);
    content().innerHTML = `<div class="admin-grid-metrics"><article class="admin-metric"><span>Unidades</span><strong>${totalUnits}</strong><small>Inventario registrado</small></article><article class="admin-metric"><span>Stock bajo</span><strong>${low.length}</strong><small>5 unidades o menos</small></article><article class="admin-metric"><span>Productos</span><strong>${data.items.length}</strong><small>Catálogo total</small></article><article class="admin-metric"><span>Sin stock</span><strong>${data.items.filter(p=>Number(p.stock_quantity)===0).length}</strong><small>Requieren revisión</small></article></div><div class="admin-card"><div class="admin-card-head"><div><h2>Inventario por producto</h2><p>Edita cantidades desde Productos.</p></div><a class="admin-btn small" href="productos.html">Gestionar productos</a></div><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>Producto</th><th>SKU</th><th>Stock</th><th>Estado</th><th></th></tr></thead><tbody>${data.items.map(p=>`<tr><td><strong>${esc(p.name)}</strong></td><td>${esc(p.sku||"—")}</td><td>${p.stock_quantity??"—"}</td><td><span class="admin-chip ${p.stock_quantity!=null&&Number(p.stock_quantity)<=5?"warn":""}">${esc(p.stock_status)}</span></td><td><a class="admin-btn small" href="productos.html">Editar</a></td></tr>`).join("")}</tbody></table></div></div>`;
  }

  async function reports() {
    setPageTitle("Reportes", "Indicadores simples para tomar decisiones rápidas.");
    const [overview, orders, quotes, products] = await Promise.all([loadAlerts(), api("/api/admin/orders"), api("/api/admin/quotes"), api("/api/admin/products")]);
    const paid = orders.items.filter(o => ["paid","processing","ready","shipped","completed"].includes(o.status));
    const quoteOpen = quotes.items.filter(q => ["new","contacted","qualified"].includes(q.status)).length;
    const low = products.items.filter(p => p.stock_quantity != null && Number(p.stock_quantity)<=5).length;
    content().innerHTML = `<div class="admin-grid-metrics"><article class="admin-metric"><span>Ingresos</span><strong>${usd(overview.metrics.sales_cents)}</strong><small>Acumulado demo</small></article><article class="admin-metric"><span>Conversión operativa</span><strong>${orders.items.length?Math.round((paid.length/orders.items.length)*100):0}%</strong><small>Pedidos válidos / total</small></article><article class="admin-metric"><span>Cotizaciones abiertas</span><strong>${quoteOpen}</strong><small>Por dar seguimiento</small></article><article class="admin-metric"><span>Stock bajo</span><strong>${low}</strong><small>Productos a revisar</small></article></div><div class="admin-grid-2"><section class="admin-card"><div class="admin-card-head"><div><h2>Salud comercial</h2><p>Resumen de actividad registrada.</p></div></div><div class="admin-alert-list"><div class="admin-alert"><div><strong>${paid.length} pedidos con valor</strong><p>Ventas pagadas, procesando, listas, enviadas o completadas.</p></div></div><div class="admin-alert info"><div><strong>${quotes.items.length} cotizaciones totales</strong><p>${quoteOpen} requieren seguimiento activo.</p></div></div><div class="admin-alert warning"><div><strong>${low} productos con stock bajo</strong><p>Revisa inventario para evitar ventas sin disponibilidad.</p></div></div></div></section><section class="admin-card"><div class="admin-card-head"><div><h2>Accesos rápidos</h2><p>Profundiza en cada indicador.</p></div></div><div class="admin-alert-list"><a class="admin-alert" href="ventas.html"><div><strong>Ver ventas</strong><p>Pedidos e ingresos.</p></div><span>→</span></a><a class="admin-alert" href="cotizaciones.html"><div><strong>Ver cotizaciones</strong><p>Seguimiento comercial.</p></div><span>→</span></a><a class="admin-alert" href="inventario.html"><div><strong>Ver inventario</strong><p>Disponibilidad y alertas.</p></div><span>→</span></a></div></section></div>`;
  }

  async function boot(){try{if(page==="ventas")await sales();else if(page==="inventario")await inventory();else if(page==="reportes")await reports();}catch(e){if(e.status===401||e.status===403)showAuth();else{toast(e.message,"error");content()&&(content().innerHTML=`<div class="admin-empty"><strong>No se pudo cargar esta sección.</strong>${esc(e.message)}</div>`)}}}
  boot();
})();
