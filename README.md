# TIPS v6.7.1 — Pedidos para retiro y servicios de diseño

## Pedidos y base incluida

El ZIP incluye la base principal en `data/tips.db`, con los usuarios anteriores y 150 clientes ficticios adicionales. Cada cliente de muestra tiene un pedido histórico con productos del catálogo. Los pedidos de muestra no consumen inventario actual. Para probar la aplicación en local:

- Correo de cliente: `muestra-001@tips.test` a `muestra-150@tips.test`.
- Clave de muestra: `TipsMuestra2026!`.
- Inicia con `python app.py` y usa la base predeterminada, sin configurar `TIPS_DB_PATH` para otra base. En modo producción se desactivan las cuentas de muestra y se revocan sus sesiones.

Los visitantes pueden guardar la bolsa, el nombre, correo, teléfono y fecha de retiro como borrador. Al entrar o crear una cuenta desde ese flujo, vuelven a revisar y confirmar el pedido. El borrador cifrado y la bolsa se recuperan en el mismo navegador mientras la sesión siga vigente. Guardar el borrador no crea un pedido ni reserva inventario.

La pantalla de inicio de sesión incorpora una imagen de una casa frente al mar generada para TIPS. En escritorio, el registro muestra el formulario a la derecha. En pantallas estrechas, los formularios quedan arriba de su imagen.

Auditoría de diseño: [TIPS v6.6](docs/v6.6/AUDITORIA-DISENO.md).

Proyecto completo basado en TIPS v6.4, con revisión integral v6.5.1.

La revisión v6.5.1 unifica todas las secciones administrativas con el diseño editorial original, identifica la sección activa, corrige el perfil administrativo y los historiales vinculados a la cuenta. Se probaron 10 clientes distintos, una administradora y root mediante Browser; véase [el informe de revisión](docs/v6.5.1/REVISION-INTEGRAL.md). Python + SQLite + HTML/CSS/JavaScript; conserva `python app.py` como punto de entrada. No realiza despliegues ni procesa pagos electrónicos. 2FA sigue siendo opcional.

## Inicio local

```sh
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Abrir http://127.0.0.1:8000. En desarrollo también existe preparación automática de dependencias en `.tips_deps`; la instalación explícita anterior es la opción reproducible. Python 3.10 o superior; probado con Python 3.14.7.

**Este ZIP no incluye ninguna base de datos del proyecto original ni el dataset ficticio.** La instalación nueva crea `data/tips.db` y carga el catálogo base. Para actualizar, conservar la base existente y sus claves, siguiendo [la guía de despliegue](docs/v6.5/DESPLIEGUE.md).

Solo en desarrollo/pruebas se crean las cuentas heredadas `admin@demo.com` y `usuario@demo.com` con contraseña `TipsDemo2026!`, y `root@demo.com` con contraseña temporal `123456789`, que exige cambiarla. En producción no se crean ni se reactivan cuentas demo automáticamente. Las cuentas demo que ya existan en una base anterior requieren revisión administrativa; la migración no las elimina silenciosamente.

## Accesos

- `/tienda.html`: catálogo, variantes, personalizaciones y carrito.
- `/checkout.html`: solicitud de retiro sin pagar en línea, también como invitado.
- `/servicios-de-diseno.html`: servicios y portafolio; `/arquitectura.html` redirige.
- `/contacto.html`: solicitud, fotos privadas, progreso y borrador de 7 días.
- `/user/pedidos.html`: historial completo de pedidos y diseño con filtros y páginas.
- `/admin/`: centro de trabajo con expedientes, avisos y acciones.
- `/admin/calendario.html`, `/admin/reportes.html`, `/admin/actividad.html`.

## Pruebas independientes

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python scripts/generate_test_data.py --output test-data/tips-test.db
```

El generador solo admite un archivo llamado `tips-test.db` dentro de una carpeta `test-data`; `--reset` reinicia exclusivamente ese destino. Semilla: 650. Contiene 223 usuarios ficticios, 100 pedidos, 100 solicitudes, fotos, notificaciones e historiales. Usuario de ambas modalidades: `cliente000@tips.test` / `SoloPruebas2026!`.

Para navegador, iniciar otro proceso apuntando a esa base con `TIPS_DB_PATH` y luego:

```sh
python -m playwright install chromium
python tests/e2e_v65.py
```

`TIPS_TEST_BASE_URL` debe apuntar a localhost; `TIPS_EVIDENCE_DIR` controla las capturas. La suite crea cuentas y operaciones ficticias adicionales. No ejecutarla contra una base real, aunque esté en localhost.

## Documentación de la entrega

- [Resumen ejecutivo](docs/v6.5/RESUMEN-EJECUTIVO.md)
- [Auditoría](docs/v6.5/AUDITORIA.md)
- [Pruebas y limitaciones](docs/v6.5/PRUEBAS.md)
- [Base de datos y conservación](docs/v6.5/BASE-DE-DATOS.md)
- [Actualización, respaldo y recuperación](docs/v6.5/DESPLIEGUE.md)
- [Matriz de aceptación](docs/v6.5/ACEPTACION.md)

Los documentos antiguos se conservan como referencia histórica; sus instrucciones de pago no se aplican a v6.5.

### Imágenes del portafolio

Seis visualizaciones conceptuales generadas para las fichas de proyectos y dos imágenes para inicio y estudio. Las portadas se incorporan por proyecto al iniciar y se conservan las imágenes propias que ya existan. Los archivos y prompts están documentados en `docs/v6.7.1/PROMPTS-IMAGENES.json`.
