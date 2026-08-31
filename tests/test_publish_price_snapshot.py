import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_price_snapshot as publisher


def test_post_offer_sends_secret_and_collected_at():
    captured = {}

    class Response:
        status = 201
        def read(self):
            return b'{"ok":true,"status":"accepted"}'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    offer = {
        "filament_key": "pla|esun|pla+hs",
        "store": "Example",
        "url": "https://example.com/p",
        "price": 99.9,
        "quantity": 1,
        "unit_weight_g": 1000,
        "price_basis": "total",
    }
    with patch.object(publisher.urllib.request, "urlopen", fake_urlopen):
        result = publisher.post_offer("https://api.example", "secret", offer, "2026-08-30T10:00:00-03:00")

    assert result["status"] == 201
    assert captured["timeout"] == 30
    assert captured["request"].get_header("X-proxy-secret") == "secret"
    body = json.loads(captured["request"].data.decode())
    assert body["collected_at"] == "2026-08-30T10:00:00-03:00"
    assert body["filament_key"] == offer["filament_key"]


def test_main_requires_secret(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"offers": []}), encoding="utf-8")
    monkeypatch.delenv("FILAMENTDB_API_SECRET", raising=False)
    monkeypatch.setattr(sys, "argv", ["publish_price_snapshot.py", str(snapshot)])
    try:
        publisher.main()
    except RuntimeError as exc:
        assert "FILAMENTDB_API_SECRET" in str(exc)
    else:
        raise AssertionError("Expected missing-secret failure")
