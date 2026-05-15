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
  headers.forEach(h => { html += `<th>${h}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    row.forEach((cell, i) => {
      const s = String(cell);
      let cls = '';
      if (i === sigCol) cls = s.includes('✓') || s.includes('&#10004;') ? 'sig-yes' : 'sig-no';
      html += `<td class="${cls}">${cell}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  return html;
}

function mkCrosstab(ctData) {
  const { counts, rows, cols } = ctData;
  if (!rows || !rows.length) return '<p class="text-muted small p-2 mb-0">Ingen data</p>';
  let html = '<table class="stats-table"><thead><tr><th></th>';
  cols.forEach(c => { html += `<th>${c}</th>`; });
  html += '<th>Total</th></tr></thead><tbody>';
  rows.forEach(r => {
    const rowData = counts[r] || {};
    const rowTotal = cols.reduce((s, c) => s + (rowData[c] || 0), 0);
    if (rowTotal === 0) return;
    html += `<tr><td>${r}</td>`;
    cols.forEach(c => {
      const val = rowData[c] || 0;
      const pct = rowTotal > 0 ? val / rowTotal * 100 : 0;
      let cls = '';
      if (val === 0) cls = 'heat-zero';
      else if (pct >= 50) cls = 'heat-hi';
      else if (pct >= 25) cls = 'heat-mid';
      else cls = 'heat-lo';
      const pctStr = rowTotal > 0 ? `<br><small style="font-weight:400;opacity:0.75">${Math.round(pct)}%</small>` : '';
      html += `<td class="${cls}">${val}${pctStr}</td>`;
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
    const pct = row.pct || 0;
    let barColor = pct >= 70 ? '#ef4444' : pct >= 30 ? '#eab308' : '#22c55e';
    html += `<tr>
      <td>${row.name}</td>
      <td>${row.n}</td>
      <td>${row.med_obs}</td>
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
    if (res.status === 403) {
      console.warn('Ingen tilgang til statistikk');
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

async function visArkivFullStatistikk() {
  if (!_aktivtArkivId) return;
  const id = _aktivtArkivId;

  const btn = document.getElementById('arkiv-detalj-fullstats-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Laster...';
  }

  try {
    const res = await apiFetch(`/pasienter/api/innstillinger/arkiv/${id}/full-stats/`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || 'Kunne ikke hente full statistikk for arkivet.');
      return;
    }
    const data = await res.json();

    fullStats = data;
    arkivStatsMode = true;
    arkivStatsMeta = {
      id: id,
      tittel: document.getElementById('arkiv-detalj-tittel')?.textContent?.trim() || `Arkiv ${id}`,
      arrangement_navn: window._sisteArkivArrangement || '',
      importert_at: window._sisteArkivImportertAt || '',
      antall_pasienter: window._sisteArkivAntall ?? '?',
    };

    bootstrap.Modal.getInstance(document.getElementById('arkivDetaljModal'))?.hide();

    const statLink = document.querySelector('[data-tab="statistikk"]');
    if (statLink) statLink.click();
    else {
      _oppdaterArkivBanner();
      renderStatTab(activeStatTab);
    }
  } catch (e) {
    console.error('Feil ved henting av arkiv full-stats:', e);
    alert('Feil ved henting av arkiv-statistikk.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-bar-chart-line me-1"></i>Vis full statistikk';
    }
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
      r.sig
        ? '<span style="color:#22c55e;font-weight:700;">&#10004; Ja</span>'
        : '<span style="color:#94a3b8;">&#10007; Nei</span>'
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
      r.sig
        ? '<span style="color:#22c55e;font-weight:700;">&#10004; Ja</span>'
        : '<span style="color:#94a3b8;">&#10007; Nei</span>'
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

  const sigTests = (s.chi2_table || []).filter(t => t.result?.sig).map(t => t.test);
  const nsTests  = (s.chi2_table || []).filter(t => t.result && !t.result.sig).map(t => t.test);

  const kwSig = [
    s.kw_triage?.sig    ? 'Tid etter triage'      : null,
    s.kw_problem?.sig   ? 'Tid etter problem'     : null,
    s.kw_transport?.sig ? 'Tid etter transport'   : null,
  ].filter(Boolean);

  let html = '';

  html += `<p class="mb-1 small" style="line-height:1.5; color:#e2e8f0;">
    <strong style="color:#ffffff;">Datagrunnlag:</strong>
    ${sum.total} pasienter registrert, ${sum.utskrevet} utskrevet.
  </p>`;

  if (tt && tt.n > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5; color:#e2e8f0;">
      <strong style="color:#ffffff;">Total tid:</strong>
      Gjennomsnitt ${fmtMin(tt.mean)}, median ${fmtMin(tt.median)} (n=${tt.n}).
    </p>`;
  }

  if (ot && ot.n > 0) {
    html += `<p class="mb-1 small" style="line-height:1.5; color:#e2e8f0;">
      <strong style="color:#ffffff;">Obspost:</strong>
      ${sum.total_obs_count} pasienter (${obsPct}%) på obspost. Snitt ${fmtMin(ot.mean)}, median ${fmtMin(ot.median)}.
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

// ════════════════════════════════════════════════════════
// SETTINGS  (GET /api/settings/ , PUT /api/settings/)
// ════════════════════════════════════════════════════════
async function loadSettings() {
  const s = await (await fetch('/pasienter/api/settings/')).json();
  if (s.event_name) {
    const inp = document.getElementById('setting-event-name');
    if (inp) inp.value = s.event_name;
    const disp = document.getElementById('event-name-display');
    if (disp) disp.textContent = s.event_name;
  }
}

async function saveEventName() {
  const name = (document.getElementById('setting-event-name')?.value || '').trim();
  if (!name) return;
  await apiFetch('/pasienter/api/settings/', {
    method: 'PUT',
    body: JSON.stringify({ event_name: name })
  });
  const disp = document.getElementById('event-name-display');
  if (disp) disp.textContent = name;
}

// ════════════════════════════════════════════════════════
// ARCHIVES  (GET /api/archives/)
// ════════════════════════════════════════════════════════
async function loadArchives() {
  const archives = await (await fetch('/pasienter/api/archives/')).json();
  const el = document.getElementById('archive-list');
  if (!el) return;
  if (!archives.length) {
    el.innerHTML = '<span class="text-muted small">Ingen arkiver ennå.</span>';
    return;
  }
  el.innerHTML = archives.map(a => `
    <div class="archive-row">
      <span><i class="bi bi-file-earmark-text me-1 text-secondary"></i>${a.fil}</span>
      <span class="text-muted">${a.antall} pasienter</span>
      <span class="text-muted">${a.arkivert ? new Date(a.arkivert).toLocaleString('no-NO') : ''}</span>
    </div>`).join('');
}

// ════════════════════════════════════════════════════════
// SESJONSTIMEOUT
// ════════════════════════════════════════════════════════
async function loadSessionTimeout() {
  const el = document.getElementById('session-timeout-input');
  if (!el) return;
  try {
    const res = await apiFetch('/pasienter/api/session-timeout/');
    const d = await res.json();
    el.value = d.hours;
  } catch (e) {}
}

async function saveSessionTimeout() {
  const el = document.getElementById('session-timeout-input');
  if (!el) return;
  const hours = parseInt(el.value, 10);
  if (isNaN(hours) || hours < 1 || hours > 24) {
    alert('Oppgi et tall mellom 1 og 24');
    return;
  }
  try {
    await apiFetch('/pasienter/api/session-timeout/', {method:'PUT', body: JSON.stringify({hours})});
    alert('Sesjonstimeout oppdatert.');
  } catch (e) {
    alert('Kunne ikke lagre: ' + e.message);
  }
}

// ════════════════════════════════════════════════════════
// BEHANDLERE
// ════════════════════════════════════════════════════════

// ETag for behandlere – unngår unyttig dataoverføring når listen er uendret
let lastBehandlereEtag = null;

async function loadBehandlere() {
  const headers = { 'Cache-Control': 'no-cache' };
  if (lastBehandlereEtag) {
    headers['If-None-Match'] = lastBehandlereEtag;
  }
  const res = await fetch('/pasienter/api/behandlere/', {
    cache: 'no-store',
    headers,
  });
  if (res.status === 304) {
    return;
  }
  const etag = res.headers.get('ETag');
  if (etag) lastBehandlereEtag = etag;
  behandlere = await res.json();
  _populateBehandlerDropdown('n-behandler', null);
  const eBeh = document.getElementById('e-behandler');
  const currentEditBeh = eBeh && eBeh.value
    ? behandlere.find(b => String(b.id) === String(eBeh.value)) || null
    : null;
  _populateBehandlerDropdown('e-behandler', currentEditBeh);
  renderBehandlereAdmin();
}

function renderBehandlereAdmin() {
  const container = document.getElementById('behandlere-list');
  if (!container) return;
  if (!behandlere.length) {
    container.innerHTML = '<span class="text-muted small">Ingen behandlere registrert.</span>';
    return;
  }
  const rows = behandlere.map(b => `
    <div class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem;">
      <span class="flex-grow-1 ${b.is_active ? '' : 'text-muted'}">${b.name}${b.is_active ? '' : ' <em>(inaktiv)</em>'}</span>
      <button class="btn btn-outline-secondary btn-sm py-0 px-1" onclick="toggleBehandler(${b.id})" title="${b.is_active ? 'Deaktiver' : 'Aktiver'}">
        <i class="bi bi-${b.is_active ? 'toggle-on' : 'toggle-off'}"></i>
      </button>
      <button class="btn btn-outline-danger btn-sm py-0 px-1" onclick="deleteBehandler(${b.id})" title="Slett">
        <i class="bi bi-trash"></i>
      </button>
    </div>`).join('');
  container.innerHTML = rows;
}

async function addBehandler() {
  const nameEl = document.getElementById('new-behandler-name');
  const name = (nameEl?.value || '').trim();
  if (!name) { alert('Skriv inn et navn.'); return; }
  const res = await apiFetch('/pasienter/api/behandlere/', {
    method: 'POST',
    body: JSON.stringify({ name })
  });
  if (res.ok) {
    nameEl.value = '';
    await loadBehandlere();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved oppretting av behandler.');
  }
}

async function toggleBehandler(id) {
  const b = behandlere.find(x => x.id === id);
  if (!b) return;
  const res = await apiFetch(`/pasienter/api/behandlere/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ is_active: !b.is_active })
  });
  if (res.ok) await loadBehandlere();
}

async function deleteBehandler(id) {
  if (!confirm('Slett behandler? Hvis behandleren er knyttet til pasienter, vil slettingen blokkeres.')) return;
  const res = await apiFetch(`/pasienter/api/behandlere/${id}/`, { method: 'DELETE' });
  if (res.ok) {
    await loadBehandlere();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved sletting.');
  }
}

// ════════════════════════════════════════════════════════
// HELSEPERSONELL (samme mønster som behandlere)
// ════════════════════════════════════════════════════════
let lastHelsepersonellEtag = null;

async function loadHelsepersonell() {
  const headers = { 'Cache-Control': 'no-cache' };
  if (lastHelsepersonellEtag) {
    headers['If-None-Match'] = lastHelsepersonellEtag;
  }
  const res = await fetch('/pasienter/api/helsepersonell/', {
    cache: 'no-store',
    headers,
  });
  if (res.status === 304) {
    return;
  }
  const etag = res.headers.get('ETag');
  if (etag) lastHelsepersonellEtag = etag;
  helsepersonellListe = await res.json();
  _populateHelsepersonellDropdown('n-helsepersonell', null);
  const eHp = document.getElementById('e-helsepersonell-ref');
  const currentEditHp = eHp && eHp.value
    ? helsepersonellListe.find(h => String(h.id) === String(eHp.value)) || null
    : null;
  _populateHelsepersonellDropdown('e-helsepersonell-ref', currentEditHp);
  renderHelsepersonellAdmin();
}

function renderHelsepersonellAdmin() {
  const container = document.getElementById('helsepersonell-list');
  if (!container) return;
  if (!helsepersonellListe.length) {
    container.innerHTML = '<span class="text-muted small">Ingen helsepersonell registrert.</span>';
    return;
  }
  const rows = helsepersonellListe.map(h => `
    <div class="d-flex align-items-center gap-2 mb-1" style="font-size:0.85rem;">
      <span class="flex-grow-1 ${h.is_active ? '' : 'text-muted'}">${h.name}${h.is_active ? '' : ' <em>(inaktiv)</em>'}</span>
      <button class="btn btn-outline-secondary btn-sm py-0 px-1" onclick="toggleHelsepersonell(${h.id})" title="${h.is_active ? 'Deaktiver' : 'Aktiver'}">
        <i class="bi bi-${h.is_active ? 'toggle-on' : 'toggle-off'}"></i>
      </button>
      <button class="btn btn-outline-danger btn-sm py-0 px-1" onclick="deleteHelsepersonell(${h.id})" title="Slett">
        <i class="bi bi-trash"></i>
      </button>
    </div>`).join('');
  container.innerHTML = rows;
}

async function addHelsepersonell() {
  const nameEl = document.getElementById('new-helsepersonell-name');
  const name = (nameEl?.value || '').trim();
  if (!name) { alert('Skriv inn et navn.'); return; }
  const res = await apiFetch('/pasienter/api/helsepersonell/', {
    method: 'POST',
    body: JSON.stringify({ name })
  });
  if (res.ok) {
    nameEl.value = '';
    await loadHelsepersonell();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved oppretting av helsepersonell.');
  }
}

async function toggleHelsepersonell(id) {
  const h = helsepersonellListe.find(x => x.id === id);
  if (!h) return;
  const res = await apiFetch(`/pasienter/api/helsepersonell/${id}/`, {
    method: 'PUT',
    body: JSON.stringify({ is_active: !h.is_active })
  });
  if (res.ok) await loadHelsepersonell();
}

async function deleteHelsepersonell(id) {
  if (!confirm('Slett helsepersonell? Hvis helsepersonellet er knyttet til pasienter, vil slettingen blokkeres.')) return;
  const res = await apiFetch(`/pasienter/api/helsepersonell/${id}/`, { method: 'DELETE' });
  if (res.ok) {
    await loadHelsepersonell();
  } else {
    const d = await res.json();
    alert(d.error || 'Feil ved sletting.');
  }
}

// ════════════════════════════════════════════════════════
// NULLSTILL AKTIV VAKT
// ════════════════════════════════════════════════════════

async function doResetActiveYear() {
  const res = await apiFetch('/pasienter/api/reset-active-year/', {
    method: 'POST',
    body: JSON.stringify({ confirm: true })
  });
  const d = await res.json();
  bootstrap.Modal.getInstance(document.getElementById('resetModal'))?.hide();
  if (res.ok) {
    const melding = `${d.antall_slettet} pasienter slettet. Aktiv vakt er nullstilt.`;
    alert(melding);
    await loadPatients();
  } else {
    alert(d.error || 'Feil ved nullstilling.');
  }
}

// ════════════════════════════════════════════════════════
// TAB NAVIGATION
// ════════════════════════════════════════════════════════
document.querySelectorAll('[data-tab]').forEach(link => link.addEventListener('click', e => {
  e.preventDefault();
  const tab = link.dataset.tab;
  document.querySelectorAll('[data-tab]').forEach(l => l.classList.remove('active'));
  link.classList.add('active');
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + tab)?.classList.add('active');
  if (tab === 'tavle')        renderBoard();
  if (tab === 'statistikk')   loadStats();
  if (tab === 'innstillinger') {
    loadSettings();
    loadArchives();
    loadSessionTimeout();
    loadBehandlere();
    loadHelsepersonell();
    loadBackupPanel();
  }
}));

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
// AUTO-REFRESH + INIT
// Polling pauses automatisk når fanen er skjult (document.hidden === true).
// Dette sparer batteri og nettverkstrafikk når brukeren ikke ser på siden.
// ════════════════════════════════════════════════════════

