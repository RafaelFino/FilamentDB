"""Testes de scripts/reclassify_inventory.py: reclassificação segura do tipo
(profile_name) de itens legados. Tudo em banco TEMPORÁRIO; nunca toca data/."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "reclassify_inventory", ROOT / "scripts" / "reclassify_inventory.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

HF = "PETG - Voolt3D - HF"
OUTLET = "PETG - Voolt3D - Outlet"
TROCA = "Troca de Cor (cor aparente)"

# (manufacturer, material, profile_name, commercial)
PROFILES = [
    ("Voolt3D", "ABS", "ABS - Voolt3D - Standard"),
    ("Creality", "PETG", "PETG - Creality - CR PETG"),
    ("Creality", "PETG", "PETG - Creality - Hyper PETG"),
    ("Futer3D", "PETG", "PETG - Futer3D - Basic"),
    ("Sunlu", "PETG", "PETG - Sunlu - High Speed Matte"),
    ("Voolt3D", "PETG", HF),
    ("Voolt3D", "PETG", OUTLET),
    ("Elegoo", "PLA", "PLA - Elegoo - Pro"),
    ("Elegoo", "PLA", "PLA - Elegoo - Standard"),
    ("Elegoo", "TPU", "TPU - Elegoo - 95A"),
    ("Soleyin", "PLA", "PLA - Soleyin - Ultra PLA"),
    ("Sunlu", "PLA", "PLA - Sunlu - Matte"),
    ("Sunlu", "PLA", "PLA - Sunlu - High Speed Matte"),
    ("Voolt3D", "PLA", "PLA - Voolt3D - Velvet"),
    ("Voolt3D", "PLA", "PLA - Voolt3D - Premium Outlet"),
    ("Voolt3D", "PLA", "PLA - Voolt3D - V-Silk"),
    ("Voolt3D", "PLA", "PLA - Voolt3D - Macaron"),
    ("Voolt3D", "PLA-CF", "PLA-CF - Voolt3D - Standard"),
]
COLORS = ["Preto", "Branco", "Amarelo", "Azul", "Translucido", "Gray", "Rosehip", "Laranja"]

# uid, manufacturer, material, finish, color, notes, color_id, profile_name(já preenchido)
F = None
ITEMS = [
    ("u-abs", "Voolt3D", "ABS", "Fosco", "Preto", None, None, F),
    ("u-cr1", "Creality", "PETG", "CR", "Azul", None, None, F),
    ("u-cr2", "Creality", "PETG", "CR", "Preto", None, None, F),
    ("u-hy1", "Creality", "PETG", "Hyper", "Preto", "rótulo Hyper-PETG Green", None, F),
    ("u-fu", "Futer3D", "PETG", None, "Cinza claro", None, "cinza-claro", F),
    ("u-su1", "Sunlu", "PETG", "HS", "Laranja", "Fosco", None, F),
    ("u-hf-am", "Voolt3D", "PETG", "HF", "Amarelo", None, None, F),
    ("u-hf-az", "Voolt3D", "PETG", "HF", "Azul", None, None, F),
    ("u-hf-tr", "Voolt3D", "PETG", "HF", "Translucido", None, None, F),
    ("a8a46e11-755c-418b-88a4-e186f256a8c7", "Voolt3D", "PETG", "HF", "Branco", TROCA, None, F),
    ("d3b66999-bfb8-4e1a-a1fb-c165639751ec", "Voolt3D", "PETG", "HF", "Branco", TROCA, None, F),
    ("ca643a96-51c7-48cc-9853-d4d72cef5cbc", "Voolt3D", "PETG", "HF", "Branco", TROCA, None, F),
    ("7fed7142-df4d-40d5-962a-455697229291", "Voolt3D", "PETG", "HF", "Branco", TROCA, None, F),
    ("u-el-pla", "Elegoo", "PLA", "PRO", "Preto", None, None, F),
    ("u-el-tpu", "Elegoo", "TPU", "T95A", "Preto", None, None, F),
    ("u-so1", "Soleyin", "PLA", "Standard", "Gray", None, None, F),
    ("u-so2", "Soleyin", "PLA", "Standard", "Rosehip", None, None, F),
    ("u-sm", "Sunlu", "PLA", "Matte", "Branco", None, None, F),
    ("u-shsm", "Sunlu", "PLA", "High Speed Matte", "Preto", "Fosco", None, F),
    ("u-ve", "Voolt3D", "PLA", "Velvet", "Preto", None, None, F),
    ("u-out", "Voolt3D", "PLA", "Outlet", "Branco", TROCA, None, F),
    ("u-silk", "Voolt3D", "PLA", "Silk", "Azul", None, None, F),
    ("u-mac", "Voolt3D", "PLA", "Macaron", "Rosehip", None, None, F),
    ("u-cf", "Voolt3D", "PLA-CF", "CF", "Preto", None, None, F),
    # extras de casos especiais
    ("u-filled", "Elegoo", "PLA", "PRO", "Preto", None, None, "PLA - Elegoo - Standard"),
    ("u-nomatch", "Sunlu", "PLA", "Linha Desconhecida", "Preto", None, None, F),
    ("u-conflict", "Voolt3D", "PLA", "Velvet", "Magenta Neon", None, None, F),
    ("u-troca-cr", "Creality", "PETG", "CR", "Branco", TROCA, None, F),
]

EXPECTED = {
    "u-abs": "ABS - Voolt3D - Standard",
    "u-cr1": "PETG - Creality - CR PETG", "u-cr2": "PETG - Creality - CR PETG",
    "u-hy1": "PETG - Creality - Hyper PETG",
    "u-fu": "PETG - Futer3D - Basic",
    "u-su1": "PETG - Sunlu - High Speed Matte",
    "u-hf-am": HF, "u-hf-az": HF, "u-hf-tr": HF,
    "u-el-pla": "PLA - Elegoo - Pro", "u-el-tpu": "TPU - Elegoo - 95A",
    "u-so1": "PLA - Soleyin - Ultra PLA", "u-so2": "PLA - Soleyin - Ultra PLA",
    "u-sm": "PLA - Sunlu - Matte", "u-shsm": "PLA - Sunlu - High Speed Matte",
    "u-ve": "PLA - Voolt3D - Velvet", "u-out": "PLA - Voolt3D - Premium Outlet",
    "u-silk": "PLA - Voolt3D - V-Silk", "u-mac": "PLA - Voolt3D - Macaron",
    "u-cf": "PLA-CF - Voolt3D - Standard",
}
TROCA_HF = [i[0] for i in ITEMS if i[5] == TROCA and i[3] == "HF"]


def make_catalog(path):
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
        """
    )
    mf, mt = {}, {}
    vid = 1
    for i, (m, mat, pn) in enumerate(PROFILES, start=1):
        mf.setdefault(m, len(mf) + 1)
        mt.setdefault(mat, len(mt) + 1)
        conn.execute("INSERT INTO filament_profiles VALUES (?,?,?,?,?)",
                     (i, mf[m], mt[mat], pn, pn))
        for c in COLORS:
            conn.execute("INSERT INTO filament_variants VALUES (?,?,?,?,?,?)",
                         (vid, i, None, c, "#101010", "Basic"))
            vid += 1
    for n, i in mf.items():
        conn.execute("INSERT INTO manufacturers VALUES (?,?)", (i, n))
    for n, i in mt.items():
        conn.execute("INSERT INTO materials VALUES (?,?)", (i, n))
    conn.commit()
    conn.close()


