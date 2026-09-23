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
let koTavleSkjema = null;    // åpent skjema: {type: 'rett'|'pause', id}
let koTavleVisning = 'tavle';  // 'tavle' | 'besok'
let koTavleBesokValg = { lokasjon: null, maal: 'antall' };

//: «Pause nå» dukker opp så mange minutter før pausen er planlagt.
const KO_TAVLE_PAUSE_FORVARSEL_MIN = 10;

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

function koTavleTo(n) {
  return String(n).padStart(2, '0');
}

function koTavleHHMM(ms) {
  const d = new Date(ms);
  return koTavleTo(d.getHours()) + ':' + koTavleTo(d.getMinutes());
}

// Et klokkeslett fra skjemaet blir **det nærmeste tidspunktet med den
// klokka** rundt `refMs` — plasseringen som rettes, eller nå for en ny pause.
// Skissen har klokkeslett, ikke dato: på en vakt over midnatt ville et
// datofelt vært en felle, mens «20:00» nesten alltid betyr den nærmeste.
function koTavleTidNaer(refMs, hhmm) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || '').trim());
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  const d = new Date(refMs);
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  if (d.getTime() - refMs > 12 * 3600000) d.setDate(d.getDate() - 1);
  else if (refMs - d.getTime() > 12 * 3600000) d.setDate(d.getDate() + 1);
  return d.getTime();
}

// Hvor en planlagt pause står: startet, ikke tatt, nå (fra forvarselet), eller
// kommer. «Nå» er når KO får knappen — tavla starter den aldri selv.
function koTavlePauseStatus(q, naaMs) {
  if (q.startet) return 'startet';
  if (naaMs >= Date.parse(q.til)) return 'ikke_tatt';
  if (naaMs >= Date.parse(q.fra) - KO_TAVLE_PAUSE_FORVARSEL_MIN * 60000) return 'naa';
  return 'kommer';
}

