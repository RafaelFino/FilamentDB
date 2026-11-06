#!/usr/bin/env python3
"""
reclassify_inventory.py — Preenche o TIPO (profile_name) dos itens legados do
estoque (type_missing), inferindo por (fabricante, material, linha/finish)
contra o catálogo, com segurança máxima: na dúvida, NÃO aplica.

Contexto: o estoque foi migrado para o modelo Tipo × Cor. O backfill automático
do init_db() usa variant_id/sku e não funciona em produção (os variant_id
derivam entre builds do catálogo). Este script cobre o legado com uma TABELA
EXPLÍCITA de regras (RULES abaixo), auditável, em vez de fuzzy matching.

Regras de decisão (nesta ordem, por item sem profile_name):
  1. profile_name já preenchido  -> intocado ("já classificado").
  2. Override por uid (--overrides FILE, {uid: profile_name}) tem precedência.
  3. Senão, regras (fabricante, material, finish) -> profile_name. Nenhuma regra
     casa => "sem match"; regras casando produtos distintos => "ambíguo".
  4. Nota "Troca de Cor" + produto resolvido que NÃO é Outlet => "precisa de
     decisão" (não decide sozinho). Para os PETG Voolt3D HF com essa nota, a
     decisão explícita é --troca-de-cor-petg=outlet|hf.
  5. O profile_name precisa existir no catálogo e o fabricante/material do
     perfil precisam bater com os do item; senão não aplica.
  6. A camada de domínio (inventory.validate_type_color) valida tipo+cor
     EXISTENTE do item; se rejeitar (ex.: cor de variante incompatível com o
     tipo) => "conflito", não aplica e não força.

O que é gravado: SOMENTE a coluna profile_name (de vazio para preenchido).
Cor (color_id/color_name/hex_color), variant_id, peso, status, spools, notes,
uid e timestamps NÃO são tocados — updated_at inclusive (mesma política do
backfill_profiles() do inventory.py). Verificado antes do commit.

Uso:
    python scripts/reclassify_inventory.py                      # DRY-RUN (padrão)
    python scripts/reclassify_inventory.py --json               # relatório JSON
    python scripts/reclassify_inventory.py --overrides o.json   # {uid: profile_name}
    python scripts/reclassify_inventory.py --troca-de-cor-petg=outlet
    python scripts/reclassify_inventory.py --apply              # grava (com backup)

Resolução do banco alvo:
    --db PATH > FILAMENT_INVENTORY_DB_PATH > <dir de DB_PATH>/inventory.db
    (default: <repo>/data/inventory.db)
Catálogo (só leitura): --catalog PATH > DB_PATH (default: <repo>/data/filament.db)
Backup (--apply): ${BACKUP_DIR:-<FILAMENTDB_BACKUP_DIR ou repo>/backups}/
    inventory_prereclassify_<ts>.db via sqlite3 Connection.backup; se falhar, aborta.

Pré-requisito de schema: o banco alvo já precisa ter as colunas profile_name e
color_id. Este script NÃO chama init_db() (ele também faz split de spools, backfill
de uid etc., o que não é "seguro" para um script de reclassificação): se faltarem,
aborta pedindo para rodar antes ./scripts/migrate_inventory.sh.

Garantias do --apply: backup → transação única (tudo ou nada) → verificação
(mesma contagem e uids, demais campos idênticos, idempotência) ANTES do commit;
qualquer divergência faz rollback.

Códigos de saída: 0 ok; 1 falha de execução/verificação; 2 uso/ambiente inválido.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TABLE = "inventory_items"

# ─── Tabela de regras (auditável) ──────────────────────────────────────────────
# (fabricante, material, finish) -> profile_name do catálogo.
# Comparação case-insensitive; finish "" casa finish NULL/vazio.
# Os profile_name foram lidos de data/filament.db (não inventados); a validação
# em runtime recusa qualquer um que não exista no catálogo alvo.
RULES = [
    ("Voolt3D", "ABS",    "Fosco",            "ABS - Voolt3D - Standard"),
    ("Creality", "PETG",  "CR",               "PETG - Creality - CR PETG"),
    ("Creality", "PETG",  "Hyper",            "PETG - Creality - Hyper PETG"),
    ("Futer3D", "PETG",   "",                 "PETG - Futer3D - Basic"),
    ("Sunlu", "PETG",     "HS",               "PETG - Sunlu - High Speed Matte"),
    ("Voolt3D", "PETG",   "HF",               "PETG - Voolt3D - HF"),
    ("Elegoo", "PLA",     "PRO",              "PLA - Elegoo - Pro"),
    ("Elegoo", "TPU",     "T95A",             "TPU - Elegoo - 95A"),
    ("Soleyin", "PLA",    "Standard",         "PLA - Soleyin - Ultra PLA"),
    ("Sunlu", "PLA",      "Matte",            "PLA - Sunlu - Matte"),
    ("Sunlu", "PLA",      "High Speed Matte", "PLA - Sunlu - High Speed Matte"),
    ("Voolt3D", "PLA",    "Velvet",           "PLA - Voolt3D - Velvet"),
    ("Voolt3D", "PLA",    "Outlet",           "PLA - Voolt3D - Premium Outlet"),
    ("Voolt3D", "PLA",    "Silk",             "PLA - Voolt3D - V-Silk"),
    ("Voolt3D", "PLA",    "Macaron",          "PLA - Voolt3D - Macaron"),
    ("Voolt3D", "PLA-CF", "CF",               "PLA-CF - Voolt3D - Standard"),
]

PETG_HF = "PETG - Voolt3D - HF"
PETG_OUTLET = "PETG - Voolt3D - Outlet"
TROCA_COR_MARK = "troca de cor"

# Motivos (códigos estáveis para --json)
R_SEM_MATCH = "sem_match"
R_AMBIGUO = "ambiguo"
R_DECISAO = "precisa_decisao"
R_PERFIL_INEXISTENTE = "perfil_inexistente"
R_TYPE_MISMATCH = "fabricante_material_divergem"
R_SEM_UID = "sem_uid"

REASON_TEXT = {
    R_SEM_MATCH: "sem match (nenhuma regra para fabricante/material/finish)",
    R_AMBIGUO: "ambíguo (mais de um produto casa)",
    R_DECISAO: "precisa de decisão (nota 'Troca de Cor' e produto não-Outlet)",
    R_PERFIL_INEXISTENTE: "profile_name inexistente no catálogo",
    R_TYPE_MISMATCH: "fabricante/material do item divergem do perfil do catálogo",
    R_SEM_UID: "item sem uid",
}


class ReclassifyError(Exception):
    """Falha de execução/verificação (exit 1)."""


class UsageError(Exception):
    """Uso/ambiente inválido (exit 2)."""


def _norm(text):
    return (text or "").strip().casefold()


# ─── Resolução de paths ────────────────────────────────────────────────────────

def resolve_db(db_arg=None):
    if db_arg:
        return Path(db_arg)
    from src import config
    env = config.get("FILAMENT_INVENTORY_DB_PATH")
    if env:
        return Path(env)
    return Path(config.get("DB_PATH")).parent / "inventory.db"


def resolve_catalog(catalog_arg=None):
    if catalog_arg:
        return Path(catalog_arg)
    from src import config
    return Path(config.get("DB_PATH"))


def resolve_backup_dir():
    env = os.environ.get("BACKUP_DIR")
    if env:
        return Path(env)
    from src import config
    return Path(config.get("FILAMENTDB_BACKUP_DIR") or ROOT / "backups")


# ─── Leitura ───────────────────────────────────────────────────────────────────

def _ro(path):
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def check_schema(conn):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})").fetchall()}
    if not cols:
        raise UsageError(f"tabela {TABLE} não existe no banco alvo")
    missing = [c for c in ("profile_name", "color_id", "uid") if c not in cols]
    if missing:
        raise UsageError(
            f"schema antigo (faltam colunas: {', '.join(missing)}). "
            "Rode antes ./scripts/migrate_inventory.sh (init_db) e repita."
        )


def fetch_rows(conn):
    cur = conn.execute(f"SELECT * FROM {TABLE} ORDER BY id")
    return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]


def load_catalog(path):
    """profile_name -> {manufacturer, material}. Aborta se ilegível."""
    if not Path(path).exists():
        raise UsageError(f"catálogo não encontrado: {path} (use --catalog PATH)")
    try:
        conn = _ro(path)
        try:
            rows = conn.execute(
                "SELECT p.profile_name, mf.name AS manufacturer, mt.name AS material "
                "FROM filament_profiles p "
                "JOIN manufacturers mf ON mf.id = p.manufacturer_id "
                "JOIN materials mt ON mt.id = p.material_id"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise UsageError(f"catálogo ilegível ({path}): {exc}")
    return {r["profile_name"]: {"manufacturer": r["manufacturer"], "material": r["material"]}
            for r in rows}


def load_overrides(path):
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"overrides ilegível ({path}): {exc}")
    if not isinstance(data, dict):
        raise UsageError("overrides deve ser um objeto JSON {uid: profile_name}")
    out = {}
    for uid, pn in data.items():
        if uid.startswith("_"):
            continue  # chaves de comentário (ex.: "_comment")
        if not isinstance(pn, str) or not pn.strip():
            raise UsageError(f"override inválido para {uid}: profile_name deve ser texto")
        out[uid] = pn.strip()
    return out


# ─── Domínio ───────────────────────────────────────────────────────────────────

def domain_check(item, profile_name, catalog_path):
    """Roda inventory.validate_type_color só como VALIDAÇÃO (nada é gravado a
    partir dos campos derivados). Retorna (ok, code, mensagem)."""
    from src import database, inventory
    prev = database.DB_PATH
    database.DB_PATH = Path(catalog_path)
    try:
        inventory.validate_type_color({"profile_name": profile_name}, existing=dict(item))
        return True, None, None
    except inventory.TypeColorError as exc:
        return False, exc.code, str(exc)
    finally:
        database.DB_PATH = prev


# ─── Planejamento ──────────────────────────────────────────────────────────────

def _label(item):
    return (f"{item.get('manufacturer')} | {item.get('material')} | "
            f"{item.get('finish') or '(sem finish)'}")


def match_rules(item):
    """Perfis candidatos pelas regras (lista de profile_name distintos)."""
    key = (_norm(item.get("manufacturer")), _norm(item.get("material")),
           _norm(item.get("finish")))
    found = []
    for m, mat, fin, pn in RULES:
        if (_norm(m), _norm(mat), _norm(fin)) == key and pn not in found:
            found.append(pn)
    return found


def build_plan(rows, catalog, catalog_path, overrides=None, troca_petg=None):
    """Decide cada item. Retorna dict com apply/pending/conflicts/filled/warnings.

    `catalog`: dict profile_name -> {manufacturer, material}.
    """
    overrides = overrides or {}
    plan = {"apply": [], "pending": [], "conflicts": [], "filled": [], "warnings": []}
    uids = {r.get("uid") for r in rows}
    for uid in sorted(set(overrides) - uids):
        plan["warnings"].append(f"override para uid inexistente no banco: {uid}")

    for item in rows:
        uid = item.get("uid")
        base = {"id": item["id"], "uid": uid, "group": _label(item),
                "color": item.get("color_name"), "notes": item.get("notes")}
        if (item.get("profile_name") or "").strip():
            plan["filled"].append({**base, "profile_name": item["profile_name"]})
            continue
        if not uid:
            plan["pending"].append({**base, "reason": R_SEM_UID})
            continue

        troca = TROCA_COR_MARK in _norm(item.get("notes"))
        if uid in overrides:
            candidate, rule = overrides[uid], "override por uid"
        else:
            cands = match_rules(item)
            if not cands:
                plan["pending"].append({**base, "reason": R_SEM_MATCH})
                continue
            if len(cands) > 1:
                plan["pending"].append({**base, "reason": R_AMBIGUO,
                                        "candidates": cands})
                continue
            candidate = cands[0]
            rule = f"regra {_label(item)}"
            if troca:
                if candidate == PETG_HF and troca_petg == "outlet":
                    candidate = PETG_OUTLET
                    rule = f"regra {_label(item)} + --troca-de-cor-petg=outlet"
                elif candidate == PETG_HF and troca_petg == "hf":
                    rule = f"regra {_label(item)} + --troca-de-cor-petg=hf"
                elif not candidate.casefold().endswith("outlet"):
                    plan["pending"].append({**base, "reason": R_DECISAO,
                                            "candidates": [candidate]})
                    continue

        info = catalog.get(candidate)
        if info is None:
            plan["pending"].append({**base, "reason": R_PERFIL_INEXISTENTE,
                                    "candidates": [candidate]})
            continue
        if (_norm(info["manufacturer"]) != _norm(item.get("manufacturer"))
                or _norm(info["material"]) != _norm(item.get("material"))):
            plan["conflicts"].append({**base, "profile_name": candidate,
                                      "code": "type_mismatch",
                                      "message": f"{R_TYPE_MISMATCH}: item "
                                      f"{item.get('manufacturer')}/{item.get('material')} × "
                                      f"perfil {info['manufacturer']}/{info['material']}"})
            continue
        ok, code, msg = domain_check(item, candidate, catalog_path)
        if not ok:
            plan["conflicts"].append({**base, "profile_name": candidate,
                                      "code": code, "message": msg})
            continue
        plan["apply"].append({**base, "profile_name": candidate, "rule": rule})
    return plan


# ─── Relatório ─────────────────────────────────────────────────────────────────

def plan_to_json(plan, db, catalog, mode):
    return {
        "mode": mode, "db": str(db), "catalog": str(catalog),
        "summary": {k: len(plan[k]) for k in ("apply", "pending", "conflicts", "filled")},
        "apply": plan["apply"], "pending": plan["pending"],
        "conflicts": plan["conflicts"], "filled": len(plan["filled"]),
        "warnings": plan["warnings"],
    }


def render_report(plan, db, catalog, mode):
    out = []
    out.append(f"Reclassificação de estoque — modo {mode}")
    out.append(f"  banco:    {db}")
    out.append(f"  catálogo: {catalog}")
    total = sum(len(plan[k]) for k in ("apply", "pending", "conflicts", "filled"))
    out.append(f"  itens: {total} | a classificar: {len(plan['apply'])} | "
               f"pendentes: {len(plan['pending'])} | conflitos: {len(plan['conflicts'])} | "
               f"já classificados: {len(plan['filled'])}")
    out.append("")

    groups = {}
    for it in plan["apply"]:
        groups.setdefault((it["rule"], it["profile_name"]), []).append(it)
    out.append("== A classificar (por regra) ==")
    if not groups:
        out.append("  (nada)")
    for (rule, pn), items in sorted(groups.items()):
        out.append(f"  [{len(items)}] {rule}")
        out.append(f"       -> {pn}")
        for it in items:
            out.append(f"       - {it['uid']}  ({it['color']})")
    out.append("")

    out.append("== Pendentes (NÃO classificados) ==")
    if not plan["pending"]:
        out.append("  (nada)")
    pend = {}
    for it in plan["pending"]:
        pend.setdefault((it["reason"], it["group"]), []).append(it)
    for (reason, grp), items in sorted(pend.items()):
        out.append(f"  [{len(items)}] {grp} — {REASON_TEXT[reason]}")
        cands = items[0].get("candidates")
        if cands:
            out.append(f"       candidato(s): {', '.join(cands)}")
        for it in items:
            out.append(f"       - {it['uid']}  ({it['color']})")
    out.append("")

    out.append("== Conflitos (tipo × cor rejeitado pelo domínio; não aplicado) ==")
    if not plan["conflicts"]:
        out.append("  (nada)")
    for it in plan["conflicts"]:
        out.append(f"  - {it['uid']}  {it['group']} ({it['color']}) -> {it['profile_name']}")
        out.append(f"      {it['code']}: {it['message']}")
    if plan["warnings"]:
        out.append("")
        out.append("== Avisos ==")
        out.extend(f"  - {w}" for w in plan["warnings"])
    return "\n".join(out)


# ─── Apply ─────────────────────────────────────────────────────────────────────

def make_backup(db, backup_dir):
    """Backup consistente via sqlite3 Connection.backup. Aborta se falhar."""
    backup_dir = Path(backup_dir)
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = backup_dir / f"inventory_prereclassify_{datetime.now():%Y%m%d_%H%M%S}.db"
        n = 1
        while dest.exists():
            dest = backup_dir / f"inventory_prereclassify_{datetime.now():%Y%m%d_%H%M%S}_{n}.db"
            n += 1
        src = _ro(db)
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        chk, ref = sqlite3.connect(str(dest)), _ro(db)
        try:
            n_src = ref.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
            n_dst = chk.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        finally:
            chk.close()
            ref.close()
        if dest.stat().st_size == 0 or n_src != n_dst:
            raise ReclassifyError("backup inconsistente (vazio ou contagem diferente)")
    except (OSError, sqlite3.Error) as exc:
        raise ReclassifyError(f"backup FALHOU, nada foi alterado: {exc}")
    return dest


def verify_state(before, after, expected):
    """before/after: listas de dicts; expected: {id: profile_name}.

    Levanta ReclassifyError em qualquer divergência: contagem/ids/uids, campos
    que não são profile_name, e profile_name só mudando nos itens planejados.
    """
    b = {r["id"]: r for r in before}
    a = {r["id"]: r for r in after}
    if len(before) != len(after) or set(b) != set(a):
        raise ReclassifyError(f"contagem/ids divergem: {len(before)} -> {len(after)}")
    if {r["uid"] for r in before} != {r["uid"] for r in after}:
        raise ReclassifyError("conjunto de uids divergiu")
    for iid, rb in b.items():
        ra = a[iid]
        for col, bv in rb.items():
            if col == "profile_name":
                continue
            if ra.get(col) != bv:
                raise ReclassifyError(f"item {iid}: campo '{col}' mudou ({bv!r} -> {ra.get(col)!r})")
        want = expected.get(iid, rb.get("profile_name"))
        if ra.get("profile_name") != want:
            raise ReclassifyError(
                f"item {iid}: profile_name {ra.get('profile_name')!r}, esperado {want!r}")


def apply_plan(db, catalog, catalog_path, overrides, troca_petg, backup_dir):
    """Backup + transação única + verificação pré-commit. Retorna (plan, backup)."""
    conn = _ro(db)
    try:
        check_schema(conn)
        rows = fetch_rows(conn)
    finally:
        conn.close()
    plan = build_plan(rows, catalog, catalog_path, overrides, troca_petg)
    if not plan["apply"]:
        return plan, None  # nada a gravar: sem backup inútil

    backup = make_backup(db, backup_dir)

    conn = sqlite3.connect(str(db), isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            before = fetch_rows(conn)
            if before != rows:
                raise ReclassifyError("o banco mudou entre o planejamento e a gravação; repita")
            expected = {}
            for it in plan["apply"]:
                cur = conn.execute(
                    f"UPDATE {TABLE} SET profile_name = ? "
                    "WHERE id = ? AND uid = ? AND (profile_name IS NULL OR TRIM(profile_name) = '')",
                    (it["profile_name"], it["id"], it["uid"]),
                )
                if cur.rowcount != 1:
                    raise ReclassifyError(f"UPDATE não afetou 1 linha (id {it['id']})")
                expected[it["id"]] = it["profile_name"]
            after = fetch_rows(conn)
            verify_state(before, after, expected)
            # Idempotência: replanejar sobre o estado novo não pode ter nada a aplicar.
            again = build_plan(after, catalog, catalog_path, overrides, troca_petg)
            if again["apply"]:
                raise ReclassifyError("não idempotente: 2ª passada ainda classificaria itens")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return plan, backup


# ─── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Preenche profile_name de itens legados do estoque (DRY-RUN por padrão).")
    p.add_argument("--db", help="inventory.db alvo (default: ver ajuda do módulo)")
    p.add_argument("--catalog", help="filament.db (catálogo, só leitura)")
    p.add_argument("--overrides", help="JSON {uid: profile_name} com precedência sobre as regras")
    p.add_argument("--troca-de-cor-petg", choices=("outlet", "hf"), default=None,
                   help="decisão para Voolt3D PETG HF com nota 'Troca de Cor' "
                        "(sem a flag ficam pendentes)")
    p.add_argument("--apply", action="store_true", help="grava (com backup); sem isso, só relatório")
    p.add_argument("--json", action="store_true", help="relatório em JSON")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        db = resolve_db(args.db)
        catalog_path = resolve_catalog(args.catalog)
        if not db.exists():
            raise UsageError(f"banco de estoque não encontrado: {db} (use --db PATH)")
        catalog = load_catalog(catalog_path)
        overrides = load_overrides(args.overrides)
        mode = "APPLY" if args.apply else "DRY-RUN"

        backup = None
        if args.apply:
            plan, backup = apply_plan(db, catalog, catalog_path, overrides,
                                      args.troca_de_cor_petg, resolve_backup_dir())
        else:
            conn = _ro(db)
            try:
                check_schema(conn)
                rows = fetch_rows(conn)
            finally:
                conn.close()
            plan = build_plan(rows, catalog, catalog_path, overrides, args.troca_de_cor_petg)

        if args.json:
            data = plan_to_json(plan, db, catalog_path, mode)
            data["backup"] = str(backup) if backup else None
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(render_report(plan, db, catalog_path, mode))
            if args.apply:
                print()
                if backup:
                    print(f"Backup: {backup}")
                    print(f"Gravados: {len(plan['apply'])} (verificação pré-commit OK)")
                else:
                    print("Nada a gravar (já idempotente); nenhum backup criado.")
            else:
                print("\nDRY-RUN: nada foi gravado. Use --apply para gravar (faz backup antes).")
        return 0
    except UsageError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    except ReclassifyError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"ERRO sqlite: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
