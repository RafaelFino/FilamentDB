import os
import unittest
from unittest.mock import Mock, patch

from src import config
from src.api_app import app


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_secret = os.environ.get("FILAMENTDB_PROXY_SECRET")
        os.environ["FILAMENTDB_PROXY_SECRET"] = "test-secret"
        config.load(force=True)
        self.client = app.test_client()

    def tearDown(self):
        if self.previous_secret is None:
            os.environ.pop("FILAMENTDB_PROXY_SECRET", None)
        else:
            os.environ["FILAMENTDB_PROXY_SECRET"] = self.previous_secret
        config.load(force=True)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_v1_health_alias(self):
        response = self.client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["service"], "filamentdb-api")

    def test_ready_uses_database(self):
        fake_conn = Mock()
        fake_conn.execute.return_value.fetchone.return_value = (1,)
        with patch("src.api.database.get_db_connection", return_value=fake_conn):
            response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ready")
        fake_conn.close.assert_called_once()

    def test_ready_fails_without_secret(self):
        os.environ["FILAMENTDB_PROXY_SECRET"] = ""
        config.load(force=True)
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["reason"], "secret_not_configured")

    def test_catalog_requires_proxy_secret(self):
        response = self.client.get("/v1/catalog/filaments")
        self.assertEqual(response.status_code, 401)

    def test_catalog_requires_exact_proxy_secret(self):
        response = self.client.get("/v1/catalog/filaments", headers={"X-Proxy-Secret": "wrong"})
        self.assertEqual(response.status_code, 401)


    def test_catalog_returns_correlation_and_technical_keys(self):
        fake_conn = Mock()
        fake_conn.execute.return_value.fetchall.return_value = [
            {
                "technical_key": "42",
                "filament_key": "petg|3dfila|petg xt line",
                "commercial_name": "PETG XT Line",
                "line": "PETG XT Line",
                "material": "PETG",
                "manufacturer": "3DFila",
                "tracking": 1,
            }
        ]
        with patch("src.api.database.get_db_connection", return_value=fake_conn):
            response = self.client.get(
                "/v1/catalog/filaments",
                headers={"X-Proxy-Secret": "test-secret"},
            )
        self.assertEqual(response.status_code, 200)
        item = response.get_json()["filaments"][0]
        self.assertEqual(item["technical_key"], "42")
        self.assertEqual(item["filament_key"], "petg|3dfila|petg xt line")
        self.assertEqual(item["tracking"], 1)
        fake_conn.close.assert_called_once()

    def test_agent_instructions_returns_non_empty_prompts(self):
        response = self.client.get(
            "/v1/agent/instructions?filament_key=petg|3dfila|petg%20xt%20line",
            headers={"X-Proxy-Secret": "test-secret"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["system_prompt"].strip())
        self.assertTrue(payload["user_prompt"].strip())
        self.assertIn("petg|3dfila|petg xt line", payload["user_prompt"])

    def test_ingest_rejects_non_json(self):
        response = self.client.post("/v1/ingest/prices", data="hello", headers={"X-Proxy-Secret": "test-secret"})
        self.assertEqual(response.status_code, 415)


if __name__ == "__main__":
    unittest.main()
