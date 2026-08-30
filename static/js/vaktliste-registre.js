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
let sok = '';               // fritekstfilter på mannskapstabellen
let sortKol = 'korps';      // 'navn' | 'korps' | 'telefon'
let sortStigende = true;

// Fane → hvordan registeret snakkes om og hvor det ligger.
// `nyEtikett` er hele knappeteksten, ikke bare ordet: «korps» er intetkjønn
// og «kompetanse» hankjønn, så en hardkodet «Ny » foran gir feil artikkel på
// en av dem uansett hvilken man velger.
const REGISTRE = {
  korps: { sti: 'korps', nyEtikett: 'Nytt korps', tittel: 'Korps', kortnavn: true },
  kompetanser: { sti: 'kompetanser', nyEtikett: 'Ny kompetanse',
                 tittel: 'Kompetanser', stige: true },
  roller: { sti: 'roller', nyEtikett: 'Ny vaktrolle', tittel: 'Vaktroller' },
};


// ── Tilgang (fase 3) ─────────────────────────────────────────────────────
//
// Speiler views_registre.py. Serveren håndhever uansett; dette avgjør hvilke
// knapper som tegnes.

function _nivaa() {
  return ((window.MODUL_TILGANG || {}).vaktliste || '').toLowerCase();
}


function kanSkriveAlt() {
  return (window.MODUL_TILGANG || {}).admin === true || _nivaa() === 'skriv_full';
}


function kanRedigerePerson(person) {
  // Badgen. `skriv_handling` fører sitt eget korps og ingen andres.
  if (kanSkriveAlt()) return true;
  if (_nivaa() !== 'skriv_handling') return false;
  return window.MITT_KORPS_ID != null && person.korps_id === window.MITT_KORPS_ID;
}


function gateKnapper() {
  const skriv = kanSkriveAlt() || _nivaa() === 'skriv_handling';
  document.querySelectorAll('.vlr-krev-skriv')
    .forEach((el) => el.classList.toggle('d-none', !skriv));
  document.querySelectorAll('.vlr-krev-full')
    .forEach((el) => el.classList.toggle('d-none', !kanSkriveAlt()));
}


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
  const paaMannskap = aktivRegisterFane === 'mannskap';
  document.getElementById('vlr-verktoy')?.classList.toggle('d-none', !paaMannskap);
  el.innerHTML = paaMannskap ? mkMannskap() : mkVerdier(aktivRegisterFane);
}


// ── Byggere (alt escapes — se filhodet) ──────────────────────────────────

function _passerSok(m) {
  if (!sok) return true;
  const n = sok.toLowerCase();
  return [m.navn, m.korps_navn, m.telefon, m.brukernavn]
    .concat((m.alle_kompetanser || []).map((k) => k.navn))
    .some((v) => (v || '').toLowerCase().includes(n));
}


function _sorterMannskap(rader) {
  const nokkel = (m) => {
    if (sortKol === 'navn') return m.navn.toLowerCase();
    if (sortKol === 'telefon') return m.telefon || '\uffff';  // tomme sist
    return m.korps_navn.toLowerCase() + '\u0000' + m.navn.toLowerCase();
  };
  const ut = rader.slice().sort((a, b) => nokkel(a).localeCompare(nokkel(b)));
  return sortStigende ? ut : ut.reverse();
}


function sorterEtter(kolonne) {
  if (sortKol === kolonne) sortStigende = !sortStigende;
  else { sortKol = kolonne; sortStigende = true; }
  tegnRegister();
}


function settSok(verdi) {
  sok = verdi;
  tegnRegister();
}


function _koblSok() {
  // Egen lytter framfor `data-action`: delegeringen i portal-utils.js er
  // klikkbasert, og dette er et tastetrykk.
  const el = document.getElementById('vlr-sok');
  if (el) el.addEventListener('input', () => settSok(el.value));
}


function _kolonneHode(kolonne, tekst) {
  // Pilen viser hvilken kolonne som styrer, og hvilken vei.
  const pil = sortKol === kolonne ? (sortStigende ? ' ▲' : ' ▼') : '';
  return `<th class="vlr-sortbar" data-action="sorterEtter" data-arg="${escHtmlValue(kolonne)}">`
       + `${escapeHtml(tekst)}${escapeHtml(pil)}</th>`;
}


