# Informe de pruebas — TIPS v6.5

10 de noviembre de 2026. Entorno local macOS, Python 3.14.7, SQLite, Chromium 158 mediante Playwright 1.65.0. Cuentas y bases ficticias independientes. Se utilizó también el navegador integrado para abrir e inspeccionar la interfaz. No se utilizaron credenciales reales.

## Resultados ejecutados

| Tipo | Resultado | Evidencia |
|---|---|---|
| Suite Python/HTTP/seguridad/estructura | **55 pruebas aprobadas; 302 subcomprobaciones aprobadas** | `suite-python.txt`, código en `tests/` |
| Navegador con interacciones | **18 escenarios aprobados; 0 fallidos** | `browser-results.json`, `tests/e2e_v65.py` |
| Desbordamiento | **0 incidencias en última pasada** | JSON de navegador; 1440, 768, 390 y anchos intermedios 600, 1000, 1200 |
| Carga local | **200/200 HTTP 200**, concurrencia 8 | `load-results.json` |
| Migración de copia de v6.4, repetida | Registros conservados, FK e integridad correctas, backup generado | `migration-results.json` |
| ZIP extraído de forma independiente | Arranque, recursos y pedido invitado persistido; cero pagos y cero cuentas demo automáticas | `package-smoke.json` |
| Dataset regenerado | 223 usuarios, 100 pedidos, 100 solicitudes, 100 fotos, 400 avisos, 535 eventos | Generador con semilla 650; paquete ficticio separado |

La suite heredada inicialmente presentó seis fallos de expectativas: registro sin teléfono, checkout sandbox, ruta de arquitectura sin redirección y número fijo de hojas CSS. Se actualizaron esos contratos al comportamiento solicitado; no se suprimieron pruebas para conseguir aprobación. La suite completa final pasa. Las primeras ejecuciones HTTP necesitaron habilitar servidores locales y descargar dependencias; esos bloqueos del entorno se resolvieron antes de dar resultados.

## Casos HTTP reales

- Registro, teléfono salvadoreño, normalización internacional, perfil y confirmación de contraseña para cambio de correo.
- Pedido invitado, enlace privado, rechazo sin autorización, clave de reintento y repetición simultánea.
- Precios del servidor, agrupación de reservas, personalizaciones obligatorias y distintas líneas de una variante.
- Dos clientes intentan adquirir la última unidad: una creación 201 y un rechazo 409, sin stock negativo.
- Dos administradoras modifican la misma versión: un éxito 200 y un conflicto 409.
- Secuencia Recibido → Confirmado → Preparación → Listo → Retirado; rechazo de saltos inválidos.
- Cancelación antes de consumo devuelve stock reservado; después del consumo no lo restituye automáticamente.
- Historial paginado con 35 pedidos (30 + 5), calendario, correcciones controladas y saldo de cobros, ajustes negativos y reintento idempotente de cobro.
- Solicitud de diseño vinculada a cuenta, fotos, original íntegro y miniatura; otro usuario no accede.
- Imagen JPEG válida superior a 4 MiB, bloques, original íntegro y miniatura de hasta 480 px.
- Carga por mitades, reenvío de bloque y reanudación; rechazo de archivo falso, demasiado grande y carga ajena.
- Borradores privados, recuperación, caducidad y eliminación tras envío definitivo.
- Fallo deliberado del reparto de avisos: pedido persistido, intento fallido registrado y reparto posterior sin duplicado.
- Notificaciones sin leer, lectura individual y aislamiento entre destinatarios.
- Sesión vencida, CSRF incorrecto, roles, vistas físicas inaccesibles y endpoints de pago retirados.
- Cambio posterior del perfil conserva el nombre/teléfono histórico del pedido.
- Notas internas de diseño no visibles para clientes; historial combinado por cuenta para administración.
- Base productiva nueva sin cuentas demo automáticas.
- Migración con un pago histórico no vacío: valores financieros intactos, estado operativo mapeado y backup.
- Worker SMTP con transporte simulado explícitamente: fallo, reintento, recuperación cifrada y ausencia de reenvío tras confirmación local. **No equivale a correo real entregado.**

