// ════════════════════════════════════════════════════════
// STATISTIKK — KO-fanen (pulje 7a, 21. sep. 2026)
//
// Lastes KUN for kontoer med lesetilgang til KO; gaten står server-side i
// statistikk/views.py, og malen laster fila deretter. Kall fra statistikk.js
// hit går gjennom `_kallOppdrag()`, som sjekker at funksjonen finnes —
// samme vern som for statistikk-oppdrag.js.
//
// Fila laster ingenting selv utover hjelperne i statistikk.js (`mkChart`,
// `mkStabletChart`, `mkStatsTable`) og primitivene i portal-utils.js
// (`apiFetch`, `fmtMin`, `klokke`, `escHtmlValue`, `cellHtml`).
//
// Alt som settes med innerHTML går gjennom mkStatsTable(), som escaper hver
// celle — hendelsestitler og siste logglinje er fritekst skrevet av
// operatører. `patients/tests_xss_stats.py` leser denne fila.
// ════════════════════════════════════════════════════════

let koStats = null;

async function loadKoStats() {
  try {
    const res = await apiFetch('/statistikk/api/kilde/ko/full-stats/');
    if (!res.ok) {
      console.warn('KO-statistikk ikke hentet, status', res.status);
      return;
    }
    koStats = await res.json();
  } catch (e) {
    console.error('KO-statistikk feil:', e);
    return;
  }
  renderKoStats(koStats);
}

// Fargene følger prioritetsnavnet, ikke posisjonen — samme regel som for
// hastegradene i oppdragsfanen. Grått for en verdi ingen kjenner.
function _koFarge(kode) {
  return {
    viktig: '#f59e0b', rod: '#dc2626', gul: '#eab308', gronn: '#16a34a',
    drift: '#2563eb', plassering: '#8b5cf6',
  }[kode] || '#64748b';
}

function _koNavn(s, kode) {
  const treff = (s.prioriteter || []).find(([k]) => k === kode);
  return treff ? treff[1] : kode;
}

// ── Tabellbyggere ────────────────────────────────────────────────────────
// Cellene bygges med `+`, ikke mal-strenger — se statistikk-oppdrag.js.

function mkKoHvemLosteTabell(s) {
  const hl = s.hvem_loste;
  const rader = Object.entries(hl.per_prioritet).map(([kode, r]) => [
    _koNavn(s, kode), r.lag_og_oppdrag, r.bare_lag, r.bare_oppdrag, r.verken,
    r.lag_og_oppdrag + r.bare_lag + r.bare_oppdrag + r.verken,
  ]);
  const sum = hl.sum;
  rader.push(['Sum', sum.lag_og_oppdrag, sum.bare_lag, sum.bare_oppdrag, sum.verken,
              sum.lag_og_oppdrag + sum.bare_lag + sum.bare_oppdrag + sum.verken]);
  return mkStatsTable(
    ['Prioritet', 'Lag + oppdrag', 'Bare lag', 'Bare oppdrag', 'Verken', 'n'], rader);
}

function mkKoVerkenTabell(s, liste) {
  const rader = liste.map(v => [
    'H' + v.hendelsesnummer + ' ' + v.tittel,
    _koNavn(s, v.prioritet),
    klokke(v.opprettet) + '–' + klokke(v.lukket) + ' (' + fmtMin(v.minutter) + ')',
    v.lukket_av, v.siste_linje,
  ]);
  return mkStatsTable(['Hendelse', 'Prioritet', 'Tid', 'Lukket av', 'Siste linje'], rader);
}

function mkKoForsteRessursTabell(s) {
  const rader = Object.entries(s.tid_til_forste_ressurs)
    .filter(([kode, ledd]) => kode !== 'alle' && ledd.ressurs.n)
    .map(([kode, ledd]) => [
      _koNavn(s, kode), ledd.ressurs.n, fmtMin(ledd.oppdrag.median),
      fmtMin(ledd.rykker_ut.median), fmtMin(ledd.lag.median), fmtMin(ledd.ressurs.median),
    ]);
  return mkStatsTable(
    ['Prioritet', 'n', '→ oppdrag', '→ Rykker ut', '→ lag på', '→ første'], rader);
}

