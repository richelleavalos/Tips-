# TIPS — sistema visual editorial v5

## Regla principal

Cada contexto carga **una sola hoja visual canónica**:

- Público, tienda y formularios: `frontend/usuario/css/public.css`
- Área privada del cliente: `frontend/usuario/css/account.css`
- Administración: `frontend/admin/css/admin.css`
- Movimiento compartido: `frontend/global/css/motion.css` + `motion-loader.js`

Las capas visuales históricas se eliminan físicamente. No deben volver a añadirse como hojas auxiliares ni como overrides acumulativos sobre las hojas canónicas. Si una evolución visual necesita cambios, se modifica la fuente canónica correspondiente y se elimina el código sustituido.

## Identidad aprobada

La experiencia completa conserva la dirección visual aprobada para TIPS:

- fondo marfil y superficies cálidas;
- verde profundo como color estructural;
- terracota y marrones como acentos;
- tipografía serif editorial para títulos;
- sans serif limpia para interfaz y datos;
- bordes finos y radios mínimos;
- fotografía cálida de arquitectura, objetos e interiores;
- formularios sobrios y composición con espacio generoso.

El área privada del cliente y la administración comparten el mismo lenguaje de dashboard: sidebar verde oscuro, topbar clara, fondo marfil, títulos editoriales, métricas discretas, tablas limpias y formularios sin apariencia genérica de SaaS.

## Overlays, carrito y wizards

Los overlays deben estar anclados al **viewport**, no al documento:

- `modal-backdrop`, `cart-drawer` y `admin-modal-layer` usan `position: fixed`;
- emplean `100dvh` con respaldo de `100vh`;
- el documento se bloquea mientras el overlay está abierto;
- el contenido largo hace scroll dentro del panel o modal;
- `Escape`, backdrop y controles de cierre restauran el estado de la página.

La animación global **nunca** puede aplicar `transform`, `filter` o `clip-path` a `html` o `body`. Safari utiliza esos efectos para crear un nuevo bloque de referencia para descendientes `position: fixed`; eso puede hacer que un modal se desplace con el scroll o que un drawer se renderice fuera de la ventana visible.

## Higiene

`tests/test_frontend_hygiene.py` protege estas reglas y evita que regresen:

- archivos visuales obsoletos;
- cadenas de `@import`;
- varias hojas visuales para un mismo rol;
- runtimes de transición duplicados;
- selectores de admin o cuenta privada mezclados en el CSS público;
- animaciones globales que rompan overlays fixed;
- overlays sin anclaje estable al viewport.
