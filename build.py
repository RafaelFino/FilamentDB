#!/usr/bin/env python3
"""
build.py — Pipeline unificado do FilamentDB.

Executa todas as etapas:
  1. Cria schema do banco SQLite
  2. Popula filamentos a partir dos YAMLs em data/
  3. Gera perfis de processo via herança (process-base/)
  4. Exporta perfis de filamento para Creality-Print/filaments/
  5. Exporta perfis de processo para Creality-Print/process/

Uso:
  python build.py              # pipeline completa
  python build.py --only-db    # apenas banco (sem export)
  python build.py --only-export # apenas export (banco já existe)
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("FILAMENT_DB_PATH", str(ROOT_DIR / "filament.db"))
DATA_DIR = ROOT_DIR / "filament-data"
PROCESS_BASE_DIR = ROOT_DIR / "process-base"
EXPORT_FILAMENTS_DIR = ROOT_DIR / "Creality-Print" / "filaments"
EXPORT_PROCESS_DIR = ROOT_DIR / "Creality-Print" / "process"
EXPORT_ORCA_FILAMENTS_DIR = ROOT_DIR / "OrcaSlicer" / "filament"
EXPORT_ORCA_PROCESS_DIR = ROOT_DIR / "OrcaSlicer" / "process"


# =============================================================================
# HELPERS
# =============================================================================

def info(msg):
    print(f"\033[0;32m[INFO]\033[0m  {msg}")


def warn(msg):
    print(f"\033[1;33m[WARN]\033[0m  {msg}")


def error(msg):
    print(f"\033[0;31m[ERROR]\033[0m {msg}", file=sys.stderr)
    sys.exit(1)


def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_filename(text):
    return text.replace(" ", "_").replace("/", "-").replace("\\", "-")


# =============================================================================
# STEP 1: CREATE SCHEMA
# =============================================================================

def create_schema():
    """Cria (ou recria) o banco de dados com todas as tabelas."""
    info("Criando schema do banco de dados...")

    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
    CREATE TABLE manufacturers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        country TEXT,
        website TEXT,
        notes TEXT
    );""")

    cur.execute("""
    CREATE TABLE materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        average_cost INTEGER DEFAULT 50,
        difficulty INTEGER DEFAULT 50,
        strength INTEGER DEFAULT 50,
        flexibility INTEGER DEFAULT 50,
        temperature_resistance INTEGER DEFAULT 50,
        uv_resistance INTEGER DEFAULT 50,
        food_safe INTEGER DEFAULT 0,
        indoor INTEGER DEFAULT 1,
        outdoor INTEGER DEFAULT 0,
        abrasive INTEGER DEFAULT 0,
        requires_enclosure INTEGER DEFAULT 0,
        recommended_nozzle_temp INTEGER,
        recommended_bed_temp INTEGER,
        notes TEXT
    );""")

    cur.execute("""
    CREATE TABLE filament_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manufacturer_id INTEGER NOT NULL,
        material_id INTEGER NOT NULL,
        commercial_name TEXT NOT NULL,
        profile_name TEXT NOT NULL UNIQUE,
        printer_model TEXT DEFAULT 'Creality K2 Combo',
        nozzle_size REAL DEFAULT 0.4,
        inherits TEXT,
        base_id TEXT DEFAULT 'GFSA04',
        creality_print_version TEXT DEFAULT '7.0',
        nozzle_temp_initial INTEGER,
        nozzle_temp_min INTEGER,
        nozzle_temp_max INTEGER,
        bed_temp_initial INTEGER,
        bed_temp INTEGER,
        textured_bed_initial INTEGER,
        textured_bed INTEGER,
        flow_ratio REAL DEFAULT 1.0,
        max_volumetric_speed REAL,
        profile_version INTEGER DEFAULT 1,
        confidence INTEGER DEFAULT 50,
        line TEXT,
        line_description TEXT,
        line_positioning TEXT,
        line_target_use TEXT,
        line_color_options TEXT,
        color TEXT,
        surface_finish TEXT,
        recommendation TEXT,
        diameter REAL DEFAULT 1.75,
        density REAL,
        drying_temperature INTEGER,
        drying_time REAL,
        notes TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(manufacturer_id) REFERENCES manufacturers(id),
        FOREIGN KEY(material_id) REFERENCES materials(id)
    );""")

    cur.execute("""
    CREATE TABLE filament_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filament_id INTEGER NOT NULL,
        sku TEXT,
        color_name TEXT,
        hex_color TEXT,
        rgb_r INTEGER,
        rgb_g INTEGER,
        rgb_b INTEGER,
        finish TEXT,
        diameter_mm REAL DEFAULT 1.75,
        weight_g INTEGER DEFAULT 1000,
        dry_temp INTEGER,
        dry_hours REAL,
        recommended_use TEXT,
        notes TEXT,
        status TEXT DEFAULT 'Active',
        FOREIGN KEY(filament_id) REFERENCES filament_profiles(id)
    );""")

    cur.execute("""
    CREATE TABLE process_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        material_id INTEGER NOT NULL,
        profile_name TEXT NOT NULL UNIQUE,
        profile_type TEXT NOT NULL,
        layer_height REAL,
        initial_layer_height REAL,
        inner_wall_speed REAL,
        outer_wall_speed REAL,
        sparse_infill_speed REAL,
        internal_solid_infill_speed REAL,
        top_surface_speed REAL,
        initial_layer_speed REAL,
        travel_speed REAL,
        support_speed REAL,
        gap_infill_speed REAL,
        default_acceleration INTEGER,
        inner_wall_acceleration INTEGER,
        outer_wall_acceleration INTEGER,
        top_surface_acceleration INTEGER,
        wall_loops INTEGER,
        wall_generator TEXT,
        wall_sequence TEXT,
        sparse_infill_density TEXT,
        sparse_infill_pattern TEXT,
        internal_solid_infill_pattern TEXT,
        infill_combination INTEGER,
        top_surface_pattern TEXT,
        bottom_surface_pattern TEXT,
        top_shell_layers INTEGER,
        bottom_shell_layers INTEGER,
        top_shell_thickness REAL,
        bottom_shell_thickness REAL,
        enable_support INTEGER,
        support_type TEXT,
        support_on_build_plate_only INTEGER,
        support_top_z_distance REAL,
        support_interface_spacing REAL,
        support_interface_top_layers INTEGER,
        support_object_xy_distance REAL,
        support_xy_overrides_z TEXT,
        support_critical_regions_only INTEGER DEFAULT 1,
        brim_width REAL,
        brim_object_gap REAL,
        ironing_type TEXT,
        ironing_speed REAL,
        ironing_flow REAL,
        ironing_spacing REAL,
        seam_position TEXT,
        seam_gap TEXT,
        seam_slope_type TEXT,
        seam_slope_conditional INTEGER DEFAULT 0,
        seam_slope_entire_loop INTEGER DEFAULT 0,
        seam_slope_inner_walls INTEGER DEFAULT 0,
        seam_slope_min_length INTEGER DEFAULT 20,
        seam_slope_start_height INTEGER DEFAULT 0,
        seam_slope_steps INTEGER DEFAULT 10,
        staggered_inner_seams INTEGER DEFAULT 0,
        role_based_wipe_speed INTEGER DEFAULT 0,
        wipe_on_loops INTEGER DEFAULT 0,
        enable_prime_tower INTEGER DEFAULT 1,
        prime_tower_width INTEGER DEFAULT 35,
        prime_tower_brim_width INTEGER DEFAULT 3,
        prime_volume INTEGER DEFAULT 45,
        flush_into_infill INTEGER DEFAULT 1,
        flush_into_objects INTEGER DEFAULT 0,
        flush_into_support INTEGER DEFAULT 1,
        flush_multiplier REAL DEFAULT 0.8,
        printer_model TEXT DEFAULT 'Creality K2 Combo',
        nozzle_size REAL DEFAULT 0.4,
        base_id TEXT DEFAULT 'GP004',
        inherits TEXT,
        version TEXT DEFAULT '26.4.28.18',
        description TEXT,
        notes TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(material_id) REFERENCES materials(id)
    );""")

    cur.execute("CREATE INDEX idx_filament_material ON filament_profiles(material_id);")
    cur.execute("CREATE INDEX idx_filament_manufacturer ON filament_profiles(manufacturer_id);")
    cur.execute("CREATE INDEX idx_variant_filament ON filament_variants(filament_id);")
    cur.execute("CREATE INDEX idx_process_material ON process_profiles(material_id);")
    cur.execute("CREATE INDEX idx_process_type ON process_profiles(profile_type);")

    conn.commit()
    conn.close()
    info(f"Schema criado: {DB_PATH}")


