// ════════════════════════════════════════════════════════════════════════════
// Backlog — endringsønsker og bugs. Lastes kun av /backlog/.
//
// Krever portal-utils.js (apiFetch, escapeHtml, klokke, withSubmitGuard).
// Alt som *kjører* på toppnivå står nederst, som i de delte modulene.
// ════════════════════════════════════════════════════════════════════════════

let backlogRader = [];
let backlogRedigerer = null;   // id under retting, eller null for nytt

// **Gatene leser MODUL_TILGANG, ikke rollen** (CLAUDE.md). Egne funksjoner og
// ikke `if`-er spredt i byggerne, fordi de avgjør hvilke knapper som finnes —
// og en knapp som fører til 403 er verre enn ingen knapp.
const NIVAA_RANG = {les: 0, les_alle: 1, skriv_handling: 2, skriv_full: 3, skriv_leder: 4};

function backlogNivaaMinst(nivaa) {
  const tilgang = (window.MODUL_TILGANG || {});
  if (tilgang.admin) return true;
  const har = NIVAA_RANG[tilgang.backlog];
  const kreves = NIVAA_RANG[nivaa];
  if (har === undefined || kreves === undefined) return false;
  return har >= kreves;
}

// Skrevet over flere linjer med vilje: `extract_function()` i
// `patients/js_test_utils.py` leser fra signaturen til første `}` i kolonne 0,
// så en ettlinjes funksjon svelger den neste når den klippes ut til en
// node-test.
function backlogKanMeldeInn() {
  return backlogNivaaMinst('skriv_full');
}

function backlogKanLose() {
  return backlogNivaaMinst('skriv_leder');
}

// ── Tegning ─────────────────────────────────────────────────────────────────

function backlogModulnavn(slug) {
  if (!slug) return '';
  const m = (window.BACKLOG_MODULER || []).find(x => x.slug === slug);
  return m ? m.navn : slug;
}

