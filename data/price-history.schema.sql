PRAGMA foreign_keys = ON;

-- Price intelligence is intentionally isolated from filament.db.
-- filament_id is a logical FK to filament.db.filament_profiles(id).
-- SQLite cannot enforce a foreign key across separate database files.

CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    domain TEXT,
    marketplace INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filament_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    external_id TEXT,
    seller TEXT,
    title TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, url),
    FOREIGN KEY(store_id) REFERENCES stores(id)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    price REAL NOT NULL,
    original_price REAL,
    shipping REAL,
    total_price REAL,
    currency TEXT NOT NULL DEFAULT 'BRL',
    available INTEGER,
    coupon TEXT,
    source TEXT,
    notes TEXT,
    FOREIGN KEY(offer_id) REFERENCES offers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'started',
    items_found INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_offers_filament ON offers(filament_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_offer_time ON price_snapshots(offer_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON price_snapshots(collected_at);
CREATE INDEX IF NOT EXISTS idx_runs_source_time ON collection_runs(source, started_at);

CREATE VIEW IF NOT EXISTS current_offers AS
SELECT
    o.id AS offer_id,
    o.filament_id,
    s.name AS store,
    o.title,
    o.url,
    o.seller,
    ps.price,
    ps.original_price,
    ps.shipping,
    ps.total_price,
    ps.currency,
    ps.available,
    ps.collected_at
FROM offers o
JOIN stores s ON s.id = o.store_id
JOIN price_snapshots ps ON ps.id = (
    SELECT ps2.id
    FROM price_snapshots ps2
    WHERE ps2.offer_id = o.id
    ORDER BY ps2.collected_at DESC, ps2.id DESC
    LIMIT 1
)
WHERE o.active = 1;
