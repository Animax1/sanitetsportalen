// ════════════════════════════════════════════════════════════════════════════
// ko-plan.js — planleggeren: programmet per døgn og sted, med beredskapsnivå
// og behov (tavleplanleggeren, 23. sep. 2026, etter skissene i Artifact
// «Tavleplanleggeren»).
//
// Fjerde av KOs fem filer (`KO_JS` i patients/js_test_utils.py), lastet etter
// ko-tavle.js — den bruker `koTavleDognnokkel` og `koTavleHHMM` derfra.
// Ingenting kjører på toppnivå her: `koPlanStart()` kalles fra
// `DOMContentLoaded` i ko.js, som er den siste fila.
//
// **Vinduet deler plass med oppdragslista** (`KO_PAR` i ko-layout.js) og står
// parkert som standard — André: «inni i ko rutenettet med samme løsning som
// tavlen, at den er minimert».
//
// **Alle med `les` i KO ser programmet; KO-leder skriver** (André: «KO-leder»).
// **Typen setter ingen ressurser** — behovet skrives inn for hånd.
// ════════════════════════════════════════════════════════════════════════════

//: Programmet endres i timer, ikke i sekunder — og tavla henter det med seg.
const KO_PLAN_MS = 60000;

//: Så mange døgn fram fra vaktstart (eller i dag) planleggeren tilbyr, i
//: tillegg til døgnene som alt har konserter.
const KO_PLAN_DOGN = 5;

let koPlan = null;           // svaret fra /ko/api/program/
let koPlanDogn = null;       // valgt døgn, `YYYY-MM-DD`
let koPlanSkjema = null;     // åpent skjema: {id} (null = ny)
let koPlanVisning = 'tidslinje';  // 'tidslinje' | 'liste' (steg 4)
let koPlanDekning = null;    // {dogn, timer} eller {dogn, feil} fra /ko/api/program/dekning/
let koPlanDekningGruppe = null;   // gruppa stripa viser
let koPlanEtterpaa = null;   // svaret fra /ko/api/program/etterpaa/ (steg 5)
let koPlanEtterpaaVakt = null;    // valgt vakt i «Etterpå», `null` = aktiv

//: En time i millisekunder — tidslinja og stripa er døgnet i tjuefire.
const KO_PLAN_TIME = 3600000;

function koPlanKanLede() {
  return typeof koKanFjerne === 'function' ? koKanFjerne() : false;
}

function koPlanDognstart() {
  return (typeof koTavle !== 'undefined' && koTavle && koTavle.dognstart) || '06:00';
}

// ── Reglene ──────────────────────────────────────────────────────────────────

// Døgnene planleggeren tilbyr: fra vaktstart — eller i dag — og noen døgn
// fram, **pluss hvert døgn som alt har en konsert**, så ingenting i
// programmet står utenfor det man kan velge.
function koPlanDognene(poster, startMs, naaMs, dognstart) {
  const sett = new Set();
  const fra = Number.isFinite(startMs) ? Math.min(startMs, naaMs) : naaMs;
  for (let i = 0; i < KO_PLAN_DOGN; i += 1) sett.add(koTavleDognnokkel(fra + i * 86400000, dognstart));
  (poster || []).forEach((p) => sett.add(koTavleDognnokkel(Date.parse(p.fra), dognstart)));
  return Array.from(sett).sort();
}

// Et klokkeslett i et døgn: **før døgnstarten hører det til neste kalenderdag**
// — «01:00» fredag er natt til lørdag, som på tavla og i «Besøk».
function koPlanTid(dogn, hhmm, dognstart) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || '').trim());
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dogn || ''));
  if (!m || !d || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  const [st, sm] = String(dognstart || '06:00').split(':').map(Number);
  const t = new Date(Number(d[1]), Number(d[2]) - 1, Number(d[3]), Number(m[1]), Number(m[2]), 0, 0);
  if (Number(m[1]) * 60 + Number(m[2]) < (st || 0) * 60 + (sm || 0)) t.setDate(t.getDate() + 1);
  return t.getTime();
}

// «Til» er **første gang klokka viser det etter «fra»** — 22:00–00:30 går
// over midnatt av seg selv, og 22:00–22:00 er et helt døgn, ikke null.
function koPlanTil(fraMs, hhmm) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || '').trim());
  if (!m || !Number.isFinite(fraMs) || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  const t = new Date(fraMs);
  t.setHours(Number(m[1]), Number(m[2]), 0, 0);
  while (t.getTime() <= fraMs) t.setDate(t.getDate() + 1);
  return t.getTime();
}

// Postene i ett døgn, gruppert på sted i den rekkefølgen stedene først
// dukker opp, og i tidsrekkefølge innenfor.
function koPlanGruppert(poster, dogn, dognstart) {
  const grupper = new Map();
  (poster || []).filter((p) => koTavleDognnokkel(Date.parse(p.fra), dognstart) === dogn)
    .sort((a, b) => Date.parse(a.fra) - Date.parse(b.fra))
    .forEach((p) => {
      const k = p.lokasjon_navn || '';
      if (!grupper.has(k)) grupper.set(k, []);
      grupper.get(k).push(p);
    });
  return Array.from(grupper, ([sted, liste]) => ({ sted, poster: liste }));
}

// «4 Lag · 1 Mannskapsbil · 2 Ambulanse» — behovet som tekst.
function koPlanBehovTekst(behov) {
  return (behov || []).map((b) => b.antall + ' ' + b.gruppe_navn).join(' · ');
}