function mkKoEskaleringTabell(s) {
  const e = s.eskaleringer;
  const brukte = e.koder.filter(k =>
    Object.values(e.matrise[k]).some(v => v) || e.koder.some(f => e.matrise[f][k]));
  if (!brukte.length) return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  const rader = brukte.map(fra => [
    _koNavn(s, fra), ...brukte.map(til => (fra === til ? '–' : e.matrise[fra][til])),
  ]);
  return mkStatsTable(['Fra ↓ · til →', ...brukte.map(k => _koNavn(s, k))], rader);
}

function mkKoStillhetTabell(s) {
  const rader = s.stillhet.map(h => [
    fmtMin(h.minutter) + (h.paagaar ? ' (pågår)' : ''),
    klokke(h.fra) + '–' + klokke(h.til),
    h.apne, h.hoyeste ? _koNavn(s, h.hoyeste) : '–',
  ]);
  return mkStatsTable(['Hull', 'Når', 'Åpne hendelser', 'Høyeste prioritet'], rader);
}

function mkKoVarighetTabell(s) {
  const rader = Object.entries(s.hendelser.varighet_per_prioritet)
    .filter(([, sd]) => sd.n)
    .map(([kode, sd]) => [_koNavn(s, kode), sd.n, fmtMin(sd.median), fmtMin(sd.p90),
                          fmtMin(sd.min), fmtMin(sd.max)]);
  return mkStatsTable(['Prioritet', 'n', 'Median', 'p90', 'Min', 'Maks'], rader);
}

function mkKoLagTabell(s) {
  const rader = Object.entries(s.ressursbruk.per_lag).map(([navn, r]) => [
    navn, r.hendelser, String(r.timer).replace('.', ',') + ' t',
  ]);
  return mkStatsTable(['Lag', 'Hendelser', 'Timer'], rader);
}

function mkKoLoggTabell(s) {
  const l = s.logg;
  const st = s.stemplinger;
  const andel = l.hendelseslinjer ? Math.round(l.delte / l.hendelseslinjer * 100) + ' %' : '–';
  const rader = [
    ['Operatørlinjer', l.operatorlinjer, ''],
    ['Systemlinjer', l.systemlinjer, ''],
    ['Rettinger', l.rettinger, 'median ' + fmtMin(l.tid_til_retting.median) + ' etter føring'],
    ['Fjerninger', l.fjerninger, ''],
    ['Delte hendelseslinjer', l.delte + ' av ' + l.hendelseslinjer + ' (' + andel + ')',
     'median ' + fmtMin(l.tid_til_deling.median) + ' fra skrevet til delt'],
    ['Stemplinger ført av KO', st.ko_forte + ' av ' + st.antall, ''],
    ['Stemplinger meldt forsinket', st.forsinkede + ' av ' + st.antall, 'fra enhet uten dekning'],
    ['Gjenåpninger', s.gjenapninger, ''],
  ];
  return mkStatsTable(['Hva', 'Antall', ''], rader);
}

