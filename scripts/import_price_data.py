#!/usr/bin/env python3
"""Import all immutable price snapshots from data/price-data into price-history.db.
This is intentionally explicit: the web request path never imports or mutates price data.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, prices  # noqa: E402

config.load()

def main():
    result = prices.import_price_data()
    synced = result["files"] - result["skipped"] - result["errors"]
    print(f"[INFO] Arquivos de snapshot: {result['files']}")
    if synced:
        print(f"[INFO] Snapshots sincronizados: {synced} ({result['imported_offers']} ofertas)")
    if result["skipped"]:
        print(f"[INFO] Snapshots já em dia: {result['skipped']}")
    if result["errors"]:
        print(f"[ERROR] Falhas na importação: {result['errors']}")
        raise SystemExit(1)
    if not result["files"]:
        print("[INFO] Nenhum snapshot em data/price-data/ — interface de preços ficará vazia.")

if __name__ == "__main__":
    main()