// Kroppen skjemaet sender. `{feil}` når noe mangler — sagt ved knappen, ikke
// som en 400. Tomt antall er null, og tas ut.
function koPlanKropp(v, dognstart) {
  if (!v.lokasjon_id) return { feil: 'Velg stedet.' };
  if (!String(v.navn || '').trim()) return { feil: 'Konserten må ha et navn.' };
  const fra = koPlanTid(v.dogn, v.fra, dognstart);
  const til = fra === null ? null : koPlanTil(fra, v.til);
  if (fra === null || til === null) return { feil: 'Fyll inn klokkeslettene som TT:MM.' };
  const publikum = String(v.publikum || '').trim();
  if (publikum && !/^\d+$/.test(publikum)) return { feil: 'Forventet publikum må være et tall.' };
  const behov = [];
  for (const [gruppe, antall] of Object.entries(v.behov || {})) {
    const a = String(antall || '').trim();
    if (!a) continue;
    if (!/^\d+$/.test(a)) return { feil: 'Behovet må være hele tall.' };
    if (Number(a) > 0) behov.push({ gruppe_id: Number(gruppe), antall: Number(a) });
  }
  return {
    kropp: {
      lokasjon_id: Number(v.lokasjon_id),
      navn: String(v.navn).trim(),
      konserttype_id: v.konserttype_id ? Number(v.konserttype_id) : null,
      beredskap: v.beredskap || '',
      fra: new Date(fra).toISOString(),
      til: new Date(til).toISOString(),
      publikum: publikum ? Number(publikum) : null,
      kjennetegn: (v.kjennetegn || []).map(Number),
      behov,
    },
  };
}

// ── Tidslinja og dekningen (steg 4) ──────────────────────────────────────────

// Døgnet som et tidsvindu: fra døgnstarten, tjuefire timer. (En natt med
// sommertid er en time kortere eller lengre; stripa har likevel 24 søyler.)
function koPlanDognVindu(dogn, dognstart) {
  const fra = koPlanTid(dogn, dognstart, dognstart);
  return fra === null ? null : { fra, til: fra + 24 * KO_PLAN_TIME };
}

// Radene i tidslinja: **stedene som har noe i døgnet**, i stedslistas
// rekkefølge — som tavla. Konserter som overlapper på samme sted får hver sin
// bane, ellers ligger den ene oppå den andre.
function koPlanTidslinje(poster, vindu, steder) {
  const orden = new Map((steder || []).map((l, i) => [l.id, i]));
  const rader = new Map();
  (poster || []).map((p) => ({ p, fra: Date.parse(p.fra), til: Date.parse(p.til) }))
    .filter((x) => x.fra < vindu.til && x.til > vindu.fra)
    .sort((a, b) => a.fra - b.fra)
    .forEach((x) => {
      const nokkel = x.p.lokasjon_id ? 'id:' + x.p.lokasjon_id : 'navn:' + x.p.lokasjon_navn;
      if (!rader.has(nokkel)) {
        rader.set(nokkel, { sted: x.p.lokasjon_navn, rekke: orden.has(x.p.lokasjon_id) ? orden.get(x.p.lokasjon_id) : 1e6,
                            baner: [], poster: [] });
      }
      const r = rader.get(nokkel);
      let bane = r.baner.findIndex((slutt) => slutt <= x.fra);
      if (bane < 0) { bane = r.baner.length; r.baner.push(0); }
      r.baner[bane] = x.til;
      r.poster.push({ post: x.p, bane, venstre: koTavleProsent(x.fra, vindu), hoyre: 100 - koTavleProsent(x.til, vindu) });
    });
  return Array.from(rader.values()).sort((a, b) => a.rekke - b.rekke || a.sted.localeCompare(b.sted))
    .map((r) => ({ sted: r.sted, poster: r.poster, baner: Math.max(1, r.baner.length) }));
}

// Behovet time for time, per gruppe: **en konsert teller i hver time den
// berører** — 22:30–23:30 trenger folk i både 22- og 23-timen. Det er
// forsiktig med vilje: to konserter som bare deler et kvarter, telles begge
// i den timen, og stripa sier heller «for få» enn «nok» når den er i tvil.
function koPlanBehovPerTime(poster, vindu) {
  const timer = Array.from({ length: 24 }, () => new Map());
  (poster || []).forEach((p) => {
    const fra = Date.parse(p.fra);
    const til = Date.parse(p.til);
    for (let i = 0; i < 24; i += 1) {
      const a = vindu.fra + i * KO_PLAN_TIME;
      if (!(fra < a + KO_PLAN_TIME && til > a)) continue;
      (p.behov || []).forEach((b) => {
        if (!b.gruppe_id) return;
        const k = String(b.gruppe_id);
        timer[i].set(k, (timer[i].get(k) || 0) + b.antall);
      });
    }
  });
  return timer;
}

// Starten på time `i` i døgnet.
function koPlanTimeStart(vindu, i) {
  return vindu.fra + i * KO_PLAN_TIME;
}

// Stripa for én gruppe: trengs mot på vakt, per time. `har` er `null` når
// vaktlistas tall ikke er hentet — da er ingenting «for få».
function koPlanDekningForGruppe(behovPerTime, timer, gruppeId) {
  return behovPerTime.map((m, i) => {
    const trengs = m.get(String(gruppeId)) || 0;
    const har = timer && timer[i] ? (timer[i].grupper[String(gruppeId)] || 0) : null;
    return { i, trengs, har, kort: har !== null && trengs > har };
  });
}

