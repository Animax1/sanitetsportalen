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

// ── Arkivmodus ───────────────────────────────────────────────────────────
// Samme mekanikk som pasientarkivet i statistikk.js: `?kilde=oppdrag&arkiv=<id>`
// laster de frosne tallene og et banner, og fanerada skjules.
async function lastOppdragArkivStatistikk(id) {
  const [statsRes, metaRes] = await Promise.all([
    apiFetch(`/statistikk/api/kilde/oppdrag/arkiv/${id}/full-stats/`),
    apiFetch(`/oppdrag/api/arkiv/${id}/`),
  ]);
  if (!statsRes.ok) {
    const err = await statsRes.json().catch(() => ({}));
    alert(err.error || 'Kunne ikke hente statistikk for arkivet.');
    return false;
  }
  oppdragStats = await statsRes.json();
  const meta = metaRes.ok ? (await metaRes.json().catch(() => ({}))).data : null;
  const dato = meta?.importert_at ? meta.importert_at.slice(0, 16).replace('T', ' ') : '';
  arkivStatsMode = true;
  arkivStatsMeta = {
    id,
    tittel: meta?.tittel || `Arkiv ${id}`,
    importert_at: meta?.importert_at || '',
    meta_tekst: meta
      ? `(${meta.vakt_navn} — arkivert ${dato}, ${meta.antall_oppdrag} oppdrag)` : '',
  };
  _oppdaterArkivBanner();
  renderOppdragStats(oppdragStats);
  return true;
}

// ── Tabellbyggere ────────────────────────────────────────────────────────

// Rad i en varighetstabell. `sd` er {n, mean, median, min, max} — samme form
// som pasientstatistikkens, slik at fmtMin() kan brukes på begge.
function _sdRad(navn, sd) {
  // fmtMin() svarer '–' på null av seg selv, så ingen ternær her. Etter
  // §12.2 er tomme tidsledd et normaltilfelle — alle varighetene i en
  // kolonne kan være utelatt fordi sluttiden var avledet.
  // `p90` kom i pulje 7b; et arkiv frosset før det mangler nøkkelen, og
  // fmtMin(undefined) er '–'.
  return [navn, sd.n, fmtMin(sd.median), fmtMin(sd.p90), fmtMin(sd.mean),
          fmtMin(sd.min), fmtMin(sd.max)];
}

// Kolonnene står inline i begge byggerne, ikke som en delt konstant:
// testharnessen henter navngitte funksjoner, og en toppnivå-`const` er
// en ReferenceError der.

function mkOppdragTiderTabell(sum) {
  // Rekkefølgen følger oppdragets gang, ikke alfabetet: den som leser skal
  // kunne se hvor tiden går uten å sortere i hodet.
  const ledd = [
    ['Til utrykning', sum.ventetid],
    ['Utrykning → fremme', sum.utrykningstid],
    ['Responstid (til fremme)', sum.responstid],
    ['Behandlet på stedet', sum.tid_pa_stedet],
    ['Hele oppdraget', sum.oppdragstid],
  ];
  const rader = ledd.map(([navn, sd]) => _sdRad(navn, sd));
  return mkStatsTable(['Tidsledd', 'n', 'Median', 'p90', 'Snitt', 'Min', 'Maks'], rader);
}

function mkOppdragSdTabell(kolonnenavn, kart) {
  const rader = Object.entries(kart).map(([navn, sd]) => _sdRad(navn, sd));
  return mkStatsTable([kolonnenavn, 'n', 'Median', 'p90', 'Snitt', 'Min', 'Maks'], rader);
}

// ── Pulje 7b (21. sep. 2026) ─────────────────────────────────────────────
// Alle byggerne her sender rader til mkStatsTable(), som escaper hver celle
// med cellHtml(). Cellene bygges med `+`, ikke mal-strenger: teksten er
// tall fra fmtMin() og navn fra basen, og begge går gjennom escapingen i
// tabellen — men en `${...}` i en bygger skal kunne leses som «escapet
// her», og det er den ikke.

// «median / p90 (n)» — ett tidsledd i én celle.
function _medianP90(sd) {
  if (!sd || !sd.n) return '–';
  return fmtMin(sd.median) + ' / ' + fmtMin(sd.p90) + ' (' + sd.n + ')';
}

function mkVentetidTabell(vd) {
  const rader = Object.entries(vd.per_hastegrad).map(([navn, ledd]) => [
    navn, _medianP90(ledd.ko_ventetid), _medianP90(ledd.reaksjonstid),
  ]);
  return mkStatsTable(
    ['Hastegrad', 'KO-ventetid median / p90 (n)', 'Reaksjonstid median / p90 (n)'],
    rader);
}

function mkAldriRykketTabell(liste) {
  const rader = liste.map(r => [
    '#' + r.oppdragsnummer + ' ' + r.hastegrad + ' · ' + r.problemstilling,
    r.enhet, fmtMin(r.sto_i), r.endte,
  ]);
  return mkStatsTable(['Oppdrag', 'Enhet', 'Sto i', 'Endte som'], rader);
}

