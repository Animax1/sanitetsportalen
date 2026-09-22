// ════════════════════════════════════════════════════════════════════════════
// ko-tavle.js — tavla: lokasjonene som rader, tida som kolonner, og lagene
// plassert i rutene (André, 22. sep. 2026, etter skissene som ble avtalt før
// koden).
//
// Tredje av KOs fire filer (`KO_JS` i patients/js_test_utils.py). Ingenting
// kjører på toppnivå her — `koTavleStart()` kalles fra `DOMContentLoaded` i
// ko.js, som er den siste fila.
//
// **Tavla og ressursoversikten deler én plass** (`KO_PAR` i ko-layout.js).
// Den som ikke står i rutenettet, står i stripa over konsollen.
//
// **Dra og slipp går med pekerhendelser, ikke med nettleserens dra-API.**
// HTML5-dra virker dårlig på nettbrett, og KO-PC-en er ikke den eneste
// skjermen. Ved siden av: **klikk laget, så raden** — samme handling for den
// som ikke kan eller vil dra, og for tastaturet.
//
// **Reglene er egne funksjoner** (`koTavleVindu`, `koTavleRader`,
// `koTavleUtenPlass`, `koTavleKanDras`, `koTavleMaal`), fordi de avgjør hva
// tavla viser og hva den lar deg gjøre — og en regel inne i en lytter lar seg
// ikke kjøre i en test.
// ════════════════════════════════════════════════════════════════════════════

//: 15 sekunder, og bare når tavla står framme — den er et bilde av det som
//: skjer, men den endres i minutter, ikke i sekunder.
const KO_TAVLE_MS = 15000;

//: Filteret huskes per nettleser, som Alle | Biler | Lag i ressursoversikten.
const KO_TAVLE_FILTER_NOKKEL = 'ko.tavle.filter';

//: Så langt må pekeren flytte seg før et trykk blir et drag. Under det er det
//: et klikk — og klikket velger laget.
const KO_TAVLE_DRAGRENSE_PX = 6;

//: Et lag som har stått like lenge på samme sted, får ⏱ — det er lett å
//: glemme et lag på en rolig post.
const KO_TAVLE_LENGE_MIN = 180;

let koTavle = null;          // svaret fra /ko/api/tavle/
let koTavleKlokkeavvik = 0;  // serverens klokke minus nettleserens, i ms
let koTavleValgt = null;     // ressursen som er valgt for klikk-så-rad
let koTavleDrag = null;      // pågående drag: {id, x, y, drar, spokelse}
let koTavleTegnEtterDrag = false;
let koTavleSvelgKlikk = false;  // klikket nettleseren sender etter et drag

function koTavleKanSkrive() {
  return typeof koKanSkrive === 'function' ? koKanSkrive() : false;
}

function koTavleLesFilter() {
  try { return window.localStorage.getItem(KO_TAVLE_FILTER_NOKKEL) || 'alle'; } catch (e) { return 'alle'; }
}

function koTavleLagreFilter(verdi) {
  try { window.localStorage.setItem(KO_TAVLE_FILTER_NOKKEL, verdi); } catch (e) { /* privat modus */ }
}

// ── Reglene ──────────────────────────────────────────────────────────────────

// Tidslinja: **nå står ved to tredjedeler**, så det meste av vinduet er det
// som har skjedd, og en tredjedel er det som kommer (pauser, i steg 2).
function koTavleVindu(naaMs, timer) {
  const lengde = Math.max(1, Number(timer) || 12) * 3600000;
  const fra = naaMs - (lengde * 2) / 3;
  return { fra, til: fra + lengde, naa: naaMs };
}

function koTavleProsent(tMs, vindu) {
  const p = ((tMs - vindu.fra) / (vindu.til - vindu.fra)) * 100;
  return Math.max(0, Math.min(100, p));
}

