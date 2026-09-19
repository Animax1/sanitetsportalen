// ════════════════════════════════════════════════════════════════════════════
// ko-hendelser.js — hendelsesloggen: tabellen, hendelsen åpnet i vinduet,
// skjemaet «Ny hendelse», prioritet, «bli med», og koblingen til oppdragene.
//
// Andre av KOs tre filer. Ingenting kjører på toppnivå; ko.js sin
// `DOMContentLoaded` starter alt. Lista kommer med logg-pollen
// (`koTaImotHendelser`), kommentarene er logglinjer med `hendelse_id`
// (`koLinjer` i ko.js), og oppdragene på hendelsen leses fra sentralbordets
// `oppdragsliste` — KO henter ingenting selv, og har ingen egen poller.
//
// Krever portal-utils.js (apiFetch, escapeHtml, data-action) og ko.js sine
// bindinger (`koLinjer`, `koKanSkrive`, `koKlokke`, `koHentLogg`). De er
// skript-scopede `let`/`const` og deles mellom filene; det som ikke må skje
// er at noe her *kjører* før ko.js er lest.
// ════════════════════════════════════════════════════════════════════════════

//: Hendelsene i vakta, nøklet på id. Hele lista byttes ut ved hver poll.
let koHendelser = new Map();

//: Hendelsen som står åpen inne i vinduet, eller `null` for lista.
let koApenHendelseId = null;

//: Bryterne i hodet. «Vis lukkede» huskes per nettleser (André, 19. sep.
//: 2026: «Når en refresher siden vises også avsluttede hendelser, selv om
//: vis lukkede er trykt av») og er **av** som standard: tallet i vinduets
//: hode sier at de finnes, og en lukket hendelse i lista er støy for den
//: som sitter med samband.
const KO_VIS_LUKKEDE_NOKKEL = 'ko.vis_lukkede';
let koVisLukkede = false;
let koSok = '';

function koLesVisLukkede() {
  try { return localStorage.getItem(KO_VIS_LUKKEDE_NOKKEL) === 'ja'; } catch (e) { return false; }
}

function koLagreVisLukkede(verdi) {
  try { localStorage.setItem(KO_VIS_LUKKEDE_NOKKEL, verdi ? 'ja' : 'nei'); } catch (e) { /* privat modus */ }
}

// Ved oppstart (kalles fra ko.js): bryteren og lista følger det som ble
// husket, ikke markupens standard.
function koStartVisLukkede() {
  koVisLukkede = koLesVisLukkede();
  const b = document.getElementById('ko-vis-lukkede');
  if (b) b.checked = koVisLukkede;
}

//: Prioriteten valgt i skjemaet. **Tom til operatøren velger** (André,
//: 19. sep. 2026: «litt misvisende med forhåndsvalgt prioritet») — skjemaet
//: nekter å sende uten, se `koPrioritetValgt`.
let koValgtPrioritet = '';

function koPrioritetValgt() {
  return Boolean(koValgtPrioritet);
}

function koPrioriteter() {
  return (globalThis.window && window.KO_PRIORITETER) || [];
}

function koPrioritetNavn(verdi) {
  const rad = koPrioriteter().find((p) => p[0] === verdi);
  return rad ? rad[1] : (verdi || '');
}

// Rangen er rekkefølgen serveren sendte (`PRIORITET_VALG`): Viktig først.
// Ukjent verdi havner sist, ikke først — en gammel klient skal ikke løfte noe.
function koPrioritetRang(verdi) {
  const i = koPrioriteter().findIndex((p) => p[0] === verdi);
  return i < 0 ? koPrioriteter().length : i;
}

// **Sorteringen er oppdragslistas** (André, 18. sep. 2026: «likt som
// oppdrag, høyere hastegrad står mest synlig, ellers kronologisk»): lukkede
// nederst, så prioriteten, og innenfor den nummeret — H3 over H7. Ren regel,
// prøvd for seg.
function koSorterHendelser(liste) {
  return [...(liste || [])].sort((a, b) => {
    const al = a.status === 'apen' ? 0 : 1;
    const bl = b.status === 'apen' ? 0 : 1;
    if (al !== bl) return al - bl;
    const ap = koPrioritetRang(a.prioritet);
    const bp = koPrioritetRang(b.prioritet);
    if (ap !== bp) return ap - bp;
    return (Number(a.nummer) || 0) - (Number(b.nummer) || 0);
  });
}

// Søket i hendelsesflaten: nummer («H12» eller «12»), tittel, sted, melder,
// tilleggene i beskrivelsen og lagene. Tom søketekst treffer alt.
function koHendelseTreffer(h, sok) {
  const s = String(sok || '').trim().toLowerCase();
  if (!s) return true;
  const felt = [h.kode, String(h.nummer), h.tittel, h.lokasjon_navn, h.melder_tekst, h.melder]
    .concat((h.beskrivelse || []).map((t) => t.tekst))
    .concat((h.lag || []).map((l) => l.navn));
  return felt.some((f) => String(f || '').toLowerCase().includes(s));
}

// **«Nytt» i ti minutter** (André, 19. sep. 2026: «lettere å se hva i
// teksten som er nytt»). Regelen står for seg fordi den avgjør et merke.
const KO_NYTT_MS = 10 * 60 * 1000;

function koErNytt(iso, naa) {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return false;
  return (naa === undefined ? Date.now() : naa) - t < KO_NYTT_MS;
}

// «23 min», «1t 05m» — hvor lenge siden. Tom for et ugyldig tidspunkt.
function koSiden(iso, naa) {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '';
  const min = Math.max(0, Math.floor(((naa === undefined ? Date.now() : naa) - t) / 60000));
  return min < 60 ? String(min) + ' min' : fmtMin(min);
}

// Vaktlistas ressurser uten enhet (`koRessurser` i ko.js), for skjemaet og
// «+ Lag» i hendelsen. Tom uten vaktlistetilgang.
function koLagKandidater() {
  return (typeof koRessurser !== 'undefined' && Array.isArray(koRessurser)) ? koRessurser : [];
}

// Hvilke **åpne** hendelser et lag står på: `[{kode, tittel, fra}]`. Regelen
// bak «På H14 · 23 min» på kortet — en lukket hendelse holder ingen.
function koLagPaa(ressursId) {
  const ut = [];
  koHendelser.forEach((h) => {
    if (h.status !== 'apen') return;
    (h.lag || []).forEach((l) => {
      if (l.ressurs_id === ressursId) ut.push({ id: h.id, kode: h.kode, tittel: h.tittel, fra: l.fra });
    });
  });
  return ut;
}

function koSynligeHendelser() {
  const alle = Array.from(koHendelser.values())
    .filter((h) => koVisLukkede || h.status === 'apen')
    .filter((h) => koHendelseTreffer(h, koSok));
  return koSorterHendelser(alle);
}

function koApneHendelser() {
  return koSorterHendelser(Array.from(koHendelser.values()).filter((h) => h.status === 'apen'));
}

// ── Byggerne ────────────────────────────────────────────────────────────────

// Prioritetsmerket med tekst — fargen bærer aldri informasjonen alene.
function koPrioMerke(prio) {
  const p = escapeHtml(prio || 'gronn');
  return '<span class="ko-prio ko-prio-m-' + p + '">' + escapeHtml(koPrioritetNavn(prio)) + '</span>';
}

