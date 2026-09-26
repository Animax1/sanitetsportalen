// ════════════════════════════════════════════════════════════════════════════
// ko.js — loggstrømmen, sidebaren, ansvarsmerket, vaktlistas ressurser, og
// **den ene `DOMContentLoaded`-kroken**. Siste av KOs fem filer (`KO_JS` i
// patients/js_test_utils.py): rutenettet bor i ko-layout.js, hendelsene i
// ko-hendelser.js, og alt som *kjører* på toppnivå står nederst her
// (CLAUDE.md). Listene eies av oppdrag-sentral-*.js (pulje 4).
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

// Nedtrekket er lukket når sida lastes.
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
// hentes når den er åpen. Ingen polling av en liste ingen ser på.
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


// ════════════════════════════════════════════════════════════════════════════
// LOGGSTRØMMEN (pulje 2, form fra 18. sep. 2026) — docs/FORSLAG_KO.md §4
//
// Én tabell med alle linjer; **strømmen viser dem som ikke hører til en
// hendelse**, pluss systemlinjene om hendelsene selv (opprettet, prioritet,
// lukket) med H-merket. Kommentarene *inne* i en hendelse står i hendelsen —
// ellers ble strømmen dobbelt så lang under en stor hendelse. Utskriften skal
// ha alt, kronologisk (TODO.md). Festede linjer står øverst i egen boks.
// ════════════════════════════════════════════════════════════════════════════

// **Sikkerhetsnettet**, 30 sekunder. Loggen endrer seg i sekunder — to
// operatører fører samtidig, og en linje som kommer et halvt minutt for sent
// er en linje man rekker å skrive på nytt — så hentingen styres av
// endringsnummeret (`folgEndringer('logg', …)`, 2,5 s). Nettet tar et tall
// som ikke kom fram. Var 15 sekunder til 24. sep. 2026, da det var den eneste.
const KO_LOGG_MS = 30000;

// **`?siden=<id>` og ikke full henting** (§7.1). Arbeidet i KO er påføringer,
// og polling skalerer fint så lenge nesten alt er nye rader. WebSockets er
// bevisst ikke tatt i bruk.
let koSisteId = 0;

// Linjene vi har tegnet, nøklet på `rot` — kjedens første ledd. **Ikke på
// `id`**: en retting er en ny rad med ny id som skal *erstatte* den gamle på
// den gamle plassen, ikke legge seg nederst. Serveren sorterer på det samme.
let koLinjer = new Map();


// **Returnerer en boolsk verdi, ikke det siste leddet i en `||`-kjede.**
// `t.admin` er `undefined` når nøkkelen mangler, og en avgjørelsesfunksjon som
// svarer «undefined» på «har hun lov?» er en funksjon man ikke kan stole på.
function koKanSkrive() {
  const t = window.MODUL_TILGANG || {};
  return Boolean(t.ko === 'skriv_full' || t.ko === 'skriv_leder' || t.admin);
}

// **Fjerning er `skriv_leder`, og knappen tegnes deretter.** Grensesnittet
// gater på `window.MODUL_TILGANG` og ikke på rollen (CLAUDE.md).
function koKanFjerne() {
  const t = window.MODUL_TILGANG || {};
  return Boolean(t.ko === 'skriv_leder' || t.admin);
}

// Regelen, ikke formateringen: hva linja *påstår* om sin egen opprinnelse.
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

