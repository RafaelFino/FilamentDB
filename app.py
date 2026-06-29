import io
import os
import sqlite3
import json
import time
import zipfile
from flask import Flask, jsonify, request, send_file, render_template_string
from pathlib import Path

app = Flask(__name__)

DB_PATH = os.environ.get("FILAMENT_DB_PATH", str(Path(__file__).resolve().parent / "filament.db"))
OUTPUT_DIR = os.environ.get("CREALITY_OUTPUT_DIR", str(Path(__file__).resolve().parent / "creality-print"))
NOZZLE_BASE = "Hyper PLA @Creality K2 0.4 nozzle"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/health")
def health():
    return jsonify({"status": "ok", "database": DB_PATH})


@app.get("/manufacturers")
def list_manufacturers():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, name, country, website, notes FROM manufacturers ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.get("/materials")
def list_materials():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, name, description, average_cost, difficulty, strength, flexibility, temperature_resistance, uv_resistance, food_safe, indoor, outdoor, abrasive, requires_enclosure, recommended_nozzle_temp, recommended_bed_temp, notes FROM materials ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.get("/filament-profiles")
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
    return jsonify([dict(row) for row in rows])


@app.get("/filament-profiles/<int:profile_id>")
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

    if row is None:
        return jsonify({"error": "profile not found"}), 404

    return jsonify(dict(row))


@app.get("/manufacturers/<int:manufacturer_id>/materials")
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
    return jsonify([dict(row) for row in rows])


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


@app.get("/download/creality-print")
def download_creality_print_zip():
    manufacturer = request.args.get("manufacturer", "").strip()
    material = request.args.get("material", "").strip()

    if not manufacturer or not material:
        return jsonify({"error": "manufacturer and material query parameters are required"}), 400

    return build_creality_print_zip_response(manufacturer, material)


@app.get("/download/creality-print/<path:manufacturer>/<path:material>")
def download_creality_print_zip_path(manufacturer, material):
    return build_creality_print_zip_response(manufacturer, material)


@app.get("/download/creality-print/options")
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
    return jsonify([{"manufacturer": row[0], "material": row[1]} for row in rows])