// Utropstegnet for Viktig (rød trekant, André). Tom for resten.
function koPrioIkon(prio) {
  return prio === 'viktig'
    ? '<i class="bi bi-exclamation-triangle-fill h-ikon" title="Viktig"></i>' : '';
}

function koOppdragForHendelse(h) {
  const liste = (typeof oppdragsliste !== 'undefined' && Array.isArray(oppdragsliste)) ? oppdragsliste : [];
  return liste.filter((o) => o.hendelse_id === h.id);
}

function koHendelseRadHtml(h) {
  const prio = escapeHtml(h.prioritet || 'gronn');
  const lukket = h.status !== 'apen';
  const klasser = 'h-rad h-' + prio + (lukket ? ' h-lukket' : '')
    + (h.id === koApenHendelseId ? ' h-apen' : '');
  // Siste tillegg i beskrivelsen står under tittelen — det nyeste er det
  // man skummer etter.
  const tillegg = h.beskrivelse || [];
  const siste = tillegg.length ? tillegg[tillegg.length - 1].tekst : '';
  const under = siste
    ? '<div class="h-under">' + escapeHtml(String(siste).slice(0, 90)) + '</div>' : '';
  const lag = (h.lag || []).map((l) => escapeHtml(l.navn)).join(', ');
  const lagHtml = lag
    ? '<span class="h-ressurs"><i class="bi bi-people me-1"></i>' + lag + '</span>'
    : '<span class="text-muted small">—</span>';
  const oppdrag = koOppdragForHendelse(h);
  const oppdragHtml = oppdrag.length
    ? oppdrag.map((o) => '<span class="hendelse-merke me-1">' + escapeHtml(oppdragsnr(o.nummer)) + '</span>').join('')
      + '<span class="text-muted small">' + escapeHtml(String(h.apne_oppdrag || 0)) + ' åpne</span>'
    : '<span class="text-muted small">Ingen</span>';
  const status = lukket
    ? '<span class="badge badge-lukket">Lukket ' + escapeHtml(koKlokke(h.lukket_at)) + '</span>'
    : '<span class="badge badge-apen">Åpen</span>';
  const melder = h.melder_tekst
    ? '<div class="h-under">Meldt av ' + escapeHtml(h.melder_tekst) + '</div>' : '';
  return '<tr class="' + klasser + '" data-action="koApneHendelse" data-id="' + escapeHtml(h.id) + '"'
    + ' role="button" tabindex="0">'
    + '<td>' + koPrioIkon(h.prioritet) + '</td>'
    + '<td class="h-nowrap"><span class="hendelse-merke">' + escapeHtml(h.kode) + '</span></td>'
    + '<td class="h-nowrap text-muted">' + escapeHtml(koKlokke(h.opprettet_at)) + '</td>'
    + '<td><div class="h-tittel">' + escapeHtml(h.tittel) + '</div>' + under + melder + '</td>'
    + '<td>' + koPrioMerke(h.prioritet) + '</td>'
    + '<td>' + escapeHtml(h.lokasjon_navn || '—') + '</td>'
    + '<td>' + lagHtml + '</td>'
    + '<td>' + oppdragHtml + '</td>'
    + '<td class="h-under h-nowrap">' + escapeHtml(h.opprettet_av || '—') + '</td>'
    + '<td>' + status + '</td>'
    + '</tr>';
}

function koTegnHendelser() {
  const boks = document.getElementById('ko-hendelser-liste');
  if (!boks) return;
  const alle = Array.from(koHendelser.values());
  const apne = alle.filter((h) => h.status === 'apen').length;
  const tall = document.getElementById('ko-hendelser-antall');
  if (tall) tall.textContent = '· ' + apne + ' åpne · ' + (alle.length - apne) + ' lukket';
  if (koApenHendelseId !== null) {
    koTegnDetalj();
    return;
  }
  boks.classList.remove('d-none');
  const detalj = document.getElementById('ko-hendelse-detalj');
  if (detalj) detalj.classList.add('d-none');
  const rader = koSynligeHendelser();
  if (!rader.length) {
    boks.innerHTML = '<p class="text-muted small p-2 mb-0">'
      + (alle.length ? 'Ingen hendelser treffer.' : 'Ingen hendelser ennå.') + '</p>';
    return;
  }
  boks.innerHTML = '<table class="h-tabell"><thead><tr>'
    + '<th></th><th>Nr</th><th>Tid</th><th>Hendelse</th><th>Prioritet</th><th>Sted</th>'
    + '<th>Lag</th><th>Oppdrag</th><th>Opprettet av</th><th>Status</th>'
    + '</tr></thead><tbody>' + rader.map(koHendelseRadHtml).join('') + '</tbody></table>';
}

function koTaImotHendelser(liste) {
  koHendelser = new Map((liste || []).map((h) => [h.id, h]));
  if (koApenHendelseId !== null && !koHendelser.has(koApenHendelseId)) koApenHendelseId = null;
  koTegnHendelser();
  koFyllHendelsevalg();
  // Lagkortene bærer «På H14 · 23 min» fra hendelsene — tegn dem på nytt.
  if (typeof koTegnRessurser === 'function') koTegnRessurser();
}

// Sentralbordet kaller denne etter at det tegnet tavla: hendelsesradene og
// den åpne hendelsen leser oppdragene derfra. Kalles gjennom en vakt fra
// `renderOppdrag()`, fordi den fila også kjører på /oppdrag/.
function koEtterOppdragTegnet() {
  const liste = (typeof oppdragsliste !== 'undefined' && Array.isArray(oppdragsliste)) ? oppdragsliste : [];
  const tall = document.getElementById('ko-oppdrag-antall');
  if (tall) {
    const aktive = liste.filter((o) => o.status !== 'ledig').length;
    tall.textContent = '· ' + aktive + ' aktive · ' + (liste.length - aktive) + ' ferdig';
  }
  koTegnHendelser();
}

// ── Hendelsen åpnet inne i vinduet ──────────────────────────────────────────

function koApneHendelse(id) {
  koApenHendelseId = Number(id);
  koTegnHendelser();
}

function koLukkDetalj() {
  koApenHendelseId = null;
  koTegnHendelser();
}

function koHendelseLinjer(h) {
  const rader = Array.from(koLinjer.values()).filter((l) => l.hendelse_id === h.id);
  rader.sort((a, b) => (a.rot - b.rot) || (a.id - b.id));
  return rader;
}

function koDetaljLinjeHtml(linje) {
  const system = linje.kilde === 'system';
  const hvem = system ? '' : ' <span class="hvem">— ' + escapeHtml(linje.forfatter || '')
    + (linje.ansvarsomraade ? ' · ' + escapeHtml(linje.ansvarsomraade) : '') + '</span>';
  const tekst = linje.fjernet
    ? '<em class="text-muted">Innholdet er fjernet.</em>'
    : escapeHtml(linje.tekst);
  // Et tillegg i beskrivelsen er en linje i tråden også — merket sier at det
  // står i beskrivelsen, så «hvem oppdaterte den» leses rett av tråden.
  const merke = linje.beskrivelse
    ? '<span class="badge text-bg-warning ko-tillegg-merke me-1">beskrivelse</span>' : '';
  const verktoy = (system || linje.fjernet) ? '' : koRettFjernKnapper(linje.id);
  return '<div class="h-linje' + (system ? ' system' : '') + '">'
    + '<span class="tid">' + escapeHtml(koKlokke(linje.tidspunkt)) + '</span>'
    + merke + tekst + hvem + verktoy + '</div>';
}