// **Dato OG klokkeslett.** `klokke()` i portal-utils gir bare «14:32», som er
// riktig for en vakt der alt skjedde i dag — og direkte misvisende her, der et
// innspill kan være tre uker gammelt. En liste som sier «14:32» om noe fra
// forrige måned lyver med et tall som ser presist ut.
//
// **Formatert for hånd, ikke med `toLocaleDateString`.** `{day: '2-digit',
// month: '2-digit'}` gir «17.09» i noen ICU-versjoner og «17.9.» i andre —
// node ga det siste. Et format som skifter med nettleseren er et format man
// ikke kan skrive en test på, og kolonnen skal stå rett i en liste.
function backlogTidspunkt(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const p = n => String(n).padStart(2, '0');
  return p(d.getDate()) + '.' + p(d.getMonth() + 1)
    + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

function backlogTypemerke(rad) {
  const klasse = rad.type === 'bug' ? 'text-bg-danger' : 'text-bg-info';
  return '<span class="badge ' + klasse + '">' + escapeHtml(rad.type_navn) + '</span>';
}

function backlogKort(rad) {
  const modul = backlogModulnavn(rad.modul_slug);
  const modulMerke = modul
    ? ' <span class="badge text-bg-secondary">' + escapeHtml(modul) + '</span>'
    : '';
  const lostMerke = rad.lost
    ? ' <span class="badge text-bg-success">Løst</span>'
    : '';

  // Knappene bygges her og ikke gates av gateKnapper(): kortene tegnes på nytt
  // ved hvert filterbytte, og `.d-none` satt én gang ved sidelasting ville vært
  // borte (CLAUDE.md, «markup som tegnes på nytt»).
  let knapper = '';
  if (backlogKanLose()) {
    knapper += rad.lost
      ? '<button type="button" class="btn btn-sm btn-outline-secondary"'
        + ' data-action="backlogGjenapne" data-id="' + rad.id + '">Gjenåpne</button>'
      : '<button type="button" class="btn btn-sm btn-outline-success"'
        + ' data-action="backlogSettLost" data-id="' + rad.id + '">Sett løst</button>';
  }
  if (rad.kan_endres) {
    knapper += ' <button type="button" class="btn btn-sm btn-outline-primary"'
      + ' data-action="backlogApneRediger" data-id="' + rad.id + '">Rett</button>'
      + ' <button type="button" class="btn btn-sm btn-outline-danger"'
      + ' data-action="backlogSlett" data-id="' + rad.id + '">Slett</button>';
  }

  const beskrivelse = rad.beskrivelse
    ? '<div class="small mt-2" style="white-space:pre-wrap">'
      + escapeHtml(rad.beskrivelse) + '</div>'
    : '';

  const lostAv = rad.lost && rad.lost_av
    ? ' · løst av ' + escapeHtml(rad.lost_av)
    : '';

  return '<div class="card mb-2"><div class="card-body py-2">'
    + '<div class="d-flex justify-content-between align-items-start gap-2 flex-wrap">'
    + '<div><div>' + backlogTypemerke(rad) + modulMerke + lostMerke
    + ' <strong>' + escapeHtml(rad.tittel) + '</strong></div>'
    + '<div class="small text-muted">'
    + escapeHtml(rad.opprettet_av || 'ukjent') + ' · ' + backlogTidspunkt(rad.opprettet_at)
    + lostAv + '</div>'
    + beskrivelse + '</div>'
    + '<div class="text-nowrap">' + knapper + '</div>'
    + '</div></div></div>';
}

function backlogTegn(rader) {
  const boks = document.getElementById('backlog-liste');
  if (!boks) return;
  if (!rader || rader.length === 0) {
    // Ikke en tom flate uten forklaring — den leses som at noe er i stykker.
    boks.innerHTML = '<p class="text-muted">Ingen innspill med dette filteret.</p>';
    return;
  }
  boks.innerHTML = rader.map(backlogKort).join('');
}

function backlogTellertekst(vist, filtrert) {
  // **Filteret skal aldri skjule noe stille.** Teksten står i bildet hele
  // tiden, også når ingenting er filtrert bort, slik at den ikke er et signal
  // man lærer seg å overse.
  if (!filtrert) return vist + (vist === 1 ? ' innspill' : ' innspill');
  return 'Viser ' + vist + (vist === 1 ? ' innspill' : ' innspill') + ' — filtrert';
}

// ── Henting ─────────────────────────────────────────────────────────────────

function backlogFilterverdier() {
  const les = id => (document.getElementById(id) || {}).value || '';
  return {type: les('backlog-filter-type'), lost: les('backlog-filter-lost'),
          modul: les('backlog-filter-modul')};
}

function backlogSporring(f) {
  const p = new URLSearchParams();
  if (f.type) p.set('type', f.type);
  if (f.lost !== '') p.set('lost', f.lost);
  if (f.modul) p.set('modul', f.modul);
  const s = p.toString();
  return '/backlog/api/innspill/' + (s ? '?' + s : '');
}

async function backlogLast() {
  const f = backlogFilterverdier();
  const teller = document.getElementById('backlog-teller');
  try {
    const res = await apiFetch(backlogSporring(f));
    const svar = await res.json();
    if (svar.status !== 'ok') throw new Error(svar.message || 'Feil');
    backlogRader = svar.data;
    backlogTegn(backlogRader);
    const filtrert = Boolean(f.type || f.lost !== '' || f.modul);
    if (teller) teller.textContent = backlogTellertekst(svar.antall, filtrert);
  } catch (e) {
    if (teller) teller.textContent = 'Fikk ikke kontakt.';
  }
}

function backlogFilterEndret() { backlogLast(); }

// ── Skriving ────────────────────────────────────────────────────────────────

function backlogFeil(melding) {
  const boks = document.getElementById('backlog-modal-feil');
  if (!boks) return;
  boks.textContent = melding || '';
  boks.classList.toggle('d-none', !melding);
}

function backlogApneNy() {
  backlogRedigerer = null;
  document.getElementById('backlog-modal-tittel').textContent = 'Meld inn';
  document.getElementById('backlog-felt-tittel').value = '';
  document.getElementById('backlog-felt-beskrivelse').value = '';
  document.getElementById('backlog-felt-modul').value = '';
  const typefelt = document.getElementById('backlog-felt-type');
  if (typefelt.options.length) typefelt.selectedIndex = 0;
  backlogFeil('');
  bootstrap.Modal.getOrCreateInstance(document.getElementById('backlog-modal')).show();
}

function backlogApneRediger(id) {
  const rad = backlogRader.find(r => r.id === id);
  if (!rad) return;
  backlogRedigerer = id;
  document.getElementById('backlog-modal-tittel').textContent = 'Rett innspill';
  document.getElementById('backlog-felt-tittel').value = rad.tittel;
  document.getElementById('backlog-felt-beskrivelse').value = rad.beskrivelse;
  document.getElementById('backlog-felt-modul').value = rad.modul_slug || '';
  document.getElementById('backlog-felt-type').value = rad.type;
  backlogFeil('');
  bootstrap.Modal.getOrCreateInstance(document.getElementById('backlog-modal')).show();
}

async function backlogLagre() {
  const kropp = {
    type: document.getElementById('backlog-felt-type').value,
    tittel: document.getElementById('backlog-felt-tittel').value,
    beskrivelse: document.getElementById('backlog-felt-beskrivelse').value,
    modul_slug: document.getElementById('backlog-felt-modul').value,
  };
  const ny = backlogRedigerer === null;
  await withSubmitGuard('backlog-lagre-knapp', async () => {
    const res = await apiFetch(
      ny ? '/backlog/api/innspill/' : '/backlog/api/innspill/' + backlogRedigerer + '/',
      {method: ny ? 'POST' : 'PUT', body: JSON.stringify(kropp)});
    const svar = await res.json();
    if (svar.status !== 'ok') { backlogFeil(svar.message || 'Kunne ikke lagre'); return; }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('backlog-modal')).hide();
    backlogLast();
  });
}