// Gruppene stripa kan vise: dem som har et behov i døgnet, i gruppenes
// rekkefølge. Uten behov er det ingenting å sammenligne.
function koPlanDekningsgrupper(behovPerTime, grupper) {
  const med = new Set();
  behovPerTime.forEach((m) => m.forEach((antall, k) => { if (antall > 0) med.add(k); }));
  return (grupper || []).filter((g) => med.has(String(g.id)));
}

// ── Byggerne ─────────────────────────────────────────────────────────────────

function koPlanBeredskapHtml(p) {
  if (!['gronn', 'gul', 'oransje', 'rod'].includes(p.beredskap)) return '';
  return '<span class="ko-plan-beredskap ko-beredskap-' + escapeHtml(p.beredskap) + '">'
    + escapeHtml(p.beredskap_navn || '') + '</span>';
}

function koPlanPostHtml(p, kanLede) {
  const tid = koTavleHHMM(Date.parse(p.fra)) + '–' + koTavleHHMM(Date.parse(p.til));
  const kjennetegn = (p.kjennetegn || []).map((k) => '<span class="ko-plan-kjennetegn">' + escapeHtml(k.navn)
    + '</span>').join('');
  const behov = koPlanBehovTekst(p.behov);
  const aapne = kanLede
    ? ' data-action="koPlanApne" data-arg="' + escapeHtml(p.id) + '" role="button" tabindex="0" title="Klikk for å endre"'
    : '';
  return '<div class="ko-plan-post"' + aapne + '>'
    + '<span class="ko-plan-tid">' + escapeHtml(tid) + '</span>'
    + '<span class="ko-plan-navn">' + escapeHtml(p.navn)
    + (p.konserttype_navn ? ' <span class="ko-plan-type">' + escapeHtml(p.konserttype_navn) + '</span>' : '')
    + '</span>'
    + koPlanBeredskapHtml(p)
    + '<span class="ko-plan-behov">' + (behov ? escapeHtml(behov) : '<span class="ko-plan-dempet">ingen behov satt</span>')
    + (p.publikum ? ' · ' + escapeHtml(String(p.publikum)) + ' publikum' : '') + '</span>'
    + (kjennetegn ? '<span class="ko-plan-kjennetegnene">' + kjennetegn + '</span>' : '')
    + '</div>';
}

function koPlanListeHtml(grupper, kanLede) {
  if (!grupper.length) {
    return '<div class="tom-melding">Ingen konserter dette døgnet.'
      + (kanLede ? ' Legg til med «+ Konsert».' : '') + '</div>';
  }
  return grupper.map((g) => {
    const rader = g.poster.map((p) => koPlanPostHtml(p, kanLede)).join('');
    return '<div class="ko-plan-sted"><div class="ko-plan-stednavn">' + escapeHtml(g.sted) + '</div>' + rader + '</div>';
  }).join('');
}

function koPlanDognvalgHtml(dognene, valgt) {
  return dognene.map((k) => '<button type="button" class="btn btn-outline-secondary'
    + (k === valgt ? ' active' : '') + '" data-action="koPlanVelgDogn" data-arg="' + escapeHtml(k) + '">'
    + escapeHtml(koTavleDognnavn(k)) + '</button>').join('');
}

function koPlanTidslinjeHtml(rader, vindu, kanLede, naaMs) {
  const timer = [];
  for (let i = 0; i < 24; i += 2) {
    const t = vindu.fra + i * KO_PLAN_TIME;
    timer.push('<span class="ko-plan-time" style="left:' + escapeHtml(koTavleProsent(t, vindu).toFixed(2)) + '%">'
      + escapeHtml(koTavleHHMM(t).slice(0, 2)) + '</span>');
  }
  const naa = naaMs >= vindu.fra && naaMs < vindu.til
    ? '<div class="ko-plan-naa" style="left:' + escapeHtml(koTavleProsent(naaMs, vindu).toFixed(2)) + '%"></div>' : '';
  const radHtml = rader.map((r) => {
    const baand = r.poster.map((x) => {
      const p = x.post;
      const behov = koPlanBehovTekst(p.behov);
      const tekst = p.navn + (behov ? ' · ' + behov : '');
      const tittel = [p.navn, koTavleHHMM(Date.parse(p.fra)) + '–' + koTavleHHMM(Date.parse(p.til)),
                      p.beredskap_navn ? ['Beredskap', p.beredskap_navn.toLowerCase()].join(' ') : '', behov]
        .filter(Boolean).join(' · ');
      const aapne = kanLede ? ' data-action="koPlanApne" data-arg="' + escapeHtml(p.id) + '" role="button" tabindex="0"' : '';
      return '<div class="ko-plan-baand' + (['gronn', 'gul', 'oransje', 'rod'].includes(p.beredskap)
        ? ' ko-beredskap-' + escapeHtml(p.beredskap) : '') + '" style="left:' + escapeHtml(x.venstre.toFixed(2))
        + '%;right:' + escapeHtml(x.hoyre.toFixed(2)) + '%;top:' + escapeHtml(String(x.bane * 30 + 3)) + 'px"'
        + aapne + ' title="' + escapeHtml(tittel) + '">' + escapeHtml(tekst) + '</div>';
    }).join('');
    return '<div class="ko-plan-rad"><div class="ko-plan-radnavn">' + escapeHtml(r.sted) + '</div>'
      + '<div class="ko-plan-spor" style="height:' + escapeHtml(String(r.baner * 30 + 6)) + 'px">' + naa + baand + '</div></div>';
  }).join('');
  return '<div class="ko-plan-tidslinje"><div class="ko-plan-rad ko-plan-akse"><div class="ko-plan-radnavn"></div>'
    + '<div class="ko-plan-spor">' + timer.join('') + '</div></div>'
    + (radHtml || '<div class="tom-melding">Ingen konserter dette døgnet.</div>') + '</div>';
}

