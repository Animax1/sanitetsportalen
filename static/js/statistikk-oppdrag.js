// ════════════════════════════════════════════════════════
// STATISTIKK — oppdragsfanen (fase 6)
//
// Lastes KUN for kontoer med lesetilgang til oppdragsmodulen; gaten står
// server-side i statistikk/views.py, og malen laster fila deretter. Kall fra
// statistikk.js hit går gjennom `_kallOppdrag()`, som sjekker at funksjonen
// finnes — samme vern som `_kall()` på pasientsiden.
//
// Fila laster ingenting selv utover Chart.js-hjelperen `mkChart()` fra
// statistikk.js og primitivene i portal-utils.js (`apiFetch`, `fmtMin`,
// `escHtmlValue`, `cellHtml`). patients-utils.js finnes ikke på denne siden.
//
// Alt som settes med innerHTML escapes — enhets-, lokasjons- og
// problemstillingsnavn er data fra basen, og lokasjonsnavn er fritekst satt
// av admin. `patients/tests_xss_stats.py` leser denne fila.
// ════════════════════════════════════════════════════════

let oppdragStats = null;

// ── Henting ──────────────────────────────────────────────────────────────
async function loadOppdragStats() {
  try {
    const res = await apiFetch('/statistikk/api/kilde/oppdrag/full-stats/');
    if (!res.ok) {
      // Samme regel som pasientfanen: la forrige visning bli stående. 403
      // betyr at tilgangen er trukket tilbake mens fanen sto åpen, 429 at
      // vi hentet for ofte — ingen av delene er noe å rendre tomme grafer på.
      console.warn('Oppdragsstatistikk ikke hentet, status', res.status);
      return;
    }
    oppdragStats = await res.json();
  } catch (e) {
    console.error('Oppdragsstatistikk feil:', e);
    return;
  }
  renderOppdragStats(oppdragStats);
}

// ── Tabellbyggere ────────────────────────────────────────────────────────

// Rad i en varighetstabell. `sd` er {n, mean, median, min, max} — samme form
// som pasientstatistikkens, slik at fmtMin() kan brukes på begge.
function _sdRad(navn, sd) {
  // fmtMin() svarer '–' på null av seg selv, så ingen ternær her. Etter
  // §12.2 er tomme tidsledd et normaltilfelle — alle varighetene i en
  // kolonne kan være utelatt fordi sluttiden var avledet.
  return [navn, sd.n, fmtMin(sd.median), fmtMin(sd.mean),
          fmtMin(sd.min), fmtMin(sd.max)];
}

function mkOppdragTiderTabell(sum) {
  // Rekkefølgen følger oppdragets gang, ikke alfabetet: den som leser skal
  // kunne se hvor tiden går uten å sortere i hodet.
  const ledd = [
    ['Til utrykning', sum.ventetid],
    ['Utrykning → fremme', sum.utrykningstid],
    ['Responstid (til fremme)', sum.responstid],
    ['På stedet', sum.tid_pa_stedet],
    ['Hele oppdraget', sum.oppdragstid],
  ];
  const rader = ledd.map(([navn, sd]) => _sdRad(navn, sd));
  return mkStatsTable(['Tidsledd', 'n', 'Median', 'Snitt', 'Min', 'Maks'], rader);
}

function mkOppdragSdTabell(kolonnenavn, kart) {
  const rader = Object.entries(kart).map(([navn, sd]) => _sdRad(navn, sd));
  return mkStatsTable([kolonnenavn, 'n', 'Median', 'Snitt', 'Min', 'Maks'], rader);
}

