"""Punto de entrada ejecutable de Tips.

La lógica de arranque vive en ``backend.application.TipsApplication``. Este
archivo se mantiene deliberadamente pequeño para que ejecutar ``python app.py``
sea obvio y no mezcle configuración, base de datos y servidor HTTP.
"""

from __future__ import annotations

from backend.application import TipsApplication


def main() -> None:
    """Construye la aplicación desde el entorno y ejecuta el servidor local."""
    TipsApplication.from_environment().run()


if __name__ == "__main__":
    main()
