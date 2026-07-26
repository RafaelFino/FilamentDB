// ─── State ────────────────────────────────────────────────────────────────────
const treeData = window.treeData || {};
const processTreeData = window.processTreeData || {};
let currentManufacturer = null;
let currentMaterial = null;
let currentView = 'filaments';
const comparedProfiles = new Map(); // profileId -> enriched profile object
const comparedProcessProfiles = new Map(); // profileId -> process profile object

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const tableContainer     = document.getElementById('table-container');
const currentLabel       = document.getElementById('current-label');
const mfrCard            = document.getElementById('mfr-card');
const manufacturerBtns   = document.querySelectorAll('.manufacturer-btn');
const compareTableWrap   = document.getElementById('compare-table-wrap');
const compareTable       = document.getElementById('compare-table');
const comparePlaceholder = document.getElementById('compare-placeholder');
const clearCompareBtn    = document.getElementById('clear-compare');
const downloadBtn        = document.getElementById('download-selected');
const selectAllBtn       = document.getElementById('select-all');

// Process view refs
const processTableContainer     = document.getElementById('process-table-container');
const processCurrentLabel       = document.getElementById('current-label-process');
const materialCard              = document.getElementById('material-card');
const materialBtns              = document.querySelectorAll('.material-btn');
const processCompareTableWrap   = document.getElementById('process-compare-table-wrap');
const processCompareTable       = document.getElementById('process-compare-table');
const processComparePlaceholder = document.getElementById('process-compare-placeholder');
const processClearCompareBtn    = document.getElementById('process-clear-compare');
const processDownloadBtn        = document.getElementById('download-all-process');

// ─── Material sort order ──────────────────────────────────────────────────────
const MAT_ORDER = ['PLA','PLA Matte','PLA Silk','PETG','PETG CF','ABS','ASA','TPU'];
const matRank = m => { const i = MAT_ORDER.indexOf(m); return i < 0 ? 99 : i; };

// ─── Helpers ─────────────────────────────────────────────────────────────────
const v = (x, suf='') => (x !== null && x !== undefined && x !== '') ? `${x}${suf}` : '—';

function tempRange(min, ideal, max) {
    if (!ideal) return '—';
    const lim = (n) => n ? `<span class="lim">${n}</span>` : '';
    return `<span class="temp-range">${lim(min)}${min?'/':''}` +
           `<span class="ideal">${ideal}°C</span>` +
           `${max?'/':''}${lim(max)}${max?'°C':''}</span>`;
}

function confBar(pct) {
    if (!pct) return '—';
    const color = pct >= 85 ? '#50e8a0' : pct >= 70 ? '#ffd84d' : '#ff7b72';
    return `<div class="conf-wrap">
        <div class="conf-bar"><div class="conf-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="conf-val">${pct}%</span>
    </div>`;
}

function scoreBar(val) {
    return `<div class="score-track"><div class="score-fill" style="width:${val||0}%"></div></div>
            <span class="score-val">${val||'—'}</span>`;
}

function boolIcon(b) {
    return b ? '<span class="bool-yes">✓</span>' : '<span class="bool-no">—</span>';
}

function colorSwatch(hex) {
    if (!hex) return '';
    return `<span class="color-swatch" style="background:${hex}" title="${hex}"></span>`;
}

function typeChip(type) {
    if (!type) return '—';
    const label = type.charAt(0).toUpperCase() + type.slice(1);
    return `<span class="chip chip-${type}">${label}</span>`;
}

function typeRank(t) {
    const order = ['fast', 'standard', 'strong', 'detail', 'safe'];
    const i = order.indexOf(t);
    return i < 0 ? 99 : i;
}

// ─── Render manufacturer card ─────────────────────────────────────────────────
function renderMfrCard(manufacturer) {
    const d = treeData[manufacturer] || {};
    const mats = Object.keys(d.materials || {});
    const profiles = mats.reduce((s, m) => s + (d.materials[m].profiles || []).length, 0);
    const variants = mats.reduce((s, m) =>
        s + (d.materials[m].profiles || []).reduce((ps, p) => ps + (p.variants || []).length, 0), 0);

    mfrCard.innerHTML = `
        <div class="mfr-card-row">
            <div>
                <div class="mfr-name">${manufacturer}</div>
                <div class="mfr-meta">
                    ${d.country ? `<strong>País:</strong> ${d.country}` : ''}
                    ${d.website ? ` · <a href="${d.website}" target="_blank">${d.website}</a>` : ''}
                    ${d.notes   ? ` · ${d.notes}` : ''}
                </div>
            </div>
        </div>
        <div class="mfr-stats">
            <div class="mfr-stat"><strong>${mats.length}</strong>tipos de material</div>
            <div class="mfr-stat"><strong>${profiles}</strong>perfis de impressão</div>
            <div class="mfr-stat"><strong>${variants || '0'}</strong>variantes de cor/SKU</div>
            <div class="mfr-stat"><strong>${mats.join(' · ')}</strong></div>
        </div>
    `;
}

// ─── Render detail panel (expanded row) ──────────────────────────────────────
function renderDetailPanel(profile, material) {
    const matData = treeData[currentManufacturer]?.materials?.[material] || {};
    const variants = profile.variants || [];

    // Scores section
    const scores = [
        ['Dificuldade de impressão', matData.difficulty],
        ['Resistência mecânica',     matData.strength],
        ['Flexibilidade',            matData.flexibility],
        ['Resistência térmica',      matData.temperature_resistance],
        ['Resistência UV',           matData.uv_resistance],
    ];
    const scoreRows = scores.map(([lbl, val]) =>
        `<div class="score-row">
            <span class="score-lbl">${lbl}</span>
            <div class="score-track"><div class="score-fill" style="width:${val||0}%"></div></div>
            <span class="score-val">${val||'—'}</span>
        </div>`
    ).join('');

    // Variants section
    const variantCards = variants.length
        ? variants.map(vr => `
            <div class="variant-card">
                ${colorSwatch(vr.hex_color)}
                <div class="variant-info">
                    <span class="variant-name">${vr.color_name || '—'}</span>
                    <span class="variant-sku">${vr.sku || ''}</span>
                    <span class="variant-meta">${vr.finish || ''} · ${vr.weight_g ? vr.weight_g+'g' : ''}</span>
                    ${vr.recommended_use ? `<span class="variant-meta" style="color:#8a95a8">${vr.recommended_use}</span>` : ''}
                    ${vr.notes ? `<span class="variant-meta" style="font-style:italic">${vr.notes}</span>` : ''}
                </div>
            </div>`).join('')
        : '<span class="muted-txt" style="font-size:.8rem;padding:10px 12px;display:block">Nenhuma variante cadastrada.</span>';

    return `<div class="detail-panel">

        <div class="info-block">
            <div class="info-block-header">🧵 Produto</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Nome comercial</span><span class="v">${v(profile.commercial_name)}</span></div>
                <div class="info-cell"><span class="lbl">Linha</span><span class="v">${v(profile.line)}</span></div>
                <div class="info-cell"><span class="lbl">Posicionamento</span><span class="v">${v(profile.line_positioning)}</span></div>
                <div class="info-cell"><span class="lbl">Uso alvo</span><span class="v">${v(profile.line_target_use)}</span></div>
                <div class="info-cell wide"><span class="lbl">Descrição da linha</span><span class="v">${v(profile.line_description)}</span></div>
                <div class="info-cell wide"><span class="lbl">Recomendação</span><span class="v" style="color:#50e8a0">${v(profile.recommendation)}</span></div>
                <div class="info-cell"><span class="lbl">Acabamento padrão</span><span class="v">${v(profile.surface_finish)}</span></div>
                <div class="info-cell"><span class="lbl">Cor de referência</span><span class="v">${v(profile.color)}</span></div>
                <div class="info-cell"><span class="lbl">Cores disponíveis</span><span class="v">${(profile.line_color_options||[]).join(', ') || '—'}</span></div>
                <div class="info-cell"><span class="lbl">Diâmetro</span><span class="v">${profile.diameter ? profile.diameter+'mm' : '1.75mm (padrão)'}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">🌡️ Parâmetros de impressão</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Bico — ideal</span><span class="v">${v(profile.nozzle_temp_initial,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Bico — mínimo</span><span class="v">${v(profile.nozzle_temp_min,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Bico — máximo</span><span class="v">${v(profile.nozzle_temp_max,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Mesa — inicial</span><span class="v">${v(profile.bed_temp_initial,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Mesa — impressão</span><span class="v">${v(profile.bed_temp,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Cama texturizada — inicial</span><span class="v">${v(profile.textured_bed_initial,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Cama texturizada</span><span class="v">${v(profile.textured_bed,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Flow ratio</span><span class="v">${v(profile.flow_ratio)}</span></div>
                <div class="info-cell"><span class="lbl">Vel. volumétrica máx.</span><span class="v">${v(profile.max_volumetric_speed,' mm³/s')}</span></div>
                <div class="info-cell"><span class="lbl">Confiança do perfil</span><span class="v">${confBar(profile.confidence)}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">🔥 Secagem</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Temperatura</span><span class="v">${v(profile.drying_temperature,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Tempo</span><span class="v">${v(profile.drying_time,'h')}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">⚙️ Perfil Slicer</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Nome do perfil</span><span class="v mono" style="font-size:.75rem">${v(profile.profile_name)}</span></div>
                <div class="info-cell"><span class="lbl">Impressora</span><span class="v">${v(profile.printer_model)}</span></div>
                <div class="info-cell"><span class="lbl">Bico</span><span class="v">${v(profile.nozzle_size,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Versão do perfil</span><span class="v">${v(profile.profile_version)}</span></div>
                <div class="info-cell"><span class="lbl">Status</span><span class="v">${profile.active ? '<span class="bool-yes">Ativo</span>' : '<span style="color:#ff7b72">Inativo</span>'}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">📊 Propriedades do material (${material})</div>
            <div style="padding:12px 12px 4px">
                ${scoreRows}
            </div>
            <div class="info-grid" style="margin-top:4px">
                <div class="info-cell"><span class="lbl">Uso interno</span><span class="v">${boolIcon(matData.indoor)}</span></div>
                <div class="info-cell"><span class="lbl">Uso externo</span><span class="v">${boolIcon(matData.outdoor)}</span></div>
                <div class="info-cell"><span class="lbl">Food safe</span><span class="v">${boolIcon(matData.food_safe)}</span></div>
                <div class="info-cell"><span class="lbl">Abrasivo</span><span class="v">${boolIcon(matData.abrasive)}</span></div>
                <div class="info-cell"><span class="lbl">Requer caixa fechada</span><span class="v">${boolIcon(matData.requires_enclosure)}</span></div>
                <div class="info-cell"><span class="lbl">Bico recomendado (geral)</span><span class="v">${v(matData.recommended_nozzle_temp,'°C')}</span></div>
                <div class="info-cell"><span class="lbl">Mesa recomendada (geral)</span><span class="v">${v(matData.recommended_bed_temp,'°C')}</span></div>
            </div>
        </div>

        <div class="info-block" style="grid-column:1/-1">
            <div class="info-block-header">🎨 Variantes de cor / SKU (${(profile.variants||[]).length})</div>
            <div class="variants-list">${variantCards}</div>
        </div>

    </div>`;
}

