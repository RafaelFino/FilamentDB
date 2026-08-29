"""Read-only price intelligence service for the web UI."""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
from statistics import median
from src import database, config
ROOT=Path(__file__).resolve().parent.parent
PRICE_DB_PATH=config.database_path("price-history.db")
SCHEMA_PATH=ROOT/"data"/"price-history.schema.sql"
SEED_PATH=ROOT/"data"/"price-history.seed.json"

def _catalog_rows():
 c=database.get_db_connection(); rows=c.execute("SELECT fp.id,fp.commercial_name,fp.profile_name,fp.line,fp.line_positioning,fp.line_finish,fp.tracking,m.name AS material_name,mf.name AS manufacturer_name FROM filament_profiles fp JOIN materials m ON m.id=fp.material_id JOIN manufacturers mf ON mf.id=fp.manufacturer_id WHERE fp.active=1 AND fp.tracking=1 ORDER BY mf.name,m.name,fp.commercial_name").fetchall(); c.close(); return [dict(r) for r in rows]
def _seed_if_empty(conn):
 conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
 if conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] or not SEED_PATH.exists(): return
 seed=json.loads(SEED_PATH.read_text(encoding="utf-8")); cat=database.get_db_connection(); collected="2026-08-29T00:00:00-03:00"
 try:
  run=conn.execute("INSERT INTO collection_runs(started_at,finished_at,source,status) VALUES(?,?,?,?)",(collected,collected,"verified-baseline-2026-08-29","completed")).lastrowid; n=0
  for x in seed:
   row=cat.execute("SELECT fp.id FROM filament_profiles fp JOIN manufacturers mf ON mf.id=fp.manufacturer_id WHERE mf.name=? AND fp.profile_name=? AND fp.tracking=1 AND fp.active=1",(x["manufacturer"],x["profile_name"])).fetchone()
   if not row: continue
   fid=row[0]; sid=conn.execute("INSERT INTO stores(name,domain,marketplace) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain RETURNING id",(x["store"],x["domain"],x["marketplace"])).fetchone()[0]
   oid=conn.execute("INSERT INTO offers(filament_id,store_id,url,external_id,seller,title,last_seen_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(store_id,url) DO UPDATE SET filament_id=excluded.filament_id,title=excluded.title,last_seen_at=excluded.last_seen_at RETURNING id",(fid,sid,x["url"],x.get("external_id"),x.get("seller"),x["title"],collected)).fetchone()[0]
   conn.execute("INSERT INTO price_snapshots(offer_id,collected_at,price,original_price,shipping,total_price,currency,available,source,notes) VALUES(?,?,?,?,?,?,?,?,?,?)",(oid,collected,x["price"],x.get("original_price"),x.get("shipping"),(x["price"]+(x.get("shipping") or 0)) if x.get("shipping") is not None else None,"BRL",x.get("available"),x.get("source"),x.get("notes"))); n+=1
  conn.execute("UPDATE collection_runs SET items_found=? WHERE id=?",(n,run)); conn.commit()
 finally: cat.close()
def get_connection():
 PRICE_DB_PATH.parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(PRICE_DB_PATH); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); _seed_if_empty(c); return c
def dashboard():
 catalog=_catalog_rows(); byid={x["id"]:x for x in catalog}; c=get_connection(); offers=[dict(x) for x in c.execute("SELECT * FROM current_offers").fetchall()]; hist=c.execute("SELECT offer_id,price FROM price_snapshots").fetchall(); c.close(); hp={}
 for x in hist: hp.setdefault(x[0],[]).append(x[1])
 cur={}
 for o in offers: cur.setdefault(o["filament_id"],[]).append(o)
 items=[]
 for fid,fil in byid.items():
  osx=cur.get(fid,[]); allp=[p for o in osx for p in hp.get(o["offer_id"],[])]
  if not osx: continue
  best=min(osx,key=lambda o:o["total_price"] if o["total_price"] is not None else o["price"]); med=median(allp) if allp else best["price"]; disc=((med-best["price"])/med*100) if med else 0
  items.append({**fil,"best_price":best["price"],"best_store":best["store"],"best_url":best["url"],"median_price":med,"min_price":min(allp) if allp else best["price"],"discount_pct":disc,"offer_count":len(osx)})
 items.sort(key=lambda x:(-x["discount_pct"],x["best_price"])); return {"summary":{"tracked_count":len(catalog),"priced_count":len(items),"offer_count":len(offers)},"items":items}
def history(filament_id):
 if not any(x["id"]==filament_id for x in _catalog_rows()): return None
 c=get_connection(); rows=c.execute("SELECT ps.collected_at,ps.price,ps.original_price,ps.shipping,ps.total_price,ps.currency,ps.available,ps.source,o.id AS offer_id,o.title,o.url,o.seller,s.name AS store FROM price_snapshots ps JOIN offers o ON o.id=ps.offer_id JOIN stores s ON s.id=o.store_id WHERE o.filament_id=? ORDER BY ps.collected_at,ps.id",(filament_id,)).fetchall(); c.close(); return [dict(r) for r in rows]