function koPlanDekningHtml(stripe, grupper, valgt, vindu, feil) {
  if (feil) return '<div class="ko-plan-dekning"><div class="ko-plan-dempet small">' + escapeHtml(feil) + '</div></div>';
  if (!grupper.length) {
    return '<div class="ko-plan-dekning"><div class="ko-plan-dempet small">Ingen behov satt dette døgnet — '
      + 'stripa sammenligner behovet med vaktlista når det finnes.</div></div>';
  }
  const faner = grupper.map((g) => '<button type="button" class="btn btn-outline-secondary'
    + (String(g.id) === String(valgt) ? ' active' : '') + '" data-action="koPlanVelgDekning" data-arg="'
    + escapeHtml(g.id) + '">' + escapeHtml(g.navn) + '</button>').join('');
  const hoyest = Math.max(1, ...stripe.map((s) => Math.max(s.trengs, s.har || 0)));
  const soyler = stripe.map((s) => {
    const kl = koTavleHHMM(koPlanTimeStart(vindu, s.i)).slice(0, 2);
    const tittel = [kl, ': ', s.trengs, ' trengs, ', s.har === null ? '?' : s.har, ' på vakt'].join('');
    return '<div class="ko-plan-soyle' + (s.kort ? ' ko-plan-kort' : '') + '" title="' + escapeHtml(tittel) + '">'
      + '<div class="ko-plan-har" style="height:' + escapeHtml(((s.har || 0) / hoyest * 100).toFixed(1)) + '%"></div>'
      + '<div class="ko-plan-trengs" style="height:' + escapeHtml((s.trengs / hoyest * 100).toFixed(1)) + '%"></div>'
      + '<span class="ko-plan-tall">' + escapeHtml(s.trengs ? String(s.trengs) + '/' + (s.har === null ? '?' : String(s.har)) : '')
      + '</span></div>';
  }).join('');
  const timer = stripe.map((s) => '<span>' + escapeHtml(koTavleHHMM(koPlanTimeStart(vindu, s.i)).slice(0, 2))
    + '</span>').join('');
  return '<div class="ko-plan-dekning"><div class="d-flex flex-wrap align-items-center gap-2 mb-1">'
    + '<span class="small fw-semibold">Dekning</span><div class="btn-group btn-group-sm flex-wrap">' + faner + '</div>'
    + '<span class="small ko-plan-dempet">trengs / på vakt i vaktlista</span></div>'
    + '<div class="ko-plan-soyler">' + soyler + '</div><div class="ko-plan-timer">' + timer + '</div></div>';
}

// ── Etterpå: plan mot faktisk (steg 5) ───────────────────────────────────────

// Det faktiske for én gruppe, som tekst. «3,6 i snitt · 48 min under» — og
// ingenting å si før konserten har begynt.
function koPlanFaktiskTekst(b, startet) {
  if (!startet || b.snitt === null || b.snitt === undefined) return 'ikke begynt';
  const snitt = String(b.snitt).replace('.', ',') + ' i snitt';
  return b.under_min ? snitt + ' · ' + b.under_min + ' min under' : snitt;
}

// En rad i historikken, som tekst: hva, og for en endring hvert felt fra → til.
function koPlanEndringTekst(e) {
  if (e.hva === 'endret') {
    return e.navn + ': ' + (e.detaljer || []).map((d) => d.felt + ' ' + (d.fra || '–') + ' → ' + (d.til || '–')).join(', ');
  }
  const d = e.detaljer || {};
  return e.navn + ' ' + (e.hva === 'slettet' ? 'slettet' : 'lagt til')
    + [d.sted, d.tid, d.beredskap ? 'beredskap ' + d.beredskap.toLowerCase() : '', d.behov]
      .filter(Boolean).map((x) => ' · ' + x).join('');
}

