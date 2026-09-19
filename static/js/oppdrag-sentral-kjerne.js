// ════════════════════════════════════════════════════════
// Sentralbordet i oppdragsmodulen (/oppdrag/).
//
// Laster KUN portal-utils.js. `patients-utils.js` gjør arbeid på toppnivå —
// Chart.defaults og `new bootstrap.Modal(...)` mot pasientskjemaene — og
// kaster på en side uten dem. Trengs en helper derfra, skal den flyttes til
// portal-utils.js, ikke kopieres. JsModulLastingTests håndhever det.
//
// All brukerdata som settes inn med innerHTML escapes: fritekst og
// lokasjonsnavn er de første virkelig frie feltene i portalen som ikke er en
// nedtrekksliste.
// ════════════════════════════════════════════════════════

let enheter = [];
let lokasjoner = [];
let oppdragsliste = [];
let enhetsadmin = [];

// ETag-verdiene fra forrige poll. Serveren svarer 304 når ingenting er
// endret, og da rendrer vi ikke på nytt — under en rolig time er trafikken
// nær null selv med mange pålogget.
let etagEnheter = null;
let etagOppdrag = null;
//: Om første henting har lykkes. Til da viser listene «kunne ikke hente»,
//: ikke «ingen enheter på vakt» — tom og ikke hentet er to ulike ting
//: (André, 13. sep. 2026: plassholderne sto tomme ved første besøk).
let enheterHentet = false;
let oppdragHentet = false;

// **Besetningen er vaktlistas data, lånt inn** (§6 i vaktlistenotatet).
// Oppdragsmodulen importerer ikke vaktlista i Python — koblingen ligger her,
// i nettleseren, som `Ressurs.enhet` peker sammen.
//
// Hentes **når operatøren spør**, ikke ved hver polling: enhetslista pollet
// hvert par sekund ville gitt ett kall per bil per runde, og svaret er
// dessuten bare interessant i det øyeblikket noen lurer.

const STATUS_REKKEFOLGE = ['venter', 'rykker_ut', 'fremme', 'avreist', 'leverer', 'ledig'];
//: Lista sorteres på hastegraden operatøren satte (André, 12. sep. 2026),
//: og innenfor den på nummer. Ferdige oppdrag står nederst.
const HASTEGRAD_REKKEFOLGE = ['Akutt', 'Haster', 'Vanlig', 'Drift'];
//: «Trenger ny ressurs» blir tydeligere jo lenger det står (minutter).
const MANGLER_TRINN = [[15, 'alvorlig'], [5, 'varsel'], [0, 'ny']];








function problemstillingerFor(hastegrad) {
  const kart = globalThis.window?.OPPDRAG_PROBLEMSTILLINGER_FOR || {};
  return kart[hastegrad] || [];
}


function fyllProblemstillinger(prefiks, hastegrad, valgt) {
  // Nedtrekket bygges om av hastegraden (André, 12. sep. 2026: «teknisk [nå Drift]
  // hastegrad endrer innholdet i problemstillinger»). Står den valgte ikke
  // i den nye lista, velges den første — «Udefinert». Antallet settes av
  // bilen, ikke her (12. sep. 2026).
  const sel = document.getElementById(`${prefiks}-problemstilling`);
  if (!sel) return;
  // Uten hastegrad finnes ingen liste (19. sep. 2026: «nytt oppdrag uten
  // hendelse skal ha ingen hastegrad selektert»). Ett tomt valg som sier
  // hvorfor, så feltet ikke ser ødelagt ut.
  if (!hastegrad) {
    sel.innerHTML = '<option value="">Velg hastegrad først</option>';
    return;
  }
  const liste = problemstillingerFor(hastegrad);
  const ny = liste.includes(valgt) ? valgt : (liste[0] || '');
  sel.innerHTML = liste.map((p) =>
    `<option value="${escHtmlValue(p)}"${p === ny ? ' selected' : ''}>${escapeHtml(p)}</option>`).join('');
}


function hastegradEndret(prefiks) {
  const h = document.getElementById(`${prefiks}-hastegrad`)?.value || '';
  const valgt = document.getElementById(`${prefiks}-problemstilling`)?.value || '';
  fyllProblemstillinger(prefiks, h, valgt);
  // Knappene i «Nytt oppdrag» speiler nedtrekket (19. sep. 2026). Inne her
  // og ikke i en egen funksjon: testene henter `hastegradEndret` alene, og
  // en tilstandsløs DOM uten `querySelectorAll` skal ikke velte den.
  if (prefiks === 'nytt' && typeof document.querySelectorAll === 'function') {
    document.querySelectorAll('#nytt-hastegrad-valg .hastegrad-knapp').forEach((k) => {
      const valgt = (k.dataset || {}).arg === h;
      if (k.classList) k.classList.toggle('valgt', valgt);
      if (k.setAttribute) k.setAttribute('aria-checked', valgt ? 'true' : 'false');
    });
  }
}


