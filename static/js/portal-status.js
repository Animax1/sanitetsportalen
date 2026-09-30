/* Server-status — /portal-admin/server-status/ (26. sep. 2026, G1).
 *
 * Sto som 531 linjer inline-JS i `templates/patients/admin_status.html`, der
 * ingen XSS-skanner, polling-regel eller node-test så den. Nå en fil som de
 * andre: `portal-utils.js` lastes foran (`apiFetch`, `escHtmlValue`,
 * `naarSynlig`), og URL-ene kommer fra `data-url-*` på `#server-status`.
 *
 * Tre ting endret seg i flyttingen: den lokale `escapeHtml` er borte
 * (`escHtmlValue` har samme regel — 0 vises), `klokke` heter `datoKlokke`
 * (portal-utils har en `klokke` med bare klokkeslett), og de lokale
 * CSRF-hjelperne er erstattet av `apiFetch`.
 */

//: Fylles av `statusStart()` fra `data-url-*` på `#server-status`.
let STATUS_URLS = {};

function fmt(n, fallback) {
  if (n === null || n === undefined) return fallback || '–';
  return n;
}

// Trinnet regnes på serveren (`beredskapsnivaa()`), ikke her: da er det
// samme terskler som i tabellen nederst og i runbooken. Til 24. sep. 2026
// sto en egen regel her, og den farget 300–500 ms grønt mens runbooken
// sa gult.
function renderBeredskap(b, kilde, modus) {
  const nivaa = (b && b.nivaa) || '';
  const merke = document.getElementById('beredskap-nivaa');
  merke.textContent = (b && b.navn) || '–';
  merke.className = 'beredskap-merke' + (nivaa ? ' beredskap-' + nivaa : '');
  document.getElementById('p95-5min').className = 'big-number' + (nivaa ? ' beredskap-' + nivaa : '');
  document.getElementById('beredskap-tiltak').textContent = b && b.fa_maalinger
    ? 'Bare ' + b.antall + ' forespørsler siste 5 min — P95 er da én treg forespørsel. Vent før du handler.'
    : ((b && b.tiltak) || '');
  if (b && b.fa_maalinger) merke.textContent += ' · få målinger';
  // Trinnet er løftet av databasekortet, ikke av P95 (`beredskap_med_databasen`).
  if (b && b.grunn === 'database') merke.textContent += ' · databasen';
  const k = document.getElementById('metrikk-kilde');
  k.textContent = (kilde && kilde.tekst) || '';
  k.className = 'sub' + (kilde && kilde.ok === false ? ' status-crit' : '');
  const m = document.getElementById('driftsmodus');
  m.textContent = (modus && modus.tekst) || '–';
  m.className = 'beredskap-merke ' + (modus && modus.ok === false ? 'beredskap-rod'
    : (modus && modus.modus === 'vakt' ? 'beredskap-gronn' : ''));
  document.querySelectorAll('[id^="trinn-"]').forEach((rad) => {
    rad.style.outline = rad.id === 'trinn-' + nivaa ? '2px solid currentColor' : '';
  });
}

async function refresh() {
  try {
    // `apiFetch` måler om noen er til stede (A8). Til 26. sep. 2026 var
    // `portal-utils.js` ikke lastet her, og hver poll sendte «ukjent».
    const res = await apiFetch(STATUS_URLS.json, {headers: {'Accept': 'application/json'}});
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    render(data);
    document.getElementById('last-update').textContent =
      new Date().toLocaleTimeString('no-NO');
  } catch (err) {
    console.error('Status-refresh feilet:', err);
    document.getElementById('last-update').textContent =
      'Feil: ' + err.message;
  }
}