// ─── Render top table ─────────────────────────────────────────────────────────
function renderTable(manufacturer) {
    currentManufacturer = manufacturer;
    const mfData = treeData[manufacturer] || {};
    renderMfrCard(manufacturer);

    const matNames = Object.keys(mfData.materials || {}).sort(
        (a, b) => matRank(a) - matRank(b) || a.localeCompare(b)
    );

    if (!matNames.length) {
        tableContainer.innerHTML = '<div class="empty">Nenhum material para este fabricante.</div>';
        currentLabel.textContent = manufacturer;
        return;
    }

    // Flatten all profiles with material name attached
    const rows = [];
    matNames.forEach(mat => {
        (mfData.materials[mat].profiles || []).forEach(p => {
            rows.push({ ...p, _mat: mat });
        });
    });

    currentLabel.textContent = `${manufacturer} — ${rows.length} perfis`;

    const tbody = rows.map(row => {
        const sel = comparedProfiles.has(row.profile_id);
        const varCount = (row.variants || []).length;
        return `
        <tr class="row-item${sel ? ' row-selected' : ''}" data-pid="${row.profile_id}" data-mat="${row._mat}">
            <td class="checkbox-cell"><input type="checkbox" class="row-check" data-pid="${row.profile_id}" ${sel?'checked':''}></td>
            <td><span class="chip chip-${row._mat}">${row._mat}</span></td>
            <td><strong>${v(row.commercial_name)}</strong></td>
            <td class="muted-txt">${v(row.line)}</td>
            <td>${tempRange(row.nozzle_temp_min, row.nozzle_temp_initial, row.nozzle_temp_max)}</td>
            <td class="muted-txt">${v(row.bed_temp,'°C')}</td>
            <td class="muted-txt">${v(row.flow_ratio)}</td>
            <td class="muted-txt">${v(row.max_volumetric_speed,' mm³/s')}</td>
            <td>${confBar(row.confidence)}</td>
            <td class="muted-txt">${row.drying_temperature ? row.drying_temperature+'°C / '+row.drying_time+'h' : '—'}</td>
            <td><span class="muted-txt" style="font-size:.78rem">${varCount > 0 ? varCount+' cores' : '—'}</span></td>
            <td><a class="dl-link" href="${row.download_url}" onclick="event.stopPropagation()">↓ CP</a> · <a class="dl-link" href="${row.orca_download_url}" onclick="event.stopPropagation()">↓ Orca</a></td>
        </tr>
        <tr class="detail-row" id="det-${row.profile_id}" style="display:none">
            <td colspan="12"></td>
        </tr>`;
    }).join('');

    tableContainer.innerHTML = `
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th class="checkbox-cell"><input type="checkbox" id="tog-all"></th>
                <th>Material</th>
                <th>Nome comercial</th>
                <th>Linha</th>
                <th>Bico (min/ideal/max)</th>
                <th>Mesa</th>
                <th>Flow</th>
                <th>Vol. máx</th>
                <th>Confiança</th>
                <th>Secagem</th>
                <th>Cores</th>
                <th>Download</th>
            </tr></thead>
            <tbody>${tbody}</tbody>
        </table>
        </div>`;

    document.getElementById('tog-all').addEventListener('change', e => {
        rows.forEach(row => {
            if (e.target.checked) comparedProfiles.set(row.profile_id, row);
            else comparedProfiles.delete(row.profile_id);
        });
        syncHighlights();
        renderCompare();
    });

    tableContainer.querySelectorAll('.row-item').forEach(tr => {
        const pid = Number(tr.dataset.pid);
        const mat = tr.dataset.mat;

        const toggleCompare = () => {
            const profile = rows.find(r => r.profile_id === pid);
            if (comparedProfiles.has(pid)) comparedProfiles.delete(pid);
            else if (profile) comparedProfiles.set(pid, profile);
            syncHighlights();
            renderCompare();
        };

        // Checkbox click adds/removes from comparison
        const cb = tr.querySelector('.row-check');
        if (cb) {
            cb.addEventListener('change', e => {
                e.stopPropagation();
                toggleCompare();
            });
        }

        tr.addEventListener('click', e => {
            if (e.target.tagName === 'A') return;
            if (e.target.tagName === 'INPUT') return; // handled by checkbox listener
            toggleCompare();

            // Toggle detail panel
            const detRow = document.getElementById(`det-${pid}`);
            if (detRow) {
                const isOpen = detRow.style.display !== 'none';
                if (isOpen) {
                    detRow.style.display = 'none';
                } else {
                    detRow.querySelector('td').innerHTML = renderDetailPanel(
                        rows.find(r => r.profile_id === pid), mat
                    );
                    detRow.style.display = '';
                }
            }
            if (comparedProfiles.size === 1) {
                document.getElementById('compare-panel')
                    .scrollIntoView({ behavior:'smooth', block:'start' });
            }
        });
    });
}

// ─── Sync row highlights ──────────────────────────────────────────────────────
function syncHighlights() {
    document.querySelectorAll('.row-item').forEach(tr => {
        const pid = Number(tr.dataset.pid);
        tr.classList.toggle('row-selected', comparedProfiles.has(pid));
        const cb = tr.querySelector('.row-check');
        if (cb) cb.checked = comparedProfiles.has(pid);
    });
}

