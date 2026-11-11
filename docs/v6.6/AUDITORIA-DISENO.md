# TIPS v6.6 — Auditoría integral de diseño

**Entorno:** copia local y base ficticia. **Entrega:** 10 de noviembre de 2026. Se conservó la identidad editorial de TIPS y el diseño del panel de la revisión anterior. No se modificó producción.

## Criterios de UX consultados antes de la revisión

Las diez reglas se adaptaron de [Jakob Nielsen, Nielsen Norman Group](https://www.nngroup.com/articles/ten-usability-heuristics/). Sirvieron de criterios de inspección, además de la solicitud sobre iconos, logotipos, imágenes, texto y movimiento.

| Regla | Comprobación aplicada a TIPS |
|---|---|
| 1. Mostrar el estado del sistema | Sección activa, pestaña seleccionada, recuento de productos, estados de solicitudes, avisos y confirmaciones. |
| 2. Hablar el idioma del usuario | Terminología de bolsa, solicitud y retiro en español. El historial expresa acciones y estados en lenguaje corriente, y 2FA se identifica como opcional. |
| 3. Dar control para volver, cerrar o cancelar | Menús, bolsa y expedientes con controles visibles, salida de seguridad opcional y enlaces de retorno. Se respeta movimiento reducido. |
| 4. Mantener consistencia | Iconos lineales SVG y logotipos con proporción estable. Un solo sistema de crossfade y selección visible entre vistas. |
| 5. Prevenir errores | Solicitud desactivada con bolsa vacía, enlaces del resumen que conservan el estado, y protección contra respuestas atrasadas al cambiar pestaña. |
| 6. Facilitar el reconocimiento | Fotografías distinguibles, textos alternativos, etiquetas de iconos y selección anunciada a tecnologías de asistencia. |
| 7. Hacer eficientes las acciones frecuentes | Búsqueda, filtros, navegación por proyectos y calendario. Se eliminó una consulta duplicada de productos. |
| 8. Mostrar solo elementos útiles | Se quitaron los indicadores que simulaban un carrusel, botones vacíos de galería y datos técnicos crudos del historial. |
| 9. Ayudar a entender y corregir errores | Se recorrieron las páginas 403, 404, 429, 500 y 503, la recuperación de acceso y estados de búsqueda/bolsa vacíos. |
| 10. Ofrecer ayuda contextual | Explicaciones de retiro, requisitos de fotos, ayuda de filtros y un aviso visible para desplazar la tabla estrecha. |

También se aplicaron [reflow de W3C](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html), [tamaño de objetivos táctiles](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum) y [movimiento desde interacciones](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions). Se revisaron manualmente contraste, jerarquía, foco y legibilidad de controles representativos. La auditoría no equivale a una certificación WCAG ni cubre cualquier combinación de colores configurable por el negocio.

## Hallazgos y correcciones

| Hallazgo | Corrección y comprobación |
|---|---|
| Logo de Mi cuenta se veía como un rectángulo blanco | El filtro invertía también el fondo blanco del archivo. Se creó la variante clara del SVG oficial sobre fondo transparente, manteniendo su forma. Se inspeccionó el menú abierto en Browser. |
| Iconos de búsqueda, menú y cuenta dependían de glifos de una fuente | SVG con tamaño fijo y etiquetas accesibles. Se revisaron la sidebar, cabecera, botón de bolsa y menús a varios anchos. |
| Filtros y ordenación se tocaban a 320 px | Dos columnas con 14 px de separación y controles de 44 px; medidas en Browser. |
| Detalle de producto ocupaba demasiado espacio en teléfono estrecho | Foto y título adaptados. En Browser a 320 px el botón de agregar quedó dentro del panel sin desbordamiento. |
| Ocho fichas sin fotos propias | Se integraron ocho imágenes generadas; se conservaron fotos cargadas. Las imágenes también se usan en la bolsa y en el resumen del pedido. |
| Un detalle mostraba una imagen anterior o decorativa durante la actualización | Tarjetas y modal ahora renderizan la foto directamente desde los datos del producto; se eliminó el observador que hacía renderizados redundantes. |
| Galería y navegación de proyecto tenían controles sin destino real | Las miniaturas aparecen solo con fotos registradas; cambian la imagen y anuncian la selección. Anterior/siguiente usan proyectos publicados adyacentes. |
| Actividad comprimía columnas y exponía JSON | Texto en español y desplazamiento horizontal dentro de la tabla. En Browser a 320 px la página conservó 320 px de ancho; solo la tabla necesitó desplazamiento. |
| El resumen abría pedidos sin aplicar el estado del enlace | El estado del enlace se usa en el filtro inicial. |
| Pantalla 503 desbordaba a 320 px | Tarjeta con ancho limitado, título más claro y texto adaptable. Se repitieron las cinco páginas de error en los cuatro tamaños. |
| La bolsa vacía permitía intentar una solicitud | Confirmación desactivada y enlace de retorno al catálogo. |
| Había demoras artificiales, animaciones superpuestas y clics perdidos al cambiar pestañas | Una duración de 500 ms; cambio de pestaña con copia visual inerte y controles activos. Se retiraron el antiguo observador de revelado, el parallax global y el retraso previo a navegar. |
| La vista 2FA decía que era obligatoria | Se identifica como opcional y ofrece volver al panel. La revisión fue visual: no se activó 2FA. |

## Movimiento

- **Entre páginas:** fundido simultáneo de salida y entrada, con ambas animaciones configuradas en `500ms`. Se utiliza la transición nativa del navegador; en motores sin ella, se conserva una copia visual temporal, inerte y sin scripts. Se quitan los valores de formularios y claves de esa copia.
- **Entre pestañas y galerías:** copia visual inerte que sale mientras entra el contenido actualizado. Esto mantiene activos los controles incluso durante el fundido. Se comprobó el cambio rápido de Servicios de diseño a Pedidos en Browser sin esperar entre clics. Se usó la [especificación de W3C](https://www.w3.org/TR/css-view-transitions-1/) para confirmar por qué un fundido nativo de documento completo puede bloquear clics durante la animación.
- **Detalle rápido, bolsa y expedientes:** opacidad compartida de `500ms`. La geometría del panel permanece anclada al dispositivo. Los indicadores de progreso y el desplazamiento de una lista siguen siendo interacciones independientes.
- **Movimiento reducido:** el ajuste del sistema desactiva los crossfades en navegación y pestañas. Los datos y controles se actualizan igual.

## Catálogo

Se usó el generador de imágenes integrado para crear fotografías de catálogo de auriculares negros, mochila, botella térmica, zapatillas, lámpara, vela, bolso de yute y libreta. Son imágenes generadas para las fichas del catálogo; no son fotografías tomadas de unidades físicas. La variante de auriculares se contrastó con la ficha “Negro” y se ajustó el color. Los ocho archivos WebP y su texto alternativo se entregan en `assets/catalog/`; la ficha `PROMPTS-CATALOGO.json` documenta los prompts y archivos finales.

Al iniciar, la aplicación añade la imagen al producto conocido solo si no tiene ninguna. Una fotografía cargada por administración tiene prioridad, y al subirla reemplaza la imagen ilustrativa del registro. No se modifica la imagen existente de otros productos ni se añaden datos ficticios al ZIP desplegable.

## Evidencias y alcance

| Validación | Resultado |
|---|---|
| Revisión visual y de geometría | **164 comprobaciones**: 41 rutas o estados en 1440, 768, 390 y 320 px. Sin desbordamiento horizontal de página, colisiones de texto detectadas, recursos de imagen rotos ni botones visuales sin nombre en la pasada final. Las tablas anchas conservan desplazamiento propio. |
| Matriz Chromium y WebKit | **298 aprobadas**: 288 transiciones de navegación/pestaña medidas en **0,5 s** de entrada y de salida, ocho comprobaciones de catálogo/bolsa y dos de movimiento reducido. |
| Compatibilidad adicional | Fundido alternativo de navegación y pestaña en ambos motores, retirada de la capa visual y desactivación de fundido por preferencia de movimiento. |
| Regresión funcional | **36 escenarios aprobados**: 18 en Chromium y 18 en WebKit, con registro, perfil, personalización, bolsa, pedido, seguimiento, diseño con fotos y administración. |
| Suite del proyecto | **57 pruebas y 366 subcomprobaciones aprobadas**. |
| Catálogo limpio | **8 de 8 productos con imagen** en la instalación limpia. En la copia de pruebas, **9 de 9**, incluida la foto que ya existía. |

Se incluyen capturas por tamaño, láminas visuales, la matriz de transición, los prompts del catálogo y resultados de las regresiones. Los valores de `0,5 s` corresponden a la duración de ambas animaciones, no al tiempo de red ni al tiempo total de cargar la vista. La mediana observada de la animación local fue de aproximadamente 512 ms, incluyendo el inicio y cierre de los fotogramas.

La comprobación combinó observación en Browser, capturas a 1440, 768, 390 y 320 px, análisis de geometría de texto e iconos y medición de animaciones en Chromium y WebKit. El inventario incluye vistas públicas, área de cliente, panel y diferencias de administrador/root, expedientes, acceso y recuperación. El 404 se provocó con una ruta inexistente; los demás errores se reprodujeron con sus plantillas y códigos HTTP en condiciones controladas.

Los tamaños se probaron con emulación de pantalla y no sustituyen pruebas en teléfonos físicos. El alcance visual corresponde a las rutas y estados inventariados, con datos ficticios; contenidos futuros o colores personalizados pueden requerir revisión. No se realizó publicación ni despliegue.
