// ════════════════════════════════════════════════════════════════════════════
// KO — situasjonsbildet. Pulje 1 (sidebaren), 2 (loggen), 3 (ressursbildet).
//
// Lastes kun av /ko/. Fortsatt **én fil**: 1 800-linjersgrensa i
// core/tests_js_splitt.py gjelder de delte modulene, og denne er langt under
// den. Deles den en dag, er regelen at alt som *kjører* på toppnivå står i den
// siste fila — derfor ligger den ene `DOMContentLoaded`-kroken nederst her
// allerede, som i de delte modulene.
//
// Krever portal-utils.js (apiFetch, escapeHtml, data-action-delegeringen).
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

// Nedtrekket er lukket når sida lastes. Var `true` i pulje 1, da lista var en
// egen kolonne som sto åpen.
let koSidebarSynlig = false;

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

// **Sidebaren er et Bootstrap-nedtrekk, ikke en kolonne** (17. sep. 2026).
// Knappen har derfor `data-bs-toggle="dropdown"` og **ingen** `data-action`:
// begge lytterne ville fyrt på samme klikk, og det er fella `klikkSkalKjore()`
// i portal-utils.js finnes for. Bootstrap eier åpningen; vi eier bare hva som
// hentes når den er åpen.
//
// Sparingen fra pulje 1 står: ingen polling av en liste ingen ser på. Den er
// bare snudd — før var lista synlig som standard og kunne slås av, nå er den
// lukket og hentes når den åpnes.
function koSidebarLyttere() {
  const nedtrekk = document.getElementById('ko-sidebar-knapp');
  if (!nedtrekk) return;
  const rot = nedtrekk.closest('.dropdown') || nedtrekk;
  rot.addEventListener('show.bs.dropdown', () => {
    koSidebarSynlig = true;
    koHentTilstede();
  });
  rot.addEventListener('hide.bs.dropdown', () => { koSidebarSynlig = false; });
}

// ── Konsollhøyden ───────────────────────────────────────────────────────────
//
// **Sida skal ikke rulle — kolonnene skal.** Det er forskjellen på en konsoll
// og en nettside: de tre flatene står på samme sted hele vakta, uansett hvor
// mye som er i dem. Rulles sida, flytter skrivefeltet seg idet tavla får en rad
// til, og operatøren treffer feil felt midt i sambandstrafikk.
//
// Høyden **måles**, den regnes ikke ut av en `calc()` med et fast tall: over
// konsollen står portalheaderen, navigasjonen og eventuelle meldinger, og alle
// tre kan brekke til to linjer på en smal skjerm. Et fast tall ville vært
// riktig på én skjerm og galt på alle andre.

// Luft under konsollen, så footeren ikke klistrer seg inntil.
const KO_BUNNMARG = 16;

// **Gulvet er en regel, ikke en forsiktighetsmargin.** Uten det gir et kort
// vindu — eller en header som brakk i tre linjer — en konsoll på nitti piksler,
// og da er alle tre kolonnene ubrukelige samtidig. Da er det bedre at sida
// ruller: det ser rart ut, men alt er lesbart.
const KO_MIN_HOYDE = 360;

function koKonsollhoyde(toppOffset, vindushoyde) {
  return Math.max(vindushoyde - toppOffset - KO_BUNNMARG, KO_MIN_HOYDE);
}

function koSettKonsollhoyde() {
  const konsoll = document.querySelector('.ko-konsoll');
  if (!konsoll) return;
  const topp = konsoll.getBoundingClientRect().top;
  konsoll.style.setProperty(
    '--ko-hoyde', koKonsollhoyde(topp, window.innerHeight) + 'px');
}


// ════════════════════════════════════════════════════════════════════════════
// LOGGEN (pulje 2) — docs/FORSLAG_KO.md §4
//
// Én strøm med alle linjer: menneskeskrevne og de systemhendelsene som løftes
// inn (ko/systemlinjer.py). Den skal være **fullstendig og kjedelig** — den
// eneste fella er å begynne å skjule ting i loggen for å gjøre den ryddig, for
// da er den ikke lenger fasit.
// ════════════════════════════════════════════════════════════════════════════

