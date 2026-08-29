// ════════════════════════════════════════════════════════
// VAKTLISTE — mannskap og registre
//
// Lastes kun av /vaktliste/registre/. Erstatter Django-admin, som er av i
// produksjon (S1). Bruker primitivene i portal-utils.js; patients-utils.js
// finnes ikke på denne siden og kan ikke lastes.
//
// Alt som settes med innerHTML escapes. Navn på personer, korps og
// kompetanser er fritekst fra basen, og notatfeltet er helt fritt.
//
// De tre verdimengdene deler bygger og skjema (mkVerdier / lagreVerdi) på
// samme måte som serveren deler fabrikk — tre kopier ville vært tre steder en
// rettelse kan bli glemt.
// ════════════════════════════════════════════════════════

let data = null;            // { mannskap, korps, kompetanser, roller, kontoer }
let aktivRegisterFane = 'mannskap';
let redigerer = null;       // id-en som redigeres, eller null for «ny»

// Fane → hvordan registeret snakkes om og hvor det ligger.
// `nyEtikett` er hele knappeteksten, ikke bare ordet: «korps» er intetkjønn
// og «kompetanse» hankjønn, så en hardkodet «Ny » foran gir feil artikkel på
// en av dem uansett hvilken man velger.
const REGISTRE = {
  korps: { sti: 'korps', nyEtikett: 'Nytt korps', tittel: 'Korps', kortnavn: true },
  kompetanser: { sti: 'kompetanser', nyEtikett: 'Ny kompetanse', tittel: 'Kompetanser' },
  roller: { sti: 'roller', nyEtikett: 'Ny vaktrolle', tittel: 'Vaktroller' },
};


// ── Henting ──────────────────────────────────────────────────────────────

async function lastRegistre() {
  const res = await apiFetch('/vaktliste/api/mannskap/');
  if (!res.ok) return;
  data = (await res.json()).data;

  document.getElementById('vlr-mangler-korps')
    ?.classList.toggle('d-none', data.korps.length > 0);
  const antall = document.getElementById('vlr-antall');
  if (antall) antall.textContent = String(data.mannskap.length);

  tegnRegister();
}


function visRegisterFane(navn) {
  aktivRegisterFane = navn;
  document.querySelectorAll('#vlr-faner .vl-fane').forEach((b) => {
    b.classList.toggle('active', b.dataset.arg === navn);
  });
  tegnRegister();
}


function tegnRegister() {
  const el = document.getElementById('vlr-panel');
  if (!el || !data) return;
  el.innerHTML = aktivRegisterFane === 'mannskap'
    ? mkMannskap()
    : mkVerdier(aktivRegisterFane);
}


// ── Byggere (alt escapes — se filhodet) ──────────────────────────────────

function mkMannskap() {
  if (!data.mannskap.length) {
    return '<div class="vl-kort"><div class="vl-tom">'
         + 'Ingen i registeret ennå. Trykk «Nytt mannskap».</div></div>';
  }

  // Gruppert på korps — bestillingen ba om personellet «sortert etter hvilket
  // korps de tilhører», og det er også slik lista leses.
  const grupper = {};
  data.mannskap.forEach((m) => {
    (grupper[m.korps_navn] = grupper[m.korps_navn] || []).push(m);
  });

  const deler = Object.keys(grupper).sort().map((korps) => {
    const rader = grupper[korps]
      .slice()
      .sort((a, b) => a.navn.localeCompare(b.navn))
      .map((m) => {
        const merker = m.kompetanser
          .map((k) => `<span class="vl-merkelapp">${escapeHtml(k.navn)}</span>`)
          .join('');
        const inaktiv = m.er_aktiv ? '' : ' vl-inaktiv';
        const inaktivMerke = m.er_aktiv ? ''
          : '<span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
        const konto = m.brukernavn
          ? `<span class="vl-meta"><i class="bi bi-person-check me-1"></i>${escapeHtml(m.brukernavn)}</span>`
          : '';
        const tlf = m.telefon
          ? `<span class="vl-meta">${escapeHtml(m.telefon)}</span>` : '';
        return `
          <div class="vl-rad${inaktiv}">
            <div class="d-flex align-items-center gap-2 flex-wrap">
              <span class="vl-navn">${escapeHtml(m.navn)}</span>
              ${inaktivMerke}${merker}${tlf}${konto}
            </div>
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-outline-secondary" type="button"
                      data-action="apneRedigerPerson" data-id="${escHtmlValue(m.id)}">Rediger</button>
              <button class="btn btn-sm btn-outline-danger" type="button"
                      data-action="slettPerson" data-id="${escHtmlValue(m.id)}">Slett</button>
            </div>
          </div>`;
      }).join('');
    return `<div class="vl-korpsgruppe"><h3>${escapeHtml(korps)} `
         + `(${escHtmlValue(grupper[korps].length)})</h3>${rader}</div>`;
  });

  return `<div class="vl-kort">${deler.join('')}</div>`;
}