// ─── Comparison column definition ────────────────────────────────────────────
const CMP_ROWS = [
    { sec:'Produto',      lbl:'Material',         fn: p => `<span class="chip chip-${p._mat}">${p._mat}</span>` },
    { sec:'Produto',      lbl:'Nome comercial',    fn: p => v(p.commercial_name) },
    { sec:'Produto',      lbl:'Linha',             fn: p => v(p.line) },
    { sec:'Produto',      lbl:'Posicionamento',    fn: p => v(p.line_positioning) },
    { sec:'Produto',      lbl:'Uso alvo',          fn: p => v(p.line_target_use) },
    { sec:'Produto',      lbl:'Acabamento',        fn: p => v(p.surface_finish) },
    { sec:'Produto',      lbl:'Recomendação',      fn: p => `<span style="color:#50e8a0;font-size:.78rem">${v(p.recommendation)}</span>` },

    { sec:'Impressão',    lbl:'Bico ideal',        fn: p => v(p.nozzle_temp_initial,'°C') },
    { sec:'Impressão',    lbl:'Bico mín/máx',      fn: p => `<span class="muted-txt">${v(p.nozzle_temp_min)}–${v(p.nozzle_temp_max)} °C</span>` },
    { sec:'Impressão',    lbl:'Mesa inicial',      fn: p => v(p.bed_temp_initial,'°C') },
    { sec:'Impressão',    lbl:'Mesa impressão',    fn: p => v(p.bed_temp,'°C') },
    { sec:'Impressão',    lbl:'Flow ratio',        fn: p => v(p.flow_ratio) },
    { sec:'Impressão',    lbl:'Vol. máx',          fn: p => v(p.max_volumetric_speed,' mm³/s') },
    { sec:'Impressão',    lbl:'Confiança',         fn: p => confBar(p.confidence) },

    { sec:'Secagem',      lbl:'Temperatura',       fn: p => v(p.drying_temperature,'°C') },
    { sec:'Secagem',      lbl:'Tempo',             fn: p => v(p.drying_time,'h') },

    { sec:'Variantes',    lbl:'Qtd. de cores',     fn: p => v((p.variants||[]).length) },
    { sec:'Variantes',    lbl:'Cores',             fn: p => {
        const vrs = (p.variants||[]);
        if (!vrs.length) return '—';
        return vrs.map(vr =>
            `<span title="${vr.color_name} (${vr.sku||''})">${colorSwatch(vr.hex_color)}</span>`
        ).join(' ');
    }},

    { sec:'Perfil CP',    lbl:'Download',          fn: p => `<a class="dl-link" href="${p.download_url}">↓ Creality Print</a> · <a class="dl-link" href="${p.orca_download_url}">↓ Orca Slicer</a>` },
];

// ─── Render comparison table ──────────────────────────────────────────────────
function renderCompare() {
    if (!comparedProfiles.size) {
        compareTableWrap.style.display = 'none';
        comparePlaceholder.style.display = '';
        return;
    }
    compareTableWrap.style.display = '';
    comparePlaceholder.style.display = 'none';

    const profiles = [...comparedProfiles.values()].sort((a, b) =>
        matRank(a._mat) - matRank(b._mat) || (a.commercial_name||'').localeCompare(b.commercial_name||'')
    );

    const headers = profiles.map(p => `
        <th>
            <div class="col-hdr">
                <span class="col-hdr-name">${p.commercial_name}</span>
                <span class="col-hdr-sub">${p._mat} · ${currentManufacturer||p.manufacturer_name||''}</span>
                <button class="remove-col" data-pid="${p.profile_id}" title="Remover coluna">✕</button>
            </div>
        </th>`).join('');

    // Group rows by section
    let lastSec = null;
    const bodyRows = CMP_ROWS.map(row => {
        let out = '';
        if (row.sec !== lastSec) {
            lastSec = row.sec;
            out += `<tr class="sec-div"><td colspan="${profiles.length+1}">${row.sec}</td></tr>`;
        }
        const cells = profiles.map(p => `<td>${row.fn(p)}</td>`).join('');
        out += `<tr><td class="row-lbl">${row.lbl}</td>${cells}</tr>`;
        return out;
    }).join('');

    compareTable.innerHTML = `
        <thead><tr><th class="corner"></th>${headers}</tr></thead>
        <tbody>${bodyRows}</tbody>`;

    compareTable.querySelectorAll('.remove-col').forEach(btn => {
        btn.addEventListener('click', () => {
            const pid = Number(btn.dataset.pid);
            comparedProfiles.delete(pid);
            syncHighlights();
            renderCompare();
        });
    });
}

// ─── Sidebar buttons ──────────────────────────────────────────────────────────
manufacturerBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        manufacturerBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderTable(btn.dataset.manufacturer);
    });
});

// ─── Toolbar buttons ──────────────────────────────────────────────────────────
clearCompareBtn?.addEventListener('click', () => {
    comparedProfiles.clear();
    syncHighlights();
    renderCompare();
});

downloadBtn?.addEventListener('click', () => {
    if (!comparedProfiles.size) { alert('Selecione ao menos um perfil.'); return; }
    comparedProfiles.forEach(p => window.open(p.download_url, '_blank'));
});

selectAllBtn?.addEventListener('click', () => {
    if (!currentManufacturer) return;
    const mfData = treeData[currentManufacturer] || {};
    Object.entries(mfData.materials || {}).forEach(([mat, matData]) => {
        (matData.profiles || []).forEach(p => {
            comparedProfiles.set(p.profile_id, { ...p, _mat: mat });
        });
    });
    syncHighlights();
    renderCompare();
});

// Initial state
renderCompare();

// ═══════════════════════════════════════════════════════════════════════════════
// ─── Process profiles (same tree style as filaments) ─────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

function renderMaterialCard(material) {
    if (!materialCard) return;
    const d = processTreeData[material] || {};
    const profiles = d.profiles || [];

    materialCard.innerHTML = `
        <div class="mfr-card-row">
            <div>
                <div class="mfr-name"><span class="chip chip-${material}">${material}</span></div>
                <div class="mfr-meta">${d.description ? d.description : ''}</div>
            </div>
        </div>
        <div class="mfr-stats">
            <div class="mfr-stat"><strong>${profiles.length}</strong>perfis de processo</div>
            <div class="mfr-stat"><strong>${[...new Set(profiles.map(p => p.profile_type))].join(' · ') || '—'}</strong>tipos</div>
            <div class="mfr-stat"><a class="dl-link" href="/download/process/${encodeURIComponent(material)}">↓ Creality Print</a> · <a class="dl-link" href="/download/orca/process/${encodeURIComponent(material)}">↓ Orca Slicer</a></div>
        </div>
    `;
}

