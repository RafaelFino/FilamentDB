"""Testes da paleta de 24 cores (dados, endpoint, validação e persistência no estoque)."""
import importlib
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import palette


def _lum(hex_):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b):
    la, lb = sorted((a, b), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class PaletteDataTests(unittest.TestCase):
    def setUp(self):
        self.data = palette.load()
        self.colors = self.data["colors"]

    def test_24_cores(self):
        self.assertEqual(len(self.colors), 24)
        self.assertIsInstance(self.data["version"], int)

    def test_ids_nomes_hex_unicos_e_formato(self):
        for key in ("id", "name", "hex"):
            vals = [c[key] for c in self.colors]
            self.assertEqual(len(vals), len(set(vals)), key)
            self.assertTrue(all(vals), key)
        for c in self.colors:
            self.assertRegex(c["id"], r"^[a-z]+(-[a-z]+)*$")
            self.assertRegex(c["hex"], r"^#[0-9A-F]{6}$")

    def test_somente_solidas(self):
        for c in self.colors:
            self.assertIsNone(re.search(r"silk|glitter|glow|multi|metal",
                                        c["id"] + c["name"], re.I), c)

    def test_contraste_do_icone_de_selecao(self):
        # Mesma regra do JS (contrastTextColor): preto se lum > 0.179, senão branco.
        for c in self.colors:
            lum = _lum(c["hex"])
            fg = _lum("#000000") if lum > 0.179 else _lum("#FFFFFF")
            self.assertGreaterEqual(_contrast(lum, fg), 4.5, c)

    def test_get_color(self):
        self.assertEqual(palette.get_color("azul")["name"], "Azul")
        self.assertIsNone(palette.get_color("xyz"))
        self.assertIsNone(palette.get_color(None))
        self.assertIsNone(palette.get_color(["azul"]))


class PaletteInventoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._prev = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(self.tmp / "filament.db")
        from src import config
        config.load(force=True)
        from src import inventory, database, web
        importlib.reload(inventory)
        importlib.reload(database)
        importlib.reload(web)
        self.inventory = inventory
        from flask import Flask
        app = Flask(__name__)
        web.register_routes(app)
        self.client = app.test_client()

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self._prev
        self._tmp.cleanup()

    def _post(self, **kw):
        payload = {"manufacturer": "Futer3D", "material": "PETG", "status": "in_stock"}
        payload.update(kw)
        return self.client.post("/api/inventory", json=payload)

    def test_endpoint_paleta(self):
        r = self.client.get("/api/color-palette")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), palette.load())

    def test_post_servidor_autoritativo(self):
        r = self._post(color_id="azul", color_name="Qualquer", hex_color="#000000")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        it = r.get_json()
        self.assertEqual(it["color_id"], "azul")
        self.assertEqual(it["color_name"], "Azul")
        self.assertEqual(it["hex_color"], palette.get_color("azul")["hex"])

    def test_post_id_invalido_400_nada_criado(self):
        r = self._post(color_id="xyz")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/inventory/items").get_json(), [])

    def test_post_sem_color_id_fluxo_legado(self):
        self.assertEqual(self._post().status_code, 400)  # color_name segue obrigatório
        r = self._post(color_name="Preto Velvet", hex_color="#111111")
        self.assertEqual(r.status_code, 201)
        it = r.get_json()
        self.assertIsNone(it["color_id"])
        self.assertEqual(it["color_name"], "Preto Velvet")

    def test_patch_valido_e_invalido(self):
        iid = self._post(color_id="azul").get_json()["id"]
        r = self.client.patch(f"/api/inventory/{iid}", json={"color_id": "vermelho"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["color_name"], "Vermelho")
        r = self.client.patch(f"/api/inventory/{iid}", json={"color_id": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get(f"/api/inventory/{iid}").get_json()["color_id"],
                         "vermelho")

    def test_spools_e_add_spool_herdam_color_id(self):
        r = self._post(color_id="verde", spools=2)
        self.assertEqual(r.status_code, 201)
        items = self.client.get("/api/inventory/items").get_json()
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i["color_id"] == "verde" for i in items))
        new = self.client.post(f"/api/inventory/{items[0]['id']}/add-spool").get_json()
        self.assertEqual(new["color_id"], "verde")

    def test_export_import_roundtrip_e_desconhecido(self):
        self._post(color_id="roxo")
        env = self.client.get("/api/inventory/export").get_json()
        self.assertEqual(env["schema_version"], 1)
        self.assertEqual(env["items"][0]["color_id"], "roxo")
        r = self.client.post("/api/inventory/import?replace=1", json=env)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        items = self.client.get("/api/inventory/items").get_json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["color_id"], "roxo")

        # color_id desconhecido: importa com None e preserva nome/hex.
        env["items"][0]["uid"] = "uid-novo"
        env["items"][0]["color_id"] = "inexistente"
        env["items"][0]["color_name"] = "Tom Custom"
        env["items"][0]["hex_color"] = "#123456"
        r = self.client.post("/api/inventory/import", json=env)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["summary"]["errors"], [])
        novo = [i for i in self.client.get("/api/inventory/items").get_json()
                if i["uid"] == "uid-novo"][0]
        self.assertIsNone(novo["color_id"])
        self.assertEqual(novo["color_name"], "Tom Custom")

        # Envelope antigo (sem a chave color_id) também importa.
        for it in env["items"]:
            it.pop("color_id")
            it["uid"] = "uid-antigo"
        r = self.client.post("/api/inventory/import", json=env)
        self.assertEqual(r.get_json()["summary"]["errors"], [])

    def test_migracao_coluna_color_id(self):
        db = self.tmp / "inventory.db"
        db.unlink(missing_ok=True)
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE inventory_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "uid TEXT, material TEXT NOT NULL, manufacturer TEXT NOT NULL, "
            "color_name TEXT NOT NULL, hex_color TEXT, finish TEXT, "
            "weight_g INTEGER DEFAULT 1000, spools INTEGER NOT NULL DEFAULT 1, "
            "status TEXT NOT NULL DEFAULT 'in_stock', variant_id INTEGER, sku TEXT, "
            "notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO inventory_items(uid,material,manufacturer,color_name,"
            "created_at,updated_at) VALUES ('u1','PLA','X','Preto','t','t')")
        conn.commit()
        conn.close()
        self.inventory.INVENTORY_DB_PATH = db
        self.inventory.init_db(force=True)
        items = self.inventory.list_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["color_name"], "Preto")
        self.assertIsNone(items[0]["color_id"])


if __name__ == "__main__":
    unittest.main()
