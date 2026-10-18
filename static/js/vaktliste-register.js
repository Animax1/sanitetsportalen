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
  const ut = rader.slice().sort((a, b) => nokkel(a).localeCompare(nokkel(b), 'nb'));
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
  const hent = document.getElementById('hentinn-sok');
  if (hent) hent.addEventListener('input', () => sokHentInn(hent.value));
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
  // «Hent inn fra tidligere» (18. okt. 2026): registeret er vaktas, og en ny vakt
  // starter tom. Samme terskel som «Nytt mannskap» — korps-føreren henter sine.
  const hentKnapp = kanSkriveNoe()
    ? `<button class="btn btn-sm btn-outline-primary" type="button"
               data-action="apneHentInn">
         <i class="bi bi-box-arrow-in-down me-1"></i>Hent inn fra tidligere
       </button>`
    : '';
  const hode = `
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">
          <i class="bi bi-person-vcard me-1"></i>Mannskap
          <span class="vl-meta">${escHtmlValue(register.mannskap.length)} i registeret for ${escapeHtml(register.vakt_navn || 'vakten')}</span>
        </span>
        <span class="d-flex gap-2 flex-wrap">${hentKnapp}${nyKnapp}</span>
      </div>`;

  if (!register.korps.length) {
    // **Korpset først.** Det er badgen tilgangsmodellen hviler på, og uten
    // ett kan ingen person opprettes. Korpsene settes opp av admin utenfor
    // vaktlista (18. okt. 2026), så admin får lenken dit og de andre beskjeden.
    const tilKorps = _erAdmin()
      ? `<a class="btn btn-sm btn-primary" href="/admin/tilhorigheter/">
           <i class="bi bi-flag me-1"></i>Sett opp korps
         </a>`
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
          Ingen korps i portalen ennå. Et mannskap må høre til et korps — korpset
          er badgen tilgangsmodellen hviler på. Korpsene settes opp av en
          administrator under Administrasjon → Tilhørigheter.
        </div>
      </div>`;
  }

  if (!register.mannskap.length) {
    return `<div class="vl-kort">${hode}`
         + '<div class="vl-tom">Ingen i registeret for denne vakten ennå. Hent inn folk fra '
         + 'tidligere vakter, eller trykk «Nytt mannskap».</div></div>';
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
         <button class="btn btn-sm btn-outline-secondary" type="button"
                 title="Ta ${escHtmlValue(m.navn)} ut av vakten" aria-label="Ta ${escHtmlValue(m.navn)} ut av vakten"
                 data-action="taUtAvVakten" data-id="${escHtmlValue(m.id)}"><i class="bi bi-person-dash"></i></button>
         <button class="btn btn-sm btn-outline-danger" type="button"
                 title="Slett ${escHtmlValue(m.navn)} fra portalen" aria-label="Slett ${escHtmlValue(m.navn)} fra portalen"
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


function mkKompetansevalg(kompetanser, valgte) {
  // Én avkryssing per kompetanse (30. sep. 2026). Flervalgslisten krevde
  // «Hold Ctrl», som ikke finnes på telefonen korps-føreren sitter med.
  // `valgte` er et Set med id-er.
  if (!kompetanser.length) {
    return '<div class="vl-meta">Ingen kompetanser er lagt inn ennå.</div>';
  }
  return kompetanser.map((k) => {
    const id = `person-komp-${escHtmlValue(k.id)}`;
    const avkrysset = valgte.has(k.id) ? ' checked' : '';
    return `<div class="form-check">
      <input class="form-check-input" type="checkbox" id="${id}"
             value="${escHtmlValue(k.id)}"${avkrysset}>
      <label class="form-check-label" for="${id}">${escapeHtml(k.navn)}</label>
    </div>`;
  }).join('');
}


function _valgteKompetanser() {
  return Array.from(document.querySelectorAll('#person-kompetanser input:checked'))
    .map((el) => Number(el.value));
}


function epostHint() {
  // **Hintet følger regelen i `_koble_paa_epost`, ikke ønsket om den**
  // (30. sep. 2026). Teksten sa «kobles kontoen av seg selv» til alle, men
  // koblingen skjer bare når en vaktleder har lagt inn e-posten — siden
  // 13. og 28. sep. med vilje, fordi koblingen flytter en badge. For
  // korps-føreren var løftet usant: hun så ikonet og ingenting skjedde.
  if (kanLede()) {
    return 'Valgfritt. Legger du inn e-posten til en portalbruker, kobles '
      + 'kontoen til personen når du lagrer.';
  }
  return 'Valgfritt. Kontoen kobles når en vaktleder legger inn e-posten.';
}


function _fyllPersonskjema(person) {
  // Inaktive korps og kompetanser tilbys ikke på nye rader, men beholdes på
  // dem som alt har dem — derfor filtreres det bare når feltet er tomt.
  const korps = register.korps.filter(
    (k) => k.er_aktiv || (person && person.korps_id === k.id));
  _fyll('person-korps', korps, velgTekst());
  // **`alle_kompetanser` og ikke `kompetanser`** (30. sep. 2026). Den siste
  // utelater det stigen impliserer, så skjemaet viste AFØR uten VFØR — og
  // en lagring av telefonnummeret fjernet VFØR fra det lagrede settet.
  // Docstringen til `_mannskap_til_dict` har sagt dette hele tiden.
  const valgte = new Set(person
    ? (person.alle_kompetanser || person.kompetanser).map((k) => k.id) : []);
  document.getElementById('person-kompetanser').innerHTML = mkKompetansevalg(
    register.kompetanser.filter((k) => k.er_aktiv || valgte.has(k.id)), valgte);
  document.getElementById('person-epost-hint').textContent = epostHint();

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
}


function apneNyPerson() {
  if (!register) return;
  if (!register.korps.length) return;  // knappen finnes ikke uten korps — se mkMannskap
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
      kompetanse_ider: _valgteKompetanser(),
      // En ny person havner i registeret til vakta man ser på.
      vakt_id: register ? register.vakt_id : null,
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


async function taUtAvVakten(id) {
  // Personen står i portalen og kan hentes inn igjen; serveren nekter mens hun
  // står på et skift i vakta (409), og meldingen sier hvorfor.
  const person = register?.mannskap.find((m) => m.id === id);
  if (!person) return;
  if (!confirm(`Ta ${person.navn} ut av registeret for denne vakten? Personen kan hentes inn igjen.`)) return;
  const res = await apiFetch(`/vaktliste/api/mannskap/${id}/ta-ut/`,
    { method: 'POST', body: JSON.stringify({ vakt_id: register.vakt_id }) });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { alert(d.message || 'Kunne ikke ta ut.'); return; }
  await _lastRegisterOgListe();
}


// ── Hent inn fra tidligere (18. okt. 2026) ──────────────────────────────────
//
// Avkrysning, gruppert på korps. Tilstanden er `hentInnFolk` og `hentInnValgt` i JS,
// ikke i DOM-en — lista tegnes på nytt ved søk, og en avkrysning i markupen ville
// forsvunnet med den.

let hentInnFolk = [];
let hentInnValgt = new Set();
let hentInnSok = '';


async function apneHentInn() {
  hentInnValgt = new Set();
  hentInnSok = '';
  const sok = document.getElementById('hentinn-sok');
  if (sok) sok.value = '';
  _skjulFeil('hentinn-feil');
  const res = await apiFetch('/vaktliste/api/mannskap/hent-inn/'
    + (register && register.vakt_id ? `?vakt=${encodeURIComponent(register.vakt_id)}` : ''));
  const d = await res.json().catch(() => ({}));
  hentInnFolk = res.ok ? (d.data || []) : [];
  tegnHentInn();
  _apneModal('hentInnModal');
}


function hentInnSynlige() {
  const q = hentInnSok.trim().toLowerCase();
  return hentInnFolk.filter((m) => !q || m.navn.toLowerCase().includes(q)
    || (m.korps_navn || '').toLowerCase().includes(q));
}


function mkHentInn(folk, valgt) {
  if (!folk.length) {
    return '<div class="vl-tom">Ingen fra de siste 24 månedene å hente inn. Nye personer '
      + 'legges inn med «Nytt mannskap».</div>';
  }
  const korps = [...new Set(folk.map((m) => m.korps_navn))]
    .sort((a, b) => a.localeCompare(b, 'nb'));
  return korps.map((k) => {
    const her = folk.filter((m) => m.korps_navn === k);
    const rader = her.map((m) => `
      <label class="form-check vl-hentinn-rad">
        <input class="form-check-input" type="checkbox" data-action="velgHentInn"
               data-hendelse="change" data-id="${escHtmlValue(m.id)}"${valgt.has(m.id) ? ' checked' : ''}>
        <span class="form-check-label">${escapeHtml(m.navn)}</span>
        <span class="vl-meta">${m.sist ? 'sist ' + escapeHtml(new Date(m.sist).toLocaleDateString('nb-NO')) : ''}</span>
      </label>`).join('');
    const alleValgt = her.every((m) => valgt.has(m.id));
    return `
      <div class="vl-hentinn-korps">
        <div class="d-flex align-items-center justify-content-between">
          <strong>${escapeHtml(k)}</strong>
          <button class="btn btn-sm btn-link" type="button" data-action="velgKorpsHentInn"
                  data-arg="${escHtmlValue(k)}">${alleValgt ? 'Fjern alle' : 'Velg alle'}</button>
        </div>
        ${rader}
      </div>`;
  }).join('');
}


function tegnHentInn() {
  const el = document.getElementById('hentinn-liste');
  if (el) el.innerHTML = mkHentInn(hentInnSynlige(), hentInnValgt);
  const knapp = document.getElementById('hentinn-lagre');
  if (knapp) {
    knapp.disabled = hentInnValgt.size === 0;
    knapp.textContent = hentInnValgt.size ? `Hent inn ${hentInnValgt.size}` : 'Hent inn';
  }
}


function velgHentInn(id) {
  const n = Number(id);
  if (hentInnValgt.has(n)) hentInnValgt.delete(n); else hentInnValgt.add(n);
  tegnHentInn();
}


function velgKorpsHentInn(korps) {
  const her = hentInnSynlige().filter((m) => m.korps_navn === korps);
  const alle = her.every((m) => hentInnValgt.has(m.id));
  her.forEach((m) => (alle ? hentInnValgt.delete(m.id) : hentInnValgt.add(m.id)));
  tegnHentInn();
}


function sokHentInn(verdi) {
  hentInnSok = String(verdi ?? '');
  tegnHentInn();
}


async function lagreHentInn() {
  if (!hentInnValgt.size) return;
  const res = await apiFetch('/vaktliste/api/mannskap/hent-inn/', {
    method: 'POST',
    body: JSON.stringify({ vakt_id: register.vakt_id, ider: [...hentInnValgt] }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visFeil('hentinn-feil', d.message || 'Kunne ikke hente inn.');
    return;
  }
  _lukkModal('hentInnModal');
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
  aktivFane = startfane();
  lastVaktlister();
  // Registeret (korps, kompetanser, mannskap) hentes med én gang, ikke
  // først når noen åpner «Innstillinger» — vinduet sto og ventet på nettet
  // (André, 12. sep. 2026: «delay når en trykker på korps»).
  lastRegister();
});
