import sys
import types
import unittest
from pathlib import Path

# The collector imports `openai` at module load. Provide a lightweight stub so
# the test suite runs even when the dependency is not installed (it is only
# needed at runtime in CI, not for testing the pure normalization logic).
if "openai" not in sys.modules:
    try:
        import openai  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("openai")
        stub.OpenAI = object
        sys.modules["openai"] = stub

import scripts.collect_prices_agent as collector


class CollectorCatalogPathTests(unittest.TestCase):
    def test_catalog_db_matches_build_output(self):
        self.assertEqual(
            collector.CATALOG_DB,
            Path(collector.ROOT) / "data" / "filament.db",
        )


class NormalizeOfferTests(unittest.TestCase):
    def test_total_basis_keeps_price_as_total(self):
        offer = collector.normalize_offer(
            {
                "store": "Voolt3D",
                "url": "https://voolt3d.com.br/x",
                "title": "PLA Velvet 1kg",
                "price": 89.90,
                "unit_weight_g": 1000,
                "quantity": 1,
                "price_basis": "total",
            },
            "pla|voolt3d|velvet line",
        )
        self.assertEqual(offer["filament_key"], "pla|voolt3d|velvet line")
        self.assertEqual(offer["price"], 89.90)
        self.assertEqual(offer["total_price"], 89.90)
        self.assertEqual(offer["quantity"], 1)
        self.assertEqual(offer["currency"], "BRL")
        self.assertEqual(offer["price_basis"], "total")

    def test_unit_basis_computes_total_price(self):
        offer = collector.normalize_offer(
            {
                "store": "ML",
                "url": "https://ml.com/y",
                "title": "Kit 3x PETG",
                "price": 80.0,
                "unit_weight_g": 1000,
                "quantity": 3,
                "price_basis": "unit",
            },
            "petg|sunlu|petg high speed matte line",
        )
        self.assertEqual(offer["total_price"], 240.0)
        self.assertEqual(offer["quantity"], 3)

    def test_parses_brazilian_number_strings(self):
        offer = collector.normalize_offer(
            {
                "store": "3D Lab",
                "url": "https://3dlab.com.br/z",
                "title": "PLA Premium",
                "price": "R$ 89,90",
                "unit_weight_g": "1000",
                "quantity": "1",
            },
            "pla|3dlab|standard/premium line",
        )
        self.assertEqual(offer["price"], 89.90)

    def test_defaults_quantity_to_one(self):
        offer = collector.normalize_offer(
            {
                "store": "S",
                "url": "https://s.com/a",
                "title": "t",
                "price": 10.0,
                "unit_weight_g": 1000,
            },
            "k",
        )
        self.assertEqual(offer["quantity"], 1)

    def test_rejects_invalid_url(self):
        with self.assertRaises(collector.ProviderError):
            collector.normalize_offer(
                {"store": "S", "url": "notaurl", "title": "t", "price": 10.0, "unit_weight_g": 1000},
                "k",
            )

    def test_rejects_nonpositive_price(self):
        with self.assertRaises(collector.ProviderError):
            collector.normalize_offer(
                {"store": "S", "url": "https://s.com", "title": "t", "price": 0, "unit_weight_g": 1000},
                "k",
            )

    def test_rejects_missing_weight(self):
        with self.assertRaises(collector.ProviderError):
            collector.normalize_offer(
                {"store": "S", "url": "https://s.com", "title": "t", "price": 10.0, "unit_weight_g": 0},
                "k",
            )


if __name__ == "__main__":
    unittest.main()