// **Hører linja hjemme i strømmen?** Regelen for hva vinduet viser, skilt ut
// fordi den avgjør noe: kommentarer i en hendelse står i hendelsen, mens
// systemlinjene om hendelsen (opprettet, lukket, prioritet, lag, knyttet)
// står i strømmen med H-merket — de er situasjonen, og skal sees uten å
// åpne noe. **Oppdragenes stempler står ikke i strømmen** (André, 19. sep.
// 2026: «statuser fra oppdrag fjernes fra loggstrøm og med det system
// knappen») — de står på tavla og i oppdraget, og i loggen for utskriften.
// Bryteren «System» gikk ut med dem.
function koIStrommen(linje) {
  if (linje.kilde === 'system') {
    return koLinjeMerke(linje) === 'hendelse' || linje.systemkode === 'oppdrag_knyttet';
  }
  return !linje.hendelse_id;
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
  const id = escapeHtml(linje.id);
  if (koKanSkrive()) {
    // Festing (18. sep. 2026): én knapp, som bytter mellom fest og løsne.
    ut += linje.festet_at
      ? '<button type="button" class="btn btn-link btn-sm p-0" title="Løsne"'
        + ' data-action="koLosne" data-id="' + id + '"><i class="bi bi-pin-angle-fill"></i></button>'
      : '<button type="button" class="btn btn-link btn-sm p-0" title="Fest øverst"'
        + ' data-action="koFest" data-id="' + id + '"><i class="bi bi-pin-angle"></i></button>';
    // «Hendelse» lager en hendelse *av* linja (§4.5): linja blir stående, og
    // hendelsen peker tilbake. Vises ikke når linja alt hører til en.
    if (!linje.hendelse_id) {
      ut += '<button type="button" class="btn btn-link btn-sm p-0" title="Lag hendelse av linja"'
        + ' data-action="koHendelseFraLinje" data-id="' + id + '"><i class="bi bi-flag"></i></button>';
    }
    ut += '<button type="button" class="btn btn-link btn-sm p-0" title="Rediger"'
      + ' data-action="koRett" data-id="' + id + '"><i class="bi bi-pencil"></i></button>';
  }
  if (koKanFjerne()) {
    ut += '<button type="button" class="btn btn-link btn-sm p-0 text-danger" title="Fjern innholdet"'
      + ' data-action="koFjern" data-id="' + id + '"><i class="bi bi-trash"></i></button>';
  }
  return ut;
}

function koLinjeHtml(linje) {
  const merke = koLinjeMerke(linje);
  const system = linje.kilde === 'system';
  const klasse = 'ls-linje' + (system ? ' ls-system' : '')
    + (merke === 'hendelse' ? ' ls-hendelse' : '') + (merke === 'chat' ? ' ls-chat' : '');
  // «H12» på linja (§4.1): hendelsen som adresse, uten å skjule noe. Klikk
  // åpner hendelsen.
  const hendelseHtml = linje.hendelse_nummer
    ? '<span class="hendelse-merke me-1" role="button" data-action="koApneHendelse"'
      + ' data-id="' + escapeHtml(linje.hendelse_id) + '">' + escapeHtml(hendelsesnr(linje.hendelse_nummer)) + '</span>'
    : '';
  const rettet = linje.korrigerer ? ' <span class="text-muted small">(rettet)</span>' : '';
  const merkeHtml = (merke === 'chat' || merke === 'delt')
    ? ' <span class="badge text-bg-secondary">' + escapeHtml(merke) + '</span>' : '';
  // Systemlinjer har ingen forfatter — de skjedde. **Hendelseslinjene har**:
  // «H12 lukket» er en handling, og operatøren står frosset på linja.
  const hvem = linje.forfatter
    ? escapeHtml(linje.forfatter) + (linje.ansvarsomraade ? ' · ' + escapeHtml(linje.ansvarsomraade) : '')
    : 'system';
  return '<div class="' + klasse + '" data-rot="' + escapeHtml(linje.rot) + '">'
    + '<span class="tid">' + escapeHtml(koKlokke(linje.tidspunkt)) + '</span>'
    + '<span class="tekst">' + hendelseHtml + koLinjeTekst(linje) + rettet + merkeHtml + '</span>'
    + '<span class="verktoy"><span class="hvem">' + hvem + '</span> ' + koLinjeKnapper(linje) + '</span>'
    + '</div>';
}

// En festet linje i boksen øverst: teksten, hvem som skrev den, og løsne.
function koFestetHtml(linje) {
  const losne = koKanSkrive()
    ? '<button type="button" class="btn btn-link btn-sm p-0 ms-auto text-muted" title="Løsne"'
      + ' data-action="koLosne" data-id="' + escapeHtml(linje.id) + '"><i class="bi bi-x-lg"></i></button>'
    : '';
  return '<div class="ls-festet"><i class="bi bi-pin-angle-fill"></i>'
    + '<div>' + koLinjeTekst(linje) + ' <span class="hvem text-muted small">— '
    + escapeHtml(linje.forfatter || '') + ' ' + escapeHtml(koKlokke(linje.tidspunkt)) + '</span></div>'
    + losne + '</div>';
}

