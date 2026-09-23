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

// ════════════════════════════════════════════════════════
// ER DET ET MENNESKE HER?
// ════════════════════════════════════════════════════════
//
// **«Pålogget» sier ingenting om tilstedeværelse** (André, 16. sep. 2026: «de
// trenger ikke være faktisk aktive og bruke nettsiden — det kan være en
// fane»). `SESSION_SAVE_EVERY_REQUEST` fornyer sesjonen ved hver forespørsel,
// og portalen poller seg selv hvert 5.–30. sekund. En glemt fane holder
// derfor sesjonen fersk i åtte timer, helt uten et menneske.
//
// **Løsningen er å la pollingen bære svaret.** Fana snakker med serveren
// uansett; den sender nå hvor lenge siden brukeren sist rørte siden. Ingen ny
// trafikk, ett felt på en forespørsel som alt går.
//
// Startverdien er sidelastingen: å åpne siden *er* en handling.
let sisteInteraksjon = Date.now();

//: Hendelsene som teller som «et menneske gjorde noe». `scroll` er **ikke**
//: med: den fyres av treghetsrulling på mobil lenge etter at fingeren er
//: borte, og av en side som laster inn. `visibilitychange` er med fordi det å
//: hente fram fana er en handling — det er nettopp da man kommer tilbake.
const INTERAKSJONER = ['pointerdown', 'keydown', 'wheel', 'touchstart'];

function merkInteraksjon() {
  sisteInteraksjon = Date.now();
}

function sekunderSidenInteraksjon(naa) {
  // Eget navn, ikke en linje inne i `apiFetch`: regelen skal kunne kjøres i
  // en test uten å gå gjennom nettverket.
  return Math.max(0, Math.round(((naa ?? Date.now()) - sisteInteraksjon) / 1000));
}

if (typeof document !== 'undefined' && document.addEventListener) {
  INTERAKSJONER.forEach((h) => document.addEventListener(h, merkInteraksjon,
                                                         { passive: true, capture: true }));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) merkInteraksjon();
  });
}


async function apiFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(options.headers || {}) };

  // Sekunder, ikke et tidspunkt: da slipper serveren å stole på klientens
  // klokke, som kan stå hvor som helst på en delt drifts-PC.
  headers['X-Portal-Inaktiv'] = String(sekunderSidenInteraksjon());

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
// **Det tomme førstevalget i et nedtrekk** (André, 23. sep. 2026): «øverste
// valg [bør] være "Velg..." fremfor at første verdi er synlig. Da ser det ut
// som det er dette som er lagret». Verdien er tom; et obligatorisk felt sier
// fra ved lagring, et valgfritt lagrer null. Én tekst for hele portalen.
// En funksjon og ikke en konstant: testharnessene henter funksjoner.
function velgTekst() {
  return 'Velg…';
}

function velgValg(valgt) {
  return `<option value=""${valgt ? '' : ' selected'}>${velgTekst()}</option>`;
}


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
  // Rund av til hele minutter FØR timene deles ut: 179,9 min var «2t 60m»
  // (funnet i bemanningsfanen 21. sep. 2026), fordi timene ble regnet av
  // 179,9 og minuttene av resten.
  const tot = Math.round(m);
  const h = Math.floor(tot / 60), min = tot % 60;
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

function klikkSkalKjore(el) {
  // **Et element som melder sin egen hendelse skal ikke også fyre på klikk.**
  // Nedtrekkene i vaktlistas ressurstabell er `<select data-action="..."
  // data-hendelse="change">`. Klikket som åpnet lista traff klikkdelegeringen
  // under, som kalte handlingen uten felt og verdi, lagret ingenting og tegnet
  // panelet på nytt — så den åpne lista forsvant i det øyeblikket den kom.
  // Symptomet var «en kort popup som blinker bort»; årsaken var to lyttere på
  // samme element.
  //
  // Regelen står som en egen funksjon fordi den er hele forskjellen, og fordi
  // en anonym `if` inne i en lytter ikke lar seg kjøre i en test.
  return !el.dataset.hendelse;
}


function hendelseArgumenter(el) {
  // Cellene i vaktlistas ressurstabell bærer `data-felt`, og handlingen
  // deres vil ha (id, felt, verdi). Alt annet får ett argument, som ved
  // klikk. Regelen er en egen funksjon av samme grunn som `klikkSkalKjore`.
  if (el.dataset.felt !== undefined) {
    return [Number(el.dataset.id), el.dataset.felt, el.value];
  }
  return [_handlerArgument(el)];
}

