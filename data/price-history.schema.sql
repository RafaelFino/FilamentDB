PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    domain TEXT,
    marketplace INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filament_key TEXT NOT NULL,
    variant_id INTEGER,
    filament_id INTEGER,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_weight_g REAL NOT NULL DEFAULT 1000,
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

CREATE INDEX IF NOT EXISTS idx_snapshots_offer_time ON price_snapshots(offer_id, collected_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON price_snapshots(collected_at);
CREATE INDEX IF NOT EXISTS idx_runs_source_time ON collection_runs(source, started_at);