function render(d) {
  const m1 = d.metrics_1min || {};
  const m5 = d.metrics_5min || {};

  document.getElementById('rps-1min').textContent = fmt(m1.rps);
  document.getElementById('count-1min').textContent = fmt(m1.count) + ' requests totalt';

  document.getElementById('avg-5min').textContent = fmt(m5.avg_ms) + ' ms';
  document.getElementById('p50-5min').textContent = fmt(m5.p50_ms) + ' ms';
  document.getElementById('p95-5min').textContent = fmt(m5.p95_ms);
  renderBeredskap(d.beredskap, d.metrikkilde, d.driftsmodus);

  document.getElementById('max-5min').textContent = fmt(m5.max_ms) + ' ms';
  document.getElementById('err-4xx').textContent = fmt(m5.errors_4xx);

  const err5El = document.getElementById('err-5xx');
  err5El.textContent = fmt(m5.errors_5xx);
  err5El.className = 'val ' + ((m5.errors_5xx || 0) > 0 ? 'status-crit' : 'status-ok');

  document.getElementById('count-5min').textContent = fmt(m5.count);

  document.getElementById('sessions').textContent = fmt(d.active_sessions);
  const mem = d.memory || {};
  document.getElementById('memory').textContent = fmt(mem.naa);
  document.getElementById('memory-peak').textContent = fmt(mem.topp) + ' MB';
  refreshSessionsList();

  const cfg = d.worker_config || {};
  document.getElementById('cfg-workers').textContent = fmt(cfg.workers);
  document.getElementById('cfg-threads').textContent = fmt(cfg.threads);
  document.getElementById('cfg-maxreq').textContent = fmt(cfg.max_requests);
  document.getElementById('cfg-pid').textContent = fmt(cfg.pid);

  const ch = d.cache_health || {};
  const backendEl = document.getElementById('cache-backend');
  const healthyEl = document.getElementById('cache-healthy');
  const latencyEl = document.getElementById('cache-latency');
  const hintEl = document.getElementById('cache-hint');
  backendEl.textContent = (ch.backend || '–').toUpperCase();
  if (ch.healthy === true) {
    healthyEl.textContent = 'OK';
    healthyEl.style.color = 'var(--success, #16a34a)';
  } else if (ch.healthy === false) {
    healthyEl.textContent = 'FEIL';
    healthyEl.style.color = 'var(--danger, #dc2626)';
  } else {
    healthyEl.textContent = '–';
    healthyEl.style.color = '';
  }
  latencyEl.textContent = (ch.latency_ms !== undefined) ? (ch.latency_ms + ' ms') : '–';
  if (ch.backend === 'redis') {
    hintEl.textContent = 'Delt cache mellom workers — rate-limit og stats-cache er konsistente.';
  } else if (ch.backend === 'locmem') {
    hintEl.textContent = 'Per-prosess cache. OK for 1 worker. Aktiver Redis før du øker WEB_WORKERS.';
  } else {
    hintEl.textContent = ch.error || '';
  }

  const uptime = m5.uptime_seconds || 0;
  const hrs = Math.floor(uptime / 3600);
  const mins = Math.floor((uptime % 3600) / 60);
  document.getElementById('cfg-uptime').textContent = hrs + 't ' + mins + 'm';

  const b = d.last_backup || {};
  if (b.found) {
    const ageEl = document.getElementById('backup-age');
    ageEl.textContent = fmt(b.age_minutes);
    ageEl.className = 'big-number ' + (b.age_minutes > 60 ? 'status-warn' : 'status-ok');
    document.getElementById('backup-details').textContent =
      (b.filename || '') + ' (' + Math.round((b.size_bytes || 0) / 1024) + ' KB)';
  } else {
    document.getElementById('backup-age').textContent = '–';
    document.getElementById('backup-details').textContent = 'Ingen backup funnet';
  }

  renderOffsite((d.last_backup || {}).offsite || {});
  renderDb(d.db_health || {});
  renderDisk(d.disk || {});
  renderVaktbilde(d.vaktbilde || {});
  renderTregeste(d.tregeste || []);
  renderInnlogging(d.innlogging || {});
  renderKonfig(d.konfig || {});
  renderCron(d.cron || {});
  renderBackupklokke(d.backupklokke || {});
  renderEpost(d.epost || {});
  renderKartkobling(d.kartkobling || {});

  // Oppdater JSON-preview
  document.getElementById('json-preview').textContent =
    JSON.stringify(d, null, 2);
}

