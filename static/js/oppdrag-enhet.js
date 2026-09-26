// ════════════════════════════════════════════════════════
// Enhetsskjermen i oppdragsmodulen (/oppdrag/, for enhetskontoer).
//
// Laster KUN portal-utils.js — samme regel som oppdrag-sentral.js, se
// kommentaren der. Bygget for en telefon i en bil: store trykkflater, og to
// knapper — «neste» og «Ledig». Fem knapper der fire alltid er ulovlige er
// fire måter å trykke feil på i en bil i bevegelse.
//
// Skjermen vet INGENTING om statuskjeden. Serveren sender `neste_overgang`
// og `neste_navn` på hver rad, og knappen poster til det navngitte
// endepunktet den ble fortalt. En kopi av kjeden her ville vært enda et sted
// å komme i utakt — rollemodellnotatets §2.6 i miniatyr.
//
// All brukerdata som settes inn med innerHTML escapes: fritekst er portalens
// første virkelig frie felt. tests_xss.py leser byggerne i denne fila.
// ════════════════════════════════════════════════════════

let mineOppdrag = [];
let etagMine = null;
// Oppdraget som har stedvalget åpent — «Avreist» spør hvor (11. sep. 2026).
// Ett om gangen: knappene bærer bare stedet, og oppdraget står her.
let velgerStedFor = null;
// «Annet sted» spør *hvor* med et fritekstfelt (André, 19. sep. 2026):
// true mens feltet står åpent under stedvalget.
let velgerAnnetSted = false;
// Stedene og grovsorteringen kommer fra serveren via malen, som kjeden.
const AVREIST_TIL = globalThis.OPPDRAG_AVREIST_TIL || [];
const GROVSORTERING = globalThis.OPPDRAG_GROVSORTERING || [];

const HASTEGRAD_REKKEFOLGE = ['Akutt', 'Haster', 'Vanlig', 'Drift', 'Plassering'];



// ════════════════════════════════════════════════════════
// OFFLINE-KØ (fase 5)
//
// Ved knappetrykk skrives stemplingen til `localStorage` FØRST, skjermen
// oppdaterer seg med en gang, og synkingen skjer i bakgrunnen. Feiler den,
// blir raden liggende og forsøkes på nytt — ved neste trykk, ved neste poll,
// og ved `online`-hendelsen.
//
// **Nøkkelen lages ved trykket og beholdes gjennom hvert forsøk.** Det er den
// som gjør avspilling trygg: serveren svarer `ok` med den opprinnelige
// meldingen i stedet for 409, og køen kan stryke raden uten å lure på om
// stemplingen kom fram.
//
// **Kun enhetens stemplinger køes.** Sykestua må ha dekning for å opprette
// oppdrag — se §6. Med bare stemplinger finnes ingen konflikt å løse: hver
// melding er en ny rad, og rekkefølgen avgjøres av `tidspunkt`.
// ════════════════════════════════════════════════════════

//: Lagringsnøkkelen som funksjon, ikke som konstant. `build_harness` i
//: js_test_utils klipper ut funksjoner og ingenting annet, så en `const` her
//: ville vært udefinert i node — og try/catch-en under ville svelget
//: `ReferenceError` og meldt «tom kø». Testen hadde da bestått uten å måle
//: noe. Versjonstallet står i navnet: endres formen på radene, byttes v1 ut,
//: og en gammel kø leses ikke som en ny.
function koNokkel() {
    return 'oppdrag_ko_v1';
}


function koLes() {
    // localStorage kan være utilgjengelig (privat vindu, blokkert lagring)
    // eller inneholde noe annet enn det vi skrev. En kø vi ikke kan lese er
    // en tom kø — skjermen skal virke, men da uten offline-dekning.
    try {
        const raa = localStorage.getItem(koNokkel());
        const verdi = raa ? JSON.parse(raa) : [];
        return Array.isArray(verdi) ? verdi : [];
    } catch (e) {
        return [];
    }
}


function koSkriv(ko) {
    try {
        localStorage.setItem(koNokkel(), JSON.stringify(ko));
        return true;
    } catch (e) {
        return false;
    }
}