function renderProcessDetailPanel(profile, material) {
    const matData = processTreeData[material] || {};
    const scores = [
        ['Dificuldade de impressão', matData.difficulty],
        ['Resistência mecânica',     matData.strength],
        ['Flexibilidade',            matData.flexibility],
        ['Resistência térmica',      matData.temperature_resistance],
        ['Resistência UV',           matData.uv_resistance],
    ];
    const scoreRows = scores.map(([lbl, val]) =>
        `<div class="score-row">
            <span class="score-lbl">${lbl}</span>
            <div class="score-track"><div class="score-fill" style="width:${val||0}%"></div></div>
            <span class="score-val">${val||'—'}</span>
        </div>`
    ).join('');

    return `<div class="detail-panel">

        <div class="info-block">
            <div class="info-block-header">⚙️ Perfil</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Nome</span><span class="v">${v(profile.profile_name)}</span></div>
                <div class="info-cell"><span class="lbl">Tipo</span><span class="v">${typeChip(profile.profile_type)}</span></div>
                <div class="info-cell wide"><span class="lbl">Descrição</span><span class="v">${v(profile.description)}</span></div>
                <div class="info-cell wide"><span class="lbl">Notas</span><span class="v">${v(profile.notes)}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">📐 Camadas e paredes</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Altura camada</span><span class="v">${v(profile.layer_height,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Altura 1ª camada</span><span class="v">${v(profile.initial_layer_height,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Paredes</span><span class="v">${v(profile.wall_loops)}</span></div>
                <div class="info-cell"><span class="lbl">Gerador paredes</span><span class="v">${v(profile.wall_generator)}</span></div>
                <div class="info-cell"><span class="lbl">Sequência paredes</span><span class="v">${v(profile.wall_sequence)}</span></div>
                <div class="info-cell"><span class="lbl">Camadas topo</span><span class="v">${v(profile.top_shell_layers)}</span></div>
                <div class="info-cell"><span class="lbl">Camadas base</span><span class="v">${v(profile.bottom_shell_layers)}</span></div>
                <div class="info-cell"><span class="lbl">Esp. topo</span><span class="v">${v(profile.top_shell_thickness,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Esp. base</span><span class="v">${v(profile.bottom_shell_thickness,'mm')}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">🏃 Velocidades</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Parede interna</span><span class="v">${v(profile.inner_wall_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Parede externa</span><span class="v">${v(profile.outer_wall_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Preenchimento</span><span class="v">${v(profile.sparse_infill_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Preench. sólido</span><span class="v">${v(profile.internal_solid_infill_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Superfície topo</span><span class="v">${v(profile.top_surface_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">1ª camada</span><span class="v">${v(profile.initial_layer_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Deslocamento</span><span class="v">${v(profile.travel_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Suporte</span><span class="v">${v(profile.support_speed,' mm/s')}</span></div>
                <div class="info-cell"><span class="lbl">Gap infill</span><span class="v">${v(profile.gap_infill_speed,' mm/s')}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">⚡ Acelerações</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Padrão</span><span class="v">${v(profile.default_acceleration,' mm/s²')}</span></div>
                <div class="info-cell"><span class="lbl">Parede interna</span><span class="v">${v(profile.inner_wall_acceleration,' mm/s²')}</span></div>
                <div class="info-cell"><span class="lbl">Parede externa</span><span class="v">${v(profile.outer_wall_acceleration,' mm/s²')}</span></div>
                <div class="info-cell"><span class="lbl">Superfície topo</span><span class="v">${v(profile.top_surface_acceleration,' mm/s²')}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">🧱 Preenchimento</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Densidade</span><span class="v">${v(profile.sparse_infill_density)}</span></div>
                <div class="info-cell"><span class="lbl">Padrão</span><span class="v">${v(profile.sparse_infill_pattern)}</span></div>
                <div class="info-cell"><span class="lbl">Preench. sólido</span><span class="v">${v(profile.internal_solid_infill_pattern)}</span></div>
                <div class="info-cell"><span class="lbl">Combinação</span><span class="v">${v(profile.infill_combination)}</span></div>
                <div class="info-cell"><span class="lbl">Padrão topo</span><span class="v">${v(profile.top_surface_pattern)}</span></div>
                <div class="info-cell"><span class="lbl">Padrão base</span><span class="v">${v(profile.bottom_surface_pattern)}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">🛟 Suporte e acabamento</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Suporte</span><span class="v">${boolIcon(profile.enable_support)}</span></div>
                <div class="info-cell"><span class="lbl">Tipo</span><span class="v">${v(profile.support_type)}</span></div>
                <div class="info-cell"><span class="lbl">Só na mesa</span><span class="v">${boolIcon(profile.support_on_build_plate_only)}</span></div>
                <div class="info-cell"><span class="lbl">Dist. topo Z</span><span class="v">${v(profile.support_top_z_distance,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Brim</span><span class="v">${v(profile.brim_width,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Ironing</span><span class="v">${v(profile.ironing_type)}</span></div>
                <div class="info-cell"><span class="lbl">Costura</span><span class="v">${v(profile.seam_position)}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">🖨️ Perfil Slicer</div>
            <div class="info-grid">
                <div class="info-cell"><span class="lbl">Impressora</span><span class="v">${v(profile.printer_model)}</span></div>
                <div class="info-cell"><span class="lbl">Bico</span><span class="v">${v(profile.nozzle_size,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Versão</span><span class="v">${v(profile.version)}</span></div>
                <div class="info-cell"><span class="lbl">Status</span><span class="v">${profile.active ? '<span class="bool-yes">Ativo</span>' : '<span style="color:#ff7b72">Inativo</span>'}</span></div>
            </div>
        </div>

        <div class="info-block">
            <div class="info-block-header">📊 Propriedades do material (${material})</div>
            <div style="padding:12px 12px 4px">${scoreRows}</div>
            <div class="info-grid" style="margin-top:4px">
                <div class="info-cell"><span class="lbl">Uso interno</span><span class="v">${boolIcon(matData.indoor)}</span></div>
                <div class="info-cell"><span class="lbl">Uso externo</span><span class="v">${boolIcon(matData.outdoor)}</span></div>
                <div class="info-cell"><span class="lbl">Food safe</span><span class="v">${boolIcon(matData.food_safe)}</span></div>
                <div class="info-cell"><span class="lbl">Abrasivo</span><span class="v">${boolIcon(matData.abrasive)}</span></div>
                <div class="info-cell"><span class="lbl">Requer caixa fechada</span><span class="v">${boolIcon(matData.requires_enclosure)}</span></div>
            </div>
        </div>

    </div>`;
}

function syncProcessHighlights() {
    processTableContainer?.querySelectorAll('.row-item').forEach(tr => {
        const pid = Number(tr.dataset.pid);
        tr.classList.toggle('row-selected', comparedProcessProfiles.has(pid));
        const cb = tr.querySelector('.row-check');
        if (cb) cb.checked = comparedProcessProfiles.has(pid);
    });
}

const PROCESS_CMP_ROWS = [
    { sec:'Perfil',       lbl:'Tipo',                  fn: p => typeChip(p.profile_type) },
    { sec:'Perfil',       lbl:'Descrição',             fn: p => v(p.description) },
    { sec:'Camadas',      lbl:'Altura camada',         fn: p => v(p.layer_height,'mm') },
    { sec:'Camadas',      lbl:'Altura 1ª camada',      fn: p => v(p.initial_layer_height,'mm') },
    { sec:'Camadas',      lbl:'Paredes',               fn: p => v(p.wall_loops) },
    { sec:'Preenchimento',lbl:'Densidade',             fn: p => v(p.sparse_infill_density) },
    { sec:'Preenchimento',lbl:'Padrão',                fn: p => v(p.sparse_infill_pattern) },
    { sec:'Velocidades',  lbl:'Parede interna',        fn: p => v(p.inner_wall_speed,' mm/s') },
    { sec:'Velocidades',  lbl:'Parede externa',        fn: p => v(p.outer_wall_speed,' mm/s') },
    { sec:'Velocidades',  lbl:'Preenchimento',         fn: p => v(p.sparse_infill_speed,' mm/s') },
    { sec:'Velocidades',  lbl:'Deslocamento',          fn: p => v(p.travel_speed,' mm/s') },
    { sec:'Acelerações',  lbl:'Padrão',                fn: p => v(p.default_acceleration,' mm/s²') },
    { sec:'Acelerações',  lbl:'Parede interna',        fn: p => v(p.inner_wall_acceleration,' mm/s²') },
    { sec:'Acelerações',  lbl:'Parede externa',        fn: p => v(p.outer_wall_acceleration,' mm/s²') },
    { sec:'Suporte',      lbl:'Ativo',                 fn: p => boolIcon(p.enable_support) },
    { sec:'Suporte',      lbl:'Tipo',                  fn: p => v(p.support_type) },
    { sec:'Perfil CP',    lbl:'Download',              fn: p => `<a class="dl-link" href="${p.download_url}">↓ Creality Print</a> · <a class="dl-link" href="${p.orca_download_url}">↓ Orca Slicer</a>` },
];