// Knappene i «Nytt oppdrag» (André, 19. sep. 2026: «lignende oppsett som ved
// prioritet fra ny hendelse»). Verdien bor fortsatt i det skjulte nedtrekket
// `#nytt-hastegrad`; knappen setter det og går veien om `hastegradEndret`,
// så problemstillingene følger med som før.
function velgHastegrad(verdi) {
  const sel = document.getElementById('nytt-hastegrad');
  if (!sel) return;
  sel.value = verdi;
  hastegradEndret('nytt');
}







// ════════════════════════════════════════════════════════
// oppdrag-sentral-kjerne.js
// ════════════════════════════════════════════════════════
//
// Tilstand, polling og enhetslista.
//
// **Denne fila må lastes først.** All toppnivå-tilstand står her, og
// `let`/`const` på toppnivå er skript-scopede: en fil som leser dem før
// denne er kjørt, treffer en temporal dead zone.
//
// Delt ut av `oppdrag-sentral.js` 14. sep. 2026 (gjeldspunkt 3.6).
// Fila var 1 991 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/oppdrag/sentral.html` og deler ett globalt navnerom som
// før. `JsSplittenErKompletTests` håndhever at ingen funksjon forsvant
// eller ble duplisert.
// ════════════════════════════════════════════════════════

// ── Enhetsliste ─────────────────────────────────────────

// **Ressurslista tegnes av `oppdrag-kort.js`, delt med `/ko/`** (18. sep.
// 2026). Sentralbordet eier `enheter` og hentingen med ETag; tegningen er
// felles, slik at de to sidene ikke kan komme til å vise ulike ting om samme
// enhet. Se fila for hvorfor.
function renderEnheter() {
  // **Sentralbordet eier `enheter`, og melder det inn her.** `lastEnheter()`
  // bytter ut arrayen uten å tegne, så den delte koden må spørre etter den
  // levende lista og ikke huske forrige — se `settEnhetslisteKilde` i
  // oppdrag-kort.js.
  //
  // Innmeldingen står *i* tegnefunksjonen og ikke som en linje på toppnivå,
  // og det er en testbarhetsregel: en toppnivålinje kjøres ikke av
  // `build_harness()`, så kallstedet kunne fjernes uten at noe ble rødt.
  // Mutanten overlevde nøyaktig sånn 18. sep. 2026. Kallet er idempotent, og
  // den første tegningen kommer alltid før et besetningspanel kan åpnes.
  settEnhetslisteKilde(() => enheter);
  tegnEnhetsliste(enheter);
}


















async function _settVakt(id, paVakt) {
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/vakt/`, {
    method: 'POST',
    body: JSON.stringify({ pa_vakt: paVakt }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke endre vaktstatus.');
    return;
  }
  etagEnheter = null;   // tving ny henting, ellers svarer serveren 304
  await lastAlt();
  if (document.getElementById('enhetsadminliste')) await lastEnhetsadmin();
}

async function taAvVakt(id) { await _settVakt(id, false); }
async function settPaaVakt(id) { await _settVakt(id, true); }


async function _settVaktmodus(id, passiv) {
  // **Passiv er ikke «av vakt»** (André, 16. sep. 2026), og derfor et eget
  // endepunkt: «kan ikke få nye oppdrag» er noe helt annet enn «ligger og
  // sover, men kommer».
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/vaktmodus/`, {
    method: 'POST',
    body: JSON.stringify({ passiv }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke endre vaktmodus.');
    return;
  }
  etagEnheter = null;   // tving ny henting, ellers svarer serveren 304
  await lastAlt();
}

async function settPassivVakt(id) { await _settVaktmodus(id, true); }
async function settAktivVakt(id) { await _settVaktmodus(id, false); }


async function avventOppdrag(arg) {
  // `arg` er «<oppdrag>:<enhet>» — klikkdelegeringen sender ett argument.
  const [oppdragId, enhetId] = String(arg).split(':');
  const res = await apiFetch(
    `/oppdrag/api/oppdrag/${oppdragId}/avvent/${enhetId}/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke sette avventer.');
    return;
  }
  etagOppdrag = null;
  await lastAlt();
}


async function kvitterAvbrutt(oppdragId) {
  // Den andre veien — å sende en ny enhet — kvitterer av seg selv på
  // serveren. Denne finnes for tilfellet der ingen skal sendes.
  const res = await apiFetch(
    `/oppdrag/api/oppdrag/${oppdragId}/kvitter-avbrutt/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke kvittere.');
    return;
  }
  etagOppdrag = null;
  await lastAlt();
}