function lagNokkel() {
    // Serveren krever ^[A-Za-z0-9-]{8,64}$. `randomUUID` gir 36 tegn som
    // passer; fallbacken finnes for eldre nettlesere i felt.
    if (globalThis.crypto && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    const tall = () => Math.floor(Math.random() * 1e9).toString(36);
    return `k-${Date.now().toString(36)}-${tall()}-${tall()}`;
}


function koLeggTil(oppdragId, overgang, sted, stedTekst) {
    // Klienttiden fryses her, ved trykket — ikke ved sendingen. Uten det
    // ville statistikken vist når dekningen kom tilbake i stedet for når
    // mannskapet faktisk meldte.
    // `sted` følger «Avreist» gjennom køen: valget ble tatt i bilen uten
    // dekning, og skal ikke gå tapt før det kommer fram.
    const rad = {
        nokkel: lagNokkel(),
        oppdragId,
        overgang,
        sted: sted || null,
        // Friteksten ved «Annet sted» (19. sep. 2026) følger raden i køen.
        sted_tekst: stedTekst || null,
        klienttid: new Date().toISOString(),
    };
    const ko = koLes();
    ko.push(rad);
    koSkriv(ko);
    return rad;
}


function koFjern(nokkel) {
    koSkriv(koLes().filter((r) => r.nokkel !== nokkel));
}


function projiser(oppdragliste, ko) {
    // Serverens svar pluss det som ligger usendt = det skjermen skal vise.
    // Uten dette ville et trykk uten dekning sett ut som ingenting: neste
    // poll henter serverens uendrede status og overskriver den optimistiske.
    //
    // Kjeden brukes KUN her, til å regne ut hva neste knapp skal hete når
    // serveren ikke har fått vite om trykket ennå. Er den ikke lastet, faller
    // vi tilbake til ingen neste-knapp — «Ledig» virker uansett, og den er
    // utgang fra enhver status.
    const kjede = globalThis.OPPDRAG_NESTE || {};
    const navn = globalThis.OPPDRAG_STATUSNAVN || {};
    const rader = Array.isArray(oppdragliste) ? oppdragliste : [];
    const usendte = Array.isArray(ko) ? ko : [];

    return rader.map((o) => {
        // Siste trykk vinner: køen er i rekkefølge, og to trykk på samme
        // oppdrag betyr at mannskapet har gått videre i kjeden.
        const mine = usendte.filter((r) => r.oppdragId === o.id);
        if (!mine.length) return o;

        const siste = mine[mine.length - 1];
        // «Avbryt» er en handling, ikke en status, og «Behandlet på sted»
        // lukker med Ledig i samme trykk: raden ender i Ledig for begge.
        const status = (siste.overgang === 'avbryt' || siste.overgang === 'behandlet')
          ? 'ledig' : siste.overgang;
        const nesteEtter = kjede[status] || null;
        const alt = (globalThis.OPPDRAG_ALTERNATIV || {})[status] || null;
        const kanAvbryte = (globalThis.OPPDRAG_AVBRYT_FRA || []).includes(status);
        // «Utført» på Drift og Plassering (19. sep. 2026) — samme regel som
        // `choices.status_navn_for` på serveren.
        const altNavn = (alt === 'behandlet' && ['Drift', 'Plassering'].includes(o.hastegrad))
          ? 'Utført' : ((globalThis.OPPDRAG_ALTERNATIV_NAVN || {})[alt] || alt);
        return {
            ...o,
            status,
            status_navn: navn[status] || status,
            neste_overgang: nesteEtter,
            neste_navn: nesteEtter ? (navn[nesteEtter] || nesteEtter) : null,
            alternativ_overgang: alt,
            alternativ_navn: alt ? altNavn : null,
            kan_avbryte: kanAvbryte,
            usendt: true,
        };
    });
}


// **Egen kopi av `oppdragsnr()`**, som `hastegradKlasse` under: enhetsskjermen
// laster ikke `oppdrag-kort.js`, der sentralbordets utgave bor. Samme form,
// `O45` (§6 i KO-notatet, 18. sep. 2026).
function oppdragsnr(nummer) {
  return 'O' + nummer;
}

// «H14» — KOs nummer på hendelsen. Samme form som i `oppdrag-kort.js`, og
// gjentatt her av samme grunn som `hastegradKlasse`: bilen laster ikke
// sentralbordets filer.
function hendelsesnr(nummer) {
  return 'H' + nummer;
}

function hastegradKlasse(h) {
  return 'hastegrad-' + (h || '').toLowerCase();
}


function _medAntall(problemstilling) {
  return (globalThis.window?.OPPDRAG_MED_ANTALL || []).includes(problemstilling);
}


function _problemMedAntall(o) {
  // «Transport · 3 pasienter» — som i sentralbordet. Tomt betyr én.
  const p = o.problemstilling || '';
  if (!_medAntall(p)) return p;
  const n = o.antall == null ? 1 : Number(o.antall);
  return `${p} · ${n} ${n === 1 ? 'pasient' : 'pasienter'}`;
}


function _antallRad(o) {
  // Bilen setter antall pasienter (André, 12. sep. 2026: «bilen må sette
  // antall pasienter ikke operatøren»). Bare der problemstillingen bærer et
  // antall, og bare på det påbegynte oppdraget. To store knapper, ikke et
  // tallfelt: hansker og en bil i bevegelse.
  if (!_medAntall(o.problemstilling)) return '';
  const n = o.antall == null ? 1 : Number(o.antall);
  return `
    <div class="antall-rad mt-2">
      <span class="oppdrag-meta">Pasienter</span>
      <div class="d-flex align-items-center gap-2 mt-1">
        <button type="button" class="btn btn-outline-light antall-knapp" id="antall-ned"
                data-action="settAntall" data-arg="${escHtmlValue(n - 1)}"${n <= 1 ? ' disabled' : ''}
                aria-label="Én pasient færre">−</button>
        <span class="antall-tall">${escHtmlValue(n)}</span>
        <button type="button" class="btn btn-outline-light antall-knapp" id="antall-opp"
                data-action="settAntall" data-arg="${escHtmlValue(n + 1)}"
                aria-label="Én pasient til">+</button>
      </div>
    </div>`;
}


// ── Feilbanner ──────────────────────────────────────────
// Feil skal synes fra førersetet, og bli stående til noe lykkes. En knapp
// som ser ut til å ha virket, men ikke har det, er verre enn en som feiler
// synlig. (Offline-køen kommer i fase 5 — fram til den finnes er beskjeden
// «meld over nødnett» det ærlige svaret.)

function visFeil(melding) {
  const el = document.getElementById('enhet-feil');
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}

function skjulFeil() {
  const el = document.getElementById('enhet-feil');
  if (el) el.classList.add('d-none');
}


//: Så lenge en stempling får være underveis før skjermen sier «venter på
//: dekning». Trykket legges i køen før det sendes, og meldingen kom derfor
//: opp i det halve sekundet sendingen tok — også med full dekning (André,
//: 13. sep. 2026: «3 sekunder delay?»).
const USENDT_VENTETID_MS = 3000;
let usendtTimer = null;


function usendtAlder(ko, naaMs) {
  // Alderen på den eldste raden i køen, i ms. En rad uten lesbar tid regnes
  // som gammel nok — meldingen skal heller komme for tidlig enn aldri.
  let eldst = 0;
  for (const rad of ko) {
    const t = Date.parse(rad.klienttid);
    const alder = Number.isFinite(t) ? naaMs - t : Infinity;
    if (alder > eldst) eldst = alder;
  }
  return eldst;
}


function visUsendt() {
  // Egen, roligere tone enn `visFeil`: dette er ikke en feil, det er en
  // stempling som venter på dekning. Men den MÅ synes — §6: en knapp som ser
  // ut til å ha virket, men ikke har det, er verre enn en som feiler synlig.
  const ko = koLes();
  const antall = ko.length;
  const el = document.getElementById('enhet-usendt');
  if (!el) return;
  if (usendtTimer) { clearTimeout(usendtTimer); usendtTimer = null; }
  if (!antall) {
    el.classList.add('d-none');
    return;
  }
  const alder = usendtAlder(ko, Date.now());
  if (alder < USENDT_VENTETID_MS) {
    // Sendingen kan fortsatt lykkes. Kom tilbake når fristen er ute — går
    // køen tom før det, skjuler `renderAlt()` meldingen som før.
    el.classList.add('d-none');
    usendtTimer = setTimeout(visUsendt, USENDT_VENTETID_MS - alder);
    return;
  }
  el.textContent = antall === 1
    ? '1 stempling venter på dekning — den sendes av seg selv.'
    : `${antall} stemplinger venter på dekning — de sendes av seg selv.`;
  el.classList.remove('d-none');
}


// ── Byggere ─────────────────────────────────────────────
// Fragmentene bygges før mal-strengen, ikke inne i en ${...}: XSS-vernet i
// tests_xss.py kan ikke se inn i en nøstet mal-streng, så en uescapet verdi
// der ville passert stille.

function _stedvalg() {
  // Seks steder fra serveren (`OPPDRAG_AVREIST_TIL`), som store knapper.
  // Nøkkelen er det som sendes; etiketten det som vises.
  // **`data-arg`, ikke `data-id`**: delegeringen gjør `data-id` om til tall,
  // og `Number('sykehus')` er NaN. Knappene sto døde i prod 12. sep. 2026
  // fordi node-testene bare så på markupen — ingen klikket på dem.
  const knapper = AVREIST_TIL.map(([nokkel, navn]) =>
    `<button type="button" class="btn btn-primary stor-knapp"
             id="stemple-sted-${escHtmlValue(nokkel)}"
             data-action="stempleAvreistTil" data-arg="${escHtmlValue(nokkel)}">
       ${escapeHtml(navn)}</button>`).join('');
  // «Annet sted» får et fritekstfelt (André, 19. sep. 2026): ett felt og én
  // knapp i stedet for de seks — samme regel om at det ikke skal finnes en
  // feil knapp å treffe midt i valget. Tom tekst er lov; stedet står uansett.
  if (velgerAnnetSted) {
    return `
    <div class="mt-3">
      <div class="oppdrag-meta mb-2">Avreist til annet sted — hvor?</div>
      <input type="text" class="form-control form-control-lg" id="stemple-sted-tekst"
             maxlength="120" placeholder="F.eks. Legevakt Karmøy" autocomplete="off">
      <button type="button" class="btn btn-primary stor-knapp mt-2 w-100"
              id="stemple-sted-annet-ok" data-action="stempleAnnetSted">Avreist</button>
      <button type="button" class="btn btn-outline-light stor-knapp mt-2 w-100"
              data-action="avbrytStedvalg">Avbryt</button>
    </div>`;
  }
  return `
    <div class="mt-3">
      <div class="oppdrag-meta mb-2">Avreist til:</div>
      <div class="stedvalg">${knapper}</div>
      <button type="button" class="btn btn-outline-light stor-knapp mt-2 w-100"
              data-action="avbrytStedvalg">Avbryt</button>
    </div>`;
}


function _kanGrovsortere(o) {
  // Ingen pasient på Drift og Plassering (André, 12. og 19. sep. 2026) —
  // raden vises ikke der. Lista står inne i funksjonen (speiler
  // `choices.UTEN_PASIENT`): testene henter funksjonen alene.
  if (['Drift', 'Plassering'].includes(o.hastegrad)) return false;
  return ['fremme', 'avreist', 'leverer'].includes(o.status);
}


function _grovsorteringsrad(o) {
  // Bilens vurdering: tre knapper, den valgte fylt. Ingen valgt betyr
  // «ikke vurdert ennå», og det står som tekst — ikke som en tom rad.
  const knapper = GROVSORTERING.map(([nokkel, navn]) => {
    const valgt = o.grovsortering === nokkel;
    const klasse = valgt ? `btn grov-knapp grov-${nokkel} grov-valgt` : `btn grov-knapp grov-${nokkel}`;
    return `<button type="button" class="${escHtmlValue(klasse)}" id="grov-${escHtmlValue(nokkel)}"
                    data-action="settGrovsortering" data-arg="${escHtmlValue(nokkel)}"
                    aria-pressed="${valgt ? 'true' : 'false'}">${escapeHtml(navn)}</button>`;
  }).join('');
  const status = o.grovsortering_navn
    ? `Grovsortering: ${o.grovsortering_navn}` : 'Grovsortering: ikke vurdert';
  return `
    <div class="grovsortering mt-2">
      <span class="oppdrag-meta">${escapeHtml(status)}</span>
      <div class="d-flex gap-2 mt-1">${knapper}</div>
    </div>`;
}


function _varsledeRad(o) {
  // Hvem som ellers er varslet på oppdraget. Hva de gjør står i tidslinjen
  // under, med navn på hver rad (`andre_meldinger`).
  const andre = o.varslede || [];
  if (!andre.length) return '';
  return `<div class="oppdrag-meta oppdrag-varslede mb-1">Også varslet: ${escapeHtml(andre.join(', '))}</div>`;
}


function tidslinjeEnhetHtml(o) {
  // **Egne og de andres stempler i én tidslinje** (André, 12. sep. 2026:
  // «nyttig for de å vite historikken der»). De andres rader bærer bilens
  // navn og er dempet; egen kjede og knappene hviler bare på
  // `statusmeldinger`, så en annen bils Fremme flytter ikke denne bilen.
  const egne = (o.statusmeldinger || []).map((m) => ({ m, andres: false }));
  const andre = (o.andre_meldinger || []).map((m) => ({ m, andres: true }));
  const rader = egne.concat(andre)
    .sort((x, y) => String(x.m.tidspunkt).localeCompare(String(y.m.tidspunkt), 'nb'));
  return rader.map(({ m, andres }) => {
    // Markøren for et avledet tidspunkt sitter på KLOKKESLETTET, ikke på
    // statusordet — det er tidspunktet som er utledet. Gråtoner, ingen
    // badge: en ny farge ville gjort metadata om til en tilstand.
    const tidKlasse = m.automatisk ? 'tidslinje-tid tid-avledet' : 'tidslinje-tid';
    const tittel = m.automatisk
      ? ' title="Avsluttet automatisk da enheten startet neste oppdrag"'
      : '';
    const notat = [];
    if (m.automatisk) notat.push('avsluttet automatisk');
    if (m.forsinket) notat.push('meldt forsinket');
    // §4.5: bilen ser at sentralen har rettet tidspunktet, men kan ikke
    // rette det selv. Samme dempede linje som på sentralbordet.
    if (m.korrigerer) notat.push('rettet av sentralen');
    // §9: sentralbordet førte statusen — bilen stemplet den ikke selv.
    if (m.manuell) notat.push('endret av KO');
    const notatBlokk = notat.length
      ? `<span class="tidslinje-notat">· ${escapeHtml(notat.join(', '))}</span>`
      : '';
    // «Avreist → Sykehus»: stedet står ved statusen, ikke som notat.
    const statusMedSted = m.sted_navn ? `${m.status_navn} → ${m.sted_navn}` : String(m.status_navn);
    const hvem = andres
      ? `<span class="tidslinje-enhet">${escapeHtml(m.enhet_navn || '')}:</span> `
      : '';
    return `
      <div class="tidslinje-rad${andres ? ' tidslinje-andre' : ''}">
        <span class="${tidKlasse}"${tittel}>${escapeHtml(klokke(m.tidspunkt))}</span>
        <span>${hvem}${escapeHtml(statusMedSted)}</span>
        ${notatBlokk}
      </div>`;
  }).join('');
}


function _udefinertVarsel(o) {
  // Står problemstillingen som «Udefinert», avviser serveren «Ledig». Det
  // skal bilen få vite FØR hun trykker, ikke som en avvisning etterpå
  // (André, 12. sep. 2026: «tydelig melding om at å melde problemstilling
  // til KO»). Ingen knapp fjernes — KO kan sette den mens hun leser.
  if ((o.problemstilling || '') !== 'Udefinert') return '';
  return `
      <div class="alert alert-warning enhet-udefinert mb-2" role="status">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>
        Problemstillingen står som «Udefinert». Meld problemstillingen til KO —
        enheten kan ikke meldes ledig før sentralbordet har satt den.
      </div>`;
}


function renderAktivt() {
  const el = document.getElementById('aktivt-oppdrag');
  if (!el) return;

  // Serveren garanterer maks ett påbegynt oppdrag (§4.3) — «neste» på et
  // ventende lukker det pågående. Skulle lista likevel ha flere, vises alle:
  // å skjule ett ville vært å gjette hvilket som er ekte.
  const aktive = mineOppdrag.filter(
    (o) => o.status !== 'venter' && o.status !== 'ledig');

  if (!aktive.length) {
    el.innerHTML = '<div class="enhet-ledig-kort">Ledig — ingen påbegynte oppdrag</div>';
    return;
  }

  el.innerHTML = aktive.map((o) => {
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    // Lagene og beskrivelsen på hendelsen oppdraget hører til (André, 18.–19.
    // sep. 2026). KO fører dem på hendelsen; bilen ser dem her. Tomme uten
    // hendelse.
    const lagNavn = (o.hendelse_id && Array.isArray(o.hendelse_lag)) ? o.hendelse_lag.join(', ') : '';
    const lagBlokk = lagNavn
      ? `<div class="oppdrag-meta oppdrag-lag mb-1"><i class="bi bi-people me-1"></i>Lag på hendelsen: ${escapeHtml(lagNavn)}</div>`
      : '';
    // Linjene KO har delt fra loggen i hendelsen, med hvem og når. Det som
    // er delt det siste minuttet står gult (`erNyDelt`). Rader bygget før
    // mal-strengen (skanneren ser ikke inn i en nøstet).
    const beskrivelseBlokk = delteLinjerBlokk(o);
    const nesteKnapp = o.neste_overgang
      ? `<button type="button" class="btn btn-primary stor-knapp flex-grow-1"
                 id="stemple-neste-${escHtmlValue(o.id)}"
                 data-action="stempleNeste" data-id="${escHtmlValue(o.id)}">
           ${escapeHtml(o.neste_navn)}</button>`
      : '';
    // **Ingen egen Ledig-knapp** (André, 12. sep. 2026). Den andre knappen
    // er statusens: «Behandlet på sted» i Fremme. Mellom Avreist og Leverer
    // finnes bare «neste» — hun har en pasient i bilen. Ledig er «neste»
    // etter Leverer og etter Behandlet.
    const altKnapp = o.alternativ_overgang
      ? `<button type="button" class="btn btn-outline-light stor-knapp"
                 id="stemple-alt-${escHtmlValue(o.id)}"
                 data-action="stempleAlternativ" data-id="${escHtmlValue(o.id)}">
           ${escapeHtml(o.alternativ_navn)}</button>`
      : '';
    // **«Avbryt» i Rykker ut og Fremme** (André, 22. sep. 2026: «fra en
    // trykker rykker ut til og med når en er fremme, gjelder ikke fra
    // avreist av»). Egen knapp, ikke den andre: i Fremme står «Behandlet på
    // sted» der. Rød kant, fordi den sender oppdraget tilbake til KO. Egen
    // linje i full bredde under de to andre: tre knapper på rad får ikke plass
    // på en telefon, og den som sjelden brukes skal ikke ta plass fra dem.
    const avbrytKnapp = o.kan_avbryte
      ? `<button type="button" class="btn btn-outline-danger stor-knapp w-100 mt-2"
                 id="stemple-avbryt-${escHtmlValue(o.id)}"
                 data-action="stempleAvbryt" data-id="${escHtmlValue(o.id)}">Avbryt</button>`
      : '';
    // **Stedvalget erstatter knapperaden** når «Avreist» er trykket: seks
    // store knapper og «Avbryt», ingen annen knapp ved siden av — i en bil i
    // bevegelse skal det ikke finnes en feil knapp å treffe midt i valget.
    const knapperad = velgerStedFor === o.id
      ? _stedvalg()
      : `<div class="d-flex gap-2 mt-3">${nesteKnapp}${altKnapp}</div>${avbrytKnapp}`;
    // Grovsorteringen er en vurdering av pasienten, og den finnes ikke før
    // bilen er framme (André, 12. sep. 2026). Under utrykning står den ikke.
    const grovRad = _kanGrovsortere(o) ? _grovsorteringsrad(o) : '';
    const udefinert = _udefinertVarsel(o);
    return `
    <div class="aktivt-kort">
      <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(_problemMedAntall(o))}</span>
        <span class="ms-auto oppdrag-status-naa">${escapeHtml(o.status_navn)}</span>
      </div>
      <div class="oppdrag-meta mb-1">${escapeHtml(o.lokasjon_navn)}</div>
      ${udefinert}
      ${_varsledeRad(o)}
      ${lagBlokk}
      ${beskrivelseBlokk}
      ${fritekstBlokk}
      ${_antallRad(o)}
      ${grovRad}
      <div class="mt-2">${tidslinjeEnhetHtml(o)}</div>
      ${knapperad}
    </div>`;
  }).join('');
}


function renderVentende() {
  const el = document.getElementById('ventende-liste');
  if (!el) return;

  const ventende = mineOppdrag
    .filter((o) => o.status === 'venter')
    .sort((a, b) => {
      // Hastegrad først, eldst først innenfor lik hastegrad. Rekkefølgen er
      // et forslag, ikke en kø: mannskapet velger selv hvilket de starter —
      // de ser hastegrad og lokasjon, og vet hva som er nærmest.
      const ah = HASTEGRAD_REKKEFOLGE.indexOf(a.hastegrad);
      const bh = HASTEGRAD_REKKEFOLGE.indexOf(b.hastegrad);
      if (ah !== bh) return ah - bh;
      return new Date(a.opprettet) - new Date(b.opprettet);
    });

  if (!ventende.length) {
    el.innerHTML = '<div class="tom-melding">Ingen ventende oppdrag.</div>';
    return;
  }

  el.innerHTML = ventende.map((o) => {
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    const lagNavn = (o.hendelse_id && Array.isArray(o.hendelse_lag)) ? o.hendelse_lag.join(', ') : '';
    const lagBlokk = lagNavn
      ? `<div class="oppdrag-meta oppdrag-lag mb-1"><i class="bi bi-people me-1"></i>Lag på hendelsen: ${escapeHtml(lagNavn)}</div>`
      : '';
    // Linjene KO har delt fra loggen i hendelsen, med hvem og når. Det som
    // er delt det siste minuttet står gult (`erNyDelt`). Rader bygget før
    // mal-strengen (skanneren ser ikke inn i en nøstet).
    const beskrivelseBlokk = delteLinjerBlokk(o);
    const startKnapp = `
      <button type="button" class="btn btn-primary stor-knapp w-100 mt-2"
              id="stemple-neste-${escHtmlValue(o.id)}"
              data-action="stempleNeste" data-id="${escHtmlValue(o.id)}">
        ${escapeHtml(o.neste_navn)}</button>`;
    // Mens hun venter har hun ingen egne stempler — men de andre bilene kan
    // ha rykket ut alt, og det er nettopp da det er verdt å vite (André,
    // 12. sep. 2026: «Bil B ser ikke A sine stempler så lenge den står i
    // venter»).
    const andresTidslinje = (o.andre_meldinger || []).length
      ? `<div class="mt-2">${tidslinjeEnhetHtml(o)}</div>` : '';
    // Forbi første terskel: raden pulserer, uansett om lyden er på. Lyd
    // alene kan overhøres i en bil med sirene.
    const venterLenge = skalPipe({ ...o, usendt: false }, Date.now(), null) ? ' oppdrag-rad-venter-lenge' : '';
    return `
    <div class="oppdrag-rad${venterLenge}">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(_problemMedAntall(o))}</span>
      </div>
      <div class="oppdrag-meta mt-1">${escapeHtml(o.lokasjon_navn)} · ${escapeHtml(klokke(o.opprettet))}</div>
      ${_varsledeRad(o)}
      ${lagBlokk}
      ${beskrivelseBlokk}
      ${fritekstBlokk}
      ${andresTidslinje}
      ${startKnapp}
    </div>`;
  }).join('');
}


function renderAvsluttet() {
  const seksjon = document.getElementById('avsluttet-seksjon');
  const el = document.getElementById('avsluttet-liste');
  if (!seksjon || !el) return;

  // Serveren har allerede utelatt fritekst her, og fjerner hele raden 30
  // minutter etter Ledig — dette er visning av det som kom, ikke filtrering.
  const avsluttede = mineOppdrag.filter((o) => o.status === 'ledig');
  if (!avsluttede.length) {
    seksjon.classList.add('d-none');
    return;
  }
  seksjon.classList.remove('d-none');

  el.innerHTML = avsluttede.map((o) => {
    const ledigMelding = (o.statusmeldinger || []).find((m) => m.status === 'ledig');
    const tidKlasse = ledigMelding && ledigMelding.automatisk
      ? 'tidslinje-tid tid-avledet' : 'tidslinje-tid';
    const tittel = ledigMelding && ledigMelding.automatisk
      ? ' title="Avsluttet automatisk da enheten startet neste oppdrag"' : '';
    const notatBlokk = ledigMelding && ledigMelding.automatisk
      ? '<span class="tidslinje-notat">· avsluttet automatisk</span>' : '';
    const tid = ledigMelding ? klokke(ledigMelding.tidspunkt) : '';
    return `
    <div class="oppdrag-rad oppdrag-avsluttet">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">${escHtmlValue(oppdragsnr(o.nummer))}</span>
        <span class="oppdrag-meta">${escapeHtml(_problemMedAntall(o))}</span>
        <span class="ms-auto">
          <span class="${tidKlasse}"${tittel}>Ledig ${escapeHtml(tid)}</span>
          ${notatBlokk}
        </span>
      </div>
    </div>`;
  }).join('');
}


// ── Lydvarsel ───────────────────────────────────────────
//
// Et ventende oppdrag som ingen trykker «Rykker ut» på skal høres, og
// oftere jo mer det haster. Lyden lages med Web Audio (ingen fil å laste,
// ingen dekning å vente på), og nettleseren krever et trykk før den får
// spille — derfor «Lyd»-knappen, som også husker valget i localStorage.
// Tida måles fra da *bilen* ble varslet (`varslet_at`), ikke fra
// opprettelsen: et oppdrag som fikk henne som bil nummer to skal ikke pipe
// som om hun hadde oversett det i en time.

let lydKontekst = null;
//: Oppdrag-ID → tidspunkt (ms) for siste pip. Nullstilles når oppdraget
//: ikke lenger venter.
let lydSistFor = {};
//: Oppdrag-ID-ene skjermen har sett — for «nytt oppdrag»-pipet. `null` til
//: første lasting, så det ikke piper for alt som lå der da siden åpnet.
let kjenteOppdrag = null;


//: **Lyden er på som standard** (André, 12. sep. 2026). Tre ting kan gjøre
//: den stille: nettleseren har ikke fått trykket sitt ennå (`lydErKlar`),
//: admin har slått lydvarselet av for alle biler (`bilinnstillinger`), eller
//: føreren har dempet denne enheten med ikonet (`erDempet`, husket lokalt).
function lydErKlar() {
  return !!(lydKontekst && lydKontekst.state === 'running');
}


function bilinnstillinger() {
  return globalThis.OPPDRAG_BILINNSTILLINGER || {};
}


//: Lagringsnøkkelen som funksjon — se `koNokkel()`.
function dempNokkel() {
  return 'oppdrag_lyd_demp_v1';
}


function erDempet() {
  try { return globalThis.localStorage.getItem(dempNokkel()) === '1'; } catch (e) { return false; }
}


function lydSkalSpille() {
  return lydErKlar() && bilinnstillinger().lyd_aktiv !== false && !erDempet();
}


//: Tersklene per hastegrad: [første varsel etter sekunder, deretter hvert
//: sekund]. Fra tabellen `Lydvarsel` via `OPPDRAG_LYDVARSEL` (12. sep. 2026:
//: admin justerer dem), hentet på nytt hvert femte minutt. Tallene her er
//: bare fallet tilbake når siden ikke fikk dem: «Rød innen 1 minutt,
//: deretter hvert 10 sekund. Gul innen 5 minutt deretter hvert 1 minutt.
//: Grønn etter 15 minutt deretter hvert 1 minutt.» Som funksjon, ikke
//: konstant — se `koNokkel()`.
function lydTerskler() {
  const fra = bilinnstillinger().terskler;
  if (fra && typeof fra === 'object' && Object.keys(fra).length) return fra;
  return { Akutt: [60, 10], Haster: [300, 60], Vanlig: [900, 60], Drift: [900, 60], Plassering: [900, 60] };
}


function _lydTerskler(hastegrad) {
  const alle = lydTerskler();
  return alle[hastegrad] || alle.Vanlig || [900, 60];
}


function ventetSekunder(o, naaMs) {
  const fra = o.varslet_at || o.opprettet;
  if (!fra) return 0;
  return Math.max(0, (naaMs - new Date(fra).getTime()) / 1000);
}


function skalPipe(o, naaMs, sist) {
  // Ventende, ikke trykket på (et usendt trykk ligger i køen — da har hun
  // svart, selv om serveren ikke vet det ennå), forbi første terskel, og
  // lenge nok siden forrige pip.
  if (o.status !== 'venter' || o.usendt) return false;
  // Admin kan slå ventevarselet av per hastegrad (12. sep. 2026).
  const aktive = bilinnstillinger().aktive || {};
  if (aktive[o.hastegrad] === false) return false;
  const [forste, hver] = _lydTerskler(o.hastegrad);
  if (ventetSekunder(o, naaMs) < forste) return false;
  if (sist == null) return true;
  return (naaMs - sist) / 1000 >= hver;
}


function ventendeSomSkalPipe(liste, naaMs, sistKart) {
  return (liste || []).filter((o) => skalPipe(o, naaMs, sistKart[o.id])).map((o) => o.id);
}


function _strengeste(liste, ider) {
  const valgte = (liste || []).filter((o) => ider.includes(o.id));
  return valgte.map((o) => o.hastegrad)
    .sort((a, b) => HASTEGRAD_REKKEFOLGE.indexOf(a) - HASTEGRAD_REKKEFOLGE.indexOf(b))[0] || 'Vanlig';
}


function _tone(ctx, fra, varighet, frekvens) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'square';
  osc.frequency.value = frekvens;
  gain.gain.setValueAtTime(0.0001, fra);
  gain.gain.exponentialRampToValueAtTime(0.4, fra + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, fra + varighet);
  osc.connect(gain).connect(ctx.destination);
  osc.start(fra);
  osc.stop(fra + varighet + 0.05);
}


