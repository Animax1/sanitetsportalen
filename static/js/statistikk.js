// ════════════════════════════════════════════════════════
// STATISTIKK — rendering for /statistikk/
//
// Skilt ut fra patients-stats.js da statistikk ble egen modul. Den fila
// blandet tre ting: statistikkrendering, arkivadministrasjon og
// admin-handlinger i pasientmodulen. Kun det første hører hjemme her; resten
// ligger i patients-admin.js.
//
// Tilgangen håndheves av serveren (@stats_required på både siden og
// endepunktet). Den gamle rollesjekken i loadStats() er derfor ikke med:
// den duplisert gaten, og en duplisert gate blir feil den dagen gaten endres.
// ════════════════════════════════════════════════════════

// ── Chart.js-tema ────────────────────────────────────────────────────────
// Lå i patients-utils.js, men brukes kun herfra. Pasientsiden laster ikke
// lenger Chart.js i det hele tatt.
let charts = {};
const chartDarkText = '#f8fafc';
const chartMainText = '#e5e7eb';
const chartMutedText = '#cbd5e1';
const chartSoftText = '#94a3b8';
const chartGrid = 'rgba(148, 163, 184, 0.18)';
const chartGridStrong = 'rgba(148, 163, 184, 0.28)';
const chartTooltipBg = '#0b1220';
const chartCanvasBorder = '#111827';

Chart.defaults.color = chartMutedText;
Chart.defaults.borderColor = chartGrid;
Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
Chart.defaults.font.size = 11;

// ── Tilstand ─────────────────────────────────────────────────────────────
let activeStatTab = 'oversikt';
let fullStats = null;
let arkivStatsMode = false;
let arkivStatsMeta = null;

// ════════════════════════════════════════════════════════
// STATISTICS – CHART HELPER
// ════════════════════════════════════════════════════════
function mkChart(id, type, labels, data, colors, horiz = false) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (charts[id]) {
    charts[id].destroy();
    delete charts[id];
  }

  if (!labels || !labels.length) return;

  const isDoughnut = type === 'doughnut';
  const isBar = type === 'bar';
  const isHorizontal = !!horiz;

  charts[id] = new Chart(ctx, {
    type,
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderColor: isDoughnut ? chartCanvasBorder : colors,
        borderWidth: isDoughnut ? 2 : 0,
        borderRadius: isBar ? 6 : 0,
        maxBarThickness: isHorizontal ? 24 : 36,
        hoverBorderWidth: isDoughnut ? 2 : 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 250 },
      layout: {
        padding: {
          top: 4,
          right: isDoughnut ? 8 : 4,
          bottom: 4,
          left: isHorizontal ? 4 : 0
        }
      },
      indexAxis: isHorizontal ? 'y' : 'x',
      plugins: {
        legend: {
          display: isDoughnut,
          position: 'right',
          labels: {
            color: chartMutedText,
            usePointStyle: true,
            pointStyle: 'circle',
            boxWidth: 10,
            boxHeight: 10,
            padding: 10,
            font: { size: 11, weight: '600' }
          }
        },
        tooltip: {
          backgroundColor: chartTooltipBg,
          titleColor: chartDarkText,
          bodyColor: chartMainText,
          borderColor: chartGridStrong,
          borderWidth: 1,
          padding: 10,
          displayColors: true,
          titleFont: { size: 12, weight: '700' },
          bodyFont: { size: 11 }
        }
      },
      scales: isBar ? {
        x: {
          beginAtZero: true,
          grid: {
            color: isHorizontal ? chartGrid : 'rgba(148, 163, 184, 0.10)',
            drawBorder: false
          },
          border: { color: chartGridStrong },
          ticks: { color: chartMutedText, font: { size: 11 }, precision: 0 }
        },
        y: {
          grid: {
            display: !isHorizontal,
            color: chartGrid,
            drawBorder: false
          },
          border: { color: chartGridStrong },
          ticks: {
            color: isHorizontal ? chartDarkText : chartMutedText,
            font: {
              size: isHorizontal ? 12 : 11,
              weight: isHorizontal ? '600' : '400'
            }
          }
        }
      } : undefined
    }
  });
}