// 15 sekunder. Loggen er det eneste på sida som endrer seg i sekunder: to
// operatører fører samtidig, og en linje som kommer et halvt minutt for sent
// er en linje man rekker å skrive på nytt. Bremsen er 240/m, altså to
// størrelsesordener over dette.
const KO_LOGG_MS = 15000;

// **`?siden=<id>` og ikke full henting** (§7.1). Arbeidet i KO er påføringer,
// og polling skalerer fint så lenge nesten alt er nye rader. WebSockets er
// bevisst ikke tatt i bruk: et stort infrahopp på Railway med synkron Django,
// uten en gevinst som forsvarer det.
let koSisteId = 0;

// Linjene vi har tegnet, nøklet på `rot` — kjedens første ledd. **Ikke på
// `id`**: en retting er en ny rad med ny id som skal *erstatte* den gamle på
// den gamle plassen, ikke legge seg nederst. Serveren sorterer på det samme.
let koLinjer = new Map();

// **Returnerer en boolsk verdi, ikke det siste leddet i en `||`-kjede.**
// `t.admin` er `undefined` når nøkkelen mangler, og en avgjørelsesfunksjon som
// svarer «undefined» på «har hun lov?» er en funksjon man ikke kan stole på i
// en `=== false` eller i en test. Falsy holdt i praksis; det er ikke det samme
// som å være riktig.
function koKanSkrive() {
  const t = window.MODUL_TILGANG || {};
  return Boolean(t.ko === 'skriv_full' || t.ko === 'skriv_leder' || t.admin);
}

// **Fjerning er `skriv_leder`, og knappen tegnes deretter.** Grensesnittet
// gater på `window.MODUL_TILGANG` og ikke på rollen (CLAUDE.md) — en knapp som
// fører til 403 er verre enn ingen knapp.
function koKanFjerne() {
  const t = window.MODUL_TILGANG || {};
  return Boolean(t.ko === 'skriv_leder' || t.admin);
}

// Regelen, ikke formateringen: hva linja *påstår* om sin egen opprinnelse.
// Egen funksjon fordi den avgjør noe — se `klikkSkalKjore()` i portal-utils.js
// for hvorfor slike regler skilles ut.
function koLinjeMerke(linje) {
  if (linje.fjernet) return 'fjernet';
  if (linje.kilde === 'system') return 'system';
  if (linje.delt_konto) return 'delt';
  return '';
}

function koKlokke(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return String(d.getHours()).padStart(2, '0') + ':'
    + String(d.getMinutes()).padStart(2, '0');
}

// **En fjernet linje viser at den er fjernet, ikke ingenting.** Et hull i
// loggen er verre enn en tømt linje: da vet ingen at det sto noe der (§4.4).
function koLinjeTekst(linje) {
  if (linje.fjernet) {
    const av = linje.fjernet_av ? ' av ' + escapeHtml(linje.fjernet_av) : '';
    return '<em class="text-muted">Innholdet er fjernet' + av
      + ', ' + escapeHtml(koKlokke(linje.fjernet_at)) + '.</em>';
  }
  return escapeHtml(linje.tekst);
}

function koLinjeKnapper(linje) {
  if (linje.kilde === 'system' || linje.fjernet) return '';
  let ut = '';
  if (koKanSkrive()) {
    ut += '<button type="button" class="btn btn-link btn-sm p-0 me-2"'
      + ' data-action="koRett" data-id="' + escapeHtml(linje.id) + '">Rett</button>';
  }
  if (koKanFjerne()) {
    ut += '<button type="button" class="btn btn-link btn-sm p-0 text-danger"'
      + ' data-action="koFjern" data-id="' + escapeHtml(linje.id) + '">Fjern</button>';
  }
  return ut;
}

