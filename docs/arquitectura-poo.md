# Arquitectura orientada a objetos de Tips

## Objetivo

Este refactor busca que el proyecto sea fácil de leer por una persona que no participó en su creación. La programación orientada a objetos se utiliza únicamente donde ayuda a representar responsabilidades estables; no se crean clases para funciones triviales ni se agregan frameworks innecesarios.

## Capas principales

```text
app.py
  └── TipsApplication
      ├── Settings / EnvironmentReader
      ├── DatabaseManager
      └── RuntimeTipsRequestHandler
          └── TipsRoleViewRequestHandler
              └── TipsScalableRequestHandler
                  └── TipsAppRequestHandler
                      └── TipsAdminRequestHandler
                          └── TipsRequestHandler
```

### `TipsApplication`

Es el objeto que representa el proceso de la aplicación. Inicializa la base, construye el servidor y garantiza su cierre. `app.py` no conoce detalles de SQLite ni del servidor HTTP.

### `Settings` y `EnvironmentReader`

`Settings` contiene la configuración efectiva e inmutable. `EnvironmentReader` interpreta las variables de entorno y valida tipos/rangos antes de que el resto del sistema las utilice.

### `DatabaseManager`

Centraliza conexiones, PRAGMAs de SQLite, transacciones, creación del esquema, datos iniciales y consultas simples. Los helpers históricos `connect`, `transaction`, `initialize` y `fetch_all` siguen disponibles como adaptadores; esto permite migrar módulos gradualmente sin romper compatibilidad.

### Seguridad

- `PasswordHasher`: crea y verifica PBKDF2-HMAC-SHA256.
- `SessionTokenManager`: genera tokens de sesión y sus hashes persistibles.
- `CsrfProtection`: crea y valida tokens CSRF vinculados a una sesión.
- `SecurityPolicy`: agrupa cabeceras HTTP, CORS y validación de búsquedas.
- `RateLimiter`: controla frecuencia de solicitudes por clave.

Las funciones antiguas (`hash_password`, `verify_password`, etc.) son adaptadores hacia estos objetos para conservar el contrato existente.

### Handlers HTTP

El servidor HTTP ya tenía una arquitectura naturalmente orientada a objetos por herencia. El refactor la conserva porque cada clase agrega una responsabilidad concreta:

1. `TipsRequestHandler`: HTTP base, autenticación, sesiones, carrito y recursos públicos.
2. `TipsAdminRequestHandler`: endpoints administrativos.
3. `TipsAppRequestHandler`: cuenta del cliente e imágenes/productos.
4. `TipsScalableRequestHandler`: extensiones del catálogo para crecimiento funcional.
5. `TipsRoleViewRequestHandler`: autorización de vistas por rol.
6. `RuntimeTipsRequestHandler`: comportamiento final ejecutado, incluido checkout demo.

Cada método relevante tiene docstring y los módulos tienen una descripción de responsabilidad.

## Frontend

El frontend conserva la organización por responsabilidad ya establecida:

```text
frontend/
  global/   # recursos compartidos
  admin/    # experiencia administrativa
  usuario/  # experiencia del cliente
```

`frontend/usuario/js/app.js` fue reescrito para abandonar funciones comprimidas y utilizar dos objetos claros:

- `ApiClient`: transporte HTTP + CSRF.
- `TipsClientApp`: estado y comportamiento de navegación, tienda, carrito, portafolio, cuenta y checkout.

Los demás HTML, CSS y JavaScript incluyen un encabezado de propósito para dejar explícito a qué capa pertenecen y qué responsabilidad tienen.

## Compatibilidad

El refactor no cambia deliberadamente:

- rutas HTTP públicas;
- endpoints `/api/...`;
- esquema de datos existente;
- roles `user` y `admin`;
- formato de respuestas consumidas por el frontend;
- ubicación de la base `data/tips.db` por defecto;
- comando de ejecución `python app.py` / `python3 app.py`.

## Principios de mantenimiento

1. Una clase debe tener una responsabilidad entendible en una frase.
2. Las reglas de seguridad no se duplican en controladores.
3. SQLite se manipula mediante transacciones explícitas para escrituras relacionadas.
4. Las funciones de compatibilidad no deben contener lógica nueva: solo delegar.
5. Los comentarios explican decisiones y responsabilidades, no repiten literalmente el código.
6. Cualquier cambio de API debe acompañarse de una prueba de integración.
