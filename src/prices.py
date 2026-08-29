"""Read-only price intelligence service for the web UI."""
from __future__ import annotations
import json, sqlite3, unicodedata, re
from pathlib import Path
from statistics import median
from src import database, config
ROOT=Path(__file__).resolve().parent.parent
PRICE_DB_PATH=config.database_path("price-history.db")
SCHEMA_PATH=ROOT/"data"/"price-history.schema.sql"
SEED_PATH=ROOT/"data"/"price-history.seed.json"
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
    # Backfill legacy offers while the old filament_id is still available. The build preserves IDs,
    # so this migration is deterministic and does not lose the existing price history.
    if "filament_id" in cols:
        cat=database.get_db_connection()
        for row in conn.execute("SELECT id,filament_id FROM offers WHERE filament_key IS NULL OR filament_key='' ").fetchall():
            if row[1] is None: continue
            x=cat.execute("SELECT filament_key FROM filament_profiles WHERE id=?",(row[1],)).fetchone()
            if x: conn.execute("UPDATE offers SET filament_key=? WHERE id=?",(x[0],row[0]))
        cat.close()
    conn.execute("UPDATE offers SET active=0 WHERE filament_key IS NULL OR filament_key='' ")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_filament_key ON offers(filament_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_offers_variant ON offers(variant_id)")
    conn.commit()

def _sync_sources(conn):
    if not SOURCES_PATH.exists(): return
    for s in json.loads(SOURCES_PATH.read_text(encoding="utf-8")):
        conn.execute("INSERT INTO stores(name,domain,marketplace) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain,marketplace=excluded.marketplace",(s["name"],s["domain"],int(s.get("marketplace",False))))

def _sync_seed(conn):
    if not SEED_PATH.exists(): return
    seed=json.loads(SEED_PATH.read_text(encoding="utf-8")); cat=_catalog_map(); collected="2026-08-29T00:00:00-03:00"; run=None
    for x in seed:
        model=x.get("model") or x.get("line") or x.get("profile_name")
        key="|".join(normalize_key_part(v) for v in (x["material"],x["manufacturer"],model)) if x.get("material") else None
        # Backward compatibility: derive the key from the catalog by manufacturer/profile name.
        if key not in cat:
            matches=[r for r in cat.values() if r["manufacturer_name"].lower()==x["manufacturer"].lower() and (r["profile_name"]==x.get("profile_name") or r["commercial_name"]==x.get("profile_name"))]
            if len(matches)==1: key=matches[0]["filament_key"]
        if key not in cat: continue
        profile=cat[key]
        sid=conn.execute("INSERT INTO stores(name,domain,marketplace) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain RETURNING id",(x["store"],x["domain"],int(x.get("marketplace",False)))).fetchone()[0]
        oid=conn.execute("SELECT id FROM offers WHERE store_id=? AND url=?",(sid,x["url"])).fetchone()
        color=x.get("color_name") or x.get("color")
        variant_id=_ensure_variant(conn,profile["id"],color)
        if oid:
            oid=oid[0]; conn.execute("UPDATE offers SET filament_key=?,variant_id=?,filament_id=?,quantity=?,unit_weight_g=?,external_id=?,seller=?,title=?,last_seen_at=? WHERE id=?",(key,variant_id,profile["id"],int(x.get("quantity",1) or 1),float(x.get("unit_weight_g",1000) or 1000),x.get("external_id"),x.get("seller"),x["title"],collected,oid))
        else:
            oid=conn.execute("INSERT INTO offers(filament_key,variant_id,filament_id,quantity,unit_weight_g,store_id,url,external_id,seller,title,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id",(key,variant_id,profile["id"],int(x.get("quantity",1) or 1),float(x.get("unit_weight_g",1000) or 1000),sid,x["url"],x.get("external_id"),x.get("seller"),x["title"],collected)).fetchone()[0]
        exists=conn.execute("SELECT 1 FROM price_snapshots WHERE offer_id=? AND collected_at=? AND price=?",(oid,collected,x["price"])).fetchone()
        if not exists:
            if run is None: run=conn.execute("INSERT INTO collection_runs(started_at,finished_at,source,status) VALUES(?,?,?,?) RETURNING id",(collected,collected,"verified-baseline-2026-08-29","completed")).fetchone()[0]
            conn.execute("INSERT INTO price_snapshots(offer_id,collected_at,price,original_price,shipping,total_price,currency,available,source,notes) VALUES(?,?,?,?,?,?,?,?,?,?)",(oid,collected,x["price"],x.get("original_price"),x.get("shipping"),(x["price"]+(x.get("shipping") or 0)) if x.get("shipping") is not None else None,"BRL",x.get("available"),x.get("source"),x.get("notes")))
            conn.execute("UPDATE collection_runs SET items_found=items_found+1 WHERE id=?",(run,))
    # Sanidade de identidade: uma loja oficial com o mesmo nome do fabricante
    # jamais pode representar outro fabricante. Marketplaces continuam livres
    # para vender qualquer marca.
    catalog_by_key = {r["filament_key"]: normalize_key_part(r["manufacturer_name"]) for r in _catalog_rows()}
    cat_conn = database.get_db_connection()
    manufacturer_keys = {normalize_key_part(r["name"]) for r in cat_conn.execute("SELECT name FROM manufacturers").fetchall()}
    cat_conn.close()
    for row in conn.execute("SELECT o.id,o.filament_key,s.name FROM offers o JOIN stores s ON s.id=o.store_id WHERE o.active=1").fetchall():
        store_key = normalize_key_part(row[2])
        manufacturer_key = catalog_by_key.get(row[1])
        # Só aplica a regra quando a loja é oficialmente nomeada como um fabricante.
        if store_key in manufacturer_keys and manufacturer_key and store_key != manufacturer_key:
            conn.execute("UPDATE offers SET active=0 WHERE id=?", (row[0],))
    conn.commit()
    conn.commit()

def _recreate_view(conn):
    conn.execute("DROP VIEW IF EXISTS current_offers")
    conn.execute("""CREATE VIEW current_offers AS
        SELECT o.id AS offer_id, o.filament_key, o.variant_id, o.filament_id,
               s.name AS store, o.title, o.url, o.seller,
               ps.price, ps.original_price, ps.shipping, ps.total_price, ps.currency,
               ps.available, ps.collected_at, ps.source, ps.notes,
               o.quantity, o.unit_weight_g
        FROM offers o
        JOIN stores s ON s.id=o.store_id
        JOIN price_snapshots ps ON ps.id=(SELECT ps2.id FROM price_snapshots ps2 WHERE ps2.offer_id=o.id ORDER BY ps2.collected_at DESC, ps2.id DESC LIMIT 1)
        WHERE o.active=1""")

def get_connection():
    PRICE_DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(PRICE_DB_PATH); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA_PATH.read_text(encoding="utf-8")); _migrate_identity(c); _recreate_view(c); _sync_sources(c); _sync_seed(c); return c

