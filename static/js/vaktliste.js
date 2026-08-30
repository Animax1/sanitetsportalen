// ════════════════════════════════════════════════════════
// VAKTLISTE — planleggingssiden (fase 2)
//
// Lastes kun av /vaktliste/. Bruker primitivene i portal-utils.js
// (apiFetch, withSubmitGuard, escapeHtml, escHtmlValue, klokke) —
// patients-utils.js finnes ikke på denne siden og kan ikke lastes: den
// gjør arbeid på toppnivå som kaster uten pasientskjemaene.
//
// Alt som settes med innerHTML escapes. Navn på mannskap, ressurser og
// korps er data fra basen, og ressursnavn er fritekst satt av admin.
//
// Fanene bygges av ressursene — de er data, ikke kode, og tilpasser seg
// vaktas art av seg selv. To faste faner i tillegg: «Oversikt», som er den
// man skriver ut, og «Ikke plassert», som er de som er meldt på uten å stå
// noe sted ennå.
// ════════════════════════════════════════════════════════

let vaktlister = [];        // alle listene, til velgeren
let aktivListe = null;      // { vaktliste, ressurser, vaktposter, korps, roller, mannskap, enheter }
let aktivFane = 'oversikt'; // 'oversikt' | 'ikke-plassert' | ressurs-id som streng

const OVERSIKT = 'oversikt';
const IKKE_PLASSERT = 'ikke-plassert';


// ── Tilgang (fase 3) ─────────────────────────────────────────────────────
//
// Speiler services.py. Serveren håndhever uansett — dette avgjør bare hvilke
// knapper som tegnes, fordi en knapp som fører til en vegg er verre enn ingen
// knapp. Reglene står to steder med vilje, og de to stedene testes hver for
// seg: JS-en her i node, serveren i vaktliste/tests_tilgang.py.

function _nivaa() {
  return ((window.MODUL_TILGANG || {}).vaktliste || '').toLowerCase();
}


function kanSkriveAlt() {
  return (window.MODUL_TILGANG || {}).admin === true || _nivaa() === 'skriv_full';
}


function kanSkriveNoe() {
  return kanSkriveAlt() || _nivaa() === 'skriv_handling';
}


function kanBemanne(ressurs) {
  // Den ene halvdelen av den doble regelen: reservasjonen. En ureservert
  // ressurs er ikke et fristed — den er vaktlederens bord.
  if (kanSkriveAlt()) return true;
  if (_nivaa() !== 'skriv_handling') return false;
  return window.MITT_KORPS_ID != null && ressurs.korps_id === window.MITT_KORPS_ID;
}


function gateKnapper() {
  document.querySelectorAll('.vl-krev-full')
    .forEach((el) => el.classList.toggle('d-none', !kanSkriveAlt()));
}


// ── Tid: dato og dag, ikke bare klokkeslett ──────────────────────────────
//
// Et skift fra lørdag 20:00 til søndag 04:00 sto som «20:00–04:00», uten at
// noe sa at det krysset midnatt. Arrangementer varer flere dager, og da er
// klokkeslettet alene tvetydig.

const DAGER = ['søn', 'man', 'tir', 'ons', 'tor', 'fre', 'lør'];
const MND = ['jan', 'feb', 'mar', 'apr', 'mai', 'jun',
             'jul', 'aug', 'sep', 'okt', 'nov', 'des'];


function _d(iso) {
  // Tomt må sjekkes før `new Date`: `new Date(null)` gir epoken (1970), ikke
  // en ugyldig dato, så et tomt tidsfelt ville vist «01:00» i stedet for
  // ingenting.
  if (iso === null || iso === undefined || iso === '') return null;
  const d = new Date(iso);
  return isNaN(d) ? null : d;
}


function _kl(iso) {
  const d = _d(iso);
  if (!d) return '';
  return String(d.getHours()).padStart(2, '0') + ':'
       + String(d.getMinutes()).padStart(2, '0');
}


function _dag(iso) {
  const d = _d(iso);
  return d ? `${DAGER[d.getDay()]} ${d.getDate()}. ${MND[d.getMonth()]}` : '';
}


function _sammeDag(a, b) {
  const x = _d(a);
  const y = _d(b);
  return !!x && !!y && x.toDateString() === y.toDateString();
}


