/* Oppsettet på /lag/ — lenkene, registreringene og verdimengdene (pulje 2).
 *
 * Lastes **kun** av templates/park/index.html, for skriv_leder og admin, etter
 * portal-utils.js (apiFetch, withSubmitGuard). Se park/CLAUDE.md.
 *
 * Reglene som avgjør noe står som egne funksjoner (park*), så de kan kjøres i
 * node (park/tests_js.py): hvem som setter opp utfallene, hva en lenke er nå,
 * og hvordan tidspunktene går mellom skjemaet og serveren. Markup bygges med
 * createElement og textContent — ingen mal-strenger med tagger.
 */

/* ── Rene regler ─────────────────────────────────────────────────────────── */

/* Utfallene er global admin (B7); problemstillingene skriv_leder (B6). */
function parkKanSetteOppUtfall(tilgang) {
  return !!(tilgang && tilgang.admin === true);
}

/* Å slette en rad fra en verdimengde er global admin, som i core.verdilister. */
function parkKanSletteVerdi(tilgang) {
  return !!(tilgang && tilgang.admin === true);
}

/* Hva lenken er akkurat nå — det lista sier ved navnet. */
function parkLenkeStatus(lenke, naaMs) {
  if (lenke.fjernet) return 'Fjernet';
  const fra = Date.parse(lenke.aapen_fra);
  const til = Date.parse(lenke.aapen_til);
  if (naaMs < fra) return 'Ikke åpnet ennå';
  if (naaMs >= til) return 'Stengt';
  return 'Åpen';
}

/* Verdien et `datetime-local`-felt skal ha for et tidspunkt: lokal tid, uten
 * sone. Serveren leser en slik streng som norsk tid (`make_aware`). */