// ── Beskrivelsen som tillegg, og lagene på hendelsen (19. sep. 2026) ─────────

// Rediger og fjern for en linje inne i hendelsen — tillegg og kommentarer
// (André, 19. sep. 2026: «kan man ikke redigere/slette beskrivelsen»). Samme
// handlinger som i strømmen (`koRett`, `koFjern`), uten fest og «lag
// hendelse»: en linje i hendelsen er alt i en. Tom for den som bare leser.
function koRettFjernKnapper(id) {
  let ut = '';
  if (koKanSkrive()) {
    ut += '<button type="button" class="btn btn-link btn-sm p-0" title="Rediger"'
      + ' data-action="koRett" data-id="' + escapeHtml(id) + '"><i class="bi bi-pencil"></i></button>';
  }
  if (koKanFjerne()) {
    ut += '<button type="button" class="btn btn-link btn-sm p-0 text-danger" title="Fjern innholdet"'
      + ' data-action="koFjern" data-id="' + escapeHtml(id) + '"><i class="bi bi-trash"></i></button>';
  }
  return ut ? '<span class="verktoy">' + ut + '</span>' : '';
}

// Ett tillegg: teksten, hvem og når. Det nyeste er uthevet, og «nytt» står
// på det i ti minutter (`koErNytt`). `verktoy` er rediger/fjern der de
// finnes — tomt i lesevisningen i «Nytt oppdrag».
function koTilleggHtml(t, nyest, naa, verktoy) {
  const klasse = 'b-tillegg' + (nyest ? ' nyest' : '') + (koErNytt(t.tid, naa) ? ' nytt' : '');
  const nyttMerke = koErNytt(t.tid, naa) ? '<span class="merke">nytt</span>' : '';
  const rettet = t.rettet ? ' <span class="text-muted small">(rettet)</span>' : '';
  return '<div class="' + klasse + '">' + escapeHtml(t.tekst) + rettet
    + '<span class="hvem">' + escapeHtml(t.av || '') + ' · ' + escapeHtml(koKlokke(t.tid)) + '</span>'
    + nyttMerke + (verktoy || '') + '</div>';
}

// Skjemaet «Legg til i beskrivelsen». `feltId` er unik per sted, fordi den
// samme beskrivelsen står både i hendelsen og i oppdragets detaljmodal. Et
// ekte `<form>`, så Enter sender: `koTilleggSubmit` i ko.js lytter på
// `submit` for hele dokumentet og kaller `handling` med hendelsens id.
function koTilleggSkjemaHtml(hendelseId, feltId, handling) {
  return '<form class="b-skjema" autocomplete="off" data-ko-tillegg="' + escapeHtml(hendelseId) + '"'
    + ' data-ko-handling="' + escapeHtml(handling) + '">'
    + '<input type="text" class="form-control form-control-sm" id="' + escapeHtml(feltId) + '"'
    + ' maxlength="2000" placeholder="Legg til i beskrivelsen …" aria-label="Legg til i beskrivelsen">'
    + '<button type="submit" class="btn btn-sm btn-outline-primary" title="Legg til">'
    + '<i class="bi bi-plus-lg"></i></button></form>';
}

// Hele beskrivelsen: tilleggene, og skjemaet for den som kan skrive.
function koBeskrivelseHtml(h, kan, feltId, handling) {
  const tillegg = h.beskrivelse || [];
  const liste = tillegg.length
    ? tillegg.map((t, i) => koTilleggHtml(t, i === tillegg.length - 1, undefined, koRettFjernKnapper(t.id))).join('')
    : '<span class="text-muted small">Ingen beskrivelse ennå.</span>';
  const skjema = kan ? koTilleggSkjemaHtml(h.id, feltId, handling) : '';
  return '<div class="b-liste">' + liste + '</div>' + skjema;
}

// Ett lag på hendelsen: navnet, siden når, og «ta av» for den som kan.
function koLagBrikkeHtml(h, l, kan) {
  const taAv = kan
    ? '<button type="button" class="btn btn-link btn-sm p-0 ms-1" title="Ta laget av hendelsen"'
      + ' data-action="koTaAvLag" data-arg="' + escapeHtml(h.id) + ':' + escapeHtml(l.ressurs_id) + '">'
      + '<i class="bi bi-x"></i></button>'
    : '';
  return '<span class="lag-brikke"><i class="bi bi-people"></i>' + escapeHtml(l.navn)
    + ' <span class="siden">siden ' + escapeHtml(koKlokke(l.fra)) + ' · ' + escapeHtml(koSiden(l.fra)) + '</span>'
    + taAv + '</span>';
}

// «+ Lag»: nedtrekk over vaktlistas lag som ikke alt står på hendelsen, med
// «på H13» som hint der laget er opptatt. Tom uten kandidater.
function koLagVelgerHtml(h) {
  const paa = new Set((h.lag || []).map((l) => l.ressurs_id));
  const valg = koLagKandidater().filter((r) => !paa.has(r.id)).map((r) => {
    const opptatt = koLagPaa(r.id).map((x) => x.kode).join(', ');
    return '<option value="' + escapeHtml(r.id) + '">' + escapeHtml(r.navn)
      + (opptatt ? ' (på ' + escapeHtml(opptatt) + ')' : '') + '</option>';
  }).join('');
  if (!valg) return '';
  // Første valg er en ledetekst, ikke et lag (André, 19. sep. 2026: «står
  // automatisk på et lag — misvisende»). «Legg til» gjør ingenting uten valg.
  return '<span class="input-group input-group-sm w-auto">'
    + '<select id="ko-lag-valg-' + escapeHtml(h.id) + '" class="form-select" aria-label="Legg til lag">'
    + '<option value="">Legg til lag …</option>' + valg + '</select>'
    + '<button type="button" class="btn btn-outline-secondary" data-action="koLeggTilLag"'
    + ' data-id="' + escapeHtml(h.id) + '">Legg til</button></span>';
}

function koHendelseOppdragHtml(o) {
  const enheter = (o.enheter || []).map((e) => escapeHtml(e.navn || e.enhet_navn || '')).filter(Boolean).join(', ');
  return '<div class="h-oppdrag-rad" data-action="visOppdrag" data-id="' + escapeHtml(o.id) + '" role="button" tabindex="0">'
    + '<span class="hendelse-merke">' + escapeHtml(oppdragsnr(o.nummer)) + '</span>'
    + '<span class="hastegrad ' + escapeHtml(hastegradKlasse(o.hastegrad)) + '">' + escapeHtml(o.hastegrad || '') + '</span>'
    + '<span class="fw-semibold">' + escapeHtml(o.problemstilling || '') + '</span>'
    + '<span class="enhet-brikke"><span class="status-prikk status-' + escapeHtml(o.status) + '"></span>'
    + (enheter || '<span class="text-muted">ingen enhet</span>') + ' · ' + escapeHtml(o.status_navn || '') + '</span>'
    + '<span class="ms-auto small">Åpne</span>'
    + '</div>';
}

function koPrioKnapperHtml(h) {
  const knapper = koPrioriteter().map(([verdi, navn]) => {
    const aktiv = h.prioritet === verdi ? ' aktiv-' + escapeHtml(verdi) : '';
    const ikon = verdi === 'viktig' ? '<i class="bi bi-exclamation-triangle-fill me-1"></i>' : '';
    return '<button type="button" class="btn btn-outline-secondary' + aktiv + '"'
      + ' data-action="koSettPrioritet" data-arg="' + escapeHtml(h.id) + ':' + escapeHtml(verdi) + '"'
      + ' title="' + escapeHtml(navn) + '">' + ikon + escapeHtml(navn) + '</button>';
  }).join('');
  return '<div class="btn-group btn-group-sm ko-prio-gruppe" role="group" aria-label="Prioritet">' + knapper + '</div>';
}

