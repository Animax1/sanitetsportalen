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

const HASTEGRAD_REKKEFOLGE = ['Akutt', 'Haster', 'Vanlig'];


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


function koLeggTil(oppdragId, overgang) {
    // Klienttiden fryses her, ved trykket — ikke ved sendingen. Uten det
    // ville statistikken vist når dekningen kom tilbake i stedet for når
    // mannskapet faktisk meldte.
    const rad = {
        nokkel: lagNokkel(),
        oppdragId,
        overgang,
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
        const nesteEtter = kjede[siste.overgang] || null;
        return {
            ...o,
            status: siste.overgang,
            status_navn: navn[siste.overgang] || siste.overgang,
            neste_overgang: nesteEtter,
            neste_navn: nesteEtter ? (navn[nesteEtter] || nesteEtter) : null,
            usendt: true,
        };
    });
}


function hastegradKlasse(h) {
  return 'hastegrad-' + (h || '').toLowerCase();
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


function visUsendt() {
  // Egen, roligere tone enn `visFeil`: dette er ikke en feil, det er en
  // stempling som venter på dekning. Men den MÅ synes — §6: en knapp som ser
  // ut til å ha virket, men ikke har det, er verre enn en som feiler synlig.
  const antall = koLes().length;
  const el = document.getElementById('enhet-usendt');
  if (!el) return;
  if (!antall) {
    el.classList.add('d-none');
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

function tidslinjeEnhetHtml(o) {
  return (o.statusmeldinger || []).map((m) => {
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
    const notatBlokk = notat.length
      ? `<span class="tidslinje-notat">· ${escapeHtml(notat.join(', '))}</span>`
      : '';
    return `
      <div class="tidslinje-rad">
        <span class="${tidKlasse}"${tittel}>${escapeHtml(klokke(m.tidspunkt))}</span>
        <span>${escapeHtml(m.status_navn)}</span>
        ${notatBlokk}
      </div>`;
  }).join('');
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
    const nesteKnapp = o.neste_overgang
      ? `<button type="button" class="btn btn-primary stor-knapp flex-grow-1"
                 id="stemple-neste-${escHtmlValue(o.id)}"
                 data-action="stempleNeste" data-id="${escHtmlValue(o.id)}">
           ${escapeHtml(o.neste_navn)}</button>`
      : '';
    const ledigKnapp = `
      <button type="button" class="btn btn-outline-light stor-knapp"
              id="stemple-ledig-${escHtmlValue(o.id)}"
              data-action="stempleLedig" data-id="${escHtmlValue(o.id)}">
        Ledig</button>`;
    return `
    <div class="aktivt-kort">
      <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
        <span class="ms-auto oppdrag-status-naa">${escapeHtml(o.status_navn)}</span>
      </div>
      <div class="oppdrag-meta mb-1">${escapeHtml(o.lokasjon_navn)}</div>
      ${fritekstBlokk}
      <div class="mt-2">${tidslinjeEnhetHtml(o)}</div>
      <div class="d-flex gap-2 mt-3">
        ${nesteKnapp}
        ${ledigKnapp}
      </div>
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
    const startKnapp = `
      <button type="button" class="btn btn-primary stor-knapp w-100 mt-2"
              id="stemple-neste-${escHtmlValue(o.id)}"
              data-action="stempleNeste" data-id="${escHtmlValue(o.id)}">
        ${escapeHtml(o.neste_navn)}</button>`;
    return `
    <div class="oppdrag-rad">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
      </div>
      <div class="oppdrag-meta mt-1">${escapeHtml(o.lokasjon_navn)} · ${escapeHtml(klokke(o.opprettet))}</div>
      ${fritekstBlokk}
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
        <span class="oppdrag-meta">${escapeHtml(o.problemstilling)}</span>
        <span class="ms-auto">
          <span class="${tidKlasse}"${tittel}>Ledig ${escapeHtml(tid)}</span>
          ${notatBlokk}
        </span>
      </div>
    </div>`;
  }).join('');
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
    while (true) {
      const ko = koLes();
      if (!ko.length) { skjulFeil(); break; }

      const rad = ko[0];
      let res;
      try {
        res = await apiFetch(
          `/oppdrag/api/oppdrag/${rad.oppdragId}/status/${rad.overgang}/`, {
            method: 'POST',
            body: JSON.stringify({
              klienttid: rad.klienttid,
              idempotency_key: rad.nokkel,
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


async function _stemple(id, overgang, knappId) {
  await withSubmitGuard(knappId, async () => {
    // Skriv lokalt FØRST. Skjermen skal vise trykket med en gang, også uten
    // dekning — en knapp som ser ut til å ha virket, men ikke har det, er
    // verre enn en som feiler synlig.
    koLeggTil(id, overgang);
    renderAlt();
    await synk();
  });
}

async function stempleNeste(id) {
  // `mineOppdrag` er allerede projisert med køen, så `neste_overgang` peker
  // videre i kjeden også når forrige trykk ligger usendt.
  const o = mineOppdrag.find((x) => x.id === id);
  if (!o || !o.neste_overgang) return;
  await _stemple(id, o.neste_overgang, `stemple-neste-${id}`);
}

async function stempleLedig(id) {
  await _stemple(id, 'ledig', `stemple-ledig-${id}`);
}


// ── Lasting ─────────────────────────────────────────────

async function lastMine() {
  let res;
  try {
    res = await apiFetch('/oppdrag/api/oppdrag/', {
      headers: etagMine ? { 'If-None-Match': etagMine } : {},
    });
  } catch (e) {
    return;   // nettbrudd midt i en poll — forrige visning står til neste
  }
  if (res.status === 304) return;
  if (!res.ok) return;
  etagMine = res.headers.get('ETag');
  // Serverens svar er sannheten, men det som ligger usendt legges oppå —
  // ellers ville neste poll visket ut et trykk mannskapet nettopp gjorde.
  mineOppdrag = projiser((await res.json()).data || [], koLes());
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
