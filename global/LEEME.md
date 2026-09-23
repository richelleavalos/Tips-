# TIPS v5 — Recursos globales

Este es uno de cuatro paquetes complementarios de **la misma versión** `Tips-v5-UX-Estable`. No es una aplicación completa por sí solo. Al unir los cuatro, se reconstruyen todos los archivos de código y recursos de la versión elegida, sin cambiar su contenido.

- Rama propuesta: `equipo/global`.
- Archivos asignados: **17** (inventario exacto en `ARCHIVOS.txt`).
- Responsabilidad: Animaciones compartidas, logos, imágenes estáticas de referencia y documentación del sistema visual. Las imágenes de admin también pertenecen a este paquete para mantener assets/ bajo un solo responsable.
- Identificador de la versión común: `d896534895af062764d354fad389a7f6c7713be449be829ffb468970b651e251`.

## Preparar la rama

Cada integrante utiliza su propio clon del mismo repositorio y acuerda con el equipo **el mismo commit base de fofo**. La referencia local comprobada en `Documents/Tips-` al preparar los paquetes es `ede19db3ab04a5e5d30ca16fc9bb75ea0d065407`; ese commit contiene únicamente el README inicial. No se crearon ni modificaron ramas del repositorio real.

Desde una terminal situada en la raíz de tu clon, con el trabajo previo guardado:

```bash
git status
git fetch origin
git switch -c equipo/global ede19db3ab04a5e5d30ca16fc9bb75ea0d065407
```

Si ese commit no está en tu repositorio, acuerden una base común de `fofo` y reemplacen el identificador en los cuatro paquetes. Si la rama propuesta ya existe, revísala y usa `git switch equipo/global` en lugar de crearla nuevamente. No hagas estos cambios directamente en `main`.

## Copiar únicamente tu sección

Descomprime este ZIP **fuera del clon**, por ejemplo en Descargas. Dentro están:

- `codigo/`: los archivos que corresponden a tu commit, con sus rutas originales.
- `aplicar.py`: asistente que copia solo esos archivos y verifica la rama.
- `ARCHIVOS.txt`: lista para preparar únicamente los archivos de tu sección.
- `MANIFIESTO.json`: identificación de la versión y huellas de integridad.
- Este `LEEME.md`: instrucciones de entrega; no se copia al repositorio.

Requiere Python 3.10 o posterior, como el código del proyecto. En Mac, desde la raíz del clon (los ejemplos suponen que descomprimiste en Descargas):

```bash
python3 "$HOME/Downloads/TIPS-v5-02-global/aplicar.py" .
python3 "$HOME/Downloads/TIPS-v5-02-global/aplicar.py" . --aplicar
```

El primer comando solo comprueba. El segundo copia. El asistente exige exactamente `equipo/global`, se detiene si hay cambios versionados pendientes o si sobrescribiría archivos locales sin seguimiento, comprueba las huellas y respalda los archivos reemplazados en una carpeta temporal cuya ruta imprime. No ejecuta commits, pushes ni merges. Se puede repetir si los archivos ya coinciden.

En Windows PowerShell:

```powershell
python "$env:USERPROFILE\Downloads\TIPS-v5-02-global\aplicar.py" .
python "$env:USERPROFILE\Downloads\TIPS-v5-02-global\aplicar.py" . --aplicar
```

Si descomprimiste en otra ubicación, ajusta solo la ruta al paquete. No copies la carpeta `codigo` como una carpeta nueva del proyecto: sus contenidos van en la raíz. El asistente hace esa combinación archivo por archivo.

## Crear un solo commit de esta sección

En Mac:

```bash
git status
git add --pathspec-from-file="$HOME/Downloads/TIPS-v5-02-global/ARCHIVOS.txt"
git diff --cached --stat
git commit -m "Agregar recursos globales y sistema visual de TIPS v5"
```

En Windows, el comando para preparar archivos es:

```powershell
git add --pathspec-from-file="$env:USERPROFILE\Downloads\TIPS-v5-02-global\ARCHIVOS.txt"
```

Luego usa el mismo `git diff` y `git commit` del ejemplo. Al estar listo para compartir la rama:

```bash
git push -u origin equipo/global
```

Si Git indica que no hay cambios, esa sección ya coincide con tu base; no hace falta crear un commit vacío. Estos paquetes son una división del código existente, no cuatro cambios nuevos sobre una base que ya contenga toda la v5.

## Coordinación de las cuatro entregas

| Paquete | Rama | Responsabilidad |
| --- | --- | --- |
| 01-backend | equipo/backend | Python, SQL, configuración, herramientas y pruebas Python |
| 02-global | equipo/global | Animaciones, logos, imágenes y documentación visual |
| 03-usuario | equipo/usuario | Sitio público, cuenta del cliente y pruebas JavaScript |
| 04-admin | equipo/admin | Interfaz administrativa |

Cada archivo de código tiene un único responsable. No cambien archivos de otra sección sin coordinar con su responsable. Las dependencias entre frontend y backend se conservan; los paquetes individuales no son ejecutables completos.

Para comprobar la aplicación completa, el coordinador puede reunir los **cuatro commits** en una rama de integración, sin tocar `main`. Estos comandos suponen que cada rama contiene exactamente el commit de su paquete sobre la misma base:

```bash
git fetch origin
git switch -c integracion/tips-v5 ede19db3ab04a5e5d30ca16fc9bb75ea0d065407
git cherry-pick origin/equipo/backend origin/equipo/global origin/equipo/usuario origin/equipo/admin
python3 -B -m unittest discover -s tests -v
node --test tests/test_user_area.cjs
python3 app.py
```

En Windows reemplaza `python3` por `python`. Si las ramas acumulan más commits, seleccionen explícitamente los commits acordados en lugar de usar solo sus puntas. No se incluyen instrucciones para integrar en `main`.

## Datos locales y alcance

No se distribuyen `data/`, sesiones, bases SQLite, claves, entornos ni cachés. El SQL de demostración sí está incluido en backend. Al iniciar el proyecto completo, la aplicación crea una nueva base local si no existe una en la ruta configurada.

El código y los recursos se conservan byte a byte. Esto también conserva cualquier limitación o referencia desactualizada de la versión original: no es una nueva versión de funcionalidades ni un refactor adicional. La separación no elimina archivos antiguos de una base distinta; el caso verificado parte del README inicial descrito arriba.
