import unittest

from src.app import app


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

    def test_tree_page(self):
        response = self.client.get("/tree")
        self.assertEqual(response.status_code, 200)
        self.assertIn("FilamentDB Explorer", response.get_data(as_text=True))

    def test_tree_page_contains_richer_material_data(self):
        response = self.client.get("/tree")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Preço médio", body)
        self.assertIn("Recomendações", body)


if __name__ == "__main__":
    unittest.main()
