// ════════════════════════════════════════════════════════
// VAKTLISTE — planleggingssiden (fase 2)
//
// Lastes kun av /vaktliste/. Bruker primitivene i portal-utils.js
// (apiFetch, withSubmitGuard, escapeHtml, escHtmlValue, klokke) —
// patients-utils.js finnes ikke på denne siden og kan ikke lastes: den
// gjør arbeid på toppnivå som kaster uten pasientskjemaene.
//
// Alt som settes med innerHTML escapes. Navn på mannskap, ressurser og
// korps er data fra basen, og ressursnavn er fritekst satt av admin.
//
// Fanene bygges av ressursene — de er data, ikke kode, og tilpasser seg
// vaktas art av seg selv. To faste faner i tillegg: «Oversikt», som er den
// man skriver ut, og «Ikke plassert», som er de som er meldt på uten å stå
// noe sted ennå.
// ════════════════════════════════════════════════════════

let vaktlister = [];        // alle listene, til velgeren
let aktivListe = null;      // { vaktliste, ressurser, vaktposter, korps, roller, mannskap, enheter }
let aktivFane = 'oversikt'; // 'oversikt' | 'ikke-plassert' | ressurs-id som streng

const OVERSIKT = 'oversikt';
const IKKE_PLASSERT = 'ikke-plassert';


// ── Henting ──────────────────────────────────────────────────────────────

async function lastVaktlister() {
  const res = await apiFetch('/vaktliste/api/vaktlister/');
  if (!res.ok) return;
  vaktlister = (await res.json()).data || [];
  fyllVelger();

  document.getElementById('vl-tom')?.classList.toggle('d-none', vaktlister.length > 0);
  if (vaktlister.length) {
    await lastListe(vaktlister[0].id);
  } else {
    aktivListe = null;
    tegn();
  }
}


async function lastListe(id) {
  const res = await apiFetch(`/vaktliste/api/vaktlister/${id}/`);
  if (!res.ok) return;
  aktivListe = (await res.json()).data;
  const velger = document.getElementById('vaktliste-velger');
  if (velger) velger.value = String(id);

  document.getElementById('vl-mangler-mannskap')
    ?.classList.toggle('d-none', (aktivListe.mannskap || []).length > 0);

  fyllNedtrekk();
  tegn();
}


function byttVaktliste() {
  const velger = document.getElementById('vaktliste-velger');
  if (!velger || !velger.value) return;
  aktivFane = OVERSIKT;
  lastListe(Number(velger.value));
}


// ── Nedtrekk ─────────────────────────────────────────────────────────────

function _fyll(id, rader, tomtValg) {
  const el = document.getElementById(id);
  if (!el) return;
  const deler = tomtValg ? [`<option value="">${escapeHtml(tomtValg)}</option>`] : [];
  rader.forEach((r) => {
    deler.push(`<option value="${escHtmlValue(r.id)}">${escapeHtml(r.navn)}</option>`);
  });
  el.innerHTML = deler.join('');
}


function fyllVelger() {
  const el = document.getElementById('vaktliste-velger');
  if (!el) return;
  el.innerHTML = vaktlister.map((vl) => {
    // Statusen står i valget selv: velgeren er ofte det eneste stedet man
    // ser flere lister samtidig.
    const merke = vl.i_drift ? ' — i drift' : '';
    return `<option value="${escHtmlValue(vl.id)}">${escapeHtml(vl.vakt_navn + merke)}</option>`;
  }).join('');

  _fyll('ny-vakt-kopier',
        vaktlister.map((vl) => ({ id: vl.id, navn: vl.vakt_navn })),
        'Ikke kopier — tom liste');
}


function fyllNedtrekk() {
  if (!aktivListe) return;
  _fyll('ny-ressurs-korps', aktivListe.korps, 'Ureservert (bemannes av vaktleder)');
  _fyll('ny-ressurs-enhet', aktivListe.enheter, 'Ingen kobling');
  _fyll('ny-vaktpost-rolle', aktivListe.roller, 'Uten rolle');
  _fyll('ny-vaktpost-mannskap', aktivListe.mannskap.map((m) => ({
    id: m.id, navn: `${m.navn} — ${m.korps_navn}`,
  })), '');
}


