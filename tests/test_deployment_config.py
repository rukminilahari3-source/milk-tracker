import tempfile
import unittest
from pathlib import Path

import app as app_module


class DeploymentConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = app_module.DB_PATH
        self.original_cors_origins = app_module.CORS_ORIGINS
        app_module.DB_PATH = Path(self.tmpdir.name) / "data" / "milklog.db"
        app_module.CORS_ORIGINS = {"https://rukminilahari3-source.github.io"}
        app_module.init_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.DB_PATH = self.original_db_path
        app_module.CORS_ORIGINS = self.original_cors_origins
        self.tmpdir.cleanup()

    def test_health_endpoint(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_entries_use_configured_database(self):
        saved = self.client.put(
            "/api/entries/2026-10-04",
            json={"qty": 1.5, "price": 60},
        )
        listed = self.client.get("/api/entries")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(len(listed.get_json()), 1)
        self.assertEqual(listed.get_json()[0]["qty"], 1.5)

    def test_allowed_pages_origin_can_use_api(self):
        response = self.client.options(
            "/api/entries",
            headers={
                "Origin": "https://rukminilahari3-source.github.io",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "https://rukminilahari3-source.github.io",
        )

    def test_unconfigured_origin_is_not_allowed(self):
        response = self.client.get(
            "/api/health",
            headers={"Origin": "https://untrusted.example"},
        )

        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_database_is_created_under_configured_path(self):
        self.assertTrue(app_module.DB_PATH.is_file())

    def test_preferences_can_be_saved_and_read_back(self):
        saved = self.client.put(
            "/api/prefs",
            json={"defaultPrice": 60, "milkType": "Cow Milk"},
        )
        loaded = self.client.get("/api/prefs")

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(loaded.get_json(), {"defaultPrice": "60", "milkType": "Cow Milk"})

    def test_postgres_placeholders_are_converted(self):
        original_database_url = app_module.DATABASE_URL
        try:
            app_module.DATABASE_URL = "postgresql://example"
            self.assertEqual(
                app_module._sql("SELECT * FROM entries WHERE date=? AND qty>?"),
                "SELECT * FROM entries WHERE date=%s AND qty>%s",
            )
        finally:
            app_module.DATABASE_URL = original_database_url

    def test_legacy_postgres_url_is_normalized(self):
        original_database_url = app_module.DATABASE_URL
        try:
            app_module.DATABASE_URL = "postgres://user:password@host/database"
            self.assertEqual(
                app_module._postgres_dsn(),
                "postgresql://user:password@host/database",
            )
        finally:
            app_module.DATABASE_URL = original_database_url
