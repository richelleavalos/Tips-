"""Punto de entrada ejecutable de TIPS.

La lógica de arranque vive en ``backend.application.TipsApplication``. El
import se realiza dentro de ``main`` para que el bootstrap de dependencias pueda
mostrar un mensaje limpio si la primera instalación local no puede completarse.
"""

from __future__ import annotations


def main() -> None:
    """Prepara dependencias, construye la aplicación y ejecuta el servidor."""
    try:
        from backend.application import TipsApplication
    except (ModuleNotFoundError, RuntimeError) as exc:
        if "cryptography" not in str(exc).lower():
            raise
        print(f"\n[TIPS] {exc}\n")
        raise SystemExit(1) from None

    TipsApplication.from_environment().run()


if __name__ == "__main__":
    main()
