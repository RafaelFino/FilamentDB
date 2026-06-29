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
    rows = conn.execute(
        """
        SELECT
            mf.name AS manufacturer,
            mf.country AS manufacturer_country,
            mf.website AS manufacturer_website,
            mf.notes AS manufacturer_notes,
            m.name AS material,
            m.description AS material_description,
            m.average_cost AS material_average_cost,
            m.difficulty AS material_difficulty,
            m.strength AS material_strength,
            m.flexibility AS material_flexibility,
            m.temperature_resistance AS material_temperature_resistance,
            m.uv_resistance AS material_uv_resistance,
            m.food_safe AS material_food_safe,
            m.indoor AS material_indoor,
            m.outdoor AS material_outdoor,
            m.abrasive AS material_abrasive,
            m.requires_enclosure AS material_requires_enclosure,
            m.recommended_nozzle_temp AS material_recommended_nozzle_temp,
            m.recommended_bed_temp AS material_recommended_bed_temp,
            m.notes AS material_notes,
            fp.commercial_name AS commercial_name,
            fp.profile_name AS profile_name,
            fp.id AS profile_id,
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
            fp.active
        FROM filament_profiles fp
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        JOIN materials m ON m.id = fp.material_id
        ORDER BY mf.name, m.name, fp.commercial_name, fp.profile_name
        """
    ).fetchall()
    conn.close()

    tree = {}
    for row in rows:
        manufacturer = row[0]
        manufacturer_country = row[1]
        manufacturer_website = row[2]
        manufacturer_notes = row[3]
        material = row[4]
        material_description = row[5]
        material_average_cost = row[6]
        material_difficulty = row[7]
        material_strength = row[8]
        material_flexibility = row[9]
        material_temperature_resistance = row[10]
        material_uv_resistance = row[11]
        material_food_safe = row[12]
        material_indoor = row[13]
        material_outdoor = row[14]
        material_abrasive = row[15]
        material_requires_enclosure = row[16]
        material_recommended_nozzle_temp = row[17]
        material_recommended_bed_temp = row[18]
        material_notes = row[19]
        commercial_name = row[20]
        profile_name = row[21]
        tree.setdefault(manufacturer, {
            "country": manufacturer_country,
            "website": manufacturer_website,
            "notes": manufacturer_notes,
            "materials": {},
        })
        tree[manufacturer]["materials"].setdefault(material, {
            "description": material_description,
            "average_cost": material_average_cost,
            "difficulty": material_difficulty,
            "strength": material_strength,
            "flexibility": material_flexibility,
            "temperature_resistance": material_temperature_resistance,
            "uv_resistance": material_uv_resistance,
            "food_safe": material_food_safe,
            "indoor": material_indoor,
            "outdoor": material_outdoor,
            "abrasive": material_abrasive,
            "requires_enclosure": material_requires_enclosure,
            "recommended_nozzle_temp": material_recommended_nozzle_temp,
            "recommended_bed_temp": material_recommended_bed_temp,
            "notes": material_notes,
            "profiles": [],
        })
        tree[manufacturer]["materials"][material]["profiles"].append({
            "commercial_name": commercial_name,
            "profile_name": profile_name,
            "profile_id": row[22],
            "printer_model": row[23],
            "nozzle_size": row[24],
            "inherits": row[25],
            "base_id": row[26],
            "creality_print_version": row[27],
            "nozzle_temp_initial": row[28],
            "nozzle_temp_min": row[29],
            "nozzle_temp_max": row[30],
            "bed_temp_initial": row[31],
            "bed_temp": row[32],
            "flow_ratio": row[33],
            "max_volumetric_speed": row[34],
            "profile_version": row[35],
            "confidence": row[36],
            "line": row[37],
            "line_description": row[38],
            "line_positioning": row[39],
            "line_target_use": row[40],
            "line_color_options": json.loads(row[41]) if row[41] else [],
            "color": row[42],
            "surface_finish": row[43],
            "recommendation": row[44],
            "diameter": row[45],
            "density": row[46],
            "drying_temperature": row[47],
            "drying_time": row[48],
            "notes": row[49],
            "active": row[50],
            "download_url": f"/download/creality-print/{manufacturer}/{material}?profile={profile_name}",
        })

    return tree
