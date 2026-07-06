#!/usr/bin/env python3
"""
create_db.py

Banco SQLite simples para perfis de filamentos do Creality Print.
"""

import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("FILAMENT_DB_PATH", "filament.db")

# Remove banco antigo (recriação limpa)
if Path(DB_PATH).exists():
    Path(DB_PATH).unlink()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA foreign_keys = ON;")

# ============================================================================
# FABRICANTES
# ============================================================================

cur.execute("""
CREATE TABLE manufacturers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    country TEXT,
    website TEXT,
    notes TEXT
);
""")

# ============================================================================
# MATERIAIS (BASE)
# ============================================================================

cur.execute("""
CREATE TABLE materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,

    -- escala relativa 0–100 (custo médio do material)
    average_cost INTEGER DEFAULT 50,

    -- propriedades gerais (0–100)
    difficulty INTEGER DEFAULT 50,
    strength INTEGER DEFAULT 50,
    flexibility INTEGER DEFAULT 50,
    temperature_resistance INTEGER DEFAULT 50,
    uv_resistance INTEGER DEFAULT 50,

    -- características booleanas
    food_safe INTEGER DEFAULT 0,
    indoor INTEGER DEFAULT 1,
    outdoor INTEGER DEFAULT 0,
    abrasive INTEGER DEFAULT 0,
    requires_enclosure INTEGER DEFAULT 0,

    -- temperaturas típicas (referência)
    recommended_nozzle_temp INTEGER,
    recommended_bed_temp INTEGER,

    notes TEXT
);
""")

# ============================================================================
# USOS
# ============================================================================

cur.execute("""
CREATE TABLE uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);
""")

cur.execute("""
CREATE TABLE material_uses (
    material_id INTEGER NOT NULL,
    use_id INTEGER NOT NULL,

    PRIMARY KEY (material_id, use_id),

    FOREIGN KEY(material_id) REFERENCES materials(id),
    FOREIGN KEY(use_id) REFERENCES uses(id)
);
""")

# ============================================================================
# TAGS (para classificação livre)
# ============================================================================

cur.execute("""
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);
""")

# ============================================================================
# PERFIS DE FILAMENTO (CORE DO SISTEMA)
# ============================================================================

cur.execute("""
CREATE TABLE filament_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    manufacturer_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL,

    commercial_name TEXT NOT NULL,
    profile_name TEXT NOT NULL UNIQUE,

    -- impressora (fixo por enquanto)
    printer_model TEXT DEFAULT 'Creality K2 Combo',
    nozzle_size REAL DEFAULT 0.4,

    -- Creality Print
    inherits TEXT NOT NULL,
    base_id TEXT DEFAULT 'GFSA04',
    creality_print_version TEXT DEFAULT '7.0',

    -- Temperaturas
    nozzle_temp_initial INTEGER,
    nozzle_temp_min INTEGER,
    nozzle_temp_max INTEGER,

    bed_temp_initial INTEGER,
    bed_temp INTEGER,

    textured_bed_initial INTEGER,
    textured_bed INTEGER,

    -- performance
    flow_ratio REAL DEFAULT 1.0,
    max_volumetric_speed REAL,

    -- controle de qualidade
    profile_version INTEGER DEFAULT 1,
    confidence INTEGER DEFAULT 50,
    -- linha / cor / acabamento
    line TEXT,
    line_description TEXT,
    line_positioning TEXT,
    line_target_use TEXT,
    line_color_options TEXT,
    color TEXT,
    surface_finish TEXT,
    recommendation TEXT,
    -- físico
    diameter REAL DEFAULT 1.75,
    density REAL,

    -- secagem
    drying_temperature INTEGER,
    drying_time REAL,

    notes TEXT,
    active INTEGER DEFAULT 1,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(manufacturer_id) REFERENCES manufacturers(id),
    FOREIGN KEY(material_id) REFERENCES materials(id)
);
""")

