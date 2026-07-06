import json
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("FILAMENT_DB_PATH", str(Path(__file__).resolve().parent / "filament.db"))


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_row(item):
    if "line_color_options" in item and isinstance(item["line_color_options"], str):
        try:
            item["line_color_options"] = json.loads(item["line_color_options"])
        except json.JSONDecodeError:
            item["line_color_options"] = [item["line_color_options"]]
    return item


def rows_to_dicts(rows):
    return [parse_row(dict(row)) for row in rows]


def list_manufacturers():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, name, country, website, notes FROM manufacturers ORDER BY name"
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def list_materials():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, name, description, average_cost, difficulty, strength, flexibility, temperature_resistance, uv_resistance, food_safe, indoor, outdoor, abrasive, requires_enclosure, recommended_nozzle_temp, recommended_bed_temp, notes FROM materials ORDER BY name"
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def list_filament_profiles():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            fp.id,
            fp.commercial_name,
            fp.profile_name,
            fp.printer_model,
            fp.nozzle_size,
            fp.inherits,
            fp.base_id,
            fp.creality_print_version,
            fp.nozzle_temp_initial,
            fp.nozzle_temp_min,
            fp.nozzle_temp_max,
            fp.bed_temp_initial,
            fp.bed_temp,
            fp.flow_ratio,
            fp.max_volumetric_speed,
            fp.profile_version,
            fp.confidence,
            fp.line,
            fp.line_description,
            fp.line_positioning,
            fp.line_target_use,
            fp.line_color_options,
            fp.color,
            fp.surface_finish,
            fp.recommendation,
            fp.diameter,
            fp.density,
            fp.drying_temperature,
            fp.drying_time,
            fp.notes,
            fp.active,
            m.name AS material_name,
            mf.name AS manufacturer_name
        FROM filament_profiles fp
        JOIN materials m ON m.id = fp.material_id
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        ORDER BY mf.name, m.name, fp.commercial_name
        """
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def get_filament_profile(profile_id):
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT
            fp.id,
            fp.commercial_name,
            fp.profile_name,
            fp.printer_model,
            fp.nozzle_size,
            fp.inherits,
            fp.base_id,
            fp.creality_print_version,
            fp.nozzle_temp_initial,
            fp.nozzle_temp_min,
            fp.nozzle_temp_max,
            fp.bed_temp_initial,
            fp.bed_temp,
            fp.flow_ratio,
            fp.max_volumetric_speed,
            fp.profile_version,
            fp.confidence,
            fp.line,
            fp.line_description,
            fp.line_positioning,
            fp.line_target_use,
            fp.line_color_options,
            fp.color,
            fp.surface_finish,
            fp.recommendation,
            fp.diameter,
            fp.density,
            fp.drying_temperature,
            fp.drying_time,
            fp.notes,
            fp.active,
            m.name AS material_name,
            mf.name AS manufacturer_name
        FROM filament_profiles fp
        JOIN materials m ON m.id = fp.material_id
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        WHERE fp.id = ?
        """,
        (profile_id,),
    ).fetchone()
    conn.close()
    return parse_row(dict(row)) if row else None


def list_materials_by_manufacturer(manufacturer_id):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT m.id, m.name, m.description
        FROM materials m
        JOIN filament_profiles fp ON fp.material_id = m.id
        WHERE fp.manufacturer_id = ?
        ORDER BY m.name
        """,
        (manufacturer_id,),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def get_creality_print_profiles(manufacturer, material):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            mf.name as brand,
            m.name as material,
            fp.profile_name,
            fp.nozzle_temp_initial,
            fp.nozzle_temp_min,
            fp.nozzle_temp_max,
            fp.bed_temp,
            fp.flow_ratio,
            fp.max_volumetric_speed
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials m ON m.id = fp.material_id
        WHERE LOWER(mf.name) = LOWER(?) AND LOWER(m.name) = LOWER(?)
        ORDER BY fp.profile_name
        """,
        (manufacturer, material),
    ).fetchall()
    conn.close()
    return rows


