#!/usr/bin/env python3
"""Helper de scripts/migrate_inventory.sh (snapshot / migrate / compare / fingerprint).

Subcomandos (todos recebem --db com o inventory.db alvo):
  snapshot     grava o estado "antes" (schema, linhas) em JSON (--out). Só leitura.
  migrate      roda inventory.init_db(force=True) apontando para --db.
  compare      compara o banco atual com o snapshot (--snapshot), imprime o
               relatório e sai com 1 em QUALQUER divergência.
  fingerprint  imprime um sha256 do conteúdo (linhas + _inv_meta), para provar
               idempotência.

O banco alvo é injetado em inventory.INVENTORY_DB_PATH (o módulo só deriva o
caminho de DB_PATH). O catálogo (usado só para LER no backfill de profile_name)
vem de --catalog; sem ele, mantém o default da config.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TABLE = "inventory_items"


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _read(path):
    conn = _ro(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})")]
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {TABLE} ORDER BY id")]
        meta = {}
        has_meta = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_inv_meta'"
        ).fetchone()
        if has_meta:
            meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM _inv_meta")}
        return cols, rows, meta
    finally:
        conn.close()


def cmd_snapshot(args):
    cols, rows, meta = _read(args.db)
    snap = {
        "columns": cols,
        "rows": rows,
        "split_done": "split_spools_v1" in meta,
    }
    Path(args.out).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    print(f"snapshot: {len(rows)} itens, {len(cols)} colunas")


def cmd_migrate(args):
    from src import database, inventory

    inventory.INVENTORY_DB_PATH = Path(args.db)
    if args.catalog:
        database.DB_PATH = Path(args.catalog)
    inventory.init_db(force=True)
    if os.environ.get("MIGRATE_INVENTORY_FAULT") == "delete_row":
        # Gancho SÓ para testes: simula perda de dado para exercitar o rollback.
        conn = sqlite3.connect(args.db)
        conn.execute(f"DELETE FROM {TABLE} WHERE id = (SELECT MIN(id) FROM {TABLE})")
        conn.commit()
        conn.close()
    print("init_db() concluído")


def cmd_compare(args):
    snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    before_cols = set(snap["columns"])
    before = {r["id"]: r for r in snap["rows"]}
    cols, rows, _ = _read(args.db)
    after = {r["id"]: r for r in rows}
    problems = []

    for needed in ("profile_name", "color_id"):
        if needed not in cols:
            problems.append(f"coluna ausente após migração: {needed}")

    split_pending = not snap["split_done"]
    expected = len(before)
    if split_pending:
        expected += sum(max(int(r.get("spools") or 1) - 1, 0) for r in before.values())
    if len(after) != expected:
        problems.append(f"contagem divergente: esperado {expected}, atual {len(after)}")

    missing = sorted(set(before) - set(after))
    if missing:
        problems.append(f"itens desaparecidos (id): {missing}")
    extra = sorted(set(after) - set(before))
    if extra and not split_pending:
        problems.append(f"itens inesperados (id): {extra}")

    # Campos não derivados que não podem mudar. Exceções legítimas: updated_at
    # (split), spools (split de linhas agregadas), uid (backfill onde era nulo)
    # e profile_name (só pode ir de vazio -> preenchido).
    exempt = {"updated_at"}
    if split_pending:
        exempt.add("spools")
    for iid, b in before.items():
        a = after.get(iid)
        if a is None:
            continue
        for col in before_cols:
            if col in exempt:
                continue
            bv, av = b.get(col), a.get(col)
            if col == "uid" and not bv:
                continue
            if col == "profile_name" and not bv:
                continue
            if bv != av:
                problems.append(f"item {iid}: campo '{col}' mudou ({bv!r} -> {av!r})")
        if split_pending and int(b.get("spools") or 1) > 1 and a.get("spools") != 1:
            problems.append(f"item {iid}: spools deveria ser 1 após split")

    uids = [r.get("uid") for r in rows]
    if any(not u for u in uids):
        problems.append("há itens sem uid após migração")
    if len(set(uids)) != len(uids):
        problems.append("uid duplicado após migração")

    total = len(rows)
    with_profile = sum(1 for r in rows if r.get("profile_name"))
    had_profile = sum(1 for r in before.values() if r.get("profile_name"))
    inferred = sum(
        1 for iid, r in after.items()
        if iid in before and r.get("profile_name") and not before[iid].get("profile_name")
    )
    missing_type = total - with_profile
    with_color = sum(1 for r in rows if r.get("color_id"))

    print("── Relatório da migração do estoque ──")
    print(f"  Total de itens (antes → depois):     {len(before)} → {total}")
    print(f"  Já tinham profile_name:              {had_profile}")
    print(f"  profile_name inferido agora:         {inferred}")
    print(f"  Com profile_name (total):            {with_profile}")
    print(f"  type_missing (reclassificar na UI):  {missing_type}"
          "  (filtro 'Tipo não definido')")
    print(f"  Com color_id:                        {with_color}")

    if problems:
        print("DIVERGÊNCIAS:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("  Integridade: OK")


def cmd_fingerprint(args):
    cols, rows, meta = _read(args.db)
    payload = json.dumps(
        {"cols": cols, "rows": rows, "meta": meta},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    print(hashlib.sha256(payload.encode("utf-8")).hexdigest())


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("snapshot", cmd_snapshot), ("migrate", cmd_migrate),
                     ("compare", cmd_compare), ("fingerprint", cmd_fingerprint)):
        sp = sub.add_parser(name)
        sp.add_argument("--db", required=True)
        sp.set_defaults(fn=fn)
        if name == "snapshot":
            sp.add_argument("--out", required=True)
        if name == "migrate":
            sp.add_argument("--catalog", default="")
        if name == "compare":
            sp.add_argument("--snapshot", required=True)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