function koPlanEtterpaaHtml(data, kanLede, aktivId) {
  const vakter = (data.vakter || []).map((v) => '<option value="' + escapeHtml(v.id) + '"'
    + (v.id === data.vakt.id ? ' selected' : '') + '>' + escapeHtml(v.navn) + '</option>').join('');
  const velger = kanLede && (data.vakter || []).length > 1
    ? '<label class="small">Vakt <select class="form-select form-select-sm d-inline-block w-auto" id="ko-plan-vakt"'
      + ' data-action="koPlanVelgVakt" data-hendelse="change">' + vakter + '</select></label>' : '';
  const kopier = kanLede && data.vakt.id !== aktivId && (data.poster || []).length
    ? '<span class="d-inline-flex align-items-end gap-1 ms-2"><label class="small">Første konsertdøgn i aktiv vakt'
      + ' <input type="date" class="form-control form-control-sm" id="ko-plan-kopier-dogn"></label>'
      + '<button type="button" class="btn btn-sm btn-outline-primary" data-action="koPlanKopier">'
      + 'Kopier programmet hit</button></span>' : '';
  const rader = (data.poster || []).map((p) => {
    const behov = (p.behov || []).map((b) => '<div>' + escapeHtml([b.trengs, b.gruppe_navn].join(' ')) + '</div>').join('')
      || '<span class="ko-plan-dempet">–</span>';
    const opprinnelig = p.behov_opprinnelig !== null && p.behov_opprinnelig !== undefined
      && p.behov_opprinnelig !== p.behov_naa
      ? '<div class="ko-plan-dempet small">opprinnelig: ' + escapeHtml(p.behov_opprinnelig || 'ingen') + '</div>' : '';
    const faktisk = (p.behov || []).map((b) => '<div' + (b.under_min ? ' class="ko-plan-under"' : '') + '>'
      + escapeHtml([b.gruppe_navn, koPlanFaktiskTekst(b, p.startet)].join(': ')) + '</div>').join('')
      || '<span class="ko-plan-dempet">–</span>';
    const oppdrag = p.oppdrag === null || p.oppdrag === undefined ? '–' : String(p.oppdrag);
    return '<tr><td><div class="fw-semibold">' + escapeHtml(p.navn) + '</div><div class="ko-plan-dempet small">'
      + escapeHtml([p.sted, p.tid, p.type].filter(Boolean).join(' · ')) + '</div></td>'
      + '<td>' + koPlanBeredskapHtml(p) + '</td>'
      + '<td>' + behov + opprinnelig + '</td><td>' + faktisk + '</td>'
      + '<td class="text-end">' + escapeHtml(oppdrag) + '</td>'
      + '<td class="text-end">' + escapeHtml(p.endringer ? String(p.endringer) : '–') + '</td></tr>';
  }).join('');
  const historikk = (data.endringer || []).slice().reverse().map((e) => '<li><span class="ko-plan-tid">'
    + escapeHtml(koTavleHHMM(Date.parse(e.tidspunkt))) + '</span> ' + escapeHtml(koPlanEndringTekst(e))
    + (e.av_navn ? ' <span class="ko-plan-dempet">(' + escapeHtml(e.av_navn) + ')</span>' : '') + '</li>').join('');
  return '<div class="d-flex flex-wrap align-items-end gap-2 mb-2">' + velger + kopier + '</div>'
    + (rader
      ? '<div class="table-responsive"><table class="table table-sm ko-plan-etterpaa"><thead><tr><th>Konsert</th>'
        + '<th>Beredskap</th><th>Behov</th><th>Faktisk på stedet</th><th class="text-end">Oppdrag</th>'
        + '<th class="text-end">Endret</th></tr></thead><tbody>' + rader + '</tbody></table></div>'
      : '<div class="tom-melding">Ingen konserter i denne vakta.</div>')
    + '<div class="small ko-plan-dempet mb-1">«Faktisk» er tavlas plasseringer på stedet, også tida på en hendelse '
    + 'der — ikke bilenes tid på oppdrag. Oppdrag er antall på stedet mens konserten pågikk.</div>'
    + (historikk ? '<div class="fw-semibold small mt-2">Endringer</div><ul class="ko-plan-historikk">' + historikk + '</ul>' : '');
}

// Hva skjemaet skal vise: den valgte posten, eller en ny i valgt døgn.
function koPlanSkjemaData(skjema, data, dogn) {
  if (!skjema || !data) return null;
  const p = skjema.id ? (data.poster || []).find((x) => x.id === skjema.id) : null;
  if (skjema.id && !p) return null;
  return {
    id: p ? p.id : null,
    tittel: p ? 'Endre · ' + p.navn : 'Ny konsert',
    lokasjon_id: p ? p.lokasjon_id : null,
    navn: p ? p.navn : '',
    dogn: p ? koTavleDognnokkel(Date.parse(p.fra), koPlanDognstart()) : dogn,
    fra: p ? koTavleHHMM(Date.parse(p.fra)) : '',
    til: p ? koTavleHHMM(Date.parse(p.til)) : '',
    konserttype_id: p ? p.konserttype_id : null,
    beredskap: p ? p.beredskap : '',
    publikum: p && p.publikum ? String(p.publikum) : '',
    kjennetegn: p ? p.kjennetegn.map((k) => k.id) : [],
    behov: p ? Object.fromEntries(p.behov.filter((b) => b.gruppe_id).map((b) => [b.gruppe_id, b.antall])) : {},
  };
}