// ── De nye kortene (13. sep. 2026) ─────────────────────────────
function setVal(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = 'val' + (cls ? ' ' + cls : '');
}
function tidSiden(minutter) {
  if (minutter === null || minutter === undefined) return '–';
  if (minutter < 60) return minutter + ' min siden';
  if (minutter < 48 * 60) return Math.round(minutter / 60) + ' t siden';
  return Math.round(minutter / 1440) + ' d siden';
}
function datoKlokke(iso) {
  if (!iso) return '–';
  const t = new Date(iso);
  return isNaN(t) ? '–' : t.toLocaleString('no-NO', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
}

function renderOffsite(o) {
  const det = document.getElementById('offsite-details');
  if (o.konfigurert === false) {
    setVal('offsite-status', 'Ikke konfigurert', 'status-warn');
    det.textContent = 'Mangler ' + (o.mangler || []).join(', ') + '. Bare prod skal ha dem.';
    return;
  }
  if (o.konfigurert !== true) {
    setVal('offsite-status', 'Ukjent', 'status-warn');
    det.textContent = o.error || '';
    return;
  }
  if (o.siste_feil) {
    setVal('offsite-status', 'Siste opplasting feilet', 'status-crit');
    det.textContent = datoKlokke(o.siste_feil_at) + ': ' + o.siste_feil;
    return;
  }
  const gammel = o.siste_ok_minutter !== null && o.siste_ok_minutter > 26 * 60;
  setVal('offsite-status', gammel ? 'Over ett døgn siden' : 'OK', gammel ? 'status-warn' : 'status-ok');
  det.textContent = (o.antall || 0) + ' fil(er) i ' + (o.bucket || '?') +
    (o.siste_ok_minutter !== null ? ' · sist ' + tidSiden(o.siste_ok_minutter) : ' · ingen opplasting ennå');
}

function renderDb(db) {
  setVal('db-vendor', (db.vendor || '–').toUpperCase());
  const hint = document.getElementById('db-hint');
  if (!db.healthy) {
    setVal('db-latency', 'FEIL', 'status-crit');
    ['db-conns', 'db-fordeling', 'db-eldste', 'db-laas', 'db-deadlocks'].forEach((id) => setVal(id, '–'));
    hint.textContent = db.error || 'Databasen svarte ikke.';
    return;
  }
  renderDbAktivitet(db);
  renderDbSortering(db.sortering || {});
  const lat = db.latency_ms || 0;
  setVal('db-latency', lat + ' ms', lat < 50 ? 'status-ok' : (lat < 200 ? 'status-warn' : 'status-crit'));
  if (db.maks_tilkoblinger) {
    const andel = db.tilkoblinger / db.maks_tilkoblinger;
    setVal('db-conns', db.tilkoblinger + ' / ' + db.maks_tilkoblinger,
      andel < 0.6 ? 'status-ok' : (andel < 0.85 ? 'status-warn' : 'status-crit'));
    hint.textContent = dbHint(db) || 'Hver worker holder egne tilkoblinger. Nær taket: ikke øk WEB_WORKERS.';
  } else {
    setVal('db-conns', 'n/a');
    hint.textContent = db.vendor === 'sqlite' ? 'SQLite lokalt — ingen tilkoblingsgrense.' : (db.error || '');
  }
}

const DB_KLASSE = { gronn: 'status-ok', gul: 'status-warn', rod: 'status-crit' };

// Vurderingen regnes på serveren (`sortering_vurdering()`), ikke her.
const SORTERING_TEKST = {
  norsk: ['Norsk', 'status-ok'],
  kodepunkt: ['Sist, men Å Æ Ø', 'status-warn'],
  blandet: ['Blandet inn (Æ=AE, Ø=O, Å=A)', 'status-warn'],
};

function renderDbSortering(s) {
  const rekke = document.getElementById('db-sortering-rekke');
  if (s.feil || !s.vurdering) {
    setVal('db-sortering', 'feil');
    rekke.textContent = s.feil || '';
    return;
  }
  const [tekst, klasse] = SORTERING_TEKST[s.vurdering] || [s.vurdering, ''];
  setVal('db-sortering', tekst, klasse);
  const basen = SORTERING_TEKST[s.basen_vurdering] || [s.basen_vurdering];
  rekke.textContent = s.rekkefolge.join(' · ')
    + (s.norsk_regel ? '' : ' — norsk regel mangler, faller tilbake til basens')
    + ' · Basen alene: ' + basen[0]
    + (s.kollasjon ? ' (datcollate ' + s.kollasjon + ', PostgreSQL ' + s.versjon + ')' : '');
}

function renderDbAktivitet(db) {
  const sig = db.signaler;
  if (!sig) {
    const tekst = db.aktivitet_feil ? 'feil' : 'n/a';
    ['db-fordeling', 'db-eldste', 'db-laas', 'db-deadlocks'].forEach((id) => setVal(id, tekst));
    return;
  }
  setVal('db-fordeling', db.arbeider + ' · ' + db.ledige + ' · ' + db.henger, DB_KLASSE[sig.henger]);
  setVal('db-eldste', String(db.eldste_s).replace('.', ',') + ' s', DB_KLASSE[sig.eldste]);
  setVal('db-laas', String(db.venter_laas), DB_KLASSE[sig.venter_laas]);
  setVal('db-deadlocks', String(db.deadlocks), DB_KLASSE[sig.deadlocks]);
  document.getElementById('db-deadlocks-etikett').textContent = db.stats_reset
    ? 'Deadlocks siden ' + new Date(db.stats_reset).toLocaleDateString('nb-NO', { day: 'numeric', month: 'short' })
    : 'Deadlocks (aldri nullstilt)';
}

// Hva kortet sier når noe er gult eller rødt — det viktigste først.
function dbHint(db) {
  const sig = db.signaler;
  if (db.aktivitet_feil) return 'Aktiviteten kunne ikke leses: ' + db.aktivitet_feil;
  if (!sig || sig.samlet === 'gronn') return '';
  if (sig.eldste !== 'gronn' || sig.henger !== 'gronn') {
    return 'En transaksjon har stått åpen i ' + String(db.eldste_s).replace('.', ',') + ' s'
      + (db.venter_laas ? ', og ' + db.venter_laas + ' venter bak den' : '')
      + '. Er svartiden fin, er det låsen og ikke basen. Runbook §8.';
  }
  if (sig.venter_laas !== 'gronn') return db.venter_laas + ' forespørsler venter på lås. Runbook §8.';
  return 'Deadlock siden nullstilling: to operasjoner låste hverandre. Si fra — det er en kodefeil.';
}

function renderDisk(disk) {
  const el = document.getElementById('disk-used');
  if (disk.error || disk.brukt_prosent === undefined) {
    el.textContent = '–'; el.className = 'big-number';
    document.getElementById('disk-path').textContent = disk.error || '';
    return;
  }
  const p = disk.brukt_prosent;
  el.textContent = p;
  el.className = 'big-number ' + (p < 70 ? 'status-ok' : (p < 90 ? 'status-warn' : 'status-crit'));
  setVal('disk-free', Math.round(disk.ledig_mb) + ' MB av ' + Math.round(disk.total_mb) + ' MB');
  setVal('disk-backups', Math.round(disk.backup_mb) + ' MB');
  document.getElementById('disk-path').textContent = disk.sti || '';
}

function renderVaktbilde(v) {
  const vakt = v.aktiv_vakt;
  setVal('vakt-navn', vakt ? vakt.navn : '–');
  const drift = v.vaktlister_i_drift || [];
  setVal('vakt-drift', drift.length ? drift.map(d => d.vakt).join(', ') : 'Ingen',
    drift.length ? 'status-ok' : '');
  const o = v.oppdrag;
  if (o) {
    setVal('vakt-oppdrag', o.paa_tavla + (o.ventende ? ' (' + o.ventende + ' venter)' : ''),
      o.ventende ? 'status-warn' : '');
    setVal('vakt-venter', o.trenger_ressurs + (o.eldste_ventende_minutter !== null ? ' · eldste ventende ' + o.eldste_ventende_minutter + ' min' : ''),
      o.trenger_ressurs ? 'status-crit' : '');
  } else {
    setVal('vakt-oppdrag', '–'); setVal('vakt-venter', '–');
  }
  const u = v.siste_utsending;
  if (u) {
    setVal('vakt-utsending', tidSiden(u.minutter_siden) + ' (' + u.utloest + ', ' + u.antall_mottakere + ' mott.)',
      u.ok ? 'status-ok' : 'status-crit');
  } else {
    setVal('vakt-utsending', 'Aldri');
  }
  document.getElementById('vakt-hint').textContent = v.error ? v.error :
    (vakt ? 'Vakta startet ' + datoKlokke(vakt.startet) + '. Tallene er den aktive vaktas.' : '');
}

function renderTregeste(rader) {
  const el = document.getElementById('tregeste');
  if (!rader.length) {
    el.innerHTML = '<div class="sub">Ingen sti med tre eller flere treff ennå.</div>';
    return;
  }
  el.innerHTML = rader.map(r => {
    const cls = r.p95_ms < 300 ? 'status-ok' : (r.p95_ms < 1000 ? 'status-warn' : 'status-crit');
    return '<div class="status-row"><span class="label" style="word-break:break-all;">' + escHtmlValue(r.path) +
      ' <span style="opacity:.7">×' + escHtmlValue(r.count) + '</span></span><span class="val ' + cls + '">' +
      escHtmlValue(r.p95_ms) + ' ms</span></div>';
  }).join('');
}

function renderInnlogging(i) {
  const el = document.getElementById('login-failed');
  if (i.error) { el.textContent = '–'; el.className = 'big-number'; document.getElementById('login-hint').textContent = i.error; return; }
  const f = i.feilede || 0;
  el.textContent = f;
  el.className = 'big-number ' + (f < 5 ? 'status-ok' : (f < 20 ? 'status-warn' : 'status-crit'));
  setVal('login-ok', fmt(i.vellykkede));
  setVal('login-spread', fmt(i.feilede_brukernavn) + ' / ' + fmt(i.feilede_ip),
    (i.feilede_ip === 1 && f >= 5) ? 'status-crit' : '');
  setVal('login-mfa', fmt(i.mfa_feilet), (i.mfa_feilet || 0) >= 5 ? 'status-warn' : '');
}

function renderKonfig(k) {
  const rader = k.rader || [];
  document.getElementById('konfig-rader').innerHTML = rader.length ? rader.map(r =>
    '<div class="status-row"><span class="label">' + escHtmlValue(r.nokkel) + '</span><span class="val ' +
    (r.ok ? 'status-ok' : 'status-crit') + '" title="' + escHtmlValue(r.verdi) + '">' +
    (r.ok ? '✓ ' : '✗ ') + escHtmlValue(r.verdi) +
    '</span></div>').join('') : '<div class="sub">–</div>';
  const sum = document.getElementById('konfig-sum');
  const feil = rader.filter(r => !r.ok).length;
  sum.textContent = rader.length ? (feil ? feil + ' avvik' : 'alt OK') : '';
  sum.className = 'unit ' + (feil ? 'status-crit' : 'status-ok');
  const v = k.versjon || {};
  setVal('konfig-versjon', (v.bygg || '?') + (v.dato ? ' · ' + datoKlokke(v.dato) : ''));
}

function renderBackupklokke(k) {
  if (k.error) { setVal('klokke-tikk', k.error, 'status-warn'); return; }
  setVal('klokke-tikk',
         k.siste_tikk ? datoKlokke(k.siste_tikk) + ' (' + tidSiden(k.minutter_siden) + ')' : 'Aldri',
         k.siste_tikk ? (k.ok ? 'status-ok' : 'status-crit') : 'status-warn');
  const f = k.forsinkede || [];
  setVal('klokke-forsinket', f.length ? f.join(', ') : 'Ingen',
         f.length ? 'status-crit' : 'status-ok');
}

function renderCron(c) {
  const navn = {purge_old_logs: 'purge_old_logs', kollaps_arkiv: 'kollaps_arkiv'};
  const forventet = {purge_old_logs: 26, kollaps_arkiv: 8 * 24};
  if (c.error) { document.getElementById('cron-rader').innerHTML = '<div class="sub">' + escHtmlValue(c.error) + '</div>'; return; }
  document.getElementById('cron-rader').innerHTML = Object.keys(navn).map(n => {
    const k = c[n];
    let tekst, cls;
    if (!k) { tekst = 'Aldri'; cls = 'status-warn'; }
    else if (!k.ok) { tekst = '✗ ' + datoKlokke(k.tid); cls = 'status-crit'; }
    else { tekst = '✓ ' + datoKlokke(k.tid); cls = (k.timer_siden !== null && k.timer_siden > forventet[n]) ? 'status-warn' : 'status-ok'; }
    const tittel = k && k.melding ? ' title="' + escHtmlValue(k.melding) + '"' : '';
    return '<div class="status-row"><span class="label">' + navn[n] + '</span><span class="val ' + cls + '"' + tittel + '>' + tekst + '</span></div>';
  }).join('');
}

function renderEpost(e) {
  const t = e.transport || '–';
  setVal('epost-transport', t.toUpperCase(), t === 'ahasend' ? 'status-ok' : (t === 'console' || t === 'locmem' ? 'status-crit' : 'status-warn'));
  setVal('epost-ok', e.siste_ok_at ? datoKlokke(e.siste_ok_at) : 'Aldri');
  setVal('epost-feil', e.siste_feil ? datoKlokke(e.siste_feil_at) + ': ' + e.siste_feil : 'Ingen', e.siste_feil ? 'status-crit' : '');
  document.getElementById('epost-hint').textContent =
    t === 'ahasend' ? 'AHASend HTTP-API — transporten i prod. Railway sperrer SMTP.' :
    t === 'console' ? 'Konsoll: ingenting sendes. I prod mangler AHASEND_API_KEY/ACCOUNT_ID.' :
    t === 'smtp' ? 'SMTP virker bare lokalt — Railway sperrer utgående SMTP.' : (e.error || '');
}

/** Kortet for kart.sanitet.net. «–» når koblingen ikke er satt opp. */
function kartkoblingTekst(k) {
  if (k.error) return { kobling: ['Feil', 'status-crit'], siste: ['–', ''], hint: k.error };
  if (!k.konfigurert) {
    return { kobling: ['–', ''], siste: ['–', ''], hint: 'Ikke satt opp: KART_URL og KART_HMAC_NOKKEL er tomme.' };
  }
  const s = k.siste;
  const siste = !s ? ['Ingen ennå', '']
    : s.ok ? ['✓ ' + datoKlokke(s.tid) + ' (' + s.hva + ')', 'status-ok']
    : ['✗ ' + datoKlokke(s.tid) + ' (' + s.hva + (s.status ? ', ' + s.status : '') + ')', 'status-crit'];
  const hint = k.pause ? 'Pause etter feil: sendinger hoppes over i ett minutt.'
    : s && !s.ok && s.status === 401 ? '401: nøkkelen stemmer ikke med kartets PORTAL_HMAC_NOKKEL.'
    : 'Posisjoner sendes ved stempling, lagene ved plassering. Portalen lagrer ingenting.';
  return { kobling: [k.vert || 'På', 'status-ok'], siste, hint };
}

function renderKartkobling(k) {
  const t = kartkoblingTekst(k);
  setVal('kart-kobling', t.kobling[0], t.kobling[1]);
  setVal('kart-siste', t.siste[0], t.siste[1]);
  document.getElementById('kart-hint').textContent = t.hint;
}

// ── Sesjonshåndtering ─────────────────────────────────────────

// Serveren sender en referanse (`ref`), aldri `session_key` — nøkkelen er
// cookie-verdien (28. sep. 2026). Backend avviser self-kill. UI gjenkjenner egen sesjon ved at
// backend returnerer 400 dersom man prøver å logge ut seg selv.
let lastSessions = [];

async function refreshSessionsList() {
  const list = document.getElementById('sessions-list');
  const status = document.getElementById('sessions-status');
  try {
    const res = await apiFetch(STATUS_URLS.sessions, {headers: {'Accept': 'application/json'}});
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    lastSessions = data.sessions || [];
    if (lastSessions.length === 0) {
      list.innerHTML = '<div class="sessions-empty">Ingen aktive påloggede brukere</div>';
      status.textContent = '';
      return;
    }
    list.innerHTML = lastSessions.map(s => `
      <div class="session-item" data-key="${escHtmlValue(s.ref)}">
        <div class="who">
          <span class="username">${escHtmlValue(s.username)}</span>
          <span class="role">${escHtmlValue(s.role || 'bruker')}</span>
        </div>
        <span class="aktivitet ${escHtmlValue(aktivitetsklasse(s.inaktiv_s))}">${escHtmlValue(aktivitetstekst(s.inaktiv_s))}</span>
        <button class="btn-kill" data-key="${escHtmlValue(s.ref)}" data-username="${escHtmlValue(s.username)}" type="button">Logg ut</button>
      </div>
    `).join('');
    // **Begge tallene.** «Pålogget» er ikke «til stede», og André trenger å
    // se begge: hvor mange sesjoner som finnes, og hvor mange av dem det
    // faktisk sitter noen bak.
    const aktive = lastSessions.filter(s => s.inaktiv_s != null && s.inaktiv_s < 300).length;
    status.textContent = lastSessions.length + ' påloggede · ' + aktive + ' aktive nå';
  } catch (err) {
    list.innerHTML = '<div class="sessions-empty">Kunne ikke hente sesjoner: ' + escHtmlValue(err.message) + '</div>';
  }
}

// **Aktivitet som tekst, ikke et tall i sekunder** (16. sep. 2026). Den som
// ser på lista spør «sitter det noen der?», ikke «hvor mange sekunder».
// Grensene er valgt etter hva pollingen betyr: fana snakker med serveren
// hvert 5.–30. sekund uansett, så under fem minutter er et menneske som
// nettopp gjorde noe.
function aktivitetstekst(sek) {
  if (sek == null) return 'ukjent';
  if (sek < 300) return 'aktiv nå';
  if (sek < 3600) return 'inaktiv ' + Math.round(sek / 60) + ' min';
  const t = Math.floor(sek / 3600);
  return 'inaktiv ' + t + (t === 1 ? ' time' : ' timer');
}

function aktivitetsklasse(sek) {
  // «ukjent» dempes som en inaktiv: en sesjon vi ikke vet noe om skal ikke
  // se like trygg ut som en vi vet er i bruk.
  if (sek == null) return 'akt-ukjent';
  if (sek < 300) return 'akt-aktiv';
  if (sek < 3600) return 'akt-rolig';
  return 'akt-borte';
}

async function killSession(sessionKey, username, btn) {
  if (!confirm('Logge ut ' + username + '?\n\nBrukeren må logge inn på nytt for å fortsette.')) return;
  btn.disabled = true;
  btn.textContent = 'Logger ut…';
  try {
    const fd = new FormData();
    fd.append('ref', sessionKey);
    const res = await apiFetch(STATUS_URLS.kill, {method: 'POST', body: fd});
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert('Kunne ikke logge ut: ' + (data.error || 'HTTP ' + res.status));
      btn.disabled = false;
      btn.textContent = 'Logg ut';
      return;
    }
    // Fjern raden umiddelbart for visuell respons
    const row = btn.closest('.session-item');
    if (row) row.remove();
    refreshSessionsList();
  } catch (err) {
    alert('Feil ved utlogging: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Logg ut';
  }
}

async function killAllSessions() {
  const count = lastSessions.length;
  if (count === 0) {
    alert('Ingen aktive sesjoner å logge ut.');
    return;
  }
  if (!confirm('NØDBREMS:\n\nLogge ut ' + count + ' brukere?\n\nDin egen sesjon påvirkes ikke.\nAlle andre må logge inn på nytt for å fortsette.')) return;
  const btn = document.getElementById('btn-kill-all');
  btn.disabled = true;
  btn.textContent = 'Logger ut…';
  try {
    const fd = new FormData();
    fd.append('confirm', 'YES');
    const res = await apiFetch(STATUS_URLS.killAll, {method: 'POST', body: fd});
    const data = await res.json();
    if (!res.ok || !data.ok) {
      alert('Kunne ikke logge ut alle: ' + (data.error || 'HTTP ' + res.status));
    } else {
      alert('Logget ut ' + (data.deleted || 0) + ' brukere.');
    }
  } catch (err) {
    alert('Feil: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Nødbrems: logg ut alle (unntatt meg)';
    refreshSessionsList();
  }
}

function statusStart() {
  const rot = document.getElementById('server-status');
  STATUS_URLS = {json: rot.dataset.urlJson, sessions: rot.dataset.urlSessions,
                 kill: rot.dataset.urlKill, killAll: rot.dataset.urlKillAll};
  // Event-delegation for «Logg ut»-knapper
  document.getElementById('sessions-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-kill');
    if (!btn) return;
    killSession(btn.dataset.key, btn.dataset.username, btn);
  });
  document.getElementById('btn-kill-all').addEventListener('click', killAllSessions);
  // Første henting med én gang, så hvert 10. sekund — ikke i en skjult fane.
  refresh();
  setInterval(naarSynlig(refresh), 10000);
}

document.addEventListener('DOMContentLoaded', statusStart);
