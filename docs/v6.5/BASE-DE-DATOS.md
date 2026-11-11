# Base de datos — TIPS v6.5

SQLite con claves foráneas, WAL, timeout y transacciones `BEGIN IMMEDIATE`. Migración idempotente y aditiva en `backend/operations.py:migrate`, invocada desde `DatabaseManager.initialize`. Antes de la primera migración de una base anterior se genera `<base>.pre-v65.bak` mediante la API de backup de SQLite. No sustituye el respaldo externo del operador.

## Campos añadidos

| Tabla | Campos |
|---|---|
| users | phone cifrado, country_code, contact_preferences (internal/email/whatsapp). |
| orders | operational_status, requested_pickup, confirmed_pickup, notes cifradas, tracking_hash, version. |
| quote_requests | user_id FK, phone cifrado, email, public_id único, operational_status, tracking_hash, due_at, version. |

`orders.status` y `quote_requests.status` conservan el valor histórico por compatibilidad del esquema. Los consumidores actuales deben usar `operational_status`, expuesto como `status` en las APIs operativas. Los pedidos nuevos usan un marcador técnico histórico `pending_payment` en la columna antigua; **no expresa obligación de pagar** y nunca gobierna el nuevo flujo. Las tablas payments/refunds/attempts/webhooks se conservan; el nuevo pedido no crea pagos.

Mapeo histórico de pedidos: paid → confirmed; processing y ready se mantienen; shipped/completed → completed; cancelled/expired/refunded → cancelled; demás → received. Cotizaciones: contacted → reviewing; qualified/closed se mantienen; archived → cancelled; new → received. No se inventan eventos históricos previos a la migración.

## Tablas nuevas

- `operation_events`: tipo y registro, actor FK, estado anterior/nuevo, observaciones y fecha. Historial acumulativo.
- `request_keys`: propietario + clave + modalidad como clave primaria; huella del contenido y respuesta. Garantiza reintento coherente sin volver a descontar stock.
- `notifications`: destinatario FK, clave de evento única por usuario, título y enlace.
- `notification_reads`: lectura individual por usuario y notificación.
- `notification_outbox`: intención durable por tipo/registro/versión; intentos, último error y fecha de reparto.
- `email_outbox`: aviso por correo opcional, intentos y fecha de envío; una entrada por notificación.
- `auth_mail_outbox`: recuperación de acceso con contenido cifrado y caducidad.
- `design_drafts`: un borrador por propietario, contenido cifrado y caducidad; fuera de estadísticas comerciales.
- `design_uploads`: ID aleatorio, propietario, cuenta, solicitud FK, nombre, MIME detectado, bytes esperados/recibidos, original BLOB, miniatura, estado completo y caducidad temporal.
- `manual_receipts`: pedido FK, importe firmado en centavos, medio, motivo, responsable FK, clave única y fecha. Ajustes negativos conservan el evento original; el saldo debe quedar entre cero y el total.
- `schema_versions`: versión aplicada y fecha.

Los eventos tienen referencia polimórfica (tipo + ID); sus inserciones se realizan junto con el registro real en transacciones. Las fotos enviadas tienen FK explícita a la solicitud. No se enlazan cuentas mediante teléfonos o nombres coincidentes.

## Estados e inventario

Pedidos: received → confirmed → processing → ready → completed; cancelled desde cualquier etapa previa al retiro. Correcciones controladas: confirmed → received y ready → processing, con motivo obligatorio y evento nuevo. No se borra el historial.

Diseño: received → reviewing → needs_info/qualified; needs_info → reviewing; qualified → closed o reviewing. Cancelación antes del cierre. `needs_info` solicita información y conserva el contacto para que la asistente continúe la conversación; no se incorpora mensajería externa automática.

Al crear el pedido se agrupan cantidades por variante y se descuentan unidades disponibles una sola vez. La reserva no expira por falta de pago. Al comenzar preparación se consume. Cancelar libera solo reservas aún `reserved`; no devuelve automáticamente unidades ya consumidas. El inventario administrativo expresa unidades disponibles, excluyendo reservas activas.

## Índices

Se conservan los índices históricos de catálogo, sesiones, reservas y pedidos por cuenta. Se añaden índices de pedidos por estado/fecha confirmada, diseño por cuenta/ID y estado/fecha, número público de diseño único, eventos por tipo/ID, adjuntos por solicitud y notificaciones por destinatario/ID. Los listados nuevos se paginan a 30 registros. Los endpoints administrativos heredados conservan su límite de compatibilidad de 200; la interfaz nueva usa `/api/ops/records` paginado.

## Conservación

Borradores y cargas no enviadas caducan a los 7 días; se ocultan al vencer y se purgan al iniciar una nueva carga. Las fotos vinculadas a expedientes no se purgan por esa caducidad. Pedidos, solicitudes, claves de reintento, eventos y cobros no tienen borrado automático. Debe establecerse una política de conservación del negocio antes de una eliminación masiva. No se implementó borrado destructivo de históricos.

Los tokens de seguimiento tienen 32 bytes aleatorios; se guarda SHA-256. Los invitados deben conservar el enlace privado; los clientes registrados también acceden mediante su sesión. Las claves de reintento incluyen la respuesta privada en la base protegida, sin endpoint público de listado.

## Dataset y reinicio

```sh
python scripts/generate_test_data.py --output test-data/tips-test.db
python scripts/generate_test_data.py --output test-data/tips-test.db --reset
```

Semilla 650; 200 clientes nuevos más 23 cuentas locales heredadas, 100 pedidos y 100 solicitudes, variantes, personalizaciones, 100 fotografías sintéticas, 400 avisos, 535 eventos y actividad administrativa. Incluye fixtures rotulados de condiciones límite; los rechazos reales se ejecutan en la suite HTTP. Fechas distribuidas, estados distintos y relaciones comprobadas. La reproducibilidad corresponde a los datos funcionales; hashes de contraseñas y cifrados conservan aleatoriedad de seguridad.

Cuenta de ambas modalidades: cliente000@tips.test / SoloPruebas2026!. Base exclusivamente ficticia, distribuida aparte del proyecto desplegable.
