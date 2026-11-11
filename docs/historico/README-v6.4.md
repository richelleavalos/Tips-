> DOCUMENTO HISTÓRICO. Para desplegar v6.5 utiliza README.md y docs/v6.5/DESPLIEGUE.md.

# TIPS v6.4 — Acceso administrativo sin 2FA obligatorio

Aplicación full-stack de TIPS Arquitectura, Diseño y Productos construida con HTML/CSS/JavaScript, Python y SQLite. v6.4 conserva usuarios demo, alta desde root, bolsa estable, seguridad, pagos y panel unificado; elimina el 2FA obligatorio para administradores y superadmin para que, después del cambio de contraseña temporal, entren directamente a su panel.

## Ejecutar localmente

```powershell
python app.py
```

En desarrollo, si `cryptography` no está instalada, TIPS la prepara automáticamente dentro de `.tips_deps` en el propio proyecto. Esto evita modificar el Python global de macOS. La primera ejecución necesita conexión a Internet. Si prefieres instalar las dependencias manualmente, usa `python -m pip install -r requirements.txt`. En producción la instalación automática está desactivada y las dependencias deben prepararse durante el despliegue.

Abre `http://127.0.0.1:8000`.

La base se inicializa y migra automáticamente en `data/tips.db`. Una base vacía carga los datos demo del catálogo y garantiza la cuenta raíz.

## Superadmin raíz

TIPS garantiza que exista esta cuenta:

- Correo: `root@demo.com`
- Contraseña temporal inicial: `123456789`
- Rol: `superadmin`

La contraseña se guarda **solo como hash PBKDF2-HMAC-SHA256 con salt**. La aplicación no vuelve a restaurarla después de que el superadmin la cambie.

En el primer inicio de sesión, el superadmin queda bloqueado en `/change-password.html` hasta reemplazar la contraseña temporal por una de al menos 12 caracteres. Después entra directamente al panel administrativo; TOTP/2FA queda disponible solo como protección opcional.

> La credencial temporal existe únicamente para bootstrap. Cámbiala inmediatamente al preparar una instalación.

## Seguridad incluida

- Roles `user`, `admin` y `superadmin` con protección del superadmin raíz.
- Contraseñas con PBKDF2-HMAC-SHA256, salt aleatorio y 600,000 iteraciones.
- AES-256-GCM para datos recuperables sensibles: contacto/mensaje de cotizaciones, teléfono/dirección de pedidos y secreto TOTP.
- 2FA TOTP opcional para administradores y superadmin; no bloquea el acceso.
- Tokens de recuperación de contraseña de un solo uso y con expiración.
- Revocación de sesiones anteriores al cambiar credenciales y de todas las sesiones al recuperar contraseña. Al migrar desde v5 también se invalidan las sesiones heredadas una sola vez.
- Bloqueo temporal tras cinco intentos de contraseña incorrectos.
- Rate limiting por IP/ruta, CSRF, CORS restringido y cookies HttpOnly/SameSite.
- CSP, `frame-ancestors 'none'`, X-Frame-Options, nosniff, política de permisos y validación de tamaño de solicitudes.
- Secretos operativos fuera del código en producción.
- SQL parametrizado, foreign keys y constraints de integridad en SQLite.

AES/Rijndael no se usa para contraseñas porque es reversible. Las contraseñas se hashean; AES-256-GCM se reserva para información que TIPS necesita poder recuperar posteriormente.

## Variables de entorno

Copia `.env.example` como referencia. TIPS no carga `.env` automáticamente; define las variables en el entorno, servicio o gestor de secretos que uses.

En `TIPS_ENV=production` son obligatorias:

```text
TIPS_SECRET_KEY
TIPS_FIELD_ENCRYPTION_KEY
TIPS_PAYMENT_WEBHOOK_SECRET
```

La aplicación falla de forma segura si falta alguna. No reutilices la misma clave para sesión, cifrado de campos y firma de webhooks.

## Recuperación de contraseña

`/recuperar.html` crea tokens de un solo uso con expiración. En desarrollo el token se devuelve a la interfaz para poder probar el flujo completo sin depender de un proveedor de correo. En producción **no se devuelve el token**: antes de publicar debe conectarse el canal de entrega (correo/transaccional) elegido para el proyecto.

## Pagos v6

El checkout ya no marca una orden como pagada desde el navegador. El flujo es:

```text
Carrito
  → checkout backend
  → recálculo de precios
  → reserva de inventario
  → Order: pending_payment
  → PaymentProvider
  → webhook firmado
  → pago confirmado
  → Order: paid
```

`PaymentProvider` desacopla TIPS de una pasarela específica. v6 incluye `SandboxPaymentProvider`, que genera eventos HMAC-SHA256 firmados y permite probar el recorrido sin una tarjeta real.

Rutas principales:

- `POST /api/checkout/create` — crea la orden, recalcula el total y reserva inventario.
- `POST /api/payments/sandbox/complete` — simulador de proveedor para desarrollo.
- `POST /api/payments/webhook/sandbox` — webhook sin CSRF; exige firma válida.
- `POST /api/admin/payments/refund` — reembolso administrativo total o parcial.

Los eventos de webhook son idempotentes por `(provider, event_id)`. Un evento repetido no vuelve a ejecutar la operación. Los totales del carrito se recalculan desde la base de datos: el backend no confía en precios enviados por JavaScript.

## Órdenes e inventario

Estados permitidos:

```text
pending_payment
payment_failed
paid
processing
ready
shipped
completed
cancelled
expired
refunded
```

`OrderStateMachine` impide transiciones inválidas y reserva los estados controlados por pago para el flujo de pasarela. Durante checkout se descuenta el inventario como reserva temporal; un pago fallido o una reserva expirada devuelve las unidades. Un reembolso total también repone el inventario una sola vez.

