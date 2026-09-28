
// ════════════════════════════════════════════════════════
// ROLE-BASED VISIBILITY
// ════════════════════════════════════════════════════════

// Modulnivået leses fra globalen malen setter (§7.4), med `nivaaMinst()` i
// portal-utils.js. Rollen sier ikke noe om hva du får gjøre i en modul.
// `modulNivaa()` sto her og ga nivået rått, og kallstedet sammenlignet med
// `===` — admin er `skriv_leder` og ble stengt ute av redigeringen.
//
// **Standarden er ingen tilgang.** Mangler globalen, oppfører koden seg som om
// brukeren ikke har noe.
//
// `applyRoleVisibility()` sto her og skjulte `.write-only`, `.admin-only` og
// `.list-only` i nettleseren. Alle tre rendres nå server-side i stedet:
// markupen — inkludert URL-ene til admin-sidene — lå i HTML-en for enhver som
// kunne lese modulen. Endepunktene var gatet, så det var ingen tilgangsgrense,
// men det er ingen grunn til å sende noe vi vet mottakeren ikke skal ha.

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
// HELPERS
// ════════════════════════════════════════════════════════
// Klokka i toppen er `portal-clock.js`, som på alle andre sider (26. sep. 2026,
// G3). Den sto her som en kopi — samme navn, samme markup — og pasientsiden
// var den ene som ikke lastet den felles.

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

