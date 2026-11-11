"""Bootstrap mínimo de dependencias externas para desarrollo local.

TIPS intenta conservar ``python app.py`` como punto de entrada único.  Si la
librería ``cryptography`` no está instalada, en desarrollo se instala dentro de
``.tips_deps`` en el propio proyecto, evitando tocar el Python global de macOS.

En producción no se instalan paquetes automáticamente: las dependencias deben
estar preparadas por el proceso de despliegue.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DEPENDENCY_DIR = PROJECT_DIR / ".tips_deps"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _dependency_dir() -> Path:
    configured = os.getenv("TIPS_DEPENDENCY_DIR")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DEPENDENCY_DIR


def _prepend_dependency_dir(path: Path) -> None:
    raw = str(path)
    if raw not in sys.path:
        sys.path.insert(0, raw)
    importlib.invalidate_caches()


def ensure_cryptography() -> None:
    """Asegura que ``cryptography`` esté disponible antes de importar AESGCM.

    Desarrollo: instala de forma local en ``.tips_deps`` si hace falta.
    Producción: falla de forma explícita; nunca modifica el entorno en runtime.
    """

    target = _dependency_dir()
    if target.exists():
        _prepend_dependency_dir(target)

    if importlib.util.find_spec("cryptography") is not None and importlib.util.find_spec("PIL") is not None and importlib.util.find_spec("phonenumbers") is not None:
        return

    environment = (os.getenv("TIPS_ENV") or "development").strip().lower()
    auto_install_disabled = _truthy(os.getenv("TIPS_DISABLE_AUTO_DEPENDENCIES"))
    install_hint = f'"{sys.executable}" -m pip install -r "{PROJECT_DIR / "requirements.txt"}"'

    if environment == "production" or auto_install_disabled:
        raise ModuleNotFoundError(
            "Falta cryptography, Pillow o phonenumbers. Instálala antes de iniciar TIPS con: "
            + install_hint
        )

    target.mkdir(parents=True, exist_ok=True)
    print("[TIPS] Preparando dependencia de cifrado para este proyecto (solo la primera vez)...")

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(target),
        "cryptography>=46,<47",
        "Pillow>=11,<13",
        "phonenumbers>=8.13,<10",
    ]

    try:
        subprocess.run(command, cwd=str(PROJECT_DIR), check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "TIPS no pudo instalar automáticamente 'cryptography'. "
            "Comprueba tu conexión a Internet y ejecuta manualmente: "
            + install_hint
        ) from exc

    _prepend_dependency_dir(target)
    if importlib.util.find_spec("cryptography") is None:
        raise RuntimeError(
            "La instalación local de 'cryptography' finalizó, pero Python no pudo cargarla. "
            "Ejecuta manualmente: " + install_hint
        )