def dashboard():
    catalog=_catalog_rows(); c=get_connection(); offers=[dict(x) for x in c.execute("SELECT * FROM current_offers ORDER BY store,title").fetchall()]; c.close()
    # Resolve color names from the canonical catalog database, never from offer ordering.
    cat=database.get_db_connection(); variant_rows=cat.execute("SELECT id,filament_id,color_name FROM filament_variants").fetchall(); cat.close(); colors={r["id"]:r["color_name"] for r in variant_rows}
    for o in offers:
        o["variant_color"]=colors.get(o.get("variant_id"))
        weight=float(o.get("unit_weight_g") or 1000) * max(int(o.get("quantity") or 1),1)
        o["total_weight_g"]=weight
        o["price_per_kg"]=((o["total_price"] if o.get("total_price") is not None else o["price"])/weight*1000) if weight else None
    hist={}; c=get_connection(); rows=c.execute("SELECT offer_id,price FROM price_snapshots").fetchall(); c.close()
    for r in rows: hist.setdefault(r[0],[]).append(r[1])
    cur={}
    for o in offers: cur.setdefault(o["filament_key"],[]).append(o)
    items=[]
    for fil in catalog:
        current=cur.get(fil["filament_key"],[]); all_prices=[p for o in current for p in hist.get(o["offer_id"],[])]; best=min(current,key=lambda o:o["total_price"] if o["total_price"] is not None else o["price"]) if current else None; med=median(all_prices) if all_prices else None; mn=min(all_prices) if all_prices else None; discount=((med-best["price"])/med*100) if best and med else 0
        items.append({**fil,"best_price":best["price"] if best else None,"best_store":best["store"] if best else None,"best_url":best["url"] if best else None,"median_price":med,"min_price":mn,"discount_pct":discount,"offer_count":len(current),"offers":current})
    return {"summary":{"tracked_count":len(catalog),"priced_count":sum(1 for x in items if x["offer_count"]),"offer_count":len(offers)},"items":items}

def history(filament_id):
    row=next((x for x in _catalog_rows() if x["id"]==filament_id),None)
    if not row: return None
    c=get_connection(); rows=c.execute("SELECT ps.collected_at,ps.price,ps.original_price,ps.shipping,ps.total_price,ps.currency,ps.available,ps.source,o.id AS offer_id,o.filament_key,o.variant_id,o.title,o.url,o.seller,s.name AS store FROM price_snapshots ps JOIN offers o ON o.id=ps.offer_id JOIN stores s ON s.id=o.store_id WHERE o.filament_key=? ORDER BY ps.collected_at,ps.id",(row["filament_key"],)).fetchall(); c.close(); return [dict(r) for r in rows]
