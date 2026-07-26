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


# =============================================================================
# SIMULATION — Combina processo + filamento e calcula velocidades efetivas
# =============================================================================

# Line width padrão para 0.4mm nozzle
DEFAULT_LINE_WIDTH = 0.45

# Campos de velocidade que sofrem cap volumétrico (extrudam material)
EXTRUSION_SPEED_FIELDS = [
    "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed",
    "internal_solid_infill_speed", "top_surface_speed", "initial_layer_speed",
    "support_speed", "gap_infill_speed",
]


def simulate_combination(process_id, filament_id):
    """Calcula as velocidades efetivas de um processo + filamento.

    Aplica o cap volumétrico do filamento sobre as velocidades do processo,
    simulando o que o slicer faria em runtime.
    """
    conn = database.get_db_connection()

    # Buscar processo
    proc = conn.execute(
        "SELECT * FROM process_profiles WHERE id = ? AND active = 1", (process_id,)
    ).fetchone()
    if not proc:
        conn.close()
        return None

    # Buscar filamento
    fil = conn.execute(
        "SELECT * FROM filament_profiles WHERE id = ? AND active = 1", (filament_id,)
    ).fetchone()
    if not fil:
        conn.close()
        return None

    # Buscar nomes
    material = conn.execute(
        "SELECT name FROM materials WHERE id = ?", (proc["material_id"],)
    ).fetchone()
    manufacturer = conn.execute(
        "SELECT name FROM manufacturers WHERE id = ?", (fil["manufacturer_id"],)
    ).fetchone()
    fil_material = conn.execute(
        "SELECT name FROM materials WHERE id = ?", (fil["material_id"],)
    ).fetchone()
    conn.close()

    proc_dict = dict(proc)
    fil_dict = dict(fil)

    # Calcular cap volumétrico
    mvs = float(fil_dict.get("max_volumetric_speed") or 14)
    layer_height = float(proc_dict.get("layer_height") or 0.2)
    max_speed_from_mvs = mvs / (layer_height * DEFAULT_LINE_WIDTH)

    # Gerar resultado com velocidades efetivas
    effective_speeds = {}
    for field in EXTRUSION_SPEED_FIELDS:
        raw = proc_dict.get(field)
        if raw is not None:
            raw_val = float(raw)
            capped_val = min(raw_val, max_speed_from_mvs)
            is_capped = raw_val > max_speed_from_mvs
            effective_speeds[field] = {
                "target": round(raw_val, 1),
                "effective": round(capped_val, 1),
                "capped": is_capped,
            }

    # Travel não é capped pelo MVS
    travel = proc_dict.get("travel_speed")
    if travel:
        effective_speeds["travel_speed"] = {
            "target": round(float(travel), 1),
            "effective": round(float(travel), 1),
            "capped": False,
        }

    return {
        "process": {
            "id": proc_dict["id"],
            "name": proc_dict["profile_name"],
            "profile_type": proc_dict["profile_type"],
            "layer_height": layer_height,
            "material": material["name"] if material else "?",
            "wall_loops": proc_dict.get("wall_loops"),
            "sparse_infill_density": proc_dict.get("sparse_infill_density"),
            "sparse_infill_pattern": proc_dict.get("sparse_infill_pattern"),
            "top_shell_layers": proc_dict.get("top_shell_layers"),
            "bottom_shell_layers": proc_dict.get("bottom_shell_layers"),
            "wall_sequence": proc_dict.get("wall_sequence"),
            "seam_position": proc_dict.get("seam_position"),
            "default_acceleration": proc_dict.get("default_acceleration"),
            "inner_wall_acceleration": proc_dict.get("inner_wall_acceleration"),
            "outer_wall_acceleration": proc_dict.get("outer_wall_acceleration"),
            "top_surface_acceleration": proc_dict.get("top_surface_acceleration"),
        },
        "filament": {
            "id": fil_dict["id"],
            "name": fil_dict["profile_name"],
            "commercial_name": fil_dict.get("commercial_name"),
            "manufacturer": manufacturer["name"] if manufacturer else "?",
            "material": fil_material["name"] if fil_material else "?",
            "mvs": mvs,
            "nozzle_temp": fil_dict.get("nozzle_temp_initial"),
            "bed_temp": fil_dict.get("bed_temp"),
            "flow_ratio": fil_dict.get("flow_ratio"),
            "confidence": fil_dict.get("confidence", 50),
        },
        "simulation": {
            "max_speed_from_mvs": round(max_speed_from_mvs, 1),
            "layer_height": layer_height,
            "line_width": DEFAULT_LINE_WIDTH,
            "mvs": mvs,
            "speeds": effective_speeds,
        },
    }


