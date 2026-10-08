import tempfile
import unittest
from pathlib import Path

import app as app_module


class MilkLogApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        app_module.DB_PATH = Path(self.tmpdir.name) / "milklog.db"
        app_module.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_user_creation_and_morning_evening_tracking(self):
        self.client.post("/api/register", json={"username": "owner", "password": "secret123"})
        with self.client.session_transaction() as session:
            session["username"] = "owner"

        response = self.client.post("/api/users", json={"name": "Asha"})
        self.assertEqual(response.status_code, 201)

        response = self.client.put(
            "/api/entries/2026-10-04?user=Asha",
            json={"morningQty": 1.5, "eveningQty": 2.0, "price": 60},
        )
        self.assertEqual(response.status_code, 200)

        item = response.get_json()
        self.assertEqual(item["userId"], "Asha")
        self.assertEqual(item["qty"], 3.5)
        self.assertEqual(item["morningQty"], 1.5)
        self.assertEqual(item["eveningQty"], 2.0)

        response = self.client.get("/api/entries?user=Asha")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()), 1)
        self.assertEqual(response.get_json()[0]["qty"], 3.5)

    def test_register_and_login(self):
        response = self.client.post("/api/register", json={"username": "anna", "password": "secret123"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["loggedIn"])

        response = self.client.get("/api/entries")
        self.assertEqual(response.status_code, 200)

        self.client.post("/api/logout")
        response = self.client.post("/api/login", json={"username": "anna", "password": "secret123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["username"], "anna")

    def test_data_requires_login(self):
        response = self.client.get("/api/entries")
        self.assertEqual(response.status_code, 401)

        response = self.client.get("/api/prefs")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
