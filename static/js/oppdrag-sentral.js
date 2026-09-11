// ════════════════════════════════════════════════════════
// Sentralbordet i oppdragsmodulen (/oppdrag/).
//
// Laster KUN portal-utils.js. `patients-utils.js` gjør arbeid på toppnivå —
// Chart.defaults og `new bootstrap.Modal(...)` mot pasientskjemaene — og
// kaster på en side uten dem. Trengs en helper derfra, skal den flyttes til
// portal-utils.js, ikke kopieres. JsModulLastingTests håndhever det.
//
// All brukerdata som settes inn med innerHTML escapes: fritekst og
// lokasjonsnavn er de første virkelig frie feltene i portalen som ikke er en
// nedtrekksliste.
// ════════════════════════════════════════════════════════

let enheter = [];
let lokasjoner = [];
let oppdragsliste = [];
let enhetsadmin = [];

// ETag-verdiene fra forrige poll. Serveren svarer 304 når ingenting er
// endret, og da rendrer vi ikke på nytt — under en rolig time er trafikken
// nær null selv med mange pålogget.
let etagEnheter = null;
let etagOppdrag = null;

// **Besetningen er vaktlistas data, lånt inn** (§6 i vaktlistenotatet).
// Oppdragsmodulen importerer ikke vaktlista i Python — koblingen ligger her,
// i nettleseren, som `Ressurs.enhet` peker sammen.
//
// Hentes **når operatøren spør**, ikke ved hver polling: enhetslista pollet
// hvert par sekund ville gitt ett kall per bil per runde, og svaret er
// dessuten bare interessant i det øyeblikket noen lurer.
let besetninger = {};
let apenBesetning = null;

const STATUS_REKKEFOLGE = ['venter', 'rykker_ut', 'fremme', 'avreist', 'leverer', 'ledig'];


function hastegradKlasse(h) {
  return 'hastegrad-' + (h || '').toLowerCase();
}


function _grovMerke(o) {
  // Bilens Rød/Gul/Grønn som merke; «—» når bilen ikke har vurdert ennå.
  // `grovsortering` er nøkkelen (rod/gul/gronn) og styrer fargen;
  // `grovsortering_navn` er teksten.
  if (!o.grovsortering) {
    return '<span class="grov-merke grov-tom" title="Bilen har ikke grovsortert ennå">Bil: —</span>';
  }
  return `<span class="grov-merke grov-${escHtmlValue(o.grovsortering)}">Bil: ${escapeHtml(o.grovsortering_navn || o.grovsortering)}</span>`;
}


function tidSiden(iso, naa) {
  // «12 min», «1 t 05 min» — hvor lenge siden et tidspunkt. Prosjektleder,
  // 11. sep. 2026: «tidspunkt siden oppdrag». Klokkeslettet står der alt;
  // dette er tallet man ellers regner ut i hodet, og det er det som sier om
  // bilen har stått lenge i Fremme. Under et minutt er «nå», ikke «0 min».
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const min = Math.floor(((naa ?? Date.now()) - t) / 60000);
  if (min < 1) return 'nå';
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const rest = min % 60;
  return `${h} t ${String(rest).padStart(2, '0')} min`;
}


// ── Enhetsliste ─────────────────────────────────────────

function renderEnheter() {
  const el = document.getElementById('enhetsliste');
  if (!el) return;

  // Tavla viser hvem som kan sendes nå. Antallet av vakt står på
  // Enheter-knappen, der hele lista ligger.
  const paVakt = enheter.filter((e) => e.pa_vakt);
  const antallAv = enheter.length - paVakt.length;

  if (!paVakt.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter på vakt.</div>';
  } else {
    el.innerHTML = (paVakt.map((e) => {
      // «Ledig (2 venter)» er distinksjonen 113 trenger: enheten har fått
      // oppdrag, men ikke rykket ut, og kan fortsatt sendes.
      // Statusen med klokkeslett og tid siden: «Fremme 14:32 · 12 min».
      // Prosjektleder, 11. sep. 2026 — «på statusen så må tidsstemplet og
      // vise». Ledig har ingen melding bak seg, så der står bare ordet.
      const statusTid = e.status_tidspunkt
        ? ` ${klokke(e.status_tidspunkt)} · ${tidSiden(e.status_tidspunkt)}` : '';
      const meta = e.antall_ventende
        ? `${e.status_navn}${statusTid} · ${e.antall_ventende} venter`
        : `${e.status_navn}${statusTid}`;
      // Det aktive oppdraget i ett blikk: nummer, hastegrad, problemstilling.
      // Hoistet ut av mal-strengen, som resten.
      const grov = e.oppdragsnummer != null ? _grovMerke(e) : '';
      const oppdragslinje = e.oppdragsnummer != null
        ? `<div class="enhet-oppdrag">
             <span class="oppdrag-nr">#${escHtmlValue(e.oppdragsnummer)}</span>
             <span class="hastegrad ${escHtmlValue(hastegradKlasse(e.hastegrad))}">${escapeHtml(e.hastegrad || '')}</span>
             ${grov}
             <span class="enhet-oppdrag-problem">${escapeHtml(e.problemstilling || '')}</span>
           </div>`
        : '';
      // Hoistet ut av mal-strengen: en nøstet mal-streng inne i en `${...}`
      // er usynlig for XSS-skanneren i tests_xss.py, og vanskelig å lese.
      const klikkbar = kanSeBesetning() ? ' enhet-kort-klikkbar' : '';
      const apner = kanSeBesetning()
        ? `data-action="visBesetning" data-id="${escHtmlValue(e.id)}"` : '';
      const besetning = mkBesetning(e.id);
      return `
      <div class="enhet-kort${klikkbar}" ${apner}>
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <div class="flex-grow-1">
          <div class="enhet-navn">${escapeHtml(e.navn)}</div>
          <div class="enhet-meta">${escapeHtml(meta)}</div>
          ${oppdragslinje}
        </div>
      </div>${besetning}`;
    }).join(''));
  }

  const teller = document.getElementById('av-vakt-teller');
  if (teller) teller.textContent = antallAv ? ` (${antallAv} av vakt)` : '';
}


