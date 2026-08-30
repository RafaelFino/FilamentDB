#!/usr/bin/env python3
"""
enrich_yaml_from_csv.py

Merge dados dos CSVs (cores, SKUs, secagem) nos YAMLs de fabricantes.
Cada perfil de impressão recebe uma lista `variants` com todas as cores/SKUs
encontradas no CSV para aquele material/linha.

Lógica de matching:
  1. Tenta casar pelo `commercial_name` do CSV com o do YAML
  2. Fallback: casa pelo nome do material (material type) e linha

Após o merge, os arquivos YAML são reescritos e os CSVs podem ser removidos.
"""
import csv
import re
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Fabricante no CSV -> nome do arquivo YAML (sem extensão)
MANUFACTURER_YAML_MAP = {
    "voolt3d": "voolt3d",
    "f3d": "f3D",
    "gtmax": "gtmax",
    "gtmax3d": "gtmax",
    "masterprint": "masterprint",
    "creality": "creality",
}

# Mapeamento explícito: (yaml_commercial_name, material_type) -> (csv_line, csv_material)
# Usado quando o matching automático não encontra correspondência.
# csv_material None = usa o mesmo material do YAML.
EXPLICIT_MAP: dict[str, dict[tuple[str, str], tuple[str, str | None]]] = {
    "voolt3d": {
        # yaml (commercial_name, material)  ->  csv (line, material)
        ("PLA Velvet",    "PLA"):  ("PLA Velvet",   "PLA"),
        ("PLA Standard",  "PLA"):  ("PLA Premium",  "PLA"),
        ("PLA High Speed","PLA"):  ("PLA Premium",  "PLA"),
        ("PETG Standard", "PETG"): ("PETG HF",      "PETG"),
        ("PETG CF",       "PETG"): ("PETG HF",      "PETG"),
        ("ABS Standard",  "ABS"):  ("ABS Premium",  "ABS"),
        ("TPU 95A",       "TPU"):  ("TPU 95A",      "TPU"),
    },
    "f3d": {
        ("PLA Premium",   "PLA"):  ("PLA Premium",  "PLA"),
        ("PETG Standard", "PETG"): ("PETG Premium", "PETG"),
        ("ABS Industrial","ABS"):  ("ABS Premium",  "ABS"),
        ("ASA Outdoor",   "ASA"):  ("ASA",          "ASA"),
        ("TPU 95A",       "TPU"):  ("TPU 95A",      "TPU"),
    },
    "gtmax": {
        # GTMax só tem uma linha de PLA Premium no CSV → todas as 3 variantes de PLA mapeiam para ela
        ("PLA",         "PLA"):  ("PLA Premium", "PLA"),
        ("PLA+",        "PLA"):  ("PLA Premium", "PLA"),
        ("PLA Economy", "PLA"):  ("PLA Premium", "PLA"),
        ("PETG",        "PETG"): ("PETG Premium","PETG"),
        ("ABS",         "ABS"):  ("ABS Premium", "ABS"),
        ("TPU 95A",     "TPU"):  ("TPU 95A",     "TPU"),
    },
    "masterprint": {
        ("PLA Standard", "PLA"):  ("PLA Easy",      "PLA"),
        ("PLA Premium",  "PLA"):  ("PLA Easy",      "PLA"),
        ("PETG Standard","PETG"): ("PETG Premium",  "PETG"),
        ("ABS Standard", "ABS"):  ("ABS Premium",   "ABS"),
        ("TPU 95A",      "TPU"):  ("TPU 95A",       "TPU"),
    },
    "creality": {
        ("Hyper PLA",  "PLA"):  ("Hyper PLA", "PLA"),
        # CR PLA e Ender PLA não têm equivalente no CSV → sem variantes de cor por ora
        ("CR PETG",    "PETG"): ("PETG",      "PETG"),
        ("Hyper PETG", "PETG"): ("PETG",      "PETG"),
        ("ABS",        "ABS"):  ("ABS",       "ABS"),
        ("ASA",        "ASA"):  ("ASA",       "ASA"),
        ("TPU 95A",    "TPU"):  ("TPU 95A",   "TPU"),
    },
}


