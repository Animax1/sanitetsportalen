// ════════════════════════════════════════════════════════
// oppdrag-sentral-oppdrag.js
// ════════════════════════════════════════════════════════
//
// Oppdragslista, detaljvisningen, enhetene på oppdraget og korreksjoner.
//
// Delt ut av `oppdrag-sentral.js` 14. sep. 2026 (gjeldspunkt 3.6).
// Fila var 1 991 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/oppdrag/sentral.html` og deler ett globalt navnerom som
// før. `JsSplittenErKompletTests` håndhever at ingen funksjon forsvant
// eller ble duplisert.
// ════════════════════════════════════════════════════════

// ── Oppdragsliste ───────────────────────────────────────

function renderOppdrag() {
  const el = document.getElementById('oppdragsliste');
  if (!el) return;

  if (!oppdragsliste.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen oppdrag i vakten ennå.</div>');
    if (typeof koEtterOppdragTegnet === 'function') koEtterOppdragTegnet();
    return;
  }

  // Filteret er KOs (19. sep. 2026: «filter knapp for ventende oppdrag»),
  // gjennom en vakt — på `/oppdrag/` finnes det ikke.
  const synlige = (typeof koOppdragFilter === 'function') ? koOppdragFilter(oppdragsliste) : oppdragsliste;
  if (!synlige.length) {
    // Tomt fordi filteret tok alt, eller tomt fordi tavla er tom.
    const tom = (typeof koOppdragTomMelding === 'function') ? koOppdragTomMelding() : 'Ingen ventende oppdrag.';
    el.innerHTML = ('<div class="tom-melding">' + escapeHtml(tom) + '</div>');
    if (typeof koEtterOppdragTegnet === 'function') koEtterOppdragTegnet();
    return;
  }
  const sortert = _sorterOppdrag(synlige);
  // **Ingen hendelser i lista** (André, 18. sep. 2026): H-merket på raden
  // bærer koblingen, og hendelsene har sitt eget vindu i /ko/. Grupperingen
  // fra pulje 5 er borte. KO får beskjed etter tegningen — hendelsesloggen
  // leser oppdragene herfra — gjennom en vakt, fordi denne fila også kjører
  // på /oppdrag/, der `ko-hendelser.js` ikke finnes (CLAUDE.md).
  el.innerHTML = sortert.map(_oppdragRadHtml).join('');
  if (typeof koEtterOppdragTegnet === 'function') koEtterOppdragTegnet();
}


function _oppdragRadHtml(o) {
  // Én rad på tavla. Skilt ut av `renderOppdrag` 18. sep. 2026, da lista
  // fikk en gruppert visning — samme rad i begge.
  //
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
  const manglerKlasse = o.trenger_ressurs ? ' oppdrag-rad-mangler mangler-' + _manglerTrinn(o) : '';
  const venterKlasse = venterForbiTerskel(o) ? ' oppdrag-rad-venter-lenge' : '';
  // «Oppdrag 45 · Hendelse 12» (§6): visningen bærer relasjonen. Vises på
  // begge sidene — på `/oppdrag/` er det den ene sporet av KO. Merket bærer
  // også hendelsens prioritet (18. sep. 2026): rød trekant for Viktig.
  // Bare Viktig har et ikon; resten bærer fargen i hendelsesloggen.
  const prioIkon = o.hendelse_prioritet === 'viktig'
    ? '<i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>' : '';
  const hendelseMerke = o.hendelse_nummer
    ? `<span class="hendelse-merke" title="${escHtmlValue(o.hendelse_tittel || '')}">${prioIkon}${escHtmlValue(hendelsesnr(o.hendelse_nummer))}</span>`
    : '';
  // Lagene på hendelsen (André, 18. sep. 2026: «et felt med lagsressurser
  // som kobles til hendelsen … såfremt oppdraget er koblet til en hendelse»;
  // fra 19. sep. rader fra vaktlista, sendt som navn). Tom uten hendelse,
  // eller når hendelsen ikke har fått lag ennå.
  const lagNavn = (o.hendelse_id && Array.isArray(o.hendelse_lag)) ? o.hendelse_lag.join(', ') : '';
  const lagBlokk = lagNavn
    ? `<div class="oppdrag-meta oppdrag-lag mt-1"><i class="bi bi-people me-1"></i>Lag: ${escapeHtml(lagNavn)}</div>`
    : '';
  return `
    <div class="oppdrag-rad${manglerKlasse}${venterKlasse}" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">${escHtmlValue(oppdragsnr(o.nummer))}</span>
        ${hendelseMerke}
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        ${grovsortering}
        <span class="oppdrag-problem">${escapeHtml(_problemMedAntall(o))}</span>
        <span class="ms-auto d-flex align-items-center gap-1">
          <span class="status-prikk status-${escHtmlValue(o.status)}"></span>
          <span class="oppdrag-meta">${escapeHtml(statusTekst)}</span>
        </span>
      </div>
      <div class="enhetsmatrise mt-1">${_enhetsmatrise(o)}</div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(o.lokasjon_navn)} · ${escapeHtml(opprettetTekst)}
      </div>
      ${lagBlokk}
      ${fritekstBlokk}
    </div>`;
}


// «Fra loggen i H14» (KO, 19. sep. 2026): linjene KO har delt med dette
// oppdraget, i rekkefølge, med hvem og når. Lista er KOs og lest fra
// oppdraget (`delte_linjer`). På `/ko/` tegner KO blokka selv gjennom
// `koDelteLinjerHtml()` — der står også de interne linjene, med «Del» —
// og kallet går gjennom en vakt fordi `ko.js` er betinget lastet.
function _delteLinjerHtml(o) {
  if (!o.hendelse_id) return '';
  if (typeof koDelteLinjerHtml === 'function') return koDelteLinjerHtml(o);
  const linjer = Array.isArray(o.delte_linjer) ? o.delte_linjer : [];
  if (!linjer.length) return '';
  const rader = linjer.map((t) =>
    `<div class="b-tillegg">${escapeHtml(t.tekst)}<span class="hvem">${escapeHtml(t.av || '')} · ${escapeHtml(klokke(t.tid))}</span></div>`
  ).join('');
  const merke = `<span class="hendelse-merke">${escHtmlValue(hendelsesnr(o.hendelse_nummer))}</span>`;
  return `<div class="mb-3"><h6 class="text-muted">Fra loggen i ${merke}</h6>${rader}</div>`;
}


function _sorterOppdrag(liste) {
  // Ferdige nederst; ellers hastegraden KO/AMK satte, og innenfor den
  // nummeret — «Akutt #3» over «Akutt #7», og alle Akutt over alle Haster.
  // Statusen sorterer ikke lenger: det er hastegraden som sier hva som er
  // viktigst, og nummeret som sier hva som kom først.
  const rang = (h) => {
    const i = HASTEGRAD_REKKEFOLGE.indexOf(h);
    return i < 0 ? HASTEGRAD_REKKEFOLGE.length : i;
  };
  return [...liste].sort((a, b) => {
    const af = a.status === 'ledig' ? 1 : 0;
    const bf = b.status === 'ledig' ? 1 : 0;
    if (af !== bf) return af - bf;
    const ah = rang(a.hastegrad);
    const bh = rang(b.hastegrad);
    if (ah !== bh) return ah - bh;
    return (Number(a.nummer) || 0) - (Number(b.nummer) || 0);
  });
}