@app.get("/tree")
def tree_page():
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
            "diameter": row[37],
            "density": row[38],
            "drying_temperature": row[39],
            "drying_time": row[40],
            "notes": row[41],
            "active": row[42],
            "download_url": f"/download/creality-print/{manufacturer}/{material}?profile={profile_name}",
        })

    html = """
    <!doctype html>
    <html lang=\"pt-BR\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>FilamentDB Explorer</title>
        <style>
            :root {
                --bg: #05070a;
                --panel: #11151b;
                --panel-2: #171d26;
                --text: #f5f7fa;
                --muted: #9aa4b2;
                --yellow: #ffd84d;
                --blue: #3dd6ff;
                --green: #55f2a1;
                --border: #2a3240;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: Inter, Segoe UI, Roboto, Arial, sans-serif;
                background: linear-gradient(135deg, #05070a 0%, #0d1218 100%);
                color: var(--text);
            }
            .app {
                display: grid;
                grid-template-columns: 290px 1fr;
                min-height: 100vh;
            }
            .sidebar {
                background: rgba(5,7,10,0.9);
                border-right: 1px solid var(--border);
                padding: 20px 16px;
            }
            .sidebar h2 {
                margin: 0 0 8px;
                color: var(--yellow);
                font-size: 1.1rem;
            }
            .sidebar p {
                color: var(--muted);
                font-size: 0.92rem;
                margin: 0 0 16px;
            }
            .tree-item {
                margin: 6px 0;
            }
            .tree-item button {
                width: 100%;
                border: 1px solid var(--border);
                background: var(--panel);
                color: var(--text);
                padding: 10px 12px;
                border-radius: 8px;
                text-align: left;
                cursor: pointer;
                font-weight: 600;
            }
            .tree-item button:hover, .tree-item button.active {
                border-color: var(--blue);
                box-shadow: 0 0 0 1px var(--blue);
                color: var(--blue);
            }
            .content {
                padding: 24px;
            }
            .hero {
                background: linear-gradient(90deg, rgba(61,214,255,0.12), rgba(255,216,77,0.08));
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 18px 20px;
                margin-bottom: 18px;
            }
            .hero h1 { margin: 0 0 8px; color: var(--yellow); }
            .hero p { margin: 0; color: var(--muted); }
            .summary-card {
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 12px 14px;
                margin-bottom: 14px;
            }
            .summary-card h3 { margin: 0 0 8px; color: var(--blue); }
            .summary-card p { margin: 4px 0; color: var(--muted); }
            .toolbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
                margin-bottom: 14px;
                flex-wrap: wrap;
            }
            .actions button {
                background: linear-gradient(90deg, var(--blue), #6ee7ff);
                color: #041018;
                border: none;
                padding: 10px 14px;
                border-radius: 999px;
                font-weight: 700;
                cursor: pointer;
            }
            .actions button.secondary {
                background: #232a34;
                color: var(--yellow);
                border: 1px solid var(--border);
            }
            table {
                width: 100%;
                border-collapse: collapse;
                background: var(--panel);
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            }
            th, td {
                padding: 12px 14px;
                text-align: left;
                border-bottom: 1px solid var(--border);
            }
            th { color: var(--yellow); background: #0f151c; }
            tr:hover { background: rgba(61,214,255,0.06); }
            .chip {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 999px;
                background: rgba(85,242,161,.12);
                color: var(--green);
                font-size: 0.82rem;
            }
            .checkbox-cell { width: 40px; }
            input[type=\"checkbox\"] { accent-color: var(--blue); transform: scale(1.1); }
            .row-item { cursor: pointer; }
            .row-item:hover { background: rgba(61,214,255,0.06); }
            .details-row td { background: #0c1118; padding: 0; }
            .details-panel {
                padding: 16px;
                display: grid;
                gap: 12px;
            }
            .report-block {
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--border);
                border-radius: 12px;
                overflow: hidden;
            }
            .report-block-header {
                padding: 10px 12px;
                background: linear-gradient(90deg, rgba(61,214,255,0.14), rgba(255,216,77,0.1));
                border-bottom: 1px solid var(--border);
                font-weight: 700;
                color: var(--yellow);
            }
            .report-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 10px;
                padding: 12px;
            }
            .report-item {
                padding: 10px 12px;
                background: rgba(255,255,255,0.02);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 8px;
            }
            .report-item .label {
                display: block;
                color: var(--muted);
                font-size: 0.8rem;
                margin-bottom: 4px;
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }
            .report-item .value {
                color: var(--text);
                font-weight: 600;
            }
            .empty { color: var(--muted); padding: 16px; background: var(--panel); border: 1px dashed var(--border); border-radius: 10px; }
            @media (max-width: 900px) {
                .app { grid-template-columns: 1fr; }
                .sidebar { border-right: none; border-bottom: 1px solid var(--border); }
            }
        </style>
    </head>
    <body>
        <div class=\"app\">
            <aside class=\"sidebar\">
                <h2>Fabricantes</h2>
                <p>Selecione um fabricante para ver seus materiais e perfis.</p>
                {% for manufacturer, data in tree.items() %}
                <div class=\"tree-item\">
                    <button type=\"button\" class=\"manufacturer-btn\" data-manufacturer=\"{{ manufacturer }}\">{{ manufacturer }}</button>
                </div>
                {% endfor %}
            </aside>
            <main class=\"content\">
                <div class=\"hero\">
                    <h1>FilamentDB Explorer</h1>
                    <p>Escolha um fabricante, marque os materiais desejados e baixe vários perfis em lote.</p>
                </div>
                <div id=\"manufacturer-summary\" class=\"summary-card\">
                    <h3>Resumo do fabricante</h3>
                    <p>Selecione um fabricante para ver país, site, notas e materiais associados.</p>
                </div>
                <div class=\"toolbar\">
                    <div id=\"current-label\">Selecione um fabricante para visualizar os produtos.</div>
                    <div class=\"actions\">
                        <button type=\"button\" id=\"download-selected\">Baixar selecionados</button>
                        <button type=\"button\" id=\"select-all\" class=\"secondary\">Marcar todos</button>
                    </div>
                </div>
                <div id=\"table-container\">
                    <div class=\"empty\">Nenhum fabricante selecionado ainda.</div>
                </div>
            </main>
        </div>
        <script>
            const treeData = {{ tree | tojson }};
            const tableContainer = document.getElementById('table-container');
            const currentLabel = document.getElementById('current-label');
            const manufacturerSummary = document.getElementById('manufacturer-summary');
            const manufacturerButtons = document.querySelectorAll('.manufacturer-btn');
            let currentManufacturer = null;
            let selected = new Set();

            function renderTable(manufacturer) {
                currentManufacturer = manufacturer;
                const manufacturerData = treeData[manufacturer] || {};
                const manufacturerCountry = manufacturerData.country || '—';
                const manufacturerWebsite = manufacturerData.website || '—';
                const manufacturerNotes = manufacturerData.notes || '—';
                currentLabel.textContent = `Fabricante: ${manufacturer}`;
                manufacturerSummary.innerHTML = `
                    <h3>${manufacturer}</h3>
                    <p><strong>País:</strong> ${manufacturerCountry}</p>
                    <p><strong>Site:</strong> ${manufacturerWebsite}</p>
                    <p><strong>Notas:</strong> ${manufacturerNotes}</p>
                `;
                const materialNames = Object.keys(manufacturerData.materials || {}).sort();

                if (!materialNames.length) {
                    tableContainer.innerHTML = '<div class=\"empty\">Nenhum material encontrado para este fabricante.</div>';
                    return;
                }

                const rows = [];
                materialNames.forEach(material => {
                    const materialData = manufacturerData.materials[material] || {};
                    const profiles = materialData.profiles || [];
                    profiles.forEach(profile => {
                        rows.push({
                            material,
                            manufacturerCountry,
                            manufacturerWebsite,
                            manufacturerNotes,
                            materialDescription: materialData.description,
                            materialAverageCost: materialData.average_cost,
                            materialDifficulty: materialData.difficulty,
                            materialStrength: materialData.strength,
                            materialFlexibility: materialData.flexibility,
                            materialTemperatureResistance: materialData.temperature_resistance,
                            materialUvResistance: materialData.uv_resistance,
                            materialFoodSafe: materialData.food_safe ? 'Sim' : 'Não',
                            materialIndoor: materialData.indoor ? 'Sim' : 'Não',
                            materialOutdoor: materialData.outdoor ? 'Sim' : 'Não',
                            materialAbrasive: materialData.abrasive ? 'Sim' : 'Não',
                            materialRequiresEnclosure: materialData.requires_enclosure ? 'Sim' : 'Não',
                            materialRecommendedNozzleTemp: materialData.recommended_nozzle_temp,
                            materialRecommendedBedTemp: materialData.recommended_bed_temp,
                            materialNotes: materialData.notes,
                            commercial: profile.commercial_name,
                            profileName: profile.profile_name,
                            profileId: profile.profile_id,
                            printerModel: profile.printer_model,
                            nozzleSize: profile.nozzle_size,
                            inherits: profile.inherits,
                            baseId: profile.base_id,
                            crealityPrintVersion: profile.creality_print_version,
                            nozzleTempInitial: profile.nozzle_temp_initial,
                            nozzleTempMin: profile.nozzle_temp_min,
                            nozzleTempMax: profile.nozzle_temp_max,
                            bedTempInitial: profile.bed_temp_initial,
                            bedTemp: profile.bed_temp,
                            flowRatio: profile.flow_ratio,
                            maxVolumetricSpeed: profile.max_volumetric_speed,
                            confidence: profile.confidence,
                            diameter: profile.diameter,
                            density: profile.density,
                            dryingTemperature: profile.drying_temperature,
                            dryingTime: profile.drying_time,
                            notes: profile.notes,
                            active: profile.active,
                            downloadUrl: profile.download_url
                        });
                    });
                });

                const html = `
                    <table>
                        <thead>
                            <tr>
                                <th class=\"checkbox-cell\"><input type=\"checkbox\" id=\"toggle-all-rows\" /></th>
                                <th>Material</th>
                                <th>Nome comercial</th>
                                <th>Perfil</th>
                                <th>Ação</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows.map(row => `
                                <tr class=\"row-item\" data-profile-id=\"${row.profileId}\">
                                    <td><input type=\"checkbox\" class=\"row-check\" value=\"${row.downloadUrl}\" data-material=\"${row.material}\" /></td>
                                    <td><span class=\"chip\">${row.material}</span></td>
                                    <td>${row.commercial}</td>
                                    <td>${row.profileName}</td>
                                    <td><a href=\"${row.downloadUrl}\">Download ZIP</a></td>
                                </tr>
                                <tr class=\"details-row\" id=\"details-${row.profileId}\" style=\"display:none;\">
                                    <td colspan=\"5\">
                                        <div class=\"details-panel\">
                                            <div class=\"report-block\">                                                <div class="report-block-header">Contexto do fabricante</div>
                                                <div class="report-grid">
                                                    <div class="report-item"><span class="label">Fabricante</span><span class="value">${manufacturer}</span></div>
                                                    <div class="report-item"><span class="label">País</span><span class="value">${row.manufacturerCountry || '—'}</span></div>
                                                    <div class="report-item"><span class="label">Site</span><span class="value">${row.manufacturerWebsite || '—'}</span></div>
                                                    <div class="report-item"><span class="label">Notas</span><span class="value">${row.manufacturerNotes || '—'}</span></div>
                                                </div>
                                            </div>
                                            <div class="report-block">                                                <div class=\"report-block-header\">Resumo do material</div>
                                                <div class=\"report-grid\">
                                                    <div class=\"report-item\"><span class=\"label\">Descrição</span><span class=\"value\">${row.materialDescription || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Preço médio</span><span class=\"value\">${row.materialAverageCost || '—'}/100</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Dificuldade</span><span class=\"value\">${row.materialDifficulty || '—'}/100</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Força</span><span class=\"value\">${row.materialStrength || '—'}/100</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Flexibilidade</span><span class=\"value\">${row.materialFlexibility || '—'}/100</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Resistência térmica</span><span class=\"value\">${row.materialTemperatureResistance || '—'}/100</span></div>                                                    <div class="report-item"><span class="label">Resistência UV</span><span class="value">${row.materialUvResistance || '—'}/100</span></div>                                                </div>
                                            </div>
                                            <div class=\"report-block\">
                                                <div class=\"report-block-header\">Indicações e recomendações</div>
                                                <div class=\"report-grid\">
                                                    <div class=\"report-item\"><span class=\"label\">Recomendações</span><span class=\"value\">${row.materialNotes || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Temperatura recomendada do bico</span><span class=\"value\">${row.materialRecommendedNozzleTemp || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Temperatura recomendada da mesa</span><span class=\"value\">${row.materialRecommendedBedTemp || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Uso interno</span><span class=\"value\">${row.materialIndoor || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Uso externo</span><span class=\"value\">${row.materialOutdoor || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Food safe</span><span class=\"value\">${row.materialFoodSafe || '—'}</span></div>                                                    <div class="report-item"><span class="label">Abrasivo</span><span class="value">${row.materialAbrasive || '—'}</span></div>
                                                    <div class="report-item"><span class="label">Requer caixa</span><span class="value">${row.materialRequiresEnclosure || '—'}</span></div>                                                </div>
                                            </div>
                                            <div class=\"report-block\">
                                                <div class=\"report-block-header\">Perfil do produto</div>
                                                <div class=\"report-grid\">
                                                    <div class=\"report-item\"><span class=\"label\">Impressora</span><span class=\"value\">${row.printerModel || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Bico</span><span class=\"value\">${row.nozzleSize || '—'} mm</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Herança</span><span class=\"value\">${row.inherits || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Base ID</span><span class=\"value\">${row.baseId || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Versão</span><span class=\"value\">${row.crealityPrintVersion || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Status</span><span class=\"value\">${row.active ? 'Ativo' : 'Inativo'}</span></div>
                                                </div>
                                            </div>
                                            <div class=\"report-block\">
                                                <div class=\"report-block-header\">Temperaturas e fluxo</div>
                                                <div class=\"report-grid\">
                                                    <div class=\"report-item\"><span class=\"label\">Temperatura inicial</span><span class=\"value\">${row.nozzleTempInitial || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Temp. mínima</span><span class=\"value\">${row.nozzleTempMin || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Temp. máxima</span><span class=\"value\">${row.nozzleTempMax || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Bed inicial</span><span class=\"value\">${row.bedTempInitial || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Bed</span><span class=\"value\">${row.bedTemp || '—'}°C</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Flow ratio</span><span class=\"value\">${row.flowRatio || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Velocidade volumétrica</span><span class=\"value\">${row.maxVolumetricSpeed || '—'}</span></div>
                                                </div>
                                            </div>
                                            <div class=\"report-block\">
                                                <div class=\"report-block-header\">Características físicas</div>
                                                <div class=\"report-grid\">
                                                    <div class=\"report-item\"><span class=\"label\">Confiança</span><span class=\"value\">${row.confidence || '—'}%</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Diâmetro</span><span class=\"value\">${row.diameter || '—'} mm</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Densidade</span><span class=\"value\">${row.density || '—'}</span></div>
                                                    <div class=\"report-item\"><span class=\"label\">Secagem</span><span class=\"value\">${row.dryingTemperature || '—'}°C / ${row.dryingTime || '—'}h</span></div>
                                                </div>
                                            </div>
                                            <div class=\"report-block\">
                                                <div class=\"report-block-header\">Observações</div>
                                                <div class=\"report-grid\">
                                                    <div class=\"report-item\"><span class=\"label\">Notas</span><span class=\"value\">${row.notes || '—'}</span></div>
                                                </div>
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>`;
                tableContainer.innerHTML = html;

                const toggleAll = document.getElementById('toggle-all-rows');
                if (toggleAll) {
                    toggleAll.addEventListener('change', (event) => {
                        document.querySelectorAll('.row-check').forEach(box => {
                            box.checked = event.target.checked;
                            if (event.target.checked) selected.add(box.value);
                            else selected.delete(box.value);
                        });
                    });
                }

                document.querySelectorAll('.row-check').forEach(box => {
                    box.addEventListener('change', () => {
                        if (box.checked) selected.add(box.value);
                        else selected.delete(box.value);
                    });
                });

                document.querySelectorAll('.row-item').forEach(row => {
                    row.addEventListener('click', (event) => {
                        if (event.target.tagName === 'INPUT' || event.target.tagName === 'A') {
                            return;
                        }
                        const panel = document.getElementById(`details-${row.dataset.profileId}`);
                        if (panel) {
                            panel.style.display = panel.style.display === 'none' ? '' : 'none';
                        }
                    });
                });
            }

            manufacturerButtons.forEach(button => {
                button.addEventListener('click', () => {
                    manufacturerButtons.forEach(btn => btn.classList.remove('active'));
                    button.classList.add('active');
                    renderTable(button.dataset.manufacturer);
                });
            });

            document.getElementById('download-selected').addEventListener('click', () => {
                const urls = Array.from(selected);
                if (!urls.length) {
                    alert('Selecione ao menos um perfil para baixar.');
                    return;
                }
                urls.forEach(url => window.open(url, '_blank'));
            });

            document.getElementById('select-all').addEventListener('click', () => {
                document.querySelectorAll('.row-check').forEach(box => {
                    box.checked = true;
                    selected.add(box.value);
                });
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html, tree=tree)


def build_creality_print_zip_response(manufacturer, material):
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

    if not rows:
        return jsonify({"error": "no profiles found for the requested manufacturer and material"}), 404

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
    return send_file(in_memory, mimetype="application/zip", as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