function haandterHendelse(e) {
  // **`data-hendelse="change"` er den andre lytteren.** Klikkdelegeringen
  // under hopper over slike elementer med vilje (`klikkSkalKjore`), og fram
  // til 12. sep. 2026 fantes det ingen delegering for `change` utenfor
  // vaktlistas ressurspanel: korpsvelgeren i vaktlinja hadde riktig markup
  // og en handling som virket når den ble kalt — og ingen kalte den.
  const el = e.target.closest('[data-action][data-hendelse="change"]');
  if (!el) return;
  const handler = globalThis[el.dataset.action];
  if (typeof handler !== 'function') return;
  handler(...hendelseArgumenter(el));
}

document.addEventListener('change', haandterHendelse);

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  if (!klikkSkalKjore(el)) return;

  // Funksjonen kan bo i patients-admin.js, som kun lastes for admin.
  const handler = globalThis[el.dataset.action];
  if (typeof handler !== 'function') return;

  // Kun for lenker — en `type="submit"`-knapp skal fortsatt kunne sende skjema.
  if (el.tagName === 'A') e.preventDefault();

  handler(_handlerArgument(el));
});


// ── Fokus ut av modalen før den skjules (14. sep. 2026) ─────────────────────
//
// Bootstrap 5.3 setter `aria-hidden="true"` på modalen når den lukkes, men
// flytter ikke fokus ut av den først. Lukker du med krysset, står fokus
// fortsatt på `.btn-close` *inne i* det som nettopp ble skjult for
// skjermlesere — og nettleseren melder fra:
//
//   Blocked aria-hidden on an element because its descendant retained focus.
//
// Det er ikke bare støy i konsollen: en skjermleserbruker mister da
// fokuspunktet sitt i det modalen lukkes, og lander ingen steder.
//
// `hide.bs.modal` bobler, så én lytter her dekker hver modal på hver side —
// og det er poenget med å legge den i fila alle sidene laster. Alternativet
// Bootstrap peker på, `inert`, måtte vært satt og fjernet per modal, altså
// samme feil gjentatt ett sted per vindu.
// Navngitt og ikke anonym, av samme grunn som `klikkSkalKjore()`: en `if`
// inne i en lytter lar seg ikke kjøre i en test.
function slippFokusFoerSkjul(modal, aktiv) {
  if (!modal || !aktiv) return false;
  if (!modal.contains(aktiv)) return false;
  if (typeof aktiv.blur !== 'function') return false;
  aktiv.blur();
  return true;
}

document.addEventListener('hide.bs.modal', (e) => {
  slippFokusFoerSkjul(e.target, document.activeElement);
});


// ── Skjemaer som skal starte blanke (André, 19. sep. 2026) ──────────────────
//
// «Hvis man lagrer et skjema og får valideringsfeil, og så åpner det igjen så
// bør det nullstilles.» De fleste modalene fylles av JS *før* de vises, og
// er alt riktige. Resten åpnes med `data-bs-toggle` og har ingen kode på
// åpningsveien — der lå de forsøkte verdiene igjen, med feilmeldingen fra
// forrige forsøk under. Hjelperen her nullstiller ved **lukking**, ikke ved
// åpning: `show.bs.modal` fyrer *inne i* `.show()`, og et skjema som JS
// fyller rett før det viser, ville da fått verdiene sine vasket bort.
//
// Bare felter som er navngitt nullstilles. Modaler med innstillinger som
// hentes fra serveren (bilinnstillingene, timetaket, grensene) skal ikke
// blankes — en blank innstilling er ikke det samme som den lagrede.
function nullstillFelter(feltIder, feilId) {
  (feltIder || []).forEach((id) => {
    const felt = document.getElementById(id);
    if (!felt) return;
    if (felt.type === 'checkbox' || felt.type === 'radio') felt.checked = Boolean(felt.defaultChecked);
    else if (felt.tagName === 'SELECT') felt.selectedIndex = 0;
    else felt.value = felt.defaultValue || '';
    if (felt.classList) felt.classList.remove('is-invalid');
  });
  const feil = feilId ? document.getElementById(feilId) : null;
  if (feil) {
    feil.textContent = '';
    if (feil.classList) feil.classList.add('d-none');
  }
}

function nullstillModalVedLukking(modalId, feltIder, feilId) {
  const el = document.getElementById(modalId);
  if (!el) return false;
  el.addEventListener('hidden.bs.modal', () => nullstillFelter(feltIder, feilId));
  return true;
}
