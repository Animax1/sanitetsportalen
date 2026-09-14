// ════════════════════════════════════════════════════════
// vaktliste-register.js
// ════════════════════════════════════════════════════════
//
// Mannskapsregisteret, korps og kompetanser.
//
// Delt ut av `vaktliste.js` 14. sep. 2026 (gjeldspunkt 3.6). Fila var
// 3 801 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/vaktliste/index.html`, og funksjonene deler ett globalt
// navnerom som før. `VaktlisteFileneDekkerAltTests` håndhever at
// ingen funksjon forsvant eller ble duplisert i delingen.
// ════════════════════════════════════════════════════════

// ── MANNSKAPSREGISTERET ──────────────────────────────────────────────────
//
// Flyttet hit fra vaktliste-registre.js 30. aug. 2026, da registersiden ble
// lagt ned. Fanen er registeret; korps og kompetanser ligger i
// «Innstillinger», fordi de røres sjelden og er portalens oppsett.
//
// Alt som settes med innerHTML escapes: navn, telefon og notat er fritekst.

function kanRedigerePerson(person) {
  // Badgen. `skriv_handling` fører sitt eget korps og ingen andres.
  if (kanSkriveAlt()) return true;
  if (_nivaa() !== 'skriv_handling') return false;
  return window.MITT_KORPS_ID != null && person.korps_id === window.MITT_KORPS_ID;
}


function _passerPersonsok(m) {
  if (!personsok) return true;
  const n = personsok.toLowerCase();
  return [m.navn, m.korps_navn, m.telefon, m.epost, m.issi, m.brukernavn]
    .concat((m.alle_kompetanser || []).map((k) => k.navn))
    .some((v) => (v || '').toLowerCase().includes(n));
}


function _sorterMannskap(rader) {
  const nokkel = (m) => {
    if (personSortKol === 'navn') return m.navn.toLowerCase();
    if (personSortKol === 'telefon') return m.telefon || '\uffff';  // tomme sist
    return m.korps_navn.toLowerCase() + '\u0000' + m.navn.toLowerCase();
  };
  const ut = rader.slice().sort((a, b) => nokkel(a).localeCompare(nokkel(b)));
  return personSortStigende ? ut : ut.reverse();
}


function sorterMannskap(kolonne) {
  if (personSortKol === kolonne) personSortStigende = !personSortStigende;
  else { personSortKol = kolonne; personSortStigende = true; }
  tegnPanel();
}


function settPersonsok(verdi) {
  personsok = verdi;
  tegnPanel();
}


function _koblPersonsok() {
  // Egen lytter framfor `data-action`: delegeringen i portal-utils.js er
  // klikkbasert, og dette er et tastetrykk.
  const el = document.getElementById('vl-sok');
  if (el) el.addEventListener('input', () => settPersonsok(el.value));
}


function _personKolonne(kolonne, tekst) {
  // Pilen viser hvilken kolonne som styrer, og hvilken vei.
  const pil = personSortKol === kolonne ? (personSortStigende ? ' \u25b2' : ' \u25bc') : '';
  return `<th class="vlr-sortbar" data-action="sorterMannskap" data-arg="${escHtmlValue(kolonne)}">`
       + `${escapeHtml(tekst)}${escapeHtml(pil)}</th>`;
}