// **Det som står i feltene overlever en omtegning.** Hendelsen tegnes på
// nytt ved hver poll (hvert 15. sekund), og `innerHTML` kaster feltene —
// operatøren «datt ut av» skrivefeltet midt i en setning (André, 19. sep.
// 2026). Verdien, markøren og fokuset tas vare på før og settes tilbake etter.
function koBevarFelter(ider) {
  const aktiv = (globalThis.document && document.activeElement) || null;
  const husket = ider.map((id) => {
    const el = document.getElementById(id);
    if (!el) return null;
    return { id, verdi: el.value, fokus: el === aktiv,
             start: el.selectionStart, slutt: el.selectionEnd };
  }).filter(Boolean);
  return () => husket.forEach((f) => {
    const el = document.getElementById(f.id);
    if (!el) return;
    if (f.verdi !== undefined && el.value !== f.verdi) el.value = f.verdi;
    if (f.fokus && typeof el.focus === 'function') {
      el.focus();
      if (typeof el.setSelectionRange === 'function' && f.start != null) {
        try { el.setSelectionRange(f.start, f.slutt); } catch (e) { /* select/number har ingen markør */ }
      }
    }
  });
}

function koTegnDetalj() {
  const boks = document.getElementById('ko-hendelse-detalj');
  const liste = document.getElementById('ko-hendelser-liste');
  const h = koHendelser.get(koApenHendelseId);
  if (!boks || !h) { koApenHendelseId = null; if (boks) boks.classList.add('d-none'); return; }
  const gjenopprett = koBevarFelter(['ko-hendelse-tekst', 'ko-hendelse-tid', 'ko-tillegg-' + escapeHtml(h.id),
                                     'ko-lag-valg-' + escapeHtml(h.id), 'ko-knytt-valg']);
  liste.classList.add('d-none');
  boks.classList.remove('d-none');
  const kan = koKanSkrive();
  const lukket = h.status !== 'apen';
  const deltar = (h.deltakere || []).map((n) => '<span class="navn">' + escapeHtml(n) + '</span>').join(', ');
  const oppdrag = koOppdragForHendelse(h);
  const kanOppdrag = kan && (window.OPPDRAG_TILGANG || {}).kanSkrive && !lukket;
  const uten = ((typeof oppdragsliste !== 'undefined' && Array.isArray(oppdragsliste)) ? oppdragsliste : [])
    .filter((o) => !o.hendelse_id && o.status !== 'ledig');
  const knyttValg = kanOppdrag && uten.length
    ? '<span class="input-group input-group-sm w-auto">'
      + '<select id="ko-knytt-valg" class="form-select" aria-label="Knytt eksisterende oppdrag">'
      + uten.map((o) => '<option value="' + escapeHtml(o.id) + '">' + escapeHtml(oppdragsnr(o.nummer))
        + ' ' + escapeHtml(o.problemstilling || '') + '</option>').join('')
      + '</select><button type="button" class="btn btn-outline-secondary" data-action="koKnyttEksisterende"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-link-45deg me-1"></i>Knytt</button></span>'
    : '';
  const nyttOppdrag = kanOppdrag
    ? '<button type="button" class="btn btn-sm btn-primary" data-action="koNyttOppdragFraHendelse"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-plus-lg me-1"></i>Nytt oppdrag</button>'
    : '';
  const hodeKnapper = !kan ? '' : (lukket
    ? '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koGjenapneHendelse"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-arrow-counterclockwise me-1"></i>Åpne igjen</button>'
    : '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koRedigerHendelse"'
      + ' data-id="' + escapeHtml(h.id) + '" title="Rediger"><i class="bi bi-pencil"></i></button>'
      + koPrioKnapperHtml(h)
      + '<button type="button" class="btn btn-sm btn-success ko-lukk-knapp" data-action="koLukkHendelse"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-check2-circle me-1"></i>Lukk hendelse</button>');
  const bliMed = kan && !(h.deltakere || []).includes(koMittBrukernavn())
    ? '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koBliMed"'
      + ' data-id="' + escapeHtml(h.id) + '"><i class="bi bi-person-plus me-1"></i>Bli med</button>'
    : '';
  // Lagene: brikker med «siden», og «+ Lag» for den som kan — ikke på en
  // lukket hendelse (serveren nekter der også).
  const kanLag = kan && !lukket;
  const lagBrikker = (h.lag || []).map((l) => koLagBrikkeHtml(h, l, kanLag)).join('')
    || '<span class="text-muted small">ingen</span>';
  const lagVelger = kanLag ? koLagVelgerHtml(h) : '';
  const beskrivelse = koBeskrivelseHtml(h, kan, 'ko-tillegg-' + escapeHtml(h.id), 'koLeggTilBeskrivelse');
  const skjema = kan
    ? '<div class="ko-vindu-fot mt-2 rounded">'
      + '<form id="ko-hendelse-linje-form" class="d-flex gap-2 align-items-start" autocomplete="off">'
      + '<textarea id="ko-hendelse-tekst" class="form-control form-control-sm" rows="2"'
      + ' placeholder="Skriv i ' + escapeHtml(h.kode) + ' … (Enter sender, Shift+Enter ny linje)"></textarea>'
      + '<input type="time" id="ko-hendelse-tid" class="form-control form-control-sm" style="width:110px" title="Blank = nå">'
      + '<button type="submit" class="btn btn-primary btn-sm" id="ko-hendelse-send" title="Send"><i class="bi bi-send"></i></button>'
      + '</form><div class="text-danger small mt-1 d-none" id="ko-hendelse-feil" role="alert"></div></div>'
    : '';
  const prio = escapeHtml(h.prioritet || 'gronn');
  boks.innerHTML = '<div class="d-flex align-items-center gap-2 mb-2 flex-wrap">'
    + '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koLukkDetalj">'
    + '<i class="bi bi-arrow-left me-1"></i>Hendelseslogg</button>'
    + '<span class="ko-deltar ms-auto"><i class="bi bi-people me-1"></i>På hendelsen: '
    + (deltar || '<span class="text-muted">ingen ennå</span>') + '</span>' + bliMed + '</div>'
    + '<div class="h-hode h-' + prio + (lukket ? ' h-lukket' : '') + ' mb-2">'
    + '<div class="d-flex align-items-center gap-2 flex-wrap">'
    + koPrioIkon(h.prioritet)
    + '<span class="hendelse-merke">' + escapeHtml(h.kode) + '</span>'
    + '<span class="h-hode-tittel">' + escapeHtml(h.tittel) + '</span>'
    + koPrioMerke(h.prioritet)
    + (lukket ? '<span class="badge badge-lukket">Lukket ' + escapeHtml(koKlokke(h.lukket_at))
        + (h.lukket_av ? ' av ' + escapeHtml(h.lukket_av) : '') + '</span>'
      : '<span class="badge badge-apen">Åpen</span>')
    + '<span class="ms-auto d-flex gap-1 flex-wrap">' + hodeKnapper + '</span></div>'
    + '<div class="d-flex gap-3 flex-wrap mt-1">'
    + '<span class="h-felt"><i class="bi bi-geo-alt"></i> <b>' + escapeHtml(h.lokasjon_navn || '—') + '</b></span>'
    + '<span class="h-felt"><i class="bi bi-megaphone"></i> Melder: <b>' + escapeHtml(h.melder_tekst || '—') + '</b></span>'
    + '<span class="h-felt"><i class="bi bi-person"></i> Opprettet av <b>' + escapeHtml(h.opprettet_av || '—') + '</b> '
    + escapeHtml(koKlokke(h.opprettet_at)) + '</span></div>'
    + '<div class="d-flex align-items-center gap-2 flex-wrap mt-2"><span class="h-felt"><i class="bi bi-people"></i> Lag:</span>'
    + lagBrikker + lagVelger + '</div>'
    + '</div>'
    + '<div class="h-seksjon mb-1">Beskrivelse</div>'
    + '<div class="mb-2">' + beskrivelse + '</div>'
    + '<div class="d-flex align-items-center gap-2 mb-1 flex-wrap"><span class="h-seksjon">Oppdrag på hendelsen</span>'
    + '<span class="ms-auto d-flex gap-1 flex-wrap">' + nyttOppdrag + knyttValg + '</span></div>'
    + '<div class="d-grid gap-1 mb-2">' + (oppdrag.length ? oppdrag.map(koHendelseOppdragHtml).join('')
      : '<span class="text-muted small">Ingen oppdrag ennå.</span>') + '</div>'
    + '<div class="h-seksjon mb-1">Løpende</div>'
    + '<div class="h-traad" id="ko-hendelse-traad">' + (koHendelseLinjer(h).map(koDetaljLinjeHtml).join('')
      || '<span class="text-muted small">Ingen linjer ennå.</span>') + '</div>'
    + skjema;
  const form = document.getElementById('ko-hendelse-linje-form');
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      withSubmitGuard('ko-hendelse-send', koSkrivIHendelse);
    });
    const felt = document.getElementById('ko-hendelse-tekst');
    felt.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    });
  }
  const traad = document.getElementById('ko-hendelse-traad');
  if (traad) traad.scrollTop = traad.scrollHeight;
  gjenopprett();
}

