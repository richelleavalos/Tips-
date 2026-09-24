"""Objeto principal de la aplicación Tips.

``TipsApplication`` encapsula el ciclo de vida completo: cargar configuración,
inicializar persistencia, crear el servidor HTTP y cerrarlo de forma segura.
El objetivo es que ``app.py`` sea un punto de entrada mínimo y que la lógica de
arranque sea reutilizable desde pruebas, scripts o futuros procesos.
"""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .config import Settings
from .database import DatabaseManager
from .runtime import create_server


class TipsApplication:
    """Coordina infraestructura y servidor HTTP sin mezclar reglas de dominio."""

    def __init__(self, settings: Settings) -> None:
        """Construye la aplicación para una configuración ya resuelta."""
        self.settings = settings
        self.database = DatabaseManager(settings)
        self._server: ThreadingHTTPServer | None = None

    @classmethod
    def from_environment(cls) -> "TipsApplication":
        """Crea una aplicación usando las variables de entorno actuales."""
        return cls(Settings.load())

    def prepare(self) -> ThreadingHTTPServer:
        """Inicializa la base y crea el servidor si todavía no existe."""
        if self._server is None:
            self.database.initialize()
            self._server = create_server(self.settings)
        return self._server

    def run(self) -> None:
        """Ejecuta el servidor hasta ``Ctrl+C`` y garantiza su cierre final."""
        server = self.prepare()
        print(f"Tips ejecutándose en http://{self.settings.host}:{self.settings.port}")
        print("Presiona Ctrl+C para detener el servidor.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")
        finally:
            self.close()

    def close(self) -> None:
        """Cierra el socket del servidor y permite preparar otra instancia después."""
        if self._server is not None:
            self._server.server_close()
            self._server = None
