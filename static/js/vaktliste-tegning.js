// ════════════════════════════════════════════════════════
// vaktliste-tegning.js
// ════════════════════════════════════════════════════════
//
// Tegning og byggere: alt som lager markup.
//
// **Alt som kommer fra data escapes** — `escapeHtml()` for tekst,
// `escHtmlValue()` i attributter og tabeller, `trustedHtml()` for markup
// koden bygger selv. `vaktliste/tests_xss.py` håndhever det bygger for bygger.
//
// Delt ut av `vaktliste.js` 14. sep. 2026 (gjeldspunkt 3.6). Fila var
// 3 801 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/vaktliste/index.html`, og funksjonene deler ett globalt
// navnerom som før. `VaktlisteFileneDekkerAltTests` håndhever at
// ingen funksjon forsvant eller ble duplisert i delingen.
// ════════════════════════════════════════════════════════

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
  // Spennet står ved siden av statusen: det er det bemanningskurven tegnes
  // over, og mangler det, skal man se hvorfor kurven er kortere enn ventet.
  const spenn = vl.planlagt_slutt
    ? ` · ${_dag(vl.startet)} ${_kl(vl.startet)} – ${_dag(vl.planlagt_slutt)} ${_kl(vl.planlagt_slutt)}`
    : ' · ingen sluttid satt';
  // Merket skal kunne leses på avstand (André, 12. sep. 2026: «noe visuelt
  // som viser at vaktlisten er i planlegging eller i drift»): ikon, navnet
  // på formen i fet, og i drift en pulserende prikk — spennet dempet etter.
  const ikon = vl.i_drift ? 'play-circle-fill' : 'pencil-square';
  el.innerHTML = `<i class="bi bi-${escHtmlValue(ikon)} me-1"></i>`
    + `<strong>${escapeHtml(vl.status_navn)}</strong>`
    + `<span class="vl-status-spenn">${escapeHtml(spenn)}</span>`;
  el.className = 'vl-status ' + (vl.i_drift ? 'vl-drift' : 'vl-planlegging');

  tegnDriftknapp();
}


function tegnDriftknapp() {
  // **Døra til innsjekken står i «Innstillinger»** (André, 12. sep. 2026).
  // Den sto i vaktlinja ved statusmerket til da — men den trykkes to ganger
  // per vakt, og der så den ut som en del av det daglige. Merket i
  // vaktlinja sier fortsatt hvilken form lista er i.
  //
  // Knappen tegnes her og ikke av `gateKnapper()`, fordi teksten skifter med
  // tilstanden: `gateKnapper()` kjører én gang ved sidelasting. Kalles fra
  // `tegnStatus()` og fra `apneVakt()`.
  const el = document.getElementById('vl-drift');
  if (!el) return;
  if (!aktivListe || !kanSkriveAlt()) { el.innerHTML = ''; return; }

  const forklaring = iDrift()
    ? 'Innsjekken er åpen. Ut av drift stenger den; ingen stempler røres.'
    : 'Sett i drift åpner innsjekken — møtt og av vakt — for denne lista.';
  el.innerHTML = (iDrift()
    ? `<button class="btn btn-sm btn-outline-warning" type="button"
               data-action="settDrift" data-arg="stopp">
         <i class="bi bi-pause-circle me-1"></i>Ut av drift
       </button>`
    : `<button class="btn btn-sm btn-success" type="button"
               data-action="settDrift" data-arg="start">
         <i class="bi bi-play-circle me-1"></i>Sett i drift
       </button>`)
    + `<div class="form-text mt-1">${escapeHtml(forklaring)}</div>`;
  tegnFilknapper();
}


function _utsendingTekst(u) {
  // «Sist sendt 12.09 08:04 til 3 mottakere (knapp)» — eller feilen, om
  // den siste ikke gikk. Uten utsending: tom streng.
  if (!u) return '';
  const naar = `${_dag(u.sendt_at)} ${_kl(u.sendt_at)}`;
  const hvordan = u.utloest === 'drift' ? 'ved sett i drift'
    : (u.utloest === 'intervall' ? 'på intervall' : 'på knapp');
  if (u.feil) return `Siste forsøk ${naar} (${hvordan}) feilet: ${u.feil}`;
  const mott = `${u.antall_mottakere} ${u.antall_mottakere === 1 ? 'mottaker' : 'mottakere'}`;
  return `Sist sendt ${naar} til ${mott} (${hvordan}), ${u.antall_rader} skift.`;
}


function tegnFilknapper() {
  // **Reserven** (12. sep. 2026): vaktlista som selvstendig HTML-fil. «Last
  // ned» henter fila til egen maskin; «Send på e-post» sender den til
  // mottakerne admin har satt. Begge for `skriv_full` — fila bærer
  // telefonnumre for hele vakta. Tegnes fra `tegnDriftknapp()`, av samme
  // grunn som den: teksten skifter med tilstanden.
  const el = document.getElementById('vl-fil');
  if (!el) return;
  if (!aktivListe || !kanSkriveAlt()) { el.innerHTML = ''; return; }
  const vl = aktivListe.vaktliste;
  const harMottakere = (vl.fil_mottakere || 0) > 0;
  // Automatikken, som admin har satt den: ved sett i drift, og/eller hvert
  // N. minutt i drift (bare ved endringer, om det er krysset av).
  const auto = [];
  if (vl.fil_ved_drift) auto.push('ved sett i drift');
  if (vl.fil_intervall_min > 0) {
    auto.push(`hvert ${vl.fil_intervall_min}. min i drift`
              + (vl.fil_bare_endret ? ' når lista er endret' : ''));
  }
  const mottakere = harMottakere
    ? `${vl.fil_mottakere} ${vl.fil_mottakere === 1 ? 'mottaker' : 'mottakere'} er satt`
      + (auto.length ? `; sendes også ${auto.join(' og ')}.` : '.')
    : 'Ingen mottakere er satt — global admin setter dem under Portalinnstillinger.';
  const sist = _utsendingTekst(vl.siste_utsending);
  el.innerHTML = `
    <a class="btn btn-sm btn-outline-secondary me-1" href="/vaktliste/api/vaktlister/${escHtmlValue(vl.id)}/fil/">
      <i class="bi bi-download me-1"></i>Last ned som fil
    </a>
    <button class="btn btn-sm btn-outline-secondary" type="button"
            data-action="sendVaktlistefil"${harMottakere ? '' : ' disabled'}>
      <i class="bi bi-envelope me-1"></i>Send på e-post
    </button>
    <div class="form-text mt-1">Reserve når portalen er nede: én fil med navn, korps, rolle,
      skift, telefon og ISSI. ${escapeHtml(mottakere)}${sist ? ' ' + escapeHtml(sist) : ''}</div>`;
}