// Krysstabellen KO × bilen. Egen markup fordi cellene farges: grønn på
// diagonalen (enige), rød der bilen fant det mer alvorlig, gul der hun fant
// det mindre. Alt som settes inn går gjennom escHtmlValue().
function mkKonkordansTabell(k) {
  if (!k || !k.vurderte && !k.rader.some(r => Object.values(k.antall[r] || {}).some(v => v))) {
    return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  }
  const rang = { 'Akutt': 0, 'Haster': 1, 'Vanlig': 2, 'rod': 0, 'gul': 1, 'gronn': 2 };
  let html = '<table class="stats-table"><thead><tr><th>KO ↓ · bilen →</th>';
  k.kolonner.forEach(([, navn]) => { html += `<th>${escHtmlValue(navn)}</th>`; });
  html += '<th>n</th></tr></thead><tbody>';
  k.rader.forEach(hastegrad => {
    const rad = k.antall[hastegrad] || {};
    const sum = Object.values(rad).reduce((a, b) => a + b, 0);
    html += `<tr><td>${escHtmlValue(hastegrad)}</td>`;
    k.kolonner.forEach(([kode]) => {
      const val = rad[kode] || 0;
      let cls = '';
      if (val > 0 && kode in rang) {
        const diff = rang[kode] - rang[hastegrad];
        cls = diff === 0 ? 'heat-lo' : (diff < 0 ? 'heat-hi' : 'heat-mid');
      } else if (val === 0) {
        cls = 'heat-zero';
      }
      html += `<td class="${cls}">${escHtmlValue(val)}</td>`;
    });
    html += `<td class="xt-total">${escHtmlValue(sum)}</td></tr>`;
  });
  return html + '</tbody></table>';
}

function mkAvreistTabell(a) {
  const rader = Object.entries(a.per_sted)
    .filter(([, antall]) => antall > 0)
    .map(([sted, antall]) => {
      const perH = a.per_sted_hastegrad[sted] || {};
      const fordeling = Object.entries(perH).map(([h, n]) => h + ' ' + n).join(' · ');
      return [sted, antall, fordeling];
    });
  return mkStatsTable(['Sted', 'n', 'Per hastegrad'], rader);
}

function mkAnnetStedTabell(liste) {
  if (!liste.length) return '';
  const rader = liste.map(r => ['#' + r.oppdragsnummer, r.enhet, r.tekst]);
  return mkStatsTable(['Oppdrag', 'Enhet', 'Annet sted'], rader);
}

function mkUtfallTabell(u) {
  const rader = Object.entries(u).map(([problem, t]) => [
    problem, t.behandlet, t.transportert, t.uten, t.behandlet + t.transportert + t.uten,
  ]);
  return mkStatsTable(
    ['Problemstilling', 'Behandlet / utført', 'Transportert', 'Verken', 'n'],
    rader);
}

function mkHendelserTabell(h) {
  const typer = h.typer.map(([kode]) => kode);
  const rader = [['Alle', ...typer.map(t => h.per_type[t] || 0)]];
  Object.entries(h.per_enhet).forEach(([enhet, per]) => {
    rader.push([enhet, ...typer.map(t => per[t] || 0)]);
  });
  if (rader.length === 1 && rader[0].slice(1).every(v => !v)) {
    return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  }
  // Korte overskrifter — verdimengdens egne («Rykket ut på et annet
  // oppdrag») er skrevet for tidslinja, ikke for en kolonne.
  const korte = { tatt_av: 'Tatt av', rykket_videre: 'Rykket videre',
                  avbrutt: 'Avbrutt', avventer: 'Avventet' };
  return mkStatsTable(['Enhet', ...h.typer.map(([kode, navn]) => korte[kode] || navn)], rader);
}

