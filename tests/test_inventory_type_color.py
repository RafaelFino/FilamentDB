"""Testes de tipo (profile_name) × cor no estoque: modelo, validação, PATCH,
bulk atômico, add-spool count, filtros, migração e export/import v2."""
import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

HF = "voolt3d-petg-hf"
OUTLET = "voolt3d-petg-outlet"
SUNLU = "sunlu-pla-hs"


def _make_catalog(path):
    """Catálogo mínimo com o contrato de colunas que o estoque consulta."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE filament_profiles (
            id INTEGER PRIMARY KEY, manufacturer_id INTEGER, material_id INTEGER,
            commercial_name TEXT, profile_name TEXT UNIQUE);
        CREATE TABLE filament_variants (
            id INTEGER PRIMARY KEY, filament_id INTEGER, sku TEXT,
            color_name TEXT, hex_color TEXT, finish TEXT);
        INSERT INTO manufacturers VALUES (1,'Voolt3D'),(2,'Sunlu');
        INSERT INTO materials VALUES (1,'PETG'),(2,'PLA');
        INSERT INTO filament_profiles VALUES
            (1,1,1,'PETG HF','voolt3d-petg-hf'),
            (2,1,1,'PETG Outlet','voolt3d-petg-outlet'),
            (3,2,2,'PLA High Speed','sunlu-pla-hs');
        INSERT INTO filament_variants VALUES
            (10,1,'S1','Preto','#111111','Basic'),
            (11,1,'S2','Azul Royal','#0000AA','Basic'),
            (20,3,'S3','Preto','#222222','Basic');
        """
    )
    conn.commit()
    conn.close()


class TypeColorBase(unittest.TestCase):
    with_catalog = True

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
        if self.with_catalog:
            _make_catalog(self.tmp / "filament.db")
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

    def post(self, **kw):
        payload = {"profile_name": HF, "color_name": "Preto"}
        payload.update(kw)
        return self.client.post("/api/inventory", json=payload)

    def create(self, **kw):
        r = self.post(**kw)
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def patch(self, iid, **kw):
        return self.client.patch(f"/api/inventory/{iid}", json=kw)

    def items(self, query=""):
        return self.client.get(f"/api/inventory/items{query}").get_json()

    def get(self, iid):
        return self.client.get(f"/api/inventory/{iid}").get_json()


