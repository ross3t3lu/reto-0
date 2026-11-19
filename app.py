import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("NOTES_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(Path(app.instance_path) / "notes.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("NOTES_COOKIE_SECURE") == "1",
        MAX_CONTENT_LENGTH=1_048_576,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    initialize_database(app)

    @app.before_request
    def load_user():
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            with connect_db() as db:
                g.user = db.execute(
                    "SELECT id, email FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            if g.user is None:
                session.clear()

    @app.before_request
    def protect_forms():
        if request.method == "POST":
            submitted = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(submitted, expected):
                abort(400, description="La sesión del formulario ha caducado. Recarga la página.")

    @app.context_processor
    def csrf_context():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"], "split_tags": split_tags}

    @app.get("/")
    def index():
        return redirect(url_for("notes") if g.user else url_for("login"))

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if g.user:
            return redirect(url_for("notes"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if len(email) > 254 or "@" not in email:
                flash("Escribe un correo electrónico válido.", "error")
            elif len(password) < 8:
                flash("Tu contraseña debe tener al menos 8 caracteres.", "error")
            elif len(password) > 256:
                flash("La contraseña es demasiado larga.", "error")
            else:
                try:
                    with connect_db() as db:
                        db.execute(
                            "INSERT INTO users (email, password_hash, created_at) "
                            "VALUES (?, ?, ?)",
                            (email, generate_password_hash(password), utc_now()),
                        )
                except sqlite3.IntegrityError:
                    flash("Ya existe una cuenta con ese correo.", "error")
                else:
                    with connect_db() as db:
                        user = db.execute(
                            "SELECT id FROM users WHERE email = ?", (email,)
                        ).fetchone()
                    session.clear()
                    session["user_id"] = user["id"]
                    flash("Tu espacio privado está listo.", "success")
                    return redirect(url_for("notes"))
        return render_template("auth.html", mode="register")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if g.user:
            return redirect(url_for("notes"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            with connect_db() as db:
                user = db.execute(
                    "SELECT id, password_hash FROM users WHERE email = ?", (email,)
                ).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Correo o contraseña incorrectos.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                flash("Qué bueno tenerte de vuelta.", "success")
                return redirect(url_for("notes"))
        return render_template("auth.html", mode="login")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/notes", methods=("GET", "POST"))
    def notes():
        if not g.user:
            return redirect(url_for("login"))

        with connect_db() as db:
            if request.method == "POST":
                action = request.form.get("action")
                if action == "delete":
                    note_id = parse_note_id(request.form.get("note_id"))
                    cursor = db.execute(
                        "DELETE FROM notes WHERE id = ? AND user_id = ?",
                        (note_id, g.user["id"]),
                    )
                    if cursor.rowcount == 0:
                        abort(404)
                    flash("Nota eliminada.", "success")
                    return redirect(url_for("notes"))
                if action != "save":
                    abort(400, description="Acción de nota no válida.")

                title = request.form.get("title", "").strip()
                body = request.form.get("body", "").strip()
                tags = normalize_tags(request.form.get("tags", ""))
                note_id_text = request.form.get("note_id", "").strip()
                if not title:
                    flash("Añade un título antes de guardar.", "error")
                    return redirect(url_for("notes", new=1))
                if len(title) > 120 or len(body) > 20000:
                    flash("El título o el contenido supera el límite permitido.", "error")
                    return redirect(url_for("notes", new=1))

                if note_id_text:
                    note_id = parse_note_id(note_id_text)
                    cursor = db.execute(
                        "UPDATE notes SET title = ?, body = ?, tags = ?, updated_at = ? "
                        "WHERE id = ? AND user_id = ?",
                        (title, body, tags, utc_now(), note_id, g.user["id"]),
                    )
                    if cursor.rowcount == 0:
                        abort(404)
                    flash("Cambios guardados.", "success")
                    return redirect(url_for("notes", note=note_id))

                cursor = db.execute(
                    "INSERT INTO notes (user_id, title, body, tags, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (g.user["id"], title, body, tags, utc_now(), utc_now()),
                )
                flash("Nota guardada.", "success")
                return redirect(url_for("notes", note=cursor.lastrowid))

            search = request.args.get("q", "").strip()[:100]
            active_tag = request.args.get("tag", "").strip()[:40]
            query = (
                "SELECT id, title, body, tags, created_at, updated_at FROM notes "
                "WHERE user_id = ?"
            )
            parameters = [g.user["id"]]
            if search:
                query += " AND (title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')"
                escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                parameters.extend((f"%{escaped_search}%", f"%{escaped_search}%"))
            if active_tag:
                query += " AND instr(',' || tags || ',', ',' || ? || ',') > 0"
                parameters.append(active_tag)
            query += " ORDER BY updated_at DESC, id DESC"
            note_rows = db.execute(query, parameters).fetchall()
            all_notes = db.execute(
                "SELECT id, title, body, tags, created_at, updated_at FROM notes "
                "WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
                (g.user["id"],),
            ).fetchall()

        available_tags = sorted({tag for note in all_notes for tag in split_tags(note["tags"])})
        selected_id = request.args.get("note", type=int)
        selected_note = next(
            (note for note in note_rows if note["id"] == selected_id), None
        )
        is_new = request.args.get("new") == "1"
        if selected_note is None and not is_new and not search and not active_tag:
            selected_note = note_rows[0] if note_rows else None
        return render_template(
            "notes.html",
            notes=note_rows,
            all_notes=all_notes,
            selected_note=selected_note,
            is_new=is_new,
            search=search,
            active_tag=active_tag,
            available_tags=available_tags,
        )

    return app


@contextmanager
def connect_db():
    db = sqlite3.connect(current_app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database(app):
    db = sqlite3.connect(app.config["DATABASE"])
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS notes_by_owner ON notes(user_id, updated_at);
            """
        )
    finally:
        db.close()


def normalize_tags(value):
    tags = []
    seen = set()
    for raw_tag in value.split(","):
        tag = " ".join(raw_tag.strip().split())[:40]
        key = tag.casefold()
        if tag and key not in seen and len(tags) < 10:
            tags.append(tag)
            seen.add(key)
    return ",".join(tags)


def split_tags(value):
    return [tag for tag in value.split(",") if tag]


def parse_note_id(value):
    try:
        note_id = int(value)
    except (TypeError, ValueError):
        abort(404)
    if note_id < 1:
        abort(404)
    return note_id


def utc_now():
    return datetime.now(UTC).isoformat(timespec="seconds")


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
