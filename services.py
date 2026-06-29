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
