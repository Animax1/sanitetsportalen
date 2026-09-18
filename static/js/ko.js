// ════════════════════════════════════════════════════════════════════════════
// KO — situasjonsbildet. Denne fila eier **loggen**, **hendelsene** (pulje
// 5), sidebaren og konsollhøyden. Listene eies av oppdrag-sentral-*.js
// (pulje 4); grupperingen av oppdragslista på hendelse eies her, og
// `renderOppdrag()` spør etter den gjennom `koGrupperOppdrag()`.
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
  // Ansvarsmerket (§5.1): «Kari · samband». Vises, styrer ingenting.
  const ansvarHtml = rad.ansvar
    ? ' <span class="text-muted">· ' + escapeHtml(rad.ansvar) + '</span>'
    : '';
  return '<li class="d-flex justify-content-between align-items-center gap-2 py-1">'
    + '<span>' + escapeHtml(rad.brukernavn) + merkeHtml + ansvarHtml + '</span>'
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
  // Hendelseslinjene skal vises **tydelig som hendelse** (André, 18. sep.
  // 2026) — de er operatørens handlinger, ikke en projeksjon av et stempel.
  if (linje.kilde === 'system' && String(linje.systemkode || '').startsWith('hendelse_')) return 'hendelse';
  if (linje.kilde === 'system') return 'system';
  if (linje.uformell) return 'chat';
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
    // «Hendelse» lager en hendelse *av* linja (§4.5): linja blir stående, og
    // hendelsen peker tilbake. Vises ikke når linja alt hører til en.
    if (!linje.hendelse_id) {
      ut += '<button type="button" class="btn btn-link btn-sm p-0 me-2"'
        + ' data-action="koHendelseFraLinje" data-id="' + escapeHtml(linje.id) + '">Hendelse</button>';
    }
    ut += '<button type="button" class="btn btn-link btn-sm p-0 me-2"'
      + ' data-action="koRett" data-id="' + escapeHtml(linje.id) + '">Rediger</button>';
  }
  if (koKanFjerne()) {
    ut += '<button type="button" class="btn btn-link btn-sm p-0 text-danger"'
      + ' data-action="koFjern" data-id="' + escapeHtml(linje.id) + '">Fjern</button>';
  }
  return ut;
}