function renderProcessCompare() {
    if (!processCompareTableWrap) return;
    if (!comparedProcessProfiles.size) {
        processCompareTableWrap.style.display = 'none';
        processComparePlaceholder.style.display = '';
        return;
    }
    processCompareTableWrap.style.display = '';
    processComparePlaceholder.style.display = 'none';

    const profiles = [...comparedProcessProfiles.values()].sort((a, b) =>
        typeRank(a.profile_type) - typeRank(b.profile_type) ||
        (a.profile_name || '').localeCompare(b.profile_name || '')
    );

    const headers = profiles.map(p => {
        const typeLabel = p.profile_type
            ? p.profile_type.charAt(0).toUpperCase() + p.profile_type.slice(1)
            : '';
        return `
        <th>
            <div class="col-hdr">
                <span class="col-hdr-name">${p.profile_name}</span>
                <span class="col-hdr-sub">${typeLabel} · ${currentMaterial || ''}</span>
                <button class="remove-col" data-pid="${p.profile_id}" title="Remover coluna">✕</button>
            </div>
        </th>`;
    }).join('');

    let lastSec = null;
    const bodyRows = PROCESS_CMP_ROWS.map(row => {
        let out = '';
        if (row.sec !== lastSec) {
            lastSec = row.sec;
            out += `<tr class="sec-div"><td colspan="${profiles.length+1}">${row.sec}</td></tr>`;
        }
        const cells = profiles.map(p => `<td>${row.fn(p)}</td>`).join('');
        out += `<tr><td class="row-lbl">${row.lbl}</td>${cells}</tr>`;
        return out;
    }).join('');

    processCompareTable.innerHTML = `
        <thead><tr><th class="corner"></th>${headers}</tr></thead>
        <tbody>${bodyRows}</tbody>`;

    processCompareTable.querySelectorAll('.remove-col').forEach(btn => {
        btn.addEventListener('click', () => {
            comparedProcessProfiles.delete(Number(btn.dataset.pid));
            syncProcessHighlights();
            renderProcessCompare();
        });
    });
}

function renderProcessTable(material) {
    if (!processTableContainer) return;
    currentMaterial = material;
    const matData = processTreeData[material] || {};
    renderMaterialCard(material);

    const rows = (matData.profiles || []).slice().sort((a, b) =>
        (a.nozzle_size || 0) - (b.nozzle_size || 0) ||
        (a.layer_height || 0) - (b.layer_height || 0) ||
        typeRank(a.profile_type) - typeRank(b.profile_type)
    );

    if (!rows.length) {
        processTableContainer.innerHTML = '<div class="empty">Nenhum perfil de processo para este material.</div>';
        if (processCurrentLabel) processCurrentLabel.textContent = material;
        return;
    }

    if (processCurrentLabel) processCurrentLabel.textContent = `${material} — ${rows.length} perfis`;

    const tbody = rows.map(row => {
        const sel = comparedProcessProfiles.has(row.profile_id);
        return `
        <tr class="row-item${sel ? ' row-selected' : ''}" data-pid="${row.profile_id}">
            <td class="checkbox-cell"><input type="checkbox" class="row-check" data-pid="${row.profile_id}" ${sel?'checked':''}></td>
            <td><strong>${v(row.profile_name)}</strong></td>
            <td>${typeChip(row.profile_type)}</td>
            <td class="mono">${v(row.layer_height,'mm')}</td>
            <td class="mono">${v(row.inner_wall_speed,' mm/s')}</td>
            <td class="mono">${v(row.sparse_infill_density)}</td>
            <td class="mono">${v(row.wall_loops)}</td>
            <td><a class="dl-link" href="${row.download_url}" onclick="event.stopPropagation()">↓ CP</a> · <a class="dl-link" href="${row.orca_download_url}" onclick="event.stopPropagation()">↓ Orca</a></td>
        </tr>
        <tr class="detail-row" id="proc-det-${row.profile_id}" style="display:none">
            <td colspan="8"></td>
        </tr>`;
    }).join('');

    processTableContainer.innerHTML = `
        <div class="table-wrap">
        <table>
            <thead><tr>
                <th class="checkbox-cell"><input type="checkbox" id="proc-tog-all"></th>
                <th>Nome do perfil</th>
                <th>Tipo</th>
                <th>Altura camada</th>
                <th>Vel. parede</th>
                <th>Preenchimento</th>
                <th>Paredes</th>
                <th>Download</th>
            </tr></thead>
            <tbody>${tbody}</tbody>
        </table>
        </div>`;

    const togAll = document.getElementById('proc-tog-all');
    togAll?.addEventListener('change', e => {
        rows.forEach(row => {
            if (e.target.checked) comparedProcessProfiles.set(row.profile_id, row);
            else comparedProcessProfiles.delete(row.profile_id);
        });
        syncProcessHighlights();
        renderProcessCompare();
    });

    processTableContainer.querySelectorAll('.row-item').forEach(tr => {
        const pid = Number(tr.dataset.pid);

        const toggleCompare = () => {
            const profile = rows.find(r => r.profile_id === pid);
            if (comparedProcessProfiles.has(pid)) comparedProcessProfiles.delete(pid);
            else if (profile) comparedProcessProfiles.set(pid, profile);
            syncProcessHighlights();
            renderProcessCompare();
        };

        // Checkbox click adds/removes from comparison
        const cb = tr.querySelector('.row-check');
        if (cb) {
            cb.addEventListener('change', e => {
                e.stopPropagation();
                toggleCompare();
            });
        }

        tr.addEventListener('click', e => {
            if (e.target.tagName === 'A') return;
            if (e.target.tagName === 'INPUT') return; // handled by checkbox listener
            toggleCompare();

            const detRow = document.getElementById(`proc-det-${pid}`);
            if (detRow) {
                const isOpen = detRow.style.display !== 'none';
                if (isOpen) {
                    detRow.style.display = 'none';
                } else {
                    detRow.querySelector('td').innerHTML = renderProcessDetailPanel(
                        rows.find(r => r.profile_id === pid), material
                    );
                    detRow.style.display = '';
                }
            }
            if (comparedProcessProfiles.size === 1) {
                document.getElementById('process-compare-panel')
                    ?.scrollIntoView({ behavior:'smooth', block:'start' });
            }
        });
    });
}

// ─── View switching ───────────────────────────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentView = btn.dataset.view;

        document.querySelectorAll('.view-content').forEach(v => v.classList.remove('active'));
        document.getElementById(`${currentView}-view`)?.classList.add('active');

        const filamentNav = document.getElementById('filament-nav');
        const processNav = document.getElementById('process-nav');
        if (filamentNav) filamentNav.style.display = currentView === 'filaments' ? 'block' : 'none';
        if (processNav) processNav.style.display = currentView === 'process' ? 'block' : 'none';
    });
});

materialBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        materialBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderProcessTable(btn.dataset.material);
    });
});

processClearCompareBtn?.addEventListener('click', () => {
    comparedProcessProfiles.clear();
    syncProcessHighlights();
    renderProcessCompare();
});

processDownloadBtn?.addEventListener('click', () => {
    if (!currentMaterial) return;
    window.location.href = `/download/process/${encodeURIComponent(currentMaterial)}`;
});

// Auto-select first material on load
const firstMaterialBtn = document.querySelector('.material-btn');
if (firstMaterialBtn) {
    renderProcessTable(firstMaterialBtn.dataset.material);
}
renderProcessCompare();



// ═══════════════════════════════════════════════════════════════════════════════
// ─── Simulation view — Cascading selectors ───────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

let simData = { processes: [], filaments: [] };
const simResult = document.getElementById('sim-result');

// Material characteristics and comparison insights
const MATERIAL_INFO = {
    PLA: {
        name: 'PLA',
        strengths: 'Fácil de imprimir, boa resolução, baixo warping',
        weaknesses: 'Baixa resistência térmica (~55°C), frágil sob impacto',
        best_for: 'Protótipos, modelos visuais, peças decorativas',
        temp_resistance: 'Baixa (deforma acima de 55°C)',
        mechanical: 'Rígido mas quebradiço',
    },
    PETG: {
        name: 'PETG',
        strengths: 'Boa resistência mecânica e química, flexível, durável',
        weaknesses: 'Stringing, requer mais cooling, acabamento menos preciso que PLA',
        best_for: 'Peças funcionais, mecânicas, uso externo coberto',
        temp_resistance: 'Moderada (~75°C)',
        mechanical: 'Flexível e resistente a impacto',
    },
    ABS: {
        name: 'ABS',
        strengths: 'Alta resistência térmica, boa resistência a impacto, pós-processável com acetona',
        weaknesses: 'Warping severo, requer câmara fechada, emite odor',
        best_for: 'Peças automotivas, carcaças, peças que aquecem',
        temp_resistance: 'Alta (~100°C)',
        mechanical: 'Resistente a impacto e flexão',
    },
    ASA: {
        name: 'ASA',
        strengths: 'Resistente a UV e intempéries, similar ao ABS sem amarelamento',
        weaknesses: 'Mesmo warping do ABS, requer câmara fechada',
        best_for: 'Peças externas expostas ao sol',
        temp_resistance: 'Alta (~100°C)',
        mechanical: 'Similar ao ABS com UV resistance',
    },
    TPU: {
        name: 'TPU',
        strengths: 'Flexível, absorve impacto, resistente a abrasão',
        weaknesses: 'Muito lento, difícil de imprimir, stringing extremo',
        best_for: 'Capas de celular, amortecedores, juntas, vedações',
        temp_resistance: 'Moderada (~60°C)',
        mechanical: 'Elástico (95A Shore)',
    },
    'PLA-CF': {
        name: 'PLA com Fibra de Carbono',
        strengths: 'Alta rigidez, baixo peso, aspecto profissional matte',
        weaknesses: 'Abrasivo (desgasta nozzle de latão), frágil, requer nozzle endurecido',
        best_for: 'Peças estruturais leves, drones, chassis',
        temp_resistance: 'Baixa (~55°C, igual PLA)',
        mechanical: 'Muito rígido mas não flexível',
    },
    'PETG-CF': {
        name: 'PETG com Fibra de Carbono',
        strengths: 'Rigidez + resistência térmica do PETG, lightweight',
        weaknesses: 'Abrasivo, caro, difícil de imprimir bem',
        best_for: 'Peças estruturais com resistência térmica',
        temp_resistance: 'Moderada (~75°C)',
        mechanical: 'Rígido com boa resistência térmica',
    },
};