let refreshId = null;

async function doAutoRefresh() {
  await loadPatients();
  await loadBehandlere();
  await loadHelsepersonell();
  const t = document.querySelector('[data-tab].active')?.dataset.tab;
  if (t === 'tavle')      renderBoard();
  if (t === 'statistikk') loadStats();
}

function startRefreshInterval() {
  if (refreshId !== null) return;
  refreshId = setInterval(doAutoRefresh, 30000);
}

function stopRefreshInterval() {
  if (refreshId !== null) {
    clearInterval(refreshId);
    refreshId = null;
  }
}

document.addEventListener('visibilitychange', async () => {
  if (document.hidden) {
    stopRefreshInterval();
  } else {
    await doAutoRefresh();
    startRefreshInterval();
  }
});

// ════════════════════════════════════════════════════════
// BACKUP
// ════════════════════════════════════════════════════════

async function loadBackupPanel() {
  const res = await fetch('/pasienter/api/backup/', { cache: 'no-store' });
  if (!res.ok) {
    document.getElementById('backup-list').innerHTML =
      '<span class="text-danger">Kunne ikke laste backups.</span>';
    return;
  }
  const data = await res.json();

  const sel = document.getElementById('backup-interval');
  if (sel) sel.value = data.config.interval_minutes;

  const lastRun = document.getElementById('backup-last-run');
  if (lastRun) {
    lastRun.textContent = data.config.last_run_at
      ? 'Siste automatiske backup: ' + new Date(data.config.last_run_at).toLocaleString('no-NO')
      : 'Ingen automatisk backup kjørt enda.';
  }

  const list = document.getElementById('backup-list');
  if (!data.backups.length) {
    list.innerHTML = '<span class="text-muted">Ingen backups ennå.</span>';
    return;
  }
  list.innerHTML = data.backups.map(b => {
    const when = new Date(b.created_at).toLocaleString('no-NO');
    const kb = (b.size_bytes / 1024).toFixed(1);
    const note = b.note ? ` – <em>${escapeHtml(b.note)}</em>` : '';
    return `
      <div class="d-flex align-items-center gap-2 py-1 border-bottom">
        <div class="flex-grow-1">
          <div><strong>${when}</strong> <span class="badge bg-secondary">${escapeHtml(b.kind_display)}</span></div>
          <div class="text-muted">${kb} KB · ${escapeHtml(b.filename)}${note}</div>
        </div>
        <a class="btn btn-outline-secondary btn-sm py-0 px-1" href="/pasienter/api/backup/${b.id}/download/" title="Last ned">
          <i class="bi bi-download"></i>
        </a>
        <button class="btn btn-outline-warning btn-sm py-0 px-1" onclick="restoreBackup(${b.id}, '${escapeHtml(b.filename)}')" title="Gjenopprett">
          <i class="bi bi-arrow-counterclockwise"></i>
        </button>
        <button class="btn btn-outline-danger btn-sm py-0 px-1" onclick="deleteBackup(${b.id})" title="Slett">
          <i class="bi bi-trash"></i>
        </button>
      </div>`;
  }).join('');
}