function lydTerskler() {
  // Samme tabell som bilen leser (`OPPDRAG_LYDVARSEL`); fallet tilbake er
  // første utgaves tall. Som funksjon — se `koNokkel()` i enhetsskjermen.
  const fra = globalThis.window?.OPPDRAG_LYDVARSEL;
  if (fra && typeof fra === 'object' && Object.keys(fra).length) return fra;
  return { Akutt: [60, 10], Haster: [300, 60], Vanlig: [900, 60], Drift: [900, 60] };
}


function venterForbiTerskel(o, naaMs) {
  // Utheving hos operatør (André, 12. sep. 2026): et oppdrag som venter på
  // at en bil skal trykke Rykker ut, forbi første lydterskel for
  // hastegraden. Tida regnes fra da den *første* ventende bilen ble varslet;
  // et oppdrag uten bil («trenger ny ressurs») har sin egen utheving.
  if (o.status !== 'venter' || o.trenger_ressurs) return false;
  const ventende = (o.enheter || []).filter((e) => e.status === 'venter' && e.varslet_at);
  if (!ventende.length) return false;
  const tidligst = Math.min(...ventende.map((e) => new Date(e.varslet_at).getTime()));
  const alle = lydTerskler();
  const [forste] = alle[o.hastegrad] || alle.Vanlig || [900];
  return ((naaMs || Date.now()) - tidligst) / 1000 >= forste;
}


function _manglerMinutter(o, naa) {
  // Fra bilen rykket videre — `trenger_ressurs_siden`. Eldre svar uten
  // feltet regner fra siste status.
  const fra = o.trenger_ressurs_siden || o.status_tidspunkt || o.opprettet;
  if (!fra) return 0;
  const ms = (naa ? new Date(naa) : new Date()) - new Date(fra);
  return Math.max(0, Math.floor(ms / 60000));
}


function _manglerTrinn(o, naa) {
  // Trinnene er visuelle, ikke regler: raden skal skille seg mer ut jo
  // lenger oppdraget har stått uten noen (André, 12. sep. 2026: «gjerne som
  // blir tydeligere desto lenger tiden går»).
  const min = _manglerMinutter(o, naa);
  return (MANGLER_TRINN.find(([grense]) => min >= grense) || [0, 'ny'])[1];
}


function _enhetsmatrise(o) {
  // Én brikke per enhet: navn, status og tid siden — matrisen fra §4 i
  // notatet om flere enheter. Oppdragets egen status står fortsatt til
  // høyre i raden; den er utledet av disse. Uten `enheter` (eldre svar)
  // er det én brikke av toppnivåfeltene.
  // Uten `enheter` (eldre svar) er det én brikke av toppnivåfeltene; uten
  // enhet i det hele tatt (opprettet uten, 19. sep. 2026) ingen.
  const rader = (o.enheter && o.enheter.length) ? o.enheter : (o.enhet_navn ? [{
    enhet_navn: o.enhet_navn, status: o.status, status_navn: o.status_navn,
    status_tidspunkt: o.status_tidspunkt,
  }] : []);
  // Bilen rykket videre og ingen har tatt over (André, 12. sep. 2026):
  // merket står først, så det er det første 113 ser på raden — med egen
  // trekant, ikke statusprikken bilene har, og med tida det har stått.
  // Bilene som er ferdige med det står i loggen, ikke i lista: «den bilen
  // må vekk» — ellers ser oppdraget bemannet ut.
  const mangler = o.trenger_ressurs
    ? `<span class="enhet-brikke enhet-brikke-mangler mangler-${escHtmlValue(_manglerTrinn(o))}">
      <i class="bi bi-exclamation-triangle-fill"></i>
      <span>Trenger ressurs · ${escHtmlValue(_manglerMinutter(o))} min</span>
    </span>` : '';
  // **«Avbrutt» er ikke «trenger ny ressurs»** (André, 15. sep. 2026). Avbrøt
  // en bil et oppdrag en annen alt hadde løst, sto det fram til da «trenger ny
  // ressurs» på et ferdig oppdrag; nå sier flagget bare om noen må sendes, og
  // dette merket hvem som avbrøt. Begge kan stå samtidig, og da er de to
  // opplysninger — hvem som falt fra, og at noen må ut.
  // **Merket står til noen har tatt stilling** (André, 15. sep. 2026: «det må
  // vises, og at det må løses av operatør»). Den andre veien — å sende en ny
  // enhet — kvitterer av seg selv på serveren; knappen her er for tilfellet
  // der ingen skal sendes. Den står *i* merket, der problemet vises, framfor
  // i et vindu man må åpne.
  //
  // `globalThis.OPPDRAG_TILGANG?.` og ikke det bare navnet: `_enhetsmatrise`
  // tegnes også der tilgangsobjektet ikke er satt, og en `ReferenceError`
  // her ville tatt ned hele oppdragslista — ikke bare skjult én knapp.
  const kvitter = globalThis.OPPDRAG_TILGANG?.kanSkrive
    ? `<button type="button" class="btn btn-link btn-sm p-0 ms-2 enhet-brikke-kvitter"
               data-action="kvitterAvbrutt" data-id="${escHtmlValue(o.id)}">Kvitter</button>`
    : '';
  const avbrutt = (o.avbrutt_av || []).length
    ? `<span class="enhet-brikke enhet-brikke-avbrutt">
      <i class="bi bi-x-octagon-fill"></i>
      <span>Avbrutt av ${escapeHtml((o.avbrutt_av || []).join(', '))}</span>
      ${kvitter}
    </span>` : '';
  // **«Avventer» er en tredje beskjed** (André, 16. sep. 2026): avbrutt sier
  // hva som skjedde, «trenger ny ressurs» krever handling nå, og avventer sier
  // at noen har svart — bare ikke ja.
  //
  // **Men den er en egenskap ved enhetens rad, ikke en deltaker til** (André,
  // 21. sep. 2026: «hvis du trykker avvent så klones det i oppdragslistens
  // oversikt»). Avventingen rører ikke koblingsraden — det er hele poenget
  // med den — så enheten står i `enheter` med status Venter *og* i
  // `avventer_av`, og et eget merke ved siden av tegnet henne to ganger.
  // Merket er derfor flyttet inn i hennes egen brikke.
  const synlige = o.trenger_ressurs ? rader.filter((e) => e.status !== 'ledig') : rader;
  return mangler + avbrutt + synlige.map((e) => {
    const statusTid = e.status_tidspunkt ? ` · ${tidSiden(e.status_tidspunkt)}` : '';
    const sted = e.sted_navn ? ` → ${e.sted_navn}` : '';
    const venter = enhetAvventer(o, e.enhet_navn);
    const meta = `${e.status_navn}${sted}${statusTid}${venter ? ' · avventer' : ''}`;
    // **«Lege 02 (passiv vakt)»** (André, 16. sep. 2026). Modusen er den som
    // sto da hun ble varslet, ikke den hun står i nå — serveren fryser den
    // på koblingsraden. Aktiv vises ikke: «Aktiv» på en ambulanse er støy,
    // og tomt felt betyr «dette spørsmålet gjaldt ikke henne».
    const modus = e.varslet_modus === 'passiv' ? ' (passiv vakt)' : '';
    const pause = venter ? '<i class="bi bi-pause-circle-fill"></i>' : '';
    return `<span class="enhet-brikke${venter ? ' enhet-brikke-avventer' : ''}">
      ${pause}<span class="status-prikk status-${escHtmlValue(e.status)}"></span>
      <span>${escapeHtml(e.enhet_navn + modus)}</span>
      <span class="oppdrag-meta">${escapeHtml(meta)}</span>
    </span>`;
  }).join('');
}


