"""
services.py — Lógica de negócio: geração de payloads Creality Print e ZIPs para download.
"""

import io
import json
import time
import zipfile

from src import database

NOZZLE_BASE = "Hyper PLA @Creality K2 0.4 nozzle"


# =============================================================================
# FILAMENT PROFILE PAYLOAD (formato Creality Print)
# =============================================================================

def build_creality_filament_payload(row):
    """Gera o JSON de um perfil de filamento no formato Creality Print.
    
    row: tupla (brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs, inherits)
    """
    brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs, inherits = row
    return {
        "base_id": "GFSA04",
        "filament_flow_ratio": [str(flow)],
        "filament_max_volumetric_speed": [str(mvs)],
        "filament_settings_id": [profile_name],
        "from": "User",
        "hot_plate_temp": [str(bed)],
        "hot_plate_temp_initial_layer": [str(int(bed) + 5)],
        "inherits": inherits or NOZZLE_BASE,
        "is_custom_defined": "0",
        "name": profile_name,
        "nozzle_temperature_initial_layer": [str(n_init)],
        "nozzle_temperature_range_low": [str(n_min)],
        "nozzle_temperature_range_high": [str(n_max)],
        "textured_plate_temp": [str(bed)],
        "textured_plate_temp_initial_layer": [str(int(bed) + 5)],
        "version": "26.4.28.18",
    }


def build_creality_filament_info():
    """Gera o conteúdo do arquivo .info para um perfil de filamento."""
    now = int(time.time())
    return f"""sync_info = update
user_id = 8401264742
setting_id = {now}
base_id = GFSA04
updated_time = {now}
"""


# =============================================================================
# PROCESS PROFILE PAYLOAD (formato Creality Print)
# =============================================================================

def build_creality_process_payload(row):
    """Gera o JSON de um perfil de processo no formato Creality Print.
    
    row: resultado da query de process_profiles (sqlite3.Row ou tupla indexada)
    """
    data = {
        "base_id": row[43] if row[43] else "GP004",
        "from": "User",
        "inherits": row[44] if row[44] else "0.20mm Standard @Creality K2 0.4 nozzle",
        "is_custom_defined": "0",
        "name": row[0],
        "print_settings_id": row[0],
        "version": row[45] if row[45] else "26.4.28.18",
    }

    field_map = [
        (3, "initial_layer_print_height"),
        (4, "inner_wall_speed"),
        (5, "outer_wall_speed"),
        (6, "sparse_infill_speed"),
        (7, "internal_solid_infill_speed"),
        (8, "top_surface_speed"),
        (9, "initial_layer_speed"),
        (10, "travel_speed"),
        (11, "support_speed"),
        (12, "gap_infill_speed"),
        (13, "default_acceleration"),
        (14, "inner_wall_acceleration"),
        (15, "outer_wall_acceleration"),
        (16, "top_surface_acceleration"),
        (17, "wall_loops"),
        (18, "wall_generator"),
        (19, "wall_sequence"),
        (20, "sparse_infill_density"),
        (21, "sparse_infill_pattern"),
        (22, "internal_solid_infill_pattern"),
        (23, "infill_combination"),
        (24, "top_surface_pattern"),
        (25, "bottom_surface_pattern"),
        (26, "top_shell_layers"),
        (27, "bottom_shell_layers"),
        (28, "top_shell_thickness"),
        (29, "bottom_shell_thickness"),
        (30, "enable_support"),
        (31, "support_type"),
        (32, "support_on_build_plate_only"),
        (33, "support_top_z_distance"),
        (34, "support_interface_spacing"),
        (35, "support_interface_top_layers"),
        (36, "support_object_xy_distance"),
        (37, "support_xy_overrides_z"),
        (38, "brim_width"),
        (39, "brim_object_gap"),
        (40, "ironing_type"),
        (41, "seam_position"),
    ]

    for idx, key in field_map:
        if row[idx] is not None:
            data[key] = str(row[idx])

    return data


def build_creality_process_info(base_id="GP004"):
    """Gera o conteúdo do arquivo .info para um perfil de processo."""
    now = int(time.time())
    return f"""sync_info = 
user_id = 8401264742
setting_id = {now}
base_id = {base_id}
updated_time = {now}
"""


