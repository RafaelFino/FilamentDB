import io
import json
import time
import zipfile

import app_database

NOZZLE_BASE = "Hyper PLA @Creality K2 0.4 nozzle"


def build_creality_profile_payload(row):
    brand, material, profile_name, n_init, n_min, n_max, bed, flow, mvs = row
    return {
        "base_id": "GFSA04",
        "filament_flow_ratio": [str(flow)],
        "filament_max_volumetric_speed": [str(mvs)],
        "filament_settings_id": [profile_name],
        "from": "User",
        "hot_plate_temp": [str(bed)],
        "hot_plate_temp_initial_layer": [str(int(bed) + 5)],
        "inherits": NOZZLE_BASE,
        "is_custom_defined": "0",
        "name": profile_name,
        "nozzle_temperature_initial_layer": [str(n_init)],
        "nozzle_temperature_range_low": [str(n_min)],
        "nozzle_temperature_range_high": [str(n_max)],
        "textured_plate_temp": [str(bed)],
        "textured_plate_temp_initial_layer": [str(int(bed) + 5)],
        "version": "26.4.28.18",
    }


def safe_filename(text):
    return text.replace(" ", "_").replace("/", "-").replace("\\", "-")


def build_creality_print_zip(manufacturer, material):
    rows = app_database.get_creality_print_profiles(manufacturer, material)
    if not rows:
        return None, None

    in_memory = io.BytesIO()
    with zipfile.ZipFile(in_memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            payload = build_creality_profile_payload(row)
            filename_base = safe_filename(f"{row[1]}_{row[2]}")
            json_bytes = json.dumps(payload, indent=4).encode("utf-8")
            zf.writestr(f"{filename_base}.json", json_bytes)

            now = int(time.time())
            info_content = f"""sync_info = update
user_id = 8401264742
setting_id = {now}
base_id = GFSA04
updated_time = {now}
"""
            zf.writestr(f"{filename_base}.info", info_content.encode("utf-8"))

    in_memory.seek(0)
    filename = f"creality-print-{safe_filename(manufacturer)}-{safe_filename(material)}.zip"
    return in_memory, filename


def build_process_profile_payload(row):
    data = {
        "base_id": row[47] if row[47] else "GP004",
        "from": "User",
        "inherits": row[48] if row[48] else "0.20mm Standard @Creality K2 0.4 nozzle",
        "is_custom_defined": "0",
        "name": row[0],
        "print_settings_id": row[0],
        "version": row[49] if row[49] else "26.4.28.18"
    }

    # Adicionar campos apenas se não forem None
    if row[3] is not None:  # initial_layer_height
        data["initial_layer_print_height"] = str(row[3])
    
    if row[4] is not None:  # inner_wall_speed
        data["inner_wall_speed"] = str(row[4])
    
    if row[5] is not None:  # outer_wall_speed
        data["outer_wall_speed"] = str(row[5])
    
    if row[6] is not None:  # sparse_infill_speed
        data["sparse_infill_speed"] = str(row[6])
    
    if row[7] is not None:  # internal_solid_infill_speed
        data["internal_solid_infill_speed"] = str(row[7])
    
    if row[8] is not None:  # top_surface_speed
        data["top_surface_speed"] = str(row[8])
    
    if row[9] is not None:  # initial_layer_speed
        data["initial_layer_speed"] = str(row[9])
    
    if row[10] is not None:  # travel_speed
        data["travel_speed"] = str(row[10])
    
    if row[11] is not None:  # support_speed
        data["support_speed"] = str(row[11])
    
    if row[12] is not None:  # gap_infill_speed
        data["gap_infill_speed"] = str(row[12])
    
    if row[13] is not None:  # default_acceleration
        data["default_acceleration"] = str(row[13])
    
    if row[14] is not None:  # inner_wall_acceleration
        data["inner_wall_acceleration"] = str(row[14])
    
    if row[15] is not None:  # outer_wall_acceleration
        data["outer_wall_acceleration"] = str(row[15])
    
    if row[16] is not None:  # top_surface_acceleration
        data["top_surface_acceleration"] = str(row[16])
    
    if row[17] is not None:  # wall_loops
        data["wall_loops"] = str(row[17])
    
    if row[18] is not None:  # wall_generator
        data["wall_generator"] = row[18]
    
    if row[19] is not None:  # wall_sequence
        data["wall_sequence"] = row[19]
    
    if row[20] is not None:  # sparse_infill_density
        data["sparse_infill_density"] = row[20]
    
    if row[21] is not None:  # sparse_infill_pattern
        data["sparse_infill_pattern"] = row[21]
    
    if row[22] is not None:  # internal_solid_infill_pattern
        data["internal_solid_infill_pattern"] = row[22]
    
    if row[23] is not None:  # infill_combination
        data["infill_combination"] = str(row[23])
    
    if row[24] is not None:  # top_surface_pattern
        data["top_surface_pattern"] = row[24]
    
    if row[25] is not None:  # bottom_surface_pattern
        data["bottom_surface_pattern"] = row[25]
    
    if row[26] is not None:  # top_shell_layers
        data["top_shell_layers"] = str(row[26])
    
    if row[27] is not None:  # bottom_shell_layers
        data["bottom_shell_layers"] = str(row[27])
    
    if row[28] is not None:  # top_shell_thickness
        data["top_shell_thickness"] = str(row[28])
    
    if row[29] is not None:  # bottom_shell_thickness
        data["bottom_shell_thickness"] = str(row[29])
    
    if row[30] is not None:  # enable_support
        data["enable_support"] = str(row[30])
    
    if row[31] is not None:  # support_type
        data["support_type"] = row[31]
    
    if row[32] is not None:  # support_on_build_plate_only
        data["support_on_build_plate_only"] = str(row[32])
    
    if row[33] is not None:  # support_top_z_distance
        data["support_top_z_distance"] = str(row[33])
    
    if row[34] is not None:  # support_interface_spacing
        data["support_interface_spacing"] = str(row[34])
    
    if row[35] is not None:  # support_interface_top_layers
        data["support_interface_top_layers"] = str(row[35])
    
    if row[36] is not None:  # support_object_xy_distance
        data["support_object_xy_distance"] = str(row[36])
    
    if row[37] is not None:  # support_xy_overrides_z
        data["support_xy_overrides_z"] = row[37]
    
    if row[38] is not None:  # brim_width
        data["brim_width"] = str(row[38])
    
    if row[39] is not None:  # brim_object_gap
        data["brim_object_gap"] = str(row[39])
    
    if row[40] is not None:  # ironing_type
        data["ironing_type"] = row[40]
    
    if row[41] is not None:  # seam_position
        data["seam_position"] = row[41]

    return data


def build_process_zip(material):
    conn = app_database.get_db_connection()
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
            payload = build_process_profile_payload(row)
            filename_base = safe_filename(row[0])
            json_bytes = json.dumps(payload, indent=4, ensure_ascii=False).encode("utf-8")
            zf.writestr(f"{filename_base}.json", json_bytes)

            now = int(time.time())
            info_content = f"""sync_info = 
user_id = 8401264742
setting_id = {now}
base_id = {payload.get('base_id', 'GP004')}
updated_time = {now}
"""
            zf.writestr(f"{filename_base}.info", info_content.encode("utf-8"))

    in_memory.seek(0)
    filename = f"process-{safe_filename(material)}.zip"
    return in_memory, filename