El carrito queda asociado al usuario autenticado y puede recuperarse al iniciar una nueva sesión. Si había un carrito de invitado, TIPS lo fusiona con el carrito activo del usuario.

## Manejo de errores

Las respuestas web ya no muestran la página cruda de `SimpleHTTPRequestHandler`. Existen vistas TIPS para:

- 403 — acceso restringido.
- 404 — recurso inexistente.
- 429 — límite de solicitudes.
- 500 — error interno con referencia `TIP-XXXXXXXX`.
- 503 — servicio temporalmente no disponible.

Las APIs siguen devolviendo JSON y nunca exponen tracebacks, consultas SQL, rutas internas ni variables de entorno.

## UX y skeletons

`frontend/global/css/components.css` y `frontend/global/js/ui-foundation.js` forman la capa compartida de componentes/estados. Cada `fetch()` iniciado por la interfaz muestra un skeleton de carga con contador de solicitudes para evitar pantallas vacías o saltos de contenido.

En v6.2 el panel administrativo usa la misma geometría y tipografía en todas sus pestañas. Los campos, botones, tarjetas, tablas, dropdowns, chips y modales comparten estilos; los logos mantienen dimensiones controladas y ya no pueden crecer según el tamaño intrínseco del SVG.

Las listas principales ya no muestran un botón repetido de “Editar”: productos, proyectos, pedidos, cotizaciones, clientes, promociones, usuarios, ventas e inventario se abren haciendo clic sobre el registro completo, con navegación por teclado incluida.

El gestor de fotos de producto se rehízo como zona de carga visual: acepta selección múltiple o arrastrar y soltar, optimiza JPG/PNG/WebP en el navegador antes de subir, limita a cinco imágenes y muestra la galería en tarjetas. La compresión evita `createImageBitmap` y usa `FileReader` + `Image` + canvas para mejorar compatibilidad con Safari.

Los modales y wizards quedan anclados al viewport y gestionan su propio scroll, incluido Safari. Las vistas conservan estados `loading`, `empty`, `error` y `success`.

## Pantallas principales

- `/` — inicio editorial.
- `/tienda.html` — catálogo y carrito.
- `/arquitectura.html` — portafolio.
- `/contacto.html` — cotizaciones.
- `/cuenta.html` — registro/login y desafío 2FA cuando corresponda.
- `/recuperar.html` — recuperación de contraseña.
- `/checkout.html` — checkout con proveedor sandbox.
- `/user/` — área privada del cliente.
- `/admin/` — panel administrativo.
- `/change-password.html` — cambio obligatorio de credencial temporal.
- `/setup-2fa.html` — activación opcional de 2FA administrativo; nunca se fuerza por redirección.

## Estructura

```text
backend/
  application.py       # ciclo de vida
  database.py          # migraciones, DB y bootstrap root
  security.py          # hashes, AES-GCM, TOTP, CSRF y rate limiting
  orders.py            # máquina de estados
  payments.py          # PaymentProvider, webhooks y reembolsos
  runtime.py           # checkout/pagos efectivos
  *_server.py          # capas HTTP
frontend/
  global/               # componentes, errores y utilidades compartidas
  admin/                # panel administrativo
  usuario/              # sitio público y área de cliente
sql/
  schema.sql
  seed.sql
tests/
```

No se mantienen hojas visuales históricas ni scripts duplicados. La base v5 se conserva como línea visual y v6 añade una única biblioteca compartida de componentes.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Y, si tienes Node.js:

```bash
node --test tests/test_user_area.cjs
```

Para comprobar sintaxis Python:

```powershell
python -m compileall -q backend app.py
```

## Antes de producción

El proveedor actual es **sandbox**. Antes de aceptar dinero real hay que implementar un `PaymentProvider` para la pasarela elegida, configurar su secreto real de webhook, usar HTTPS, conectar el canal real de recuperación de contraseña, gestionar claves en un secret manager y ejecutar las pruebas con la configuración de producción.

Consulta `docs/v6-seguridad-pagos.md`, `docs/arquitectura-poo.md` y `docs/sistema-visual.md` para más detalle.


## TIPS v6.4 — acceso administrativo sin 2FA obligatorio

Esta entrega añade datos demo idempotentes y mejora el flujo administrativo de usuarios y la bolsa pública.

- Superadmin demo: `root@demo.com` / contraseña inicial `123456789` (obliga cambio).
- Administrador demo: `admin@demo.com` / `TipsDemo2026!`.
- Usuario demo: `usuario@demo.com` / `TipsDemo2026!`.
- 20 clientes adicionales: `cliente01@demo.com` a `cliente20@demo.com`, todos con `TipsDemo2026!`.
- El botón **Nuevo usuario** aparece solo para `root@demo.com` y permite crear rol Cliente o Administrador. Las cuentas creadas deben reemplazar la contraseña temporal en su primer ingreso; después acceden directamente a su panel.
- La bolsa abre mediante una única ruta de interacción, muestra carga skeleton al refrescar, bloquea correctamente el scroll, conserva foco y usa el mismo comportamiento en Inicio, Tienda y Arquitectura.

> Las credenciales demo son intencionalmente conocidas para pruebas locales. Antes de una puesta en producción deben deshabilitarse o sustituirse por cuentas reales.


### Cambio v6.4

- Se eliminó la redirección obligatoria a `setup-2fa.html`.
- Admin y superadmin pueden entrar al panel sin activar 2FA.
- El cambio de contraseña temporal continúa siendo obligatorio.
- Si una cuenta ya tenía 2FA activado, su desafío de inicio de sesión sigue funcionando; 2FA queda como opción voluntaria.
