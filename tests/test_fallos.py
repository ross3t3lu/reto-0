import secrets

from app import connect_db, create_app, utc_now


def test_usuario_no_puede_eliminar_nota_de_otra_cuenta(tmp_path):
    identificador = secrets.randbelow(1_000_000_000)
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": secrets.token_hex(32),
            "DATABASE": str(tmp_path / "test.sqlite"),
        }
    )
    with app.app_context(), connect_db() as db:
        propietario_id = db.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (f"propietario{identificador}@example.test", "unused", utc_now()),
        ).lastrowid
        usuario_id = db.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (f"usuario{identificador}@example.test", "unused", utc_now()),
        ).lastrowid
        titulo = f"nota{identificador}"
        nota_id = db.execute(
            "INSERT INTO notes (user_id, title, body, tags, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (propietario_id, titulo, "Contenido privado", "", utc_now(), utc_now()),
        ).lastrowid

    cliente = app.test_client()
    csrf_token = f"token-{identificador}"
    with cliente.session_transaction() as sesion:
        sesion["user_id"] = usuario_id
        sesion["csrf_token"] = csrf_token

    respuesta = cliente.post(
        "/notes",
        data={
            "csrf_token": csrf_token,
            "action": "delete",
            "note_id": str(nota_id),
        },
        follow_redirects=False,
    )

    with app.app_context(), connect_db() as db:
        nota = db.execute(
            "SELECT title FROM notes WHERE id = ? AND user_id = ?",
            (nota_id, propietario_id),
        ).fetchone()
    assert nota is not None
    assert nota["title"] == titulo
    assert respuesta.status_code in (403, 404)
