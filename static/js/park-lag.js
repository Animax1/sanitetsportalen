/* Parksiden — lagets registrering, uten innlogging (docs/FORSLAG_PARK.md §4).
 *
 * Lastes **kun** av templates/park/lag.html, og ikke sammen med portal-utils.js:
 * siden har ingen sesjon, og portal-utils sender portalens egne headere.
 *
 * Reglene som avgjør noe står som egne funksjoner (park*), så de kan kjøres i
 * node (park/tests_js.py): hvilket lag som huskes, hvilket sted som
 * forhåndsvelges og hva linja under sier, hva som tømmes etter en registrering,
 * og hvor lenge «Angre» står. Markup bygges med createElement og textContent —
 * ingen mal-strenger med tagger, så ingen navn kan bli til markup.
 */

const PARK_LAGRING = {token: 'park.token', telefon: 'park.telefon', lag: 'park.lag',
                      sted: 'park.sted', angre: 'park.angre'};

/* ── Rene regler ─────────────────────────────────────────────────────────── */

/* Tokenet: fragmentet vinner over det lagrede — en ny lenke fra tiltakskortet
 * skal erstatte en gammel som ligger igjen på telefonen. */
function parkLesToken(hash, lagret) {
  const fra = String(hash || '').replace(/^#/, '').trim();
  if (fra) return fra;
  return lagret ? String(lagret) : '';
}

/* Laget huskes på **navn**, ikke ID: vaktlistas ressurser er nye rader for
 * hver vaktliste, og en ID ville vært glemt neste vakt (B4). */
function parkVelgLag(lag, husketNavn) {
  if (!husketNavn) return null;
  const treff = (lag || []).find((l) => l.navn === husketNavn);
  return treff ? treff.id : null;
}

/* Forhåndsvalget av sted (§5.1, B19). Serveren har alt avgjort «nyeste vinner»
 * mellom KO-tavla og lagets siste registrering — med sin egen klokke. Telefonens
 * minne brukes bare når serveren ikke har noe, og aldri i en sammenligning:
 * telefonklokka kan stå hvor som helst. */
function parkVelgSted(server, husketNavn, steder) {
  const liste = steder || [];
  if (server && server.sted != null && liste.some((s) => s.id === server.sted)) {
    return {id: server.sted, kilde: server.kilde, tid: server.tid || null};
  }
  const husket = husketNavn ? liste.find((s) => s.navn === husketNavn) : null;
  if (husket) return {id: husket.id, kilde: 'telefon', tid: null};
  return {id: null, kilde: 'ingen', tid: null};
}

/* Linja under stedet: *hvorfor* det står der. Et ferdig utfylt felt blir ikke
 * lest; en linje som sier hvor valget kom fra, blir det oftere (§5.1). */
function parkKildeTekst(kilde, tid) {
  const kl = tid ? parkKlokke(tid) : '';
  if (kilde === 'ko') return kl ? `Fra KO-tavla ${kl}` : 'Fra KO-tavla';
  if (kilde === 'registrering') return kl ? `Sist registrert ${kl}` : 'Sist registrert';
  if (kilde === 'telefon') return 'Sist valgt på denne telefonen';
  return '';
}

function parkKlokke(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('nb-NO', {hour: '2-digit', minute: '2-digit',
                                         timeZone: 'Europe/Oslo'});
}

/* Alt må være valgt, og antallet må være et helt tall i [1, 99]. */
function parkKanRegistrere(v) {
  if (!v || !v.lag || !v.sted || !v.problemstilling || !v.utfall) return false;
  const n = Number(v.antall);
  return Number.isInteger(n) && n >= 1 && n <= 99;
}

/* Etter en registrering: lag og sted står, resten tømmes (B9). */
function parkNesteSkjema(v) {
  return {lag: v.lag, sted: v.sted, problemstilling: null, antall: 1, utfall: null};
}

/* Kroppen til POST-en. `forhandsvalg_endret` er målingen (B21): stod det et
 * forhåndsvalg, og valgte laget noe annet? */
function parkKropp(v, forhandsvalg, nokkel) {
  const hadde = forhandsvalg && forhandsvalg.id != null;
  return {
    lag: v.lag, sted: v.sted, problemstilling: v.problemstilling,
    antall: Number(v.antall), utfall: v.utfall, idempotency_key: nokkel,
    forhandsvalg_kilde: hadde ? forhandsvalg.kilde : 'ingen',
    forhandsvalg_endret: hadde ? Number(v.sted) !== Number(forhandsvalg.id) : false,
  };
}

/* Sekunder igjen av angrefristen, aldri under null. */
function parkAngreSekunder(angreTil, naaMs) {
  const til = new Date(angreTil).getTime();
  if (Number.isNaN(til)) return 0;
  return Math.max(0, Math.floor((til - naaMs) / 1000));
}

/* Kvitteringene som fortsatt kan angres — de utløpte ryddes bort. */
function parkAktiveAngre(liste, naaMs) {
  return (liste || []).filter((k) => parkAngreSekunder(k.angre_til, naaMs) > 0);
}

function parkKvitteringstekst(k) {
  const antall = Number(k.antall) > 1 ? `${k.antall} × ` : '';
  return `${parkKlokke(k.registrert_at)} · ${antall}${k.problemstilling} · ${k.sted} · ${k.utfall}`;
}

/* En UUID. `crypto.randomUUID` krever sikker kontekst; reserven bygger en v4
 * av `getRandomValues`, som finnes overalt. */
function parkUuid() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  const b = globalThis.crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/* ── Lagring: kan kaste i privat modus, og siden skal virke uten den ─────── */

function parkLes(nokkel) {
  try { return globalThis.localStorage.getItem(nokkel); } catch (e) { return null; }
}

function parkSkriv(nokkel, verdi) {
  try {
    if (verdi == null) globalThis.localStorage.removeItem(nokkel);
    else globalThis.localStorage.setItem(nokkel, verdi);
  } catch (e) { /* uten lagring huskes ingenting — siden virker likevel */ }
}

/* ── Tilstand og DOM ─────────────────────────────────────────────────────── */

const parkTilstand = {token: '', telefon: '', oppsett: null, forhandsvalg: null,
                      nokkel: null, sender: false, angre: []};

function parkEl(id) { return document.getElementById(id); }

function parkFyllValg(select, rader, tomTekst) {
  select.replaceChildren();
  const tom = document.createElement('option');
  tom.value = '';
  tom.textContent = tomTekst;
  select.appendChild(tom);
  for (const r of rader) {
    const o = document.createElement('option');
    o.value = String(r.id);
    o.textContent = r.navn;
    select.appendChild(o);
  }
}

function parkMelding(tekst) {
  const el = parkEl('park-melding');
  el.textContent = tekst || '';
  el.classList.toggle('d-none', !tekst);
}

/* Glem tokenet når serveren sier nei (sikkerhetsgjennomgangen 28. sep. 2026).
   Lenker brukes på tvers av vakter (B18): uten dette fikk en telefon fra i fjor
   tilgang igjen den dagen samme lenke ble åpnet på nytt. Serveren gir med vilje
   samme 403 for alle avslag — også «ikke åpnet ennå» — så en telefon som kommer
   for tidlig, må åpne lenken fra tiltakskortet igjen. Det er den vanlige veien inn. */
function parkSkalGlemmeTokenet(status) {
  return status === 403;
}

async function parkKall(sti, metode, kropp) {
  const svar = await fetch(sti, {
    method: metode,
    headers: {'X-Park-Lenke': parkTilstand.token, 'X-Park-Telefon': parkTilstand.telefon,
              'Content-Type': 'application/json', 'Accept': 'application/json'},
    body: kropp ? JSON.stringify(kropp) : undefined,
    credentials: 'omit',
    cache: 'no-store',
  });
  let data = {};
  try { data = await svar.json(); } catch (e) { data = {}; }
  if (parkSkalGlemmeTokenet(svar.status)) parkSkriv(PARK_LAGRING.token, null);
  return {ok: svar.ok, status: svar.status, data};
}

function parkValgt() {
  const tall = (id) => (parkEl(id).value ? Number(parkEl(id).value) : null);
  return {lag: tall('park-lag'), sted: tall('park-sted'),
          problemstilling: tall('park-problemstilling'),
          antall: Number(parkEl('park-antall').value), utfall: tall('park-utfall')};
}

async function parkHentSted() {
  const lag = parkEl('park-lag').value;
  parkTilstand.forhandsvalg = null;
  parkEl('park-sted-kilde').textContent = '';
  if (!lag) return;
  let server = null;
  try {
    const svar = await parkKall(`/lag/r/api/sted/?lag=${encodeURIComponent(lag)}`, 'GET');
    if (svar.ok) server = svar.data;
  } catch (e) { server = null; }
  const valg = parkVelgSted(server, parkLes(PARK_LAGRING.sted), parkTilstand.oppsett.steder);
  parkTilstand.forhandsvalg = valg;
  parkEl('park-sted').value = valg.id != null ? String(valg.id) : '';
  parkEl('park-sted-kilde').textContent = parkKildeTekst(valg.kilde, valg.tid);
}

function parkTegnKvitteringer() {
  const boks = parkEl('park-kvitteringer');
  const naa = Date.now();
  parkTilstand.angre = parkAktiveAngre(parkTilstand.angre, naa);
  parkSkriv(PARK_LAGRING.angre, JSON.stringify(parkTilstand.angre));
  boks.replaceChildren();
  for (const k of parkTilstand.angre.slice(0, 3)) {
    const rad = document.createElement('div');
    rad.className = 'park-kort park-kvittering mb-2 d-flex align-items-center gap-2';
    const tekst = document.createElement('div');
    tekst.className = 'flex-grow-1 small';
    const topp = document.createElement('div');
    topp.className = 'fw-semibold';
    topp.textContent = `Registrert — ${k.lag}`;
    const linje = document.createElement('div');
    linje.textContent = parkKvitteringstekst(k);
    tekst.append(topp, linje);
    const knapp = document.createElement('button');
    knapp.type = 'button';
    knapp.className = 'btn btn-sm btn-outline-light';
    const s = parkAngreSekunder(k.angre_til, naa);
    knapp.textContent = `Angre (${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')})`;
    knapp.addEventListener('click', () => parkAngre(k.nokkel));
    rad.append(tekst, knapp);
    boks.appendChild(rad);
  }
}

async function parkAngre(nokkel) {
  let svar;
  try { svar = await parkKall('/lag/r/api/angre/', 'POST', {idempotency_key: nokkel}); } catch (e) {
    parkMelding('Ikke angret — ingen forbindelse. Prøv igjen.');
    return;
  }
  parkTilstand.angre = parkTilstand.angre.filter((k) => k.nokkel !== nokkel);
  parkMelding(svar.ok ? '' : (svar.data.message || 'Kunne ikke angre.'));
  parkTegnKvitteringer();
}

async function parkRegistrer(e) {
  e.preventDefault();
  if (parkTilstand.sender) return;
  const v = parkValgt();
  if (!parkKanRegistrere(v)) {
    parkMelding('Velg lag, sted, problemstilling og utfall, og et antall fra 1 til 99.');
    return;
  }
  // Samme nøkkel til sendingen lykkes: en ny runde etter et brudd er da den
  // samme registreringen, ikke en til.
  if (!parkTilstand.nokkel) parkTilstand.nokkel = parkUuid();
  parkTilstand.sender = true;
  parkEl('park-registrer').disabled = true;
  let svar;
  try {
    svar = await parkKall('/lag/r/api/registrer/', 'POST',
                          parkKropp(v, parkTilstand.forhandsvalg, parkTilstand.nokkel));
  } catch (feil) {
    svar = null;
  }
  parkTilstand.sender = false;
  parkEl('park-registrer').disabled = false;
  if (!svar) {
    // Ingen offline (B14): siden later aldri som den lagret.
    parkMelding('Ikke lagret — ingen forbindelse. Valgene står; prøv igjen.');
    return;
  }
  if (!svar.ok) {
    parkMelding(svar.data.message || 'Ikke lagret. Prøv igjen.');
    return;
  }
  parkMelding('');
  const k = svar.data.kvittering;
  parkTilstand.angre.unshift({...k, nokkel: parkTilstand.nokkel});
  parkTilstand.nokkel = null;
  const neste = parkNesteSkjema(v);
  parkEl('park-problemstilling').value = '';
  parkEl('park-utfall').value = '';
  parkEl('park-antall').value = String(neste.antall);
  // Det laget nettopp registrerte fra er nå det nyeste stedet.
  parkTilstand.forhandsvalg = {id: v.sted, kilde: 'registrering', tid: k.registrert_at};
  parkEl('park-sted-kilde').textContent = parkKildeTekst('registrering', k.registrert_at);
  parkTegnKvitteringer();
  // Telleren er et tall, ikke data — og det som viser laget at det kommer fram.
  parkEl('park-vakt').textContent = `${parkTilstand.oppsett.vakt} · ${k.lag}: ${k.antall_for_laget} registrert`;
}

async function parkStart() {
  parkTilstand.token = parkLesToken(globalThis.location.hash, parkLes(PARK_LAGRING.token));
  // Tokenet ut av adressefeltet (§4.6): fragmentet når aldri serveren, men
  // nettleserloggen lagrer hele adressen.
  if (globalThis.location.hash) {
    globalThis.history.replaceState(null, '', globalThis.location.pathname);
  }
  if (!parkTilstand.token) {
    parkMelding('Åpne lenken fra tiltakskortet for å registrere.');
    return;
  }
  parkSkriv(PARK_LAGRING.token, parkTilstand.token);
  parkTilstand.telefon = parkLes(PARK_LAGRING.telefon) || parkUuid();
  parkSkriv(PARK_LAGRING.telefon, parkTilstand.telefon);
  try { parkTilstand.angre = JSON.parse(parkLes(PARK_LAGRING.angre) || '[]'); } catch (e) {
    parkTilstand.angre = [];
  }

  let svar;
  try { svar = await parkKall('/lag/r/api/oppsett/', 'GET'); } catch (e) {
    parkMelding('Ingen forbindelse. Last siden på nytt når du har dekning.');
    return;
  }
  if (!svar.ok) {
    parkMelding(svar.data.message || 'Lenken er ikke åpen.');
    return;
  }
  const o = svar.data;
  parkTilstand.oppsett = o;
  parkEl('park-vakt').textContent = o.vakt;
  parkFyllValg(parkEl('park-lag'), o.lag, 'Velg lag');
  parkFyllValg(parkEl('park-sted'), o.steder, 'Velg sted');
  parkFyllValg(parkEl('park-problemstilling'), o.problemstillinger, 'Velg problemstilling');
  parkFyllValg(parkEl('park-utfall'), o.utfall, 'Velg utfall');
  if (!o.lag.length) parkMelding('Ingen lag er satt opp for registrering på denne vakta. Si fra til KO.');

  const lag = parkVelgLag(o.lag, parkLes(PARK_LAGRING.lag));
  if (lag != null) parkEl('park-lag').value = String(lag);
  parkEl('park-skjema').classList.remove('d-none');
  parkTegnKvitteringer();
  await parkHentSted();

  parkEl('park-lag').addEventListener('change', () => {
    const valgt = o.lag.find((l) => String(l.id) === parkEl('park-lag').value);
    parkSkriv(PARK_LAGRING.lag, valgt ? valgt.navn : null);
    parkHentSted();
  });
  parkEl('park-sted').addEventListener('change', () => {
    const valgt = o.steder.find((s) => String(s.id) === parkEl('park-sted').value);
    parkSkriv(PARK_LAGRING.sted, valgt ? valgt.navn : null);
    parkEl('park-sted-kilde').textContent = '';
  });
  const antall = parkEl('park-antall');
  const flytt = (d) => {
    const n = Math.min(99, Math.max(1, (Number(antall.value) || 1) + d));
    antall.value = String(n);
  };
  parkEl('park-antall-ned').addEventListener('click', () => flytt(-1));
  parkEl('park-antall-opp').addEventListener('click', () => flytt(1));
  parkEl('park-skjema').addEventListener('submit', parkRegistrer);
  setInterval(parkTegnKvitteringer, 1000);
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', parkStart);
}