function mkMannskap() {
  if (!data.mannskap.length) {
    return '<div class="vl-kort"><div class="vl-tom">'
         + 'Ingen i registeret ennå. Trykk «Nytt mannskap».</div></div>';
  }

  // **Tabell, ikke merkelapper på rad.** Med én kompetanse så den gamle
  // visningen fin ut; med åtte brøt den om og skjøv telefonnummeret ut av
  // syne. Faste kolonner gjør at det du leter etter alltid står samme sted.
  const rader = _sorterMannskap(data.mannskap.filter(_passerSok));

  const kropp = rader.length ? rader.map((m) => {
    const inaktiv = m.er_aktiv ? '' : ' vl-inaktiv';

    // Bare de synlige kompetansene — har hun AFØR, er VFØR implisert.
    // Hele settet ligger i `title`, så «har hun egentlig VFØR?» kan besvares
    // uten å åpne skjemaet.
    const alle = (m.alle_kompetanser || []).map((k) => k.navn).join(', ');
    const merker = m.kompetanser.length
      ? m.kompetanser.map((k) =>
          `<span class="vl-merkelapp">${escapeHtml(k.navn)}</span>`).join('')
      : '<span class="vl-meta">—</span>';

    const knapper = kanRedigerePerson(m)
      ? `<button class="btn btn-sm btn-outline-secondary" type="button"
                 data-action="apneRedigerPerson" data-id="${escHtmlValue(m.id)}">Rediger</button>
         <button class="btn btn-sm btn-outline-danger" type="button"
                 data-action="slettPerson" data-id="${escHtmlValue(m.id)}">Slett</button>`
      : '';

    const inaktivMerke = m.er_aktiv ? ''
      : ' <span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
    const konto = m.brukernavn
      ? escapeHtml(m.brukernavn) : '<span class="vl-meta">—</span>';

    return `
      <tr class="${escHtmlValue(inaktiv.trim())}">
        <td class="vl-navn">${escapeHtml(m.navn)}${inaktivMerke}</td>
        <td>${escapeHtml(m.korps_kort)}</td>
        <td class="vlr-komp" title="${escHtmlValue(alle)}">${merker}</td>
        <td class="vlr-tlf">${escapeHtml(m.telefon || '—')}</td>
        <td>${konto}</td>
        <td class="vlr-handling">${knapper}</td>
      </tr>`;
  }).join('')
    : `<tr><td colspan="6" class="vl-tom">Ingen treff på «${escapeHtml(sok)}».</td></tr>`;

  const treff = document.getElementById('vlr-treff');
  if (treff) {
    treff.textContent = sok
      ? `${rader.length} av ${data.mannskap.length}` : `${rader.length}`;
  }

  return `
    <div class="vl-kort">
      <div class="vlr-tabellramme">
        <table class="vlr-tabell">
          <thead>
            <tr>
              ${_kolonneHode('navn', 'Navn')}
              ${_kolonneHode('korps', 'Korps')}
              <th>Kompetanse</th>
              ${_kolonneHode('telefon', 'Telefon')}
              <th>Konto</th>
              <th></th>
            </tr>
          </thead>
          <tbody>${kropp}</tbody>
        </table>
      </div>
    </div>`;
}


function mkVerdier(fane) {
  const reg = REGISTRE[fane];
  const rader = data[fane];

  // Verdimengdene er organisasjonens oppsett — `skriv_full`. Korps-føreren
  // ser dem (nedtrekkslistene trenger dem), men endrer dem ikke.
  const full = kanSkriveAlt();
  const innhold = rader.length ? rader.map((r) => {
    const verdiKnapper = full
      ? `<button class="btn btn-sm btn-outline-secondary" type="button"
                 data-action="apneRedigerVerdi" data-id="${escHtmlValue(r.id)}">Rediger</button>
         <button class="btn btn-sm btn-outline-danger" type="button"
                 data-action="slettVerdi" data-id="${escHtmlValue(r.id)}">Slett</button>`
      : '';
    const inaktiv = r.er_aktiv ? '' : ' vl-inaktiv';
    const inaktivMerke = r.er_aktiv ? ''
      : '<span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
    const kort = r.kortnavn
      ? `<span class="vl-merkelapp">${escapeHtml(r.kortnavn)}</span>` : '';
    // Stigen synliggjøres i lista: uten den må man åpne hver rad for å se
    // hvilke kurs som overordner hvilke.
    const stige = r.bygger_paa_navn
      ? `<span class="vl-meta">bygger på ${escapeHtml(r.bygger_paa_navn)}</span>`
      : '';
    // Tallet står i lista, ikke bare i feilmeldingen: en verdimengde man kan
    // slette uten å vite hva som henger i den, sletter man for lett.
    const bruk = r.i_bruk
      ? `<span class="vl-meta">${escHtmlValue(r.i_bruk)} i bruk</span>`
      : '<span class="vl-meta">ubrukt</span>';
    return `
      <div class="vl-rad${inaktiv}">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="vl-navn">${escapeHtml(r.navn)}</span>
          ${inaktivMerke}${kort}${stige}${bruk}
        </div>
        <div class="d-flex gap-2">${verdiKnapper}</div>
      </div>`;
  }).join('') : '<div class="vl-tom">Ingen ennå.</div>';

  const nyKnapp = full
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneNyVerdi">
         <i class="bi bi-plus-lg me-1"></i>${escapeHtml(reg.nyEtikett)}
       </button>`
    : '';

  return `
    <div class="vl-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">${escapeHtml(reg.tittel)}</span>
        ${nyKnapp}
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
  document.getElementById('verdi-aktiv').checked = true;
  document.getElementById('verdi-aktiv-rad').classList.add('d-none');
  _stigefelt(reg, null);
  document.getElementById('verdi-kortnavn-rad')
    .classList.toggle('d-none', !reg.kortnavn);
  _apneModal('verdiModal');
}


function _stigefelt(reg, rad) {
  // Kun kompetanser har en stige. En kompetanse kan ikke bygge på seg selv;
  // resten av ringene stoppes på serveren, som er den som kan se hele treet.
  const rad_el = document.getElementById('verdi-bygger-paa-rad');
  if (rad_el) rad_el.classList.toggle('d-none', !reg.stige);
  if (!reg.stige) return;
  const valg = (data.kompetanser || []).filter((k) => !rad || k.id !== rad.id);
  _fyllValg('verdi-bygger-paa', valg, 'Ingen — står alene');
  _sett('verdi-bygger-paa', rad && rad.bygger_paa_id ? rad.bygger_paa_id : '');
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
  document.getElementById('verdi-aktiv').checked = rad.er_aktiv;
  document.getElementById('verdi-aktiv-rad').classList.remove('d-none');
  _stigefelt(reg, rad);
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

    const kropp = { navn };
    if (reg.kortnavn) kropp.kortnavn = _les('verdi-kortnavn');
    if (reg.stige) kropp.bygger_paa_id = _les('verdi-bygger-paa') || null;
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
  gateKnapper();
  _koblSok();
  lastRegistre();
});