function getMaterialInsights(matA, matB) {
    if (!matA || !matB || matA === matB) return '';
    const infoA = MATERIAL_INFO[matA] || { name: matA };
    const infoB = MATERIAL_INFO[matB] || { name: matB };

    return `
    <div class="info-block" style="margin-bottom:16px;">
        <div class="info-block-header">Diferença de materiais: ${infoA.name} vs ${infoB.name}</div>
        <div style="padding:12px; display:grid; grid-template-columns:1fr 1fr; gap:12px; font-size:.82rem;">
            <div>
                <strong style="color:var(--blue)">${infoA.name}</strong>
                <div style="color:var(--muted); margin-top:4px;">
                    <div><strong>Pontos fortes:</strong> ${infoA.strengths || '—'}</div>
                    <div><strong>Limitações:</strong> ${infoA.weaknesses || '—'}</div>
                    <div><strong>Melhor para:</strong> ${infoA.best_for || '—'}</div>
                    <div><strong>Térmica:</strong> ${infoA.temp_resistance || '—'}</div>
                    <div><strong>Mecânica:</strong> ${infoA.mechanical || '—'}</div>
                </div>
            </div>
            <div>
                <strong style="color:var(--blue)">${infoB.name}</strong>
                <div style="color:var(--muted); margin-top:4px;">
                    <div><strong>Pontos fortes:</strong> ${infoB.strengths || '—'}</div>
                    <div><strong>Limitações:</strong> ${infoB.weaknesses || '—'}</div>
                    <div><strong>Melhor para:</strong> ${infoB.best_for || '—'}</div>
                    <div><strong>Térmica:</strong> ${infoB.temp_resistance || '—'}</div>
                    <div><strong>Mecânica:</strong> ${infoB.mechanical || '—'}</div>
                </div>
            </div>
        </div>
        <div style="padding:0 12px 12px; font-size:.78rem; color:var(--orange);">
            ⚠️ Materiais diferentes têm propriedades físicas distintas — a comparação de velocidades não reflete resistência, flexibilidade ou resistência térmica da peça final.
        </div>
    </div>`;
}

// Speed parameter explanations
const SPEED_EXPLAIN = {
    inner_wall_speed: { name: 'Parede interna', faster: 'Impressão mais rápida, pode vibrar mais', slower: 'Mais lento mas paredes mais precisas' },
    outer_wall_speed: { name: 'Parede externa', faster: 'Menos tempo, acabamento pode piorar', slower: 'Melhor acabamento superficial' },
    sparse_infill_speed: { name: 'Preenchimento', faster: 'Infill mais rápido (não visível)', slower: 'Infill mais lento (melhor adesão)' },
    internal_solid_infill_speed: { name: 'Infill sólido', faster: 'Camadas sólidas internas mais rápidas', slower: 'Melhor adesão entre camadas' },
    top_surface_speed: { name: 'Superfície topo', faster: 'Topo mais rápido, pode ter gaps', slower: 'Superfície superior mais lisa' },
    initial_layer_speed: { name: '1ª camada', faster: 'Primeira camada mais rápida, risco de descolamento', slower: 'Melhor adesão à mesa' },
    travel_speed: { name: 'Deslocamento', faster: 'Menos tempo morto entre movimentos', slower: 'Menos vibrações em movimentos longos' },
    support_speed: { name: 'Suporte', faster: 'Suporte impresso mais rápido', slower: 'Suporte mais preciso (remoção mais fácil)' },
    gap_infill_speed: { name: 'Gap infill', faster: 'Gaps estreitos preenchidos mais rápido', slower: 'Preenchimento mais consistente' },
};

// ─── Cascading logic for one column ──────────────────────────────────────────
function setupSimColumn(prefix) {
    const layerSel = document.getElementById(`sim-${prefix}-layer`);
    const profileSel = document.getElementById(`sim-${prefix}-profile`);
    const materialSel = document.getElementById(`sim-${prefix}-material`);
    const processInfo = document.getElementById(`sim-${prefix}-process-info`);
    const mfrSel = document.getElementById(`sim-${prefix}-manufacturer`);
    const filamentSel = document.getElementById(`sim-${prefix}-filament`);
    const filamentInfo = document.getElementById(`sim-${prefix}-filament-info`);

    if (!layerSel) return;

    const fmtLH = (lh) => Number(lh).toFixed(2);

    // ── Populate layer heights ──
    const layers = [...new Set(simData.processes.map(p => p.layer_height))].sort((a,b) => a-b);
    layerSel.innerHTML = '<option value="">Altura...</option>' +
        layers.map(l => `<option value="${l}">${fmtLH(l)}mm</option>`).join('');

    // ── Helper: update process info box ──
    function updateProcessInfo() {
        const lh = parseFloat(layerSel.value);
        const type = profileSel.value;
        const mat = materialSel.value;

        if (!lh || !type || !mat) { processInfo.style.display = 'none'; return; }

        const match = simData.processes.find(p =>
            parseFloat(p.layer_height) === lh && p.profile_type === type && p.material === mat
        );

        if (match) {
            processInfo.style.display = 'block';
            processInfo.innerHTML = `
                <div class="match-name">${match.profile_name}</div>
                <div class="match-detail">Perfil de processo selecionado</div>
            `;
        } else {
            processInfo.style.display = 'block';
            processInfo.innerHTML = `
                <div class="match-name" style="color:var(--orange)">Combinação não disponível</div>
                <div class="match-detail">Não existe perfil para ${fmtLH(lh)}mm ${type} ${mat}</div>
            `;
        }
    }

    // ── Helper: update filament selectors based on material ──
    function updateFilamentCascade() {
        const mat = materialSel.value;
        mfrSel.disabled = !mat;
        filamentSel.disabled = true;
        filamentSel.innerHTML = '<option value="">Filamento...</option>';
        filamentInfo.style.display = 'none';

        if (!mat) {
            mfrSel.innerHTML = '<option value="">Fabricante...</option>';
            return;
        }

        const matching = simData.filaments.filter(f => f.material === mat);
        const mfrs = [...new Set(matching.map(f => f.manufacturer))].sort();
        mfrSel.innerHTML = '<option value="">Fabricante...</option>' +
            mfrs.map(m => `<option value="${m}">${m}</option>`).join('');
        mfrSel.disabled = false;
    }

    // ── Layer height change → populate profile types ──
    layerSel.addEventListener('change', () => {
        const lh = parseFloat(layerSel.value);
        profileSel.disabled = !lh;
        materialSel.disabled = true;
        materialSel.innerHTML = '<option value="">Material...</option>';
        processInfo.style.display = 'none';
        updateFilamentCascade();

        if (!lh) {
            profileSel.innerHTML = '<option value="">Perfil...</option>';
            trySimulate();
            return;
        }

        const matching = simData.processes.filter(p => parseFloat(p.layer_height) === lh);
        const types = [...new Set(matching.map(p => p.profile_type))].sort((a,b) => {
            const order = ['fast','standard','strong','detail','safe'];
            return order.indexOf(a) - order.indexOf(b);
        });
        profileSel.innerHTML = '<option value="">Perfil...</option>' +
            types.map(t => `<option value="${t}">${t.charAt(0).toUpperCase()+t.slice(1)}</option>`).join('');
        profileSel.disabled = false;
        trySimulate();
    });

    // ── Profile type change → populate materials ──
    profileSel.addEventListener('change', () => {
        const lh = parseFloat(layerSel.value);
        const type = profileSel.value;
        materialSel.disabled = !type;
        processInfo.style.display = 'none';
        updateFilamentCascade();

        if (!lh || !type) {
            materialSel.innerHTML = '<option value="">Material...</option>';
            trySimulate();
            return;
        }

        const matching = simData.processes.filter(p =>
            parseFloat(p.layer_height) === lh && p.profile_type === type
        );
        const mats = [...new Set(matching.map(p => p.material))].sort();
        materialSel.innerHTML = '<option value="">Material...</option>' +
            mats.map(m => `<option value="${m}">${m}</option>`).join('');
        materialSel.disabled = false;
        trySimulate();
    });

    // ── Material change → update process info + filament cascade ──
    materialSel.addEventListener('change', () => {
        updateProcessInfo();
        updateFilamentCascade();
        trySimulate();
    });

    // ── Manufacturer change → populate filaments ──
    mfrSel.addEventListener('change', () => {
        const mat = materialSel.value;
        const mfr = mfrSel.value;
        filamentSel.disabled = !mfr;
        filamentInfo.style.display = 'none';

        if (!mfr) {
            filamentSel.innerHTML = '<option value="">Filamento...</option>';
            trySimulate();
            return;
        }

        const matching = simData.filaments.filter(f => f.material === mat && f.manufacturer === mfr);
        filamentSel.innerHTML = '<option value="">Filamento...</option>' +
            matching.map(f => `<option value="${f.id}">${f.commercial_name} (MVS ${f.max_volumetric_speed})</option>`).join('');
        filamentSel.disabled = false;
        trySimulate();
    });

    // ── Filament selected → show info ──
    filamentSel.addEventListener('change', () => {
        const fid = parseInt(filamentSel.value);
        if (!fid) { filamentInfo.style.display = 'none'; trySimulate(); return; }

        const fil = simData.filaments.find(f => f.id === fid);
        if (fil) {
            filamentInfo.style.display = 'block';
            filamentInfo.innerHTML = `
                <div class="match-name">${fil.manufacturer} — ${fil.commercial_name}</div>
                <div class="match-detail">MVS: ${fil.max_volumetric_speed} mm³/s · Material: ${fil.material}</div>
            `;
        }
        trySimulate();
    });
}

