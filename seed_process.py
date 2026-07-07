#!/usr/bin/env python3

import os
import sqlite3
import json
from pathlib import Path

DB_PATH = os.environ.get("FILAMENT_DB_PATH", "filament.db")
DATA_SOURCE_DIR = os.path.join(os.path.dirname(__file__), "data-source/process")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Criar materiais PLA e PETG se não existirem
def ensure_materials():
    materials = [
        ("PLA", "Polylactic Acid - Filamento versátil para impressão geral"),
        ("PETG", "Polyethylene Terephthalate Glycol - Filamento resistente e durável")
    ]
    
    for name, description in materials:
        cur.execute("SELECT id FROM materials WHERE name = ?", (name,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO materials(name, description, average_cost, difficulty, strength, 
                                     flexibility, temperature_resistance, uv_resistance, food_safe, 
                                     indoor, outdoor, abrasive, requires_enclosure, 
                                     recommended_nozzle_temp, recommended_bed_temp)
                VALUES (?, ?, 50, 50, 50, 50, 50, 50, 0, 1, 0, 0, 0, 220, 60)
            """, (name, description))
            print(f"Material {name} criado")

ensure_materials()
conn.commit()

# Mapeamento de tipos de perfil
PROFILE_TYPE_MAPPING = {
    "Fast": "fast",
    "Standard": "standard", 
    "Balanced": "balanced",
    "Strong": "strong",
    "Quality": "quality"
}

# Extrair material do nome do arquivo
def extract_material(filename):
    if "PLA" in filename:
        return "PLA"
    elif "PETG" in filename:
        return "PETG"
    return None

# Extrair tipo de perfil do nome do arquivo
def extract_profile_type(filename):
    for type_name, type_code in PROFILE_TYPE_MAPPING.items():
        if type_name in filename:
            return type_code
    return "standard"

# Extrair altura de camada do nome do arquivo
def extract_layer_height(filename):
    import re
    match = re.search(r'(\d+\.?\d*)mm', filename)
    if match:
        return float(match.group(1))
    return 0.2

# Buscar ID do material
def get_material_id(material_name):
    cur.execute("SELECT id FROM materials WHERE name = ?", (material_name,))
    result = cur.fetchone()
    if result:
        return result[0]
    else:
        print(f"ERRO: Material {material_name} não encontrado no banco de dados")
        return None

# Ler todos os arquivos JSON de process
process_files = list(Path(DATA_SOURCE_DIR).glob("*.json"))

if not process_files:
    print(f"ERRO: Nenhum arquivo JSON encontrado em {DATA_SOURCE_DIR}")
    exit(1)

print(f"Encontrados {len(process_files)} arquivos de perfil de processo")

# Limpar perfis de processo existentes
cur.execute("DELETE FROM process_profiles")
conn.commit()
print("Perfis de processo existentes removidos")

# Processar cada arquivo
for json_file in sorted(process_files):
    try:
        with open(json_file, 'r') as f:
            profile_data = json.load(f)
        
        filename = json_file.name
        material_name = extract_material(filename)
        profile_type = extract_profile_type(filename)
        layer_height = extract_layer_height(filename)
        
        if not material_name:
            print(f"AVISO: Não foi possível extrair material do arquivo {filename}")
            continue
        
        material_id = get_material_id(material_name)
        if not material_id:
            continue
        
        # Construir query dinâmica baseada nos campos disponíveis no JSON
        columns = [
            "material_id", "profile_name", "profile_type", "layer_height", "initial_layer_height",
            "inner_wall_speed", "outer_wall_speed", "sparse_infill_speed", "internal_solid_infill_speed",
            "top_surface_speed", "initial_layer_speed", "travel_speed", "support_speed", "gap_infill_speed",
            "default_acceleration", "inner_wall_acceleration", "outer_wall_acceleration", "top_surface_acceleration",
            "wall_loops", "wall_generator", "wall_sequence", "sparse_infill_density", "sparse_infill_pattern",
            "internal_solid_infill_pattern", "infill_combination", "top_surface_pattern", "bottom_surface_pattern",
            "top_shell_layers", "bottom_shell_layers", "top_shell_thickness", "bottom_shell_thickness",
            "enable_support", "support_type", "support_on_build_plate_only", "support_top_z_distance",
            "support_interface_spacing", "support_interface_top_layers", "support_object_xy_distance",
            "support_xy_overrides_z", "brim_width", "brim_object_gap", "ironing_type", "seam_position",
            "inherits", "description", "notes"
        ]
        
        # Mapeamento de campos JSON para colunas do banco
        field_mapping = {
            "material_id": material_id,
            "profile_name": profile_data.get("name", filename),
            "profile_type": profile_type,
            "layer_height": layer_height,
            "initial_layer_height": float(profile_data.get("initial_layer_print_height", "0.24")),
            "inner_wall_speed": float(profile_data.get("inner_wall_speed", "200")),
            "outer_wall_speed": float(profile_data.get("outer_wall_speed", "150")),
            "sparse_infill_speed": float(profile_data.get("sparse_infill_speed", "200")),
            "internal_solid_infill_speed": float(profile_data.get("internal_solid_infill_speed", "200")),
            "top_surface_speed": float(profile_data.get("top_surface_speed", "150")),
            "initial_layer_speed": float(profile_data.get("initial_layer_speed", "30")),
            "travel_speed": float(profile_data.get("travel_speed", "300")),
            "support_speed": float(profile_data.get("support_speed", "80")),
            "gap_infill_speed": float(profile_data.get("gap_infill_speed", "60")),
            "default_acceleration": int(profile_data.get("default_acceleration", "3000")),
            "inner_wall_acceleration": int(profile_data.get("inner_wall_acceleration", "2000")),
            "outer_wall_acceleration": int(profile_data.get("outer_wall_acceleration", "1500")),
            "top_surface_acceleration": int(profile_data.get("top_surface_acceleration", "1500")),
            "wall_loops": int(profile_data.get("wall_loops", "3")),
            "wall_generator": profile_data.get("wall_generator", "arachne"),
            "wall_sequence": profile_data.get("wall_sequence", "inner wall/outer wall"),
            "sparse_infill_density": profile_data.get("sparse_infill_density", "20%"),
            "sparse_infill_pattern": profile_data.get("sparse_infill_pattern", "gyroid"),
            "internal_solid_infill_pattern": profile_data.get("internal_solid_infill_pattern", "monotonic"),
            "infill_combination": int(profile_data.get("infill_combination", "0")),
            "top_surface_pattern": profile_data.get("top_surface_pattern", "monotonic"),
            "bottom_surface_pattern": profile_data.get("bottom_surface_pattern", "monotonic"),
            "top_shell_layers": int(profile_data.get("top_shell_layers", "4")),
            "bottom_shell_layers": int(profile_data.get("bottom_shell_layers", "4")),
            "top_shell_thickness": float(profile_data.get("top_shell_thickness", "0.8")),
            "bottom_shell_thickness": float(profile_data.get("bottom_shell_thickness", "0.8")),
            "enable_support": int(profile_data.get("enable_support", "1")),
            "support_type": profile_data.get("support_type", "tree(auto)"),
            "support_on_build_plate_only": int(profile_data.get("support_on_build_plate_only", "1")),
            "support_top_z_distance": float(profile_data.get("support_top_z_distance", "0.2")),
            "support_interface_spacing": float(profile_data.get("support_interface_spacing", "0.6")),
            "support_interface_top_layers": int(profile_data.get("support_interface_top_layers", "3")),
            "support_object_xy_distance": float(profile_data.get("support_object_xy_distance", "0.4")),
            "support_xy_overrides_z": profile_data.get("support_xy_overrides_z", "z_overrides_xy"),
            "brim_width": float(profile_data.get("brim_width", "6")),
            "brim_object_gap": float(profile_data.get("brim_object_gap", "0.15")),
            "ironing_type": profile_data.get("ironing_type", "no ironing"),
            "seam_position": profile_data.get("seam_position", "aligned"),
            "inherits": profile_data.get("inherits", "0.20mm Standard @Creality K2 0.4 nozzle"),
            "description": f"Perfil {profile_type} para {material_name}",
            "notes": f"Importado de {filename}"
        }
        
        # Construir placeholders e valores
        placeholders = ", ".join(["?"] * len(columns))
        values = [field_mapping[col] for col in columns]
        
        # Inserir no banco de dados
        cur.execute(f"""
            INSERT INTO process_profiles({", ".join(columns)})
            VALUES ({placeholders})
        """, values)
        
        print(f"Inserido: {field_mapping['profile_name']}")
        
    except Exception as e:
        print(f"ERRO ao processar {json_file.name}: {e}")
        import traceback
        traceback.print_exc()
        continue

conn.commit()
conn.close()

print(f"Seed de perfis de processo concluído com sucesso!")
print(f"Total de perfis inseridos: {len(process_files)}")