class ModelAndValidationTests(TypeColorBase):
    def test_tipo_persiste_e_deriva_material_fabricante_e_hex(self):
        it = self.create()
        self.assertEqual(it["profile_name"], HF)
        self.assertEqual(it["material"], "PETG")
        self.assertEqual(it["manufacturer"], "Voolt3D")
        self.assertEqual(it["hex_color"], "#111111")
        self.assertEqual(it["variant_id"], 10)
        self.assertEqual(it["needs_review"], [])

    def test_payload_divergente_400(self):
        r = self.post(material="PLA")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["code"], "type_mismatch")
        r = self.post(manufacturer="Sunlu")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.items(), [])

    def test_tipo_inexistente_e_cor_livre(self):
        r = self.post(profile_name="nao-existe")
        self.assertEqual((r.status_code, r.get_json()["code"]), (400, "profile_not_found"))
        r = self.post(color_name="Verde Maçã")
        self.assertEqual((r.status_code, r.get_json()["code"]), (400, "color_invalid"))
        self.assertEqual(self.items(), [])

    def test_cor_da_paleta_passa_em_qualquer_tipo(self):
        it = self.create(profile_name=OUTLET, color_id="azul", color_name=None)
        self.assertEqual(it["color_name"], "Azul")
        self.assertIsNone(it["variant_id"])

    def test_tipo_sem_variantes_aceita_so_paleta(self):
        self.assertEqual(self.post(profile_name=OUTLET).status_code, 400)

    def test_legado_sem_profile_name(self):
        r = self.client.post("/api/inventory", json={
            "material": "PETG", "manufacturer": "Futer3D", "color_name": "Verde Maçã"})
        self.assertEqual(r.status_code, 201)
        it = r.get_json()
        self.assertIsNone(it["profile_name"])
        self.assertEqual(it["needs_review"], ["type_missing", "color_free_text"])

    def test_validadores_hex_peso(self):
        for bad in ("111111", "#12345", "#GGGGGG", 5):
            r = self.post(hex_color=bad)
            self.assertEqual(r.status_code, 400, bad)
        for bad in ("5", "x", 5.5, True, -1, 10001):
            self.assertEqual(self.post(weight_g=bad).status_code, 400, bad)

    def test_peso_zero_preservado_no_post_e_no_agrupamento(self):
        a = self.create(weight_g=0)
        self.assertEqual(a["weight_g"], 0)
        b = self.create()
        self.assertEqual(b["weight_g"], 1000)
        cards = self.inventory._material_groups(self.inventory.list_items())
        self.assertEqual(len(cards[0]["items"]), 2)  # 0 g e 1000 g não colapsam

    def test_catalogo_indisponivel(self):
        (self.tmp / "filament.db").unlink()
        r = self.post()
        self.assertEqual((r.status_code, r.get_json()["code"]), (400, "catalog_unavailable"))
        self.assertFalse((self.tmp / "filament.db").exists())  # não cria o arquivo
        # legado continua funcionando sem catálogo
        r = self.client.post("/api/inventory", json={
            "material": "PLA", "manufacturer": "X", "color_name": "Preto"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.patch(r.get_json()["id"], notes="ok").status_code, 200)


class PatchTests(TypeColorBase):
    def test_patch_so_campos_enviados(self):
        it = self.create(weight_g=750, finish="Basic")
        r = self.patch(it["id"], notes="x")
        self.assertEqual(r.status_code, 200)
        new = r.get_json()
        for k in ("weight_g", "finish", "variant_id", "color_id", "profile_name", "hex_color"):
            self.assertEqual(new[k], it[k], k)
        self.assertEqual(new["notes"], "x")

    def test_editar_tipo_cor_e_peso_persiste(self):
        it = self.create()
        r = self.patch(it["id"], profile_name=SUNLU, color_name="Preto", weight_g=500)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        got = [i for i in self.items() if i["id"] == it["id"]][0]
        self.assertEqual((got["profile_name"], got["material"], got["manufacturer"]),
                         (SUNLU, "PLA", "Sunlu"))
        self.assertEqual((got["variant_id"], got["hex_color"], got["weight_g"]),
                         (20, "#222222", 500))
        r = self.patch(it["id"], color_name="azul royal")  # fora do produto Sunlu
        self.assertEqual(r.get_json()["code"], "color_invalid")
        r = self.patch(it["id"], profile_name=HF, color_name="azul royal")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["color_name"], "Azul Royal")

    def test_trocar_tipo_com_cor_incompativel(self):
        it = self.create()
        r = self.patch(it["id"], profile_name=OUTLET)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["code"], "color_incompatible")
        self.assertEqual(self.get(it["id"])["profile_name"], HF)  # nada escrito

    def test_trocar_tipo_com_cor_da_paleta_passa(self):
        it = self.create(color_id="verde", color_name=None)
        r = self.patch(it["id"], profile_name=OUTLET)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["color_id"], "verde")
        # trocar para paleta junto com o tipo também funciona
        it2 = self.create()
        r = self.patch(it2["id"], profile_name=OUTLET, color_id="azul")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["variant_id"])

    def test_patch_color_name_sem_color_id_sai_da_paleta_e_valida(self):
        it = self.create(color_id="verde", color_name=None)
        r = self.patch(it["id"], color_name="cor-inexistente")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.get(it["id"])["color_id"], "verde")  # nada escrito
        r = self.patch(it["id"], color_name="Preto")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIsNone(j["color_id"])
        self.assertEqual(j["color_name"], "Preto")

    def test_patch_peso_spools_hex(self):
        it = self.create()
        for kw in ({"weight_g": "5"}, {"weight_g": True}, {"weight_g": 1.5},
                   {"weight_g": 10001}, {"weight_g": None}, {"spools": 2},
                   {"spools": True}, {"hex_color": "azul"}):
            self.assertEqual(self.patch(it["id"], **kw).status_code, 400, kw)
        r = self.patch(it["id"], weight_g=0)
        self.assertEqual(r.get_json()["weight_g"], 0)
        self.assertEqual(self.patch(it["id"], spools=0, status="empty").status_code, 200)

    def test_tipo_invalido_no_patch(self):
        it = self.create()
        r = self.patch(it["id"], profile_name="nope")
        self.assertEqual(r.get_json()["code"], "profile_not_found")
        r = self.patch(it["id"], material="PLA")
        self.assertEqual(r.get_json()["code"], "type_mismatch")

    def test_item_legado_patch_simples_nao_revalida(self):
        r = self.client.post("/api/inventory", json={
            "material": "PETG", "manufacturer": "Futer3D", "color_name": "Verde Maçã"})
        iid = r.get_json()["id"]
        self.assertEqual(self.patch(iid, weight_g=300, notes="n").status_code, 200)
        self.assertEqual(self.get(iid)["color_name"], "Verde Maçã")


