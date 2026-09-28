// ════════════════════════════════════════════════════════
// STATISTIKK — fanen «Lag» (park pulje 3, 28. sep. 2026)
//
// Lastes KUN for kontoer med `les` i park; gaten står server-side i
// statistikk/views.py, og malen laster fila deretter. Kallet fra statistikk.js
// hit går gjennom `_kallOppdrag()`, som sjekker at funksjonen finnes.
//
// Bruker hjelperne i statistikk.js (`mkChart`, `mkStatsTable`) og primitivene
// i portal-utils.js (`apiFetch`, `klokke`). Alt som settes med innerHTML går
// gjennom mkStatsTable(), som escaper hver celle — navnene på lag, steder og
// verdimengder er satt av mennesker. `patients/tests_xss_stats.py` leser fila.
// ════════════════════════════════════════════════════════

let parkStats = null;

async function loadParkStats() {
  try {
    const res = await apiFetch('/statistikk/api/kilde/park/full-stats/');
    if (!res.ok) {
      console.warn('Lag-statistikk ikke hentet, status', res.status);
      return;
    }
    parkStats = await res.json();
  } catch (e) {
    console.error('Lag-statistikk feil:', e);
    return;
  }
  renderParkStats(parkStats);
}

// Andelen som ble behandlet på stedet — det tallet ledelsen spør etter først.
// Navnet leses, ikke posisjonen: admin kan flytte og omdøpe utfallene.
function parkAndelPaStedet(s) {
  const total = s.summary.kontakter;
  const rad = (s.per_utfall || []).find(u => u.navn === 'Behandlet på stedet');
  const n = rad ? rad.kontakter : 0;
  return {n, prosent: total ? Math.round(n / total * 100) : null};
}

// ── Tabellbyggere ────────────────────────────────────────────────────────
// Cellene bygges med `+`, ikke mal-strenger — se statistikk-oppdrag.js.

function mkParkKryssTabell(s) {
  const k = s.kryss;
  const rader = k.rader.map((navn, i) => [navn, ...k.celler[i]]);
  return mkStatsTable(['Problemstilling ↓ · utfall →', ...k.kolonner], rader);
}

function mkParkLagTabell(s) {
  const rader = s.per_lag.map(l => [l.navn, l.kontakter, l.registreringer,
                                    l.siste ? klokke(l.siste) : '–']);
  return mkStatsTable(['Lag', 'Kontakter', 'Registreringer', 'Siste'], rader);
}

function mkParkForhandsvalgTabell(s) {
  const rader = s.forhandsvalg.map(f => [f.navn, f.registreringer,
                                         f.endret + ' (' + f.andel_endret + ' %)']);
  return mkStatsTable(['Stedet kom fra', 'Registreringer', 'Byttet av laget'], rader);
}

// ── Rendering ────────────────────────────────────────────────────────────
function renderParkStats(s) {
  if (!s || !s.summary) return;
  const sum = s.summary;
  document.getElementById('pkpi-kontakter').textContent = String(sum.kontakter);
  document.getElementById('pkpi-kontakter-sub').textContent = sum.registreringer + ' registreringer';
  const sted = parkAndelPaStedet(s);
  document.getElementById('pkpi-stedet').textContent = String(sted.n);
  document.getElementById('pkpi-stedet-sub').textContent =
    sted.prosent == null ? '' : sted.prosent + ' % av kontaktene';
  document.getElementById('pkpi-lag').textContent = String(sum.lag);
  document.getElementById('pkpi-steder').textContent = String(sum.steder);
  document.getElementById('pkpi-slettet').textContent = String(sum.slettet);

  const ps = s.per_problemstilling;
  mkChart('chart-park-problemstilling', 'bar', ps.map(p => p.navn), ps.map(p => p.kontakter),
          '#3b82f6', true);
  const ut = s.per_utfall;
  mkChart('chart-park-utfall', 'bar', ut.map(u => u.navn), ut.map(u => u.kontakter), '#16a34a', true);
  const st = s.per_sted;
  mkChart('chart-park-sted', 'bar', st.map(x => x.navn), st.map(x => x.kontakter), '#14b8a6', true);
  mkChart('chart-park-time', 'bar', s.per_time.map(r => String(r.time).padStart(2, '0')),
          s.per_time.map(r => r.kontakter), '#8b5cf6');

  document.getElementById('tbl-park-kryss').innerHTML = mkParkKryssTabell(s);
  document.getElementById('tbl-park-lag').innerHTML = mkParkLagTabell(s);
  document.getElementById('tbl-park-forhandsvalg').innerHTML = mkParkForhandsvalgTabell(s);
}
