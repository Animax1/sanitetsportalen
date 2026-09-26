// Overnatting — hvem sover hvor, for brannsikkerhetens skyld (André, 25. sep. 2026).
//
// «Dens funksjon er for brannsikkerhet.» Når alarmen går om natta, skal den
// som teller opp vite hvem som skal være i hvilket rom — og hvem som står på
// et skift og altså *ikke* er der. Papiret er hovedsaken: brannlista skrives
// ut per natt, og den står også i fila på e-post.
//
// Reglene står i `vaktliste/overnatting.py`; denne fila speiler dem bare for
// å gate knappene. Dataene kommer i vaktlistas hovedsvar (`aktivListe.
// overnatting`), så de følger med i offline-kopien.
//
// Alt som settes inn med `innerHTML` escapes — navn, rom, plassering og
// brannrutine er fritekst. Se `vaktliste/tests_xss.py`.


function _overnatting() {
  const o = aktivListe && aktivListe.overnatting;
  return {
    netter: (o && o.netter) || [],
    netter_i_vakta: (o && o.netter_i_vakta) || [],
    rom: (o && o.rom) || [],
    plasseringer: (o && o.plasseringer) || [],
    brannrutine: (o && o.brannrutine) || '',
  };
}


function _nattIso(d) {
  // Lokal dato som «2026-10-02». Ikke `toISOString()`, som gir UTC og flytter
  // natta en dag for alt etter midnatt om sommeren.
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}


function overnattingStandardnatt(netter, naa) {
  // **Natta fanen åpner på.** Er vi inne i en av vaktas netter, er det den —
  // og før klokka tolv regnes morgenen til natta som begynte kvelden før,
  // for det er den lista nattevakta fortsatt står med. Ellers den første som
  // ennå ikke er over, og etter vakta den siste.
  if (!netter || !netter.length) return null;
  const d = new Date(naa);
  if (d.getHours() < 12) d.setDate(d.getDate() - 1);
  const iNatt = _nattIso(d);
  if (netter.includes(iNatt)) return iNatt;
  const kommende = netter.find((n) => n > iNatt);
  return kommende || netter[netter.length - 1];
}


function _valgtNatt() {
  const netter = _overnatting().netter;
  if (overnattingNatt && netter.includes(overnattingNatt)) return overnattingNatt;
  return overnattingStandardnatt(netter, Date.now());
}


function overnattingNattTekst(natt) {
  // «Natt til lørdag 03.10» — slik natta sies, med morgenens dato. Samme
  // tekst som `overnatting.natt_tekst()` bruker i fila.
  const DAGER = ['søndag', 'mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag'];
  const [aar, mnd, dag] = String(natt).split('-').map(Number);
  const morgen = new Date(aar, mnd - 1, dag + 1);
  if (isNaN(morgen)) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `Natt til ${DAGER[morgen.getDay()]} ${p(morgen.getDate())}.${p(morgen.getMonth() + 1)}`;
}


function _overnattingsfane() {
  // Fanen finnes når det er rom å vise, eller når brukeren kan sette dem opp —
  // en fane som alltid er tom for den som bare leser, er en fane man slutter å
  // se. Tallet er dem som sover der natta fanen står på.
  if (!_overnatting().rom.length && !kanLede()) return null;
  const natt = _valgtNatt();
  return {
    id: OVERNATTING, navn: 'Overnatting', ikon: 'moon-stars',
    antall: natt ? _overnatting().plasseringer.filter((p) => p.natt === natt).length : null,
  };
}


function _folkIRom(romId, natt) {
  return _overnatting().plasseringer
    .filter((p) => p.rom_id === romId && p.natt === natt);
}


function overnattingFyll(rom, antall) {
  // «over» når flere enn kapasiteten er ført, «full» når den er nådd. Det
  // varsler, det sperrer ikke — serveren tar imot uansett.
  if (rom.kapasitet == null || rom.kapasitet === '') return '';
  if (antall > rom.kapasitet) return 'over';
  if (antall === rom.kapasitet) return 'full';
  return '';
}