// Filteret er ressursgruppene fra vaktlista; «alle» viser alt.
function koTavleSynlig(ressurs, filter) {
  if (!filter || filter === 'alle') return true;
  return Boolean(ressurs) && String(ressurs.gruppe_id) === String(filter);
}

// **Bare en ledig ressurs kan flyttes, og bare av den som skriver i KO**
// (André: «en skal bare kunne plasseres på tavlen når en er ledig»).
function koTavleKanDras(ressurs, kanSkrive) {
  return Boolean(kanSkrive && ressurs && !ressurs.opptatt);
}

// Hvor et slipp havner: en rad, Pause-raden eller «Uten plass».
function koTavleMaal(el) {
  const mal = el && el.closest ? el.closest('[data-tavle-mal]') : null;
  if (!mal) return null;
  const v = mal.getAttribute('data-tavle-mal');
  if (v === 'uten') return { uten: true };
  if (v === 'pause') return { pause: true };
  const id = Number(v);
  return Number.isFinite(id) && id > 0 ? { lokasjon_id: id } : null;
}

function koTavleVarighet(min) {
  const m = Math.max(0, Math.round(min));
  return m >= 60 ? Math.floor(m / 60) + ' t ' + String(m % 60).padStart(2, '0') : m + ' min';
}

// Radene med stolpene sine. **Pause-raden står øverst og er ikke en
// lokasjon.** En stolpe er en plassering som overlapper vinduet, eller en
// ressurs som er opptatt på en hendelse eller et oppdrag med lokasjon —
// den siste stiplet, fordi den ikke er noe tavla satte.
function koTavleRader(data, vindu, filter) {
  const ressurser = new Map((data.ressurser || []).map((r) => [r.id, r]));
  const rader = [{ id: 'pause', navn: 'Pause', pause: true }]
    .concat((data.rader || []).map((r) => ({ id: r.id, navn: r.navn, pause: false })));
  return rader.map((rad) => {
    const treff = [];
    (data.plasseringer || []).forEach((p) => {
      // En pause har ingen lokasjon, så den havner aldri i en lokasjonsrad.
      const iRaden = rad.pause ? p.pause : p.lokasjon_id === rad.id;
      if (!iRaden) return;
      const r = ressurser.get(p.ressurs_id);
      // Historikk for en ressurs som ikke er på vakt nå har ingen gruppe å
      // filtrere på — den står bare under «Alle».
      if (!(r ? koTavleSynlig(r, filter) : (!filter || filter === 'alle'))) return;
      const fra = Date.parse(p.fra);
      const til = p.til ? Date.parse(p.til) : vindu.naa;
      if (!(fra < vindu.til && til > vindu.fra)) return;
      treff.push({ p, r, fra, til, aapen: !p.til, opptatt: false });
    });
    if (!rad.pause) {
      (data.ressurser || []).forEach((r) => {
        if (!r.opptatt || r.opptatt.lokasjon_id !== rad.id || !koTavleSynlig(r, filter)) return;
        treff.push({ p: null, r, fra: Date.parse(r.opptatt.fra), til: vindu.naa, aapen: false, opptatt: true });
      });
    }
    treff.sort((a, b) => a.fra - b.fra);
    const baner = [];
    const stolper = treff.map((t) => {
      let bane = baner.findIndex((slutt) => slutt <= t.fra);
      if (bane < 0) { bane = baner.length; baner.push(0); }
      baner[bane] = t.til;
      const navn = t.r ? t.r.navn : (t.p ? t.p.ressurs_navn : '');
      const min = (t.til - t.fra) / 60000;
      let merke = '';
      if (t.opptatt) merke = t.r.opptatt.merke;
      else if (t.p && t.p.hendelse_nummer) merke = 'H' + t.p.hendelse_nummer;
      return {
        ressurs_id: t.r ? t.r.id : null,
        navn,
        merke,
        venstre: koTavleProsent(t.fra, vindu),
        hoyre: 100 - koTavleProsent(t.til, vindu),
        bane,
        aapen: t.aapen,
        opptatt: t.opptatt,
        hendelse: Boolean(t.p && t.p.hendelse_nummer),
        bil: Boolean(t.r && t.r.bil),
        varighet: t.aapen ? koTavleVarighet(min) : '',
        lenge: t.aapen && !rad.pause && min >= KO_TAVLE_LENGE_MIN,
        dras: t.aapen && koTavleKanDras(t.r, koTavleKanSkrive()),
      };
    });
    return { id: rad.id, navn: rad.navn, pause: rad.pause, stolper, baner: Math.max(1, baner.length),
             naa: treff.filter((t) => t.aapen || t.opptatt).length };
  });
}

