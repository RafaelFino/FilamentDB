import os
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
        # Fake OpenAI client that accepts the same kwargs the real one does
        # (base_url/api_key/timeout) and exposes base_url — providers() builds it
        # and the registry test inspects client.base_url. `object` won't do: it
        # rejects kwargs, which fails in CI where openai isn't installed.
        class _StubOpenAI:
            def __init__(self, *args, base_url=None, api_key=None, timeout=None, **kwargs):
                self.base_url = base_url
        stub = types.ModuleType("openai")
        stub.OpenAI = _StubOpenAI
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


class ProviderRegistryTests(unittest.TestCase):
    """The registry must build one provider per configured key, with the right
    endpoint, and skip providers whose key is absent."""

    def _run_with_keys(self, keys):
        import importlib
        saved = {k: os.environ.get(k) for k in (
            "MISTRAL_API_KEY", "CEREBRAS_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
            "OPENROUTER_API_KEY", "Z_API_KEY", "GEMINI_API_KEY")}
        try:
            for k in saved:
                os.environ.pop(k, None)
            for k in keys:
                os.environ[k] = "test-key"
            importlib.reload(collector)
            return {p.name: p.client.base_url for p in collector.providers()}
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            importlib.reload(collector)

    def test_all_seven_providers_build(self):
        got = self._run_with_keys([
            "MISTRAL_API_KEY", "CEREBRAS_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
            "OPENROUTER_API_KEY", "Z_API_KEY", "GEMINI_API_KEY"])
        self.assertEqual(set(got), {"mistral", "cerebras", "groq", "openai", "openrouter", "z", "gemini"})
        # base_url may come back as an httpx URL with a trailing slash; normalize.
        self.assertEqual(str(got["cerebras"]).rstrip("/"), "https://api.cerebras.ai/v1")
        self.assertEqual(str(got["z"]).rstrip("/"), "https://api.z.ai/api/paas/v4")

    def test_missing_keys_are_skipped(self):
        got = self._run_with_keys(["CEREBRAS_API_KEY", "GEMINI_API_KEY"])
        self.assertEqual(set(got), {"cerebras", "gemini"})


class TrimHistoryTests(unittest.TestCase):
    def setUp(self):
        self._prev = collector.HISTORY_MAX_MESSAGES
        collector.HISTORY_MAX_MESSAGES = 6

    def tearDown(self):
        collector.HISTORY_MAX_MESSAGES = self._prev

    def _convo(self, pairs):
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        for i in range(pairs):
            msgs.append({"role": "assistant", "content": f"a{i}"})
            msgs.append({"role": "tool", "content": f"t{i}"})
        return msgs

    def test_short_history_untouched(self):
        msgs = self._convo(1)  # 4 messages, under cap
        self.assertEqual(collector._trim_history(msgs), msgs)

    def test_long_history_capped_and_head_preserved(self):
        out = collector._trim_history(self._convo(5))  # 12 messages -> cap 6
        self.assertLessEqual(len(out), 6)
        self.assertEqual(collector._msg_role(out[0]), "system")
        self.assertEqual(collector._msg_role(out[1]), "user")

    def test_tail_never_starts_with_orphan_tool(self):
        out = collector._trim_history(self._convo(5))
        self.assertNotEqual(collector._msg_role(out[2]), "tool")


class _RateLimit(Exception):
    status_code = 429


class LlmRetryAndFallbackTests(unittest.TestCase):
    def setUp(self):
        self._prev = (collector.LLM_MAX_RETRIES, collector.LLM_BACKOFF_BASE)
        collector.LLM_MAX_RETRIES = 2
        collector.LLM_BACKOFF_BASE = 0  # no sleep in tests

    def tearDown(self):
        collector.LLM_MAX_RETRIES, collector.LLM_BACKOFF_BASE = self._prev

    def _client(self, effect):
        import types
        comp = types.SimpleNamespace(create=effect)
        return types.SimpleNamespace(chat=types.SimpleNamespace(completions=comp))

    def test_rate_limit_becomes_provider_error(self):
        # A raw 429 from the openai lib must be converted to ProviderError so the
        # provider loop can fall back — not crash the whole run.
        def always_429(**kwargs):
            raise _RateLimit("Rate limit exceeded")
        p = collector.AgentProvider(self._client(always_429), "m")
        p.name = "mistral"
        with self.assertRaises(collector.ProviderError) as ctx:
            p._complete([{"role": "user", "content": "x"}], [])
        self.assertIn("rate limit", str(ctx.exception).lower())

    def test_permanent_error_does_not_retry(self):
        # 402 (payment) / 404 (bad model) must fail fast — no retry — so the
        # provider loop falls back immediately instead of waiting on backoff.
        class _Payment(Exception):
            status_code = 402
        calls = {"n": 0}
        def always_402(**kwargs):
            calls["n"] += 1
            raise _Payment("Payment required")
        p = collector.AgentProvider(self._client(always_402), "m")
        p.name = "cerebras"
        with self.assertRaises(collector.ProviderError):
            p._complete([{"role": "user", "content": "x"}], [])
        self.assertEqual(calls["n"], 1)  # exactly one attempt, no retry

    def test_insufficient_balance_429_is_permanent(self):
        # Z.ai reports "no balance" as HTTP 429 (code 1113). It must NOT be
        # treated as a transient rate limit — no retry, fail straight to fallback.
        class _Balance(Exception):
            status_code = 429
        calls = {"n": 0}
        def no_balance(**kwargs):
            calls["n"] += 1
            raise _Balance("Error 429: Insufficient balance or no resource package. Please recharge.")
        p = collector.AgentProvider(self._client(no_balance), "glm")
        p.name = "z"
        with self.assertRaises(collector.ProviderError):
            p._complete([{"role": "user", "content": "x"}], [])
        self.assertEqual(calls["n"], 1)

    def test_retry_then_success(self):
        # First call 429, second succeeds → _complete returns the response.
        import types
        calls = {"n": 0}
        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _RateLimit("Rate limit exceeded")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(tool_calls=None, content="ok"))])
        p = collector.AgentProvider(self._client(flaky), "m")
        p.name = "mistral"
        resp = p._complete([{"role": "user", "content": "x"}], [])
        self.assertEqual(calls["n"], 2)
        self.assertEqual(resp.choices[0].message.content, "ok")


if __name__ == "__main__":
    unittest.main()
