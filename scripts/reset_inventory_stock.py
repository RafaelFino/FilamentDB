#!/usr/bin/env python3
"""
reset_inventory_stock.py — Reset total do estoque de filamentos.

Grande atualização de estoque: a LISTA abaixo é a fonte de verdade. O script
apaga TODO o estoque atual e insere exatamente estes rolos, todos como
`in_stock`. Qualquer estado de carregamento anterior (cfs/spool/drybox/open) é
descartado — a contagem física mudou e o que vale é esta lista.

Modelo do banco (ver src/inventory.py): 1 linha = 1 rolo (spools=1), com `uid`
estável por rolo. Uma linha da lista com Quantidade=N vira N linhas físicas.

O reset é feito via `inventory.import_data(payload, replace=True)`, que espelha
o payload: insere os itens da lista e remove todo o resto. Reusa a validação e
a geração de uid do próprio módulo, sem depender do servidor HTTP no ar.

Antes de escrever, faz um backup do inventory.db atual (dump lógico versionado
via export_data()) em data/backups/.

Uso:
    python scripts/reset_inventory_stock.py            # executa o reset (com backup)
    python scripts/reset_inventory_stock.py --dry-run  # só mostra o que faria
    python scripts/reset_inventory_stock.py --no-backup # pula o backup (não recomendado)
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Permite rodar como `python scripts/reset_inventory_stock.py` a partir da raiz.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import inventory  # noqa: E402


# ─── Fonte de verdade: lista atualizada de estoque ───────────────────────────
# Cada tupla: (material, manufacturer, color_name, finish, quantidade, weight_g, notes)
#   - `finish` recebe o "Tipo" literal da lista (Velvet, Silk, Matte, HF, CR, HS, PRO).
#   - `quantidade` é expandido em N linhas de 1 rolo cada.
#   - `weight_g`: 1000 para rolo de 1 kg, 500 para 0.5 kg.
#   - `notes`: coluna "Obs" (ex.: "Troca de Cor"); vazio vira None.
STOCK = [
    # ─── PLA ───────────────────────────────────────────────────────────────
    ("PLA", "Voolt3D", "Vermelho", "Velvet", 2, 1000, "Troca de Cor"),
    ("PLA", "Voolt3D", "Dourado",  "Velvet", 1, 1000, "Troca de Cor"),
    ("PLA", "Voolt3D", "Amarelo",  "Velvet", 1, 1000, "Troca de Cor"),
    ("PLA", "Voolt3D", "Azul",     "Velvet", 1, 1000, "Troca de Cor"),
    ("PLA", "Voolt3D", "Amarelo",  "Velvet", 1, 1000, "Troca de Cor"),
    ("PLA", "Voolt3D", "Preto",    "Velvet", 1, 1000, None),
    ("PLA", "Voolt3D", "Lilas",    "Velvet", 1, 1000, None),
    ("PLA", "Voolt3D", "Dourado",  "Silk",   1, 1000, None),
    ("PLA", "Voolt3D", "Vermelho", "Velvet", 1, 1000, None),
    ("PLA", "Voolt3D", "Branco",   "Velvet", 1, 1000, None),
    ("PLA", "Elegoo",  "Preto",    "PRO",    1, 1000, None),
    ("PLA", "Sunlu",   "Preto",    "Matte",  3, 1000, None),
    ("PLA", "Sunlu",   "Preto",    "Matte",  1, 500,  None),
    ("PLA", "Sunlu",   "Branco",   "Matte",  1, 500,  None),

    # ─── PETG ──────────────────────────────────────────────────────────────
    ("PETG", "Voolt3D",  "Branco",      "HF", 4, 1000, "Troca de Cor"),
    ("PETG", "Voolt3D",  "Azul",        "HF", 1, 1000, None),
    ("PETG", "Creality", "Azul",        "CR", 2, 1000, None),
    ("PETG", "Creality", "Preto",       "CR", 2, 1000, None),
    ("PETG", "Creality", "Verde",       "CR", 2, 1000, None),
    ("PETG", "Voolt3D",  "Amarelo",     "HF", 1, 1000, None),
    ("PETG", "Voolt3D",  "Translucido", "HF", 1, 1000, None),
    ("PETG", "Sunlu",    "Preto",       "HS", 1, 1000, None),
    ("PETG", "Sunlu",    "Laranja",     "HS", 1, 1000, None),
]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_items():
    """Expande a lista em linhas físicas (1 rolo = 1 item, uid próprio)."""
    now = _now()
    items = []
    for material, manufacturer, color, finish, qty, weight_g, notes in STOCK:
        for _ in range(qty):
            items.append({
                "uid": str(uuid.uuid4()),
                "material": material,
                "manufacturer": manufacturer,
                "color_name": color,
                "hex_color": None,
                "finish": finish,
                "weight_g": weight_g,
                "spools": 1,
                "status": inventory.STATUS_IN_STOCK,
                "variant_id": None,
                "sku": None,
                "notes": notes,
                "created_at": now,
                "updated_at": now,
            })
    return items


def backup_current(backup_dir: Path):
    """Dump lógico do estoque atual antes do reset. Retorna o caminho ou None."""
    inventory.init_db()
    data = inventory.export_data()
    if data["count"] == 0:
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"inventory_backup_{stamp}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def summarize(items):
    by_mat = {}
    for it in items:
        by_mat.setdefault(it["material"], 0)
        by_mat[it["material"]] += 1
    return by_mat


def main():
    ap = argparse.ArgumentParser(description="Reset total do estoque de filamentos.")
    ap.add_argument("--dry-run", action="store_true", help="mostra o que faria sem escrever")
    ap.add_argument("--no-backup", action="store_true", help="pula o backup do estoque atual")
    args = ap.parse_args()

    items = build_items()
    by_mat = summarize(items)

    print(f"Banco de estoque: {inventory.INVENTORY_DB_PATH}")
    print(f"Itens a inserir (1 rolo = 1 linha): {len(items)}")
    for mat, n in sorted(by_mat.items()):
        print(f"  {mat}: {n} rolos")

    current = inventory.list_items()
    print(f"Itens atualmente no banco (serão substituídos): {len(current)}")

    if args.dry_run:
        print("\n[dry-run] nenhuma alteração feita.")
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    if not args.no_backup:
        backup_path = backup_current(Path(inventory.INVENTORY_DB_PATH).parent / "backups")
        if backup_path:
            print(f"Backup do estoque atual: {backup_path}")
        else:
            print("Estoque atual vazio — nenhum backup necessário.")

    payload = {
        "schema_version": inventory.INVENTORY_SCHEMA_VERSION,
        "exported_at": _now(),
        "count": len(items),
        "items": items,
    }
    summary = inventory.import_data(payload, replace=True)
    print("\nReset concluído (espelho da lista):")
    print(f"  criados:    {summary['created']}")
    print(f"  atualizados:{summary['updated']}")
    print(f"  removidos:  {summary['deleted']}")
    print(f"  ignorados:  {summary['skipped']}")
    if summary["errors"]:
        print("  ERROS:")
        for e in summary["errors"]:
            print(f"    - {e}")

    final = inventory.list_items()
    print(f"\nTotal final no banco: {len(final)} rolos")


if __name__ == "__main__":
    main()