// «Uten plass»: de ledige som ikke står noe sted, og de opptatte — som ikke
// kan plasseres, men skal synes. **Tid siden pause** står på de ledige.
function koTavleUtenPlass(data, filter, naaMs) {
  const aapne = new Set((data.plasseringer || []).filter((p) => !p.til).map((p) => p.ressurs_id));
  const sistePause = new Map();
  (data.plasseringer || []).forEach((p) => {
    if (!p.pause) return;
    const slutt = p.til ? Date.parse(p.til) : naaMs;
    sistePause.set(p.ressurs_id, Math.max(sistePause.get(p.ressurs_id) || 0, slutt));
  });
  const synlige = (data.ressurser || []).filter((r) => koTavleSynlig(r, filter));
  return {
    ledige: synlige.filter((r) => !r.opptatt && !aapne.has(r.id)).map((r) => ({
      id: r.id, navn: r.navn, bil: r.bil,
      pause: sistePause.has(r.id) ? koTavleVarighet((naaMs - sistePause.get(r.id)) / 60000) : '',
      dras: koTavleKanDras(r, koTavleKanSkrive()),
    })),
    opptatt: synlige.filter((r) => r.opptatt).map((r) => ({
      id: r.id, navn: r.navn, tekst: r.opptatt.tekst,
    })),
  };
}

// ── Byggerne ─────────────────────────────────────────────────────────────────

function koTavleStolpeHtml(s) {
  const klasser = ['ko-tavle-stolpe'];
  if (s.opptatt) klasser.push('ko-tavle-opptatt');
  if (s.hendelse) klasser.push('ko-tavle-hendelse');
  if (s.aapen) klasser.push('ko-tavle-aapen');
  if (s.bil) klasser.push('ko-tavle-bil');
  if (s.dras) klasser.push('ko-tavle-dras');
  if (s.ressurs_id !== null && s.ressurs_id === koTavleValgt) klasser.push('ko-tavle-valgt');
  const etikett = escapeHtml(s.navn) + (s.merke ? ' · ' + escapeHtml(s.merke) : '')
    + (s.varighet ? ' <span class="ko-tavle-tid-tekst">' + escapeHtml(s.varighet) + '</span>' : '')
    + (s.lenge ? ' <span title="Samme sted over 3 timer">⏱</span>' : '');
  // Den åpne (og den opptatte) slutter ved nå og vokser **bakover** til lesbar
  // bredde — en stolpe som stakk forbi nå-streken ville sett ut som en plan.
  const bredde = Math.max(0, 100 - s.venstre - s.hoyre).toFixed(2);
  const plass = (s.aapen || s.opptatt
    ? 'right:' + escapeHtml(s.hoyre.toFixed(2)) + '%;width:max(72px,' + escapeHtml(bredde) + '%)'
    : 'left:' + escapeHtml(s.venstre.toFixed(2)) + '%;right:' + escapeHtml(s.hoyre.toFixed(2)) + '%')
    + ';top:' + escapeHtml(String(s.bane * 28 + 4)) + 'px';
  const dra = s.dras
    ? ' data-tavle-ressurs="' + escapeHtml(s.ressurs_id) + '" data-dras="1" tabindex="0" role="button"'
      + ' title="Dra til en rad, eller klikk og velg rad"'
    : '';
  return '<div class="' + klasser.join(' ') + '" style="' + plass + '"' + dra + '>' + etikett + '</div>';
}

