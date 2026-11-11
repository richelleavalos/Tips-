# Matriz de aceptación

“Verificado” indica ejecución local con datos ficticios. No supone validación del hosting productivo ni de todas las combinaciones del sistema.

| Requisito | Estado y evidencia |
|---|---|
| Registro con teléfono internacional | Verificado HTTP y formulario de navegador; máscara salvadoreña en los tres formatos. Otros países se comprueban con planes de numeración; no se verifica titularidad. |
| Autocompletar datos | Verificado en checkout y solicitud de diseño, con cuenta creada y perfil actualizado. |
| Modificar perfil | Verificado por navegador y HTTP; cambio de correo requiere contraseña. Snapshot histórico conservado tras cambio posterior. |
| Carrito con productos, variantes y personalizaciones | Verificado con dos productos en navegador; opciones y reservas de distintas líneas comprobadas por HTTP. |
| Pedido sin pago electrónico | Verificado: persistencia sin entrada en payments; endpoints antiguos de cobro retirados. |
| Registro transaccional e idempotencia | Verificado con reintentos, doble envío concurrente y última unidad disponible. |
| Aparición y detalle administrativo | Verificado entre contextos de navegador independientes y consulta HTTP. |
| Estados e historial | Verificado ciclo completo y rechazos; correcciones preservan eventos. |
| Seguimiento de cliente/invitado | Verificado por sesión y enlace privado; sin permiso se devuelve 404. |
| Inventario y cancelaciones | Verificado reserva agrupada, consumo y devolución únicamente antes de consumo. |
| Diseño con descripción y fotos | Verificado formulario real con dos fotos y API con imagen válida superior a 4 MiB. |
| Fotos privadas y administración | Verificado original byte a byte, miniatura, permisos, archivo falso y tamaño excesivo. |
| Fecha, hora, teléfono y fotos de diseño | Verificado listado/expediente en los tres formatos; zona America/El_Salvador. |
| Relación con la cuenta | Verificado ambas modalidades bajo user_id; aislamiento entre clientes. |
| Avisos internos persistentes | Verificado campana, contador, lectura, destinatarios y reparto con fallo/reintento. |
| Correo | Implementado y probado con SMTP simulado; **pendiente entrega mediante proveedor real**. |
| WhatsApp | Implementado enlace con mensaje preparado; **no se afirma envío automático ni se probó recepción real**. |
| Borradores | Verificado guardado, recuperación después de recargar, privacidad, caducidad y eliminación al enviar. |
| Reanudación de archivos | Verificado offset persistido y reenvío de bloque. Requiere seleccionar de nuevo el archivo local; no recupera automáticamente archivos del dispositivo. |
| Calendario real | Verificado compromiso guardado, conversión horaria y retiro de eventos de pedidos completados. Un compromiso activo por expediente, con cambios históricos conservados. |
| Actividad administrativa | Verificado actor, estados, notas, fecha y cambios/cobros en audit_logs y operation_events. |
| Dashboard real | Verificado contra SQL; tarjetas abren listados y expedientes, sin indicadores simulados. |
| Reportes | Verificado consulta real y separación de importes/cobros; filtros por período y exportación implementados. Primera atención calculada para pedidos. |
| 200 usuarios / 100 por modalidad | Verificado generador: 223 / 100 / 100, fotos y relaciones; base distribuida separadamente. |
| Usuario de ambas modalidades | Escenario real de navegador en cada formato: cuenta, perfil, diseño, fotos, carrito, pedido, cambios administrativos y seguimiento de ambos. Dataset incluye cliente000 con ambos procesos y cambio de perfil sin alterar snapshots. |
| Escritorio, tablet y teléfono | 18 escenarios completos aprobados en los tres viewports obligatorios; resoluciones intermedias comprobadas en páginas seleccionadas. |
| Sin desbordamientos graves detectados | Verificado segunda/última pasada tras corregir menú móvil. Evidencia antes/después disponible. |
| Análisis de lentitud | 200 consultas de dashboard con concurrencia 8, índices y paginación; **pendiente estrés sostenido en hosting real**. |
| Permisos de roles | HTTP y rutas para invitado, cliente, admin y superadmin; admin/cliente también en navegador. |
| Sin dependencia de pagos anteriores | Verificado flujo nuevo y rutas 410; tablas y utilidades históricas conservadas para auditoría. |
| Todos los módulos originales | Inspeccionados y rutas/recursos probados; pantallas recorridas en los tres tamaños. **No se declara prueba exhaustiva de cada edición/combinación de todos los módulos heredados**. |
| Producción | **No desplegado**. Actualización y recuperación documentadas; validar infraestructura, SMTP y operación del negocio antes de abrir tráfico. |