class BulkTests(TypeColorBase):
    def test_bulk_aplica_a_todos(self):
        self.create(spools=3)
        ids = [i["id"] for i in self.items()]
        r = self.client.patch("/api/inventory/bulk",
                              json={"ids": ids, "weight_g": 500, "notes": "lote"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["updated"], 3)
        self.assertTrue(all(i["weight_g"] == 500 and i["notes"] == "lote" for i in self.items()))

    def test_bulk_troca_tipo_e_cor(self):
        self.create(spools=2)
        ids = [i["id"] for i in self.items()]
        r = self.client.patch("/api/inventory/bulk", json={
            "ids": ids, "profile_name": SUNLU, "color_name": "Preto"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(i["profile_name"] == SUNLU and i["variant_id"] == 20
                            for i in self.items()))

    def test_bulk_atomico_id_inexistente(self):
        self.create(spools=2)
        ids = [i["id"] for i in self.items()]
        r = self.client.patch("/api/inventory/bulk", json={"ids": ids + [9999], "weight_g": 1})
        self.assertEqual(r.status_code, 404)
        self.assertTrue(all(i["weight_g"] == 1000 for i in self.items()))

    def test_bulk_atomico_validacao(self):
        a = self.create()
        b = self.create(color_id="azul", color_name=None)
        r = self.client.patch("/api/inventory/bulk", json={
            "ids": [a["id"], b["id"]], "profile_name": OUTLET})
        self.assertEqual(r.status_code, 400)  # a: cor 'Preto' incompatível
        self.assertEqual(r.get_json()["code"], "color_incompatible")
        self.assertEqual({i["profile_name"] for i in self.items()}, {HF})

    def test_bulk_atomico_capacidade_cfs(self):
        self.create(spools=5)
        ids = [i["id"] for i in self.items()]
        r = self.client.patch("/api/inventory/bulk", json={"ids": ids, "status": "cfs"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual({i["status"] for i in self.items()}, {"in_stock"})
        r = self.client.patch("/api/inventory/bulk", json={"ids": ids[:4], "status": "cfs"})
        self.assertEqual(r.status_code, 200)

    def test_bulk_entradas_invalidas(self):
        for body in ({"weight_g": 1}, {"ids": [], "weight_g": 1}, {"ids": ["a"], "weight_g": 1},
                     {"ids": [True], "weight_g": 1}, {"ids": [1]}):
            r = self.client.patch("/api/inventory/bulk", json=body)
            self.assertEqual(r.status_code, 400, body)


class AddSpoolAndFilterTests(TypeColorBase):
    def test_add_spool_count(self):
        it = self.create(weight_g=0)
        r = self.client.post(f"/api/inventory/{it['id']}/add-spool", json={"count": 3})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(self.items()), 4)
        self.assertTrue(all(i["profile_name"] == HF and i["weight_g"] == 0 for i in self.items()))
        r = self.client.post(f"/api/inventory/{it['id']}/add-spool")  # default 1
        self.assertEqual(len(self.items()), 5)
        for bad in (0, 51, "2", True, 1.5):
            r = self.client.post(f"/api/inventory/{it['id']}/add-spool", json={"count": bad})
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(len(self.items()), 5)

    def test_add_spool_nao_revalida_catalogo(self):
        it = self.create()
        (self.tmp / "filament.db").unlink()
        r = self.client.post(f"/api/inventory/{it['id']}/add-spool")
        self.assertEqual(r.status_code, 201)

    def test_filtros(self):
        self.create()
        self.create(profile_name=SUNLU)
        self.create(profile_name=OUTLET, color_id="azul", color_name=None)
        self.assertEqual(len(self.items()), 3)
        self.assertEqual(len(self.items("?material=pla")), 1)
        self.assertEqual(len(self.items("?manufacturer=VOOLT3D")), 2)
        self.assertEqual(len(self.items(f"?profile_name={HF}")), 1)
        self.assertEqual(len(self.items("?color_id=azul")), 1)
        self.assertEqual(len(self.items("?color_name=preto")), 2)
        self.assertEqual(len(self.items("?manufacturer=Voolt3D&color_name=Preto")), 1)
        self.assertEqual(self.items("?material='; DROP TABLE inventory_items; --"), [])
        self.assertEqual(len(self.items()), 3)


class MigrationTests(TypeColorBase):
    def _old_db(self):
        db = self.tmp / "inventory.db"
        db.unlink(missing_ok=True)
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE inventory_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "uid TEXT, material TEXT NOT NULL, manufacturer TEXT NOT NULL, "
            "color_name TEXT NOT NULL, hex_color TEXT, color_id TEXT, finish TEXT, "
            "weight_g INTEGER DEFAULT 1000, spools INTEGER NOT NULL DEFAULT 1, "
            "status TEXT NOT NULL DEFAULT 'in_stock', variant_id INTEGER, sku TEXT, "
            "notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        rows = [
            # ok: variant 10 = Voolt3D PETG Preto
            ("a", "PETG", "Voolt3D", "Preto", 10, None),
            # deriva: variant 20 é da Sunlu PLA, item diz Voolt3D PETG
            ("b", "PETG", "Voolt3D", "Preto", 20, None),
            # deriva: variant 11 existe mas a cor do item é outra
            ("c", "PETG", "Voolt3D", "Azul", 11, None),
            # sku único Sunlu PLA, sem variant_id
            ("d", "PLA", "Sunlu", "Texto livre", None, "S3"),
            # nada para inferir
            ("e", "PLA", "Outra", "Preto Velvet", None, None),
        ]
        for uid, mat, mfr, color, vid, sku in rows:
            conn.execute(
                "INSERT INTO inventory_items(uid,material,manufacturer,color_name,"
                "weight_g,variant_id,sku,created_at,updated_at) "
                "VALUES (?,?,?,?,0,?,?,'t','t')", (uid, mat, mfr, color, vid, sku))
        conn.commit()
        conn.close()
        self.inventory.INVENTORY_DB_PATH = db
        return db

    def _snapshot(self):
        return {i["uid"]: (i["profile_name"], i["color_name"], i["weight_g"], tuple(i["needs_review"]))
                for i in self.inventory.list_items()}

    def test_migracao_e_backfill_idempotente(self):
        self._old_db()
        self.inventory.init_db(force=True)
        first = self._snapshot()
        self.assertEqual(len(first), 5)
        self.assertEqual(first["a"][0], HF)
        self.assertIsNone(first["b"][0])
        self.assertIsNone(first["c"][0])
        self.assertEqual(first["d"][0], SUNLU)
        self.assertIsNone(first["e"][0])
        self.assertIn("type_missing", first["b"][3])
        self.assertEqual(first["b"][1], "Preto")  # cor nunca reescrita
        self.assertTrue(all(v[2] == 0 for v in first.values()))  # peso 0 preservado
        self.inventory.init_db(force=True)
        self.assertEqual(self._snapshot(), first)
        self.assertEqual(self.inventory.backfill_profiles(), 0)

    def test_backfill_sem_catalogo_nao_falha(self):
        self._old_db()
        (self.tmp / "filament.db").unlink()
        self.inventory.init_db(force=True)
        self.assertTrue(all(v[0] is None for v in self._snapshot().values()))
        self.assertFalse((self.tmp / "filament.db").exists())


class ExportImportTests(TypeColorBase):
    def test_roundtrip_v2(self):
        self.create(weight_g=0)
        env = self.client.get("/api/inventory/export").get_json()
        self.assertEqual(env["schema_version"], 2)
        self.assertEqual(env["items"][0]["profile_name"], HF)
        r = self.client.post("/api/inventory/import?replace=1", json=env)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        got = self.items()
        self.assertEqual((got[0]["profile_name"], got[0]["weight_g"]), (HF, 0))

    def _v1_item(self, uid, **kw):
        base = {"uid": uid, "material": "PETG", "manufacturer": "Voolt3D",
                "color_name": "Preto", "weight_g": 0, "spools": 1, "status": "in_stock"}
        base.update(kw)
        return base

    def test_import_v1_infere_com_seguranca(self):
        env = {"schema_version": 1, "items": [
            self._v1_item("u1", variant_id=10),
            self._v1_item("u2", variant_id=20),  # deriva -> NULL
            self._v1_item("u3"),
        ]}
        r = self.client.post("/api/inventory/import", json=env)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["summary"]["errors"], [])
        by = {i["uid"]: i for i in self.items()}
        self.assertEqual(by["u1"]["profile_name"], HF)
        self.assertIsNone(by["u2"]["profile_name"])
        self.assertIsNone(by["u3"]["profile_name"])
        self.assertEqual(by["u1"]["weight_g"], 0)

    def test_import_lista_pura_e_tipo_invalido(self):
        r = self.client.post("/api/inventory/import", json=[
            self._v1_item("l1", profile_name="nao-existe"),
            self._v1_item("l2", profile_name=HF),
        ])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["summary"]["errors"], [])
        by = {i["uid"]: i for i in self.items()}
        self.assertIsNone(by["l1"]["profile_name"])
        self.assertEqual(by["l2"]["profile_name"], HF)

    def test_schema_3_recusado(self):
        r = self.client.post("/api/inventory/import", json={"schema_version": 3, "items": []})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
