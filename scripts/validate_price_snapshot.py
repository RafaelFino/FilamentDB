#!/usr/bin/env python3
"""Validate a FilamentDB daily price snapshot before it can be committed."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "filament.db"
DATA = ROOT / "data" / "price-data"


def main(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("schema_version", "snapshot_date", "collected_at", "collector", "offers", "collection"):
        if key not in payload:
            raise ValueError(f"Campo obrigatório ausente: {key}")
    conn = sqlite3.connect(DB)
    valid = {r[0]: r[1:] for r in conn.execute("""
        SELECT LOWER(TRIM(m.name)) || '|' || LOWER(TRIM(mf.name)) || '|' || LOWER(TRIM(fp.line)), m.name, mf.name
        FROM filament_profiles fp
        JOIN materials m ON m.id=fp.material_id
        JOIN manufacturers mf ON mf.id=fp.manufacturer_id
        WHERE fp.active=1 AND fp.tracking=1
    """)}
    conn.close()
    seen = set()
    for i, x in enumerate(payload["offers"]):
        key = x.get("filament_key")
        if key not in valid:
            raise ValueError(f"Oferta {i}: filament_key não monitorado: {key}")
        if not x.get("url", "").startswith(("http://", "https://")):
            raise ValueError(f"Oferta {i}: URL inválida")
        if float(x.get("price", 0)) <= 0 or float(x.get("unit_weight_g", 0)) <= 0 or int(x.get("quantity", 0)) <= 0:
            raise ValueError(f"Oferta {i}: preço/peso/quantidade inválidos")
        basis = x.get("price_basis")
        expected = float(x["price"]) * int(x["quantity"]) if basis == "unit" else float(x["price"])
        if abs(float(x.get("total_price", 0)) - expected) > 0.02:
            raise ValueError(f"Oferta {i}: total_price inconsistente")
        dedupe = (key, x.get("store"), x.get("url"), x.get("quantity"), x.get("unit_weight_g"), basis)
        if dedupe in seen:
            raise ValueError(f"Oferta duplicada: {dedupe}")
        seen.add(dedupe)
    print(f"[OK] Snapshot válido: {path.name} | ofertas={len(payload['offers'])} | resultados={len(payload['collection'])}")


if __name__ == "__main__":
    files = [Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(DATA.glob("*.json"))[-1:]
    if not files:
        raise SystemExit("Nenhum snapshot encontrado")
    for f in files:
        main(f)
