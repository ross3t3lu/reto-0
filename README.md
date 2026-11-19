# Clarito

Aplicación web sencilla para guardar notas privadas, organizarlas con etiquetas y encontrarlas con búsqueda. Cada cuenta solo puede ver y editar sus propias notas.

## Ejecutar en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Abre http://127.0.0.1:5000 y crea una cuenta. Las notas se guardan en `instance\notes.sqlite`.

## Configuración

Para conservar sesiones seguras entre reinicios, define `NOTES_SECRET_KEY` con un valor secreto antes de iniciar la aplicación. En producción, sirve la aplicación detrás de HTTPS y define `NOTES_COOKIE_SECURE=1`. No actives el modo de depuración en producción.

## Funciones

- Registro e inicio de sesión con contraseñas almacenadas como hash.
- Notas con título, contenido y hasta diez etiquetas.
- Búsqueda en títulos y contenido, y filtros por etiqueta.
- Protección CSRF en formularios y separación de datos por cuenta.
- Base de datos SQLite local, sin servicios externos.