// **Avventer denne enheten på dette oppdraget?** Egen funksjon fordi den
// avgjør noe: står den som en `if` inne i byggeren, lar regelen seg ikke
// kjøre. `avventer_av` er navn, og `Enhet.navn` er unik.
function enhetAvventer(oppdrag, enhetNavn) {
  if (!enhetNavn) return false;
  return (oppdrag.avventer_av || []).includes(enhetNavn);
}


// ── Detaljvisning ───────────────────────────────────────

// **Én tekst per type, og ingen «ellers»** (André, 21. sep. 2026: «det må
// logges i oppdrags tidslinjen at en enhet blir satt på avvent»). Den sto
// som en ternær med «Tatt av» i siste gren, og da ble *hver* type som ikke
// var avbrutt eller rykket videre til «Tatt av» — en enhet satt på avvent
// sto i tidslinjen som tatt av oppdraget. Fallet er nå navnløst og ikke en
// påstand: en ny type i `Enhetshendelse` skal se rar ut, ikke lyve.
function enhetshendelseTekst(h) {
  const ord = {
    tatt_av: 'Tatt av',
    rykket_videre: 'Rykket videre',
    avbrutt: 'Avbrutt',
    avventer: 'Avventer',
  }[h.type] || h.type || 'Hendelse';
  const detalj = (h.type === 'rykket_videre' && h.detalj) ? ' til ' + h.detalj : '';
  return ord + detalj + ': ' + h.enhet_navn;
}


// «Hastegrad: Haster → Akutt». Notatet står uten verdier — samme regel som
// audit: at det ble endret, ikke hva det sto.
function endringTekst(e) {
  if (e.felt === 'fritekst') return 'Oppdragsnotat endret';
  const tekst = `${e.felt_navn}: ${e.fra || '–'} → ${e.til || '–'}`;
  return e.automatisk ? `${tekst} (passet ikke den nye hastegraden)` : tekst;
}

function tidslinjeHtml(data) {
  // Unionen av statusmeldinger og enhetsbytter. De to er skilt i databasen
  // fordi et bytte ikke er en status og statistikken måler statusene; å slå
  // dem sammen her er en visningsjobb.
  const rader = [];

  const erstattet = new Set(
    (data.historikk || []).filter((m) => m.korrigerer).map((m) => m.korrigerer));
  const flere = (data.enheter || []).length > 1;

  // Hvem som ble varslet, og hvem som ble tatt av (André, 12. sep. 2026).
  (data.enheter || []).forEach((e) => {
    if (!e.varslet_at) return;
    rader.push({
      tid: e.varslet_at,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(e.varslet_at))}</span>
          <span>Varslet: ${escapeHtml(e.enhet_navn)}</span>
        </div>`,
    });
  });
  (data.enhetshendelser || []).forEach((h) => {
    const tekst = enhetshendelseTekst(h);
    rader.push({
      tid: h.tidspunkt,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(h.tidspunkt))}</span>
          <span>${escapeHtml(tekst)}</span>
          <span class="tidslinje-notat">· ${escapeHtml(h.av)}</span>
        </div>`,
    });
  });

  // Endringene i verdiene (23. sep. 2026): et feilklikk skal ikke være stille.
  (data.endringer || []).forEach((e) => {
    rader.push({
      tid: e.tidspunkt,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(e.tidspunkt))}</span>
          <span>${escapeHtml(endringTekst(e))}</span>
          <span class="tidslinje-notat">· ${escapeHtml(e.av)}</span>
        </div>`,
    });
  });

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
    if (m.manuell) notat.push('endret av KO' + (m.meldt_av ? ` (${m.meldt_av})` : ''));
    // Trukket tilbake (22. sep. 2026): raden står, gjennomstreket, med hvem
    // og når — «loggen må bevares» (André). Det var «Angre» som slettet den.
    if (m.trukket_tilbake_at) {
      notat.push('trukket tilbake ' + klokke(m.trukket_tilbake_at)
                 + (m.trukket_tilbake_av ? ` av ${m.trukket_tilbake_av}` : ''));
    }
    const erErstattet = erstattet.has(m.id) || Boolean(m.trukket_tilbake_at);
    const klasse = erErstattet ? 'tidslinje-rad tidslinje-erstattet' : 'tidslinje-rad';
    const notatBlokk = notat.length
      ? `<span class="tidslinje-notat">· ${escapeHtml(notat.join(', '))}</span>`
      : '';
    // Kun gjeldende rader kan rettes. En overstyrt eller tilbaketrukket rad
    // beskriver ikke lenger noe som gjelder, og serveren avviser den uansett
    // — knappen skal ikke tilby noe som er stengt.
    const rettKnapp = (OPPDRAG_TILGANG.kanSkrive && !erErstattet)
      ? `<button type="button" class="btn btn-link btn-sm tidslinje-rett p-0 ms-2"
                 data-action="visRettTid" data-id="${escHtmlValue(m.id)}">Rett tid</button>`
      : '';
    // Ingen «Angre» her lenger (22. sep. 2026): «det er ikke intuitivt å
    // endre det der» (André). Et steg tilbake er et valg i «Endre status».
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

  // Opprettelsen er første hendelse (André, 12. sep. 2026). Den har ingen
  // «Rett tid»: den er ikke et stempel, og ingen melding kan rettes til før
  // den — serveren stopper det uansett.
  if (data.opprettet) {
    rader.push({
      tid: data.opprettet,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(data.opprettet))}</span>
          <span>Oppdrag opprettet</span>
        </div>`,
    });
  }

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
    `${oppdragsnr(o.nummer)} ${o.problemstilling} – ${navn}`;
  const enheterFeil = document.getElementById('enheter-feil');
  if (enheterFeil) enheterFeil.classList.add('d-none');
  innhold.classList.remove('foer-aapen');

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
  const flyttValg = OPPDRAG_TILGANG.kanSkrive ? _flyttValg(o) : '';

  // Hendelsen oppdraget hører til, med knytt/løsne — **KOs**, og bare på
  // `/ko/`: `ko.js` er betinget lastet, og kallet går gjennom en vakt
  // (CLAUDE.md). Markupen skannes i `ko/tests_js.py`, der byggeren bor.
  const hendelseValg = (typeof koHendelseValg === 'function') ? koHendelseValg(o) : '';
  // Lagene på hendelsen — samme blokk som på raden — og linjene KO har
  // delt fra loggen i hendelsen (skisse D), de samme som bilen ser.
  const lagNavn = (o.hendelse_id && Array.isArray(o.hendelse_lag)) ? o.hendelse_lag.join(', ') : '';
  const lagBlokk = lagNavn
    ? `<div class="oppdrag-meta oppdrag-lag mb-2"><i class="bi bi-people me-1"></i>Lag: ${escapeHtml(lagNavn)}</div>`
    : '';
  const beskrivelse = _delteLinjerHtml(o);
  const slettKnapp = o.kan_slettes
    ? `<button type="button" class="btn btn-outline-danger btn-sm" data-action="slettOppdrag"
               data-id="${escHtmlValue(o.id)}"><i class="bi bi-trash me-1"></i>Slett oppdrag</button>`
    : '';
  // **Verdiene står framme, og endres der de står** (backlog punkt 4 og 5,
  // 23. sep. 2026): «Rediger»-knappen gjemte det man åpnet oppdraget for.
  apentVerdivalg = null;
  apentNotat = false;
  innhold.innerHTML = (`
    <div class="oppdrag-verdier mb-2" id="oppdrag-verdier">${_verdierHtml(o, null, OPPDRAG_TILGANG.kanSkrive)}</div>
    <div class="text-danger small mb-2 d-none" id="verdi-feil"></div>
    ${hendelseValg}
    ${lagBlokk}
    ${beskrivelse}
    <div id="oppdrag-notat">${_notatHtml(o, false, OPPDRAG_TILGANG.kanSkrive)}</div>
    <h6 class="text-muted">Enheter</h6>
    <div class="mb-3">${mkEnhetsrader(o)}${OPPDRAG_TILGANG.kanSkrive ? _varsleValg(o) : ''}</div>
    <h6 class="text-muted">Tidslinje</h6>
    ${tidslinjeHtml(o)}
    ${(historikkKnapp || slettKnapp) ? `<div class="mt-3 d-flex gap-2 flex-wrap">${historikkKnapp}${slettKnapp}</div>` : ''}
    ${flyttValg}`);
}