function koLinjeHtml(linje) {
  const merke = koLinjeMerke(linje);
  const merkeHtml = merke
    ? ' <span class="badge text-bg-secondary">' + escapeHtml(merke) + '</span>'
    : '';
  const rettet = linje.korrigerer
    ? ' <span class="text-muted small">(rettet)</span>'
    : '';
  const omraade = linje.ansvarsomraade
    ? ' <span class="text-muted small">· ' + escapeHtml(linje.ansvarsomraade) + '</span>'
    : '';
  const hvem = linje.kilde === 'system'
    ? '<span class="text-muted">system</span>'
    : escapeHtml(linje.forfatter);
  return '<li class="list-group-item py-2" data-rot="' + escapeHtml(linje.rot) + '">'
    + '<div class="d-flex justify-content-between align-items-start gap-2">'
    + '<div><span class="fw-semibold me-2">' + escapeHtml(koKlokke(linje.tidspunkt))
    + '</span>' + koLinjeTekst(linje) + rettet + '</div>'
    + '<div class="text-nowrap small">' + koLinjeKnapper(linje) + '</div>'
    + '</div>'
    + '<div class="small text-muted">' + hvem + merkeHtml + omraade + '</div>'
    + '</li>';
}

function koTegnLogg() {
  const boks = document.getElementById('ko-logg-liste');
  if (!boks) return;
  const rader = Array.from(koLinjer.values());
  // Samme sortering som serveren: kjedens første ledd, så id. Klienten kan få
  // linjer i to omganger, og rekkefølgen skal ikke avhenge av når de kom.
  rader.sort((a, b) => (a.rot - b.rot) || (a.id - b.id));
  const antall = document.getElementById('ko-logg-antall');
  if (antall) antall.textContent = rader.length + ' linjer';
  if (rader.length === 0) {
    boks.innerHTML = '<p class="text-muted small p-3 mb-0">Ingen linjer ennå.</p>';
    return;
  }
  boks.innerHTML = '<ul class="list-group list-group-flush">'
    + rader.map(koLinjeHtml).join('') + '</ul>';
}

async function koHentLogg() {
  try {
    const res = await apiFetch('/ko/api/logg/?siden=' + koSisteId);
    const data = await res.json();
    (data.data || []).forEach(linje => {
      koLinjer.set(linje.rot, linje);
      if (linje.id > koSisteId) koSisteId = linje.id;
    });
    // **Fjernede linjer kommer aldri gjennom `?siden=`**: sletteinngangen
    // endrer en rad i stedet for å legge til en ny, så den har ingen ny id.
    // Uten denne løkka ville teksten blitt stående på hver annen operatørs
    // skjerm til hun lastet siden på nytt.
    (data.fjernede || []).forEach(id => {
      koLinjer.forEach(linje => {
        if (linje.id === id && !linje.fjernet) {
          linje.fjernet = true;
          linje.tekst = '';
        }
      });
    });
    const vakt = document.getElementById('ko-logg-vakt');
    if (vakt && data.vakt) vakt.textContent = '· ' + data.vakt;
    koTegnLogg();
  } catch (e) {
    // En logg som ikke svarer skal ikke tømme skjermen: linjene som alt står
    // der er fortsatt sanne. Feilen vises bare når det ikke står noe.
    const boks = document.getElementById('ko-logg-liste');
    if (boks && koLinjer.size === 0) {
      boks.innerHTML = '<p class="text-muted small p-3 mb-0">Fikk ikke kontakt.</p>';
    }
  }
}

function koLoggFeil(melding) {
  const boks = document.getElementById('ko-logg-feil');
  if (!boks) return;
  boks.textContent = melding || '';
  boks.classList.toggle('d-none', !melding);
}

// Klokkeslettet fra `<input type="time">` er «21:14» uten dato. Dagens dato
// legges på her. Krysser vakta midnatt, ville «00:05» skrevet klokka 00:10 blitt
// riktig, mens «23:58» skrevet 00:02 havnet et døgn fram — serveren avviser det
// som «fram i tid», og operatøren får en feilmelding i stedet for en linje på
// feil dag. Det er riktig vei å ta feil på.
function koTidspunktISO(verdi) {
  if (!verdi) return null;
  const biter = verdi.split(':');
  if (biter.length < 2) return null;
  const d = new Date();
  d.setHours(Number(biter[0]), Number(biter[1]), 0, 0);
  return d.toISOString();
}

