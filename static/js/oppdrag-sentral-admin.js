// ════════════════════════════════════════════════════════
// oppdrag-sentral-admin.js
// ════════════════════════════════════════════════════════
//
// Historikk, oppretting, verdimengdene og enhetsadmin.
//
// Delt ut av `oppdrag-sentral.js` 14. sep. 2026 (gjeldspunkt 3.6).
// Fila var 1 991 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/oppdrag/sentral.html` og deler ett globalt navnerom som
// før. `JsSplittenErKompletTests` håndhever at ingen funksjon forsvant
// eller ble duplisert.
// ════════════════════════════════════════════════════════

// ── Historikk (ferdigstilte oppdrag) ────────────────────
// Rydding av tavla, ikke vaktarkivet: radene er urørt, og «Hent tilbake»
// angrer. Ordet «arkiv» er reservert core.arkiv, som fryser hele vakter —
// se kommentaren i oppdrag/services.py.

let historikkliste = [];


function renderHistorikk() {
  const el = document.getElementById('historikkliste');
  if (!el) return;
  if (!historikkliste.length) {
    el.innerHTML = '<div class="tom-melding">Ingen ferdigstilte oppdrag.</div>';
    return;
  }
  el.innerHTML = (historikkliste.map((o) => {
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    // Alle bilene, ikke bare den primære — historikken viste én til
    // 12. sep. 2026.
    const enhetsnavn = (o.enheter || []).map((e) => e.enhet_navn).join(', ') || o.enhet_navn;
    // Sletting i historikken er global admin. Knappen er sin egen rad-
    // handling: klikk på resten av raden åpner oppdraget.
    const slett = OPPDRAG_TILGANG.erAdmin
      ? `<button type="button" class="btn btn-sm btn-outline-danger mt-2"
                 data-action="slettOppdrag" data-id="${escHtmlValue(o.id)}">Slett</button>`
      : '';
    return `
    <div class="oppdrag-rad" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">#${escHtmlValue(o.nummer)}</span>
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(enhetsnavn)} · ${escapeHtml(o.lokasjon_navn)} · ferdig ${escapeHtml(klokke(o.historikk_fra))}
      </div>
      ${fritekstBlokk}
      ${slett}
    </div>`;
  }).join(''));
}


async function lastHistorikk() {
  const felt = document.getElementById('historikk-sok');
  const sok = felt ? (felt.value || '').trim() : '';
  const url = sok
    ? `/oppdrag/api/historikk/?sok=${encodeURIComponent(sok)}`
    : '/oppdrag/api/historikk/';
  const res = await apiFetch(url);
  if (!res.ok) return;
  historikkliste = (await res.json()).data || [];
  renderHistorikk();
}


async function flyttTilHistorikk(id) {
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/historikk/`, { method: 'POST' });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke legge oppdraget i historikken.');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  etagOppdrag = null;   // raden forsvinner fra den aktive lista
  await lastAlt();
  if (document.getElementById('historikkliste')) await lastHistorikk();
}


async function hentTilbakeOppdrag(id) {
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/historikk/`, { method: 'DELETE' });
  if (!res.ok) return;
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  etagOppdrag = null;
  await lastAlt();
  if (document.getElementById('historikkliste')) await lastHistorikk();
}


// ── Oppretting ──────────────────────────────────────────

