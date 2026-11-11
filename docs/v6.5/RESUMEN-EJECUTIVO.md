# TIPS v6.5 — Resumen ejecutivo

La plataforma pasa de un checkout dependiente de pago sandbox a la recepción y gestión de pedidos para retirar. Los clientes pueden solicitar productos sin pagar en línea, conservar su seguimiento privado y consultar pedidos y servicios de diseño desde su cuenta.

El centro administrativo reúne estados, expedientes, fotografías, compromisos y avisos. Las administradoras pueden preparar y entregar pedidos, controlar fechas, registrar cobros presenciales o externos y corregir determinados estados sin borrar el historial. Los importes solicitados se presentan separados de los cobros registrados.

Las solicitudes de diseño incorporan teléfono internacional, autocompletado, descripción extensa, fotografías privadas con miniaturas, cargas por bloques y borradores de siete días. La página pública utiliza la denominación servicios de diseño y una presentación fotográfica que conserva la identidad de TIPS.

La actualización conserva los datos financieros históricos mediante una migración aditiva y un respaldo previo. No obliga a activar 2FA, no introduce servicios de pago y no modifica producción.

## Validación local

- **55 pruebas Python aprobadas y 302 subcomprobaciones de rutas/recursos aprobadas.**
- **18 escenarios de navegador aprobados**, repartidos entre escritorio 1440 × 900, tablet 768 × 1024 y teléfono 390 × 844.
- Flujos conectados entre cliente y administradora, inventario, cancelaciones, doble envío, concurrencia, privacidad de fotos y notificaciones con fallo/reintento.
- Imagen válida de más de 4 MiB cargada por bloques y recuperada íntegra.
- Dataset independiente: **223 usuarios ficticios, 100 pedidos y 100 solicitudes**, con 100 fotografías y actividad asociada.
- 200 consultas locales de dashboard: todas correctas; p95 18.21 ms con 8 consultas concurrentes. Esta medición breve no garantiza capacidad de producción.

## Antes de usarla en producción

Ensayar la actualización con una copia de la base real, conservar sus claves de cifrado, revisar cuentas demo históricas y validar el despliegue HTTPS existente. El envío SMTP real, la recepción de correo y la carga sostenida del hosting siguen pendientes. WhatsApp abre un mensaje para envío manual.

Se entrega el proyecto completo con instrucciones, pruebas y generador. La base ficticia y las capturas se distribuyen separadas para evitar que se utilicen como datos reales. El informe de pruebas distingue ejecución automatizada, revisión visual y limitaciones; no presenta como aprobadas las pruebas externas que no se hicieron.