// ── Enhetene på oppdraget (flere enheter, 11. sep. 2026) ───────────
// Radene i detaljvisningen, med handlingene per enhet: «Før status» (§9),
// «Gjenåpne» og «Ta av». Og «Legg til» under dem. Alle går på
// `apentOppdrag` — klikkdelegeringen sender ett argument, og det er enheten.

//: Oppdraget som står åpent i detaljmodalen, som data. `apentOppdragId`
//: under er ID-en alene; handlingene per enhet trenger radene.
let apentOppdrag = null;


function mkEnhetsrader(o) {
  const flere = (o.enheter || []).length > 1;
  return (o.enheter || []).map((e) => {
    const statusTid = e.status_tidspunkt
      ? ` ${klokke(e.status_tidspunkt)} · ${tidSiden(e.status_tidspunkt)}` : '';
    const sted = e.sted_navn ? ` → ${e.sted_navn}` : '';
    const venter = enhetAvventer(o, e.enhet_navn);
    const meta = `${e.status_navn}${sted}${statusTid}${venter ? ' · avventer' : ''}`;
    const knapper = OPPDRAG_TILGANG.kanSkrive ? _enhetsknapper(e, flere, o.id, venter) : '';
    return `
      <div class="enhet-rad" id="enhet-rad-${escHtmlValue(e.enhet_id)}">
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <span class="enhet-rad-navn">${escapeHtml(e.enhet_navn)}</span>
        <span class="oppdrag-meta">${escapeHtml(meta)}</span>
        <span class="ms-auto d-flex gap-1 flex-wrap">${knapper}</span>
      </div>`;
  }).join('');
}


function _enhetsknapper(e, flere, oppdragId, avventer) {
  // Bare knappene som kan brukes: «Ta av» mens hun venter og ikke er den
  // siste, og «Endre status» alltid. Også for den som er ledig — der sto
  // «Gjenåpne» til 22. sep. 2026; nå er det et steg tilbake i nedtrekket.
  // En knapp som alltid feiler er verre enn ingen.
  const ut = [];
  ut.push(`<button type="button" class="btn btn-outline-primary btn-sm"
                   data-action="visFoerStatus" data-id="${escHtmlValue(e.enhet_id)}">Endre status</button>`);
  if (e.status === 'venter' && flere) {
    ut.push(`<button type="button" class="btn btn-outline-danger btn-sm"
                     data-action="taAvEnhet" data-id="${escHtmlValue(e.enhet_id)}">Ta av</button>`);
  }
  // **«Avvent» er ikke «ta av»** (André, 16. sep. 2026). Hun blir stående
  // varslet, så «Rykk ut» er fortsatt tilgjengelig, og begge deler står i
  // loggen. Knappen vises bare før hun har rykket ut, og bare der
  // enhetstypen tillater det — `kanAvvente()` leser enhetslista, for
  // koblingsraden kjenner ikke typen.
  //
  // **Og ikke én gang til på en som alt avventer** (21. sep. 2026): raden
  // blir stående i `Venter` — det er hele poenget med avventingen — så
  // serveren tar imot trykk nummer to og skriver en `Enhetshendelse` til.
  // Da kom hun to ganger i tidslinjen og to ganger i hendelsens logg. Veien
  // videre for henne er «Endre status», som står ved siden av.
  if (e.status === 'venter' && !avventer && kanAvvente(e.enhet_id)) {
    ut.push(`<button type="button" class="btn btn-outline-secondary btn-sm"
                     data-action="avventOppdrag" data-arg="${escHtmlValue(oppdragId + ':' + e.enhet_id)}">Avvent</button>`);
  }
  return ut.join('');
}


function kanAvvente(enhetId) {
  // Flagget bor på enhetstypen og følger med i enhetslista; koblingsraden på
  // oppdraget kjenner bare enheten. Ett sted å slå det opp, så en knapp og et
  // endepunkt ikke svarer ulikt.
  const treff = (enheter || []).find((e) => e.id === enhetId);
  return !!(treff && treff.kan_avvente);
}