function kanSeBesetning() {
  // Speiler `har_tilgang(bruker, 'vaktliste', 'les')`, satt av malen.
  // **Komposisjonsregelen fra rollemodellen §5:** en modul viser bare kilder
  // brukeren har tilgang til, framfor å gi avledet innsyn. Serveren nekter
  // uansett — dette avgjør bare om panelet finnes.
  return globalThis.window?.KAN_SE_BESETNING === true;
}


function mkBesetning(enhetId) {
  // Panelet ligger *under* enhetskortet, ikke inni: kortet er en linje 113
  // skummer, og en besetning på fire ville sprengt den.
  if (apenBesetning !== enhetId) return '';
  const b = besetninger[enhetId];
  if (b === undefined) {
    return '<div class="besetning"><span class="enhet-meta">Henter…</span></div>';
  }
  if (b.feil) {
    // **Serverens forklaring, ikke vår egen.** Den vanligste grunnen til at
    // en besetning ikke finnes er at bilen er koblet i en vakt man har
    // *planlagt*, mens sentralbordet står i den aktive — og da er ikke
    // oppsettet feil, det er feil vakt som er aktiv. Skrev vi vår egen
    // generiske «ikke koblet» her, sendte vi operatøren ut på jakt etter en
    // feil som ikke finnes.
    return `<div class="besetning"><span class="enhet-meta">${escapeHtml(b.feil)}</span></div>`;
  }
  if (!b.mannskap.length) {
    return `<div class="besetning"><span class="enhet-meta">`
         + `Ingen på vakt på ${escapeHtml(b.ressurs_navn)} nå.</span></div>`;
  }

  const rader = b.mannskap.map((m) => {
    // Tre tilstander, ikke to: «møtt» og «av vakt» er begge stemplet, men
    // bare den ene er til stede nå.
    const merke = m.tilstede
      ? '<span class="besetning-inne" title="Møtt">●</span>'
      : (m.mott
          ? '<span class="besetning-ute" title="Av vakt">○</span>'
          : '<span class="besetning-ute" title="Ikke møtt">○</span>');
    const rolle = m.rolle
      ? `<span class="enhet-meta">${escapeHtml(m.rolle)}</span>` : '';
    return `<div class="besetning-rad">${merke}
              <span>${escapeHtml(m.navn)}</span>${rolle}</div>`;
  }).join('');

  const status = b.i_drift
    ? `${escHtmlValue(b.tilstede)} av ${escHtmlValue(b.antall)} møtt`
    : `${escHtmlValue(b.antall)} satt opp · innsjekk ikke åpnet`;

  return `<div class="besetning">
      <div class="besetning-topp">
        <span>${escapeHtml(b.ressurs_navn)}</span>
        <span class="enhet-meta">${status}</span>
      </div>
      ${rader}
    </div>`;
}


async function visBesetning(enhetId) {
  if (apenBesetning === enhetId) { apenBesetning = null; renderEnheter(); return; }
  apenBesetning = enhetId;
  renderEnheter();
  await hentBesetning(enhetId);
}


async function hentBesetning(enhetId) {
  const res = await apiFetch(`/vaktliste/api/enhet/${enhetId}/besetning/`);
  const d = await res.json().catch(() => ({}));
  // Serveren skiller mellom «koblet i en annen vakt» og «ikke koblet noe
  // sted», og meldingen bæres uendret hit — se `mkBesetning`.
  besetninger[enhetId] = res.ok
    ? d.data
    : { feil: d.message || 'Kunne ikke hente besetningen.' };
  renderEnheter();
}