// ── Tegning ──────────────────────────────────────────────────────────────

function tegn() {
  tegnStatus();
  tegnFaner();
  tegnPanel();
}


function tegnStatus() {
  const el = document.getElementById('vaktliste-status');
  if (!el) return;
  if (!aktivListe) { el.textContent = ''; el.className = 'vl-status'; return; }
  const vl = aktivListe.vaktliste;
  el.textContent = vl.status_navn;
  el.className = 'vl-status' + (vl.i_drift ? ' vl-drift' : '');
}


function _posterFor(ressursId) {
  return (aktivListe.vaktposter || []).filter((vp) => vp.ressurs_id === ressursId);
}


function tegnFaner() {
  const el = document.getElementById('vl-faner');
  if (!el) return;
  if (!aktivListe) { el.innerHTML = ''; return; }

  const faner = [{ id: OVERSIKT, navn: 'Oversikt', ikon: 'list-ul', antall: null }];
  aktivListe.ressurser.forEach((r) => {
    faner.push({
      id: String(r.id), navn: r.navn, ikon: r.ikon,
      antall: _posterFor(r.id).length,
    });
  });
  faner.push({
    id: IKKE_PLASSERT, navn: 'Ikke plassert', ikon: 'person-dash',
    antall: _ikkePlassert().length,
  });

  el.innerHTML = faner.map((f) => {
    const aktiv = f.id === aktivFane ? ' active' : '';
    const antall = f.antall === null ? ''
      : `<span class="vl-antall">${escHtmlValue(f.antall)}</span>`;
    return `<button class="vl-fane${aktiv}" data-action="visFane" data-arg="${escHtmlValue(f.id)}">`
         + `<i class="bi bi-${escHtmlValue(f.ikon)} me-1"></i>${escapeHtml(f.navn)}${antall}</button>`;
  }).join('');
}


function visFane(id) {
  aktivFane = id;
  tegnFaner();
  tegnPanel();
}


function _ikkePlassert() {
  // Mannskap som ikke står på noen ressurs i denne lista. Fanen finnes for
  // at ingen skal bli glemt — en person som er meldt på og ikke satt opp er
  // usynlig ellers.
  const satt = new Set((aktivListe.vaktposter || []).map((vp) => vp.mannskap_id));
  return (aktivListe.mannskap || []).filter((m) => !satt.has(m.id));
}


function tegnPanel() {
  const el = document.getElementById('vl-panel');
  if (!el) return;
  if (!aktivListe) { el.innerHTML = ''; return; }

  if (aktivFane === OVERSIKT) { el.innerHTML = mkOversikt(); return; }
  if (aktivFane === IKKE_PLASSERT) { el.innerHTML = mkIkkePlassert(); return; }

  const ressurs = aktivListe.ressurser.find((r) => String(r.id) === String(aktivFane));
  el.innerHTML = ressurs ? mkRessurs(ressurs)
    : '<div class="vl-tom">Ressursen finnes ikke lenger.</div>';
}


// ── Byggere (alt escapes — se filhodet) ──────────────────────────────────

function _tidsspenn(vp) {
  return `${klokke(vp.fra_tid)}–${klokke(vp.til_tid)}`;
}