// «Flytt» (André, 19. sep. 2026: «viser alle enheter uavhengig om de er av
// eller ei … hvem er fra og hvem er til?»). «Til» er enheter **på vakt** som
// ikke alt står på oppdraget — samme utvalg som «Legg til». Med én enhet
// under «Fra» er den gitt og vises som tekst.
function _flyttValg(o) {
  const paa = new Set((o.enheter || []).map((e) => e.enhet_id));
  const kandidater = enheter.filter((e) => e.pa_vakt && !paa.has(e.id));
  const paaOppdraget = flyttFraEnheter(o);
  // Ingen har oppdraget — da er det ingenting å flytte *fra*, og veien
  // videre er å varsle en ny enhet. Knappen skal ikke tilby noe som er tomt.
  if (!paaOppdraget.length) {
    return `<hr>
      <div class="form-label">Flytt oppdraget til en annen enhet</div>
      <div class="form-text">Ingen enhet har oppdraget nå — bruk «Legg til» under Enheter.</div>`;
  }
  // Valgene bygges før mal-strengene — en nøstet mal-streng er usynlig for
  // XSS-skanneren (oppdrag/tests_xss.py).
  const fraValg = velgValg('') + paaOppdraget.map((e) => `<option value="${escHtmlValue(e.enhet_id)}">${escapeHtml(e.enhet_navn)}</option>`).join('');
  const tilValg = velgValg('') + kandidater.map((e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('');
  const fra = paaOppdraget.length > 1
    ? `<select id="flytt-fra" class="form-select" aria-label="Flytt fra enhet">${fraValg}</select>`
    : `<span class="input-group-text fw-semibold">${escapeHtml(paaOppdraget[0]?.enhet_navn || o.enhet_navn || '')}</span>`;
  const til = kandidater.length
    ? `<select id="flytt-enhet" class="form-select" aria-label="Flytt til enhet">${tilValg}</select>
       <button class="btn btn-outline-primary" type="button"
               data-action="flyttOppdrag" data-id="${escHtmlValue(o.id)}">Flytt</button>`
    : `<span class="input-group-text text-muted">ingen andre enheter på vakt</span>`;
  return `<hr>
      <div class="form-label">Flytt oppdraget til en annen enhet</div>
      <div class="input-group input-group-sm">
        <span class="input-group-text">Fra</span>
        ${fra}
        <span class="input-group-text">Til</span>
        ${til}
      </div>
      <div class="form-text">Enheten under «Fra» tas av oppdraget; status og stempler står.
        Skal en enhet <em>til</em> på oppdraget, bruk «Legg til» under Enheter.</div>
      <div id="flytt-feil" class="text-danger small mt-2 d-none"></div>`;
}


// **«Fra» er enhetene som fortsatt *har* oppdraget** (André, 21. sep. 2026:
// «fra lista viser alle biler — fra lista må bare vise biler som har
// oppdraget»). Koblingsraden blir stående når en bil melder seg `Ledig`:
// stemplene hennes skal bevares, og statistikken måler dem. Men da sto hun
// igjen i «Fra» på et oppdrag hun var ferdig med — og på et oppdrag som har
// gått gjennom to biler, så lista ut som hele flåten. `Ledig` er den ene
// statusen som betyr «ikke min lenger»; alle de andre er pågående.
function flyttFraEnheter(oppdrag) {
  return (oppdrag.enheter || []).filter((e) => e.status !== 'ledig');
}


function _varsleValg(o) {
  // Enhetene på vakt som ikke alt står på oppdraget.
  const paa = new Set((o.enheter || []).map((e) => e.enhet_id));
  const ledige = enheter.filter((e) => e.pa_vakt && !paa.has(e.id));
  if (!ledige.length) return '';
  const valg = velgValg('') + ledige.map(
    (e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('');
  return `
    <div class="input-group input-group-sm mt-2">
      <select id="varsle-enhet" class="form-select" aria-label="Enhet å varsle">${valg}</select>
      <button class="btn btn-outline-primary" type="button"
              data-action="varsleEnhet" data-id="${escHtmlValue(o.id)}">Legg til</button>
    </div>`;
}


//: Hvor langt i kjeden en status står. Speiler `services._REKKEFOLGE`:
//: Behandlet er en sidegren fra Fremme og deler trinn med Avreist.
const STATUS_RANG = { venter: 0, rykker_ut: 1, fremme: 2, avreist: 3, behandlet: 3, leverer: 4, ledig: 5 };

function _statusvalg(status) {
  // **Alle statuser utenom den hun står i** (backlog, 22. sep. 2026:
  // «KO/administrator bør kunne sette alle statuser, også de som har vært»).
  // To grupper: det som ligger bak (et steg tilbake — meldingene etter
  // trekkes tilbake) og det som ligger foran (en ny melding, også med hopp).
  // Serveren avgjør uansett; dette er hva nedtrekket tilbyr, i den
  // rekkefølgen kjeden går.
  const rang = STATUS_RANG[status] ?? -1;
  const alle = ['venter', 'rykker_ut', 'fremme', 'avreist', 'leverer', 'behandlet', 'ledig']
    .filter((s) => s !== status);
  const bak = alle.filter((s) => STATUS_RANG[s] < rang
    || (STATUS_RANG[s] === rang && s !== status));
  const foran = alle.filter((s) => !bak.includes(s));
  // **«Avbrutt»** (bestilt 22. sep. 2026): bilen melder på samband at den
  // avbryter. Ikke en status i kjeden, men bilens Avbryt-knapp ført av
  // sentralbordet — ledig, og oppdraget trenger ny ressurs. Bare der bilen
  // selv har knappen (`AVBRYT_FRA`, fra serveren).
  if ((globalThis.window?.OPPDRAG_AVBRYT_FRA || []).includes(status)) foran.push('avbryt');
  return { bak, foran };
}

function _nesteStatus(status) {
  // Det nedtrekket står på når det åpnes: neste ledd i kjeden, som før.
  const kjede = STATUS_REKKEFOLGE.filter((s) => s !== 'ledig');
  const i = kjede.indexOf(status);
  if (i >= 0 && i + 1 < kjede.length) return kjede[i + 1];
  return status === 'ledig' ? null : 'ledig';
}

function _forrigeStatus(enhetId, status) {
  // Den høyeste gjeldende statusen hun har hatt før den hun står i nå.
  const rang = STATUS_RANG[status] ?? -1;
  const tidligere = ((apentOppdrag && apentOppdrag.statusmeldinger) || [])
    .filter((m) => Number(m.enhet_id) === Number(enhetId) && STATUS_RANG[m.status] < rang)
    .sort((a, b) => STATUS_RANG[a.status] - STATUS_RANG[b.status]);
  return tidligere.length ? tidligere[tidligere.length - 1].status : null;
}

function _trengerTid(enhetId, maal) {
  // Et steg tilbake til en status hun *har hatt* — eller til Venter —
  // skriver ingen ny melding, og trenger derfor ikke noe tidspunkt. Alt
  // annet er en føring, og den må ha et. Samme regel som `foer_status`.
  if (maal === 'venter') return false;
  const gjeldende = ((apentOppdrag && apentOppdrag.statusmeldinger) || [])
    .filter((m) => Number(m.enhet_id) === Number(enhetId));
  const e = ((apentOppdrag && apentOppdrag.enheter) || [])
    .find((x) => Number(x.enhet_id) === Number(enhetId));
  const rang = STATUS_RANG[maal];
  const erBak = e && (STATUS_RANG[e.status] > rang
    || (STATUS_RANG[e.status] === rang && e.status !== maal));
  return !(erBak && gjeldende.some((m) => m.status === maal));
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
  if (!valg) return;
  if (!valg.value) { _visEnhetsfeil('Velg en enhet å legge til.'); return; }
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


function visFoerStatus(enhetId) {
  const rad = document.getElementById(`enhet-rad-${enhetId}`);
  if (!rad || rad.querySelector('.foer-skjema')) return;
  const e = ((apentOppdrag && apentOppdrag.enheter) || [])
    .find((x) => Number(x.enhet_id) === Number(enhetId));
  if (!e) return;

  const navn = window.OPPDRAG_STATUS_NAVN || {};
  const { bak, foran } = _statusvalg(e.status);
  // Forvalget er neste ledd — og for den som er ledig, statusen hun sto i før.
  const valgt = _nesteStatus(e.status) || _forrigeStatus(enhetId, e.status) || bak[bak.length - 1];
  const etikett = (st) => (st === 'avbryt' ? 'Avbrutt — trenger ny ressurs' : (navn[st] || st));
  const valg = (st) => `<option value="${escHtmlValue(st)}"${st === valgt ? ' selected' : ''}>${escapeHtml(etikett(st))}</option>`;
  const gruppe = (etikett, liste) => (liste.length
    ? `<optgroup label="${escHtmlValue(etikett)}">${liste.map(valg).join('')}</optgroup>` : '');
  const statusvalg = gruppe('Videre', foran) + gruppe('Tilbake til', bak);
  const stedvalg = (window.OPPDRAG_AVREIST_TIL || []).map(
    ([nokkel, tekst]) => `<option value="${escHtmlValue(nokkel)}">${escapeHtml(tekst)}</option>`).join('');
  // Stedet hører til «Avreist» og vises bare når det er valgt (André,
  // 12. sep. 2026). Nedtrekket melder `change`, og `foerStatusEndret`
  // slår stedet av og på.
  const stedSkjult = valgt === 'avreist' ? '' : ' hidden';
  const tidSkjult = _trengerTid(enhetId, valgt) ? '' : ' hidden';
  // Ett skjema om gangen: de andre radenes knapper skjules mens dette står,
  // og radens egen «Endre status» låses (André, 12. sep. 2026).
  document.getElementById('detalj-innhold')?.classList.add('foer-aapen');
  rad.querySelectorAll('[data-action="visFoerStatus"]').forEach((b) => { b.disabled = true; });

  const skjema = document.createElement('div');
  skjema.className = 'foer-skjema mt-1 d-flex gap-2 align-items-center flex-wrap w-100';
  skjema.innerHTML = (`
    <select id="foer-status" class="form-select form-select-sm w-auto" aria-label="Status"
            data-enhet="${escHtmlValue(enhetId)}"
            data-action="foerStatusEndret" data-hendelse="change">${statusvalg}</select>
    <select id="foer-sted" class="form-select form-select-sm w-auto" aria-label="Sted ved Avreist"${stedSkjult}
            data-action="foerStatusEndret" data-hendelse="change">
      <option value="">Velg sted</option>${stedvalg}</select>
    <input type="text" id="foer-sted-tekst" class="form-control form-control-sm w-auto" maxlength="120"
           placeholder="Hvor?" aria-label="Annet sted" hidden>
    <input type="datetime-local" class="form-control form-control-sm w-auto"
           id="foer-tid" value="${_lokalNaa()}" step="60"${tidSkjult}>
    <span id="foer-feil" class="text-danger small"></span>
    <span class="ms-auto d-flex gap-2">
      <button type="button" class="btn btn-sm btn-outline-secondary"
              data-action="avbrytFoerStatus">Avbryt</button>
      <button type="button" class="btn btn-sm btn-primary"
              id="foer-lagre" data-action="lagreFoerStatus" data-id="${escHtmlValue(enhetId)}">Endre</button>
    </span>`);
  rad.appendChild(skjema);
  document.getElementById('foer-status').focus();
}


function avbrytFoerStatus() {
  document.querySelectorAll('.foer-skjema').forEach((el) => el.remove());
  document.getElementById('detalj-innhold')?.classList.remove('foer-aapen');
  document.querySelectorAll('#detalj-innhold [data-action="visFoerStatus"]')
    .forEach((b) => { b.disabled = false; });
}


async function slettOppdrag(id) {
  // Sletting mens alle biler venter (sentralbord), eller i historikken
  // (global admin). Dialogen stopper feilklikket; `confirm: true` i kroppen
  // stopper et kall som treffer URL-en uten å mene det.
  if (!confirm('Slette oppdraget? Det kan ikke angres.')) return;
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/`, {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visEnhetsfeil(d.message || 'Kunne ikke slette oppdraget.');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  await lastAlt();
  if (historikkliste.length) await lastHistorikk();
}


async function slettHistorikk() {
  const feil = document.getElementById('historikk-feil');
  if (!confirm('Slette alle oppdragene i historikken for vakten? Det kan ikke angres.')) return;
  const res = await apiFetch('/oppdrag/api/historikk/', {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    if (feil) { feil.textContent = d.message || 'Kunne ikke slette.'; feil.classList.remove('d-none'); }
    return;
  }
  await lastHistorikk();
  await lastAlt();
}


// ── Verdiene rett i vinduet (backlog punkt 4 og 5, 23. sep. 2026) ─────────
//
// André: «klikke på disse verdiene … gir en liten dropdown for de andre
// valgene», og «rediger-knappen inne i oppdraget gjemmer redigerbar info».
// Hvert felt lagres for seg, idet det velges — serveren tar ett felt om
// gangen, og hver endring står i tidslinjen. **Inne i oppdraget, ikke i
// lista** (André: «avvent litt» med lista): lista tegnes om ved hver
// polling, hele raden er en knapp, og et feilklikk der ses av ingen.

//: Feltet som står åpent som nedtrekk, eller `null`.
let apentVerdivalg = null;
//: Står oppdragsnotatet åpent for redigering?
let apentNotat = false;

const VERDIFELT = ['hastegrad', 'problemstilling', 'lokasjon', 'ressurs'];

// Kan feltet endres her? **Ressursen bare med null eller én enhet** (André:
// «ja») — med flere er det «Flytt» og «Legg til» under, fordi et bytte da
// ikke sier hvem som byttes.
function _verdiKanEndres(o, felt, kanSkrive) {
  if (!kanSkrive || !VERDIFELT.includes(felt)) return false;
  return felt !== 'ressurs' || (o.enheter || []).length <= 1;
}

// Valgene i nedtrekket, med den gjeldende verdien først valgt — så `change`
// bare fyrer på et ekte bytte.
function _verdiValg(o, felt) {
  // **«Velg…» først i alle** (23. sep. 2026). Den lagrede verdien står
  // valgt; velges «Velg…», er det en feilmelding for de obligatoriske.
  const velg = (valgt) => ({ verdi: '', tekst: velgTekst(), valgt });
  if (felt === 'hastegrad') {
    return [velg(!o.hastegrad)].concat(
      HASTEGRAD_REKKEFOLGE.map((h) => ({ verdi: h, tekst: h, valgt: h === o.hastegrad })));
  }
  if (felt === 'problemstilling') {
    const liste = problemstillingerFor(o.hastegrad);
    if (o.problemstilling && !liste.includes(o.problemstilling)) liste.unshift(o.problemstilling);
    return [velg(!o.problemstilling)].concat(
      liste.map((p) => ({ verdi: p, tekst: p, valgt: p === o.problemstilling })));
  }
  if (felt === 'lokasjon') {
    return [velg(!o.lokasjon_id)].concat(lokasjoner.filter((l) => l.er_aktiv || l.id === o.lokasjon_id)
      .map((l) => ({ verdi: String(l.id), tekst: l.navn, valgt: l.id === o.lokasjon_id })));
  }
  if (felt === 'ressurs') {
    const naa = (o.enheter || [])[0];
    const valg = enheter.filter((e) => e.pa_vakt || (naa && e.id === naa.enhet_id))
      .map((e) => ({ verdi: String(e.id), tekst: e.navn, valgt: Boolean(naa) && e.id === naa.enhet_id }));
    return [velg(!naa)].concat(valg);
  }
  return [];
}

// Forespørselen et valg blir til. **Ressursen er ikke et felt på
// oppdraget:** uten enhet varsles den valgte («Legg til»), med én flyttes
// oppdraget (`flytt_til_enhet`, som står i tidslinjen som før).
function _verdiForesporsel(o, felt, verdi) {
  const url = `/oppdrag/api/oppdrag/${Number(o.id)}/`;
  // «Velg…» er en feilmelding og ingen forespørsel for de obligatoriske
  // (André, 23. sep. 2026: «feilmelding om man lagrer med "Velg..." selected»).
  // Ressursen er ikke obligatorisk — «Opprett uten enhet» finnes — så uten
  // enhet er «Velg…» bare ingenting. Med én kan den ikke fjernes herfra.
  if (!verdi) {
    if (felt === 'ressurs') {
      return (o.enheter || []).length === 1
        ? { feil: 'Oppdraget har én enhet — velg en annen for å flytte det.' } : null;
    }
    return { feil: `${VERDIFELT_NAVN[felt] || 'Feltet'} må ha en verdi.` };
  }
  if (felt === 'hastegrad') return { url, method: 'PUT', body: { hastegrad: verdi } };
  if (felt === 'problemstilling') return { url, method: 'PUT', body: { problemstilling: verdi } };
  if (felt === 'lokasjon') return { url, method: 'PUT', body: { lokasjon_id: Number(verdi) } };
  if (felt === 'ressurs') {
    const antall = (o.enheter || []).length;
    if (antall === 0) return { url: `${url}enheter/${Number(verdi)}/`, method: 'POST', body: {} };
    if (antall === 1) return { url: `${url}flytt/`, method: 'POST', body: { enhet_id: Number(verdi) } };
  }
  return null;
}

function _verdiTekst(o, felt) {
  if (felt === 'hastegrad') return o.hastegrad;
  if (felt === 'problemstilling') return o.problemstilling;
  if (felt === 'lokasjon') return o.lokasjon_navn || 'Ingen lokasjon';
  const navn = (o.enheter || []).map((e) => e.enhet_navn);
  return navn.length ? navn.join(', ') : 'Ingen ressurs';
}

const VERDIFELT_NAVN = { hastegrad: 'Hastegrad', problemstilling: 'Problemstilling',
                         lokasjon: 'Lokasjon', ressurs: 'Tildelt ressurs' };

function _verdiBrikke(o, felt, kanSkrive) {
  const verdiTekst = escapeHtml(_verdiTekst(o, felt));
  const klasse = felt === 'hastegrad' ? ` hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}` : '';
  if (!_verdiKanEndres(o, felt, kanSkrive)) {
    const hvorfor = (felt === 'ressurs' && kanSkrive)
      ? ' title="Flere enheter — bruk «Flytt» eller «Legg til» under"' : '';
    return `<span class="verdi-brikke${klasse}"${hvorfor}>${verdiTekst}</span>`;
  }
  return `<button type="button" class="verdi-brikke verdi-kan-endres${klasse}" data-action="visVerdivalg"
            data-arg="${escHtmlValue(felt)}" title="${escHtmlValue(VERDIFELT_NAVN[felt])} — klikk for å endre">${verdiTekst}<i class="bi bi-caret-down-fill ms-1"></i></button>`;
}

function _verdiVelgerHtml(o, felt) {
  const valg = _verdiValg(o, felt).map((v) =>
    `<option value="${escHtmlValue(v.verdi)}"${v.valgt ? ' selected' : ''}>${escapeHtml(v.tekst)}</option>`).join('');
  return `<span class="verdi-velger">
      <select id="verdi-valg" class="form-select form-select-sm d-inline-block w-auto"
              aria-label="${escHtmlValue(VERDIFELT_NAVN[felt])}"
              data-action="lagreVerdi" data-hendelse="change" data-arg="${escHtmlValue(felt)}">${valg}</select>
      <button type="button" class="btn btn-link btn-sm p-0 ms-1" data-action="avbrytVerdivalg">Avbryt</button>
    </span>`;
}

function _verdierHtml(o, aapen, kanSkrive) {
  const brikker = VERDIFELT.map((felt) => (aapen === felt && _verdiKanEndres(o, felt, kanSkrive)
    ? _verdiVelgerHtml(o, felt) : _verdiBrikke(o, felt, kanSkrive))).join('');
  return `${brikker}<span class="oppdrag-meta ms-1">${escapeHtml(o.status_navn)}</span>`;
}

function _tegnVerdiene() {
  const el = document.getElementById('oppdrag-verdier');
  if (!el || !apentOppdrag) return;
  el.innerHTML = _verdierHtml(apentOppdrag, apentVerdivalg, OPPDRAG_TILGANG.kanSkrive);
  const valg = document.getElementById('verdi-valg');
  if (valg) valg.focus();
}

function visVerdivalg(felt) {
  apentVerdivalg = felt;
  _visVerdifeil('');
  _tegnVerdiene();
}

function avbrytVerdivalg() {
  apentVerdivalg = null;
  _tegnVerdiene();
}

function _visVerdifeil(melding) {
  const el = document.getElementById('verdi-feil');
  if (!el) return;
  el.textContent = melding || '';
  el.classList.toggle('d-none', !melding);
}

async function _sendVerdi(foresporsel) {
  const res = await apiFetch(foresporsel.url, {
    method: foresporsel.method, body: JSON.stringify(foresporsel.body),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visVerdifeil(d.message || 'Kunne ikke lagre.');
    return false;
  }
  await visOppdrag(apentOppdragId);
  await lastAlt();
  return true;
}

async function lagreVerdi(felt) {
  const valg = document.getElementById('verdi-valg');
  if (!valg || !apentOppdrag) return;
  const foresporsel = _verdiForesporsel(apentOppdrag, felt, valg.value);
  if (!foresporsel) return;
  if (foresporsel.feil) { _visVerdifeil(foresporsel.feil); return; }
  await _sendVerdi(foresporsel);
}

// Oppdragsnotatet: alltid synlig, redigeres der det står.
function _notatHtml(o, aapen, kanSkrive) {
  if (aapen && kanSkrive) {
    return `<div class="oppdrag-notat mb-3">
        <label class="form-label small mb-1" for="notat-felt">Oppdragsnotat</label>
        <textarea id="notat-felt" class="form-control form-control-sm" rows="3">${escapeHtml(o.fritekst || '')}</textarea>
        <div class="form-text">Oppdragets egen tekst — vises i bilen til oppdraget avsluttes.</div>
        <div class="d-flex gap-2 justify-content-end mt-1">
          <button type="button" class="btn btn-sm btn-outline-secondary" data-action="avbrytNotat">Avbryt</button>
          <button type="button" class="btn btn-sm btn-primary" id="notat-lagre" data-action="lagreNotat">Lagre</button>
        </div>
      </div>`;
  }
  const knapp = kanSkrive
    ? `<button type="button" class="btn btn-link btn-sm p-0 ms-2" data-action="visNotat">${o.fritekst ? 'Endre' : 'Legg til'}</button>`
    : '';
  const notatTekst = o.fritekst
    ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
    : '<div class="oppdrag-meta">Ingen oppdragsnotat.</div>';
  return `<div class="oppdrag-notat mb-3"><div class="oppdrag-meta small">Oppdragsnotat${knapp}</div>${notatTekst}</div>`;
}

function _tegnNotat() {
  const el = document.getElementById('oppdrag-notat');
  if (!el || !apentOppdrag) return;
  el.innerHTML = _notatHtml(apentOppdrag, apentNotat, OPPDRAG_TILGANG.kanSkrive);
  const felt = document.getElementById('notat-felt');
  if (felt) felt.focus();
}

function visNotat() { apentNotat = true; _tegnNotat(); }

function avbrytNotat() { apentNotat = false; _tegnNotat(); }

async function lagreNotat() {
  const felt = document.getElementById('notat-felt');
  if (!felt || !apentOppdrag) return;
  await withSubmitGuard('notat-lagre', async () => {
    await _sendVerdi({ url: `/oppdrag/api/oppdrag/${Number(apentOppdrag.id)}/`, method: 'PUT',
                       body: { fritekst: felt.value } });
  });
}


function foerStatusEndret() {
  // Stedet finnes bare for «Avreist», og klokkeslettet bare når det skrives
  // en ny melding — et steg tilbake har ingen tid å føre (22. sep. 2026).
  const status = document.getElementById('foer-status');
  const sted = document.getElementById('foer-sted');
  if (!status || !sted) return;
  const tid = document.getElementById('foer-tid');
  if (tid) tid.hidden = !_trengerTid(status.dataset.enhet, status.value);
  sted.hidden = status.value !== 'avreist';
  if (sted.hidden) sted.value = '';
  // Friteksten hører til «Annet sted» (19. sep. 2026) og vises bare da.
  const tekst = document.getElementById('foer-sted-tekst');
  if (tekst) {
    tekst.hidden = sted.hidden || sted.value !== 'annet';
    if (tekst.hidden) tekst.value = '';
  }
}


function _lokalNaa() {
  // `datetime-local` vil ha lokal tid uten sone.
  const naa = new Date();
  return new Date(naa.getTime() - naa.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16);
}


async function lagreFoerStatus(enhetId) {
  const status = document.getElementById('foer-status');
  const sted = document.getElementById('foer-sted');
  const tid = document.getElementById('foer-tid');
  const feil = document.getElementById('foer-feil');
  if (!status || !tid || apentOppdragId === null) return;
  // Tiden sendes bare når den står synlig — et steg tilbake har ingen.
  const medTid = !tid.hidden;
  if (medTid && !tid.value) return;

  await withSubmitGuard('foer-lagre', async () => {
    // Stedet hører til «Avreist» og ingen annen status — sendes bare da.
    const stedLedd = (status.value === 'avreist' && sted && sted.value) ? `${sted.value}/` : '';
    const stedTekst = document.getElementById('foer-sted-tekst');
    const res = await apiFetch(
      `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/status/${status.value}/${stedLedd}`, {
        method: 'POST',
        // Ingen sone på `datetime-local`; serveren tolker den som lokal tid.
        body: JSON.stringify({ tidspunkt: medTid ? tid.value : undefined,
                               sted_tekst: (stedTekst && !stedTekst.hidden) ? stedTekst.value : undefined }),
      });
    const d = await res.json();
    if (!res.ok || d.status !== 'ok') {
      feil.textContent = d.message || 'Kunne ikke føre statusen.';
      // Et avvist klokkeslett settes tilbake til nå (André, 12. sep. 2026):
      // det som sto der var galt, og nå er det tryggeste utgangspunktet.
      tid.value = _lokalNaa();
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

  // Klokkeslettet som allerede står i raden er utgangspunktet — operatøren
  // retter et minutt eller to, hun skriver ikke inn datoen på nytt.
  const lokal = _lokalNaa();

  const skjema = document.createElement('div');
  skjema.className = 'rett-tid-skjema mt-1 d-flex gap-2 align-items-center flex-wrap';
  // En streng, ikke `trustedHtml(...)`: den pakker inn i et objekt for
  // `cellHtml()`, og som innerHTML blir det «[object Object]». Skjemaet sto
  // slik fra fase 3 til 11. sep. 2026 — «Rett tid» viste ingenting.
  skjema.innerHTML = (`
    <input type="datetime-local" class="form-control form-control-sm w-auto"
           id="rett-tid-verdi" value="${lokal}">
    <span id="rett-tid-feil" class="text-danger small"></span>
    <span class="ms-auto d-flex gap-2">
      <button type="button" class="btn btn-sm btn-outline-secondary"
              data-action="avbrytRettTid">Avbryt</button>
      <button type="button" class="btn btn-sm btn-primary"
              id="rett-tid-lagre" data-action="lagreRettTid" data-id="${escHtmlValue(meldingId)}">Lagre</button>
    </span>`);
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
  if ((fra && !fra.value) || !valg.value) {
    feil.textContent = fra && !fra.value ? 'Velg hvilken enhet oppdraget flyttes fra.' : 'Velg enheten oppdraget flyttes til.';
    feil.classList.remove('d-none');
    return;
  }
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