function _tegn7b(s) {
  const vd = s.ventetid_delt;
  if (!vd) return;   // arkiv frosset før pulje 7b

  const hastegrader = Object.keys(vd.per_hastegrad);
  mkStabletChart('chart-oppdrag-ventetid', hastegrader, [
    { label: 'KO-ventetid', backgroundColor: '#f59e0b',
      data: hastegrader.map(h => vd.per_hastegrad[h].ko_ventetid.median ?? 0) },
    { label: 'Reaksjonstid', backgroundColor: '#3b82f6',
      data: hastegrader.map(h => vd.per_hastegrad[h].reaksjonstid.median ?? 0) },
  ], { horisontal: true });

  document.getElementById('tbl-oppdrag-ventetid').innerHTML = mkVentetidTabell(vd);
  const fot = [];
  if (vd.reaksjonstid_passiv.n) {
    fot.push(`Passiv vakt holdt utenfor reaksjonstida: ${vd.reaksjonstid_passiv.n} `
      + `innsats(er), median ${fmtMin(vd.reaksjonstid_passiv.median)}`);
  }
  if (vd.uten_ressurs_etter_avgang) {
    fot.push(`${vd.uten_ressurs_etter_avgang} oppdrag ble stående uten ressurs etter at `
      + 'en enhet dro fra det');
  }
  document.getElementById('oppdrag-ventetid-fot').textContent =
    fot.length ? fot.join('. ') + '.' : '';

  document.getElementById('tbl-oppdrag-reaksjon-enhet').innerHTML =
    mkOppdragSdTabell('Enhet', vd.reaksjonstid_per_enhet);
  document.getElementById('tbl-oppdrag-aldri-rykket').innerHTML =
    mkAldriRykketTabell(s.aldri_rykket_ut);
  document.getElementById('oppdrag-aldri-rykket-fot').textContent =
    s.aldri_rykket_ut.length
      ? `${s.aldri_rykket_ut.length} av ${s.summary.enhetsinnsatser} innsatser. `
        + 'Hver er en enhet som var bundet uten å gjøre noe.'
      : '';

  mkStabletChart('chart-oppdrag-koe', s.koe.map(k => String(k.time).padStart(2, '0')), [
    { label: 'Uten ressurs', backgroundColor: '#f59e0b', data: s.koe.map(k => k.uten_ressurs) },
    { label: 'Tildelt, venter', backgroundColor: '#3b82f6', data: s.koe.map(k => k.tildelt_venter) },
  ], { etiketter: s.koe.map(k => (k.uten_ressurs + k.tildelt_venter) ? fmtMin(k.lengste) : '') });

  const lengste = s.lengste_uten_ressurs;
  document.getElementById('okpi-lengste-uten').textContent =
    lengste ? fmtMin(lengste.minutter) : '–';
  document.getElementById('okpi-lengste-uten-sub').textContent = lengste
    ? `#${lengste.oppdragsnummer} ${lengste.hastegrad}, fra ${klokke(lengste.fra)}`
      + (lengste.paagaar ? ' (står fortsatt)' : '')
    : 'ingen ventet';
  const flest = s.flest_i_koe;
  document.getElementById('okpi-flest-koe').textContent = flest ? String(flest.antall) : '0';
  document.getElementById('okpi-flest-koe-sub').textContent =
    flest ? `kl. ${String(flest.time).padStart(2, '0')}–${String((flest.time + 1) % 24).padStart(2, '0')}` : '';

  const k = s.konkordans;
  document.getElementById('tbl-oppdrag-konkordans').innerHTML = mkKonkordansTabell(k);
  document.getElementById('oppdrag-konkordans-fot').textContent = k.vurderte
    ? `Diagonalen er enighet: ${k.enige} av ${k.vurderte} vurderte `
      + `(${Math.round(k.enige / k.vurderte * 100)} %). Rødt: bilen fant det mer alvorlig `
      + `enn meldt — ${k.bilen_hoyere}. Gult: mindre — ${k.bilen_lavere}. `
      + 'To blikk fra to steder, ikke en karakter på noen.'
    : 'Ingen oppdrag er grovsortert av bilen ennå.';

  document.getElementById('tbl-oppdrag-avreist').innerHTML = mkAvreistTabell(s.avreist_til);
  document.getElementById('tbl-oppdrag-annet-sted').innerHTML =
    mkAnnetStedTabell(s.avreist_til.annet_tekster);
  document.getElementById('tbl-oppdrag-utfall').innerHTML =
    mkUtfallTabell(s.utfall_per_problemstilling);
  document.getElementById('tbl-oppdrag-hendelser').innerHTML =
    mkHendelserTabell(s.enhetshendelser);
}

// ── Rendering ────────────────────────────────────────────────────────────
function renderOppdragStats(s) {
  if (!s || !s.summary) return;
  const sum = s.summary;

  // Med flere biler på ett oppdrag er radene flere enn oppdragene. Tallet
  // er oppdragene; radene står som undertekst — «(15 enhetsinnsatser)» i
  // selve tallet fikk ikke plass i boksen (André, 12. sep. 2026).
  document.getElementById('okpi-total').textContent = String(sum.total);
  const sub = document.getElementById('okpi-sub');
  if (sub) {
    sub.textContent = (sum.enhetsinnsatser != null && sum.enhetsinnsatser !== sum.total)
      ? `${sum.enhetsinnsatser} enhetsinnsatser` : '';
  }
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
  _tegn7b(s);
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
    // Rekkefølgen kommer fra serveren (AMK-rekkefølge, alle fem — C8, 21.
    // sep. 2026); fargene følger navnet, ikke posisjonen, slik at en tom
    // hastegrad ikke forskyver paletten. Grått er for en verdi ingen av oss
    // kjenner — data fra før en hastegrad ble omdøpt.
    hastegrader.map(h => ({
      'Akutt': '#dc2626', 'Haster': '#f59e0b', 'Vanlig': '#16a34a', 'Drift': '#2563eb',
      'Plassering': '#8b5cf6',
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