async function _settVakt(id, paVakt) {
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/vakt/`, {
    method: 'POST',
    body: JSON.stringify({ pa_vakt: paVakt }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke endre vaktstatus.');
    return;
  }
  etagEnheter = null;   // tving ny henting, ellers svarer serveren 304
  await lastAlt();
  if (document.getElementById('enhetsadminliste')) await lastEnhetsadmin();
}

async function taAvVakt(id) { await _settVakt(id, false); }
async function settPaaVakt(id) { await _settVakt(id, true); }


// ── Oppdragsliste ───────────────────────────────────────

function renderOppdrag() {
  const el = document.getElementById('oppdragsliste');
  if (!el) return;

  if (!oppdragsliste.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen oppdrag i vakta ennå.</div>');
    return;
  }

  const sortert = [...oppdragsliste].sort((a, b) => {
    const ai = STATUS_REKKEFOLGE.indexOf(a.status);
    const bi = STATUS_REKKEFOLGE.indexOf(b.status);
    if (ai !== bi) return ai - bi;
    return new Date(b.opprettet) - new Date(a.opprettet);
  });

  el.innerHTML = (sortert.map((o) => {
    // Fragmentene bygges før mal-strengen, ikke inne i en ${...}. En nøstet
    // mal-streng inne i en interpolasjon er vanskelig å lese — og XSS-vernet
    // i tests_xss.py klarer ikke å se inn i den, så en uescapet verdi der
    // ville passert stille.
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    // «Fremme · 12 min» og «14:20 · 31 min siden» — ren tekst, escapet ved
    // innsetting. Uten statusmelding (venter) står bare ordet.
    const statusTekst = o.status_tidspunkt
      ? `${o.status_navn} · ${tidSiden(o.status_tidspunkt)}`
      : String(o.status_navn);
    const opprettetTekst = `${klokke(o.opprettet)} · ${tidSiden(o.opprettet)} siden`;
    // To vurderinger, to plasser: KO/AMKs hastegrad til venstre, bilens
    // grovsortering til høyre. Tom grovsortering vises som «—», fordi
    // «ikke vurdert ennå» er informasjon.
    const grovsortering = _grovMerke(o);
    return `
    <div class="oppdrag-rad" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">#${escHtmlValue(o.nummer)}</span>
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        ${grovsortering}
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
        <span class="ms-auto d-flex align-items-center gap-1">
          <span class="status-prikk status-${escHtmlValue(o.status)}"></span>
          <span class="oppdrag-meta">${escapeHtml(statusTekst)}</span>
        </span>
      </div>
      <div class="enhetsmatrise mt-1">${_enhetsmatrise(o)}</div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(o.lokasjon_navn)} · ${escapeHtml(opprettetTekst)}
      </div>
      ${fritekstBlokk}
    </div>`;
  }).join(''));
}


function _enhetsmatrise(o) {
  // Én brikke per enhet: navn, status og tid siden — matrisen fra §4 i
  // notatet om flere enheter. Oppdragets egen status står fortsatt til
  // høyre i raden; den er utledet av disse. Uten `enheter` (eldre svar)
  // er det én brikke av toppnivåfeltene.
  const rader = (o.enheter && o.enheter.length) ? o.enheter : [{
    enhet_navn: o.enhet_navn, status: o.status, status_navn: o.status_navn,
    status_tidspunkt: o.status_tidspunkt,
  }];
  return rader.map((e) => {
    const statusTid = e.status_tidspunkt ? ` · ${tidSiden(e.status_tidspunkt)}` : '';
    const meta = `${e.status_navn}${statusTid}`;
    return `<span class="enhet-brikke">
      <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
      <span>${escapeHtml(e.enhet_navn)}</span>
      <span class="oppdrag-meta">${escapeHtml(meta)}</span>
    </span>`;
  }).join('');
}


// ── Detaljvisning ───────────────────────────────────────

function tidslinjeHtml(data) {
  // Unionen av statusmeldinger og enhetsbytter. De to er skilt i databasen
  // fordi et bytte ikke er en status og statistikken måler statusene; å slå
  // dem sammen her er en visningsjobb.
  const rader = [];

  const erstattet = new Set(
    (data.historikk || []).filter((m) => m.korrigerer).map((m) => m.korrigerer));
  const flere = (data.enheter || []).length > 1;

  (data.historikk || []).forEach((m) => {
    // Markøren for et avledet tidspunkt sitter på KLOKKESLETTET, ikke på
    // statusordet: det er tidspunktet som er utledet, ikke at oppdraget ble
    // ledig. Ingen badge — den ville konkurrert med statusen.
    const tidKlasse = m.automatisk ? 'tidslinje-tid tid-avledet' : 'tidslinje-tid';
    const tittel = m.automatisk
      ? ' title="Avsluttet automatisk da enheten startet neste oppdrag"'
      : '';
    const notat = [];
    if (m.automatisk) notat.push('avsluttet automatisk');
    if (m.forsinket) notat.push('meldt forsinket');
    if (m.korrigerer) notat.push('rettet av sentralen');
    // §9: sentralbordet førte statusen — og hvem, for det er ikke bilen.
    if (m.manuell) notat.push('ført av sentralen' + (m.meldt_av ? ` (${m.meldt_av})` : ''));
    const erErstattet = erstattet.has(m.id);
    const klasse = erErstattet ? 'tidslinje-rad tidslinje-erstattet' : 'tidslinje-rad';
    const notatBlokk = notat.length
      ? `<span class="tidslinje-notat">· ${escapeHtml(notat.join(', '))}</span>`
      : '';
    // Kun gjeldende rader kan rettes. En overstyrt rad beskriver ikke lenger
    // noe som gjelder, og serveren avviser den uansett — knappen skal ikke
    // tilby noe som er stengt.
    const rettKnapp = (OPPDRAG_TILGANG.kanSkrive && !erErstattet)
      ? `<button type="button" class="btn btn-link btn-sm tidslinje-rett p-0 ms-2"
                 data-action="visRettTid" data-id="${escHtmlValue(m.id)}">Rett tid</button>`
      : '';
    // «Avreist → Sykehus» — stedet ved statusen, som på enhetsskjermen.
    // Og med flere enheter: hvem sin — «KARM 12: Fremme». Med én står
    // navnet alt i tittelen.
    const hvem = (flere && m.enhet_navn) ? m.enhet_navn + ': ' : '';
    const statusMedSted = hvem + (m.sted_navn ? `${m.status_navn} → ${m.sted_navn}` : String(m.status_navn));
    rader.push({
      tid: m.tidspunkt,
      html: `
        <div class="${klasse}" id="tidslinje-rad-${escHtmlValue(m.id)}">
          <span class="${tidKlasse}"${tittel}>${escapeHtml(klokke(m.tidspunkt))}</span>
          <span>${escapeHtml(statusMedSted)}</span>
          ${notatBlokk}
          ${rettKnapp}
        </div>`,
    });
  });

  (data.enhetsbytter || []).forEach((b) => {
    rader.push({
      tid: b.tidspunkt,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(b.tidspunkt))}</span>
          <span>Flyttet ${escapeHtml(b.fra_enhet)} → ${escapeHtml(b.til_enhet)}</span>
          <span class="tidslinje-notat">· ${escapeHtml(b.byttet_av)}</span>
        </div>`,
    });
  });

  rader.sort((a, b) => new Date(a.tid) - new Date(b.tid));
  if (!rader.length) return '<div class="tom-melding">Ingen hendelser ennå.</div>';
  return rader.map((r) => r.html).join('');
}


