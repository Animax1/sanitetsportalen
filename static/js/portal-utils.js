// ════════════════════════════════════════════════════════
// PORTAL-UTILS — primitivene flere moduler deler
//
// Skilt ut fra patients-utils.js da statistikk ble egen modul. Grunnen er
// konkret: patients-utils.js gjør arbeid på toppnivå — den setter
// Chart.defaults og kaller `new bootstrap.Modal(document.getElementById(
// 'newModal'))`. På en side uten #newModal kaster den ved lasting. Fila kunne
// altså ikke bare lastes av statistikksiden også.
//
// Her ligger kun det som er trygt overalt: ingen DOM-oppslag på toppnivå,
// ingen avhengighet til Chart eller bootstrap.
//
// Escaping-hjelperne bor her fordi begge sidene bygger markup med innerHTML.
// patients/tests_xss_stats.py håndhever at de faktisk brukes.
// ════════════════════════════════════════════════════════

// ════════════════════════════════════════════════════════
// CSRF & API HELPERS  (Django-specific)
// ════════════════════════════════════════════════════════

// Rekkefølgen er ikke tilfeldig, og cookie-grenen er i praksis død:
// `CSRF_COOKIE_HTTPONLY = True` gjør at JS aldri får se cookien på dette
// nettstedet. Den beholdes for miljøer uten det flagget, men den som leser
// koden bør vite at den ikke er veien tokenet kommer.
//
// `<meta name="csrf-token">` settes av `base_portal.html` på HVER side som
// arver den. Den ble lagt inn for akkurat dette formålet, men ble aldri lest
// — så en ny modulside uten `#csrf-token-holder` fikk tom token, og hver
// skriving derfra ble avvist med en HTML-403 som `res.json()` kastet på.
// Brukeren så at ingenting skjedde. Det er fikset ved å lese den, ikke ved å
// legge en holder i hver mal: da ville neste modul gjort samme feil.
function getCsrfToken() {
  const name = 'csrftoken';
  const cookies = document.cookie.split(';');
  for (let c of cookies) {
    const trimmed = c.trim();
    if (trimmed.startsWith(name + '=')) {
      return decodeURIComponent(trimmed.slice(name.length + 1));
    }
  }

  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;

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

// escapeHtml() og _escHtml() returnerer tom streng for alt falsy, slik at
// tomme felt blir borte i stedet for å vises som "null". I tabellceller er
// det feil: tallet 0 er en helt gyldig verdi som skal vises. escHtmlValue()
// skiller derfor på «ikke satt» (null/undefined) og «falsy, men en verdi».
function escHtmlValue(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// Marker for HTML vi har bygget selv og som derfor skal settes inn uendret.
// Tabell-byggerne escaper alt de får inn; formatering som `<span>Ja</span>`
// må pakkes her for å slippe gjennom. Poenget er at det blir et bevisst valg
// per celle i stedet for en generell åpning for markup.
function trustedHtml(html) {
  return { __trustedHtml: String(html) };
}

// Gjør én celleverdi klar for innsetting: klarert markup slipper gjennom,
// alt annet escapes.
function cellHtml(v) {
  if (v && typeof v === 'object' && typeof v.__trustedHtml === 'string') {
    return v.__trustedHtml;
  }
  return escHtmlValue(v);
}

// ════════════════════════════════════════════════════════
// FORMATERING
// ════════════════════════════════════════════════════════

// Minutter → «2t 15m». Både pasienttabellen og statistikksiden viser
// varigheter, så helperen kan ikke bo i én av dem.
function fmtMin(m) {
  if (m == null || m < 0) return '–';
  const h = Math.floor(m / 60), min = Math.round(m % 60);
  return h > 0 ? `${h}t ${min}m` : `${min}m`;
}


// ISO-tidsstempel → «21:14». Bodde i oppdrag-sentral.js til enhetsskjermen
// også trengte den — og helpere begge sidene bruker flyttes hit, de kopieres
// ikke. Samme regel som for fmtMin.
function klokke(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('nb-NO', { hour: '2-digit', minute: '2-digit' });
}


// ════════════════════════════════════════════════════════
// HANDLERE VIA data-action (F5)
//
// Erstatter inline `onclick=`/`oninput=` i markup. Inline handlere krever
// `unsafe-inline` i CSP-ens script-src; skal det direktivet strammes, kan
// ingen handlere ligge i attributter.
//
// Delegert fra document, så markup som genereres senere (arkivlista,
// admin-registrene) virker uten at noe må kobles opp på nytt.
//
// Ligger i portal-utils.js fordi begge sidene bruker den: pasientsiden
// for filtre og admin-handlinger, statistikksiden for «tilbake til
// live-statistikk». Duplisering ville gitt to dispatchere som kan komme
// i utakt.
//
//   <button data-action="setFilter" data-arg="rod">
//   <button data-action="visArkivDetalj" data-id="12">
//
// `data-arg` sendes som streng, `data-id` som tall. Skillet er nødvendig:
// toggleForstehjelper() slår opp med `x.id === id`, og en streng ville gitt
// et stille ikke-treff i stedet for en feil.
// ════════════════════════════════════════════════════════

function _handlerArgument(el) {
  if (el.dataset.id !== undefined) return Number(el.dataset.id);
  return el.dataset.arg;
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;

  // Funksjonen kan bo i patients-admin.js, som kun lastes for admin.
  const handler = globalThis[el.dataset.action];
  if (typeof handler !== 'function') return;

  // Kun for lenker — en `type="submit"`-knapp skal fortsatt kunne sende skjema.
  if (el.tagName === 'A') e.preventDefault();

  handler(_handlerArgument(el));
});
