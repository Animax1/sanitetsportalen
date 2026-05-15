// ════════════════════════════════════════════════════════
// TABULATOR – GRID COLUMNS
// ════════════════════════════════════════════════════════
function trFmt(cell) {
  const v = cell.getValue();
  const map = { 'Grønn': 'tb-gronn', 'Gul': 'tb-gul', 'Rød': 'tb-rod' };
  if (!v) return '<span class="triage-badge tb-ingen">–</span>';
  return `<span class="triage-badge ${map[v] || 'tb-ingen'}">${v}</span>`;
}

function totalFmt(cell) {
  const d = cell.getRow().getData();
  if (!d.inntid || !d.utskrevet) return '';
  const t1 = parseDt(d.inntid), t2 = parseDt(d.utskrevet);
  if (!t1 || !t2) return '';
  const m = (t2 - t1) / 60000;
  return m >= 0 ? fmtMin(m) : '';
}

const COLS = [
  { title:'Nr',             field:'patient_nr',      width:55,  frozen:true, sorter:'number',
    formatter:(c)=>`<strong>${c.getValue()}</strong>` },
  { title:'Triage',         field:'grovsortering',   width:85,  formatter:trFmt },
  { title:'Problemstilling',field:'problemstilling', width:175 },
  { title:'Årsak',          field:'arsak',           width:140 },
  { title:'Transport',      field:'transport',       width:135 },
  { title:'Inntid',         field:'inntid',          width:135 },
  { title:'Påbegynt',       field:'pabegynt',        width:135 },
  { title:'Plassering',     field:'plassering',      width:125 },
  { title:'Behandler',      field:'behandler',       width:115, formatter:(c)=>{ const v = c.getValue(); return v ? (v.name || v) : ''; } },
  { title:'Helsepersonell', field:'helsepersonell_ref', width:130, formatter:(c)=>{ const v = c.getValue(); return v ? (v.name || '') : ''; } },
  { title:'Inn-Obs',        field:'inn_obspost',     width:135 },
  { title:'UT-Obs',         field:'ut_obspost',      width:135 },
  { title:'Utskrevet',      field:'utskrevet',       width:135 },
  { title:'Utfall',         field:'utskrevet_til',   width:110 },
  { title:'Total',          field:'_total',          width:80,  formatter:totalFmt, sorter:false, headerSort:false },
];

function rowFmt(row) {
  const d = row.getData();
  const el = row.getElement();
  el.classList.remove('row-gronn','row-gul','row-rod','row-done');
  if (d.utskrevet) { el.classList.add('row-done'); return; }
  if (d.grovsortering === 'Grønn') el.classList.add('row-gronn');
  else if (d.grovsortering === 'Gul') el.classList.add('row-gul');
  else if (d.grovsortering === 'Rød') el.classList.add('row-rod');
}

function initTable() {
  table = new Tabulator('#patient-grid', {
    layout: 'fitDataFill',
    height: '100%',
    columns: COLS,
    rowFormatter: rowFmt,
    initialSort: [{ column:'patient_nr', dir:'asc' }],
    placeholder: '<div style="padding:2.5rem;text-align:center;color:#94a3b8"><i class="bi bi-person-plus" style="font-size:2.5rem"></i><br><br>Ingen pasienter registrert.<br>Klikk <strong>Ny pasient</strong> for å starte.</div>',
  });

  table.on('rowClick', function(e, row) {
    openEdit(row.getData());
  });

  loadPatients();
}

// ════════════════════════════════════════════════════════
// DATA LOADING
// ════════════════════════════════════════════════════════
async function loadPatients() {
  const url = '/pasienter/api/patients/' + (mineOnly ? '?mine=1' : '');
  const res  = await fetch(url);
  allPatients = await res.json();
  if (!table) return;
  await table.setData(allPatients);
  applyFilter();
  updateHeader(allPatients);
}

// Fase 5: Slå "Mine pasienter"-filter av/på. Refetcher fra server fordi
// filtreringen skjer server-side (Behandler.user / Helsepersonell.user).
async function toggleMine(checked) {
  mineOnly = !!checked;
  try { localStorage.setItem('mineOnly', mineOnly ? '1' : '0'); } catch (_) {}
  await loadPatients();
  const tavleTab = document.getElementById('tab-tavle');
  if (tavleTab && tavleTab.classList.contains('active')) {
    renderBoard();
  }
}