# ============================================================================
# VARIANTES DE FILAMENTO (cores / SKUs por perfil de impressão)
# ============================================================================

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
);
""")

cur.execute("""
CREATE INDEX idx_variant_filament
ON filament_variants(filament_id);
""")

# ============================================================================
# RELAÇÃO PERFIL <-> TAG
# ============================================================================

cur.execute("""
CREATE TABLE filament_tags (
    filament_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,

    PRIMARY KEY (filament_id, tag_id),

    FOREIGN KEY(filament_id) REFERENCES filament_profiles(id),
    FOREIGN KEY(tag_id) REFERENCES tags(id)
);
""")

# ============================================================================
# COMPATIBILIDADE ENTRE PERFIS
# ============================================================================

cur.execute("""
CREATE TABLE filament_compatibility (
    filament_id INTEGER NOT NULL,
    compatible_filament_id INTEGER NOT NULL,

    compatibility INTEGER DEFAULT 100,
    notes TEXT,

    PRIMARY KEY (filament_id, compatible_filament_id),

    FOREIGN KEY(filament_id) REFERENCES filament_profiles(id),
    FOREIGN KEY(compatible_filament_id) REFERENCES filament_profiles(id)
);
""")

# ============================================================================
# PERFIS DE PROCESSO (PRINT SETTINGS)
# ============================================================================

cur.execute("""
CREATE TABLE process_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    material_id INTEGER NOT NULL,

    profile_name TEXT NOT NULL UNIQUE,
    profile_type TEXT NOT NULL, -- 'fast', 'strong', 'quality'

    -- Configurações básicas
    layer_height REAL,
    initial_layer_height REAL,

    -- Velocidades
    inner_wall_speed REAL,
    outer_wall_speed REAL,
    sparse_infill_speed REAL,
    internal_solid_infill_speed REAL,
    top_surface_speed REAL,
    initial_layer_speed REAL,
    travel_speed REAL,
    support_speed REAL,
    gap_infill_speed REAL,

    -- Acelerações
    default_acceleration INTEGER,
    inner_wall_acceleration INTEGER,
    outer_wall_acceleration INTEGER,
    top_surface_acceleration INTEGER,

    -- Paredes
    wall_loops INTEGER,
    wall_generator TEXT,
    wall_sequence TEXT,

    -- Preenchimento
    sparse_infill_density TEXT,
    sparse_infill_pattern TEXT,
    internal_solid_infill_pattern TEXT,
    infill_combination INTEGER,

    -- Superfícies
    top_surface_pattern TEXT,
    bottom_surface_pattern TEXT,
    top_shell_layers INTEGER,
    bottom_shell_layers INTEGER,
    top_shell_thickness REAL,
    bottom_shell_thickness REAL,

    -- Suporte
    enable_support INTEGER,
    support_type TEXT,
    support_on_build_plate_only INTEGER,
    support_top_z_distance REAL,
    support_interface_spacing REAL,
    support_interface_top_layers INTEGER,
    support_object_xy_distance REAL,
    support_xy_overrides_z TEXT,

    -- Brim
    brim_width REAL,
    brim_object_gap REAL,

    -- Outros
    ironing_type TEXT,
    seam_position TEXT,

    -- Metadados
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
);
""")

cur.execute("""
CREATE INDEX idx_process_material
ON process_profiles(material_id);
""")

cur.execute("""
CREATE INDEX idx_process_type
ON process_profiles(profile_type);
""")

# ============================================================================
# ÍNDICES
# ============================================================================

cur.execute("""
CREATE INDEX idx_filament_material
ON filament_profiles(material_id);
""")

cur.execute("""
CREATE INDEX idx_filament_manufacturer
ON filament_profiles(manufacturer_id);
""")

# ============================================================================
# FINALIZA
# ============================================================================

conn.commit()
conn.close()

print("Banco criado com sucesso: filament.db")