#!/usr/bin/env python3
"""Import process profiles from Creality Print JSON files into filament.db."""

import json
import os
import re
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("FILAMENT_DB_PATH", "filament.db")
DATA_SOURCE_DIR = os.environ.get(
    "PROCESS_SOURCE_DIR",
    os.path.join(os.path.dirname(__file__), "creality-print-process"),
)

PROFILE_TYPE_MAPPING = {
    "Draft": "draft",
    "Fast": "fast",
    "Standard": "standard",
    "Balanced": "balanced",
    "Strong": "strong",
    "Quality": "quality",
}

JSON_TO_COLUMN = {
    "initial_layer_print_height": "initial_layer_height",
}

BOOL_COLUMNS = {"enable_support", "support_on_build_plate_only"}
INT_COLUMNS = {
    "default_acceleration",
    "inner_wall_acceleration",
    "outer_wall_acceleration",
    "top_surface_acceleration",
    "wall_loops",
    "infill_combination",
    "top_shell_layers",
    "bottom_shell_layers",
    "support_interface_top_layers",
}
FLOAT_COLUMNS = {
    "inner_wall_speed",
    "outer_wall_speed",
    "sparse_infill_speed",
    "internal_solid_infill_speed",
    "top_surface_speed",
    "initial_layer_speed",
    "travel_speed",
    "support_speed",
    "gap_infill_speed",
    "top_shell_thickness",
    "bottom_shell_thickness",
    "support_top_z_distance",
    "support_interface_spacing",
    "support_object_xy_distance",
    "brim_width",
    "brim_object_gap",
    "nozzle_size",
}
TEXT_COLUMNS = {
    "wall_generator",
    "wall_sequence",
    "sparse_infill_density",
    "sparse_infill_pattern",
    "internal_solid_infill_pattern",
    "top_surface_pattern",
    "bottom_surface_pattern",
    "support_type",
    "support_xy_overrides_z",
    "ironing_type",
    "seam_position",
    "inherits",
    "base_id",
    "version",
    "printer_model",
}