function koPlanSkjemaHtml(d, data, steder, dognene) {
  const stedValg = velgValg(d.lokasjon_id ? String(d.lokasjon_id) : '') + (steder || []).map((l) => '<option value="'
    + escapeHtml(l.id) + '"' + (l.id === d.lokasjon_id ? ' selected' : '') + '>' + escapeHtml(l.navn) + '</option>').join('');
  const dognValg = (dognene || []).map((k) => '<option value="' + escapeHtml(k) + '"' + (k === d.dogn ? ' selected' : '')
    + '>' + escapeHtml(koTavleDognnavn(k)) + '</option>').join('');
  // Typen og kjennetegnene: de aktive, pluss dem posten alt har.
  const typer = (data.konserttyper || []).filter((t) => t.er_aktiv || t.id === d.konserttype_id);
  const typeValg = velgValg(d.konserttype_id ? String(d.konserttype_id) : '') + typer.map((t) => '<option value="'
    + escapeHtml(t.id) + '"' + (t.id === d.konserttype_id ? ' selected' : '') + '>' + escapeHtml(t.navn) + '</option>').join('');
  const beredskap = [{ verdi: '', navn: 'Ikke satt' }].concat(data.beredskap || []).map((b) => '<label class="ko-plan-nivaa'
    + (b.verdi ? ' ko-beredskap-' + escapeHtml(b.verdi) : '') + '"><input type="radio" name="ko-plan-beredskap" value="'
    + escapeHtml(b.verdi) + '"' + (b.verdi === d.beredskap ? ' checked' : '') + '> ' + escapeHtml(b.navn) + '</label>').join('');
  const kjennetegn = (data.kjennetegn || []).filter((k) => k.er_aktiv || d.kjennetegn.includes(k.id))
    .map((k) => '<label class="form-check form-check-inline small"><input type="checkbox" class="form-check-input"'
      + ' data-plan-kjennetegn value="' + escapeHtml(k.id) + '"' + (d.kjennetegn.includes(k.id) ? ' checked' : '') + '> '
      + escapeHtml(k.navn) + '</label>').join('');
  const behov = (data.grupper || []).map((g) => '<label class="ko-plan-behov-felt small">' + escapeHtml(g.navn)
    + ' <input type="number" min="0" max="99" class="form-control form-control-sm" data-plan-behov="' + escapeHtml(g.id)
    + '" value="' + escapeHtml(d.behov[g.id] ? String(d.behov[g.id]) : '') + '"></label>').join('');
  return '<div class="ko-tavle-skjema-tittel">' + escapeHtml(d.tittel) + '</div>'
    + '<div class="ko-plan-skjema-rad">'
    + '<label class="small">Sted <select class="form-select form-select-sm" id="ko-plan-sted">' + stedValg + '</select></label>'
    + '<label class="small ko-plan-navnefelt">Navn <input type="text" maxlength="120" class="form-control form-control-sm"'
    + ' id="ko-plan-navn" value="' + escapeHtml(d.navn) + '"></label>'
    + '<label class="small">Døgn <select class="form-select form-select-sm" id="ko-plan-dogn">' + dognValg + '</select></label>'
    + '<label class="small">Fra <input type="time" class="form-control form-control-sm" id="ko-plan-fra" value="'
    + escapeHtml(d.fra) + '"></label>'
    + '<label class="small">Til <input type="time" class="form-control form-control-sm" id="ko-plan-til" value="'
    + escapeHtml(d.til) + '"></label>'
    + '<label class="small">Type <select class="form-select form-select-sm" id="ko-plan-type">' + typeValg + '</select></label>'
    + '<label class="small">Forventet publikum <input type="number" min="0" class="form-control form-control-sm"'
    + ' id="ko-plan-publikum" value="' + escapeHtml(d.publikum) + '"></label>'
    + '</div>'
    + '<div class="ko-plan-skjema-rad"><span class="small ko-plan-dempet">Beredskapsnivå</span>' + beredskap + '</div>'
    + (kjennetegn ? '<div class="ko-plan-skjema-rad"><span class="small ko-plan-dempet">Kjennetegn</span>' + kjennetegn + '</div>' : '')
    + '<div class="ko-plan-skjema-rad"><span class="small ko-plan-dempet">Behov</span>' + behov + '</div>'
    + '<div class="d-flex flex-wrap gap-2 mt-1">'
    + '<button type="button" class="btn btn-sm btn-primary" data-action="koPlanLagre">Lagre</button>'
    + '<button type="button" class="btn btn-sm btn-outline-secondary" data-action="koPlanLukk">Avbryt</button>'
    + (d.id ? '<button type="button" class="btn btn-sm btn-outline-danger ms-auto" data-action="koPlanSlett">Slett konserten</button>' : '')
    + '</div><div class="small ko-plan-dempet mt-1">Typen setter ingen ressurser — behovet skrives inn for hånd. '
    + 'Et klokkeslett før døgnstarten hører til natta etter.</div>';
}

// ── Tegning og handlinger ────────────────────────────────────────────────────

// Stedene kommer med programmet — ikke fra sentralbordets `lokasjoner`, som
// bare finnes med oppdragstilgang. Et sted posten alt står på, er med selv om
// det er gjort inaktivt, så en endring ikke flytter konserten stille.
function koPlanSteder(data, lokasjonId) {
  const steder = (data && data.steder) || [];
  const post = lokasjonId && !steder.some((l) => l.id === lokasjonId)
    ? (data.poster || []).find((p) => p.lokasjon_id === lokasjonId) : null;
  return post ? steder.concat([{ id: lokasjonId, navn: post.lokasjon_navn }]) : steder;
}

