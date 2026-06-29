// ─── State ────────────────────────────────────────────────────────────────────
const treeData = window.treeData || {};
let currentManufacturer = null;
const comparedProfiles = new Map(); // profileId -> enriched profile object

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
            <div class="info-block-header">⚙️ Perfil Creality Print</div>
            <div class="info-grid">
                <div class="info-cell wide"><span class="lbl">Herda de</span><span class="v mono">${v(profile.inherits)}</span></div>
                <div class="info-cell"><span class="lbl">Nome do perfil</span><span class="v mono" style="font-size:.75rem">${v(profile.profile_name)}</span></div>
                <div class="info-cell"><span class="lbl">Impressora</span><span class="v">${v(profile.printer_model)}</span></div>
                <div class="info-cell"><span class="lbl">Bico</span><span class="v">${v(profile.nozzle_size,'mm')}</span></div>
                <div class="info-cell"><span class="lbl">Base ID</span><span class="v mono">${v(profile.base_id)}</span></div>
                <div class="info-cell"><span class="lbl">Versão CP</span><span class="v">${v(profile.creality_print_version)}</span></div>
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
            <td><a class="dl-link" href="${row.download_url}" onclick="event.stopPropagation()">↓ ZIP</a></td>
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

        tr.addEventListener('click', e => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'A') return;
            // Toggle compare selection
            const profile = rows.find(r => r.profile_id === pid);
            if (comparedProfiles.has(pid)) comparedProfiles.delete(pid);
            else if (profile) comparedProfiles.set(pid, profile);
            syncHighlights();
            renderCompare();

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

    { sec:'Perfil CP',    lbl:'Herda de',          fn: p => `<span class="mono" style="font-size:.72rem">${v(p.inherits)}</span>` },
    { sec:'Perfil CP',    lbl:'Base ID',           fn: p => v(p.base_id) },
    { sec:'Perfil CP',    lbl:'Download',          fn: p => `<a class="dl-link" href="${p.download_url}">↓ ZIP</a>` },
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
