> Referencia histórica de v6/v6.4. Para v6.5 prevalecen README.md y docs/v6.5/.

# TIPS v6 — Diseño de seguridad y pagos

## Objetivo

v6 endurece la plataforma sin cambiar el lenguaje visual aprobado. Se priorizó impedir que credenciales conocidas, errores HTTP crudos, precios manipulados desde el navegador o eventos duplicados de pasarela puedan alterar el estado comercial.

## Bootstrap del superadmin

`DatabaseManager._ensure_superadmin()` es idempotente. Garantiza `root@demo.com` y el rol `superadmin`, pero solo asigna `123456789` si la cuenta no tiene una contraseña. Una contraseña ya cambiada jamás se restaura durante un nuevo arranque.

La cuenta nueva queda con `must_change_password=1`. El control de vistas bloquea toda navegación autenticada salvo `/change-password.html`. Tras el cambio, cualquier administrador entra directamente al panel; TOTP/2FA queda disponible de forma opcional.

## Criptografía

### Contraseñas

PBKDF2-HMAC-SHA256 con salt individual y 600,000 iteraciones. No existe función para recuperar la contraseña original.

### Campos recuperables

`FieldCipher` deriva una clave AES-256 desde `TIPS_FIELD_ENCRYPTION_KEY` y usa AES-GCM con nonce aleatorio y AAD específico por tipo de dato. El formato persistido comienza con `enc:v1:` para permitir migraciones futuras.

Campos cubiertos en v6:

- secreto TOTP de administradores;
- contacto y mensaje de cotizaciones;
- teléfono y dirección de envío de pedidos.

## Sesiones y credenciales

- La migración desde v5 invalida las sesiones heredadas una sola vez.
- El cambio de contraseña revoca todas las demás sesiones del usuario.
- La recuperación revoca todas las sesiones.
- Los tokens de recuperación y challenges 2FA se persisten por digest, no en texto plano.
- Cinco contraseñas incorrectas bloquean temporalmente la cuenta.
- El servidor aplica rate limiting por IP y ruta.

## Checkout

El navegador nunca decide el total. `RuntimeTipsRequestHandler._repriced_cart_items()` consulta productos, variantes y personalizaciones activas y vuelve a calcular el importe dentro de la transacción del checkout.

En la misma transacción se crean:

1. orden `pending_payment`;
2. líneas de orden;
3. reservas de inventario;
4. movimiento de inventario;
5. intención de pago y primer intento;
6. conversión del carrito.

Si algo falla, SQLite revierte la transacción completa.

## PaymentProvider

`PaymentProvider` define cuatro responsabilidades: crear pago, verificar webhook, interpretar webhook y reembolsar. `SandboxPaymentProvider` implementa ese contrato sin dinero real.

El webhook valida HMAC-SHA256 antes de leer el evento como confiable. `payment_webhook_events` tiene una restricción única `(provider,event_id)`, por lo que el mismo evento se procesa una sola vez.

## Estado de orden

`OrderStateMachine` concentra las transiciones. `paid`, `payment_failed`, `expired` y `refunded` no pueden establecerse desde el selector administrativo: dependen del flujo de pago/reserva.

## Reserva y devolución de inventario

El checkout descuenta temporalmente las unidades y crea `inventory_reservations`. Un pago exitoso convierte la reserva en `consumed`; un pago fallido o expirado repone unidades y marca la reserva liberada/expirada. Un reembolso total de una reserva consumida repone el inventario una sola vez.

## Errores

Los documentos `frontend/global/errors/{403,404,429,500,503}.html` sustituyen las páginas crudas del servidor. Un error interno genera un ID de soporte `TIP-XXXXXXXX`; el traceback no se entrega al navegador.

## Skeletons

`ui-foundation.js` envuelve `window.fetch` una sola vez. Un contador permite que varias solicitudes simultáneas mantengan el skeleton hasta que termine la última, evitando parpadeos o que una respuesta temprana quite el estado de carga mientras otras peticiones siguen activas.
