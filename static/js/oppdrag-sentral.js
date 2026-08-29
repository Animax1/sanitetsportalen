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
let kontoer = [];

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

  if (!enheter.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen aktive enheter.</div>');
    return;
  }

  // Enheter som ikke er på vakt skjules ikke — de vises i en egen gruppe
  // under. En bil som forsvinner fra tavla er en bil ingen husker å sette
  // inn igjen, og da mangler den neste vakt uten at noen vet hvorfor.
  const paVakt = enheter.filter((e) => e.pa_vakt);
  const av = enheter.filter((e) => !e.pa_vakt);

  const kort = (e) => {
    // «Ledig (2 venter)» er distinksjonen 113 trenger: enheten har fått
    // oppdrag, men ikke rykket ut, og kan fortsatt sendes.
    const meta = e.antall_ventende
      ? `${e.status_navn} · ${e.antall_ventende} venter`
      : String(e.status_navn);
    // Fragmentene bygges før mal-strengen. En nøstet mal-streng inne i en
    // interpolasjon er usynlig for XSS-gjennomgangen i tests_xss.py, så en
    // uescapet verdi der ville passert stille.
    const knappKlasse = e.pa_vakt ? 'btn-outline-secondary' : 'btn-outline-success';
    const knappHandling = e.pa_vakt ? 'taAvVakt' : 'settPaaVakt';
    const knappTekst = e.pa_vakt ? 'Av vakt' : 'På vakt';
    const knapp = (globalThis.OPPDRAG_TILGANG || {}).kanSkrive
      ? `<button class="btn btn-sm ${knappKlasse}" data-action="${knappHandling}" data-id="${escHtmlValue(e.id)}">${knappTekst}</button>`
      : '';
    const kortKlasse = e.pa_vakt ? 'enhet-kort' : 'enhet-kort enhet-av-vakt';
    const prikk = e.pa_vakt ? e.status : 'av_vakt';
    const metatekst = e.pa_vakt ? meta : 'Ikke på vakt';
    return `
      <div class="${kortKlasse}">
        <span class="status-prikk status-${escHtmlValue(prikk)}"></span>
        <div class="flex-grow-1">
          <div class="enhet-navn">${escapeHtml(e.navn)}</div>
          <div class="enhet-meta">${escapeHtml(metatekst)}</div>
        </div>
        ${knapp}
      </div>`;
  };

  const deler = [];
  deler.push(paVakt.length
    ? paVakt.map(kort).join('')
    : '<div class="tom-melding">Ingen enheter på vakt.</div>');
  if (av.length) {
    deler.push(`<div class="enhet-gruppe">Ikke på vakt (${escHtmlValue(av.length)})</div>`);
    deler.push(av.map(kort).join(''));
  }
  el.innerHTML = (deler.join(''));
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
    el.innerHTML = '<div class="tom-melding">Ingen enheter ennå. Legg til én over.</div>';
    return;
  }

  el.innerHTML = (enhetsadmin.map((e) => {
    // Kontoen som allerede er valgt må stå i lista selv om den er «opptatt»
    // — ellers ville et lagre-trykk stille koblet den fra.
    const valg = kontoer
      .filter((k) => !k.opptatt || k.id === e.user_id)
      .map((k) => {
        const merke = k.er_delt_konto ? ' (delt)' : '';
        const valgt = k.id === e.user_id ? ' selected' : '';
        return `<option value="${escHtmlValue(k.id)}"${valgt}>${escapeHtml(k.username + merke)}</option>`;
      }).join('');
    const dempet = e.er_aktiv ? '' : ' text-muted';
    const knapp = e.er_aktiv
      ? `<button class="btn btn-sm btn-outline-secondary" data-action="deaktiverEnhet" data-id="${escHtmlValue(e.id)}">Deaktiver</button>`
      : `<button class="btn btn-sm btn-outline-success" data-action="aktiverEnhet" data-id="${escHtmlValue(e.id)}">Aktiver</button>`;
    return `
    <div class="d-flex align-items-center gap-2 py-2 flex-wrap">
      <span class="flex-grow-1${dempet}">${escapeHtml(e.navn)}</span>
      <select class="form-select form-select-sm" style="max-width:16rem"
              data-enhet-konto="${escHtmlValue(e.id)}">
        <option value="">Ingen konto</option>
        ${valg}
      </select>
      <button class="btn btn-sm btn-outline-primary"
              data-action="lagreEnhetskonto" data-id="${escHtmlValue(e.id)}">Lagre</button>
      ${knapp}
    </div>`;
  }).join(''));
}


async function lastEnhetsadmin() {
  const [enhetSvar, kontoSvar] = await Promise.all([
    apiFetch('/oppdrag/api/enheter/'),
    apiFetch('/oppdrag/api/kontoer/'),
  ]);
  if (enhetSvar.ok) {
    // Admin-lista trenger inaktive enheter også, så den hentes per enhet.
    const grunn = (await enhetSvar.json()).data || [];
    const detaljer = await Promise.all(
      grunn.map((e) => apiFetch(`/oppdrag/api/enheter/${e.id}/`).then((r) => r.json())));
    enhetsadmin = detaljer.filter((d) => d.status === 'ok').map((d) => d.data);
  }
  if (kontoSvar.ok) kontoer = (await kontoSvar.json()).data || [];
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


async function lagreEnhetskonto(id) {
  const valg = document.querySelector(`[data-enhet-konto="${id}"]`);
  if (!valg) return;
  const verdi = valg.value ? Number(valg.value) : null;
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ user_id: verdi }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke lagre koblingen.');
    return;
  }
  await lastEnhetsadmin();
}


async function _settEnhetAktiv(id, aktiv) {
  await apiFetch(`/oppdrag/api/enheter/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ er_aktiv: aktiv }),
  });
  await lastEnhetsadmin();
  await lastAlt();
}

async function deaktiverEnhet(id) { await _settEnhetAktiv(id, false); }
async function aktiverEnhet(id) { await _settEnhetAktiv(id, true); }


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
