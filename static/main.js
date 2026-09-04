// ─── State ────────────────────────────────────────────────────────────────────
const treeData = window.treeData || {};
const processTreeData = window.processTreeData || {};
let currentManufacturer = null;
let currentMaterial = null;
let currentView = 'inventory';
const comparedProfiles = new Map(); // profileId -> enriched profile object
const comparedProcessProfiles = new Map(); // profileId -> process profile object

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const tableContainer     = document.getElementById('table-container');
const currentLabel       = document.getElementById('current-label');
const mfrCard            = document.getElementById('mfr-card');
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
    const color = pct >= 85 ? 'var(--green)' : pct >= 70 ? 'var(--yellow)' : 'var(--red)';
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
                    ${vr.recommended_use ? `<span class="variant-meta" style="color:var(--muted)">${vr.recommended_use}</span>` : ''}
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
                <div class="info-cell wide"><span class="lbl">Recomendação</span><span class="v" style="color:var(--green)">${v(profile.recommendation)}</span></div>
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
                <div class="info-cell"><span class="lbl">Status</span><span class="v">${profile.active ? '<span class="bool-yes">Ativo</span>' : '<span style="color:var(--red)">Inativo</span>'}</span></div>
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
    // Mantém o combo em sincronia caso renderTable seja chamado programaticamente.
    if (mfrSelect && mfrSelect.value !== manufacturer) mfrSelect.value = manufacturer;
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
            rows.push({ ...p, _mat: mat, _mfr: manufacturer });
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
    { sec:'Produto',      lbl:'Fabricante',        fn: p => v(p._mfr) },
    { sec:'Produto',      lbl:'Material',         fn: p => `<span class="chip chip-${p._mat}">${p._mat}</span>` },
    { sec:'Produto',      lbl:'Nome comercial',    fn: p => v(p.commercial_name) },
    { sec:'Produto',      lbl:'Linha',             fn: p => v(p.line) },
    { sec:'Produto',      lbl:'Posicionamento',    fn: p => v(p.line_positioning) },
    { sec:'Produto',      lbl:'Uso alvo',          fn: p => v(p.line_target_use) },
    { sec:'Produto',      lbl:'Acabamento',        fn: p => v(p.surface_finish) },
    { sec:'Produto',      lbl:'Recomendação',      fn: p => `<span style="color:var(--green);font-size:.78rem">${v(p.recommendation)}</span>` },

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
                <span class="col-hdr-sub">${p._mat} · ${p._mfr||p.manufacturer_name||''}</span>
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

// ─── Manufacturer selector (combo no topo da tela de Filamentos) ───────────────
const mfrSelect = document.getElementById('mfr-select');
mfrSelect?.addEventListener('change', () => {
    const mfr = mfrSelect.value;
    if (!mfr) return;
    renderTable(mfr);
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
            comparedProfiles.set(p.profile_id, { ...p, _mat: mat, _mfr: currentManufacturer });
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
                <div class="info-cell"><span class="lbl">Status</span><span class="v">${profile.active ? '<span class="bool-yes">Ativo</span>' : '<span style="color:var(--red)">Inativo</span>'}</span></div>
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

// Speed score for process comparison (no filament cap — shows raw machine potential)
function calcProcessSpeedScore(profile) {
    const speedFields = [
        'inner_wall_speed', 'outer_wall_speed', 'sparse_infill_speed',
        'internal_solid_infill_speed', 'top_surface_speed', 'initial_layer_speed',
        'support_speed', 'gap_infill_speed'
    ];
    const speeds = speedFields.map(f => parseFloat(profile[f]) || 0).filter(s => s > 0);
    if (!speeds.length) return 0;
    const avg = speeds.reduce((a, b) => a + b, 0) / speeds.length;
    // Normalize: 0→0, 450→100 (K2 reference avg for max potential)
    return Math.min(100, Math.max(0, Math.round((avg / 450) * 100)));
}

function renderSpeedScore(profile) {
    const score = calcProcessSpeedScore(profile);
    const color = score >= 80 ? 'var(--green)' : score >= 60 ? 'var(--yellow)' : score >= 40 ? 'var(--orange)' : 'var(--red)';
    return `<div style="display:flex;align-items:center;gap:8px;">
        <span style="font-weight:700;color:${color};font-size:.95rem;">${score}</span>
        <div style="flex:1;height:4px;border-radius:2px;background:var(--border);min-width:40px;">
            <div style="width:${score}%;height:100%;border-radius:2px;background:${color};"></div>
        </div>
        <span style="font-size:.7rem;color:var(--muted);">/100</span>
    </div>`;
}

// Material usage score — relative indicator of how much filament a profile uses
// Based on walls, infill density, and top/bottom layers
function calcMaterialUsageScore(profile) {
    const walls = parseInt(profile.wall_loops) || 4;
    const infillStr = (profile.sparse_infill_density || '15%').replace('%', '');
    const infill = parseFloat(infillStr) || 15;
    const topLayers = parseInt(profile.top_shell_layers) || 5;
    const bottomLayers = parseInt(profile.bottom_shell_layers) || 4;

    // Weighted formula: walls contribute most, then infill, then shells
    // Normalize each component to 0-100 range based on our profile extremes:
    //   walls: 2 (economy) to 6 (strong) → normalize over 1-8 range
    //   infill: 8% (economy) to 50% (strong) → normalize over 0-60 range
    //   shells: 3+3=6 (economy/fast) to 7+6=13 (detail) → normalize over 4-16 range
    const wallScore = Math.min(100, Math.max(0, ((walls - 1) / 7) * 100));
    const infillScore = Math.min(100, Math.max(0, (infill / 60) * 100));
    const shellScore = Math.min(100, Math.max(0, (((topLayers + bottomLayers) - 4) / 12) * 100));

    // Weighted: infill has biggest volume impact, then walls, then shells
    return Math.round(infillScore * 0.50 + wallScore * 0.35 + shellScore * 0.15);
}

function renderMaterialUsageScore(profile) {
    const score = calcMaterialUsageScore(profile);
    // Invert color: LOW usage = green (good for economy), HIGH usage = orange/red
    const color = score <= 25 ? 'var(--green)' : score <= 45 ? 'var(--yellow)' : score <= 65 ? 'var(--orange)' : 'var(--red)';
    const label = score <= 20 ? 'Mínimo' : score <= 35 ? 'Baixo' : score <= 55 ? 'Moderado' : score <= 75 ? 'Alto' : 'Muito alto';
    return `<div style="display:flex;align-items:center;gap:8px;">
        <span style="font-weight:700;color:${color};font-size:.95rem;">${score}</span>
        <div style="flex:1;height:4px;border-radius:2px;background:var(--border);min-width:40px;">
            <div style="width:${score}%;height:100%;border-radius:2px;background:${color};"></div>
        </div>
        <span style="font-size:.7rem;color:var(--muted);">${label}</span>
    </div>`;
}

// Strength score for process comparison (structural resistance without material data)
function calcProcessStrengthScore(profile) {
    const walls = parseInt(profile.wall_loops) || 4;
    const infillStr = (profile.sparse_infill_density || '15%').toString().replace('%', '');
    const infill = parseFloat(infillStr) || 15;
    const pattern = profile.sparse_infill_pattern || 'grid';
    const lh = parseFloat(profile.layer_height) || 0.2;

    const strengthWalls = Math.min(100, Math.max(0, ((walls - 1) / 6) * 100));
    const strengthInfill = Math.min(100, Math.max(0, (infill / 60) * 100));
    const patternBonus = pattern.includes('gyroid') ? 10 : 0;
    const lhBonus = Math.round((0.20 - lh) * 75);

    // Without material data, use 50 as neutral base
    return Math.min(100, Math.max(0, Math.round(
        strengthWalls * 0.40 + strengthInfill * 0.35 + (50 + lhBonus + patternBonus) * 0.25
    )));
}

function renderStrengthScore(profile) {
    const score = calcProcessStrengthScore(profile);
    const color = score >= 70 ? 'var(--green)' : score >= 50 ? 'var(--yellow)' : score >= 30 ? 'var(--orange)' : 'var(--red)';
    const label = score >= 75 ? 'Alta' : score >= 55 ? 'Boa' : score >= 35 ? 'Moderada' : 'Baixa';
    return `<div style="display:flex;align-items:center;gap:8px;">
        <span style="font-weight:700;color:${color};font-size:.95rem;">${score}</span>
        <div style="flex:1;height:4px;border-radius:2px;background:var(--border);min-width:40px;">
            <div style="width:${score}%;height:100%;border-radius:2px;background:${color};"></div>
        </div>
        <span style="font-size:.7rem;color:var(--muted);">${label}</span>
    </div>`;
}

const PROCESS_CMP_ROWS = [
    { sec:'Perfil',       lbl:'Tipo',                  fn: p => typeChip(p.profile_type) },
    { sec:'Perfil',       lbl:'Descrição',             fn: p => v(p.description) },
    { sec:'Score',        lbl:'Velocidade',            fn: p => renderSpeedScore(p) },
    { sec:'Score',        lbl:'Uso de material',       fn: p => renderMaterialUsageScore(p) },
    { sec:'Score',        lbl:'Resistência',           fn: p => renderStrengthScore(p) },
    { sec:'Camadas',      lbl:'Altura camada',         fn: p => v(p.layer_height,'mm') },
    { sec:'Camadas',      lbl:'Altura 1ª camada',      fn: p => v(p.initial_layer_height,'mm') },
    { sec:'Camadas',      lbl:'Paredes',               fn: p => v(p.wall_loops) },
    { sec:'Preenchimento',lbl:'Densidade',             fn: p => v(p.sparse_infill_density) },
    { sec:'Preenchimento',lbl:'Padrão',                fn: p => v(p.sparse_infill_pattern) },
    { sec:'Velocidades',  lbl:'Parede interna',        fn: p => v(p.inner_wall_speed,' mm/s') },
    { sec:'Velocidades',  lbl:'Parede externa',        fn: p => v(p.outer_wall_speed,' mm/s') },
    { sec:'Velocidades',  lbl:'Preenchimento',         fn: p => v(p.sparse_infill_speed,' mm/s') },
    { sec:'Velocidades',  lbl:'Superfície topo',       fn: p => v(p.top_surface_speed,' mm/s') },
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

        const processNav = document.getElementById('process-nav');
        if (processNav) processNav.style.display = currentView === 'process' ? 'block' : 'none';

        if (currentView === 'inventory') loadInventory();
        if (currentView === 'prices') loadPrices();

        // Fecha o menu dropdown após escolher uma view
        closeAppsMenu();
    });
});