function pip(hastegrad) {
  // Lengre enn første utgave (André, 12. sep. 2026: «noe som er litt lengre
  // i varighet»), men aldri over tre sekunder. Akutt: seks toner, vekslende
  // høyt og lavt. Haster: fire. Vanlig/Drift: tre rolige.
  if (!lydKontekst) return;
  const ctx = lydKontekst;
  const t = ctx.currentTime;
  if (hastegrad === 'Akutt') {
    for (let i = 0; i < 6; i++) _tone(ctx, t + i * 0.48, 0.4, i % 2 ? 660 : 880);
  } else if (hastegrad === 'Haster') {
    for (let i = 0; i < 4; i++) _tone(ctx, t + i * 0.65, 0.5, 660);
  } else {
    for (let i = 0; i < 3; i++) _tone(ctx, t + i * 0.8, 0.6, 520);
  }
}


function pipNytt() {
  // Nytt oppdrag i lista (12. sep. 2026): to korte stigende toner, tydelig
  // forskjellig fra ventevarselet. Admin kan slå det av (`OPPDRAG_LYD_NYTT`).
  if (!lydKontekst) return;
  const t = lydKontekst.currentTime;
  _tone(lydKontekst, t, 0.25, 660); _tone(lydKontekst, t + 0.3, 0.45, 990);
}