def ensure_materials(cur):
    materials = [
        ("PLA", "Polylactic Acid - Filamento versátil para impressão geral", 220, 60),
        ("PETG", "Polyethylene Terephthalate Glycol - Filamento resistente e durável", 230, 75),
        ("TPU", "Thermoplastic Polyurethane - Filamento flexível e elástico", 220, 50),
        ("ABS", "Acrylonitrile Butadiene Styrene - Filamento resistente ao calor e impacto", 250, 100),
        ("PLA-CF", "PLA com fibra de carbono - Filamento reforçado com alta rigidez", 220, 60),
        ("PETG-CF", "PETG com fibra de carbono - Filamento reforçado com alta resistência", 230, 75),
    ]
    for name, description, nozzle_temp, bed_temp in materials:
        cur.execute("SELECT id FROM materials WHERE name = ?", (name,))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO materials(
                    name, description, average_cost, difficulty, strength,
                    flexibility, temperature_resistance, uv_resistance, food_safe,
                    indoor, outdoor, abrasive, requires_enclosure,
                    recommended_nozzle_temp, recommended_bed_temp
                )
                VALUES (?, ?, 50, 50, 50, 50, 50, 50, 0, 1, 0, 0, 0, ?, ?)
                """,
                (name, description, nozzle_temp, bed_temp),
            )
            print(f"Material {name} criado")


def extract_material(filename, profile_data):
    name = profile_data.get("name", filename)
    for token in ("PLA-CF", "PETG-CF", "TPU", "ABS", "PLA", "PETG"):
        if token in name or token in filename:
            return token
    return None


def extract_profile_type(filename):
    for type_name, type_code in PROFILE_TYPE_MAPPING.items():
        if type_name in filename:
            return type_code
    return "standard"


def extract_layer_height(filename):
    match = re.search(r"(\d+\.?\d*)mm", filename)
    return float(match.group(1)) if match else 0.2


def coerce_value(column, raw):
    if raw is None or raw == "":
        return None
    if column in BOOL_COLUMNS:
        return int(str(raw).strip().lower() in {"1", "true", "yes"})
    if column in INT_COLUMNS:
        return int(float(raw))
    if column in FLOAT_COLUMNS:
        return float(raw)
    return str(raw)


def json_field_to_column(json_key):
    return JSON_TO_COLUMN.get(json_key, json_key)


def build_row(profile_data, filename, material_id):
    material_name = extract_material(filename, profile_data)
    profile_type = extract_profile_type(filename)
    layer_height = extract_layer_height(filename)
    profile_name = profile_data.get("name", filename.replace(".json", ""))

    row = {
        "material_id": material_id,
        "profile_name": profile_name,
        "profile_type": profile_type,
        "layer_height": layer_height,
        "description": f"Perfil {profile_type} para {material_name} — K2 Combo 0.4mm",
        "notes": f"Importado de {filename}",
        "printer_model": "Creality K2 Combo",
        "nozzle_size": 0.4,
        "base_id": profile_data.get("base_id", "GP004"),
        "inherits": profile_data.get("inherits", "0.20mm Standard @Creality K2 0.4 nozzle"),
        "version": profile_data.get("version", "26.4.28.18"),
        "active": 1,
    }

    for json_key, value in profile_data.items():
        column = json_field_to_column(json_key)
        if column in row:
            continue
        if column in BOOL_COLUMNS | INT_COLUMNS | FLOAT_COLUMNS | TEXT_COLUMNS:
            coerced = coerce_value(column, value)
            if coerced is not None:
                row[column] = coerced

    return row


def main():
    source = Path(DATA_SOURCE_DIR)
    process_files = sorted(source.glob("*.json"))
    if not process_files:
        raise SystemExit(f"ERRO: Nenhum arquivo JSON encontrado em {source}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ensure_materials(cur)
    conn.commit()

    cur.execute("DELETE FROM process_profiles")
    conn.commit()
    print(f"Importando {len(process_files)} perfis de {source}")

    columns = [
        "material_id", "profile_name", "profile_type", "layer_height", "initial_layer_height",
        "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed", "internal_solid_infill_speed",
        "top_surface_speed", "initial_layer_speed", "travel_speed", "support_speed", "gap_infill_speed",
        "default_acceleration", "inner_wall_acceleration", "outer_wall_acceleration", "top_surface_acceleration",
        "wall_loops", "wall_generator", "wall_sequence", "sparse_infill_density", "sparse_infill_pattern",
        "internal_solid_infill_pattern", "infill_combination", "top_surface_pattern", "bottom_surface_pattern",
        "top_shell_layers", "bottom_shell_layers", "top_shell_thickness", "bottom_shell_thickness",
        "enable_support", "support_type", "support_on_build_plate_only", "support_top_z_distance",
        "support_interface_spacing", "support_interface_top_layers", "support_object_xy_distance",
        "support_xy_overrides_z", "brim_width", "brim_object_gap", "ironing_type", "seam_position",
        "printer_model", "nozzle_size", "base_id", "inherits", "version",
        "description", "notes", "active",
    ]

    inserted = 0
    for json_file in process_files:
        try:
            with open(json_file, encoding="utf-8") as handle:
                profile_data = json.load(handle)

            material_name = extract_material(json_file.name, profile_data)
            if not material_name:
                print(f"AVISO: material não identificado em {json_file.name}")
                continue

            cur.execute("SELECT id FROM materials WHERE name = ?", (material_name,))
            material_row = cur.fetchone()
            if not material_row:
                print(f"ERRO: material {material_name} não encontrado")
                continue

            row = build_row(profile_data, json_file.name, material_row[0])
            values = [row.get(col) for col in columns]
            placeholders = ", ".join(["?"] * len(columns))
            cur.execute(
                f"INSERT INTO process_profiles({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            inserted += 1
            print(f"  ✓ {row['profile_name']}")
        except Exception as exc:
            print(f"ERRO em {json_file.name}: {exc}")
            raise

    conn.commit()
    conn.close()
    print(f"\nConcluído: {inserted} perfis importados.")


if __name__ == "__main__":
    main()