function mkMannskap() {
  if (!register) {
    return '<div class="vl-kort"><div class="vl-tom">Henter registeret\u2026</div></div>';
  }

  const nyKnapp = kanSkriveNoe()
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneNyPerson">
         <i class="bi bi-person-plus me-1"></i>Nytt mannskap
       </button>`
    : '';
  const hode = `
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">
          <i class="bi bi-person-vcard me-1"></i>Mannskap
          <span class="vl-meta">${escHtmlValue(register.mannskap.length)} i registeret</span>
        </span>
        ${nyKnapp}
      </div>`;

  if (!register.korps.length) {
    // **Korpset først.** Det er badgen tilgangsmodellen hviler på, og uten
    // ett kan ingen person opprettes. Knappen sier derfor «Legg inn korps»
    // og ikke «Nytt mannskap»: en knapp som åpner noe annet enn det den
    // heter, er en knapp man klikker på én gang og aldri stoler på igjen.
    const tilKorps = kanSkriveAlt()
      ? `<button class="btn btn-sm btn-primary" type="button"
                 data-action="apneVerdier" data-arg="korps">
           <i class="bi bi-flag me-1"></i>Legg inn korps
         </button>`
      : '';
    return `
      <div class="vl-kort">
        <div class="vl-kort-topp">
          <span class="vl-kort-tittel">
            <i class="bi bi-person-vcard me-1"></i>Mannskap
          </span>
          ${tilKorps}
        </div>
        <div class="vl-tom">
          Ingen korps ennå. Et mannskap må høre til et korps — korpset er
          badgen tilgangsmodellen hviler på.
        </div>
      </div>`;
  }

  if (!register.mannskap.length) {
    return `<div class="vl-kort">${hode}`
         + '<div class="vl-tom">Ingen i registeret ennå. Trykk «Nytt mannskap».</div></div>';
  }

  // **Tabell, ikke merkelapper på rad.** Med én kompetanse så den gamle
  // visningen fin ut; med åtte brøt den om og skjøv telefonnummeret ut av
  // syne. Faste kolonner gjør at det du leter etter alltid står samme sted.
  const rader = _sorterMannskap(register.mannskap.filter(_passerPersonsok));

  const kropp = rader.length ? rader.map((m) => {
    const inaktiv = m.er_aktiv ? '' : ' vl-inaktiv';

    // Bare de synlige kompetansene — har hun AFØR, er VFØR implisert.
    // Hele settet ligger i `title`, så «har hun egentlig VFØR?» kan besvares
    // uten å åpne skjemaet.
    const alle = (m.alle_kompetanser || []).map((k) => k.navn).join(', ');
    // Merkelappene ligger i en wrapper, ikke rett i cella: `display: flex`
    // på en `<td>` tar cella ut av tabellens boksmodell (se stilarket).
    const merkelapper = m.kompetanser.map((k) =>
      `<span class="vl-merkelapp">${escapeHtml(k.navn)}</span>`).join('');
    const merker = merkelapper
      ? `<div class="vlr-kompliste">${merkelapper}</div>`
      : '<span class="vl-meta">—</span>';

    // Ikoner, ikke tekst: to tekstknapper trenger ~150px og sprengte
    // handlingskolonnen på smale skjermer. `title` og `aria-label` bærer
    // betydningen — en ikonknapp uten dem er en gåte.
    const knapper = kanRedigerePerson(m)
      ? `<button class="btn btn-sm btn-outline-secondary" type="button"
                 title="Rediger ${escHtmlValue(m.navn)}" aria-label="Rediger ${escHtmlValue(m.navn)}"
                 data-action="apneRedigerPerson" data-id="${escHtmlValue(m.id)}"><i class="bi bi-pencil"></i></button>
         <button class="btn btn-sm btn-outline-danger" type="button"
                 title="Slett ${escHtmlValue(m.navn)}" aria-label="Slett ${escHtmlValue(m.navn)}"
                 data-action="slettPerson" data-id="${escHtmlValue(m.id)}"><i class="bi bi-trash"></i></button>`
      : '';

    const inaktivMerke = m.er_aktiv ? ''
      : ' <span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
    const konto = m.brukernavn
      ? escapeHtml(m.brukernavn) : '<span class="vl-meta">—</span>';
    // Merket ved e-posten sier at en portalbruker finnes med adressen —
    // altså at koblingen skjer (eller har skjedd) av seg selv.
    const epost = m.epost
      ? escapeHtml(m.epost) + (m.konto_finnes
          ? ' <i class="bi bi-person-check vl-konto-finnes" title="Portalbruker med denne e-posten"></i>'
          : '')
      : '<span class="vl-meta">—</span>';
    const kontoCelle = _erAdmin() ? `<td>${konto}</td>` : '';

    return `
      <tr class="${escHtmlValue(inaktiv.trim())}">
        <td class="vl-navn">${escapeHtml(m.navn)}${inaktivMerke}</td>
        <td>${escapeHtml(m.korps_kort)}</td>
        <td class="vlr-komp" title="${escHtmlValue(alle)}">${merker}</td>
        <td class="vlr-tlf">${escapeHtml(m.telefon || '—')}</td>
        <td class="vlr-epost">${epost}</td>
        <td class="vlr-tlf">${escapeHtml(m.issi || '—')}</td>
        ${kontoCelle}
        <td class="vlr-handling">${knapper}</td>
      </tr>`;
  }).join('')
    : `<tr><td colspan="${_erAdmin() ? 8 : 7}" class="vl-tom">Ingen treff på «${escapeHtml(personsok)}».</td></tr>`;

  const treff = document.getElementById('vl-treff');
  if (treff) {
    treff.textContent = personsok
      ? `${rader.length} av ${register.mannskap.length}` : `${rader.length}`;
  }

  // Andelene summerer til 100 i begge utgaver — kontokolonnen finnes bare
  // for global admin, og de andre kolonnene får plassen når den mangler.
  // Kolonnene: navn, korps, kompetanse, telefon, e-post, ISSI, [konto], handling.
  const kolonner = _erAdmin()
    ? `<colgroup>
            <col style="width: 18%"><col style="width: 8%">
            <col style="width: 23%"><col style="width: 11%">
            <col style="width: 16%"><col style="width: 8%">
            <col style="width: 8%"><col style="width: 8%">
          </colgroup>`
    : `<colgroup>
            <col style="width: 20%"><col style="width: 9%">
            <col style="width: 26%"><col style="width: 12%">
            <col style="width: 17%"><col style="width: 8%">
            <col style="width: 8%">
          </colgroup>`;

  return `
    <div class="vl-kort">
      ${hode}
      <div class="vlr-tabellramme">
        <table class="vlr-tabell">
          ${kolonner}
          <thead>
            <tr>
              ${_personKolonne('navn', 'Navn')}
              ${_personKolonne('korps', 'Korps')}
              <th>Kompetanse</th>
              ${_personKolonne('telefon', 'Telefon')}
              <th>E-post</th>
              <th title="Nødnettsterminalens nummer">ISSI</th>
              ${_erAdmin() ? '<th>Konto</th>' : ''}
              <th></th>
            </tr>
          </thead>
          <tbody>${kropp}</tbody>
        </table>
      </div>
    </div>`;
}


function _lesFelt(id) {
  return (document.getElementById(id)?.value || '').trim();
}


function _apneModal(id) {
  bootstrap.Modal.getOrCreateInstance(document.getElementById(id)).show();
}


function _fyllPersonskjema(person) {
  // Inaktive korps og kompetanser tilbys ikke på nye rader, men beholdes på
  // dem som alt har dem — derfor filtreres det bare når feltet er tomt.
  const korps = register.korps.filter(
    (k) => k.er_aktiv || (person && person.korps_id === k.id));
  _fyll('person-korps', korps, '');
  _fyll('person-kompetanser', register.kompetanser.filter(
    (k) => k.er_aktiv || (person && person.kompetanser.some((x) => x.id === k.id))), '');

  // En konto kan bare kobles til én person (OneToOne). Vis de ledige, pluss
  // denne personens egen.
  const kontoer = register.kontoer
    .filter((u) => !u.mannskap_id || (person && u.mannskap_id === person.id))
    .map((u) => ({ id: u.id, navn: u.brukernavn }));
  _fyll('person-konto', kontoer, 'Ingen konto');

  _settVerdi('person-navn', person ? person.navn : '');
  _settVerdi('person-korps', person ? person.korps_id : '');
  _settVerdi('person-telefon', person ? person.telefon : '');
  _settVerdi('person-epost', person ? person.epost : '');
  _settVerdi('person-issi', person ? person.issi : '');
  _settVerdi('person-konto', person && person.user_id ? person.user_id : '');
  _settVerdi('person-notat', person ? person.notat : '');
  document.getElementById('person-aktiv').checked = person ? person.er_aktiv : true;
  document.getElementById('person-aktiv-rad').classList.toggle('d-none', !person);

  const valgte = new Set(person ? person.kompetanser.map((k) => k.id) : []);
  Array.from(document.getElementById('person-kompetanser').options).forEach((o) => {
    o.selected = valgte.has(Number(o.value));
  });
}


function apneNyPerson() {
  if (!register) return;
  if (!register.korps.length) { apneVerdier('korps'); return; }
  redigererPerson = null;
  _skjulFeil('person-feil');
  document.getElementById('person-tittel').textContent = 'Nytt mannskap';
  _fyllPersonskjema(null);
  _apneModal('personModal');
}


function apneRedigerPerson(id) {
  const person = register?.mannskap.find((m) => m.id === id);
  if (!person) return;
  redigererPerson = id;
  _skjulFeil('person-feil');
  document.getElementById('person-tittel').textContent = person.navn;
  _fyllPersonskjema(person);
  _apneModal('personModal');
}


async function lagrePerson() {
  _skjulFeil('person-feil');
  await withSubmitGuard('person-knapp', async () => {
    const navn = _lesFelt('person-navn');
    if (!navn) { _visFeil('person-feil', 'Personen må ha et navn.'); return; }
    const korpsId = _lesFelt('person-korps');
    if (!korpsId) {
      _visFeil('person-feil', 'Velg hvilket korps personen hører til.');
      return;
    }

    const kropp = {
      navn,
      korps_id: Number(korpsId),
      telefon: _lesFelt('person-telefon'),
      epost: _lesFelt('person-epost'),
      issi: _lesFelt('person-issi'),
      notat: _lesFelt('person-notat'),
      kompetanse_ider: Array.from(
        document.getElementById('person-kompetanser').selectedOptions)
        .map((o) => Number(o.value)),
    };
    if (redigererPerson) {
      kropp.er_aktiv = document.getElementById('person-aktiv').checked;
    }
    // Kontokobling for hånd er global admin; andre sender ikke feltet, og
    // serveren avviser det uansett.
    if (_erAdmin()) {
      kropp.user_id = _lesFelt('person-konto') ? Number(_lesFelt('person-konto')) : null;
    }

    const res = await apiFetch(
      redigererPerson ? `/vaktliste/api/mannskap/${redigererPerson}/`
                      : '/vaktliste/api/mannskap/',
      { method: redigererPerson ? 'PUT' : 'POST', body: JSON.stringify(kropp) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('person-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    _lukkModal('personModal');
    await _lastRegisterOgListe();
  });
}


async function slettPerson(id) {
  const person = register?.mannskap.find((m) => m.id === id);
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
  await _lastRegisterOgListe();
}


async function _lastRegisterOgListe() {
  // **Begge, ikke bare registeret.** Navn, korps og aktiv-flagget står i
  // nedtrekkene på planleggingssiden også — endres en person uten at lista
  // hentes på nytt, bemanner man fra en liste som er utdatert.
  await lastRegister();
  if (aktivListe) await lastListe(aktivListe.vaktliste.id);
}


// ── Korps og kompetanser (i «Innstillinger») ─────────────────────────────
//
// De to deler bygger og skjema, på samme måte som serveren deler fabrikk —
// kopier er kopier å glemme. Vinduet viser lista, og skjemaet folder seg ut
// inni det samme vinduet: en modal oppå en modal oppå en modal er tre lag
// man ikke finner tilbake fra.

function apneVerdier(navn) {
  aktivVerdiregister = navn;
  const reg = REGISTRE[navn];
  _skjulFeil('verdi-feil');
  _skjulVerdiskjema();
  const tittel = document.getElementById('verdi-tittel');
  if (tittel) tittel.textContent = reg.tittel;
  const ny = document.getElementById('verdi-ny-knapp');
  if (ny) {
    ny.textContent = reg.nyEtikett;
    ny.classList.toggle('d-none', !kanSkriveAlt());
  }
  if (!register) { lastRegister(); }
  tegnVerdiliste();
  _apneModal('verdiModal');
}


function tegnVerdiliste() {
  const el = document.getElementById('verdi-liste');
  if (!el) return;
  el.innerHTML = register ? mkVerdiliste(aktivVerdiregister)
    : '<div class="vl-tom">Henter\u2026</div>';
}


function mkVerdiliste(navn) {
  const rader = register[navn] || [];
  // Verdimengdene er organisasjonens oppsett — `skriv_full`. Korps-føreren
  // ser dem (nedtrekkslistene trenger dem), men endrer dem ikke.
  const full = kanSkriveAlt();
  if (!rader.length) return '<div class="vl-tom">Ingen ennå.</div>';

  return rader.map((r) => {
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
  }).join('');
}


function _skjulVerdiskjema() {
  document.getElementById('verdi-skjema')?.classList.add('d-none');
  document.getElementById('verdi-ny-knapp')?.classList.toggle(
    'd-none', !kanSkriveAlt());
}


function _visVerdiskjema(reg, rad) {
  document.getElementById('verdi-skjema')?.classList.remove('d-none');
  document.getElementById('verdi-ny-knapp')?.classList.add('d-none');
  _settVerdi('verdi-navn', rad ? rad.navn : '');
  _settVerdi('verdi-kortnavn', rad && rad.kortnavn ? rad.kortnavn : '');
  document.getElementById('verdi-aktiv').checked = rad ? rad.er_aktiv : true;
  document.getElementById('verdi-aktiv-rad').classList.toggle('d-none', !rad);
  document.getElementById('verdi-kortnavn-rad')
    .classList.toggle('d-none', !reg.kortnavn);
  _stigefelt(reg, rad);
}


function apneNyVerdi() {
  const reg = REGISTRE[aktivVerdiregister];
  redigererVerdi = null;
  _skjulFeil('verdi-feil');
  _visVerdiskjema(reg, null);
}


function _stigefelt(reg, rad) {
  // Kun kompetanser har en stige. En kompetanse kan ikke bygge på seg selv;
  // resten av ringene stoppes på serveren, som er den som kan se hele treet.
  const rad_el = document.getElementById('verdi-bygger-paa-rad');
  if (rad_el) rad_el.classList.toggle('d-none', !reg.stige);
  if (!reg.stige) return;
  const valg = ((register && register.kompetanser) || [])
    .filter((k) => !rad || k.id !== rad.id);
  _fyll('verdi-bygger-paa', valg, 'Ingen — står alene');
  _settVerdi('verdi-bygger-paa', rad && rad.bygger_paa_id ? rad.bygger_paa_id : '');
}


function apneRedigerVerdi(id) {
  const reg = REGISTRE[aktivVerdiregister];
  const rad = (register[aktivVerdiregister] || []).find((r) => r.id === id);
  if (!rad) return;
  redigererVerdi = id;
  _skjulFeil('verdi-feil');
  _visVerdiskjema(reg, rad);
}


function avbrytVerdi() {
  redigererVerdi = null;
  _skjulFeil('verdi-feil');
  _skjulVerdiskjema();
}


async function lagreVerdi() {
  const reg = REGISTRE[aktivVerdiregister];
  _skjulFeil('verdi-feil');
  await withSubmitGuard('verdi-knapp', async () => {
    const navn = _lesFelt('verdi-navn');
    if (!navn) { _visFeil('verdi-feil', 'Navn må fylles ut.'); return; }

    const kropp = { navn };
    if (reg.kortnavn) kropp.kortnavn = _lesFelt('verdi-kortnavn');
    if (reg.stige) kropp.bygger_paa_id = _lesFelt('verdi-bygger-paa') || null;
    if (redigererVerdi) {
      kropp.er_aktiv = document.getElementById('verdi-aktiv').checked;
    }

    const res = await apiFetch(
      redigererVerdi ? `/vaktliste/api/${reg.sti}/${redigererVerdi}/`
                     : `/vaktliste/api/${reg.sti}/`,
      { method: redigererVerdi ? 'PUT' : 'POST', body: JSON.stringify(kropp) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('verdi-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    redigererVerdi = null;
    _skjulVerdiskjema();
    await _lastRegisterOgListe();
    tegnVerdiliste();
  });
}


async function slettVerdi(id) {
  const reg = REGISTRE[aktivVerdiregister];
  const rad = (register[aktivVerdiregister] || []).find((r) => r.id === id);
  if (!rad) return;
  if (!confirm(`Slette «${rad.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/${reg.sti}/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { alert(d.message || 'Kunne ikke slette.'); return; }
  await _lastRegisterOgListe();
  tegnVerdiliste();
}


document.addEventListener('DOMContentLoaded', () => {
  gateKnapper();
  // Offline drift (13. sep. 2026): workeren registreres først, så siden
  // ligger i kopi fra første besøk; køen sendes hvert 15. sekund og når
  // nettet kommer tilbake.
  registrerOffline();
  tegnOffline();
  // Cellene i ressurstabellen og korpsvelgeren melder `change`; begge går
  // gjennom `haandterHendelse` i portal-utils.js (12. sep. 2026). Lytteren
  // som lå her var scopet til panelet, og korpsvelgeren står utenfor det.
  _koblPersonsok();
  document.getElementById('ny-vaktpost-mannskap')
    ?.addEventListener('change', _vaktpostModusSkifte);
  document.getElementById('ny-vaktpost-fra')
    ?.addEventListener('change', () => foreslaaTil('ny-vaktpost-fra', 'ny-vaktpost-til'));
  document.getElementById('vaktpost-fra')
    ?.addEventListener('change', () => foreslaaTil('vaktpost-fra', 'vaktpost-til'));
  lastVaktlister();
  // Registeret (korps, kompetanser, mannskap) hentes med én gang, ikke
  // først når noen åpner «Innstillinger» — vinduet sto og ventet på nettet
  // (André, 12. sep. 2026: «delay når en trykker på korps»).
  lastRegister();
});