async function koSkriv() {
  const felt = document.getElementById('ko-logg-tekst');
  const tidfelt = document.getElementById('ko-logg-tid');
  if (!felt) return;
  koLoggFeil('');
  const res = await apiFetch('/ko/api/logg/ny/', {
    method: 'POST',
    body: JSON.stringify({
      tekst: felt.value,
      tidspunkt: koTidspunktISO(tidfelt ? tidfelt.value : ''),
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    koLoggFeil(data.message || 'Linja ble ikke lagret.');
    return;
  }
  felt.value = '';
  if (tidfelt) tidfelt.value = '';
  koLinjer.set(data.data.rot, data.data);
  if (data.data.id > koSisteId) koSisteId = data.data.id;
  koTegnLogg();
}

async function koRett(id) {
  const linje = Array.from(koLinjer.values()).find(l => l.id === id);
  if (!linje) return;
  const tekst = window.prompt('Rett linja. Den gamle blir stående som historikk.',
                              linje.tekst);
  if (tekst === null) return;
  const res = await apiFetch('/ko/api/logg/' + id + '/rett/', {
    method: 'POST',
    body: JSON.stringify({ tekst: tekst }),
  });
  const data = await res.json();
  if (!res.ok) {
    koLoggFeil(data.message || 'Rettingen gikk ikke gjennom.');
    // 409 betyr at noen andre rettet den først, og da er det den nye
    // versjonen som gjelder — hent den før operatøren prøver igjen på et
    // grunnlag som ikke finnes lenger.
    if (res.status === 409) koHentLogg();
    return;
  }
  koLinjer.set(data.data.rot, data.data);
  if (data.data.id > koSisteId) koSisteId = data.data.id;
  koTegnLogg();
}

async function koFjern(id) {
  // **`confirm` kreves også server-side.** Dette er den ene handlingen i
  // modulen som ikke lar seg angre: teksten finnes etterpå bare i en backupfil
  // ingen har en knapp til.
  if (!window.confirm(
      'Fjern innholdet i linja?\n\n'
      + 'Rada blir stående med «fjernet av deg», men teksten er borte for '
      + 'godt. Bruk dette når noen har skrevet en personopplysning som ikke '
      + 'skal stå der.')) {
    return;
  }
  const res = await apiFetch('/ko/api/logg/' + id + '/fjern/', {
    method: 'POST',
    body: JSON.stringify({ confirm: true }),
  });
  const data = await res.json();
  if (!res.ok) {
    koLoggFeil(data.message || 'Linja ble ikke fjernet.');
    return;
  }
  koHentLogg();
}


// ════════════════════════════════════════════════════════════════════════════
// Ressursbildet (pulje 3, §3.1) — tavla over hvem som er på vakt og hvor de er.
//
// **KO eier ikke ressursene.** Serveren setter bildet sammen av tre kilder;
// her tegnes det bare. Det ene valget som ligger i klienten er om
// statusknappene skal finnes på en rad, og det er en regel — se
// `koKanStyreRessurs()`.
// ════════════════════════════════════════════════════════════════════════════

// 20 sekunder. Tavla endrer seg oftere enn sidebaren (en status kan skifte
// midt i en samtale) og sjeldnere enn loggen (som skrives mens man ser på).
const KO_RESSURSER_MS = 20000;

// Statusene KO fører. Rekkefølgen er knapperekkefølgen, og den er
// **operatørens** og ikke alfabetisk: «Ledig» først fordi det er den man
// trykker for å melde noen tilbake i tjeneste, og den gjør man oftest.
const KO_STATUSER = [
  { verdi: 'ledig', navn: 'Ledig', klasse: 'success' },
  { verdi: 'opptatt', navn: 'Opptatt', klasse: 'warning' },
  { verdi: 'pause', navn: 'Pause', klasse: 'info' },
  { verdi: 'ute_av_drift', navn: 'Ute av drift', klasse: 'danger' },
];

let koRessursbilde = { vaktliste: null, grupper: [] };

// **Regelen, ikke tegningen.** Knappene skal finnes bare når begge er sanne:
// brukeren kan skrive, *og* det er KO som fører statusen for ressursen. Den
// andre halvdelen er lett å glemme, og da tegner vi knapper på en koblet bil —
// serveren avviser dem, og operatøren står med en knapp som fører til en vegg.
function koKanStyreRessurs(ressurs) {
  return Boolean(koKanSkrive() && ressurs && ressurs.fort_av_ko);
}

// Fargen bærer en påstand om hvem som kan sendes, så den er en regel og ikke
// pynt. Ukjent status gir `secondary` og ikke grønt: en verdi vi ikke kjenner
// skal aldri se ledig ut.
function koStatusklasse(ressurs) {
  if (!ressurs.status) return 'secondary';
  if (ressurs.fort_av_ko) {
    const treff = KO_STATUSER.find((s) => s.verdi === ressurs.status);
    return treff ? treff.klasse : 'secondary';
  }
  return ressurs.status === 'ledig' ? 'success' : 'warning';
}

// «2 av 3 møtt» — og tallet er ikke pynt heller: en ressurs med skift men uten
// noen møtt er nettopp den man tror man har.
function koBemanningstekst(ressurs) {
  if (!ressurs.antall) return 'ingen på skift nå';
  return ressurs.tilstede + ' av ' + ressurs.antall + ' møtt';
}

function koRessursKnapper(ressurs) {
  if (!koKanStyreRessurs(ressurs)) return '';
  let ut = '<div class="btn-group btn-group-sm mt-1" role="group"'
    + ' aria-label="Sett status">';
  for (const s of KO_STATUSER) {
    const aktiv = ressurs.status === s.verdi
      ? 'btn-' + s.klasse
      : 'btn-outline-' + s.klasse;
    ut += '<button type="button" class="btn ' + aktiv + '"'
      + ' data-action="koSettRessursstatus"'
      + ' data-id="' + escapeHtml(ressurs.id) + '"'
      + ' data-felt="status"'
      + ' data-verdi="' + escapeHtml(s.verdi) + '">'
      + escapeHtml(s.navn) + '</button>';
  }
  return ut + '</div>';
}

function koRessursHtml(ressurs) {
  const mannskap = ressurs.mannskap.length
    ? ressurs.mannskap.map((m) => escapeHtml(m.navn)
        + (m.tilstede ? '' : ' <span class="text-muted">(ikke møtt)</span>')).join(', ')
    : '<span class="text-muted">—</span>';
  // **Kilden til statusen står i bildet** (§3.1): «bilen sa det» mot «KO førte
  // det» er hele skillet den tredje kilden finnes for, og det skal ikke måtte
  // utledes av at en rad tilfeldigvis har knapper.
  const kilde = ressurs.fort_av_ko
    ? '<span class="text-muted small">ført av KO'
      + (ressurs.status_satt_av ? ' · ' + escapeHtml(ressurs.status_satt_av) : '')
      + '</span>'
    : '<span class="text-muted small">melder selv</span>';
  const venter = ressurs.antall_ventende
    ? ' <span class="text-muted small">(' + escapeHtml(ressurs.antall_ventende)
      + ' venter)</span>'
    : '';
  return '<li class="list-group-item py-2">'
    + '<div class="d-flex justify-content-between align-items-start gap-2">'
    + '<div><span class="fw-semibold">' + escapeHtml(ressurs.navn) + '</span>'
    + (ressurs.korps ? ' <span class="text-muted small">'
        + escapeHtml(ressurs.korps) + '</span>' : '')
    + '<div class="small">' + mannskap + '</div>'
    + '<div class="small text-muted">' + escapeHtml(koBemanningstekst(ressurs))
    + '</div></div>'
    + '<div class="text-end">'
    + '<span class="badge text-bg-' + koStatusklasse(ressurs) + '">'
    + escapeHtml(ressurs.status_navn || 'ukjent') + '</span>' + venter
    + '<div>' + kilde + '</div>'
    + '</div></div>'
    + koRessursKnapper(ressurs)
    + '</li>';
}

function koTegnRessurser() {
  const boks = document.getElementById('ko-ressurser');
  if (!boks) return;
  const merke = document.getElementById('ko-ressurser-vakt');
  if (merke) {
    merke.textContent = koRessursbilde.vaktliste
      ? koRessursbilde.vaktliste.vakt_navn
        + (koRessursbilde.vaktliste.i_drift ? ' · i drift' : '')
      : '';
  }
  if (!koRessursbilde.vaktliste) {
    // **Ukoblet og tomt skal ikke se likt ut.** Ingen vaktliste er et oppsett
    // som mangler; en tom liste er en vakt uten ressurser. Samme skille
    // `vaktliste.services.besetning()` gjør.
    boks.innerHTML = '<p class="text-muted small p-3 mb-0">Ingen vaktliste i drift'
      + ' og ingen aktiv vakt. Sett en liste i drift i'
      + ' <a href="/vaktliste/">vaktlista</a>.</p>';
    return;
  }
  if (!koRessursbilde.grupper.length) {
    boks.innerHTML = '<p class="text-muted small p-3 mb-0">Ingen ressurser i'
      + ' denne vaktlista.</p>';
    return;
  }
  let ut = '';
  for (const g of koRessursbilde.grupper) {
    ut += '<div class="px-3 pt-2 pb-1 small fw-semibold text-muted">'
      + escapeHtml(g.navn) + '</div>'
      + '<ul class="list-group list-group-flush">'
      + g.ressurser.map(koRessursHtml).join('')
      + '</ul>';
  }
  boks.innerHTML = ut;
}

async function koHentRessurser() {
  try {
    const svar = await apiFetch('/ko/api/ressurser/');
    if (!svar.ok) return;
    const json = await svar.json();
    koRessursbilde = json.data || { vaktliste: null, grupper: [] };
    koTegnRessurser();
  } catch (e) {
    // En tavle som feiler skal ikke ta med seg loggen. Samme valg som
    // sidebaren gjør — det forrige bildet blir stående, og det er riktigere
    // enn et tomt: det sier i det minste hva som var sant sist.
  }
}

async function koSettRessursstatus(id, felt, verdi) {
  const svar = await apiFetch('/ko/api/ressurser/' + encodeURIComponent(id)
    + '/status/', {
    method: 'POST',
    body: JSON.stringify({ status: verdi }),
  });
  if (!svar.ok) return;
  const json = await svar.json();
  koRessursbilde = json.data || koRessursbilde;
  koTegnRessurser();
}


// ════════════════════════════════════════════════════════════════════════════
// OPPSTART
//
// **Alt som kjører på toppnivå står her, nederst.** Regelen er skrevet for de
// delte modulene (CLAUDE.md), men den gjelder like fullt i én fil: kjører en
// tidlig linje noe, kan den lese en binding som ikke er nådd, og siden dør på
// en ReferenceError før noe er tegnet.
// ════════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  koSettKonsollhoyde();
  // Ny måling ved endret vindusstørrelse. `resize` dekker også at headeren
  // brekker til to linjer, som er den ekte grunnen målingen finnes.
  window.addEventListener('resize', koSettKonsollhoyde);
  koSidebarLyttere();
  koHentRessurser();
  // Tavla polles alltid — den står i venstre kolonne og er aldri skjult. Det
  // er forskjellen fra sidebaren, som kan slås av og da ikke skal pollen.
  setInterval(koHentRessurser, KO_RESSURSER_MS);
  setInterval(() => {
    // Ikke poll en liste ingen ser på. Det er den ene sparingen som betyr noe
    // her: flere operatører sitter på samme side hele vakta. Nedtrekket er
    // lukket som standard, så dette er nå det normale tilfellet.
    if (koSidebarSynlig) koHentTilstede();
  }, KO_TILSTEDE_MS);

  const skjema = document.getElementById('ko-logg-form');
  if (skjema) {
    skjema.addEventListener('submit', (e) => {
      e.preventDefault();
      // `withSubmitGuard` og ikke en egen flagg-variabel: dobbelttrykk under
      // en hendelse er regelen og ikke unntaket, og to like linjer i loggen er
      // en feil man ikke oppdager før man leser den i etterkant.
      withSubmitGuard('ko-logg-send', koSkriv);
    });
  }

  // Skjemaet skjules for den som bare har `les`. Serveren svarer 403 uansett,
  // men et skrivefelt som ikke kan sende er en vegg man går inn i.
  const boks = document.getElementById('ko-logg-skjema');
  if (boks && !koKanSkrive()) boks.classList.add('d-none');

  koHentLogg();
  setInterval(koHentLogg, KO_LOGG_MS);
});