// ─── Apps menu dropdown ──────────────────────────────────────────────────────
const appsBtn = document.getElementById('apps-btn');
const menuDropdown = document.getElementById('menu-dropdown');

function openAppsMenu() {
    menuDropdown?.classList.add('open');
    appsBtn?.setAttribute('aria-expanded', 'true');
}
function closeAppsMenu() {
    menuDropdown?.classList.remove('open');
    appsBtn?.setAttribute('aria-expanded', 'false');
}
function toggleAppsMenu() {
    if (menuDropdown?.classList.contains('open')) closeAppsMenu();
    else openAppsMenu();
}

appsBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleAppsMenu();
});

// Fecha ao clicar fora
document.addEventListener('click', (e) => {
    if (!menuDropdown?.classList.contains('open')) return;
    if (menuDropdown.contains(e.target) || appsBtn?.contains(e.target)) return;
    closeAppsMenu();
});

// Fecha com ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAppsMenu();
});

materialBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        materialBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderProcessTable(btn.dataset.material);
        closeAppsMenu();
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

// ─── Score calculation for simulation combinations ──────────────────────────
function calcCombinationScore(data) {
    // 1. Confiabilidade (0-100): direto do perfil do filamento
    const confidence = data.filament.confidence || 50;

    // 2. Acabamento (0-100): altura de camada domina (rugosidade FDM escala com layer height).
    //    Layer height 65%, profile type 25%, wall sequence 10%.
    const profileTypeFinish = {
        detail: 100, safe: 85, standard: 70, strong: 60, economy: 45, fast: 30,
    };
    const typeScore = profileTypeFinish[data.process.profile_type] || 50;

    // Layer height (componente dominante): 0.08mm → 100, 0.28mm → 20 (linear)
    const lh = Math.max(0.08, Math.min(0.28, data.process.layer_height || 0.2));
    const lhScore = Math.round(100 - (lh - 0.08) / (0.28 - 0.08) * 80);

    // Wall sequence: outer-first melhora acabamento externo
    const wallScore = (data.process.wall_sequence || '').includes('outer') ? 100 : 50;

    const finish = Math.min(100, Math.max(0, Math.round(lhScore * 0.65 + typeScore * 0.25 + wallScore * 0.10)));

    // 3. Velocidade (0-100): quanto do potencial da máquina é aproveitado
    // Baseado na proporção de velocidades efetivas vs. máximo da K2 (500 mm/s para extrusão)
    const speeds = data.simulation.speeds;
    const extrusionFields = Object.keys(speeds).filter(k => k !== 'travel_speed');
    if (extrusionFields.length === 0) return { confidence, finish, speed: 50, overall: Math.round((confidence + finish + 50) / 3), material_usage: 40, strength: 50 };

    const avgEffective = extrusionFields.reduce((sum, k) => sum + (speeds[k].effective || 0), 0) / extrusionFields.length;
    // Normalizar: 0 mm/s → 0, 350 mm/s → 100 (referência: velocidade média alta típica na K2)
    const speed = Math.min(100, Math.max(0, Math.round((avgEffective / 350) * 100)));

    // Overall: média ponderada (velocidade 35%, acabamento 40%, confiabilidade 25%)
    const overall = Math.round(speed * 0.35 + finish * 0.40 + confidence * 0.25);

    // 4. Uso de material relativo (0-100, onde menor = mais econômico)
    const walls = parseInt(data.process.wall_loops) || 4;
    const infillStr = (data.process.sparse_infill_density || '15%').toString().replace('%', '');
    const infill = parseFloat(infillStr) || 15;
    const topLayers = parseInt(data.process.top_shell_layers) || 5;
    const bottomLayers = parseInt(data.process.bottom_shell_layers) || 4;
    const wallScore_m = Math.min(100, Math.max(0, ((walls - 1) / 7) * 100));
    const infillScore_m = Math.min(100, Math.max(0, (infill / 60) * 100));
    const shellScore_m = Math.min(100, Math.max(0, (((topLayers + bottomLayers) - 4) / 12) * 100));
    const material_usage = Math.round(infillScore_m * 0.50 + wallScore_m * 0.35 + shellScore_m * 0.15);

    // 5. Resistência mecânica (0-100) — baseado em estrutura + material
    const matStrength = parseInt(data.process.material_strength) || 50;
    // Walls: 2→20, 4→50, 6→85 (normalized over 1-7 range, weighted)
    const strengthWalls = Math.min(100, Math.max(0, ((walls - 1) / 6) * 100));
    // Infill: 8%→13, 15%→25, 50%→83 (normalized over 0-60)
    const strengthInfill = Math.min(100, Math.max(0, (infill / 60) * 100));
    // Infill pattern: gyroid = +10 bonus (isotrópico), grid = 0
    const patternBonus = (data.process.sparse_infill_pattern || '').includes('gyroid') ? 10 : 0;
    // Layer height: menor = melhor adesão Z. 0.08→+15, 0.20→0, 0.28→-8
    const lhStrengthBonus = Math.round((0.20 - lh) * 75);
    // Combine: walls 35%, infill 30%, material 25%, layer height + pattern 10%
    const strength = Math.min(100, Math.max(0, Math.round(
        strengthWalls * 0.35 + strengthInfill * 0.30 + matStrength * 0.25 +
        (50 + lhStrengthBonus + patternBonus) * 0.10
    )));

    return { confidence, finish, speed, overall, material_usage, strength };
}

