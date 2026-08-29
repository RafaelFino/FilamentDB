#!/usr/bin/env python3
"""Initialize and seed the isolated FilamentDB price-history database.

The catalog remains the source of truth. Offers are persisted only with the
filament_id resolved from filament.db and tracking=1. Product names are used
only to resolve the current catalog ID during seeding; the price-history
relationship itself is stored as filament_id.
"""
from __future__ import annotations
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_FILAMENT_DB=ROOT/'filament.db'
DEFAULT_PRICE_DB=ROOT/'price-history.db'
SCHEMA=ROOT/'price-history'/'schema.sql'
INITIAL_OBSERVATIONS=[
 {"manufacturer":"3DLab","profile_name":"3DLab PLA Premium","store":"3D Lab","domain":"3dlab.com.br","marketplace":0,"title":"Filamento PLA Premium Preto Eclipse","url":"https://3dlab.com.br/produto/filamento-pla-preto/","external_id":None,"seller":"3D Lab","price":89.90,"original_price":99.89,"shipping":None,"available":1,"source":"web-search-2026-08-29","notes":"Preço Pix; produto premium, 1 kg. Oferta direta do fabricante."},
 {"manufacturer":"Elegoo","profile_name":"Elegoo PLA Matte","store":"Mercado Livre","domain":"mercadolivre.com.br","marketplace":1,"title":"Filamento Elegoo PLA Matte 1.75mm 1kg - Matte Black","url":"https://produto.mercadolivre.com.br/MLB-5768091224-filamento-elegoo-pla-matte-175mm-1kg-_JM","external_id":"MLB-5768091224","seller":"Translaser","price":139.90,"original_price":None,"shipping":0.0,"available":1,"source":"web-search-2026-08-29","notes":"Frete grátis; anúncio ativo; variante Matte Black observada."},
 {"manufacturer":"Creality","profile_name":"Creality Hyper PETG","store":"Mercado Livre","domain":"mercadolivre.com.br","marketplace":1,"title":"Filamento Petg 3D 1kg/rolo 1.75mm Creality Hyper PETG","url":"https://produto.mercadolivre.com.br/MLB-6097600700-filamento-petg-3d-1kgrolo-175mm-creality-hyper-petg-_JM","external_id":"MLB-6097600700","seller":"Mundo Tech 3D","price":123.18,"original_price":176.00,"shipping":0.0,"available":1,"source":"web-search-2026-08-29","notes":"Preço observado; frete grátis; variante amarela; anúncio ativo."},
 {"manufacturer":"Voolt3D","profile_name":"Voolt3D PLA Velvet","store":"Voolt3D","domain":"voolt3d.com.br","marketplace":0,"title":"Filamento PLA Preto Velvet High Speed Premium - 1Kg","url":"https://voolt3d.com.br/produtos/filamento-pla-preto-velvet-premium/","external_id":"PL-PR-VE-1","seller":"Voolt3D","price":84.90,"original_price":129.99,"shipping":None,"available":1,"source":"web-search-2026-08-29","notes":"Preço Pix; página direta; SKU PL-PR-VE-1."},
 {"manufacturer":"Voolt3D","profile_name":"Voolt3D PETG HF","store":"Voolt3D","domain":"voolt3d.com.br","marketplace":0,"title":"Filamento PETG HF Preto High Fluidity Premium - 1Kg","url":"https://voolt3d.com.br/filamentos/petg/filamento-petg-preto-premium-loja-voolt3d","external_id":"PG-HF-PR-1","seller":"Voolt3D","price":99.90,"original_price":139.99,"shipping":None,"available":1,"source":"web-search-2026-08-29","notes":"Preço Pix; linha PETG High Fluidity Premium; SKU PG-HF-PR-1."},
]
def initialize_price_db(price_db:Path)->sqlite3.Connection:
 price_db.parent.mkdir(parents=True,exist_ok=True)
 conn=sqlite3.connect(price_db)
 conn.execute('PRAGMA foreign_keys=ON')
 conn.executescript(SCHEMA.read_text(encoding='utf-8'))
 return conn
def resolve_filament_id(conn, item):
 row=conn.execute("""SELECT fp.id FROM filament_profiles fp JOIN manufacturers m ON m.id=fp.manufacturer_id WHERE m.name=? AND fp.profile_name=? AND fp.tracking=1""", (item['manufacturer'],item['profile_name'])).fetchone()
 if not row: raise RuntimeError(f"Tracked filament not found: {item['manufacturer']} / {item['profile_name']}")
 return int(row[0])
def seed_initial_observations(filament_db:Path, price_db:Path)->int:
 filament=sqlite3.connect(filament_db)
 price=initialize_price_db(price_db)
 collected_at='2026-08-29T00:00:00-03:00'
 run_id=price.execute('INSERT INTO collection_runs(started_at,finished_at,source,status) VALUES(?,?,?,?)',(collected_at,collected_at,'web-search-2026-08-29','completed')).lastrowid
 inserted=0
 try:
  for item in INITIAL_OBSERVATIONS:
   filament_id=resolve_filament_id(filament,item)
   store_id=price.execute('INSERT INTO stores(name,domain,marketplace) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET domain=excluded.domain,marketplace=excluded.marketplace RETURNING id',(item['store'],item['domain'],item['marketplace'])).fetchone()[0]
   offer_id=price.execute("""INSERT INTO offers(filament_id,store_id,url,external_id,seller,title,last_seen_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(store_id,url) DO UPDATE SET filament_id=excluded.filament_id,external_id=excluded.external_id,seller=excluded.seller,title=excluded.title,last_seen_at=excluded.last_seen_at RETURNING id""", (filament_id,store_id,item['url'],item.get('external_id'),item.get('seller'),item['title'],collected_at)).fetchone()[0]
   price.execute("""INSERT INTO price_snapshots(offer_id,collected_at,price,original_price,shipping,total_price,currency,available,source,notes) VALUES(?,?,?,?,?,?,"BRL",?,?,?)""", (offer_id,collected_at,item['price'],item.get('original_price'),item.get('shipping'),(item['price']+(item['shipping'] or 0)) if item.get('shipping') is not None else None,item.get('available'),item['source'],item.get('notes')))
   inserted+=1
  price.execute('UPDATE collection_runs SET items_found=? WHERE id=?',(inserted,run_id))
  price.commit()
 except Exception:
  price.rollback(); raise
 finally:
  filament.close(); price.close()
 return inserted
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--filament-db',type=Path,default=DEFAULT_FILAMENT_DB)
 parser.add_argument('--price-db',type=Path,default=DEFAULT_PRICE_DB)
 parser.add_argument('--init-only',action='store_true')
 args=parser.parse_args()
 if not args.filament_db.exists(): raise SystemExit(f'filament.db not found: {args.filament_db}. Run build.py first.')
 if args.init_only:
  conn=initialize_price_db(args.price_db); conn.close(); print(f'Initialized {args.price_db}'); return
 print(f'Seeded {seed_initial_observations(args.filament_db,args.price_db)} initial price observations into {args.price_db}')
if __name__=='__main__': main()
