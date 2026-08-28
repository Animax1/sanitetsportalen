
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

// Gates på MODULTILGANG, ikke på rolle (§7.4). Rollen sier ikke lenger noe om
// hva du får gjøre i denne modulen.
//
// Fellen dette lukker: en `read_write`-konto med bare `les` på pasientmodulen
// fikk `canWrite = true` her, så «Ny pasient» sto der, skjemaet åpnet seg —
// og lagringen møtte 403. Serveren var riktig hele tiden; grensesnittet
// gatet på feil kilde.
//
// **Standarden er ingen tilgang.** Mangler globalen, skjules alt som krever
// noe. Feiler malen, skal knappene forsvinne — ikke dukke opp.
function modulNivaa() {
  return ((window.MODUL_TILGANG || {}).patients || '').toLowerCase();
}

function erAdmin() {
  return !!(window.MODUL_TILGANG || {}).admin;
}

function applyRoleVisibility() {
  const nivaa = modulNivaa();

  const canWrite = nivaa === 'skriv_full';
  const isAdmin  = erAdmin();
  // `les` dekker både gamle `read_only` og `lead_view`, som var uenige om
  // lista: den ene fikk den, den andre ikke. Skillet lå aldri i dataene —
  // `/api/patients/` returnerer det samme til begge, og tavla viser de samme
  // pasientene. Lista gis derfor til alle som kan lese, og forskjellen
  // forsvinner med rollene i deploy 2.
  const canList  = nivaa !== '';

  if (!canWrite) {
    document.querySelectorAll('.write-only').forEach(el => {
      el.style.display = 'none';
    });
  }

  if (!canList) {
    document.querySelectorAll('.list-only').forEach(el => {
      el.style.display = 'none';
    });
    document.querySelectorAll('[data-tab="liste"]').forEach(el => el.classList.remove('active'));
    const listePanel = document.getElementById('tab-liste');
    if (listePanel) listePanel.classList.remove('active');
    const tavleLink = document.querySelector('[data-tab="tavle"]');
    if (tavleLink) tavleLink.classList.add('active');
    const tavlePanel = document.getElementById('tab-tavle');
    if (tavlePanel) tavlePanel.classList.add('active');
  }

  if (!isAdmin) {
    document.querySelectorAll('.admin-only').forEach(el => {
      el.style.display = 'none';
    });
  }
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