def normalize(text: str) -> str:
    """Lowercase, strip e remove espaços extras."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_rgb(rgb_str: str) -> list[int] | None:
    """'245,245,245' -> [245, 245, 245]"""
    if not rgb_str:
        return None
    try:
        parts = [int(x.strip()) for x in rgb_str.split(",")]
        if len(parts) == 3:
            return parts
    except ValueError:
        pass
    return None


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True,
                  default_flow_style=False, width=120)


def build_variant(row: dict) -> dict:
    """Converte uma linha CSV em um dict de variante."""
    variant: dict = {}

    sku = row.get("sku", "").strip()
    if sku:
        variant["sku"] = sku

    color_name = row.get("color_name", "").strip()
    if color_name:
        variant["color_name"] = color_name

    hex_val = row.get("hex", "").strip()
    if hex_val:
        variant["hex"] = hex_val

    rgb = parse_rgb(row.get("rgb", ""))
    if rgb:
        variant["rgb"] = rgb

    finish = row.get("finish", "").strip()
    if finish:
        variant["finish"] = finish

    try:
        diameter = float(row.get("diameter_mm", 0))
        if diameter:
            variant["diameter_mm"] = diameter
    except (ValueError, TypeError):
        pass

    try:
        weight = int(row.get("weight_g", 0))
        if weight:
            variant["weight_g"] = weight
    except (ValueError, TypeError):
        pass

    try:
        dry_temp = int(row.get("dry_temp", 0))
        if dry_temp:
            variant["dry_temp"] = dry_temp
    except (ValueError, TypeError):
        pass

    try:
        dry_hours = float(row.get("dry_hours", 0))
        if dry_hours:
            variant["dry_hours"] = dry_hours
    except (ValueError, TypeError):
        pass

    rec = row.get("recommended_use", "").strip()
    if rec:
        variant["recommended_use"] = rec

    notes = row.get("notes", "").strip()
    if notes:
        variant["notes"] = notes

    status = row.get("status", "").strip()
    if status:
        variant["status"] = status

    return variant


def match_profile_to_rows(
    profile: dict,
    material_name: str,
    csv_rows: list[dict],
    manufacturer_key: str = "",
) -> list[dict]:
    """
    Retorna todas as linhas CSV que correspondem a este perfil.

    Ordem de resolução:
      1. Mapeamento explícito (EXPLICIT_MAP) — mais confiável
      2. commercial_name exato + material
      3. CSV line == commercial_name do perfil + material
      4. linha YAML == linha CSV + material
    """
    profile_commercial = normalize(profile.get("commercial_name", ""))
    mat_norm = normalize(material_name)

    # 1. Mapeamento explícito
    explicit = EXPLICIT_MAP.get(manufacturer_key, {})
    mapping_key = (profile.get("commercial_name", ""), material_name)
    if mapping_key in explicit:
        csv_line, csv_mat = explicit[mapping_key]
        csv_mat_norm = normalize(csv_mat) if csv_mat else mat_norm
        matched = [
            r for r in csv_rows
            if normalize(r.get("line", "")) == normalize(csv_line)
            and normalize(r.get("material", "")) == csv_mat_norm
        ]
        if matched:
            return matched

    # 2. commercial_name exato
    matched = [
        r for r in csv_rows
        if normalize(r.get("commercial_name", "")) == profile_commercial
        and normalize(r.get("material", "")) == mat_norm
    ]
    if matched:
        return matched

    # 3. CSV line == commercial_name do perfil
    if profile_commercial:
        matched = [
            r for r in csv_rows
            if normalize(r.get("line", "")) == profile_commercial
            and normalize(r.get("material", "")) == mat_norm
        ]
        if matched:
            return matched

    return []


def enrich(yaml_path: Path, csv_path: Path, manufacturer_key: str = "") -> dict:
    data = load_yaml(yaml_path)
    summary = {"file": yaml_path.name, "profiles_enriched": 0, "variants_added": 0, "unmatched": []}

    with open(csv_path, newline="", encoding="utf-8") as f:
        csv_rows = [r for r in csv.DictReader(f) if any(v.strip() for v in r.values())]

    if not csv_rows:
        print(f"  Nenhum dado CSV em {csv_path.name}")
        return summary

    for material_name, material_block in data.get("materials", {}).items():
        for profile in material_block.get("profiles", []):
            matched_rows = match_profile_to_rows(profile, material_name, csv_rows, manufacturer_key)

            if not matched_rows:
                summary["unmatched"].append({
                    "material": material_name,
                    "profile": profile.get("profile_name"),
                })
                continue

            # Enriquecer campos diretos do perfil com dados da primeira linha
            first = matched_rows[0]
            if not profile.get("drying_temperature"):
                try:
                    dry_t = int(first.get("dry_temp", 0))
                    if dry_t:
                        profile["drying_temperature"] = dry_t
                except (ValueError, TypeError):
                    pass
            if not profile.get("drying_time"):
                try:
                    dry_h = float(first.get("dry_hours", 0))
                    if dry_h:
                        profile["drying_time"] = dry_h
                except (ValueError, TypeError):
                    pass

            # Construir lista de variantes
            variants = [build_variant(r) for r in matched_rows]
            profile["variants"] = variants

            summary["profiles_enriched"] += 1
            summary["variants_added"] += len(variants)

    write_yaml(yaml_path, data)
    return summary


def main():
    print("=== Enriquecendo YAMLs com dados dos CSVs ===\n")

    for csv_path in sorted(DATA_DIR.glob("*.csv")):
        manuf_key = normalize(csv_path.stem)
        yaml_stem = MANUFACTURER_YAML_MAP.get(manuf_key)

        if not yaml_stem:
            print(f"Pulando {csv_path.name}: sem mapeamento para YAML")
            continue

        yaml_path = DATA_DIR / f"{yaml_stem}.yaml"
        if not yaml_path.exists():
            print(f"Pulando {csv_path.name}: YAML não encontrado ({yaml_path})")
            continue

        print(f"Processando: {csv_path.name} -> {yaml_path.name}")
        summary = enrich(yaml_path, csv_path, manuf_key)

        print(f"  Perfis enriquecidos : {summary['profiles_enriched']}")
        print(f"  Variantes adicionadas: {summary['variants_added']}")
        if summary["unmatched"]:
            print(f"  Perfis sem match ({len(summary['unmatched'])}):")
            for u in summary["unmatched"]:
                print(f"    - [{u['material']}] {u['profile']}")
        print()

    print("=== Merge concluído. ===")
    print("Verifique os YAMLs e então delete os CSVs manualmente se estiver satisfeito.")


if __name__ == "__main__":
    main()