async function opprettOppdrag() {
  const feil = document.getElementById('nytt-feil');
  feil.classList.add('d-none');

  const enhetIder = _valgteEnheter();
  if (!enhetIder.length) {
    feil.textContent = 'Kryss av minst én enhet.';
    feil.classList.remove('d-none');
    return;
  }

  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    method: 'POST',
    body: JSON.stringify({
      enhet_ider: enhetIder,
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
  document.querySelectorAll('input[name="nytt-enhet"]:checked').forEach((i) => { i.checked = false; });
  await lastAlt();
}


function nullstillNyttOppdrag() {
  // Ved hver åpning (André, 12. sep. 2026: «husker den avhukede enheter fra
  // forrige opprettelse», og senere «nedtrekksfeltene … må starte øverst på
  // hver»). Uavhengig av hvilken vei forrige forsøk gikk.
  document.querySelectorAll('input[name="nytt-enhet"]').forEach((i) => { i.checked = false; });
  document.getElementById('nytt-feil')?.classList.add('d-none');
  ['nytt-hastegrad', 'nytt-lokasjon', 'nytt-problemstilling'].forEach((id) => {
    const sel = document.getElementById(id);
    if (sel && sel.options.length) sel.selectedIndex = 0;
  });
  ['nytt-fritekst'].forEach((id) => {
    const felt = document.getElementById(id);
    if (felt) felt.value = '';
  });
  // Problemstillingene følger hastegraden som står valgt — den første nå.
  hastegradEndret('nytt');
}


function _valgteEnheter() {
  // I avkryssingsrekkefølge = listas rekkefølge; den første blir primær.
  return Array.from(document.querySelectorAll('input[name="nytt-enhet"]:checked'))
    .map((i) => Number(i.value));
}


function mkEnhetsvalg() {
  // Avkryssing, ikke nedtrekk: operatøren sender gjerne to biler på samme
  // hendelse. Bare enhetene på vakt — gruppert på type, ambulansene først
  // (André, 12. sep. 2026).
  const grupper = _grupperEnheter(enheter.filter((e) => e.pa_vakt));
  return grupper.map((g) => {
    const hode = grupper.length > 1
      ? `<div class="enhet-gruppe">${escapeHtml(g.navn)}</div>` : '';
    return hode + g.enheter.map((e) => `
    <label class="form-check nytt-enhet-valg">
      <input class="form-check-input" type="checkbox" name="nytt-enhet" value="${escHtmlValue(e.id)}">
      <span class="form-check-label">${escapeHtml(e.navn)}</span>
    </label>`).join('');
  }).join('');
}


// ── Verdimengdene: lokasjoner, enhetstyper, problemstillinger ────────────
//
// Tre tabeller, ett vindu med tre faner (André, 12. sep. 2026: «Admin må
// kunne redigere listen over problemstillinger blant annet hvor de skal stå i
// rekkefølgen i nedtrekksvinduet. Samme gjelder med rekkefølge på lokasjoner
// og grupperinger.»). Serveren svarer likt for alle tre (`views_verdier`), så
// klienten har én bygger og én sett handlinger med tabellen i argumentet.
// Rekkefølgen sendes som hele lista etter et flytt, ikke som «opp» per rad.

const VERDIMENGDER = {
  lokasjoner: { tittel: 'Lokasjoner', ny: 'Ny lokasjon' },
  enhetstyper: { tittel: 'Enhetstyper', ny: 'Ny enhetstype' },
  problemstillinger: { tittel: 'Problemstillinger', ny: 'Ny problemstilling' },
  // Ikke en liste, men et skjema (12. sep. 2026): lydvarsel og krav i bilen.
  bilinnstillinger: { tittel: 'Bilen', ny: '' },
};
const PROBLEM_KATEGORIER = [
  ['medisinsk', 'Medisinsk'], ['drift', 'Drift'], ['begge', 'Begge'],
];
let verdiFane = 'lokasjoner';
let verdier = { lokasjoner: [], enhetstyper: [], problemstillinger: [], bilinnstillinger: null };


function _verdiArg(arg) {
  // «slug:id[:hva]» — klikkdelegeringen sender ett argument.
  const [slug, id, hva] = String(arg).split(':');
  return { slug, id: Number(id), hva, rad: (verdier[slug] || []).find((r) => r.id === Number(id)) };
}


function _byggProblemkart(rader) {
  // Speiler `Problemstilling.passer()` på serveren: begge → alle
  // hastegrader, drift → Drift, medisinsk → resten. Udefinert først.
  // Bygges her, ikke hentet, så nedtrekket følger med idet noen endrer lista.
  const aktive = rader.filter((r) => r.er_aktiv);
  const passer = (r, h) => r.kategori === 'begge' || (r.kategori === 'drift') === (h === 'Drift');
  const kart = {};
  HASTEGRAD_REKKEFOLGE.forEach((h) => {
    kart[h] = aktive.filter((r) => passer(r, h)).map((r) => r.navn);
  });
  return { kart, medAntall: aktive.filter((r) => r.med_antall).map((r) => r.navn) };
}


async function lastVerdier(slug) {
  const res = await apiFetch(`/oppdrag/api/${slug}/`);
  if (!res.ok) return false;
  verdier[slug] = (await res.json()).data || [];
  if (slug === 'bilinnstillinger') {
    if (globalThis.window && verdier.bilinnstillinger?.terskler) {
      globalThis.window.OPPDRAG_LYDVARSEL = verdier.bilinnstillinger.terskler;
    }
    return true;
  }
  // Det som ellers på siden leser tabellen, følger med.
  if (slug === 'lokasjoner') {
    lokasjoner = verdier[slug];
    fyllNedtrekk();
  } else if (slug === 'enhetstyper') {
    if (globalThis.window) {
      globalThis.window.OPPDRAG_ENHETSTYPER = verdier[slug]
        .filter((t) => t.er_aktiv).map((t) => [t.id, t.navn]);
    }
    renderEnheter();
    fyllNedtrekk();
    renderEnhetsadmin();
  } else if (slug === 'problemstillinger') {
    const { kart, medAntall } = _byggProblemkart(verdier[slug]);
    if (globalThis.window) {
      globalThis.window.OPPDRAG_PROBLEMSTILLINGER_FOR = kart;
      globalThis.window.OPPDRAG_MED_ANTALL = medAntall;
    }
    hastegradEndret('nytt');
  }
  return true;
}


async function lastLokasjoner() {
  await lastVerdier('lokasjoner');
}


async function lastVerdiadmin() {
  // Bilinnstillingene hentes bare for admin — fanen finnes ikke for andre.
  const slugs = Object.keys(VERDIMENGDER).filter(
    (slug) => slug !== 'bilinnstillinger' || globalThis.window?.OPPDRAG_TILGANG?.erAdmin);
  await Promise.all(slugs.map((slug) => lastVerdier(slug)));
  renderVerdiadmin();
}


function _lydvarselSkjema(d) {
  // Én rad per hastegrad: første varsel og gjentakelse, i sekunder. Og
  // bryteren for pip ved nytt oppdrag. Lagres samlet med «Lagre».
  const rader = HASTEGRAD_REKKEFOLGE.map((h) => {
    const [forste, gjenta] = (d.terskler || {})[h] || [900, 60];
    const paa = (d.aktive || {})[h] !== false;
    return `
      <tr>
        <td><input type="checkbox" class="form-check-input me-1" id="lyd-aktiv-${escHtmlValue(h)}"${paa ? ' checked' : ''}
                   aria-label="Lydvarsel på for ${escHtmlValue(h)}"> ${escapeHtml(h)}</td>
        <td><input type="number" class="form-control form-control-sm lyd-felt" min="0" max="86400" step="5"
                   id="lyd-forste-${escHtmlValue(h)}" value="${escHtmlValue(forste)}" aria-label="Første varsel"></td>
        <td><input type="number" class="form-control form-control-sm lyd-felt" min="5" max="86400" step="5"
                   id="lyd-gjenta-${escHtmlValue(h)}" value="${escHtmlValue(gjenta)}" aria-label="Gjenta hvert"></td>
      </tr>`;
  }).join('');
  return `
    <h6 class="mb-2">Lydvarsel</h6>
    <div class="form-check mb-2">
      <input class="form-check-input" type="checkbox" id="lyd-aktiv"${d.lyd_aktiv !== false ? ' checked' : ''}>
      <label class="form-check-label" for="lyd-aktiv">Lydvarsel i bilene er på</label>
    </div>
    <table class="table table-sm mb-2 lyd-tabell">
      <thead><tr><th>På · hastegrad</th><th>Første varsel etter (s)</th><th>Gjenta hvert (s)</th></tr></thead>
      <tbody>${rader}</tbody>
    </table>
    <div class="form-check mb-3">
      <input class="form-check-input" type="checkbox" id="lyd-nytt"${d.nytt_oppdrag ? ' checked' : ''}>
      <label class="form-check-label" for="lyd-nytt">Pip i bilen når den får et nytt oppdrag</label>
    </div>
    <h6 class="mb-2">Grovsortering</h6>
    <p class="form-text mt-0 mb-2">Kreves alltid før «Behandlet på sted» og før Ledig etter Leverer. Ikke på Drift.</p>
    <div class="form-check mb-3">
      <input class="form-check-input" type="checkbox" id="krev-grov-avreist"${d.krev_grov_avreist ? ' checked' : ''}>
      <label class="form-check-label" for="krev-grov-avreist">Krev grovsortering også før Avreist</label>
    </div>
    <button type="button" class="btn btn-sm btn-primary" id="lyd-lagre" data-action="lagreLydvarsel">Lagre</button>
    <span class="form-text ms-2">Gjelder alle biler; bilen henter innstillingene innen fem minutter.</span>`;
}


async function lagreLydvarsel() {
  const terskler = {};
  const aktive = {};
  HASTEGRAD_REKKEFOLGE.forEach((h) => {
    terskler[h] = [Number(document.getElementById(`lyd-forste-${h}`)?.value),
                   Number(document.getElementById(`lyd-gjenta-${h}`)?.value)];
    aktive[h] = !!document.getElementById(`lyd-aktiv-${h}`)?.checked;
  });
  const kropp = {
    terskler,
    aktive,
    nytt_oppdrag: !!document.getElementById('lyd-nytt')?.checked,
    lyd_aktiv: !!document.getElementById('lyd-aktiv')?.checked,
    krev_grov_avreist: !!document.getElementById('krev-grov-avreist')?.checked,
  };
  await withSubmitGuard('lyd-lagre', async () => {
    if (await _verdiKall('/oppdrag/api/bilinnstillinger/',
                         { method: 'PUT', body: JSON.stringify(kropp) },
                         'Kunne ikke lagre bilinnstillingene.')) {
      await lastVerdier('bilinnstillinger');
      renderVerdiadmin();
    }
  });
}


async function velgVerdifane(slug) {
  if (!VERDIMENGDER[slug]) return;
  verdiFane = slug;
  renderVerdiadmin();
}


function _verdirad(slug, r, forste, siste) {
  const arg = (hva) => escHtmlValue(slug + ':' + r.id + ':' + hva);
  const dempet = r.er_aktiv ? '' : ' text-muted';
  const knappAktiv = r.fast ? '' : (r.er_aktiv
    ? `<button class="btn btn-sm btn-outline-secondary" data-action="settVerdiAktiv" data-arg="${arg('0')}">Deaktiver</button>`
    : `<button class="btn btn-sm btn-outline-success" data-action="settVerdiAktiv" data-arg="${arg('1')}">Aktiver</button>`);
  const endre = r.fast ? ''
    : `<button class="btn btn-sm btn-outline-secondary" data-action="endreVerdinavn" data-arg="${arg('navn')}" title="Endre navn"><i class="bi bi-pencil"></i></button>`;
  const slett = (globalThis.window?.OPPDRAG_TILGANG?.erAdmin && !r.fast)
    ? `<button class="btn btn-sm btn-outline-danger" data-action="slettVerdi" data-arg="${arg('slett')}" title="Slett"><i class="bi bi-trash"></i></button>`
    : '';
  // Opp/ned: «Udefinert» er fast øverst, og flyttes ikke — knappene ligger
  // der, men er avslått, så raden ikke hopper i høyde.
  const opp = `<button class="btn btn-sm btn-outline-secondary" data-action="flyttVerdi" data-arg="${arg('opp')}" title="Flytt opp"${(forste || r.fast) ? ' disabled' : ''}><i class="bi bi-chevron-up"></i></button>`;
  const ned = `<button class="btn btn-sm btn-outline-secondary" data-action="flyttVerdi" data-arg="${arg('ned')}" title="Flytt ned"${(siste || r.fast) ? ' disabled' : ''}><i class="bi bi-chevron-down"></i></button>`;
  let ekstra = '';
  if (slug === 'problemstillinger' && !r.fast) {
    const kategorivalg = PROBLEM_KATEGORIER.map(([v, n]) =>
      `<option value="${escHtmlValue(v)}"${v === r.kategori ? ' selected' : ''}>${escapeHtml(n)}</option>`).join('');
    ekstra = `
      <select class="form-select form-select-sm verdi-kategori" aria-label="Kategori"
              data-action="settVerdifelt" data-hendelse="change" data-felt="kategori" data-id="${escHtmlValue(r.id)}">${kategorivalg}</select>
      <select class="form-select form-select-sm verdi-antall" aria-label="Bærer antall"
              data-action="settVerdifelt" data-hendelse="change" data-felt="med_antall" data-id="${escHtmlValue(r.id)}">
        <option value="0"${r.med_antall ? '' : ' selected'}>Uten antall</option>
        <option value="1"${r.med_antall ? ' selected' : ''}>Med antall</option>
      </select>`;
  }
  const iBruk = r.i_bruk ? `<span class="oppdrag-meta">· ${escHtmlValue(r.i_bruk)} i bruk</span>` : '';
  const fast = r.fast ? '<span class="oppdrag-meta">· fast</span>' : '';
  return `
    <div class="d-flex align-items-center gap-2 py-1 verdi-rad">
      <span class="btn-group">${opp}${ned}</span>
      <span class="flex-grow-1${dempet}">${escapeHtml(r.navn)} ${iBruk}${fast}</span>
      ${ekstra}${endre}${knappAktiv}${slett}
    </div>`;
}


function renderVerdiadmin() {
  const el = document.getElementById('verdiliste');
  if (!el) return;
  document.querySelectorAll('[data-verdifane]').forEach((k) => {
    k.classList.toggle('active', k.dataset.verdifane === verdiFane);
  });
  const nyFelt = document.getElementById('ny-verdi');
  if (nyFelt) nyFelt.placeholder = VERDIMENGDER[verdiFane].ny;
  const nyKategori = document.getElementById('ny-verdi-kategori');
  if (nyKategori) nyKategori.classList.toggle('d-none', verdiFane !== 'problemstillinger');
  const nyRad = document.getElementById('ny-verdi-rad');
  if (nyRad) nyRad.classList.toggle('d-none', verdiFane === 'bilinnstillinger');
  if (verdiFane === 'bilinnstillinger') {
    el.innerHTML = _lydvarselSkjema(verdier.bilinnstillinger || {});
    return;
  }
  const rader = verdier[verdiFane] || [];
  if (!rader.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen ennå.</div>');
    return;
  }
  el.innerHTML = (rader.map((r, i) => _verdirad(verdiFane, r, i === 0, i === rader.length - 1)).join(''));
}


async function _verdiKall(url, valg, feilmelding) {
  const res = await apiFetch(url, valg);
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') { alert(d.message || feilmelding); return false; }
  return true;
}


async function leggTilVerdi() {
  const felt = document.getElementById('ny-verdi');
  const navn = (felt?.value || '').trim();
  if (!navn) return;
  const kropp = { navn };
  if (verdiFane === 'problemstillinger') {
    kropp.kategori = document.getElementById('ny-verdi-kategori')?.value || 'medisinsk';
  }
  if (await _verdiKall(`/oppdrag/api/${verdiFane}/`, { method: 'POST', body: JSON.stringify(kropp) },
                       'Kunne ikke legge til.')) {
    felt.value = '';
    await lastVerdier(verdiFane);
    renderVerdiadmin();
  }
}


async function endreVerdinavn(arg) {
  const { slug, id, rad } = _verdiArg(arg);
  if (!rad) return;
  const navn = (prompt('Nytt navn:', rad.navn) || '').trim();
  if (!navn || navn === rad.navn) return;
  if (await _verdiKall(`/oppdrag/api/${slug}/${id}/`, { method: 'PUT', body: JSON.stringify({ navn }) },
                       'Kunne ikke endre navnet.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


async function settVerdiAktiv(arg) {
  const { slug, id, hva } = _verdiArg(arg);
  if (await _verdiKall(`/oppdrag/api/${slug}/${id}/`,
                       { method: 'PUT', body: JSON.stringify({ er_aktiv: hva === '1' }) },
                       'Kunne ikke endre.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


async function settVerdifelt(id, felt, verdi) {
  // Kategori og antall på en problemstilling — nedtrekk i raden, som
  // enhetstypen i enhetspanelet. Bare problemstillinger har slike felt.
  const kropp = felt === 'med_antall' ? { med_antall: verdi === '1' } : { [felt]: verdi };
  if (await _verdiKall(`/oppdrag/api/problemstillinger/${id}/`,
                       { method: 'PUT', body: JSON.stringify(kropp) }, 'Kunne ikke endre.')) {
    await lastVerdier('problemstillinger');
    renderVerdiadmin();
  }
}


async function flyttVerdi(arg) {
  const { slug, id, hva } = _verdiArg(arg);
  const ider = (verdier[slug] || []).map((r) => r.id);
  const i = ider.indexOf(id);
  const j = hva === 'opp' ? i - 1 : i + 1;
  if (i < 0 || j < 0 || j >= ider.length) return;
  [ider[i], ider[j]] = [ider[j], ider[i]];
  if (await _verdiKall(`/oppdrag/api/${slug}/rekkefolge/`,
                       { method: 'PUT', body: JSON.stringify({ ider }) }, 'Kunne ikke flytte.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


async function slettVerdi(arg) {
  const { slug, id, rad } = _verdiArg(arg);
  if (!rad) return;
  if (!confirm(`Slette «${rad.navn}» for godt?`)) return;
  if (await _verdiKall(`/oppdrag/api/${slug}/${id}/`,
                       { method: 'DELETE', body: JSON.stringify({ confirm: true }) }, 'Kunne ikke slette.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


// ── Enhetsadmin ─────────────────────────────────────────

function renderEnhetsadmin() {
  const el = document.getElementById('enhetsadminliste');
  if (!el) return;
  if (!enhetsadmin.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter ennå.</div>';
    return;
  }

  // Kontokoblingen vises, men redigeres ikke: enheten får den ved oppretting
  // av kontoen, og mister den når kontoen slettes. Står det «Ingen konto
  // knyttet», er det en ekte feiltilstand og verdt å se.
  el.innerHTML = (enhetsadmin.map((e) => {
    const vaktKlasse = e.pa_vakt ? 'btn-outline-secondary' : 'btn-outline-success';
    const vaktHandling = e.pa_vakt ? 'taAvVakt' : 'settPaaVakt';
    const vaktTekst = e.pa_vakt ? 'Av vakt' : 'På vakt';
    const vaktKnapp = e.er_aktiv
      ? `<button class="btn btn-sm ${vaktKlasse}" data-action="${vaktHandling}" data-id="${escHtmlValue(e.id)}">${vaktTekst}</button>`
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
    // Typen settes her (12. sep. 2026): kontoskjemaet vet ikke hva bilen er.
    const typer = (globalThis.window?.OPPDRAG_ENHETSTYPER || []).map(([id, navn]) => [String(id), navn]);
    const valgt = e.type == null ? '' : String(e.type);
    // En type som er deaktivert står fortsatt på bilen som har den — nedtrekket
    // må tilby den, ellers velges den bort i stillhet ved neste tegning.
    if (valgt && !typer.some(([id]) => id === valgt)) typer.push([valgt, e.type_navn || 'Inaktiv type']);
    const typevalg = [['', 'Uten type'], ...typer].map(([verdi, navn]) =>
      `<option value="${escHtmlValue(verdi)}"${verdi === valgt ? ' selected' : ''}>${escapeHtml(navn)}</option>`).join('');
    const typeNedtrekk = `<select class="form-select form-select-sm enhet-type" aria-label="Enhetstype"
              data-action="settEnhetstype" data-hendelse="change" data-felt="type" data-id="${escHtmlValue(e.id)}">${typevalg}</select>`;

    return `
    <div class="${radKlasse} mb-2">
      <div class="flex-grow-1">
        <div class="enhet-navn">${escapeHtml(e.navn)} <span class="enhet-meta">· ${escapeHtml(status)}</span></div>
        <div class="${koblingKlasse}">${escapeHtml(koblingTekst)}</div>
      </div>
      ${typeNedtrekk}
      ${vaktKnapp}
    </div>`;
  }).join(''));
}


async function settEnhetstype(id, felt, verdi) {
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/`, {
    method: 'PUT', body: JSON.stringify({ type: verdi ? Number(verdi) : null }),
  });
  if (!res.ok) { alert('Kunne ikke endre enhetstypen.'); return; }
  await lastEnhetsadmin();
  await lastEnheter();
}


async function lastEnhetsadmin() {
  // `?alle=1` tar med pensjonerte enheter. Tavla skal ikke se dem, men lista
  // skal: en pensjonert bil er ikke borte, den venter på at kontoen sin
  // opprettes igjen.
  const res = await apiFetch('/oppdrag/api/enheter/?alle=1');
  if (res.ok) enhetsadmin = (await res.json()).data || [];
  renderEnhetsadmin();
}