function nyeOppdrag(liste) {
  // ID-ene i `liste` skjermen ikke har sett før. Første kall lærer bare
  // lista og svarer tomt — det som lå der da siden åpnet er ikke nytt.
  const ider = (liste || []).map((o) => o.id);
  if (kjenteOppdrag === null) {
    kjenteOppdrag = new Set(ider);
    return [];
  }
  const nye = ider.filter((id) => !kjenteOppdrag.has(id));
  ider.forEach((id) => kjenteOppdrag.add(id));
  return nye;
}


function lydTikk(naaMs) {
  // Kalles hvert femte sekund. Rydder først: et oppdrag som ikke lenger
  // venter skal ikke bære et gammelt tidspunkt til det dukker opp igjen.
  const naa = naaMs || Date.now();
  const venter = new Set((mineOppdrag || []).filter((o) => o.status === 'venter').map((o) => o.id));
  Object.keys(lydSistFor).forEach((id) => { if (!venter.has(Number(id))) delete lydSistFor[id]; });
  if (!lydSkalSpille()) return [];
  const ider = ventendeSomSkalPipe(mineOppdrag, naa, lydSistFor);
  if (!ider.length) return [];
  ider.forEach((id) => { lydSistFor[id] = naa; });
  pip(_strengeste(mineOppdrag, ider));
  return ider;
}


