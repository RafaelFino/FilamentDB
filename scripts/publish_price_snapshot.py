#!/usr/bin/env python3
"""Publish a validated FilamentDB price snapshot through the public ingest API."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_URL = "https://filamentdb-api.learnops.duckdns.org"


def post_offer(url: str, secret: str, offer: dict, collected_at: str | None) -> dict:
    payload = dict(offer)
    if collected_at:
        payload["collected_at"] = collected_at
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/ingest/prices",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Proxy-Secret": secret,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {"status": response.status, "body": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API connection failed: {exc.reason}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", nargs="?", help="Snapshot JSON; defaults to the latest dated snapshot")
    args = parser.parse_args()

    api_url = os.getenv("FILAMENTDB_API_URL", DEFAULT_API_URL).strip().rstrip("/")
    secret = os.getenv("FILAMENTDB_API_SECRET", "")
    if not secret:
        raise RuntimeError("FILAMENTDB_API_SECRET is not configured")
    if not api_url.startswith(("http://", "https://")):
        raise RuntimeError("FILAMENTDB_API_URL must be an absolute HTTP(S) URL")

    snapshot_path = Path(args.snapshot) if args.snapshot else None
    if snapshot_path is None:
        snapshots = sorted((ROOT / "data" / "price-data").glob("*.json"))
        if not snapshots:
            raise RuntimeError("No price snapshot found")
        snapshot_path = snapshots[-1]
    if not snapshot_path.is_absolute():
        snapshot_path = ROOT / snapshot_path
    if not snapshot_path.exists():
        raise RuntimeError(f"Snapshot not found: {snapshot_path}")

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    offers = snapshot.get("offers")
    if not isinstance(offers, list):
        raise RuntimeError("Snapshot has no valid offers array")

    collected_at = snapshot.get("collected_at")
    print(f"[INFO] Publishing {len(offers)} offers from {snapshot_path}")
    accepted = 0
    for index, offer in enumerate(offers, 1):
        try:
            result = post_offer(api_url, secret, offer, collected_at)
        except Exception as exc:
            key = offer.get("filament_key", "?")
            store = offer.get("store", "?")
            url = offer.get("url", "?")
            print(f"[ERROR] Offer {index}/{len(offers)} failed: {key} | {store} | {url} | {exc}", file=sys.stderr)
            raise
        status = result["body"].get("status", "unknown")
        print(f"[INFO] {index}/{len(offers)} -> HTTP {result['status']} ({status}) {offer.get('filament_key')} | {offer.get('store')}", flush=True)
        if result["status"] not in (200, 201):
            raise RuntimeError(f"Unexpected API status: {result['status']}")
        accepted += 1

    print(f"[INFO] API publication complete: {accepted}/{len(offers)} offers accepted")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