async function visOppdrag(id) {
  apentOppdragId = id;
  const modalEl = document.getElementById('oppdragDetaljModal');
  const innhold = document.getElementById('detalj-innhold');
  innhold.innerHTML = ('<div class="tom-melding">Laster…</div>');
  bootstrap.Modal.getOrCreateInstance(modalEl).show();

  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/`);
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    innhold.innerHTML = (
      `<div class="text-danger">${escapeHtml(d.message || 'Kunne ikke hente oppdraget.')}</div>`);
    return;
  }

  const o = d.data;
  apentOppdrag = o;
  const navn = (o.enheter || []).map((e) => e.enhet_navn).join(', ') || o.enhet_navn;
  document.getElementById('detalj-tittel').textContent =
    `#${o.nummer} ${o.problemstilling} – ${navn}`;
  const enheterFeil = document.getElementById('enheter-feil');
  if (enheterFeil) enheterFeil.classList.add('d-none');

  // Ferdigstilte oppdrag går til historikken av seg selv i `sett_status`, så
  // knappen her er for hånd-tilfellene: hent tilbake til tavla, og rydd bort
  // igjen etterpå. Vises bare når den kan brukes — et pågående oppdrag skal
  // ikke kunne ryddes bort, og en knapp som alltid feiler er verre enn ingen.
  const historikkKnapp = (OPPDRAG_TILGANG.kanSkrive && o.status === 'ledig')
    ? (o.historikk_fra
      ? `<button class="btn btn-outline-secondary btn-sm" type="button"
                 data-action="hentTilbakeOppdrag" data-id="${escHtmlValue(o.id)}">
           Hent tilbake til tavla</button>`
      : `<button class="btn btn-outline-secondary btn-sm" type="button"
                 data-action="flyttTilHistorikk" data-id="${escHtmlValue(o.id)}">
           <i class="bi bi-clock-history me-1"></i>Legg i historikk</button>`)
    : '';

  // Med flere enheter er «flytt» flytt av én rad — hvilken, spørres om.
  const flyttFra = (o.enheter || []).length > 1
    ? `<select id="flytt-fra" class="form-select" aria-label="Flytt fra">
        ${(o.enheter || []).map((e) => `<option value="${escHtmlValue(e.enhet_id)}">${escapeHtml(e.enhet_navn)}</option>`).join('')}
       </select><span class="input-group-text">→</span>`
    : '';
  const flyttValg = OPPDRAG_TILGANG.kanSkrive
    ? `
      <hr>
      <label class="form-label" for="flytt-enhet">Flytt til enhet</label>
      <div class="input-group">
        ${flyttFra}
        <select id="flytt-enhet" class="form-select">
          ${enheter.map((e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('')}
        </select>
        <button class="btn btn-outline-primary" type="button"
                data-action="flyttOppdrag" data-id="${escHtmlValue(o.id)}">Flytt</button>
      </div>
      <div id="flytt-feil" class="text-danger small mt-2 d-none"></div>`
    : '';

  innhold.innerHTML = (`
    <div class="oppdrag-meta mb-2">
      <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
      <span class="ms-2">${escapeHtml(o.lokasjon_navn)}</span>
      <span class="ms-2">${escapeHtml(o.status_navn)}</span>
    </div>
    ${o.fritekst ? `<div class="oppdrag-fritekst mb-3">${escapeHtml(o.fritekst)}</div>` : ''}
    <h6 class="text-muted">Enheter</h6>
    <div class="mb-3">${mkEnhetsrader(o)}${OPPDRAG_TILGANG.kanSkrive ? _varsleValg(o) : ''}</div>
    <h6 class="text-muted">Tidslinje</h6>
    ${tidslinjeHtml(o)}
    ${historikkKnapp ? `<div class="mt-3">${historikkKnapp}</div>` : ''}
    ${flyttValg}`);
}


// ── Enhetene på oppdraget (flere enheter, 11. sep. 2026) ───────────
// Radene i detaljvisningen, med handlingene per enhet: «Før status» (§9),
// «Gjenåpne» og «Ta av». Og «Varsle enhet til» under dem. Alle går på
// `apentOppdrag` — klikkdelegeringen sender ett argument, og det er enheten.

//: Oppdraget som står åpent i detaljmodalen, som data. `apentOppdragId`
//: under er ID-en alene; handlingene per enhet trenger radene.
let apentOppdrag = null;


function mkEnhetsrader(o) {
  const flere = (o.enheter || []).length > 1;
  return (o.enheter || []).map((e) => {
    const statusTid = e.status_tidspunkt
      ? ` ${klokke(e.status_tidspunkt)} · ${tidSiden(e.status_tidspunkt)}` : '';
    const meta = `${e.status_navn}${statusTid}`;
    const knapper = OPPDRAG_TILGANG.kanSkrive ? _enhetsknapper(e, flere) : '';
    return `
      <div class="enhet-rad" id="enhet-rad-${escHtmlValue(e.enhet_id)}">
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <span class="enhet-rad-navn">${escapeHtml(e.enhet_navn)}</span>
        <span class="oppdrag-meta">${escapeHtml(meta)}</span>
        <span class="ms-auto d-flex gap-1 flex-wrap">${knapper}</span>
      </div>`;
  }).join('');
}


