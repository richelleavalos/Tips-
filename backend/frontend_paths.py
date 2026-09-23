"""Rutas web estables, independientes de la organización física del frontend.

Las vistas se sirven solo por estas rutas; las rutas físicas no son públicas.
Los alias de recursos conservan páginas abiertas antes de la reorganización.
"""

VIEW_ROUTES = {
    "/index.html": "frontend/usuario/vistas/publicas/index.html",
    "/arquitectura.html": "frontend/usuario/vistas/publicas/arquitectura.html",
    "/cuenta.html": "frontend/usuario/vistas/publicas/cuenta.html",
    "/proyecto.html": "frontend/usuario/vistas/publicas/proyecto.html",
    "/checkout.html": "frontend/usuario/vistas/publicas/checkout.html",
    "/tienda.html": "frontend/usuario/vistas/publicas/tienda.html",
    "/contacto.html": "frontend/usuario/vistas/publicas/contacto.html",
    "/merchandise.html": "frontend/usuario/vistas/publicas/merchandise.html",
    "/user/pedidos.html": "frontend/usuario/vistas/cuenta/pedidos.html",
    "/user/index.html": "frontend/usuario/vistas/cuenta/index.html",
    "/user/datos.html": "frontend/usuario/vistas/cuenta/datos.html",
    "/user/seguridad.html": "frontend/usuario/vistas/cuenta/seguridad.html",
    "/admin/productos.html": "frontend/admin/vistas/productos.html",
    "/admin/proyectos.html": "frontend/admin/vistas/proyectos.html",
    "/admin/ventas.html": "frontend/admin/vistas/ventas.html",
    "/admin/pedidos.html": "frontend/admin/vistas/pedidos.html",
    "/admin/index.html": "frontend/admin/vistas/index.html",
    "/admin/cuenta.html": "frontend/admin/vistas/cuenta.html",
    "/admin/configuracion.html": "frontend/admin/vistas/configuracion.html",
    "/admin/usuarios.html": "frontend/admin/vistas/usuarios.html",
    "/admin/cotizaciones.html": "frontend/admin/vistas/cotizaciones.html",
    "/admin/reportes.html": "frontend/admin/vistas/reportes.html",
    "/admin/promociones.html": "frontend/admin/vistas/promociones.html",
    "/admin/clientes.html": "frontend/admin/vistas/clientes.html",
    "/admin/inventario.html": "frontend/admin/vistas/inventario.html",
    "/": "frontend/usuario/vistas/publicas/index.html",
    "/admin/": "frontend/admin/vistas/index.html",
    "/user/": "frontend/usuario/vistas/cuenta/index.html"
}

# Recursos frontend canónicos. Las capas históricas se mantienen eliminadas desde v5.
ASSET_ROUTES = {
    "/frontend/usuario/css/public.css": "frontend/usuario/css/public.css",
    "/frontend/usuario/css/account.css": "frontend/usuario/css/account.css",
    "/frontend/admin/css/admin.css": "frontend/admin/css/admin.css",
    "/frontend/global/css/motion.css": "frontend/global/css/motion.css",
    "/frontend/usuario/js/site-settings.js": "frontend/usuario/js/site-settings.js",
    "/frontend/usuario/js/app.js": "frontend/usuario/js/app.js",
    "/frontend/usuario/js/profile-menu.js": "frontend/usuario/js/profile-menu.js",
    "/frontend/usuario/js/client-ui.js": "frontend/usuario/js/client-ui.js",
    "/frontend/usuario/js/account-routing.js": "frontend/usuario/js/account-routing.js",
    "/frontend/usuario/js/user-area.js": "frontend/usuario/js/user-area.js",
    "/frontend/admin/js/admin-core.js": "frontend/admin/js/admin-core.js",
    "/frontend/admin/js/admin-pages.js": "frontend/admin/js/admin-pages.js",
    "/frontend/admin/js/admin-aux-pages.js": "frontend/admin/js/admin-aux-pages.js",
    "/frontend/admin/js/admin-account.js": "frontend/admin/js/admin-account.js",
    "/frontend/admin/js/admin-config.js": "frontend/admin/js/admin-config.js",
    "/frontend/admin/js/admin-product-payload.js": "frontend/admin/js/admin-product-payload.js",
    "/frontend/global/js/motion-loader.js": "frontend/global/js/motion-loader.js",
    "/frontend/global/js/motion-runtime.js": "frontend/global/js/motion-runtime.js",
}