function kanPlassereKorps(korpsId) {
  // Speiler `overnatting.kan_plassere` → `services.kan_fore_korps`: alle for
  // den som skriver alt, eget korps for korps-føreren.
  if (kanSkriveAlt()) return true;
  if (_nivaa() !== 'skriv_handling') return false;
  return window.MITT_KORPS_ID != null && korpsId === window.MITT_KORPS_ID;
}


function kanPlassereNoen() {
  // Knappen «Plasser» i rommet: finnes det noen brukeren kan legge inn?
  return kanSkriveAlt()
    || (_nivaa() === 'skriv_handling' && window.MITT_KORPS_ID != null);
}


function _paaVaktTekst(p) {
  return (p.paa_vakt || [])
    .map((s) => `${s.ressurs} ${_kl(s.fra)}–${_kl(s.til)}`).join(', ');
}


function _overnattingTelling(folk) {
  // `er_paa_vakt`, ikke lengden på `paa_vakt`: skiftene fra et annet korps
  // sendes ikke til en ren `les` (C1), men tellingen skal stemme likevel.
  const paaVakt = folk.filter((p) => p.er_paa_vakt).length;
  return { antall: folk.length, paaVakt, inne: folk.length - paaVakt };
}


function overnattingUtenSeng(natt) {
  // **Har vakt dette døgnet, men står ikke på noen seng.** Bare et hint —
  // mange sover hjemme. Døgnet regnes fra tolv til tolv rundt natta, i lokal
  // tid, og avmeldte skift teller ikke.
  if (!natt || !aktivListe) return [];
  const [aar, mnd, dag] = natt.split('-').map(Number);
  const fra = new Date(aar, mnd - 1, dag, 12);
  const til = new Date(aar, mnd - 1, dag + 1, 12);
  const sover = new Set(_overnatting().plasseringer
    .filter((p) => p.natt === natt).map((p) => p.mannskap_id));
  const sett = new Map();
  (aktivListe.vaktposter || []).forEach((vp) => {
    if (vp.mannskap_id == null || vp.avmeldt_at || sover.has(vp.mannskap_id)) return;
    const a = _d(vp.fra_tid);
    const b = _d(vp.til_tid);
    if (!a || !b || !(a < til && b > fra)) return;
    if (!sett.has(vp.mannskap_id)) sett.set(vp.mannskap_id, vp);
  });
  return [...sett.values()].sort((x, y) => x.navn.localeCompare(y.navn, 'nb'));
}


// ── Byggerne ─────────────────────────────────────────────────────────────

function _nattvelger(netter, valgt) {
  const knapper = netter.map((n) => {
    const aktiv = n === valgt ? ' active' : '';
    return `<button type="button" class="btn btn-sm btn-outline-secondary${aktiv}"
                    data-action="velgNatt" data-arg="${escHtmlValue(n)}">${escapeHtml(overnattingNattTekst(n))}</button>`;
  }).join('');
  return `<div class="btn-group flex-wrap vl-nattvelger" role="group" aria-label="Natt">${knapper}</div>`;
}


function _brannrutineboks(tekst) {
  const rediger = kanLede()
    ? `<button type="button" class="btn btn-sm btn-outline-secondary"
               data-action="apneBrannrutine"><i class="bi bi-pencil me-1"></i>Brannrutine</button>`
    : '';
  const innhold = tekst
    ? `<div class="vl-brannrutine-tekst">${escapeHtml(tekst)}</div>`
    : '<div class="vl-meta">Ingen brannrutine er skrevet inn. Lederen skriver samleplass og hva som gjøres ved alarm.</div>';
  return `
    <div class="vl-kort vl-brannrutine">
      <div class="d-flex align-items-start gap-2">
        <i class="bi bi-fire vl-brannikon" aria-hidden="true"></i>
        <div class="flex-grow-1">${innhold}</div>
        ${rediger}
      </div>
    </div>`;
}


function _sengerad(p) {
  const fjern = kanPlassereKorps(p.korps_id)
    ? `<button type="button" class="btn btn-sm btn-link text-danger p-0"
               data-action="fjernOvernatting" data-id="${escHtmlValue(p.id)}"
               title="Ta ut av rommet denne natta" aria-label="Ta ut av rommet">
         <i class="bi bi-x-lg"></i></button>`
    : '';
  const vakt = _paaVaktTekst(p);
  const merke = p.er_paa_vakt
    ? `<span class="vl-paavakt"><i class="bi bi-lightning-charge-fill me-1"></i>På vakt ${escapeHtml(vakt)}</span>`
    : '';
  return `
    <tr>
      <td>${escapeHtml(p.navn)}</td>
      <td>${escapeHtml(p.korps_kort)}</td>
      <td class="vl-tall">${escapeHtml(p.telefon || '')}</td>
      <td>${merke}</td>
      <td class="text-end">${fjern}</td>
    </tr>`;
}