// Den planlagte slutten på en åpen plassering (23. sep. 2026, André:
// «planlegge tid per plassering med beskjed/tegn på overtid»). `null` uten
// plan og på en lukket plassering; ellers om tida er ute, og hvor mange
// minutter over eller igjen. **Tavla flytter ingen** — overtid er et tegn,
// ikke en handling.
function koTavleSlutt(p, naaMs) {
  if (!p || p.til || !p.planlagt_til) return null;
  const til = Date.parse(p.planlagt_til);
  if (!Number.isFinite(til)) return null;
  const over = naaMs > til;
  return { til, over, min: Math.round(Math.abs(naaMs - til) / 60000) };
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
      treff.push({ p, r, fra, til, aapen: !p.til, opptatt: false, slutt: koTavleSlutt(p, vindu.naa) });
    });
    if (rad.pause) {
      // De planlagte pausene som ikke er startet. Den startede står som
      // plasseringen den ble til.
      (data.pauser || []).forEach((q) => {
        if (q.startet) return;
        const r = ressurser.get(q.ressurs_id);
        if (!(r ? koTavleSynlig(r, filter) : (!filter || filter === 'alle'))) return;
        const fra = Date.parse(q.fra);
        const til = Date.parse(q.til);
        if (!(fra < vindu.til && til > vindu.fra)) return;
        treff.push({ p: null, r, q, fra, til, aapen: false, opptatt: false });
      });
    } else {
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
      // En planlagt pause tegnes bredere enn tida si (navnet og knappen skal
      // få plass), så banen holdes opptatt litt lenger — ellers havner neste
      // stolpe oppå knappen.
      // Den stiplede slutten står i banen også, ellers tegnes neste stolpe
      // oppå den.
      baner[bane] = t.q ? Math.max(t.til, t.fra + 2.5 * 3600000)
        : (t.slutt && !t.slutt.over ? Math.max(t.til, t.slutt.til) : t.til);
      const navn = t.r ? t.r.navn : (t.p ? t.p.ressurs_navn : (t.q ? t.q.ressurs_navn : ''));
      const min = (t.til - t.fra) / 60000;
      let merke = '';
      if (t.opptatt) merke = t.r.opptatt.merke;
      else if (t.p && t.p.hendelse_nummer) merke = 'H' + t.p.hendelse_nummer;
      else if (t.q) merke = koTavleHHMM(t.fra) + '–' + koTavleHHMM(t.til);
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
        // Rettes med et klikk: det tavla selv satte, ikke tida på en hendelse.
        plassering_id: t.p && !t.p.hendelse_nummer ? t.p.id : null,
        pause_id: t.q ? t.q.id : null,
        pause_status: t.q ? koTavlePauseStatus(t.q, vindu.naa) : '',
        slutt: t.slutt ? { over: t.slutt.over, min: t.slutt.min, kl: koTavleHHMM(t.slutt.til),
                           prosent: koTavleProsent(t.slutt.til, vindu) } : null,
      };
    });
    return { id: rad.id, navn: rad.navn, pause: rad.pause, stolper, baner: Math.max(1, baner.length),
             naa: treff.filter((t) => t.aapen || t.opptatt).length,
             over: stolper.filter((s) => s.slutt && s.slutt.over).length,
             fulgt: !rad.pause && (data.fulgte || []).includes(rad.id) };
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
  // Neste planlagte pause som ikke er tatt, per ressurs.
  const planlagt = new Map();
  (data.pauser || []).forEach((q) => {
    const status = koTavlePauseStatus(q, naaMs);
    if (status !== 'naa' && status !== 'kommer') return;
    const f = planlagt.get(q.ressurs_id);
    if (!f || Date.parse(q.fra) < Date.parse(f.q.fra)) planlagt.set(q.ressurs_id, { q, status });
  });
  return {
    ledige: synlige.filter((r) => !r.opptatt && !aapne.has(r.id)).map((r) => {
      const p = planlagt.get(r.id);
      return {
        id: r.id, navn: r.navn, bil: r.bil,
        pause: sistePause.has(r.id) ? koTavleVarighet((naaMs - sistePause.get(r.id)) / 60000) : '',
        dras: koTavleKanDras(r, koTavleKanSkrive()),
        planlagt: p ? { id: p.q.id, naa: p.status === 'naa', kl: koTavleHHMM(Date.parse(p.q.fra)) } : null,
      };
    }),
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
  if (s.ressurs_id !== null && s.ressurs_id === koTavleValgt && !s.pause_id) klasser.push('ko-tavle-valgt');
  if (s.pause_id) klasser.push('ko-tavle-planlagt', 'ko-tavle-pause-' + escapeHtml(s.pause_status));
  if (s.slutt && s.slutt.over) klasser.push('ko-tavle-over');
  // Den planlagte er kort og står tett: bare navnet, tida i `title`.
  const etikett = escapeHtml(s.navn) + (s.merke && !s.pause_id ? ' · ' + escapeHtml(s.merke) : '')
    + (s.varighet ? ' <span class="ko-tavle-tid-tekst">' + escapeHtml(s.varighet) + '</span>' : '')
    + (s.lenge ? ' <span title="Samme sted over 3 timer">⏱</span>' : '')
    + (s.slutt && s.slutt.over ? ' <span class="ko-tavle-over-tekst">' + escapeHtml(koTavleVarighet(s.slutt.min))
      + ' over</span>' : '');
  // Den åpne (og den opptatte) slutter ved nå og vokser **bakover** til lesbar
  // bredde — en stolpe som stakk forbi nå-streken ville sett ut som en plan.
  const bredde = Math.max(0, 100 - s.venstre - s.hoyre).toFixed(2);
  // Den planlagte vokser framover til den har plass til navnet — og til
  // «Pause nå» når den er her; ellers dekket naboen knappen.
  let plass = 'left:' + escapeHtml(s.venstre.toFixed(2)) + '%;right:' + escapeHtml(s.hoyre.toFixed(2)) + '%';
  if (s.aapen || s.opptatt) {
    plass = 'right:' + escapeHtml(s.hoyre.toFixed(2)) + '%;width:max(72px,' + escapeHtml(bredde) + '%)';
  } else if (s.pause_id) {
    plass = 'left:' + escapeHtml(s.venstre.toFixed(2)) + '%;width:max('
      + (s.pause_status === 'naa' ? '140px' : '64px') + ',' + escapeHtml(bredde) + '%)';
  }
  plass += ';top:' + escapeHtml(String(s.bane * 28 + 4)) + 'px';
  const skriv = koTavleKanSkrive();
  let dra = '';
  if (s.dras) {
    dra = ' data-tavle-ressurs="' + escapeHtml(s.ressurs_id) + '" data-dras="1" tabindex="0" role="button"'
      + ' title="Dra til en rad, eller klikk og velg rad"';
  } else if (skriv && s.pause_id) {
    dra = ' data-tavle-pause="' + escapeHtml(s.pause_id) + '" tabindex="0" role="button"'
      + ' title="Planlagt pause ' + escapeHtml(s.merke) + ' — klikk for å endre"';
  } else if (skriv && s.plassering_id && !s.aapen) {
    dra = ' data-tavle-plassering="' + escapeHtml(s.plassering_id) + '" tabindex="0" role="button"'
      + ' title="Klikk for å rette tidene"';
  }
  // «Pause nå» på den planlagte når tiden er inne. KO starter den; tavla
  // flytter ingen av seg selv.
  const start = skriv && s.pause_id && s.pause_status === 'naa'
    ? ' <button type="button" class="btn btn-sm btn-warning ko-tavle-pause-knapp" data-action="koTavleStartPause"'
      + ' data-arg="' + escapeHtml(s.pause_id) + '">Pause nå</button>'
    : '';
  return '<div class="' + klasser.join(' ') + '" style="' + plass + '"' + dra + '>' + etikett + start + '</div>'
    + koTavleSluttHtml(s, skriv);
}

