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

//: Bryterne i hodet.
let koVisLukkede = true;
let koSok = '';

//: Prioriteten valgt i skjemaet.
let koValgtPrioritet = 'gronn';

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
// beskrivelse og lagene. Tom søketekst treffer alt.
function koHendelseTreffer(h, sok) {
  const s = String(sok || '').trim().toLowerCase();
  if (!s) return true;
  const felt = [h.kode, String(h.nummer), h.tittel, h.lokasjon_navn, h.melder,
                h.beskrivelse, h.lagsressurser];
  return felt.some((f) => String(f || '').toLowerCase().includes(s));
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
  const under = h.beskrivelse
    ? '<div class="h-under">' + escapeHtml(String(h.beskrivelse).slice(0, 90)) + '</div>' : '';
  const behov = (h.ressursbehov || []).map((r) => escapeHtml(r.navn)).join(', ');
  const behovHtml = behov
    ? '<span class="h-ressurs"><i class="bi bi-truck me-1"></i>' + behov + '</span>'
    : '<span class="text-muted small">—</span>';
  const oppdrag = koOppdragForHendelse(h);
  const oppdragHtml = oppdrag.length
    ? oppdrag.map((o) => '<span class="hendelse-merke me-1">' + escapeHtml(oppdragsnr(o.nummer)) + '</span>').join('')
      + '<span class="text-muted small">' + escapeHtml(String(h.apne_oppdrag || 0)) + ' åpne</span>'
    : '<span class="text-muted small">Ingen</span>';
  const status = lukket
    ? '<span class="badge badge-lukket">Lukket ' + escapeHtml(koKlokke(h.lukket_at)) + '</span>'
    : '<span class="badge badge-apen">Åpen</span>';
  const melder = h.melder
    ? '<div class="h-under">Meldt av ' + escapeHtml(h.melder) + '</div>' : '';
  return '<tr class="' + klasser + '" data-action="koApneHendelse" data-id="' + escapeHtml(h.id) + '"'
    + ' role="button" tabindex="0">'
    + '<td>' + koPrioIkon(h.prioritet) + '</td>'
    + '<td class="h-nowrap"><span class="hendelse-merke">' + escapeHtml(h.kode) + '</span></td>'
    + '<td class="h-nowrap text-muted">' + escapeHtml(koKlokke(h.opprettet_at)) + '</td>'
    + '<td><div class="h-tittel">' + escapeHtml(h.tittel) + '</div>' + under + melder + '</td>'
    + '<td>' + koPrioMerke(h.prioritet) + '</td>'
    + '<td>' + escapeHtml(h.lokasjon_navn || '—') + '</td>'
    + '<td>' + behovHtml + '</td>'
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
    + '<th>Ressurs</th><th>Oppdrag</th><th>Opprettet av</th><th>Status</th>'
    + '</tr></thead><tbody>' + rader.map(koHendelseRadHtml).join('') + '</tbody></table>';
}

function koTaImotHendelser(liste) {
  koHendelser = new Map((liste || []).map((h) => [h.id, h]));
  if (koApenHendelseId !== null && !koHendelser.has(koApenHendelseId)) koApenHendelseId = null;
  koTegnHendelser();
  koFyllHendelsevalg();
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
  return '<div class="h-linje' + (system ? ' system' : '') + '">'
    + '<span class="tid">' + escapeHtml(koKlokke(linje.tidspunkt)) + '</span>'
    + tekst + hvem + '</div>';
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

function koTegnDetalj() {
  const boks = document.getElementById('ko-hendelse-detalj');
  const liste = document.getElementById('ko-hendelser-liste');
  const h = koHendelser.get(koApenHendelseId);
  if (!boks || !h) { koApenHendelseId = null; if (boks) boks.classList.add('d-none'); return; }
  liste.classList.add('d-none');
  boks.classList.remove('d-none');
  const kan = koKanSkrive();
  const lukket = h.status !== 'apen';
  const deltar = (h.deltakere || []).map((n) => '<span class="navn">' + escapeHtml(n) + '</span>').join(', ');
  const behov = (h.ressursbehov || []).map((r) => escapeHtml(r.navn)).join(', ');
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
  const lagFelt = kan
    ? '<span class="input-group input-group-sm w-auto flex-grow-1">'
      + '<span class="input-group-text"><i class="bi bi-people"></i></span>'
      + '<input type="text" class="form-control" id="ko-lag-' + escapeHtml(h.id) + '" maxlength="255"'
      + ' placeholder="Lagene som er på hendelsen, f.eks. Lag 1, Lag 3"'
      + ' value="' + escapeHtml(h.lagsressurser || '') + '" aria-label="Lagsressurser">'
      + '<button type="button" class="btn btn-outline-secondary" data-action="koLagreLagsressurser"'
      + ' data-id="' + escapeHtml(h.id) + '">Lagre</button></span>'
    : '<span class="h-felt"><i class="bi bi-people"></i> Lag: <b>' + escapeHtml(h.lagsressurser || '—') + '</b></span>';
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
    + '<div class="h-hode h-' + prio + ' mb-2">'
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
    + '<span class="h-felt"><i class="bi bi-megaphone"></i> Melder: <b>' + escapeHtml(h.melder || '—') + '</b></span>'
    + '<span class="h-felt"><i class="bi bi-truck"></i> Ressursbehov: <b>' + (behov || '—') + '</b></span>'
    + '<span class="h-felt"><i class="bi bi-person"></i> Opprettet av <b>' + escapeHtml(h.opprettet_av || '—') + '</b> '
    + escapeHtml(koKlokke(h.opprettet_at)) + '</span></div>'
    + (h.beskrivelse ? '<div class="h-beskrivelse mt-1">' + escapeHtml(h.beskrivelse) + '</div>' : '')
    + '</div>'
    + '<div class="d-flex align-items-center gap-2 mb-1 flex-wrap"><span class="h-seksjon">Oppdrag på hendelsen</span>'
    + '<span class="ms-auto d-flex gap-1 flex-wrap">' + nyttOppdrag + knyttValg + '</span></div>'
    + '<div class="d-grid gap-1 mb-2">' + (oppdrag.length ? oppdrag.map(koHendelseOppdragHtml).join('')
      : '<span class="text-muted small">Ingen oppdrag ennå.</span>') + '</div>'
    + '<div class="d-flex align-items-center gap-2 mb-2 flex-wrap"><span class="h-seksjon">Lagsressurser</span>' + lagFelt + '</div>'
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
  sett('ko-h-beskrivelse', h ? h.beskrivelse : '');
  koFyllLokasjoner(h ? h.lokasjon_id : null);
  koVelgPrioritet(h ? h.prioritet : 'gronn');
  const valgte = new Set((h ? h.ressursbehov : []).map((r) => r.id));
  document.querySelectorAll('#ko-h-ressursbehov input[type="checkbox"]').forEach((b) => {
    b.checked = valgte.has(Number(b.value));
  });
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
    ressursbehov: Array.from(document.querySelectorAll('#ko-h-ressursbehov input:checked'))
      .map((b) => Number(b.value)),
  };
}

