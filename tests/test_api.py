import unittest

from src.app import app
from src.api import _validate_offer


class FlaskApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")

    def test_manufacturers_endpoint(self):
        response = self.client.get("/manufacturers")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, list)
        self.assertTrue(len(payload) > 0)
        self.assertIn("id", payload[0])
        self.assertIn("name", payload[0])

    def test_materials_endpoint(self):
        response = self.client.get("/materials")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, list)
        self.assertTrue(len(payload) > 0)
        self.assertIn("id", payload[0])
        self.assertIn("name", payload[0])

    def test_download_zip_endpoint(self):
        response = self.client.get("/download/creality-print?manufacturer=Creality&material=PLA")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertTrue(response.data.startswith(b"PK"))

    def test_download_zip_path_endpoint(self):
        response = self.client.get("/download/creality-print/Creality/PLA")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")

    def test_download_options_endpoint(self):
        response = self.client.get("/download/creality-print/options")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, list)
        self.assertTrue(len(payload) > 0)
        self.assertIn("manufacturer", payload[0])
        self.assertIn("material", payload[0])

    def test_page_routes_render_dashboard(self):
        # /, /dashboard, /tree and /process-profiles all serve the single
        # consolidated dashboard.html (client-side tabs). The old dedicated
        # tree.html/process-profiles.html templates were removed.
        for route in ("/", "/dashboard", "/tree", "/process-profiles"):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, route)
            self.assertIn("FilamentDB Dashboard", response.get_data(as_text=True), route)

    def test_agent_offer_normalizes_common_llm_values(self):
        offer, _ = _validate_offer({
            "filament_key": "petg|3dfila|petg xt line",
            "store": "3D Lab",
            "url": "https://3dlab.com.br/produto/petg",
            "title": "PETG XT Line",
            "price": "R$ 89,90",
            "original_price": "99,90",
            "shipping": "R$ 12,50",
            "currency": "R$",
            "available": "sim",
            "marketplace": "0",
            "quantity": "3 rolos",
            "unit_weight_g": "1 kg",
            "price_basis": "por unidade",
            "total_price": "R$ 269,70",
        })
        self.assertEqual(offer["price"], 89.90)
        self.assertEqual(offer["original_price"], 99.90)
        self.assertEqual(offer["shipping"], 12.50)
        self.assertEqual(offer["currency"], "BRL")
        self.assertIs(offer["available"], True)
        self.assertIs(offer["marketplace"], False)
        self.assertEqual(offer["quantity"], 3)
        self.assertEqual(offer["unit_weight_g"], 1000.0)
        self.assertEqual(offer["price_basis"], "unit")
        self.assertEqual(offer["total_price"], 269.70)

    def test_agent_offer_tolerates_unknown_optional_boolean(self):
        offer, _ = _validate_offer({
            "filament_key": "petg|3dfila|petg xt line",
            "store": "3D Lab",
            "url": "https://3dlab.com.br/produto/petg",
            "title": "PETG XT Line",
            "price": 89.9,
            "unit_weight_g": 1000,
            "available": "maybe",
            "marketplace": "unknown",
        })
        self.assertIsNone(offer["available"])
        self.assertFalse(offer["marketplace"])


if __name__ == "__main__":
    unittest.main()
