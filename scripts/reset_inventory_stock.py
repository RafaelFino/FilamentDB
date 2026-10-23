#!/usr/bin/env python3
"""
reset_inventory_stock.py — Reset total do estoque a partir do arquivo de estoque.

O arquivo `data/Estoque <data>.md` é a IMAGEM COMPLETA do estoque físico (fonte
de verdade). Este script lê as tabelas markdown desse arquivo e espelha o banco:
apaga TODO o estoque atual e insere exatamente os rolos listados, todos como
`in_stock`. Qualquer localização anterior (cfs/spool/drybox/open) é descartada —
a redistribuição física (CFS, drybox, etc.) é feita depois pela interface.

Modelo do banco (ver src/inventory.py): 1 linha = 1 rolo (spools=1), com `uid`
estável por rolo. Uma linha da tabela com Quantidade=N vira N linhas físicas.

O reset é feito via `inventory.import_data(payload, replace=True)`, que espelha
o payload: insere os itens do arquivo e remove todo o resto. Reusa a validação e
a geração de uid do próprio módulo, sem depender do servidor HTTP no ar.

Antes de escrever, faz um backup do estoque atual (dump lógico versionado via
export_data()) em <data_dir>/backups/.

Formato esperado do markdown (uma seção por material):

    ## PLA
    | Marca | Tipo | Cor | Quantidade | Tamanho do rolo | Obs |
    | - | - | - | - | - | - |
    | Voolt3d | Velvet | Vermelho | 2 | 1 kg | (Troca de Cor) |
    ...

Mapeamentos:
  - título da seção (## PLA)      → material
  - Marca                         → manufacturer (Voolt3d → Voolt3D)
  - Tipo                          → finish (literal: Velvet, HF, CR, HS, PRO, ...)
  - Cor                           → color_name
  - Quantidade                    → nº de linhas físicas (spools=1 cada)
  - Tamanho do rolo               → weight_g (1 kg→1000, 0.5kg→500)
  - Obs                           → notes (parênteses removidos; vazio → None)

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
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Permite rodar como `python scripts/reset_inventory_stock.py` a partir da raiz.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src import inventory  # noqa: E402

# Normalização de fabricante para a capitalização usada no banco/catálogo.
# O arquivo digita "Voolt3d"; o banco usa "Voolt3D". Demais marcas já batem.
_MANUFACTURER_CANON = {
    "voolt3d": "Voolt3D",
    "creality": "Creality",
    "sunlu": "Sunlu",
    "elegoo": "Elegoo",
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon_manufacturer(raw: str) -> str:
    return _MANUFACTURER_CANON.get(raw.strip().casefold(), raw.strip())


def _parse_weight_g(raw: str) -> int:
    """'1 kg' → 1000, '0.5kg' → 500, '500 g' → 500. Default 1000 se não parsear."""
    s = (raw or "").strip().casefold().replace(",", ".")
    m = re.search(r"([0-9]*\.?[0-9]+)\s*(kg|g)?", s)
    if not m:
        return 1000
    value = float(m.group(1))
    unit = m.group(2) or "kg"  # "1" sem unidade é interpretado como kg (formato do arquivo)
    grams = value * 1000 if unit == "kg" else value
    return int(round(grams))


def _clean_notes(raw: str):
    """Obs → notes. Remove parênteses externos e espaços; vazio vira None."""
    s = (raw or "").strip()
    # Remove um par de parênteses externos, se houver: "(Troca de Cor)" → "Troca de Cor".
    m = re.fullmatch(r"\((.*)\)", s)
    if m:
        s = m.group(1).strip()
    return s or None


def _split_row(line: str):
    """Quebra uma linha de tabela markdown em células, descartando as bordas."""
    # Tira o pipe inicial/final e separa; strip em cada célula.
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _is_separator_row(cells) -> bool:
    """Linha separadora do header: células só com '-', ':' (ex.: '-', ':-:')."""
    return all(re.fullmatch(r":?-+:?", c or "") for c in cells) and any(cells)


def parse_markdown(path: Path):
    """Lê o arquivo de estoque e retorna a lista de itens físicos (1 rolo cada).

    Levanta ValueError com mensagem clara se o formato não bater (header de
    coluna ausente, material sem tabela, etc.) — melhor falhar explícito do que
    espelhar o banco com dados parciais.
    """
    text = path.read_text(encoding="utf-8")
    now = _now()
    items = []
    current_material = None
    header = None  # mapeia nome-de-coluna normalizado → índice

    # Nomes de coluna aceitos (normalizados em casefold, sem acento relevante).
    col_aliases = {
        "marca": "manufacturer",
        "tipo": "finish",
        "cor": "color_name",
        "quantidade": "quantity",
        "tamanho do rolo": "weight",
        "obs": "notes",
    }
    required = {"manufacturer", "finish", "color_name", "quantity", "weight"}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        # Cabeçalho de seção: "## PLA" define o material corrente.
        m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if m:
            heading = m.group(1).strip()
            # Só tratamos como material se for uma palavra de material plausível
            # (evita pegar o título "# Lista atualizada..."). Um material é um
            # token curto sem espaços (PLA, PETG, ABS, TPU, PLA-CF).
            if re.fullmatch(r"[A-Za-z0-9\-]+", heading):
                current_material = heading.upper()
                header = None  # nova seção reinicia o header
            else:
                current_material = None
                header = None
            continue

        # Fora de qualquer tabela de material: ignora texto solto.
        if not line.lstrip().startswith("|"):
            continue

        cells = _split_row(line)

        # Linha separadora (|---|---|): ignora.
        if _is_separator_row(cells):
            continue

        # Primeira linha de pipes após o heading é o header de colunas.
        if header is None:
            header = {}
            for idx, name in enumerate(cells):
                key = col_aliases.get(name.strip().casefold())
                if key:
                    header[key] = idx
            missing = required - set(header)
            if missing:
                raise ValueError(
                    f"Seção '## {current_material}': header de tabela não "
                    f"reconhecido (faltam colunas {sorted(missing)}). "
                    f"Linha: {line!r}"
                )
            continue

        # Linha de dados.
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
        notes = _clean_notes(cell("notes"))

        if not color or not manufacturer:
            raise ValueError(f"Linha com Marca/Cor vazias: {line!r}")
        try:
            qty = int(qty_raw)
        except ValueError:
            raise ValueError(f"Quantidade inválida ({qty_raw!r}) na linha: {line!r}")
        if qty < 1:
            raise ValueError(f"Quantidade < 1 na linha: {line!r}")

        for _ in range(qty):
            items.append({
                "uid": str(uuid.uuid4()),
                "material": current_material,
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

    if not items:
        raise ValueError(
            f"Nenhum item encontrado em {path}. Confira se há tabelas de "
            f"material (## PLA, ## PETG, ...) no formato esperado."
        )
    return items


def _resolve_source(arg: str | None) -> Path:
    """Resolve o arquivo de estoque: o argumento, ou o 'data/Estoque *.md' mais recente."""
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
            "Nenhum 'data/Estoque *.md' encontrado. Passe o caminho explícito: "
            "python scripts/reset_inventory_stock.py <arquivo.md>"
        )
    return candidates[-1]  # ordenação lexicográfica = data mais recente no nome


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
        by_mat[it["material"]] = by_mat.get(it["material"], 0) + 1
    return by_mat


def main():
    ap = argparse.ArgumentParser(description="Reset total do estoque a partir do arquivo markdown.")
    ap.add_argument("source", nargs="?", help="arquivo de estoque .md (default: data/Estoque *.md mais recente)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o que faria sem escrever")
    ap.add_argument("--no-backup", action="store_true", help="pula o backup do estoque atual")
    args = ap.parse_args()

    source = _resolve_source(args.source)
    items = parse_markdown(source)
    by_mat = summarize(items)

    print(f"Fonte: {source}")
    print(f"Banco de estoque: {inventory.INVENTORY_DB_PATH}")
    print(f"Itens a inserir (1 rolo = 1 linha, todos in_stock): {len(items)}")
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
    print(f"\nTotal final no banco: {len(final)} rolos (todos in_stock)")


if __name__ == "__main__":
    main()