function _romkort(rom, natt) {
  const folk = _folkIRom(rom.id, natt);
  const fyll = overnattingFyll(rom, folk.length);
  const tak = rom.kapasitet != null ? ` / ${escHtmlValue(rom.kapasitet)}` : '';
  const fyllMerke = fyll === 'over' ? '<span class="vl-romfyll vl-romfyll-over">Over kapasiteten</span>'
    : fyll === 'full' ? '<span class="vl-romfyll">Fullt</span>' : '';
  const plasser = kanPlassereNoen()
    ? `<button type="button" class="btn btn-sm btn-outline-primary"
               data-action="apnePlasser" data-id="${escHtmlValue(rom.id)}">
         <i class="bi bi-person-plus me-1"></i>Plasser</button>`
    : '';
  const rediger = kanLede()
    ? `<button type="button" class="btn btn-sm btn-outline-secondary"
               data-action="apneRedigerRom" data-id="${escHtmlValue(rom.id)}">Rediger</button>`
    : '';
  const plassering = rom.plassering
    ? `<span class="vl-meta">${escapeHtml(rom.plassering)}</span>` : '';
  const merknad = rom.merknad
    ? `<div class="vl-meta mt-1"><i class="bi bi-info-circle me-1"></i>${escapeHtml(rom.merknad)}</div>` : '';
  const rader = folk.map(_sengerad).join('');
  const tabell = rader
    ? `<div class="vl-tabellramme"><table class="vl-tabell vl-sengetabell">
         <thead><tr><th>Navn</th><th>Korps</th><th>Telefon</th><th></th><th></th></tr></thead>
         <tbody>${rader}</tbody></table></div>`
    : '<div class="vl-tom">Ingen sover her denne natta.</div>';
  return `
    <div class="vl-kort vl-romkort">
      <div class="vl-romhode">
        <div>
          <strong>${escapeHtml(rom.navn)}</strong> ${plassering}
        </div>
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="vl-romtall">${escHtmlValue(folk.length)}${tak}</span>${fyllMerke}
          ${plasser}${rediger}
        </div>
      </div>
      ${merknad}
      ${tabell}
    </div>`;
}


function _utenSengBolk(natt) {
  const folk = overnattingUtenSeng(natt);
  if (!folk.length) return '';
  const navn = folk.map((vp) => `<li>${escapeHtml(vp.navn)} <span class="vl-meta">${escapeHtml(vp.korps_kort || '')}</span></li>`).join('');
  return `
    <details class="vl-kort vl-utenseng">
      <summary>Har vakt dette døgnet, men ingen overnatting registrert (${escHtmlValue(folk.length)})</summary>
      <div class="vl-meta mb-1">Bare et hint — mange sover hjemme.</div>
      <ul class="mb-0">${navn}</ul>
    </details>`;
}