# =============================================================================
# ZIP BUILDERS (usados pela API para download)
# =============================================================================

def safe_filename(text):
    return text.replace(" ", "_").replace("/", "-").replace("\\", "-")


def build_creality_print_zip(manufacturer, material):
    """Gera ZIP com perfis de filamento para download via API."""
    rows = database.get_creality_print_profiles(manufacturer, material)
    if not rows:
        return None, None

    in_memory = io.BytesIO()
    with zipfile.ZipFile(in_memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            payload = build_creality_filament_payload(row)
            filename_base = safe_filename(f"{row[1]}_{row[2]}")
            zf.writestr(f"{filename_base}.json", json.dumps(payload, indent=4).encode("utf-8"))
            zf.writestr(f"{filename_base}.info", build_creality_filament_info().encode("utf-8"))

    in_memory.seek(0)
    filename = f"creality-print-{safe_filename(manufacturer)}-{safe_filename(material)}.zip"
    return in_memory, filename


def build_process_zip(material):
    """Gera ZIP com perfis de processo para download via API."""
    conn = database.get_db_connection()
    rows = conn.execute(
        """
        SELECT
            pp.profile_name,
            pp.profile_type,
            pp.layer_height,
            pp.initial_layer_height,
            pp.inner_wall_speed,
            pp.outer_wall_speed,
            pp.sparse_infill_speed,
            pp.internal_solid_infill_speed,
            pp.top_surface_speed,
            pp.initial_layer_speed,
            pp.travel_speed,
            pp.support_speed,
            pp.gap_infill_speed,
            pp.default_acceleration,
            pp.inner_wall_acceleration,
            pp.outer_wall_acceleration,
            pp.top_surface_acceleration,
            pp.wall_loops,
            pp.wall_generator,
            pp.wall_sequence,
            pp.sparse_infill_density,
            pp.sparse_infill_pattern,
            pp.internal_solid_infill_pattern,
            pp.infill_combination,
            pp.top_surface_pattern,
            pp.bottom_surface_pattern,
            pp.top_shell_layers,
            pp.bottom_shell_layers,
            pp.top_shell_thickness,
            pp.bottom_shell_thickness,
            pp.enable_support,
            pp.support_type,
            pp.support_on_build_plate_only,
            pp.support_top_z_distance,
            pp.support_interface_spacing,
            pp.support_interface_top_layers,
            pp.support_object_xy_distance,
            pp.support_xy_overrides_z,
            pp.brim_width,
            pp.brim_object_gap,
            pp.ironing_type,
            pp.seam_position,
            pp.printer_model,
            pp.base_id,
            pp.inherits,
            pp.version,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE m.name = ? AND pp.active = 1
        """,
        (material,)
    ).fetchall()
    conn.close()

    if not rows:
        return None, None

    in_memory = io.BytesIO()
    with zipfile.ZipFile(in_memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            payload = build_creality_process_payload(row)
            filename_base = safe_filename(row[0])
            zf.writestr(f"{filename_base}.json", json.dumps(payload, indent=4, ensure_ascii=False).encode("utf-8"))
            zf.writestr(f"{filename_base}.info", build_creality_process_info(payload.get("base_id", "GP004")).encode("utf-8"))

    in_memory.seek(0)
    filename = f"process-{safe_filename(material)}.zip"
    return in_memory, filename


# =============================================================================
# ORCA SLICER — FILAMENT PAYLOAD
# =============================================================================

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


def build_orca_filament_payload(row):
    """Gera o JSON de um perfil de filamento no formato Orca Slicer.

    row: tupla (brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs, inherits)
    """
    brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs, inherits = row
    orca_name = f"{profile_name} @K2"
    filament_inherits = ORCA_FILAMENT_INHERITS.get(material, "fdm_filament_pla")
    filament_type = ORCA_FILAMENT_TYPE.get(material, "PLA")
    bed_temp = int(bed) if bed else 60

    return {
        "type": "filament",
        "name": orca_name,
        "inherits": filament_inherits,
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
        "compatible_printers": ["Creality K2 0.4 nozzle"],
    }


# =============================================================================
# ORCA SLICER — PROCESS PAYLOAD
# =============================================================================

def _orca_process_inherits(layer_height):
    """Determina qual perfil built-in do Orca herdar baseado no layer height."""
    lh = float(layer_height) if layer_height else 0.2
    if lh <= 0.10:
        return "0.08mm SuperDetail @Creality K2 0.4 nozzle"
    elif lh <= 0.14:
        return "0.12mm Detail @Creality K2 0.4 nozzle"
    elif lh <= 0.18:
        return "0.16mm Optimal @Creality K2 0.4 nozzle"
    elif lh <= 0.22:
        return "0.20mm Standard @Creality K2 0.4 nozzle"
    elif lh <= 0.26:
        return "0.24mm Draft @Creality K2 0.4 nozzle"
    else:
        return "0.28mm SuperDraft @Creality K2 0.4 nozzle"


def build_orca_process_payload(row):
    """Gera o JSON de um perfil de processo no formato Orca Slicer.

    Herda do built-in do Orca e sobrescreve apenas os campos que personalizamos.
    """
    profile_name = row[0]
    layer_height = row[2]

    data = {
        "type": "process",
        "name": profile_name,
        "inherits": _orca_process_inherits(layer_height),
        "from": "User",
        "instantiation": "true",
        "compatible_printers": ["Creality K2 0.4 nozzle"],
    }

    field_map = [
        (2, "layer_height"),
        (4, "inner_wall_speed"),
        (5, "outer_wall_speed"),
        (6, "sparse_infill_speed"),
        (7, "internal_solid_infill_speed"),
        (8, "top_surface_speed"),
        (9, "initial_layer_speed"),
        (10, "travel_speed"),
        (11, "support_speed"),
        (12, "gap_infill_speed"),
        (13, "default_acceleration"),
        (14, "inner_wall_acceleration"),
        (15, "outer_wall_acceleration"),
        (16, "top_surface_acceleration"),
        (17, "wall_loops"),
        (26, "top_shell_layers"),
        (27, "bottom_shell_layers"),
        (41, "seam_position"),
    ]

    for idx, key in field_map:
        if row[idx] is not None:
            val = row[idx]
            if isinstance(val, float):
                data[key] = str(int(val)) if val == int(val) else str(round(val, 1))
            else:
                data[key] = str(val)

    # infill_density: Orca uses "15" not "15%"
    if row[20] is not None:
        data["sparse_infill_density"] = str(row[20]).replace("%", "")
    if row[21] is not None:
        data["sparse_infill_pattern"] = str(row[21])

    return data


# =============================================================================
# ORCA ZIP BUILDERS
# =============================================================================

def build_orca_filament_zip(manufacturer, material):
    """Gera ZIP com perfis de filamento no formato Orca Slicer."""
    rows = database.get_creality_print_profiles(manufacturer, material)
    if not rows:
        return None, None

    in_memory = io.BytesIO()
    with zipfile.ZipFile(in_memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            payload = build_orca_filament_payload(row)
            filename_base = safe_filename(payload["name"])
            zf.writestr(f"{filename_base}.json", json.dumps(payload, indent=4, ensure_ascii=False).encode("utf-8"))

    in_memory.seek(0)
    filename = f"orca-filament-{safe_filename(manufacturer)}-{safe_filename(material)}.zip"
    return in_memory, filename


def build_orca_process_zip(material):
    """Gera ZIP com perfis de processo no formato Orca Slicer."""
    conn = database.get_db_connection()
    rows = conn.execute(
        """
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
            pp.support_xy_overrides_z, pp.brim_width, pp.brim_object_gap,
            pp.ironing_type, pp.seam_position,
            pp.printer_model, pp.base_id, pp.inherits, pp.version,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE m.name = ? AND pp.active = 1
        """,
        (material,)
    ).fetchall()
    conn.close()

    if not rows:
        return None, None

    in_memory = io.BytesIO()
    with zipfile.ZipFile(in_memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            payload = build_orca_process_payload(row)
            filename_base = safe_filename(row[0])
            zf.writestr(f"{filename_base}.json", json.dumps(payload, indent=4, ensure_ascii=False).encode("utf-8"))

    in_memory.seek(0)
    filename = f"orca-process-{safe_filename(material)}.zip"
    return in_memory, filename