// Den planlagte slutten ved siden av den åpne stolpen: **stiplet fra nå** og
// fram til slutten, eller — når tida er ute — en rød strek der den skulle
// sluttet. Et klikk på den stiplede åpner skjemaet, for den som skriver.
function koTavleSluttHtml(s, skriv) {
  if (!s.slutt) return '';
  const topp = 'top:' + escapeHtml(String(s.bane * 28 + 4)) + 'px';
  if (s.slutt.over) {
    return '<div class="ko-tavle-slutt-merke" style="left:' + escapeHtml(s.slutt.prosent.toFixed(2)) + '%;' + topp
      + '" title="Planlagt slutt ' + escapeHtml(s.slutt.kl) + '"></div>';
  }
  const aapne = skriv && s.plassering_id
    ? ' data-tavle-plassering="' + escapeHtml(s.plassering_id) + '" tabindex="0" role="button"'
      + ' title="Planlagt slutt ' + escapeHtml(s.slutt.kl) + ' — klikk for å endre"'
    : ' title="Planlagt slutt ' + escapeHtml(s.slutt.kl) + '"';
  return '<div class="ko-tavle-slutt-plan" style="left:' + escapeHtml((100 - s.hoyre).toFixed(2)) + '%;right:'
    + escapeHtml((100 - s.slutt.prosent).toFixed(2)) + '%;' + topp + '"' + aapne + '>til '
    + escapeHtml(s.slutt.kl) + '</div>';
}

function koTavleRadHtml(rad) {
  const hoyde = rad.baner * 28 + 8;
  const stolper = rad.stolper.map(koTavleStolpeHtml).join('');
  return '<div class="ko-tavle-rad' + (rad.pause ? ' ko-tavle-pause' : '') + '" tabindex="0" data-tavle-mal="'
    + escapeHtml(rad.id) + '">'
    + '<div class="ko-tavle-radnavn"><span>' + escapeHtml(rad.navn) + '</span>'
    + (rad.fulgt ? '<span class="ko-tavle-stjerne" title="Fulgt sted — «ikke vært» står under tavla">★</span>' : '')
    + (rad.pause && koTavleKanSkrive()
      ? '<button type="button" class="btn btn-sm btn-outline-secondary ko-tavle-planlegg"'
        + ' data-action="koTavlePlanlegg" title="Planlegg en pause for et lag">+ Planlegg</button>'
      : '')
    + (rad.over ? '<span class="ko-tavle-over-tall" title="Står over planlagt slutt">' + escapeHtml(String(rad.over))
      + ' over</span>' : '')
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
    + koTavlePlanlagtHtml(r.planlagt)
    + '</div>').join('') || '<div class="ko-tavle-tom">Alle ledige har en plass.</div>';
  const travle = u.opptatt.map((r) => '<div class="ko-tavle-kort ko-tavle-opptatt"'
    + ' title="Hendelsen eller oppdraget styrer hvor ressursen er">' + escapeHtml(r.navn)
    + '<div class="ko-tavle-kort-under">' + escapeHtml(r.tekst) + '</div></div>').join('');
  return '<div class="ko-tavle-overskrift">Uten plass</div>' + kort
    + (travle ? '<div class="ko-tavle-overskrift mt-2">Opptatt</div>' + travle : '');
}

// Den planlagte pausen på et kort i «Uten plass»: knappen når den er her,
// klokkeslettet ellers.
function koTavlePlanlagtHtml(p) {
  if (!p) return '';
  if (p.naa && koTavleKanSkrive()) {
    return '<button type="button" class="btn btn-sm btn-warning mt-1 ko-tavle-pause-knapp"'
      + ' data-action="koTavleStartPause" data-arg="' + escapeHtml(p.id) + '">Pause nå</button>';
  }
  return '<div class="ko-tavle-kort-under">Pause ' + escapeHtml(p.kl) + '</div>';
}

// Linja over tavla når et lag er valgt. «Rett tidene» for plasseringen det
// står på nå — en åpen stolpe velges med klikk, så rettingen trenger en dør.
function koTavleValgtHtml(r, aapen) {
  const tekst = `Velg raden ${r.navn} skal til — eller «Uten plass». Esc avbryter.`;
  return escapeHtml(tekst)
    + (aapen ? ' <button type="button" class="btn btn-sm btn-outline-light ms-2" data-action="koTavleRettValgt"'
      + ' data-arg="' + escapeHtml(aapen.id) + '">Tider og slutt</button>' : '');
}

function koTavleFilterHtml(data, filter) {
  const antall = (id) => (data.ressurser || []).filter((r) => koTavleSynlig(r, id)).length;
  const knapp = (id, navn) => '<button type="button" class="btn btn-outline-secondary'
    + (String(filter) === String(id) ? ' active' : '') + '" data-action="koTavleVelgFilter" data-arg="'
    + escapeHtml(id) + '">' + escapeHtml(navn) + ' <span class="ko-vindu-tall">' + escapeHtml(String(antall(id)))
    + '</span></button>';
  return knapp('alle', 'Alle') + (data.grupper || []).map((g) => knapp(g.id, g.navn)).join('');
}

// ── Besøk og «ikke vært» (steg 2) ────────────────────────────────────────────

// Døgnet et tidspunkt hører til, som `YYYY-MM-DD`. **Døgnet begynner ved
// døgnstarten** (portalinnstilling, 06:00): en konsert kl. 01 hører til
// fredagen, som på tavla på veggen.
function koTavleDognnokkel(ms, dognstart) {
  const [t, m] = String(dognstart || '06:00').split(':').map(Number);
  const d = new Date(ms);
  d.setMinutes(d.getMinutes() - ((t || 0) * 60 + (m || 0)));
  return d.getFullYear() + '-' + koTavleTo(d.getMonth() + 1) + '-' + koTavleTo(d.getDate());
}