// ── Filteret i loggstrømmen (André, 21. sep. 2026) ─────────────────────────
//
// «Loggstrømmen må filtreres mellom system meldinger og bruker sendte
// meldinger.» Tre valg, huskes per nettleser som Alle | Biler | Lag i
// ressursoversikten. **Regelen er en egen funksjon** fordi den avgjør hva
// som vises; en `if` inne i `koTegnLogg()` lar seg ikke kjøre for seg.
const KO_LOGGFILTER_NOKKEL = 'ko.loggfilter';
const KO_LOGGFILTRE = ['alle', 'meldinger', 'system'];

let koLoggfilter = 'alle';

function koLoggfilterTreffer(linje, valg) {
  if (valg === 'system') return linje.kilde === 'system';
  if (valg === 'meldinger') return linje.kilde !== 'system';
  return true;
}

function koLesLoggfilter() {
  try {
    const lagret = globalThis.window?.localStorage?.getItem(KO_LOGGFILTER_NOKKEL);
    return KO_LOGGFILTRE.includes(lagret) ? lagret : 'alle';
  } catch (e) {
    return 'alle';
  }
}

function koLagreLoggfilter(valg) {
  try {
    globalThis.window?.localStorage?.setItem(KO_LOGGFILTER_NOKKEL, valg);
  } catch (e) {
    // Uten lagring gjelder valget til sida lastes på nytt. Ikke en feil.
  }
}

function koMerkLoggfilter() {
  const boks = document.getElementById('ko-loggfilter');
  if (!boks) return;
  boks.querySelectorAll('[data-action="koVelgLoggfilter"]').forEach((knapp) => {
    const aktiv = knapp.dataset.arg === koLoggfilter;
    knapp.classList.toggle('active', aktiv);
    knapp.setAttribute('aria-pressed', aktiv ? 'true' : 'false');
  });
}

function koVelgLoggfilter(valg) {
  if (!KO_LOGGFILTRE.includes(valg)) return;
  koLoggfilter = valg;
  koLagreLoggfilter(valg);
  koMerkLoggfilter();
  koTegnLogg();
}

function koStartLoggfilter() {
  koLoggfilter = koLesLoggfilter();
  koMerkLoggfilter();
}

// Tom strøm betyr to ting: filteret tok alt, eller det står ingenting der.
// Teksten skal si hvilket — samme regel som `koOppdragTomMelding()`.
function koLoggTomMelding(harLinjer) {
  if (harLinjer && koLoggfilter === 'system') return 'Ingen systemlinjer i strømmen.';
  if (harLinjer && koLoggfilter === 'meldinger') return 'Ingen meldinger i strømmen.';
  return 'Ingen linjer ennå.';
}

function koTegnLogg() {
  const boks = document.getElementById('ko-logg-liste');
  if (!boks) return;
  const alle = Array.from(koLinjer.values());
  // Samme sortering som serveren: kjedens første ledd, så id — **nyeste
  // øverst** i strømmen, så det siste som skjedde står nærmest øyet uten å
  // rulle (skisse 6).
  const iStrommen = alle.filter(koIStrommen);
  const rader = iStrommen.filter((l) => koLoggfilterTreffer(l, koLoggfilter))
    .sort((a, b) => (b.rot - a.rot) || (b.id - a.id));
  const festede = alle.filter((l) => l.festet_at && !l.fjernet)
    .sort((a, b) => String(a.festet_at).localeCompare(String(b.festet_at), 'nb'));
  // Hodet sier hendelsen når en står åpen i vinduet — ko-hendelser.js.
  koTegnLoggHode();
  if (rader.length === 0 && festede.length === 0) {
    boks.innerHTML = '<p class="text-muted small p-2 mb-0">'
      + escapeHtml(koLoggTomMelding(iStrommen.length > 0)) + '</p>';
    return;
  }
  const festetHtml = festede.length
    ? '<div class="ls-festet-hode"><i class="bi bi-pin-angle-fill me-1"></i>Festet</div>'
      + festede.map(koFestetHtml).join('')
      + '<div class="ls-festet-hode ls-strom-hode mt-2"><i class="bi bi-clock me-1"></i>Strøm</div>'
    : '';
  boks.innerHTML = festetHtml + '<div>' + rader.map(koLinjeHtml).join('') + '</div>';
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
    (data.fjernede || []).forEach(id => {
      koLinjer.forEach(linje => {
        if (linje.id === id && !linje.fjernet) {
          linje.fjernet = true;
          linje.tekst = '';
        }
      });
    });
    // Festing endrer heller ikke id-en; lista over festede sendes hel.
    if (Array.isArray(data.festede)) {
      const festet = new Map(data.festede.map((f) => [f.id, f]));
      koLinjer.forEach((linje) => {
        const f = festet.get(linje.id);
        linje.festet_at = f ? f.festet_at : '';
        linje.festet_av = f ? f.festet_av : '';
      });
    }
    // Delingen (19. sep. 2026) endrer heller ikke id-en, og en angret
    // deling er fravær: lista sendes hel, og tilstanden settes på alle.
    if (Array.isArray(data.delte)) koTaImotDelte(data.delte);
    koTegnLogg();
    // Hendelsene følger med hver poll — hele lista, som `fjernede`: en
    // hendelse som lukkes eller omdøpes har ingen ny id.
    if (data.hendelser) koTaImotHendelser(data.hendelser);
  } catch (e) {
    // En logg som ikke svarer skal ikke tømme skjermen: linjene som alt står
    // der er fortsatt sanne. Feilen vises bare når det ikke står noe.
    const boks = document.getElementById('ko-logg-liste');
    if (boks && koLinjer.size === 0) {
      boks.innerHTML = '<p class="text-muted small p-2 mb-0">Fikk ikke kontakt.</p>';
    }
  }
}