// ════════════════════════════════════════════════════════
// STATISTICS – TABLE HELPERS
// ════════════════════════════════════════════════════════
function mkStatsTable(headers, rows, opts={}) {
  if (!rows.length) return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  const sigCol = opts.sigCol ?? -1;
  let html = '<table class="stats-table"><thead><tr>';
  headers.forEach(h => { html += `<th>${escHtmlValue(h)}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    row.forEach((cell, i) => {
      // cellHtml() escaper feltverdier og slipper gjennom trustedHtml()-celler.
      const s = cellHtml(cell);
      let cls = '';
      if (i === sigCol) cls = s.includes('✓') || s.includes('&#10004;') ? 'sig-yes' : 'sig-no';
      html += `<td class="${cls}">${s}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  return html;
}

function mkCrosstab(ctData) {
  const { counts, rows, cols } = ctData;
  if (!rows || !rows.length) return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  // Rad- og kolonnenøklene er pasientdata (problemstilling, transport,
  // grovsortering, utskrevet_til). De escapes ved utskrift, men brukes rå
  // som oppslagsnøkler i `counts`.
  let html = '<table class="stats-table"><thead><tr><th></th>';
  cols.forEach(c => { html += `<th>${escHtmlValue(c)}</th>`; });
  html += '<th>Total</th></tr></thead><tbody>';
  rows.forEach(r => {
    const rowData = counts[r] || {};
    const rowTotal = cols.reduce((s, c) => s + (rowData[c] || 0), 0);
    if (rowTotal === 0) return;
    html += `<tr><td>${escHtmlValue(r)}</td>`;
    cols.forEach(c => {
      const val = rowData[c] || 0;
      const pct = rowTotal > 0 ? val / rowTotal * 100 : 0;
      let cls = '';
      if (val === 0) cls = 'heat-zero';
      else if (pct >= 50) cls = 'heat-hi';
      else if (pct >= 25) cls = 'heat-mid';
      else cls = 'heat-lo';
      const pctStr = rowTotal > 0 ? `<br><small style="font-weight:400;opacity:0.75">${Math.round(pct)}%</small>` : '';
      html += `<td class="${cls}">${escHtmlValue(val)}${pctStr}</td>`;
    });
    html += `<td style="font-weight:700;color:#1e293b">${rowTotal}</td></tr>`;
  });
  html += '</tbody></table>';
  return html;
}

function mkObsTable(rowData) {
  if (!rowData.length) return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  let html = '<table class="stats-table"><thead><tr><th>Gruppe</th><th>N</th><th>Med obs</th><th>Andel</th><th>Snitt obs-tid</th></tr></thead><tbody>';
  rowData.forEach(row => {
    // Number() fordi pct går inn i et style-attributt lenger ned.
    const pct = Number(row.pct) || 0;
    let barColor = pct >= 70 ? '#ef4444' : pct >= 30 ? '#eab308' : '#22c55e';
    html += `<tr>
      <td>${escHtmlValue(row.name)}</td>
      <td>${escHtmlValue(row.n)}</td>
      <td>${escHtmlValue(row.med_obs)}</td>
      <td>
        <strong>${pct.toFixed(1)}%</strong>
        <div class="obs-pct-bar"><div class="obs-pct-fill" style="width:${Math.min(100,pct)}%;background:${barColor}"></div></div>
      </td>
      <td>${row.avg != null ? fmtMin(row.avg) : '–'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  return html;
}

function fmtChi2Badge(chi2, elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!chi2) { el.className = 'chi2-badge chi2-nd'; el.textContent = 'Ingen data'; return; }
  const pStr = chi2.p < 0.001 ? 'p<0,001' : `p=${chi2.p.toFixed(3).replace('.',',')}`;
  if (chi2.sig) {
    el.className = 'chi2-badge chi2-sig';
    el.textContent = `✓ Signifikant (χ²=${chi2.chi2.toFixed(1)}, ${pStr})`;
  } else {
    el.className = 'chi2-badge chi2-ns';
    el.textContent = `✗ Ikke sign. (χ²=${chi2.chi2.toFixed(1)}, ${pStr})`;
  }
}

function fmtChi2Inline(chi2) {
  if (!chi2) return '<span class="chi2-badge chi2-nd">Ingen data</span>';
  const pStr = chi2.p < 0.001 ? 'p<0,001' : `p=${chi2.p.toFixed(3).replace('.',',')}`;
  if (chi2.sig) {
    return `<span class="chi2-badge chi2-sig">✓ Sign. (χ²=${chi2.chi2.toFixed(1)}, ${pStr})</span>`;
  }
  return `<span class="chi2-badge chi2-ns">✗ N.S. (χ²=${chi2.chi2.toFixed(1)}, ${pStr})</span>`;
}

// ════════════════════════════════════════════════════════
// STATISTICS – MAIN LOADER  (calls /api/full-stats/)
// ════════════════════════════════════════════════════════
async function loadStats() {
  const role = (window.USER_ROLE || 'read_only').toLowerCase();
  if (role !== 'admin' && role !== 'lead' && role !== 'lead_view') {
    return;
  }
  if (arkivStatsMode) {
    renderStatTab(activeStatTab);
    _oppdaterArkivBanner();
    return;
  }
  try {
    const res = await fetch('/pasienter/api/full-stats/');
    if (!res.ok) {
      // 403 = ingen statistikktilgang. 429 = hentet for ofte (S3).
      // Begge skal la forrige visning bli stående: alternativet er å
      // legge feilkroppen i `fullStats` og rendre tomme grafer over den.
      console.warn('Statistikk ikke hentet, status', res.status);
      return;
    }
    fullStats = await res.json();
  } catch(e) {
    console.error('Statistikk feil:', e);
    return;
  }
  _oppdaterArkivBanner();
  renderStatTab(activeStatTab);
}

function _oppdaterArkivBanner() {
  const banner = document.getElementById('arkiv-stats-banner');
  if (!banner) return;
  if (arkivStatsMode && arkivStatsMeta) {
    document.getElementById('arkiv-stats-banner-tittel').textContent =
      arkivStatsMeta.tittel || '';
    const datoStr = arkivStatsMeta.importert_at
      ? arkivStatsMeta.importert_at.slice(0, 16).replace('T', ' ')
      : '';
    const arr = arkivStatsMeta.arrangement_navn || '';
    const ant = arkivStatsMeta.antall_pasienter ?? '?';
    document.getElementById('arkiv-stats-banner-meta').textContent =
      `(${arr} — arkivert ${datoStr}, ${ant} pasienter)`;
    banner.classList.remove('d-none');
  } else {
    banner.classList.add('d-none');
  }
}

function exitArkivStatsMode() {
  arkivStatsMode = false;
  arkivStatsMeta = null;
  fullStats = null;
  _oppdaterArkivBanner();
  loadStats();
}

function renderStatTab(tab) {
  document.querySelectorAll('.stab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('stab-' + tab)?.classList.add('active');
  document.querySelectorAll('.stats-subbtn').forEach(b => {
    b.classList.toggle('active', b.dataset.stab === tab);
  });

  if (!fullStats || !fullStats.summary) return;
  const s = fullStats;

  if (tab === 'oversikt')           renderOversikt(s);
  else if (tab === 'tidsanalyse')   renderTidsanalyse(s);
  else if (tab === 'krysstabeller') renderKrysstabeller(s);
  else if (tab === 'obspost')       renderObspost(s);
  else if (tab === 'tester')        renderTester(s);
}

// ════════════════════════════════════════════════════════
// STATISTICS – OVERSIKT
// ════════════════════════════════════════════════════════
function renderOversikt(s) {
  const sum = s.summary;
  document.getElementById('kpi-total').textContent     = sum.total;
  document.getElementById('kpi-tilstede').textContent  = sum.tilstede;
  document.getElementById('kpi-rod').textContent       = sum.rod;
  document.getElementById('kpi-gul').textContent       = sum.gul;
  document.getElementById('kpi-gronn').textContent     = sum.gronn;
  document.getElementById('kpi-utskrevet').textContent = sum.utskrevet;

  const wt = sum.wait_time,  ot = sum.obs_time,  tt = sum.total_time;
  document.getElementById('kpi-wait-both').textContent =
    (wt && wt.n) ? `${fmtMin(wt.mean)} / ${fmtMin(wt.median)}` : '–';
  document.getElementById('kpi-obs-both').textContent =
    (ot && ot.n) ? `${fmtMin(ot.mean)} / ${fmtMin(ot.median)}` : '–';
  document.getElementById('kpi-total-both').textContent =
    (tt && tt.n) ? `${fmtMin(tt.mean)} / ${fmtMin(tt.median)}` : '–';

  const obsCnt = sum.total_obs_count || 0;
  const obsPct = sum.total > 0 ? (obsCnt / sum.total * 100).toFixed(1) : 0;
  document.getElementById('kpi-obs-pct').textContent = `${obsPct}%`;
  document.getElementById('kpi-obs-sub').textContent = `${obsCnt} av ${sum.total} pasienter`;

  const notTriaged = Math.max(0, sum.total - sum.rod - sum.gul - sum.gronn);
  const tLabels = ['Rød','Gul','Grønn'];
  const tData   = [sum.rod, sum.gul, sum.gronn];
  const tColors = ['#ef4444','#eab308','#22c55e'];
  if (notTriaged > 0) { tLabels.push('Ukjent'); tData.push(notTriaged); tColors.push('#cbd5e1'); }
  mkChart('chart-triage','doughnut', tLabels, tData, tColors);

  const tk = Object.keys(s.transport_counts);
  mkChart('chart-transport','doughnut', tk, tk.map(k=>s.transport_counts[k]),
    ['#3b82f6','#8b5cf6','#f59e0b','#10b981','#ef4444','#94a3b8']);

  const uk = Object.keys(s.utfall_counts);
  mkChart('chart-utfall','doughnut', uk, uk.map(k=>s.utfall_counts[k]),
    ['#22c55e','#64748b','#3b82f6','#ef4444','#f59e0b','#a855f7']);

  const probs = Object.entries(s.prob_counts)
    .sort((a,b) => b[1]-a[1]).slice(0,10);
  mkChart('chart-problems','bar',
    probs.map(([k]) => k.length>22 ? k.slice(0,21)+'…' : k),
    probs.map(([,v]) => v),
    Array(probs.length).fill('#6366f1'), true);

  const ak = Object.keys(s.arrivals);
  mkChart('chart-arrivals','bar', ak, ak.map(k=>s.arrivals[k]),
    Array(ak.length).fill('#3b82f6'));
}

// ════════════════════════════════════════════════════════
// STATISTICS – TIDSANALYSE
// ════════════════════════════════════════════════════════
function renderTidsanalyse(s) {
  const triageOrder = ['Rød','Gul','Grønn'];
  const triageColors = ['#ef4444','#eab308','#22c55e'];
  const tpt = s.time_per_triage;
  const tKeys = triageOrder.filter(t => tpt[t] && tpt[t].n > 0);

  mkChart('chart-time-triage','bar', tKeys,
    tKeys.map(t => tpt[t].mean || 0),
    tKeys.map(t => triageColors[triageOrder.indexOf(t)]),
    true);

  document.getElementById('tbl-time-triage').innerHTML = mkStatsTable(
    ['Grovsortering','N','Snitt','Median'],
    tKeys.map(t => [t, tpt[t].n, fmtMin(tpt[t].mean), fmtMin(tpt[t].median)])
  );

  const tptr = s.time_per_transport;
  const tpKeys = Object.keys(tptr).filter(k => tptr[k].n > 0);
  mkChart('chart-time-transport','bar', tpKeys,
    tpKeys.map(k => tptr[k].mean || 0),
    ['#3b82f6','#8b5cf6','#f59e0b','#10b981','#ef4444','#94a3b8'],
    true);
  document.getElementById('tbl-time-transport').innerHTML = mkStatsTable(
    ['Transport','N','Snitt','Median'],
    tpKeys.map(k => [k, tptr[k].n, fmtMin(tptr[k].mean), fmtMin(tptr[k].median)])
  );

  const tpp = s.time_per_problem;
  const ppKeys = Object.keys(tpp).filter(k => tpp[k].n > 0);
  mkChart('chart-time-problem','bar',
    ppKeys.map(k => k.length>24 ? k.slice(0,23)+'…' : k),
    ppKeys.map(k => tpp[k].mean || 0),
    Array(ppKeys.length).fill('#6366f1'),
    true);
  document.getElementById('tbl-time-problem').innerHTML = mkStatsTable(
    ['Problemstilling','N','Snitt','Median','Min','Maks'],
    ppKeys.map(k => [
      k, tpp[k].n,
      fmtMin(tpp[k].mean), fmtMin(tpp[k].median),
      fmtMin(tpp[k].min),  fmtMin(tpp[k].max)
    ])
  );
}

// ════════════════════════════════════════════════════════
// STATISTICS – KRYSSTABELLER
// ════════════════════════════════════════════════════════
function renderKrysstabeller(s) {
  document.getElementById('xt-prob-triage').innerHTML =
    mkCrosstab(s.crosstab_prob_triage);
  fmtChi2Badge(s.crosstab_prob_triage.chi2, 'chi2-badge-prob-triage');

  document.getElementById('xt-triage-transport').innerHTML =
    mkCrosstab(s.crosstab_triage_transport);
  fmtChi2Badge(s.crosstab_triage_transport.chi2, 'chi2-badge-triage-transport');

  document.getElementById('xt-prob-utfall').innerHTML =
    mkCrosstab(s.crosstab_prob_utfall);
  fmtChi2Badge(s.crosstab_prob_utfall.chi2, 'chi2-badge-prob-utfall');
}

// ════════════════════════════════════════════════════════
// STATISTICS – OBSPOST
// ════════════════════════════════════════════════════════
function renderObspost(s) {
  const sum = s.summary;
  const obsCnt = sum.total_obs_count || 0;
  const obsPct = sum.total > 0 ? (obsCnt / sum.total * 100).toFixed(1) : 0;
  document.getElementById('obs-total-n').textContent        = obsCnt;
  document.getElementById('obs-total-pct-text').textContent = `${obsPct}% av alle pasienter`;

  const ot = sum.obs_time;
  document.getElementById('obs-avg-time').textContent = (ot && ot.n) ? fmtMin(ot.mean)   : '–';
  document.getElementById('obs-med-time').textContent = (ot && ot.n) ? fmtMin(ot.median) : '–';
  document.getElementById('obs-chi2-display').innerHTML = fmtChi2Inline(
    s.chi2_table?.find(t => t.test.includes('Obspost'))?.result
  );

  const opt = s.obs_per_triage;
  const triageOrder = ['Rød','Gul','Grønn'];
  const tRows = triageOrder.filter(t => opt[t]).map(t => ({
    name: t, n: opt[t].n, med_obs: opt[t].med_obs, pct: opt[t].pct, avg: opt[t].avg_obs_min
  }));
  document.getElementById('tbl-obs-triage').innerHTML = mkObsTable(tRows);

  const opp = s.obs_per_problem;
  const pRows = Object.entries(opp)
    .filter(([, v]) => v.med_obs > 0)
    .sort((a, b) => b[1].pct - a[1].pct)
    .map(([k, v]) => ({ name: k, n: v.n, med_obs: v.med_obs, pct: v.pct, avg: v.avg_obs_min }));
  document.getElementById('tbl-obs-problem').innerHTML = mkObsTable(pRows);
}

// ════════════════════════════════════════════════════════
// STATISTICS – STATISTISKE TESTER
// ════════════════════════════════════════════════════════
function renderTester(s) {
  const chi2Rows = s.chi2_table.map(row => {
    const r = row.result;
    if (!r) return [row.test, '–', '–', '–', '–'];
    const pStr = r.p < 0.001 ? '<0,001' : r.p.toFixed(4).replace('.',',');
    return [row.test, r.chi2.toFixed(2), r.dof, pStr,
      trustedHtml(r.sig
        ? '<span style="color:#22c55e;font-weight:700;">&#10004; Ja</span>'
        : '<span style="color:#94a3b8;">&#10007; Nei</span>')
    ];
  });
  document.getElementById('tbl-chi2').innerHTML = mkStatsTable(
    ['Test','χ²','df','p-verdi','Signifikant'],
    chi2Rows, { sigCol: 4 }
  );

  const kwRows = [
    ['Total tid mellom grovsorteringer', s.kw_triage],
    ['Total tid mellom problemstillinger', s.kw_problem],
    ['Total tid mellom transportmåter', s.kw_transport],
  ].map(([name, r]) => {
    if (!r) return [name, '–', '–', '–'];
    const pStr = r.p < 0.001 ? '<0,001' : r.p.toFixed(4).replace('.',',');
    return [name, r.H.toFixed(2), pStr,
      trustedHtml(r.sig
        ? '<span style="color:#22c55e;font-weight:700;">&#10004; Ja</span>'
        : '<span style="color:#94a3b8;">&#10007; Nei</span>')
    ];
  });
  document.getElementById('tbl-kw').innerHTML = mkStatsTable(
    ['Test','H-statistikk','p-verdi','Signifikant'],
    kwRows, { sigCol: 3 }
  );

  document.getElementById('tbl-interpretation').innerHTML = mkInterpretation(s);
}

function mkInterpretation(s) {
  const sum = s.summary;
  if (!sum || sum.total === 0) {
    return '<p class="text-muted small mb-0">Ingen data registrert ennå.</p>';
  }

  const obsPct = sum.total > 0 ? (sum.total_obs_count / sum.total * 100).toFixed(1) : 0;
  const tt = sum.total_time, ot = sum.obs_time;

  const sigTests = (s.chi2_table || []).filter(t => t.result?.sig).map(t => escHtmlValue(t.test));
  const nsTests  = (s.chi2_table || []).filter(t => t.result && !t.result.sig).map(t => escHtmlValue(t.test));

  const kwSig = [
    s.kw_triage?.sig    ? 'Tid etter triage'      : null,
    s.kw_problem?.sig   ? 'Tid etter problem'     : null,
    s.kw_transport?.sig ? 'Tid etter transport'   : null,
  ].filter(Boolean);

  let html = '';

  html += `<p class="mb-1 small" style="line-height:1.5; color:#e2e8f0;">
    <strong style="color:#ffffff;">Datagrunnlag:</strong>
    ${escHtmlValue(sum.total)} pasienter registrert, ${escHtmlValue(sum.utskrevet)} utskrevet.
  </p>`;

  if (tt && tt.n > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5; color:#e2e8f0;">
      <strong style="color:#ffffff;">Total tid:</strong>
      Gjennomsnitt ${fmtMin(tt.mean)}, median ${fmtMin(tt.median)} (n=${escHtmlValue(tt.n)}).
    </p>`;
  }

  if (ot && ot.n > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5; color:#e2e8f0;">
      <strong style="color:#ffffff;">Obspost:</strong>
      ${escHtmlValue(sum.total_obs_count)} pasienter (${escHtmlValue(obsPct)}%) på obspost. Snitt ${fmtMin(ot.mean)}, median ${fmtMin(ot.median)}.
    </p>`;
  }

  if (sigTests.length > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5;">
      <i class="bi bi-check2-circle me-1" style="color:#22c55e;"></i>
      <strong style="color:#22c55e;">Signifikante sammenhenger:</strong>
      <span style="color:#e2e8f0;">${sigTests.join(', ')}.</span>
    </p>`;
  }

  if (nsTests.length > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5;">
      <i class="bi bi-dash-circle me-1" style="color:#94a3b8;"></i>
      <strong style="color:#cbd5e1;">Ikke signifikant:</strong>
      <span style="color:#cbd5e1;">${nsTests.join(', ')}.</span>
    </p>`;
  }

  if (kwSig.length > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5;">
      <i class="bi bi-check2-circle me-1" style="color:#22c55e;"></i>
      <strong style="color:#22c55e;">Kruskal-Wallis:</strong>
      <span style="color:#e2e8f0;">${kwSig.join(', ')}.</span>
    </p>`;
  }

  return html;
}
// TAB NAVIGATION
// ════════════════════════════════════════════════════════

// Stats sub-tab navigation
document.querySelectorAll('.stats-subbtn').forEach(btn => {
  btn.addEventListener('click', () => {
    activeStatTab = btn.dataset.stab;
    if (fullStats) {
      renderStatTab(activeStatTab);
    } else {
      loadStats();
    }
  });
});

// ════════════════════════════════════════════════════════
// OPPSTART
//
// Arkiv-modus kommer nå fra URL-en (?arkiv=<id>) i stedet for fra en
// modal-knapp i pasientmodulen. Siden er sin egen — den kan lastes, deles og
// oppdateres — så tilstanden må ligge et sted som overlever en refresh.
// ════════════════════════════════════════════════════════

async function _lastArkivStatistikk(id) {
  // To kall: tallene fra statistikk-appen, metadataene til banneret fra
  // pasientmodulen som eier arkivet. Begge krever arkivrollen.
  const [statsRes, metaRes] = await Promise.all([
    apiFetch(`/statistikk/api/arkiv/${id}/full-stats/`),
    apiFetch(`/pasienter/api/innstillinger/arkiv/${id}/`),
  ]);

  if (!statsRes.ok) {
    const err = await statsRes.json().catch(() => ({}));
    alert(err.error || 'Kunne ikke hente statistikk for arkivet.');
    return false;
  }

  fullStats = await statsRes.json();
  arkivStatsMode = true;

  // Banneret er pynt. Feiler metadata-kallet, viser vi tallene uansett —
  // alternativet ville vært å skjule statistikk fordi en overskrift manglet.
  const meta = metaRes.ok ? await metaRes.json().catch(() => null) : null;
  arkivStatsMeta = {
    id: id,
    tittel: meta?.tittel || `Arkiv ${id}`,
    arrangement_navn: meta?.arrangement_navn || '',
    importert_at: meta?.importert_at || '',
    antall_pasienter: meta?.antall_pasienter ?? '?',
  };
  return true;
}

document.addEventListener('DOMContentLoaded', async () => {
  const arkivId = new URLSearchParams(window.location.search).get('arkiv');
  if (arkivId && /^\d+$/.test(arkivId)) {
    if (await _lastArkivStatistikk(arkivId)) {
      _oppdaterArkivBanner();
      renderStatTab(activeStatTab);
      return;
    }
  }
  loadStats();
});