El ensayo del ZIP extraído utilizó una base temporal y configuración de producción simulada. Para probar por HTTP local se desactivó Secure exclusivamente en la configuración temporal del ensayo; no se verificó TLS ni se modificó la configuración productiva del proyecto.

Los tests heredados también cubren APIs de productos, configuración, roles, seguridad y utilidades financieras históricas; esas utilidades se conservan para datos anteriores y no están conectadas al nuevo checkout.

## Navegador: resultados por formato y rol

Cada uno de los siguientes seis escenarios se ejecutó en **1440 × 900**, **768 × 1024** y **390 × 844**, dando 18 escenarios aprobados:

1. Páginas públicas, navegación y apertura/cierre del menú adaptable.
2. Registro real con cuenta ficticia y máscara `7123-4567`.
3. Modificación real del perfil y comprobación del resultado.
4. Compra: dos productos, cantidades, variantes/personalizaciones, carrito, autocompletado, registro sin pago y seguimiento privado.
5. Diseño: autocompletado, borrador guardado y recuperado después de recargar, dos fotos, progreso, previsualización, envío y referencia.
6. Administradora en contexto separado: localización del pedido, cambios guardados hasta Retirado y verificación desde cliente; expediente de diseño con dos fotos, cambio a En revisión, compromiso y seguimiento del cliente. Recorrido de dashboard, pedidos, diseño, calendario, reportes, actividad, productos, inventario, proyectos, clientes, promociones, usuarios, configuración y cuenta; búsqueda y campana. Se cerraron las sesiones de cliente y administradora y se comprobó el regreso al acceso.

Las verificaciones de estado esperan el estado devuelto y renderizado después de guardar, no solo la selección local del formulario. Se tomaron capturas de modales y páginas. Los anchos intermedios se verificaron para servicios, tienda y formulario de diseño.

Roles: invitado y cliente cubiertos por HTTP y navegador; admin por ambos; superadmin y controles de seguridad/roles por suite HTTP. No se afirma haber recorrido cada edición administrativa posible como superadmin en los tres formatos.

## Revisión visual y antes/después

Se inspeccionaron capturas de dashboard/tablet, producto/móvil y expediente de diseño/escritorio, además de las capturas automatizadas del conjunto. El menú cerrado generaba anchos de 780 px en un viewport de 390 y 1200 px en uno de 600. Se corrigió la visibilidad real del elemento; la repetición final no detectó desbordamientos.

Evidencia comparativa: `antes-checkout-1440.png` → `checkout-1440.png`; `antes-servicios-1440.png` → `servicios-1440.png`; `antes-producto-390.png` → `producto-390.png`; `antes-servicios-390.png` → `servicios-390.png`.

## Rendimiento e integridad

200 consultas del dashboard con 8 trabajadores sobre la base de más de 100 registros por modalidad: 0.393 s totales; p50 15.63 ms, p95 18.21 ms, máximo 25.75 ms. Prueba local corta, no extrapolable a capacidad de producción. La suite también ejecuta 100 consultas paralelas y comprueba su respuesta.

`PRAGMA foreign_key_check` sin incidencias e `integrity_check=ok` tras escenarios de concurrencia y migración. La base original adjunta no contenía pagos ni pedidos; por eso se añadió una prueba financiera histórica sintética no vacía.

## Limitaciones explícitas

- Pendiente SMTP real, recepción en buzón, filtros antispam y credenciales de despliegue. Ningún correo real fue enviado en las pruebas.
- WhatsApp no se envió: se genera un enlace de conversación para envío por la asistente.
- Viewports de Chromium; no dispositivos físicos ni Safari/Firefox/Windows/Linux.
- Carga breve y local; sin estrés prolongado, caída eléctrica ni prueba de capacidad del hosting.
- Reanudación de carga comprobada por reenvío de bloques; no se simuló cada combinación de caída de navegador/sistema operativo. Para reanudar, el usuario vuelve a seleccionar el mismo archivo; el sistema no recupera archivos locales automáticamente.
- Se verificaron los flujos críticos entre roles y las pantallas conservadas. No se declara exhaustividad de todas las combinaciones de controles del sistema original.
- Pruebas `.cjs` históricas de navegador no ejecutadas como suite independiente; su cobertura relevante se reemplaza por la suite Playwright Python adjunta.
