import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_price_snapshot as validator


def _make_catalog_conn():
    """In-memory catalog with the real column contract the validator queries."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(
        "CREATE TABLE filament_profiles ("
        "id INTEGER PRIMARY KEY, material_id INTEGER, manufacturer_id INTEGER, "
        "filament_key TEXT, active INTEGER, tracking INTEGER)"
    )
    conn.execute("INSERT INTO materials VALUES (1, 'PLA')")
    conn.execute("INSERT INTO manufacturers VALUES (2, 'Voolt3D')")
    conn.execute(
        "INSERT INTO filament_profiles VALUES (42, 1, 2, 'pla|voolt3d|velvet line', 1, 1)"
    )
    return conn


def _base_offer(**overrides):
    offer = {
        "filament_key": "pla|voolt3d|velvet line",
        "store": "Voolt3D",
        "url": "https://voolt3d.com.br/pla-velvet",
        "title": "PLA Velvet 1kg",
        "price": 89.90,
        "currency": "BRL",
        "quantity": 1,
        "unit_weight_g": 1000,
        "price_basis": "total",
        "total_price": 89.90,
    }
    offer.update(overrides)
    return offer


def _run_validator(snapshot):
    conn = _make_catalog_conn()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        with patch.object(validator, "DB", Path(tmp) / "filament.db"):
            with patch.object(validator.sqlite3, "connect", return_value=conn):
                validator.main(path)
    conn.close()


class ValidatePriceSnapshotTests(unittest.TestCase):
    def _snapshot(self, offers):
        return {
            "schema_version": 2,
            "snapshot_date": "2026-09-02",
            "collected_at": "2026-09-02T12:00:00-03:00",
            "collector": "test",
            "offers": offers,
            "collection": [{"filament_key": "pla|voolt3d|velvet line"}],
        }

    def test_accepts_valid_complete_offer(self):
        # Should not raise.
        _run_validator(self._snapshot([_base_offer()]))

    def test_accepts_unit_basis_with_total_price(self):
        # unit basis: total_price must equal price * quantity.
        offer = _base_offer(price=50.0, quantity=2, price_basis="unit", total_price=100.0)
        _run_validator(self._snapshot([offer]))

    def test_rejects_untracked_key(self):
        offer = _base_offer(filament_key="pla|unknown|nope")
        with self.assertRaises(ValueError):
            _run_validator(self._snapshot([offer]))

    def test_rejects_non_http_url(self):
        offer = _base_offer(url="ftp://example.com/x")
        with self.assertRaises(ValueError):
            _run_validator(self._snapshot([offer]))

    def test_rejects_nonpositive_price(self):
        offer = _base_offer(price=0, total_price=0)
        with self.assertRaises(ValueError):
            _run_validator(self._snapshot([offer]))

    def test_rejects_inconsistent_total_price(self):
        offer = _base_offer(price=50.0, quantity=2, price_basis="unit", total_price=80.0)
        with self.assertRaises(ValueError):
            _run_validator(self._snapshot([offer]))

    def test_rejects_duplicate_offer(self):
        offer = _base_offer()
        with self.assertRaises(ValueError):
            _run_validator(self._snapshot([offer, dict(offer)]))

    def test_rejects_missing_required_top_level_field(self):
        snapshot = self._snapshot([_base_offer()])
        del snapshot["collected_at"]
        with self.assertRaises(ValueError):
            _run_validator(snapshot)


if __name__ == "__main__":
    unittest.main()
