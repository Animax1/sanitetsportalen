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
  if (valg) valg.innerHTML = koPlanDognvalgHtml(dognene, koPlanDogn);
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
  boks.innerHTML = koPlanListeHtml(koPlanGruppert(koPlan.poster, koPlanDogn, koPlanDognstart()), koPlanKanLede());
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