// ── Fargeforklaringen i ressursoversikten (André, 19. sep. 2026) ──────────
//
// «i» i vinduets hode folder den ut og inn; valget huskes per nettleser som
// Alle | Biler | Lag. Ren markup uten data — men den bygger markup, og står
// derfor i byggerlista i ko/tests_js.py som «Nullstill»-fanen.
const KO_LEGENDE_NOKKEL = 'ko.legende';

function koLesLegende() {
  try { return window.localStorage.getItem(KO_LEGENDE_NOKKEL) === 'ja'; } catch (e) { return false; }
}

function koLagreLegende(paa) {
  try { window.localStorage.setItem(KO_LEGENDE_NOKKEL, paa ? 'ja' : 'nei'); } catch (e) { /* privat modus */ }
}

function koLegendeHtml() {
  const rad = (prikk, navn, tekst) => '<span class="rad">' + prikk + '<b>' + navn + '</b>' + (tekst ? ' ' + tekst : '') + '</span>';
  const p = (status) => '<span class="status-prikk status-' + status + '"></span>';
  return rad(p('ledig'), 'Ledig', 'kan sendes')
    + rad(p('tildelt'), 'Tildelt', 'har oppdrag, ikke rykket ut')
    + rad(p('rykker_ut'), 'Rykker ut', '')
    + rad(p('fremme'), 'Fremme', '')
    + rad(p('behandlet'), 'Behandlet på sted / Utført', '')
    + rad(p('avreist'), 'Avreist', '')
    + rad(p('leverer'), 'Leverer', '')
    + rad(p('av_vakt'), 'Av vakt', '')
    + rad('<i class="bi bi-exclamation-triangle-fill"></i>', 'Trenger ressurs', 'oppdrag uten enhet')
    + rad('<span class="enhet-passivmerke">passiv vakt</span>', '', 'sover, kan vekkes')
    + rad('<span class="ko-opptatt">På H14</span>', '', 'laget står på en åpen hendelse');
}

function koTegnLegende() {
  const boks = document.getElementById('ko-legende');
  const knapp = document.getElementById('ko-legende-knapp');
  const paa = koLesLegende();
  if (boks) {
    boks.classList.toggle('d-none', !paa);
    if (paa && !boks.innerHTML) boks.innerHTML = koLegendeHtml();
  }
  if (knapp) {
    knapp.classList.toggle('aktiv', paa);
    knapp.setAttribute('aria-expanded', paa ? 'true' : 'false');
  }
}

function koVippLegende() {
  koLagreLegende(!koLesLegende());
  koTegnLegende();
}

// Regelen for `delte`: det som står i lista er delt, alt annet er intern.
function koTaImotDelte(delte) {
  const delt = new Map(delte.map((d) => [d.id, d]));
  koLinjer.forEach((linje) => {
    const d = delt.get(linje.id);
    linje.delt_at = d ? d.delt_at : null;
    linje.delt_av = d ? d.delt_av : '';
    linje.delt_med = d ? (d.delt_med || []) : [];
  });
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
    // versjonen som gjelder — hent den før operatøren prøver igjen.
    if (res.status === 409) koHentLogg();
    return;
  }
  koLinjer.set(data.data.rot, data.data);
  if (data.data.id > koSisteId) koSisteId = data.data.id;
  koTegnLogg();
  // Hendelsesradene leser loggen: hent alt, så raden og bilen får rettingen.
  koHentLogg();
  koHentOppdragPaaNytt();
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