function _enhetsknapper(e, flere) {
  // Bare knappene som kan brukes: «Ta av» mens hun venter og ikke er den
  // siste, «Gjenåpne» når hun er ledig, «Før status» ellers. En knapp som
  // alltid feiler er verre enn ingen.
  const ut = [];
  if (e.status !== 'ledig') {
    ut.push(`<button type="button" class="btn btn-outline-primary btn-sm"
                     data-action="visFoerStatus" data-id="${escHtmlValue(e.enhet_id)}">Før status</button>`);
  } else {
    ut.push(`<button type="button" class="btn btn-outline-secondary btn-sm"
                     data-action="gjenaapneEnhet" data-id="${escHtmlValue(e.enhet_id)}">Gjenåpne</button>`);
  }
  if (e.status === 'venter' && flere) {
    ut.push(`<button type="button" class="btn btn-outline-danger btn-sm"
                     data-action="taAvEnhet" data-id="${escHtmlValue(e.enhet_id)}">Ta av</button>`);
  }
  return ut.join('');
}


function _varsleValg(o) {
  // Enhetene på vakt som ikke alt står på oppdraget.
  const paa = new Set((o.enheter || []).map((e) => e.enhet_id));
  const ledige = enheter.filter((e) => e.pa_vakt && !paa.has(e.id));
  if (!ledige.length) return '';
  const valg = ledige.map(
    (e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('');
  return `
    <div class="input-group input-group-sm mt-2">
      <select id="varsle-enhet" class="form-select" aria-label="Enhet å varsle">${valg}</select>
      <button class="btn btn-outline-primary" type="button"
              data-action="varsleEnhet" data-id="${escHtmlValue(o.id)}">Varsle enhet til</button>
    </div>`;
}


function _lovligeOverganger(status) {
  // Speiler `services.OVERGANGER`: neste ledd i kjeden, og «Ledig» fra alt.
  // Serveren avgjør uansett; dette er hva nedtrekket tilbyr.
  const kjede = STATUS_REKKEFOLGE.filter((s) => s !== 'ledig');
  const i = kjede.indexOf(status);
  const ut = [];
  if (i >= 0 && i + 1 < kjede.length) ut.push(kjede[i + 1]);
  if (status !== 'ledig') ut.push('ledig');
  return ut;
}


function _visEnhetsfeil(melding) {
  const el = document.getElementById('enheter-feil');
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


async function _enhetshandling(url, metode, feiltekst) {
  const res = await apiFetch(url, { method: metode });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    _visEnhetsfeil(d.message || feiltekst);
    return false;
  }
  if (apentOppdragId !== null) await visOppdrag(apentOppdragId);
  await lastAlt();
  return true;
}


async function varsleEnhet(oppdragId) {
  const valg = document.getElementById('varsle-enhet');
  if (!valg || !valg.value) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${oppdragId}/enheter/${Number(valg.value)}/`, 'POST',
    'Kunne ikke varsle enheten.');
}


async function taAvEnhet(enhetId) {
  if (apentOppdragId === null) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/`, 'DELETE',
    'Kunne ikke ta enheten av.');
}


async function gjenaapneEnhet(enhetId) {
  if (apentOppdragId === null) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/gjenaapne/`, 'POST',
    'Kunne ikke gjenåpne.');
}


function visFoerStatus(enhetId) {
  const rad = document.getElementById(`enhet-rad-${enhetId}`);
  if (!rad || rad.querySelector('.foer-skjema')) return;
  const e = ((apentOppdrag && apentOppdrag.enheter) || [])
    .find((x) => Number(x.enhet_id) === Number(enhetId));
  if (!e) return;

  const navn = window.OPPDRAG_STATUS_NAVN || {};
  const statusvalg = _lovligeOverganger(e.status).map(
    (st) => `<option value="${escHtmlValue(st)}">${escapeHtml(navn[st] || st)}</option>`).join('');
  const stedvalg = (window.OPPDRAG_AVREIST_TIL || []).map(
    ([nokkel, tekst]) => `<option value="${escHtmlValue(nokkel)}">${escapeHtml(tekst)}</option>`).join('');
  // Som «Rett tid»: `datetime-local` vil ha lokal tid uten sone, og nå er
  // utgangspunktet — operatøren fører noe som skjedde for litt siden.
  const naa = new Date();
  const lokal = new Date(naa.getTime() - naa.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16);

  const skjema = document.createElement('div');
  skjema.className = 'foer-skjema mt-1 d-flex gap-2 align-items-center flex-wrap w-100';
  skjema.innerHTML = (`
    <select id="foer-status" class="form-select form-select-sm w-auto" aria-label="Status">${statusvalg}</select>
    <select id="foer-sted" class="form-select form-select-sm w-auto" aria-label="Sted ved Avreist">
      <option value="">Sted (ved Avreist)</option>${stedvalg}</select>
    <input type="datetime-local" class="form-control form-control-sm w-auto"
           id="foer-tid" value="${lokal}" step="60">
    <button type="button" class="btn btn-sm btn-primary"
            id="foer-lagre" data-action="lagreFoerStatus" data-id="${escHtmlValue(enhetId)}">Før</button>
    <button type="button" class="btn btn-sm btn-outline-secondary"
            data-action="avbrytFoerStatus">Avbryt</button>
    <span id="foer-feil" class="text-danger small"></span>`);
  rad.appendChild(skjema);
  document.getElementById('foer-tid').focus();
}


function avbrytFoerStatus() {
  document.querySelectorAll('.foer-skjema').forEach((el) => el.remove());
}


async function lagreFoerStatus(enhetId) {
  const status = document.getElementById('foer-status');
  const sted = document.getElementById('foer-sted');
  const tid = document.getElementById('foer-tid');
  const feil = document.getElementById('foer-feil');
  if (!status || !tid || !tid.value || apentOppdragId === null) return;

  await withSubmitGuard('foer-lagre', async () => {
    // Stedet hører til «Avreist» og ingen annen status — sendes bare da.
    const stedLedd = (status.value === 'avreist' && sted && sted.value) ? `${sted.value}/` : '';
    const res = await apiFetch(
      `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/status/${status.value}/${stedLedd}`, {
        method: 'POST',
        // Ingen sone på `datetime-local`; serveren tolker den som lokal tid.
        body: JSON.stringify({ tidspunkt: tid.value }),
      });
    const d = await res.json();
    if (!res.ok || d.status !== 'ok') {
      feil.textContent = d.message || 'Kunne ikke føre statusen.';
      return;
    }
    await visOppdrag(apentOppdragId);
    await lastAlt();
  });
}


// ── Korreksjon av tidspunkt ─────────────────────────────
// Rettingen skriver en NY rad som peker på den gamle; begge blir stående i
// tidslinjen. Se §4.4 i beslutningsnotatet — `Statusmelding` er et spor av
// hva som ble meldt, ikke en tilstand som overskrives.

//: Oppdraget som står åpent i detaljmodalen. Trengs fordi tidslinjen må
//: tegnes på nytt etter en retting, og rettingen kjenner bare meldings-ID-en.
let apentOppdragId = null;


function visRettTid(meldingId) {
  const rad = document.getElementById(`tidslinje-rad-${meldingId}`);
  if (!rad || rad.querySelector('.rett-tid-skjema')) return;

  // `datetime-local` vil ha lokal tid uten sone. Klokkeslettet som allerede
  // står i raden er utgangspunktet — operatøren retter et minutt eller to,
  // hun skriver ikke inn datoen på nytt.
  const naa = new Date();
  const lokal = new Date(naa.getTime() - naa.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16);

  const skjema = document.createElement('div');
  skjema.className = 'rett-tid-skjema mt-1 d-flex gap-2 align-items-center flex-wrap';
  // En streng, ikke `trustedHtml(...)`: den pakker inn i et objekt for
  // `cellHtml()`, og som innerHTML blir det «[object Object]». Skjemaet sto
  // slik fra fase 3 til 11. sep. 2026 — «Rett tid» viste ingenting.
  skjema.innerHTML = (`
    <input type="datetime-local" class="form-control form-control-sm w-auto"
           id="rett-tid-verdi" value="${lokal}">
    <button type="button" class="btn btn-sm btn-primary"
            id="rett-tid-lagre" data-action="lagreRettTid" data-id="${meldingId}">Lagre</button>
    <button type="button" class="btn btn-sm btn-outline-secondary"
            data-action="avbrytRettTid">Avbryt</button>
    <span id="rett-tid-feil" class="text-danger small"></span>`);
  rad.appendChild(skjema);
  document.getElementById('rett-tid-verdi').focus();
}


function avbrytRettTid() {
  document.querySelectorAll('.rett-tid-skjema').forEach((el) => el.remove());
}


async function lagreRettTid(meldingId) {
  const felt = document.getElementById('rett-tid-verdi');
  const feil = document.getElementById('rett-tid-feil');
  if (!felt || !felt.value) return;

  await withSubmitGuard('rett-tid-lagre', async () => {
    const res = await apiFetch(`/oppdrag/api/statusmelding/${meldingId}/korriger/`, {
      method: 'POST',
      // Ingen sone på `datetime-local`; serveren tolker den som lokal tid.
      body: JSON.stringify({ tidspunkt: felt.value }),
    });
    const d = await res.json();
    if (!res.ok || d.status !== 'ok') {
      // Feilen navngir hvilken nabo som er i veien, så den skal stå i
      // skjemaet der operatøren kan handle på den — ikke i en alert.
      feil.textContent = d.message || 'Kunne ikke rette tidspunktet.';
      return;
    }
    // Tegn detaljvisningen på nytt: både tidslinjen og den gjeldende raden
    // har endret seg, og å flikke på DOM-en her ville duplisert regelen om
    // hvilken rad som vinner.
    if (apentOppdragId !== null) await visOppdrag(apentOppdragId);
    await lastAlt();
  });
}


async function flyttOppdrag(id) {
  const valg = document.getElementById('flytt-enhet');
  const fra = document.getElementById('flytt-fra');
  const feil = document.getElementById('flytt-feil');
  const kropp = { enhet_id: Number(valg.value) };
  if (fra) kropp.fra_enhet_id = Number(fra.value);
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/flytt/`, {
    method: 'POST',
    body: JSON.stringify(kropp),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    feil.textContent = d.message || 'Kunne ikke flytte oppdraget.';
    feil.classList.remove('d-none');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  await lastAlt();
}


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
    return `
    <div class="oppdrag-rad" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">#${escHtmlValue(o.nummer)}</span>
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(o.enhet_navn)} · ${escapeHtml(o.lokasjon_navn)} · ferdig ${escapeHtml(klokke(o.historikk_fra))}
      </div>
      ${fritekstBlokk}
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


function _valgteEnheter() {
  // I avkryssingsrekkefølge = listas rekkefølge; den første blir primær.
  return Array.from(document.querySelectorAll('input[name="nytt-enhet"]:checked'))
    .map((i) => Number(i.value));
}


function mkEnhetsvalg() {
  // Avkryssing, ikke nedtrekk: operatøren sender gjerne to biler på samme
  // hendelse. Bare enhetene på vakt — som nedtrekket var.
  return enheter.filter((e) => e.pa_vakt).map((e) => `
    <label class="form-check nytt-enhet-valg">
      <input class="form-check-input" type="checkbox" name="nytt-enhet" value="${escHtmlValue(e.id)}">
      <span class="form-check-label">${escapeHtml(e.navn)}</span>
    </label>`).join('');
}


// ── Lokasjonsadmin ──────────────────────────────────────

function renderLokasjonsadmin() {
  const el = document.getElementById('lokasjonsliste');
  if (!el) return;
  if (!lokasjoner.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen lokasjoner ennå.</div>');
    return;
  }
  el.innerHTML = (lokasjoner.map((l) => {
    const knapp = l.er_aktiv
      ? `<button class="btn btn-sm btn-outline-secondary" data-action="deaktiverLokasjon" data-id="${escHtmlValue(l.id)}">Deaktiver</button>`
      : `<button class="btn btn-sm btn-outline-success" data-action="aktiverLokasjon" data-id="${escHtmlValue(l.id)}">Aktiver</button>`;
    const dempet = l.er_aktiv ? '' : ' text-muted';
    return `
    <div class="d-flex align-items-center gap-2 py-1">
      <span class="flex-grow-1${dempet}">${escapeHtml(l.navn)}</span>
      ${knapp}
    </div>`;
  }).join(''));
}


async function lastLokasjonsadmin() {
  await lastLokasjoner();
  renderLokasjonsadmin();
}


async function leggTilLokasjon() {
  const felt = document.getElementById('ny-lokasjon');
  const navn = (felt.value || '').trim();
  if (!navn) return;
  const res = await apiFetch('/oppdrag/api/lokasjoner/', {
    method: 'POST',
    body: JSON.stringify({ navn }),
  });
  if (res.ok) {
    felt.value = '';
    await lastLokasjonsadmin();
  }
}


async function _settLokasjonAktiv(id, aktiv) {
  await apiFetch(`/oppdrag/api/lokasjoner/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ er_aktiv: aktiv }),
  });
  await lastLokasjonsadmin();
}

