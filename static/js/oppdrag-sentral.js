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

const STATUS_REKKEFOLGE = ['venter', 'rykker_ut', 'fremme', 'avreist', 'leverer', 'ledig'];


function hastegradKlasse(h) {
  return 'hastegrad-' + (h || '').toLowerCase();
}


function klokke(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit' });
}


// ── Enhetsliste ─────────────────────────────────────────

function renderEnheter() {
  const el = document.getElementById('enhetsliste');
  if (!el) return;

  // Tavla svarer på ett spørsmål: hvem kan sendes nå. Enheter som ikke er på
  // vakt hører ikke hjemme her — men de forsvinner ikke i stillhet. Antallet
  // står på Enheter-knappen og under lista, og hele oversikten ligger bak
  // knappen. En bil som forsvinner uten spor er en bil ingen husker å sette
  // inn igjen, og da mangler den neste vakt uten at noen vet hvorfor.
  const paVakt = enheter.filter((e) => e.pa_vakt);
  const antallAv = enheter.length - paVakt.length;

  if (!paVakt.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter på vakt.</div>';
  } else {
    el.innerHTML = (paVakt.map((e) => {
      // «Ledig (2 venter)» er distinksjonen 113 trenger: enheten har fått
      // oppdrag, men ikke rykket ut, og kan fortsatt sendes.
      const meta = e.antall_ventende
        ? `${e.status_navn} · ${e.antall_ventende} venter`
        : String(e.status_navn);
      return `
      <div class="enhet-kort">
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <div class="flex-grow-1">
          <div class="enhet-navn">${escapeHtml(e.navn)}</div>
          <div class="enhet-meta">${escapeHtml(meta)}</div>
        </div>
      </div>`;
    }).join(''));
  }

  const notis = document.getElementById('av-vakt-notis');
  if (notis) {
    notis.textContent = antallAv
      ? `${antallAv} ${antallAv === 1 ? 'enhet' : 'enheter'} ikke på vakt`
      : '';
    notis.hidden = !antallAv;
  }
  const teller = document.getElementById('av-vakt-teller');
  if (teller) teller.textContent = antallAv ? ` (${antallAv} av vakt)` : '';
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


// ── Oppdragsliste ───────────────────────────────────────

function renderOppdrag() {
  const el = document.getElementById('oppdragsliste');
  if (!el) return;

  if (!oppdragsliste.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen oppdrag i vakta ennå.</div>');
    return;
  }

  const sortert = [...oppdragsliste].sort((a, b) => {
    const ai = STATUS_REKKEFOLGE.indexOf(a.status);
    const bi = STATUS_REKKEFOLGE.indexOf(b.status);
    if (ai !== bi) return ai - bi;
    return new Date(b.opprettet) - new Date(a.opprettet);
  });

  el.innerHTML = (sortert.map((o) => {
    // Fragmentene bygges før mal-strengen, ikke inne i en ${...}. En nøstet
    // mal-streng inne i en interpolasjon er vanskelig å lese — og XSS-vernet
    // i tests_xss.py klarer ikke å se inn i den, så en uescapet verdi der
    // ville passert stille.
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    return `
    <div class="oppdrag-rad" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
        <span class="ms-auto d-flex align-items-center gap-1">
          <span class="status-prikk status-${escHtmlValue(o.status)}"></span>
          <span class="oppdrag-meta">${escapeHtml(o.status_navn)}</span>
        </span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(o.enhet_navn)} · ${escapeHtml(o.lokasjon_navn)} · ${escapeHtml(klokke(o.opprettet))}
      </div>
      ${fritekstBlokk}
    </div>`;
  }).join(''));
}


// ── Detaljvisning ───────────────────────────────────────

function tidslinjeHtml(data) {
  // Unionen av statusmeldinger og enhetsbytter. De to er skilt i databasen
  // fordi et bytte ikke er en status og statistikken måler statusene; å slå
  // dem sammen her er en visningsjobb.
  const rader = [];

  const erstattet = new Set(
    (data.historikk || []).filter((m) => m.korrigerer).map((m) => m.korrigerer));

  (data.historikk || []).forEach((m) => {
    // Markøren for et avledet tidspunkt sitter på KLOKKESLETTET, ikke på
    // statusordet: det er tidspunktet som er utledet, ikke at oppdraget ble
    // ledig. Ingen badge — den ville konkurrert med statusen.
    const tidKlasse = m.automatisk ? 'tidslinje-tid tid-avledet' : 'tidslinje-tid';
    const tittel = m.automatisk
      ? ' title="Avsluttet automatisk da enheten startet neste oppdrag"'
      : '';
    const notat = [];
    if (m.automatisk) notat.push('avsluttet automatisk');
    if (m.forsinket) notat.push('meldt forsinket');
    if (m.korrigerer) notat.push('rettet av sentralen');
    const klasse = erstattet.has(m.id) ? 'tidslinje-rad tidslinje-erstattet' : 'tidslinje-rad';
    const notatBlokk = notat.length
      ? `<span class="tidslinje-notat">· ${escapeHtml(notat.join(', '))}</span>`
      : '';
    rader.push({
      tid: m.tidspunkt,
      html: `
        <div class="${klasse}">
          <span class="${tidKlasse}"${tittel}>${escapeHtml(klokke(m.tidspunkt))}</span>
          <span>${escapeHtml(m.status_navn)}</span>
          ${notatBlokk}
        </div>`,
    });
  });

  (data.enhetsbytter || []).forEach((b) => {
    rader.push({
      tid: b.tidspunkt,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(b.tidspunkt))}</span>
          <span>Flyttet ${escapeHtml(b.fra_enhet)} → ${escapeHtml(b.til_enhet)}</span>
          <span class="tidslinje-notat">· ${escapeHtml(b.byttet_av)}</span>
        </div>`,
    });
  });

  rader.sort((a, b) => new Date(a.tid) - new Date(b.tid));
  if (!rader.length) return '<div class="tom-melding">Ingen hendelser ennå.</div>';
  return rader.map((r) => r.html).join('');
}


async function visOppdrag(id) {
  const modalEl = document.getElementById('oppdragDetaljModal');
  const innhold = document.getElementById('detalj-innhold');
  innhold.innerHTML = ('<div class="tom-melding">Laster…</div>');
  new bootstrap.Modal(modalEl).show();

  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/`);
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    innhold.innerHTML = (
      `<div class="text-danger">${escapeHtml(d.message || 'Kunne ikke hente oppdraget.')}</div>`);
    return;
  }

  const o = d.data;
  document.getElementById('detalj-tittel').textContent =
    `${o.problemstilling} – ${o.enhet_navn}`;

  const flyttValg = OPPDRAG_TILGANG.kanSkrive
    ? `
      <hr>
      <label class="form-label" for="flytt-enhet">Flytt til enhet</label>
      <div class="input-group">
        <select id="flytt-enhet" class="form-select">
          ${enheter.map((e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('')}
        </select>
        <button class="btn btn-outline-primary" type="button"
                data-action="flyttOppdrag" data-id="${escHtmlValue(o.id)}">Flytt</button>
      </div>
      <div id="flytt-feil" class="text-danger small mt-2 d-none"></div>`
    : '';

  innhold.innerHTML = (`
    <div class="oppdrag-meta mb-2">
      <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
      <span class="ms-2">${escapeHtml(o.lokasjon_navn)}</span>
      <span class="ms-2">${escapeHtml(o.status_navn)}</span>
    </div>
    ${o.fritekst ? `<div class="oppdrag-fritekst mb-3">${escapeHtml(o.fritekst)}</div>` : ''}
    <h6 class="text-muted">Tidslinje</h6>
    ${tidslinjeHtml(o)}
    ${flyttValg}`);
}


async function flyttOppdrag(id) {
  const valg = document.getElementById('flytt-enhet');
  const feil = document.getElementById('flytt-feil');
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/flytt/`, {
    method: 'POST',
    body: JSON.stringify({ enhet_id: Number(valg.value) }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    feil.textContent = d.message || 'Kunne ikke flytte oppdraget.';
    feil.classList.remove('d-none');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  await lastAlt();
}


// ── Oppretting ──────────────────────────────────────────

async function opprettOppdrag() {
  const feil = document.getElementById('nytt-feil');
  feil.classList.add('d-none');

  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    method: 'POST',
    body: JSON.stringify({
      enhet_id: Number(document.getElementById('nytt-enhet').value),
      lokasjon_id: Number(document.getElementById('nytt-lokasjon').value),
      problemstilling: document.getElementById('nytt-problemstilling').value,
      hastegrad: document.getElementById('nytt-hastegrad').value,
      fritekst: document.getElementById('nytt-fritekst').value,
    }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    feil.textContent = d.message || 'Kunne ikke opprette oppdraget.';
    feil.classList.remove('d-none');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('nyttOppdragModal'))?.hide();
  document.getElementById('nytt-fritekst').value = '';
  await lastAlt();
}


// ── Lokasjonsadmin ──────────────────────────────────────

function renderLokasjonsadmin() {
  const el = document.getElementById('lokasjonsliste');
  if (!el) return;
  if (!lokasjoner.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen lokasjoner ennå.</div>');
    return;
  }
  el.innerHTML = (lokasjoner.map((l) => {
    const knapp = l.er_aktiv
      ? `<button class="btn btn-sm btn-outline-secondary" data-action="deaktiverLokasjon" data-id="${escHtmlValue(l.id)}">Deaktiver</button>`
      : `<button class="btn btn-sm btn-outline-success" data-action="aktiverLokasjon" data-id="${escHtmlValue(l.id)}">Aktiver</button>`;
    const dempet = l.er_aktiv ? '' : ' text-muted';
    return `
    <div class="d-flex align-items-center gap-2 py-1">
      <span class="flex-grow-1${dempet}">${escapeHtml(l.navn)}</span>
      ${knapp}
    </div>`;
  }).join(''));
}


async function lastLokasjonsadmin() {
  await lastLokasjoner();
  renderLokasjonsadmin();
}


async function leggTilLokasjon() {
  const felt = document.getElementById('ny-lokasjon');
  const navn = (felt.value || '').trim();
  if (!navn) return;
  const res = await apiFetch('/oppdrag/api/lokasjoner/', {
    method: 'POST',
    body: JSON.stringify({ navn }),
  });
  if (res.ok) {
    felt.value = '';
    await lastLokasjonsadmin();
  }
}


async function _settLokasjonAktiv(id, aktiv) {
  await apiFetch(`/oppdrag/api/lokasjoner/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ er_aktiv: aktiv }),
  });
  await lastLokasjonsadmin();
}

