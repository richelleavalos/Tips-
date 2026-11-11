# Actualización desde TIPS v6.4

La entrada continúa siendo `python app.py`; no hay compilación de frontend ni pasarelas de pago nuevas. Este paquete contiene el proyecto completo, no parches. La configuración se lee del entorno del proceso; `.env.example` es una referencia y no se carga automáticamente.

## Preparación y respaldo

1. Programar mantenimiento y detener nuevas operaciones en la instancia anterior.
2. Respaldar mediante SQLite Backup la base existente, junto con los archivos públicos de productos y las claves de entorno. No copiar únicamente el archivo `.db` mientras haya escrituras WAL sin coordinar el respaldo.
3. Conservar la versión anterior del código y verificar que el respaldo pueda abrirse con `PRAGMA integrity_check` y `PRAGMA foreign_key_check`.
4. Extraer v6.5 en otro directorio. **No sobrescribir la base real con el dataset ficticio ni con una base vacía.** El ZIP desplegable no contiene bases de datos.
5. Instalar dependencias con `python -m pip install -r requirements.txt`. Se añaden Pillow y phonenumbers a cryptography. Para una instalación reproducible, fijar las versiones resueltas del entorno validado; esta entrega se probó con cryptography 46.0.7, Pillow 12.3.0 y phonenumbers 9.0.43.
6. Probar primero una copia de la base real con las mismas claves, aislada del tráfico y de los servicios externos.

## Variables de producción

- `TIPS_ENV=production`.
- `TIPS_DB_PATH`: ruta absoluta a la base conservada.
- `TIPS_SECRET_KEY` y **la misma `TIPS_FIELD_ENCRYPTION_KEY` que utilizaba v6.4**. No rotar la clave de cifrado durante esta actualización; cambiarla sin recifrar vuelve ilegibles los datos existentes.
- `TIPS_TRUSTED_PROXIES`: lista de IPs del proxy autorizado si se utiliza `CF-Connecting-IP`. Sin esta lista se usa la IP de la conexión, evitando aceptar cabeceras de IP de cualquier visitante.
- `TIPS_HOST` y `TIPS_PORT`: dirección/puerto del servicio detrás de la infraestructura existente.
- `TIPS_ALLOWED_ORIGINS`: origen HTTPS real del sitio, sin comodines.
- `TIPS_SECURE_COOKIES=1` con HTTPS.
- `TIPS_DESIGN_MAX_IMAGE_BYTES`: por defecto 20971520 (20 MiB por imagen). El límite temporal por propietario es 20 archivos / 200 MiB y el límite de decodificación 40 megapíxeles.
- `TIPS_MAX_REQUEST_BYTES`: puede conservarse en 1048576; cada bloque fotográfico es de 256 KiB binarios antes de base64.

`TIPS_PAYMENT_WEBHOOK_SECRET`, `TIPS_PAYMENT_PROVIDER` y el tiempo antiguo de reserva por pago ya no son necesarios para el flujo activo. Sus tablas se conservan como históricos. 2FA no se obliga ni se desactiva a quienes ya lo habilitaron.

Ejemplo local macOS/Linux, siempre con una base ficticia:

```sh
export TIPS_DB_PATH="$PWD/test-data/tips-test.db"
export TIPS_ENV=development
python app.py
```

En PowerShell: `$env:TIPS_DB_PATH="$PWD/test-data/tips-test.db"`. Configurar las variables equivalentes en el gestor de procesos del despliegue real; no incrustar secretos en el código ni en el ZIP.

## Migración y comprobación

Al primer arranque, el proyecto realiza el respaldo local `<base>.pre-v65.bak` si encuentra una base anterior, aplica migraciones idempotentes y conserva las tablas financieras. No inventa historial previo. En una base productiva vacía no crea cuentas demo: utilizar `python scripts/create_admin.py` para crear una administradora. En una actualización, revisar y retirar mediante el procedimiento del negocio los accesos demo históricos que ya existan.

Comprobar antes de abrir tráfico: acceso de administradoras y clientes, descifrado de contactos históricos, creación de pedido sin pago, aparición administrativa, transiciones, stock reservado, cancelación, carga y autorización de fotografías, seguimiento privado, campana y calendario. Repetir los flujos de la matriz de aceptación en el destino real.

La copia del ZIP original tenía 24 usuarios, 8 variantes y cero pedidos/pagos/cotizaciones; la migración se ejecutó dos veces en una copia y conservó los registros. Una prueba adicional utiliza un pedido histórico pagado y comprueba preservación exacta del pago y mapeo operativo a Confirmado.

## Avisos y correo opcional

Los avisos internos se reparten al consultar la campana, cada 30 segundos mientras la página esté visible. La intención ya queda registrada al confirmar la operación. Un fallo de reparto conserva el pedido y permite reintento.

Para correo, configurar `TIPS_SMTP_HOST`, `TIPS_SMTP_PORT` (587 por defecto), `TIPS_SMTP_FROM`, opcionalmente `TIPS_SMTP_USER` y `TIPS_SMTP_PASSWORD`, y `TIPS_PUBLIC_URL=https://...`. Ejecutar periódicamente:

```sh
python scripts/send_notifications.py
```

El worker usa STARTTLS con validación de certificado, conserva errores e intenta hasta 10 veces. El envío solo se marca tras la respuesta del servidor SMTP. Un fallo de proceso después de la aceptación SMTP y antes del guardado local puede causar repetición; se conserva un Message-ID estable, pero la deduplicación externa no puede garantizarse sin soporte del proveedor. No se ha verificado un proveedor real en esta entrega.

Un directorio `<base>.mail.lock` evita dos workers simultáneos. Tras una caída, comprobar que no quede un worker activo antes de retirar manualmente un lock huérfano. Las preferencias `email` habilitan correo de estados; la recuperación de acceso genera su propio aviso cifrado con caducidad. WhatsApp únicamente abre el mensaje preparado para envío manual.

## Recuperación

Si el ensayo falla, no habilitar tráfico: conservar la copia para diagnóstico y volver al respaldo verificado y al código anterior. Si ya hubo operaciones en v6.5, detener escrituras, respaldar también esa base y conciliar/exportar sus operaciones antes de restaurar una copia anterior; restaurarla directamente perdería los cambios posteriores. Nunca ejecutar una migración inversa destructiva sobre la única copia disponible.

Las fotografías privadas están dentro de SQLite: el respaldo de esa base incluye originales y miniaturas. Las imágenes públicas de productos siguen en `assets/uploads/products` y deben respaldarse aparte. Proteger también las claves de cifrado; una copia sin sus claves no permite recuperar el contenido cifrado.

## Alcance pendiente del destino

TLS, proxy, permisos del proceso, disponibilidad, copias externas, SMTP real y carga sostenida deben comprobarse en el entorno definitivo. No se realizó despliegue productivo.
