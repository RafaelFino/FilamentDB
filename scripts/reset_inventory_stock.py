#!/usr/bin/env python3
"""
reset_inventory_stock.py — Reset total do estoque a partir do arquivo de estoque.

O arquivo `data/Estoque <data>.md` é a IMAGEM COMPLETA do estoque físico (fonte
de verdade, recontada por foto e enriquecida com a nomenclatura do catálogo).
Este script lê as tabelas markdown e espelha o banco de estoque: apaga TODO o
estoque atual e insere exatamente os rolos listados, preservando a localização
(`Local`) de cada um.

Modelo do banco (ver src/inventory.py): 1 linha = 1 rolo (spools=1), com `uid`
estável por rolo. Uma linha da tabela com Quantidade=N vira N linhas físicas.

Enriquecimento com o catálogo: a coluna `filament_key` casa o rolo com um
`filament_profiles` do catálogo (filament.db); o id resolvido é gravado em
`variant_id`, criando a ponte estoque↔catálogo (MVS, temps, preço acessíveis a
partir do item). O `hex_color` vem da coluna `Hex` do arquivo (tom curado), que
alimenta o swatch da UI — sem ele o quadradinho de cor fica cinza.

O reset usa `inventory.import_data(payload, replace=True)` (espelho). Antes de
escrever, faz backup do estoque atual em <data_dir>/backups/.

Formato esperado do markdown (uma seção `## <MATERIAL>` por material):

    | Marca | Tipo | Cor | Quantidade | Tamanho do rolo | Hex | RGB | Local | Obs | Linha | Produto | filament_key |

Colunas Hex, Local e filament_key são opcionais (ausentes → hex nulo,
Local=in_stock, sem ponte com o catálogo). O `filament_key` contém `|`
(separador de célula do markdown), então é escapado como `\\|` no arquivo; o
parser divide em pipes NÃO escapados e des-escapa cada célula.

Uso:
    python scripts/reset_inventory_stock.py <arquivo.md>   # explícito
    python scripts/reset_inventory_stock.py                # auto: data/Estoque *.md mais recente
    python scripts/reset_inventory_stock.py --dry-run      # só mostra o que faria
    python scripts/reset_inventory_stock.py --no-backup    # pula o backup (não recomendado)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src import config, inventory  # noqa: E402

# Normalização de fabricante para a capitalização usada no banco/catálogo.
_MANUFACTURER_CANON = {
    "voolt3d": "Voolt3D",
    "creality": "Creality",
    "sunlu": "Sunlu",
    "elegoo": "Elegoo",
}

# Colunas aceitas (nome normalizado em casefold → chave interna).
_COL_ALIASES = {
    "marca": "manufacturer",
    "tipo": "finish",
    "cor": "color_name",
    "quantidade": "quantity",
    "tamanho do rolo": "weight",
    "hex": "hex_color",
    "rgb": "rgb",
    "local": "status",
    "obs": "notes",
    "linha": "line",
    "produto": "product",
    "filament_key": "filament_key",
}
_REQUIRED_COLS = {"manufacturer", "finish", "color_name", "quantity", "weight"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon_manufacturer(raw: str) -> str:
    return _MANUFACTURER_CANON.get(raw.strip().casefold(), raw.strip())


def _parse_weight_g(raw: str) -> int:
    """'1 kg' → 1000, '0.5kg' → 500, '500 g' → 500. Default 1000."""
    s = (raw or "").strip().casefold().replace(",", ".")
    m = re.search(r"([0-9]*\.?[0-9]+)\s*(kg|g)?", s)
    if not m:
        return 1000
    value = float(m.group(1))
    unit = m.group(2) or "kg"  # número sem unidade = kg (formato do arquivo)
    grams = value * 1000 if unit == "kg" else value
    return int(round(grams))


def _clean_notes(raw: str):
    """Obs → notes. Remove parênteses externos; vazio vira None."""
    s = (raw or "").strip()
    m = re.fullmatch(r"\((.*)\)", s)
    if m:
        s = m.group(1).strip()
    return s or None


def _split_cells(line: str):
    """Divide uma linha de tabela markdown em células.

    Divide apenas em pipes NÃO escapados (`(?<!\\)\\|`) e des-escapa `\\|`→`|`
    em cada célula. Necessário porque o filament_key contém `|`.
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", s)]


def _is_separator_row(cells) -> bool:
    return all(re.fullmatch(r":?-+:?", c or "") for c in cells) and any(cells)


def _load_catalog_keys():
    """Mapa filament_key → filament_profiles.id (ponte estoque↔catálogo).

    Lê o catálogo (filament.db). Se o banco/tabela não existir, devolve {} e o
    script segue sem preencher variant_id (não é fatal — o estoque é autônomo).
    """
    try:
        db_path = config.database_path("filament.db")
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT filament_key, id FROM filament_profiles "
            "WHERE filament_key IS NOT NULL AND TRIM(filament_key) <> ''"
        ).fetchall()
        conn.close()
        return {k: i for k, i in rows}
    except Exception as exc:
        print(f"[aviso] catálogo indisponível ({exc}); variant_id ficará nulo.")
        return {}


