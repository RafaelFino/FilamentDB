"""Smoke/contract test for the catalog build (build.py --only-db).

Runs the real build into an isolated temp DB and asserts the invariants the
rest of the system depends on (the price pipeline resolves offers by
filament_key and filters on tracking=1). If a change breaks the catalog schema
or the key contract, this fails loudly instead of surfacing as a broken job.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BuildCatalogContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls._tmp.name) / "filament.db"
        env = dict(os.environ)
        env["DB_PATH"] = str(cls.db_path)
        # Prefer the project venv python if present; fall back to current.
        py = ROOT / ".venv" / "bin" / "python"
        python = str(py) if py.exists() else sys.executable
        cls.result = subprocess.run(
            [python, "build.py", "--only-db"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        if self.result.returncode != 0:
            self.fail(f"build.py --only-db failed:\n{self.result.stderr[-2000:]}")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_core_tables_exist(self):
        names = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("materials", "manufacturers", "filament_profiles",
                      "filament_variants", "process_profiles"):
            self.assertIn(table, names, f"tabela ausente: {table}")

    def test_catalog_has_profiles(self):
        n = self.conn.execute("SELECT COUNT(*) FROM filament_profiles").fetchone()[0]
        self.assertGreater(n, 0, "catálogo vazio após build")

    def test_tracking_column_and_tracked_keys(self):
        # The price pipeline requires the tracking column and tracked PLA/PETG keys.
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(filament_profiles)")}
        self.assertIn("tracking", cols)
        self.assertIn("filament_key", cols)
        rows = self.conn.execute(
            "SELECT fp.filament_key, m.name FROM filament_profiles fp "
            "JOIN materials m ON m.id=fp.material_id "
            "WHERE fp.active=1 AND fp.tracking=1 "
            "AND fp.filament_key IS NOT NULL AND TRIM(fp.filament_key)<>''"
        ).fetchall()
        self.assertGreater(len(rows), 0, "nenhum perfil tracking=1 com filament_key")
        self.assertTrue(any(r["name"].upper() in ("PLA", "PETG") for r in rows))

    def test_filament_key_is_unique_and_normalized(self):
        # filament_key is the stable identity used across DBs; it must be unique
        # among tracked profiles and lower-case pipe-delimited.
        rows = self.conn.execute(
            "SELECT filament_key FROM filament_profiles "
            "WHERE tracking=1 AND filament_key IS NOT NULL AND TRIM(filament_key)<>''"
        ).fetchall()
        keys = [r["filament_key"] for r in rows]
        self.assertEqual(len(keys), len(set(keys)), "filament_key duplicado entre perfis tracked")
        for k in keys:
            self.assertEqual(k, k.lower(), f"filament_key não normalizado (lowercase): {k}")
            self.assertEqual(len(k.split("|")), 3, f"filament_key deve ter 3 partes: {k}")


if __name__ == "__main__":
    unittest.main()