// Døgnene vakta har hatt, fra vaktstart (eller den første plasseringen) til nå.
function koTavleDognene(data, naaMs) {
  const starter = (data.plasseringer || []).map((p) => Date.parse(p.fra));
  const vs = Date.parse(data.vakt_start);
  if (Number.isFinite(vs)) starter.push(vs);
  let t = starter.length ? Math.min(...starter, naaMs) : naaMs;
  const siste = koTavleDognnokkel(naaMs, data.dognstart);
  const ut = [];
  for (let i = 0; i < 60; i += 1) {
    const k = koTavleDognnokkel(t, data.dognstart);
    if (!ut.includes(k)) ut.push(k);
    if (k === siste) break;
    t += 12 * 3600000;
  }
  return ut;
}

// «Besøk» for én lokasjon: per ressurs, antall og tid per døgn, for hele
// vakta, og sist der. Et besøk er en plassering der, eller tida på en
// hendelse der — også en laget står på nå. **Nuller øverst når stedet er
// fulgt (★)**, så «hvem skal få gå neste» leses fra toppen.
function koTavleBesok(data, lokasjonId, filter, naaMs) {
  const dogn = koTavleDognene(data, naaMs);
  const besok = (data.plasseringer || [])
    .filter((p) => p.lokasjon_id === lokasjonId)
    .map((p) => ({ ressurs_id: p.ressurs_id, fra: Date.parse(p.fra), til: p.til ? Date.parse(p.til) : naaMs,
                   naa: !p.til, h: p.hendelse_nummer }));
  (data.ressurser || []).forEach((r) => {
    if (r.opptatt && r.opptatt.hendelse_id && r.opptatt.lokasjon_id === lokasjonId) {
      besok.push({ ressurs_id: r.id, fra: Date.parse(r.opptatt.fra), til: naaMs, naa: true,
                   merke: r.opptatt.merke });
    }
  });
  const rader = (data.ressurser || []).filter((r) => koTavleSynlig(r, filter)).map((r, rekke) => {
    const mine = besok.filter((b) => b.ressurs_id === r.id);
    const per = {};
    const tid = {};
    let sist = null;
    mine.forEach((b) => {
      const k = koTavleDognnokkel(b.fra, data.dognstart);
      per[k] = (per[k] || 0) + 1;
      tid[k] = (tid[k] || 0) + (b.til - b.fra);
      // Plasseringene kommer i tidsrekkefølge og hendelsen nå sist, og ett lag
      // står ett sted om gangen — så den siste er den siste.
      sist = b;
    });
    return {
      id: r.id, navn: r.navn, rekke, per, tid,
      antall: mine.length,
      tid_totalt: mine.reduce((sum, b) => sum + (b.til - b.fra), 0),
      sist: sist ? { naa: sist.naa, til: sist.til, merke: sist.h ? 'H' + sist.h : (sist.merke || '') } : null,
    };
  });
  if ((data.fulgte || []).includes(lokasjonId)) {
    rader.sort((a, b) => (a.antall - b.antall)
      || ((a.sist ? (a.sist.naa ? Infinity : a.sist.til) : -Infinity)
        - (b.sist ? (b.sist.naa ? Infinity : b.sist.til) : -Infinity))
      || (a.rekke - b.rekke));
  }
  return { dogn, rader };
}

// Under tavla: hvem som ikke har vært på et fulgt sted denne vakta.
function koTavleIkkeVaert(data, filter, naaMs) {
  return (data.rader || []).filter((l) => (data.fulgte || []).includes(l.id)).map((l) => ({
    navn: l.navn,
    ressurser: koTavleBesok(data, l.id, filter, naaMs).rader.filter((r) => !r.antall).map((r) => r.navn),
  }));
}

function koTavleDognnavn(k) {
  const d = new Date(k + 'T12:00:00');
  const navn = d.toLocaleDateString('nb-NO', { weekday: 'short', day: '2-digit', month: '2-digit' });
  return navn.charAt(0).toUpperCase() + navn.slice(1);
}

function koTavleSistHtml(sist) {
  if (!sist) return '<span class="ko-tavle-dempet">aldri</span>';
  const tekst = sist.naa ? 'der nå'
    : new Date(sist.til).toLocaleDateString('nb-NO', { weekday: 'short' }) + ' ' + koTavleHHMM(sist.til);
  return escapeHtml(tekst + (sist.merke ? ' · ' + sist.merke : ''));
}