function koTegnPlan() {
  const boks = document.getElementById('ko-plan');
  if (!boks || !koPlan) return;
  const naa = Date.now() + (typeof koTavleKlokkeavvik !== 'undefined' ? koTavleKlokkeavvik : 0);
  const start = typeof koTavle !== 'undefined' && koTavle ? Date.parse(koTavle.vakt_start) : NaN;
  const dognene = koPlanDognene(koPlan.poster, start, naa, koPlanDognstart());
  if (!dognene.includes(koPlanDogn)) {
    const idag = koTavleDognnokkel(naa, koPlanDognstart());
    koPlanDogn = dognene.includes(idag) ? idag : dognene[0];
  }
  const valg = document.getElementById('ko-plan-dogn-valg');
  if (valg) {
    valg.innerHTML = koPlanDognvalgHtml(dognene, koPlanDogn);
    // «Etterpå» er hele vakta — et døgnvalg der ville sett ut som et filter.
    valg.classList.toggle('d-none', koPlanVisning === 'etterpaa');
  }
  const tall = document.getElementById('ko-plan-antall');
  if (tall) tall.textContent = '· ' + (koPlan.poster || []).length + ' i programmet';
  const skjema = document.getElementById('ko-plan-skjema');
  if (skjema) {
    const d = koPlanSkjemaData(koPlanSkjema, koPlan, koPlanDogn);
    // Et åpent skjema tegnes ikke om av pollen — feltet skal ikke tømmes.
    const nokkel = d ? String(d.id || 'ny') : '';
    if (!(d && skjema.dataset.skjema === nokkel)) {
      skjema.dataset.skjema = nokkel;
      skjema.classList.toggle('d-none', !d);
      skjema.innerHTML = d ? koPlanSkjemaHtml(d, koPlan, koPlanSteder(koPlan, d.lokasjon_id), dognene) : '';
    }
  }
  document.querySelectorAll('[data-action="koPlanVelgVisning"]').forEach((k) => {
    k.classList.toggle('active', k.getAttribute('data-arg') === koPlanVisning);
  });
  if (koPlanVisning === 'etterpaa') {
    if (!koPlanEtterpaa) { koHentEtterpaa(); boks.innerHTML = '<div class="tom-melding">Henter …</div>'; return; }
    boks.innerHTML = koPlanEtterpaaHtml(koPlanEtterpaa, koPlanKanLede(), koPlanAktivVakt());
    return;
  }
  if (koPlanVisning === 'liste') {
    boks.innerHTML = koPlanListeHtml(koPlanGruppert(koPlan.poster, koPlanDogn, koPlanDognstart()), koPlanKanLede());
    return;
  }
  const vindu = koPlanDognVindu(koPlanDogn, koPlanDognstart());
  if (!vindu) { boks.innerHTML = ''; return; }
  const perTime = koPlanBehovPerTime(koPlan.poster, vindu);
  const grupper = koPlanDekningsgrupper(perTime, koPlan.grupper);
  if (!grupper.some((g) => String(g.id) === String(koPlanDekningGruppe))) {
    koPlanDekningGruppe = grupper.length ? grupper[0].id : null;
  }
  const dekning = koPlanDekning && koPlanDekning.dogn === koPlanDogn ? koPlanDekning : null;
  const stripe = koPlanDekningForGruppe(perTime, dekning && dekning.timer, koPlanDekningGruppe);
  boks.innerHTML = koPlanTidslinjeHtml(koPlanTidslinje(koPlan.poster, vindu, koPlan.steder), vindu, koPlanKanLede(), naa)
    + koPlanDekningHtml(stripe, grupper, koPlanDekningGruppe, vindu, dekning && dekning.feil);
  if (!dekning) koHentDekning(koPlanDogn);
}

function koPlanVisFeil(melding) {
  const el = document.getElementById('ko-plan-feil');
  if (!el) return;
  el.textContent = melding || '';
  el.classList.toggle('d-none', !melding);
}

function koPlanVelgDogn(k) {
  koPlanDogn = String(k);
  koTegnPlan();
}

function koPlanVelgVisning(v) {
  koPlanVisning = ['liste', 'etterpaa'].includes(v) ? v : 'tidslinje';
  if (koPlanVisning === 'etterpaa') koPlanEtterpaa = null;
  koTegnPlan();
}

function koPlanAktivVakt() {
  return (koPlan && koPlan.vakt_id) || null;
}

async function koHentEtterpaa() {
  const url = '/ko/api/program/etterpaa/' + (koPlanEtterpaaVakt ? '?vakt=' + Number(koPlanEtterpaaVakt) : '');
  const res = await apiFetch(url);
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { koPlanVisFeil(d.message || 'Kunne ikke hente plan mot faktisk.'); return; }
  koPlanEtterpaa = d.data || null;
  koTegnPlan();
}

function koPlanVelgVakt() {
  const el = document.getElementById('ko-plan-vakt');
  koPlanEtterpaaVakt = el && Number(el.value) !== koPlanAktivVakt() ? Number(el.value) : null;
  koPlanEtterpaa = null;
  koTegnPlan();
}

async function koPlanKopier(bekreftet) {
  if (!koPlanEtterpaa) return;
  const dogn = (document.getElementById('ko-plan-kopier-dogn') || {}).value || '';
  if (!dogn) { koPlanVisFeil('Velg første konsertdøgn i aktiv vakt.'); return; }
  const kropp = { fra_vakt_id: koPlanEtterpaa.vakt.id, forste_dogn: dogn };
  if (bekreftet === true) kropp.confirm = true;
  const res = await apiFetch('/ko/api/program/kopier/', { method: 'POST', body: JSON.stringify(kropp) });
  const d = await res.json().catch(() => ({}));
  if (res.status === 409 && bekreftet !== true) {
    if (window.confirm(d.message || 'Vakta har alt et program. Legge til likevel?')) await koPlanKopier(true);
    return;
  }
  if (!res.ok) { koPlanVisFeil(d.message || 'Kunne ikke kopiere.'); return; }
  const svar = d.data || {};
  koPlanVisFeil((svar.hoppet_over || []).length
    ? 'Kopierte ' + svar.kopiert + '. Hoppet over: ' + svar.hoppet_over.join('; ') : '');
  koPlanEtterpaaVakt = null;
  koPlanEtterpaa = null;
  koPlanVisning = 'tidslinje';
  await koHentPlan();
}

