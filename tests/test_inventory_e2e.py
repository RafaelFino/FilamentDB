"""End-to-end regression tests for the inventory subsystem (the only write path).

Exercises the real Flask routes against an isolated inventory.db in a temp dir,
covering CRUD, physical-location limits (CFS=4, spool=1), the "use" decrement,
and the export/import round-trip. This is the guardrail so a future change can't
silently break stock management (the feature the user relies on day to day).
"""
import os
import tempfile
import unittest
from pathlib import Path


class InventoryE2ETests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Isolate DBs into the temp dir; auth stays OFF (open system) by default.
        self._env = {"DB_PATH": str(self.tmp / "filament.db")}
        self._prev = {k: os.environ.get(k) for k in self._env}
        os.environ.update(self._env)

        import importlib
        from src import config
        config.load(force=True)
        from src import inventory, database, auth, buildinfo, services
        from src import web
        importlib.reload(inventory)
        importlib.reload(database)
        importlib.reload(web)
        self.inventory = inventory

        from flask import Flask
        app = Flask(__name__)
        web.register_routes(app)
        self.client = app.test_client()

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _add(self, **overrides):
        payload = {
            "material": "PLA", "manufacturer": "Voolt3D", "color_name": "Preto",
            "weight_g": 1000, "spools": 1, "status": "in_stock",
        }
        payload.update(overrides)
        return self.client.post("/api/inventory", json=payload)

    def test_crud_lifecycle(self):
        # CREATE
        resp = self._add(color_name="Velvet Preto")
        self.assertEqual(resp.status_code, 201, resp.get_data(as_text=True))
        item = resp.get_json()
        item_id = item["id"]
        self.assertEqual(item["material"], "PLA")
        self.assertEqual(item["spools"], 1)
        self.assertTrue(item.get("uid"))

        # READ (single + list)
        self.assertEqual(self.client.get(f"/api/inventory/{item_id}").status_code, 200)
        listing = self.client.get("/api/inventory/items").get_json()
        self.assertEqual(len(listing), 1)

        # UPDATE
        resp = self.client.patch(f"/api/inventory/{item_id}", json={"color_name": "Azul"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["color_name"], "Azul")

        # DELETE
        self.assertEqual(self.client.delete(f"/api/inventory/{item_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/inventory/{item_id}").status_code, 404)

    def test_use_decrements_spools(self):
        item_id = self._add(spools=3).get_json()["id"]
        resp = self.client.post(f"/api/inventory/{item_id}/use", json={"amount": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["spools"], 2)

    def test_cfs_limit_enforced(self):
        # CFS holds at most 4 physical slots. Filling 4 is fine; the 5th fails 409.
        r = self._add(status="cfs", spools=4, color_name="Um")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        r2 = self._add(status="cfs", spools=1, color_name="Dois")
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.get_json().get("code"), "location_full")

    def test_spool_limit_enforced(self):
        r = self._add(status="spool", spools=1, color_name="Um")
        self.assertEqual(r.status_code, 201)
        r2 = self._add(status="spool", spools=1, color_name="Dois")
        self.assertEqual(r2.status_code, 409)

    def test_create_requires_mandatory_fields(self):
        resp = self.client.post("/api/inventory", json={"material": "PLA"})
        self.assertEqual(resp.status_code, 400)

    def test_export_import_round_trip(self):
        self._add(color_name="Preto").get_json()
        self._add(color_name="Branco", manufacturer="Sunlu").get_json()

        exported = self.client.get("/api/inventory/export").get_json()
        self.assertEqual(exported["count"], 2)
        self.assertIn("items", exported)
        self.assertIn("schema_version", exported)

        # Wipe and re-import: the round-trip must restore both items by uid.
        for it in self.client.get("/api/inventory/items").get_json():
            self.client.delete(f"/api/inventory/{it['id']}")
        self.assertEqual(len(self.client.get("/api/inventory/items").get_json()), 0)

        resp = self.client.post("/api/inventory/import", json=exported)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        restored = self.client.get("/api/inventory/items").get_json()
        self.assertEqual(len(restored), 2)
        uids = {i["uid"] for i in restored}
        self.assertEqual(uids, {i["uid"] for i in exported["items"]})

    def test_import_is_idempotent_by_uid(self):
        self._add(color_name="Preto")
        exported = self.client.get("/api/inventory/export").get_json()
        # Importing the same envelope twice must not create duplicates.
        self.client.post("/api/inventory/import", json=exported)
        self.client.post("/api/inventory/import", json=exported)
        self.assertEqual(len(self.client.get("/api/inventory/items").get_json()), 1)


if __name__ == "__main__":
    unittest.main()