function mkVerdier(fane) {
  const reg = REGISTRE[fane];
  const rader = data[fane];

  const innhold = rader.length ? rader.map((r) => {
    const inaktiv = r.er_aktiv ? '' : ' vl-inaktiv';
    const inaktivMerke = r.er_aktiv ? ''
      : '<span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
    const kort = r.kortnavn
      ? `<span class="vl-merkelapp">${escapeHtml(r.kortnavn)}</span>` : '';
    // Tallet står i lista, ikke bare i feilmeldingen: en verdimengde man kan
    // slette uten å vite hva som henger i den, sletter man for lett.
    const bruk = r.i_bruk
      ? `<span class="vl-meta">${escHtmlValue(r.i_bruk)} i bruk</span>`
      : '<span class="vl-meta">ubrukt</span>';
    return `
      <div class="vl-rad${inaktiv}">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="vl-navn">${escapeHtml(r.navn)}</span>
          ${inaktivMerke}${kort}${bruk}
        </div>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-outline-secondary" type="button"
                  data-action="apneRedigerVerdi" data-id="${escHtmlValue(r.id)}">Rediger</button>
          <button class="btn btn-sm btn-outline-danger" type="button"
                  data-action="slettVerdi" data-id="${escHtmlValue(r.id)}">Slett</button>
        </div>
      </div>`;
  }).join('') : '<div class="vl-tom">Ingen ennå.</div>';

  return `
    <div class="vl-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">${escapeHtml(reg.tittel)}</span>
        <button class="btn btn-sm btn-primary" type="button"
                data-action="apneNyVerdi">
          <i class="bi bi-plus-lg me-1"></i>${escapeHtml(reg.nyEtikett)}
        </button>
      </div>
      ${innhold}
    </div>`;
}


// ── Skjemahjelpere ───────────────────────────────────────────────────────

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


function _apneModal(id) {
  new bootstrap.Modal(document.getElementById(id)).show();
}


function _sett(id, verdi) {
  const el = document.getElementById(id);
  if (el) el.value = verdi ?? '';
}


function _les(id) {
  return (document.getElementById(id)?.value || '').trim();
}


function _fyllValg(id, rader, tomtValg) {
  const el = document.getElementById(id);
  if (!el) return;
  const deler = tomtValg ? [`<option value="">${escapeHtml(tomtValg)}</option>`] : [];
  rader.forEach((r) => {
    deler.push(`<option value="${escHtmlValue(r.id)}">${escapeHtml(r.navn)}</option>`);
  });
  el.innerHTML = deler.join('');
}


// ── Mannskap ─────────────────────────────────────────────────────────────

function _fyllPersonskjema(person) {
  // Inaktive korps og kompetanser tilbys ikke på nye rader, men beholdes på
  // dem som alt har dem — derfor filtreres det bare når feltet er tomt.
  const korps = data.korps.filter(
    (k) => k.er_aktiv || (person && person.korps_id === k.id));
  _fyllValg('person-korps', korps, '');
  _fyllValg('person-kompetanser', data.kompetanser.filter(
    (k) => k.er_aktiv || (person && person.kompetanser.some((x) => x.id === k.id))), '');

  // En konto kan bare kobles til én person (OneToOne). Vis de ledige, pluss
  // denne personens egen.
  const kontoer = data.kontoer
    .filter((u) => !u.mannskap_id || (person && u.mannskap_id === person.id))
    .map((u) => ({ id: u.id, navn: u.brukernavn }));
  _fyllValg('person-konto', kontoer, 'Ingen konto');

  _sett('person-navn', person ? person.navn : '');
  _sett('person-korps', person ? person.korps_id : '');
  _sett('person-telefon', person ? person.telefon : '');
  _sett('person-konto', person && person.user_id ? person.user_id : '');
  _sett('person-notat', person ? person.notat : '');
  document.getElementById('person-aktiv').checked = person ? person.er_aktiv : true;
  document.getElementById('person-aktiv-rad').classList.toggle('d-none', !person);

  const valgte = new Set(person ? person.kompetanser.map((k) => k.id) : []);
  Array.from(document.getElementById('person-kompetanser').options).forEach((o) => {
    o.selected = valgte.has(Number(o.value));
  });
}


function apneNyPerson() {
  if (!data.korps.length) {
    visRegisterFane('korps');
    return;
  }
  redigerer = null;
  _skjulFeil('person-feil');
  document.getElementById('person-tittel').textContent = 'Nytt mannskap';
  _fyllPersonskjema(null);
  _apneModal('personModal');
}


function apneRedigerPerson(id) {
  const person = data.mannskap.find((m) => m.id === id);
  if (!person) return;
  redigerer = id;
  _skjulFeil('person-feil');
  document.getElementById('person-tittel').textContent = person.navn;
  _fyllPersonskjema(person);
  _apneModal('personModal');
}


