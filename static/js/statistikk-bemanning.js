// ════════════════════════════════════════════════════════
// STATISTIKK — bemanningsfanen (pulje 7c, 21. sep. 2026)
//
// Lastes KUN for kontoer med `les_alle` i vaktlista; gaten står server-side
// i statistikk/views.py. Kall hit fra de andre filene går gjennom
// `_kallOppdrag()` i statistikk.js, som sjekker at funksjonen finnes — de to
// andre fanene legger bemanningen som linjer over sine egne grafer, og skal
// virke uten denne fila.
//
// Alt som settes med innerHTML går gjennom mkStatsTable(). Enhetsnavn er
// data fra basen; ingen personnavn finnes i svaret.
// ════════════════════════════════════════════════════════

let bemanningStats = null;
let _bemanningLast = null;

// Henter én gang og deler svaret. Oppdrags- og KO-fanen kaller denne for
// linjene sine; svaret er `null` når hentingen feiler, og da tegnes grafene
// uten linjer — ikke uten stolper.
function sikreBemanning() {
  if (bemanningStats) return Promise.resolve(bemanningStats);
  if (!_bemanningLast) {
    _bemanningLast = apiFetch('/statistikk/api/kilde/vaktliste/full-stats/')
      .then(res => (res.ok ? res.json() : null))
      .then(data => { bemanningStats = data; return data; })
      .catch(e => { console.error('Bemanningsstatistikk feil:', e); return null; });
  }
  return _bemanningLast;
}

async function loadBemanningStats() {
  const s = await sikreBemanning();
  if (s) renderBemanningStats(s);
}

// Linjene de andre fanene legger over grafene sine. Samme farger som i
// bemanningsfanens egen graf, så en linje betyr det samme overalt.
function bemanningLinjer(s, hvilke) {
  const alle = {
    personer: { label: 'Personer på vakt', borderColor: '#22c55e', data: s.per_time.map(r => r.personer) },
    mott: { label: 'Møtt', borderColor: '#86efac', borderDash: [4, 3], data: s.per_time.map(r => r.mott) },
    lag: { label: 'Lag på vakt', borderColor: '#a78bfa', borderDash: [4, 3], data: s.per_time.map(r => r.lag) },
    enheter: { label: 'Enheter på vakt', borderColor: '#0ea5e9', data: s.per_time.map(r => r.enheter) },
  };
  return hvilke.map(k => alle[k]).filter(Boolean);
}

function _timerTekst(t) {
  return t == null ? '–' : String(t).replace('.', ',') + ' t';
}

function mkBemanningUtnyttelseTabell(u) {
  const rader = Object.entries(u).map(([navn, r]) => [
    navn, r.oppdrag, _timerTekst(r.bemannet_timer), _timerTekst(r.oppdrag_timer),
    r.andel == null ? 'ukjent' : r.andel + ' %',
    r.lengste_ledig == null ? 'ukjent' : fmtMin(r.lengste_ledig),
  ]);
  return mkStatsTable(
    ['Enhet', 'Oppdrag', 'Bemannet', 'På oppdrag', 'Andel', 'Lengste ledig'], rader);
}

function renderBemanningStats(s) {
  if (!s || !s.summary) return;
  const sum = s.summary;
  document.getElementById('bkpi-personer').textContent = String(sum.personer);
  document.getElementById('bkpi-personer-sub').textContent =
    sum.skift + ' skift · ' + _timerTekst(sum.persontimer);
  document.getElementById('bkpi-mott').textContent = String(sum.mott);
  document.getElementById('bkpi-enhetstimer').textContent = _timerTekst(sum.enhetstimer);
  document.getElementById('bkpi-lagtimer').textContent = _timerTekst(sum.lagtimer);
  document.getElementById('bkpi-per-enhetstime').textContent =
    sum.oppdrag_per_enhetstime == null ? '–' : String(sum.oppdrag_per_enhetstime).replace('.', ',');
  document.getElementById('bkpi-per-enhetstime-sub').textContent =
    sum.antall_oppdrag + ' oppdrag / ' + _timerTekst(sum.enhetstimer);
  document.getElementById('bkpi-utnyttelse').textContent =
    sum.utnyttelse_median == null ? '–' : sum.utnyttelse_median + ' %';
  document.getElementById('bemanning-uten-liste').classList.toggle('d-none', s.har_vaktliste);

  mkStabletChart('chart-bemanning-time', s.per_time.map(r => String(r.time).padStart(2, '0')), [],
    { linjer: bemanningLinjer(s, ['personer', 'mott', 'lag', 'enheter']), linjeakse: 'y' });
  document.getElementById('tbl-bemanning-utnyttelse').innerHTML =
    mkBemanningUtnyttelseTabell(s.utnyttelse);
}