async function createBackupNow() {
  const noteEl = document.getElementById('backup-note');
  const note = (noteEl?.value || '').trim();
  const res = await apiFetch('/pasienter/api/backup/create/', {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
  if (res.ok) {
    if (noteEl) noteEl.value = '';
    await loadBackupPanel();
  } else {
    const d = await res.json();
    alert(d.error || 'Kunne ikke lage backup.');
  }
}

async function restoreBackup(id, filename) {
  const warning = `ADVARSEL: Dette ERSTATTER ALL DATA med innholdet fra\n\n${filename}\n\n` +
                  `En sikkerhetskopi av nåværende tilstand lages automatisk først.\n\n` +
                  `Skriv GJENOPPRETT for å bekrefte:`;
  const ans = prompt(warning);
  if (ans !== 'GJENOPPRETT') return;

  const res = await apiFetch(`/pasienter/api/backup/${id}/restore/`, {
    method: 'POST',
    body: JSON.stringify({ confirm: 'GJENOPPRETT' }),
  });
  if (res.ok) {
    alert('Gjenoppretting fullført. Du blir logget ut.');
    window.location.href = '/accounts/logout/';
  } else {
    const d = await res.json();
    alert(d.error || 'Gjenoppretting feilet.');
  }
}

async function deleteBackup(id) {
  if (!confirm('Slett denne backupen?')) return;
  const res = await apiFetch(`/pasienter/api/backup/${id}/`, { method: 'DELETE' });
  if (res.ok) await loadBackupPanel();
  else {
    const d = await res.json();
    alert(d.error || 'Sletting feilet.');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('backup-interval');
  if (sel) {
    sel.addEventListener('change', async (e) => {
      const statusEl = document.getElementById('backup-interval-status');
      if (statusEl) {
        statusEl.textContent = 'Lagrer…';
        statusEl.className = 'small text-muted ms-2';
      }
      const res = await apiFetch('/pasienter/api/backup/config/', {
        method: 'POST',
        body: JSON.stringify({ interval_minutes: parseInt(e.target.value) }),
      });
      if (!res.ok) {
        const d = await res.json();
        if (statusEl) {
          statusEl.textContent = 'Feil: ' + (d.error || 'Kunne ikke lagre');
          statusEl.className = 'small text-danger ms-2';
        } else {
          alert(d.error || 'Kunne ikke lagre.');
        }
        return;
      }
      if (statusEl) {
        statusEl.textContent = 'Lagret ✓';
        statusEl.className = 'small text-success ms-2';
        setTimeout(() => {
          if (statusEl.textContent === 'Lagret ✓') statusEl.textContent = '';
        }, 3000);
      }
    });
  }
});

document.addEventListener('DOMContentLoaded', async () => {
  applyRoleVisibility();
  initTable();
  const mineToggle = document.getElementById('toggle-mine');
  if (mineToggle) mineToggle.checked = mineOnly;
  await loadBehandlere();
  await loadHelsepersonell();
  await loadPatients();
  loadSettings();
  loadSessionTimeout();
  if (document.getElementById('tab-tavle')?.classList.contains('active')) {
    renderBoard();
  }
  startRefreshInterval();
});


// ════════════════════════════════════════════════════════
// VAKTARKIV
// ════════════════════════════════════════════════════════

let _aktivtArkivId = null;

async function lagreVaktSomArkiv() {
  const navn = (document.getElementById('arkiv-arrangement-navn')?.value || '').trim();
  const notat = (document.getElementById('arkiv-notat')?.value || '').trim();
  const feilEl = document.getElementById('arkiv-lagre-feil');

  if (!navn) {
    if (feilEl) { feilEl.textContent = 'Arrangementsnavn er påkrevd.'; feilEl.classList.remove('d-none'); }
    return;
  }
  if (feilEl) feilEl.classList.add('d-none');

  const res = await apiFetch('/pasienter/api/innstillinger/arkiv/lagre/', {
    method: 'POST',
    body: JSON.stringify({ arrangement_navn: navn, notat })
  });
  const d = await res.json();
  bootstrap.Modal.getInstance(document.getElementById('arkivLagreModal'))?.hide();
  if (res.ok) {
    alert(`Arkiv lagret: "${d.tittel}" (${d.antall_pasienter} pasienter).`);
  } else {
    alert(d.error || 'Feil ved arkivering.');
  }
}

async function loadArkivListe() {
  const container = document.getElementById('arkiv-liste-innhold');
  if (!container) return;
  container.innerHTML = '<span class="text-muted small">Laster...</span>';

  const res = await apiFetch('/pasienter/api/innstillinger/arkiv/');
  if (!res.ok) {
    container.innerHTML = '<span class="text-danger small">Kunne ikke hente arkivliste.</span>';
    return;
  }
  const data = await res.json();
  if (!data.length) {
    container.innerHTML = '<span class="text-muted small">Ingen arkiverte vakter funnet.</span>';
    return;
  }

  const rows = data.map(a => `
    <tr>
      <td class="small">${_escHtml(a.tittel)}</td>
      <td class="small text-nowrap">${_escHtml(a.importert_at ? a.importert_at.slice(0,16).replace('T',' ') : '')}</td>
      <td class="small text-center">${a.antall_pasienter}</td>
      <td class="small">
        <button class="btn btn-outline-primary btn-sm py-0 px-1" onclick="visArkivDetalj(${a.id})">
          <i class="bi bi-bar-chart me-1"></i>Statistikk
        </button>
        <button class="btn btn-outline-danger btn-sm py-0 px-1 ms-1" onclick="slettArkiv(${a.id})">
          <i class="bi bi-trash"></i>
        </button>
      </td>
    </tr>
  `).join('');

  container.innerHTML = `
    <table class="table table-sm table-hover mb-0">
      <thead class="table-light"><tr>
        <th>Tittel</th><th>Dato</th><th class="text-center">Antall</th><th>Handlinger</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function visArkivDetalj(id) {
  _aktivtArkivId = id;
  const modal = new bootstrap.Modal(document.getElementById('arkivDetaljModal'));
  modal.show();

  document.getElementById('arkiv-detalj-tittel').innerHTML =
    '<i class="bi bi-archive me-2"></i>Laster arkiv...';
  document.getElementById('arkiv-detalj-meta').textContent = '';
  document.getElementById('arkiv-detalj-stats').innerHTML =
    '<span class="text-muted small">Henter statistikk...</span>';
  document.getElementById('arkiv-detalj-tamper')?.classList.add('d-none');
  document.getElementById('arkiv-detalj-slett')?.classList.add('d-none');
  document.getElementById('arkiv-detalj-fullstats-btn')?.classList.add('d-none');

  const res = await apiFetch(`/pasienter/api/innstillinger/arkiv/${id}/`);
  if (!res.ok) {
    document.getElementById('arkiv-detalj-stats').innerHTML =
      '<span class="text-danger">Kunne ikke hente arkivdata.</span>';
    return;
  }
  const d = await res.json();

  document.getElementById('arkiv-detalj-tittel').innerHTML =
    `<i class="bi bi-archive me-2"></i>${_escHtml(d.tittel)}`;

  const datoStr = d.importert_at ? d.importert_at.slice(0,16).replace('T',' ') : '';
  document.getElementById('arkiv-detalj-meta').innerHTML =
    `Arrangement: <strong>${_escHtml(d.arrangement_navn)}</strong> &nbsp;|&nbsp; ` +
    `Arkivert: ${datoStr} av ${_escHtml(d.importert_av)} &nbsp;|&nbsp; ` +
    `Pasienter: ${d.antall_pasienter} &nbsp;|&nbsp; År: ${d.year_snapshot}` +
    (d.notat ? ` &nbsp;|&nbsp; <em>${_escHtml(d.notat)}</em>` : '');

  if (d.tamper_detected) {
    document.getElementById('arkiv-detalj-tamper')?.classList.remove('d-none');
  }

  const s = d.stats || {};
  document.getElementById('arkiv-detalj-stats').innerHTML = `
    <div class="row g-2 mb-3">
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small">
        <div class="fw-bold fs-5">${s.total ?? 0}</div><div class="text-muted">Totalt</div>
      </div></div>
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small" style="border-color:#16a34a!important">
        <div class="fw-bold fs-5 text-success">${s.gronn ?? 0}</div><div class="text-muted">Grønn</div>
      </div></div>
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small" style="border-color:#ca8a04!important">
        <div class="fw-bold fs-5" style="color:#ca8a04">${s.gul ?? 0}</div><div class="text-muted">Gul</div>
      </div></div>
      <div class="col-6 col-md-3"><div class="border rounded p-2 text-center small" style="border-color:#dc2626!important">
        <div class="fw-bold fs-5 text-danger">${s.rod ?? 0}</div><div class="text-muted">Rød</div>
      </div></div>
    </div>
    <div class="row g-2 mb-3">
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.tilstede ?? 0}</div><div class="text-muted">Tilstede</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.utskrevet ?? 0}</div><div class="text-muted">Utskrevet</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.i_obs ?? 0}</div><div class="text-muted">I obs</div>
      </div></div>
    </div>
    <div class="row g-2">
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.avg_wait_min ?? 0} min</div><div class="text-muted">Snitt ventetid</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.avg_obs_min ?? 0} min</div><div class="text-muted">Snitt obs-tid</div>
      </div></div>
      <div class="col-4"><div class="border rounded p-2 text-center small">
        <div class="fw-bold">${s.avg_total_min ?? 0} min</div><div class="text-muted">Snitt total tid</div>
      </div></div>
    </div>
  `;

  window._sisteArkivArrangement = d.arrangement_navn || '';
  window._sisteArkivImportertAt = d.importert_at || '';
  window._sisteArkivAntall = d.antall_pasienter ?? 0;

  const fullBtn = document.getElementById('arkiv-detalj-fullstats-btn');
  if (fullBtn) fullBtn.classList.remove('d-none');

  const slettDiv = document.getElementById('arkiv-detalj-slett');
  if (slettDiv) slettDiv.classList.remove('d-none');
}

async function slettArkivFraDetalj() {
  if (!_aktivtArkivId) return;
  await slettArkiv(_aktivtArkivId);
  bootstrap.Modal.getInstance(document.getElementById('arkivDetaljModal'))?.hide();
}

async function slettArkiv(id) {
  if (!confirm('Er du sikker på at du vil slette dette arkivet? Handlingen kan ikke angres.')) return;
  const res = await apiFetch(`/pasienter/api/innstillinger/arkiv/${id}/`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm: true })
  });
  const d = await res.json();
  if (res.ok) {
    alert('Arkivet er slettet.');
    await loadArkivListe();
  } else {
    alert(d.error || 'Feil ved sletting av arkiv.');
  }
}