async function lagrePerson() {
  _skjulFeil('person-feil');
  await withSubmitGuard('person-knapp', async () => {
    const navn = _les('person-navn');
    if (!navn) { _visFeil('person-feil', 'Personen må ha et navn.'); return; }
    const korpsId = _les('person-korps');
    if (!korpsId) {
      _visFeil('person-feil', 'Velg hvilket korps personen hører til.');
      return;
    }

    const kropp = {
      navn,
      korps_id: Number(korpsId),
      telefon: _les('person-telefon'),
      user_id: _les('person-konto') ? Number(_les('person-konto')) : null,
      notat: _les('person-notat'),
      kompetanse_ider: Array.from(
        document.getElementById('person-kompetanser').selectedOptions)
        .map((o) => Number(o.value)),
    };
    if (redigerer) kropp.er_aktiv = document.getElementById('person-aktiv').checked;

    const res = await apiFetch(
      redigerer ? `/vaktliste/api/mannskap/${redigerer}/` : '/vaktliste/api/mannskap/',
      { method: redigerer ? 'PUT' : 'POST', body: JSON.stringify(kropp) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('person-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    _lukkModal('personModal');
    await lastRegistre();
  });
}


async function slettPerson(id) {
  const person = data.mannskap.find((m) => m.id === id);
  if (!person) return;
  if (person.i_bruk) {
    alert(`${person.navn} står på ${person.i_bruk} vaktpost(er) og kan ikke `
        + 'slettes.\n\nSett personen inaktiv i stedet — da skjules hun i '
        + 'nedtrekkslistene, men blir stående der hun gikk vakt.');
    return;
  }
  if (!confirm(`Slette ${person.navn} fra registeret?`)) return;

  const res = await apiFetch(`/vaktliste/api/mannskap/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { alert(d.message || 'Kunne ikke slette.'); return; }
  await lastRegistre();
}


// ── De tre verdimengdene ─────────────────────────────────────────────────

function apneNyVerdi() {
  const reg = REGISTRE[aktivRegisterFane];
  redigerer = null;
  _skjulFeil('verdi-feil');
  document.getElementById('verdi-tittel').textContent = reg.nyEtikett;
  _sett('verdi-navn', '');
  _sett('verdi-kortnavn', '');
  _sett('verdi-rekkefolge', 100);
  document.getElementById('verdi-aktiv').checked = true;
  document.getElementById('verdi-aktiv-rad').classList.add('d-none');
  document.getElementById('verdi-kortnavn-rad')
    .classList.toggle('d-none', !reg.kortnavn);
  _apneModal('verdiModal');
}


function apneRedigerVerdi(id) {
  const reg = REGISTRE[aktivRegisterFane];
  const rad = data[aktivRegisterFane].find((r) => r.id === id);
  if (!rad) return;
  redigerer = id;
  _skjulFeil('verdi-feil');
  document.getElementById('verdi-tittel').textContent = rad.navn;
  _sett('verdi-navn', rad.navn);
  _sett('verdi-kortnavn', rad.kortnavn || '');
  _sett('verdi-rekkefolge', rad.rekkefolge);
  document.getElementById('verdi-aktiv').checked = rad.er_aktiv;
  document.getElementById('verdi-aktiv-rad').classList.remove('d-none');
  document.getElementById('verdi-kortnavn-rad')
    .classList.toggle('d-none', !reg.kortnavn);
  _apneModal('verdiModal');
}


async function lagreVerdi() {
  const fane = aktivRegisterFane;
  const reg = REGISTRE[fane];
  _skjulFeil('verdi-feil');
  await withSubmitGuard('verdi-knapp', async () => {
    const navn = _les('verdi-navn');
    if (!navn) { _visFeil('verdi-feil', 'Navn må fylles ut.'); return; }

    const kropp = { navn, rekkefolge: Number(_les('verdi-rekkefolge')) || 100 };
    if (reg.kortnavn) kropp.kortnavn = _les('verdi-kortnavn');
    if (redigerer) kropp.er_aktiv = document.getElementById('verdi-aktiv').checked;

    const res = await apiFetch(
      redigerer ? `/vaktliste/api/${reg.sti}/${redigerer}/`
                : `/vaktliste/api/${reg.sti}/`,
      { method: redigerer ? 'PUT' : 'POST', body: JSON.stringify(kropp) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('verdi-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    _lukkModal('verdiModal');
    await lastRegistre();
  });
}


async function slettVerdi(id) {
  const reg = REGISTRE[aktivRegisterFane];
  const rad = data[aktivRegisterFane].find((r) => r.id === id);
  if (!rad) return;
  if (!confirm(`Slette «${rad.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/${reg.sti}/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { alert(d.message || 'Kunne ikke slette.'); return; }
  await lastRegistre();
}


document.addEventListener('DOMContentLoaded', () => {
  lastRegistre();
});