function koTavleRadHtml(rad) {
  const hoyde = rad.baner * 28 + 8;
  const stolper = rad.stolper.map(koTavleStolpeHtml).join('');
  return '<div class="ko-tavle-rad' + (rad.pause ? ' ko-tavle-pause' : '') + '" tabindex="0" data-tavle-mal="'
    + escapeHtml(rad.id) + '">'
    + '<div class="ko-tavle-radnavn"><span>' + escapeHtml(rad.navn) + '</span>'
    + '<span class="ko-tavle-radtall">' + escapeHtml(rad.naa ? String(rad.naa) : '–') + '</span></div>'
    + '<div class="ko-tavle-spor" style="height:' + escapeHtml(String(hoyde)) + 'px">'
    + stolper + '</div></div>';
}

function koTavleTimerHtml(vindu) {
  const deler = [];
  const time = 3600000;
  for (let t = Math.ceil(vindu.fra / time) * time; t < vindu.til; t += time) {
    const d = new Date(t);
    deler.push('<span class="ko-tavle-time" style="left:' + escapeHtml(koTavleProsent(t, vindu).toFixed(2))
      + '%">' + escapeHtml(String(d.getHours()).padStart(2, '0')) + '</span>');
  }
  return deler.join('');
}

function koTavleUtenPlassHtml(u) {
  const kort = u.ledige.map((r) => '<div class="ko-tavle-kort' + (r.bil ? ' ko-tavle-bil' : '')
    + (r.dras ? ' ko-tavle-dras' : '') + (r.id === koTavleValgt ? ' ko-tavle-valgt' : '') + '"'
    + (r.dras ? ' data-tavle-ressurs="' + escapeHtml(r.id) + '" data-dras="1" tabindex="0" role="button"' : '')
    + '>' + escapeHtml(r.navn)
    + (r.pause ? '<div class="ko-tavle-kort-under">Siden pause: ' + escapeHtml(r.pause) + '</div>' : '')
    + '</div>').join('') || '<div class="ko-tavle-tom">Alle ledige har en plass.</div>';
  const travle = u.opptatt.map((r) => '<div class="ko-tavle-kort ko-tavle-opptatt"'
    + ' title="Hendelsen eller oppdraget styrer hvor ressursen er">' + escapeHtml(r.navn)
    + '<div class="ko-tavle-kort-under">' + escapeHtml(r.tekst) + '</div></div>').join('');
  return '<div class="ko-tavle-overskrift">Uten plass</div>' + kort
    + (travle ? '<div class="ko-tavle-overskrift mt-2">Opptatt</div>' + travle : '');
}

function koTavleFilterHtml(data, filter) {
  const antall = (id) => (data.ressurser || []).filter((r) => koTavleSynlig(r, id)).length;
  const knapp = (id, navn) => '<button type="button" class="btn btn-outline-secondary'
    + (String(filter) === String(id) ? ' active' : '') + '" data-action="koTavleVelgFilter" data-arg="'
    + escapeHtml(id) + '">' + escapeHtml(navn) + ' <span class="ko-vindu-tall">' + escapeHtml(String(antall(id)))
    + '</span></button>';
  return knapp('alle', 'Alle') + (data.grupper || []).map((g) => knapp(g.id, g.navn)).join('');
}