function renderScoreCard(score, label, capInfo) {
    const colorFor = (val) => val >= 80 ? 'var(--green)' : val >= 60 ? 'var(--yellow)' : val >= 40 ? 'var(--orange)' : 'var(--red)';
    // Material usage: invert color (low = green = good)
    const matColorFor = (val) => val <= 25 ? 'var(--green)' : val <= 45 ? 'var(--yellow)' : val <= 65 ? 'var(--orange)' : 'var(--red)';
    const capColor = capInfo.count > 0 ? 'var(--orange)' : 'var(--green)';
    const capPct = Math.round((capInfo.count / capInfo.total) * 100);
    const matScore = score.material_usage || 0;
    const strScore = score.strength || 0;

    return `
    <div class="info-block" style="flex:1;">
        <div class="info-block-header">${label}</div>
        <div style="padding:12px; display:flex; flex-direction:column; gap:10px;">
            <div style="display:flex; align-items:baseline; justify-content:center; gap:4px;">
                <span style="font-size:2.2rem; font-weight:700; color:${colorFor(score.overall)}">${score.overall}</span>
                <span style="font-size:.8rem; color:var(--muted)">/100</span>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr 1fr; gap:8px;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:3px;">
                    <span style="font-size:.68rem; color:var(--muted)">Velocidade</span>
                    <span style="font-size:.85rem; font-weight:600; color:${colorFor(score.speed)}">${score.speed}</span>
                    <div style="width:100%; height:4px; border-radius:2px; background:var(--border);">
                        <div style="width:${score.speed}%; height:100%; border-radius:2px; background:${colorFor(score.speed)};"></div>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:center; gap:3px;">
                    <span style="font-size:.68rem; color:var(--muted)">Acabamento</span>
                    <span style="font-size:.85rem; font-weight:600; color:${colorFor(score.finish)}">${score.finish}</span>
                    <div style="width:100%; height:4px; border-radius:2px; background:var(--border);">
                        <div style="width:${score.finish}%; height:100%; border-radius:2px; background:${colorFor(score.finish)};"></div>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:center; gap:3px;">
                    <span style="font-size:.68rem; color:var(--muted)">Resistência</span>
                    <span style="font-size:.85rem; font-weight:600; color:${colorFor(strScore)}">${strScore}</span>
                    <div style="width:100%; height:4px; border-radius:2px; background:var(--border);">
                        <div style="width:${strScore}%; height:100%; border-radius:2px; background:${colorFor(strScore)};"></div>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:center; gap:3px;">
                    <span style="font-size:.68rem; color:var(--muted)">Material</span>
                    <span style="font-size:.85rem; font-weight:600; color:${matColorFor(matScore)}">${matScore}</span>
                    <div style="width:100%; height:4px; border-radius:2px; background:var(--border);">
                        <div style="width:${matScore}%; height:100%; border-radius:2px; background:${matColorFor(matScore)};"></div>
                    </div>
                </div>
                <div style="display:flex; flex-direction:column; align-items:center; gap:3px;">
                    <span style="font-size:.68rem; color:var(--muted)">Confiança</span>
                    <span style="font-size:.85rem; font-weight:600; color:${colorFor(score.confidence)}">${score.confidence}</span>
                    <div style="width:100%; height:4px; border-radius:2px; background:var(--border);">
                        <div style="width:${score.confidence}%; height:100%; border-radius:2px; background:${colorFor(score.confidence)};"></div>
                    </div>
                </div>
            </div>
            <div style="margin-top:4px; padding-top:8px; border-top:1px solid var(--border); display:flex; align-items:center; gap:8px;">
                <div style="flex:1;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
                        <span style="font-size:.72rem; color:var(--muted)">Velocidades limitadas pelo MVS</span>
                        <span style="font-size:.78rem; font-weight:600; color:${capColor}">${capInfo.count} de ${capInfo.total}</span>
                    </div>
                    <div style="width:100%; height:6px; border-radius:3px; background:var(--border); overflow:hidden; display:flex;">
                        ${Array.from({length: capInfo.total}, (_, i) => {
                            const isCapped = i < capInfo.count;
                            const bg = isCapped ? 'var(--orange)' : 'var(--green)';
                            return `<div style="flex:1; height:100%; background:${bg}; margin-right:${i < capInfo.total - 1 ? '1px' : '0'};"></div>`;
                        }).join('')}
                    </div>
                </div>
            </div>
        </div>
    </div>`;
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

    // Score cards
    const scoreA = calcCombinationScore(a);
    const scoreB = hasB ? calcCombinationScore(b) : null;
    const capInfoA = { count: capCountA, total: Object.keys(a.simulation.speeds).filter(k => k !== 'travel_speed').length };
    const capInfoB = hasB ? { count: capCountB, total: Object.keys(b.simulation.speeds).filter(k => k !== 'travel_speed').length } : null;
    const scoreSection = `
        <div style="display:flex; gap:12px; margin-bottom:16px;">
            ${renderScoreCard(scoreA, `Score A — ${a.process.profile_type} + ${a.filament.commercial_name}`, capInfoA)}
            ${hasB ? renderScoreCard(scoreB, `Score B — ${b.process.profile_type} + ${b.filament.commercial_name}`, capInfoB) : ''}
        </div>`;

    simResult.innerHTML = `
        ${scoreSection}
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

// ═══════════════════════════════════════════════════════════════════════════════
// ─── Ranking view ────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

let rankingData = [];
let rankingLoaded = false;

const rankingSortSel = document.getElementById('ranking-sort');
const rankingMaterialSel = document.getElementById('ranking-material');
const rankingProfileTypeSel = document.getElementById('ranking-profile-type');
const rankingLayerSel = document.getElementById('ranking-layer');
const rankingManufacturerSel = document.getElementById('ranking-manufacturer');
const rankingTableWrap = document.getElementById('ranking-table-wrap');
const rankingCount = document.getElementById('ranking-count');

async function loadRanking() {
    if (rankingLoaded) return;
    try {
        rankingTableWrap.innerHTML = '<div class="empty">Carregando ranking...</div>';
        const r = await fetch('/api/ranking');
        rankingData = await r.json();
        rankingLoaded = true;
        populateRankingFilters();
        renderRanking();
    } catch (e) {
        rankingTableWrap.innerHTML = '<div class="empty">Erro ao carregar ranking.</div>';
        console.error('Failed to load ranking', e);
    }
}

function populateRankingFilters() {
    const materials = [...new Set(rankingData.map(r => r.material))].sort();
    const profileTypes = [...new Set(rankingData.map(r => r.profile_type))].sort((a, b) => {
        const order = ['fast', 'standard', 'strong', 'detail', 'safe'];
        return order.indexOf(a) - order.indexOf(b);
    });
    const layers = [...new Set(rankingData.map(r => r.layer_height))].sort((a, b) => a - b);
    const manufacturers = [...new Set(rankingData.map(r => r.manufacturer))].sort();

    rankingMaterialSel.innerHTML = '<option value="">Todos</option>' +
        materials.map(m => `<option value="${m}">${m}</option>`).join('');
    rankingProfileTypeSel.innerHTML = '<option value="">Todos</option>' +
        profileTypes.map(t => `<option value="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</option>`).join('');
    rankingLayerSel.innerHTML = '<option value="">Todos</option>' +
        layers.map(l => `<option value="${l}">${Number(l).toFixed(2)}mm</option>`).join('');
    rankingManufacturerSel.innerHTML = '<option value="">Todos</option>' +
        manufacturers.map(m => `<option value="${m}">${m}</option>`).join('');
}

function getFilteredRanking() {
    const sortBy = rankingSortSel.value;
    const matFilter = rankingMaterialSel.value;
    const ptFilter = rankingProfileTypeSel.value;
    const lhFilter = rankingLayerSel.value;
    const mfrFilter = rankingManufacturerSel.value;

    let filtered = rankingData;

    if (matFilter) filtered = filtered.filter(r => r.material === matFilter);
    if (ptFilter) filtered = filtered.filter(r => r.profile_type === ptFilter);
    if (lhFilter) filtered = filtered.filter(r => r.layer_height === parseFloat(lhFilter));
    if (mfrFilter) filtered = filtered.filter(r => r.manufacturer === mfrFilter);

    // Sort
    filtered = [...filtered].sort((a, b) => b.scores[sortBy] - a.scores[sortBy]);

    return filtered;
}

function rankingScoreBar(val, max = 100) {
    const pct = Math.round((val / max) * 100);
    const color = val >= 80 ? 'var(--green)' : val >= 60 ? 'var(--yellow)' : val >= 40 ? 'var(--orange)' : 'var(--red)';
    return `<div style="display:flex; align-items:center; gap:6px;">
        <span style="font-size:.82rem; font-weight:600; color:${color}; min-width:28px;">${val}</span>
        <div style="flex:1; height:6px; border-radius:3px; background:var(--border); min-width:50px;">
            <div style="width:${pct}%; height:100%; border-radius:3px; background:${color};"></div>
        </div>
    </div>`;
}

function rankingCapIndicator(capped, total) {
    if (total === 0) return '—';
    const color = capped > 0 ? 'var(--orange)' : 'var(--green)';
    const segments = Array.from({length: total}, (_, i) => {
        const bg = i < capped ? 'var(--orange)' : 'var(--green)';
        return `<div style="flex:1; height:6px; background:${bg}; border-radius:1px;"></div>`;
    }).join('');
    return `<div style="display:flex; align-items:center; gap:4px;">
        <span style="font-size:.78rem; color:${color}; min-width:32px;">${capped}/${total}</span>
        <div style="display:flex; gap:1px; flex:1; min-width:40px;">${segments}</div>
    </div>`;
}

function renderRanking() {
    const filtered = getFilteredRanking();
    rankingCount.textContent = `${filtered.length} combinações`;

    if (!filtered.length) {
        rankingTableWrap.innerHTML = '<div class="empty">Nenhuma combinação encontrada para os filtros selecionados.</div>';
        return;
    }

    // Limit to top 200 for performance
    const shown = filtered.slice(0, 200);

    const rows = shown.map((r, i) => {
        const pos = i + 1;
        const medal = pos <= 3 ? ['🥇','🥈','🥉'][pos-1] : `<span style="color:var(--muted)">${pos}</span>`;
        const typeLabel = r.profile_type.charAt(0).toUpperCase() + r.profile_type.slice(1);
        return `
        <tr>
            <td style="text-align:center; width:40px;">${medal}</td>
            <td><strong>${r.filament_name}</strong><br><span style="font-size:.72rem; color:var(--muted)">${r.manufacturer}</span></td>
            <td><span class="chip chip-${r.material}">${r.material}</span></td>
            <td>${Number(r.layer_height).toFixed(2)}mm</td>
            <td>${typeLabel}</td>
            <td style="min-width:100px;">${rankingScoreBar(r.scores.overall)}</td>
            <td style="min-width:90px;">${rankingScoreBar(r.scores.speed)}</td>
            <td style="min-width:90px;">${rankingScoreBar(r.scores.finish)}</td>
            <td style="min-width:90px;">${rankingScoreBar(r.scores.confidence)}</td>
            <td style="min-width:90px;">${rankingCapIndicator(r.scores.capped_count, r.scores.total_speeds)}</td>
            <td style="font-size:.78rem; color:var(--muted)">${r.scores.avg_effective_speed} mm/s</td>
            <td style="font-size:.78rem; color:var(--muted)">${r.mvs} mm³/s</td>
        </tr>`;
    }).join('');

    rankingTableWrap.innerHTML = `
    <table>
        <thead><tr>
            <th style="width:40px;">#</th>
            <th>Filamento</th>
            <th>Material</th>
            <th>Layer</th>
            <th>Perfil</th>
            <th>Score</th>
            <th>Velocidade</th>
            <th>Acabamento</th>
            <th>Confiança</th>
            <th>Limitações</th>
            <th>Vel. média</th>
            <th>MVS</th>
        </tr></thead>
        <tbody>${rows}</tbody>
    </table>
    ${filtered.length > 200 ? `<div style="text-align:center; padding:12px; font-size:.78rem; color:var(--muted);">Mostrando top 200 de ${filtered.length} combinações. Use os filtros para refinar.</div>` : ''}`;
}

