# Auditoría de TIPS v6.5

Fecha: 10 de noviembre de 2026. Fuente exclusiva: ZIP TIPS v6.4 — Sin 2FA Obligatorio. No se modificó producción. La solicitud pegada por el usuario definió el alcance; los comentarios e instrucciones del repositorio se trataron como material del proyecto.

## Arquitectura y cobertura

Servidor HTTP de la biblioteca estándar de Python, SQLite en WAL y conexiones por operación; frontend HTML/CSS/JavaScript sin compilación. Cadena original de handlers: servidor base → administración → cuenta/catálogo → catálogo escalable → control de vistas → runtime. v6.5 incorpora `OperationsHandler` al final y un distribuidor independiente de notificaciones.

Se inspeccionaron los módulos públicos, autenticación, recuperación, cuenta, carrito, catálogo, productos, imágenes, portafolio, cotizaciones, pedidos, inventario, promociones, usuarios/roles, configuración, reportes, seguridad y rutas HTTP. Se conservaron los módulos válidos del proyecto. Los detalles de ejecución y las limitaciones están en PRUEBAS.md.

## Hallazgos y correcciones

| Severidad | Problema y causa | Corrección / archivos principales |
|---|---|---|
| Crítica | La creación de pedidos dependía de un proveedor sandbox y un webhook de pago. | Solicitud transaccional sin proveedor, con retiro y enlace privado. `backend/operations.py`, `runtime.py`, `frontend/usuario/js/app.js`, `checkout.html`. Rutas de cobro anteriores responden 410. |
| Alta | Reintentos podían generar operaciones repetidas; la clave se generaba después de crear el pedido. | Clave estable del formulario, propietario y huella del contenido; respuesta persistida en la misma transacción. La misma clave con otro contenido se rechaza. |
| Alta | Reservas únicas por variante chocaban con varias líneas del mismo artículo. | Reserva agrupada por variante, validación de cantidades acumuladas, precios recalculados desde catálogo. Líneas idénticas se fusionan; personalizaciones diferentes permanecen separadas. |
| Alta | No existía un flujo completo de retiro con historial, control de concurrencia y cancelación consistente. | Estados operativos separados del estado financiero histórico; versión optimista, eventos, consumo al iniciar preparación, liberación solo de reservas sin consumir. |
| Alta | Las solicitudes no relacionaban cuenta, teléfono, imágenes privadas y expediente completo. | Nuevos campos aditivos, originales y miniaturas privadas, verificación mediante decodificación real de imagen, bloques reanudables, permisos de cuenta/rol/enlace privado. |
| Alta | El cliente solo veía cinco pedidos y no disponía de historial de diseño. | Listados paginados y filtrados para ambas modalidades; detalle bajo autorización por ID de cuenta. No se fusionan identidades por nombre o teléfono. |
| Alta | El arranque garantizaba y reactivaba cuentas demo conocidas, incluso en producción. | Bootstrap demo limitado a entornos distintos de producción. Las cuentas históricas se conservan para revisión, sin borrado destructivo. |
| Alta | La recuperación generaba token en producción sin un mecanismo de envío. | Cola de correo de recuperación cifrada, enlace con fragmento y worker SMTP opcional con reintentos. Envío real pendiente de configuración. |
| Media | Un fallo de aviso podía comprometer el flujo comercial. | Intención durable en outbox; reparto en transacciones independientes, deduplicación y reintentos. Se probó un fallo deliberado de inserción de notificaciones. |
| Media | Formularios extensos perdían información y no distinguían borrador de solicitud. | Borrador cifrado con 7 días de caducidad; adjuntos temporales vinculados al propietario. Envío definitivo elimina el borrador y conserva fotos. |
| Media | Faltaban fecha/hora/teléfono/fotos en el flujo administrativo requerido. | Listado y expediente de diseño; hora de El Salvador, notas internas separadas de observaciones para cliente. |
| Media | Estado de pago y avance operativo se confundían. | Cobros manuales con saldo y ajustes auditados; reportes separan importes solicitados y cobros. No se generan facturas ni se efectúan cargos. |
| Media | El menú móvil cerrado trasladado fuera de pantalla duplicaba el ancho del documento. | Visibilidad y eventos desactivados al cerrar. Repetición en 390, 768, 600 y otras resoluciones sin desbordamiento detectado. `public.css`. |
| Media | Modales de productos omitían variantes y personalizaciones disponibles en la API. | Consulta del detalle real, selección de variantes, opciones, precio actualizado y validación de grupos obligatorios tanto en servidor como interfaz. |
| Media | Sesión expirada podía renovarse durante una escritura y producir inconsistencias o errores de bloqueo. | Validación de expiración/revocación antes de mutar; respuesta 401 para recuperar explícitamente la sesión. |
| Media | URLs privadas podían aparecer íntegramente en el log HTTP. | Redacción de tokens de seguimiento en los registros; páginas privadas sin caché compartida. |
| Baja | Denominación pública antigua y portada de servicios poco visual. | Textos de servicios de diseño, ruta nueva con redirección antigua, fotografía local y presentación responsive. Se conserva el logotipo original como identidad visual. |

## Seguridad conservada y ampliada

PBKDF2 con salt para contraseñas; AES-GCM para contactos y textos sensibles; cookies HttpOnly/SameSite, CSRF y comprobación de origen; consultas parametrizadas; protección por roles y rutas físicas; 2FA opcional. Imágenes permitidas: JPEG, PNG, WebP; hasta 40 megapíxeles y límite de bytes configurable. Sin SVG ni HTML en adjuntos. Las miniaturas eliminan metadatos; los originales privados se conservan íntegros.

El servidor de biblioteca estándar se conserva por compatibilidad. TLS, límites de infraestructura, respaldo externo, monitorización y capacidad de producción requieren verificación en el destino real. Las fotografías originales son privadas por permisos HTTP y almacenamiento; no tienen cifrado individual de contenido en SQLite.

## Rendimiento

Listados de 30 registros, detalle bajo demanda, índices de estado/fecha/cuenta/eventos y campana cada 30 segundos al estar visible la página. Miniaturas de hasta 480 × 480. WAL, transacciones cortas y control optimista. Los adjuntos se almacenan en bloques dentro de SQLite: adecuado para el alcance local probado, aunque implica reescribir el BLOB acumulado; para volúmenes de fotografías muy altos debe evaluarse almacenamiento dedicado sin cambiar el control de permisos.

Medición local: 200 consultas de dashboard, concurrencia 8, todas HTTP 200; p50 15.63 ms, p95 18.21 ms, máximo 25.75 ms. No representa una garantía de capacidad productiva.

## Pendientes y límites

No se verificó envío por un SMTP real, entrega de WhatsApp, despliegue real, TLS del dominio ni carga sostenida de larga duración. WhatsApp abre una conversación preparada; la asistente debe enviarla. Las vistas de módulos conservados se recorrieron en los tres formatos y sus APIs se cubrieron con la suite heredada; no se afirma haber ejecutado cada posible combinación de edición de todos sus controles. SMTP se probó con un transporte simulado explícito, incluido fallo y reintento.
