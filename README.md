# Tips — tienda digital y portafolio

Aplicación full-stack de Tips Arquitectura, Diseño y Productos desarrollada con HTML, CSS y JavaScript puros, Python (biblioteca estándar) y SQLite.

## Probar la versión actual

Desde la carpeta del repositorio en VS Code:

```powershell
git pull
.\.venv\Scripts\Activate.ps1
python app.py
```

Abre `http://127.0.0.1:8000`.

Si ya tienes el servidor abierto cuando haces `git pull`, detenlo con `Ctrl+C` y vuelve a ejecutar `python app.py`.

SQLite se crea automáticamente en `data/tips.db`. En una base vacía se cargan productos y proyectos de demostración para poder probar los flujos.

## Pantallas disponibles

- `/` — inicio editorial basado en los wireframes de Tips.
- `/tienda.html` — catálogo dinámico, filtros, búsqueda, ordenamiento y vista rápida.
- `/arquitectura.html` — portafolio filtrable, servicios y proceso.
- `/proyecto.html?id=1` — ficha detallada de proyecto.
- `/contacto.html` — solicitud de cotización guardada en SQLite.
- `/cuenta.html` — registro e inicio de sesión con email/contraseña.
- `/checkout.html` — checkout de prueba; exige una cuenta iniciada.
- `/admin/` — dashboard protegido para administradores.

El carrito aparece como panel lateral y solo ocupa la pantalla completa cuando el usuario lo solicita o entra al checkout.

## Crear las dos cuentas administradoras

No existe registro público de administradores. Crea cada cuenta desde la terminal:

```powershell
python scripts/create_admin.py
```

Introduce correo, nombre y una contraseña de al menos 12 caracteres. Luego inicia sesión en `/cuenta.html` y abre `/admin/`.

## Estructura de vistas

El frontend está organizado por responsabilidad:

```text
frontend/
  global/             # Marca y utilidades visuales compartidas (css/ y js/)
  admin/              # Panel administrativo: vistas/, css/ y js/
  usuario/            # Experiencia del cliente: css/, js/ y vistas/
    vistas/publicas/  # Inicio, catálogo, cuenta, checkout y portafolio
    vistas/cuenta/    # Resumen, datos personales, pedidos y seguridad
```

`backend/` conserva los servicios Python; `sql/`, `scripts/` y `tests/` mantienen sus responsabilidades. Los logos y medios permanecen en `assets/` para conservar rutas guardadas en SQLite.

El servidor mantiene las URLs `/`, `/tienda.html`, `/admin/` y `/user/`, mediante `backend/frontend_paths.py`. Las rutas físicas de las vistas no son accesibles desde el navegador. Los estilos de cada contexto se sirven desde una única hoja canónica; las capas visuales antiguas fueron eliminadas para evitar mezclas entre diseños.

Consulta [el registro de reorganización y UX](docs/reorganizacion-fofo.md) para ver todos los movimientos, motivos, límites y validaciones.

Ambos administradores tienen el mismo rol y permisos base.

## Pago

El checkout actual utiliza el proveedor `mock`. Sirve para probar carrito → autenticación → datos de envío → pedido → pago simulado → actualización de inventario → dashboard, pero **no procesa tarjetas reales**.

La integración real se conectará cuando se defina la pasarela de pago. La moneda del sistema es USD.

## Autenticación

Actualmente funciona email + contraseña segura con PBKDF2 y bloqueo temporal después de intentos fallidos. La arquitectura de base de datos ya contempla OAuth; el botón de Google se muestra como próximo paso porque todavía faltan las credenciales OAuth del proyecto. 2FA administrativo también queda para la etapa de integración.

## Seguridad implementada en la base actual

- CSRF por sesión para operaciones de escritura.
- CORS restringido.
- Cookies de sesión HttpOnly y SameSite.
- Contraseñas con PBKDF2-HMAC-SHA256 y salt aleatorio.
- Bloqueo temporal después de intentos fallidos de acceso.
- SQL parametrizado y claves foráneas SQLite.
- Rate limiting.
- CSP, X-Frame-Options, nosniff y otras cabeceras defensivas.
- Bloqueo del acceso web a `backend`, `data`, `sql`, `tests`, `.git` y `.github`.
- Validación de tamaños y tipos de JSON.

Antes de un despliegue público se debe completar la pasarela, HTTPS, almacenamiento de imágenes, Google OAuth/2FA, backups y revisión de seguridad de producción.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

Las regresiones de los formularios de usuario también se pueden ejecutar con Node.js, sin instalar paquetes:

```bash
node --test tests/test_user_area.cjs
```

Node.js solo se usa para estas pruebas; iniciar la aplicación sigue requiriendo únicamente Python.

GitHub Actions ejecuta compilación y pruebas automáticamente al hacer `push` a `tips`.

## Flujo Git + VS Code

Para recibir cambios hechos en GitHub:

```powershell
git pull
```

Para subir tus cambios desde VS Code:

```powershell
git add .
git commit -m "Descripción corta del cambio"
git push
```

Git conserva el historial, por lo que no necesitas crear carpetas o archivos `v1`, `v2`, `final`, etc.

## Estado funcional

La versión actual permite probar la mayoría del recorrido público: catálogo, búsqueda, carrito, cuenta, compra simulada, portafolio y cotización. El dashboard ya muestra métricas, pedidos, cotizaciones e inventario real de SQLite y presenta en navegación todos los módulos definidos para v1. Los CRUD completos de cada módulo administrativo, carga real de imágenes/logos, Google OAuth, 2FA, promociones avanzadas, reportes completos y pasarela real son las siguientes capas de implementación.

## Arquitectura orientada a objetos y autodocumentación

La aplicación usa una arquitectura orientada a objetos sin frameworks externos. El ciclo de vida se concentra en `TipsApplication`; SQLite en `DatabaseManager`; seguridad en `PasswordHasher`, `SessionTokenManager`, `CsrfProtection`, `SecurityPolicy` y `RateLimiter`; y la interfaz HTTP continúa separada en handlers por responsabilidad.

El JavaScript principal del cliente utiliza `ApiClient` y `TipsClientApp` para separar transporte, estado y comportamiento de interfaz. Los módulos Python incluyen docstrings y el frontend incorpora comentarios de propósito por archivo.

La explicación completa de responsabilidades, herencia y compatibilidad está en [`docs/arquitectura-poo.md`](docs/arquitectura-poo.md).



## Diseño editorial estable — v5

La v5 mantiene una sola fuente visual por contexto y corrige el comportamiento de overlays en Safari. Los modales, el carrito y los wizards permanecen anclados al viewport y administran su propio scroll; la animación global nunca transforma `body` ni `html`.

El panel administrativo y el área privada del cliente comparten el dashboard editorial aprobado: sidebar verde profundo, superficies marfil, títulos serif, controles sobrios y tablas de líneas finas. `tests/test_frontend_hygiene.py` impide que regresen selectores de roles mezclados o capas visuales antiguas. Consulta `docs/sistema-visual.md`.