function _tidsspenn(vp) {
  // Dagen nevnes én gang når skiftet holder seg innenfor et døgn, og to
  // ganger når det ikke gjør det. Å alltid vise begge blir støy på en
  // endagsvakt; å aldri vise dem skjuler at skiftet krysser midnatt.
  if (_sammeDag(vp.fra_tid, vp.til_tid)) {
    return `${_dag(vp.fra_tid)} ${_kl(vp.fra_tid)}–${_kl(vp.til_tid)}`;
  }
  return `${_dag(vp.fra_tid)} ${_kl(vp.fra_tid)} – ${_dag(vp.til_tid)} ${_kl(vp.til_tid)}`;
}


function _vaktspenn() {
  // Vaktas spenn utledes av skiftene framfor å være et felt noen må fylle ut:
  // da holder det seg riktig av seg selv når lista endrer seg.
  const poster = (aktivListe && aktivListe.vaktposter) || [];
  if (!poster.length) return '';
  const fra = poster.map((v) => v.fra_tid).sort()[0];
  const til = poster.map((v) => v.til_tid).sort().slice(-1)[0];
  if (_sammeDag(fra, til)) return `${_dag(fra)} ${_kl(fra)}–${_kl(til)}`;
  return `${_dag(fra)} ${_kl(fra)} – ${_dag(til)} ${_kl(til)}`;
}


// ── Henting ──────────────────────────────────────────────────────────────

async function lastVaktlister() {
  const res = await apiFetch('/vaktliste/api/vaktlister/');
  if (!res.ok) return;
  vaktlister = (await res.json()).data || [];
  fyllVelger();

  document.getElementById('vl-tom')?.classList.toggle('d-none', vaktlister.length > 0);
  if (vaktlister.length) {
    await lastListe(vaktlister[0].id);
  } else {
    aktivListe = null;
    tegn();
  }
}


async function lastListe(id) {
  const res = await apiFetch(`/vaktliste/api/vaktlister/${id}/`);
  if (!res.ok) return;
  aktivListe = (await res.json()).data;
  const velger = document.getElementById('vaktliste-velger');
  if (velger) velger.value = String(id);

  document.getElementById('vl-mangler-mannskap')
    ?.classList.toggle('d-none', (aktivListe.mannskap || []).length > 0);

  fyllNedtrekk();
  tegn();
}


function byttVaktliste() {
  const velger = document.getElementById('vaktliste-velger');
  if (!velger || !velger.value) return;
  aktivFane = OVERSIKT;
  lastListe(Number(velger.value));
}


// ── Nedtrekk ─────────────────────────────────────────────────────────────

function _fyll(id, rader, tomtValg) {
  const el = document.getElementById(id);
  if (!el) return;
  const deler = tomtValg ? [`<option value="">${escapeHtml(tomtValg)}</option>`] : [];
  rader.forEach((r) => {
    deler.push(`<option value="${escHtmlValue(r.id)}">${escapeHtml(r.navn)}</option>`);
  });
  el.innerHTML = deler.join('');
}


function fyllVelger() {
  const el = document.getElementById('vaktliste-velger');
  if (!el) return;
  el.innerHTML = vaktlister.map((vl) => {
    // Statusen og datoen står i valget selv: velgeren er ofte det eneste
    // stedet man ser flere lister samtidig, og «Sommervakta» uten dato sier
    // ikke hvilken av dem det er.
    const merke = vl.i_drift ? ' — i drift' : '';
    const dato = vl.startet ? ` (${_dag(vl.startet)})` : '';
    return `<option value="${escHtmlValue(vl.id)}">${escapeHtml(vl.vakt_navn + dato + merke)}</option>`;
  }).join('');

  _fyll('ny-vakt-kopier',
        vaktlister.map((vl) => ({ id: vl.id, navn: vl.vakt_navn })),
        'Ikke kopier — tom liste');
}


function fyllNedtrekk() {
  if (!aktivListe) return;
  _fyll('ny-ressurs-korps', aktivListe.korps, 'Ureservert (bemannes av vaktleder)');
  _fyll('ny-ressurs-enhet', aktivListe.enheter, 'Ingen kobling');
  _fyll('ny-vaktpost-rolle', aktivListe.roller, 'Uten rolle');
  _fyll('ny-vaktpost-mannskap', aktivListe.mannskap.map((m) => ({
    id: m.id, navn: `${m.navn} — ${m.korps_navn}`,
  })), '— ledig plass —');
}


