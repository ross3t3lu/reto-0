# AGENTS.md

## Proyecto
Clarito permite crear notas privadas, organizarlas con etiquetas y buscarlas.
Cada cuenta solo puede ver y modificar sus propias notas.

## Stack
- Python y Flask para la aplicación web.
- SQLite (`sqlite3`) para persistir cuentas y notas.
- Werkzeug para hashes de contraseña; Jinja2 para las plantillas.

## Comandos
- Instalar la aplicación: `python -m pip install -r requirements.txt`
- Herramientas de pruebas y estilo, si faltan: `python -m pip install pytest ruff`
- Ejecutar localmente: `python app.py`
- Pruebas: `python -m pytest -v`
- Revisar estilo: `ruff check .`

## Estructura
- `.gitignore`: excluye entornos virtuales, bases de datos y cachés.
- `README.md`: instrucciones de ejecución, configuración y funciones.
- `app.py`: rutas Flask, sesiones, autenticación y operaciones SQLite.
- `requirements.txt`: dependencias de la aplicación.
- `static/`: estilos CSS responsivos.
- `templates/`: plantillas Jinja para acceso y notas.
- `tests/`: pruebas de autenticación, privacidad y operaciones con notas.
- `instance/`: directorio generado para la base de datos local.

## Qué no hacer
- No modificar las pruebas para que pasen.
- No escribir claves en el código.
- No instalar dependencias sin explicar para qué.
- No hacer commit ni push.

## Lecciones aprendidas