function mkRessurs(r) {
  const poster = _posterFor(r.id);
  const korpsmerke = r.korps_navn
    ? `<span class="vl-merkelapp vl-korps">${escapeHtml(r.korps_navn)}</span>`
    : '<span class="vl-merkelapp vl-ureservert">Ureservert</span>';
  const enhetsmerke = r.enhet_navn
    ? `<span class="vl-merkelapp">Enhet: ${escapeHtml(r.enhet_navn)}</span>` : '';

  const rader = poster.length ? poster.map((vp) => `
    <div class="vl-rad">
      <div>
        <span class="vl-navn">${escapeHtml(vp.navn)}</span>
        <span class="vl-meta">· ${escapeHtml(vp.korps_kort)}${vp.rolle ? ' · ' + escapeHtml(vp.rolle) : ''}</span>
      </div>
      <div class="d-flex align-items-center gap-2">
        <span class="vl-meta">${escapeHtml(_tidsspenn(vp))}</span>
        <button class="btn btn-sm btn-outline-danger" type="button"
                data-action="fjernVaktpost" data-id="${escHtmlValue(vp.id)}">Fjern</button>
      </div>
    </div>`).join('')
    : '<div class="vl-tom">Ingen satt opp ennå.</div>';

  return `
    <div class="vl-kort">
      <div class="vl-kort-topp">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="vl-kort-tittel">
            <i class="bi bi-${escHtmlValue(r.ikon)} me-1"></i>${escapeHtml(r.navn)}
          </span>
          <span class="vl-merkelapp">${escapeHtml(r.type_navn)}</span>
          ${korpsmerke}
          ${enhetsmerke}
        </div>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-primary" type="button"
                  data-action="apneVaktpost" data-id="${escHtmlValue(r.id)}">
            <i class="bi bi-person-plus me-1"></i>Sett på vakt
          </button>
          <button class="btn btn-sm btn-outline-danger" type="button"
                  data-action="fjernRessurs" data-id="${escHtmlValue(r.id)}">Fjern ressurs</button>
        </div>
      </div>
      ${rader}
    </div>`;
}


function mkOversikt() {
  // Gruppert på korps — det er slik lista leses og henges opp.
  const poster = aktivListe.vaktposter || [];
  if (!poster.length) {
    return '<div class="vl-kort"><div class="vl-tom">Ingen er satt opp ennå.</div></div>';
  }

  const ressursnavn = {};
  aktivListe.ressurser.forEach((r) => { ressursnavn[r.id] = r.navn; });

  const grupper = {};
  poster.forEach((vp) => {
    (grupper[vp.korps_navn] = grupper[vp.korps_navn] || []).push(vp);
  });

  const deler = Object.keys(grupper).sort().map((korps) => {
    const rader = grupper[korps]
      .slice()
      .sort((a, b) => a.fra_tid.localeCompare(b.fra_tid) || a.navn.localeCompare(b.navn))
      .map((vp) => `
        <div class="vl-rad">
          <div>
            <span class="vl-navn">${escapeHtml(vp.navn)}</span>
            <span class="vl-meta">· ${escapeHtml(ressursnavn[vp.ressurs_id] || '—')}${vp.rolle ? ' · ' + escapeHtml(vp.rolle) : ''}</span>
          </div>
          <span class="vl-meta">${escapeHtml(_tidsspenn(vp))}</span>
        </div>`).join('');
    return `<div class="vl-korpsgruppe"><h3>${escapeHtml(korps)} `
         + `(${escHtmlValue(grupper[korps].length)})</h3>${rader}</div>`;
  });

  return `<div class="vl-kort">${deler.join('')}</div>`;
}


function mkIkkePlassert() {
  const folk = _ikkePlassert();
  if (!folk.length) {
    return '<div class="vl-kort"><div class="vl-tom">Alle i registeret står på lista.</div></div>';
  }
  const rader = folk.map((m) => `
    <div class="vl-rad">
      <span class="vl-navn">${escapeHtml(m.navn)}</span>
      <span class="vl-meta">${escapeHtml(m.korps_navn)}</span>
    </div>`).join('');
  return `<div class="vl-kort">
      <div class="vl-kort-topp"><span class="vl-kort-tittel">Ikke plassert</span></div>
      ${rader}
    </div>`;
}


// ── Handlinger ───────────────────────────────────────────────────────────

function _visFeil(id, melding) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


function _skjulFeil(id) {
  document.getElementById(id)?.classList.add('d-none');
}


function _lukkModal(id) {
  bootstrap.Modal.getInstance(document.getElementById(id))?.hide();
}


// datetime-local gir «2026-10-03T08:00» uten sone. Serveren gjør den aware
// i lokal sone — det er den tiden brukeren faktisk mente.
function _tidFraFelt(id) {
  const el = document.getElementById(id);
  return el && el.value ? el.value : null;
}