function koPlanVelgDekning(id) {
  koPlanDekningGruppe = Number(id);
  koTegnPlan();
}

// Vaktlistas tall for døgnet. **Hentes ett døgn om gangen**, når døgnet
// vises og ved hver runde — tjuefire tellinger er for mye å gjøre ved hver
// tegning. Uten vaktlistetilgang sier stripa hvorfor, i stedet for å vise null.
let koPlanDekningHenter = null;
async function koHentDekning(dogn) {
  if (!dogn || koPlanDekningHenter === dogn) return;
  koPlanDekningHenter = dogn;
  try {
    const res = await apiFetch('/ko/api/program/dekning/?dogn=' + encodeURIComponent(dogn));
    const d = await res.json().catch(() => ({}));
    koPlanDekning = res.ok ? { dogn, timer: (d.data || {}).timer || [] }
      : { dogn, feil: res.status === 403 ? 'Dekningen er vaktlistas tall, og krever lesetilgang i vaktlista.'
        : (d.message || 'Kunne ikke hente dekningen.') };
  } catch (e) {
    koPlanDekning = null;
  } finally {
    koPlanDekningHenter = null;
  }
  if (koPlanDogn === dogn) koTegnPlan();
}

function koPlanNy() {
  koPlanSkjema = { id: null };
  koPlanVisFeil('');
  koTegnPlan();
}

function koPlanApne(id) {
  if (!koPlanKanLede()) return;
  koPlanSkjema = { id: Number(id) };
  koPlanVisFeil('');
  koTegnPlan();
}

function koPlanLukk() {
  koPlanSkjema = null;
  koPlanVisFeil('');
  koTegnPlan();
}

function koPlanLesSkjema() {
  const verdi = (id) => { const el = document.getElementById(id); return el ? el.value : ''; };
  const behov = {};
  document.querySelectorAll('[data-plan-behov]').forEach((el) => { behov[el.getAttribute('data-plan-behov')] = el.value; });
  const nivaa = document.querySelector('input[name="ko-plan-beredskap"]:checked');
  return {
    lokasjon_id: verdi('ko-plan-sted'), navn: verdi('ko-plan-navn'), dogn: verdi('ko-plan-dogn'),
    fra: verdi('ko-plan-fra'), til: verdi('ko-plan-til'), konserttype_id: verdi('ko-plan-type'),
    publikum: verdi('ko-plan-publikum'), beredskap: nivaa ? nivaa.value : '',
    kjennetegn: Array.from(document.querySelectorAll('[data-plan-kjennetegn]')).filter((el) => el.checked)
      .map((el) => el.value),
    behov,
  };
}

async function koPlanSend(url, metode, kropp) {
  const res = await apiFetch(url, { method: metode, body: JSON.stringify(kropp || {}) });
  const d = await res.json().catch(() => ({}));
  koPlanVisFeil(res.ok ? '' : (d.message || 'Det gikk ikke.'));
  if (res.ok) {
    await koHentPlan();
    // Tavla viser programmet som bånd — den skal ikke vente på sin egen poll.
    if (typeof koTavleErFramme === 'function' && koTavleErFramme()) koHentTavle();
  }
  return res.ok;
}

async function koPlanLagre() {
  if (!koPlanSkjema) return;
  const r = koPlanKropp(koPlanLesSkjema(), koPlanDognstart());
  if (r.feil) { koPlanVisFeil(r.feil); return; }
  const url = koPlanSkjema.id ? '/ko/api/program/' + Number(koPlanSkjema.id) + '/' : '/ko/api/program/';
  if (await koPlanSend(url, koPlanSkjema.id ? 'PUT' : 'POST', r.kropp)) {
    koPlanDogn = document.getElementById('ko-plan-dogn')?.value || koPlanDogn;
    koPlanLukk();
  }
}

async function koPlanSlett() {
  if (!koPlanSkjema || !koPlanSkjema.id) return;
  if (!window.confirm('Slette konserten? Lag som følger den, mister den planlagte slutten.')) return;
  if (await koPlanSend('/ko/api/program/' + Number(koPlanSkjema.id) + '/', 'DELETE', {})) koPlanLukk();
}

// ── Lasting ──────────────────────────────────────────────────────────────────

function koPlanErFramme() {
  const vindu = document.querySelector('.ko-vindu[data-vindu="plan"]');
  return Boolean(vindu && !vindu.classList.contains('d-none'));
}

async function koHentPlan() {
  try {
    const res = await apiFetch('/ko/api/program/');
    if (!res.ok) return;
    koPlan = (await res.json()).data || null;
    // Vaktlistas tall kan ha endret seg siden sist — hent dem på nytt.
    koPlanDekning = null;
    koTegnPlan();
  } catch (e) {
    // Neste runde prøver igjen; planen står som den sto.
  }
}

// Kalles av `koTegnOppsett()` (ko-layout.js) hver gang vinduene tegnes.
function koPlanSynligNaa() {
  if (koPlanErFramme()) koHentPlan();
}

function koPlanStart() {
  if (!document.getElementById('ko-plan')) return;
  koPlanSynligNaa();
  setInterval(() => { if (koPlanErFramme()) koHentPlan(); }, KO_PLAN_MS);
}
