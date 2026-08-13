// ════════════════════════════════════════════════════════
// APP-OPPSTART OG DELTE LASTERE
//
// Denne modulen lastes for ALLE roller. Alt her må fungere uten at
// patients-stats.js finnes — den lastes kun for roller med
// statistikktilgang (F7).
//
// Bootstrappen lå tidligere i patients-stats.js. Å laste den fila betinget,
// slik F7 opprinnelig foreslo, ville tatt ned hele appen for read_only og
// read_write: tabellen, faneskiftet og auto-refresh startet derfra.
//
// Regel: alt en read_only- eller read_write-bruker kan nå, skal ligge her.
// `saveEventName` er med nettopp derfor — knappen er `write-only`, og
// read_write har skrivetilgang uten statistikktilgang.
// ════════════════════════════════════════════════════════

// Kall en funksjon som bor i patients-stats.js, hvis modulen er lastet.
// `typeof` på et udeklarert navn er trygt i JS og gir 'undefined'.
function _kall(navn, ...args) {
  const fn = globalThis[navn];
  if (typeof fn === 'function') return fn(...args);
  return undefined;
}

async function loadSettings() {
  const s = await (await fetch('/pasienter/api/settings/')).json();
  if (s.event_name) {
    const inp = document.getElementById('setting-event-name');
    if (inp) inp.value = s.event_name;
    const disp = document.getElementById('event-name-display');
    if (disp) disp.textContent = s.event_name;
  }
}

async function saveEventName() {
  const name = (document.getElementById('setting-event-name')?.value || '').trim();
  if (!name) return;
  await apiFetch('/pasienter/api/settings/', {
    method: 'PUT',
    body: JSON.stringify({ event_name: name })
  });
  const disp = document.getElementById('event-name-display');
  if (disp) disp.textContent = name;
}

async function loadSessionTimeout() {
  const el = document.getElementById('session-timeout-input');
  if (!el) return;
  try {
    const res = await apiFetch('/pasienter/api/session-timeout/');
    const d = await res.json();
    el.value = d.hours;
  } catch (e) {}
}

let lastForstehjelperEtag = null;

async function loadForstehjelpere() {
  const headers = { 'Cache-Control': 'no-cache' };
  if (lastForstehjelperEtag) {
    headers['If-None-Match'] = lastForstehjelperEtag;
  }
  const res = await fetch('/pasienter/api/forstehjelpere/', {
    cache: 'no-store',
    headers,
  });
  if (res.status === 304) {
    return;
  }
  const etag = res.headers.get('ETag');
  if (etag) lastForstehjelperEtag = etag;
  forstehjelpere = await res.json();
  _populateForstehjelperDropdown('n-forstehjelper', null);
  const eBeh = document.getElementById('e-forstehjelper');
  const currentEditBeh = eBeh && eBeh.value
    ? forstehjelpere.find(b => String(b.id) === String(eBeh.value)) || null
    : null;
  _populateForstehjelperDropdown('e-forstehjelper', currentEditBeh);
  _kall('renderForstehjelperAdmin');
}


let lastHelsepersonellEtag = null;

async function loadHelsepersonell() {
  const headers = { 'Cache-Control': 'no-cache' };
  if (lastHelsepersonellEtag) {
    headers['If-None-Match'] = lastHelsepersonellEtag;
  }
  const res = await fetch('/pasienter/api/helsepersonell/', {
    cache: 'no-store',
    headers,
  });
  if (res.status === 304) {
    return;
  }
  const etag = res.headers.get('ETag');
  if (etag) lastHelsepersonellEtag = etag;
  helsepersonellListe = await res.json();
  _populateHelsepersonellDropdown('n-helsepersonell', null);
  const eHp = document.getElementById('e-helsepersonell-ref');
  const currentEditHp = eHp && eHp.value
    ? helsepersonellListe.find(h => String(h.id) === String(eHp.value)) || null
    : null;
  _populateHelsepersonellDropdown('e-helsepersonell-ref', currentEditHp);
  _kall('renderHelsepersonellAdmin');
}


document.querySelectorAll('[data-tab]').forEach(link => link.addEventListener('click', e => {
  e.preventDefault();
  const tab = link.dataset.tab;
  document.querySelectorAll('[data-tab]').forEach(l => l.classList.remove('active'));
  link.classList.add('active');
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + tab)?.classList.add('active');
  if (tab === 'tavle')        renderBoard();
  if (tab === 'statistikk')   _kall('loadStats');
  if (tab === 'innstillinger') {
    loadSettings();
    loadSessionTimeout();
    loadForstehjelpere();
    loadHelsepersonell();
  }
}));

let refreshId = null;

async function doAutoRefresh() {
  await loadPatients();
  await loadForstehjelpere();
  await loadHelsepersonell();
  const t = document.querySelector('[data-tab].active')?.dataset.tab;
  if (t === 'tavle')      renderBoard();
  if (t === 'statistikk') _kall('loadStats');
}

function startRefreshInterval() {
  if (refreshId !== null) return;
  refreshId = setInterval(doAutoRefresh, 30000);
}

function stopRefreshInterval() {
  if (refreshId !== null) {
    clearInterval(refreshId);
    refreshId = null;
  }
}

document.addEventListener('visibilitychange', async () => {
  if (document.hidden) {
    stopRefreshInterval();
  } else {
    await doAutoRefresh();
    startRefreshInterval();
  }
});

document.addEventListener('DOMContentLoaded', async () => {
  applyRoleVisibility();
  initTable();
  const mineBtn = document.getElementById('btn-mine');
  if (mineBtn) mineBtn.classList.toggle('active-mine', mineOnly);
  await loadForstehjelpere();
  await loadHelsepersonell();
  await loadPatients();
  loadSettings();
  loadSessionTimeout();
  if (document.getElementById('tab-tavle')?.classList.contains('active')) {
    renderBoard();
  }
  startRefreshInterval();
});