function mkBrannliste(netter) {
  // **Arket som henger hos nattevakta.** Tegnes alltid, men vises bare på
  // papiret (`.vl-brannliste` i @media print). Én side per natt, avkryssing
  // per person — lista skal kunne brukes med penn under opptelling.
  const o = _overnatting();
  const rutine = o.brannrutine
    ? `<div class="vl-brannliste-rutine">${escapeHtml(o.brannrutine)}</div>`
    : '<div class="vl-brannliste-rutine">Samleplass ved alarm: ______________________________</div>';
  const ark = netter.map((natt) => {
    const alle = o.plasseringer.filter((p) => p.natt === natt);
    const t = _overnattingTelling(alle);
    const rom = o.rom.map((r) => {
      const folk = _folkIRom(r.id, natt);
      if (!folk.length) return '';
      const tak = r.kapasitet != null ? ` av ${escHtmlValue(r.kapasitet)}` : '';
      const sted = r.plassering ? ` · ${escapeHtml(r.plassering)}` : '';
      const merknad = r.merknad ? `<div class="vl-meta">${escapeHtml(r.merknad)}</div>` : '';
      const rader = folk.map((p) => `
          <tr>
            <td class="vl-hake">☐</td>
            <td>${escapeHtml(p.navn)}</td>
            <td>${escapeHtml(p.korps_kort)}</td>
            <td>${escapeHtml(p.telefon || '')}</td>
            <td>${escapeHtml(p.er_paa_vakt ? ('PÅ VAKT ' + _paaVaktTekst(p)).trim() : '')}</td>
          </tr>`).join('');
      return `
        <h3>${escapeHtml(r.navn)}<small>${sted} · ${escHtmlValue(folk.length)}${tak}</small></h3>
        ${merknad}
        <table class="vl-brannliste-tabell">
          <thead><tr><th class="vl-hake">✓</th><th>Navn</th><th>Korps</th><th>Telefon</th><th>På vakt</th></tr></thead>
          <tbody>${rader}</tbody>
        </table>`;
    }).join('');
    const tom = rom ? '' : '<p>Ingen er registrert denne natta.</p>';
    return `
      <section class="vl-brannliste-ark">
        <h2>Brannliste – ${escapeHtml(aktivListe.vaktliste.vakt_navn)}</h2>
        <div class="vl-brannliste-natt">${escapeHtml(overnattingNattTekst(natt))} ·
          ${escHtmlValue(t.antall)} overnatter · ${escHtmlValue(t.paaVakt)} på vakt ·
          <strong>${escHtmlValue(t.inne)} skal være inne</strong></div>
        ${rutine}${rom}${tom}
        <div class="vl-meta">Skrevet ut ${escapeHtml(_kl(new Date().toISOString()))}. Slett etter vakta.</div>
      </section>`;
  }).join('');
  return `<div class="vl-brannliste">${ark}</div>`;
}


function mkOvernatting() {
  const o = _overnatting();
  if (!o.netter.length) {
    return `
      <div class="vl-kort"><div class="vl-tom">
        Vakta går ikke over noen natt. Sett vaktas lengde under «Innstillinger»
        slik at den dekker nettene folk skal sove, så kan rommene fylles.
      </div></div>`;
  }
  const natt = _valgtNatt();
  const alle = o.plasseringer.filter((p) => p.natt === natt);
  const t = _overnattingTelling(alle);
  const nyttRom = kanLede()
    ? `<button type="button" class="btn btn-sm btn-outline-primary"
               data-action="apneNyttRom"><i class="bi bi-plus-lg me-1"></i>Nytt rom</button>`
    : '';
  const flereNetter = o.netter.length > 1
    ? `<button type="button" class="btn btn-sm btn-outline-secondary"
               data-action="skrivUtBrannliste" data-arg="alle">Alle netter</button>`
    : '';
  const hint = kanLede() ? ' Trykk «Nytt rom».' : '';
  const rom = o.rom.length
    ? o.rom.map((r) => _romkort(r, natt)).join('')
    : `<div class="vl-kort"><div class="vl-tom">Ingen rom er satt opp ennå.${hint}</div></div>`;
  const utskrift = overnattingUtskrift === 'alle' ? o.netter : [natt];
  return `
    <div class="vl-overnatting-skjerm d-print-none">
      <div class="vl-kort vl-overnattinghode">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          ${_nattvelger(o.netter, natt)}
          <span class="flex-grow-1"></span>
          ${nyttRom}
          <button type="button" class="btn btn-sm btn-outline-secondary"
                  data-action="skrivUtBrannliste" data-arg="natt">
            <i class="bi bi-printer me-1"></i>Brannliste</button>${flereNetter}
        </div>
        <div class="vl-meta mt-2">
          <strong>${escHtmlValue(t.antall)}</strong> overnatter ·
          ${escHtmlValue(t.paaVakt)} på vakt i natt ·
          <strong>${escHtmlValue(t.inne)}</strong> skal være inne
        </div>
      </div>
      ${_brannrutineboks(o.brannrutine)}
      ${rom}
      ${_utenSengBolk(natt)}
    </div>
    ${mkBrannliste(utskrift)}`;
}