// Event listeners for ranking filters
[rankingSortSel, rankingMaterialSel, rankingProfileTypeSel, rankingLayerSel, rankingManufacturerSel].forEach(sel => {
    if (sel) sel.addEventListener('change', renderRanking);
});

// Lazy-load ranking when view is activated
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.dataset.view === 'ranking') loadRanking();
    });
});


// ═══════════════════════════════════════════════════════════════════════════════

// ─── Prices view ────────────────────────────────────────────────────────────
let priceData = null;
let priceLoaded = false;
const priceGrid = document.getElementById('price-grid');
const priceMaterial = document.getElementById('price-material');
const priceManufacturer = document.getElementById('price-manufacturer');
const priceSort = document.getElementById('price-sort');
const priceStore = document.getElementById('price-store');

function priceMoney(value) {
    return value == null ? '—' : Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}
function priceEsc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}
function populatePriceFilters() {
    const mats = [...new Set(priceData.items.map(x => x.material_name).filter(Boolean))].sort((a,b) => a.localeCompare(b,'pt-BR'));
    const mfrs = [...new Set(priceData.items.map(x => x.manufacturer_name).filter(Boolean))].sort((a,b) => a.localeCompare(b,'pt-BR'));
    priceMaterial.innerHTML = '<option value="">Material: Todos</option>' + mats.map(x => `<option value="${priceEsc(x)}">${priceEsc(x)}</option>`).join('');
    priceManufacturer.innerHTML = '<option value="">Fabricante: Todos</option>' + mfrs.map(x => `<option value="${priceEsc(x)}">${priceEsc(x)}</option>`).join('');
}
function renderPriceOffer(offer) {
    const qty = Math.max(Number(offer.quantity || 1), 1);
    const total = offer.total_price ?? offer.price;
    const shipping = offer.shipping != null ? ` · frete ${priceMoney(offer.shipping)}` : '';
    const color = offer.variant_color ? `<div class="price-color">Cor: ${priceEsc(offer.variant_color)}</div>` : '';
    const volume = offer.is_volume_offer ? `<span class="price-volume">${qty}× ${Number(offer.unit_weight_g || 1000).toLocaleString('pt-BR')}g</span>` : '';
    const unit = offer.price_per_kg != null ? `<div class="price-unit">${priceMoney(offer.price_per_kg)}/kg</div>` : '';
    let change = '';
    if (offer.price_change_pct != null) {
        const pct = offer.price_change_pct;
        const down = pct < 0;
        const dir = down ? 'down' : 'up';
        const arrow = down ? '↓' : '↑';
        // Variação acima de 20% (em módulo) vira alerta destacado: verde se for
        // queda (bom pra quem compra), vermelho se for alta.
        const isAlert = Math.abs(pct) > 20;
        const cls = isAlert ? `price-change ${dir} alert` : `price-change ${dir}`;
        const prefix = isAlert ? '⚠️ ' : '';
        const label = isAlert
            ? `${prefix}${arrow} ${Math.abs(pct).toFixed(1)}% ${down ? 'de queda' : 'de alta'} desde a coleta anterior`
            : `${arrow} ${Math.abs(pct).toFixed(1)}% desde a coleta anterior`;
        const alertAttr = isAlert ? ' role="alert"' : '';
        change = `<div class="${cls}"${alertAttr}>${label}</div>`;
    }
    const isWholesale = qty > 1 || offer.price_basis === 'unit';
    const priceMain = isWholesale && offer.price != null ? `${priceMoney(offer.price)}/rolo` : priceMoney(total);
    const priceSub = isWholesale ? `<div class="price-unit">${priceMoney(total)} total${shipping}</div>` : shipping;
    return `<div class="price-offer"><div><div class="price-store">${priceEsc(offer.store)} ${volume}</div>${color}<div class="price-title" title="${priceEsc(offer.title)}">${priceEsc(offer.title || 'Oferta')}</div><a class="price-offer-link" href="${priceEsc(offer.url)}" target="_blank" rel="noopener">Abrir oferta ↗</a>${change}</div><div class="price-offer-price">${priceMain}${isWholesale ? '' : priceSub}${unit}${isWholesale ? priceSub : ''}</div></div>`;
}


function renderCollectionLog(log) {
    if (!Array.isArray(log) || !log.length) return '';
    const runs = log.slice(0, 10).map(run => {
        const results = Array.isArray(run.results) ? run.results : [];
        const found = results.filter(r => r.status === 'found').length;
        const missing = results.filter(r => r.status !== 'found').length;
        const resultHtml = results.length ? results.map(r => {
            const label = r.filament_key ? `${r.filament_key}${r.color ? ` · ${r.color}` : ''}` : 'Fonte geral';
            const icon = r.status === 'found' ? '✓' : '—';
            return `<div class="price-collection-result"><span>${icon}</span><span>${priceEsc(r.store)}</span><span>${priceEsc(label)}</span><span>${r.offers_found || 0} oferta(s)</span><span>${priceEsc(r.notes || '')}</span></div>`;
        }).join('') : '<div class="price-muted">Nenhum detalhe registrado.</div>';
        return `<details class="price-collection-run"><summary><strong>${priceEsc(run.snapshot_file || 'coleta')}</strong> · ${priceEsc(run.status)} · ${run.items_found || 0} ofertas · ${found} fontes com resultado · ${missing} sem resultado</summary><div class="price-collection-results">${resultHtml}</div></details>`;
    }).join('');
    return `<div class="price-report-group">Log das coletas</div><div class="price-collection-log">${runs}</div>`;
}