def get_simulation_options():
    """Retorna processos e filamentos disponíveis para simulação."""
    conn = database.get_db_connection()

    processes = conn.execute("""
        SELECT pp.id, pp.profile_name, pp.profile_type, pp.layer_height, m.name as material
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE pp.active = 1
        ORDER BY m.name, pp.profile_type, pp.layer_height
    """).fetchall()

    filaments = conn.execute("""
        SELECT fp.id, fp.profile_name, fp.commercial_name, fp.max_volumetric_speed,
               mf.name as manufacturer, m.name as material
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials m ON m.id = fp.material_id
        WHERE fp.active = 1
        ORDER BY m.name, mf.name, fp.profile_name
    """).fetchall()

    conn.close()

    return {
        "processes": [dict(r) for r in processes],
        "filaments": [dict(r) for r in filaments],
    }

# =============================================================================
# ─── Ranking: All combinations scored ────────────────────────────────────────
# =============================================================================

# Profile type finish scores (same logic as frontend calcCombinationScore)
_PROFILE_TYPE_FINISH = {
    "detail": 95,
    "safe": 75,
    "standard": 65,
    "strong": 60,
    "fast": 30,
}


def _calc_score(proc_dict, fil_dict, layer_height, mvs):
    """Calculate speed, finish, confidence and overall scores for a combination."""
    max_speed_from_mvs = mvs / (layer_height * DEFAULT_LINE_WIDTH)

    # Speed score: average effective speed / 350 (reference high speed on K2)
    effective_speeds = []
    capped_count = 0
    for field in EXTRUSION_SPEED_FIELDS:
        raw = proc_dict.get(field)
        if raw is not None:
            raw_val = float(raw)
            eff = min(raw_val, max_speed_from_mvs)
            effective_speeds.append(eff)
            if raw_val > max_speed_from_mvs:
                capped_count += 1

    if effective_speeds:
        avg_effective = sum(effective_speeds) / len(effective_speeds)
        speed_score = min(100, max(0, round((avg_effective / 350) * 100)))
    else:
        avg_effective = 0
        speed_score = 0

    # Finish score: profile type + wall_sequence bonus + layer height bonus
    profile_type = proc_dict.get("profile_type", "standard")
    type_score = _PROFILE_TYPE_FINISH.get(profile_type, 50)
    wall_seq = proc_dict.get("wall_sequence") or ""
    wall_seq_bonus = 10 if "outer" in wall_seq else 0
    lh_bonus = round((0.20 - layer_height) * 100)
    finish_score = min(100, max(0, type_score + wall_seq_bonus + lh_bonus))

    # Confidence: from filament profile
    confidence = int(fil_dict.get("confidence") or 50)

    # Overall: weighted average
    overall = round(speed_score * 0.35 + finish_score * 0.40 + confidence * 0.25)

    return {
        "speed": speed_score,
        "finish": finish_score,
        "confidence": confidence,
        "overall": overall,
        "avg_effective_speed": round(avg_effective, 1),
        "capped_count": capped_count,
        "total_speeds": len(effective_speeds),
        "max_speed_from_mvs": round(max_speed_from_mvs, 1),
    }


def get_ranking():
    """Cross all process × filament combinations (same material) and return scored ranking."""
    conn = database.get_db_connection()

    processes = conn.execute("""
        SELECT pp.*, m.name as material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE pp.active = 1
        ORDER BY pp.layer_height, pp.profile_type
    """).fetchall()

    filaments = conn.execute("""
        SELECT fp.*, m.name as material_name, mf.name as manufacturer_name
        FROM filament_profiles fp
        JOIN materials m ON m.id = fp.material_id
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        WHERE fp.active = 1
        ORDER BY mf.name, fp.profile_name
    """).fetchall()

    conn.close()

    # Build lookup: material_name -> list of filaments
    fil_by_material = {}
    for f in filaments:
        fd = dict(f)
        mat = fd["material_name"]
        fil_by_material.setdefault(mat, []).append(fd)

    results = []
    for p in processes:
        pd = dict(p)
        mat = pd["material_name"]
        layer_height = float(pd.get("layer_height") or 0.2)
        profile_type = pd.get("profile_type", "standard")

        # Cross with all filaments of the same material
        for fd in fil_by_material.get(mat, []):
            mvs = float(fd.get("max_volumetric_speed") or 14)
            scores = _calc_score(pd, fd, layer_height, mvs)

            results.append({
                "process_id": pd["id"],
                "filament_id": fd["id"],
                "layer_height": layer_height,
                "profile_type": profile_type,
                "material": mat,
                "process_name": pd["profile_name"],
                "filament_name": fd.get("commercial_name") or fd["profile_name"],
                "manufacturer": fd["manufacturer_name"],
                "mvs": mvs,
                "scores": scores,
            })

    # Sort by overall descending
    results.sort(key=lambda r: r["scores"]["overall"], reverse=True)

    return results