function _lydHintTegn() {
  // Linja «trykk for å slå på lyden» står til nettleseren har sluppet lyden
  // gjennom. Dempeikonet viser om lyden faktisk vil spille: dempet av
  // føreren, slått av av admin, eller klar.
  const hint = document.getElementById('lyd-hint');
  if (hint) hint.classList.toggle('d-none', lydErKlar());
  const knapp = document.getElementById('lyd-demp');
  if (!knapp) return;
  const dempet = erDempet();
  const adminAv = bilinnstillinger().lyd_aktiv === false;
  knapp.setAttribute('aria-pressed', dempet ? 'true' : 'false');
  knapp.classList.toggle('lyd-demp-paa', dempet);
  knapp.disabled = adminAv;
  knapp.title = adminAv ? 'Lydvarselet er slått av av admin'
    : (dempet ? 'Slå på lydvarsel' : 'Demp lydvarsel');
  knapp.setAttribute('aria-label', knapp.title);
  knapp.innerHTML = (dempet || adminAv)
    ? '<i class="bi bi-volume-mute"></i>'
    : '<i class="bi bi-volume-up-fill"></i>';
}


async function vekslDemp() {
  // Per enhet, husket lokalt. Å slå på igjen vekker også lyden om trykket
  // er det første på siden.
  const dempet = !erDempet();
  try { globalThis.localStorage.setItem(dempNokkel(), dempet ? '1' : '0'); } catch (e) { /* uten lagring: gjelder til siden lastes */ }
  if (!dempet && await _lydKlar()) {
    _tone(lydKontekst, lydKontekst.currentTime, 0.15, 660);
  }
  _lydHintTegn();
}