# =============================================================================
# STEP 2: SEED FILAMENTS
# =============================================================================

def seed_filaments():
    """Importa perfis de filamentos dos YAMLs em data/."""
    info("Importando filamentos de filament-data/*.yaml...")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    def get_or_create_manufacturer(name, country=None, website=None):
        cur.execute("SELECT id FROM manufacturers WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("INSERT INTO manufacturers(name, country, website) VALUES (?, ?, ?)",
                    (name, country, website))
        return cur.lastrowid

    def get_or_create_material(name):
        cur.execute("SELECT id FROM materials WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("""
            INSERT INTO materials(name, description, average_cost, difficulty, strength,
                flexibility, temperature_resistance, uv_resistance, food_safe,
                indoor, outdoor, abrasive, requires_enclosure, recommended_nozzle_temp, recommended_bed_temp)
            VALUES (?, '', 50, 50, 50, 50, 50, 50, 0, 1, 0, 0, 0, 220, 60)
        """, (name,))
        return cur.lastrowid

    def get_inherits_for_material(material_name):
        """Deriva o 'inherits' do Creality Print baseado no material."""
        mapping = {
            "PLA": "Hyper PLA @Creality K2 0.4 nozzle",
            "PETG": "Hyper PETG @Creality K2 0.4 nozzle",
            "PETG CF": "Hyper PETG CF @Creality K2 0.4 nozzle",
            "ABS": "ABS @Creality K2 0.4 nozzle",
            "ASA": "ASA @Creality K2 0.4 nozzle",
            "TPU": "TPU @Creality K2 0.4 nozzle",
            "SUPPORT": "Generic Support @Creality K2 0.4 nozzle",
        }
        return mapping.get(material_name, "Hyper PLA @Creality K2 0.4 nozzle")

    def insert_profile(manufacturer_id, material_id, profile, material_name):
        inherits = profile.get("inherits", get_inherits_for_material(material_name))
        cur.execute("""
            INSERT INTO filament_profiles(
                manufacturer_id, material_id, commercial_name, profile_name,
                printer_model, nozzle_size, inherits, base_id, creality_print_version,
                nozzle_temp_initial, nozzle_temp_min, nozzle_temp_max,
                bed_temp_initial, bed_temp, flow_ratio, max_volumetric_speed,
                profile_version, confidence, line, line_description, line_positioning,
                line_target_use, line_color_options, color, surface_finish,
                recommendation, diameter, density, drying_temperature, drying_time,
                notes, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            manufacturer_id, material_id,
            profile["commercial_name"], profile["profile_name"],
            profile.get("printer_model", "Creality K2 Combo"),
            profile.get("nozzle_size", 0.4),
            inherits,
            profile.get("base_id", "GFSA04"),
            profile.get("version", "7.0"),
            profile["nozzle"]["initial"], profile["nozzle"]["min"], profile["nozzle"]["max"],
            profile["bed"]["initial"], profile["bed"]["temp"],
            profile.get("flow_ratio", 1.0), profile.get("max_volumetric_speed", 12),
            profile.get("profile_version", 1), profile.get("confidence", 70),
            profile.get("line"), profile.get("line_description"),
            profile.get("line_positioning"), profile.get("line_target_use"),
            json.dumps(profile.get("line_color_options", []), ensure_ascii=False)
                if profile.get("line_color_options") is not None else None,
            profile.get("color"), profile.get("surface_finish"),
            profile.get("recommendation"), profile.get("diameter"),
            profile.get("density"), profile.get("drying_temperature"),
            profile.get("drying_time"), profile.get("notes", ""),
            profile.get("active", 1),
        ))
        profile_id = cur.lastrowid

        for variant in profile.get("variants", []):
            rgb = variant.get("rgb")
            cur.execute("""
                INSERT INTO filament_variants(
                    filament_id, sku, color_name, hex_color,
                    rgb_r, rgb_g, rgb_b, finish, diameter_mm, weight_g,
                    dry_temp, dry_hours, recommended_use, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile_id, variant.get("sku"), variant.get("color_name"),
                variant.get("hex"),
                rgb[0] if rgb and len(rgb) >= 3 else None,
                rgb[1] if rgb and len(rgb) >= 3 else None,
                rgb[2] if rgb and len(rgb) >= 3 else None,
                variant.get("finish"), variant.get("diameter_mm", 1.75),
                variant.get("weight_g", 1000), variant.get("dry_temp"),
                variant.get("dry_hours"), variant.get("recommended_use"),
                variant.get("notes"), variant.get("status", "Active"),
            ))

    count = 0
    for file in sorted(DATA_DIR.glob("*.yaml")):
        with open(file, "r") as f:
            data = yaml.safe_load(f)

        manufacturer_name = data["manufacturer"]["name"]
        manufacturer_id = get_or_create_manufacturer(
            manufacturer_name,
            data["manufacturer"].get("country"),
            data["manufacturer"].get("website"),
        )

        line_map = {line_def["name"]: line_def for line_def in data.get("lines", []) if "name" in line_def}

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
                    profile["color"] = material_name
                if "surface_finish" not in profile:
                    profile["surface_finish"] = "Standard"

                # Gerar profile_name no formato: "Material - Fabricante - Linha"
                # Ex: "PLA - Voolt3D - Velvet", "PETG - Sunlu - High Speed"
                # Usa commercial_name sem o prefixo do material como identificador
                commercial = profile["commercial_name"]
                # Remove prefixo do material (ex: "PLA Velvet" -> "Velvet", "PETG CF" -> "CF")
                suffix = re.sub(rf"^{re.escape(material_name)}\s*", "", commercial).strip()
                if not suffix:
                    suffix = "Standard"
                profile["profile_name"] = f"{material_name} - {manufacturer_name} - {suffix}"

                insert_profile(manufacturer_id, material_id, profile, material_name)
                count += 1

    conn.commit()
    conn.close()
    info(f"Filamentos importados: {count} perfis")


# =============================================================================
# STEP 3: SEED PROCESSES
# =============================================================================

PROFILE_MULTIPLIERS = {
    "fast": {"speed": 1.50, "accel": 1.50},
    "economy": {"speed": 1.0, "accel": 1.0},
    "standard": {"speed": 1.0, "accel": 1.0},
    "strong": {"speed": 0.85, "accel": 0.80},
    "detail": {"speed": 0.80, "accel": 0.75, "quality_speed": 0.45},
    "safe": {"speed": 0.70, "accel": 0.60, "quality_speed": 0.50},
}

# Fields where lower speed actually improves visible quality or print reliability.
# These use 'quality_speed' multiplier when available (Detail/Safe).
# All other speed fields use the regular 'speed' multiplier.
QUALITY_SPEED_FIELDS = {
    "outer_wall_speed", "top_surface_speed", "initial_layer_speed",
}

# Nozzle diameter and default line width (kept for reference)
NOZZLE_DIAMETER = 0.4
DEFAULT_LINE_WIDTH = 0.45  # Typical line width for 0.4mm nozzle

# NOTE: Volumetric flow limiting is handled by the slicer at runtime via
# filament_max_volumetric_speed in each filament profile. Process profiles
# define target speeds for the printer/profile_type combination.

SPEED_FIELDS = [
    "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed", "initial_layer_speed",
    "travel_speed", "support_speed", "gap_infill_speed",
]
ACCEL_FIELDS = [
    "default_acceleration", "inner_wall_acceleration",
    "outer_wall_acceleration", "top_surface_acceleration",
]

BOOL_COLUMNS = {"enable_support", "support_on_build_plate_only", "support_critical_regions_only",
                "enable_prime_tower", "flush_into_infill", "flush_into_objects", "flush_into_support",
                "seam_slope_conditional", "seam_slope_entire_loop", "seam_slope_inner_walls",
                "staggered_inner_seams", "role_based_wipe_speed", "wipe_on_loops"}
INT_COLUMNS = {
    "default_acceleration", "inner_wall_acceleration", "outer_wall_acceleration",
    "top_surface_acceleration", "wall_loops", "infill_combination",
    "top_shell_layers", "bottom_shell_layers", "support_interface_top_layers",
    "prime_tower_width", "prime_tower_brim_width", "prime_volume",
    "seam_slope_min_length", "seam_slope_start_height", "seam_slope_steps",
}
FLOAT_COLUMNS = {
    "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed", "initial_layer_speed",
    "travel_speed", "support_speed", "gap_infill_speed",
    "top_shell_thickness", "bottom_shell_thickness", "support_top_z_distance",
    "support_interface_spacing", "support_object_xy_distance", "brim_width", "brim_object_gap",
    "flush_multiplier", "ironing_speed", "ironing_flow", "ironing_spacing",
}


def generate_process_profile(profile_type, layer_height, material_name):
    """Gera um perfil de processo combinando base + layer_height + profile_type + material.

    As velocidades são definidas com base nas capacidades da impressora (K2) e do
    profile_type. O limite volumétrico real é aplicado pelo Creality Print em runtime,
    baseado no filament_max_volumetric_speed do perfil de filamento selecionado.
    """
    base = load_json(PROCESS_BASE_DIR / "base.json")
    layer_data = load_json(PROCESS_BASE_DIR / "layer_heights" / f"{layer_height}.json")
    type_data = load_json(PROCESS_BASE_DIR / "profile_types" / f"{profile_type}.json")
    material_data = load_json(PROCESS_BASE_DIR / "materials" / f"{material_name}.json")

    # Merge: base < layer_height < profile_type
    profile = {**base, **layer_data, **type_data}

    # Layer height overrides for adhesion-critical fields (brim, initial_layer_print_height)
    # take precedence over profile_type — thinner layers need more adhesion help regardless
    # of profile_type settings.
    ADHESION_OVERRIDE_FIELDS = {"brim_width", "brim_object_gap", "initial_layer_print_height"}
    for field in ADHESION_OVERRIDE_FIELDS:
        if field in layer_data:
            # Only override if layer_height value provides better adhesion (wider brim, thicker first layer)
            layer_val = float(layer_data[field])
            profile_val = float(profile.get(field, 0))
            if field == "brim_object_gap":
                # Smaller gap = better adhesion, so layer overrides if smaller
                if layer_val < profile_val:
                    profile[field] = layer_data[field]
            else:
                # Larger value = better adhesion (wider brim, thicker first layer)
                if layer_val > profile_val:
                    profile[field] = layer_data[field]

    # Apply material speeds with profile_type multipliers
    mult = PROFILE_MULTIPLIERS.get(profile_type, {"speed": 1.0, "accel": 1.0})
    material_mult = material_data.get("speed_multiplier", 1.0)
    material_accel_mult = material_data.get("acceleration_multiplier", 1.0)

    for field in SPEED_FIELDS:
        if field in material_data:
            # Use quality_speed multiplier for fields that affect visible quality
            if field in QUALITY_SPEED_FIELDS and "quality_speed" in mult:
                speed_mult = mult["quality_speed"]
            else:
                speed_mult = mult["speed"]
            raw_speed = float(material_data[field]) * speed_mult * material_mult
            # Cap at machine maximum (800 mm/s for travel, 600 mm/s for extrusion)
            # K2 spec: 600 mm/s max print speed, 800 mm/s travel
            if field == "travel_speed":
                raw_speed = min(raw_speed, 800.0)
            else:
                raw_speed = min(raw_speed, 600.0)
            # Layer height can define a speed cap (e.g. lower initial_layer_speed
            # for thin layers to improve bed adhesion)
            if field in layer_data:
                layer_cap = float(layer_data[field])
                raw_speed = min(raw_speed, layer_cap)
            profile[field] = str(raw_speed)

    for field in ACCEL_FIELDS:
        if field in material_data:
            raw_accel = float(material_data[field]) * mult["accel"] * material_accel_mult
            # Cap acceleration at machine maximum (20000 mm/s²)
            profile[field] = str(min(raw_accel, 20000.0))

    nozzle = "0.4"
    profile["name"] = f"{layer_height}mm {profile_type.capitalize()} @Creality K2 {nozzle} nozzle - {material_name}"
    profile["print_settings_id"] = profile["name"]

    # Creality Print built-in profiles for K2 0.4 nozzle only go up to 0.28mm.
    # For layer heights above 0.28, inherit from the highest available built-in.
    MAX_BUILTIN_LAYER_HEIGHT = "0.28"
    inherits_height = layer_height if float(layer_height) <= float(MAX_BUILTIN_LAYER_HEIGHT) else MAX_BUILTIN_LAYER_HEIGHT
    profile["inherits"] = f"{inherits_height}mm Standard @Creality K2 {nozzle} nozzle"

    return profile


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


def seed_processes():
    """Gera perfis de processo via herança e insere no banco."""
    info("Gerando perfis de processo via herança...")

    combinations = load_json(PROCESS_BASE_DIR / "combinations.json")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Garantir que os materiais de processo existam
    process_materials = [
        ("PLA", "Polylactic Acid", 220, 60),
        ("PETG", "Polyethylene Terephthalate Glycol", 230, 75),
        ("TPU", "Thermoplastic Polyurethane", 220, 50),
        ("ABS", "Acrylonitrile Butadiene Styrene", 250, 100),
        ("PLA-CF", "PLA com fibra de carbono", 220, 60),
        ("PETG-CF", "PETG com fibra de carbono", 230, 75),
    ]
    for name, desc, nozzle_temp, bed_temp in process_materials:
        cur.execute("SELECT id FROM materials WHERE name = ?", (name,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO materials(name, description, average_cost, difficulty, strength,
                    flexibility, temperature_resistance, uv_resistance, food_safe,
                    indoor, outdoor, abrasive, requires_enclosure,
                    recommended_nozzle_temp, recommended_bed_temp)
                VALUES (?, ?, 50, 50, 50, 50, 50, 50, 0, 1, 0, 0, 0, ?, ?)
            """, (name, desc, nozzle_temp, bed_temp))

    conn.commit()

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
        "support_xy_overrides_z", "support_critical_regions_only",
        "brim_width", "brim_object_gap", "ironing_type", "ironing_speed",
        "ironing_flow", "ironing_spacing", "seam_position",
        "seam_gap", "seam_slope_type", "seam_slope_conditional", "seam_slope_entire_loop",
        "seam_slope_inner_walls", "seam_slope_min_length", "seam_slope_start_height", "seam_slope_steps",
        "staggered_inner_seams", "role_based_wipe_speed", "wipe_on_loops",
        "enable_prime_tower", "prime_tower_width", "prime_tower_brim_width", "prime_volume",
        "flush_into_infill", "flush_into_objects", "flush_into_support", "flush_multiplier",
        "printer_model", "nozzle_size", "base_id", "inherits", "version",
        "description", "notes", "active",
    ]

    # JSON field name -> DB column name mapping
    json_to_col = {"initial_layer_print_height": "initial_layer_height"}

    inserted = 0
    for combo in combinations["combinations"]:
        profile_type = combo["profile_type"]
        for layer_height in combo["layer_heights"]:
            for material in combo["materials"]:
                profile_data = generate_process_profile(profile_type, layer_height, material)

                cur.execute("SELECT id FROM materials WHERE name = ?", (material,))
                material_row = cur.fetchone()
                if not material_row:
                    warn(f"Material {material} nao encontrado, pulando")
                    continue

                row = {
                    "material_id": material_row[0],
                    "profile_name": profile_data["name"],
                    "profile_type": profile_type,
                    "layer_height": float(layer_height),
                    "printer_model": "Creality K2 Combo",
                    "nozzle_size": 0.4,
                    "base_id": profile_data.get("base_id", "GP004"),
                    "inherits": profile_data.get("inherits"),
                    "version": profile_data.get("version", "26.4.28.18"),
                    "description": f"Perfil {profile_type} para {material} - K2 0.4mm",
                    "notes": f"Gerado via heranca: {profile_type}/{layer_height}/{material}",
                    "active": 1,
                }

                # Map all other fields
                for json_key, value in profile_data.items():
                    col = json_to_col.get(json_key, json_key)
                    if col in row:
                        continue
                    if col in set(columns):
                        coerced = coerce_value(col, value)
                        if coerced is not None:
                            row[col] = coerced

                values = [row.get(col) for col in columns]
                placeholders = ", ".join(["?"] * len(columns))
                cur.execute(
                    f"INSERT INTO process_profiles({', '.join(columns)}) VALUES ({placeholders})",
                    values,
                )
                inserted += 1

    conn.commit()
    conn.close()
    info(f"Perfis de processo gerados: {inserted}")