// ── Rendering ────────────────────────────────────────────────────────────
function renderOppdragStats(s) {
  if (!s || !s.summary) return;
  const sum = s.summary;

  document.getElementById('okpi-total').textContent = sum.total;
  document.getElementById('okpi-aktive').textContent = sum.aktive;
  document.getElementById('okpi-fullforte').textContent = sum.fullforte;
  document.getElementById('okpi-enheter').textContent = sum.enheter_pa_vakt;
  document.getElementById('okpi-responstid').textContent =
    fmtMin(sum.responstid.median);
  document.getElementById('okpi-oppdragstid').textContent =
    fmtMin(sum.oppdragstid.median);

  _visUtelatt(sum);

  document.getElementById('tbl-oppdrag-tider').innerHTML =
    mkOppdragTiderTabell(sum);
  document.getElementById('tbl-oppdrag-resp-hastegrad').innerHTML =
    mkOppdragSdTabell('Hastegrad', s.responstid_per_hastegrad);
  document.getElementById('tbl-oppdrag-resp-enhet').innerHTML =
    mkOppdragSdTabell('Enhet', s.responstid_per_enhet);
  document.getElementById('tbl-oppdrag-tid-problem').innerHTML =
    mkOppdragSdTabell('Problemstilling', s.oppdragstid_per_problemstilling);

  _tegnGrafer(s);
}

// Utelatte varigheter (§12.2). Teksten står bare når det faktisk er noe å
// si fra om — en permanent «0 utelatt» ville vært støy som gjør at den ene
// gangen tallet betyr noe, leses den ikke.
function _visUtelatt(sum) {
  const el = document.getElementById('oppdrag-utelatt');
  if (!el) return;
  const u = sum.utelatt || { automatisk: 0, negativ: 0 };
  const deler = [];
  if (u.automatisk) {
    deler.push(`${u.automatisk} varighet(er) er utelatt fordi oppdraget ble `
      + 'avsluttet automatisk da enheten rykket ut på det neste — sluttiden '
      + 'er avledet, ikke målt');
  }
  if (u.negativ) {
    deler.push(`${u.negativ} varighet(er) er utelatt fordi tidspunktene står i `
      + 'omvendt rekkefølge');
  }
  if (sum.forsinket_meldt) {
    deler.push(`${sum.forsinket_meldt} stempling(er) ble meldt forsinket fra `
      + 'en enhet uten dekning');
  }
  if (!deler.length) {
    el.classList.add('d-none');
    el.textContent = '';
    return;
  }
  // textContent, ikke innerHTML: strengene er bygget av tall her, men
  // regelen skal ikke måtte vurderes på nytt neste gang noen legger til en
  // setning.
  el.textContent = deler.join('. ') + '.';
  el.classList.remove('d-none');
}

function _tegnGrafer(s) {
  const hastegrader = Object.keys(s.per_hastegrad);
  mkChart('chart-oppdrag-hastegrad', 'doughnut',
    hastegrader, hastegrader.map(h => s.per_hastegrad[h]),
    // Akutt/Haster/Vanlig i AMK-rekkefølge — fargene følger navnet, ikke
    // posisjonen, slik at en tom hastegrad ikke forskyver paletten.
    hastegrader.map(h => ({
      'Akutt': '#dc2626', 'Haster': '#f59e0b', 'Vanlig': '#16a34a',
    }[h] || '#64748b')));

  const statuser = s.status_naa.filter(r => r.antall > 0);
  mkChart('chart-oppdrag-status', 'bar',
    statuser.map(r => r.navn), statuser.map(r => r.antall), '#3b82f6');

  const enheter = Object.keys(s.per_enhet);
  mkChart('chart-oppdrag-enhet', 'bar',
    enheter, enheter.map(e => s.per_enhet[e]), '#0ea5e9');

  const problemer = Object.keys(s.per_problemstilling);
  mkChart('chart-oppdrag-problem', 'bar',
    problemer, problemer.map(p => s.per_problemstilling[p]), '#8b5cf6', true);

  const lokasjoner = Object.keys(s.per_lokasjon);
  mkChart('chart-oppdrag-lokasjon', 'bar',
    lokasjoner, lokasjoner.map(l => s.per_lokasjon[l]), '#14b8a6', true);

  mkChart('chart-oppdrag-ankomster', 'bar',
    s.ankomster.map(a => `${String(a.time).padStart(2, '0')}`),
    s.ankomster.map(a => a.antall), '#f59e0b');
}