function renderPrices() {
    if (!priceData) return;
    let items = [...priceData.items];
    if (priceMaterial.value) items = items.filter(x => x.material_name === priceMaterial.value);
    if (priceManufacturer.value) items = items.filter(x => x.manufacturer_name === priceManufacturer.value);
    if (priceStore.value) items = items.filter(x => (x.offers || []).some(o => o.store === priceStore.value));
    if (priceSort.value === 'price') items.sort((a,b) => (a.best_price ?? Infinity) - (b.best_price ?? Infinity));
    else if (priceSort.value === 'name') items.sort((a,b) => (a.commercial_name || a.profile_name || '').localeCompare(b.commercial_name || b.profile_name || '', 'pt-BR'));
    else if (priceSort.value === 'opportunity') items.sort((a,b) => (b.discount_pct || 0) - (a.discount_pct || 0) || (a.best_price ?? Infinity) - (b.best_price ?? Infinity));
    else items.sort((a,b) => a.material_name.localeCompare(b.material_name, 'pt-BR') || a.manufacturer_name.localeCompare(b.manufacturer_name, 'pt-BR') || (a.commercial_name || a.profile_name || '').localeCompare(b.commercial_name || b.profile_name || '', 'pt-BR'));

    document.getElementById('price-tracked').textContent = priceData.summary.tracked_count;
    document.getElementById('price-priced').textContent = priceData.summary.priced_count;
    document.getElementById('price-offers').textContent = priceData.summary.offer_count;

    const collectionBox = document.getElementById('price-collection-summary');
    if (collectionBox) {
        const cs = priceData.collection_summary || {};
        const statusClass = cs.status === 'completed' ? 'ok' : 'warn';
        const statusText = cs.status === 'completed' ? 'Concluída' : (cs.status || 'Sem coleta');
        const when = cs.collected_at ? new Date(cs.collected_at).toLocaleString('pt-BR') : '—';
        collectionBox.innerHTML = `
            <div class="price-collection-status ${statusClass}"><div class="k">Última coleta</div><div class="v">${priceEsc(cs.snapshot_file || '—')}</div></div>
            <div class="price-collection-status ${statusClass}"><div class="k">Status</div><div class="v">${priceEsc(statusText)}</div></div>
            <div class="price-collection-status"><div class="k">Ofertas encontradas</div><div class="v">${cs.offers_found ?? 0}</div></div>
            <div class="price-collection-status"><div class="k">Fontes com resultado</div><div class="v">${cs.sources_with_results ?? 0} · ${cs.sources_without_results ?? 0} sem</div></div>
            <div class="price-collection-status"><div class="k">Coletado em</div><div class="v">${priceEsc(when)}</div></div>`;
    }

    if (!items.length) { priceGrid.innerHTML = '<div class="price-empty">Nenhum filamento encontrado para os filtros.</div>'; return; }

    let lastGroup = '';
    const rows = items.map(x => {
        const group = `${x.material_name} · ${x.manufacturer_name}`;
        const groupHtml = group !== lastGroup ? `<div class="price-report-group">${priceEsc(group)}</div>` : '';
        lastGroup = group;
        const discount = x.opportunity_pct > 0 ? `↓ ${x.opportunity_pct.toFixed(0)}%` : '—';
        const drop = x.max_drop_pct > 0 ? ` · queda ${x.max_drop_pct.toFixed(0)}%` : '';
        const offers = x.offers?.length ? x.offers.map(renderPriceOffer).join('') : '<span class="price-muted">Nenhuma oferta encontrada</span>';
        const volNote = x.best_is_volume ? ' · melhor/kg em atacado' : '';
        return `${groupHtml}<div class="price-report-row"><div><div class="price-filament-name">${priceEsc(x.commercial_name || x.profile_name)}</div><div class="price-filament-meta">${priceEsc(x.filament_key || x.profile_name || '')} · ${priceEsc(x.profile_name || '')}${x.line ? ` · ${priceEsc(x.line)}` : ''}${x.line_finish ? ` · ${priceEsc(x.line_finish)}` : ''}</div></div><div class="price-number">${priceMoney(x.best_price)}<small>1 rolo${x.best_price_per_kg != null ? ` · ${priceMoney(x.best_price_per_kg)}/kg${volNote}` : ''}</small></div><div class="price-number">${priceMoney(x.median_price)}<small>/kg histórico</small></div><div class="price-number">${priceMoney(x.best_historical_price_per_kg)}<small>melhor histórico/kg</small></div><div class="price-opportunity">${discount}${drop}</div><div class="price-offers">${offers}</div></div>`;
    }).join('');

    priceGrid.innerHTML = `<div class="price-report"><div class="price-report-head"><div>Filamento</div><div>Melhor preço</div><div>Mediana</div><div>Melhor histórico/kg</div><div>Oportunidade</div><div>Ofertas encontradas</div></div>${rows}</div>${renderCollectionLog(priceData.collection_log)}`;
}
async function loadPrices() {
    if (priceLoaded) return;
    try {
        const response = await fetch('/api/prices');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        priceData = await response.json();
        priceLoaded = true;
        populatePriceFilters();
        renderPrices();
    } catch (error) {
        priceGrid.innerHTML = '<div class="price-empty">Não foi possível carregar o histórico de preços.</div>';
        console.error('Failed to load prices', error);
    }
}
[priceMaterial, priceManufacturer, priceStore, priceSort].forEach(el => el?.addEventListener('change', renderPrices));

// ─── Inventory view — Controle de estoque ─────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

const invContainer   = document.getElementById('inventory-container');
const invSummary     = document.getElementById('inv-summary');
const invCharts      = document.getElementById('inv-charts');
const invFormPanel   = document.getElementById('inv-form-panel');
const invFormTitle   = document.getElementById('inv-form-title');
const invAddBtn      = document.getElementById('inv-add-btn');
const invSaveBtn     = document.getElementById('inv-save-btn');
const invCancelBtn   = document.getElementById('inv-cancel-btn');
const invShowUsed    = document.getElementById('inv-show-used');

// Form fields
const invF = {
    material:     document.getElementById('inv-material'),
    manufacturer: document.getElementById('inv-manufacturer'),
    colorName:    document.getElementById('inv-color-name'),
    hex:          document.getElementById('inv-hex'),
    hexPicker:    document.getElementById('inv-hex-picker'),
    finish:       document.getElementById('inv-finish'),
    weight:       document.getElementById('inv-weight'),
    spools:       document.getElementById('inv-spools'),
    status:       document.getElementById('inv-status'),
    notes:        document.getElementById('inv-notes'),
};

// Catalog selects (pre-fill from window.treeData)
const invCatMfr     = document.getElementById('inv-cat-manufacturer');
const invCatMat     = document.getElementById('inv-cat-material');
const invCatVariant = document.getElementById('inv-cat-variant');
const invCatPreview = document.getElementById('inv-cat-preview');

let invEditingId = null;   // null = criando, número = editando
let invLoaded = false;

const STATUS_LABEL = {
    in_stock: '📦 Em estoque',
    cfs:      '🎡 No CFS',
    spool:    '🎣 No spool',
    drybox:   '🌡️ No Drybox',
    open:     '⚠️ Aberto',
    empty:    '✔️ Usado',
};
const STATUS_ORDER = ['in_stock', 'cfs', 'spool', 'drybox', 'open', 'empty'];

// ─── Load + render ────────────────────────────────────────────────────────────
let invData = null;   // último estado carregado (para consultas rápidas, ex: materiais no CFS)

async function loadInventory() {
    if (!invContainer) return;
    if (!invLoaded) populateCatalogManufacturers();
    invLoaded = true;
    try {
        const res = await fetch('/api/inventory');
        const data = await res.json();
        invData = data;
        renderInventory(data);
    } catch (err) {
        invContainer.innerHTML = `<div class="empty">Erro ao carregar estoque: ${err}</div>`;
    }
}

// Materiais atualmente carregados no CFS (a partir do último estado).
function materialsInCfs() {
    const items = invData?.printer?.cfs?.items || [];
    return items.map(i => i.material);
}

// Busca um item pelo id no estado carregado (para saber material/cor sem novo fetch).
function findItemInState(id) {
    if (!invData) return null;
    const buckets = [
        ...(invData.printer?.cfs?.items || []),
        ...(invData.printer?.spool?.items || []),
        ...(invData.drybox?.items || []),
        ...(invData.open?.items || []),
        ...(invData.empty?.items || []),
    ];
    for (const m of (invData.sealed?.materials || [])) buckets.push(...(m.items || []));
    return buckets.find(i => i.id === id) || null;
}