def make_inventory(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT,
            material TEXT NOT NULL, manufacturer TEXT NOT NULL,
            color_name TEXT NOT NULL, hex_color TEXT, color_id TEXT,
            profile_name TEXT, finish TEXT, weight_g INTEGER DEFAULT 1000,
            spools INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'in_stock', variant_id INTEGER,
            sku TEXT, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    conn.execute("CREATE UNIQUE INDEX idx_inv_uid ON inventory_items(uid)")
    for n, (uid, mfr, mat, fin, color, notes, cid, pn) in enumerate(ITEMS):
        conn.execute(
            "INSERT INTO inventory_items(uid, material, manufacturer, color_name, hex_color,"
            " color_id, profile_name, finish, weight_g, spools, status, variant_id, sku, notes,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)",
            (uid, mat, mfr, color, "#101010", cid, pn, fin, 500 + n,
             "drybox" if n % 3 == 0 else "in_stock", 9000 + n,  # variant_id "à deriva"
             "SKU%d" % n, notes, "2026-10-23T17:42:22+00:00", "2026-10-24T10:00:00+00:00"))
    conn.commit()
    conn.close()


def md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "inventory.db"
        self.cat = self.tmp / "filament.db"
        self.backups = self.tmp / "bk"
        make_catalog(self.cat)
        make_inventory(self.db)
        self._prev_bk = os.environ.get("BACKUP_DIR")
        os.environ["BACKUP_DIR"] = str(self.backups)

    def tearDown(self):
        if self._prev_bk is None:
            os.environ.pop("BACKUP_DIR", None)
        else:
            os.environ["BACKUP_DIR"] = self._prev_bk
        self._tmp.cleanup()

    def run_cli(self, *extra, apply=False):
        argv = ["--db", str(self.db), "--catalog", str(self.cat), *extra]
        if apply:
            argv.append("--apply")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rc.main(argv)
        return code, out.getvalue(), err.getvalue()

    def state(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM inventory_items ORDER BY id")]
        conn.close()
        return rows

    def profiles(self):
        return {r["uid"]: r["profile_name"] for r in self.state()}

    def plan_json(self, *extra):
        code, out, err = self.run_cli("--json", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)


class DryRunTests(Base):
    def test_dry_run_nao_altera_e_reporta(self):
        before = md5(self.db)
        code, out, err = self.run_cli()
        self.assertEqual(code, 0, err)
        self.assertEqual(md5(self.db), before)
        self.assertIn("DRY-RUN", out)
        self.assertIn("PLA - Voolt3D - Premium Outlet", out)
        self.assertFalse(self.backups.exists())

    def test_json_resumo(self):
        data = self.plan_json()
        self.assertEqual(data["summary"]["apply"], len(EXPECTED))
        self.assertEqual(data["summary"]["filled"], 1)
        applied = {i["uid"]: i["profile_name"] for i in data["apply"]}
        self.assertEqual(applied, EXPECTED)

    def test_pendentes_e_motivos(self):
        data = self.plan_json()
        pend = {i["uid"]: i["reason"] for i in data["pending"]}
        for uid in TROCA_HF:
            self.assertEqual(pend[uid], rc.R_DECISAO)
        self.assertEqual(pend["u-troca-cr"], rc.R_DECISAO)
        self.assertEqual(pend["u-nomatch"], rc.R_SEM_MATCH)
        # Troca de Cor em produto já Outlet (PLA Premium Outlet) NÃO é pendente.
        self.assertNotIn("u-out", pend)

    def test_conflito_de_cor_nao_aplicado(self):
        data = self.plan_json()
        conf = {i["uid"]: i["code"] for i in data["conflicts"]}
        self.assertEqual(conf, {"u-conflict": "color_incompatible"})
        self.assertNotIn("u-conflict", {i["uid"] for i in data["apply"]})

    def test_ambiguo(self):
        orig = list(rc.RULES)
        rc.RULES.append(("Sunlu", "PLA", "Matte", "PLA - Sunlu - High Speed Matte"))
        try:
            data = self.plan_json()
        finally:
            rc.RULES[:] = orig
        pend = {i["uid"]: i["reason"] for i in data["pending"]}
        self.assertEqual(pend["u-sm"], rc.R_AMBIGUO)

    def test_perfil_inexistente_no_catalogo_nao_aplica(self):
        conn = sqlite3.connect(self.cat)
        conn.execute("DELETE FROM filament_profiles WHERE profile_name = ?", ("PLA - Elegoo - Pro",))
        conn.commit()
        conn.close()
        data = self.plan_json()
        pend = {i["uid"]: i["reason"] for i in data["pending"]}
        self.assertEqual(pend["u-el-pla"], rc.R_PERFIL_INEXISTENTE)

    def test_regras_apontam_para_perfis_distintos_e_existentes_no_catalogo_de_teste(self):
        names = {p[2] for p in PROFILES}
        for _, _, _, pn in rc.RULES:
            self.assertIn(pn, names)


class ApplyTests(Base):
    def test_apply_classifica_o_esperado_e_preserva_campos(self):
        before = {r["uid"]: r for r in self.state()}
        code, out, err = self.run_cli(apply=True)
        self.assertEqual(code, 0, err)
        after = {r["uid"]: r for r in self.state()}
        self.assertEqual(set(before), set(after))
        for uid, b in before.items():
            a = after[uid]
            want = EXPECTED.get(uid, b["profile_name"])
            self.assertEqual(a["profile_name"], want, uid)
            for col in b:
                if col != "profile_name":
                    self.assertEqual(a[col], b[col], f"{uid}.{col}")

    def test_pendentes_ficam_sem_tipo(self):
        self.run_cli(apply=True)
        p = self.profiles()
        for uid in TROCA_HF + ["u-troca-cr", "u-nomatch", "u-conflict"]:
            self.assertIsNone(p[uid], uid)

    def test_nao_sobrescreve_preenchido(self):
        self.run_cli(apply=True)
        self.assertEqual(self.profiles()["u-filled"], "PLA - Elegoo - Standard")
        # nem com override
        ov = self.tmp / "ov.json"
        ov.write_text(json.dumps({"u-filled": "PLA - Elegoo - Pro"}))
        self.run_cli("--overrides", str(ov), apply=True)
        self.assertEqual(self.profiles()["u-filled"], "PLA - Elegoo - Standard")

    def test_backup_criado_e_valido(self):
        before = self.state()
        code, out, err = self.run_cli(apply=True)
        self.assertEqual(code, 0, err)
        files = list(self.backups.glob("inventory_prereclassify_*.db"))
        self.assertEqual(len(files), 1)
        conn = sqlite3.connect(files[0])
        n = conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0]
        nulls = conn.execute(
            "SELECT COUNT(*) FROM inventory_items WHERE profile_name IS NULL").fetchone()[0]
        conn.close()
        self.assertEqual(n, len(before))
        self.assertEqual(nulls, sum(1 for r in before if r["profile_name"] is None))

    def test_falha_de_backup_aborta_sem_gravar(self):
        h = md5(self.db)
        blocker = self.tmp / "arquivo"
        blocker.write_text("x")
        os.environ["BACKUP_DIR"] = str(blocker / "sub")  # mkdir falha
        code, out, err = self.run_cli(apply=True)
        self.assertEqual(code, 1)
        self.assertEqual(md5(self.db), h)

    def test_idempotencia(self):
        self.run_cli(apply=True)
        h = md5(self.db)
        n_backups = len(list(self.backups.glob("*.db")))
        code, out, err = self.run_cli(apply=True)
        self.assertEqual(code, 0, err)
        self.assertEqual(md5(self.db), h)
        self.assertEqual(len(list(self.backups.glob("*.db"))), n_backups)
        self.assertEqual(self.plan_json()["summary"]["apply"], 0)

    def test_rollback_em_falha_simulada(self):
        h = md5(self.db)

        def boom(*a, **k):
            raise rc.ReclassifyError("falha simulada")

        orig = rc.verify_state
        rc.verify_state = boom
        try:
            code, out, err = self.run_cli(apply=True)
        finally:
            rc.verify_state = orig
        self.assertEqual(code, 1)
        self.assertIn("falha simulada", err)
        self.assertEqual(md5(self.db), h)
        self.assertEqual(len(list(self.backups.glob("*.db"))), 1)  # backup mantido

    def test_verify_state_detecta_campo_alterado(self):
        rows = self.state()
        bad = [dict(r) for r in rows]
        bad[0]["weight_g"] = 1
        with self.assertRaises(rc.ReclassifyError):
            rc.verify_state(rows, bad, {})
        with self.assertRaises(rc.ReclassifyError):
            rc.verify_state(rows, rows[:-1], {})


class DecisionTests(Base):
    def test_override_por_uid_tem_precedencia(self):
        ov = self.tmp / "ov.json"
        ov.write_text(json.dumps({
            "_comment": "ignorado",
            TROCA_HF[0]: OUTLET,                    # resolve pendente
            "u-hf-am": OUTLET,                      # sobrepõe a regra (HF)
            "uid-que-nao-existe": OUTLET,
        }))
        self.run_cli("--overrides", str(ov), apply=True)
        p = self.profiles()
        self.assertEqual(p[TROCA_HF[0]], OUTLET)
        self.assertEqual(p["u-hf-am"], OUTLET)
        self.assertIsNone(p[TROCA_HF[1]])
        data = self.plan_json("--overrides", str(ov))
        self.assertTrue(any("uid-que-nao-existe" in w for w in data["warnings"]))

    def test_override_com_perfil_de_outro_fabricante_e_conflito(self):
        ov = self.tmp / "ov.json"
        ov.write_text(json.dumps({"u-abs": "PLA - Sunlu - Matte"}))
        data = self.plan_json("--overrides", str(ov))
        self.assertIn("u-abs", {i["uid"] for i in data["conflicts"]})

    def test_override_perfil_inexistente(self):
        ov = self.tmp / "ov.json"
        ov.write_text(json.dumps({"u-abs": "nao-existe"}))
        data = self.plan_json("--overrides", str(ov))
        pend = {i["uid"]: i["reason"] for i in data["pending"]}
        self.assertEqual(pend["u-abs"], rc.R_PERFIL_INEXISTENTE)

    def test_flag_troca_de_cor_outlet(self):
        self.run_cli("--troca-de-cor-petg=outlet", apply=True)
        p = self.profiles()
        for uid in TROCA_HF:
            self.assertEqual(p[uid], OUTLET)
        # HF sem a nota continua HF; Creality com a nota continua pendente.
        self.assertEqual(p["u-hf-am"], HF)
        self.assertIsNone(p["u-troca-cr"])

    def test_flag_troca_de_cor_hf(self):
        self.run_cli("--troca-de-cor-petg=hf", apply=True)
        p = self.profiles()
        for uid in TROCA_HF:
            self.assertEqual(p[uid], HF)
        self.assertIsNone(p["u-troca-cr"])


class EnvironmentTests(Base):
    def test_schema_antigo_aborta_pedindo_migracao(self):
        conn = sqlite3.connect(self.db)
        conn.execute("ALTER TABLE inventory_items DROP COLUMN profile_name")
        conn.commit()
        conn.close()
        h = md5(self.db)
        code, out, err = self.run_cli(apply=True)
        self.assertEqual(code, 2)
        self.assertIn("migrate_inventory", err)
        self.assertEqual(md5(self.db), h)

    def test_catalogo_ausente(self):
        self.cat.unlink()
        code, out, err = self.run_cli()
        self.assertEqual(code, 2)

    def test_resolucao_do_banco(self):
        self.assertEqual(rc.resolve_db("/x/y.db"), Path("/x/y.db"))
        prev = os.environ.get("FILAMENT_INVENTORY_DB_PATH")
        os.environ["FILAMENT_INVENTORY_DB_PATH"] = "/z/inv.db"
        try:
            self.assertEqual(rc.resolve_db(), Path("/z/inv.db"))
        finally:
            if prev is None:
                os.environ.pop("FILAMENT_INVENTORY_DB_PATH")
            else:
                os.environ["FILAMENT_INVENTORY_DB_PATH"] = prev


if __name__ == "__main__":
    unittest.main()
