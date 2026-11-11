# TIPS v6.5.1 — Revisión visual y funcional entre roles

Fecha: 10 de noviembre de 2026. Revisión solicitada después de ver la grabación de pantalla del usuario. Se trabajó exclusivamente en localhost con una base ficticia independiente. No se desplegó ni se modificó producción.

## Resultado del rediseño

Todas las secciones administrativas usan ahora el mismo shell del panel editorial anterior: sidebar verde, fondo marfil, tipografía coherente, iconos, cabecera y separación uniforme entre contenidos. La sección activa tiene un fondo claro de alto contraste, indicador lateral y `aria-current="page"`. La cabecera también indica la sección. Ya no se alternan dos paneles visualmente distintos al abrir módulos antiguos y nuevos.

Se reorganizaron el resumen, tarjetas, filtros, tablas, expedientes y fotos. En móvil la sidebar se abre como menú y se cierra al navegar. En tablet se retiró la búsqueda de la cabecera para evitar que compitiera por espacio con la identidad y las notificaciones; los reportes usan tarjetas de dos columnas e importes adaptados al espacio disponible. La búsqueda administrativa de escritorio se presenta honestamente como búsqueda de productos por nombre o SKU, que es la función que realiza.

Se retiró el desvanecimiento forzado de la administración: el código anterior ocultaba la página e interceptaba los enlaces con un retraso artificial al navegar. No se afirma haber reproducido un fallo permanente de Safari; la grabación mostraba el cambio entre layouts y un momento de pantalla vacía durante navegación. Las páginas públicas conservan su sistema de movimiento.

## Pruebas directas mediante Browser

Se utilizó el Browser integrado, con formularios, clics y selección real de archivos. No se sustituyeron estas operaciones por inserciones en la base.

### Diez cuentas independientes

Cuentas ficticias `cliente010@tips.test` a `cliente019@tips.test`. Son diez identidades distintas del dataset aislado, no diez sesiones de la misma cuenta. Cada una:

1. Inició sesión y consultó su cuenta; guardó cambios de perfil.
2. Buscó y abrió un producto, seleccionó personalizaciones y cantidad.
3. Confirmó un pedido sin pago y abrió el seguimiento persistido.
4. Envió una solicitud de diseño con dos fotografías y consultó su expediente.
5. En las cuentas 2–10, guardó y recuperó un borrador después de recargar antes de enviar. La primera cuenta también completó su envío con dos imágenes.
6. Cerró sesión para pasar a la siguiente cuenta.

Después de los cambios administrativos se volvió a entrar como los diez clientes. Se comprobó el estado guardado del pedido, el avance del diseño, las dos fotos, los avisos y la apertura de su expediente desde una notificación. En las diez cuentas se intentó abrir un pedido ajeno sin token: el acceso se denegó. Las notas internas no aparecieron en las diez vistas de cliente.

| Cliente | Pedido creado por Browser | Estado final comprobado por el cliente | Solicitud creada por Browser | Estado final comprobado |
|---|---|---|---|---|
| 01 | TIPS-B1CB19B53869 | Retirado | DIS-9438F2B663D4 | Atendido |
| 02 | TIPS-A1B60E0F6868 | Retirado | DIS-5B736B2534D7 | Requiere información |
| 03 | TIPS-54A76CCB1E85 | Listo para retirar | DIS-CB9A14F1034B | En revisión |
| 04 | TIPS-B2303C2C2287 | En preparación | DIS-09F4A23C5B6F | Atendido |
| 05 | TIPS-BD1E47CA8D65 | Retirado | DIS-FE5AC06B1126 | Requiere información |
| 06 | TIPS-AD6F7301C8A9 | Cancelado | DIS-8E952E6DFEC8 | En revisión |
| 07 | TIPS-4A4B5E207B3F | Cancelado | DIS-ACA49E6B2043 | En revisión |
| 08 | TIPS-425B50BA1D33 | En preparación, tras corrección justificada | DIS-A9A4785C1E2E | Requiere información |
| 09 | TIPS-2459DC258369 | Retirado | DIS-136E745254A9 | En revisión |
| 10 | TIPS-7D02F24AC229 | Listo para retirar | DIS-DE9E36733412 | En revisión |

