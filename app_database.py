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