function koLinjeHtml(linje) {
  const merke = koLinjeMerke(linje);
  // Hendelsesmerket er blått og linja uthevet; chat er dempet. Resten grått.
  const merkeKlasse = merke === 'hendelse' ? 'text-bg-primary' : 'text-bg-secondary';
  const merkeHtml = merke
    ? ' <span class="badge ' + merkeKlasse + '">' + escapeHtml(merke) + '</span>'
    : '';
  const linjeKlasse = merke === 'hendelse' ? ' ko-linje-hendelse'
    : (merke === 'chat' ? ' ko-linje-chat' : '');
  // «H12» på linja (§4.1): hendelsen som filter, uten å skjule noe.
  const hendelseHtml = linje.hendelse_nummer
    ? ' <span class="hendelse-merke">' + escapeHtml(hendelsesnr(linje.hendelse_nummer)) + '</span>'
    : '';
  const rettet = linje.korrigerer
    ? ' <span class="text-muted small">(rettet)</span>'
    : '';
  const omraade = linje.ansvarsomraade
    ? ' <span class="text-muted small">· ' + escapeHtml(linje.ansvarsomraade) + '</span>'
    : '';
  // Systemlinjer har ingen forfatter — de skjedde. **Hendelseslinjene har**:
  // «H12 lukket» er en handling, og operatøren står frosset på linja.
  const hvem = linje.forfatter
    ? escapeHtml(linje.forfatter)
    : '<span class="text-muted">system</span>';
  return '<li class="list-group-item py-2' + linjeKlasse + '" data-rot="' + escapeHtml(linje.rot) + '">'
    + '<div class="d-flex justify-content-between align-items-start gap-2">'
    + '<div><span class="fw-semibold me-2">' + escapeHtml(koKlokke(linje.tidspunkt))
    + '</span>' + hendelseHtml + koLinjeTekst(linje) + rettet + '</div>'
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
    // Hendelsene følger med hver poll — hele lista, som `fjernede`: en
    // hendelse som lukkes eller omdøpes har ingen ny id.
    if (data.hendelser) koTaImotHendelser(data.hendelser);
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
  const uformell = document.getElementById('ko-logg-uformell');
  const res = await apiFetch('/ko/api/logg/ny/', {
    method: 'POST',
    body: JSON.stringify({
      tekst: felt.value,
      tidspunkt: koTidspunktISO(tidfelt ? tidfelt.value : ''),
      // Chat (§4.5): samme logg, et merke. Avkryssingen finnes bare når
      // admin har slått chatten på; serveren avviser flagget ellers.
      uformell: Boolean(uformell && uformell.checked),
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
  const tekst = window.prompt('Rediger linja. Den gamle blir stående som historikk.',
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
// Ressurslista og oppdragslista hentes **ikke herfra** (pulje 4).
//
// `/ko/` laster `oppdrag-sentral-*.js`, og de eier begge listene: henting med
// ETag, tegning, polling og alle handlingene. En egen henter her ville vært en
// andre poller mot de samme endepunktene, og to pollere som skriver til samme
// `#enhetsliste` blir uenige før eller siden.
//
// Pulje 3 hadde en kort stund `/ko/api/ressurser/` med `ko:les` som gate. Den
// er borte: oppdragsdata gates av **oppdragsmodulen**, også når sida er KO
// (André, 18. sep. 2026). Se ko/CLAUDE.md.
// ════════════════════════════════════════════════════════════════════════════


// ════════════════════════════════════════════════════════════════════════════
// HENDELSENE (pulje 5) — docs/FORSLAG_KO.md §3.3, §4.6, §6, §7
//
// En hendelse er **en gruppering av oppdragslista og et filter i loggen**,
// ikke en egen flate. Lista her kommer med logg-pollen; tavla spør etter
// grupperingen gjennom `koGrupperOppdrag()`, og detaljmodalen etter
// knytt/løsne gjennom `koHendelseValg()`. Begge kalles fra
// `oppdrag-sentral-oppdrag.js` gjennom en vakt — den fila kjører også på
// `/oppdrag/`, der denne ikke finnes.
// ════════════════════════════════════════════════════════════════════════════

//: Hendelsene i vakta, nøklet på id. Hele lista byttes ut ved hver poll.
let koHendelser = new Map();

//: Om oppdragslista grupperes på hendelse. Husket per nettleser: det er et
//: visningsvalg, ikke data — og **det skjuler ingenting** (§7.2): av og på
//: viser de samme radene, bare med eller uten overskrifter.
let koGruppert = true;
const KO_GRUPPERT_NOKKEL = 'ko.gruppert';

function koLesGruppering() {
  try {
    const lagret = window.localStorage.getItem(KO_GRUPPERT_NOKKEL);
    if (lagret !== null) koGruppert = lagret === '1';
  } catch (e) { /* privat modus e.l. — standardverdien gjelder */ }
  const bryter = document.getElementById('ko-gruppert');
  if (bryter) bryter.checked = koGruppert;
}

function koToggleGruppering() {
  const bryter = document.getElementById('ko-gruppert');
  koGruppert = bryter ? bryter.checked : !koGruppert;
  try { window.localStorage.setItem(KO_GRUPPERT_NOKKEL, koGruppert ? '1' : '0'); } catch (e) { /* som over */ }
  koTegnOppdragslistaPaaNytt();
}

function koTegnOppdragslistaPaaNytt() {
  // Sentralbordet eier lista og tegner den; vi ber om en ny tegning. Vakt
  // fordi oppdragsflata ikke finnes uten oppdragstilgang (`kan_se_oppdrag`).
  if (typeof renderOppdrag === 'function') renderOppdrag();
}

function koTaImotHendelser(liste) {
  koHendelser = new Map((liste || []).map((h) => [h.id, h]));
  koTegnOppdragslistaPaaNytt();
  koFyllHendelsevalg();
}

function koApneHendelser() {
  return Array.from(koHendelser.values()).filter((h) => h.status === 'apen');
}

// **Regelen for grupperingen**, som en ren funksjon over `sortert` — den
// avgjør hva tavla viser, og prøves i node. `null` når bryteren er av
// (tavla tegner flatt). Ellers: hver **åpen** hendelse, nyeste først, også
// den som ennå ikke har et oppdrag — det er nettopp hendelsen som «lever i
// tjue minutter før en ressurs sendes»; så lukkede hendelser som fortsatt
// har rader på tavla (ellers ville radene forsvunnet); så «Uten hendelse»,
// som er de fleste (§7) og derfor står sist og ikke som en bøtte på toppen.
function koGrupperOppdrag(sortert) {
  if (!koGruppert) return null;
  const rader = sortert || [];
  const perHendelse = new Map();
  rader.forEach((o) => {
    const id = o.hendelse_id || null;
    if (!perHendelse.has(id)) perHendelse.set(id, []);
    perHendelse.get(id).push(o);
  });
  const alle = Array.from(koHendelser.values()).sort((a, b) => b.nummer - a.nummer);
  const grupper = [];
  alle.filter((h) => h.status === 'apen').forEach((h) => {
    grupper.push({ hendelse: h, hode: koHendelseHode(h, perHendelse.get(h.id) || []),
                   rader: perHendelse.get(h.id) || [] });
  });
  alle.filter((h) => h.status !== 'apen' && perHendelse.has(h.id)).forEach((h) => {
    grupper.push({ hendelse: h, hode: koHendelseHode(h, perHendelse.get(h.id)),
                   rader: perHendelse.get(h.id) });
  });
  // Oppdrag som peker på en hendelse vi ikke har fått ennå (to pollere,
  // to klokker) skal ikke forsvinne: de går i «Uten hendelse» til neste poll.
  const kjente = new Set(alle.map((h) => h.id));
  const uten = rader.filter((o) => !o.hendelse_id || !kjente.has(o.hendelse_id));
  // En tom «Uten hendelse» skjuler ingenting, og en overskrift over ingenting
  // er støy — men står den alene, er den lista, og da skal den stå.
  if (uten.length || !grupper.length) {
    grupper.push({ hendelse: null, hode: koHendelseHode(null, uten), rader: uten });
  }
  return grupper;
}

function koHendelseHode(h, rader) {
  const antall = (rader || []).length;
  const antallTekst = antall === 1 ? '1 oppdrag' : antall + ' oppdrag';
  if (!h) {
    return '<div class="hendelse-hode hendelse-hode-uten">'
      + '<span class="hendelse-tittel">Uten hendelse</span>'
      + '<span class="oppdrag-meta ms-2">' + escapeHtml(antallTekst) + '</span>'
      + '</div>';
  }
  const lukket = h.status !== 'apen';
  const sted = h.lokasjon_navn
    ? '<span class="oppdrag-meta ms-2">· ' + escapeHtml(h.lokasjon_navn) + '</span>' : '';
  const apne = h.apne_oppdrag
    ? '<span class="oppdrag-meta ms-2">· ' + escapeHtml(h.apne_oppdrag) + ' åpne</span>' : '';
  const knapper = koKanSkrive() ? koHendelseKnapper(h) : '';
  return '<div class="hendelse-hode' + (lukket ? ' hendelse-hode-lukket' : '') + '" data-hendelse-id="' + escapeHtml(h.id) + '">'
    + '<span class="hendelse-merke">' + escapeHtml(h.kode) + '</span>'
    + '<span class="hendelse-tittel ms-2">' + escapeHtml(h.tittel) + '</span>'
    + sted
    + '<span class="oppdrag-meta ms-2">· ' + escapeHtml(antallTekst) + '</span>'
    + apne
    + (lukket ? '<span class="badge text-bg-secondary ms-2">lukket</span>' : '')
    + '<span class="ms-auto d-flex gap-2">' + knapper + '</span>'
    + '</div>';
}

function koHendelseKnapper(h) {
  const id = escapeHtml(h.id);
  if (h.status !== 'apen') {
    return '<button type="button" class="btn btn-link btn-sm p-0"'
      + ' data-action="koGjenapneHendelse" data-id="' + id + '">Åpne igjen</button>';
  }
  return '<button type="button" class="btn btn-link btn-sm p-0"'
    + ' data-action="koRedigerHendelse" data-id="' + id + '">Rediger</button>'
    + '<button type="button" class="btn btn-link btn-sm p-0"'
    + ' data-action="koLukkHendelse" data-id="' + id + '">Lukk</button>';
}

// ── Detaljmodalen: hvilken hendelse oppdraget hører til ──────────────────

function koHendelseValg(o) {
  // Bare for den som kan skrive i **begge** modulene — serveren krever det.
  const kanKnytte = koKanSkrive() && (window.OPPDRAG_TILGANG || {}).kanSkrive;
  const naa = o.hendelse_nummer
    ? '<span class="hendelse-merke">' + escapeHtml(hendelsesnr(o.hendelse_nummer)) + '</span>'
      + ' <span>' + escapeHtml(o.hendelse_tittel || '') + '</span>'
    : '<span class="text-muted">Uten hendelse</span>';
  if (!kanKnytte) return '<div class="mb-2 small">Hendelse: ' + naa + '</div>';
  const valg = koApneHendelser()
    .filter((h) => h.id !== o.hendelse_id)
    .map((h) => '<option value="' + escapeHtml(h.id) + '">' + escapeHtml(h.kode) + ' ' + escapeHtml(h.tittel) + '</option>')
    .join('');
  const losne = o.hendelse_id
    ? '<button class="btn btn-outline-secondary" type="button"'
      + ' data-action="koLosneOppdrag" data-id="' + escapeHtml(o.id) + '">Løsne</button>'
    : '';
  return '<div class="mb-2 small d-flex align-items-center gap-2 flex-wrap">'
    + '<span>Hendelse: ' + naa + '</span>'
    + '<span class="input-group input-group-sm w-auto">'
    + '<select id="knytt-hendelse" class="form-select" aria-label="Hendelse">'
    + '<option value="">Velg hendelse</option>' + valg + '</select>'
    + '<button class="btn btn-outline-primary" type="button"'
    + ' data-action="koKnyttOppdrag" data-id="' + escapeHtml(o.id) + '">Knytt</button>'
    + losne
    + '</span></div>';
}

async function _koSettHendelsePaaOppdrag(oppdragId, hendelseId) {
  const res = await apiFetch('/ko/api/oppdrag/' + oppdragId + '/hendelse/', {
    method: 'POST',
    body: JSON.stringify({ hendelse_id: hendelseId }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    window.alert(data.message || 'Kunne ikke knytte oppdraget.');
    return false;
  }
  // Tavla har sin egen ETag; tving ny henting så grupperingen følger med.
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  if (typeof visOppdrag === 'function') await visOppdrag(oppdragId);
  if (typeof lastAlt === 'function') await lastAlt();
  koHentLogg();
  return true;
}

async function koKnyttOppdrag(oppdragId) {
  const valg = document.getElementById('knytt-hendelse');
  if (!valg || !valg.value) return;
  await _koSettHendelsePaaOppdrag(oppdragId, Number(valg.value));
}

async function koLosneOppdrag(oppdragId) {
  await _koSettHendelsePaaOppdrag(oppdragId, null);
}

// ── «Nytt oppdrag»: velg hendelse i samme skjema ─────────────────────────

function koLeggHendelsevalgINyttOppdrag() {
  // Nedtrekket legges inn i sentralbordets modal herfra, ikke i malbiten:
  // `_sentralbord_modaler.html` er delt med `/oppdrag/`, der hendelser ikke
  // finnes. Ett felt, og `koEtterOpprettet()` leser det.
  const fritekst = document.getElementById('nytt-fritekst');
  if (!fritekst || document.getElementById('nytt-hendelse')) return;
  const boks = fritekst.closest('.mb-3');
  if (!boks) return;
  const felt = document.createElement('div');
  felt.className = 'mb-3';
  felt.innerHTML = '<label class="form-label" for="nytt-hendelse">Hendelse</label>'
    + '<select id="nytt-hendelse" class="form-select"><option value="">Uten hendelse</option></select>'
    + '<div class="form-text">Oppdraget knyttes til hendelsen når det er opprettet.</div>';
  boks.parentNode.insertBefore(felt, boks);
  koFyllHendelsevalg();
}

function koFyllHendelsevalg() {
  const sel = document.getElementById('nytt-hendelse');
  if (!sel) return;
  const valgt = sel.value;
  sel.innerHTML = '<option value="">Uten hendelse</option>'
    + koApneHendelser().map((h) =>
      '<option value="' + escapeHtml(h.id) + '">' + escapeHtml(h.kode) + ' ' + escapeHtml(h.tittel) + '</option>').join('');
  if (valgt && koHendelser.has(Number(valgt))) sel.value = valgt;
}

async function koEtterOpprettet(oppdragId) {
  const sel = document.getElementById('nytt-hendelse');
  if (!sel || !sel.value) return;
  const hendelseId = Number(sel.value);
  sel.value = '';
  const res = await apiFetch('/ko/api/oppdrag/' + oppdragId + '/hendelse/', {
    method: 'POST',
    body: JSON.stringify({ hendelse_id: hendelseId }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    window.alert(data.message || 'Oppdraget ble opprettet, men ikke knyttet til hendelsen.');
  }
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  koHentLogg();
}

// ── Handlingene på en hendelse ───────────────────────────────────────────

async function _koHendelsehandling(sti, kropp) {
  const res = await apiFetch(sti, { method: 'POST', body: JSON.stringify(kropp || {}) });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

async function koNyHendelse(forslag, fraLinjeId) {
  const tittel = window.prompt('Hva kaller dere hendelsen på samband?', forslag || '');
  if (tittel === null) return;
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/ny/', {
    tittel: tittel, fra_linje: fraLinjeId || null,
  });
  if (!res.ok) { koLoggFeil(data.message || 'Hendelsen ble ikke opprettet.'); return; }
  koHentLogg();
}

function koHendelseFraLinje(linjeId) {
  const linje = Array.from(koLinjer.values()).find((l) => l.id === linjeId);
  koNyHendelse(linje ? linje.tekst.slice(0, 60) : '', linjeId);
}

async function koLukkHendelse(id) {
  const h = koHendelser.get(id);
  if (!h) return;
  let { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/lukk/');
  if (res.status === 409) {
    // §4.6: en dør hun må åpne bevisst, ikke en vegg. Antallet står i svaret.
    const antall = data.apne_oppdrag || 0;
    if (!window.confirm(
        (data.message || 'Hendelsen har åpne oppdrag.')
        + '\n\nLukke likevel? Oppdragene blir stående på tavla, og at du lukket med '
        + antall + ' åpne står i loggen.')) {
      return;
    }
    ({ res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/lukk/', { confirm: true }));
  }
  if (!res.ok) { window.alert(data.message || 'Hendelsen ble ikke lukket.'); return; }
  koHentLogg();
}

async function koGjenapneHendelse(id) {
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/gjenapne/');
  if (!res.ok) { window.alert(data.message || 'Hendelsen ble ikke åpnet igjen.'); return; }
  koHentLogg();
}

async function koRedigerHendelse(id) {
  const h = koHendelser.get(id);
  if (!h) return;
  const tittel = window.prompt('Ny tittel på ' + h.kode + ':', h.tittel);
  if (tittel === null || tittel === h.tittel) return;
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/rediger/', {
    tittel: tittel, versjon: h.versjon,
  });
  if (res.status === 409) {
    // §7.1: noen andre endret hodet først. Hent det nye før hun prøver igjen.
    window.alert(data.message || 'Hendelsen er endret av noen andre.');
    koHentLogg();
    return;
  }
  if (!res.ok) { window.alert(data.message || 'Hendelsen ble ikke endret.'); return; }
  koHentLogg();
}


// ════════════════════════════════════════════════════════════════════════════
// ANSVARSMERKET (pulje 6) — docs/FORSLAG_KO.md §5.1
//
// Vises, styrer ingenting. Nedtrekket i toppen setter operatørens eget merke;
// serveren stempler det på linjene hun skriver, og sidebaren viser det ved
// navnet.
// ════════════════════════════════════════════════════════════════════════════

async function koSettAnsvar() {
  const sel = document.getElementById('ko-ansvar');
  if (!sel) return;
  const res = await apiFetch('/ko/api/ansvar/', {
    method: 'POST', body: JSON.stringify({ omraade: sel.value }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    window.alert(data.message || 'Kunne ikke sette ansvarsområde.');
  }
}


// ════════════════════════════════════════════════════════════════════════════
// VAKTLISTAS RESSURSER UTEN OPPDRAGSENHET (pulje 6) — §3.1, §7.2
//
// Lag, samleplass, KO: det som bemannes i vaktlista, men aldri stempler i
// /oppdrag/. Tegnes under enhetslista, gruppert på ressursgruppe, med samme
// minimering som enhetstypene. **Ingen status** — hva en KO-ført status skal
// hete er ubesvart (TODO.md), og kortet sier bare det vaktlista vet.
//
// Egen beholder (`#vaktliste-ressurser`), ikke `#enhetsliste`: sentralbordet
// tegner den andre om igjen ved hver poll, og to skrivere til samme element
// blir uenige.
// ════════════════════════════════════════════════════════════════════════════

const KO_RESSURSER_MS = 30000;
let koRessurser = [];

function koRessursMannskap(r) {
  // Navnene hoistes ut før konkateneringen, som resten av byggerne: skanneren
  // i ko/tests_js.py ser et datafelt limt inn, ikke at `map` escaper inni.
  const navn = (r.mannskap || []).map((m) => escapeHtml(m.navn)
    + (m.tilstede ? '' : ' <span class="text-muted">(ikke møtt)</span>')).join(', ');
  if (navn) return navn;
  const nesteNavn = (r.neste || []).map((m) => escapeHtml(m.navn)).join(', ');
  if (nesteNavn) {
    return '<span class="text-muted">Ingen nå · ' + escapeHtml(koKlokke(r.neste_fra)) + ': '
      + nesteNavn + '</span>';
  }
  return '<span class="text-muted">Ingen på vakt</span>';
}

function koRessurskort(r) {
  const tall = r.antall
    ? escapeHtml(String(r.tilstede)) + ' av ' + escapeHtml(String(r.antall)) + ' møtt'
    : 'ubemannet';
  return '<div class="enhet-kort ko-ressurskort">'
    + '<i class="bi bi-' + escapeHtml(r.gruppe_ikon || 'box') + ' ko-ressursikon"></i>'
    + '<div class="flex-grow-1">'
    + '<div class="enhet-navn">' + escapeHtml(r.navn) + '</div>'
    + '<div class="enhet-meta">' + tall + '</div>'
    + '<div class="enhet-meta">' + koRessursMannskap(r) + '</div>'
    + '</div></div>';
}

function koGrupperRessurser(liste) {
  const grupper = new Map();
  (liste || []).forEach((r) => {
    if (!grupper.has(r.gruppe_id)) grupper.set(r.gruppe_id, { id: r.gruppe_id, navn: r.gruppe_navn, ressurser: [] });
    grupper.get(r.gruppe_id).ressurser.push(r);
  });
  return Array.from(grupper.values());
}

function koTegnRessurser() {
  const el = document.getElementById('vaktliste-ressurser');
  if (!el) return;
  if (!koRessurser.length) { el.innerHTML = ''; return; }
  el.innerHTML = koGrupperRessurser(koRessurser).map((g) => {
    const nokkel = 'gruppe:' + escapeHtml(String(g.id));
    const bemannet = g.ressurser.filter((r) => r.antall).length;
    const hode = gruppehode(nokkel, g.navn, g.ressurser.length,
                            bemannet ? String(bemannet) + ' bemannet' : '');
    if (gruppeErLukket(nokkel)) return hode;
    const kort = g.ressurser.map(koRessurskort).join('');
    return hode + kort;
  }).join('');
}

function koTegnRessurserPaaNytt() {
  koTegnRessurser();
}

async function koHentRessurser() {
  try {
    const res = await apiFetch('/vaktliste/api/ressurser/uten-enhet/');
    if (!res.ok) return;
    koRessurser = (await res.json()).data || [];
    koTegnRessurser();
  } catch (e) {
    // Lista som alt står er fortsatt sann; feilen viser seg ved neste poll.
  }
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
  const nyKnapp = document.getElementById('ko-ny-hendelse');
  if (nyKnapp && !koKanSkrive()) nyKnapp.classList.add('d-none');

  koLesGruppering();
  koLeggHendelsevalgINyttOppdrag();

  koHentLogg();
  setInterval(koHentLogg, KO_LOGG_MS);

  // Vaktlistas ressurser uten oppdragsenhet (pulje 6). Bare når flata finnes
  // — den tegnes ikke uten vaktlistetilgang.
  if (document.getElementById('vaktliste-ressurser')) {
    koHentRessurser();
    setInterval(koHentRessurser, KO_RESSURSER_MS);
  }
});