function koTavleBesokHtml(data, b, valg, lokasjonId) {
  const fulgt = (data.fulgte || []).includes(lokasjonId);
  const steder = (data.rader || []).slice().sort((x, y) =>
    Number((data.fulgte || []).includes(y.id)) - Number((data.fulgte || []).includes(x.id)));
  const valgHtml = steder.map((l) => '<option value="' + escapeHtml(l.id) + '"'
    + (l.id === lokasjonId ? ' selected' : '') + '>' + escapeHtml(l.navn)
    + ((data.fulgte || []).includes(l.id) ? ' ★' : '') + '</option>').join('');
  const maalKnapp = (maal, navn) => '<button type="button" class="btn btn-outline-secondary'
    + (valg.maal === maal ? ' active' : '') + '" data-action="koTavleBesokMaal" data-arg="' + escapeHtml(maal)
    + '">' + escapeHtml(navn) + '</button>';
  const celle = (r, k) => {
    if (valg.maal === 'tid') return r.tid[k] ? escapeHtml(koTavleVarighet(r.tid[k] / 60000)) : '–';
    return escapeHtml(String(r.per[k] || 0));
  };
  const hode = b.dogn.map((k) => '<th>' + escapeHtml(koTavleDognnavn(k)) + '</th>').join('');
  const dogn = b.dogn;
  const rader = b.rader.map((r) => '<tr' + (fulgt && !r.antall ? ' class="ko-tavle-null"' : '') + '>'
    + '<td>' + escapeHtml(r.navn) + '</td>'
    + dogn.map((k) => '<td>' + celle(r, k) + '</td>').join('')
    + '<td class="fw-semibold">' + escapeHtml(String(r.antall)) + (fulgt && !r.antall ? ' ★' : '') + '</td>'
    + '<td>' + (r.tid_totalt ? escapeHtml(koTavleVarighet(r.tid_totalt / 60000)) : '–') + '</td>'
    + '<td>' + koTavleSistHtml(r.sist) + '</td></tr>').join('');
  return '<div class="ko-tavle-besok">'
    + '<div class="d-flex flex-wrap align-items-center gap-2 mb-2">'
    + '<label class="small">Lokasjon <select class="form-select form-select-sm d-inline-block w-auto"'
    + ' id="ko-tavle-besok-lokasjon" data-action="koTavleBesokLokasjon" data-hendelse="change">' + valgHtml + '</select></label>'
    + '<div class="btn-group btn-group-sm">' + maalKnapp('antall', 'Antall ganger') + maalKnapp('tid', 'Tid') + '</div>'
    + '<span class="small ko-tavle-dempet">Døgnet regnes fra ' + escapeHtml(data.dognstart || '06:00') + '</span></div>'
    + (steder.length
      ? '<table class="table table-sm ko-tavle-besok-tabell"><thead><tr><th>Ressurs</th>' + hode
        + '<th>Hele vakta</th><th>Tid totalt</th><th>Sist der</th></tr></thead><tbody>' + rader + '</tbody></table>'
      : '<div class="ko-tavle-tom">Ingen lokasjoner på tavla.</div>')
    + '</div>';
}

function koTavleIkkeVaertHtml(liste) {
  return liste.map((l) => '<div class="ko-tavle-ikke-vaert"><span class="ko-tavle-stjerne">★</span> Ikke vært på '
    + escapeHtml(l.navn) + ' denne vakta: '
    + (l.ressurser.length ? l.ressurser.map((n) => '<span class="ko-tavle-navnelapp">' + escapeHtml(n) + '</span>').join(' ')
      : '<span class="ko-tavle-dempet">alle har vært der</span>')
    + '</div>').join('');
}

// ── Skjemaet: rett en plassering, eller planlegg en pause (steg 2) ──────────

// Hva skjemaet skal vise. En regel og ikke en del av byggeren, fordi den
// avgjør **hva som kan endres**: «til» er låst på den åpne plasseringen (den
// slutter nå) og der en hendelse tok over — hendelsen eier tida videre.
function koTavleSkjemaData(skjema, data, naaMs) {
  if (!skjema || !data) return null;
  if (skjema.type === 'rett') {
    const p = (data.plasseringer || []).find((x) => x.id === skjema.id);
    if (!p) return null;
    const neste = (data.plasseringer || []).find((x) => x.ressurs_id === p.ressurs_id && x.id !== p.id
      && p.til && x.fra === p.til);
    const hendelseTok = Boolean(neste && neste.hendelse_nummer);
    return {
      type: 'rett', id: p.id,
      tittel: p.ressurs_navn + ' · ' + (p.pause ? 'Pause' : p.lokasjon_navn),
      fra: koTavleHHMM(Date.parse(p.fra)),
      til: p.til ? koTavleHHMM(Date.parse(p.til)) : '',
      tilLaast: !p.til || hendelseTok,
      // Den planlagte slutten hører bare til den åpne.
      harSlutt: !p.til,
      slutt: p.planlagt_til ? koTavleHHMM(Date.parse(p.planlagt_til)) : '',
      hint: !p.til ? '«Til» er nå: plasseringen er åpen. Planlagt slutt flytter ingen — når tida er ute, '
        + 'får laget rød kant til det flyttes. Tomt felt er ingen plan.'
        : (hendelseTok ? '«Til» er låst: laget gikk på H' + neste.hendelse_nummer + ', og hendelsen eier tida videre.'
          : 'Naboplasseringene tilpasses i samme lagring — laget står aldri to steder samtidig.'),
      kanFjerne: true,
    };
  }
  const q = skjema.id ? (data.pauser || []).find((x) => x.id === skjema.id) : null;
  if (skjema.id && !q) return null;
  const kvarter = 15 * 60000;
  const forslag = Math.ceil(naaMs / kvarter) * kvarter;
  return {
    type: 'pause', id: q ? q.id : null,
    tittel: q ? 'Endre pause · ' + q.ressurs_navn : 'Planlegg pause',
    ressurser: q ? null : (data.ressurser || []).filter((r) => !r.bil).map((r) => ({ id: r.id, navn: r.navn })),
    fra: q ? koTavleHHMM(Date.parse(q.fra)) : koTavleHHMM(forslag),
    til: q ? koTavleHHMM(Date.parse(q.til)) : koTavleHHMM(forslag + 30 * 60000),
    tilLaast: false,
    hint: 'Planen flytter ingen: når tiden er inne, får laget «Pause nå», og KO starter den.',
    kanFjerne: Boolean(q),
  };
}

