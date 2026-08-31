import unittest
from pathlib import Path

import scripts.collect_prices_agent as collector


class CollectorCatalogPathTests(unittest.TestCase):
    def test_catalog_db_matches_build_output(self):
        self.assertEqual(
            collector.CATALOG_DB,
            Path(collector.ROOT) / "data" / "filament.db",
        )


if __name__ == "__main__":
    unittest.main()
