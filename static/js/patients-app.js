// ════════════════════════════════════════════════════════
// APP-OPPSTART OG DELTE LASTERE
//
// Denne modulen lastes for ALLE roller. Alt her må fungere uten at
// patients-admin.js finnes — den lastes kun for admin (F7).
//
// Bootstrappen lå tidligere i den betinget lastede modulen. Å laste den
// slik F7 opprinnelig foreslo, ville tatt ned hele appen for read_only og
// read_write: tabellen, faneskiftet og auto-refresh startet derfra.
//
// Regel: alt en ikke-admin kan nå, skal ligge her. Kall til
// patients-admin.js må gå gjennom `_kall()`.
// ════════════════════════════════════════════════════════

// Kall en funksjon som bor i patients-admin.js, hvis modulen er lastet.
// `typeof` på et udeklarert navn er trygt i JS og gir 'undefined'.
function _kall(navn, ...args) {
  const fn = globalThis[navn];
  if (typeof fn === 'function') return fn(...args);
  return undefined;
}


document.addEventListener('input', (e) => {
  const el = e.target.closest('[data-input-action]');
  if (!el) return;
  const handler = globalThis[el.dataset.inputAction];
  if (typeof handler === 'function') handler();
});



// Leser kun. Skrivingen flyttet til /portal-admin/innstillinger/ (§4.1),
// og redigeringsfeltet som lå i innstillingsfanen fulgte med.
async function loadSettings() {
  const s = await (await fetch('/pasienter/api/settings/')).json();
  if (s.event_name) {
    const disp = document.getElementById('event-name-display');
    if (disp) disp.textContent = s.event_name;
  }
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
  if (tab === 'innstillinger') {
    loadSettings();
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
  if (document.getElementById('tab-tavle')?.classList.contains('active')) {
    renderBoard();
  }
  startRefreshInterval();
});