function koTavleSkjemaHtml(d) {
  const valg = velgValg('') + (d.ressurser || [])
    .map((r) => '<option value="' + escapeHtml(r.id) + '">' + escapeHtml(r.navn) + '</option>').join('');
  const velger = d.ressurser
    ? '<label class="small">Lag <select class="form-select form-select-sm" id="ko-tavle-skjema-ressurs">'
      + valg + '</select></label>'
    : '';
  return '<div class="ko-tavle-skjema-tittel">' + escapeHtml(d.tittel) + '</div>'
    + '<div class="d-flex flex-wrap align-items-end gap-2">' + velger
    + '<label class="small">Fra <input type="time" class="form-control form-control-sm" id="ko-tavle-skjema-fra" value="'
    + escapeHtml(d.fra) + '"></label>'
    + '<label class="small">Til <input type="time" class="form-control form-control-sm" id="ko-tavle-skjema-til" value="'
    + escapeHtml(d.til) + '"' + (d.tilLaast ? ' disabled' : '') + '></label>'
    + (d.harSlutt ? '<label class="small">Planlagt slutt <input type="time" class="form-control form-control-sm"'
      + ' id="ko-tavle-skjema-slutt" value="' + escapeHtml(d.slutt) + '"></label>' : '')
    + '<button type="button" class="btn btn-sm btn-primary" data-action="koTavleLagreSkjema">Lagre</button>'
    + '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koTavleLukkSkjema">Avbryt</button>'
    + (d.kanFjerne ? '<button type="button" class="btn btn-sm btn-outline-danger ms-auto" data-action="koTavleFjernISkjema">'
      + (d.type === 'rett' ? 'Fjern plasseringen' : 'Fjern pausen') + '</button>' : '')
    + '</div><div class="small ko-tavle-dempet mt-1">' + escapeHtml(d.hint) + '</div>';
}

function koTegnTavle() {
  const boks = document.getElementById('ko-tavle');
  if (!boks || !koTavle) return;
  if (koTavleDrag && koTavleDrag.drar) { koTavleTegnEtterDrag = true; return; }
  const filter = koTavleLesFilter();
  const naa = Date.now() + koTavleKlokkeavvik;
  const f = document.getElementById('ko-tavle-filter');
  if (f) f.innerHTML = koTavleFilterHtml(koTavle, filter);
  const besokKnapp = document.getElementById('ko-tavle-besok-knapp');
  if (besokKnapp) besokKnapp.classList.toggle('active', koTavleVisning === 'besok');
  koTegnTavleSkjema(naa);
  if (koTavleVisning === 'besok') {
    const rader = koTavle.rader || [];
    const fulgte = rader.filter((l) => (koTavle.fulgte || []).includes(l.id));
    if (!rader.some((l) => l.id === koTavleBesokValg.lokasjon)) {
      koTavleBesokValg.lokasjon = (fulgte[0] || rader[0] || {}).id ?? null;
    }
    const b = koTavleBesok(koTavle, koTavleBesokValg.lokasjon, filter, naa);
    boks.innerHTML = koTavleBesokHtml(koTavle, b, koTavleBesokValg, koTavleBesokValg.lokasjon);
    return;
  }
  const vindu = koTavleVindu(naa, koTavle.timer);
  const rader = koTavleRader(koTavle, vindu, filter);
  const naaStrek = '<div class="ko-tavle-naa" style="left:' + escapeHtml(koTavleProsent(naa, vindu).toFixed(2)) + '%"></div>';
  boks.innerHTML = '<div class="ko-tavle-uten" tabindex="0" data-tavle-mal="uten">'
    + koTavleUtenPlassHtml(koTavleUtenPlass(koTavle, filter, naa)) + '</div>'
    + '<div class="ko-tavle-rutenett"><div class="ko-tavle-hode"><div class="ko-tavle-radnavn">Lokasjon · nå</div>'
    + '<div class="ko-tavle-tidslinje">' + koTavleTimerHtml(vindu) + naaStrek + '</div></div>'
    + '<div class="ko-tavle-rader">' + rader.map(koTavleRadHtml).join('')
    + '<div class="ko-tavle-naa-lag">' + naaStrek + '</div></div>'
    + koTavleIkkeVaertHtml(koTavleIkkeVaert(koTavle, filter, naa)) + '</div>';
  const valgt = document.getElementById('ko-tavle-valgt');
  if (valgt) {
    const r = (koTavle.ressurser || []).find((x) => x.id === koTavleValgt);
    const aapen = r ? (koTavle.plasseringer || []).find((p) => p.ressurs_id === r.id && !p.til) : null;
    valgt.classList.toggle('d-none', !r);
    valgt.innerHTML = r ? koTavleValgtHtml(r, aapen) : '';
  }
}

