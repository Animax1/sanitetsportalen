
// ════════════════════════════════════════════════════════
// IDEMPOTENS-NØKKEL (F3)
// ════════════════════════════════════════════════════════

// Lages når registreringsskjemaet åpnes og følger hver innsending fra det
// skjemaet. Serveren oppretter kun én pasient per nøkkel, så en automatisk
// nettverks-retry eller en dobbeltinnsending guarden ikke fanget gir ikke to
// rader. To faner får hver sin nøkkel — det er to reelle registreringer.
function nyIdempotensNokkel() {
  // crypto.randomUUID() finnes kun i «secure context», altså ikke over ren
  // HTTP. OFFLINE_MODE kjører nettopp uten TLS, så fallbacken er ikke
  // teoretisk — uten den ville feltbruk kastet TypeError ved hver
  // registrering. getRandomValues er tilgjengelig også uten TLS.
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
      const a = new Uint8Array(16);
      crypto.getRandomValues(a);
      return Array.from(a, b => b.toString(16).padStart(2, '0')).join('');
    }
  } catch (e) {
    // faller gjennom til siste utvei
  }
  return 'k' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
}


// ════════════════════════════════════════════════════════
// ROLE-BASED VISIBILITY
// ════════════════════════════════════════════════════════

// Modulnivået, lest fra globalen malen setter (§7.4). Rollen sier ikke noe om
// hva du får gjøre i en modul.
//
// **Standarden er ingen tilgang.** Mangler globalen, oppfører koden seg som om
// brukeren ikke har noe.
//
// `applyRoleVisibility()` sto her og skjulte `.write-only`, `.admin-only` og
// `.list-only` i nettleseren. Alle tre rendres nå server-side i stedet:
// markupen — inkludert URL-ene til admin-sidene — lå i HTML-en for enhver som
// kunne lese modulen. Endepunktene var gatet, så det var ingen tilgangsgrense,
// men det er ingen grunn til å sende noe vi vet mottakeren ikke skal ha.
function modulNivaa() {
  return ((window.MODUL_TILGANG || {}).patients || '').toLowerCase();
}

// ════════════════════════════════════════════════════════
// STATE & MODALS
// ════════════════════════════════════════════════════════
// Chart.js-temaet og statistikktilstanden lå her fram til statistikk ble egen
// modul. De hører til statistikk.js nå — pasientsiden laster ikke Chart.js.
let table = null;
let currentEditId = null;
let nyPasientNokkel = null;   // F3: settes av openNewModal()

let activeFilter = 'alle';
let allPatients = [];
let mineOnly = (typeof localStorage !== 'undefined' && localStorage.getItem('mineOnly') === '1');
let boardMineFilter = false;

function isMine(p) {
  if (window.MY_FORSTEHJELPER_ID && p.forstehjelper
      && p.forstehjelper.id === window.MY_FORSTEHJELPER_ID) return true;
  if (window.MY_HELSEPERSONELL_ID && p.helsepersonell_ref
      && p.helsepersonell_ref.id === window.MY_HELSEPERSONELL_ID) return true;
  return false;
}

let forstehjelpere = [];
let helsepersonellListe = [];

const bsNew   = new bootstrap.Modal(document.getElementById('newModal'));
const bsEdit  = new bootstrap.Modal(document.getElementById('editModal'));

// ════════════════════════════════════════════════════════
// CLOCK & HELPERS
// ════════════════════════════════════════════════════════
const DAYS_NO = ['søndag', 'mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag'];

function updateClock() {
  const now = new Date();
  const el = document.getElementById('header-dt');
  if (!el) return;

  const dayStr = DAYS_NO[now.getDay()];
  const dateStr =
    String(now.getDate()).padStart(2, '0') + '.' +
    String(now.getMonth() + 1).padStart(2, '0') + '.' +
    now.getFullYear();

  const timeStr = now.toLocaleTimeString('no-NO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });

  el.innerHTML = `
    <div style="font-size:0.8rem;opacity:0.85;">${dayStr} ${dateStr}</div>
    <div style="font-size:1.35rem;font-weight:300;letter-spacing:0.07em;">${timeStr}</div>
  `;
}

setInterval(updateClock, 1000);
updateClock();

function nowStr() {
  const d = new Date();
  return [
    String(d.getDate()).padStart(2,'0'),
    String(d.getMonth()+1).padStart(2,'0'),
    d.getFullYear()
  ].join('.') + ' ' +
  [String(d.getHours()).padStart(2,'0'), String(d.getMinutes()).padStart(2,'0')].join(':');
}

function stamp(id) {
  const el = document.getElementById(id);
  if (el) el.value = nowStr();
}

function parseDt(s) {
  if (!s) return null;
  const m = s.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{2}):(\d{2})/);
  if (m) return new Date(+m[3], +m[2]-1, +m[1], +m[4], +m[5]);
  return null;
}

function updateTotal() {
  const t1 = parseDt(document.getElementById('e-inntid')?.value);
  const t2 = parseDt(document.getElementById('e-utskrevet')?.value);
  const el = document.getElementById('e-total-time');
  if (!el) return;
  if (t1 && t2) {
    const m = (t2 - t1) / 60000;
    el.textContent = m >= 0 ? fmtMin(m) : '–';
  } else { el.textContent = '–'; }
}

// Utskrevet-tidspunktet påvirker totaltiden, så de to hører sammen. Lå
// tidligere i markup som `onclick="stamp('e-utskrevet');updateTotal()"` — en
// sammensatt inline handler som ikke lot seg uttrykke med ett data-action (F5).
function stampUtskrevet() {
  stamp('e-utskrevet');
  updateTotal();
}

document.getElementById('e-inntid')?.addEventListener('input', updateTotal);