function koTegnTavle() {
  const boks = document.getElementById('ko-tavle');
  if (!boks || !koTavle) return;
  if (koTavleDrag && koTavleDrag.drar) { koTavleTegnEtterDrag = true; return; }
  const filter = koTavleLesFilter();
  const naa = Date.now() + koTavleKlokkeavvik;
  const vindu = koTavleVindu(naa, koTavle.timer);
  const rader = koTavleRader(koTavle, vindu, filter);
  const naaStrek = '<div class="ko-tavle-naa" style="left:' + escapeHtml(koTavleProsent(naa, vindu).toFixed(2)) + '%"></div>';
  boks.innerHTML = '<div class="ko-tavle-uten" tabindex="0" data-tavle-mal="uten">'
    + koTavleUtenPlassHtml(koTavleUtenPlass(koTavle, filter, naa)) + '</div>'
    + '<div class="ko-tavle-rutenett"><div class="ko-tavle-hode"><div class="ko-tavle-radnavn">Lokasjon · nå</div>'
    + '<div class="ko-tavle-tidslinje">' + koTavleTimerHtml(vindu) + naaStrek + '</div></div>'
    + '<div class="ko-tavle-rader">' + rader.map(koTavleRadHtml).join('')
    + '<div class="ko-tavle-naa-lag">' + naaStrek + '</div></div></div>';
  const f = document.getElementById('ko-tavle-filter');
  if (f) f.innerHTML = koTavleFilterHtml(koTavle, filter);
  const valgt = document.getElementById('ko-tavle-valgt');
  if (valgt) {
    const r = (koTavle.ressurser || []).find((x) => x.id === koTavleValgt);
    valgt.classList.toggle('d-none', !r);
    valgt.textContent = r ? `Velg raden ${r.navn} skal til — eller «Uten plass». Esc avbryter.` : '';
  }
}

// ── Handlingene ──────────────────────────────────────────────────────────────

function koTavleVisFeil(melding) {
  const el = document.getElementById('ko-tavle-feil');
  if (!el) return;
  el.textContent = melding || '';
  el.classList.toggle('d-none', !melding);
}

async function koTavleFlytt(ressursId, mal) {
  if (!mal) return;
  koTavleValgt = null;
  const url = mal.uten ? '/ko/api/tavle/uten-plass/' : '/ko/api/tavle/plasser/';
  const kropp = { ressurs_id: ressursId };
  if (mal.pause) kropp.pause = true;
  if (mal.lokasjon_id) kropp.lokasjon_id = mal.lokasjon_id;
  const res = await apiFetch(url, { method: 'POST', body: JSON.stringify(kropp) });
  const d = await res.json().catch(() => ({}));
  koTavleVisFeil(res.ok ? '' : (d.message || 'Kunne ikke flytte.'));
  await koHentTavle();
}

function koTavleVelgFilter(id) {
  koTavleLagreFilter(String(id));
  koTegnTavle();
}

// Klikk (eller Enter) på et lag velger det; klikk på en rad etterpå flytter.
// Samme regel for musa, fingeren og tastaturet — `koTavleKlikk` får elementet.
function koTavleKlikk(el) {
  const kort = el.closest ? el.closest('[data-tavle-ressurs][data-dras="1"]') : null;
  if (kort) {
    const id = Number(kort.getAttribute('data-tavle-ressurs'));
    koTavleValgt = koTavleValgt === id ? null : id;
    koTegnTavle();
    return;
  }
  if (koTavleValgt !== null) {
    const mal = koTavleMaal(el);
    if (mal) koTavleFlytt(koTavleValgt, mal);
  }
}