function updateHeader(pts) {
  const act = pts.filter(p => !p.utskrevet);

  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };

  setText('hdr-tilstede', act.length);
  setText('hdr-rod', act.filter(p => p.grovsortering === 'Rød').length);
  setText('hdr-gul', act.filter(p => p.grovsortering === 'Gul').length);
  setText('hdr-gronn', act.filter(p => p.grovsortering === 'Grønn').length);
  setText('hdr-ventende', act.filter(p => !p.pabegynt).length);
  setText('hdr-obs', act.filter(p =>
    (p.inn_obspost && !p.ut_obspost) ||
    (p.plassering && p.plassering.startsWith('Obs '))
  ).length);
  setText('hdr-utskrevet', pts.filter(p => !!p.utskrevet).length);
}

// ════════════════════════════════════════════════════════
// FILTER
// ════════════════════════════════════════════════════════
function setFilter(f) {
  activeFilter = f;
  const map = {
    'alle':       ['btn-alle',      'active-alle'],
    'rod':        ['btn-rod',       'active-rod'],
    'gul':        ['btn-gul',       'active-gul'],
    'rodgul':     ['btn-rodgul',    'active-rodgul'],
    'gronn':      ['btn-gronn',     'active-gronn'],
    'aktive':     ['btn-aktive',    'active-aktive'],
    'utskrevet':  ['btn-utskrevet', 'active-utskrevet'],
  };
  Object.entries(map).forEach(([key, [id, cls]]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.className = btn.className.replace(/active-\S+/g, '').trim();
    if (key === f) btn.classList.add(cls);
  });
  applyFilter();
}

function applyFilter() {
  if (!table || !allPatients.length) return;
  const q  = (document.getElementById('grid-search')?.value || '').toLowerCase().trim();
  const af = activeFilter;

  let filtered = [...allPatients];
  if      (af === 'rod')       filtered = filtered.filter(d => d.grovsortering === 'Rød' && !d.utskrevet);
  else if (af === 'gul')       filtered = filtered.filter(d => d.grovsortering === 'Gul' && !d.utskrevet);
  else if (af === 'rodgul')    filtered = filtered.filter(d =>
    (d.grovsortering === 'Rød' || d.grovsortering === 'Gul') && !d.utskrevet);
  else if (af === 'gronn')     filtered = filtered.filter(d => d.grovsortering === 'Grønn' && !d.utskrevet);
  else if (af === 'aktive')    filtered = filtered.filter(d => !d.utskrevet);
  else if (af === 'utskrevet') filtered = filtered.filter(d => !!d.utskrevet);
  if (q) filtered = filtered.filter(d =>
    Object.values(d).some(v => v && String(v).toLowerCase().includes(q)));

  table.setData(filtered);

  const count = filtered.length;
  const total = allPatients.length;
  const rowEl = document.getElementById('row-count');
  if (rowEl) rowEl.textContent = count === total ? `${total} pasienter` : `${count} av ${total} pasienter`;
}

// Plasseringer som kan romme flere pasienter (delte soner).
// Alle andre plasseringer er unike – bare én aktiv pasient om gangen.
const SHARED_PLASSERINGER = new Set(['Grønn sone', 'Gul sone']);

/**
 * Marker opptatte plasseringer i en plassering-dropdown som disabled,
 * med pasientnummer i label-en. Gjøres for både ny-skjema (n-plassering)
 * og rediger-skjema (e-plassering). excludePatientId brukes i rediger-modus
 * slik at pasienten ikke blokkerer sin egen plassering.
 */
function updatePlasseringDropdownState(selectId, excludePatientId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const activePatients = (allPatients || []).filter(p => !p.utskrevet);
  const taken = new Map();
  activePatients.forEach(p => {
    const loc = (p.plassering || '').trim();
    if (!loc || SHARED_PLASSERINGER.has(loc)) return;
    if (excludePatientId && String(p.id) === String(excludePatientId)) return;
    taken.set(loc, p.patient_nr);
  });
  sel.querySelectorAll('option').forEach(opt => {
    const raw = (opt.dataset.originalLabel || opt.textContent || '').trim();
    if (!opt.dataset.originalLabel) opt.dataset.originalLabel = raw;
    const val = opt.value;
    if (!val) return;
    if (taken.has(val)) {
      opt.disabled = true;
      opt.textContent = `${opt.dataset.originalLabel} (opptatt – #${taken.get(val)})`;
    } else {
      opt.disabled = false;
      opt.textContent = opt.dataset.originalLabel;
    }
  });
}

// ════════════════════════════════════════════════════════
// BOARD HELPERS
// ════════════════════════════════════════════════════════

function behandlerNavn(p) {
  if (p.behandler && p.behandler.name) return p.behandler.name;
  return '—';
}