# =============================================================================
# STEP 4: EXPORT FILAMENTS (Creality Print format)
# =============================================================================

NOZZLE_BASE = "Hyper PLA @Creality K2 0.4 nozzle"

# Fabricantes habilitados para exportação Creality Print
# Pode ser sobrescrito via variável de ambiente EXPORT_MANUFACTURERS_OVERRIDE
_mfr_override = os.environ.get("EXPORT_MANUFACTURERS_OVERRIDE", "")
if _mfr_override == "__ALL__":
    EXPORT_MANUFACTURERS = None  # None = exporta todos
elif _mfr_override:
    EXPORT_MANUFACTURERS = set(m.strip() for m in _mfr_override.split(","))
else:
    EXPORT_MANUFACTURERS = {"Voolt3D", "Creality", "Sunlu"}


def export_filaments():
    """Exporta perfis de filamento do banco para Creality-Print/filaments/."""
    info("Exportando filamentos para Creality-Print/filaments/...")

    # Limpa diretório para evitar arquivos órfãos de builds anteriores
    if EXPORT_FILAMENTS_DIR.exists():
        for f in EXPORT_FILAMENTS_DIR.iterdir():
            f.unlink()
    EXPORT_FILAMENTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            mf.name as brand, m.name as material, fp.profile_name,
            fp.nozzle_temp_initial, fp.nozzle_temp_min, fp.nozzle_temp_max,
            fp.bed_temp, fp.flow_ratio, fp.max_volumetric_speed, fp.inherits
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials m ON m.id = fp.material_id
        WHERE fp.active = 1
    """)
    rows = cur.fetchall()
    conn.close()

    exported = 0
    for row in rows:
        brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs, inherits = row

        # Filtrar apenas fabricantes habilitados (None = todos)
        if EXPORT_MANUFACTURERS is not None and brand not in EXPORT_MANUFACTURERS:
            continue

        payload = {
            "base_id": "GFSA04",
            "filament_flow_ratio": [str(flow)],
            "filament_max_volumetric_speed": [str(mvs)],
            "filament_settings_id": [profile_name],
            "filament_vendor": [brand],
            "filament_type": [material],
            "filament_density": ["1.24"],
            "filament_diameter": ["1.75"],
            "from": "User",
            "hot_plate_temp": [str(bed)],
            "hot_plate_temp_initial_layer": [str(int(bed) + 5)],
            "inherits": inherits or NOZZLE_BASE,
            "is_custom_defined": "0",
            "name": profile_name,
            "nozzle_temperature": [str(n_init)],
            "nozzle_temperature_initial_layer": [str(n_init)],
            "nozzle_temperature_range_low": [str(n_min)],
            "nozzle_temperature_range_high": [str(n_max)],
            "textured_plate_temp": [str(bed)],
            "textured_plate_temp_initial_layer": [str(int(bed) + 5)],
            "version": "26.4.28.18",
        }

        file_base = profile_name
        json_path = EXPORT_FILAMENTS_DIR / f"{file_base}.json"
        info_path = EXPORT_FILAMENTS_DIR / f"{file_base}.info"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)

        now = int(time.time())
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(f"sync_info = update\nuser_id = 8401264742\nsetting_id = {now}\nbase_id = GFSA04\nupdated_time = {now}\n")

        exported += 1

    filter_desc = "todos" if EXPORT_MANUFACTURERS is None else ', '.join(sorted(EXPORT_MANUFACTURERS))
    info(f"Exportados: {exported} perfis de filamento (de {len(rows)} no banco, filtro: {filter_desc})")


# =============================================================================
# STEP 5: EXPORT PROCESSES (Creality Print format)
# =============================================================================

def export_processes():
    """Exporta perfis de processo do banco para Creality-Print/process/."""
    info("Exportando processos para Creality-Print/process/...")

    # Limpa diretório para evitar arquivos órfãos de builds anteriores
    if EXPORT_PROCESS_DIR.exists():
        for f in EXPORT_PROCESS_DIR.iterdir():
            f.unlink()
    EXPORT_PROCESS_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            pp.profile_name, pp.profile_type, pp.layer_height, pp.initial_layer_height,
            pp.inner_wall_speed, pp.outer_wall_speed, pp.sparse_infill_speed,
            pp.internal_solid_infill_speed, pp.top_surface_speed, pp.initial_layer_speed,
            pp.travel_speed, pp.support_speed, pp.gap_infill_speed,
            pp.default_acceleration, pp.inner_wall_acceleration,
            pp.outer_wall_acceleration, pp.top_surface_acceleration,
            pp.wall_loops, pp.wall_generator, pp.wall_sequence,
            pp.sparse_infill_density, pp.sparse_infill_pattern,
            pp.internal_solid_infill_pattern, pp.infill_combination,
            pp.top_surface_pattern, pp.bottom_surface_pattern,
            pp.top_shell_layers, pp.bottom_shell_layers,
            pp.top_shell_thickness, pp.bottom_shell_thickness,
            pp.enable_support, pp.support_type, pp.support_on_build_plate_only,
            pp.support_top_z_distance, pp.support_interface_spacing,
            pp.support_interface_top_layers, pp.support_object_xy_distance,
            pp.support_xy_overrides_z, pp.support_critical_regions_only,
            pp.brim_width, pp.brim_object_gap,
            pp.ironing_type, pp.ironing_speed, pp.ironing_flow, pp.ironing_spacing,
            pp.seam_position, pp.seam_gap, pp.seam_slope_type,
            pp.seam_slope_conditional, pp.seam_slope_entire_loop,
            pp.seam_slope_inner_walls, pp.seam_slope_min_length,
            pp.seam_slope_start_height, pp.seam_slope_steps,
            pp.staggered_inner_seams, pp.role_based_wipe_speed, pp.wipe_on_loops,
            pp.enable_prime_tower, pp.prime_tower_width, pp.prime_tower_brim_width,
            pp.prime_volume,
            pp.flush_into_infill, pp.flush_into_objects, pp.flush_into_support,
            pp.flush_multiplier,
            pp.printer_model, pp.base_id, pp.inherits, pp.version,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE pp.active = 1
    """)
    rows = cur.fetchall()
    conn.close()

    for row in rows:
        profile_name = row[0]

        data = {
            "base_id": row[66] if row[66] else "GP004",
            "from": "User",
            "inherits": row[67] if row[67] else "0.20mm Standard @Creality K2 0.4 nozzle",
            "is_custom_defined": "0",
            "name": profile_name,
            "print_settings_id": profile_name,
            "version": row[68] if row[68] else "26.4.28.18",
        }

        # Map indexed fields
        field_map = [
            (2, "layer_height"),
            (3, "initial_layer_print_height"), (4, "inner_wall_speed"),
            (5, "outer_wall_speed"), (6, "sparse_infill_speed"),
            (7, "internal_solid_infill_speed"), (8, "top_surface_speed"),
            (9, "initial_layer_speed"), (10, "travel_speed"),
            (11, "support_speed"), (12, "gap_infill_speed"),
            (13, "default_acceleration"), (14, "inner_wall_acceleration"),
            (15, "outer_wall_acceleration"), (16, "top_surface_acceleration"),
            (17, "wall_loops"), (18, "wall_generator"), (19, "wall_sequence"),
            (20, "sparse_infill_density"), (21, "sparse_infill_pattern"),
            (22, "internal_solid_infill_pattern"), (23, "infill_combination"),
            (24, "top_surface_pattern"), (25, "bottom_surface_pattern"),
            (26, "top_shell_layers"), (27, "bottom_shell_layers"),
            (28, "top_shell_thickness"), (29, "bottom_shell_thickness"),
            (30, "enable_support"), (31, "support_type"),
            (32, "support_on_build_plate_only"), (33, "support_top_z_distance"),
            (34, "support_interface_spacing"), (35, "support_interface_top_layers"),
            (36, "support_object_xy_distance"), (37, "support_xy_overrides_z"),
            (38, "support_critical_regions_only"),
            (39, "brim_width"), (40, "brim_object_gap"),
            (41, "ironing_type"), (42, "ironing_speed"),
            (43, "ironing_flow"), (44, "ironing_spacing"),
            (45, "seam_position"), (46, "seam_gap"), (47, "seam_slope_type"),
            (48, "seam_slope_conditional"), (49, "seam_slope_entire_loop"),
            (50, "seam_slope_inner_walls"), (51, "seam_slope_min_length"),
            (52, "seam_slope_start_height"), (53, "seam_slope_steps"),
            (54, "staggered_inner_seams"), (55, "role_based_wipe_speed"),
            (56, "wipe_on_loops"),
            (57, "enable_prime_tower"), (58, "prime_tower_width"),
            (59, "prime_tower_brim_width"), (60, "prime_volume"),
            (61, "flush_into_infill"), (62, "flush_into_objects"),
            (63, "flush_into_support"), (64, "flush_multiplier"),
        ]

        for idx, key in field_map:
            if row[idx] is not None:
                val = row[idx]
                # Round speed/float values for clean output
                if isinstance(val, float):
                    # Round to 1 decimal for speeds, 2 for small values
                    if val > 10:
                        val = round(val, 1)
                    else:
                        val = round(val, 2)
                data[key] = str(val)

        file_base = profile_name
        json_path = EXPORT_PROCESS_DIR / f"{file_base}.json"
        info_path = EXPORT_PROCESS_DIR / f"{file_base}.info"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        now = int(time.time())
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(f"sync_info = \nuser_id = 8401264742\nsetting_id = {now}\nbase_id = {data.get('base_id', 'GP004')}\nupdated_time = {now}\n")

    info(f"Exportados: {len(rows)} perfis de processo")