// ── Handlingene ──────────────────────────────────────────────────────────

function velgNatt(natt) {
  overnattingNatt = natt;
  tegnPanel();
  tegnFaner();
}


function skrivUtBrannliste(hva) {
  // Utvalget settes, panelet tegnes med arket for det, og nettleseren skriver
  // ut. Tilbake til én natt etterpå, så neste utskrift ikke overrasker.
  overnattingUtskrift = hva === 'alle' ? 'alle' : 'natt';
  tegnPanel();
  window.print();
  overnattingUtskrift = 'natt';
}


function _visRomvindu(rom) {
  const modal = document.getElementById('romModal');
  if (!modal) return;
  _skjulFeil('rom-feil');
  modal.dataset.rom = rom ? String(rom.id) : '';
  document.getElementById('rom-tittel').textContent = rom ? `Rom — ${rom.navn}` : 'Nytt rom';
  document.getElementById('rom-navn').value = rom ? rom.navn : '';
  document.getElementById('rom-plassering').value = rom ? rom.plassering : '';
  document.getElementById('rom-kapasitet').value = rom && rom.kapasitet != null ? rom.kapasitet : '';
  document.getElementById('rom-merknad').value = rom ? rom.merknad : '';
  document.getElementById('rom-slett-knapp')?.classList.toggle('d-none', !rom);
  bootstrap.Modal.getOrCreateInstance(modal).show();
}


function apneNyttRom() {
  _visRomvindu(null);
}


function apneRedigerRom(romId) {
  const rom = _overnatting().rom.find((r) => r.id === romId);
  if (rom) _visRomvindu(rom);
}