function koTegnTavleSkjema(naa) {
  const el = document.getElementById('ko-tavle-skjema');
  if (!el) return;
  const d = koTavleSkjemaData(koTavleSkjema, koTavle, naa);
  // Et skjema som står åpent, tegnes ikke om under fingrene på den som
  // skriver — pollen skal ikke tømme et felt.
  if (d && el.dataset.skjema === koTavleSkjema.type + ':' + (koTavleSkjema.id || 'ny')) return;
  el.dataset.skjema = d ? koTavleSkjema.type + ':' + (koTavleSkjema.id || 'ny') : '';
  el.classList.toggle('d-none', !d);
  el.innerHTML = d ? koTavleSkjemaHtml(d) : '';
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
//
// Rekkefølgen er regelen: en knapp har sin egen handling; et lag som kan
// flyttes velges; **er et lag valgt, er et klikk i en rad en flytting** —
// også om det treffer en gammel stolpe der. Først uten noe valgt åpner en
// planlagt pause eller en lukket plassering skjemaet sitt.
function koTavleKlikk(el) {
  if (!el || !el.closest) return;
  if (el.closest('[data-action]')) return;
  const kort = el.closest('[data-tavle-ressurs][data-dras="1"]');
  if (kort) {
    const id = Number(kort.getAttribute('data-tavle-ressurs'));
    koTavleValgt = koTavleValgt === id ? null : id;
    koTegnTavle();
    return;
  }
  if (koTavleValgt !== null) {
    const mal = koTavleMaal(el);
    if (mal) koTavleFlytt(koTavleValgt, mal);
    return;
  }
  const pause = el.closest('[data-tavle-pause]');
  if (pause) { koTavleApneSkjema('pause', Number(pause.getAttribute('data-tavle-pause'))); return; }
  const hist = el.closest('[data-tavle-plassering]');
  if (hist) koTavleApneSkjema('rett', Number(hist.getAttribute('data-tavle-plassering')));
}

function koTavleApneSkjema(type, id) {
  koTavleSkjema = { type, id: id || null };
  koTavleValgt = null;
  koTavleVisFeil('');
  koTegnTavle();
}

function koTavleLukkSkjema() {
  koTavleSkjema = null;
  koTegnTavle();
}

function koTavlePlanlegg() { koTavleApneSkjema('pause', null); }

function koTavleRettValgt(id) { koTavleApneSkjema('rett', Number(id)); }

// Kroppen skjemaet sender: klokkeslettene gjort om til tidspunkter nær det
// de retter. `null` når et felt ikke er et klokkeslett.
function koTavleSkjemaKropp(skjema, data, verdier, naaMs) {
  if (skjema.type === 'rett') {
    const p = (data.plasseringer || []).find((x) => x.id === skjema.id);
    if (!p) return null;
    const fra = koTavleTidNaer(Date.parse(p.fra), verdier.fra);
    if (fra === null) return null;
    const kropp = { fra: new Date(fra).toISOString() };
    if (p.til) {
      const til = koTavleTidNaer(Date.parse(p.til), verdier.til);
      if (til === null) return null;
      kropp.til = new Date(til).toISOString();
    } else {
      // Den planlagte slutten leses nær **nå**: «00:30» kl. 22 er i natt.
      // Tomt er ingen plan, og sendes som det — ikke utelatt, ellers kunne
      // en plan aldri tas bort.
      const slutt = String(verdier.slutt || '').trim();
      if (slutt) {
        const t = koTavleTidNaer(naaMs, slutt);
        if (t === null) return null;
        kropp.planlagt_til = new Date(t).toISOString();
      } else {
        kropp.planlagt_til = null;
      }
    }
    return kropp;
  }
  const fra = koTavleTidNaer(naaMs, verdier.fra);
  // «Til» leses nær «fra», så «23:50–00:20» går over midnatt av seg selv.
  const til = fra === null ? null : koTavleTidNaer(fra, verdier.til);
  if (fra === null || til === null) return null;
  const kropp = { fra: new Date(fra).toISOString(), til: new Date(til).toISOString() };
  if (!skjema.id) {
    // «Velg…» står først (23. sep. 2026): uten lag er det ingen pause å planlegge.
    if (!verdier.ressurs) return null;
    kropp.ressurs_id = Number(verdier.ressurs);
  }
  return kropp;
}

async function koTavleSend(url, metode, kropp) {
  const res = await apiFetch(url, { method: metode, body: JSON.stringify(kropp || {}) });
  const d = await res.json().catch(() => ({}));
  koTavleVisFeil(res.ok ? '' : (d.message || 'Det gikk ikke.'));
  await koHentTavle();
  return res.ok;
}

async function koTavleLagreSkjema() {
  const s = koTavleSkjema;
  if (!s || !koTavle) return;
  const verdi = (id) => { const el = document.getElementById(id); return el ? el.value : ''; };
  const kropp = koTavleSkjemaKropp(s, koTavle, {
    fra: verdi('ko-tavle-skjema-fra'), til: verdi('ko-tavle-skjema-til'), ressurs: verdi('ko-tavle-skjema-ressurs'),
    slutt: verdi('ko-tavle-skjema-slutt'),
  }, Date.now() + koTavleKlokkeavvik);
  if (!kropp) {
    koTavleVisFeil(s.type === 'pause' && !s.id && !verdi('ko-tavle-skjema-ressurs')
      ? 'Velg laget pausen gjelder.' : 'Fyll inn klokkeslettene som TT:MM.');
    return;
  }
  const url = s.type === 'rett' ? '/ko/api/tavle/plasseringer/' + s.id + '/'
    : (s.id ? '/ko/api/tavle/pauser/' + s.id + '/' : '/ko/api/tavle/pauser/');
  const metode = s.type === 'pause' && !s.id ? 'POST' : 'PUT';
  if (await koTavleSend(url, metode, kropp)) koTavleLukkSkjema();
}

async function koTavleFjernISkjema() {
  const s = koTavleSkjema;
  if (!s) return;
  const sporsmaal = s.type === 'rett'
    ? 'Fjerne plasseringen? Den forsvinner fra tavla og fra «Besøk», og loggen får en linje om det.'
    : 'Fjerne den planlagte pausen?';
  if (!window.confirm(sporsmaal)) return;
  const url = s.type === 'rett' ? '/ko/api/tavle/plasseringer/' + s.id + '/' : '/ko/api/tavle/pauser/' + s.id + '/';
  if (await koTavleSend(url, 'DELETE', {})) koTavleLukkSkjema();
}

async function koTavleStartPause(id) {
  await koTavleSend('/ko/api/tavle/pauser/' + Number(id) + '/start/', 'POST', {});
}

function koTavleVisBesok() {
  koTavleVisning = koTavleVisning === 'besok' ? 'tavle' : 'besok';
  koTavleValgt = null;
  koTegnTavle();
}

function koTavleBesokLokasjon() {
  const el = document.getElementById('ko-tavle-besok-lokasjon');
  if (el) koTavleBesokValg.lokasjon = Number(el.value);
  koTegnTavle();
}

function koTavleBesokMaal(maal) {
  koTavleBesokValg.maal = maal === 'tid' ? 'tid' : 'antall';
  koTegnTavle();
}

// ── KO-innstillinger, fanen «Tavla» (steg 2) ─────────────────────────────────
//
// Tegnes gjennom kroken `tegn` i sentralbordets valgliste-modal, som
// «Nullstill»: oppdragsmodulens JS kjenner ikke KO. Fanen tegnes synkront, så
// den setter en beholder og henter lista etterpå.

function koTavleOppsettHtml(rader) {
  if (!rader.length) return '<div class="tom-melding">Ingen aktive lokasjoner i oppdragsmodulen.</div>';
  return '<table class="table table-sm align-middle mb-2"><thead><tr><th>Lokasjon (fra oppdragsmodulen)</th>'
    + '<th class="text-center">På tavla</th><th class="text-center">Følg besøk ★</th></tr></thead><tbody>'
    + rader.map((l) => '<tr><td>' + escapeHtml(l.navn) + '</td>'
      + '<td class="text-center"><input type="checkbox" class="form-check-input" data-tavle-oppsett="paa" value="'
      + escapeHtml(l.id) + '"' + (l.paa_tavla ? ' checked' : '') + ' aria-label="' + escapeHtml(l.navn) + ' på tavla"></td>'
      + '<td class="text-center"><input type="checkbox" class="form-check-input" data-tavle-oppsett="fulgt" value="'
      + escapeHtml(l.id) + '"' + (l.fulgt ? ' checked' : '') + ' aria-label="Følg ' + escapeHtml(l.navn) + '"></td></tr>').join('')
    + '</tbody></table>'
    + '<button type="button" class="btn btn-sm btn-primary" data-action="koLagreTavleOppsett">Lagre</button>'
    + '<div class="form-text">Rekkefølgen er lokasjonenes egen. KO eier bare de to avkryssingene — ikke lokasjonene. '
    + 'Pause er en fast rad øverst, ikke en lokasjon. «Følg» gir stjerne på raden, nuller øverst i «Besøk», '
    + 'og «Ikke vært på» under tavla.</div>';
}

function koTegnTavleOppsett() {
  koHentTavleOppsett();
  return '<div id="ko-tavle-oppsett"><div class="tom-melding">Henter …</div></div>';
}

async function koHentTavleOppsett(svar) {
  let rader = svar;
  if (!rader) {
    const res = await apiFetch('/ko/api/tavle/oppsett/');
    if (!res.ok) return;
    rader = (await res.json()).data || [];
  }
  const el = document.getElementById('ko-tavle-oppsett');
  if (el) el.innerHTML = koTavleOppsettHtml(rader);
}

async function koLagreTavleOppsett() {
  const ider = (hva, avkrysset) => Array.from(document.querySelectorAll('[data-tavle-oppsett="' + hva + '"]'))
    .filter((el) => el.checked === avkrysset).map((el) => Number(el.value));
  const res = await apiFetch('/ko/api/tavle/oppsett/', {
    method: 'PUT', body: JSON.stringify({ skjulte: ider('paa', false), fulgte: ider('fulgt', true) }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { window.alert(d.message || 'Kunne ikke lagre.'); return; }
  await koHentTavleOppsett(d.data || []);
  if (koTavleErFramme()) koHentTavle();
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
