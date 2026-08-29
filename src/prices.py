"""Read-only price intelligence service for the web UI."""
from __future__ import annotations
import json, sqlite3, unicodedata, re
from pathlib import Path
from statistics import median
from src import database, config
ROOT=Path(__file__).resolve().parent.parent
PRICE_DB_PATH=config.database_path("price-history.db")
SCHEMA_PATH=ROOT/"data"/"price-history.schema.sql"
PRICE_DATA_PATH=ROOT/"data"/"price-data"
SOURCES_PATH=ROOT/"data"/"price-sources.json"

def normalize_key_part(value):
    text=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii")
    return re.sub(r"\s+"," ",text.strip().lower())

def _catalog_rows():
    c=database.get_db_connection(); rows=c.execute("""SELECT fp.id,fp.filament_key,fp.commercial_name,fp.profile_name,fp.line,fp.line_positioning,fp.line_finish,fp.tracking, m.name AS material_name,mf.name AS manufacturer_name FROM filament_profiles fp JOIN materials m ON m.id=fp.material_id JOIN manufacturers mf ON mf.id=fp.manufacturer_id WHERE fp.active=1 AND fp.tracking=1 ORDER BY m.name,mf.name,fp.commercial_name""").fetchall(); c.close(); return [dict(r) for r in rows]

def _catalog_map():
    return {r["filament_key"]: r for r in _catalog_rows()}

def _ensure_variant(conn, filament_id, color_name):
    if not color_name: return None
    norm=normalize_key_part(color_name)
    row=conn.execute("SELECT id,color_name FROM variants_lookup WHERE filament_id=? AND color_norm=? LIMIT 1",(filament_id,norm)).fetchone() if _table_exists(conn,"variants_lookup") else None
    if row: return row[0]
    # variant_id is a logical FK to filament.db; resolve existing variant by attached catalog when possible.
    cat=database.get_db_connection(); row=cat.execute("SELECT id FROM filament_variants WHERE filament_id=? AND lower(trim(color_name))=lower(trim(?)) LIMIT 1",(filament_id,color_name)).fetchone(); cat.close()
    return row[0] if row else None