def _normalize_status(raw: str) -> str:
    s = (raw or "").strip().casefold()
    return s if s in inventory.VALID_STATUSES else inventory.DEFAULT_STATUS


def parse_markdown(path: Path, catalog_keys: dict):
    """Lê o arquivo de estoque e devolve a lista de itens físicos (1 rolo cada)."""
    text = path.read_text(encoding="utf-8")
    now = _now()
    items = []
    unknown_keys = set()
    current_material = None
    header = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if m:
            heading = m.group(1).strip()
            if re.fullmatch(r"[A-Za-z0-9\-]+", heading):
                current_material = heading.upper()
            else:
                current_material = None
            header = None
            continue

        if not line.lstrip().startswith("|"):
            continue

        cells = _split_cells(line)

        if _is_separator_row(cells):
            continue

        if header is None:
            header = {}
            for idx, name in enumerate(cells):
                key = _COL_ALIASES.get(name.strip().casefold())
                if key:
                    header[key] = idx
            missing = _REQUIRED_COLS - set(header)
            if missing:
                raise ValueError(
                    f"Seção '## {current_material}': header não reconhecido "
                    f"(faltam {sorted(missing)}). Linha: {line!r}"
                )
            continue

        if current_material is None:
            raise ValueError(f"Linha de tabela sem material definido: {line!r}")

        def cell(key):
            idx = header.get(key)
            return cells[idx] if idx is not None and idx < len(cells) else ""

        manufacturer = _canon_manufacturer(cell("manufacturer"))
        finish = cell("finish").strip() or None
        color = cell("color_name").strip()
        qty_raw = cell("quantity").strip()
        weight_g = _parse_weight_g(cell("weight"))
        hex_color = cell("hex_color").strip() or None
        status = _normalize_status(cell("status"))
        notes = _clean_notes(cell("notes"))
        filament_key = cell("filament_key").strip() or None

        variant_id = None
        if filament_key:
            variant_id = catalog_keys.get(filament_key)
            if variant_id is None:
                unknown_keys.add(filament_key)

        if not color or not manufacturer:
            raise ValueError(f"Linha com Marca/Cor vazias: {line!r}")
        try:
            qty = int(qty_raw)
        except ValueError:
            raise ValueError(f"Quantidade inválida ({qty_raw!r}): {line!r}")
        if qty < 1:
            raise ValueError(f"Quantidade < 1: {line!r}")

        for _ in range(qty):
            items.append({
                "uid": str(uuid.uuid4()),
                "material": current_material,
                "manufacturer": manufacturer,
                "color_name": color,
                "hex_color": hex_color,
                "finish": finish,
                "weight_g": weight_g,
                "spools": 1,
                "status": status,
                "variant_id": variant_id,
                "sku": None,
                "notes": notes,
                "created_at": now,
                "updated_at": now,
            })

    if not items:
        raise ValueError(
            f"Nenhum item em {path}. Confira as tabelas de material (## PLA, ...)."
        )
    if unknown_keys:
        print("[aviso] filament_key(s) não encontrados no catálogo (variant_id "
              f"ficou nulo nesses): {sorted(unknown_keys)}")
    return items


def _resolve_source(arg):
    if arg:
        p = Path(arg)
        if not p.is_absolute():
            p = _REPO_ROOT / p
        if not p.is_file():
            raise SystemExit(f"Arquivo de estoque não encontrado: {p}")
        return p
    candidates = sorted((_REPO_ROOT / "data").glob("Estoque *.md"))
    if not candidates:
        raise SystemExit(
            "Nenhum 'data/Estoque *.md'. Passe o caminho: "
            "python scripts/reset_inventory_stock.py <arquivo.md>"
        )
    return candidates[-1]


def backup_current(backup_dir: Path):
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
    by_mat, by_loc = {}, {}
    for it in items:
        by_mat[it["material"]] = by_mat.get(it["material"], 0) + 1
        by_loc[it["status"]] = by_loc.get(it["status"], 0) + 1
    return by_mat, by_loc


def main():
    ap = argparse.ArgumentParser(description="Reset total do estoque a partir do arquivo markdown.")
    ap.add_argument("source", nargs="?", help="arquivo .md (default: data/Estoque *.md mais recente)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o que faria sem escrever")
    ap.add_argument("--no-backup", action="store_true", help="pula o backup do estoque atual")
    args = ap.parse_args()

    source = _resolve_source(args.source)
    catalog_keys = _load_catalog_keys()
    items = parse_markdown(source, catalog_keys)
    by_mat, by_loc = summarize(items)

    print(f"Fonte: {source}")
    print(f"Banco de estoque: {inventory.INVENTORY_DB_PATH}")
    print(f"Itens a inserir (1 rolo = 1 linha): {len(items)}")
    for mat, n in sorted(by_mat.items()):
        print(f"  {mat}: {n} rolos")
    print(f"Por localização: {by_loc}")
    linked = sum(1 for it in items if it["variant_id"] is not None)
    print(f"Vinculados ao catálogo (variant_id): {linked}/{len(items)}")

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
    print("\nReset concluído (espelho do arquivo):")
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
