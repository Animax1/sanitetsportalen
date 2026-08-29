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
  const stempel = document.getElementById('enhet-oppdatert');
  if (stempel) stempel.textContent = 'Oppdatert ' + klokke(new Date().toISOString());
}


// ── Stempling ───────────────────────────────────────────

async function _stemple(id, overgang, knappId) {
  await withSubmitGuard(knappId, async () => {
    let res;
    try {
      res = await apiFetch(`/oppdrag/api/oppdrag/${id}/status/${overgang}/`, {
        method: 'POST',
        // Klienttid følger med fra første dag: online er den lik ankomsttid
        // og ufarlig, og offline-køen (fase 5) gjenbruker samme kropp.
        body: JSON.stringify({ klienttid: new Date().toISOString() }),
      });
    } catch (e) {
      visFeil('Ingen kontakt med serveren — meldingen er IKKE lagret. '
        + 'Meld status over nødnett.');
      return;
    }

    if (res.status === 409) {
      // Dobbelttrykk der det første vant, eller en skjerm som har sakket
      // akterut. Ikke en feil verdt et banner — hent ferskt og vis det.
      etagMine = null;
      await lastMine();
      return;
    }

    let d = {};
    try { d = await res.json(); } catch (e) { /* håndteres under */ }
    if (!res.ok || d.status !== 'ok') {
      visFeil(d.message || 'Stemplingen feilet — meld status over nødnett.');
      return;
    }

    skjulFeil();
    etagMine = null;
    await lastMine();
  });
}

async function stempleNeste(id) {
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
  mineOppdrag = (await res.json()).data || [];
  renderAlt();
}


document.addEventListener('DOMContentLoaded', async () => {
  await lastMine();
  // Tettere kadens enn sentralbordets 30 s: et nytt oppdrag skal dukke opp i
  // bilen uten at noen står og venter på det. ETag gjør at et poll uten
  // endring koster en 304 uten kropp. Ingen varsling utover lista — beskjeden
  // går uansett over nødnett (§7).
  setInterval(lastMine, 15000);
});