// ─── Get selected IDs from a column ─────────────────────────────────────────
function getSimSelection(prefix) {
    const layerSel = document.getElementById(`sim-${prefix}-layer`);
    const profileSel = document.getElementById(`sim-${prefix}-profile`);
    const materialSel = document.getElementById(`sim-${prefix}-material`);
    const filamentSel = document.getElementById(`sim-${prefix}-filament`);

    if (!layerSel) return null;

    const lh = parseFloat(layerSel.value);
    const type = profileSel.value;
    const mat = materialSel.value;
    const fid = parseInt(filamentSel.value);

    if (!lh || !type || !mat || !fid) return null;

    // Find process matching all 3 criteria
    const process = simData.processes.find(p =>
        parseFloat(p.layer_height) === lh && p.profile_type === type && p.material === mat
    );
    if (!process) return null;

    return { processId: process.id, filamentId: fid };
}

// ─── Auto-simulate when selection is complete ────────────────────────────────
async function trySimulate() {
    const selA = getSimSelection('a');
    if (!selA) {
        if (simResult) simResult.innerHTML = '<div class="empty">Selecione altura, perfil, material e filamento na Combinação A para simular.</div>';
        return;
    }

    const rA = await fetch(`/api/simulate?process_id=${selA.processId}&filament_id=${selA.filamentId}`);
    if (!rA.ok) { simResult.innerHTML = '<div class="empty">Erro ao simular.</div>'; return; }
    const dataA = await rA.json();

    let dataB = null;
    const selB = getSimSelection('b');
    if (selB) {
        const rB = await fetch(`/api/simulate?process_id=${selB.processId}&filament_id=${selB.filamentId}`);
        if (rB.ok) dataB = await rB.json();
    }

    renderSimResult(dataA, dataB);
}

// ─── Render simulation result ────────────────────────────────────────────────
function formatSpeed(val, capped) {
    if (val === undefined || val === null) return '—';
    const cls = capped ? 'val-capped' : 'val-normal';
    const suffix = capped ? ' ⚡' : '';
    return `<span class="${cls}">${Math.round(val)} mm/s${suffix}</span>`;
}

function diffCell(valA, valB, field) {
    if (valA === undefined || valB === undefined) return '<td class="diff-same">—</td>';
    const diff = valB - valA;
    const pct = valA > 0 ? Math.round((diff / valA) * 100) : 0;
    const info = SPEED_EXPLAIN[field] || {};

    if (Math.abs(pct) < 2) return `<td><span class="diff-same">≈ igual</span></td>`;

    const cls = diff > 0 ? 'diff-better' : 'diff-worse';
    const arrow = diff > 0 ? '▲' : '▼';
    const explain = diff > 0 ? (info.faster || '') : (info.slower || '');
    return `<td><span class="${cls}">${arrow} ${Math.abs(pct)}%</span>${explain ? `<br><span class="diff-explain">${explain}</span>` : ''}</td>`;
}