def _table_exists(conn,name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def _migrate_identity(conn):
    cols={r[1] for r in conn.execute("PRAGMA table_info(offers)").fetchall()}
    if not cols: return
    if "filament_key" not in cols: conn.execute("ALTER TABLE offers ADD COLUMN filament_key TEXT")
    if "variant_id" not in cols: conn.execute("ALTER TABLE offers ADD COLUMN variant_id INTEGER")
    if "quantity" not in cols: conn.execute("ALTER TABLE offers ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
    if "unit_weight_g" not in cols: conn.execute("ALTER TABLE offers ADD COLUMN unit_weight_g REAL NOT NULL DEFAULT 1000")
    if "price_basis" not in cols: conn.execute("ALTER TABLE offers ADD COLUMN price_basis TEXT NOT NULL DEFAULT 'total'")
    if "offer_key" not in cols: conn.execute("ALTER TABLE offers ADD COLUMN offer_key TEXT")
    if "filament_id" in cols:
        cat=database.get_db_connection()
        for row in conn.execute("SELECT id,filament_id FROM offers WHERE filament_key IS NULL OR filament_key='' ").fetchall():
            if row[1] is None: continue
            x=cat.execute("SELECT filament_key FROM filament_profiles WHERE id=?",(row[1],)).fetchone()
            if x: conn.execute("UPDATE offers SET filament_key=? WHERE id=?",(x[0],row[0]))
        cat.close()
    # Existing rows came from the old model, where price was treated as package total.
    conn.execute("UPDATE offers SET price_basis='total' WHERE price_basis IS NULL OR price_basis='' ")
    for row in conn.execute("SELECT id,store_id,url,quantity,unit_weight_g,price_basis,offer_key FROM offers").fetchall():
        if not row[6]:
            key=f"{row[1]}|{row[2]}|{max(int(row[3] or 1),1)}|{float(row[4] or 1000):g}|{row[5] or 'total'}"
            conn.execute("UPDATE offers SET offer_key=? WHERE id=?",(key,row[0]))
    # The old schema had UNIQUE(store_id,url), which prevents legitimate tiered offers
    # from sharing the same product page. Rebuild only when that legacy unique index exists.
    legacy_unique=False
    for idx in conn.execute("PRAGMA index_list('offers')").fetchall():
        if int(idx[2]) != 1: continue
        name=idx[1]
        cols_idx=[r[2] for r in conn.execute(f"PRAGMA index_info('{name}')").fetchall()]
        if cols_idx == ["store_id","url"]:
            legacy_unique=True; break
    if legacy_unique:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("CREATE TABLE offers_new (id INTEGER PRIMARY KEY AUTOINCREMENT,offer_key TEXT NOT NULL UNIQUE,filament_key TEXT NOT NULL,variant_id INTEGER,filament_id INTEGER,quantity INTEGER NOT NULL DEFAULT 1,unit_weight_g REAL NOT NULL DEFAULT 1000,price_basis TEXT NOT NULL DEFAULT 'total',store_id INTEGER NOT NULL,url TEXT NOT NULL,external_id TEXT,seller TEXT,title TEXT,active INTEGER NOT NULL DEFAULT 1,first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(store_id) REFERENCES stores(id))")
        conn.execute("INSERT INTO offers_new(id,offer_key,filament_key,variant_id,filament_id,quantity,unit_weight_g,price_basis,store_id,url,external_id,seller,title,active,first_seen_at,last_seen_at) SELECT id,offer_key,filament_key,variant_id,filament_id,quantity,unit_weight_g,price_basis,store_id,url,external_id,seller,title,active,first_seen_at,last_seen_at FROM offers")
        conn.execute("DROP TABLE offers")
        conn.execute("ALTER TABLE offers_new RENAME TO offers")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_filament_key ON offers(filament_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_variant ON offers(variant_id)")
    conn.commit()

def _ensure_column(conn, table, column, definition):
    cols={r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def _migrate_collection_schema(conn):
    _ensure_column(conn,"collection_runs","snapshot_file","TEXT")
    _ensure_column(conn,"collection_runs","snapshot_hash","TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_snapshot_file ON collection_runs(snapshot_file) WHERE snapshot_file IS NOT NULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS collection_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        filament_key TEXT,
        color TEXT,
        store TEXT NOT NULL,
        status TEXT NOT NULL,
        offers_found INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY(run_id) REFERENCES collection_runs(id) ON DELETE CASCADE
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_collection_results_run ON collection_results(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_collection_results_filament ON collection_results(filament_key)")

def _snapshot_key(x):
    key=x.get("filament_key")
    if key: return "|".join(normalize_key_part(v) for v in key.split("|"))
    material=x.get("material"); manufacturer=x.get("manufacturer"); model=x.get("model") or x.get("line") or x.get("profile_name")
    if material and manufacturer and model:
        return "|".join(normalize_key_part(v) for v in (material,manufacturer,model))
    return None

def _snapshot_price_basis(x):
    basis = str(x.get("price_basis") or x.get("price_type") or "").strip().lower()
    if basis in {"unit", "per_unit", "unit_price", "per_roll", "por_rolo"}: return "unit"
    if basis in {"total", "package", "pack", "bundle", "kit"}: return "total"
    text = f"{x.get('title') or ''} {x.get('notes') or ''}".lower()
    if "atacado" in text or "por rolo" in text or "preço por rolo" in text or "preco por rolo" in text:
        return "unit"
    return "total"

def _normalized_total_price(price, quantity, basis):
    if basis == "unit": return float(price) * max(int(quantity or 1), 1)
    return float(price)

def _upsert_snapshot_offer(conn, x, cat, collected, source_default):
    key=_snapshot_key(x)
    if key not in cat: return False
    profile=cat[key]
    store=x.get("store") or "Desconhecida"
    domain=x.get("domain") or ""
    sid=conn.execute("INSERT INTO stores(name,domain,marketplace) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain,marketplace=excluded.marketplace RETURNING id",(store,domain,int(x.get("marketplace",False)))).fetchone()[0]
    color=x.get("color_name") or x.get("color")
    variant_id=_ensure_variant(conn,profile["id"],color)
    quantity=max(int(x.get("quantity",1) or 1),1)
    unit_weight=float(x.get("unit_weight_g",1000) or 1000)
    basis=_snapshot_price_basis(x)
    url=x.get("url")
    if not url: return False
    offer_key=f"{sid}|{url}|{quantity}|{unit_weight:g}|{basis}"
    row=conn.execute("SELECT id FROM offers WHERE offer_key=?",(offer_key,)).fetchone()
    if row:
        oid=row[0]
        conn.execute("UPDATE offers SET filament_key=?,variant_id=?,filament_id=?,quantity=?,unit_weight_g=?,price_basis=?,external_id=?,seller=?,title=?,active=1,last_seen_at=? WHERE id=?",(key,variant_id,profile["id"],quantity,unit_weight,basis,x.get("external_id"),x.get("seller"),x.get("title"),collected,oid))
    else:
        oid=conn.execute("INSERT INTO offers(offer_key,filament_key,variant_id,filament_id,quantity,unit_weight_g,price_basis,store_id,url,external_id,seller,title,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",(offer_key,key,variant_id,profile["id"],quantity,unit_weight,basis,sid,url,x.get("external_id"),x.get("seller"),x.get("title"),collected)).fetchone()[0]
    price=float(x["price"])
    shipping=x.get("shipping")
    supplied_total=x.get("total_price")
    total=float(supplied_total) if supplied_total is not None else _normalized_total_price(price,quantity,basis)
    exists=conn.execute("SELECT 1 FROM price_snapshots WHERE offer_id=? AND collected_at=?",(oid,collected)).fetchone()
    if not exists:
        conn.execute("INSERT INTO price_snapshots(offer_id,collected_at,price,original_price,shipping,total_price,currency,available,coupon,source,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(oid,collected,price,x.get("original_price"),shipping,total,x.get("currency","BRL"),x.get("available"),x.get("coupon"),x.get("source") or source_default,x.get("notes")))
    return True

def _import_snapshot(conn, path):
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,dict) or not isinstance(payload.get("offers",[]),list):
        raise ValueError(f"Snapshot inválido: {path.name}")
    snapshot_date=payload.get("snapshot_date") or path.stem
    collected=payload.get("collected_at") or f"{snapshot_date}T00:00:00-03:00"
    digest=__import__("hashlib").sha256(path.read_bytes()).hexdigest()
    existing=conn.execute("SELECT id,snapshot_hash FROM collection_runs WHERE snapshot_file=? OR snapshot_hash=? ORDER BY id DESC LIMIT 1",(path.name,digest)).fetchone()
    if existing:
        if existing[1] == digest: return 0,0,True
        # A changed file with the same date/name is treated as a deliberate correction.
        # Keep its historical price rows; replace only the collection-run metadata so the
        # corrected snapshot can be ingested and tiered offers can be discovered.
        conn.execute("DELETE FROM collection_runs WHERE id=?",(existing[0],))
    run=conn.execute("INSERT INTO collection_runs(started_at,finished_at,source,status,items_found,notes,snapshot_file,snapshot_hash) VALUES(?,?,?,?,?,?,?,?) RETURNING id",(collected,collected,payload.get("collector") or "price-agent","completed",0,payload.get("notes"),path.name,digest)).fetchone()[0]
    cat=_catalog_map(); imported=0
    for x in payload["offers"]:
        if _upsert_snapshot_offer(conn,x,cat,collected,payload.get("collector") or "price-agent"): imported+=1
    for r in payload.get("collection",[]):
        conn.execute("INSERT INTO collection_results(run_id,filament_key,color,store,status,offers_found,notes) VALUES(?,?,?,?,?,?,?)",(run,r.get("filament_key"),r.get("color") or r.get("color_name"),r.get("store") or "Desconhecida",r.get("status") or "not_found",int(r.get("offers_found",0) or 0),r.get("notes")))
    conn.execute("UPDATE collection_runs SET items_found=? WHERE id=?",(imported,run))
    conn.commit()
    return imported,len(payload.get("collection",[])),False

def _sync_sources(conn):
    if not SOURCES_PATH.exists(): return
    for s in json.loads(SOURCES_PATH.read_text(encoding="utf-8")):
        conn.execute("INSERT INTO stores(name,domain,marketplace) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain,marketplace=excluded.marketplace",(s["name"],s["domain"],int(s.get("marketplace",False))))
    conn.commit()

def _recreate_view(conn):
    conn.execute("DROP VIEW IF EXISTS current_offers")
    conn.execute("""CREATE VIEW current_offers AS
        SELECT o.id AS offer_id, o.filament_key, o.variant_id, o.filament_id,
               s.name AS store, o.title, o.url, o.seller,
               ps.price, ps.original_price, ps.shipping, ps.total_price, ps.currency,
               ps.available, ps.collected_at, ps.source, ps.notes,
               o.quantity, o.unit_weight_g, o.price_basis
        FROM offers o
        JOIN stores s ON s.id=o.store_id
        JOIN price_snapshots ps ON ps.id=(SELECT ps2.id FROM price_snapshots ps2 WHERE ps2.offer_id=o.id ORDER BY ps2.collected_at DESC, ps2.id DESC LIMIT 1)
        WHERE o.active=1""")

def get_connection():
    PRICE_DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(PRICE_DB_PATH); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8")); _migrate_identity(c); _migrate_collection_schema(c); _recreate_view(c); _sync_sources(c); return c

def import_price_data():
    """Import all immutable snapshots explicitly. The web request path never mutates price data."""
    PRICE_DATA_PATH.mkdir(parents=True, exist_ok=True)
    c=get_connection()
    files=sorted(PRICE_DATA_PATH.glob("*.json"))
    imported=0; skipped=0; errors=0
    for path in files:
        try:
            n, _, was_skipped = _import_snapshot(c,path)
            if was_skipped: skipped += 1
            else: imported += n
        except Exception as exc:
            errors += 1
            c.execute("INSERT INTO collection_runs(started_at,finished_at,source,status,notes,snapshot_file) VALUES(CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?,?,?,?)",("price-agent","error",str(exc),path.name))
            c.commit()
    c.close()
    return {"files":len(files),"imported_offers":imported,"skipped":skipped,"errors":errors}

def dashboard():
    catalog = _catalog_rows()
    c = get_connection()
    offers = [dict(x) for x in c.execute("SELECT * FROM current_offers ORDER BY store,title").fetchall()]
    hist_rows = c.execute("SELECT offer_id,collected_at,price,shipping,total_price FROM price_snapshots ORDER BY collected_at, id").fetchall()
    collection_log = []
    for r in c.execute("SELECT id,started_at,finished_at,source,status,items_found,notes,snapshot_file FROM collection_runs ORDER BY started_at DESC, id DESC LIMIT 30").fetchall():
        item=dict(r); item["results"]=[dict(x) for x in c.execute("SELECT filament_key,color,store,status,offers_found,notes FROM collection_results WHERE run_id=? ORDER BY store,filament_key",(r["id"],)).fetchall()]
        collection_log.append(item)
    c.close()

    cat = database.get_db_connection()
    variant_rows = cat.execute("SELECT id,filament_id,color_name FROM filament_variants").fetchall()
    cat.close()
    colors = {r["id"]: r["color_name"] for r in variant_rows}

    history_by_offer = {}
    for r in hist_rows:
        history_by_offer.setdefault(r["offer_id"], []).append(dict(r))

    for o in offers:
        o["variant_color"] = colors.get(o.get("variant_id"))
        quantity = max(int(o.get("quantity") or 1), 1)
        unit_weight = float(o.get("unit_weight_g") or 1000)
        weight = unit_weight * quantity
        total = o.get("total_price") if o.get("total_price") is not None else o.get("price")
        o["total_weight_g"] = weight
        o["price_per_kg"] = (float(total) / weight * 1000) if total is not None and weight else None
        o["is_volume_offer"] = quantity > 1 or unit_weight > 1000
        series = history_by_offer.get(o["offer_id"], [])
        normalized = []
        for h in series:
            htotal = h["total_price"] if h["total_price"] is not None else h["price"]
            if htotal is not None and weight:
                normalized.append({**h, "price_per_kg": float(htotal) / weight * 1000})
        o["historical_best_price_per_kg"] = min((h["price_per_kg"] for h in normalized), default=None)
        o["historical_best_price"] = min((float(h["price"]) for h in series if h["price"] is not None), default=None)
        if len(series) >= 2:
            previous = series[-2]["total_price"] if series[-2]["total_price"] is not None else series[-2]["price"]
            current = total
            o["price_change_pct"] = ((float(current) - float(previous)) / float(previous) * 100) if previous and current is not None else None
        else:
            o["price_change_pct"] = None

    cur = {}
    hist = {}
    for o in offers:
        cur.setdefault(o["filament_key"], []).append(o)
        for h in history_by_offer.get(o["offer_id"], []):
            total = h["total_price"] if h["total_price"] is not None else h["price"]
            weight = float(o.get("unit_weight_g") or 1000) * max(int(o.get("quantity") or 1), 1)
            if total is not None and weight:
                hist.setdefault(o["filament_key"], []).append({**h, "price_per_kg": float(total) / weight * 1000})

    items = []
    for fil in catalog:
        current = cur.get(fil["filament_key"], [])
        historical = hist.get(fil["filament_key"], [])
        best = min(current, key=lambda o: o["price_per_kg"] if o["price_per_kg"] is not None else float("inf")) if current else None
        best_hist = min(historical, key=lambda h: h["price_per_kg"]) if historical else None
        historical_prices = [h["price_per_kg"] for h in historical]
        med = median(historical_prices) if historical_prices else None
        mn = min(historical_prices) if historical_prices else None
        opportunity = ((med - best["price_per_kg"]) / med * 100) if best and best["price_per_kg"] is not None and med else 0
        drops = [o["price_change_pct"] for o in current if o.get("price_change_pct") is not None and o["price_change_pct"] < 0]
        max_drop = abs(min(drops)) if drops else 0
        items.append({
            **fil,
            "best_price": best["price"] if best else None,
            "best_price_per_kg": best["price_per_kg"] if best else None,
            "best_store": best["store"] if best else None,
            "best_url": best["url"] if best else None,
            "best_is_volume": best["is_volume_offer"] if best else False,
            "median_price": med,
            "min_price": mn,
            "best_historical_price_per_kg": best_hist["price_per_kg"] if best_hist else None,
            "best_historical_price": best_hist["price"] if best_hist else None,
            "best_historical_date": best_hist["collected_at"] if best_hist else None,
            "opportunity_pct": opportunity,
            "discount_pct": opportunity,
            "max_drop_pct": max_drop,
            "offer_count": len(current),
            "volume_offer_count": sum(1 for o in current if o["is_volume_offer"]),
            "offers": current,
        })
    latest=collection_log[0] if collection_log else None
    latest_results=(latest or {}).get("results",[])
    return {
        "summary": {
            "tracked_count": len(catalog),
            "priced_count": sum(1 for x in items if x["offer_count"]),
            "offer_count": len(offers),
            "volume_offer_count": sum(x["volume_offer_count"] for x in items),
            "opportunity_count": sum(1 for x in items if x["opportunity_pct"] > 5),
        },
        "collection_summary": {
            "snapshot_file": (latest or {}).get("snapshot_file"),
            "collected_at": (latest or {}).get("finished_at") or (latest or {}).get("started_at"),
            "status": (latest or {}).get("status"),
            "source": (latest or {}).get("source"),
            "offers_found": (latest or {}).get("items_found",0),
            "sources_with_results": sum(1 for r in latest_results if r.get("status")=="found"),
            "sources_without_results": sum(1 for r in latest_results if r.get("status")!="found"),
        },
        "collection_log": collection_log,
        "items": items,
    }

def history(filament_id):
    row=next((x for x in _catalog_rows() if x["id"]==filament_id),None)
    if not row: return None
    c=get_connection(); rows=c.execute("SELECT ps.collected_at,ps.price,ps.original_price,ps.shipping,ps.total_price,ps.currency,ps.available,ps.source,o.id AS offer_id,o.filament_key,o.variant_id,o.title,o.url,o.seller,s.name AS store FROM price_snapshots ps JOIN offers o ON o.id=ps.offer_id JOIN stores s ON s.id=o.store_id WHERE o.filament_key=? ORDER BY ps.collected_at,ps.id",(row["filament_key"],)).fetchall(); c.close(); return [dict(r) for r in rows]