async function deaktiverLokasjon(id) { await _settLokasjonAktiv(id, false); }
async function aktiverLokasjon(id) { await _settLokasjonAktiv(id, true); }


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

    return `
    <div class="${radKlasse} mb-2">
      <div class="flex-grow-1">
        <div class="enhet-navn">${escapeHtml(e.navn)} <span class="enhet-meta">· ${escapeHtml(status)}</span></div>
        <div class="${koblingKlasse}">${escapeHtml(koblingTekst)}</div>
      </div>
      ${vaktKnapp}
    </div>`;
  }).join(''));
}


async function lastEnhetsadmin() {
  // `?alle=1` tar med pensjonerte enheter. Tavla skal ikke se dem, men lista
  // skal: en pensjonert bil er ikke borte, den venter på at kontoen sin
  // opprettes igjen.
  const res = await apiFetch('/oppdrag/api/enheter/?alle=1');
  if (res.ok) enhetsadmin = (await res.json()).data || [];
  renderEnhetsadmin();
}


// ── Lasting ─────────────────────────────────────────────

async function lastEnheter() {
  const res = await apiFetch('/oppdrag/api/enheter/', {
    headers: etagEnheter ? { 'If-None-Match': etagEnheter } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagEnheter = res.headers.get('ETag');
  enheter = (await res.json()).data || [];

  // **Bufferet tømmes bare når noe faktisk endret seg** — etter 304-sjekken,
  // ikke før. Tømte vi det på hver runde, ville et åpent panel stått på
  // «Henter…» for alltid: `undefined` betyr «ikke hentet», og ingenting
  // ville hentet det på nytt.
  //
  // Står et panel åpent, hentes det på nytt her. Et tall om hvem som er i
  // bilen skal ikke bli stående fra forrige time.
  besetninger = {};
  if (apenBesetning !== null) hentBesetning(apenBesetning);
  return true;
}


async function lastOppdrag() {
  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    headers: etagOppdrag ? { 'If-None-Match': etagOppdrag } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagOppdrag = res.headers.get('ETag');
  oppdragsliste = (await res.json()).data || [];
  return true;
}


async function lastLokasjoner() {
  const res = await apiFetch('/oppdrag/api/lokasjoner/');
  if (!res.ok) return;
  lokasjoner = (await res.json()).data || [];
}


function fyllNedtrekk() {
  const enhetsvalg = document.getElementById('nytt-enheter');
  if (enhetsvalg) {
    enhetsvalg.innerHTML = mkEnhetsvalg()
      || '<div class="tom-melding">Ingen enheter på vakt.</div>';
  }
  const lokvalg = document.getElementById('nytt-lokasjon');
  if (lokvalg) {
    const aktive = lokasjoner.filter((l) => l.er_aktiv);
    lokvalg.innerHTML = (aktive.map(
      (l) => `<option value="${escHtmlValue(l.id)}">${escapeHtml(l.navn)}</option>`).join(''));
  }
}


function visManglendeOppsett() {
  // Et skjema som lar deg trykke «Opprett» og så feiler med «Ukjent enhet» er
  // verre enn et som sier fra på forhånd hva som mangler.
  const boks = document.getElementById('mangler-oppsett');
  if (!boks) return;
  const mangler = [];
  if (!enheter.filter((e) => e.pa_vakt).length) mangler.push('ingen enheter på vakt');
  if (!lokasjoner.filter((l) => l.er_aktiv).length) mangler.push('ingen aktive lokasjoner');

  const knapp = document.querySelector('[data-bs-target="#nyttOppdragModal"]');
  if (mangler.length) {
    document.getElementById('mangler-hva').textContent = ' Portalen har ' + mangler.join(' og ') + '.';
    boks.classList.remove('d-none');
    if (knapp) knapp.disabled = true;
  } else {
    boks.classList.add('d-none');
    if (knapp) knapp.disabled = false;
  }
}


async function lastAlt() {
  const [nyeEnheter, nyeOppdrag] = await Promise.all([lastEnheter(), lastOppdrag()]);
  if (nyeEnheter) renderEnheter();
  if (nyeOppdrag) renderOppdrag();
  if (nyeEnheter) fyllNedtrekk();
  visManglendeOppsett();
}


// ── Vaktarkiv (fase 7) ───────────────────────────────────────────────────
//
// Kun global admin ser knappen, og serveren gater alle fire endepunktene på
// nytt. Arkivering fryser vakta med signatur; historikken over rydder tavla
// og er reversibel. To handlinger, to knapper.

let arkivliste = [];

function renderArkiv() {
  const el = document.getElementById('arkivliste');
  if (!el) return;
  if (!arkivliste.length) {
    el.innerHTML = '<div class="tom-melding">Ingen arkiverte vakter ennå.</div>';
    return;
  }
  el.innerHTML = arkivliste.map((a) => {
    const kollaps = a.kollapset
      ? '<span class="oppdrag-meta">· radene er slettet, kun tall igjen</span>'
      : '';
    return `
    <div class="oppdrag-rad">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-problem">${escapeHtml(a.tittel)}</span>
        <span class="oppdrag-nr">${escHtmlValue(a.antall_oppdrag)} oppdrag</span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(a.vakt_navn)} · arkivert av ${escapeHtml(a.importert_av)}
        ${kollaps}
      </div>
      <div class="mt-2 d-flex gap-2">
        <button class="btn btn-sm btn-outline-secondary" type="button"
                data-action="visArkiv" data-id="${escHtmlValue(a.id)}">Vis tall</button>
        <button class="btn btn-sm btn-outline-danger" type="button"
                data-action="slettArkiv" data-id="${escHtmlValue(a.id)}">Slett</button>
      </div>
      <div id="arkiv-detalj-${escHtmlValue(a.id)}" class="mt-2"></div>
    </div>`;
  }).join('');
}


async function lastArkiv() {
  const res = await apiFetch('/oppdrag/api/arkiv/');
  if (!res.ok) return;
  arkivliste = (await res.json()).data || [];
  renderArkiv();
}


async function arkiverVakt() {
  const feil = document.getElementById('arkiv-feil');
  feil?.classList.add('d-none');
  await withSubmitGuard('arkiv-knapp', async () => {
    const notat = (document.getElementById('arkiv-notat')?.value || '').trim();
    const res = await apiFetch('/oppdrag/api/arkiv/', {
      method: 'POST',
      body: JSON.stringify({ notat }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      // Inline, ikke alert(): meldingen hører hjemme ved knappen som
      // feilet, og en alert forsvinner før man rekker å lese den.
      if (feil) {
        feil.textContent = d.message || 'Arkivering feilet.';
        feil.classList.remove('d-none');
      }
      return;
    }
    const notatfelt = document.getElementById('arkiv-notat');
    if (notatfelt) notatfelt.value = '';
    await lastArkiv();
  });
}


async function visArkiv(id) {
  const boks = document.getElementById(`arkiv-detalj-${id}`);
  if (!boks) return;
  if (boks.innerHTML) { boks.innerHTML = ''; return; }   // klikk igjen = lukk

  const res = await apiFetch(`/oppdrag/api/arkiv/${id}/`);
  if (!res.ok) return;
  const a = (await res.json()).data || {};
  const s = a.stats && a.stats.summary ? a.stats.summary : null;
  if (!s) { boks.innerHTML = '<div class="tom-melding">Ingen tall.</div>'; return; }

  // Signaturen er hele poenget med et arkiv: stemmer den ikke, skal det stå
  // først og tydelig, ikke som en detalj under tallene.
  const tukling = a.tamper_detected
    ? '<div class="text-danger fw-bold mb-1">Signaturen stemmer ikke — arkivet kan være endret.</div>'
    : '';
  boks.innerHTML = `
    ${tukling}
    <div class="oppdrag-meta">
      ${escHtmlValue(s.total)} oppdrag · ${escHtmlValue(s.fullforte)} fullført ·
      median responstid ${escHtmlValue(fmtMin(s.responstid.median))} ·
      median oppdragstid ${escHtmlValue(fmtMin(s.oppdragstid.median))}
    </div>
    <div class="oppdrag-meta">SHA-256: ${escapeHtml((a.sha256 || '').slice(0, 16))}…</div>`;
}


async function slettArkiv(id) {
  if (!confirm('Slette arkivet? Det kan ikke angres, og arkivet er det '
             + 'eneste som står igjen etter at vakta er avsluttet.')) return;
  const res = await apiFetch(`/oppdrag/api/arkiv/${id}/`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm: true }),
  });
  if (!res.ok) return;
  await lastArkiv();
}


document.addEventListener('DOMContentLoaded', async () => {
  await lastLokasjoner();
  await lastAlt();
  renderEnheter();
  renderOppdrag();
  fyllNedtrekk();
  visManglendeOppsett();
  // Samme kadens som pasientlista. ETag gjør at et poll uten endring koster
  // en 304 uten kropp.
  setInterval(lastAlt, 30000);
  // «12 min siden» eldes uten at serveren sier noe — lista svarer 304 når
  // ingenting er endret. Én tegning i minuttet holder tallene ærlige.
  setInterval(() => { renderOppdrag(); renderEnheter(); }, 60000);
});