function _stilleLydbaerer() {
  // **iOS med lydbryteren på stille.** Web Audio regnes som «ambient» og
  // dempes av bryteren — men et `<audio>`-element som spiller, flytter
  // lydøkta til «playback», og da går Web Audio gjennom likevel. En stum,
  // loopende WAV på ett tiendedels sekund holder økta åpen. Fra iOS 17 sier
  // vi det også rett ut med `navigator.audioSession`. Ingen garanti — det er
  // en omvei rundt en regel Apple eier — men det er den omveien som finnes.
  try {
    if (globalThis.navigator?.audioSession) globalThis.navigator.audioSession.type = 'playback';
  } catch (e) { /* ikke støttet */ }
  if (globalThis._lydbaerer || typeof Audio === 'undefined') return;
  const rate = 8000; const n = rate / 10;
  const buf = new ArrayBuffer(44 + n);
  const dv = new DataView(buf);
  const skriv = (pos, str) => { for (let i = 0; i < str.length; i++) dv.setUint8(pos + i, str.charCodeAt(i)); };
  skriv(0, 'RIFF'); dv.setUint32(4, 36 + n, true); skriv(8, 'WAVE'); skriv(12, 'fmt ');
  dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, rate, true); dv.setUint32(28, rate, true); dv.setUint16(32, 1, true);
  dv.setUint16(34, 8, true); skriv(36, 'data'); dv.setUint32(40, n, true);
  for (let i = 0; i < n; i++) dv.setUint8(44 + i, 128);
  const blob = new Blob([buf], { type: 'audio/wav' });
  const a = new Audio(URL.createObjectURL(blob));
  a.loop = true; a.setAttribute('playsinline', ''); a.volume = 0.01;
  a.play().catch(() => {});
  globalThis._lydbaerer = a;
}


async function _lydKlar() {
  // Nettleseren lar lyd spille først etter et trykk; kontekst lages og
  // vekkes her, fra det første trykket på siden.
  const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!AC) return false;
  if (!lydKontekst) lydKontekst = new AC();
  if (lydKontekst.state !== 'running') {
    try { await lydKontekst.resume(); } catch (e) { /* ikke lov ennå */ }
  }
  if (lydErKlar()) _stilleLydbaerer();
  return lydErKlar();
}


async function lastBilinnstillinger() {
  // Det admin setter skal nå bilen uten at siden lastes på nytt.
  let res;
  try { res = await apiFetch('/oppdrag/api/bilinnstillinger/'); } catch (e) { return; }
  if (!res.ok) return;
  const d = (await res.json()).data || {};
  if (d.terskler) globalThis.OPPDRAG_BILINNSTILLINGER = d;
  _lydHintTegn();
}


