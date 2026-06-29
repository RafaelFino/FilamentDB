#!/usr/bin/env python3

import json
import os
import sqlite3
import yaml
from pathlib import Path

DB_PATH = os.environ.get("FILAMENT_DB_PATH", "filament.db")
DATA_DIR = Path("data")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ============================================================================
# HELPERS
# ============================================================================

def get_or_create_manufacturer(name, country=None, website=None):
    cur.execute("SELECT id FROM manufacturers WHERE name = ?", (name,))
    row = cur.fetchone()

    if row:
        return row[0]

    cur.execute("""
        INSERT INTO manufacturers(name, country, website)
        VALUES (?, ?, ?)
    """, (name, country, website))

    return cur.lastrowid


def get_or_create_material(name, material_data=None):
    cur.execute("SELECT id FROM materials WHERE name = ?", (name,))
    row = cur.fetchone()

    if row:
        return row[0]

    cur.execute("""
        INSERT INTO materials(
            name,
            description,
            average_cost,
            difficulty,
            strength,
            flexibility,
            temperature_resistance,
            uv_resistance,
            food_safe,
            indoor,
            outdoor,
            abrasive,
            requires_enclosure,
            recommended_nozzle_temp,
            recommended_bed_temp
        )
        VALUES (?, '', 50, 50, 50, 50, 50, 50, 0, 1, 0, 0, 0, 220, 60)
    """, (name,))

    return cur.lastrowid


def insert_profile(manufacturer_id, material_id, profile):
    cur.execute("""
        INSERT INTO filament_profiles(
            manufacturer_id,
            material_id,
            commercial_name,
            profile_name,
            printer_model,
            nozzle_size,
            inherits,
            base_id,
            creality_print_version,
            nozzle_temp_initial,
            nozzle_temp_min,
            nozzle_temp_max,
            bed_temp_initial,
            bed_temp,
            flow_ratio,
            max_volumetric_speed,
            profile_version,
            confidence,
            line,
            line_description,
            line_positioning,
            line_target_use,
            line_color_options,
            color,
            surface_finish,
            recommendation,
            diameter,
            density,
            drying_temperature,
            drying_time,
            notes,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        manufacturer_id,
        material_id,
        profile["commercial_name"],
        profile["profile_name"],
        profile.get("printer_model", "Creality K2 Combo"),
        profile.get("nozzle_size", 0.4),
        profile["inherits"],
        profile.get("base_id", "GFSA04"),
        profile.get("version", "7.0"),
        profile["nozzle"]["initial"],
        profile["nozzle"]["min"],
        profile["nozzle"]["max"],
        profile["bed"]["initial"],
        profile["bed"]["temp"],
        profile.get("flow_ratio", 1.0),
        profile.get("max_volumetric_speed", 12),
        profile.get("profile_version", 1),
        profile.get("confidence", 70),
        profile.get("line"),
        profile.get("line_description"),
        profile.get("line_positioning"),
        profile.get("line_target_use"),
        json.dumps(profile.get("line_color_options", []), ensure_ascii=False) if profile.get("line_color_options") is not None else None,
        profile.get("color"),
        profile.get("surface_finish"),
        profile.get("recommendation"),
        profile.get("diameter"),
        profile.get("density"),
        profile.get("drying_temperature"),
        profile.get("drying_time"),
        profile.get("notes", ""),
        profile.get("active", 1)
    ))


# ============================================================================
# LOAD YAML FILES
# ============================================================================

for file in DATA_DIR.glob("*.yaml"):

    print(f"Loading {file.name}")

    with open(file, "r") as f:
        data = yaml.safe_load(f)

    manufacturer_name = data["manufacturer"]["name"]
    manufacturer_id = get_or_create_manufacturer(
        manufacturer_name,
        data["manufacturer"].get("country"),
        data["manufacturer"].get("website")
    )

    line_map = {
        line_def["name"]: line_def
        for line_def in data.get("lines", [])
        if "name" in line_def
    }

    for material_name, material_block in data["materials"].items():

        material_id = get_or_create_material(material_name)

        for profile in material_block["profiles"]:
            line_name = profile.get("line")
            line_def = line_map.get(line_name, {})
            profile["line_description"] = line_def.get("description")
            profile["line_positioning"] = line_def.get("positioning")
            profile["line_target_use"] = line_def.get("target_use")
            profile["line_color_options"] = line_def.get("color_options")

            if "color" not in profile:
                profile["color"] = profile.get("color", material_name if material_name in ["PLA", "PETG", "ABS", "ASA", "TPU"] else "Natural")

            if "surface_finish" not in profile:
                profile["surface_finish"] = profile.get("surface_finish", "Standard")

            insert_profile(manufacturer_id, material_id, profile)


conn.commit()
conn.close()

print("Seed concluído com sucesso!")