function koTavleLyttere() {
  const boks = document.getElementById('ko-tavle');
  if (!boks) return;
  boks.addEventListener('pointerdown', (e) => {
    const kort = e.target.closest('[data-tavle-ressurs][data-dras="1"]');
    if (!kort || e.button > 0) return;
    koTavleDrag = { id: Number(kort.getAttribute('data-tavle-ressurs')), x: e.clientX, y: e.clientY,
                    drar: false, spokelse: null,
                    // Navnet er første tekstnode; resten er varighet og «siden pause».
                    tekst: ((kort.firstChild && kort.firstChild.textContent) || '').trim() };
  });
  window.addEventListener('pointermove', (e) => {
    const d = koTavleDrag;
    if (!d) return;
    if (!d.drar && Math.hypot(e.clientX - d.x, e.clientY - d.y) < KO_TAVLE_DRAGRENSE_PX) return;
    if (!d.drar) {
      d.drar = true;
      d.spokelse = document.createElement('div');
      d.spokelse.className = 'ko-tavle-spokelse';
      d.spokelse.textContent = d.tekst;
      document.body.appendChild(d.spokelse);
      document.body.classList.add('ko-tavle-drar');
    }
    e.preventDefault();
    d.spokelse.style.left = e.clientX + 'px';
    d.spokelse.style.top = e.clientY + 'px';
    document.querySelectorAll('.ko-tavle-mal-over').forEach((el) => el.classList.remove('ko-tavle-mal-over'));
    const under = document.elementFromPoint(e.clientX, e.clientY);
    const mal = under && under.closest ? under.closest('[data-tavle-mal]') : null;
    if (mal) mal.classList.add('ko-tavle-mal-over');
  });
  window.addEventListener('pointerup', (e) => {
    const d = koTavleDrag;
    koTavleDrag = null;
    // Et trykk som ikke ble et drag, er et klikk, og `click` tar det.
    if (!d || !d.drar) return;
    koTavleSvelgKlikk = true;
    setTimeout(() => { koTavleSvelgKlikk = false; }, 0);
    if (d.spokelse) d.spokelse.remove();
    document.body.classList.remove('ko-tavle-drar');
    document.querySelectorAll('.ko-tavle-mal-over').forEach((el) => el.classList.remove('ko-tavle-mal-over'));
    const under = document.elementFromPoint(e.clientX, e.clientY);
    koTavleFlytt(d.id, koTavleMaal(under));
    if (koTavleTegnEtterDrag) { koTavleTegnEtterDrag = false; koTegnTavle(); }
  });
  window.addEventListener('pointercancel', () => {
    if (koTavleDrag && koTavleDrag.spokelse) koTavleDrag.spokelse.remove();
    koTavleDrag = null;
    document.body.classList.remove('ko-tavle-drar');
  });
  // Klikk på et lag, så på en rad. **Klikket etter et drag svelges** — det
  // lander på det felles foreldreelementet og ville ellers valgt noe.
  boks.addEventListener('click', (e) => {
    if (koTavleSvelgKlikk) { koTavleSvelgKlikk = false; return; }
    koTavleKlikk(e.target);
  });
  boks.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); koTavleKlikk(e.target); }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && koTavleValgt !== null) { koTavleValgt = null; koTegnTavle(); }
  });
}

// ── Lasting ──────────────────────────────────────────────────────────────────

function koTavleErFramme() {
  const vindu = document.querySelector('.ko-vindu[data-vindu="tavle"]');
  return Boolean(vindu && !vindu.classList.contains('d-none'));
}

async function koHentTavle() {
  try {
    const res = await apiFetch('/ko/api/tavle/');
    if (!res.ok) return;
    koTavle = (await res.json()).data || null;
    if (koTavle && koTavle.naa) koTavleKlokkeavvik = Date.parse(koTavle.naa) - Date.now();
    koTegnTavle();
  } catch (e) {
    // Neste runde prøver igjen; tavla står som den sto.
  }
}

// Kalles av `koTegnOppsett()` (ko-layout.js) hver gang vinduene tegnes: tavla
// som nettopp ble hentet fram, skal vise nå og ikke for et kvarter siden.
function koTavleSynligNaa() {
  if (koTavleErFramme()) koHentTavle();
}

function koTavleStart() {
  if (!document.getElementById('ko-tavle')) return;
  koTavleLyttere();
  koTavleSynligNaa();
  setInterval(() => { if (koTavleErFramme()) koHentTavle(); }, KO_TAVLE_MS);
  // Nå-streken flytter seg mellom rundene, uten et kall.
  setInterval(() => { if (koTavleErFramme()) koTegnTavle(); }, 60000);
}
