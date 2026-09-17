// ════════════════════════════════════════════════════════════════════════════
// KO — situasjonsbildet. Pulje 1: skallet.
//
// Lastes kun av /ko/. Én fil, fordi det er én ting den gjør: sidebaren over
// hvem som har KO oppe (docs/FORSLAG_KO.md §5.3). Flatene er tomme markup i
// malen og trenger ingen kode ennå.
//
// Krever portal-utils.js (apiFetch, escapeHtml). Alt som *kjører* på toppnivå
// står nederst, som i de delte modulene — leser en tidlig linje en binding
// som ikke er nådd, dør siden på en ReferenceError før noe er tegnet.
// ════════════════════════════════════════════════════════════════════════════

// 30 sekunder. Lista svarer på hvem som sitter der, ikke på hva de gjør, og
// den endrer seg i minutter og ikke i sekunder. Bremsen på endepunktet er
// 120/m, altså to størrelsesordener over dette — den finnes for løkka, ikke
// for denne.
const KO_TILSTEDE_MS = 30000;

// Grensa for «nå». Under den sier vi ingenting om tid: et tall som teller
// sekunder på en kollega som sitter ved siden av deg er støy, og det er nettopp
// de lange fraværene kolonnen finnes for.
const KO_AKTIV_GRENSE_S = 120;

let koSidebarSynlig = true;

// **Regelen, ikke formateringen.** Egen funksjon fordi den avgjør noe: hva
// lista *påstår* om en person. `null` er «vet ikke» og skal aldri bli «0» —
// en sesjon fra før aktivitetsmålingen fantes ville da sett ut som om noen satt
// der. Se `inaktiv_sekunder` i core/sesjoner.py, som gjør det samme valget på
// den andre sida.
function koInaktivTekst(sekunder) {
  if (sekunder === null || sekunder === undefined) return 'ukjent';
  if (sekunder < KO_AKTIV_GRENSE_S) return 'aktiv';
  const min = Math.floor(sekunder / 60);
  if (min < 60) return min + ' min';
  return Math.floor(min / 60) + ' t';
}

// **En delt konto må se ut som en delt konto** (§4.5). «Enhet 2» er to til tre
// personer man må slå opp i vaktlista for å finne; «Kari Nordmann» er én. Blir
// lista noen gang lest i en personalsak, er den forskjellen alt.
function koKontomerke(rad) {
  if (rad.er_delt_konto) return 'delt';
  if (rad.er_global_admin) return 'admin';
  return '';
}

function koTilstedeRad(rad) {
  const merke = koKontomerke(rad);
  const merkeHtml = merke
    ? ' <span class="badge text-bg-secondary">' + escapeHtml(merke) + '</span>'
    : '';
  return '<li class="d-flex justify-content-between align-items-center gap-2 py-1">'
    + '<span>' + escapeHtml(rad.brukernavn) + merkeHtml + '</span>'
    + '<span class="text-muted">' + escapeHtml(koInaktivTekst(rad.inaktiv_s)) + '</span>'
    + '</li>';
}

function koTegnTilstede(rader) {
  const boks = document.getElementById('ko-tilstede');
  if (!boks) return;
  if (!rader || rader.length === 0) {
    // Ikke en tom liste uten forklaring: den leses som at noe er i stykker.
    boks.innerHTML = '<span class="text-muted">Ingen andre har KO oppe.</span>';
    return;
  }
  boks.innerHTML = '<ul class="list-unstyled mb-0">'
    + rader.map(koTilstedeRad).join('') + '</ul>';
}

async function koHentTilstede() {
  try {
    const res = await apiFetch('/ko/api/tilstede/');
    const data = await res.json();
    koTegnTilstede(data.data);
  } catch (e) {
    // En sidebar som feiler skal ikke ta med seg resten av siden, og den skal
    // heller ikke stå igjen med gamle navn som om de var ferske.
    const boks = document.getElementById('ko-tilstede');
    if (boks) boks.innerHTML = '<span class="text-muted">Fikk ikke kontakt.</span>';
  }
}

function koVisSidebar() {
  koSidebarSynlig = !koSidebarSynlig;
  const sidebar = document.getElementById('ko-sidebar');
  const knapp = document.getElementById('ko-sidebar-knapp');
  if (sidebar) sidebar.classList.toggle('d-none', !koSidebarSynlig);
  if (knapp) knapp.setAttribute('aria-expanded', koSidebarSynlig ? 'true' : 'false');
  if (koSidebarSynlig) koHentTilstede();
}

document.addEventListener('DOMContentLoaded', () => {
  koHentTilstede();
  setInterval(() => {
    // Ikke poll en sidebar ingen ser på. Det er den ene sparingen som betyr
    // noe her: flere operatører sitter på samme side hele vakta.
    if (koSidebarSynlig) koHentTilstede();
  }, KO_TILSTEDE_MS);
});