Los identificadores y estados se contrastaron posteriormente mediante lectura de SQLite. Los 20 archivos de estos expedientes permanecen vinculados a su solicitud y cuenta correctas. La base también recibió registros adicionales de las suites automatizadas; las cantidades globales de las capturas pueden superar las del dataset inicial.

### Una administradora

Se inició sesión como `admin@demo.com` y se realizaron acciones reales desde la interfaz:

- Gestión de los diez pedidos: confirmación, preparación, listo, retiro y cancelaciones en etapas distintas.
- Gestión de los diez diseños, consulta de sus 20 fotos, notas internas, observaciones y fechas.
- Registro de un cobro presencial ficticio de $97.80, separado del avance operativo.
- Corrección de Listo a Preparación con motivo obligatorio, conservando el historial.
- Guardado del perfil administrativo y recarga para comprobar persistencia.
- Alta de un producto ficticio; fotografía, texto alternativo, cambio de precio a $19.50 y stock a 21; consulta posterior de inventario.
- Edición de un proyecto y creación de una promoción de prueba.
- Guardado de apariencia, contenido del inicio y contacto del sitio.
- Consulta de clientes y apertura de su historial combinado.
- Navegación del calendario entre meses; reportes con período y descarga real de CSV.
- Apertura de un expediente desde la campana. Se comprobó que esta cuenta no muestra el botón de creación de usuarios reservado a root.

### Root

Se utilizó `root@demo.com`, configurado previamente solo en la base ficticia de QA. No se cambió la contraseña de una cuenta real ni se afirmó probar el primer cambio obligatorio mediante Browser.

Root creó una cuenta ficticia, la desactivó y reactivó, comprobó la vista protegida de su propia cuenta, guardó su perfil y gestionó un pedido y un diseño de los clientes anteriores. El correo raíz permanece readonly en la interfaz y protegido también en la API mediante una prueba de regresión.

Se recorrieron las 14 secciones administrativas como root en 1440×900, 768×1024 y 390×844: **42 comprobaciones de navegación y diseño**. En cada una se comprobó contenido, una única sección activa y ausencia de desbordamiento horizontal. Se abrió un expediente en tablet y se interactuó con el menú móvil; el menú se cerró tras navegar. Estas comprobaciones de páginas no se presentan como 42 flujos comerciales completos.

## Regresión automatizada complementaria

| Comprobación | Resultado |
|---|---|
| Suite Python, HTTP, seguridad y estructura | **57 pruebas aprobadas; 320 subcomprobaciones aprobadas** |
| Chromium: seis escenarios en cada uno de los tres formatos | **18 aprobados, 0 fallidos** |
| WebKit: los mismos escenarios en los tres formatos | **18 aprobados, 0 fallidos** |
| Desbordamientos en las últimas pasadas completas | **0 detectados** |
| Integridad SQLite y claves foráneas del entorno QA | **Correctas** |

Los 36 escenarios automatizados incluyen registro nuevo, máscara telefónica, edición del perfil, carrito y personalización, pedido y seguimiento, borrador y dos fotografías, gestión de estados entre contextos de cliente/admin, módulos administrativos, notificaciones y cierre de sesiones. Se adjunta la suite repetible `tests/e2e_v65.py`, que admite `TIPS_TEST_ENGINE=chromium` o `webkit` y solo destinos localhost.

WebKit es una comprobación adicional del motor relacionado con Safari; **no equivale a una certificación en la aplicación Safari ni en dispositivos físicos**.

## Errores encontrados y corregidos