function renderInventory(data) {
    const { summary = {} } = data;

    const cfsUsed = summary.cfs_used || 0;
    const cfsMax = summary.cfs_max || 4;
    const cfsFull = cfsUsed >= cfsMax;
    const spoolUsed = summary.spool_used || 0;
    const spoolMax = summary.spool_max || 1;
    const spoolFull = spoolUsed >= spoolMax;
    const activeInputs = cfsUsed + spoolUsed;   // entradas ativas na impressora (máx 5)
    const openCount = summary.open_count || 0;

    invSummary.innerHTML = `
        <div class="inv-summary-card"><div class="num">${summary.materials || 0}</div><span class="lbl">Materiais</span></div>
        <div class="inv-summary-card"><div class="num">${summary.total_items || 0}</div><span class="lbl">Itens (cores)</span></div>
        <div class="inv-summary-card"><div class="num">${summary.total_spools || 0}</div><span class="lbl">Rolos no total</span></div>
        <div class="inv-summary-card">
            <div class="num" style="color:${cfsFull ? 'var(--red)' : 'var(--blue)'}">${cfsUsed}/${cfsMax}</div>
            <span class="lbl">CFS ${cfsFull ? '(cheio)' : ''}</span>
        </div>
        <div class="inv-summary-card">
            <div class="num" style="color:${spoolFull ? 'var(--yellow)' : 'var(--green)'}">${spoolUsed}/${spoolMax}</div>
            <span class="lbl">Spool holder</span>
        </div>
        <div class="inv-summary-card">
            <div class="num" style="color:${activeInputs >= 5 ? 'var(--yellow)' : 'var(--text)'}">${activeInputs}/5</div>
            <span class="lbl">Entradas ativas</span>
        </div>
        ${openCount ? `<div class="inv-summary-card">
            <div class="num" style="color:var(--orange)">${openCount}</div>
            <span class="lbl">⚠️ Abertos</span>
        </div>` : ''}
    `;

    renderInvCharts(data);

    const anyItems = (summary.total_items || 0) + (summary.used_count || 0);
    if (!anyItems) {
        invContainer.innerHTML = `<div class="empty">Estoque vazio. Clique em "+ Adicionar filamento" para começar.</div>`;
        return;
    }

    const showUsed = invShowUsed?.checked;
    const printer = data.printer || { cfs: {}, spool: {} };
    const cfs = printer.cfs || { items: [], used: 0, max: 4 };
    const spool = printer.spool || { items: [], used: 0, max: 1 };
    const drybox = (data.drybox && data.drybox.items) || [];
    const open = (data.open && data.open.items) || [];
    const sealedMaterials = (data.sealed && data.sealed.materials) || [];
    const empty = (data.empty && data.empty.items) || [];

    let html = '';

    // ── 1. Na impressora (CFS + spool holder) ──
    const cfsSlots = renderCfsSlots(cfs);
    const spoolCards = spool.items.length
        ? spool.items.map(renderInvCard).join('')
        : `<div class="inv-slot-empty">Spool holder livre</div>`;
    html += `
    <section class="inv-section inv-section-printer">
        <div class="inv-section-head">
            <span class="inv-section-title">🖨️ Na impressora</span>
            <span class="inv-section-meta">${cfs.used}/${cfs.max} no CFS · ${spool.used}/${spool.max} no spool · ${cfs.used + spool.used}/5 entradas</span>
        </div>
        <div class="inv-subsection-label">CFS <span class="inv-slot-count">${cfs.used}/${cfs.max}</span></div>
        <div class="inv-cards">${cfsSlots}</div>
        <div class="inv-subsection-label">Spool holder <span class="inv-slot-count">${spool.used}/${spool.max}</span></div>
        <div class="inv-cards">${spoolCards}</div>
    </section>`;

    // ── 2. Nos dryboxes (prontos para engatar) ──
    if (drybox.length) {
        html += renderLocationSection('🌡️ Nos dryboxes', 'Secos, prontos para engatar', drybox, 'inv-section-drybox');
    }

    // ── 3. Abertos (alerta) ──
    if (open.length) {
        html += renderLocationSection('⚠️ Abertos (fora do drybox)', 'Expostos à umidade — engate num drybox ou guarde', open, 'inv-section-open');
    }

    // ── 4. Estoque fechado (por material → cor) ──
    let sealedHtml = '';
    for (const group of sealedMaterials) {
        if (!group.items.length) continue;
        const palette = group.items.map(i =>
            `<span class="inv-palette-dot" style="background:${i.hex_color || '#333'}" title="${escapeHtml(i.color_name)}"></span>`
        ).join('');
        sealedHtml += `
        <div class="inv-material-group">
            <div class="inv-group-header">
                <span class="chip chip-standard inv-group-mat">${escapeHtml(group.material)}</span>
                <span class="inv-group-meta">${group.colors_available} cor(es) · ${group.total_spools} rolo(s)</span>
                <div class="inv-group-palette">${palette}</div>
            </div>
            <div class="inv-cards">${group.items.map(renderInvCard).join('')}</div>
        </div>`;
    }
    if (sealedHtml) {
        html += `
        <section class="inv-section">
            <div class="inv-section-head">
                <span class="inv-section-title">📦 Estoque fechado</span>
                <span class="inv-section-meta">Lacrados/guardados, por material</span>
            </div>
            ${sealedHtml}
        </section>`;
    }

    // ── 5. Usados — escondidos por padrão; só aparecem com "Exibir rolos usados" ──
    // Não entram em gráficos nem estatísticas (já foram consumidos).
    if (empty.length && showUsed) {
        html += `
        <section class="inv-section inv-section-empty">
            <details open>
                <summary class="inv-section-title">✔️ Usados (${empty.length})</summary>
                <div class="inv-cards" style="margin-top:12px;">${empty.map(renderInvCard).join('')}</div>
            </details>
        </section>`;
    }

    invContainer.innerHTML = html || `<div class="empty">Nenhum item para exibir com o filtro atual.</div>`;

    invContainer.querySelectorAll('[data-inv-use]').forEach(btn =>
        btn.addEventListener('click', () => invUse(+btn.dataset.invUse)));
    invContainer.querySelectorAll('[data-inv-add-spool]').forEach(btn =>
        btn.addEventListener('click', () => invAddSpool(+btn.dataset.invAddSpool)));
    invContainer.querySelectorAll('[data-inv-edit]').forEach(btn =>
        btn.addEventListener('click', () => invStartEdit(+btn.dataset.invEdit)));
    invContainer.querySelectorAll('[data-inv-del]').forEach(btn =>
        btn.addEventListener('click', () => invDelete(+btn.dataset.invDel)));
    invContainer.querySelectorAll('[data-inv-move]').forEach(btn =>
        btn.addEventListener('click', () => invMove(+btn.dataset.invMove, btn.dataset.target)));
    invContainer.querySelectorAll('[data-inv-restore]').forEach(btn =>
        btn.addEventListener('click', () => invRestore(+btn.dataset.invRestore)));
}

// Cores das localizações (batem com os badges de status)
// Paleta NEON para as localizações — matizes bem espaçados e brilhos distintos
// para serem distinguíveis também por quem tem daltonismo.
const LOC_COLORS = {
    cfs:      '#00e5ff',   // ciano neon
    spool:    '#39ff14',   // verde-lima neon
    drybox:   '#ff9500',   // laranja neon
    open:     '#ffee00',   // amarelo neon (alerta)
    in_stock: '#7c8cff',   // azul-violeta neon
};
const LOC_LABELS = {
    cfs: 'CFS', spool: 'Spool', drybox: 'Drybox', open: 'Aberto', in_stock: 'Estoque',
};

// Junta todos os itens (exceto vazios) a partir da estrutura por localização.
function collectAllItems(data) {
    const items = [];
    (data.printer?.cfs?.items || []).forEach(i => items.push(i));
    (data.printer?.spool?.items || []).forEach(i => items.push(i));
    (data.drybox?.items || []).forEach(i => items.push(i));
    (data.open?.items || []).forEach(i => items.push(i));
    (data.sealed?.materials || []).forEach(m => (m.items || []).forEach(i => items.push(i)));
    return items;
}

function renderInvCharts(data) {
    if (!invCharts) return;
    const items = collectAllItems(data);
    if (!items.length) { invCharts.innerHTML = ''; return; }

    // ── 1. Distribuição de rolos por localização (barra empilhada) ──
    const spoolsByLoc = {};
    for (const it of items) {
        spoolsByLoc[it.status] = (spoolsByLoc[it.status] || 0) + (it.spools || 0);
    }
    const order = ['cfs', 'spool', 'drybox', 'open', 'in_stock'];
    const totalSpools = order.reduce((s, k) => s + (spoolsByLoc[k] || 0), 0) || 1;
    const segs = order.filter(k => spoolsByLoc[k]).map(k => {
        const pct = (spoolsByLoc[k] / totalSpools) * 100;
        return `<div class="inv-dist-seg" style="width:${pct}%;background:${LOC_COLORS[k]}" title="${LOC_LABELS[k]}: ${spoolsByLoc[k]}"></div>`;
    }).join('');
    const legend = order.filter(k => spoolsByLoc[k]).map(k =>
        `<span class="inv-dist-key"><span class="inv-dist-swatch" style="background:${LOC_COLORS[k]}"></span>${LOC_LABELS[k]} <strong>${spoolsByLoc[k]}</strong></span>`
    ).join('');

    // ── 2. Paleta por material (cores que tenho, com quantidade) ──
    const byMat = {};
    for (const it of items) {
        (byMat[it.material] = byMat[it.material] || []).push(it);
    }
    // Ordena materiais por total de rolos desc
    const matRows = Object.entries(byMat)
        .sort((a, b) => b[1].reduce((s, i) => s + i.spools, 0) - a[1].reduce((s, i) => s + i.spools, 0))
        .map(([mat, its]) => {
            // agrupa por cor (name+hex) somando rolos
            const byColor = {};
            for (const i of its) {
                const key = `${i.color_name}|${i.hex_color}`;
                if (!byColor[key]) byColor[key] = { name: i.color_name, hex: i.hex_color, qty: 0 };
                byColor[key].qty += i.spools;
            }
            const chips = Object.values(byColor)
                .sort((a, b) => b.qty - a.qty)
                .map(c => `<span class="inv-palette-chip" style="background:${c.hex || '#333'}" title="${escapeHtml(c.name)} — ${c.qty} rolo(s)">${c.qty > 1 ? `<span class="qty">${c.qty}</span>` : ''}</span>`)
                .join('');
            return `<div class="inv-palette-row">
                <span class="inv-palette-mat">${escapeHtml(mat)}</span>
                <div class="inv-palette-swatches">${chips}</div>
            </div>`;
        }).join('');

    // ── 3. Barra por material: quantidade de rolos, cores empilhadas ──
    // Largura da barra proporcional entre materiais; segmentos internos = cores.
    const matTotals = Object.entries(byMat).map(([mat, its]) => ({
        mat, total: its.reduce((s, i) => s + i.spools, 0), its,
    })).sort((a, b) => b.total - a.total);
    const maxTotal = matTotals.length ? matTotals[0].total : 1;

    // Escala global: 1 rolo = 1/maxTotal da largura, IGUAL em todas as barras.
    // Assim a barra do material com mais rolos preenche 100% e as demais ficam
    // proporcionais à quantidade real (didático: dá para "contar" os rolos).
    const unitPct = 100 / (maxTotal || 1);

    const matBarRows = matTotals.map(({ mat, total, its }) => {
        // agrupa por cor somando rolos
        const byColor = {};
        for (const i of its) {
            const key = `${i.color_name}|${i.hex_color}`;
            if (!byColor[key]) byColor[key] = { name: i.color_name, hex: i.hex_color, qty: 0 };
            byColor[key].qty += i.spools;
        }
        const colors = Object.values(byColor).sort((a, b) => b.qty - a.qty);
        // Cada segmento ocupa (qtd de rolos) × unitPct da TRACK inteira.
        // A track representa 100% = maxTotal rolos; o material preenche só as
        // posições que possui. Assim 1 rolo tem o MESMO tamanho em toda barra.
        const segsInner = colors.map(c => {
            const wpct = c.qty * unitPct;
            // rótulo só quando o segmento é largo o suficiente para caber
            const showNum = wpct >= (unitPct * 0.9) && c.qty >= 1;
            return `<div class="inv-matbar-seg" style="width:${wpct}%;background:${c.hex || '#333'};color:${textColorFor(c.hex)}" title="${escapeHtml(c.name)}: ${c.qty} rolo(s)">${showNum ? c.qty : ''}</div>`;
        }).join('');
        return `<div class="inv-matbar-row">
            <span class="inv-matbar-label">${escapeHtml(mat)}</span>
            <div class="inv-matbar-track" style="--unit:${unitPct}%">${segsInner}</div>
            <span class="inv-matbar-total"><strong>${total}</strong> rolo(s)</span>
        </div>`;
    }).join('');

    invCharts.innerHTML = `
        <div class="inv-chart">
            <div class="inv-chart-title">Distribuição por localização (${totalSpools} rolos)</div>
            <div class="inv-dist-bar">${segs}</div>
            <div class="inv-dist-legend">${legend}</div>
        </div>
        <div class="inv-chart">
            <div class="inv-chart-title">Paleta por material</div>
            <div class="inv-palette-rows">${matRows}</div>
        </div>
        <div class="inv-chart inv-chart-wide">
            <div class="inv-chart-title">Rolos por material e cor</div>
            <div class="inv-matbar-rows">${matBarRows}</div>
        </div>
    `;
}

