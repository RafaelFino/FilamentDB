import os
import sqlite3
import json
import time

DB_PATH = os.environ.get("FILAMENT_DB_PATH", "filament.db")
OUTPUT_DIR = os.environ.get("CREALITY_OUTPUT_DIR", "./creality-print")

NOZZLE_BASE = "Hyper PLA @Creality K2 0.4 nozzle"


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_connection():
    return sqlite3.connect(DB_PATH)


def fetch_all_profiles(conn):
    cur = conn.cursor()

    cur.execute("""
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
    """)

    return cur.fetchall()


def build_json(row):
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
        "version": "26.4.28.18"
    }


def safe_filename(text):
    return (
        text.replace(" ", "_")
            .replace("/", "-")
            .replace("\\", "-")
    )


def write_files(brand, material, profile_name, data):
    ensure_dirs()

    file_base = safe_filename(f"{material}_{profile_name}")

    json_path = os.path.join(OUTPUT_DIR, f"{file_base}.json")
    info_path = os.path.join(OUTPUT_DIR, f"{file_base}.info")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    now = int(time.time())

    with open(info_path, "w", encoding="utf-8") as f:
        f.write(f"""sync_info = update
user_id = 8401264742
setting_id = {now}
base_id = GFSA04
updated_time = {now}
""")


def main():
    conn = get_connection()
    rows = fetch_all_profiles(conn)

    print(f"Encontrados {len(rows)} perfis no banco")

    for row in rows:
        brand, material, profile_name = row[:3]

        data = build_json(row)
        write_files(brand, material, profile_name, data)

        print(f"Exportado: {brand} - {material} - {profile_name}")

    conn.close()


if __name__ == "__main__":
    main()