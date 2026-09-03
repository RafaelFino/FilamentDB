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


class MergeOffersTests(unittest.TestCase):
    def _offer(self, url, price, store="Voolt3D", qty=1, weight=1000, basis="total"):
        return {"store": store, "url": url, "title": "t", "price": price,
                "currency": "BRL", "quantity": qty, "unit_weight_g": weight,
                "price_basis": basis, "total_price": price}

    def test_new_offers_are_appended(self):
        merged = collector.merge_offers(
            [self._offer("https://x.com/a", 10)],
            [self._offer("https://x.com/b", 20)],
        )
        self.assertEqual(len(merged), 2)

    def test_same_identity_is_deduped_fresh_wins(self):
        # Same store+url+qty+weight+basis => same offer; the fresh price wins.
        merged = collector.merge_offers(
            [self._offer("https://x.com/a", 100)],
            [self._offer("https://x.com/a", 79.9)],
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["price"], 79.9)

    def test_different_quantity_is_a_distinct_offer(self):
        # A tiered offer (same URL, different quantity) is a separate listing.
        merged = collector.merge_offers(
            [self._offer("https://x.com/a", 100, qty=1)],
            [self._offer("https://x.com/a", 270, qty=3)],
        )
        self.assertEqual(len(merged), 2)

    def test_rerun_same_day_is_idempotent(self):
        # Re-running with the exact same offers must not grow the list.
        base = [self._offer("https://x.com/a", 10), self._offer("https://x.com/b", 20)]
        merged = collector.merge_offers(base, list(base))
        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