async function deaktiverLokasjon(id) { await _settLokasjonAktiv(id, false); }
async function aktiverLokasjon(id) { await _settLokasjonAktiv(id, true); }


// ── Enhetsadmin ─────────────────────────────────────────

function renderEnhetsadmin() {
  const el = document.getElementById('enhetsadminliste');
  if (!el) return;
  if (!enhetsadmin.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter ennå.</div>';
    return;
  }

  // Kontokoblingen vises, men redigeres ikke. Nye biler får kobling ved
  // oppretting av kontoen, så nedtrekket her var en tredje vei til noe som
  // allerede er gjort — og den veien inviterte til å tro at koblingen er
  // tilgangen. Mangler koblingen, er det en ekte feiltilstand, og da (og kun
  // da) tilbys en reparasjon.
  el.innerHTML = (enhetsadmin.map((e) => {
    const vaktKlasse = e.pa_vakt ? 'btn-outline-secondary' : 'btn-outline-success';
    const vaktHandling = e.pa_vakt ? 'taAvVakt' : 'settPaaVakt';
    const vaktTekst = e.pa_vakt ? 'Av vakt' : 'På vakt';
    const vaktKnapp = e.er_aktiv
      ? `<button class="btn btn-sm ${vaktKlasse}" data-action="${vaktHandling}" data-id="${escHtmlValue(e.id)}">${vaktTekst}</button>`
      : '';

    const adminKnapp = OPPDRAG_TILGANG.erAdmin
      ? (e.er_aktiv
        ? `<button class="btn btn-sm btn-outline-danger" data-action="pensjonerEnhet" data-id="${escHtmlValue(e.id)}">Pensjoner</button>`
        : `<button class="btn btn-sm btn-outline-success" data-action="gjenopprettEnhet" data-id="${escHtmlValue(e.id)}">Gjenopprett</button>`)
      : '';

    const koblingTekst = e.username
      ? `Logger inn som ${e.username}`
      : 'Ingen konto knyttet';
    const koblingKlasse = e.username ? 'enhet-meta' : 'enhet-meta text-danger';

    const status = e.er_aktiv
      ? (e.pa_vakt ? 'På vakt' : 'Ikke på vakt')
      : 'Pensjonert';
    const radKlasse = e.er_aktiv && e.pa_vakt
      ? 'enhet-kort' : 'enhet-kort enhet-av-vakt';

    return `
    <div class="${radKlasse} mb-2">
      <div class="flex-grow-1">
        <div class="enhet-navn">${escapeHtml(e.navn)} <span class="enhet-meta">· ${escapeHtml(status)}</span></div>
        <div class="${koblingKlasse}">${escapeHtml(koblingTekst)}</div>
      </div>
      ${vaktKnapp}
      ${adminKnapp}
    </div>`;
  }).join(''));
}


