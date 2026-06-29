const treeData = window.treeData || {};
const tableContainer = document.getElementById('table-container');
const currentLabel = document.getElementById('current-label');
const manufacturerSummary = document.getElementById('manufacturer-summary');
const manufacturerButtons = document.querySelectorAll('.manufacturer-btn');
let currentManufacturer = null;
let selected = new Set();

function formatStars(value) {
    const score = Number(value);
    if (!Number.isFinite(score)) {
        return '—';
    }
    const stars = Math.round(Math.max(0, Math.min(10, score / 10)));
    return `${stars}/10 ⭐`;
}

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
        <p><strong>Observações:</strong> ${manufacturerNotes}</p>
    `;

    const materialNames = Object.keys(manufacturerData.materials || {}).sort();
    if (!materialNames.length) {
        tableContainer.innerHTML = '<div class="empty">Nenhum material encontrado para este fabricante.</div>';
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
                    <th class="checkbox-cell"><input type="checkbox" id="toggle-all-rows" /></th>
                    <th>Material</th>
                    <th>Nome comercial</th>
                    <th>Perfil</th>
                    <th>Ação</th>
                </tr>
            </thead>
            <tbody>
                ${rows.map(row => `
                    <tr class="row-item" data-profile-id="${row.profileId}">
                        <td><input type="checkbox" class="row-check" value="${row.downloadUrl}" data-material="${row.material}" /></td>
                        <td><span class="chip">${row.material}</span></td>
                        <td>${row.commercial}</td>
                        <td>${row.profileName}</td>
                        <td><a href="${row.downloadUrl}">Download ZIP</a></td>
                    </tr>
                    <tr class="details-row" id="details-${row.profileId}" style="display:none;">
                        <td colspan="5">
                            <div class="details-panel">
                                <div class="report-block">
                                    <div class="report-block-header">Contexto do fabricante</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Fabricante</span><span class="value">${manufacturer}</span></div>
                                        <div class="report-item"><span class="label">País</span><span class="value">${row.manufacturerCountry || '—'}</span></div>
                                        <div class="report-item"><span class="label">Site</span><span class="value">${row.manufacturerWebsite || '—'}</span></div>
                                        <div class="report-item"><span class="label">Observações</span><span class="value">${row.manufacturerNotes || '—'}</span></div>
                                    </div>
                                </div>
                                <div class="report-block">
                                    <div class="report-block-header">Resumo do material</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Descrição</span><span class="value">${row.materialDescription || '—'}</span></div>
                                        <div class="report-item"><span class="label">Preço médio</span><span class="value">${formatStars(row.materialAverageCost)}</span></div>
                                        <div class="report-item"><span class="label">Dificuldade</span><span class="value">${formatStars(row.materialDifficulty)}</span></div>
                                        <div class="report-item"><span class="label">Força</span><span class="value">${formatStars(row.materialStrength)}</span></div>
                                        <div class="report-item"><span class="label">Flexibilidade</span><span class="value">${formatStars(row.materialFlexibility)}</span></div>
                                        <div class="report-item"><span class="label">Resistência térmica</span><span class="value">${formatStars(row.materialTemperatureResistance)}</span></div>
                                        <div class="report-item"><span class="label">Resistência UV</span><span class="value">${formatStars(row.materialUvResistance)}</span></div>
                                    </div>
                                </div>
                                <div class="report-block">
                                    <div class="report-block-header">Indicações e recomendações</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Recomendações</span><span class="value">${row.materialNotes || '—'}</span></div>
                                        <div class="report-item"><span class="label">Temperatura recomendada do bico</span><span class="value">${row.materialRecommendedNozzleTemp || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Temperatura recomendada da mesa</span><span class="value">${row.materialRecommendedBedTemp || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Uso interno</span><span class="value">${row.materialIndoor || '—'}</span></div>
                                        <div class="report-item"><span class="label">Uso externo</span><span class="value">${row.materialOutdoor || '—'}</span></div>
                                        <div class="report-item"><span class="label">Food safe</span><span class="value">${row.materialFoodSafe || '—'}</span></div>
                                        <div class="report-item"><span class="label">Abrasivo</span><span class="value">${row.materialAbrasive || '—'}</span></div>
                                        <div class="report-item"><span class="label">Requer caixa</span><span class="value">${row.materialRequiresEnclosure || '—'}</span></div>
                                    </div>
                                </div>
                                <div class="report-block">
                                    <div class="report-block-header">Perfil do produto</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Impressora</span><span class="value">${row.printerModel || '—'}</span></div>
                                        <div class="report-item"><span class="label">Bico</span><span class="value">${row.nozzleSize || '—'} mm</span></div>
                                        <div class="report-item"><span class="label">Herança</span><span class="value">${row.inherits || '—'}</span></div>
                                        <div class="report-item"><span class="label">Base ID</span><span class="value">${row.baseId || '—'}</span></div>
                                        <div class="report-item"><span class="label">Versão</span><span class="value">${row.crealityPrintVersion || '—'}</span></div>
                                        <div class="report-item"><span class="label">Status</span><span class="value">${row.active ? 'Ativo' : 'Inativo'}</span></div>
                                    </div>
                                </div>
                                <div class="report-block">
                                    <div class="report-block-header">Temperaturas e fluxo</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Temperatura inicial</span><span class="value">${row.nozzleTempInitial || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Temp. mínima</span><span class="value">${row.nozzleTempMin || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Temp. máxima</span><span class="value">${row.nozzleTempMax || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Bed inicial</span><span class="value">${row.bedTempInitial || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Bed</span><span class="value">${row.bedTemp || '—'}°C</span></div>
                                        <div class="report-item"><span class="label">Flow ratio</span><span class="value">${row.flowRatio || '—'}</span></div>
                                        <div class="report-item"><span class="label">Velocidade volumétrica</span><span class="value">${row.maxVolumetricSpeed || '—'}</span></div>
                                    </div>
                                </div>
                                <div class="report-block">
                                    <div class="report-block-header">Características físicas</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Confiança</span><span class="value">${row.confidence || '—'}%</span></div>
                                        <div class="report-item"><span class="label">Diâmetro</span><span class="value">${row.diameter || '—'} mm</span></div>
                                        <div class="report-item"><span class="label">Densidade</span><span class="value">${row.density || '—'}</span></div>
                                        <div class="report-item"><span class="label">Secagem</span><span class="value">${row.dryingTemperature || '—'}°C / ${row.dryingTime || '—'}h</span></div>
                                    </div>
                                </div>
                                <div class="report-block">
                                    <div class="report-block-header">Observações</div>
                                    <div class="report-grid">
                                        <div class="report-item"><span class="label">Notas</span><span class="value">${row.notes || '—'}</span></div>
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;

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

const downloadButton = document.getElementById('download-selected');
if (downloadButton) {
    downloadButton.addEventListener('click', () => {
        const urls = Array.from(selected);
        if (!urls.length) {
            alert('Selecione ao menos um perfil para baixar.');
            return;
        }
        urls.forEach(url => window.open(url, '_blank'));
    });
}

const selectAllButton = document.getElementById('select-all');
if (selectAllButton) {
    selectAllButton.addEventListener('click', () => {
        document.querySelectorAll('.row-check').forEach(box => {
            box.checked = true;
            selected.add(box.value);
        });
    });
}
