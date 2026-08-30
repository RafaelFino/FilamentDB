#!/usr/bin/env python3
"""
Enriches ./data/*.yaml with verified data from ~/git/open-filament-database (OFDB).

OFDB structure:
  data/<manufacturer>/<MATERIAL>/<filament_id>/filament.json  → density, temps, tolerance
  data/<manufacturer>/<MATERIAL>/<filament_id>/<color>/variant.json → hex, name, traits

This script:
  1. Reads every filament.json and variant.json from OFDB for relevant manufacturers
  2. Maps them to our YAML profiles using a mapping table
  3. Updates density, min/max temps, diameter_tolerance, and variant hex/traits
  4. Adds new slicer_settings block when present
  5. Writes the updated YAMLs
"""

import json
import os
import re
from pathlib import Path

import yaml

# ── paths ──────────────────────────────────────────────────────────────────────
OFDB = Path("/home/fino/git/open-filament-database/data")
YAMLDIR = Path("/home/fino/git/FilamentDB/data")

# ── manufacturer mapping: our yaml filename → OFDB folder name ─────────────────
MFR_MAP = {
    "bambu.yaml":      "bambu_lab",
    "creality.yaml":   "creality",
    "elegoo.yaml":     "elegoo",
    "sunlu.yaml":      "sunlu",
    "prusament.yaml":  "prusament",
    "fiberlogy.yaml":  "fiberlogy",
}

# ── filament mapping: (our_material, our_commercial_name) → OFDB filament_id ──
# Format: (material_key, commercial_name_lower_pattern) → (ofdb_material_folder, ofdb_filament_id)
FILAMENT_MAP = {
    # Bambu
    ("PLA",  "pla basic"):           ("PLA",  "basic"),
    ("PLA",  "pla matte"):           ("PLA",  "matte"),
    ("PLA",  "pla silk"):            ("PLA",  "silk_pla"),
    ("PLA",  "pla silk+"):           ("PLA",  "silk+"),
    ("PLA",  "pla-cf"):              ("PLA",  "pla_cf"),
    ("PLA",  "pla galaxy"):          ("PLA",  "galaxy"),
    ("PLA",  "pla marble"):          ("PLA",  "marble"),
    ("PLA",  "pla sparkle"):         ("PLA",  "sparkle"),
    ("PLA",  "pla wood"):            ("PLA",  "wood"),
    ("PLA",  "pla metal"):           ("PLA",  "metal"),
    ("PLA",  "pla translucent"):     ("PLA",  "translucent"),
    ("PLA",  "pla tough+"):          ("PLA",  "tough+"),
    ("PLA",  "pla aero"):            ("PLA",  "aero"),
    ("PETG", "petg basic"):          ("PETG", "petg_basic"),
    ("PETG", "petg hf"):             ("PETG", "hf"),
    ("PETG", "petg-cf"):             ("PETG", "petg_cf"),
    ("PETG", "petg translucent"):    ("PETG", "translucent"),
    ("TPU",  "tpu 95a hf"):          ("TPU",  "95a_hf"),
    ("TPU",  "tpu for ams"):         ("TPU",  "for_ams"),

    # Creality
    ("PLA",  "hyper pla"):           ("PLA",  "hyper_pla"),
    ("PLA",  "cr pla"):              ("PLA",  "pla"),
    ("PLA",  "ender pla"):           ("PLA",  "ender_fast_pla"),
    ("PLA",  "hyper pla-cf"):        ("PLA",  "hyper_pla_cf"),
    ("PLA",  "silk pla"):            ("PLA",  "silk_pla"),
    ("PETG", "cr petg"):             ("PETG", "petg"),
    ("PETG", "hyper petg"):          ("PETG", "hyper_petg"),
    ("ABS",  "abs"):                 ("ABS",  "abs"),
    ("ABS",  "hyper abs"):           ("ABS",  "hyper_abs"),
    ("TPU",  "tpu 95a"):             ("TPU",  "95a_tpu"),

    # Elegoo
    ("PLA",  "pla"):                 ("PLA",  "pla"),
    ("PLA",  "pla basic"):           ("PLA",  "pla_basic"),
    ("PLA",  "pla+"):                ("PLA",  "pla_plus"),
    ("PLA",  "pla pro"):             ("PLA",  "pla_pro"),
    ("PLA",  "rapid pla+"):          ("PLA",  "rapid_pla_plus"),
    ("PLA",  "pla matte"):           ("PLA",  "pla_matte"),
    ("PLA",  "pla silk"):            ("PLA",  "silk_pla"),
    ("PLA",  "pla galaxy"):          ("PLA",  "galaxy_pla"),
    ("PLA",  "pla-cf"):              ("PLA",  "pla_cf"),
    ("PETG", "petg"):                ("PETG", "petg"),
    ("PETG", "petg pro"):            ("PETG", "petg_pro"),
    ("PETG", "rapid petg"):          ("PETG", "rapid_petg"),
    ("PETG", "petg-cf"):             ("PETG", "petg_cf"),
    ("ABS",  "abs"):                 ("ABS",  "abs"),
    ("ASA",  "asa"):                 ("ASA",  "asa"),
    ("TPU",  "tpu 95a"):             ("TPU",  "tpu_95a"),
    ("TPU",  "rapid tpu 95a"):       ("TPU",  "rapid_tpu_95a"),

    # Sunlu
    ("PLA",  "pla"):                 ("PLA",  "pla"),
    ("PLA",  "pla+"):                ("PLA",  "pla+"),
    ("PLA",  "pla high speed"):      ("PLA",  "high_speed_pla"),
    ("PLA",  "pla meta"):            ("PLA",  "pla_meta"),
    ("PLA",  "pla matte"):           ("PLA",  "pla_matte"),
    ("PLA",  "pla silk"):            ("PLA",  "silk"),
    ("PETG", "petg"):                ("PETG", "petg"),
    ("PETG", "high speed petg"):     ("PETG", "high_speed_petg"),
    ("ABS",  "abs"):                 ("ABS",  "abs"),
    ("TPU",  "tpu 95a"):             ("TPU",  "tpu95a"),
    ("TPU",  "tpu"):                 ("TPU",  "tpu"),

    # Prusament
    ("PLA",  "pla"):                 ("PLA",  "pla"),
    ("PLA",  "pla recycled"):        ("PLA",  "pla_recycled"),
    ("PETG", "petg"):                ("PETG", "petg"),
    ("PETG", "petg cf"):             ("PETG", "cf_petg"),
    ("ASA",  "asa"):                 ("ASA",  "asa"),
    ("TPU",  "tpu 95a"):             ("TPU",  "tpu_95a"),

    # Fiberlogy
    ("ABS",  "abs"):                 ("ABS",  "abs"),
}