function parkLokalFelt(ms) {
  const d = new Date(ms);
  const to = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${to(d.getMonth() + 1)}-${to(d.getDate())}T${to(d.getHours())}:${to(d.getMinutes())}`;
}

/* Standardoppetiden for en ny lenke: fra nå, tre døgn. En lenke uten slutt er
 * en lenke noen glemmer — derfor er begge feltene fylt, ikke tomme. */
function parkStandardOppetid(naaMs) {
  return {fra: parkLokalFelt(naaMs), til: parkLokalFelt(naaMs + 3 * 24 * 3600 * 1000)};
}

/* Med år: en lenke lever på tvers av vakter (B18), og «1.1.–1.1.» sier ikke
 * hvilket år den stenger. */
function parkDato(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('nb-NO', {day: '2-digit', month: '2-digit', year: 'numeric',
                                    hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Oslo'});
}

/* Registreringene som passer filteret. Hvert ord må finnes i lag, sted,
 * problemstilling eller utfall — «sandnes kramper» finner Sandnes 2.1s
 * kramper, ikke alt fra Sandnes og alle kramper. */
function parkFiltrer(rader, tekst) {
  const ord = String(tekst || '').toLocaleLowerCase('nb').split(/\s+/).filter(Boolean);
  if (!ord.length) return rader;
  return rader.filter((r) => {
    const felt = [r.lag, r.sted, r.problemstilling, r.utfall].join(' ').toLocaleLowerCase('nb');
    return ord.every((o) => felt.includes(o));
  });
}

/* Hva telleren sier. Et filter skal aldri skjule noe stille (CLAUDE.md), og
 * en tegnegrense heller ikke: står det ikke hvor mange som ikke vises, tror
 * man at lista er hele vakta. */
function parkTellertekst(vist, treff, totalt, filtrert) {
  if (!totalt) return '';
  if (vist < treff) return `Viser ${vist} av ${treff}${filtrert ? ` treff (${totalt} i alt)` : ''} — filtrer for å finne resten`;
  return filtrert ? `${treff} av ${totalt}` : `${totalt} registreringer`;
}

/* Kopier til utklippstavla. Svarer 'kopiert' når det gikk, 'merket' når
 * nettleseren nektet (eldre nettleser, ikke HTTPS) og teksten i stedet er
 * merket så brukeren kan kopiere selv. Svaret styrer hva siden sier — en
 * knapp som sier «Kopiert» uten at noe ble kopiert, er verre enn ingen. */
async function parkKopier(tekst, utklipp, merk) {
  try {
    // Uten utklippstavle kaster kallet selv (TypeError), og da er svaret likt.
    await utklipp.writeText(tekst);
    return 'kopiert';
  } catch (e) {
    if (typeof merk === 'function') merk();
    return 'merket';
  }
}

function parkTid(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('nb-NO', {day: '2-digit', month: '2-digit', hour: '2-digit',
                                    minute: '2-digit', timeZone: 'Europe/Oslo'});
}

/* ── DOM-hjelpere ────────────────────────────────────────────────────────── */

function parkNode(tag, attr, ...barn) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attr || {})) {
    if (k === 'tekst') e.textContent = v;
    else if (k === 'klikk') e.addEventListener('click', v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const b of barn) if (b != null) e.append(b);
  return e;
}

function parkFeil(tekst) {
  const boks = document.getElementById('park-feil');
  boks.textContent = tekst || '';
  boks.classList.toggle('d-none', !tekst);
}

async function parkApi(url, metode, kropp) {
  const res = await apiFetch(url, {method: metode || 'GET',
                                   body: kropp ? JSON.stringify(kropp) : undefined});
  const d = await res.json().catch(() => ({}));
  return {ok: res.ok, status: res.status, d};
}

function parkTabell(koloner, rader) {
  const hode = parkNode('tr', {}, ...koloner.map((k) => parkNode('th', {tekst: k})));
  return parkNode('table', {class: 'table table-sm table-dark align-middle mb-0'},
                parkNode('thead', {}, hode), parkNode('tbody', {}, ...rader));
}

/* ── Lenkene ─────────────────────────────────────────────────────────────── */

let parkLenkene = [];

async function parkHentLenker() {
  const {ok, d} = await parkApi('/lag/api/lenker/');
  if (!ok) { parkFeil(d.message || 'Kunne ikke hente lenkene.'); return; }
  parkLenkene = d.data;
  const naa = Date.now();
  const rader = parkLenkene.map((l) => {
    const fjern = l.fjernet ? '' : parkNode('button', {
      class: 'btn btn-sm btn-outline-danger', type: 'button', tekst: 'Fjern',
      klikk: () => parkFjernLenke(l)});
    return parkNode('tr', {class: l.fjernet ? 'text-decoration-line-through' : null},
      parkNode('td', {tekst: l.navn}),
      parkNode('td', {tekst: `${parkDato(l.aapen_fra)} – ${parkDato(l.aapen_til)}`}),
      parkNode('td', {tekst: parkLenkeStatus(l, naa)}),
      parkNode('td', {tekst: String(l.antall)}),
      parkNode('td', {tekst: l.sist_brukt_at ? parkTid(l.sist_brukt_at) : 'Aldri'}),
      parkNode('td', {class: 'text-end'}, fjern));
  });
  const boks = document.getElementById('park-lenker');
  boks.replaceChildren(rader.length
    ? parkTabell(['Hvor', 'Oppetid', 'Nå', 'Registreringer', 'Sist brukt', ''], rader)
    : parkNode('p', {class: 'small text-muted', tekst: 'Ingen lenker ennå.'}));
  const valg = document.getElementById('park-rydd-lenke');
  valg.replaceChildren(...parkLenkene.map((l) => parkNode('option', {value: l.id, tekst: l.navn})));
}

async function parkLagLenke(e) {
  e.preventDefault();
  await withSubmitGuard('park-lenke-knapp', async () => {
    parkFeil('');
    const {ok, d} = await parkApi('/lag/api/lenker/', 'POST', {
      navn: document.getElementById('park-lenke-navn').value,
      aapen_fra: document.getElementById('park-lenke-fra').value,
      aapen_til: document.getElementById('park-lenke-til').value,
    });
    if (!ok) { parkFeil(d.message || 'Kunne ikke lage lenken.'); return; }
    // Adressen vises én gang og lagres ikke — heller ikke i nettleseren.
    const boks = document.getElementById('park-ny-adresse');
    // Hele feltet og knappen kopierer (André, 28. sep. 2026: «trykker på
    // feltet så kopieres hele linken … det må vises at det ble kopiert»).
    const felt = parkNode('input', {class: 'form-control form-control-sm', readonly: true,
                                    value: d.adresse, title: 'Trykk for å kopiere',
                                    style: 'cursor: pointer;'});
    const kopier = parkNode('button', {class: 'btn btn-sm btn-dark', type: 'button', tekst: 'Kopier'});
    const status = parkNode('div', {class: 'small mt-1', 'aria-live': 'polite'});
    const kopierNaa = async () => {
      const utfall = await parkKopier(d.adresse, navigator.clipboard, () => felt.select());
      if (utfall === 'kopiert') {
        kopier.textContent = 'Kopiert ✓';
        kopier.className = 'btn btn-sm btn-success';
        felt.classList.add('is-valid');
        status.textContent = 'Lenken er kopiert — lim den inn i tiltakskortet.';
      } else {
        status.textContent = 'Lenken er merket — kopier den selv (Ctrl+C, eller hold fingeren på den).';
      }
    };
    felt.addEventListener('click', kopierNaa);
    kopier.addEventListener('click', kopierNaa);
    boks.replaceChildren(
      parkNode('div', {class: 'fw-semibold mb-1',
                     tekst: `«${d.data.navn}» er laget. Legg adressen i tiltakskortet nå — den vises ikke igjen.`}),
      parkNode('div', {class: 'input-group input-group-sm'}, felt, kopier), status);
    boks.classList.remove('d-none');
    document.getElementById('park-lenke-navn').value = '';
    await parkHentLenker();
  });
}

async function parkFjernLenke(lenke) {
  if (!confirm(`Fjerne «${lenke.navn}»? Den slutter å virke med en gang, også i tiltakskortet.`)) return;
  const {ok, d} = await parkApi(`/lag/api/lenker/${lenke.id}/fjern/`, 'POST', {confirm: true});
  if (!ok) { parkFeil(d.message || 'Kunne ikke fjerne lenken.'); return; }
  await parkHentLenker();
}

/* ── Stedene lagene ser ──────────────────────────────────────────────────── */

async function parkHentSteder() {
  const {ok, d} = await parkApi('/lag/api/steder/');
  if (!ok) { parkFeil(d.message || 'Kunne ikke hente stedene.'); return; }
  const linjer = d.data.map((st) => parkNode('li', {
    class: `list-group-item d-flex justify-content-between align-items-center gap-2${st.skjult ? ' text-muted' : ''}`},
    parkNode('span', {tekst: st.skjult ? `${st.navn} — skjult for lagene` : st.navn}),
    parkNode('button', {class: `btn btn-sm ${st.skjult ? 'btn-outline-success' : 'btn-outline-secondary'}`,
                        type: 'button', tekst: st.skjult ? 'Vis for lagene' : 'Skjul for lagene',
                        klikk: () => parkSettSkjult(st.id, !st.skjult)})));
  document.getElementById('park-steder').replaceChildren(linjer.length
    ? parkNode('ul', {class: 'list-group list-group-flush'}, ...linjer)
    : parkNode('p', {class: 'small text-muted', tekst: 'Ingen aktive steder i oppdragsmodulen.'}));
}

async function parkSettSkjult(id, skjult) {
  const {ok, d} = await parkApi(`/lag/api/steder/${id}/skjul/`, 'POST', {skjult});
  if (!ok) { parkFeil(d.message || 'Kunne ikke endre stedet.'); return; }
  parkFeil('');
  await parkHentSteder();
}

/* ── Registreringene ─────────────────────────────────────────────────────── */

/* Hvor mange rader som tegnes. Hele vakta hentes, så filteret søker i alt;
 * men 1 500 rader i DOM-en gjør siden treg, og ingen leser dem uten å filtrere. */
const PARK_TEGN_MAKS = 200;
let parkRegistreringene = [];

async function parkHentRegistreringer() {
  const {ok, d} = await parkApi('/lag/api/registreringer/');
  if (!ok) { parkFeil(d.message || 'Kunne ikke hente registreringene.'); return; }
  document.getElementById('park-reg-vakt').textContent =
    `— ${d.vakt}${d.data.length >= d.maks ? ` (de siste ${d.maks})` : ''}`;
  parkRegistreringene = d.data;
  parkTegnRegistreringer();
}

function parkTegnRegistreringer() {
  const filter = document.getElementById('park-reg-filter').value;
  const treff = parkFiltrer(parkRegistreringene, filter);
  const synlige = treff.slice(0, PARK_TEGN_MAKS);
  document.getElementById('park-reg-teller').textContent = parkTellertekst(
    synlige.length, treff.length, parkRegistreringene.length, !!filter.trim());
  const rader = synlige.map((r) => {
    const slett = r.slettet
      ? parkNode('span', {class: 'small text-muted', tekst: `Slettet av ${r.slettet_av}: ${r.slettet_grunn}`})
      : parkNode('button', {class: 'btn btn-sm btn-outline-danger', type: 'button', tekst: 'Slett',
                          klikk: () => parkSlettRegistrering(r)});
    return parkNode('tr', {class: r.slettet ? 'text-decoration-line-through text-muted' : null},
      parkNode('td', {tekst: parkTid(r.registrert_at)}), parkNode('td', {tekst: r.lag}),
      parkNode('td', {tekst: r.sted}), parkNode('td', {tekst: r.problemstilling}),
      parkNode('td', {tekst: String(r.antall)}), parkNode('td', {tekst: r.utfall}),
      parkNode('td', {class: 'text-end'}, slett));
  });
  const tabell = parkTabell(['Tid', 'Lag', 'Sted', 'Problemstilling', 'Antall', 'Utfall', ''], rader);
  // Overskriften står fast når lista rulles i sin egen boks.
  tabell.querySelector('thead').setAttribute('style', 'position: sticky; top: 0; z-index: 1;');
  const tom = parkRegistreringene.length ? 'Ingen treff.' : 'Ingen registreringer på denne vakta.';
  document.getElementById('park-registreringer').replaceChildren(rader.length
    ? tabell : parkNode('p', {class: 'small text-muted', tekst: tom}));
}

/* Minimeringen huskes per nettleser — samme valg som KOs grupper. */
function parkSettRegSkjult(skjult) {
  document.getElementById('park-reg-innhold').classList.toggle('d-none', skjult);
  const knapp = document.getElementById('park-reg-bryter');
  knapp.textContent = skjult ? 'Vis' : 'Skjul';
  knapp.setAttribute('aria-expanded', String(!skjult));
  try { globalThis.localStorage.setItem('park.reg.skjult', skjult ? '1' : '0'); } catch (e) { /* uten lagring huskes det ikke */ }
}

async function parkSlettRegistrering(r) {
  const grunn = prompt(`Slette «${r.antall} × ${r.problemstilling}» fra ${r.lag}? Skriv hvorfor:`);
  if (grunn == null) return;
  const {ok, d} = await parkApi(`/lag/api/registreringer/${r.id}/slett/`, 'POST', {grunn});
  if (!ok) { parkFeil(d.message || 'Kunne ikke slette.'); return; }
  parkFeil('');
  await parkHentRegistreringer();
}

async function parkRydd(e) {
  e.preventDefault();
  const id = document.getElementById('park-rydd-lenke').value;
  const kropp = {etter: document.getElementById('park-rydd-etter').value,
                 grunn: document.getElementById('park-rydd-grunn').value};
  if (!id) { parkFeil('Velg en lenke.'); return; }
  // Første kall uten `confirm`: serveren svarer 409 med antallet, og sletter
  // ingenting. Den som rydder skal se hvor mye som går før det går.
  let svar = await parkApi(`/lag/api/lenker/${id}/slett-etter/`, 'POST', kropp);
  if (svar.status === 409) {
    if (!confirm(`${svar.d.antall} registrering(er) fra denne lenken slettes. Fortsette?`)) return;
    svar = await parkApi(`/lag/api/lenker/${id}/slett-etter/`, 'POST', {...kropp, confirm: true});
  }
  if (!svar.ok) { parkFeil(svar.d.message || 'Kunne ikke slette.'); return; }
  parkFeil('');
  await parkHentRegistreringer();
  await parkHentLenker();
}

/* ── Verdimengdene (core.verdilister) ────────────────────────────────────── */

async function parkHentVerdier(slug, boksId, kanRedigere) {
  const {ok, d} = await parkApi(`/lag/api/${slug}/`);
  if (!ok) { parkFeil(d.message || 'Kunne ikke hente lista.'); return; }
  const rader = d.data;
  const knapp = (tekst, fn, klasse = 'btn-outline-secondary') => parkNode('button', {
    class: `btn btn-sm ${klasse}`, type: 'button', tekst, klikk: fn});
  const linjer = rader.map((r, i) => {
    const handlinger = kanRedigere ? parkNode('div', {class: 'd-flex gap-1'},
      i > 0 ? knapp('↑', () => parkFlytt(slug, boksId, rader, i, -1)) : null,
      i < rader.length - 1 ? knapp('↓', () => parkFlytt(slug, boksId, rader, i, 1)) : null,
      knapp('Endre', () => parkEndre(slug, boksId, r)),
      knapp(r.er_aktiv ? 'Deaktiver' : 'Aktiver',
            () => parkSettVerdi(slug, boksId, r.id, {er_aktiv: !r.er_aktiv})),
      parkKanSletteVerdi(window.MODUL_TILGANG) && !r.i_bruk
        ? knapp('Slett', () => parkSlettVerdi(slug, boksId, r), 'btn-outline-danger') : null) : null;
    return parkNode('li', {class: `list-group-item d-flex justify-content-between align-items-center gap-2${r.er_aktiv ? '' : ' text-muted'}`},
      parkNode('span', {tekst: `${r.navn}${r.er_aktiv ? '' : ' (inaktiv)'}${r.i_bruk ? ` · ${r.i_bruk} i bruk` : ''}`}),
      handlinger);
  });
  const liste = parkNode('ul', {class: 'list-group list-group-flush mb-2'}, ...linjer);
  let skjema = null;
  if (kanRedigere) {
    const felt = parkNode('input', {class: 'form-control form-control-sm', maxlength: 64,
                                  placeholder: 'Ny verdi'});
    skjema = parkNode('form', {class: 'input-group input-group-sm'}, felt,
                    parkNode('button', {class: 'btn btn-outline-primary', type: 'submit', tekst: 'Legg til'}));
    skjema.addEventListener('submit', async (e) => {
      e.preventDefault();
      const svar = await parkApi(`/lag/api/${slug}/`, 'POST', {navn: felt.value});
      if (!svar.ok) { parkFeil(svar.d.message || 'Kunne ikke legge til.'); return; }
      parkFeil('');
      await parkHentVerdier(slug, boksId, kanRedigere);
    });
  }
  document.getElementById(boksId).replaceChildren(liste, skjema || '');
}

async function parkSettVerdi(slug, boksId, id, kropp) {
  const {ok, d} = await parkApi(`/lag/api/${slug}/${id}/`, 'PUT', kropp);
  if (!ok) { parkFeil(d.message || 'Kunne ikke endre.'); return; }
  parkFeil('');
  await parkHentVerdier(slug, boksId, true);
}

async function parkEndre(slug, boksId, r) {
  const navn = prompt('Nytt navn:', r.navn);
  if (navn == null || navn.trim() === r.navn) return;
  await parkSettVerdi(slug, boksId, r.id, {navn});
}

async function parkFlytt(slug, boksId, rader, i, retning) {
  const ider = rader.map((r) => r.id);
  [ider[i], ider[i + retning]] = [ider[i + retning], ider[i]];
  const {ok, d} = await parkApi(`/lag/api/${slug}/rekkefolge/`, 'PUT', {ider});
  if (!ok) { parkFeil(d.message || 'Kunne ikke flytte.'); return; }
  await parkHentVerdier(slug, boksId, true);
}

async function parkSlettVerdi(slug, boksId, r) {
  if (!confirm(`Slette «${r.navn}»?`)) return;
  const {ok, d} = await parkApi(`/lag/api/${slug}/${r.id}/`, 'DELETE', {confirm: true});
  if (!ok) { parkFeil(d.message || 'Kunne ikke slette.'); return; }
  await parkHentVerdier(slug, boksId, true);
}

/* ── Oppstart ────────────────────────────────────────────────────────────── */

async function parkOppsettStart() {
  const std = parkStandardOppetid(Date.now());
  document.getElementById('park-lenke-fra').value = std.fra;
  document.getElementById('park-lenke-til').value = std.til;
  document.getElementById('park-ny-lenke').addEventListener('submit', parkLagLenke);
  document.getElementById('park-rydd').addEventListener('submit', parkRydd);
  document.getElementById('park-reg-filter').addEventListener('input', parkTegnRegistreringer);
  let skjult = false;
  try { skjult = globalThis.localStorage.getItem('park.reg.skjult') === '1'; } catch (e) { skjult = false; }
  parkSettRegSkjult(skjult);
  document.getElementById('park-reg-bryter').addEventListener('click', () => parkSettRegSkjult(
    !document.getElementById('park-reg-innhold').classList.contains('d-none')));
  await Promise.all([
    parkHentLenker(),
    parkHentRegistreringer(),
    parkHentSteder(),
    parkHentVerdier('problemstillinger', 'park-problemstillinger', true),
    parkHentVerdier('utfall', 'park-utfall', parkKanSetteOppUtfall(window.MODUL_TILGANG)),
  ]);
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', parkOppsettStart);
}