async function lagreRom() {
  const modal = document.getElementById('romModal');
  if (!modal) return;
  _skjulFeil('rom-feil');
  await withSubmitGuard('rom-knapp', async () => {
    const kropp = {
      navn: document.getElementById('rom-navn').value,
      plassering: document.getElementById('rom-plassering').value,
      kapasitet: document.getElementById('rom-kapasitet').value,
      merknad: document.getElementById('rom-merknad').value,
    };
    if (!kropp.navn.trim()) {
      _visFeil('rom-feil', 'Rommet må ha et navn.');
      return;
    }
    const url = modal.dataset.rom
      ? `/vaktliste/api/overnattingsrom/${Number(modal.dataset.rom)}/`
      : `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/overnattingsrom/`;
    const res = await apiFetch(url, {
      method: modal.dataset.rom ? 'PUT' : 'POST',
      body: JSON.stringify(kropp),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('rom-feil', d.message || 'Kunne ikke lagre rommet.');
      return;
    }
    _lukkModal('romModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function slettRom() {
  const modal = document.getElementById('romModal');
  if (!modal || !modal.dataset.rom) return;
  const romId = Number(modal.dataset.rom);
  const rom = _overnatting().rom.find((r) => r.id === romId);
  const antall = _overnatting().plasseringer.filter((p) => p.rom_id === romId).length;
  const advarsel = antall
    ? `\n\n${antall} plassering${antall === 1 ? '' : 'er'} i rommet forsvinner med det.` : '';
  if (!confirm(`Fjerne rommet «${rom ? rom.navn : ''}»?${advarsel}`)) return;
  const res = await apiFetch(`/vaktliste/api/overnattingsrom/${romId}/`, {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) {
    _visFeil('rom-feil', d.message || 'Kunne ikke fjerne rommet.');
    return;
  }
  _lukkModal('romModal');
  await lastListe(aktivListe.vaktliste.id);
}


function overnattingHvorSover(mannskapId, natt) {
  // Rommet personen alt står i den natta, eller `null`.
  const p = _overnatting().plasseringer
    .find((x) => x.mannskap_id === mannskapId && x.natt === natt);
  if (!p) return null;
  return _overnatting().rom.find((r) => r.id === p.rom_id) || null;
}


function apnePlasser(romId) {
  const modal = document.getElementById('plasserModal');
  const o = _overnatting();
  const rom = o.rom.find((r) => r.id === romId);
  if (!modal || !rom) return;
  _skjulFeil('plasser-feil');
  document.getElementById('plasser-flytt')?.classList.add('d-none');
  modal.dataset.rom = String(romId);
  document.getElementById('plasser-tittel').textContent = 'Plasser i ' + rom.navn;
  const natt = _valgtNatt();
  // **Nedtrekket er dem brukeren får føre** — `aktivListe.mannskap` er
  // serverens `mannskap_brukeren_kan_sette`, samme sett som bemanningen. Står
  // personen alt et sted den valgte natta, sies det i valget.
  const valg = (aktivListe.mannskap || []).map((m) => {
    const der = overnattingHvorSover(m.id, natt);
    const merke = der ? ' — sover i ' + der.navn : '';
    return `<option value="${escHtmlValue(m.id)}">${escapeHtml(m.navn + ' (' + (m.korps_navn || '') + ')' + merke)}</option>`;
  }).join('');
  document.getElementById('plasser-mannskap').innerHTML =
    '<option value="">Velg person …</option>' + valg;
  // Alle vaktas netter er huket av: det vanlige er samme seng hele vakta.
  document.getElementById('plasser-netter').innerHTML = o.netter_i_vakta.map((n) => `
      <div class="form-check form-check-inline">
        <input class="form-check-input" type="checkbox" id="plasser-natt-${escHtmlValue(n)}"
               value="${escHtmlValue(n)}" checked>
        <label class="form-check-label" for="plasser-natt-${escHtmlValue(n)}">${escapeHtml(overnattingNattTekst(n))}</label>
      </div>`).join('');
  bootstrap.Modal.getOrCreateInstance(modal).show();
}


async function lagrePlassering(flytt) {
  const modal = document.getElementById('plasserModal');
  if (!modal) return;
  _skjulFeil('plasser-feil');
  const mannskapId = Number(document.getElementById('plasser-mannskap').value);
  const netter = [...document.querySelectorAll('#plasser-netter input:checked')]
    .map((el) => el.value);
  if (!mannskapId) { _visFeil('plasser-feil', 'Velg en person.'); return; }
  if (!netter.length) { _visFeil('plasser-feil', 'Velg minst én natt.'); return; }
  await withSubmitGuard('plasser-knapp', async () => {
    const res = await apiFetch(
      `/vaktliste/api/overnattingsrom/${Number(modal.dataset.rom)}/plasser/`, {
        method: 'POST',
        body: JSON.stringify({ mannskap_id: mannskapId, netter, flytt: flytt === 'ja' }),
      });
    const d = await res.json().catch(() => ({}));
    if (res.status === 409) {
      // Sover et annet sted: si hvor, og tilby å flytte. Aldri stille —
      // det andre rommets opptelling blir feil.
      _visFeil('plasser-feil', `${d.message || ''} Flytte hit?`);
      document.getElementById('plasser-flytt')?.classList.remove('d-none');
      return;
    }
    if (!res.ok || d.status !== 'ok') {
      _visFeil('plasser-feil', d.message || 'Kunne ikke plassere personen.');
      return;
    }
    _lukkModal('plasserModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function fjernOvernatting(id) {
  const p = _overnatting().plasseringer.find((x) => x.id === id);
  if (!p) return;
  if (!confirm(`Ta ${p.navn} ut av rommet ${overnattingNattTekst(p.natt).toLowerCase()}?`)) return;
  const res = await apiFetch(`/vaktliste/api/overnattinger/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    alert(d.message || 'Kunne ikke ta personen ut av rommet.');
    return;
  }
  await lastListe(aktivListe.vaktliste.id);
}


function apneBrannrutine() {
  const modal = document.getElementById('brannrutineModal');
  if (!modal) return;
  _skjulFeil('brannrutine-feil');
  document.getElementById('brannrutine-tekst').value = _overnatting().brannrutine;
  bootstrap.Modal.getOrCreateInstance(modal).show();
}


async function lagreBrannrutine() {
  _skjulFeil('brannrutine-feil');
  await withSubmitGuard('brannrutine-knapp', async () => {
    const res = await apiFetch(`/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/`, {
      method: 'PUT',
      body: JSON.stringify({ brannrutine: document.getElementById('brannrutine-tekst').value }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('brannrutine-feil', d.message || 'Kunne ikke lagre brannrutinen.');
      return;
    }
    _lukkModal('brannrutineModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}
