#!/usr/bin/env python3
"""
Generate Creality Print process profile JSON files for K2 Combo 0.4 nozzle.
Run from repo root: python3 scripts/generate_process_profiles.py
"""

import json
from copy import deepcopy
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "creality-print-process"
BASE_INHERITS = "0.20mm Standard @Creality K2 0.4 nozzle"
VERSION = "26.4.28.18"
BASE_ID = "GP004"

# ── Material speed/accel scaling ─────────────────────────────────────────────
MAT = {
    "PLA": {"speed": 1.0, "accel": 1.0, "flow_cap": 32},
    "PETG": {"speed": 0.62, "accel": 0.75, "flow_cap": 18},
}


def s(speed, material):
    return round(speed * MAT[material]["speed"], 1)


def a(accel, material):
    return int(accel * MAT[material]["accel"])


def shell_layers(layer, top, bottom=None):
    bottom = bottom or top
    return {
        "top_shell_layers": str(top),
        "bottom_shell_layers": str(bottom),
        "top_shell_thickness": str(round(layer * top, 2)),
        "bottom_shell_thickness": str(round(layer * bottom, 2)),
    }


def base_profile(name, material):
    return {
        "base_id": BASE_ID,
        "from": "System",
        "inherits": BASE_INHERITS,
        "is_custom_defined": "0",
        "name": name,
        "print_settings_id": name,
        "version": VERSION,
        "wall_generator": "arachne",
        "enable_support": "1",
        "support_type": "tree(auto)",
        "support_on_build_plate_only": "1",
        "support_xy_overrides_z": "z_overrides_xy",
        "infill_combination": "0",
        "ironing_type": "no ironing",
        "seam_position": "aligned",
    }


def apply_speeds(p, material, inner, outer, infill, solid, top, init_layer, travel, support, gap):
    p.update({
        "inner_wall_speed": str(s(inner, material)),
        "outer_wall_speed": str(s(outer, material)),
        "sparse_infill_speed": str(s(infill, material)),
        "internal_solid_infill_speed": str(s(solid, material)),
        "top_surface_speed": str(s(top, material)),
        "initial_layer_speed": str(s(init_layer, material)),
        "travel_speed": str(s(travel, material)),
        "support_speed": str(s(support, material)),
        "gap_infill_speed": str(s(gap, material)),
    })


def apply_accels(p, material, default, inner, outer, top):
    p.update({
        "default_acceleration": str(a(default, material)),
        "inner_wall_acceleration": str(a(inner, material)),
        "outer_wall_acceleration": str(a(outer, material)),
        "top_surface_acceleration": str(a(top, material)),
    })


def build_draft(layer, material):
    """Protótipo descartável — mínimo material, máxima velocidade."""
    name = f"{layer:.2f}mm Draft @Creality K2 0.4 nozzle - {material}"
    p = base_profile(name, material)
    p["initial_layer_print_height"] = str(layer)
    p["wall_loops"] = "1" if material == "PLA" else "2"
    p["wall_sequence"] = "inner wall/outer wall"
    p["sparse_infill_density"] = "5%" if material == "PLA" else "8%"
    p["sparse_infill_pattern"] = "grid"
    p["internal_solid_infill_pattern"] = "monotonic"
    p["infill_combination"] = "1"
    p["top_surface_pattern"] = "monotonic"
    p["bottom_surface_pattern"] = "monotonic"
    p.update(shell_layers(layer, 2))
    apply_speeds(p, material, 320, 220, 380, 300, 200, 70, 600, 140, 100)
    apply_accels(p, material, 12000, 10000, 7000, 5000)
    p["support_top_z_distance"] = "0.28"
    p["support_interface_spacing"] = "1.0"
    p["support_interface_top_layers"] = "1"
    p["support_object_xy_distance"] = "0.5"
    p["brim_width"] = "3.0"
    p["brim_object_gap"] = "0.25"
    p["seam_position"] = "nearest"
    return p


