import tempfile
import unittest
from pathlib import Path

from app import create_app


class NotesAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-key",
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf_token(self):
        with self.client.session_transaction() as browser_session:
            token = browser_session.get("csrf_token")
        if token:
            return token
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def register(self, email):
        token = self.csrf_token()
        return self.client.post(
            "/register",
            data={"csrf_token": token, "email": email, "password": "correct-horse"},
            follow_redirects=True,
        )

    def save_note(self, title, body, tags, note_id=""):
        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        return self.client.post(
            "/notes",
            data={
                "csrf_token": token,
                "action": "save",
                "note_id": note_id,
                "title": title,
                "body": body,
                "tags": tags,
            },
            follow_redirects=True,
        )

    def test_registration_login_and_private_note_search(self):
        response = self.register("ana@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tu primera idea empieza aqu", response.data)

        self.save_note("Plan de viaje", "Visitar Oaxaca en primavera", "personal, viajes, personal")
        result = self.client.get("/notes?q=Oaxaca")
        self.assertIn(b"Plan de viaje", result.data)

        filtered = self.client.get("/notes?tag=viajes")
        self.assertIn(b"Plan de viaje", filtered.data)
        with self.app.app_context():
            from app import connect_db

            with connect_db() as db:
                saved = db.execute("SELECT tags FROM notes").fetchone()["tags"]
        self.assertEqual(saved, "personal,viajes")

        token = self.csrf_token()
        self.client.post(
            "/logout", data={"csrf_token": token}, follow_redirects=True
        )
        login_token = self.csrf_token()
        login = self.client.post(
            "/login",
            data={
                "csrf_token": login_token,
                "email": "ana@example.com",
                "password": "correct-horse",
            },
            follow_redirects=True,
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn(b"Plan de viaje", login.data)

    def test_other_accounts_cannot_view_or_edit_notes(self):
        self.register("ana@example.com")
        created = self.save_note("Privada", "Solo para Ana", "personal")
        self.assertIn(b"Privada", created.data)

        with self.app.app_context():
            from app import connect_db

            with connect_db() as db:
                note_id = db.execute("SELECT id FROM notes").fetchone()["id"]

        token = self.csrf_token()
        self.client.post("/logout", data={"csrf_token": token})
        self.register("luis@example.com")

        self.assertNotIn(b"Privada", self.client.get("/notes").data)
        forbidden_update = self.save_note("Cambio ajeno", "No permitido", "", str(note_id))
        self.assertEqual(forbidden_update.status_code, 404)

    def test_owner_can_update_and_delete_a_note(self):
        self.register("ana@example.com")
        self.save_note("Borrador", "Primera versión", "ideas")
        with self.app.app_context():
            from app import connect_db

            with connect_db() as db:
                note_id = db.execute("SELECT id FROM notes").fetchone()["id"]

        updated = self.save_note("Nota final", "Versión revisada", "ideas, personal", str(note_id))
        self.assertIn(b"Nota final", updated.data)
        self.assertIn(b"Versi\xc3\xb3n revisada", updated.data)
        self.assertNotIn(b"Borrador", updated.data)

        with self.client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        deleted = self.client.post(
            "/notes",
            data={"csrf_token": token, "action": "delete", "note_id": str(note_id)},
            follow_redirects=True,
        )
        self.assertIn(b"Nota eliminada", deleted.data)
        self.assertNotIn(b"Nota final", deleted.data)

    def test_post_without_csrf_token_is_rejected(self):
        response = self.client.post(
            "/register", data={"email": "ana@example.com", "password": "correct-horse"}
        )
        self.assertEqual(response.status_code, 400)

    def test_wrong_password_does_not_start_a_session(self):
        self.register("ana@example.com")
        token = self.csrf_token()
        self.client.post("/logout", data={"csrf_token": token})
        token = self.csrf_token()
        response = self.client.post(
            "/login",
            data={"csrf_token": token, "email": "ana@example.com", "password": "wrong"},
            follow_redirects=True,
        )
        self.assertIn(b"Correo o contrase", response.data)
        self.assertIn(b"Vuelve a tus notas", response.data)


if __name__ == "__main__":
    unittest.main()