async function opprettVaktliste() {
  _skjulFeil('ny-vakt-feil');
  await withSubmitGuard('ny-vakt-knapp', async () => {
    const navn = (document.getElementById('ny-vakt-navn')?.value || '').trim();
    if (!navn) { _visFeil('ny-vakt-feil', 'Vakta må ha et navn.'); return; }

    const res = await apiFetch('/vaktliste/api/vaktlister/', {
      method: 'POST',
      body: JSON.stringify({
        navn,
        startet: _tidFraFelt('ny-vakt-start'),
        kopier_fra: document.getElementById('ny-vakt-kopier')?.value || null,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-vakt-feil', d.message || 'Kunne ikke opprette vaktlista.');
      return;
    }
    _lukkModal('nyVaktlisteModal');
    document.getElementById('ny-vakt-navn').value = '';
    await lastVaktlister();
    await lastListe(d.data.id);
  });
}


async function opprettRessurs() {
  if (!aktivListe) return;
  _skjulFeil('ny-ressurs-feil');
  await withSubmitGuard('ny-ressurs-knapp', async () => {
    const navn = (document.getElementById('ny-ressurs-navn')?.value || '').trim();
    if (!navn) { _visFeil('ny-ressurs-feil', 'Ressursen må ha et navn.'); return; }

    const res = await apiFetch(
      `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/ressurser/`, {
        method: 'POST',
        body: JSON.stringify({
          navn,
          type: document.getElementById('ny-ressurs-type')?.value,
          korps_id: document.getElementById('ny-ressurs-korps')?.value || null,
          enhet_id: document.getElementById('ny-ressurs-enhet')?.value || null,
        }),
      });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-ressurs-feil', d.message || 'Kunne ikke legge til ressursen.');
      return;
    }
    _lukkModal('nyRessursModal');
    document.getElementById('ny-ressurs-navn').value = '';
    aktivFane = String(d.data.id);   // åpne den nye med én gang
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function fjernRessurs(id) {
  const ressurs = aktivListe?.ressurser.find((r) => r.id === id);
  const antall = _posterFor(id).length;
  const advarsel = antall
    ? `\n\n${antall} oppsatt(e) person(er) fjernes fra lista sammen med den.` : '';
  if (!confirm(`Fjerne «${ressurs ? ressurs.navn : 'ressursen'}»?${advarsel}`)) return;

  const res = await apiFetch(`/vaktliste/api/ressurser/${id}/`, { method: 'DELETE' });
  if (!res.ok) return;
  aktivFane = OVERSIKT;
  await lastListe(aktivListe.vaktliste.id);
}


function apneVaktpost(ressursId) {
  const ressurs = aktivListe?.ressurser.find((r) => r.id === ressursId);
  if (!ressurs) return;
  _skjulFeil('ny-vaktpost-feil');
  document.getElementById('ny-vaktpost-tittel').textContent =
    `Sett på vakt — ${ressurs.navn}`;
  document.getElementById('nyVaktpostModal').dataset.ressurs = String(ressursId);
  new bootstrap.Modal(document.getElementById('nyVaktpostModal')).show();
}


async function opprettVaktpost() {
  const modal = document.getElementById('nyVaktpostModal');
  const ressursId = modal?.dataset.ressurs;
  if (!ressursId) return;

  _skjulFeil('ny-vaktpost-feil');
  await withSubmitGuard('ny-vaktpost-knapp', async () => {
    const fra = _tidFraFelt('ny-vaktpost-fra');
    const til = _tidFraFelt('ny-vaktpost-til');
    if (!fra || !til) {
      _visFeil('ny-vaktpost-feil', 'Skiftet må ha både fra- og til-tidspunkt.');
      return;
    }

    const res = await apiFetch(`/vaktliste/api/ressurser/${ressursId}/vaktposter/`, {
      method: 'POST',
      body: JSON.stringify({
        mannskap_id: document.getElementById('ny-vaktpost-mannskap')?.value,
        rolle_id: document.getElementById('ny-vaktpost-rolle')?.value || null,
        fra_tid: fra,
        til_tid: til,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-vaktpost-feil', d.message || 'Kunne ikke sette personen på vakt.');
      return;
    }
    _lukkModal('nyVaktpostModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function fjernVaktpost(id) {
  const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, { method: 'DELETE' });
  if (!res.ok) return;
  await lastListe(aktivListe.vaktliste.id);
}


document.addEventListener('DOMContentLoaded', () => {
  lastVaktlister();
});