def build_fast(layer, material):
    """Velocidade alta com resultado ainda utilizável."""
    name = f"{layer:.2f}mm Fast @Creality K2 0.4 nozzle - {material}"
    p = base_profile(name, material)
    init = max(layer, 0.24) if layer <= 0.2 else layer
    p["initial_layer_print_height"] = str(init)
    p["wall_loops"] = "2"
    p["wall_sequence"] = "inner wall/outer wall"
    p["sparse_infill_density"] = "12%"
    p["sparse_infill_pattern"] = "gyroid"
    p["internal_solid_infill_pattern"] = "monotonic"
    p["infill_combination"] = "1"
    p["top_surface_pattern"] = "monotonic"
    p["bottom_surface_pattern"] = "monotonic"
    p.update(shell_layers(layer, 3))
    if layer >= 0.28:
        apply_speeds(p, material, 300, 210, 300, 350, 220, 65, 600, 150, 120)
        apply_accels(p, material, 12000, 9000, 6000, 5000)
    else:
        apply_speeds(p, material, 400, 290, 400, 380, 280, 55, 550, 130, 90)
        apply_accels(p, material, 10000, 7000, 5000, 4000)
    p["support_top_z_distance"] = "0.25"
    p["support_interface_spacing"] = "0.8"
    p["support_interface_top_layers"] = "2"
    p["support_object_xy_distance"] = "0.4"
    p["brim_width"] = "5.0"
    p["brim_object_gap"] = "0.2"
    return p


def build_balanced(layer, material):
    """Equilíbrio real entre tempo, qualidade e resistência."""
    name = f"{layer:.2f}mm Balanced @Creality K2 0.4 nozzle - {material}"
    p = base_profile(name, material)
    p["initial_layer_print_height"] = "0.24"
    p["wall_loops"] = "3"
    p["wall_sequence"] = "outer wall/inner wall"
    p["sparse_infill_density"] = "18%" if material == "PLA" else "16%"
    p["sparse_infill_pattern"] = "cubic" if material == "PLA" else "gyroid"
    p["internal_solid_infill_pattern"] = "monotonic"
    p["infill_combination"] = "1"
    p["top_surface_pattern"] = "monotonic"
    p["bottom_surface_pattern"] = "monotonic"
    p.update(shell_layers(layer, 5, 4))
    apply_speeds(p, material, 300, 220, 320, 220, 160, 45, 500, 110, 80)
    apply_accels(p, material, 6000, 4500, 3000, 2500)
    p["support_top_z_distance"] = "0.2"
    p["support_interface_spacing"] = "0.6"
    p["support_interface_top_layers"] = "3"
    p["support_object_xy_distance"] = "0.4"
    p["brim_width"] = "6.0"
    p["brim_object_gap"] = "0.15"
    return p


def build_standard(layer, material):
    """Uso diário confiável — referência Creality."""
    name = f"{layer:.2f}mm Standard @Creality K2 0.4 nozzle - {material}"
    p = base_profile(name, material)
    p["initial_layer_print_height"] = "0.24"
    p["wall_loops"] = "3"
    p["wall_sequence"] = "inner wall/outer wall"
    p["sparse_infill_density"] = "20%" if material == "PLA" else "18%"
    p["sparse_infill_pattern"] = "gyroid"
    p["internal_solid_infill_pattern"] = "monotonic"
    p["infill_combination"] = "1"
    p["top_surface_pattern"] = "monotonic"
    p["bottom_surface_pattern"] = "monotonic"
    p.update(shell_layers(layer, 4))
    apply_speeds(p, material, 260, 190, 280, 240, 180, 40, 480, 100, 75)
    apply_accels(p, material, 5000, 4000, 3000, 2500)
    p["support_top_z_distance"] = "0.2"
    p["support_interface_spacing"] = "0.6"
    p["support_interface_top_layers"] = "3"
    p["support_object_xy_distance"] = "0.4"
    p["brim_width"] = "6.0"
    p["brim_object_gap"] = "0.15"
    return p


