#!/usr/bin/env python3
import csv
import json
from pathlib import Path
import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
CSV_FILES = [p for p in DATA_DIR.glob('*.csv')]

FIELD_MAP = {
    'color_name': 'color',
    'finish': 'surface_finish',
    'diameter_mm': 'diameter',
    'dry_temp': 'drying_temperature',
    'dry_hours': 'drying_time',
    'recommended_use': 'recommendation',
    'notes': 'notes',
}

LINE_ALIAS_MAP = {
    'Hyper PLA': 'Hyper Series',
    'PLA Matte': 'PLA Matte',
    'PLA Silk': 'PLA Silk',
    'Hyper PETG': 'Hyper PETG Line',
    'CR PETG': 'CR PETG Line',
    'ABS': 'ABS Industrial Line',
    'ASA': 'ASA Outdoor Line',
    'TPU 95A': 'TPU Flex Line',
    'PLA Premium': 'Premium Line',
    'PETG Premium': 'Industrial Line',
    'ABS Premium': 'High Temp Line',
    'ASA': 'High Temp Line',
    'PLA Easy': 'Standard Line',
    'PLA Velvet': 'Velvet Line',
    'V-Silk': 'V-Silk',
    'Duo Color Shadow': 'Duo Color Shadow',
    'PETG HF': 'Engineering Line',
    'Stone PLA': 'Stone PLA',
    'Wood PLA': 'Wood PLA',
}

SUMMARY = []


def normalize_text(value):
    if value is None:
        return None
    return str(value).strip()


def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def write_yaml(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def find_profile_match(profile, candidates):
    profile_line = normalize_text(profile.get('line'))
    profile_name = normalize_text(profile.get('profile_name'))
    commercial_name = normalize_text(profile.get('commercial_name'))

    for candidate in candidates:
        if profile_name and profile_name == normalize_text(candidate.get('profile_name')):
            return candidate
        if commercial_name and commercial_name == normalize_text(candidate.get('commercial_name')):
            return candidate
        if profile_line and profile_line == normalize_text(candidate.get('line')):
            return candidate
    return None


def build_candidate_index(csv_rows):
    index = {}
    for row in csv_rows:
        key = normalize_text(row['commercial_name']) or normalize_text(row['profile_name']) or normalize_text(row['line'])
        index.setdefault(key, []).append(row)
    return index


def enrich_yaml(yaml_path, csv_path):
    data = load_yaml(yaml_path)
    csv_rows = list(csv.DictReader(open(csv_path, newline='', encoding='utf-8')))
    if not csv_rows:
        return None

    candidates = csv_rows
    index = build_candidate_index(candidates)
    update_count = 0
    unmatched = []

    for material_name, material_data in data.get('materials', {}).items():
        for profile in material_data.get('profiles', []):
            match = find_profile_match(profile, candidates)
            if not match:
                alias_line = LINE_ALIAS_MAP.get(normalize_text(profile.get('line')))
                if alias_line:
                    match = next((row for row in candidates if normalize_text(row['line']) == normalize_text(alias_line) and normalize_text(row['material']) == normalize_text(material_name)), None)
            if not match and profile.get('color'):
                match = next((row for row in candidates if normalize_text(row['color_name']) == normalize_text(profile.get('color')) and normalize_text(row['material']) == normalize_text(material_name)), None)
            if not match:
                unmatched.append({'material': material_name, 'profile_name': profile.get('profile_name'), 'commercial_name': profile.get('commercial_name'), 'line': profile.get('line')})
                continue
            for csv_field, yaml_field in FIELD_MAP.items():
                value = normalize_text(match.get(csv_field))
                if value not in [None, '']:
                    if yaml_field == 'recommendation' and profile.get('recommendation'):
                        continue
                    profile[yaml_field] = value
            if 'line' not in profile or not profile['line']:
                profile['line'] = normalize_text(match.get('line'))
            if 'color' not in profile or not profile['color']:
                profile['color'] = normalize_text(match.get('color_name'))
            if 'surface_finish' not in profile or not profile['surface_finish']:
                profile['surface_finish'] = normalize_text(match.get('finish'))
            update_count += 1

    return {'yaml_path': yaml_path, 'csv_path': csv_path, 'updates': update_count, 'unmatched': unmatched}


def main():
    yaml_map = {p.stem.lower(): p for p in DATA_DIR.glob('*.yaml')}
    for csv_path in CSV_FILES:
        name = csv_path.stem.lower()
        yaml_path = yaml_map.get(name)
        if not yaml_path:
            print(f'Pular {csv_path.name}: não há YAML correspondente')
            continue
        print(f'Enriquecendo {yaml_path.name} com {csv_path.name}')
        result = enrich_yaml(yaml_path, csv_path)
        if result is None:
            print('  Nenhum dado CSV encontrado')
            continue
        if result['updates'] > 0:
            write_yaml(yaml_path, load_yaml(yaml_path))
            print(f"  Atualizadas {result['updates']} perfis")
        else:
            print('  Nenhuma atualização aplicada')
        if result['unmatched']:
            print('  Perfis sem correspondência:', len(result['unmatched']))
            for item in result['unmatched'][:5]:
                print('   -', item)

if __name__ == '__main__':
    main()
