# Auditoría de seguridad de TIPS v6.6.1

La prueba se ejecutó contra TIPS v6.6 y se repitió sobre v6.6.1. Ambas corridas usaron servidores HTTP en loopback, SQLite desechable y cuentas ficticias. Se ejercieron las rutas reales con solicitudes HTTP y se comprobaron los flujos de interfaz en Browser, Chromium y WebKit.

La selección de métodos parte de la [Guía de pruebas de seguridad web de OWASP](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/), los [riesgos para APIs de OWASP](https://api-security.owasp.org/editions/2023/en/0x11-t10/), la [guía de sesiones de OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) y la [guía de validación de lógica de negocio](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/10-Business_Logic_Testing/01-Test_Business_Logic_Data_Validation/). Cada fila de la matriz representa un caso aplicado a un objetivo de TIPS. Los casos que comparten causa se agrupan en el resumen.

## Resultado y prioridad

**58 casos ejecutados.** La versión anterior aprobó 38 y falló 20. La versión parcheada aprobó los 58. El alcance da evidencia sobre el código y los flujos ensayados. La configuración real de TLS, CDN, proxy, correo y capacidad bajo carga requiere pruebas sobre su propio entorno.

| Prioridad | Hallazgo reproducido | Corrección verificada |
|---|---|---|
| Alta | Una cookie de invitado conocida antes de iniciar sesión permitía reutilizar la sesión autenticada. El registro tenía la misma falla. | Se emite una cookie nueva tras autenticar. El token anterior deja de identificar la sesión. El cliente recibe un CSRF ligado a la cookie nueva. Se mantiene la transferencia del carrito y el borrador de invitado. |
| Alta | Una base de desarrollo migrada a producción dejaba activas cuentas con credenciales demo conocidas. | En producción se desactivan las cuentas demo que todavía conservan esas claves y se revocan sus sesiones. Las cuentas con claves cambiadas conservan su estado. |
| Alta | Un administrador ordinario podía promover cuentas a administración. | Solo la cuenta raíz puede cambiar roles o editar cuentas administrativas. Cambiar rol o activación revoca las sesiones y los enlaces de recuperación pendientes. |
| Alta | Un enlace de recuperación anterior seguía siendo utilizable tras cambiar el correo o la contraseña. | Se invalidan los enlaces y desafíos anteriores, se caducan los correos de recuperación pendientes y se mantienen las revocaciones de sesión del flujo de cambio o recuperación de contraseña. |
| Alta | Los enlaces privados podían quedar en registros HTTP usando el nombre del parámetro codificado. Una copia del enlace quedaba en texto claro en la respuesta de reintento persistida. | Los registros HTTP omiten la consulta completa. Los resultados de reintento se cifran con AES-GCM, incluidos los existentes. Se aplica una política de referencia que omite la URL del origen. |
| Media | Al cambiar de cuenta en el mismo navegador, la segunda cuenta podía recibir el carrito de la primera. | Se revoca la sesión anterior y se crea una sesión independiente para la otra cuenta. El carrito permanece asociado a su propietario. |
| Media | El desafío 2FA podía completarse desde una sesión distinta con el desafío y un código válido. | El desafío queda ligado a la sesión que inició el acceso y se consume al usarlo. |
| Media | El servidor podía declarar una redirección dependiente de la sesión como pública y privada a la vez. | Solo los recursos estáticos no HTML se marcan cacheables. HTML, redirecciones, respuestas de API y archivos privados se sirven con `no-store`. |
| Media | Los expedientes de cliente devolvían nombres e identificadores internos de responsables. Las cargas privadas temporales podían abrirse después de caducar. | Se retiran los datos de responsables de la respuesta de cliente y se valida la caducidad de la carga antes de servirla. |
| Baja | HEAD permitía consultar la existencia de archivos internos por el servidor estático heredado. | HEAD usa el mismo control de rutas que GET para recursos y vistas. En las APIs se rechaza con 405. |
| Baja | Se aceptaban claves JSON repetidas, números no finitos y booleanos como cantidades. Una paginación extrema y un código 2FA con dígitos Unicode causaban errores de servidor. | Se valida el JSON de entrada, se limitan enteros y paginación, y se exigen cantidades enteras y códigos 2FA ASCII. |

Se restringió la copia visual guardada para el fundido de navegación en navegadores antiguos. Las pantallas privadas y los formularios con datos personales quedan fuera de esa copia. En navegadores sin transiciones nativas, las vistas privadas de llegada pueden usar un fundido de entrada de 500 ms. El fundido nativo y el de pestañas siguen disponibles.

## Reproducción y actualización

Ejecutar desde la carpeta extraída, con las dependencias instaladas.

```sh
python -m pytest -q tests/test_security_audit.py
python -m pytest -q
```

Las pruebas levantan su propio servidor local y crean su propia base. Para una instalación de producción que necesite crear o recuperar la cuenta raíz, ejecutar `python scripts/create_admin.py --root` con la configuración y la base de esa instalación. El comando pide la contraseña de forma interactiva. Si ya existe una cuenta raíz, se usa su correo para actualizarla.

Respaldar la base antes de actualizar. La migración cifra los resultados de reintentos históricos usando la clave de cifrado existente. Una reversión a v6.6 requiere restaurar la base respaldada antes de la actualización si se necesita conservar la lectura de esos reintentos. Los clientes que llamen a la API directamente deben adoptar el nuevo `csrf_token` devuelto después de autenticar o pedir uno nuevo a `/api/csrf`.

## Evidencia de cierre

Pasaron 115 pruebas de la suite completa y 366 subcomprobaciones. Pasaron los 36 escenarios de regresión de interfaz, 18 en Chromium y 18 en WebKit. En Browser se confirmó que el panel exige volver a iniciar sesión después de salir, que el administrador ordinario no ve el alta de usuarios y que el marcador de HTML guardado en una cotización se muestra como texto sin crear un elemento ni ejecutar su evento.

## Matriz de los 58 casos

| Caso | Método aplicado | v6.6 | v6.6.1 |
|---|---|---|---|
| 01 | Acceso directo a una vista privada | Aprobado | Aprobado |
| 02 | Omisión del enrutador con HEAD | Hallazgo reproducido | Aprobado |
| 03 | Recorrido de directorios | Aprobado | Aprobado |
| 04 | Listado de directorios | Aprobado | Aprobado |
| 05 | Alteración del método HTTP | Aprobado | Aprobado |
| 06 | API privada sin sesión | Aprobado | Aprobado |
| 07 | Escalada vertical cliente a admin | Aprobado | Aprobado |
| 08 | Omisión de permisos por ruta antigua | Aprobado | Aprobado |
| 09 | Asignación masiva de rol al registrarse | Aprobado | Aprobado |
| 10 | Delegación de privilegios desde admin ordinario | Hallazgo reproducido | Aprobado |
| 11 | Pedido ajeno por ID | Aprobado | Aprobado |
| 12 | Cotización ajena por ID | Aprobado | Aprobado |
| 13 | Miniatura privada por ID | Aprobado | Aprobado |
| 14 | Uso de un enlace para otro expediente | Aprobado | Aprobado |
| 15 | Lectura de borrador ajeno | Aprobado | Aprobado |
| 16 | Asociación de foto ajena | Aprobado | Aprobado |
| 17 | Marcar como leído un aviso ajeno | Aprobado | Aprobado |
| 18 | Escritura desde otro origen | Aprobado | Aprobado |
| 19 | Omisión del token CSRF | Aprobado | Aprobado |
| 20 | Reutilización de CSRF entre sesiones | Aprobado | Aprobado |
| 21 | Fijación de sesión en login | Hallazgo reproducido | Aprobado |
| 22 | Fijación de sesión al registrarse | Hallazgo reproducido | Aprobado |
| 23 | Reutilización de sesión tras salir | Aprobado | Aprobado |
| 24 | Reutilización de sesión vencida | Aprobado | Aprobado |
| 25 | Atributos de protección de cookies | Aprobado | Aprobado |
| 26 | Caché de redirecciones dependientes de sesión | Hallazgo reproducido | Aprobado |
| 27 | Protección contra clickjacking | Aprobado | Aprobado |
| 28 | Preflight CORS desde origen opaco | Aprobado | Aprobado |
| 29 | Inyección SQL en búsqueda | Aprobado | Aprobado |
| 30 | JSON malformado | Aprobado | Aprobado |
| 31 | Parámetros JSON duplicados | Hallazgo reproducido | Aprobado |
| 32 | Paginación fuera de rango | Hallazgo reproducido | Aprobado |
| 33 | Sustitución del tipo de contenido | Aprobado | Aprobado |
| 34 | Carga de SVG disfrazado de foto | Aprobado | Aprobado |
| 35 | Tamaño declarado de archivo excesivo | Aprobado | Aprobado |
| 36 | Edición de carrito ajeno por ID | Aprobado | Aprobado |
| 37 | Confusión de tipo en cantidad | Hallazgo reproducido | Aprobado |
| 38 | Manipulación del precio enviado | Aprobado | Aprobado |
| 39 | Reintento con datos alterados | Aprobado | Aprobado |
| 40 | Salto de estados de pedido | Aprobado | Aprobado |
| 41 | Escritura con una versión obsoleta | Aprobado | Aprobado |
| 42 | Cobro manual fuera de límites | Aprobado | Aprobado |
| 43 | Reactivación de una ruta de pago retirada | Aprobado | Aprobado |
| 44 | Exposición de propiedades internas | Hallazgo reproducido | Aprobado |
| 45 | Cifrado de campos de expediente | Aprobado | Aprobado |
| 46 | Política de referencia de enlaces privados | Hallazgo reproducido | Aprobado |
| 47 | Credenciales demo en una base migrada | Hallazgo reproducido | Aprobado |
| 48 | Traslado del desafío 2FA entre navegadores | Hallazgo reproducido | Aprobado |
| 49 | Reutilización de recuperación después de cambiar correo | Hallazgo reproducido | Aprobado |
| 50 | Lectura de carga temporal caducada | Hallazgo reproducido | Aprobado |
| 51 | Transferencia de carrito al cambiar de cuenta | Hallazgo reproducido | Aprobado |
| 52 | Límite de intentos de acceso | Aprobado | Aprobado |
| 53 | Solicitud que supera el tamaño de cuerpo | Aprobado | Aprobado |
| 54 | Número JSON no finito | Hallazgo reproducido | Aprobado |
| 55 | Enlace privado en respuestas persistidas | Hallazgo reproducido | Aprobado |
| 56 | Parámetro codificado en registros HTTP | Hallazgo reproducido | Aprobado |
| 57 | Dígitos Unicode en código 2FA | Hallazgo reproducido | Aprobado |
| 58 | Recuperación anterior tras cambiar contraseña | Hallazgo reproducido | Aprobado |
