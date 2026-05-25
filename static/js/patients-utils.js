// ════════════════════════════════════════════════════════
// CSRF & API HELPERS  (Django-specific)
// ════════════════════════════════════════════════════════

function getCsrfToken() {
  const name = 'csrftoken';
  const cookies = document.cookie.split(';');
  for (let c of cookies) {
    const trimmed = c.trim();
    if (trimmed.startsWith(name + '=')) {
      return decodeURIComponent(trimmed.slice(name.length + 1));
    }
  }
  const holder = document.getElementById('csrf-token-holder');
  if (holder) {
    const input = holder.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;
  }
  return '';
}

async function apiFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(options.headers || {}) };

  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    headers['X-CSRFToken'] = getCsrfToken();
  }

  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  return fetch(url, { ...options, headers });
}

// ════════════════════════════════════════════════════════
// SUBMIT GUARD (forhindrer dobbeltklikk-registrering)
// ════════════════════════════════════════════════════════

async function withSubmitGuard(buttonId, fn, opts = {}) {
  const minLockMs = opts.minLockMs ?? 250;
  const btn = document.getElementById(buttonId);

  if (btn && btn.dataset.submitting === '1') {
    return;
  }

  let originalHtml = null;
  if (btn) {
    btn.dataset.submitting = '1';
    btn.disabled = true;
    originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Lagrer…';
  }

  const startedAt = Date.now();
  try {
    return await fn();
  } finally {
    const elapsed = Date.now() - startedAt;
    if (elapsed < minLockMs) {
      await new Promise(r => setTimeout(r, minLockMs - elapsed));
    }
    if (btn) {
      btn.disabled = false;
      delete btn.dataset.submitting;
      if (originalHtml !== null) btn.innerHTML = originalHtml;
    }
  }
}

// ════════════════════════════════════════════════════════
// ROLE-BASED VISIBILITY
// ════════════════════════════════════════════════════════

function applyRoleVisibility() {
  const role = (window.USER_ROLE || 'read_only').toLowerCase();

  const canWrite = role === 'admin' || role === 'lead' || role === 'read_write';
  const canStats = role === 'admin' || role === 'lead' || role === 'lead_view';
  const canList  = role !== 'read_only';
  const isAdmin  = role === 'admin';

  if (!canWrite) {
    document.querySelectorAll('.write-only').forEach(el => {
      el.style.display = 'none';
    });
  }

  if (!canStats) {
    document.querySelectorAll('.stats-only').forEach(el => {
      el.style.display = 'none';
    });
  }

  if (!canList) {
    document.querySelectorAll('.list-only').forEach(el => {
      el.style.display = 'none';
    });
    document.querySelectorAll('[data-tab="liste"]').forEach(el => el.classList.remove('active'));
    const listePanel = document.getElementById('tab-liste');
    if (listePanel) listePanel.classList.remove('active');
    const tavleLink = document.querySelector('[data-tab="tavle"]');
    if (tavleLink) tavleLink.classList.add('active');
    const tavlePanel = document.getElementById('tab-tavle');
    if (tavlePanel) tavlePanel.classList.add('active');
  }

  if (!isAdmin) {
    document.querySelectorAll('.admin-only').forEach(el => {
      el.style.display = 'none';
    });
  }
}

// ════════════════════════════════════════════════════════
// STATE & MODALS
// ════════════════════════════════════════════════════════
let table = null;
let charts = {};
let currentEditId = null;
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

let activeFilter = 'alle';
let allPatients = [];
let mineOnly = (typeof localStorage !== 'undefined' && localStorage.getItem('mineOnly') === '1');
let boardMineFilter = false;

function isMine(p) {
  if (window.MY_FORSTEHJELPER_ID && p.forstehjelper
      && p.forstehjelper.id === window.MY_FORSTEHJELPER_ID) return true;
  if (window.MY_HELSEPERSONELL_ID && p.helsepersonell_ref
      && p.helsepersonell_ref.id === window.MY_HELSEPERSONELL_ID) return true;
  return false;
}

let activeStatTab = 'oversikt';
let fullStats = null;

let arkivStatsMode = false;
let arkivStatsMeta = null;

let forstehjelpere = [];
let helsepersonellListe = [];

const bsNew   = new bootstrap.Modal(document.getElementById('newModal'));
const bsEdit  = new bootstrap.Modal(document.getElementById('editModal'));

// ════════════════════════════════════════════════════════
// CLOCK & HELPERS
// ════════════════════════════════════════════════════════
const DAYS_NO = ['søndag', 'mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag'];

function updateClock() {
  const now = new Date();
  const el = document.getElementById('header-dt');
  if (!el) return;

  const dayStr = DAYS_NO[now.getDay()];
  const dateStr =
    String(now.getDate()).padStart(2, '0') + '.' +
    String(now.getMonth() + 1).padStart(2, '0') + '.' +
    now.getFullYear();

  const timeStr = now.toLocaleTimeString('no-NO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });

  el.innerHTML = `
    <div style="font-size:0.8rem;opacity:0.85;">${dayStr} ${dateStr}</div>
    <div style="font-size:1.35rem;font-weight:300;letter-spacing:0.07em;">${timeStr}</div>
  `;
}

setInterval(updateClock, 1000);
updateClock();

function nowStr() {
  const d = new Date();
  return [
    String(d.getDate()).padStart(2,'0'),
    String(d.getMonth()+1).padStart(2,'0'),
    d.getFullYear()
  ].join('.') + ' ' +
  [String(d.getHours()).padStart(2,'0'), String(d.getMinutes()).padStart(2,'0')].join(':');
}

function stamp(id) {
  const el = document.getElementById(id);
  if (el) el.value = nowStr();
}

function parseDt(s) {
  if (!s) return null;
  const m = s.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{2}):(\d{2})/);
  if (m) return new Date(+m[3], +m[2]-1, +m[1], +m[4], +m[5]);
  return null;
}

function fmtMin(m) {
  if (m == null || m < 0) return '–';
  const h = Math.floor(m / 60), min = Math.round(m % 60);
  return h > 0 ? `${h}t ${min}m` : `${min}m`;
}

function updateTotal() {
  const t1 = parseDt(document.getElementById('e-inntid')?.value);
  const t2 = parseDt(document.getElementById('e-utskrevet')?.value);
  const el = document.getElementById('e-total-time');
  if (!el) return;
  if (t1 && t2) {
    const m = (t2 - t1) / 60000;
    el.textContent = m >= 0 ? fmtMin(m) : '–';
  } else { el.textContent = '–'; }
}

document.getElementById('e-inntid')?.addEventListener('input', updateTotal);

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function _escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