async function _settAktiv(id, aktiv) {
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ er_aktiv: aktiv }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke endre enheten.');
    return;
  }
  etagEnheter = null;
  await lastEnhetsadmin();
  await lastAlt();
}

async function pensjonerEnhet(id) { await _settAktiv(id, false); }
async function gjenopprettEnhet(id) { await _settAktiv(id, true); }


async function lastEnhetsadmin() {
  // `?alle=1` tar med pensjonerte enheter. Ressursoversikten på tavla skal
  // ikke se dem; denne lista er stedet man gjenoppretter dem fra.
  const res = await apiFetch('/oppdrag/api/enheter/?alle=1');
  if (res.ok) enhetsadmin = (await res.json()).data || [];
  renderEnhetsadmin();
}


async function leggTilEnhet() {
  const felt = document.getElementById('ny-enhet');
  const navn = (felt.value || '').trim();
  if (!navn) return;
  const res = await apiFetch('/oppdrag/api/enheter/ny/', {
    method: 'POST',
    body: JSON.stringify({ navn }),
  });
  if (res.ok) {
    felt.value = '';
    await lastEnhetsadmin();
    await lastAlt();
  }
}


// ── Lasting ─────────────────────────────────────────────

async function lastEnheter() {
  const res = await apiFetch('/oppdrag/api/enheter/', {
    headers: etagEnheter ? { 'If-None-Match': etagEnheter } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagEnheter = res.headers.get('ETag');
  enheter = (await res.json()).data || [];
  return true;
}


async function lastOppdrag() {
  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    headers: etagOppdrag ? { 'If-None-Match': etagOppdrag } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagOppdrag = res.headers.get('ETag');
  oppdragsliste = (await res.json()).data || [];
  return true;
}


async function lastLokasjoner() {
  const res = await apiFetch('/oppdrag/api/lokasjoner/');
  if (!res.ok) return;
  lokasjoner = (await res.json()).data || [];
}


function fyllNedtrekk() {
  const enhetsvalg = document.getElementById('nytt-enhet');
  if (enhetsvalg) {
    enhetsvalg.innerHTML = (enheter.filter((e) => e.pa_vakt).map(
      (e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join(''));
  }
  const lokvalg = document.getElementById('nytt-lokasjon');
  if (lokvalg) {
    const aktive = lokasjoner.filter((l) => l.er_aktiv);
    lokvalg.innerHTML = (aktive.map(
      (l) => `<option value="${escHtmlValue(l.id)}">${escapeHtml(l.navn)}</option>`).join(''));
  }
}


function visManglendeOppsett() {
  // Et skjema som lar deg trykke «Opprett» og så feiler med «Ukjent enhet» er
  // verre enn et som sier fra på forhånd hva som mangler.
  const boks = document.getElementById('mangler-oppsett');
  if (!boks) return;
  const mangler = [];
  if (!enheter.filter((e) => e.pa_vakt).length) mangler.push('ingen enheter på vakt');
  if (!lokasjoner.filter((l) => l.er_aktiv).length) mangler.push('ingen aktive lokasjoner');

  const knapp = document.querySelector('[data-bs-target="#nyttOppdragModal"]');
  if (mangler.length) {
    document.getElementById('mangler-hva').textContent = ' Portalen har ' + mangler.join(' og ') + '.';
    boks.classList.remove('d-none');
    if (knapp) knapp.disabled = true;
  } else {
    boks.classList.add('d-none');
    if (knapp) knapp.disabled = false;
  }
}


async function lastAlt() {
  const [nyeEnheter, nyeOppdrag] = await Promise.all([lastEnheter(), lastOppdrag()]);
  if (nyeEnheter) renderEnheter();
  if (nyeOppdrag) renderOppdrag();
  if (nyeEnheter) fyllNedtrekk();
  visManglendeOppsett();
}


document.addEventListener('DOMContentLoaded', async () => {
  await lastLokasjoner();
  await lastAlt();
  renderEnheter();
  renderOppdrag();
  fyllNedtrekk();
  visManglendeOppsett();
  // Samme kadens som pasientlista. ETag gjør at et poll uten endring koster
  // en 304 uten kropp.
  setInterval(lastAlt, 30000);
});