async function sendVaktlistefil() {
  if (!aktivListe) return;
  const vl = aktivListe.vaktliste;
  const antall = vl.fil_mottakere || 0;
  // Bekreftelse: fila går ut av portalen, og hver adresse er en kopi.
  if (!confirm(`Sende vaktlista for «${vl.vakt_navn}» til ${antall} `
             + `${antall === 1 ? 'mottaker' : 'mottakere'}? Fila inneholder navn og telefonnumre.`)) return;
  skjulPanelfeil();
  const res = await apiFetch(`/vaktliste/api/vaktlister/${vl.id}/fil/send/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke sende vaktlista.');
  }
  await lastListe(vl.id);
}


function _posterFor(ressursId) {
  return (aktivListe.vaktposter || []).filter((vp) => vp.ressurs_id === ressursId);
}


function _ressurserIGruppe(gruppeId) {
  // Rekkefølgen er den serveren sender — `Ressurs.rekkefolge`, satt til
  // opprettelsesrekkefølgen. Den som bygger vakten legger inn bilene i den
  // rekkefølgen hun tenker på dem.
  return (aktivListe.ressurser || []).filter((r) => r.gruppe_id === gruppeId);
}


function _grupperMedRessurser() {
  // Bare grupper som faktisk har noe i seg blir faner. En tom fane per
  // ubrukt gruppe er seks faner på en vakt med to ressurser.
  return (aktivListe.grupper || [])
    .filter((g) => _ressurserIGruppe(g.id).length);
}


function gruppaHarPlass(g) {
  // **Noen grupper finnes i ett eksemplar.** Samleplassen og KO er
  // samlingspunkt for flere korps, ikke flåter — «Ny samleplass» inviterer
  // til å lage noe som ikke finnes. Den *første* må man fortsatt kunne
  // opprette, så plassen tar slutt først når den ene står der.
  //
  // Regelen står som én funksjon fordi den har to lesere: knappen inne i
  // fanen og nedtrekket i «Ny ressurs». Skjulte vi bare knappen, kunne man
  // fortsatt velge gruppa i nedtrekket — og da var regelen halvveis, som er
  // verre enn ingen regel.
  if (!g) return false;
  return g.flere_enheter !== false || !_ressurserIGruppe(g.id).length;
}


function visFane(id) {
  aktivFane = id;
  // Registeret hentes først når noen faktisk ber om det. Det er globalt og
  // uavhengig av vaktlista, så det koster ingenting å utsette.
  if (id === MANNSKAP && !register) { lastRegister(); }
  if (id === BELASTNING && !belastning) { lastBelastning(); }
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


function skrivUt() {
  // Nettleserens egen utskrift. `@media print` i vaktliste.css skjuler nav,
  // faner og knapper, så det som kommer ut er lista og ingenting annet.
  window.print();
}


function _mannskapsfane() {
  // Antallet er registeret, ikke vaktas påmeldte: fanen *er* registeret.
  return {
    id: MANNSKAP, navn: 'Mannskap', ikon: 'person-vcard',
    antall: register ? register.mannskap.length : null,
  };
}


function tegnFaner() {
  const el = document.getElementById('vl-faner');
  if (!el) return;

  // **Uten vaktliste står Mannskap alene.** Korps må inn før mannskap, og
  // mannskap før noen kan settes på vakt. Var fanen borte til den første
  // vaktlista fantes, sto man fast på skritt én.
  if (!aktivListe) {
    el.innerHTML = _fanerad([_mannskapsfane()], '');
    return;
  }

  const faner = [{ id: OVERSIKT, navn: 'Oversikt', ikon: 'list-ul', antall: null }];
  // **Én fane per gruppe.** «Ambulanse» er alle ambulansene, ikke én av dem.
  _grupperMedRessurser().forEach((g) => {
    const ressurser = _ressurserIGruppe(g.id);
    faner.push({
      id: String(g.id), navn: g.navn, ikon: g.ikon,
      antall: ressurser.reduce((n, r) => n + _posterFor(r.id).length, 0),
    });
  });
  // **Planleggingstallene er lista regnet sammen** (§8b), ikke en ny kilde.
  // Fanen står ved siden av «Oversikt» fordi det er samme spørsmål sett fra
  // en annen kant: oversikten er hvem som står hvor, denne er hva det koster
  // dem.
  faner.push({
    id: BELASTNING, navn: 'Planlegging', ikon: 'graph-up',
    antall: belastning ? belastning.sammendrag.personer : null,
  });

  // **«Tilstede nå» finnes bare i drift.** I planlegging er den tom per
  // definisjon — ingen er stemplet — og en fane som alltid sier null er en
  // fane man slutter å se.
  if (iDrift()) {
    faner.push({
      id: TILSTEDE, navn: 'Tilstede nå', ikon: 'person-check',
      antall: _tilstede().length,
    });
  }

  faner.push({
    id: IKKE_PLASSERT, navn: 'Ikke plassert', ikon: 'person-dash',
    antall: _ikkePlassert().length,
  });

  // **«Mitt korps»** (11. sep. 2026): plassene korpset har ansvar for, på
  // tvers av ressursene. Tallet er det som gjenstår å dekke. Finnes bare
  // når det er et korps å vise — badgen, eller korpsvelgeren.
  if (_mittKorpsId() != null) {
    const mine = _synligePoster(aktivListe.alle_vaktposter || aktivListe.vaktposter, _mittKorpsId());
    faner.splice(2, 0, {
      id: MITT_KORPS, navn: 'Mitt korps', ikon: 'people-fill',
      antall: mine.filter((vp) => vp.ledig).length,
    });
  }

  // **Mannskap er en ekte fane, ikke en lenke.** Den var en lenke ut til
  // /vaktliste/registre/, og et klikk kostet deg plassen i planleggingen —
  // mens mannskap og ressurser er nettopp de to man veksler mellom.
  faner.splice(1, 0, _mannskapsfane());

  // «Ny ressurs» sist. Bygges her og ikke i malen fordi den skal stå etter
  // faner som kommer fra data; `gateKnapper()` rekker ikke over markup som
  // tegnes på nytt ved hvert panelbytte, så tilgangen sjekkes her.
  const nyRessurs = kanLede()
    ? `<button class="vl-fane vl-fane-ny" type="button"
               data-action="apneNyRessurs">
         <i class="bi bi-plus-lg me-1"></i>Ny ressurs
       </button>`
    : '';

  el.innerHTML = _fanerad(faner, nyRessurs);
}


function _fanerad(faner, hale) {
  return faner.map((f) => {
    const aktiv = f.id === aktivFane ? ' active' : '';
    const antall = f.antall === null ? ''
      : `<span class="vl-antall">${escHtmlValue(f.antall)}</span>`;
    return `<button class="vl-fane${aktiv}" data-action="visFane" data-arg="${escHtmlValue(f.id)}">`
         + `<i class="bi bi-${escHtmlValue(f.ikon)} me-1"></i>${escapeHtml(f.navn)}${antall}</button>`;
  }).join('') + hale;
}


function tegnPanel() {
  const el = document.getElementById('vl-panel');
  if (!el) return;

  // Søkefeltet hører til mannskapsfanen og ligger UTENFOR panelet med vilje:
  // panelet tegnes på nytt ved hvert tastetrykk, og et input inni ville mistet
  // fokus etter første bokstav.
  document.getElementById('vl-verktoy')
    ?.classList.toggle('d-none', aktivFane !== MANNSKAP);

  // **Mannskapsfanen står også uten vaktliste** — se `tegnFaner()`.
  if (aktivFane === MANNSKAP) { el.innerHTML = mkMannskap(); return; }
  if (!aktivListe) { el.innerHTML = ''; return; }

  if (aktivFane === OVERSIKT) { el.innerHTML = mkOversikt(); return; }
  if (aktivFane === BELASTNING) { el.innerHTML = mkBelastning(); return; }
  if (aktivFane === TILSTEDE) { el.innerHTML = mkTilstede(); return; }
  if (aktivFane === IKKE_PLASSERT) { el.innerHTML = mkIkkePlassert(); return; }
  if (aktivFane === MITT_KORPS) { el.innerHTML = mkMittKorps(); return; }

  const gruppe = (aktivListe.grupper || [])
    .find((g) => String(g.id) === String(aktivFane));
  el.innerHTML = gruppe ? mkGruppe(gruppe)
    : '<div class="vl-tom">Gruppa finnes ikke lenger.</div>';
}


// ── Byggere (alt escapes — se filhodet) ──────────────────────────────────

function _iso16(iso) {
  // `datetime-local` vil ha «2026-10-03T08:00» i LOKAL tid. `toISOString()`
  // ville gitt UTC og flyttet skiftet to timer om sommeren.
  const d = _d(iso);
  if (!d) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
       + `T${p(d.getHours())}:${p(d.getMinutes())}`;
}


function opptattPaaPlassen(vp, poster) {
  // **Hvem kan ikke settes på denne plassen?** De som alt står på samme
  // ressurs til samme starttid.
  //
  // Databasen har en unik-skranke på `(ressurs, mannskap, fra_tid)`, og
  // nedtrekket tilbød fram til 14. sep. 2026 *alle* i registeret. Valgte man
  // en som alt sto der, svarte serveren 400 «Personen står allerede på denne
  // ressursen fra dette tidspunktet» — altså et valg som ikke kunne gjennom­
  // føres, tilbudt som om det kunne. Portalens egen regel sier det motsatte:
  // **en knapp som fører til en vegg er verre enn ingen knapp.**
  //
  // Egen funksjon, ikke en `filter` inne i byggeren, av samme grunn som
  // `klikkSkalKjore()`: en regel som ikke lar seg kalle, lar seg ikke prøve.
  const ut = new Set();
  (poster || []).forEach((p) => {
    if (p.id === vp.id) return;                     // raden selv teller ikke
    if (p.mannskap_id == null) return;              // ledige plasser sperrer ingen
    if (p.ressurs_id !== vp.ressurs_id) return;     // annen ressurs er fritt fram
    if (p.fra_tid !== vp.fra_tid) return;           // annen starttid er en annen rad
    ut.add(p.mannskap_id);
  });
  return ut;
}


function _fyllValgFor(vp, kanRedigere) {
  // Å fylle plassen er én feltendring, ikke en flytting mellom to tabeller —
  // det er hele grunnen til at en ledig plass er en `Vaktpost` uten person.
  if (!kanRedigere) return '<span class="vl-ledigtekst">Ledig plass</span>';
  // `alle_vaktposter` er alt serveren sendte; `vaktposter` er det korpsfilteret
  // slapp gjennom. Skranken er en databasekjensgjerning uavhengig av hvem som
  // ser raden, så den ufiltrerte lista er riktig kilde — samme idiom som
  // `mkMittKorps()`. (Serveren filtrerer i tillegg sitt eget svar, så en
  // korps-bruker kan fortsatt treffe veggen. Da vises meldingen, som nå rulles
  // fram — se `rullTilFeil()`.)
  const opptatt = opptattPaaPlassen(vp, aktivListe.alle_vaktposter || aktivListe.vaktposter);
  const valg = ['<option value="">— ledig plass —</option>'].concat(
    (aktivListe.mannskap || [])
      .filter((m) => !opptatt.has(m.id))
      .map((m) =>
        `<option value="${escHtmlValue(m.id)}">${escapeHtml(m.navn + ' — ' + m.korps_navn)}</option>`
      )).join('');
  return `<select class="vl-celle vl-fyll" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="mannskap_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function rollerForGruppe(gruppeId, valgtId) {
  // **Rollen hører til ressursgruppa** (30. aug. 2026). «Sjåfør» gir mening
  // på hver ambulanse og ikke på samleplassen, og et globalt register ville
  // tvunget hver rolle inn i hvert nedtrekk.
  //
  // Tre ledd, og hvert av dem er en egen feil å gjøre:
  //   · gruppa       — ellers tilbys samleplassens roller på bilen
  //   · `er_aktiv`   — en pensjonert rolle skal ikke kunne velges på nytt
  //   · den valgte   — uten den forsvinner en deaktivert rolle fra sin egen
  //                    rad ved neste tegning, og velges bort i stillhet
  return (aktivListe.roller || []).filter((r) =>
    r.id === valgtId || (r.gruppe_id === gruppeId && r.er_aktiv));
}


function _plassKorps(vp) {
  // Reservasjonen på en ledig plass. Bare den som deler ut kan endre den —
  // kunne korps-brukeren, kunne hun tildelt seg selv en plass. Andre ser
  // hvem plassen tilhører, som tekst.
  // Tre tilstander (André, 12. sep. 2026): ett korps, **åpen for alle** (alle
  // ser og kan fylle — `alle_korps`), eller **planlagt** — lederens kladd,
  // som korps-brukerne ikke ser. Planlagt går én vei: valget finnes bare
  // så lenge plassen står der, og serveren avviser veien tilbake.
  const valgt = vp.alle_korps ? 'alle'
    : (vp.plass_korps_id != null ? vp.plass_korps_id
      : (vp.reservert_korps_id != null ? vp.reservert_korps_id : ''));
  if (!kanSkriveAlt()) {
    if (vp.alle_korps) return '<span class="vl-meta">Åpen for alle</span>';
    const k = (aktivListe.korps || []).find((x) => x.id === valgt);
    return `<span class="vl-meta">${escapeHtml(k ? (k.kortnavn || k.navn) : '—')}</span>`;
  }
  const alleMerke = valgt === 'alle' ? ' selected' : '';
  const planlagt = valgt === '' ? ['<option value="" selected>Planlagt</option>'] : [];
  const valg = planlagt.concat([
                `<option value="alle"${alleMerke}>Åpen for alle</option>`]).concat(
    (aktivListe.korps || []).map((k) => {
      const merke = k.id === valgt ? ' selected' : '';
      return `<option value="${escHtmlValue(k.id)}"${merke}>`
           + `${escapeHtml(k.kortnavn || k.navn)}</option>`;
    })).join('');
  return `<select class="vl-celle" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="korps_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function _rolleValg(vp, ressurs, kanRedigere) {
  // Rollen redigeres i raden. Før lå den bare i «Sett på vakt»-modalen, og
  // å endre den krevde å fjerne skiftet og sette det opp på nytt — samme
  // person kan være sjåfør på bilen én vakt og lagleder på samleplass neste.
  if (!kanRedigere) {
    return escapeHtml(vp.rolle || '—');
  }
  const valg = ['<option value="">—</option>'].concat(
    rollerForGruppe(ressurs.gruppe_id, vp.rolle_id).map((r) => {
      const valgt = r.id === vp.rolle_id ? ' selected' : '';
      return `<option value="${escHtmlValue(r.id)}"${valgt}>${escapeHtml(r.navn)}</option>`;
    })).join('');
  return `<select class="vl-celle" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="rolle_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function mkGruppe(gruppe) {
  // **Fanen er oversikten over gruppa.** Kurven øverst summerer akkurat de
  // ressursene som står under den — det er hele grunnen til at fanen er
  // gruppa og ikke den enkelte bilen.
  const ressurser = _ressurserIGruppe(gruppe.id);

  // **Knappen for å legge til én til står HER, i gruppa.** Den lå bare sist i
  // fanerekka, og da var det usynlig at fanen «Ambulanse» rommer bil A, bil B
  // og bil C — man så én rad med knapper og trodde gruppa *var* bilen. Det
  // kostet André en time og meg tre runder.
  const leggTil = kanLede() && gruppaHarPlass(gruppe)
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneNyRessurs" data-arg="${escHtmlValue(gruppe.id)}">
         <i class="bi bi-plus-lg me-1"></i>Ny ${escapeHtml(gruppe.navn)}
       </button>`
    : '';

  if (!ressurser.length) {
    return `
      <div class="vl-kort">
        <div class="vl-kort-topp">
          <span class="vl-kort-tittel">
            <i class="bi bi-${escHtmlValue(gruppe.ikon)} me-1"></i>${escapeHtml(gruppe.navn)}
          </span>
          ${leggTil}
        </div>
        <div class="vl-tom">
          Ingen ${escapeHtml(gruppe.navn)} satt opp ennå. Hver enhet er sin egen
          rad her — én per bil, lag eller post — med egne skift og egen kobling
          mot oppdragsmodulen.
        </div>
      </div>`;
  }

  const hode = `
    <div class="vl-kort vl-gruppehode">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">
          <i class="bi bi-${escHtmlValue(gruppe.ikon)} me-1"></i>${escapeHtml(gruppe.navn)}
          <span class="vl-meta">${escHtmlValue(ressurser.length)} ${
            ressurser.length === 1 ? 'enhet' : 'enheter'} ·
            ${escapeHtml(_telling(_posterIGruppe(gruppe.id),
                                  _tidsblokker(_posterIGruppe(gruppe.id)).length))}</span>
        </span>
        ${leggTil}
      </div>
    </div>`;

  // **I drift står kurven nederst** (prosjektleder, 11. sep. 2026). I
  // planlegging er kurven det man ser først — hullene er jobben. I drift er
  // spørsmålet «hvem har møtt?», og da skal stemplene stå øverst; kurven er
  // fortsatt der, for den som vil se resten av vakten, men under.
  const kurve = mkGruppekurve(gruppe);
  const kort = _gruppedagbolker(ressurser);
  return hode + (iDrift() ? kort + kurve : kurve + kort);
}


function _gruppedagbolker(ressurser) {
  // **Dagen ytterst, som i «Oversikt»** (André, 15. sep. 2026). Fanen var en
  // stabel ressurskort med dagrader inni; nå er den en stabel dager med
  // ressurskort inni. De to flatene leses da likt, og den som planlegger ser
  // hele dagen på tvers av bilene uten å lese ni tabeller for å finne den.
  //
  // **`map(mkRessurs)` ville sendt indeksen som `apen`.** Den formen sto her
  // og var harmløs så lenge byggeren tok ett argument; den sluttet å være det
  // i det øyeblikket den tok flere.
  // Skiftene leses i **serverens** rekkefølge (`fra_tid`), ikke ressurs for
  // ressurs. Samlet per ressurs ville rekkefølgen i dagbolken vært garantert
  // av hvordan lista ble bygget, ikke av regelen under — og en mutasjon som
  // fjernet regelen ville gått grønn.
  const idn = new Set(ressurser.map((r) => r.id));
  const alle = (aktivListe.vaktposter || []).filter((vp) => idn.has(vp.ressurs_id));
  const bolker = _grupperPaaDag(alle).map((dag) => {
    const perRessurs = new Map();
    dag.poster.forEach((vp) => {
      if (!perRessurs.has(vp.ressurs_id)) perRessurs.set(vp.ressurs_id, []);
      perRessurs.get(vp.ressurs_id).push(vp);
    });
    // Rekkefølgen er ressursenes, ikke postenes — fanerekka skal ikke hoppe
    // fra dag til dag etter hvem som tilfeldigvis har det første skiftet.
    const kort = ressurser
      .filter((r) => perRessurs.has(r.id))
      .map((r) => mkRessurs(r, ressursErApen(r), perRessurs.get(r.id)))
      .join('');
    return `
      <section class="vl-dagbolk">
        <h3 class="vl-dagtittel">${escapeHtml(_dagtekst(dag.fra_tid))}</h3>
        ${kort}
      </section>`;
  });

  // **En ressurs uten skift hører ikke til noen dag, og må likevel nås.**
  // Uten denne bolken kunne ingen sette opp den første vakta på en ny bil —
  // kortet med «Opprett vakt» ville ikke finnes noe sted.
  const tomme = ressurser.filter((r) => !_posterFor(r.id).length);
  if (tomme.length) {
    bolker.push(`
      <section class="vl-dagbolk">
        <h3 class="vl-dagtittel vl-utenskift">Uten skift</h3>
        ${tomme.map((r) => mkRessurs(r, ressursErApen(r), [])).join('')}
      </section>`);
  }
  return bolker.join('');
}


function _driftrad(vp, r, kanRore) {
  // **Drift er planleggingsraden pluss innsjekken** (André, 12. sep. 2026:
  // «Kunne redigere mannskaper selv om vi er i drift modus»). Fram til da
  // var driftraden en egen, smal form uten tidsfelt, kompetanse og merknad
  // — redigering gikk gjennom blyanten. Det holdt ikke i bruk: folk uteblir
  // og bytter midt i vakta, og da skal raden kunne rettes der den står,
  // som i planlegging. Prisen er bredden: tabellen ruller sidelengs på en
  // laptop, og stempelet står først så det er det man ser.
  return `
    <tr class="${escHtmlValue(_radklasse(vp))}">
      <td class="vl-stempelcelle">${_stempelknapper(vp)}</td>
      ${_plancellene(vp, r, kanRore)}
    </tr>`;
}


function _radklasse(vp) {
  // Tilstanden skal synes på raden, ikke bare i en kolonne. Under drift er
  // det «hvem mangler» man leter etter, og da er det fargen man skummer.
  if (vp.ledig) return 'vl-ledig';
  if (!iDrift()) return '';
  if (vp.tilstede) return 'vl-tilstede';
  if (vp.av_vakt_at) return 'vl-avgatt';
  return '';
}


function _stempelknapper(vp) {
  // **Cella er handlingen, ikke en knapp blant flere.** Første utgave la
  // stempelet i handlingskolonnen ytterst til høyre: 45 × 21 px, tusen
  // piksler fra navnet man nettopp leste, bak en sidescroll — den minste
  // kontrollen på raden, der den skulle vært den største. Nå står den først
  // og fyller cella.
  //
  // **Én knapp, ikke to.** Raden er i nøyaktig én tilstand: «Møtt» på en som
  // alt har møtt gjør enten ingenting eller noe hun ikke ba om.
  //
  // Uten stemplerett vises **statusen** i stedet for en knapp. `les` ser hele
  // lista, og «hvem har møtt» er det samme spørsmålet enten man kan svare på
  // det eller ikke.
  if (vp.ledig) return '<span class="vl-meta">—</span>';

  // Et stempel som står i kø (offline drift) vises som satt, men merket.
  const koKlasse = vp.i_ko ? ' vl-i-ko' : '';
  const naar = (iso) => `<span class="vl-stempeltid${koKlasse}"${vp.i_ko ? ' title="Venter på å bli sendt"' : ''}>${escapeHtml(_kl(iso))}</span>`;
  if (!kanStemple()) {
    if (vp.av_vakt_at) return `<span class="vl-meta">Av vakt</span>${naar(vp.av_vakt_at)}`;
    if (vp.mott_at) return `<span class="vl-meta">Møtt</span>${naar(vp.mott_at)}`;
    return '<span class="vl-meta">Ikke møtt</span>';
  }

  // **Én `data-action` per overgang**, ikke én generisk med overgangen i et
  // attributt. Klikkdelegeringen i portal-utils.js sender ett argument —
  // `data-id` — og å utvide den for én sides skyld ville rørt hver side i
  // portalen. Navnene speiler `services.STEMPLINGER`, og
  // `StemplingsnavnTests` holder de to listene like.
  const knapp = (handling, etikett, stil, ikon) =>
    `<button class="btn ${stil} vl-stempel" type="button"
             data-action="${escHtmlValue(handling)}" data-id="${escHtmlValue(vp.id)}">
       <i class="bi bi-${escHtmlValue(ikon)} me-1"></i>${escapeHtml(etikett)}
     </button>`;
  const angre = (handling, tittel) =>
    `<button class="btn btn-sm btn-link vl-angre" type="button"
             title="${escHtmlValue(tittel)}" aria-label="${escHtmlValue(tittel)}"
             data-action="${escHtmlValue(handling)}" data-id="${escHtmlValue(vp.id)}">
       <i class="bi bi-arrow-counterclockwise"></i>
     </button>`;

  if (!vp.mott_at) {
    return knapp('stemplMott', 'Møtt', 'btn-success', 'box-arrow-in-right');
  }
  if (!vp.av_vakt_at) {
    return knapp('stemplAvVakt', 'Av vakt', 'btn-outline-warning', 'box-arrow-right')
         + `<div class="vl-stempeltid">Møtt ${escapeHtml(_kl(vp.mott_at))}`
         + angre('angreMott', 'Angre møtt') + '</div>';
  }
  return `<span class="vl-meta">Av vakt</span>`
       + `<div class="vl-stempeltid">${escapeHtml(_kl(vp.av_vakt_at))}`
       + angre('angreAvVakt', 'Angre av vakt') + '</div>';
}


function _varighet(vp) {
  // **Timer per skift, som en egen kolonne.** Andrés bestilling, og den er
  // det eneste tallet man ellers må regne ut i hodet for hver rad — «20:00
  // til 04:30» er ikke åtte timer, og kolonnen er det man summerer når man
  // vurderer om noen står for lenge.
  const timer = _skifttimer(vp);
  return timer == null ? '—' : `${_tall(timer)} t`;
}


function _skifttimer(vp) {
  // Skiftets lengde i timer som tall, eller `null` når spennet mangler
  // eller er negativt. Et skift under oppsett kan mangle den ene tida, og
  // serveren avviser et negativt spenn — men raden tegnes før svaret kommer.
  const fra = _d(vp.fra_tid);
  const til = _d(vp.til_tid);
  if (!fra || !til) return null;
  const timer = (til.getTime() - fra.getTime()) / 3600000;
  return timer > 0 ? timer : null;
}


function _sumTimer(poster) {
  // Summen av skiftene, som tall. Skift uten gyldig spenn teller null —
  // de vises som «—» i raden, og en strek har ingen timer å legge til.
  // **Probono teller heller ikke** (11. sep. 2026): skiftet går, men
  // timene er ikke organisasjonens. Speiler `belastning_per_person`.
  return poster.reduce((sum, vp) => sum + (vp.probono ? 0 : (_skifttimer(vp) || 0)), 0);
}


function _probonoMerke(vp) {
  // Merket ved navnet, ikke i timekolonnen: timene står der fortsatt —
  // det er summene som hopper over dem, og det skal man kunne se hvorfor.
  return vp.probono ? ' <span class="vl-merkelapp vl-probono">Probono</span>' : '';
}


function _planrad(vp, r, kanRore) {
  return `
    <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
      ${_plancellene(vp, r, kanRore)}
    </tr>`;
}


function _plancellene(vp, r, kanRore) {
  // **Regnearkradens celler.** Alt redigeres der det står: tider, rolle,
  // merknad og — for en ledig plass — hvem som skal fylle den. Lå inne i
  // `mkRessurs()` fram til 11. sep. 2026; hevet ut da radene fikk
  // blokklinjer over seg. Cellene uten `<tr>`, fordi driftraden (12. sep.
  // 2026) er de samme cellene med stempelet foran.
  // Merkelappene ligger i en wrapper, ikke rett i cella: `display: flex`
  // på en `<td>` tar cella ut av tabellens boksmodell, og da forskyves
  // kolonnene etter den i forhold til overskriftene.
  const merkelapper = (vp.kompetanser || []).map((k) =>
    `<span class="vl-merkelapp">${escapeHtml(k)}</span>`).join('');
  const komp = merkelapper
    ? `<div class="vl-merkelapper">${merkelapper}</div>`
    : '<span class="vl-meta">—</span>';

  // **Dagen står i tidsfeltet, ikke i en egen kolonne.** Kolonnen var
  // et tredje sted å lese for å forstå én rad, og `datetime-local` bærer
  // datoen selv — den manglet bare ukedagen, som er den man planlegger
  // etter. Nå står «lør.» under feltet den hører til.
  const tid = (felt) => {
    const merke = _d(vp[felt])
      ? `<span class="vl-dagmerke">${escapeHtml(_dag(vp[felt]))}</span>` : '';
    const innhold = kanRore
      ? `<input type="datetime-local" step="300" class="vl-celle"
                value="${escHtmlValue(_iso16(vp[felt]))}"
                data-action="endreVaktpost" data-hendelse="change"
                data-felt="${escHtmlValue(felt)}" data-id="${escHtmlValue(vp.id)}">`
      : escapeHtml(_kl(vp[felt]));
    return `<div class="vl-tidcelle">${innhold}${merke}</div>`;
  };

  const merknad = kanRore
    ? `<input type="text" class="vl-celle" maxlength="255"
              value="${escHtmlValue(vp.merknad || '')}" placeholder="—"
              data-action="endreVaktpost" data-hendelse="change"
              data-felt="merknad" data-id="${escHtmlValue(vp.id)}">`
    : escapeHtml(vp.merknad || '—');

  // **Rediger, ikke slett.** Å bytte person på et skift var før å fjerne
  // raden og sette den opp på nytt — og da mistet man tidene og rollen
  // som allerede sto der. Sletting ligger nå inne i vinduet, bak en
  // bekreftelse, slik den gjør på ressursen.
  const redigerPost = kanRore
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               title="Rediger skiftet" aria-label="Rediger skiftet"
               data-action="apneRedigerVaktpost" data-id="${escHtmlValue(vp.id)}"><i class="bi bi-pencil"></i></button>`
    : '';


  // En ledig plass er raden uten person. Den skal se ut som noe som
  // gjenstår — ikke som en rad der navnet mangler ved en feil.
  const navnCelle = vp.ledig
    ? _fyllValgFor(vp, kanRore || kanBemannePlass(vp, r)) + _probonoMerke(vp)
    : escapeHtml(vp.navn) + _probonoMerke(vp);

  // **Korpskolonnen svarer på to ulike spørsmål.** Står det en person
  // der, er det *hennes* korps — et faktum. Er plassen ledig, er det
  // korpset plassen er *satt av til* — en beslutning, og den kan endres
  // av den som deler ut. En samleplass har gjerne to plasser til
  // Haugesund og to til Karmøy.
  const korpsCelle = vp.ledig
    ? _plassKorps(vp)
    : escapeHtml(vp.korps_kort || '—');

  // Rekkefølgen er lesestrekket: hvem, hvorfra, hvilken rolle, når, hvor
  // lenge — og først da kompetansen, som er det man vurderer laget på
  // når resten står. Merknaden sist, fordi den er unntaket.
  return `
      <td class="vl-navn">${navnCelle}</td>
      <td>${korpsCelle}</td>
      <td>${_rolleValg(vp, r, kanRore)}</td>
      <td>${tid('fra_tid')}</td>
      <td>${tid('til_tid')}</td>
      <td class="vl-timer">${escapeHtml(_varighet(vp))}</td>
      <td class="vl-kompcelle">${komp}</td>
      <td>${merknad}</td>
      <td class="vl-handling">${redigerPost}</td>`;
}


function ressursErApen(r) {
  // **Standarden er gruppas, valget er brukerens.** Har hun trykket på
  // kortet, gjelder det hun valgte; ellers er en gruppe med flere enheter
  // sammenslått og en gruppe med én åpen.
  //
  // André ba om «alle minimert som standard», og snevret det 15. sep. 2026 til
  // «bare når gruppa har mer enn én»: en vakt med én ambulanse ville ellers
  // kostet et klikk hver gang for å se det eneste som er der.
  // `_blokkerMedDager()` hadde presedensen for samme resonnement — men gikk
  // motsatt vei samme dag, og det er verdt å merke seg at de to nå skiller
  // lag: dagoverskriften koster én linje, et sammenslått kort koster et klikk.
  if (ressursApen.has(r.id)) return ressursApen.get(r.id);
  return _ressurserIGruppe(r.gruppe_id).length <= 1;
}


function mkRessurs(r, apen = true, egne = null) {
  // `apen` er gruppas avgjørelse, ikke ressursens — `mkGruppe()` vet hvor
  // mange søsken kortet har. Standardverdien `true` er for de stedene som
  // tegner ett kort alene; de har ingen gruppe å spørre.
  //
  // `egne` er skiftene kortet skal vise. **Dagbolken sender sin egen dags
  // skift** (André, 15. sep. 2026: «i ressursgruppene må det være likt som
  // oversikt — ressurser per dag»), så ett kort dekker én dag. Uten den
  // tegnes alle ressursens skift.
  const poster = egne || _posterFor(r.id);
  const kanRore = kanBemanne(r);
  // Per rad, ikke per ressurs: egen person på andres plass er egen rad
  // (`kanRoreRad`), og en ledig plass satt av til korpset er hennes å fylle.

  const korpsmerke = r.korps_navn
    ? `<span class="vl-merkelapp vl-korps">${escapeHtml(r.korps_navn)}</span>`
    : '<span class="vl-merkelapp vl-ureservert">Ureservert</span>';
  // **Koblingen vises også når den mangler.** Merkelappen sto bare der bilen
  // *var* koblet, så den som ikke hadde koblet noe så ingenting — og kunne
  // ikke vite at koblingen finnes per bil i det hele tatt. Nå står den som en
  // tom plass som ber om å fylles, for den som har lov til å fylle den.
  const enhetsmerke = r.enhet_navn
    ? `<span class="vl-merkelapp vl-enhet">
         <i class="bi bi-broadcast me-1"></i>${escapeHtml(r.enhet_navn)}
       </span>`
    : (kanLede()
        ? `<button class="vl-merkelapp vl-enhet-tom" type="button"
                   title="Koble denne enheten til oppdragsmodulen"
                   data-action="apneRessurs" data-id="${escHtmlValue(r.id)}">
             <i class="bi bi-broadcast me-1"></i>Ikke koblet
           </button>`
        : '');

  const settKnapp = kanRore
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneVaktpost" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-plus-lg me-1"></i>Opprett vakt
       </button>` : '';

  // **Rollene administreres inne i ressursen**, ikke i toppen av siden.
  // Trenger man «Sjåfør» mens man bemanner ambulansen, skal den lages der —
  // og den blir gruppas, så den finnes på hver ambulanse med én gang.
  const rolleKnapp = kanLede()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneRoller" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-person-badge me-1"></i>Roller
       </button>` : '';

  // **Sletting ligger bak «Rediger», ikke i toppen.** En naken «Fjern
  // ressurs» ved siden av «Sett på vakt» gjør det for lett å rive bort hele
  // bilen med bemanningen på — CASCADE tar skiftene.
  const redigerKnapp = kanLede()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneRessurs" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-pencil me-1"></i>Rediger
       </button>` : '';
  const knapper = settKnapp + rolleKnapp + redigerKnapp;

  // **Tabellen har én form, og drift legger innsjekken foran.** I
  // planlegging er den et regneark: radene er skift, kolonnene er det man
  // sammenligner på tvers av dem, og alt redigeres der det står. Under
  // drift står stempelet først i raden — resten er som før (André, 12. sep.
  // 2026). Se `_driftrad()`.
  // **Sammenslått: hodet, tallene og knappene — ikke tabellen.** Knappene blir
  // stående nettopp for at et sammenslått kort ikke skal være en blindvei:
  // «Rediger», «Roller» og «Opprett vakt» virker uten å åpne det først.
  const blokker = _tidsblokker(poster);
  const ledige = poster.filter((vp) => vp.ledig).length;
  // Bygget med `+`, ikke i en template-literal: XSS-skanneren leser hvert
  // `${}` i byggerne, og et tall den ikke kan se er escapet er et funn den må
  // avvise. Samme grep som `_blokklinje()`.
  const deler = [_telling(poster, blokker.length)];
  if (ledige) deler.push(ledige + (ledige === 1 ? ' ledig' : ' ledige'));
  deler.push(_tall(_sumTimer(poster)) + ' t');
  const sammendrag = poster.length ? deler.join(' · ') : 'Ingen satt opp ennå';
  const vippe = `
          <button type="button" class="vl-vippe" data-action="veksleRessurs"
                  data-id="${escHtmlValue(r.id)}"
                  aria-expanded="${escHtmlValue(apen ? 'true' : 'false')}"
                  title="${escHtmlValue(apen ? 'Slå sammen' : 'Vis skiftene')}">
            <i class="bi bi-chevron-${escHtmlValue(apen ? 'down' : 'right')}"></i>
          </button>`;

  const drift = iDrift();
  // **Blokker, ikke bare rader.** Skift med samme fra–til samles under én
  // blokklinje som bærer tiden, timene og antallet — se `_tidsblokker()`.
  // Raden under er enten regnearket (`_planrad`) eller driftraden.
  const rad = (vp) => (drift ? _driftrad(vp, r, kanRoreRad(vp, r, kanRore))
                              : _planrad(vp, r, kanRoreRad(vp, r, kanRore)));
  const kolonner = drift ? 10 : 9;
  // `_blokkrader`, ikke `_blokkerMedDager`: **i gruppefanen er dagen en
  // seksjonsoverskrift, aldri en rad.** En dagrad inni kortet ville gjentatt
  // tittelen rett over det. «Mitt korps» er den andre flaten og beholder
  // dagrader, fordi den har én tabell på tvers av ressursene.
  const kropp = poster.length
    ? _blokkrader(blokker, kolonner, rad)
    : `<tr><td colspan="${escHtmlValue(kolonner)}" class="vl-tom">Ingen satt opp ennå.</td></tr>`;

  // Tabellhodet heves ut hit framfor å stå som en ternær med to
  // template-literaler inne i en tredje: den formen er vanskelig å lese, og
  // XSS-skanneren i `tests_xss.py` kan ikke se inn i den.
  const tabellklasse = drift ? 'vl-tabell vl-tabell-drift' : 'vl-tabell';
  // Driftkolonnene er planleggingens andeler skalert til 88 %, med 12 % til
  // stempelet foran; `.vl-tabell-drift` har en bredere gulvbredde tilsvarende.
  const tabellhode = drift ? `
          <colgroup>
            <col style="width: 12%">
            <col style="width: 12%"><col style="width: 9%"><col style="width: 9%">
            <col style="width: 16%"><col style="width: 16%"><col style="width: 4%">
            <col style="width: 9%"><col style="width: 9%"><col style="width: 4%">
          </colgroup>
          <thead>
            <tr>
              <th>Innsjekk</th><th>Navn</th><th>Korps</th><th>Rolle</th>
              <th>Fra</th><th>Til</th><th>Timer</th>
              <th>Kompetanse</th><th>Merknad</th><th></th>
            </tr>
          </thead>` : `
          <colgroup>
            <col style="width: 14%"><col style="width: 10%"><col style="width: 10%">
            <col style="width: 18%"><col style="width: 18%"><col style="width: 5%">
            <col style="width: 10%"><col style="width: 10%"><col style="width: 5%">
          </colgroup>
          <thead>
            <tr>
              <th>Navn</th><th>Korps</th><th>Rolle</th>
              <th>Fra</th><th>Til</th><th>Timer</th>
              <th>Kompetanse</th><th>Merknad</th><th></th>
            </tr>
          </thead>`;

  const tabell = apen ? `
      <div class="vl-tabellramme">
        <table class="${tabellklasse}">
          ${tabellhode}
          <tbody>${kropp}</tbody>
        </table>
      </div>` : `
      <div class="vl-sammendrag">${escapeHtml(sammendrag)}</div>`;

  return `
    <div class="vl-kort${escHtmlValue(apen ? '' : ' vl-kort-sammenslatt')}">
      <div class="vl-kort-topp">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          ${vippe}
          <span class="vl-kort-tittel">
            <i class="bi bi-${escHtmlValue(r.ikon)} me-1"></i>${escapeHtml(r.navn)}
          </span>
          <span class="vl-merkelapp">${escapeHtml(r.gruppe_navn)}</span>
          ${korpsmerke}
          ${enhetsmerke}
        </div>
        <div class="d-flex gap-2">${knapper}</div>
      </div>
      ${tabell}
    </div>`;
}


function _vaktensSpenn() {
  // Spennet kurvene tegnes over. Ett sted, fordi alle gruppenes kurver må
  // dekke *samme* timer — ellers ligger ikke søylene under hverandre, og to
  // kurver man ikke kan sammenligne er verre enn én samlet.
  const poster = aktivListe.vaktposter || [];
  const vl = aktivListe.vaktliste || {};
  const TIME = 3600 * 1000;

  let start = vl.startet ? _d(vl.startet)?.getTime() : null;
  let slutt = vl.planlagt_slutt ? _d(vl.planlagt_slutt)?.getTime() : null;

  // Mangler spennet — eller er det urimelig langt — faller vi tilbake på
  // skiftene. Bedre en kurve som dekker for lite enn ingen kurve. Kurven
  // forsvant helt på en vaktliste der vaktens start lå uker før slutten
  // (André, 12. sep. 2026: «fullstendig vekke»).
  const MAKS = 24 * 14;
  const rimelig = (a, b) => a != null && b != null && b > a && (b - a) / TIME <= MAKS;
  if (!rimelig(start, slutt)) {
    if (!poster.length) return null;
    start = Math.min(...poster.map((v) => _d(v.fra_tid).getTime()));
    slutt = Math.max(...poster.map((v) => _d(v.til_tid).getTime()));
    if (!rimelig(start, slutt)) return null;   // et feiltastet årstall: ikke tegn
  }

  return { start, steg: Math.ceil((slutt - start) / TIME) };
}


function _bemanningPerTime(poster) {
  // **Hele vaktas lengde, ikke bare fra første til siste skift.** Leste vi
  // bare skiftene, ville hullet i begynnelsen vært usynlig nettopp fordi
  // ingen er satt opp der ennå — og det er det hullet planleggeren leter
  // etter.
  const spenn = _vaktensSpenn();
  if (!spenn) return [];
  const rader = poster || aktivListe.vaktposter || [];
  const TIME = 3600 * 1000;

  const ut = [];
  for (let i = 0; i < spenn.steg; i += 1) {
    const t = spenn.start + i * TIME;
    const paa = rader.filter((v) =>
      _d(v.fra_tid).getTime() <= t && _d(v.til_tid).getTime() > t);
    const bemannet = paa.filter((v) => !v.ledig);
    ut.push({
      tid: new Date(t).toISOString(),
      // To tall, ikke ett: `planlagt` er alle plassene, `antall` er de som
      // faktisk har en person. Avstanden mellom dem er det som gjenstår.
      antall: bemannet.length,
      planlagt: paa.length,
      // Probono for seg (André, 12. sep. 2026): de er med i `antall`, og
      // tegnes som den øverste delen av søylen i egen farge.
      probono: bemannet.filter((v) => v.probono).length,
    });
  }
  return ut;
}


function _posterPerGruppe() {
  // **Kurven følger grupperingen** (Andrés bestilling, 30. aug. 2026). En
  // samlet kurve summerte samleplassen, ambulansene og KO til ett tall, og
  // det tallet svarer ikke på noe: fire på samleplassen og null på
  // ambulansen ser likt ut som to og to. Gruppene beholder rekkefølgen
  // serveren sender — den styrer også fanene.
  const gruppePerRessurs = {};
  (aktivListe.ressurser || []).forEach((r) => {
    gruppePerRessurs[r.id] = r.gruppe_id;
  });

  const per = new Map();
  (aktivListe.grupper || []).forEach((g) => per.set(g.id, { gruppe: g, poster: [] }));
  (aktivListe.vaktposter || []).forEach((vp) => {
    const bunke = per.get(gruppePerRessurs[vp.ressurs_id]);
    if (bunke) bunke.poster.push(vp);
  });

  // Grupper uten et eneste skift tegnes ikke — en tom kurve per ubrukt
  // gruppe er seks tomme kurver på en vakt med to ressurser.
  return [...per.values()].filter((b) => b.poster.length);
}


function _timesteg(antall) {
  // Hvor ofte klokkeslettet skrives under søylene. Alle timer på en kort
  // vakt, sjeldnere når spennet er langt — ellers står tallene oppå
  // hverandre og kurven blir uleselig av å være «mer informativ».
  if (antall <= 14) return 1;
  if (antall <= 28) return 2;
  if (antall <= 60) return 4;
  return 6;
}


function _mkEnKurve(tittel, poster) {
  const punkter = _bemanningPerTime(poster);
  if (!punkter.length) {
    // Ingen tom flate: en kurve som mangler uten et ord ser ut som en feil
    // (og var det, 12. sep. 2026). Si hva som mangler.
    return '<div class="vl-meta">Kurven trenger vaktens start og slutt — sett dem i «Innstillinger» (høyst 14 dager), eller legg inn et skift.</div>';
  }
  const topp = Math.max(...punkter.map((p) => p.planlagt)) || 1;
  // Bunnlinja teller folk, ikke plasser (André, 12. sep. 2026: «N personell
  // på det meste»). Skalaen er fortsatt planlagte plasser.
  const flest = Math.max(...punkter.map((p) => p.antall));
  const ledige = punkter.reduce((n, p) => n + (p.planlagt - p.antall), 0);

  // Rene CSS-søyler framfor Chart.js: biblioteket lastes kun på
  // /statistikk/, og en bemanningskurve er ett tall per time. Den lyse delen
  // er plasser uten person — hullene man planlegger for å tette.
  const soyler = punkter.map((p) => {
    const hBemannet = Math.round((p.antall / topp) * 100);
    const hPlanlagt = Math.round((p.planlagt / topp) * 100);
    const probono = p.probono || 0;
    const hProbono = Math.round((probono / topp) * 100);
    const bunnProbono = Math.round(((p.antall - probono) / topp) * 100);
    const skille = _d(p.tid).getHours() === 0 ? ' vl-dogn' : '';
    const tittelTekst = `${_dag(p.tid)} kl. ${_kl(p.tid)}: `
                      + `${p.antall} av ${p.planlagt} plasser fylt`
                      + (probono ? ` (${probono} probono)` : '');
    const probonoDel = probono
      ? `<div class="vl-probonodel" style="height: ${escHtmlValue(hProbono)}%; bottom: ${escHtmlValue(bunnProbono)}%"></div>`
      : '';
    return `<div class="vl-stolpe${skille}" title="${escHtmlValue(tittelTekst)}">
              <div class="vl-planlagt" style="height: ${escHtmlValue(hPlanlagt)}%"></div>
              <div class="vl-bemannet" style="height: ${escHtmlValue(hBemannet)}%"></div>
              ${probonoDel}
            </div>`;
  }).join('');

  // Klokkeslettene ligger i sin egen rad med én celle per søyle, ikke som
  // tekst inni søylen: cellene arver samme flex-bredde, så tallet står
  // under den timen det gjelder uansett hvor mange timer vakten er.
  const steg = _timesteg(punkter.length);
  const timeakse = punkter.map((p, i) => {
    const vis = i % steg === 0;
    return `<span class="vl-time">${vis ? escapeHtml(_kl(p.tid)) : ''}</span>`;
  }).join('');

  const bunn = `${escapeHtml(_dag(punkter[0].tid))} → `
             + `${escapeHtml(_dag(punkter[punkter.length - 1].tid))}`;
  // Tre tall og ikke mer (André, 12. sep. 2026: «Holder med ledige plasser:
  // N og N plasser på det meste og N plasser dekket. Blir for mye clutter
  // hvis ikke»). Plasser, ikke plasstimer — skiftene står i tabellen under.
  const ledigePlasser = poster.filter((vp) => vp.ledig).length;
  const dekket = poster.length - ledigePlasser;
  const ledigTekst = ledigePlasser ? 'Ledige plasser: ' + ledigePlasser : 'Alle plasser fylt';
  const dekketTekst = dekket + (dekket === 1 ? ' plass dekket' : ' plasser dekket');
  const rest = `<span class="vl-meta">${escapeHtml(ledigTekst)} · ${escapeHtml(dekketTekst)}</span>`;

  return `
    <div class="vl-kurvegruppe">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">${escapeHtml(tittel)}</span>
        <div class="d-flex align-items-center gap-3">${rest}</div>
      </div>
      <div class="vl-kurve">${soyler}</div>
      <div class="vl-timeakse">${timeakse}</div>
      <div class="vl-meta">${bunn} · ${escHtmlValue(flest)} personell på det meste</div>
    </div>`;
}


function _tegnforklaring() {
  // Døgnskillet står i forklaringen fordi André spurte hva den hvite streken
  // var. En strek man må spørre om, er en strek som ikke forklarer noe.
  return `
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-bemannet"></i>Bemannet</span>
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-probono"></i>Probono</span>
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-planlagt"></i>Ledig plass</span>
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-dogn"></i>Midnatt</span>`;
}


function _posterIGruppe(gruppeId) {
  const ressurser = new Set(_ressurserIGruppe(gruppeId).map((r) => r.id));
  return (aktivListe.vaktposter || [])
    .filter((vp) => ressurser.has(vp.ressurs_id));
}


function mkGruppekurve(gruppe) {
  // **Kurven står i fanen den gjelder**, øverst, over de ressursene den
  // summerer. Å lete etter samleplassens bemanning under «Oversikt» mens man
  // bemanner samleplassen, er ett skifte for mye.
  //
  // **Og den tegnes selv om gruppa ennå ikke har et eneste skift.** Den falt
  // bort i den tilstanden fram til 30. aug. 2026, og det var feil på akkurat
  // samme måte som at kurven en gang bare dekket skiftene: hullet man
  // planlegger for å tette er størst når ingen er satt opp, og da forsvant
  // hele kurven. Nå står den flat på null over vaktas spenn — som er svaret
  // på «hvor mye gjenstår her».
  const kurve = _mkEnKurve(gruppe.navn, _posterIGruppe(gruppe.id));
  if (!kurve) return '';
  return `
    <div class="vl-kort vl-kurve-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">Bemanning — ${escapeHtml(gruppe.navn)}</span>
        <div class="d-flex align-items-center gap-3">${_tegnforklaring()}</div>
      </div>
      ${kurve}
    </div>`;
}


function _skiftrekkefolge(a, b) {
  // **Fra, så til, så navn.** Uten `til_tid` som andre ledd står skiftene som
  // begynner samtidig i tilfeldig rekkefølge, og et kort skift på fem timer
  // havner midt blant de lange — det var André som så det: en rad som slutter
  // 22:15 lå mellom rader som slutter 03:00 neste dag. Rekkefølgen skal si
  // noe, ellers er den bare innsettingsrekkefølgen forkledd som sortering.
  return a.fra_tid.localeCompare(b.fra_tid)
      || a.til_tid.localeCompare(b.til_tid)
      || (a.navn || '').localeCompare(b.navn || '');
}


function _tidsblokker(poster) {
  // **Skift med samme fra–til er én blokk.** Andrés punkt 11. sep. 2026:
  // mange på en vakt deler tid, og en liste der «fre. 20:00 – lør. 04:00»
  // står på fire rader under hverandre er lang og lik — man ser ikke
  // skiftbyttet før man har lest hver rad. Tiden skrives derfor én gang, på
  // en blokklinje, og radene under er hvem.
  //
  // Sortert med `_skiftrekkefolge` først, så blokkene kommer kronologisk og
  // radene i hver blokk alfabetisk. Nøkkelen er ISO-strengene som de kom fra
  // serveren: to skift er i samme blokk når de er *like*, ikke når de
  // overlapper — et skift som slutter en time før de andre er sitt eget.
  const blokker = [];
  poster.slice().sort(_skiftrekkefolge).forEach((vp) => {
    const sist = blokker[blokker.length - 1];
    if (sist && sist.fra_tid === vp.fra_tid && sist.til_tid === vp.til_tid) {
      sist.poster.push(vp);
    } else {
      blokker.push({ fra_tid: vp.fra_tid, til_tid: vp.til_tid, poster: [vp] });
    }
  });
  return blokker;
}


function _telling(poster, skift) {
  // «2 skift · 5 mannskap» som ren tekst — escapes der den settes inn.
  // Mannskap utelates når ingen er satt opp: «0 mannskap» ved siden av
  // «3 ledige» sier det samme to ganger.
  const mannskap = poster.filter((vp) => !vp.ledig).length;
  const deler = [skift + ' skift'];
  if (mannskap) deler.push(mannskap + ' mannskap');
  return deler.join(' · ');
}


function _dagnokkel(iso) {
  // **Den ene regelen for hvilken dag et skift hører til: startdagen.**
  // Lokal dato — «hvilken dag» er et spørsmål om lokal tid, og et skift som
  // starter 00:30 lørdag er lørdagens, ikke fredagens. «fre. 20:00 – lør.
  // 04:00» står under fredag (André, 15. sep. 2026), også etter at
  // «Oversikt» fikk dagen ytterst.
  //
  // **Nullpolstret, fordi nøkkelen sorteres.** `2026-8-15` og `2026-8-4`
  // sorterer feil vei som tekst; `2026-09-15` og `2026-09-04` gjør ikke det.
  // `_grupperPaaDag()` sorterer på nøkkelen framfor å hvile på at den som
  // kaller har sortert — samme grunn som `_hviletider()` sorterer selv.
  const d = _d(iso);
  if (!d) return '';
  const to = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${to(d.getMonth() + 1)}-${to(d.getDate())}`;
}


function _grupperPaaDag(poster) {
  // Skiftene samlet per dag, i kronologisk rekkefølge. Brukes av «Oversikt»,
  // der dagen er ytterste nivå; `_blokkerMedDager()` gjør det samme inne i
  // en tabell. Begge spør `_dagnokkel()`, så de kan ikke svare ulikt på
  // hvilken dag et skift hører til.
  const indeks = new Map();
  (poster || []).forEach((vp) => {
    const nokkel = _dagnokkel(vp.fra_tid);
    if (!indeks.has(nokkel)) indeks.set(nokkel, { nokkel, fra_tid: vp.fra_tid, poster: [] });
    indeks.get(nokkel).poster.push(vp);
  });
  return [...indeks.values()].sort((a, b) => (a.nokkel < b.nokkel ? -1 : a.nokkel > b.nokkel ? 1 : 0));
}


function _dagtekst(iso) {
  // «Fredag 2. okt». Lang ukedag, fordi dette er en overskrift og ikke et
  // merke; lista er lokal så byggerne kan kjøres uten mer enn `MND` fra sida.
  // Heves ut av `_dagoverskrift()` fordi «Oversikt» trenger den samme teksten
  // uten `<tr>` rundt — to formuleringer av samme dato ville før eller siden
  // skrevet dagen ulikt på de to flatene.
  const DAGER_LANGE = ['Søndag', 'Mandag', 'Tirsdag', 'Onsdag', 'Torsdag',
                       'Fredag', 'Lørdag'];
  const d = _d(iso);
  if (!d) return '';
  const mnd = (globalThis.MND || [])[d.getMonth()] || '';
  return `${DAGER_LANGE[d.getDay()]} ${d.getDate()}. ${mnd}`;
}


function _dagoverskrift(iso, kolonner) {
  // Dagraden inne i en tabell (prosjektleder, 11. sep. 2026: «starttid
  // definerer hvilken dag»).
  const tekst = _dagtekst(iso);
  if (!tekst) return '';
  return `
        <tr class="vl-dag">
          <td colspan="${escHtmlValue(kolonner)}">${escapeHtml(tekst)}</td>
        </tr>`;
}


function _blokkrader(blokker, kolonner, radbygger) {
  // Blokkene uten dagoverskrifter. «Oversikt» bruker denne, fordi dagen der
  // står som overskrift *over* tabellen — en dagrad inni ville sagt det samme
  // to ganger på rad.
  return blokker.map((blokk) =>
    _blokklinje(blokk, kolonner) + blokk.poster.map(radbygger).join('')).join('');
}


function _blokkerMedDager(blokker, kolonner, radbygger) {
  // Blokkene, med en dagoverskrift der dagen skifter — **også når vakten bare
  // varer én dag** (André, 15. sep. 2026: «alltid»).
  //
  // Fram til da sto overskriften bare på flerdagsvakter, med begrunnelsen at
  // «én overskrift over alt sier ingenting». Det er fortsatt sant om selve
  // linja, men den koster lite, og regelen kostet mer: planleggeren måtte
  // vite at fraværet av en dagrad *betydde* noe, og en tabell som skifter
  // form når vakta forlenges er en tabell man må lære to ganger.
  let forrige = null;
  return blokker.map((blokk) => {
    const dag = _dagnokkel(blokk.fra_tid);
    const overskrift = dag !== forrige ? _dagoverskrift(blokk.fra_tid, kolonner) : '';
    forrige = dag;
    return overskrift + _blokkrader([blokk], kolonner, radbygger);
  }).join('');
}


function _blokklinje(blokk, kolonner) {
  // Linja over en blokk: tiden, timene og hvor mange som står der. **Ordene
  // er Andrés (11. sep. 2026): et skift er en vakttid, og de som går det er
  // mannskap.** «4 satt opp» kunne leses som fire skift.
  // Blokka
  // har samme form som et skift (`fra_tid`/`til_tid`), så `_tidsspenn` og
  // `_varighet` leser den rett. Tellingen bygges med `+`, ikke i en
  // template-literal — XSS-skanneren leser hvert `${}` i byggerne, og et
  // tall den ikke kan se er escapet er et funn den må avvise.
  const ledige = blokk.poster.filter((vp) => vp.ledig).length;
  const bemannet = blokk.poster.length - ledige;
  const deler = [];
  if (bemannet) deler.push(bemannet + ' mannskap');
  if (ledige) deler.push(ledige + (ledige === 1 ? ' ledig' : ' ledige'));
  return `
        <tr class="vl-blokk">
          <td colspan="${escHtmlValue(kolonner)}">
            <span class="vl-blokktid">${escapeHtml(_tidsspenn(blokk))}</span>
            <span class="vl-blokktimer">${escapeHtml(_varighet(blokk))}</span>
            <span class="vl-meta">${escapeHtml(deler.join(' · '))}</span>
          </td>
        </tr>`;
}


function mkOversikt() {
  // **Utskriftslista.** Hele vakten på ett ark, gruppert på **ressurs** — den
  // man henger opp.
  //
  // Gruppert på korps fram til 30. aug. 2026, og det var feil bord: den som
  // leser lista står på samleplassen eller ved bilen og spør «hvem er her, og
  // når?». Korpset er et kjennetegn ved personen, ikke et sted — det er en
  // kolonne, ikke en overskrift.
  // **Utvalget** (12. sep. 2026): korpset kommer ferdig filtrert i
  // `aktivListe.vaktposter` (korpsvelgeren, eller serveren for korps-
  // brukeren); ressursen velges her. Arket skal kunne henges opp på bilen
  // eller gis til ett korps, og da er resten av vakten bare sider å bla forbi.
  const verktoy = mkUtskriftsverktoy();
  const poster = (aktivListe.vaktposter || [])
    .filter((vp) => utskriftRessurs == null || vp.ressurs_id === utskriftRessurs);
  if (!poster.length) {
    return `${verktoy}<div class="vl-kort"><div class="vl-tom">Ingen er satt opp ennå.</div></div>`;
  }

  const korpsnavn = {};
  (aktivListe.korps || []).forEach((k) => {
    korpsnavn[k.id] = k.kortnavn || k.navn;
  });

  // **Dagen er ytterste nivå** (André, 14. sep. 2026): «oversikten skal bare
  // vise hvem som er på vakt og hvilken ressurs de er på, på dag — ikke silt
  // etter ressurs først og så dag».
  //
  // **Lesemodellen er en annen enn før.** Fram til nå svarte lista på «hvem
  // står på denne bilen, og når» — den som leser sto ved bilen. Snudd svarer
  // den på «hvem er på vakt i dag, og hvor», som er det den som møter om
  // morgenen spør om. Begge er gyldige; dette er et valg om hvem arket er for.
  //
  // Et skift som krysser midnatt står under **startdagen**, ikke under begge
  // og ikke splittet (André, 15. sep. 2026) — `_dagnokkel()` er regelen.
  // Merk at rapportmodulen har landet motsatt for *timer* (§2.2 der):
  // fakturagrunnlag splittes ved midnatt. Det er ikke en motsigelse — der er
  // spørsmålet hvor mange timer, her er det hvem som er til stede — men
  // forskjellen er bevisst og skal ikke «rettes».
  const perRessursDag = (dagposter) => {
    const kart = new Map();
    (aktivListe.ressurser || []).forEach((r) => kart.set(r.id, []));
    dagposter.forEach((vp) => {
      if (kart.has(vp.ressurs_id)) kart.get(vp.ressurs_id).push(vp);
    });
    return kart;
  };

  // Rekkefølgen er gruppas, så ressursens — samme som fanene. Ressurser uten
  // skift *den dagen* utelates: en tom tabell på papiret er en linje man må
  // lese for å se at det ikke står noe der.
  // **Tiden står på blokklinja, ikke i raden** (11. sep. 2026). Skift med
  // samme fra–til samles i `_tidsblokker()`, og linja over dem bærer spennet,
  // timene og antallet. Raden under er hvem — navn, korps, rolle, merknad.
  // Kolonnen «Tid» er borte fordi den sto med samme verdi fire ganger.
  const rad = (vp) => {
    // Korpset i lista: personens når raden er fylt, plassens reservasjon
    // når den er ledig. Det er det samme skillet som i ressurstabellen, og
    // av samme grunn.
    const korps = vp.ledig
      ? (vp.alle_korps ? 'Åpen for alle' : (korpsnavn[vp.reservert_korps_id] || 'Planlagt'))
      : (vp.korps_kort || '');
    return `
        <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
          <td class="vl-navn">${escapeHtml(vp.ledig ? '— ledig —' : vp.navn)}${_probonoMerke(vp)}</td>
          <td>${escapeHtml(korps || '—')}</td>
          <td>${escapeHtml(vp.rolle || '—')}</td>
          <td>${escapeHtml(vp.merknad || '')}</td>
        </tr>`;
  };

  const ressursdeler = (kart) => _grupperMedRessurser().flatMap((g) =>
    _ressurserIGruppe(g.id)
      .filter((r) => utskriftRessurs == null || r.id === utskriftRessurs)
      .filter((r) => (kart.get(r.id) || []).length)
      .map((r) => {
        const egne = kart.get(r.id);
        const blokker = _tidsblokker(egne);
        // `_blokkrader`, ikke `_blokkerMedDager`: dagen står i overskriften
        // over tabellen, og en dagrad inni ville gjentatt den.
        const rader = _blokkrader(blokker, 4, rad);
        const ledige = egne.filter((vp) => vp.ledig).length;
        const rest = ledige
          ? ` <span class="vl-meta">· ${escHtmlValue(ledige)} ${escapeHtml(ledige === 1 ? 'ledig' : 'ledige')}</span>` : '';
        // **Et skift er en vakttid, mannskap er de som går den** (André,
        // 11. sep. 2026). Tallene er derfor blokkene og de bemannede radene,
        // ikke radene. Summene er **per dag per ressurs** etter snuingen —
        // det er det tallet som står under overskriften de hører til. Summen
        // for hele vakta står fortsatt i arkhodet.
        const tall = _telling(egne, blokker.length);
        const timer = `${escapeHtml(_tall(_sumTimer(egne)))} t`;
        return `
      <div class="vl-korpsgruppe">
        <h3>${escapeHtml(r.navn)}
          <span class="vl-meta">${escapeHtml(g.navn)} ·
            ${escapeHtml(tall)} · ${timer}</span>${rest}
        </h3>
        <div class="vl-tabellramme">
        <table class="vl-tabell vl-utskrift">
          <colgroup>
            <col style="width: 34%"><col style="width: 14%"><col style="width: 22%">
            <col style="width: 30%">
          </colgroup>
          <thead>
            <tr><th>Navn</th><th>Korps</th><th>Rolle</th><th>Merknad</th></tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
        </div>
      </div>`;
      }));

  // **Dagbolken er en `<section>` med sin egen overskrift.** Utskriften har
  // `break-inside: avoid` på den der det får plass — en dagoverskrift alene
  // nederst på et ark er en side ingen kan bruke.
  const deler = _grupperPaaDag(poster).map((dag) => `
      <section class="vl-dagbolk">
        <h2 class="vl-dagtittel">${escapeHtml(_dagtekst(dag.fra_tid))}</h2>
        ${ressursdeler(perRessursDag(dag.poster)).join('')}
      </section>`);

  const tittel = aktivListe.vaktliste.vakt_navn;
  const spenn = _vaktspenn();
  const antallLedige = poster.filter((vp) => vp.ledig).length;
  const ledigtekst = antallLedige
    ? ` · ${escHtmlValue(antallLedige)} ${escapeHtml(antallLedige === 1 ? 'ledig plass' : 'ledige plasser')}` : '';
  const sumTimer = `${escapeHtml(_tall(_sumTimer(poster)))} t`;
  // Skiftene over hele vakten er de *ulike* vakttidene — samme spenn på
  // samleplassen og på bilen er ett skift, ikke to.
  const vaktTall = _telling(poster, _tidsblokker(poster).length);
  // **Ingen kurve her.** Den står i fanen den gjelder, og to steder å lese
  // den samme kurven er ett for mye. «Oversikt» er utskriftslista, og bare det.
  // Utvalget står i arkhodet, for det er arket som skal si hva det er —
  // «HGSD · Ambulanse 1» — ikke velgeren, som ikke kommer med på papiret.
  const utvalg = _utvalgstekst();
  const utvalgslinje = utvalg
    ? `<div class="vl-utvalg">${escapeHtml(utvalg)}</div>` : '';
  return `${verktoy}
    <div class="vl-kort vl-utskriftsark">
      <div class="vl-arkhode">
        <h2>${escapeHtml(tittel)}</h2>
        ${utvalgslinje}
        <div class="vl-meta">${escapeHtml(spenn)} ·
          ${escapeHtml(vaktTall)} · ${sumTimer}${escapeHtml(ledigtekst)}</div>
      </div>
      ${deler.join('')}
    </div>`;
}


function _tilstede() {
  // **Definisjonen er knivskarp: møtt, og ikke gått av vakt.** Utledet av
  // stemplene, aldri en lagret status — to kilder til samme sannhet går i
  // utakt første gang noe feiler halvveis. Speiler `Vaktpost.er_tilstede`,
  // og serveren sender flagget ferdig utregnet nettopp derfor.
  return (aktivListe?.vaktposter || []).filter((vp) => vp.tilstede);
}


async function lastBelastning() {
  if (!aktivListe) return;
  const korps = korpsfilter == null ? '' : `?korps=${encodeURIComponent(korpsfilter)}`;
  const res = await apiFetch(
    `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/belastning/${korps}`);
  if (!res.ok) return;
  belastning = (await res.json()).data;
  tegn();
}


function _tall(n) {
  // **Ett format for timer, overalt: «8,5», ikke «8.5».** Én desimal, komma
  // som desimaltegn, og uten «,0» på hele tall — «14 t» leses raskere enn
  // «14,0 t» i en kolonne man skummer. Planleggingsfanen skrev «8.5» fram
  // til 11. sep. 2026, mens ressurstabellen skrev «8,5»; André ba om komma.
  const rundet = Math.round(n * 10) / 10;
  return Number.isInteger(rundet) ? String(rundet)
    : rundet.toFixed(1).replace('.', ',');
}


function mkBelastning() {
  // **Belastningen før vakten, ikke bemanningen** (§8b). Bemanningskurvene
  // svarer på «er plassene fylt»; denne svarer på «hva koster det dem som
  // fyller dem».
  //
  // **Varsler, ikke sperrer.** Ingenting her nekter noe — et langt skift
  // merkes, og det er alt. Noen ganger *må* noen ta et langt skift, og da
  // skal lista si det høyt framfor å tvinge planleggeren til å lyve om
  // tidene for å komme videre.
  if (!belastning) {
    return '<div class="vl-kort"><div class="vl-tom">Regner\u2026</div></div>';
  }
  const s = belastning.sammendrag;
  const g = belastning.grenser;

  // Hvert ledd heves ut i sin egen variabel framfor å stå som en ternær med
  // en template-literal inni en annen: den formen er vanskelig å lese, og
  // XSS-skanneren i `tests_xss.py` kan ikke se inn i den.
  const varsel = (antall, tekst) => antall
    ? `<div class="vl-varseltall"><span class="vl-varselantall">${escHtmlValue(antall)}</span>
         <span class="vl-meta">${escapeHtml(tekst)}</span></div>`
    : '';
  const langeSkift = varsel(s.lange_skift, `skift over ${g.maks_skift_timer} t`);
  const korteHviler = varsel(s.korte_hviler, `hviler under ${g.min_hvile_timer} t`);
  const ingenVarsler = (!s.lange_skift && !s.korte_hviler)
    ? '<span class="vl-meta">Ingen varsler</span>' : '';
  const grenseknapp = kanLede()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneGrenser">
         <i class="bi bi-sliders me-1"></i>Grenser
       </button>`
    : '';

  const hode = `
    <div class="vl-kort vl-belastningshode">
      <div class="vl-noekkeltall">
        <div><b>${escHtmlValue(s.personer)}</b><span class="vl-meta">personer</span></div>
        <div><b>${escHtmlValue(s.skift)}</b><span class="vl-meta">skift</span></div>
        <div><b>${escapeHtml(_tall(s.timer))}</b><span class="vl-meta">timer totalt</span></div>
        <div><b>${escHtmlValue(s.ledige_plasser)}</b><span class="vl-meta">ledige plasser</span></div>
      </div>
      <div class="vl-varsler">
        ${langeSkift}${korteHviler}${ingenVarsler}
      </div>
      ${grenseknapp}
    </div>`;

  if (!belastning.personer.length) {
    return hode + '<div class="vl-kort"><div class="vl-tom">Ingen er satt '
         + 'opp på vakten ennå. Tallene fylles ut etter hvert som plassene '
         + 'bemannes.</div></div>';
  }

  // Faktisk-kolonnen står bare når det finnes noe å vise. I planlegging er
  // den tom for alle, og en kolonne med bare streker er en kolonne som
  // stjeler bredde fra dem som betyr noe.
  const harFaktisk = belastning.personer.some((r) => r.faktiske_timer !== null);

  const merket = (paa) => (paa ? 'vl-advarsel' : '');
  const strek = '<span class="vl-meta">—</span>';

  const rader = belastning.personer.map((r) => {
    const hvileklasse = merket(r.kort_hvile);
    const hvile = r.korteste_hvile === null ? strek
      : `<span class="${hvileklasse}">${escapeHtml(_tall(r.korteste_hvile))} t</span>`;
    const lengsteklasse = merket(r.langt_skift);
    const lengste = `<span class="${lengsteklasse}">${escapeHtml(_tall(r.lengste_skift))} t</span>`;
    const faktiskTall = r.faktiske_timer === null
      ? strek : `${escapeHtml(_tall(r.faktiske_timer))} t`;
    const faktisk = harFaktisk ? `<td>${faktiskTall}</td>` : '';
    return `
      <tr>
        <td class="vl-navn">${escapeHtml(r.navn)}</td>
        <td>${escapeHtml(r.korps_kort)}</td>
        <td>${escHtmlValue(r.antall_skift)}</td>
        <td><b>${escapeHtml(_tall(r.timer))} t</b></td>
        ${faktisk}
        <td>${lengste}</td>
        <td>${hvile}</td>
      </tr>`;
  }).join('');

  const faktiskHode = harFaktisk ? '<th>Faktisk</th>' : '';
  // **Tabellen får ikke krympes under det navnet trenger.** Med
  // `table-layout: fixed` og ingen kolonnebredder delte nettleseren 308 px
  // likt på seks kolonner — 51 px hver, og «Korteste hvile» sto i tre
  // linjer over et tall. André: «veldig tett på mobil». Kolonnene får
  // andeler, og stilarket gir tabellen en gulvbredde så den ruller i ramma
  // på en telefon i stedet for å klemmes.
  const kolonner = harFaktisk ? `
          <colgroup>
            <col style="width: 24%"><col style="width: 10%"><col style="width: 8%">
            <col style="width: 13%"><col style="width: 11%"><col style="width: 17%">
            <col style="width: 17%">
          </colgroup>` : `
          <colgroup>
            <col style="width: 27%"><col style="width: 11%"><col style="width: 9%">
            <col style="width: 15%"><col style="width: 19%"><col style="width: 19%">
          </colgroup>`;
  return hode + `
    <div class="vl-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">Per person</span>
        <span class="vl-meta">Sortert på timer — den som er i ferd med å bli
          brukt opp ligger øverst</span>
      </div>
      <div class="vl-tabellramme">
        <table class="vl-tabell vl-tabell-belastning vl-utskrift">
          ${kolonner}
          <thead>
            <tr>
              <th>Navn</th><th>Korps</th><th>Skift</th><th>Planlagt</th>
              ${faktiskHode}
              <th>Lengste skift</th><th>Korteste hvile</th>
            </tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
      </div>
    </div>`;
}


function mkTilstede() {
  // **Modulens mest alvorlige visning.** På et sted med overnatting brukes
  // den til å vite hvem som er i bygget ved brann. Det stiller tre krav
  // resten av sida ikke har:
  //
  // 1. Tellingen står øverst, stor. I en evakuering teller man hoder mot et
  //    tall, og da skal tallet være det første man ser.
  // 2. Lista skal kunne skrives ut. Strøm og nett er det første som ryker i
  //    nettopp situasjonen lista finnes for, så rutinen bør være å skrive
  //    den ut ved vaktstart og ved skiftbytte.
  // 3. Ingen redigering. Dette er en oversikt man leser under press;
  //    stemplene settes i ressursfanene, der man ser hvem som mangler.
  const rader = _tilstede();
  const alle = (aktivListe?.vaktposter || []).filter((vp) => !vp.ledig);
  const stemplet = new Date().toLocaleTimeString('no-NO',
    { hour: '2-digit', minute: '2-digit' });

  // Gruppert på ressurs, som utskriftslista: den som leter etter en person
  // vet hvilken bil hun står på, ikke hvilken rad hun har.
  const perRessurs = new Map();
  rader.forEach((vp) => {
    if (!perRessurs.has(vp.ressurs_id)) perRessurs.set(vp.ressurs_id, []);
    perRessurs.get(vp.ressurs_id).push(vp);
  });

  const bolker = (aktivListe?.ressurser || [])
    .filter((r) => perRessurs.has(r.id))
    .map((r) => {
      const linjer = perRessurs.get(r.id)
        .slice().sort((a, b) => (a.navn || '').localeCompare(b.navn || ''))
        .map((vp) => `
          <tr>
            <td class="vl-navn">${escapeHtml(vp.navn)}</td>
            <td>${escapeHtml(vp.korps_kort || '—')}</td>
            <td>${escapeHtml(vp.rolle || '—')}</td>
            <td>${escapeHtml(_kl(vp.mott_at))}</td>
            <td>${escapeHtml(_tidsspenn(vp))}</td>
          </tr>`).join('');
      return `
        <div class="vl-kort">
          <div class="vl-kort-topp">
            <span class="vl-kort-tittel">
              <i class="bi bi-${escHtmlValue(r.ikon)} me-1"></i>${escapeHtml(r.navn)}
              <span class="vl-meta">${escHtmlValue(perRessurs.get(r.id).length)}</span>
            </span>
          </div>
          <div class="vl-tabellramme">
            <table class="vl-tabell vl-utskrift">
              <thead>
                <tr><th>Navn</th><th>Korps</th><th>Rolle</th>
                    <th>Møtt</th><th>Planlagt skift</th></tr>
              </thead>
              <tbody>${linjer}</tbody>
            </table>
          </div>
        </div>`;
    }).join('');

  const mangler = alle.length - rader.length;
  const innhold = bolker || '<div class="vl-kort"><div class="vl-tom">Ingen '
    + 'er registrert møtt ennå. Stemplene settes i ressursfanene.</div></div>';
  return `
    <div class="vl-kort vl-tilstedehode">
      <div>
        <div class="vl-tilstedetall">${escHtmlValue(rader.length)}</div>
        <div class="vl-meta">tilstede nå · ${escapeHtml(stemplet)}</div>
      </div>
      <div class="vl-tilstedemeta">
        <div>${escHtmlValue(alle.length)} satt opp på vakten</div>
        <div>${escHtmlValue(mangler)} ikke møtt eller gått av vakt</div>
        <div class="vl-meta">Møtt, og ikke gått av vakt. Utledet av
          stemplene.</div>
      </div>
      <button class="btn btn-sm btn-outline-secondary" type="button"
              data-action="skrivUt">
        <i class="bi bi-printer me-1"></i>Skriv ut
      </button>
    </div>
    ${innhold}`;
}


function mkMittKorps() {
  // Prosjektleder, 11. sep. 2026: «Mitt korps som viser alle vaktene som
  // skal dekkes» — «dine tildelte vakter og de vakter som er satt universal
  // tildelt». Ledige først i hver blokk (sorteringen setter tomt navn
  // først), dagoverskrifter som ellers, og det som gjenstår å dekke øverst.
  const korpsId = _mittKorpsId();
  if (korpsId == null) {
    return '<div class="vl-kort"><div class="vl-tom">Velg et korps for å se plassene det har ansvar for.</div></div>';
  }
  const korps = (aktivListe.korps || []).find((k) => k.id === korpsId);
  const korpsnavn = korps ? korps.navn : 'korpset';
  const poster = _synligePoster(aktivListe.alle_vaktposter || aktivListe.vaktposter, korpsId);
  const ledige = poster.filter((vp) => vp.ledig).length;
  const bemannet = poster.length - ledige;
  // Timene, delt slik André leste dem (12. sep. 2026): bemannet er
  // korpsets egne folk, å dekke er de ledige plassene korpset har fått,
  // åpent for alle er dem alle korps kan fylle, probono for seg. Ett samlet
  // «å dekke» leste som at korpset skyldte alle de åpne timene.
  const bemannet_t = _tall(_sumTimer(poster.filter((vp) => !vp.ledig)));
  const dekke_t = _tall(_sumTimer(poster.filter((vp) => vp.ledig && !vp.alle_korps)));
  const aapent_t = _tall(_sumTimer(poster.filter((vp) => vp.ledig && vp.alle_korps)));
  const probono = _tall(poster.reduce((sum, vp) => sum + (vp.probono ? (_skifttimer(vp) || 0) : 0), 0));

  const hode = `
    <div class="vl-kort vl-belastningshode">
      <div class="vl-noekkeltall">
        <div><b>${escHtmlValue(ledige)}</b><span class="vl-meta">${escapeHtml(ledige === 1 ? 'plass å dekke' : 'plasser å dekke')}</span></div>
        <div><b>${escHtmlValue(bemannet)}</b><span class="vl-meta">mannskap satt opp</span></div>
        <div><b>${escapeHtml(bemannet_t)} t</b><span class="vl-meta">bemannet</span></div>
        <div><b>${escapeHtml(dekke_t)} t</b><span class="vl-meta">å dekke for korpset</span></div>
        <div><b>${escapeHtml(aapent_t)} t</b><span class="vl-meta">åpent for alle</span></div>
        <div><b>${escapeHtml(probono)} t</b><span class="vl-meta">probono</span></div>
      </div>
      <span class="vl-meta">${escapeHtml(korpsnavn)} — tildelte plasser og plasser åpne for alle</span>
    </div>`;

  if (!poster.length) {
    return hode + '<div class="vl-kort"><div class="vl-tom">Ingen plasser er tildelt korpset ennå.</div></div>';
  }

  const ressursnavn = {};
  (aktivListe.ressurser || []).forEach((r) => { ressursnavn[r.id] = r; });
  const rad = (vp) => {
    const r = ressursnavn[vp.ressurs_id];
    const hvem = vp.ledig
      ? _fyllValgFor(vp, kanBemannePlass(vp, r)) + _probonoMerke(vp)
      : escapeHtml(vp.navn) + _probonoMerke(vp);
    const tildelt = vp.ledig
      ? (vp.alle_korps ? 'Åpen for alle' : (korps ? (korps.kortnavn || korps.navn) : ''))
      : (vp.korps_kort || '');
    return `
        <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
          <td class="vl-navn">${escapeHtml(r ? r.navn : '')}</td>
          <td>${hvem}</td>
          <td>${escapeHtml(tildelt || '—')}</td>
          <td>${escapeHtml(vp.rolle || '—')}</td>
          <td>${escapeHtml(vp.merknad || '')}</td>
        </tr>`;
  };
  const rader = _blokkerMedDager(_tidsblokker(poster), 5, rad);
  return hode + `
    <div class="vl-kort">
      <div class="vl-tabellramme">
        <table class="vl-tabell vl-utskrift">
          <colgroup>
            <col style="width: 22%"><col style="width: 30%"><col style="width: 14%">
            <col style="width: 16%"><col style="width: 18%">
          </colgroup>
          <thead>
            <tr><th>Ressurs</th><th>Hvem</th><th>Tildelt</th><th>Rolle</th><th>Merknad</th></tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
      </div>
    </div>`;
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
