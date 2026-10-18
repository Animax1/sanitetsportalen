// ════════════════════════════════════════════════════════
// TABULATOR – GRID COLUMNS
// ════════════════════════════════════════════════════════
function trFmt(cell) {
  const v = cell.getValue();
  const map = { 'Grønn': 'tb-gronn', 'Gul': 'tb-gul', 'Rød': 'tb-rod' };
  if (!v) return '<span class="triage-badge tb-ingen">–</span>';
  return `<span class="triage-badge ${map[v] || 'tb-ingen'}">${escapeHtml(v)}</span>`;
}

// Navnet på førstehjelperen eller helsepersonellet i en celle — escapet
// (sikkerhetsgjennomgangen 28. sep. 2026). En streng fra en formatter settes
// inn med `innerHTML` av Tabulator; standardformatteren escaper, en egen gjør
// det ikke. Alle andre steder navnene vises, escapes de eller settes som tekst.
function personFmt(cell) {
  const v = cell.getValue();
  if (!v) return '';
  return escapeHtml(typeof v === 'object' ? (v.name || '') : v);
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
  { title:'Førstehjelper',  field:'forstehjelper',   width:115, formatter:personFmt },
  { title:'Helsepersonell', field:'helsepersonell_ref', width:130, formatter:personFmt },
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
// ETag for pasientlista. Hver klient poller hvert 30. sekund, og lista er
// det største svaret i appen — 454 kB ved 1000 pasienter. Endrer ingenting
// seg mellom to pollinger, svarer serveren 304 uten kropp.
let lastPatientsEtag = null;

async function loadPatients() {
  const url = '/pasienter/api/patients/' + (mineOnly ? '?mine=1' : '');
  const headers = {};
  if (lastPatientsEtag) headers['If-None-Match'] = lastPatientsEtag;

  const res = await apiFetch(url, { headers });

  // 304: ingenting er endret, og svaret har ingen kropp. Behold dataene vi
  // allerede har — å kalle res.json() her ville kastet.
  //
  // Men filteret må fortsatt anvendes: setFilter() kaller hit nettopp for å
  // bytte visning når «Mine pasienter» slås av eller på, og stoler på at vi
  // kjører applyFilter(). Returnerer vi rått her, blir griden stående med
  // forrige filter selv om knappen har byttet utseende.
  if (res.status === 304) {
    if (table) applyFilter();
    return;
  }

  const etag = res.headers.get('ETag');
  if (etag) lastPatientsEtag = etag;

  allPatients = await res.json();
  if (!table) return;
  await table.setData(allPatients);
  applyFilter();
  updateHeader(allPatients);
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
async function setFilter(f) {
  activeFilter = f;
  const map = {
    'alle':       ['btn-alle',      'active-alle'],
    'rod':        ['btn-rod',       'active-rod'],
    'gul':        ['btn-gul',       'active-gul'],
    'rodgul':     ['btn-rodgul',    'active-rodgul'],
    'gronn':      ['btn-gronn',     'active-gronn'],
    'aktive':     ['btn-aktive',    'active-aktive'],
    'utskrevet':  ['btn-utskrevet', 'active-utskrevet'],
    'mine':       ['btn-mine',      'active-mine'],
  };
  Object.entries(map).forEach(([key, [id, cls]]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.className = btn.className.replace(/active-\S+/g, '').trim();
    if (key === f) btn.classList.add(cls);
  });
  const newMineOnly = (f === 'mine');
  if (newMineOnly !== mineOnly) {
    mineOnly = newMineOnly;
    try { localStorage.setItem('mineOnly', mineOnly ? '1' : '0'); } catch (_) {}
    await loadPatients();
  } else {
    applyFilter();
  }
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

function forstehjelperNavn(p) {
  if (p.forstehjelper && p.forstehjelper.name) return p.forstehjelper.name;
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
//
// **Dra og slipp** (18. okt. 2026, som KO-tavla i `ko-tavle.js`): et kort dras
// til en sone eller en ledig plass, og slippet er `PUT {plassering}` — samme
// endepunkt og samme validering som redigeringsskjemaet. Obs-stemplingen og
// unikheten avgjøres fortsatt av serveren (`patients/services.py`); tavla
// avviser bare det den selv kan se, så et slipp på en opptatt seng ikke koster
// en tur til serveren for å få et nei.
//
// Reglene er egne funksjoner (`tavleMaal`, `tavleAvgjorSlipp`, `tavleKanDra`),
// fordi en regel inne i en lytter ikke lar seg kjøre i en test.

//: Så langt må pekeren flytte seg før et trykk blir et drag. Under det er det
//: et klikk, og klikket åpner pasienten — som før. Samme grense som KO-tavla.
const TAVLE_DRAGRENSE_PX = 6;

let tavleDrag = null;            // pågående drag: {id, fra, x, y, drar, spokelse, tekst}
let tavleTegnEtterDrag = false;  // en auto-refresh kom mens kortet var i lufta
let tavleSvelgKlikk = false;     // klikket nettleseren sender etter et drag

// Samme port som `openEdit()`: den som ikke kan lagre skjemaet, kan ikke dra.
function tavleKanDra() {
  return nivaaMinst(window.MODUL_TILGANG, 'patients', 'skriv_full');
}

// Merker et kort som drabart. Ett sted, så porten ikke står i hver bygger.
function tavleGjorDrabar(el, p) {
  if (!tavleKanDra()) return;
  el.setAttribute('data-pasient', String(p.id));
  el.setAttribute('data-fra', p.plassering || '');
  el.classList.add('tavle-dras');
}

// Hva pekeren står over: `{plassering, opptattAv}`, eller null utenfor tavla.
// `opptattAv` er pasientnummeret som står i en seng — sonene får aldri det,
// fordi de er delte. Lista over delte plasseringer bor dermed bare på serveren.
function tavleMaal(el) {
  const mal = el && el.closest ? el.closest('[data-plassering]') : null;
  if (!mal) return null;
  return {
    plassering: mal.getAttribute('data-plassering'),
    opptattAv: mal.getAttribute('data-opptatt-av') || '',
  };
}

// null: ingenting skal skje. {feil}: si fra. {plassering}: flytt dit.
function tavleAvgjorSlipp(fra, maal) {
  if (!maal || !maal.plassering || maal.plassering === (fra || '')) return null;
  if (maal.opptattAv) {
    return { feil: `${maal.plassering} er opptatt av pasient #${maal.opptattAv}.` };
  }
  return { plassering: maal.plassering };
}

async function tavleFlytt(id, plassering) {
  try {
    const res = await apiFetch(`/pasienter/api/patients/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({ plassering }),
    });
    if (!res.ok) {
      let msg = 'Kunne ikke flytte pasienten.';
      try { const d = await res.json(); if (d.error) msg = d.error; } catch (e) {}
      window.alert(msg);
    }
  } finally {
    // Også etter et nei: en kollega kan ha tatt sengen, og det skal synes.
    await loadPatients();
    await renderBoard();
  }
}

function tavleRyddDrag() {
  if (tavleDrag && tavleDrag.spokelse) tavleDrag.spokelse.remove();
  tavleDrag = null;
  document.body.classList.remove('tavle-drar');
  document.querySelectorAll('.tavle-mal-over').forEach(el => el.classList.remove('tavle-mal-over'));
}

// Kalles fra `DOMContentLoaded` i patients-app.js — alt som kjører på
// toppnivå står i den siste fila.
function tavleLyttere() {
  const panel = document.getElementById('tab-tavle');
  if (!panel) return;
  panel.addEventListener('pointerdown', e => {
    const kort = e.target.closest('[data-pasient]');
    if (!kort || e.button > 0) return;
    tavleDrag = { id: Number(kort.getAttribute('data-pasient')), fra: kort.getAttribute('data-fra') || '',
                  x: e.clientX, y: e.clientY, drar: false, spokelse: null,
                  tekst: (kort.querySelector('.zc-nr, .obs-patient-nr')?.textContent || '').trim() };
  });
  window.addEventListener('pointermove', e => {
    const d = tavleDrag;
    if (!d) return;
    if (!d.drar && Math.hypot(e.clientX - d.x, e.clientY - d.y) < TAVLE_DRAGRENSE_PX) return;
    if (!d.drar) {
      d.drar = true;
      d.spokelse = document.createElement('div');
      d.spokelse.className = 'tavle-spokelse';
      d.spokelse.textContent = d.tekst;
      document.body.appendChild(d.spokelse);
      document.body.classList.add('tavle-drar');
    }
    e.preventDefault();
    d.spokelse.style.left = e.clientX + 'px';
    d.spokelse.style.top = e.clientY + 'px';
    document.querySelectorAll('.tavle-mal-over').forEach(el => el.classList.remove('tavle-mal-over'));
    const under = document.elementFromPoint(e.clientX, e.clientY);
    const mal = under && under.closest ? under.closest('[data-plassering]') : null;
    if (mal && !mal.hasAttribute('data-opptatt-av')) mal.classList.add('tavle-mal-over');
  });
  window.addEventListener('pointerup', e => {
    const d = tavleDrag;
    // Et trykk som ikke ble et drag, er et klikk, og `onclick` tar det.
    if (!d || !d.drar) { tavleDrag = null; return; }
    tavleRyddDrag();
    tavleSvelgKlikk = true;
    setTimeout(() => { tavleSvelgKlikk = false; }, 0);
    const utfall = tavleAvgjorSlipp(d.fra, tavleMaal(document.elementFromPoint(e.clientX, e.clientY)));
    if (utfall && utfall.feil) window.alert(utfall.feil);
    if (utfall && utfall.plassering) { tavleTegnEtterDrag = false; tavleFlytt(d.id, utfall.plassering); return; }
    if (tavleTegnEtterDrag) { tavleTegnEtterDrag = false; renderBoard(); }
  });
  window.addEventListener('pointercancel', tavleRyddDrag);
  // **Klikket etter et drag svelges** i capture-fasen, før kortets `onclick`:
  // slippes kortet der det kom fra, ville det ellers åpnet pasienten.
  panel.addEventListener('click', e => {
    if (tavleSvelgKlikk) { tavleSvelgKlikk = false; e.stopPropagation(); }
  }, true);
}

async function toggleBoardMine() {
  boardMineFilter = !boardMineFilter;
  const btn = document.getElementById('btn-board-mine');
  if (btn) btn.classList.toggle('active-mine', boardMineFilter);
  await renderBoard();
}

// Egen ETag for tavla. Den henter den ufiltrerte lista, altså en annen URL
// enn loadPatients() når «Mine pasienter» er på — og dermed en annen ETag.
// Uten dette hentet tavlefanen hele lista på nytt ved hver auto-refresh,
// i tillegg til loadPatients(). Det doblet trafikken for de som står på tavla.
let lastBoardEtag = null;
let lastBoardPatients = [];

async function renderBoard() {
  // Tegnes tavla om mens et kort er i lufta, forsvinner målet under pekeren.
  // Auto-refreshen venter derfor til slippet.
  if (tavleDrag && tavleDrag.drar) { tavleTegnEtterDrag = true; return; }
  const url = '/pasienter/api/patients/';
  const headers = {};
  if (lastBoardEtag) headers['If-None-Match'] = lastBoardEtag;

  const res = await apiFetch(url, { headers });

  let pts;
  if (res.status === 304) {
    pts = lastBoardPatients;
  } else {
    const etag = res.headers.get('ETag');
    if (etag) lastBoardEtag = etag;
    pts = await res.json();
    lastBoardPatients = pts;
  }

  const act = pts.filter(p => !p.utskrevet);

  function renderZone(elId, zoneName) {
    const container = document.getElementById(elId);
    if (!container) return;
    container.setAttribute('data-plassering', zoneName);
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
      card.className = `zone-card ${tCls}${boardMineFilter && !isMine(p) ? ' not-mine' : ''}`;
      const hpNavn = helsepersonellNavn(p);
      card.innerHTML = `
        <div class="zc-head">
          <span class="zc-nr">#${p.patient_nr}</span>
          <span class="zc-prob">${escapeHtml(p.problemstilling || '–')}</span>
        </div>
        <div class="zc-meta">
          <span class="zc-forstehjelper"><i class="bi bi-person-badge"></i> B: ${escapeHtml(forstehjelperNavn(p))}</span>
          <span class="zc-duration"><i class="bi bi-clock"></i> ${totalDuration(p)}</span>
        </div>
        ${hpNavn ? `<div class="zc-meta"><span class="zc-helsepersonell"><i class="bi bi-person"></i> H: ${escapeHtml(hpNavn)}</span></div>` : ''}`;
      tavleGjorDrabar(card, p);
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
    div.setAttribute('data-plassering', label);
    if (p) {
      div.setAttribute('data-opptatt-av', String(p.patient_nr));
      const cls = p.grovsortering === 'Grønn' ? 'occ-gronn'
                : p.grovsortering === 'Gul'   ? 'occ-gul'
                : p.grovsortering === 'Rød'   ? 'occ-rod' : '';
      if (cls) div.classList.add(cls);
      if (boardMineFilter && !isMine(p)) div.classList.add('not-mine');
      const hpNavn = helsepersonellNavn(p);
      div.innerHTML = `
        <div class="obs-bed-nr">${label}</div>
        <div class="obs-patient-nr">#${p.patient_nr}</div>
        <div class="obs-problem">${escapeHtml(p.problemstilling || '–')}</div>
        <div class="obs-meta">
          <span class="obs-forstehjelper-name">B: ${escapeHtml(forstehjelperNavn(p))}</span>
          <span class="obs-duration">${totalDuration(p)}</span>
        </div>
        ${hpNavn ? `<div class="obs-meta"><span class="obs-forstehjelper-name">H: ${escapeHtml(hpNavn)}</span></div>` : ''}`;
      tavleGjorDrabar(div, p);
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
