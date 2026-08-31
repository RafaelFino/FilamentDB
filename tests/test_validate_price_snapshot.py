import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_price_snapshot as validator


class ValidatePriceSnapshotTests(unittest.TestCase):
    def test_accepts_catalog_key_without_legacy_tracking_column(self):
        snapshot = {
            "schema_version": 1,
            "snapshot_date": "2026-08-30",
            "collected_at": "2026-08-30T23:00:00+00:00",
            "collector": "test",
            "offers": [],
            "collection": [{"filament_key": "petg|3dfila|petg xt line"}],
        }

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE filament_profiles (id INTEGER PRIMARY KEY, material_id INTEGER, manufacturer_id INTEGER, line TEXT, active INTEGER)")
        conn.execute("INSERT INTO materials VALUES (1, 'PETG')")
        conn.execute("INSERT INTO manufacturers VALUES (2, '3DFila')")
        conn.execute("INSERT INTO filament_profiles VALUES (42, 1, 2, 'PETG XT Line', 1)")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with patch.object(validator, "DB", Path(tmp) / "filament.db"):
                with patch.object(validator.sqlite3, "connect", return_value=conn):
                    validator.main(path)

        conn.close()


if __name__ == "__main__":
    unittest.main()