async function koLagreHendelse() {
  await withSubmitGuard('ko-h-lagre', async () => {
    const feil = document.getElementById('ko-h-feil');
    const id = (document.getElementById('ko-h-id') || {}).value;
    const verdier = _koSkjemaverdier();
    let svar;
    if (id) {
      verdier.versjon = Number((document.getElementById('ko-h-versjon') || {}).value);
      svar = await _koHendelsehandling('/ko/api/hendelser/' + id + '/rediger/', verdier);
    } else {
      verdier.prioritet = koValgtPrioritet;
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
  });
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

async function koLagreLagsressurser(id) {
  const h = koHendelser.get(Number(id));
  const felt = document.getElementById('ko-lag-' + id);
  if (!h || !felt) return;
  if (felt.value.trim() === (h.lagsressurser || '')) return;
  const { res, data } = await _koHendelsehandling('/ko/api/hendelser/' + id + '/rediger/', {
    lagsressurser: felt.value, versjon: h.versjon,
  });
  if (res.status === 409) { window.alert(data.message || 'Hendelsen er endret av noen andre.'); koHentLogg(); return; }
  if (!res.ok) { window.alert(data.message || 'Lagene ble ikke lagret.'); return; }
  koHentLogg();
  // Oppdragene bærer lagene videre til bilene: hent tavla på nytt.
  if (typeof etagOppdrag !== 'undefined') etagOppdrag = null;
  if (typeof lastOppdrag === 'function') lastOppdrag();
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
  koTegnHendelser();
}

// ── Oppdragene: nytt fra hendelsen, knytt og løsne ──────────────────────────

// «Nytt oppdrag» fra hendelsen: sentralbordets eget skjema, med hendelsen og
// stedet forhåndsvalgt (skisse 5). Samme modal, samme endepunkt.
function koNyttOppdragFraHendelse(id) {
  const h = koHendelser.get(Number(id));
  const el = document.getElementById('nyttOppdragModal');
  if (!h || !el || typeof bootstrap === 'undefined') return;
  koFyllHendelsevalg();
  const sel = document.getElementById('nytt-hendelse');
  if (sel) sel.value = String(h.id);
  const lok = document.getElementById('nytt-lokasjon');
  if (lok && h.lokasjon_id) lok.value = String(h.lokasjon_id);
  bootstrap.Modal.getOrCreateInstance(el).show();
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
    + '<select id="nytt-hendelse" class="form-select"><option value="">Uten hendelse</option></select>'
    + '<div class="form-text">Oppdraget knyttes til hendelsen når det er opprettet. Kan endres senere.</div>';
  koFyllHendelsevalg();
}

function koFyllHendelsevalg() {
  const sel = document.getElementById('nytt-hendelse');
  if (!sel) return;
  const valgt = sel.value;
  sel.innerHTML = '<option value="">Uten hendelse</option>'
    + koApneHendelser().map((h) =>
      '<option value="' + escapeHtml(h.id) + '">' + escapeHtml(h.kode) + ' ' + escapeHtml(h.tittel) + '</option>').join('');
  if (valgt && koHendelser.has(Number(valgt))) sel.value = valgt;
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