function helsepersonellNavn(p) {
  if (p.helsepersonell_ref && p.helsepersonell_ref.name) return p.helsepersonell_ref.name;
  return '';
}

function totalDuration(p) {
  const t1 = parseDt(p.inntid);
  if (!t1) return '';
  const t2 = p.utskrevet ? parseDt(p.utskrevet) : new Date();
  if (!t2) return '';
  const mins = Math.floor((t2 - t1) / 60000);
  if (mins < 0) return '';
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}t ${m}min`;
}

// ════════════════════════════════════════════════════════
// BOARD (TAVLE)
// ════════════════════════════════════════════════════════
async function renderBoard() {
  const url = '/pasienter/api/patients/' + (mineOnly ? '?mine=1' : '');
  const res = await fetch(url);
  const pts = await res.json();
  const act = pts.filter(p => !p.utskrevet);

  function renderZone(elId, zoneName) {
    const container = document.getElementById(elId);
    if (!container) return;
    container.innerHTML = '';
    const zone_pts = act.filter(p => p.plassering === zoneName);
    if (!zone_pts.length) {
      container.innerHTML = '<span class="zone-empty">Ingen pasienter</span>';
      return;
    }
    zone_pts.forEach(p => {
      const card = document.createElement('div');
      const tCls = p.grovsortering === 'Rød'   ? 'occ-rod'
                 : p.grovsortering === 'Gul'   ? 'occ-gul'
                 : p.grovsortering === 'Grønn' ? 'occ-gronn' : '';
      card.className = `zone-card ${tCls}`;
      const hpNavn = helsepersonellNavn(p);
      card.innerHTML = `
        <div class="zc-head">
          <span class="zc-nr">#${p.patient_nr}</span>
          <span class="zc-prob">${escapeHtml(p.problemstilling || '–')}</span>
        </div>
        <div class="zc-meta">
          <span class="zc-behandler"><i class="bi bi-person-badge"></i> B: ${escapeHtml(behandlerNavn(p))}</span>
          <span class="zc-duration"><i class="bi bi-clock"></i> ${totalDuration(p)}</span>
        </div>
        ${hpNavn ? `<div class="zc-meta"><span class="zc-helsepersonell"><i class="bi bi-person"></i> H: ${escapeHtml(hpNavn)}</span></div>` : ''}`;
      card.onclick = () => openEdit(p);
      container.appendChild(card);
    });
  }
  renderZone('zone-gronn', 'Grønn sone');
  renderZone('zone-gul',   'Gul sone');

  function byPlace(label) { return act.find(p => p.plassering === label) || null; }

  function cell(label, p) {
    const div = document.createElement('div');
    div.className = 'obs-cell';
    if (p) {
      const cls = p.grovsortering === 'Grønn' ? 'occ-gronn'
                : p.grovsortering === 'Gul'   ? 'occ-gul'
                : p.grovsortering === 'Rød'   ? 'occ-rod' : '';
      if (cls) div.classList.add(cls);
      const hpNavn = helsepersonellNavn(p);
      div.innerHTML = `
        <div class="obs-bed-nr">${label}</div>
        <div class="obs-patient-nr">#${p.patient_nr}</div>
        <div class="obs-problem">${escapeHtml(p.problemstilling || '–')}</div>
        <div class="obs-meta">
          <span class="obs-behandler-name">B: ${escapeHtml(behandlerNavn(p))}</span>
          <span class="obs-duration">${totalDuration(p)}</span>
        </div>
        ${hpNavn ? `<div class="obs-meta"><span class="obs-behandler-name">H: ${escapeHtml(hpNavn)}</span></div>` : ''}`;
      div.onclick = () => openEdit(p);
    } else {
      div.innerHTML = `<div class="obs-bed-nr">${label}</div><div class="obs-empty">Ledig</div>`;
    }
    return div;
  }

  const akuttGrid = document.getElementById('akutt-grid');
  if (akuttGrid) {
    akuttGrid.innerHTML = '';
    for (let i = 1; i <= 4; i++) akuttGrid.appendChild(cell(`Akutt ${i}`, byPlace(`Akutt ${i}`)));
  }

  const obsGrid = document.getElementById('obs-grid');
  if (obsGrid) {
    obsGrid.innerHTML = '';
    for (let i = 1; i <= 20; i++) obsGrid.appendChild(cell(`Obs ${i}`, byPlace(`Obs ${i}`)));
  }

  const bGrid = document.getElementById('behandling-grid');
  if (bGrid) {
    bGrid.innerHTML = '';
    for (let i = 1; i <= 5; i++) bGrid.appendChild(cell(`Behandling ${i}`, byPlace(`Behandling ${i}`)));
  }
}