def build_strong(layer, material):
    """Peças mecânicas — paredes, infill e cascas reforçados."""
    name = f"{layer:.2f}mm Strong @Creality K2 0.4 nozzle - {material}"
    p = base_profile(name, material)
    init = "0.28" if layer >= 0.24 else "0.24"
    p["initial_layer_print_height"] = init
    p["wall_loops"] = "6" if material == "PETG" else "5"
    p["wall_sequence"] = "inner wall/outer wall"
    density = "55%" if material == "PETG" else "50%"
    if layer >= 0.24:
        density = "48%" if material == "PETG" else "45%"
    p["sparse_infill_density"] = density
    p["sparse_infill_pattern"] = "gyroid"
    p["internal_solid_infill_pattern"] = "gyroid"
    p["infill_combination"] = "0"
    p["top_surface_pattern"] = "zig-zag"
    p["bottom_surface_pattern"] = "zig-zag"
    shells = 6 if layer <= 0.2 else 5
    p.update(shell_layers(layer, shells))
    apply_speeds(p, material, 180, 130, 180, 160, 130, 30, 380, 80, 55)
    apply_accels(p, material, 3500, 2500, 2000, 1800)
    p["support_top_z_distance"] = "0.2"
    p["support_interface_spacing"] = "0.5"
    p["support_interface_top_layers"] = "4"
    p["support_object_xy_distance"] = "0.5"
    p["brim_width"] = "12.0"
    p["brim_object_gap"] = "0.1"
    p["seam_position"] = "back"
    return p


def build_quality(layer, material):
    """Máximo detalhe e acabamento superficial."""
    name = f"{layer:.2f}mm Quality @Creality K2 0.4 nozzle - {material}"
    p = base_profile(name, material)
    init_map = {0.08: 0.16, 0.12: 0.20, 0.16: 0.24, 0.20: 0.24}
    p["initial_layer_print_height"] = str(init_map.get(layer, layer))
    p["wall_loops"] = "6" if layer <= 0.12 else "5"
    p["wall_sequence"] = "outer wall/inner wall"
    p["sparse_infill_density"] = "22%" if material == "PLA" else "25%"
    p["sparse_infill_pattern"] = "gyroid"
    p["internal_solid_infill_pattern"] = "hilbertcurve"
    p["infill_combination"] = "1"
    p["top_surface_pattern"] = "zig-zag"
    p["bottom_surface_pattern"] = "zig-zag"
    shells = 8 if layer <= 0.08 else (7 if layer <= 0.12 else 6)
    p.update(shell_layers(layer, shells))
    speed_scale = {0.08: 0.45, 0.12: 0.6, 0.16: 0.75, 0.20: 0.85}
    sc = speed_scale.get(layer, 0.85)
    apply_speeds(
        p, material,
        200 * sc, 140 * sc, 220 * sc, 160 * sc, 100 * sc,
        25 * sc, 500, 70 * sc, 50 * sc,
    )
    accel_scale = {0.08: 0.5, 0.12: 0.65, 0.16: 0.8, 0.20: 0.85}
    ac = accel_scale.get(layer, 0.85)
    apply_accels(p, material, 3000 * ac, 2500 * ac, 1800 * ac, 1500 * ac)
    p["support_top_z_distance"] = "0.16" if layer <= 0.12 else "0.2"
    p["support_interface_spacing"] = "0.35" if layer <= 0.12 else "0.4"
    p["support_interface_top_layers"] = "5" if layer <= 0.12 else "4"
    p["support_object_xy_distance"] = "0.35" if layer <= 0.12 else "0.4"
    p["brim_width"] = "14.0" if layer <= 0.12 else "12.0"
    p["brim_object_gap"] = "0.08"
    p["ironing_type"] = "topmost" if layer <= 0.16 else "no ironing"
    p["seam_position"] = "back"
    return p


BUILDERS = [
    (0.36, "Draft", build_draft),
    (0.28, "Fast", build_fast),
    (0.20, "Fast", build_fast),
    (0.20, "Balanced", build_balanced),
    (0.20, "Standard", build_standard),
    (0.24, "Strong", build_strong),
    (0.20, "Strong", build_strong),
    (0.08, "Quality", build_quality),
    (0.12, "Quality", build_quality),
    (0.16, "Quality", build_quality),
    (0.20, "Quality", build_quality),
]

MATERIALS = ["PLA", "PETG"]


def filename_for(profile):
    return f"{profile['name']}.json"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old profiles before regenerating
    for old in OUTPUT_DIR.glob("*.json"):
        old.unlink()

    written = []
    for layer, _ptype, builder in BUILDERS:
        for material in MATERIALS:
            profile = builder(layer, material)
            path = OUTPUT_DIR / filename_for(profile)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(profile, handle, indent=4, ensure_ascii=False)
                handle.write("\n")
            written.append(profile["name"])
            print(f"  ✓ {profile['name']}")

    print(f"\n{len(written)} perfis gerados em {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