// ── Tegning ──────────────────────────────────────────────────────────────

function tegn() {
  tegnStatus();
  tegnFaner();
  tegnPanel();
}


function tegnStatus() {
  const el = document.getElementById('vaktliste-status');
  if (!el) return;
  if (!aktivListe) { el.textContent = ''; el.className = 'vl-status'; return; }
  const vl = aktivListe.vaktliste;
  // Spennet står ved siden av statusen: det er det bemanningskurven tegnes
  // over, og mangler det, skal man se hvorfor kurven er kortere enn ventet.
  const spenn = vl.planlagt_slutt
    ? ` · ${_dag(vl.startet)} ${_kl(vl.startet)} – ${_dag(vl.planlagt_slutt)} ${_kl(vl.planlagt_slutt)}`
    : ' · ingen sluttid satt';
  el.textContent = vl.status_navn + spenn;
  el.className = 'vl-status' + (vl.i_drift ? ' vl-drift' : '');
}


function _posterFor(ressursId) {
  return (aktivListe.vaktposter || []).filter((vp) => vp.ressurs_id === ressursId);
}


function tegnFaner() {
  const el = document.getElementById('vl-faner');
  if (!el) return;
  if (!aktivListe) { el.innerHTML = ''; return; }

  const faner = [{ id: OVERSIKT, navn: 'Oversikt', ikon: 'list-ul', antall: null }];
  aktivListe.ressurser.forEach((r) => {
    faner.push({
      id: String(r.id), navn: r.navn, ikon: r.ikon,
      antall: _posterFor(r.id).length,
    });
  });
  faner.push({
    id: IKKE_PLASSERT, navn: 'Ikke plassert', ikon: 'person-dash',
    antall: _ikkePlassert().length,
  });

  el.innerHTML = faner.map((f) => {
    const aktiv = f.id === aktivFane ? ' active' : '';
    const antall = f.antall === null ? ''
      : `<span class="vl-antall">${escHtmlValue(f.antall)}</span>`;
    return `<button class="vl-fane${aktiv}" data-action="visFane" data-arg="${escHtmlValue(f.id)}">`
         + `<i class="bi bi-${escHtmlValue(f.ikon)} me-1"></i>${escapeHtml(f.navn)}${antall}</button>`;
  }).join('');
}


function skrivUt() {
  // Nettleserens egen utskrift. `@media print` i vaktliste.css skjuler nav,
  // faner og knapper, så det som kommer ut er lista og ingenting annet.
  window.print();
}


function visFane(id) {
  aktivFane = id;
  tegnFaner();
  tegnPanel();
}


function _ikkePlassert() {
  // Mannskap som ikke står på noen ressurs i denne lista. Fanen finnes for
  // at ingen skal bli glemt — en person som er meldt på og ikke satt opp er
  // usynlig ellers.
  const satt = new Set((aktivListe.vaktposter || []).map((vp) => vp.mannskap_id));
  return (aktivListe.mannskap || []).filter((m) => !satt.has(m.id));
}


function tegnPanel() {
  const el = document.getElementById('vl-panel');
  if (!el) return;
  if (!aktivListe) { el.innerHTML = ''; return; }

  if (aktivFane === OVERSIKT) { el.innerHTML = mkOversikt(); return; }
  if (aktivFane === IKKE_PLASSERT) { el.innerHTML = mkIkkePlassert(); return; }

  const ressurs = aktivListe.ressurser.find((r) => String(r.id) === String(aktivFane));
  el.innerHTML = ressurs ? mkRessurs(ressurs)
    : '<div class="vl-tom">Ressursen finnes ikke lenger.</div>';
}


// ── Byggere (alt escapes — se filhodet) ──────────────────────────────────

function _iso16(iso) {
  // `datetime-local` vil ha «2026-10-03T08:00» i LOKAL tid. `toISOString()`
  // ville gitt UTC og flyttet skiftet to timer om sommeren.
  const d = _d(iso);
  if (!d) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
       + `T${p(d.getHours())}:${p(d.getMinutes())}`;
}