// Escolhe texto claro ou escuro para contraste sobre um fundo hex (luminância).
function textColorFor(hex) {
    if (!hex || !/^#[0-9a-fA-F]{6}$/.test(hex)) return '#05070a';
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    // luminância relativa aproximada
    const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return lum > 0.55 ? '#05070a' : '#ffffff';
}

// Renderiza os 4 slots do CFS: cada rolo ocupa 1 slot; slots vazios aparecem como placeholders.
function renderCfsSlots(cfs) {
    const cards = [];
    for (const item of cfs.items) {
        // Um item com N rolos ocupa N slots — mostramos o card uma vez com a contagem de rolos.
        cards.push(renderInvCard(item));
    }
    let html = cards.join('');
    const free = Math.max(0, (cfs.max || 4) - (cfs.used || 0));
    for (let i = 0; i < free; i++) {
        html += `<div class="inv-slot-empty">Slot ${(cfs.used || 0) + i + 1} livre</div>`;
    }
    return html;
}

function renderLocationSection(title, subtitle, items, extraClass = '') {
    return `
    <section class="inv-section ${extraClass}">
        <div class="inv-section-head">
            <span class="inv-section-title">${title}</span>
            <span class="inv-section-meta">${subtitle} · ${items.length} item(ns)</span>
        </div>
        <div class="inv-cards">${items.map(renderInvCard).join('')}</div>
    </section>`;
}

// Destinos de movimentação disponíveis a partir de cada status.
// Mostra atalhos contextuais (não repete o status atual).
const MOVE_TARGETS = [
    { status: 'cfs',      label: 'CFS',     icon: '🎡' },
    { status: 'spool',    label: 'Spool',   icon: '🎣' },
    { status: 'drybox',   label: 'Drybox',  icon: '🌡️' },
    { status: 'open',     label: 'Aberto',  icon: '⚠️' },
    { status: 'in_stock', label: 'Estoque', icon: '📦' },
];

function renderInvCard(item) {
    const isEmpty = item.status === 'empty';
    const notes = item.notes ? `<div class="inv-card-notes">${escapeHtml(item.notes)}</div>` : '';

    // Botões "mover para" — só destinos diferentes do atual, e só se não estiver vazio.
    let moveButtons = '';
    if (!isEmpty) {
        moveButtons = MOVE_TARGETS
            .filter(t => t.status !== item.status)
            .map(t => `<button type="button" class="btn-move" data-inv-move="${item.id}" data-target="${t.status}" title="Mover para ${t.label}">${t.icon} ${t.label}</button>`)
            .join('');
    }

    // Ações de ciclo de vida
    let lifecycle = '';
    if (isEmpty) {
        // Recuperação de erro: devolver ao estoque
        lifecycle = `
            <button type="button" class="btn btn-secondary" data-inv-restore="${item.id}" title="Marquei como usado por engano — voltar ao estoque">↩ Recuperar</button>
            <button type="button" class="btn btn-ghost" data-inv-edit="${item.id}">Editar</button>
            <button type="button" class="btn btn-ghost" data-inv-del="${item.id}">Excluir</button>`;
    } else {
        lifecycle = `
            <button type="button" class="btn btn-secondary" data-inv-use="${item.id}" title="Usei um rolo (marca como vazio quando zerar)">− Usei</button>
            <button type="button" class="btn btn-ghost" data-inv-add-spool="${item.id}" title="Comprei mais um rolo">+ Rolo</button>
            <button type="button" class="btn btn-ghost" data-inv-edit="${item.id}">Editar</button>
            <button type="button" class="btn btn-ghost" data-inv-del="${item.id}">Excluir</button>`;
    }

    return `
    <div class="inv-card ${isEmpty ? 'is-empty' : ''} status-${item.status}">
        <div class="inv-card-top">
            <span class="inv-card-swatch" style="background:${item.hex_color || '#333'}"></span>
            <div class="inv-card-title">
                <div class="inv-card-headline">
                    <span class="inv-card-mat">${escapeHtml(item.material)}</span>
                    <span class="inv-card-color">${escapeHtml(item.color_name)}</span>
                </div>
                <span class="inv-card-sub">${escapeHtml(item.manufacturer)}${item.finish ? ' · ' + escapeHtml(item.finish) : ''} · ${item.weight_g}g</span>
            </div>
        </div>
        <div class="inv-card-badges">
            <span class="inv-status ${item.status}">${STATUS_LABEL[item.status] || item.status}</span>
            <span class="inv-spools"><strong>${item.spools}</strong> rolo(s)</span>
        </div>
        ${notes}
        ${moveButtons ? `<div class="inv-move-row"><span class="inv-move-lbl">Mover:</span>${moveButtons}</div>` : ''}
        <div class="inv-card-actions">
            ${lifecycle}
        </div>
    </div>`;
}

function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
}

// ─── Actions ──────────────────────────────────────────────────────────────────
async function invUse(id) {
    await fetch(`/api/inventory/${id}/use`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 1 }),
    });
    loadInventory();
}

// Move um rolo para outra localização (CFS/spool/drybox/aberto/estoque).
// Sempre pede confirmação. Ao ir para o CFS com material diferente dos que já
// estão lá, adiciona um alerta de incompatibilidade (não bloqueia).
async function invMove(id, target) {
    const item = findItemInState(id);
    const label = item ? `${item.material} ${item.color_name}` : 'este rolo';
    const targetLabel = (STATUS_LABEL[target] || target).replace(/^[^ ]+ /, ''); // sem emoji

    let msg = `Mover ${label} para ${targetLabel}?`;

    // Alerta de material misto no CFS
    if (target === 'cfs' && item) {
        const others = materialsInCfs().filter(m => m !== item.material);
        const distinct = [...new Set(others)];
        if (distinct.length) {
            msg += `\n\n⚠️ ATENÇÃO: o CFS já tem ${distinct.join(', ')} e você está adicionando ${item.material}.`
                 + `\nMateriais diferentes no mesmo CFS podem causar problemas de impressão`
                 + ` (temperaturas e velocidades incompatíveis). Prossiga apenas se souber o que está fazendo.`;
        }
    }

    if (!confirm(msg)) return;

    const res = await fetch(`/api/inventory/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: target }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Não foi possível mover o rolo.');
    }
    loadInventory();
}

// Recupera um rolo marcado como usado por engano: volta ao estoque com 1 rolo.
async function invRestore(id) {
    const item = await (await fetch(`/api/inventory/${id}`)).json();
    const spools = (item.spools || 0) < 1 ? 1 : item.spools;
    const res = await fetch(`/api/inventory/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'in_stock', spools }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Não foi possível recuperar o rolo.');
    }
    loadInventory();
}