// Fest og løsne (18. sep. 2026). Svaret er linja; den byttes ut på plass.
async function _koFesting(id, sti) {
  const res = await apiFetch('/ko/api/logg/' + id + '/' + sti + '/', {
    method: 'POST', body: JSON.stringify({}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { koLoggFeil(data.message || 'Gikk ikke.'); return; }
  koLinjer.set(data.data.rot, data.data);
  koTegnLogg();
}

async function koFest(id) { await _koFesting(id, 'fest'); }
async function koLosne(id) { await _koFesting(id, 'losne'); }

// ════════════════════════════════════════════════════════════════════════════
// Ressurslista og oppdragslista hentes **ikke herfra** (pulje 4).
// `/ko/` laster `oppdrag-sentral-*.js`, og de eier begge listene: henting med
// ETag, tegning, polling og alle handlingene. Se ko/CLAUDE.md.
// ════════════════════════════════════════════════════════════════════════════


// ════════════════════════════════════════════════════════════════════════════
// ANSVARSMERKET (pulje 6) — docs/FORSLAG_KO.md §5.1. Vises, styrer ingenting.
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
// ════════════════════════════════════════════════════════════════════════════

const KO_RESSURSER_MS = 30000;
let koRessurser = [];

//: Ressursen med besetningen åpen — én om gangen, som `apenBesetning` for
//: bilene (André, 19. sep. 2026: «du må trykke på ressursen for å se, da
//: sparer vi plass»).
let koApenRessurs = null;

//: Alle | Biler | Lag sto her til 23. sep. 2026. Den er nå seksjonene
//: «Biler» og «Lag» i «Vis»-menyen (`oppdrag-kort.js`), der hver gruppe også
//: kan skjules for seg.

function koVippRessurs(id) {
  koApenRessurs = koApenRessurs === Number(id) ? null : Number(id);
  koTegnRessurser();
}

function koRessursMannskap(r) {
  // Navnene hoistes ut før konkateneringen, som resten av byggerne: skanneren
  // i ko/tests_js.py ser et datafelt limt inn, ikke at `map` escaper inni.
  const navn = (r.mannskap || []).map((m) => escapeHtml(m.navn)
    + (m.tilstede ? '' : ' <span class="text-muted">(ikke møtt)</span>')).join(', ');
  if (navn) return navn;
  return '<span class="text-muted">Ingen på vakt</span>';
}

// Besetningen bak et klikk (19. sep. 2026): navn, møtt, telefon som
// ringbar lenke, ISSI — samme rader som bilens `mkBesetning`, med samme
// kontaktbygger når den er lastet.
function koRessursBesetningHtml(r) {
  const rader = (r.mannskap || []).map((m) => {
    const merke = m.tilstede
      ? '<span class="besetning-inne" title="Møtt">●</span>'
      : '<span class="besetning-ute" title="Ikke møtt">○</span>';
    const rolle = m.rolle ? '<span class="enhet-meta">' + escapeHtml(m.rolle) + '</span>' : '';
    const kontakt = (typeof _besetningKontakt === 'function') ? _besetningKontakt(m) : '';
    return '<div class="besetning-rad">' + merke + '<span>' + escapeHtml(m.navn) + '</span>' + rolle + kontakt + '</div>';
  }).join('');
  return '<div class="besetning">' + (rader || '<span class="enhet-meta">' + koRessursMannskap(r) + '</span>') + '</div>';
}

// «På H14 · Hovedscene · 23 min» — hendelsene laget står på, fra
// hendelsesloggen, med hendelsens sted (André, 19. sep. 2026: «i
// ressursoversikt er det ønskelig at lokasjon vises»). Tom når laget er
// ledig, eller når hendelsene ikke er lastet.
function koRessursOpptattHtml(r) {
  const paa = (typeof koLagPaa === 'function') ? koLagPaa(r.id) : [];
  if (!paa.length) return '';
  const hode = paa.map((x) => '<span class="ko-opptatt">På ' + escapeHtml(x.kode)
    + (x.lokasjon_navn ? ' · ' + escapeHtml(x.lokasjon_navn) : '') + ' · '
    + escapeHtml(koSiden(x.fra)) + '</span>').join(' ');
  const linjer = paa.map((x) => '<div class="enhet-oppdrag" role="button" data-action="koApneHendelse"'
    + ' data-id="' + escapeHtml(x.id) + '"><span class="hendelse-merke">' + escapeHtml(x.kode) + '</span>'
    + '<span class="enhet-oppdrag-problem">' + escapeHtml(x.tittel) + '</span></div>').join('');
  return '<div class="enhet-meta">' + hode + '</div>' + linjer;
}

function koRessurskort(r) {
  const tall = r.antall
    ? escapeHtml(String(r.tilstede)) + ' av ' + escapeHtml(String(r.antall)) + ' møtt'
    : 'ubemannet';
  const apen = koApenRessurs === r.id;
  const besetning = apen ? koRessursBesetningHtml(r) : '';
  const opptatt = koRessursOpptattHtml(r);
  return '<div class="enhet-kort ko-ressurskort enhet-kort-klikkbar' + (apen ? ' ko-ressurskort-apen' : '') + '"'
    + ' data-action="koVippRessurs" data-id="' + escapeHtml(r.id) + '" role="button" tabindex="0">'
    + '<i class="bi bi-' + escapeHtml(r.gruppe_ikon || 'box') + ' ko-ressursikon"></i>'
    + '<div class="flex-grow-1">'
    + '<div class="enhet-navn">' + escapeHtml(r.navn) + '</div>'
    + '<div class="enhet-meta">' + tall + '</div>'
    + opptatt
    + besetning
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
  // En skjult gruppe tas ikke med; tallet står på «Vis» (23. sep. 2026).
  el.innerHTML = koGrupperRessurser(koRessurser)
    .filter((g) => !gruppeErSkjult(koGruppenokkel(g)))
    .map((g) => {
      const hode = gruppehode(g.navn);
      const kort = g.ressurser.map(koRessurskort).join('');
      return '<div class="enhet-gruppe-blokk">' + hode + kort + '</div>';
    }).join('');
}

// «Vis»-menyen bor i `oppdrag-kort.js`, som bare lastes med tilgang til
// oppdragsmodulen — kallet går derfor gjennom en vakt (CLAUDE.md).
function koOppdaterSynlighet() {
  if (typeof oppdaterSynlighetsmeny === 'function') oppdaterSynlighetsmeny();
}

// Vaktlistas grupper til «Vis»-menyen. Menyen bor i `oppdrag-kort.js` og
// spør etter denne gjennom en vakt — sentralbordet i `/oppdrag/` har ingen
// lag å vise.
function koSynlighetsgrupper() {
  return koGrupperRessurser(koRessurser)
    .map((g) => ({ nokkel: koGruppenokkel(g), navn: g.navn, antall: g.ressurser.length }));
}

// Nøkkelen i «Vis»-menyen. Ett sted, så lista og menyen ikke kan komme til å
// mene hver sin gruppe.
function koGruppenokkel(g) {
  return 'gruppe:' + g.id;
}

// ── Én eller to kolonner i ressursoversikten (André, 19. sep. 2026) ─────────
//
// Huskes per nettleser. To spor inne i hver gruppe, gruppene under hverandre
// (23. sep. 2026, se `ko.css`): «en gruppe som mannskapsbil skal ikke begynne
// i kolonne 1 og så gå over i kolonne 2» holder fortsatt.
const KO_KOLONNER_NOKKEL = 'ko.ressurskolonner';

function koLesKolonner() {
  try { return window.localStorage.getItem(KO_KOLONNER_NOKKEL) === '2' ? 2 : 1; } catch (e) { return 1; }
}

function koLagreKolonner(antall) {
  try { window.localStorage.setItem(KO_KOLONNER_NOKKEL, String(antall)); } catch (e) { /* privat modus */ }
}

function koBrukKolonner() {
  const to = koLesKolonner() === 2;
  const kropp = document.querySelector('#ko-vindu-ressurser .ko-vindu-kropp');
  if (kropp) kropp.classList.toggle('ko-to-kolonner', to);
  const knapp = document.getElementById('ko-kolonner-knapp');
  if (knapp) {
    knapp.classList.toggle('aktiv', to);
    knapp.setAttribute('aria-pressed', to ? 'true' : 'false');
  }
}

function koVippKolonner() {
  koLagreKolonner(koLesKolonner() === 2 ? 1 : 2);
  koBrukKolonner();
}

// Sentralbordet kaller denne etter at det tegnet enhetslista (gjennom en
// vakt), så gruppene under følger med — og tallet i vinduets hode.
function koTegnRessurserPaaNytt() {
  koTegnRessurser();
  koOppdaterSynlighet();
  const tall = document.getElementById('ko-ressurser-antall');
  const liste = (typeof sisteEnhetsliste !== 'undefined' && Array.isArray(sisteEnhetsliste)) ? sisteEnhetsliste : [];
  if (tall) {
    const paVakt = liste.filter((e) => e.pa_vakt);
    const ledige = paVakt.filter((e) => e.status === 'ledig').length;
    tall.textContent = '· ' + ledige + ' ledig · ' + (liste.length - paVakt.length) + ' av vakt';
  }
}

async function koHentRessurser() {
  try {
    const res = await apiFetch('/vaktliste/api/ressurser/uten-enhet/');
    if (!res.ok) return;
    koRessurser = (await res.json()).data || [];
    koTegnRessurser();
    koOppdaterSynlighet();
  } catch (e) {
    // Lista som alt står er fortsatt sann; feilen viser seg ved neste poll.
  }
}


// ════════════════════════════════════════════════════════════════════════════
// OPPSTART
//
// **Alt som kjører på toppnivå står her, nederst, i den siste fila.** Kjører
// en tidlig fil noe, kan den lese en binding som ikke er nådd, og siden dør på
// en ReferenceError før noe er tegnet (CLAUDE.md).
// ════════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  koOppsettStart();
  koHendelseVinduStart();
  koTidStart();
  koTavleStart();
  koPlanStart();
  koSidebarLyttere();
  setInterval(() => {
    // Ikke poll en liste ingen ser på: flere operatører sitter på samme side
    // hele vakta, og nedtrekket er lukket som standard.
    if (koSidebarSynlig) koHentTilstede();
  }, KO_TILSTEDE_MS);

  const skjema = document.getElementById('ko-logg-form');
  if (skjema) {
    skjema.addEventListener('submit', (e) => {
      e.preventDefault();
      // `withSubmitGuard` og ikke en egen flagg-variabel: dobbelttrykk under
      // en hendelse er regelen og ikke unntaket.
      withSubmitGuard('ko-logg-send', koSkriv);
    });
    const felt = document.getElementById('ko-logg-tekst');
    // Enter sender, Shift+Enter gir ny linje — som i en chat, og som i
    // hendelsen. Knappen står der fortsatt for den som vil klikke.
    if (felt) {
      felt.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); skjema.requestSubmit(); }
      });
    }
  }

  // Skjemaet skjules for den som bare har `les`. Serveren svarer 403 uansett,
  // men et skrivefelt som ikke kan sende er en vegg man går inn i.
  const boks = document.getElementById('ko-logg-skjema');
  if (boks && !koKanSkrive()) boks.classList.add('d-none');

  const sok = document.getElementById('ko-hendelse-sok');
  if (sok) sok.addEventListener('input', koSokEndret);
  koStartVisLukkede();
  koStartLoggfilter();

  // «Nytt oppdrag» starter uten hendelse hver gang det åpnes, som resten av
  // skjemaet (`nullstillNyttOppdrag`) — og arven må kunne kjøre på nytt.
  const nyttModal = document.getElementById('nyttOppdragModal');
  if (nyttModal) nyttModal.addEventListener('show.bs.modal', koNullstillHendelsevalg);

  koOppdaterSynlighet();
  koTegnLegende();
  koBrukKolonner();

  koLeggHendelsevalgINyttOppdrag();

  koHentLogg();
  setInterval(koHentLogg, KO_LOGG_MS);
  folgEndringer('logg', koHentLogg);

  // Vaktlistas ressurser uten oppdragsenhet (pulje 6). Bare når flata finnes
  // — den tegnes ikke uten vaktlistetilgang.
  if (document.getElementById('vaktliste-ressurser')) {
    koHentRessurser();
    setInterval(koHentRessurser, KO_RESSURSER_MS);
  }
});