function _fyllValgFor(vp, kanRedigere) {
  // Å fylle plassen er én feltendring, ikke en flytting mellom to tabeller —
  // det er hele grunnen til at en ledig plass er en `Vaktpost` uten person.
  if (!kanRedigere) return '<span class="vl-ledigtekst">Ledig plass</span>';
  const valg = ['<option value="">— ledig plass —</option>'].concat(
    (aktivListe.mannskap || []).map((m) =>
      `<option value="${escHtmlValue(m.id)}">${escapeHtml(m.navn + ' — ' + m.korps_navn)}</option>`
    )).join('');
  return `<select class="vl-celle vl-fyll" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="mannskap_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function _rolleValg(vp, kanRedigere) {
  // Rollen redigeres i raden. Før lå den bare i «Sett på vakt»-modalen, og
  // å endre den krevde å fjerne skiftet og sette det opp på nytt — samme
  // person kan være sjåfør på bilen én vakt og lagleder på samleplass neste.
  if (!kanRedigere) {
    return escapeHtml(vp.rolle || '—');
  }
  const valg = ['<option value="">—</option>'].concat(
    (aktivListe.roller || []).map((r) => {
      const valgt = r.id === vp.rolle_id ? ' selected' : '';
      return `<option value="${escHtmlValue(r.id)}"${valgt}>${escapeHtml(r.navn)}</option>`;
    })).join('');
  return `<select class="vl-celle" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="rolle_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function mkRessurs(r) {
  const poster = _posterFor(r.id);
  const kanRore = kanBemanne(r);

  const korpsmerke = r.korps_navn
    ? `<span class="vl-merkelapp vl-korps">${escapeHtml(r.korps_navn)}</span>`
    : '<span class="vl-merkelapp vl-ureservert">Ureservert</span>';
  const enhetsmerke = r.enhet_navn
    ? `<span class="vl-merkelapp">Enhet: ${escapeHtml(r.enhet_navn)}</span>` : '';

  const settKnapp = kanRore
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneVaktpost" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-person-plus me-1"></i>Sett på vakt
       </button>` : '';
  const fjernKnapp = kanSkriveAlt()
    ? `<button class="btn btn-sm btn-outline-danger" type="button"
               data-action="fjernRessurs" data-id="${escHtmlValue(r.id)}">Fjern ressurs</button>`
    : '';
  const knapper = settKnapp + fjernKnapp;

  // **Regneark, ikke kort.** Radene er skift, kolonnene er det man
  // sammenligner på tvers av dem — og alt utenom navn og korps redigeres der
  // det står, uten å åpne noe.
  const kropp = poster.length ? poster
    .slice()
    .sort((a, b) => a.fra_tid.localeCompare(b.fra_tid)
                 || a.navn.localeCompare(b.navn))
    .map((vp) => {
      const komp = (vp.kompetanser || []).length
        ? vp.kompetanser.map((k) =>
            `<span class="vl-merkelapp">${escapeHtml(k)}</span>`).join('')
        : '<span class="vl-meta">—</span>';

      const tid = (felt) => kanRore
        ? `<input type="datetime-local" class="vl-celle"
                  value="${escHtmlValue(_iso16(vp[felt]))}"
                  data-action="endreVaktpost" data-hendelse="change"
                  data-felt="${escHtmlValue(felt)}" data-id="${escHtmlValue(vp.id)}">`
        : escapeHtml(_kl(vp[felt]));

      const merknad = kanRore
        ? `<input type="text" class="vl-celle" maxlength="255"
                  value="${escHtmlValue(vp.merknad || '')}" placeholder="—"
                  data-action="endreVaktpost" data-hendelse="change"
                  data-felt="merknad" data-id="${escHtmlValue(vp.id)}">`
        : escapeHtml(vp.merknad || '—');

      const fjernPost = kanRore
        ? `<button class="btn btn-sm btn-outline-danger" type="button"
                   title="Fjern skiftet" aria-label="Fjern skiftet"
                   data-action="fjernVaktpost" data-id="${escHtmlValue(vp.id)}"><i class="bi bi-trash"></i></button>`
        : '';

      // Dagen står i sin egen kolonne, ikke inne i tidene: da kan man skanne
      // nedover og se hvilke skift som er på hvilken dag.
      const dager = _sammeDag(vp.fra_tid, vp.til_tid)
        ? escapeHtml(_dag(vp.fra_tid))
        : escapeHtml(`${_dag(vp.fra_tid)} → ${_dag(vp.til_tid)}`);

      // En ledig plass er raden uten person. Den skal se ut som noe som
      // gjenstår — ikke som en rad der navnet mangler ved en feil.
      const navnCelle = vp.ledig
        ? _fyllValgFor(vp, kanRore)
        : escapeHtml(vp.navn);

      return `
        <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
          <td class="vl-navn">${navnCelle}</td>
          <td>${escapeHtml(vp.korps_kort || '—')}</td>
          <td class="vl-kompcelle">${komp}</td>
          <td>${_rolleValg(vp, kanRore)}</td>
          <td class="vl-dagcelle">${dager}</td>
          <td>${tid('fra_tid')}</td>
          <td>${tid('til_tid')}</td>
          <td>${merknad}</td>
          <td class="vl-handling">${fjernPost}</td>
        </tr>`;
    }).join('')
    : '<tr><td colspan="9" class="vl-tom">Ingen satt opp ennå.</td></tr>';

  return `
    <div class="vl-kort">
      <div class="vl-kort-topp">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="vl-kort-tittel">
            <i class="bi bi-${escHtmlValue(r.ikon)} me-1"></i>${escapeHtml(r.navn)}
          </span>
          <span class="vl-merkelapp">${escapeHtml(r.type_navn)}</span>
          ${korpsmerke}
          ${enhetsmerke}
        </div>
        <div class="d-flex gap-2">${knapper}</div>
      </div>
      <div class="vl-tabellramme">
        <table class="vl-tabell">
          <colgroup>
            <col style="width: 17%"><col style="width: 7%"><col style="width: 20%">
            <col style="width: 12%"><col style="width: 12%"><col style="width: 11%">
            <col style="width: 11%"><col style="width: 6%"><col style="width: 4%">
          </colgroup>
          <thead>
            <tr>
              <th>Navn</th><th>Korps</th><th>Kompetanse</th><th>Rolle</th>
              <th>Dag</th><th>Fra</th><th>Til</th><th>Merknad</th><th></th>
            </tr>
          </thead>
          <tbody>${kropp}</tbody>
        </table>
      </div>
    </div>`;
}


function _bemanningPerTime() {
  // **Hele vaktas lengde, ikke bare fra første til siste skift.** Leste vi
  // bare skiftene, ville hullet i begynnelsen vært usynlig nettopp fordi
  // ingen er satt opp der ennå — og det er det hullet planleggeren leter
  // etter.
  const poster = aktivListe.vaktposter || [];
  const vl = aktivListe.vaktliste || {};
  const TIME = 3600 * 1000;

  let start = vl.startet ? _d(vl.startet)?.getTime() : null;
  let slutt = vl.planlagt_slutt ? _d(vl.planlagt_slutt)?.getTime() : null;

  // Mangler spennet, faller vi tilbake på skiftene — bedre en kurve som
  // dekker for lite enn ingen kurve mens vakta ennå ikke har en slutt.
  if (start == null || slutt == null || slutt <= start) {
    if (!poster.length) return [];
    start = Math.min(...poster.map((v) => _d(v.fra_tid).getTime()));
    slutt = Math.max(...poster.map((v) => _d(v.til_tid).getTime()));
  }

  const steg = Math.ceil((slutt - start) / TIME);
  if (steg <= 0 || steg > 24 * 14) return [];   // urimelig spenn: ikke tegn

  const ut = [];
  for (let i = 0; i < steg; i += 1) {
    const t = start + i * TIME;
    const paa = poster.filter((v) =>
      _d(v.fra_tid).getTime() <= t && _d(v.til_tid).getTime() > t);
    ut.push({
      tid: new Date(t).toISOString(),
      // To tall, ikke ett: `planlagt` er alle plassene, `antall` er de som
      // faktisk har en person. Avstanden mellom dem er det som gjenstår.
      antall: paa.filter((v) => !v.ledig).length,
      planlagt: paa.length,
    });
  }
  return ut;
}


function mkKurve() {
  const punkter = _bemanningPerTime();
  if (!punkter.length) return '';
  const topp = Math.max(...punkter.map((p) => p.planlagt)) || 1;
  const ledige = punkter.reduce((n, p) => n + (p.planlagt - p.antall), 0);

  // Rene CSS-søyler framfor Chart.js: biblioteket lastes kun på
  // /statistikk/, og en bemanningskurve er ett tall per time. Den lyse delen
  // er plasser uten person — hullene man planlegger for å tette.
  const soyler = punkter.map((p) => {
    const hBemannet = Math.round((p.antall / topp) * 100);
    const hPlanlagt = Math.round((p.planlagt / topp) * 100);
    const skille = _d(p.tid).getHours() === 0 ? ' vl-dogn' : '';
    const tittel = `${_dag(p.tid)} kl. ${_kl(p.tid)}: `
                 + `${p.antall} av ${p.planlagt} plasser fylt`;
    return `<div class="vl-stolpe${skille}" title="${escHtmlValue(tittel)}">
              <div class="vl-planlagt" style="height: ${escHtmlValue(hPlanlagt)}%"></div>
              <div class="vl-bemannet" style="height: ${escHtmlValue(hBemannet)}%"></div>
            </div>`;
  }).join('');

  const bunn = `${escapeHtml(_dag(punkter[0].tid))} → `
             + `${escapeHtml(_dag(punkter[punkter.length - 1].tid))}`;
  const rest = ledige
    ? `<span class="vl-meta">${escHtmlValue(ledige)} ubesatte plasstimer</span>`
    : '<span class="vl-meta">Alle plasser fylt</span>';

  return `
    <div class="vl-kort vl-kurve-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">Bemanning gjennom vakta</span>
        <div class="d-flex align-items-center gap-3">
          <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-bemannet"></i>Bemannet</span>
          <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-planlagt"></i>Ledig plass</span>
          ${rest}
        </div>
      </div>
      <div class="vl-kurve">${soyler}</div>
      <div class="vl-meta">${bunn} · topp ${escHtmlValue(topp)} plasser</div>
    </div>`;
}


function mkOversikt() {
  // **Utskriftslista.** Hele vakta på ett ark, gruppert på korps — den man
  // henger opp. Kurven står over og følger ikke med på papiret.
  const poster = aktivListe.vaktposter || [];
  if (!poster.length) {
    return '<div class="vl-kort"><div class="vl-tom">Ingen er satt opp ennå.</div></div>';
  }

  const ressursnavn = {};
  aktivListe.ressurser.forEach((r) => { ressursnavn[r.id] = r.navn; });

  // Ledige plasser hører ikke til noe korps ennå — de samles til slutt, som
  // det som gjenstår. Uten dette ville de havnet under en gruppe uten navn.
  const LEDIG = 'Ledige plasser';
  const grupper = {};
  poster.forEach((vp) => {
    const n = vp.ledig ? LEDIG : vp.korps_navn;
    (grupper[n] = grupper[n] || []).push(vp);
  });

  const navn = Object.keys(grupper).sort((a, b) => {
    if (a === LEDIG) return 1;
    if (b === LEDIG) return -1;
    return a.localeCompare(b);
  });

  const deler = navn.map((korps) => {
    const rader = grupper[korps]
      .slice()
      .sort((a, b) => a.fra_tid.localeCompare(b.fra_tid)
                   || a.navn.localeCompare(b.navn))
      .map((vp) => `
        <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
          <td class="vl-navn">${escapeHtml(vp.ledig ? '— ledig —' : vp.navn)}</td>
          <td>${escapeHtml(ressursnavn[vp.ressurs_id] || '—')}</td>
          <td>${escapeHtml(vp.rolle || '—')}</td>
          <td>${escapeHtml(_tidsspenn(vp))}</td>
          <td>${escapeHtml(vp.merknad || '')}</td>
        </tr>`).join('');
    return `
      <div class="vl-korpsgruppe">
        <h3>${escapeHtml(korps)} (${escHtmlValue(grupper[korps].length)})</h3>
        <div class="vl-tabellramme">
        <table class="vl-tabell vl-utskrift">
          <colgroup>
            <col style="width: 24%"><col style="width: 20%"><col style="width: 16%">
            <col style="width: 26%"><col style="width: 14%">
          </colgroup>
          <thead>
            <tr><th>Navn</th><th>Ressurs</th><th>Rolle</th><th>Tid</th><th>Merknad</th></tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
        </div>
      </div>`;
  });

  const tittel = aktivListe.vaktliste.vakt_navn;
  const spenn = _vaktspenn();
  return `
    ${mkKurve()}
    <div class="vl-kort vl-utskriftsark">
      <div class="vl-arkhode">
        <h2>${escapeHtml(tittel)}</h2>
        <div class="vl-meta">${escapeHtml(spenn)} · ${escHtmlValue(poster.length)} skift</div>
      </div>
      ${deler.join('')}
    </div>`;
}


function mkIkkePlassert() {
  const folk = _ikkePlassert();
  if (!folk.length) {
    return '<div class="vl-kort"><div class="vl-tom">Alle i registeret står på lista.</div></div>';
  }
  const rader = folk.map((m) => `
    <div class="vl-rad">
      <span class="vl-navn">${escapeHtml(m.navn)}</span>
      <span class="vl-meta">${escapeHtml(m.korps_navn)}</span>
    </div>`).join('');
  return `<div class="vl-kort">
      <div class="vl-kort-topp"><span class="vl-kort-tittel">Ikke plassert</span></div>
      ${rader}
    </div>`;
}


// ── Handlinger ───────────────────────────────────────────────────────────

function _visFeil(id, melding) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


function _skjulFeil(id) {
  document.getElementById(id)?.classList.add('d-none');
}


function _lukkModal(id) {
  bootstrap.Modal.getInstance(document.getElementById(id))?.hide();
}


// datetime-local gir «2026-10-03T08:00» uten sone. Serveren gjør den aware
// i lokal sone — det er den tiden brukeren faktisk mente.
function _tidFraFelt(id) {
  const el = document.getElementById(id);
  return el && el.value ? el.value : null;
}


async function opprettVaktliste() {
  _skjulFeil('ny-vakt-feil');
  await withSubmitGuard('ny-vakt-knapp', async () => {
    const navn = (document.getElementById('ny-vakt-navn')?.value || '').trim();
    if (!navn) { _visFeil('ny-vakt-feil', 'Vakta må ha et navn.'); return; }

    const res = await apiFetch('/vaktliste/api/vaktlister/', {
      method: 'POST',
      body: JSON.stringify({
        navn,
        startet: _tidFraFelt('ny-vakt-start'),
        kopier_fra: document.getElementById('ny-vakt-kopier')?.value || null,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-vakt-feil', d.message || 'Kunne ikke opprette vaktlista.');
      return;
    }
    _lukkModal('nyVaktlisteModal');
    document.getElementById('ny-vakt-navn').value = '';
    await lastVaktlister();
    await lastListe(d.data.id);
  });
}


async function opprettRessurs() {
  if (!aktivListe) return;
  _skjulFeil('ny-ressurs-feil');
  await withSubmitGuard('ny-ressurs-knapp', async () => {
    const navn = (document.getElementById('ny-ressurs-navn')?.value || '').trim();
    if (!navn) { _visFeil('ny-ressurs-feil', 'Ressursen må ha et navn.'); return; }

    const res = await apiFetch(
      `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/ressurser/`, {
        method: 'POST',
        body: JSON.stringify({
          navn,
          type: document.getElementById('ny-ressurs-type')?.value,
          korps_id: document.getElementById('ny-ressurs-korps')?.value || null,
          enhet_id: document.getElementById('ny-ressurs-enhet')?.value || null,
        }),
      });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-ressurs-feil', d.message || 'Kunne ikke legge til ressursen.');
      return;
    }
    _lukkModal('nyRessursModal');
    document.getElementById('ny-ressurs-navn').value = '';
    aktivFane = String(d.data.id);   // åpne den nye med én gang
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function fjernRessurs(id) {
  const ressurs = aktivListe?.ressurser.find((r) => r.id === id);
  const antall = _posterFor(id).length;
  const advarsel = antall
    ? `\n\n${antall} oppsatt(e) person(er) fjernes fra lista sammen med den.` : '';
  if (!confirm(`Fjerne «${ressurs ? ressurs.navn : 'ressursen'}»?${advarsel}`)) return;

  const res = await apiFetch(`/vaktliste/api/ressurser/${id}/`, { method: 'DELETE' });
  if (!res.ok) return;
  aktivFane = OVERSIKT;
  await lastListe(aktivListe.vaktliste.id);
}


function apneVaktpost(ressursId) {
  const ressurs = aktivListe?.ressurser.find((r) => r.id === ressursId);
  if (!ressurs) return;
  _skjulFeil('ny-vaktpost-feil');
  document.getElementById('ny-vaktpost-tittel').textContent =
    `Sett på vakt — ${ressurs.navn}`;
  document.getElementById('nyVaktpostModal').dataset.ressurs = String(ressursId);
  document.getElementById('ny-vaktpost-mannskap').value = '';
  document.getElementById('ny-vaktpost-antall').value = '1';
  _vaktpostModusSkifte();
  new bootstrap.Modal(document.getElementById('nyVaktpostModal')).show();
}


function _vaktpostModusSkifte() {
  // Antall plasser gir bare mening for ledige: to identiske rader med samme
  // person ville uansett brutt unik-skranken.
  const valgt = document.getElementById('ny-vaktpost-mannskap')?.value;
  document.getElementById('ny-vaktpost-antall-rad')
    ?.classList.toggle('d-none', !!valgt);
}


function apneVaktlengde() {
  if (!aktivListe) return;
  _skjulFeil('vakt-lengde-feil');
  const vl = aktivListe.vaktliste;
  _settTid('vakt-start', vl.startet);
  _settTid('vakt-slutt', vl.planlagt_slutt);
  new bootstrap.Modal(document.getElementById('vaktlengdeModal')).show();
}


function _settTid(id, iso) {
  const el = document.getElementById(id);
  if (el) el.value = iso ? _iso16(iso) : '';
}


async function lagreVaktlengde() {
  _skjulFeil('vakt-lengde-feil');
  await withSubmitGuard('vakt-lengde-knapp', async () => {
    const res = await apiFetch(`/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        startet: _tidFraFelt('vakt-start'),
        planlagt_slutt: _tidFraFelt('vakt-slutt'),
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('vakt-lengde-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    _lukkModal('vaktlengdeModal');
    await lastVaktlister();
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function opprettVaktpost() {
  const modal = document.getElementById('nyVaktpostModal');
  const ressursId = modal?.dataset.ressurs;
  if (!ressursId) return;

  _skjulFeil('ny-vaktpost-feil');
  await withSubmitGuard('ny-vaktpost-knapp', async () => {
    const fra = _tidFraFelt('ny-vaktpost-fra');
    const til = _tidFraFelt('ny-vaktpost-til');
    if (!fra || !til) {
      _visFeil('ny-vaktpost-feil', 'Skiftet må ha både fra- og til-tidspunkt.');
      return;
    }

    const res = await apiFetch(`/vaktliste/api/ressurser/${ressursId}/vaktposter/`, {
      method: 'POST',
      body: JSON.stringify({
        mannskap_id: document.getElementById('ny-vaktpost-mannskap')?.value || null,
        rolle_id: document.getElementById('ny-vaktpost-rolle')?.value || null,
        antall: Number(document.getElementById('ny-vaktpost-antall')?.value) || 1,
        fra_tid: fra,
        til_tid: til,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-vaktpost-feil', d.message || 'Kunne ikke sette personen på vakt.');
      return;
    }
    _lukkModal('nyVaktpostModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function endreVaktpost(id, felt, verdi) {
  // Redigering i raden: skriv, gå videre, ferdig. Serveren avviser fortsatt
  // et skift som slutter før det begynner — da rulles raden tilbake til det
  // som faktisk står lagret, og meldingen vises over tabellen.
  const kropp = {};
  kropp[felt] = verdi === '' ? null : verdi;

  const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, {
    method: 'PUT', body: JSON.stringify(kropp),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke lagre endringen.');
    await lastListe(aktivListe.vaktliste.id);   // rull tilbake til lagret verdi
    return;
  }
  skjulPanelfeil();
  await lastListe(aktivListe.vaktliste.id);
}


function visPanelfeil(melding) {
  const el = document.getElementById('vl-feil');
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


function skjulPanelfeil() {
  document.getElementById('vl-feil')?.classList.add('d-none');
}


function _koblCellelytter() {
  // `data-action`-delegeringen i portal-utils.js er klikkbasert. Cellene i
  // ressurstabellen er nedtrekk og tekstfelt, og de melder `change`.
  document.getElementById('vl-panel')?.addEventListener('change', (e) => {
    const el = e.target.closest('[data-hendelse="change"]');
    if (!el) return;
    endreVaktpost(Number(el.dataset.id), el.dataset.felt, el.value);
  });
}


async function fjernVaktpost(id) {
  const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, { method: 'DELETE' });
  if (!res.ok) return;
  await lastListe(aktivListe.vaktliste.id);
}


document.addEventListener('DOMContentLoaded', () => {
  gateKnapper();
  _koblCellelytter();
  document.getElementById('ny-vaktpost-mannskap')
    ?.addEventListener('change', _vaktpostModusSkifte);
  lastVaktlister();
});