# ── color mapping: OFDB variant id → hex (already in variant.json) ────────────
# We just read them from variant.json

# ──────────────────────────────────────────────────────────────────────────────


def load_ofdb_filament(ofdb_mfr: str, material: str, filament_id: str) -> dict:
    """Load filament.json from OFDB."""
    path = OFDB / ofdb_mfr / material / filament_id / "filament.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def load_ofdb_variants(ofdb_mfr: str, material: str, filament_id: str) -> dict:
    """Load all variant.json files for a filament, returns {color_id: variant_dict}."""
    base = OFDB / ofdb_mfr / material / filament_id
    variants = {}
    if base.exists():
        for entry in base.iterdir():
            if entry.is_dir():
                vpath = entry / "variant.json"
                if vpath.exists():
                    with open(vpath) as f:
                        v = json.load(f)
                        variants[entry.name] = v
    return variants


def normalize(s: str) -> str:
    """Lowercase and strip for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_ofdb_key(material: str, commercial_name: str) -> tuple:
    """Find the best OFDB (material_folder, filament_id) for a given profile."""
    cn_norm = normalize(commercial_name)
    # exact match first
    for (mat, pat), target in FILAMENT_MAP.items():
        if mat == material and normalize(pat) == cn_norm:
            return target
    # partial match
    for (mat, pat), target in FILAMENT_MAP.items():
        if mat == material and normalize(pat) in cn_norm:
            return target
    return None, None


def apply_ofdb_to_profile(profile: dict, ofdb_data: dict, variants: dict) -> bool:
    """Mutate profile dict with OFDB data. Returns True if anything changed."""
    changed = False

    if not ofdb_data:
        return False

    # density
    if "density" in ofdb_data and "density" not in profile:
        profile["density"] = ofdb_data["density"]
        changed = True
    elif "density" in ofdb_data and profile.get("density") != ofdb_data["density"]:
        profile["density"] = ofdb_data["density"]
        changed = True

    # diameter_tolerance
    if "diameter_tolerance" in ofdb_data:
        tol = ofdb_data["diameter_tolerance"]
        tol_str = f"1.75±{tol:.2f}mm"
        if profile.get("diameter_tolerance") != tol_str:
            profile["diameter_tolerance"] = tol_str
            changed = True

    # temperatures — only update nozzle/bed if not already set from official source
    if "min_print_temperature" in ofdb_data and "max_print_temperature" in ofdb_data:
        nozzle = profile.setdefault("nozzle", {})
        old_min = nozzle.get("min")
        old_max = nozzle.get("max")
        new_min = ofdb_data["min_print_temperature"]
        new_max = ofdb_data["max_print_temperature"]
        if old_min != new_min or old_max != new_max:
            nozzle["min"] = new_min
            nozzle["max"] = new_max
            if "initial" not in nozzle:
                nozzle["initial"] = round((new_min + new_max) / 2)
            changed = True

    if "min_bed_temperature" in ofdb_data and "max_bed_temperature" in ofdb_data:
        bed = profile.setdefault("bed", {})
        old_min = bed.get("min")
        old_max = bed.get("max")
        new_min = ofdb_data["min_bed_temperature"]
        new_max = ofdb_data["max_bed_temperature"]
        if old_min != new_min or old_max != new_max:
            bed["min"] = new_min
            bed["max"] = new_max
            if "initial" not in bed:
                bed["initial"] = round((new_min + new_max) / 2)
            changed = True

    # drying
    if "max_dry_temperature" in ofdb_data and "drying_temperature" not in profile:
        profile["drying_temperature"] = ofdb_data["max_dry_temperature"]
        changed = True

    # slicer settings (add if not present)
    if "slicer_settings" in ofdb_data and "slicer_settings" not in profile:
        profile["slicer_settings"] = ofdb_data["slicer_settings"]
        changed = True

    # data sheet URL
    if "data_sheet_url" in ofdb_data and "data_sheet_url" not in profile:
        profile["data_sheet_url"] = ofdb_data["data_sheet_url"]
        changed = True

    # variants: enrich existing ones with OFDB hex if missing
    if variants and "variants" in profile:
        for var in profile["variants"]:
            color_name = var.get("color_name") or var.get("color", "")
            color_norm = normalize(color_name)
            # try to find matching OFDB variant
            best_match = None
            best_score = 0
            for vid, vdata in variants.items():
                vid_norm = normalize(vid)
                vname_norm = normalize(vdata.get("name", ""))
                # exact id match
                if vid_norm == color_norm:
                    best_match = vdata
                    best_score = 3
                    break
                # id contains color or vice versa
                elif color_norm in vid_norm or vid_norm in color_norm:
                    if 2 > best_score:
                        best_match = vdata
                        best_score = 2
                # name match
                elif vname_norm == color_norm or color_norm in vname_norm:
                    if 1 > best_score:
                        best_match = vdata
                        best_score = 1

            if best_match:
                ofdb_hex = best_match.get("color_hex", "")
                if ofdb_hex and (not var.get("hex") or var.get("hex") == ""):
                    var["hex"] = ofdb_hex
                    # also set rgb from hex
                    try:
                        h = ofdb_hex.lstrip("#")
                        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                        var["rgb"] = [r, g, b]
                    except Exception:
                        pass
                    changed = True
                # traits
                traits = best_match.get("traits", {})
                if traits.get("transparent") and not var.get("transparent"):
                    var["transparent"] = True
                    changed = True
                if traits.get("abrasive") and not var.get("abrasive"):
                    var["abrasive"] = True
                    changed = True

    return changed


def process_yaml(yaml_path: Path, ofdb_mfr: str):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    total_changes = 0

    materials = data.get("materials", {})
    for mat_key, mat_data in materials.items():
        profiles = mat_data.get("profiles", [])
        for profile in profiles:
            commercial_name = profile.get("commercial_name", "")
            ofdb_mat, ofdb_fid = find_ofdb_key(mat_key, commercial_name)

            if not ofdb_mat or not ofdb_fid:
                # Try generic match by material type
                ofdb_mat = mat_key
                ofdb_fid = mat_key.lower()

            ofdb_data = load_ofdb_filament(ofdb_mfr, ofdb_mat, ofdb_fid)
            variants = load_ofdb_variants(ofdb_mfr, ofdb_mat, ofdb_fid)

            if apply_ofdb_to_profile(profile, ofdb_data, variants):
                total_changes += 1
                print(f"  ✓ {mat_key}/{commercial_name} → {ofdb_mfr}/{ofdb_mat}/{ofdb_fid}")

    if total_changes:
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False, width=120)
        print(f"  Saved {yaml_path.name} ({total_changes} profiles updated)")
    else:
        print(f"  No changes for {yaml_path.name}")

    return total_changes


def main():
    print("=== Enriching FilamentDB YAMLs from open-filament-database ===\n")
    total = 0
    for yaml_file, ofdb_mfr in MFR_MAP.items():
        yaml_path = YAMLDIR / yaml_file
        if not yaml_path.exists():
            print(f"  SKIP {yaml_file} (not found)")
            continue
        ofdb_path = OFDB / ofdb_mfr
        if not ofdb_path.exists():
            print(f"  SKIP {yaml_file} (OFDB folder {ofdb_mfr} not found)")
            continue
        print(f"\n── {yaml_file} ← {ofdb_mfr}")
        total += process_yaml(yaml_path, ofdb_mfr)

    print(f"\n=== Done. {total} profile blocks enriched. ===")


if __name__ == "__main__":
    main()