function grovKrevesFor(o, overgang) {
  // Speiler `verdier.grov_kreves_for` på serveren: alltid før Behandlet på
  // sted og før Ledig fra Leverer; før Avreist når admin har satt det.
  // Aldri på Drift og Plassering. Sjekkes før trykket går i køen, så bilen
  // får beskjeden med en gang i stedet for en avvist rad.
  if (['Drift', 'Plassering'].includes(o.hastegrad)) return false;
  if (overgang === 'behandlet') return true;
  if (overgang === 'ledig' && o.status === 'leverer') return true;
  if (overgang === 'avreist') return bilinnstillinger().krev_grov_avreist === true;
  return false;
}


function _grovMangler(o, overgang) {
  if (o.grovsortering || !grovKrevesFor(o, overgang)) return false;
  visFeil('Sett grovsortering (Rød, Gul, Grønn eller Ikke aktuelt) først.');
  return true;
}


function renderAlt() {
  renderAktivt();
  renderVentende();
  renderAvsluttet();
  visUsendt();
  const stempel = document.getElementById('enhet-oppdatert');
  if (stempel) stempel.textContent = 'Oppdatert ' + klokke(new Date().toISOString());
}


// ── Stempling ───────────────────────────────────────────

//: True mens `synk()` kjører, slik at to utløsere (trykk og poll) ikke
//: sender samme rad to ganger. Nøkkelen ville gjort det ufarlig, men to
//: parallelle løp kan levere ut av rekkefølge.
let synkerNaa = false;


async function synk() {
  if (synkerNaa) return;
  synkerNaa = true;
  try {
    // Serielt og i rekkefølge. Statusmeldinger er et spor av hva som skjedde,
    // og to parallelle sendinger kunne landet «Avreist» før «Fremme».
    // En avvisning i denne runden skal bli stående når køen er tom etterpå:
    // «køen er tom» er ellers akkurat det som skjer når serveren nettopp
    // strøk raden med en beskjed (André, 12. sep. 2026: bilen fikk aldri se
    // «Udefinert»-meldingen — den ble skjult i samme åndedrag).
    let avvist = false;
    while (true) {
      const ko = koLes();
      if (!ko.length) { if (!avvist) skjulFeil(); break; }

      const rad = ko[0];
      let res;
      try {
        // Stedet er et URL-ledd, ikke et felt i kroppen — endepunktet leser
        // ingen domenefelt derfra.
        const stedLedd = rad.sted ? `${encodeURIComponent(rad.sted)}/` : '';
        res = await apiFetch(
          `/oppdrag/api/oppdrag/${rad.oppdragId}/status/${rad.overgang}/${stedLedd}`, {
            method: 'POST',
            body: JSON.stringify({
              klienttid: rad.klienttid,
              idempotency_key: rad.nokkel,
              // Det ene domenefeltet: friteksten ved «Annet sted».
              sted_tekst: rad.sted_tekst || undefined,
            }),
          });
      } catch (e) {
        // Ingen kontakt. Raden blir liggende og forsøkes ved neste trykk,
        // neste poll, eller `online`-hendelsen. Stopp her: rekkefølgen.
        visUsendt();
        break;
      }

      if (res.ok) {
        // Enten levert nå, eller en avspilling serveren kjente igjen på
        // nøkkelen. Begge betyr at stemplingen står — stryk raden.
        koFjern(rad.nokkel);
        continue;
      }

      let d = {};
      try { d = await res.json(); } catch (e) { /* tom kropp */ }

      if (res.status === 409 && d.duplikat) {
        // Samme trykk er allerede underveis. La den andre fullføre.
        break;
      }
      if (res.status >= 400 && res.status < 500) {
        // Serveren avviste den, og vil gjøre det igjen: ulovlig overgang,
        // manglende tilgang, oppdrag borte. Å beholde raden ville låst køen
        // for alt bak den.
        koFjern(rad.nokkel);
        avvist = true;
        visFeil(d.message
          || 'En stempling ble avvist av serveren. Meld status over nødnett.');
        continue;
      }
      // 5xx: serverfeil. Behold raden og prøv igjen senere.
      visUsendt();
      break;
    }
  } finally {
    synkerNaa = false;
    etagMine = null;      // tving ferskt svar, ellers svarer serveren 304
    await lastMine();
  }
}


async function _stemple(id, overgang, knappId, sted, stedTekst) {
  await withSubmitGuard(knappId, async () => {
    // Skriv lokalt FØRST. Skjermen skal vise trykket med en gang, også uten
    // dekning — en knapp som ser ut til å ha virket, men ikke har det, er
    // verre enn en som feiler synlig.
    koLeggTil(id, overgang, sted, stedTekst);
    renderAlt();
    await synk();
  });
}

async function stempleNeste(id) {
  // `mineOppdrag` er allerede projisert med køen, så `neste_overgang` peker
  // videre i kjeden også når forrige trykk ligger usendt.
  const o = mineOppdrag.find((x) => x.id === id);
  if (!o || !o.neste_overgang) return;
  if (_grovMangler(o, o.neste_overgang)) return;
  if (o.neste_overgang === 'avreist') {
    // «Avreist» spør hvor. Knappen åpner valget i stedet for å stemple;
    // stempelet settes av `stempleAvreistTil` med stedet.
    velgerStedFor = id;
    renderAlt();
    return;
  }
  await _stemple(id, o.neste_overgang, `stemple-neste-${id}`);
}

async function stempleAvreistTil(sted) {
  const id = velgerStedFor;
  if (id == null) return;
  if (!AVREIST_TIL.some((s) => s[0] === sted)) return;
  if (sted === 'annet') {
    // «Annet sted» spør hvor (19. sep. 2026): feltet åpnes, stempelet
    // settes av `stempleAnnetSted` med teksten.
    velgerAnnetSted = true;
    renderAlt();
    return;
  }
  velgerStedFor = null;
  await _stemple(id, 'avreist', `stemple-sted-${sted}`, sted);
}

async function stempleAnnetSted() {
  const id = velgerStedFor;
  if (id == null) return;
  const felt = document.getElementById('stemple-sted-tekst');
  const tekst = (felt && felt.value ? felt.value : '').trim().slice(0, 120);
  velgerStedFor = null;
  velgerAnnetSted = false;
  await _stemple(id, 'avreist', 'stemple-sted-annet-ok', 'annet', tekst);
}

function avbrytStedvalg() {
  velgerStedFor = null;
  velgerAnnetSted = false;
  renderAlt();
}

