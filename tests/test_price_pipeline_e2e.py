"""End-to-end regression test for the price pipeline (snapshot-first, Mode A).

This test exercises the whole flow OFFLINE, without network or real LLM keys:

    fake LLM agent  ->  collect snapshot JSON
                    ->  validate_price_snapshot
                    ->  POST /v1/ingest/prices (Flask test client)
                    ->  assert the offer landed in price-history.db

It is the guardrail against a change silently breaking the pipeline again.
Everything runs in an isolated temp dir via DB_PATH, so no repo file is touched.
"""
import json
import os
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

# The collector imports `openai` at module load; stub it if absent.
if "openai" not in sys.modules:
    try:
        import openai  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("openai")
        stub.OpenAI = object
        sys.modules["openai"] = stub


# --- Minimal catalog matching the columns the pipeline queries ---------------
def _build_catalog(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE filament_profiles (
            id INTEGER PRIMARY KEY, manufacturer_id INTEGER, material_id INTEGER,
            filament_key TEXT, commercial_name TEXT, profile_name TEXT, line TEXT,
            line_positioning TEXT, line_finish TEXT, line_tier TEXT, line_category TEXT,
            line_target_use TEXT, surface_finish TEXT, color TEXT,
            tracking INTEGER, active INTEGER
        );
        CREATE TABLE filament_variants (
            id INTEGER PRIMARY KEY, filament_id INTEGER, color_name TEXT, weight_g REAL
        );
        """
    )
    conn.execute("INSERT INTO materials VALUES (1,'PLA')")
    conn.execute("INSERT INTO manufacturers VALUES (2,'Voolt3D')")
    conn.execute(
        "INSERT INTO filament_profiles "
        "(id,manufacturer_id,material_id,filament_key,commercial_name,profile_name,line,color,tracking,active) "
        "VALUES (10,2,1,'pla|voolt3d|velvet line','PLA Velvet','PLA Velvet','Velvet Line','Preto',1,1)"
    )
    conn.execute("INSERT INTO filament_variants VALUES (100,10,'Preto',1000)")
    conn.commit()
    conn.close()


# --- Fake OpenAI-compatible client -------------------------------------------
class _FakeMessage:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls
        self.content = content
        self.role = "assistant"


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = types.SimpleNamespace(name=name, arguments=arguments)


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    """Turn 1: submit one valid offer. Turn 2: no tool calls -> finish."""
    def __init__(self):
        self._turn = 0

    def create(self, model, messages, tools, tool_choice):
        self._turn += 1
        if self._turn == 1:
            args = json.dumps({
                "filament_key": "pla|voolt3d|velvet line",
                "store": "Voolt3D",
                "url": "https://voolt3d.com.br/pla-velvet-preto",
                "title": "PLA Velvet Preto 1kg",
                "price": 89.90,
                "currency": "BRL",
                "quantity": 1,
                "unit_weight_g": 1000,
                "price_basis": "total",
                "color_name": "Preto",
            })
            return _FakeResponse(_FakeMessage(tool_calls=[_FakeToolCall("c1", "submit_offer", args)]))
        return _FakeResponse(_FakeMessage(tool_calls=None, content="done"))


class _FakeClient:
    def __init__(self):
        self.chat = types.SimpleNamespace(completions=_FakeCompletions())


class PricePipelineE2ETests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.catalog_db = self.tmp / "filament.db"
        _build_catalog(self.catalog_db)
        self.snapshot_dir = self.tmp / "price-data"
        self.snapshot_dir.mkdir()

        # Isolate all DBs into the temp dir and force the API secret.
        self._env = {
            "DB_PATH": str(self.catalog_db),
            "FILAMENTDB_PROXY_SECRET": "e2e-secret",
            "FILAMENTDB_API_SECRET": "e2e-secret",
        }
        self._prev = {k: os.environ.get(k) for k in self._env}
        os.environ.update(self._env)

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _fresh_api_client(self):
        """Reload the config/database/prices/api chain so all module-level DB
        paths rebind to the current temp dir, avoiding cross-test contamination."""
        import importlib
        from src import config
        config.load(force=True)
        from src import database, prices
        from src import api as api_mod
        importlib.reload(database)
        importlib.reload(prices)
        importlib.reload(api_mod)
        from flask import Flask
        app = Flask(__name__)
        api_mod.register_public_api(app)
        return api_mod, prices, app.test_client()

    def test_full_pipeline_offline(self):
        import scripts.collect_prices_agent as collector

        # 1) COLLECT: run the agent with a fake LLM, pointing at our temp catalog/snapshot.
        item = {"filament_key": "pla|voolt3d|velvet line", "color": "Preto"}
        provider = collector.AgentProvider(_FakeClient(), "fake-model")
        provider.name = "fake"

        # The agent calls the ingest API only for /v1/agent/instructions; stub that
        # single GET so the collector uses its local fallback prompts (offline).
        with patch.object(collector, "api_call", side_effect=collector.ProviderError("offline")):
            offers = provider.run(item, "2026-09-02")

        self.assertEqual(len(offers), 1)
        offer = offers[0]
        self.assertEqual(offer["filament_key"], "pla|voolt3d|velvet line")
        self.assertEqual(offer["total_price"], 89.90)

        # Write the snapshot exactly like main() would.
        snapshot = {
            "schema_version": 2,
            "snapshot_date": "2026-09-02",
            "collected_at": "2026-09-02T12:00:00-03:00",
            "collector": "e2e-test",
            "collection": [{"filament_key": item["filament_key"], "store": "agentic",
                            "status": "found", "offers_found": 1, "notes": "e2e"}],
            "offers": offers,
        }
        snap_path = self.snapshot_dir / "2026-09-02.json"
        snap_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

        # 2) VALIDATE: reuse the real validator against our temp catalog.
        import importlib
        import scripts.validate_price_snapshot as validator
        importlib.reload(validator)  # picks up DB_PATH from env
        validator.main(snap_path)

        # 3) PUBLISH + INGEST: POST the offer through the real Flask API into a
        #    real (temp) price-history.db.
        api_mod, prices, client = self._fresh_api_client()

        payload = dict(offer)
        payload["collected_at"] = snapshot["collected_at"]
        resp = client.post("/v1/ingest/prices", json=payload,
                           headers={"X-Proxy-Secret": "e2e-secret"})
        self.assertEqual(resp.status_code, 201, resp.get_data(as_text=True))
        self.assertEqual(resp.get_json()["status"], "accepted")

        # 4) ASSERT: the offer + snapshot are persisted in price-history.db.
        conn = prices.get_connection()
        try:
            row = conn.execute(
                "SELECT filament_key, quantity, unit_weight_g, price_basis "
                "FROM offers WHERE filament_key=?",
                ("pla|voolt3d|velvet line",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["filament_key"], "pla|voolt3d|velvet line")
            snap = conn.execute(
                "SELECT price, total_price, currency FROM price_snapshots "
                "WHERE offer_id=(SELECT id FROM offers WHERE filament_key=?)",
                ("pla|voolt3d|velvet line",),
            ).fetchone()
            self.assertAlmostEqual(snap["price"], 89.90, places=2)
            self.assertAlmostEqual(snap["total_price"], 89.90, places=2)
            self.assertEqual(snap["currency"], "BRL")
        finally:
            conn.close()

    def test_ingest_rejects_untracked_key(self):
        """An offer whose key is not in the catalog must be refused by the API (404)."""
        api_mod, prices, client = self._fresh_api_client()

        payload = {
            "filament_key": "pla|unknown|nope",
            "store": "X", "url": "https://x.com/p", "title": "t",
            "price": 10.0, "currency": "BRL", "quantity": 1,
            "unit_weight_g": 1000, "price_basis": "total", "total_price": 10.0,
            "collected_at": "2026-09-02T12:00:00-03:00",
        }
        resp = client.post("/v1/ingest/prices", json=payload,
                           headers={"X-Proxy-Secret": "e2e-secret"})
        self.assertEqual(resp.status_code, 404, resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
