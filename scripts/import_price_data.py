#!/usr/bin/env python3
"""Import all immutable price snapshots from data/price-data into price-history.db.
This is intentionally explicit: the web request path never imports or mutates price data.
"""
from src import prices

def main():
    result = prices.import_price_data()
    print(f"[INFO] Arquivos de snapshot: {result['files']}")
    print(f"[INFO] Ofertas importadas: {result['imported_offers']}")
    print(f"[INFO] Snapshots já processados: {result['skipped']}")
    print(f"[INFO] Erros: {result['errors']}")
    if result['errors']:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