function koMittBrukernavn() {
  return (globalThis.window && window.KO_BRUKERNAVN) || '';
}

function koHendelseFeil(melding) {
  const boks = document.getElementById('ko-hendelse-feil');
  if (!boks) return;
  boks.textContent = melding || '';
  boks.classList.toggle('d-none', !melding);
}

async function koSkrivIHendelse() {
  const felt = document.getElementById('ko-hendelse-tekst');
  const tidfelt = document.getElementById('ko-hendelse-tid');
  if (!felt || koApenHendelseId === null) return;
  koHendelseFeil('');
  const res = await apiFetch('/ko/api/logg/ny/', {
    method: 'POST',
    body: JSON.stringify({
      tekst: felt.value,
      tidspunkt: koTidspunktISO(tidfelt ? tidfelt.value : ''),
      hendelse_id: koApenHendelseId,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { koHendelseFeil(data.message || 'Linja ble ikke lagret.'); return; }
  felt.value = '';
  if (tidfelt) tidfelt.value = '';
  koLinjer.set(data.data.rot, data.data);
  if (data.data.id > koSisteId) koSisteId = data.data.id;
  // Den som skriver er på hendelsen — hent lista, så navnet står der.
  koHentLogg();
}

// ── Skjemaet «Ny hendelse» / «Rediger hendelse» ─────────────────────────────

function koFyllLokasjoner(valgtId) {
  const sel = document.getElementById('ko-h-lokasjon');
  if (!sel) return;
  const liste = (typeof lokasjoner !== 'undefined' && Array.isArray(lokasjoner)) ? lokasjoner : [];
  sel.innerHTML = '<option value="">—</option>' + liste
    .filter((l) => l.er_aktiv || l.id === valgtId)
    .map((l) => '<option value="' + escapeHtml(l.id) + '">' + escapeHtml(l.navn) + '</option>').join('');
  sel.value = valgtId ? String(valgtId) : '';
}

function koVelgPrioritet(verdi) {
  koValgtPrioritet = verdi;
  document.querySelectorAll('#ko-h-prioritet .ko-prio-knapp').forEach((k) => {
    const valgt = k.dataset.arg === verdi;
    k.classList.toggle('valgt', valgt);
    k.setAttribute('aria-checked', valgt ? 'true' : 'false');
  });
}

function koHendelseModal() {
  const el = document.getElementById('koHendelseModal');
  if (!el || typeof bootstrap === 'undefined') return null;
  return bootstrap.Modal.getOrCreateInstance(el);
}

function _koFyllSkjema(h, fraLinjeId, forslag) {
  const sett = (id, verdi) => { const el = document.getElementById(id); if (el) el.value = verdi || ''; };
  sett('ko-h-id', h ? h.id : '');
  sett('ko-h-versjon', h ? h.versjon : '');
  sett('ko-h-fra-linje', fraLinjeId || '');
  sett('ko-h-tittel', h ? h.tittel : (forslag || ''));
  sett('ko-h-melder', h ? h.melder : '');
  sett('ko-h-beskrivelse', '');
  koFyllLokasjoner(h ? h.lokasjon_id : null);
  koVelgPrioritet(h ? h.prioritet : '');
  const typer = new Set(h ? (h.melder_typer || []) : []);
  document.querySelectorAll('#ko-h-melder-typer input[type="checkbox"]').forEach((b) => {
    b.checked = typer.has(b.value);
  });
  koMelderAndreEndret();
  koFyllLagvalg(h);
  // Beskrivelsen legges til, aldri redigeres: ved redigering står den i
  // hendelsen med sitt eget skjema, og blokka her skjules.
  const besk = document.getElementById('ko-h-beskrivelse-blokk');
  if (besk) besk.classList.toggle('d-none', Boolean(h));
  const tittel = document.getElementById('ko-hendelse-modal-tittel');
  if (tittel) tittel.innerHTML = '<i class="bi bi-flag me-2"></i>' + (h ? 'Rediger ' + escapeHtml(h.kode) : 'Ny hendelse');
  const lagre = document.getElementById('ko-h-lagre-tekst');
  if (lagre) lagre.textContent = h ? 'Lagre' : 'Opprett hendelse';
  const av = document.getElementById('ko-h-opprettes-av');
  if (av) {
    av.innerHTML = h
      ? '<i class="bi bi-person me-1"></i>Opprettet av <b>' + escapeHtml(h.opprettet_av || '—') + '</b> ' + escapeHtml(koKlokke(h.opprettet_at))
      : '<i class="bi bi-person me-1"></i>Opprettes av <b>' + escapeHtml(koMittBrukernavn()) + '</b> · nå';
  }
  const prio = document.getElementById('ko-h-prioritet');
  // Prioriteten endres med sin egen knapp i hendelsen (og logges der), ikke
  // i redigeringsskjemaet — ellers ville to veier gitt to ulike spor.
  if (prio) prio.closest('.mb-3').classList.toggle('d-none', Boolean(h));
  const feil = document.getElementById('ko-h-feil');
  if (feil) feil.classList.add('d-none');
}

// Tekstfeltet bak «Andre» vises bare når «Andre» er krysset av.
function koMelderAndreEndret() {
  const andre = document.querySelector('#ko-h-melder-typer input[value="andre"]');
  const felt = document.getElementById('ko-h-melder');
  if (!felt) return;
  const vis = Boolean(andre && andre.checked);
  felt.classList.toggle('d-none', !vis);
  if (vis) felt.focus();
}

// Avkryssingene for lag: vaktlistas ressurser uten enhet, med «på H13 ·
// 18 min» der laget er opptatt. Uten kandidater sier skjemaet hvorfor.
function koFyllLagvalg(h) {
  const boks = document.getElementById('ko-h-lag');
  if (!boks) return;
  const paa = new Set((h ? h.lag : []).map((l) => l.ressurs_id));
  const rader = koLagKandidater().map((r) => {
    const opptatt = koLagPaa(r.id).filter((x) => !h || x.id !== h.id);
    const hint = opptatt.length
      ? '<span class="ko-opptatt small">på ' + escapeHtml(opptatt.map((x) => x.kode).join(', '))
        + ' · ' + escapeHtml(koSiden(opptatt[0].fra)) + '</span>'
      : '<span class="text-muted small">' + (r.antall
        ? escapeHtml(String(r.tilstede)) + ' av ' + escapeHtml(String(r.antall)) + ' møtt' : 'ubemannet') + '</span>';
    return '<label class="form-check nytt-enhet-valg"><input class="form-check-input" type="checkbox"'
      + ' value="' + escapeHtml(r.id) + '"' + (paa.has(r.id) ? ' checked' : '') + '> '
      + escapeHtml(r.navn) + ' ' + hint + '</label>';
  }).join('');
  boks.innerHTML = rader
    || '<span class="form-text">Ingen lag i vaktlista som er i bruk — eller du mangler vaktlistetilgang.</span>';
}

function koNyHendelse() {
  _koFyllSkjema(null, null, '');
  const modal = koHendelseModal();
  if (modal) modal.show();
  const felt = document.getElementById('ko-h-tittel');
  if (felt) setTimeout(() => felt.focus(), 200);
}

// «Hendelse» på en logglinje (§4.5): linja blir stående, hendelsen peker
// tilbake. Tittelen foreslås fra linja.
function koHendelseFraLinje(linjeId) {
  const linje = Array.from(koLinjer.values()).find((l) => l.id === linjeId);
  _koFyllSkjema(null, linjeId, linje ? String(linje.tekst).slice(0, 120) : '');
  const modal = koHendelseModal();
  if (modal) modal.show();
}

function koRedigerHendelse(id) {
  const h = koHendelser.get(Number(id));
  if (!h) return;
  _koFyllSkjema(h, null, '');
  const modal = koHendelseModal();
  if (modal) modal.show();
}

async function _koHendelsehandling(sti, kropp) {
  const res = await apiFetch(sti, { method: 'POST', body: JSON.stringify(kropp || {}) });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

function _koSkjemaverdier() {
  const les = (id) => (document.getElementById(id) || {}).value || '';
  const lok = les('ko-h-lokasjon');
  return {
    tittel: les('ko-h-tittel'),
    melder: les('ko-h-melder'),
    beskrivelse: les('ko-h-beskrivelse'),
    lokasjon_id: lok ? Number(lok) : null,
    melder_typer: Array.from(document.querySelectorAll('#ko-h-melder-typer input:checked'))
      .map((b) => b.value),
    lag: Array.from(document.querySelectorAll('#ko-h-lag input:checked'))
      .map((b) => Number(b.value)),
  };
}

async function koLagreHendelse() {
  await withSubmitGuard('ko-h-lagre', async () => {
    const les = (feltId) => (document.getElementById(feltId) || {}).value || '';
    const feil = document.getElementById('ko-h-feil');
    const id = (document.getElementById('ko-h-id') || {}).value;
    const verdier = _koSkjemaverdier();
    let svar;
    if (id) {
      verdier.versjon = Number((document.getElementById('ko-h-versjon') || {}).value);
      svar = await _koHendelsehandling('/ko/api/hendelser/' + id + '/rediger/', verdier);
    } else {
      if (!koPrioritetValgt()) {
        if (feil) { feil.textContent = 'Velg prioritet.'; feil.classList.remove('d-none'); }
        return;
      }
      verdier.prioritet = koValgtPrioritet;
      verdier.beskrivelse = les('ko-h-beskrivelse');
      const fra = (document.getElementById('ko-h-fra-linje') || {}).value;
      verdier.fra_linje = fra ? Number(fra) : null;
      svar = await _koHendelsehandling('/ko/api/hendelser/ny/', verdier);
    }
    if (!svar.res.ok) {
      if (feil) { feil.textContent = svar.data.message || 'Hendelsen ble ikke lagret.'; feil.classList.remove('d-none'); }
      if (svar.res.status === 409) koHentLogg();
      return;
    }
    const modal = koHendelseModal();
    if (modal) modal.hide();
    // Åpne den nye hendelsen med det samme — det er der oppdragene lages.
    if (!id && svar.data.data) koApenHendelseId = svar.data.data.id;
    koHentLogg();
    // Lagene og beskrivelsen følger oppdragene ut til bilene.
    koHentOppdragPaaNytt();
  });
}

// Tavla er sentralbordets: nullstill ETag-en så neste henting får raden.
function koHentOppdragPaaNytt() {
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  if (typeof lastOppdrag === 'function') lastOppdrag();
}

// ── Handlingene på en hendelse ──────────────────────────────────────────────

async function koSettPrioritet(arg) {
  const [id, verdi] = String(arg).split(':');
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/prioritet/', { prioritet: verdi });
  if (!res.ok) { window.alert(data.message || 'Prioriteten ble ikke endret.'); return; }
  koHentLogg();
}

async function koBliMed(id) {
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/bli-med/');
  if (!res.ok) { window.alert(data.message || 'Kunne ikke bli med.'); return; }
  koHentLogg();
}

// Lagene sendes som hele lista; serveren regner differansen og logger.
async function _koSettLag(id, ider) {
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/lag/', { lag: ider });
  if (!res.ok) { window.alert(data.message || 'Lagene ble ikke endret.'); return; }
  await koHentLogg();
  koHentOppdragPaaNytt();
}

async function koLeggTilLag(id) {
  const h = koHendelser.get(Number(id));
  const sel = document.getElementById('ko-lag-valg-' + id);
  if (!h || !sel || !sel.value) return;
  await _koSettLag(id, (h.lag || []).map((l) => l.ressurs_id).concat([Number(sel.value)]));
}

async function koTaAvLag(arg) {
  const [id, ressursId] = String(arg).split(':').map(Number);
  const h = koHendelser.get(id);
  if (!h) return;
  await _koSettLag(id, (h.lag || []).map((l) => l.ressurs_id).filter((r) => r !== ressursId));
}

// Et tillegg til beskrivelsen: samme sti som en kommentar, med merket.
async function _koLeggTilTillegg(hendelseId, feltId) {
  const felt = document.getElementById(feltId);
  if (!felt || !felt.value.trim()) return false;
  const res = await apiFetch('/ko/api/logg/ny/', {
    method: 'POST',
    body: JSON.stringify({ tekst: felt.value, hendelse_id: Number(hendelseId), beskrivelse: true }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { window.alert(data.message || 'Tillegget ble ikke lagret.'); return false; }
  felt.value = '';
  koLinjer.set(data.data.rot, data.data);
  if (data.data.id > koSisteId) koSisteId = data.data.id;
  await koHentLogg();
  koHentOppdragPaaNytt();
  return true;
}

async function koLeggTilBeskrivelse(id) {
  await _koLeggTilTillegg(id, 'ko-tillegg-' + id);
}

// Fra oppdragets detaljmodal (skisse D): samme tillegg, og oppdraget
// tegnes på nytt så lista der oppdateres.
async function koLeggTilBeskrivelseFraOppdrag(id) {
  const ok = await _koLeggTilTillegg(id, 'ko-tillegg-o-' + id);
  if (ok && typeof apentOppdragId !== 'undefined' && apentOppdragId && typeof visOppdrag === 'function') {
    await visOppdrag(apentOppdragId);
  }
}

// Detaljmodalen på et oppdrag: beskrivelsen på hendelsen, med skjemaet for
// den som kan skrive i KO. Kalles fra `oppdrag-sentral-oppdrag.js` gjennom
// en vakt; oppdragsmodulen tegner lista selv på `/oppdrag/`, der KO ikke
// finnes, og denne legger skjemaet til på `/ko/`.
function koBeskrivelseSkjema(o) {
  if (!o.hendelse_id || !koKanSkrive()) return '';
  const id = escapeHtml(o.hendelse_id);
  return koTilleggSkjemaHtml(id, 'ko-tillegg-o-' + id, 'koLeggTilBeskrivelseFraOppdrag');
}

async function koLukkHendelse(id) {
  const h = koHendelser.get(Number(id));
  if (!h) return;
  let { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/lukk/');
  if (res.status === 409) {
    // §4.6: en dør hun må åpne bevisst, ikke en vegg. Antallet står i svaret.
    const antall = data.apne_oppdrag || 0;
    if (!window.confirm(
        (data.message || 'Hendelsen har åpne oppdrag.')
        + '\n\nLukke likevel? Oppdragene blir stående på tavla, og at du lukket med '
        + antall + ' åpne står i loggen.')) {
      return;
    }
    ({ res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/lukk/', { confirm: true }));
  }
  if (!res.ok) { window.alert(data.message || 'Hendelsen ble ikke lukket.'); return; }
  // Tilbake til lista (André, 19. sep. 2026): hendelsen er avsluttet, og
  // neste ting å se på er de som fortsatt er åpne.
  koApenHendelseId = null;
  koHentLogg();
}

async function koGjenapneHendelse(id) {
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/gjenapne/');
  if (!res.ok) { window.alert(data.message || 'Hendelsen ble ikke åpnet igjen.'); return; }
  koHentLogg();
}

// ── Søk og brytere i hodet ──────────────────────────────────────────────────

function koVippSok() {
  const felt = document.getElementById('ko-hendelse-sok-felt');
  const input = document.getElementById('ko-hendelse-sok');
  if (!felt) return;
  const skjult = felt.classList.toggle('d-none');
  if (skjult) { koSok = ''; if (input) input.value = ''; koTegnHendelser(); }
  else if (input) input.focus();
}

function koSokEndret() {
  const input = document.getElementById('ko-hendelse-sok');
  koSok = input ? input.value : '';
  koTegnHendelser();
}

function koVippLukkede() {
  const b = document.getElementById('ko-vis-lukkede');
  koVisLukkede = !b || b.checked;
  koLagreVisLukkede(koVisLukkede);
  koTegnHendelser();
}

// ── Oppdragene: nytt fra hendelsen, knytt og løsne ──────────────────────────

// «Nytt oppdrag» fra hendelsen: sentralbordets eget skjema, med hendelsen og
// stedet forhåndsvalgt (skisse 5). Samme modal, samme endepunkt.
function koNyttOppdragFraHendelse(id) {
  const h = koHendelser.get(Number(id));
  const el = document.getElementById('nyttOppdragModal');
  if (!h || !el || typeof bootstrap === 'undefined') return;
  // **Vis først, fyll etterpå.** `show.bs.modal` fyrer inne i `.show()` og
  // kjører `nullstillNyttOppdrag`, som setter nedtrekkene til første valg —
  // fylt vi før, ble stedet vasket bort (funnet 19. sep. 2026).
  bootstrap.Modal.getOrCreateInstance(el).show();
  koFyllHendelsevalg();
  const sel = document.getElementById('nytt-hendelse');
  if (sel) sel.value = String(h.id);
  koHendelsevalgEndret();
  const lok = document.getElementById('nytt-lokasjon');
  if (lok && h.lokasjon_id) lok.value = String(h.lokasjon_id);
}

async function koKnyttEksisterende(id) {
  const sel = document.getElementById('ko-knytt-valg');
  if (!sel || !sel.value) return;
  await _koSettHendelsePaaOppdrag(Number(sel.value), Number(id));
}

// Detaljmodalen på et oppdrag: hvilken hendelse det hører til, med knytt og
// løsne. Kalles fra `oppdrag-sentral-oppdrag.js` gjennom en vakt.
function koHendelseValg(o) {
  // Bare for den som kan skrive i **begge** modulene — serveren krever det.
  const kanKnytte = koKanSkrive() && (window.OPPDRAG_TILGANG || {}).kanSkrive;
  const naa = o.hendelse_nummer
    ? '<span class="hendelse-merke">' + escapeHtml(hendelsesnr(o.hendelse_nummer)) + '</span>'
      + ' <span>' + escapeHtml(o.hendelse_tittel || '') + '</span>'
    : '<span class="text-muted">Uten hendelse</span>';
  if (!kanKnytte) return '<div class="mb-2 small">Hendelse: ' + naa + '</div>';
  const valg = koApneHendelser()
    .filter((h) => h.id !== o.hendelse_id)
    .map((h) => '<option value="' + escapeHtml(h.id) + '">' + escapeHtml(h.kode) + ' ' + escapeHtml(h.tittel) + '</option>')
    .join('');
  const losne = o.hendelse_id
    ? '<button class="btn btn-outline-secondary" type="button"'
      + ' data-action="koLosneOppdrag" data-id="' + escapeHtml(o.id) + '">Løsne</button>'
    : '';
  return '<div class="mb-2 small d-flex align-items-center gap-2 flex-wrap">'
    + '<span>Hendelse: ' + naa + '</span>'
    + '<span class="input-group input-group-sm w-auto">'
    + '<select id="knytt-hendelse" class="form-select" aria-label="Hendelse">'
    + '<option value="">Velg hendelse</option>' + valg + '</select>'
    + '<button class="btn btn-outline-primary" type="button"'
    + ' data-action="koKnyttOppdrag" data-id="' + escapeHtml(o.id) + '">Knytt</button>'
    + losne
    + '</span></div>';
}

async function _koSettHendelsePaaOppdrag(oppdragId, hendelseId) {
  const res = await apiFetch('/ko/api/oppdrag/' + oppdragId + '/hendelse/', {
    method: 'POST',
    body: JSON.stringify({ hendelse_id: hendelseId }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { window.alert(data.message || 'Kunne ikke endre hendelsen på oppdraget.'); return; }
  // Tavla er sentralbordets: nullstill ETag-en så neste henting får raden.
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  if (typeof lastOppdrag === 'function') await lastOppdrag();
  if (typeof apentOppdragId !== 'undefined' && apentOppdragId === oppdragId
      && typeof visOppdrag === 'function') await visOppdrag(oppdragId);
  koHentLogg();
}

async function koKnyttOppdrag(oppdragId) {
  const sel = document.getElementById('knytt-hendelse');
  if (!sel || !sel.value) return;
  await _koSettHendelsePaaOppdrag(oppdragId, Number(sel.value));
}

async function koLosneOppdrag(oppdragId) {
  await _koSettHendelsePaaOppdrag(oppdragId, null);
}

// Nedtrekket «Hendelse» sist i «Nytt oppdrag» (André, 18. sep. 2026). Plassen
// (`#nytt-hendelse-plass`) står tom i den delte malbiten, fordi
// oppdragsmodulen ikke kjenner hendelser; KO fyller den.
function koLeggHendelsevalgINyttOppdrag() {
  const plass = document.getElementById('nytt-hendelse-plass');
  if (!plass || document.getElementById('nytt-hendelse')) return;
  plass.className = 'mb-3';
  plass.innerHTML = '<label class="form-label" for="nytt-hendelse">Hendelse</label>'
    + '<select id="nytt-hendelse" class="form-select" data-action="koHendelsevalgEndret" data-hendelse="change">'
    + '<option value="">Uten hendelse</option></select>'
    + '<div class="form-text">Oppdraget knyttes til hendelsen når det er opprettet. Kan endres senere.</div>'
    + '<div id="nytt-hendelse-info" class="mt-2"></div>';
  koFyllHendelsevalg();
}

// Beskrivelsen fra hendelsen, vist i «Nytt oppdrag» så det er tydelig at den
// følger med til enhetene (André, 19. sep. 2026). Lesevisning; tillegg
// legges til i hendelsen.
function koHendelseInfoHtml(h) {
  const tillegg = h.beskrivelse || [];
  const liste = tillegg.length
    ? '<div class="b-liste b-liste-kompakt">' + tillegg.map((t, i) => koTilleggHtml(t, i === tillegg.length - 1)).join('') + '</div>'
    : '<span class="text-muted small">Hendelsen har ingen beskrivelse ennå.</span>';
  return '<div class="ko-hendelse-info"><div class="form-label mb-1">Beskrivelse fra '
    + '<span class="hendelse-merke">' + escapeHtml(h.kode) + '</span> <span class="text-muted small fw-normal">'
    + '— følger med til enhetene på oppdraget</span></div>' + liste + '</div>';
}

// Når hendelsen i skjemaet endres: vis beskrivelsen som følger med, og la
// friteksten hete «Bare dette oppdraget» — den gjelder bare enhetene på
// dette oppdraget, ikke hendelsen.
function koHendelsevalgEndret() {
  const sel = document.getElementById('nytt-hendelse');
  const info = document.getElementById('nytt-hendelse-info');
  const etikett = document.getElementById('nytt-fritekst-label');
  const hint = document.getElementById('nytt-fritekst-hint');
  if (!sel) return;
  const h = koHendelser.get(Number(sel.value));
  if (info) info.innerHTML = h ? koHendelseInfoHtml(h) : '';
  if (etikett) {
    if (!etikett.dataset.standard) etikett.dataset.standard = etikett.textContent;
    etikett.textContent = h ? 'Bare dette oppdraget' : etikett.dataset.standard;
  }
  if (hint) {
    if (!hint.dataset.standard) hint.dataset.standard = hint.textContent;
    hint.textContent = h
      ? 'Gjelder bare enhetene på dette oppdraget — beskrivelsen fra ' + h.kode
        + ' står over og følger med av seg selv. Lagres ikke i auditloggen.'
      : hint.dataset.standard;
  }
}

function koFyllHendelsevalg() {
  const sel = document.getElementById('nytt-hendelse');
  if (!sel) return;
  const valgt = sel.value;
  sel.innerHTML = '<option value="">Uten hendelse</option>'
    + koApneHendelser().map((h) =>
      '<option value="' + escapeHtml(h.id) + '">' + escapeHtml(h.kode) + ' ' + escapeHtml(h.tittel) + '</option>').join('');
  if (valgt && koHendelser.has(Number(valgt))) sel.value = valgt;
  koHendelsevalgEndret();
}

// Etter «Opprett» i sentralbordets skjema: knytt til hendelsen som var valgt.
async function koEtterOpprettet(oppdragId) {
  const sel = document.getElementById('nytt-hendelse');
  if (!sel || !sel.value) return;
  const hendelseId = Number(sel.value);
  sel.value = '';
  const res = await apiFetch('/ko/api/oppdrag/' + oppdragId + '/hendelse/', {
    method: 'POST',
    body: JSON.stringify({ hendelse_id: hendelseId }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    window.alert(data.message || 'Oppdraget ble opprettet, men ikke knyttet til hendelsen.');
  }
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  koHentLogg();
}


// ── Nullstill (KO-innstillinger, 18. sep. 2026) ─────────────────────────────
//
// «Det skal gå an for test og utvikling. På prod så står admin ansvarlig for
// databehandlingen» (André). Fanen tegnes herfra gjennom `tegn`-kroken i
// sentralbordets admin-JS; serveren krever global admin og `confirm`, og
// skriver en auditrad. Ren markup uten data — ingenting å escape.

const KO_NULLSTILL = [
  ['oppdrag', 'Nullstill oppdragslista', 'Alle oppdrag i aktiv vakt, tavla og historikken, med statusmeldingene. O-serien starter på 1 igjen. Enheter, lokasjoner og valglister røres ikke.'],
  ['hendelser', 'Nullstill hendelsesloggen', 'Alle hendelser i aktiv vakt. Loggen og oppdragene blir stående, men mister H-merkene. H-serien starter på 1 igjen.'],
  ['logg', 'Nullstill loggstrømmen', 'Alle logglinjer i aktiv vakt, systemlinjer og festede inkludert. Hendelsene blir stående uten linjer.'],
];

function koTegnNullstill() {
  const rader = KO_NULLSTILL.map(([hva, tittel, tekst]) =>
    '<div class="d-flex align-items-start gap-3 py-2 border-bottom">'
    + '<div class="flex-grow-1"><div class="fw-semibold">' + tittel + '</div>'
    + '<div class="oppdrag-meta">' + tekst + '</div></div>'
    + '<button type="button" class="btn btn-sm btn-outline-danger" data-action="koNullstill"'
    + ' data-arg="' + hva + '"><i class="bi bi-trash me-1"></i>Nullstill</button>'
    + '</div>').join('');
  return '<div class="alert alert-warning py-2 small mb-2"><strong>Sletter for godt, uten arkiv.</strong> '
    + 'Ment for test og utvikling. I produksjon står du som admin ansvarlig for databehandlingen; '
    + 'det som slettes finnes etterpå bare i backupen. Hver nullstilling logges i revisjonsloggen.</div>'
    + rader;
}

async function koNullstill(hva) {
  const rad = KO_NULLSTILL.find((r) => r[0] === hva);
  if (!rad) return;
  if (!window.confirm(rad[1] + '?\n\n' + rad[2] + '\n\nDette kan ikke angres.')) return;
  const { res, data } = await _koHendelsehandling('/ko/api/nullstill/' + hva + '/', { confirm: true });
  if (!res.ok) { window.alert(data.message || 'Nullstillingen gikk ikke gjennom.'); return; }
  // Alt tegnes på nytt fra null: loggen henter alt igjen, og tavla nullstiller ETag-ene.
  koLinjer = new Map();
  koSisteId = 0;
  koApenHendelseId = null;
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  if (typeof etagEnheter !== 'undefined') etagEnheter = null;
  if (typeof lastAlt === 'function') await lastAlt();
  await koHentLogg();
  window.alert(rad[1] + ': ' + data.antall + ' slettet.');
}