async function invAddSpool(id) {
    const item = await (await fetch(`/api/inventory/${id}`)).json();
    const res = await fetch(`/api/inventory/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spools: (item.spools || 0) + 1 }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Não foi possível adicionar mais um rolo.');
    }
    loadInventory();
}

async function invDelete(id) {
    if (!confirm('Remover este filamento do estoque?')) return;
    await fetch(`/api/inventory/${id}`, { method: 'DELETE' });
    loadInventory();
}

// ─── Form: add / edit ───────────────────────────────────────────────────────
function invOpenForm(editing = false) {
    invFormPanel.style.display = 'block';
    invFormTitle.textContent = editing ? 'Editar filamento' : 'Adicionar filamento ao estoque';
    invFormPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function invCloseForm() {
    invFormPanel.style.display = 'none';
    invEditingId = null;
    invClearForm();
}

function invClearForm() {
    invF.material.value = '';
    invF.manufacturer.value = '';
    invF.colorName.value = '';
    invF.hex.value = '';
    invF.hexPicker.value = '#00e5ff';
    invF.finish.value = '';
    invF.weight.value = '1000';
    invF.spools.value = '1';
    invF.status.value = 'in_stock';
    invF.notes.value = '';
    if (invCatMfr) invCatMfr.value = '';
    if (invCatMat) { invCatMat.innerHTML = '<option value="">Material...</option>'; invCatMat.disabled = true; }
    if (invCatVariant) { invCatVariant.innerHTML = '<option value="">Cor...</option>'; invCatVariant.disabled = true; }
    if (invCatPreview) { invCatPreview.style.display = 'none'; invCatPreview.innerHTML = ''; }
}

function invStartEdit(id) {
    fetch(`/api/inventory/${id}`).then(r => r.json()).then(item => {
        invEditingId = id;
        invF.material.value = item.material || '';
        invF.manufacturer.value = item.manufacturer || '';
        invF.colorName.value = item.color_name || '';
        invF.hex.value = item.hex_color || '';
        if (item.hex_color) invF.hexPicker.value = item.hex_color;
        invF.finish.value = item.finish || '';
        invF.weight.value = item.weight_g ?? 1000;
        invF.spools.value = item.spools ?? 1;
        invF.status.value = item.status || 'in_stock';
        invF.notes.value = item.notes || '';
        invOpenForm(true);
    });
}

async function invSave() {
    const payload = {
        material:     invF.material.value.trim(),
        manufacturer: invF.manufacturer.value.trim(),
        color_name:   invF.colorName.value.trim(),
        hex_color:    invF.hex.value.trim() || null,
        finish:       invF.finish.value.trim() || null,
        weight_g:     parseInt(invF.weight.value) || 1000,
        spools:       parseInt(invF.spools.value) || 0,
        status:       invF.status.value,
        notes:        invF.notes.value.trim() || null,
    };
    if (!payload.material || !payload.manufacturer || !payload.color_name) {
        alert('Material, fabricante e cor são obrigatórios.');
        return;
    }

    // Alerta de material misto ao cadastrar/editar direto no CFS (não bloqueia).
    if (payload.status === 'cfs') {
        const others = materialsInCfs().filter(m => m !== payload.material);
        // ao editar, ignora o próprio item se ele já estava no CFS
        const distinct = [...new Set(others)];
        if (distinct.length) {
            const proceed = confirm(
                `⚠️ ATENÇÃO: o CFS já tem ${distinct.join(', ')} e você está colocando ${payload.material}.\n\n`
                + `Materiais diferentes no mesmo CFS podem causar problemas de impressão `
                + `(temperaturas e velocidades incompatíveis). Deseja continuar mesmo assim?`
            );
            if (!proceed) return;
        }
    }

    const url = invEditingId ? `/api/inventory/${invEditingId}` : '/api/inventory';
    const method = invEditingId ? 'PATCH' : 'POST';
    const res = await fetch(url, {
        method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert('Erro ao salvar: ' + (err.error || res.status));
        return;
    }
    invCloseForm();
    loadInventory();
}

invAddBtn?.addEventListener('click', () => {
    if (invFormPanel.style.display === 'block' && !invEditingId) { invCloseForm(); return; }
    invEditingId = null;
    invClearForm();
    invOpenForm(false);
});
invCancelBtn?.addEventListener('click', invCloseForm);
invSaveBtn?.addEventListener('click', invSave);
invShowUsed?.addEventListener('change', loadInventory);

// Keep hex text <-> picker in sync
invF.hexPicker?.addEventListener('input', () => { invF.hex.value = invF.hexPicker.value; });
invF.hex?.addEventListener('input', () => {
    if (/^#[0-9a-fA-F]{6}$/.test(invF.hex.value)) invF.hexPicker.value = invF.hex.value;
});

// ─── Catalog pre-fill (window.treeData) ──────────────────────────────────────
function populateCatalogManufacturers() {
    if (!invCatMfr) return;
    const mfrs = Object.keys(treeData || {}).sort();
    invCatMfr.innerHTML = '<option value="">Fabricante...</option>' +
        mfrs.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
}

invCatMfr?.addEventListener('change', () => {
    const mfr = invCatMfr.value;
    invCatMat.innerHTML = '<option value="">Material...</option>';
    invCatVariant.innerHTML = '<option value="">Cor...</option>';
    invCatVariant.disabled = true;
    if (!mfr) { invCatMat.disabled = true; return; }
    const mats = Object.keys(treeData[mfr]?.materials || {}).sort();
    invCatMat.innerHTML += mats.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
    invCatMat.disabled = false;
});

invCatMat?.addEventListener('change', () => {
    const mfr = invCatMfr.value, mat = invCatMat.value;
    invCatVariant.innerHTML = '<option value="">Cor...</option>';
    if (!mfr || !mat) { invCatVariant.disabled = true; return; }
    const profiles = treeData[mfr]?.materials?.[mat]?.profiles || [];
    // Flatten all variants of all profiles/lines for this material
    let opts = '';
    profiles.forEach((p, pi) => {
        (p.variants || []).forEach((varnt, vi) => {
            const label = `${varnt.color_name || 'Cor'}${varnt.finish ? ' · ' + varnt.finish : ''} (${p.commercial_name})`;
            opts += `<option value="${pi}:${vi}">${escapeHtml(label)}</option>`;
        });
    });
    if (!opts) opts = '<option value="" disabled>Sem variantes no catálogo</option>';
    invCatVariant.innerHTML += opts;
    invCatVariant.disabled = false;
    // Pre-fill material + manufacturer even if no variant chosen yet
    invF.material.value = mat;
    invF.manufacturer.value = mfr;
});

invCatVariant?.addEventListener('change', () => {
    const mfr = invCatMfr.value, mat = invCatMat.value, sel = invCatVariant.value;
    if (!sel) return;
    const [pi, vi] = sel.split(':').map(Number);
    const profile = treeData[mfr]?.materials?.[mat]?.profiles?.[pi];
    const varnt = profile?.variants?.[vi];
    if (!varnt) return;
    invF.material.value = mat;
    invF.manufacturer.value = mfr;
    invF.colorName.value = varnt.color_name || '';
    invF.hex.value = varnt.hex_color || '';
    if (varnt.hex_color) invF.hexPicker.value = varnt.hex_color;
    invF.finish.value = varnt.finish || '';
    invF.weight.value = varnt.weight_g || 1000;

    // Preview visual da cor escolhida no catálogo
    if (invCatPreview) {
        invCatPreview.style.display = 'flex';
        invCatPreview.innerHTML = `
            <span class="sw" style="background:${varnt.hex_color || '#333'}"></span>
            <span class="txt">
                <strong>${escapeHtml(varnt.color_name || 'Cor')}</strong>
                <span>${escapeHtml(mfr)} ${escapeHtml(mat)}${varnt.finish ? ' · ' + escapeHtml(varnt.finish) : ''}${varnt.sku ? ' · ' + escapeHtml(varnt.sku) : ''}</span>
            </span>`;
    }
});


// ─── Identidade do usuário + permissão (auth feature flag) ────────────────────
// Busca /api/me: com auth desligada retorna guest/can_write=true; com ligada,
// o e-mail do header do proxy e se ele pode escrever. Aplica o modo somente
// leitura na UI (esconder botões de escrita). Isto é apenas UX — a fronteira
// de segurança é o gate no servidor (403 nos endpoints de escrita).
async function loadIdentity() {
    const userEl = document.getElementById('inv-user');
    try {
        const me = await (await fetch('/api/me')).json();
        const user = me.user || 'guest';
        if (userEl) userEl.textContent = `👤 ${user}`;

        const readonly = !me.can_write;
        document.body.classList.toggle('readonly', readonly);
        const banner = document.getElementById('inv-readonly-banner');
        if (banner) banner.style.display = readonly ? 'block' : 'none';
    } catch (err) {
        // Falha ao consultar identidade: assume o pior (somente leitura) por segurança.
        if (userEl) userEl.textContent = '👤 —';
        document.body.classList.add('readonly');
    }
}

// ─── Data da última atualização do servidor (build-info) ──────────────────────
async function loadBuildInfo() {
    const el = document.getElementById('inv-build');
    if (!el) return;
    try {
        const info = await (await fetch('/api/build-info')).json();
        if (info.updated_at) {
            const d = new Date(info.updated_at);
            const when = isNaN(d) ? info.updated_at : d.toLocaleString('pt-BR');
            const commit = info.commit ? ` · ${info.commit}` : '';
            el.textContent = `🕗 Atualizado ${when}${commit}`;
            el.title = info.commit_subject || 'Última atualização do servidor';
        } else {
            el.textContent = '🕗 Atualização desconhecida';
        }
    } catch (err) {
        el.textContent = '🕗 —';
    }
}

// ─── Inicialização: Estoque é a tela principal ────────────────────────────────
// A view de inventory começa ativa (definido no HTML e em currentView), então
// carregamos o estoque no load da página.
loadIdentity();
loadBuildInfo();
loadInventory();