async function _backlogPost(sti) {
  const res = await apiFetch(sti, {method: 'POST'});
  const svar = await res.json();
  if (svar.status === 'ok') backlogLast();
}

function backlogSettLost(id) { _backlogPost('/backlog/api/innspill/' + id + '/lost/'); }
function backlogGjenapne(id) { _backlogPost('/backlog/api/innspill/' + id + '/gjenapne/'); }

async function backlogSlett(id) {
  if (!confirm('Slette innspillet? Det kan ikke angres.')) return;
  const res = await apiFetch('/backlog/api/innspill/' + id + '/', {method: 'DELETE'});
  const svar = await res.json();
  if (svar.status === 'ok') backlogLast();
}

// ── Oppstart ────────────────────────────────────────────────────────────────

function backlogFyllNedtrekk() {
  const typer = window.BACKLOG_TYPER || [];
  const moduler = window.BACKLOG_MODULER || [];
  const filterType = document.getElementById('backlog-filter-type');
  const feltType = document.getElementById('backlog-felt-type');
  typer.forEach(t => {
    filterType.insertAdjacentHTML('beforeend',
      '<option value="' + escapeHtml(t.verdi) + '">' + escapeHtml(t.navn) + '</option>');
    feltType.insertAdjacentHTML('beforeend',
      '<option value="' + escapeHtml(t.verdi) + '">' + escapeHtml(t.navn) + '</option>');
  });
  const filterModul = document.getElementById('backlog-filter-modul');
  const feltModul = document.getElementById('backlog-felt-modul');
  moduler.forEach(m => {
    const o = '<option value="' + escapeHtml(m.slug) + '">' + escapeHtml(m.navn) + '</option>';
    filterModul.insertAdjacentHTML('beforeend', o);
    feltModul.insertAdjacentHTML('beforeend', o);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  backlogFyllNedtrekk();
  const knapp = document.getElementById('backlog-ny-knapp');
  if (knapp && backlogKanMeldeInn()) knapp.classList.remove('d-none');
  backlogLast();
});