# =============================================================================
# STEP 6: EXPORT FILAMENTS (Orca Slicer format)
# =============================================================================

# Mapping material -> Orca base filament profile to inherit from
ORCA_FILAMENT_INHERITS = {
    "PLA": "fdm_filament_pla",
    "PETG": "fdm_filament_petg",
    "ABS": "fdm_filament_abs",
    "ASA": "fdm_filament_asa",
    "TPU": "fdm_filament_tpu",
    "PLA-CF": "fdm_filament_pla",
    "PETG-CF": "fdm_filament_petg",
    "SUPPORT": "fdm_filament_pla",
}

# Mapping material -> filament_type field for Orca
ORCA_FILAMENT_TYPE = {
    "PLA": "PLA",
    "PETG": "PETG",
    "ABS": "ABS",
    "ASA": "ASA",
    "TPU": "TPU",
    "PLA-CF": "PLA-CF",
    "PETG-CF": "PETG-CF",
    "SUPPORT": "Support",
}


def export_orca_filaments():
    """Exporta perfis de filamento do banco para OrcaSlicer/filament/."""
    info("Exportando filamentos para OrcaSlicer/filament/...")

    if EXPORT_ORCA_FILAMENTS_DIR.exists():
        for f in EXPORT_ORCA_FILAMENTS_DIR.iterdir():
            f.unlink()
    EXPORT_ORCA_FILAMENTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            mf.name as brand, m.name as material, fp.profile_name,
            fp.nozzle_temp_initial, fp.nozzle_temp_min, fp.nozzle_temp_max,
            fp.bed_temp, fp.flow_ratio, fp.max_volumetric_speed
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials m ON m.id = fp.material_id
        WHERE fp.active = 1
    """)
    rows = cur.fetchall()
    conn.close()

    exported = 0
    for row in rows:
        brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs = row

        if EXPORT_MANUFACTURERS is not None and brand not in EXPORT_MANUFACTURERS:
            continue

        # Orca profile name includes @K2 suffix for printer compatibility
        orca_name = f"{profile_name} @K2"
        inherits = ORCA_FILAMENT_INHERITS.get(material, "fdm_filament_pla")
        filament_type = ORCA_FILAMENT_TYPE.get(material, "PLA")

        bed_temp = int(bed) if bed else 60

        payload = {
            "type": "filament",
            "name": orca_name,
            "inherits": inherits,
            "from": "User",
            "instantiation": "true",
            "filament_flow_ratio": [str(flow or 1.0)],
            "filament_max_volumetric_speed": [str(int(mvs)) if mvs else "14"],
            "filament_type": [filament_type],
            "filament_vendor": [brand],
            "nozzle_temperature": [str(n_init)],
            "nozzle_temperature_initial_layer": [str(n_init)],
            "nozzle_temperature_range_low": [str(n_min)],
            "nozzle_temperature_range_high": [str(n_max)],
            "hot_plate_temp": [str(bed_temp)],
            "hot_plate_temp_initial_layer": [str(bed_temp + 5)],
            "textured_plate_temp": [str(bed_temp)],
            "textured_plate_temp_initial_layer": [str(bed_temp + 5)],
            "cool_plate_temp": [str(bed_temp)],
            "cool_plate_temp_initial_layer": [str(bed_temp + 5)],
            "compatible_printers": [
                "Creality K2 0.4 nozzle",
            ],
        }

        json_path = EXPORT_ORCA_FILAMENTS_DIR / f"{orca_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)

        exported += 1

    filter_desc = "todos" if EXPORT_MANUFACTURERS is None else ', '.join(sorted(EXPORT_MANUFACTURERS))
    info(f"Exportados: {exported} perfis de filamento Orca (filtro: {filter_desc})")


# =============================================================================
# STEP 7: EXPORT PROCESSES (Orca Slicer format)
# =============================================================================

# Orca process profiles inherit from the built-in K2 Standard profile
ORCA_PROCESS_BASE = "0.20mm Standard @Creality K2 0.4 nozzle"


def export_orca_processes():
    """Exporta perfis de processo para OrcaSlicer/process/.

    Os perfis herdam do built-in do Orca e sobrescrevem apenas os campos
    que personalizamos (velocidades, acelerações, estrutura).
    """
    info("Exportando processos para OrcaSlicer/process/...")

    if EXPORT_ORCA_PROCESS_DIR.exists():
        for f in EXPORT_ORCA_PROCESS_DIR.iterdir():
            f.unlink()
    EXPORT_ORCA_PROCESS_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            pp.profile_name, pp.profile_type, pp.layer_height, pp.initial_layer_height,
            pp.inner_wall_speed, pp.outer_wall_speed, pp.sparse_infill_speed,
            pp.internal_solid_infill_speed, pp.top_surface_speed, pp.initial_layer_speed,
            pp.travel_speed, pp.support_speed, pp.gap_infill_speed,
            pp.default_acceleration, pp.inner_wall_acceleration,
            pp.outer_wall_acceleration, pp.top_surface_acceleration,
            pp.wall_loops, pp.wall_sequence,
            pp.sparse_infill_density, pp.sparse_infill_pattern,
            pp.top_shell_layers, pp.bottom_shell_layers,
            pp.seam_position, pp.seam_gap, pp.seam_slope_type,
            pp.seam_slope_conditional, pp.seam_slope_entire_loop,
            pp.seam_slope_inner_walls, pp.seam_slope_min_length,
            pp.seam_slope_start_height, pp.seam_slope_steps,
            pp.staggered_inner_seams,
            pp.ironing_type, pp.ironing_speed, pp.ironing_flow, pp.ironing_spacing,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE pp.active = 1
    """)
    rows = cur.fetchall()
    conn.close()

    for row in rows:
        (profile_name, profile_type, layer_height, initial_layer_height,
         inner_wall, outer_wall, sparse_infill, solid_infill, top_surface,
         initial_layer, travel, support, gap_infill,
         default_accel, inner_accel, outer_accel, top_accel,
         wall_loops, wall_sequence, infill_density, infill_pattern,
         top_shell, bottom_shell, seam_position, seam_gap, seam_slope_type,
         seam_slope_conditional, seam_slope_entire_loop,
         seam_slope_inner_walls, seam_slope_min_length,
         seam_slope_start_height, seam_slope_steps,
         staggered_inner_seams,
         ironing_type, ironing_speed, ironing_flow, ironing_spacing,
         material_name) = row

        # Orca profile name (same as Creality Print)
        orca_name = profile_name

        # Determine which built-in to inherit from based on layer height
        lh = float(layer_height) if layer_height else 0.2
        if lh <= 0.10:
            orca_inherits = "0.08mm SuperDetail @Creality K2 0.4 nozzle"
        elif lh <= 0.14:
            orca_inherits = "0.12mm Detail @Creality K2 0.4 nozzle"
        elif lh <= 0.18:
            orca_inherits = "0.16mm Optimal @Creality K2 0.4 nozzle"
        elif lh <= 0.22:
            orca_inherits = "0.20mm Standard @Creality K2 0.4 nozzle"
        elif lh <= 0.26:
            orca_inherits = "0.24mm Draft @Creality K2 0.4 nozzle"
        else:
            orca_inherits = "0.28mm SuperDraft @Creality K2 0.4 nozzle"

        data = {
            "type": "process",
            "name": orca_name,
            "inherits": orca_inherits,
            "from": "User",
            "instantiation": "true",
            "compatible_printers": ["Creality K2 0.4 nozzle"],
        }

        # Only set fields we override (Orca inherits the rest from base)
        def set_val(key, val, as_int=False):
            if val is not None:
                if as_int:
                    data[key] = str(int(float(val)))
                elif isinstance(val, float):
                    data[key] = str(int(val)) if val == int(val) else str(round(val, 1))
                else:
                    data[key] = str(val)

        set_val("layer_height", layer_height)
        set_val("inner_wall_speed", inner_wall, as_int=True)
        set_val("outer_wall_speed", outer_wall, as_int=True)
        set_val("sparse_infill_speed", sparse_infill, as_int=True)
        set_val("internal_solid_infill_speed", solid_infill, as_int=True)
        set_val("top_surface_speed", top_surface, as_int=True)
        set_val("initial_layer_speed", initial_layer, as_int=True)
        set_val("travel_speed", travel, as_int=True)
        set_val("support_speed", support, as_int=True)
        set_val("gap_infill_speed", gap_infill, as_int=True)
        set_val("default_acceleration", default_accel, as_int=True)
        set_val("inner_wall_acceleration", inner_accel, as_int=True)
        set_val("outer_wall_acceleration", outer_accel, as_int=True)
        set_val("top_surface_acceleration", top_accel, as_int=True)
        set_val("wall_loops", wall_loops, as_int=True)
        set_val("top_shell_layers", top_shell, as_int=True)
        set_val("bottom_shell_layers", bottom_shell, as_int=True)
        set_val("seam_position", seam_position)
        set_val("seam_gap", seam_gap)
        set_val("seam_slope_type", seam_slope_type)
        set_val("seam_slope_conditional", seam_slope_conditional, as_int=True)
        set_val("seam_slope_entire_loop", seam_slope_entire_loop, as_int=True)
        set_val("seam_slope_inner_walls", seam_slope_inner_walls, as_int=True)
        set_val("seam_slope_min_length", seam_slope_min_length, as_int=True)
        set_val("seam_slope_start_height", seam_slope_start_height, as_int=True)
        set_val("seam_slope_steps", seam_slope_steps, as_int=True)
        set_val("staggered_inner_seams", staggered_inner_seams, as_int=True)

        if ironing_type and ironing_type != "no ironing":
            data["ironing_type"] = str(ironing_type)
            set_val("ironing_speed", ironing_speed)
            set_val("ironing_flow", ironing_flow)
            set_val("ironing_spacing", ironing_spacing)

        if infill_density:
            # Orca uses "15" not "15%"
            data["sparse_infill_density"] = str(infill_density).replace("%", "")

        if infill_pattern:
            data["sparse_infill_pattern"] = str(infill_pattern)

        json_path = EXPORT_ORCA_PROCESS_DIR / f"{orca_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    info(f"Exportados: {len(rows)} perfis de processo Orca")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FilamentDB — Build Pipeline")
    parser.add_argument("--only-db", action="store_true", help="Apenas cria banco (sem export)")
    parser.add_argument("--only-export", action="store_true", help="Apenas exporta (banco ja existe)")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  FilamentDB — Build Pipeline")
    print("=" * 60)
    print()

    if args.only_export:
        export_filaments()
        export_processes()
        export_orca_filaments()
        export_orca_processes()
    elif args.only_db:
        create_schema()
        seed_filaments()
        seed_processes()
    else:
        create_schema()
        seed_filaments()
        seed_processes()
        export_filaments()
        export_processes()
        export_orca_filaments()
        export_orca_processes()

    print()
    info("Build concluido com sucesso!")
    print()


if __name__ == "__main__":
    main()