| Problema | Corrección |
|---|---|
| Dos layouts administrativos y ausencia de sección activa en el panel nuevo | Un shell compartido y estado activo accesible en todas las secciones y expedientes. |
| La sección contextual de un expediente podía marcar Resumen | El shell identifica Pedidos, Diseño o Clientes según la ruta y sus parámetros. |
| El cambio de pestaña del historial de un cliente perdía su filtro | Se conserva `client` al cambiar entre pedidos y diseño. |
| El perfil admin no enviaba teléfono/prefijo requeridos | Formulario y solicitud completos; guardado y recarga comprobados con admin y root. |
| Uso de `event.currentTarget` después de `await` en cuenta administrativa | Referencia estable al formulario antes de esperar la respuesta. |
| Clientes agregados por correo y estadísticas dependientes de un listado limitado de pedidos | Relaciones y agregados reales por `user_id`, sin depender de un correo mutable ni del límite de 200 pedidos de compatibilidad. |
| La protección del correo root no estaba en la nueva API de perfil | Protección restaurada en backend y prueba de rechazo explícita. |
| Actividad reciente sin fecha de creación en su consulta | Selección de fechas reales y presentación con hora de El Salvador. |
| Avisos distintos según el módulo abierto | Campana persistente compartida y lectura individual en todas las páginas administrativas. |
| Guardado del texto alternativo de fotos poco claro | Botón explícito de guardado y confirmación; se repitió la operación y se verificó su persistencia. |
| Corrección de estado basada en un prompt del navegador | Formulario visible con motivo, confirmación, validación y preservación de eventos. |
| Responsables mostrados como números y versión técnica visible | Nombres de responsables, fechas legibles y eliminación de la versión interna del texto de usuario. |
| Falta de espacio en cabecera e importes de tablet | Cabecera simplificada y tarjetas/importes adaptados; capturas finales revisadas. |
| Transición administrativa que ocultaba la página | Navegación directa sin el desvanecimiento forzado. |
| Caché podía conservar recursos de una versión anterior | Recursos actualizados identificados con la versión de esta entrega. |

## Regresión adicional de fotografías del catálogo

Al cargar desde administración una fotografía real de producto se detectó un bucle del observador de cambios del modal público. Se corrigió para modificar clases y atributos solo cuando cambian, identificar el producto por su ID y limpiar la imagen anterior al cambiar de producto.

Después de la corrección se completó desde Browser el pedido `TIPS-07E46D277BE1` por $19.50 del producto creado y editado por administración, y se abrió su seguimiento persistido. Además, `tests/e2e_product_photo.py` aprobó seis recorridos: Chromium y WebKit en 1440×900, 768×1024 y 390×844. Cada recorrido verificó fotografía cargada, precio actualizado, cambio a otro producto sin arrastrar la foto, carrito, confirmación y seguimiento. Resultados y capturas en `fotografias/`. Estas seis comprobaciones complementan los 36 escenarios automatizados anteriores.

## Evidencia e integridad

`Browser-10-clientes-admin-root.json` contiene los expedientes específicos, sus relaciones y los estados contrastados. El pedido 106 liberó su reserva al cancelar antes de preparación; el 107 mantuvo consumidos sus materiales al cancelar después. El cobro del pedido 101 sumó exactamente 9780 centavos. `foreign_key_check` no devolvió incidencias e `integrity_check` devolvió `ok`.

Se incluyen capturas de antes/después, las pasadas Chromium y WebKit, el CSV descargado desde Browser y los resultados de pruebas. No se distribuyen la grabación personal del usuario ni las capturas de sus otras pestañas.

## Actualización y límites

El ZIP contiene el proyecto completo v6.5.1. Esta revisión no añade una migración de esquema respecto a v6.5: actualiza código, consultas y recursos de interfaz. Para actualizar desde v6.4 se mantienen las migraciones aditivas documentadas en `docs/v6.5/DESPLIEGUE.md`. Conservar la base y sus claves, respaldar antes de actualizar y ensayar con una copia. El paquete desplegable excluye bases, imágenes generadas por QA y credenciales del entorno de pruebas.

El envío SMTP real y la recepción de WhatsApp no se probaron; los avisos internos sí. WhatsApp sigue siendo un enlace para envío manual. No se ejecutó despliegue productivo, estrés prolongado ni certificación en hardware móvil. Los cambios/recuperación de contraseñas se cubren por HTTP; no se afirma haber cambiado la contraseña de root desde Browser. Se realizaron los recorridos descritos, no una demostración de todas las combinaciones posibles de cada control.