async function settGrovsortering(verdi) {
  // Bilens Rød/Gul/Grønn på det påbegynte oppdraget. Ikke i køen: det er
  // en vurdering som kan endres, ikke et stempel i en kjede — og uten
  // dekning sier skjermen fra i stedet for å late som.
  const o = mineOppdrag.find((x) => x.status !== 'venter' && x.status !== 'ledig');
  if (!o || !GROVSORTERING.some((g) => g[0] === verdi)) return;
  await withSubmitGuard(`grov-${verdi}`, async () => {
    let res;
    try {
      res = await apiFetch(`/oppdrag/api/oppdrag/${o.id}/grovsortering/${encodeURIComponent(verdi)}/`,
                           { method: 'POST' });
    } catch (e) {
      visFeil('Ingen kontakt — grovsorteringen ble ikke lagret. Prøv igjen når dekningen er tilbake.');
      return;
    }
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      visFeil(d.message || 'Kunne ikke lagre grovsorteringen.');
      return;
    }
    etagMine = null;
    await lastMine();
  });
}

async function settAntall(verdi) {
  // Som grovsorteringen: ikke i køen, og uten dekning sier skjermen fra.
  const n = Number(verdi);
  const o = mineOppdrag.find((x) => x.status !== 'venter' && x.status !== 'ledig');
  if (!o || !Number.isInteger(n) || n < 1) return;
  await withSubmitGuard(n > (o.antall == null ? 1 : o.antall) ? 'antall-opp' : 'antall-ned', async () => {
    let res;
    try {
      res = await apiFetch(`/oppdrag/api/oppdrag/${o.id}/antall/${n}/`, { method: 'POST' });
    } catch (e) {
      visFeil('Ingen kontakt — antallet ble ikke lagret. Prøv igjen når dekningen er tilbake.');
      return;
    }
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      visFeil(d.message || 'Kunne ikke lagre antallet.');
      return;
    }
    etagMine = null;
    await lastMine();
  });
}

async function stempleAlternativ(id) {
  // Den andre knappen: «Behandlet på sted» i Fremme.
  const o = mineOppdrag.find((x) => x.id === id);
  if (!o || !o.alternativ_overgang) return;
  if (_grovMangler(o, o.alternativ_overgang)) return;
  await _stemple(id, o.alternativ_overgang, `stemple-alt-${id}`);
}

async function stempleAvbryt(id) {
  // «Avbryt» spør først — den sender oppdraget tilbake til sentralen, og et
  // feiltrykk i en bil i fart skal ikke gjøre det. Ingen grovsortering: hun
  // er ikke ferdig med pasienten, hun gir oppdraget fra seg.
  const o = mineOppdrag.find((x) => x.id === id);
  if (!o || !o.kan_avbryte) return;
  if (!confirm('Avbryte oppdraget? Enheten meldes ledig, og oppdraget går tilbake til sentralen som ventende.')) {
    return;
  }
  await _stemple(id, 'avbryt', `stemple-avbryt-${id}`);
}


// ── Lasting ─────────────────────────────────────────────

// **Gult i ett minutt** (André, 19. sep. 2026: «hver tekst som er nytt i
// enhetens oppdrag må vises med gul markert tekst. Og det skal vare i 1
// minutt»). Regnet fra *delingen*, ikke fra når linja ble skrevet: det er
// delingen som er nytt for bilen. Regelen står for seg fordi den avgjør et
// merke, og fordi klokka må kunne oppgis i en test.
const NY_DELT_MS = 60 * 1000;

function erNyDelt(deltAt, naa) {
  const t = Date.parse(deltAt || '');
  if (isNaN(t)) return false;
  return (naa === undefined ? Date.now() : naa) - t < NY_DELT_MS;
}

function delteLinjerBlokk(o, naa) {
  const linjer = (o.hendelse_id && Array.isArray(o.delte_linjer)) ? o.delte_linjer : [];
  if (!linjer.length) return '';
  const rader = linjer.map((t) => '<div class="b-tillegg' + (erNyDelt(t.delt_at, naa) ? ' ny' : '') + '">'
    + escapeHtml(t.tekst) + '<span class="hvem">' + escapeHtml(t.av || '') + ' · ' + escapeHtml(klokke(t.tid)) + '</span></div>').join('');
  return '<div class="oppdrag-beskrivelse mb-1"><div class="oppdrag-meta"><i class="bi bi-card-text me-1"></i>Fra loggen i '
    + '<span class="hendelse-merke">' + escapeHtml(hendelsesnr(o.hendelse_nummer)) + '</span></div>' + rader + '</div>';
}

// Det gule skal slukke av seg selv, også når serveren svarer 304 og
// `lastMine` ikke tegner: tegn på nytt så lenge noe er nytt.
function harNyDelt(liste, naa) {
  return liste.some((o) => (o.delte_linjer || []).some((t) => erNyDelt(t.delt_at, naa)));
}

async function lastMine() {
  let res;
  try {
    res = await apiFetch('/oppdrag/api/oppdrag/', {
      headers: etagMine ? { 'If-None-Match': etagMine } : {},
    });
  } catch (e) {
    return;   // nettbrudd midt i en poll — forrige visning står til neste
  }
  if (res.status === 304) {
    if (harNyDelt(mineOppdrag)) renderAlt();
    return;
  }
  if (!res.ok) return;
  etagMine = res.headers.get('ETag');
  // Serverens svar er sannheten, men det som ligger usendt legges oppå —
  // ellers ville neste poll visket ut et trykk mannskapet nettopp gjorde.
  mineOppdrag = projiser((await res.json()).data || [], koLes());
  // Nytt oppdrag i lista piper én gang (12. sep. 2026), om admin ikke har
  // slått det av. Ventevarselet tar over fra første terskel.
  const nye = nyeOppdrag(mineOppdrag.filter((o) => o.status === 'venter'));
  if (nye.length && bilinnstillinger().nytt_oppdrag !== false && lydSkalSpille()) pipNytt();
  renderAlt();
}


async function pollOgSynk() {
  // Pollingen er også en synk-utløser: ligger noe usendt, er dette det
  // hyppigste tidspunktet vi vet at nettet kan ha kommet tilbake.
  if (koLes().length) {
    await synk();
    return;             // synk() laster selv til slutt
  }
  await lastMine();
}


document.addEventListener('DOMContentLoaded', async () => {
  await lastMine();
  visUsendt();

  // Lydvarselet er alltid på; selve lyden må vekkes av et trykk, og det
  // første trykket hvor som helst på siden er det trykket.
  _lydHintTegn();
  const vekk = async () => { if (await _lydKlar()) { _lydHintTegn(); document.removeEventListener('pointerdown', vekk); } };
  document.addEventListener('pointerdown', vekk);
  setInterval(() => lydTikk(), 5000);
  setInterval(lastBilinnstillinger, 5 * 60 * 1000);

  // Køen kan ha overlevd at fanen ble lukket midt i en vakt.
  if (koLes().length) await synk();

  // Tettere kadens enn sentralbordets 30 s: et nytt oppdrag skal dukke opp i
  // bilen uten at noen står og venter på det. ETag gjør at et poll uten
  // endring koster en 304 uten kropp. Ingen varsling utover lista — beskjeden
  // går uansett over nødnett (§7).
  setInterval(pollOgSynk, 15000);

  // Den raskeste utløseren vi har: nettleseren sier fra selv når dekningen
  // er tilbake, i stedet for at køen venter på neste poll.
  globalThis.addEventListener('online', () => { synk(); });
});