def list_creality_print_download_options():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT mf.name AS manufacturer, m.name AS material
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials m ON m.id = fp.material_id
        ORDER BY mf.name, m.name
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_process_profiles():
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            pp.id,
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
            pp.nozzle_size,
            pp.base_id,
            pp.inherits,
            pp.version,
            pp.description,
            pp.notes,
            pp.active,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        ORDER BY m.name, pp.profile_type, pp.profile_name
        """
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def get_process_profile(profile_id):
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT
            pp.id,
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
            pp.nozzle_size,
            pp.base_id,
            pp.inherits,
            pp.version,
            pp.description,
            pp.notes,
            pp.active,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE pp.id = ?
        """,
        (profile_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_process_profiles_by_material(material_id):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT
            pp.id,
            pp.profile_name,
            pp.profile_type,
            pp.description,
            pp.notes,
            pp.active,
            m.name AS material_name
        FROM process_profiles pp
        JOIN materials m ON m.id = pp.material_id
        WHERE pp.material_id = ?
        ORDER BY pp.profile_type, pp.profile_name
        """,
        (material_id,),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def insert_process_profile(process_data):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO process_profiles(
            material_id,
            profile_name,
            profile_type,
            layer_height,
            initial_layer_height,
            inner_wall_speed,
            outer_wall_speed,
            sparse_infill_speed,
            internal_solid_infill_speed,
            top_surface_speed,
            initial_layer_speed,
            travel_speed,
            support_speed,
            gap_infill_speed,
            default_acceleration,
            inner_wall_acceleration,
            outer_wall_acceleration,
            top_surface_acceleration,
            wall_loops,
            wall_generator,
            wall_sequence,
            sparse_infill_density,
            sparse_infill_pattern,
            internal_solid_infill_pattern,
            infill_combination,
            top_surface_pattern,
            bottom_surface_pattern,
            top_shell_layers,
            bottom_shell_layers,
            top_shell_thickness,
            bottom_shell_thickness,
            enable_support,
            support_type,
            support_on_build_plate_only,
            support_top_z_distance,
            support_interface_spacing,
            support_interface_top_layers,
            support_object_xy_distance,
            support_xy_overrides_z,
            brim_width,
            brim_object_gap,
            ironing_type,
            seam_position,
            printer_model,
            nozzle_size,
            base_id,
            inherits,
            version,
            description,
            notes,
            active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        process_data["material_id"],
        process_data["profile_name"],
        process_data["profile_type"],
        process_data.get("layer_height"),
        process_data.get("initial_layer_height"),
        process_data.get("inner_wall_speed"),
        process_data.get("outer_wall_speed"),
        process_data.get("sparse_infill_speed"),
        process_data.get("internal_solid_infill_speed"),
        process_data.get("top_surface_speed"),
        process_data.get("initial_layer_speed"),
        process_data.get("travel_speed"),
        process_data.get("support_speed"),
        process_data.get("gap_infill_speed"),
        process_data.get("default_acceleration"),
        process_data.get("inner_wall_acceleration"),
        process_data.get("outer_wall_acceleration"),
        process_data.get("top_surface_acceleration"),
        process_data.get("wall_loops"),
        process_data.get("wall_generator"),
        process_data.get("wall_sequence"),
        process_data.get("sparse_infill_density"),
        process_data.get("sparse_infill_pattern"),
        process_data.get("internal_solid_infill_pattern"),
        process_data.get("infill_combination"),
        process_data.get("top_surface_pattern"),
        process_data.get("bottom_surface_pattern"),
        process_data.get("top_shell_layers"),
        process_data.get("bottom_shell_layers"),
        process_data.get("top_shell_thickness"),
        process_data.get("bottom_shell_thickness"),
        process_data.get("enable_support"),
        process_data.get("support_type"),
        process_data.get("support_on_build_plate_only"),
        process_data.get("support_top_z_distance"),
        process_data.get("support_interface_spacing"),
        process_data.get("support_interface_top_layers"),
        process_data.get("support_object_xy_distance"),
        process_data.get("support_xy_overrides_z"),
        process_data.get("brim_width"),
        process_data.get("brim_object_gap"),
        process_data.get("ironing_type"),
        process_data.get("seam_position"),
        process_data.get("printer_model", "Creality K2 Combo"),
        process_data.get("nozzle_size", 0.4),
        process_data.get("base_id", "GP004"),
        process_data.get("inherits"),
        process_data.get("version", "26.4.28.18"),
        process_data.get("description"),
        process_data.get("notes"),
        process_data.get("active", 1)
    ))
    
    profile_id = cur.lastrowid
    conn.commit()
    conn.close()
    return profile_id


def build_tree():
    conn = get_db_connection()

    # ── Profiles ──────────────────────────────────────────────────────────────
    profile_rows = conn.execute(
        """
        SELECT
            mf.name              AS manufacturer,
            mf.country           AS manufacturer_country,
            mf.website           AS manufacturer_website,
            mf.notes             AS manufacturer_notes,
            m.name               AS material,
            m.description        AS material_description,
            m.average_cost       AS material_average_cost,
            m.difficulty         AS material_difficulty,
            m.strength           AS material_strength,
            m.flexibility        AS material_flexibility,
            m.temperature_resistance AS material_temperature_resistance,
            m.uv_resistance      AS material_uv_resistance,
            m.food_safe          AS material_food_safe,
            m.indoor             AS material_indoor,
            m.outdoor            AS material_outdoor,
            m.abrasive           AS material_abrasive,
            m.requires_enclosure AS material_requires_enclosure,
            m.recommended_nozzle_temp AS material_recommended_nozzle_temp,
            m.recommended_bed_temp    AS material_recommended_bed_temp,
            m.notes              AS material_notes,
            fp.id                AS profile_id,
            fp.commercial_name,
            fp.profile_name,
            fp.printer_model,
            fp.nozzle_size,
            fp.inherits,
            fp.base_id,
            fp.creality_print_version,
            fp.nozzle_temp_initial,
            fp.nozzle_temp_min,
            fp.nozzle_temp_max,
            fp.bed_temp_initial,
            fp.bed_temp,
            fp.textured_bed_initial,
            fp.textured_bed,
            fp.flow_ratio,
            fp.max_volumetric_speed,
            fp.profile_version,
            fp.confidence,
            fp.line,
            fp.line_description,
            fp.line_positioning,
            fp.line_target_use,
            fp.line_color_options,
            fp.color,
            fp.surface_finish,
            fp.recommendation,
            fp.diameter,
            fp.density,
            fp.drying_temperature,
            fp.drying_time,
            fp.notes,
            fp.active,
            fp.created_at,
            fp.updated_at
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials     m  ON m.id  = fp.material_id
        ORDER BY mf.name, m.name, fp.commercial_name, fp.profile_name
        """
    ).fetchall()

    # ── Variants (all, indexed by filament_id) ────────────────────────────────
    variant_rows = conn.execute(
        """
        SELECT id, filament_id, sku, color_name, hex_color,
               rgb_r, rgb_g, rgb_b, finish,
               diameter_mm, weight_g,
               dry_temp, dry_hours,
               recommended_use, notes, status
        FROM filament_variants
        ORDER BY filament_id, id
        """
    ).fetchall()
    conn.close()

    # Build variants index: filament_id -> list[dict]
    variants_by_profile: dict[int, list] = {}
    for vr in variant_rows:
        fid = vr["filament_id"]
        variants_by_profile.setdefault(fid, []).append({
            "id":             vr["id"],
            "sku":            vr["sku"],
            "color_name":     vr["color_name"],
            "hex_color":      vr["hex_color"],
            "rgb":            [vr["rgb_r"], vr["rgb_g"], vr["rgb_b"]]
                              if vr["rgb_r"] is not None else None,
            "finish":         vr["finish"],
            "diameter_mm":    vr["diameter_mm"],
            "weight_g":       vr["weight_g"],
            "dry_temp":       vr["dry_temp"],
            "dry_hours":      vr["dry_hours"],
            "recommended_use": vr["recommended_use"],
            "notes":          vr["notes"],
            "status":         vr["status"],
        })

    # ── Assemble tree ─────────────────────────────────────────────────────────
    tree: dict = {}
    for row in profile_rows:
        manufacturer = row["manufacturer"]
        material     = row["material"]
        profile_id   = row["profile_id"]

        tree.setdefault(manufacturer, {
            "country":  row["manufacturer_country"],
            "website":  row["manufacturer_website"],
            "notes":    row["manufacturer_notes"],
            "materials": {},
        })
        tree[manufacturer]["materials"].setdefault(material, {
            "description":              row["material_description"],
            "average_cost":             row["material_average_cost"],
            "difficulty":               row["material_difficulty"],
            "strength":                 row["material_strength"],
            "flexibility":              row["material_flexibility"],
            "temperature_resistance":   row["material_temperature_resistance"],
            "uv_resistance":            row["material_uv_resistance"],
            "food_safe":                bool(row["material_food_safe"]),
            "indoor":                   bool(row["material_indoor"]),
            "outdoor":                  bool(row["material_outdoor"]),
            "abrasive":                 bool(row["material_abrasive"]),
            "requires_enclosure":       bool(row["material_requires_enclosure"]),
            "recommended_nozzle_temp":  row["material_recommended_nozzle_temp"],
            "recommended_bed_temp":     row["material_recommended_bed_temp"],
            "notes":                    row["material_notes"],
            "profiles": [],
        })

        tree[manufacturer]["materials"][material]["profiles"].append({
            "profile_id":               profile_id,
            "commercial_name":          row["commercial_name"],
            "profile_name":             row["profile_name"],
            "printer_model":            row["printer_model"],
            "nozzle_size":              row["nozzle_size"],
            "inherits":                 row["inherits"],
            "base_id":                  row["base_id"],
            "creality_print_version":   row["creality_print_version"],
            "nozzle_temp_initial":      row["nozzle_temp_initial"],
            "nozzle_temp_min":          row["nozzle_temp_min"],
            "nozzle_temp_max":          row["nozzle_temp_max"],
            "bed_temp_initial":         row["bed_temp_initial"],
            "bed_temp":                 row["bed_temp"],
            "textured_bed_initial":     row["textured_bed_initial"],
            "textured_bed":             row["textured_bed"],
            "flow_ratio":               row["flow_ratio"],
            "max_volumetric_speed":     row["max_volumetric_speed"],
            "profile_version":          row["profile_version"],
            "confidence":               row["confidence"],
            "line":                     row["line"],
            "line_description":         row["line_description"],
            "line_positioning":         row["line_positioning"],
            "line_target_use":          row["line_target_use"],
            "line_color_options":       json.loads(row["line_color_options"])
                                        if row["line_color_options"] else [],
            "color":                    row["color"],
            "surface_finish":           row["surface_finish"],
            "recommendation":           row["recommendation"],
            "diameter":                 row["diameter"],
            "density":                  row["density"],
            "drying_temperature":       row["drying_temperature"],
            "drying_time":              row["drying_time"],
            "notes":                    row["notes"],
            "active":                   bool(row["active"]),
            "created_at":               row["created_at"],
            "updated_at":               row["updated_at"],
            "variants":                 variants_by_profile.get(profile_id, []),
            "download_url":             f"/download/creality-print/{manufacturer}/{material}",
        })

    return tree