function renderSimResult(a, b) {
    const speedFields = Object.keys(SPEED_EXPLAIN);
    const hasB = !!b;

    const colBHeader = hasB
        ? `<th>${b.process.name}<br><span style="font-weight:400;font-size:.72rem;color:var(--muted)">${b.filament.manufacturer} ${b.filament.commercial_name} (MVS ${b.filament.mvs})</span></th><th>Diferença</th>`
        : '';

    const speedRows = speedFields.map(field => {
        const sA = a.simulation.speeds[field];
        const sB = hasB ? (b.simulation.speeds[field] || {}) : null;
        if (!sA) return '';
        const info = SPEED_EXPLAIN[field];
        const colA = `<td>${formatSpeed(sA.effective, sA.capped)}${sA.capped ? `<br><span class="diff-explain">alvo: ${sA.target} → cap MVS</span>` : ''}</td>`;
        const colB = hasB && sB.effective !== undefined
            ? `<td>${formatSpeed(sB.effective, sB.capped)}${sB.capped ? `<br><span class="diff-explain">alvo: ${sB.target} → cap MVS</span>` : ''}</td>`
            : (hasB ? '<td>—</td>' : '');
        const colDiff = hasB ? diffCell(sA.effective, sB?.effective, field) : '';
        return `<tr><td class="param-name">${info.name}</td>${colA}${colB}${colDiff}</tr>`;
    }).join('');

    const structFields = [
        { key: 'wall_loops', name: 'Paredes', unit: '',
          explain: (a,b) => parseInt(a) > parseInt(b) ? 'Mais paredes = peça mais resistente, mais tempo' : 'Menos paredes = mais rápido, menos resistência lateral' },
        { key: 'sparse_infill_density', name: 'Infill', unit: '',
          explain: (a,b) => parseInt(a) > parseInt(b) ? 'Mais preenchimento = mais resistente e pesado' : 'Menos preenchimento = mais leve e rápido' },
        { key: 'sparse_infill_pattern', name: 'Padrão infill', unit: '',
          explain: (a,b) => {
            const desc = { gyroid:'forte em todas direções', grid:'rápido, forte em X/Y', honeycomb:'bom equilíbrio', line:'mais rápido, fraco' };
            return `A: ${desc[a]||a} · B: ${desc[b]||b}`;
          }},
        { key: 'top_shell_layers', name: 'Camadas topo', unit: '',
          explain: (a,b) => parseInt(a) > parseInt(b) ? 'Mais camadas sólidas no topo = superfície mais lisa e resistente' : 'Menos camadas topo = mais rápido, pode ter gaps visíveis' },
        { key: 'bottom_shell_layers', name: 'Camadas base', unit: '',
          explain: (a,b) => parseInt(a) > parseInt(b) ? 'Mais camadas na base = fundo mais forte' : 'Menos camadas base = mais rápido' },
        { key: 'wall_sequence', name: 'Sequência paredes', unit: '',
          explain: (a,b) => {
            const desc = { 'outer wall/inner wall':'outer-first = melhor acabamento externo', 'inner wall/outer wall':'inner-first = mais rápido, melhor dimensional' };
            return `A: ${desc[a]||a} · B: ${desc[b]||b}`;
          }},
        { key: 'seam_position', name: 'Costura', unit: '',
          explain: (a,b) => {
            const desc = { aligned:'alinhada = costura vertical visível mas previsível', nearest:'mais próximo = mais rápido, costura dispersa', back:'atrás = escondida mas mais lento' };
            return `A: ${desc[a]||a} · B: ${desc[b]||b}`;
          }},
        { key: 'default_acceleration', name: 'Aceleração padrão', unit: ' mm/s²',
          explain: (a,b) => parseFloat(a) > parseFloat(b) ? 'Aceleração maior = atinge velocidade mais rápido, pode vibrar' : 'Aceleração menor = movimentos mais suaves, menos artefatos' },
        { key: 'inner_wall_acceleration', name: 'Aceleração paredes int.', unit: ' mm/s²',
          explain: (a,b) => parseFloat(a) > parseFloat(b) ? 'Paredes internas aceleram mais = tempo reduzido' : 'Menos aceleração nas paredes = menos ringing' },
        { key: 'outer_wall_acceleration', name: 'Aceleração paredes ext.', unit: ' mm/s²',
          explain: (a,b) => parseFloat(a) > parseFloat(b) ? 'Mais aceleração = pode gerar artefatos na superfície' : 'Menos aceleração = superfície externa mais limpa' },
    ];

    const structRows = structFields.map(({ key, name, unit, explain }) => {
        const vA = a.process[key];
        const vB = hasB ? b.process[key] : null;
        const colA = `<td>${vA != null ? vA + unit : '—'}</td>`;
        const colB = hasB ? `<td>${vB != null ? vB + unit : '—'}</td>` : '';
        let colDiff = '';
        if (hasB) {
            if (String(vA) === String(vB)) {
                colDiff = '<td><span class="diff-same">≈ igual</span></td>';
            } else {
                const explanation = explain ? explain(vA, vB) : '';
                colDiff = `<td><span class="diff-worse">≠</span> <span class="diff-explain">${explanation}</span></td>`;
            }
        }
        return `<tr><td class="param-name">${name}</td>${colA}${colB}${colDiff}</tr>`;
    }).join('');

    const filFields = [
        { key: 'mvs', name: 'MVS', unit: ' mm³/s',
          explain: (a,b) => parseFloat(a) > parseFloat(b) ? 'MVS maior = filamento aguenta mais fluxo, menos limitações de velocidade' : 'MVS menor = filamento limita mais as velocidades, impressão mais lenta' },
        { key: 'nozzle_temp', name: 'Nozzle', unit: '°C',
          explain: (a,b) => parseInt(a) > parseInt(b) ? 'Temperatura maior = material precisa de mais calor para fluir' : 'Temperatura menor = material funde mais fácil' },
        { key: 'bed_temp', name: 'Mesa', unit: '°C',
          explain: (a,b) => parseInt(a) > parseInt(b) ? 'Mesa mais quente = melhor adesão, necessário para esse material' : 'Mesa mais fria = material adere com menos calor' },
        { key: 'flow_ratio', name: 'Flow ratio', unit: '',
          explain: (a,b) => parseFloat(a) > parseFloat(b) ? 'Flow maior = filamento precisa extrudar mais para compensar' : 'Flow menor = filamento flui bem com menos compensação' },
    ];

    const filRows = filFields.map(({ key, name, unit, explain }) => {
        const vA = a.filament[key];
        const vB = hasB ? b.filament[key] : null;
        const colA = `<td>${vA != null ? vA + unit : '—'}</td>`;
        const colB = hasB ? `<td>${vB != null ? vB + unit : '—'}</td>` : '';
        let colDiff = '';
        if (hasB) {
            if (String(vA) === String(vB)) {
                colDiff = '<td><span class="diff-same">≈ igual</span></td>';
            } else {
                const explanation = explain ? explain(vA, vB) : '';
                colDiff = `<td><span class="diff-worse">≠</span> <span class="diff-explain">${explanation}</span></td>`;
            }
        }
        return `<tr><td class="param-name">${name}</td>${colA}${colB}${colDiff}</tr>`;
    }).join('');

    const capCountA = Object.values(a.simulation.speeds).filter(s => s.capped).length;
    const capCountB = hasB ? Object.values(b.simulation.speeds).filter(s => s.capped).length : 0;

    const summary = `
        <div style="display:grid; grid-template-columns:${hasB ? '1fr 1fr' : '1fr'}; gap:12px; margin-bottom:16px;">
            <div class="info-block">
                <div class="info-block-header">A — ${a.process.profile_type} + ${a.filament.commercial_name}</div>
                <div style="padding:10px 12px; font-size:.82rem; color:var(--muted);">
                    Cap volumétrico: <strong style="color:var(--text)">${Math.round(a.simulation.max_speed_from_mvs)} mm/s</strong> (MVS ${a.filament.mvs} @ ${a.process.layer_height}mm)<br>
                    Velocidades limitadas: <strong style="color:${capCountA > 0 ? 'var(--orange)' : 'var(--green)'}">${capCountA} de ${Object.keys(a.simulation.speeds).length}</strong>
                </div>
            </div>
            ${hasB ? `
            <div class="info-block">
                <div class="info-block-header">B — ${b.process.profile_type} + ${b.filament.commercial_name}</div>
                <div style="padding:10px 12px; font-size:.82rem; color:var(--muted);">
                    Cap volumétrico: <strong style="color:var(--text)">${Math.round(b.simulation.max_speed_from_mvs)} mm/s</strong> (MVS ${b.filament.mvs} @ ${b.process.layer_height}mm)<br>
                    Velocidades limitadas: <strong style="color:${capCountB > 0 ? 'var(--orange)' : 'var(--green)'}">${capCountB} de ${Object.keys(b.simulation.speeds).length}</strong>
                </div>
            </div>` : ''}
        </div>`;

    const numCols = hasB ? 4 : 2;

    // Material comparison insights (when materials differ)
    const materialInsights = hasB ? getMaterialInsights(a.filament.material, b.filament.material) : '';

    simResult.innerHTML = `
        ${materialInsights}
        ${summary}
        <div class="table-wrap">
        <table class="sim-table">
            <thead><tr>
                <th style="min-width:140px">Parâmetro</th>
                <th>${a.process.name}<br><span style="font-weight:400;font-size:.72rem;color:var(--muted)">${a.filament.manufacturer} ${a.filament.commercial_name} (MVS ${a.filament.mvs})</span></th>
                ${colBHeader}
            </tr></thead>
            <tbody>
                <tr class="sim-section"><td colspan="${numCols}">Velocidades efetivas</td></tr>
                ${speedRows}
                <tr class="sim-section"><td colspan="${numCols}">Estrutura da peça</td></tr>
                ${structRows}
                <tr class="sim-section"><td colspan="${numCols}">Filamento</td></tr>
                ${filRows}
            </tbody>
        </table>
        </div>`;
}


// ─── Init simulation ─────────────────────────────────────────────────────────
async function initSimulation() {
    try {
        const r = await fetch('/api/simulation-options');
        simData = await r.json();
        setupSimColumn('a');
        setupSimColumn('b');

        // Pre-select 0.20mm + Standard for both columns
        for (const prefix of ['a', 'b']) {
            const layerSel = document.getElementById(`sim-${prefix}-layer`);
            if (!layerSel) continue;

            // Select 0.20mm
            const opt020 = [...layerSel.options].find(o => parseFloat(o.value) === 0.2);
            if (opt020) {
                layerSel.value = opt020.value;
                layerSel.dispatchEvent(new Event('change'));
            }

            // Select Standard profile type
            const profileSel = document.getElementById(`sim-${prefix}-profile`);
            if (profileSel) {
                const optStd = [...profileSel.options].find(o => o.value === 'standard');
                if (optStd) {
                    profileSel.value = optStd.value;
                    profileSel.dispatchEvent(new Event('change'));
                }
            }
        }
    } catch (e) {
        console.error('Failed to load simulation options', e);
    }
}
initSimulation();
