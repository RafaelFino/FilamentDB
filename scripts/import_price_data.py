#!/usr/bin/env python3
"""Import all immutable price snapshots from data/price-data into price-history.db.
Idempotent: a snapshot file is imported once by filename/hash.
"""
from src import prices

def main():
    conn = prices.get_connection()
    row = conn.execute("SELECT COUNT(*) AS n FROM collection_runs WHERE snapshot_file IS NOT NULL").fetchone()
    offers = conn.execute("SELECT COUNT(*) AS n FROM price_snapshots").fetchone()
    print(f"[INFO] Snapshots processados: {row['n']}")
    print(f"[INFO] Price snapshots no banco: {offers['n']}")
    conn.close()

if __name__ == "__main__":
    main()
