#!/usr/bin/env python3
"""Initialize and seed the isolated FilamentDB price-history database.

The catalog remains the source of truth. Every offer is linked to an existing
filament_profiles.id from filament.db; this script refuses to create an offer
when that filament is missing or is not marked tracking=1.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILAMENT_DB = ROOT / "filament.db"
DEFAULT_PRICE_DB = ROOT / "price-history.db"
SCHEMA = ROOT / "price-history" / "schema.sql"

# Only observations that were explicitly identified in the previous report
# and can be mapped to an existing tracked catalog profile are seeded here.
INITIAL_OBSERVATIONS = [
    {
        "manufacturer": "Voolt3D",
        "profile_name": "Voolt3D PLA Velvet",
        "store": "Voolt3D",
        "domain": "voolt3d.com.br",
        "marketplace": 0,
        "title": "PLA Velvet High Speed Premium 1 kg",
        "url": "https://voolt3d.com.br/velvet",
        "price": 74.90,
        "original_price": 129.99,
        "available": 1,
        "source": "initial-report-2026-08-29",
        "notes": "Preço observado no Pix; linha Velvet High Speed Premium.",
    },
    {
        "manufacturer": "Voolt3D",
        "profile_name": "Voolt3D PLA Velvet",
        "store": "Voolt3D",
        "domain": "voolt3d.com.br",
        "marketplace": 0,
        "title": "PLA Velvet High Speed Premium 1 kg",
        "url": "https://voolt3d.com.br/velvet",
        "price": 84.90,
        "original_price": 129.99,
        "available": 1,
        "source": "initial-report-2026-08-29",
        "notes": "Outra cor/preço observado no Pix; mesma linha premium.",
    },
    {
        "manufacturer": "Voolt3D",
        "profile_name": "Voolt3D PETG HF",
        "store": "Voolt3D",
        "domain": "voolt3d.com.br",
        "marketplace": 0,
        "title": "PETG HF High Fluidity Premium 1 kg",
        "url": "https://www.voolt3d.com.br/petg",
        "price": 99.90,
        "available": 1,
        "source": "initial-report-2026-08-29",
        "notes": "Preço observado no Pix; linha PETG High Fluidity Premium.",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialize_price_db(price_db: Path) -> sqlite3.Connection:
    price_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(price_db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def resolve_filament_id(filament_conn: sqlite3.Connection, observation: dict) -> int:
    row = filament_conn.execute(
        """
        SELECT fp.id
        FROM filament_profiles fp
        JOIN manufacturers m ON m.id = fp.manufacturer_id
        WHERE m.name = ?
          AND fp.profile_name = ?
          AND fp.tracking = 1
        """,
        (observation["manufacturer"], observation["profile_name"]),
    ).fetchone()
    if not row:
        raise RuntimeError(
            "Tracked filament not found: "
            f"{observation['manufacturer']} / {observation['profile_name']}"
        )
    return int(row[0])


def seed_initial_observations(filament_db: Path, price_db: Path) -> int:
    filament = sqlite3.connect(filament_db)
    price = initialize_price_db(price_db)
    collected_at = "2026-08-29T00:00:00-03:00"
    run_id = price.execute(
        "INSERT INTO collection_runs(started_at, finished_at, source, status) VALUES (?, ?, ?, ?)",
        (collected_at, collected_at, "initial-report-2026-08-29", "completed"),
    ).lastrowid

    inserted = 0
    try:
        for item in INITIAL_OBSERVATIONS:
            filament_id = resolve_filament_id(filament, item)
            store_id = price.execute(
                """
                INSERT INTO stores(name, domain, marketplace)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET domain=excluded.domain, marketplace=excluded.marketplace
                RETURNING id
                """,
                (item["store"], item["domain"], item["marketplace"]),
            ).fetchone()[0]

            offer_id = price.execute(
                """
                INSERT INTO offers(filament_id, store_id, url, title, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(store_id, url) DO UPDATE SET
                    filament_id=excluded.filament_id,
                    title=excluded.title,
                    last_seen_at=excluded.last_seen_at
                RETURNING id
                """,
                (filament_id, store_id, item["url"], item["title"], collected_at),
            ).fetchone()[0]

            price.execute(
                """
                INSERT INTO price_snapshots(
                    offer_id, collected_at, price, original_price, currency,
                    available, source, notes
                ) VALUES (?, ?, ?, ?, 'BRL', ?, ?, ?)
                """,
                (
                    offer_id,
                    collected_at,
                    item["price"],
                    item.get("original_price"),
                    item.get("available"),
                    item["source"],
                    item.get("notes"),
                ),
            )
            inserted += 1

        price.execute(
            "UPDATE collection_runs SET items_found = ? WHERE id = ?",
            (inserted, run_id),
        )
        price.commit()
    except Exception:
        price.rollback()
        raise
    finally:
        filament.close()
        price.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filament-db", type=Path, default=DEFAULT_FILAMENT_DB)
    parser.add_argument("--price-db", type=Path, default=DEFAULT_PRICE_DB)
    parser.add_argument("--init-only", action="store_true", help="Create schema without seeding")
    args = parser.parse_args()

    if not args.filament_db.exists():
        raise SystemExit(f"filament.db not found: {args.filament_db}. Run build.py first.")

    if args.init_only:
        conn = initialize_price_db(args.price_db)
        conn.close()
        print(f"Initialized {args.price_db}")
        return

    count = seed_initial_observations(args.filament_db, args.price_db)
    print(f"Seeded {count} initial price observations into {args.price_db}")


if __name__ == "__main__":
    main()