// ── Rendering ────────────────────────────────────────────────────────────
function renderKoStats(s) {
  if (!s || !s.hendelser) return;
  const h = s.hendelser;
  const p = h.per_prioritet;

  document.getElementById('kkpi-hendelser').textContent = String(h.antall);
  document.getElementById('kkpi-hendelser-sub').textContent = h.apne + ' åpne nå';
  document.getElementById('kkpi-rod-viktig').textContent = String((p.rod || 0) + (p.viktig || 0));
  document.getElementById('kkpi-rod-viktig-sub').textContent =
    (p.rod || 0) + ' rød · ' + (p.viktig || 0) + ' viktig';
  document.getElementById('kkpi-varighet').textContent = fmtMin(h.varighet.median);
  document.getElementById('kkpi-varighet-sub').textContent =
    'median · p90 ' + fmtMin(h.varighet.p90) + ' · ' + h.varighet.n + ' lukkede';

  // «alle» regnes av hendelsene på serveren — medianen av medianene er
  // ikke en median.
  document.getElementById('kkpi-forste-ressurs').textContent =
    fmtMin(s.tid_til_forste_ressurs.alle.ressurs.median);

  const hl = s.hvem_loste;
  const total = hl.sum.lag_og_oppdrag + hl.sum.bare_lag + hl.sum.bare_oppdrag + hl.sum.verken;
  document.getElementById('kkpi-bare-lag').textContent = String(hl.sum.bare_lag);
  document.getElementById('kkpi-bare-lag-sub').textContent = 'av ' + total + ' lukkede utenom drift';
  document.getElementById('kkpi-lagtimer').textContent =
    String(s.ressursbruk.lagtimer).replace('.', ',') + ' t';
  document.getElementById('kkpi-lagtimer-sub').textContent =
    'på hendelser, ' + Object.keys(s.ressursbruk.per_lag).length + ' lag';

  document.getElementById('tbl-ko-hvem-loste').innerHTML = mkKoHvemLosteTabell(s);
  document.getElementById('ko-hvem-loste-fot').textContent = hl.lag_til_oppdrag.n
    ? 'Lag + oppdrag: lag satt på → oppdrag laget, median ' + fmtMin(hl.lag_til_oppdrag.median) + '.'
    : '';
  document.getElementById('tbl-ko-forste-ressurs').innerHTML = mkKoForsteRessursTabell(s);
  document.getElementById('tbl-ko-verken').innerHTML = hl.verken_liste.length
    ? mkKoVerkenTabell(s, hl.verken_liste)
    : '<p class="text-muted small p-2 mb-0">Ingen — hver Rød og Viktig fikk lag eller oppdrag.</p>';

  const sam = s.samtidighet;
  const tegnSam = (linjer) => mkStabletChart(
    'chart-ko-samtidighet', sam.map(r => String(r.time).padStart(2, '0')),
    [{ label: 'Åpne hendelser', data: sam.map(r => r.apne),
       backgroundColor: sam.map(r => _koFarge(r.hoyeste)) }], { linjer });
  tegnSam([]);
  // Lagene på vakt fra vaktlistas kilde (7c), når kontoen har den.
  Promise.resolve(_kallOppdrag('sikreBemanning')).then(b => {
    if (b && koStats === s) tegnSam(_kallOppdrag('bemanningLinjer', b, ['lag', 'personer']) || []);
  });

  document.getElementById('tbl-ko-eskaleringer').innerHTML = mkKoEskaleringTabell(s);
  const e = s.eskaleringer;
  document.getElementById('ko-eskaleringer-fot').textContent = (e.opp + e.ned)
    ? 'Opp: ' + e.opp + ', median ' + fmtMin(e.etter_opprettelse.median)
      + ' etter opprettelse. Ned: ' + e.ned + '.'
    : '';

  document.getElementById('tbl-ko-stillhet').innerHTML = mkKoStillhetTabell(s);
  document.getElementById('tbl-ko-varighet').innerHTML = mkKoVarighetTabell(s);

  const prioKoder = s.prioriteter.map(([k]) => k);
  mkChart('chart-ko-prioritet', 'doughnut',
    s.prioriteter.map(([, navn]) => navn), prioKoder.map(k => p[k] || 0),
    prioKoder.map(_koFarge));
  const lok = Object.keys(h.per_lokasjon);
  mkChart('chart-ko-lokasjon', 'bar', lok, lok.map(l => h.per_lokasjon[l]), '#14b8a6', true);
  mkChart('chart-ko-melder', 'bar',
    s.meldere.map(([, navn]) => navn), s.meldere.map(([k]) => h.per_melder[k] || 0), '#0ea5e9', true);

  document.getElementById('tbl-ko-lag').innerHTML = mkKoLagTabell(s);
  mkStabletChart('chart-ko-logg', s.logg.per_time.map(r => String(r.time).padStart(2, '0')), [
    { label: 'Operatør', backgroundColor: '#3b82f6', data: s.logg.per_time.map(r => r.operator) },
    { label: 'System', backgroundColor: '#64748b', data: s.logg.per_time.map(r => r.system) },
  ]);
  document.getElementById('tbl-ko-logg').innerHTML = mkKoLoggTabell(s);
}
