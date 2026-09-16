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
  if (faneTrengerBelastning(id) && !belastning) { lastBelastning(); }
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
  // **Fanen heter «Timeoversikt»** (André, 16. sep. 2026). Den het
  // «Planlegging», og det navnet var opptatt: `Vaktliste.status` har verdien
  // «Planlegging» ved siden av «I drift», så merket øverst på siden og fanen
  // sa det samme ordet om to helt ulike ting. Nå sier navnet hva den viser —
  // timer per person — og «Planlegging» betyr bare status.
  //
  // Tallene er lista regnet sammen (§8b), ikke en ny kilde. Fanen står ved
  // siden av «Oversikt» fordi det er samme spørsmål sett fra en annen kant:
  // oversikten er hvem som står hvor, denne er hva det koster dem.
  faner.push({
    id: BELASTNING, navn: 'Timeoversikt', ikon: 'graph-up',
    antall: belastning ? belastning.sammendrag.personer : null,
  });

  // **Planleggeren, for dem som setter opp vakta.** Den står etter
  // «Timeoversikt» fordi rekkefølgen i fanerekka er den man arbeider i:
  // først lager man grunnlaget, så ser man hva det koster. At den er sist av
  // de to er altså ikke en rangering — det er at man kommer tilbake til
  // tallene oftere enn til generatoren.
  if (kanPlanlegge()) {
    faner.push({
      id: PLANLEGGER, navn: 'Planlegger', ikon: 'magic',
      antall: null,
    });
  }

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
  if (aktivFane === PLANLEGGER) {
    // **Oppsettet leses tilbake her, ikke i byggeren.** `mkPlanlegger()` skal
    // kunne kalles uten å endre noe; tilstanden settes på vei inn i panelet,
    // og da gjelder det uansett hvilken vei man kom — fanevalg, listebytte
    // eller omtegning etter en generering.
    planleggerSikreLinjer();
    el.innerHTML = mkPlanlegger();
    return;
  }
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
    const innhold = kanSetteOppSkift()
      ? `<input type="datetime-local" step="300" class="vl-celle"
                value="${escHtmlValue(_iso16(vp[felt]))}"
                data-action="endreVaktpost" data-hendelse="change"
                data-felt="${escHtmlValue(felt)}" data-id="${escHtmlValue(vp.id)}">`
      : escapeHtml(_kl(vp[felt]));
    return `<div class="vl-tidcelle">${innhold}${merke}</div>`;
  };

  // **Merknaden følger raden, ikke oppsettet** (André, 16. sep. 2026):
  // «kommer 17:30» er en beskjed om den som står der, og den som setter
  // personen på plassen er den som vet det. Tidene over er vaktas rammer og
  // settes av den som setter opp — der er et felt man kan skrive i og ikke
  // lagre verre enn en tekst, for det ser ut som om endringen gikk igjennom.
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

  // **«Opprett vakt» er å sette opp behovet**, ikke å fylle det (André,
  // 15. sep. 2026). Knappen sto på `kanRore` — altså badgen — og da kunne
  // korps-føreren lage skift med frie tidspunkt på sin egen ressurs.
  const settKnapp = kanSetteOppSkift()
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
  // **Vinduet åpnes av den som kan bemanne ressursen**, fordi navnet er det
  // ene hun får rette (15. sep. 2026). Hva vinduet *viser*, avgjøres inne i
  // det: gruppe, reservasjon, enhetskobling og sletting er lederens.
  const redigerKnapp = kanGiNyttNavn(r)
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
