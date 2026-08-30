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
// **Én fane per ressursgruppe**, ikke per ressurs (30. aug. 2026). Fanen
// «Ambulanse» er oversikten over alle ambulansene som skal på vakt, med hver
// bil som sitt eget kort inni. Én fane per bil ga ti faner på en vakt med ti
// biler, og ingen plass der man kunne se dem i sammenheng — som er nettopp
// det man planlegger etter. Gruppekurven ligger øverst i fanen, over de
// ressursene den summerer.
//
// Faste faner i tillegg: «Oversikt», som er den man skriver ut, «Mannskap»,
// som er personellregisteret, og «Ikke plassert», som er de som er meldt på
// uten å stå noe sted ennå.
//
// **Mannskapsregisteret er en fane her, ikke en egen side** (30. aug. 2026).
// Det lå på /vaktliste/registre/, og et klikk dit kostet deg plassen i
// planleggingen — mens mannskap og ressurser er nettopp de to man veksler
// mellom. Korps og kompetanser fulgte med inn, men til «Innstillinger»: de
// røres sjelden, og de er portalens oppsett, ikke denne vaktas.
//
// **Mannskapsfanen står også når det ikke finnes noen vaktliste.** Korps må
// legges inn før mannskap, og mannskap før noen kan settes på vakt — lå
// registeret bare bak en vaktliste, var portalen låst på første skritt.
// ════════════════════════════════════════════════════════

let vaktlister = [];        // alle listene, til velgeren
let aktivListe = null;      // { vaktliste, ressurser, vaktposter, korps, roller, mannskap, enheter }
let aktivFane = 'oversikt'; // 'oversikt' | 'ikke-plassert' | gruppe-id som streng

//: Personellregisteret: { mannskap, korps, kompetanser, roller, kontoer }.
//: Hentes for seg fordi det er globalt — `aktivListe.mannskap` er den slanke
//: lista fanene bemanner fra, uten telefon, konto og notat.
let register = null;
let personsok = '';              // fritekstfilter på mannskapstabellen
let personSortKol = 'korps';     // 'navn' | 'korps' | 'telefon'
let personSortStigende = true;
let redigererPerson = null;      // id-en som redigeres, eller null for «ny»
let redigererVerdi = null;
let aktivVerdiregister = 'korps';  // hvilket register verdivinduet står i

const OVERSIKT = 'oversikt';
const MANNSKAP = 'mannskap';
const TILSTEDE = 'tilstede';
const IKKE_PLASSERT = 'ikke-plassert';

// Register → hvordan det snakkes om og hvor det ligger.
// `nyEtikett` er hele knappeteksten, ikke bare ordet: «korps» er intetkjønn
// og «kompetanse» hankjønn, så en hardkodet «Ny » foran gir feil artikkel på
// en av dem uansett hvilken man velger.
const REGISTRE = {
  korps: { sti: 'korps', nyEtikett: 'Nytt korps', tittel: 'Korps',
           kortnavn: true },
  kompetanser: { sti: 'kompetanser', nyEtikett: 'Ny kompetanse',
                 tittel: 'Kompetanser', stige: true },
};


// ── Tilgang (fase 3) ─────────────────────────────────────────────────────
//
// Speiler services.py. Serveren håndhever uansett — dette avgjør bare hvilke
// knapper som tegnes, fordi en knapp som fører til en vegg er verre enn ingen
// knapp. Reglene står to steder med vilje, og de to stedene testes hver for
// seg: JS-en her i node, serveren i vaktliste/tests_tilgang.py.

function _nivaa() {
  return ((window.MODUL_TILGANG || {}).vaktliste || '').toLowerCase();
}


function _erAdmin() {
  return (window.MODUL_TILGANG || {}).admin === true;
}


function kanSkriveAlt() {
  // `skriv_leder` er trinnet over og inneholder dette — stigen er ordnet,
  // og speilingen av `services.kan_skrive_alt` må være det også. Glemmes det,
  // mister lederen knappene bemanneren har.
  return _erAdmin() || _nivaa() === 'skriv_full' || _nivaa() === 'skriv_leder';
}


function kanLede() {
  // Den som *setter opp* vakta: oppretter og fjerner ressurser og
  // vaktlister, endrer vaktas lengde, lager roller og grupper. Speiler
  // `services.kan_lede`.
  return _erAdmin() || _nivaa() === 'skriv_leder';
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


function kanStemple() {
  // Speiler `services.kan_stemple`. **Avklaring 11.3: ikke korps-føreren.**
  // Hun setter opp sine egne folk, men «Tilstede nå» er brannsikkerhet, og
  // det tallet skal ha én ansvarlig — ikke ett per korps.
  return kanSkriveAlt();
}


function iDrift() {
  return !!aktivListe?.vaktliste?.i_drift;
}


function gateKnapper() {
  document.querySelectorAll('.vl-krev-full')
    .forEach((el) => el.classList.toggle('d-none', !kanSkriveAlt()));
  document.querySelectorAll('.vl-krev-leder')
    .forEach((el) => el.classList.toggle('d-none', !kanLede()));
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
    // **Uten vaktliste er registeret det eneste man kan gjøre noe med** — og
    // det er også det man må gjøre først: korps før mannskap, mannskap før
    // noen kan settes på vakt. Sto fanen der uklikket, viste sida ingenting.
    aktivListe = null;
    aktivFane = MANNSKAP;
    tegn();
    lastRegister();
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


async function lastRegister() {
  // Registeret er globalt, ikke vaktas. Det hentes for seg, og lastes på
  // nytt etter hver endring — navn og korps står i nedtrekkene på
  // planleggingssiden, så `lastListe()` må med når personer endres.
  const res = await apiFetch('/vaktliste/api/mannskap/');
  if (!res.ok) return;
  register = (await res.json()).data;
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
  // Gruppene kommer fra basen nå, ikke fra malen: en ny gruppe skal virke
  // uten en ny sidelasting, og uten en deploy.
  // «Ny ressurs»-nedtrekket fylles i `apneNyRessurs()`, ikke her: hvilke
  // grupper som har plass endrer seg hver gang en ressurs opprettes.
  _fyll('ny-vaktpost-mannskap', aktivListe.mannskap.map((m) => ({
    id: m.id, navn: `${m.navn} — ${m.korps_navn}`,
  })), '— ledig plass —');
  _fyll('ny-vaktpost-korps', (aktivListe.korps || []).map((k) => ({
    id: k.id, navn: k.kortnavn || k.navn,
  })), '— som ressursen —');

  // Rollenedtrekket i «Sett på vakt» fylles når vinduet åpnes: det som
  // tilbys avhenger av hvilken ressurs man står på, altså av gruppa.
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

  tegnDriftknapp();
}


function tegnDriftknapp() {
  // **Døra til innsjekken står ved statusen den endrer.** Lå den i
  // «Innstillinger», måtte man åpne et vindu for å se om innsjekken var
  // åpen — og det er det første man vil vite når vakta begynner.
  //
  // Knappen tegnes her og ikke av `gateKnapper()`, fordi teksten skifter med
  // tilstanden: `gateKnapper()` kjører én gang ved sidelasting.
  const el = document.getElementById('vl-drift');
  if (!el) return;
  if (!aktivListe || !kanSkriveAlt()) { el.innerHTML = ''; return; }

  el.innerHTML = iDrift()
    ? `<button class="btn btn-sm btn-outline-warning" type="button"
               data-action="settDrift" data-arg="stopp">
         <i class="bi bi-pause-circle me-1"></i>Ut av drift
       </button>`
    : `<button class="btn btn-sm btn-success" type="button"
               data-action="settDrift" data-arg="start">
         <i class="bi bi-play-circle me-1"></i>Sett i drift
       </button>`;
}


function _posterFor(ressursId) {
  return (aktivListe.vaktposter || []).filter((vp) => vp.ressurs_id === ressursId);
}


function _ressurserIGruppe(gruppeId) {
  // Rekkefølgen er den serveren sender — `Ressurs.rekkefolge`, satt til
  // opprettelsesrekkefølgen. Den som bygger vakta legger inn bilene i den
  // rekkefølgen hun tenker på dem.
  return (aktivListe.ressurser || []).filter((r) => r.gruppe_id === gruppeId);
}


function _grupperMedRessurser() {
  // Bare grupper som faktisk har noe i seg blir faner. En tom fane per
  // ubrukt gruppe er seks faner på en vakt med to ressurser.
  return (aktivListe.grupper || [])
    .filter((g) => _ressurserIGruppe(g.id).length);
}


function gruppaHarPlass(g) {
  // **Noen grupper finnes i ett eksemplar.** Samleplassen og KO er
  // samlingspunkt for flere korps, ikke flåter — «Ny samleplass» inviterer
  // til å lage noe som ikke finnes. Den *første* må man fortsatt kunne
  // opprette, så plassen tar slutt først når den ene står der.
  //
  // Regelen står som én funksjon fordi den har to lesere: knappen inne i
  // fanen og nedtrekket i «Ny ressurs». Skjulte vi bare knappen, kunne man
  // fortsatt velge gruppa i nedtrekket — og da var regelen halvveis, som er
  // verre enn ingen regel.
  if (!g) return false;
  return g.flere_enheter !== false || !_ressurserIGruppe(g.id).length;
}


function visFane(id) {
  aktivFane = id;
  // Registeret hentes først når noen faktisk ber om det. Det er globalt og
  // uavhengig av vaktlista, så det koster ingenting å utsette.
  if (id === MANNSKAP && !register) { lastRegister(); }
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


function skrivUt() {
  // Nettleserens egen utskrift. `@media print` i vaktliste.css skjuler nav,
  // faner og knapper, så det som kommer ut er lista og ingenting annet.
  window.print();
}


function _mannskapsfane() {
  // Antallet er registeret, ikke vaktas påmeldte: fanen *er* registeret.
  return {
    id: MANNSKAP, navn: 'Mannskap', ikon: 'person-vcard',
    antall: register ? register.mannskap.length : null,
  };
}


function tegnFaner() {
  const el = document.getElementById('vl-faner');
  if (!el) return;

  // **Uten vaktliste står Mannskap alene.** Korps må inn før mannskap, og
  // mannskap før noen kan settes på vakt. Var fanen borte til den første
  // vaktlista fantes, sto man fast på skritt én.
  if (!aktivListe) {
    el.innerHTML = _fanerad([_mannskapsfane()], '');
    return;
  }

  const faner = [{ id: OVERSIKT, navn: 'Oversikt', ikon: 'list-ul', antall: null }];
  // **Én fane per gruppe.** «Ambulanse» er alle ambulansene, ikke én av dem.
  _grupperMedRessurser().forEach((g) => {
    const ressurser = _ressurserIGruppe(g.id);
    faner.push({
      id: String(g.id), navn: g.navn, ikon: g.ikon,
      antall: ressurser.reduce((n, r) => n + _posterFor(r.id).length, 0),
    });
  });
  // **«Tilstede nå» finnes bare i drift.** I planlegging er den tom per
  // definisjon — ingen er stemplet — og en fane som alltid sier null er en
  // fane man slutter å se.
  if (iDrift()) {
    faner.push({
      id: TILSTEDE, navn: 'Tilstede nå', ikon: 'person-check',
      antall: _tilstede().length,
    });
  }

  faner.push({
    id: IKKE_PLASSERT, navn: 'Ikke plassert', ikon: 'person-dash',
    antall: _ikkePlassert().length,
  });

  // **Mannskap er en ekte fane, ikke en lenke.** Den var en lenke ut til
  // /vaktliste/registre/, og et klikk kostet deg plassen i planleggingen —
  // mens mannskap og ressurser er nettopp de to man veksler mellom.
  faner.splice(1, 0, _mannskapsfane());

  // «Ny ressurs» sist. Bygges her og ikke i malen fordi den skal stå etter
  // faner som kommer fra data; `gateKnapper()` rekker ikke over markup som
  // tegnes på nytt ved hvert panelbytte, så tilgangen sjekkes her.
  const nyRessurs = kanLede()
    ? `<button class="vl-fane vl-fane-ny" type="button"
               data-action="apneNyRessurs">
         <i class="bi bi-plus-lg me-1"></i>Ny ressurs
       </button>`
    : '';

  el.innerHTML = _fanerad(faner, nyRessurs);
}


function _fanerad(faner, hale) {
  return faner.map((f) => {
    const aktiv = f.id === aktivFane ? ' active' : '';
    const antall = f.antall === null ? ''
      : `<span class="vl-antall">${escHtmlValue(f.antall)}</span>`;
    return `<button class="vl-fane${aktiv}" data-action="visFane" data-arg="${escHtmlValue(f.id)}">`
         + `<i class="bi bi-${escHtmlValue(f.ikon)} me-1"></i>${escapeHtml(f.navn)}${antall}</button>`;
  }).join('') + hale;
}


function tegnPanel() {
  const el = document.getElementById('vl-panel');
  if (!el) return;

  // Søkefeltet hører til mannskapsfanen og ligger UTENFOR panelet med vilje:
  // panelet tegnes på nytt ved hvert tastetrykk, og et input inni ville mistet
  // fokus etter første bokstav.
  document.getElementById('vl-verktoy')
    ?.classList.toggle('d-none', aktivFane !== MANNSKAP);

  // **Mannskapsfanen står også uten vaktliste** — se `tegnFaner()`.
  if (aktivFane === MANNSKAP) { el.innerHTML = mkMannskap(); return; }
  if (!aktivListe) { el.innerHTML = ''; return; }

  if (aktivFane === OVERSIKT) { el.innerHTML = mkOversikt(); return; }
  if (aktivFane === TILSTEDE) { el.innerHTML = mkTilstede(); return; }
  if (aktivFane === IKKE_PLASSERT) { el.innerHTML = mkIkkePlassert(); return; }

  const gruppe = (aktivListe.grupper || [])
    .find((g) => String(g.id) === String(aktivFane));
  el.innerHTML = gruppe ? mkGruppe(gruppe)
    : '<div class="vl-tom">Gruppa finnes ikke lenger.</div>';
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


function rollerForGruppe(gruppeId, valgtId) {
  // **Rollen hører til ressursgruppa** (30. aug. 2026). «Sjåfør» gir mening
  // på hver ambulanse og ikke på samleplassen, og et globalt register ville
  // tvunget hver rolle inn i hvert nedtrekk.
  //
  // Tre ledd, og hvert av dem er en egen feil å gjøre:
  //   · gruppa       — ellers tilbys samleplassens roller på bilen
  //   · `er_aktiv`   — en pensjonert rolle skal ikke kunne velges på nytt
  //   · den valgte   — uten den forsvinner en deaktivert rolle fra sin egen
  //                    rad ved neste tegning, og velges bort i stillhet
  return (aktivListe.roller || []).filter((r) =>
    r.id === valgtId || (r.gruppe_id === gruppeId && r.er_aktiv));
}


function _plassKorps(vp) {
  // Reservasjonen på en ledig plass. Bare den som deler ut kan endre den —
  // kunne korps-brukeren, kunne hun tildelt seg selv en plass. Andre ser
  // hvem plassen tilhører, som tekst.
  const valgt = vp.plass_korps_id != null ? vp.plass_korps_id
    : (vp.reservert_korps_id != null ? vp.reservert_korps_id : '');
  if (!kanSkriveAlt()) {
    const k = (aktivListe.korps || []).find((x) => x.id === valgt);
    return `<span class="vl-meta">${escapeHtml(k ? (k.kortnavn || k.navn) : '—')}</span>`;
  }
  const valg = ['<option value="">— alle —</option>'].concat(
    (aktivListe.korps || []).map((k) => {
      const merke = k.id === valgt ? ' selected' : '';
      return `<option value="${escHtmlValue(k.id)}"${merke}>`
           + `${escapeHtml(k.kortnavn || k.navn)}</option>`;
    })).join('');
  return `<select class="vl-celle" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="korps_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function _rolleValg(vp, ressurs, kanRedigere) {
  // Rollen redigeres i raden. Før lå den bare i «Sett på vakt»-modalen, og
  // å endre den krevde å fjerne skiftet og sette det opp på nytt — samme
  // person kan være sjåfør på bilen én vakt og lagleder på samleplass neste.
  if (!kanRedigere) {
    return escapeHtml(vp.rolle || '—');
  }
  const valg = ['<option value="">—</option>'].concat(
    rollerForGruppe(ressurs.gruppe_id, vp.rolle_id).map((r) => {
      const valgt = r.id === vp.rolle_id ? ' selected' : '';
      return `<option value="${escHtmlValue(r.id)}"${valgt}>${escapeHtml(r.navn)}</option>`;
    })).join('');
  return `<select class="vl-celle" data-action="endreVaktpost" data-hendelse="change"
                  data-felt="rolle_id" data-id="${escHtmlValue(vp.id)}">${valg}</select>`;
}


function mkGruppe(gruppe) {
  // **Fanen er oversikten over gruppa.** Kurven øverst summerer akkurat de
  // ressursene som står under den — det er hele grunnen til at fanen er
  // gruppa og ikke den enkelte bilen.
  const ressurser = _ressurserIGruppe(gruppe.id);

  // **Knappen for å legge til én til står HER, i gruppa.** Den lå bare sist i
  // fanerekka, og da var det usynlig at fanen «Ambulanse» rommer bil A, bil B
  // og bil C — man så én rad med knapper og trodde gruppa *var* bilen. Det
  // kostet André en time og meg tre runder.
  const leggTil = kanLede() && gruppaHarPlass(gruppe)
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneNyRessurs" data-arg="${escHtmlValue(gruppe.id)}">
         <i class="bi bi-plus-lg me-1"></i>Ny ${escapeHtml(gruppe.navn)}
       </button>`
    : '';

  if (!ressurser.length) {
    return `
      <div class="vl-kort">
        <div class="vl-kort-topp">
          <span class="vl-kort-tittel">
            <i class="bi bi-${escHtmlValue(gruppe.ikon)} me-1"></i>${escapeHtml(gruppe.navn)}
          </span>
          ${leggTil}
        </div>
        <div class="vl-tom">
          Ingen ${escapeHtml(gruppe.navn)} satt opp ennå. Hver enhet er sin egen
          rad her — én per bil, lag eller post — med egne skift og egen kobling
          mot oppdragsmodulen.
        </div>
      </div>`;
  }

  const hode = `
    <div class="vl-kort vl-gruppehode">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">
          <i class="bi bi-${escHtmlValue(gruppe.ikon)} me-1"></i>${escapeHtml(gruppe.navn)}
          <span class="vl-meta">${escHtmlValue(ressurser.length)} ${
            ressurser.length === 1 ? 'enhet' : 'enheter'} ·
            ${escHtmlValue(_posterIGruppe(gruppe.id).length)} skift</span>
        </span>
        ${leggTil}
      </div>
    </div>`;

  return hode + mkGruppekurve(gruppe) + ressurser.map(mkRessurs).join('');
}


function _radklasse(vp) {
  // Tilstanden skal synes på raden, ikke bare i en kolonne. Under drift er
  // det «hvem mangler» man leter etter, og da er det fargen man skummer.
  if (vp.ledig) return 'vl-ledig';
  if (!iDrift()) return '';
  if (vp.tilstede) return 'vl-tilstede';
  if (vp.av_vakt_at) return 'vl-avgatt';
  return '';
}


function _stempelknapper(vp) {
  // **Én knapp, ikke to.** Se kommentaren i `mkRessurs()`. Rekkefølgen er
  // radens egen: har hun ikke møtt, er «Møtt» det eneste som gir mening.
  if (!iDrift() || vp.ledig || !kanStemple()) return '';

  // **Én `data-action` per overgang**, ikke én generisk med overgangen i et
  // attributt. Klikkdelegeringen i portal-utils.js sender ett argument —
  // `data-id` — og å utvide den for én sides skyld ville rørt hver side i
  // portalen. Navnene speiler `services.STEMPLINGER`, og
  // `StemplingsnavnTests` holder de to listene like.
  const knapp = (handling, etikett, stil, ikon) =>
    `<button class="btn btn-sm ${stil} vl-stempel" type="button"
             data-action="${escHtmlValue(handling)}" data-id="${escHtmlValue(vp.id)}">
       <i class="bi bi-${escHtmlValue(ikon)} me-1"></i>${escapeHtml(etikett)}
     </button>`;
  const angre = (handling, tittel) =>
    `<button class="btn btn-sm btn-outline-secondary" type="button"
             title="${escHtmlValue(tittel)}" aria-label="${escHtmlValue(tittel)}"
             data-action="${escHtmlValue(handling)}" data-id="${escHtmlValue(vp.id)}">
       <i class="bi bi-arrow-counterclockwise"></i>
     </button>`;

  if (!vp.mott_at) return knapp('stemplMott', 'Møtt', 'btn-success', 'box-arrow-in-right');
  if (!vp.av_vakt_at) {
    return knapp('stemplAvVakt', 'Av vakt', 'btn-outline-warning', 'box-arrow-right')
         + angre('angreMott', 'Angre møtt');
  }
  return `<span class="vl-meta me-1">${escapeHtml(_kl(vp.av_vakt_at))}</span>`
       + angre('angreAvVakt', 'Angre av vakt');
}


function _varighet(vp) {
  // **Timer per skift, som en egen kolonne.** Andrés bestilling, og den er
  // det eneste tallet man ellers må regne ut i hodet for hver rad — «20:00
  // til 04:30» er ikke åtte timer, og kolonnen er det man summerer når man
  // vurderer om noen står for lenge.
  const fra = _d(vp.fra_tid);
  const til = _d(vp.til_tid);
  if (!fra || !til) return '—';
  const timer = (til.getTime() - fra.getTime()) / 3600000;
  if (!(timer > 0)) return '—';
  // Halvtimer forekommer; en desimal holder og «8» skal ikke bli «8,0».
  const vist = Number.isInteger(timer) ? String(timer)
    : timer.toFixed(1).replace('.', ',');
  return `${vist} t`;
}


function mkRessurs(r) {
  const poster = _posterFor(r.id);
  const kanRore = kanBemanne(r);

  const korpsmerke = r.korps_navn
    ? `<span class="vl-merkelapp vl-korps">${escapeHtml(r.korps_navn)}</span>`
    : '<span class="vl-merkelapp vl-ureservert">Ureservert</span>';
  // **Koblingen vises også når den mangler.** Merkelappen sto bare der bilen
  // *var* koblet, så den som ikke hadde koblet noe så ingenting — og kunne
  // ikke vite at koblingen finnes per bil i det hele tatt. Nå står den som en
  // tom plass som ber om å fylles, for den som har lov til å fylle den.
  const enhetsmerke = r.enhet_navn
    ? `<span class="vl-merkelapp vl-enhet">
         <i class="bi bi-broadcast me-1"></i>${escapeHtml(r.enhet_navn)}
       </span>`
    : (kanLede()
        ? `<button class="vl-merkelapp vl-enhet-tom" type="button"
                   title="Koble denne enheten til oppdragsmodulen"
                   data-action="apneRessurs" data-id="${escHtmlValue(r.id)}">
             <i class="bi bi-broadcast me-1"></i>Ikke koblet
           </button>`
        : '');

  const settKnapp = kanRore
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneVaktpost" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-plus-lg me-1"></i>Opprett vakt
       </button>` : '';

  // **Rollene administreres inne i ressursen**, ikke i toppen av siden.
  // Trenger man «Sjåfør» mens man bemanner ambulansen, skal den lages der —
  // og den blir gruppas, så den finnes på hver ambulanse med én gang.
  const rolleKnapp = kanLede()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneRoller" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-person-badge me-1"></i>Roller
       </button>` : '';

  // **Sletting ligger bak «Rediger», ikke i toppen.** En naken «Fjern
  // ressurs» ved siden av «Sett på vakt» gjør det for lett å rive bort hele
  // bilen med bemanningen på — CASCADE tar skiftene.
  const redigerKnapp = kanLede()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneRessurs" data-id="${escHtmlValue(r.id)}">
         <i class="bi bi-pencil me-1"></i>Rediger
       </button>` : '';
  const knapper = settKnapp + rolleKnapp + redigerKnapp;

  // **Regneark, ikke kort.** Radene er skift, kolonnene er det man
  // sammenligner på tvers av dem — og alt utenom navn og korps redigeres der
  // det står, uten å åpne noe.
  const kropp = poster.length ? poster
    .slice()
    .sort(_skiftrekkefolge)
    .map((vp) => {
      // Merkelappene ligger i en wrapper, ikke rett i cella: `display: flex`
      // på en `<td>` tar cella ut av tabellens boksmodell, og da forskyves
      // kolonnene etter den i forhold til overskriftene.
      const merkelapper = (vp.kompetanser || []).map((k) =>
        `<span class="vl-merkelapp">${escapeHtml(k)}</span>`).join('');
      const komp = merkelapper
        ? `<div class="vl-merkelapper">${merkelapper}</div>`
        : '<span class="vl-meta">—</span>';

      // **Dagen står i tidsfeltet, ikke i en egen kolonne.** Kolonnen var
      // et tredje sted å lese for å forstå én rad, og `datetime-local` bærer
      // datoen selv — den manglet bare ukedagen, som er den man planlegger
      // etter. Nå står «lør.» under feltet den hører til.
      const tid = (felt) => {
        const merke = _d(vp[felt])
          ? `<span class="vl-dagmerke">${escapeHtml(_dag(vp[felt]))}</span>` : '';
        const innhold = kanRore
          ? `<input type="datetime-local" step="300" class="vl-celle"
                    value="${escHtmlValue(_iso16(vp[felt]))}"
                    data-action="endreVaktpost" data-hendelse="change"
                    data-felt="${escHtmlValue(felt)}" data-id="${escHtmlValue(vp.id)}">`
          : escapeHtml(_kl(vp[felt]));
        return `<div class="vl-tidcelle">${innhold}${merke}</div>`;
      };

      const merknad = kanRore
        ? `<input type="text" class="vl-celle" maxlength="255"
                  value="${escHtmlValue(vp.merknad || '')}" placeholder="—"
                  data-action="endreVaktpost" data-hendelse="change"
                  data-felt="merknad" data-id="${escHtmlValue(vp.id)}">`
        : escapeHtml(vp.merknad || '—');

      // **Rediger, ikke slett.** Å bytte person på et skift var før å fjerne
      // raden og sette den opp på nytt — og da mistet man tidene og rollen
      // som allerede sto der. Sletting ligger nå inne i vinduet, bak en
      // bekreftelse, slik den gjør på ressursen.
      const redigerPost = kanRore
        ? `<button class="btn btn-sm btn-outline-secondary" type="button"
                   title="Rediger skiftet" aria-label="Rediger skiftet"
                   data-action="apneRedigerVaktpost" data-id="${escHtmlValue(vp.id)}"><i class="bi bi-pencil"></i></button>`
        : '';

      // **Stemplene står i handlingskolonnen, som er `sticky`.** Den er den
      // ene kolonnen som aldri ruller bort, og KO står med en telefon i
      // hånda og skal treffe riktig rad første gang.
      //
      // Notatet ba om «to store knapper per rad». Det ble **én** — den som
      // gjelder nå — pluss en liten angre. Raden er i nøyaktig én tilstand:
      // «Møtt» på en som alt har møtt gjør enten ingenting eller noe hun
      // ikke ba om, og to knapper i en kolonne på 5 % blir to *små* knapper,
      // altså det motsatte av bestillingen. Angreknappen er liten med vilje:
      // et feiltrykk skal kunne rettes, men ikke like lett som å stemple.
      const stempler = _stempelknapper(vp);

      // En ledig plass er raden uten person. Den skal se ut som noe som
      // gjenstår — ikke som en rad der navnet mangler ved en feil.
      const navnCelle = vp.ledig
        ? _fyllValgFor(vp, kanRore)
        : escapeHtml(vp.navn);

      // **Korpskolonnen svarer på to ulike spørsmål.** Står det en person
      // der, er det *hennes* korps — et faktum. Er plassen ledig, er det
      // korpset plassen er *satt av til* — en beslutning, og den kan endres
      // av den som deler ut. En samleplass har gjerne to plasser til
      // Haugesund og to til Karmøy.
      const korpsCelle = vp.ledig
        ? _plassKorps(vp)
        : escapeHtml(vp.korps_kort || '—');

      // Rekkefølgen er lesestrekket: hvem, hvorfra, hvilken rolle, når, hvor
      // lenge — og først da kompetansen, som er det man vurderer laget på
      // når resten står. Merknaden sist, fordi den er unntaket.
      return `
        <tr class="${escHtmlValue(_radklasse(vp))}">
          <td class="vl-navn">${navnCelle}</td>
          <td>${korpsCelle}</td>
          <td>${_rolleValg(vp, r, kanRore)}</td>
          <td>${tid('fra_tid')}</td>
          <td>${tid('til_tid')}</td>
          <td class="vl-timer">${escapeHtml(_varighet(vp))}</td>
          <td class="vl-kompcelle">${komp}</td>
          <td>${merknad}</td>
          <td class="vl-handling">${stempler}${redigerPost}</td>
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
          <span class="vl-merkelapp">${escapeHtml(r.gruppe_navn)}</span>
          ${korpsmerke}
          ${enhetsmerke}
        </div>
        <div class="d-flex gap-2">${knapper}</div>
      </div>
      <div class="vl-tabellramme">
        <table class="vl-tabell">
          <colgroup>
            <col style="width: 14%"><col style="width: 10%"><col style="width: 10%">
            <col style="width: 18%"><col style="width: 18%"><col style="width: 5%">
            <col style="width: 10%"><col style="width: 10%"><col style="width: 5%">
          </colgroup>
          <thead>
            <tr>
              <th>Navn</th><th>Korps</th><th>Rolle</th>
              <th>Fra</th><th>Til</th><th>Timer</th>
              <th>Kompetanse</th><th>Merknad</th><th></th>
            </tr>
          </thead>
          <tbody>${kropp}</tbody>
        </table>
      </div>
    </div>`;
}


function _vaktensSpenn() {
  // Spennet kurvene tegnes over. Ett sted, fordi alle gruppenes kurver må
  // dekke *samme* timer — ellers ligger ikke søylene under hverandre, og to
  // kurver man ikke kan sammenligne er verre enn én samlet.
  const poster = aktivListe.vaktposter || [];
  const vl = aktivListe.vaktliste || {};
  const TIME = 3600 * 1000;

  let start = vl.startet ? _d(vl.startet)?.getTime() : null;
  let slutt = vl.planlagt_slutt ? _d(vl.planlagt_slutt)?.getTime() : null;

  // Mangler spennet, faller vi tilbake på skiftene — bedre en kurve som
  // dekker for lite enn ingen kurve mens vakta ennå ikke har en slutt.
  if (start == null || slutt == null || slutt <= start) {
    if (!poster.length) return null;
    start = Math.min(...poster.map((v) => _d(v.fra_tid).getTime()));
    slutt = Math.max(...poster.map((v) => _d(v.til_tid).getTime()));
  }

  const steg = Math.ceil((slutt - start) / TIME);
  if (steg <= 0 || steg > 24 * 14) return null;   // urimelig spenn: ikke tegn
  return { start, steg };
}


function _bemanningPerTime(poster) {
  // **Hele vaktas lengde, ikke bare fra første til siste skift.** Leste vi
  // bare skiftene, ville hullet i begynnelsen vært usynlig nettopp fordi
  // ingen er satt opp der ennå — og det er det hullet planleggeren leter
  // etter.
  const spenn = _vaktensSpenn();
  if (!spenn) return [];
  const rader = poster || aktivListe.vaktposter || [];
  const TIME = 3600 * 1000;

  const ut = [];
  for (let i = 0; i < spenn.steg; i += 1) {
    const t = spenn.start + i * TIME;
    const paa = rader.filter((v) =>
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


function _posterPerGruppe() {
  // **Kurven følger grupperingen** (Andrés bestilling, 30. aug. 2026). En
  // samlet kurve summerte samleplassen, ambulansene og KO til ett tall, og
  // det tallet svarer ikke på noe: fire på samleplassen og null på
  // ambulansen ser likt ut som to og to. Gruppene beholder rekkefølgen
  // serveren sender — den styrer også fanene.
  const gruppePerRessurs = {};
  (aktivListe.ressurser || []).forEach((r) => {
    gruppePerRessurs[r.id] = r.gruppe_id;
  });

  const per = new Map();
  (aktivListe.grupper || []).forEach((g) => per.set(g.id, { gruppe: g, poster: [] }));
  (aktivListe.vaktposter || []).forEach((vp) => {
    const bunke = per.get(gruppePerRessurs[vp.ressurs_id]);
    if (bunke) bunke.poster.push(vp);
  });

  // Grupper uten et eneste skift tegnes ikke — en tom kurve per ubrukt
  // gruppe er seks tomme kurver på en vakt med to ressurser.
  return [...per.values()].filter((b) => b.poster.length);
}


function _timesteg(antall) {
  // Hvor ofte klokkeslettet skrives under søylene. Alle timer på en kort
  // vakt, sjeldnere når spennet er langt — ellers står tallene oppå
  // hverandre og kurven blir uleselig av å være «mer informativ».
  if (antall <= 14) return 1;
  if (antall <= 28) return 2;
  if (antall <= 60) return 4;
  return 6;
}


function _toppunkt(punkter, topp) {
  // **Når er bemanningen høyest?** Det er spørsmålet kurven skal svare på,
  // og å lese det av søylehøyder er å gjette. Sammenhengende timer på
  // toppnivå slås sammen til ett spenn.
  const paaTopp = punkter.filter((p) => p.planlagt === topp);
  if (!paaTopp.length) return '';
  const forste = paaTopp[0];
  const siste = paaTopp[paaTopp.length - 1];
  const sammenhengende = paaTopp.length ===
    (punkter.indexOf(siste) - punkter.indexOf(forste) + 1);
  if (paaTopp.length === 1 || !sammenhengende) {
    return `kl. ${_kl(forste.tid)}`;
  }
  // Toppen varer ut den siste timen, ikke til den begynner.
  const slutt = new Date(_d(siste.tid).getTime() + 3600 * 1000).toISOString();
  return `kl. ${_kl(forste.tid)}–${_kl(slutt)}`;
}


function _mkEnKurve(tittel, poster) {
  const punkter = _bemanningPerTime(poster);
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
    const tittelTekst = `${_dag(p.tid)} kl. ${_kl(p.tid)}: `
                      + `${p.antall} av ${p.planlagt} plasser fylt`;
    return `<div class="vl-stolpe${skille}" title="${escHtmlValue(tittelTekst)}">
              <div class="vl-planlagt" style="height: ${escHtmlValue(hPlanlagt)}%"></div>
              <div class="vl-bemannet" style="height: ${escHtmlValue(hBemannet)}%"></div>
            </div>`;
  }).join('');

  // Klokkeslettene ligger i sin egen rad med én celle per søyle, ikke som
  // tekst inni søylen: cellene arver samme flex-bredde, så tallet står
  // under den timen det gjelder uansett hvor mange timer vakta er.
  const steg = _timesteg(punkter.length);
  const timeakse = punkter.map((p, i) => {
    const vis = i % steg === 0;
    return `<span class="vl-time">${vis ? escapeHtml(_kl(p.tid)) : ''}</span>`;
  }).join('');

  const bunn = `${escapeHtml(_dag(punkter[0].tid))} → `
             + `${escapeHtml(_dag(punkter[punkter.length - 1].tid))}`;
  const rest = ledige
    ? `<span class="vl-meta">${escHtmlValue(ledige)} ubesatte plasstimer</span>`
    : '<span class="vl-meta">Alle plasser fylt</span>';
  const naar = _toppunkt(punkter, topp);

  return `
    <div class="vl-kurvegruppe">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">${escapeHtml(tittel)}</span>
        <div class="d-flex align-items-center gap-3">${rest}</div>
      </div>
      <div class="vl-kurve">${soyler}</div>
      <div class="vl-timeakse">${timeakse}</div>
      <div class="vl-meta">${bunn} · topp ${escHtmlValue(topp)} plasser${
        naar ? ' ' + escapeHtml(naar) : ''}</div>
    </div>`;
}


function _tegnforklaring() {
  // Døgnskillet står i forklaringen fordi André spurte hva den hvite streken
  // var. En strek man må spørre om, er en strek som ikke forklarer noe.
  return `
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-bemannet"></i>Bemannet</span>
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-planlagt"></i>Ledig plass</span>
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-dogn"></i>Midnatt</span>`;
}


function _posterIGruppe(gruppeId) {
  const ressurser = new Set(_ressurserIGruppe(gruppeId).map((r) => r.id));
  return (aktivListe.vaktposter || [])
    .filter((vp) => ressurser.has(vp.ressurs_id));
}


function mkGruppekurve(gruppe) {
  // **Kurven står i fanen den gjelder**, øverst, over de ressursene den
  // summerer. Å lete etter samleplassens bemanning under «Oversikt» mens man
  // bemanner samleplassen, er ett skifte for mye.
  //
  // **Og den tegnes selv om gruppa ennå ikke har et eneste skift.** Den falt
  // bort i den tilstanden fram til 30. aug. 2026, og det var feil på akkurat
  // samme måte som at kurven en gang bare dekket skiftene: hullet man
  // planlegger for å tette er størst når ingen er satt opp, og da forsvant
  // hele kurven. Nå står den flat på null over vaktas spenn — som er svaret
  // på «hvor mye gjenstår her».
  const kurve = _mkEnKurve(gruppe.navn, _posterIGruppe(gruppe.id));
  if (!kurve) return '';
  return `
    <div class="vl-kort vl-kurve-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">Bemanning — ${escapeHtml(gruppe.navn)}</span>
        <div class="d-flex align-items-center gap-3">${_tegnforklaring()}</div>
      </div>
      ${kurve}
    </div>`;
}


function _skiftrekkefolge(a, b) {
  // **Fra, så til, så navn.** Uten `til_tid` som andre ledd står skiftene som
  // begynner samtidig i tilfeldig rekkefølge, og et kort skift på fem timer
  // havner midt blant de lange — det var André som så det: en rad som slutter
  // 22:15 lå mellom rader som slutter 03:00 neste dag. Rekkefølgen skal si
  // noe, ellers er den bare innsettingsrekkefølgen forkledd som sortering.
  return a.fra_tid.localeCompare(b.fra_tid)
      || a.til_tid.localeCompare(b.til_tid)
      || (a.navn || '').localeCompare(b.navn || '');
}


function mkOversikt() {
  // **Utskriftslista.** Hele vakta på ett ark, gruppert på **ressurs** — den
  // man henger opp.
  //
  // Gruppert på korps fram til 30. aug. 2026, og det var feil bord: den som
  // leser lista står på samleplassen eller ved bilen og spør «hvem er her, og
  // når?». Korpset er et kjennetegn ved personen, ikke et sted — det er en
  // kolonne, ikke en overskrift.
  const poster = aktivListe.vaktposter || [];
  if (!poster.length) {
    return '<div class="vl-kort"><div class="vl-tom">Ingen er satt opp ennå.</div></div>';
  }

  const korpsnavn = {};
  (aktivListe.korps || []).forEach((k) => {
    korpsnavn[k.id] = k.kortnavn || k.navn;
  });

  const perRessurs = new Map();
  (aktivListe.ressurser || []).forEach((r) => perRessurs.set(r.id, []));
  poster.forEach((vp) => {
    if (perRessurs.has(vp.ressurs_id)) perRessurs.get(vp.ressurs_id).push(vp);
  });

  // Rekkefølgen er gruppas, så ressursens — samme som fanene. Ressurser uten
  // skift utelates: en tom tabell på papiret er en linje man må lese for å se
  // at det ikke står noe der.
  const deler = _grupperMedRessurser().flatMap((g) =>
    _ressurserIGruppe(g.id)
      .filter((r) => (perRessurs.get(r.id) || []).length)
      .map((r) => {
        const rader = perRessurs.get(r.id).slice().sort(_skiftrekkefolge)
          .map((vp) => {
            // Korpset i lista: personens når raden er fylt, plassens
            // reservasjon når den er ledig. Det er det samme skillet som i
            // ressurstabellen, og av samme grunn.
            const korps = vp.ledig
              ? (korpsnavn[vp.reservert_korps_id] || '')
              : (vp.korps_kort || '');
            return `
        <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
          <td class="vl-navn">${escapeHtml(vp.ledig ? '— ledig —' : vp.navn)}</td>
          <td>${escapeHtml(korps || '—')}</td>
          <td>${escapeHtml(vp.rolle || '—')}</td>
          <td>${escapeHtml(_tidsspenn(vp))}</td>
          <td>${escapeHtml(vp.merknad || '')}</td>
        </tr>`;
          }).join('');
        const ledige = perRessurs.get(r.id).filter((vp) => vp.ledig).length;
        const rest = ledige
          ? ` <span class="vl-meta">· ${escHtmlValue(ledige)} ledige</span>` : '';
        return `
      <div class="vl-korpsgruppe">
        <h3>${escapeHtml(r.navn)}
          <span class="vl-meta">${escapeHtml(g.navn)} ·
            ${escHtmlValue(perRessurs.get(r.id).length)} skift</span>${rest}
        </h3>
        <div class="vl-tabellramme">
        <table class="vl-tabell vl-utskrift">
          <colgroup>
            <col style="width: 26%"><col style="width: 12%"><col style="width: 18%">
            <col style="width: 30%"><col style="width: 14%">
          </colgroup>
          <thead>
            <tr><th>Navn</th><th>Korps</th><th>Rolle</th><th>Tid</th><th>Merknad</th></tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
        </div>
      </div>`;
      }));

  const tittel = aktivListe.vaktliste.vakt_navn;
  const spenn = _vaktspenn();
  const antallLedige = poster.filter((vp) => vp.ledig).length;
  const ledigtekst = antallLedige
    ? ` · ${escHtmlValue(antallLedige)} ledige plasser` : '';
  // **Ingen kurve her.** Den står i fanen den gjelder, og to steder å lese
  // den samme kurven er ett for mye. «Oversikt» er utskriftslista, og bare det.
  return `
    <div class="vl-kort vl-utskriftsark">
      <div class="vl-arkhode">
        <h2>${escapeHtml(tittel)}</h2>
        <div class="vl-meta">${escapeHtml(spenn)} ·
          ${escHtmlValue(poster.length)} skift${escapeHtml(ledigtekst)}</div>
      </div>
      ${deler.join('')}
    </div>`;
}


function _tilstede() {
  // **Definisjonen er knivskarp: møtt, og ikke gått av vakt.** Utledet av
  // stemplene, aldri en lagret status — to kilder til samme sannhet går i
  // utakt første gang noe feiler halvveis. Speiler `Vaktpost.er_tilstede`,
  // og serveren sender flagget ferdig utregnet nettopp derfor.
  return (aktivListe?.vaktposter || []).filter((vp) => vp.tilstede);
}


function mkTilstede() {
  // **Modulens mest alvorlige visning.** På et sted med overnatting brukes
  // den til å vite hvem som er i bygget ved brann. Det stiller tre krav
  // resten av sida ikke har:
  //
  // 1. Tellingen står øverst, stor. I en evakuering teller man hoder mot et
  //    tall, og da skal tallet være det første man ser.
  // 2. Lista skal kunne skrives ut. Strøm og nett er det første som ryker i
  //    nettopp situasjonen lista finnes for, så rutinen bør være å skrive
  //    den ut ved vaktstart og ved skiftbytte.
  // 3. Ingen redigering. Dette er en oversikt man leser under press;
  //    stemplene settes i ressursfanene, der man ser hvem som mangler.
  const rader = _tilstede();
  const alle = (aktivListe?.vaktposter || []).filter((vp) => !vp.ledig);
  const stemplet = new Date().toLocaleTimeString('no-NO',
    { hour: '2-digit', minute: '2-digit' });

  // Gruppert på ressurs, som utskriftslista: den som leter etter en person
  // vet hvilken bil hun står på, ikke hvilken rad hun har.
  const perRessurs = new Map();
  rader.forEach((vp) => {
    if (!perRessurs.has(vp.ressurs_id)) perRessurs.set(vp.ressurs_id, []);
    perRessurs.get(vp.ressurs_id).push(vp);
  });

  const bolker = (aktivListe?.ressurser || [])
    .filter((r) => perRessurs.has(r.id))
    .map((r) => {
      const linjer = perRessurs.get(r.id)
        .slice().sort((a, b) => (a.navn || '').localeCompare(b.navn || ''))
        .map((vp) => `
          <tr>
            <td class="vl-navn">${escapeHtml(vp.navn)}</td>
            <td>${escapeHtml(vp.korps_kort || '—')}</td>
            <td>${escapeHtml(vp.rolle || '—')}</td>
            <td>${escapeHtml(_kl(vp.mott_at))}</td>
            <td>${escapeHtml(_tidsspenn(vp))}</td>
          </tr>`).join('');
      return `
        <div class="vl-kort">
          <div class="vl-kort-topp">
            <span class="vl-kort-tittel">
              <i class="bi bi-${escHtmlValue(r.ikon)} me-1"></i>${escapeHtml(r.navn)}
              <span class="vl-meta">${escHtmlValue(perRessurs.get(r.id).length)}</span>
            </span>
          </div>
          <div class="vl-tabellramme">
            <table class="vl-tabell vl-utskrift">
              <thead>
                <tr><th>Navn</th><th>Korps</th><th>Rolle</th>
                    <th>Møtt</th><th>Planlagt skift</th></tr>
              </thead>
              <tbody>${linjer}</tbody>
            </table>
          </div>
        </div>`;
    }).join('');

  const mangler = alle.length - rader.length;
  const innhold = bolker || '<div class="vl-kort"><div class="vl-tom">Ingen '
    + 'er registrert møtt ennå. Stemplene settes i ressursfanene.</div></div>';
  return `
    <div class="vl-kort vl-tilstedehode">
      <div>
        <div class="vl-tilstedetall">${escHtmlValue(rader.length)}</div>
        <div class="vl-meta">tilstede nå · ${escapeHtml(stemplet)}</div>
      </div>
      <div class="vl-tilstedemeta">
        <div>${escHtmlValue(alle.length)} satt opp på vakta</div>
        <div>${escHtmlValue(mangler)} ikke møtt eller gått av vakt</div>
        <div class="vl-meta">Møtt, og ikke gått av vakt. Utledet av
          stemplene.</div>
      </div>
      <button class="btn btn-sm btn-outline-secondary" type="button"
              data-action="skrivUt">
        <i class="bi bi-printer me-1"></i>Skriv ut
      </button>
    </div>
    ${innhold}`;
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


function apneNyRessurs(gruppeId) {
  // Gruppa kommer enten fra knappen inne i fanen (`data-arg`), eller fra
  // fanen man står i. Nedtrekket er fortsatt et nedtrekk, så den første
  // enheten i en ny gruppe også har en vei inn.
  _skjulFeil('ny-ressurs-feil');
  const felt = document.getElementById('ny-ressurs-gruppe');
  const maal = gruppeId != null && gruppeId !== '' ? gruppeId : aktivFane;
  const valgbare = (aktivListe?.grupper || [])
    .filter((g) => g.er_aktiv && gruppaHarPlass(g));
  _fyll('ny-ressurs-gruppe', valgbare, null);
  const gruppe = valgbare.find((g) => String(g.id) === String(maal));
  if (felt && gruppe) {
    felt.value = String(gruppe.id);
    const tittel = document.getElementById('ny-ressurs-tittel');
    if (tittel) tittel.textContent = `Ny ${gruppe.navn}`;
  }
  new bootstrap.Modal(document.getElementById('nyRessursModal')).show();
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
        // Bare navn og gruppe. Reservasjon og enhetskobling settes i
        // «Rediger» — de hører til enheten, ikke til opprettelsen.
        body: JSON.stringify({
          navn,
          gruppe_id: document.getElementById('ny-ressurs-gruppe')?.value,
        }),
      });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ny-ressurs-feil', d.message || 'Kunne ikke legge til ressursen.');
      return;
    }
    _lukkModal('nyRessursModal');
    document.getElementById('ny-ressurs-navn').value = '';
    // Fanen er gruppa, så det er dit den nye ressursen dukker opp.
    aktivFane = String(d.data.gruppe_id);
    await lastListe(aktivListe.vaktliste.id);
  });
}


function apneRessurs(id) {
  // **Rediger-vinduet, og det eneste stedet en ressurs kan fjernes.**
  // «Fjern ressurs» sto tidligere naken ved siden av «Sett på vakt», og
  // CASCADE tar alle skiftene: ett feilklikk kostet hele bemanningen på
  // bilen. Nå må man inn hit først, og bekrefte etterpå.
  const r = aktivListe?.ressurser.find((x) => x.id === id);
  if (!r) return;
  _skjulFeil('ressurs-feil');
  const modal = document.getElementById('ressursModal');
  modal.dataset.ressurs = String(id);

  document.getElementById('ressurs-navn').value = r.navn;
  _settValg('ressurs-gruppe', (aktivListe.grupper || []).filter(
    (g) => g.er_aktiv || g.id === r.gruppe_id), r.gruppe_id);
  _settValg('ressurs-korps', aktivListe.korps || [], r.korps_id, 'Ureservert');
  _settValg('ressurs-enhet', aktivListe.enheter || [], r.enhet_id, 'Ingen');

  const antall = _posterFor(id).length;
  const tekst = document.getElementById('ressurs-slett-tekst');
  if (tekst) {
    tekst.textContent = antall
      ? `${antall} oppsatt(e) skift fjernes sammen med ressursen.`
      : 'Ressursen har ingen skift på seg.';
  }
  new bootstrap.Modal(modal).show();
}


function _settValg(id, rader, valgt, tomEtikett) {
  // Fylles fra data hver gang vinduet åpnes. Serveren sender listene i
  // hovedsvaret, og å bygge dem i malen ville krevd en ny sidelasting for
  // hver nye gruppe.
  const el = document.getElementById(id);
  if (!el) return;
  const valg = tomEtikett != null
    ? [`<option value="">— ${escapeHtml(tomEtikett)} —</option>`] : [];
  el.innerHTML = valg.concat(rader.map((r) => {
    const merke = r.id === valgt ? ' selected' : '';
    return `<option value="${escHtmlValue(r.id)}"${merke}>${escapeHtml(r.navn)}</option>`;
  })).join('');
}


async function lagreRessurs() {
  const id = document.getElementById('ressursModal')?.dataset.ressurs;
  if (!id) return;
  _skjulFeil('ressurs-feil');
  await withSubmitGuard('ressurs-knapp', async () => {
    const navn = (document.getElementById('ressurs-navn')?.value || '').trim();
    if (!navn) { _visFeil('ressurs-feil', 'Ressursen må ha et navn.'); return; }

    const res = await apiFetch(`/vaktliste/api/ressurser/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        navn,
        gruppe_id: document.getElementById('ressurs-gruppe')?.value || null,
        korps_id: document.getElementById('ressurs-korps')?.value || null,
        enhet_id: document.getElementById('ressurs-enhet')?.value || null,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('ressurs-feil', d.message || 'Kunne ikke lagre ressursen.');
      return;
    }
    _lukkModal('ressursModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function slettRessurs() {
  const id = Number(document.getElementById('ressursModal')?.dataset.ressurs);
  if (!id) return;
  const ressurs = aktivListe?.ressurser.find((r) => r.id === id);
  const antall = _posterFor(id).length;
  const advarsel = antall
    ? `\n\n${antall} oppsatt(e) skift fjernes sammen med den. Dette kan ikke angres.`
    : '\n\nDette kan ikke angres.';
  if (!confirm(`Fjerne «${ressurs ? ressurs.navn : 'ressursen'}»?${advarsel}`)) return;

  // Serveren krever `confirm` i tillegg til dialogen her. De to er ikke
  // samme sperre: dialogen stopper feilklikket, kroppen stopper et kall som
  // treffer URL-en uten å mene det.
  const res = await apiFetch(`/vaktliste/api/ressurser/${id}/`, {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) {
    _visFeil('ressurs-feil', d.message || 'Kunne ikke fjerne ressursen.');
    return;
  }
  _lukkModal('ressursModal');
  // Bli stående i gruppa hvis den har flere ressurser igjen; var det den
  // siste, forsvinner fanen og «Oversikt» er det eneste rimelige stedet.
  const gruppeId = ressurs ? ressurs.gruppe_id : null;
  await lastListe(aktivListe.vaktliste.id);
  if (!gruppeId || !_ressurserIGruppe(gruppeId).length) {
    aktivFane = OVERSIKT;
    tegn();
  }
}




function apneVaktpost(ressursId) {
  const ressurs = aktivListe?.ressurser.find((r) => r.id === ressursId);
  if (!ressurs) return;
  _skjulFeil('ny-vaktpost-feil');
  document.getElementById('ny-vaktpost-tittel').textContent =
    `Opprett vakt — ${ressurs.navn}`;
  document.getElementById('nyVaktpostModal').dataset.ressurs = String(ressursId);
  // Rollene som tilbys er gruppas — samme regel som i raden.
  _fyll('ny-vaktpost-rolle',
        rollerForGruppe(ressurs.gruppe_id, null), 'Uten rolle');
  document.getElementById('ny-vaktpost-mannskap').value = '';
  document.getElementById('ny-vaktpost-antall').value = '1';

  // **Datoen står der på forhånd, hentet fra vaktas start.** Feltet er
  // uendret — samme native velger, samme visning — men det er aldri tomt,
  // og da taster man fire siffer for klokkeslettet i stedet for tolv for
  // hele datoen. Vaktas start og ikke klokka nå: en oktobervakt planlegges i
  // august, og «i dag» er da et årstall på avveie.
  //
  // Sto feltene urørt, bar de dessuten tidene fra forrige gang vinduet var
  // åpent — på en annen ressurs, i en annen gruppe.
  const start = aktivListe?.vaktliste?.startet || null;
  _settTid('ny-vaktpost-fra', start);
  _settTid('ny-vaktpost-til', start);

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


// ── Ressursroller ────────────────────────────────────────────────────────
//
// Administreres herfra, ikke fra mannskapsregisteret: rollene brukes i
// ressurstabellen, og å måtte bytte side for å lage «Sjåfør» mens man bemanner
// en bil er akkurat den knotet dette skal fjerne.

function apneRoller(ressursId) {
  // **Manageren åpnes fra ressursen og gjelder ressursens gruppe.** Lager du
  // «Sjåfør» inne i Ambulanse 1, finnes den på hver ambulanse — men ikke på
  // samleplassen. Gruppa er riktig nivå: har du tre ambulanser, vil du lage
  // rollen én gang, ikke tre.
  const r = aktivListe?.ressurser.find((x) => x.id === ressursId);
  if (!r) return;
  _skjulFeil('rolle-feil');
  const modal = document.getElementById('rollerModal');
  modal.dataset.gruppe = String(r.gruppe_id);
  document.getElementById('ny-rolle-navn').value = '';

  const tittel = document.getElementById('roller-tittel');
  if (tittel) tittel.textContent = `Roller for ${r.gruppe_navn}`;
  const hjelp = document.getElementById('roller-hjelp');
  if (hjelp) {
    hjelp.textContent = `Rollene gjelder alle ressurser i gruppa `
                      + `«${r.gruppe_navn}», ikke bare ${r.navn}.`;
  }

  tegnRoller();
  new bootstrap.Modal(modal).show();
}


function tegnRoller() {
  const el = document.getElementById('rolle-liste');
  if (!el) return;
  const gruppeId = Number(document.getElementById('rollerModal')?.dataset.gruppe);
  const roller = ((aktivListe && aktivListe.roller) || [])
    .filter((r) => r.gruppe_id === gruppeId);
  el.innerHTML = roller.length ? roller.map(mkRolleRad).join('')
    : '<div class="vl-tom">Ingen roller i denne gruppa ennå.</div>';
}


function mkRolleRad(r) {
  // «I bruk» står i lista: en rolle man kan slette uten å vite hvor mange
  // skift som peker på den, sletter man for lett.
  const bruk = r.i_bruk
    ? `<span class="vl-meta">${escHtmlValue(r.i_bruk)} i bruk</span>`
    : '<span class="vl-meta">ubrukt</span>';
  return `
    <div class="vl-rad">
      <span class="vl-navn">${escapeHtml(r.navn)}</span>
      <div class="d-flex align-items-center gap-2">
        ${bruk}
        <button class="btn btn-sm btn-outline-danger" type="button"
                title="Slett rollen" aria-label="Slett rollen"
                data-action="slettRolle" data-id="${escHtmlValue(r.id)}"><i class="bi bi-trash"></i></button>
      </div>
    </div>`;
}


async function opprettRolle() {
  _skjulFeil('rolle-feil');
  await withSubmitGuard('ny-rolle-knapp', async () => {
    const navn = (document.getElementById('ny-rolle-navn')?.value || '').trim();
    if (!navn) { _visFeil('rolle-feil', 'Rollen må ha et navn.'); return; }
    const gruppeId = document.getElementById('rollerModal')?.dataset.gruppe;

    const res = await apiFetch('/vaktliste/api/roller/', {
      method: 'POST', body: JSON.stringify({ navn, gruppe_id: gruppeId }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('rolle-feil', d.message || 'Kunne ikke legge til rollen.');
      return;
    }
    document.getElementById('ny-rolle-navn').value = '';
    await lastListe(aktivListe.vaktliste.id);
    tegnRoller();
  });
}


async function slettRolle(id) {
  const rolle = (aktivListe.roller || []).find((r) => r.id === id);
  if (!rolle) return;
  if (!confirm(`Slette rollen «${rolle.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/roller/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { _visFeil('rolle-feil', d.message || 'Kunne ikke slette.'); return; }
  _skjulFeil('rolle-feil');
  await lastListe(aktivListe.vaktliste.id);
  tegnRoller();
}


function apneGrupper() {
  // **Gruppene hadde endepunkt, men ingen flate.** Det er nøyaktig feilen
  // Django-admin ga oss én gang før: et register som bare finnes i API-et,
  // finnes ikke for brukeren. Uten dette kunne man ikke lage «Førstehjelpstelt»
  // i det hele tatt — bare velge blant de seks migrasjonen seedet.
  _skjulFeil('gruppe-feil');
  document.getElementById('ny-gruppe-navn').value = '';
  document.getElementById('ny-gruppe-ikon').value = '';
  const flere = document.getElementById('ny-gruppe-flere');
  if (flere) flere.checked = true;
  tegnGrupper();
  new bootstrap.Modal(document.getElementById('grupperModal')).show();
}


function tegnGrupper() {
  const el = document.getElementById('gruppe-liste');
  if (!el) return;
  const grupper = (aktivListe && aktivListe.grupper) || [];
  el.innerHTML = grupper.length ? grupper.map(mkGruppeRad).join('')
    : '<div class="vl-tom">Ingen grupper ennå.</div>';
}


function mkGruppeRad(g) {
  // «I bruk» er antall ressurser på gruppa. En gruppe man kan slette uten å
  // vite hvor mange biler som står i den, sletter man for lett — og
  // `PROTECT` ville uansett stoppet det, men da som en feilmelding framfor
  // som noe man kunne sett på forhånd.
  const bruk = g.i_bruk
    ? `<span class="vl-meta">${escHtmlValue(g.i_bruk)} i bruk</span>`
    : '<span class="vl-meta">ubrukt</span>';
  const ett = g.flere_enheter === false
    ? '<span class="vl-merkelapp">ett eksemplar</span>' : '';
  const slett = g.i_bruk ? '' : `
        <button class="btn btn-sm btn-outline-danger" type="button"
                title="Slett gruppa" aria-label="Slett gruppa"
                data-action="slettGruppe" data-id="${escHtmlValue(g.id)}"><i class="bi bi-trash"></i></button>`;
  return `
    <div class="vl-rad">
      <span class="vl-navn">
        <i class="bi bi-${escHtmlValue(g.ikon)} me-2"></i>${escapeHtml(g.navn)}
      </span>
      <div class="d-flex align-items-center gap-2">
        ${ett}
        ${bruk}
        ${slett}
      </div>
    </div>`;
}


async function opprettGruppe() {
  _skjulFeil('gruppe-feil');
  await withSubmitGuard('ny-gruppe-knapp', async () => {
    const navn = (document.getElementById('ny-gruppe-navn')?.value || '').trim();
    if (!navn) { _visFeil('gruppe-feil', 'Gruppa må ha et navn.'); return; }

    const res = await apiFetch('/vaktliste/api/grupper/', {
      method: 'POST',
      body: JSON.stringify({
        navn,
        ikon: (document.getElementById('ny-gruppe-ikon')?.value || '').trim(),
        flere_enheter: !!document.getElementById('ny-gruppe-flere')?.checked,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('gruppe-feil', d.message || 'Kunne ikke legge til gruppa.');
      return;
    }
    document.getElementById('ny-gruppe-navn').value = '';
    document.getElementById('ny-gruppe-ikon').value = '';
    await lastListe(aktivListe.vaktliste.id);
    tegnGrupper();
  });
}


async function slettGruppe(id) {
  const gruppe = (aktivListe.grupper || []).find((g) => g.id === id);
  if (!gruppe) return;
  if (!confirm(`Slette gruppa «${gruppe.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/grupper/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { _visFeil('gruppe-feil', d.message || 'Kunne ikke slette.'); return; }
  _skjulFeil('gruppe-feil');
  await lastListe(aktivListe.vaktliste.id);
  tegnGrupper();
}


function apneVakt() {
  // **Ett vindu for vakta.** Lengden og utskriften er begge ting man gjør
  // med *vakta*, ikke med en ressurs — og som to knapper i toppen konkurrerte
  // de med «Ny ressurs» og «Ny vaktliste» om plassen uten å høre til samme
  // spørsmål. Utskriften ligger her fordi den er hele vaktlista på ett ark.
  //
  // **Vinduet åpnes også uten vaktliste.** Korps og kompetanser bor her, og
  // de er nettopp det man legger inn før den første lista finnes — sto
  // vinduet stengt til da, var registrene uten vei inn. Bolkene som gjelder
  // én liste skjules i stedet.
  _skjulFeil('vakt-lengde-feil');
  const harListe = !!aktivListe;
  document.getElementById('vakt-for-lista')
    ?.classList.toggle('d-none', !harListe);
  const lengde = document.getElementById('vakt-lengde-bolk');
  if (lengde && !harListe) lengde.classList.add('d-none');

  if (!harListe) {
    const t = document.getElementById('vakt-tittel');
    if (t) t.textContent = 'Innstillinger';
    _apneModal('vaktModal');
    return;
  }

  const vl = aktivListe.vaktliste;
  _settTid('vakt-start', vl.startet);
  _settTid('vakt-slutt', vl.planlagt_slutt);

  const tittel = document.getElementById('vakt-tittel');
  if (tittel) tittel.textContent = vl.vakt_navn;
  const spenn = document.getElementById('vakt-spenn');
  if (spenn) spenn.textContent = _vaktspenn();
  const antall = document.getElementById('vakt-antall');
  if (antall) {
    const poster = aktivListe.vaktposter || [];
    const ledige = poster.filter((v) => v.ledig).length;
    antall.textContent = ledige
      ? `${poster.length} skift, hvorav ${ledige} ledige plasser`
      : `${poster.length} skift`;
  }

  if (lengde) lengde.classList.toggle('d-none', !kanLede());
  _apneModal('vaktModal');
}


function skrivUtVakta() {
  // Vinduet må lukkes først: en åpen modal ligger over arket, og
  // `window.print()` tar med det som står på skjermen.
  _lukkModal('vaktModal');
  visFane(OVERSIKT);
  setTimeout(skrivUt, 250);
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
    _lukkModal('vaktModal');
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
        korps_id: document.getElementById('ny-vaktpost-korps')?.value || null,
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


async function settDrift(tilstand) {
  if (!aktivListe) return;
  skjulPanelfeil();
  const res = await apiFetch(
    `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/drift/${tilstand}/`,
    { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke endre driftstatus.');
    return;
  }
  // Stenges innsjekken mens man står i «Tilstede nå», forsvinner fanen —
  // og en fane som forsvinner under føttene skal ikke etterlate et tomt
  // panel.
  if (tilstand === 'stopp' && aktivFane === TILSTEDE) aktivFane = OVERSIKT;
  await lastListe(aktivListe.vaktliste.id);
}


//: Klienthandling → serverens overgang. Ett sted, slik at de fire knappene
//: og de fire endepunktene ikke kan gli fra hverandre.
const STEMPLINGER = {
  stemplMott: 'mott',
  stemplAvVakt: 'av_vakt',
  angreMott: 'angre_mott',
  angreAvVakt: 'angre_av_vakt',
};


function stemplMott(id) { return _stemple(id, STEMPLINGER.stemplMott); }
function stemplAvVakt(id) { return _stemple(id, STEMPLINGER.stemplAvVakt); }
function angreMott(id) { return _stemple(id, STEMPLINGER.angreMott); }
function angreAvVakt(id) { return _stemple(id, STEMPLINGER.angreAvVakt); }


async function _stemple(id, handling) {
  // **Kroppen sendes ikke.** Knappen vet hvilken overgang den utfører, og
  // serveren utleder ingenting av gjeldende tilstand — samme grep som
  // oppdragsmodulens stemplinger. `POST .../neste/` ville gitt et kappløp
  // når to trykk kommer tett.
  if (!aktivListe) return;
  skjulPanelfeil();
  const res = await apiFetch(
    `/vaktliste/api/vaktposter/${id}/stempling/${handling}/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    visPanelfeil(d.message || 'Kunne ikke registrere stemplingen.');
    return;
  }
  await lastListe(aktivListe.vaktliste.id);
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


function apneRedigerVaktpost(id) {
  // **Bytte person skal ikke koste skiftet.** Før måtte man fjerne raden og
  // sette den opp på nytt, og da mistet man tidene og rollen som allerede
  // sto der. Her endres alt sammen i ett kall, og serveren sjekker den doble
  // regelen på nytt mot den som skal inn.
  const vp = (aktivListe?.vaktposter || []).find((v) => v.id === id);
  if (!vp) return;
  const ressurs = aktivListe.ressurser.find((r) => r.id === vp.ressurs_id);
  if (!ressurs) return;

  _skjulFeil('vaktpost-feil');
  const modal = document.getElementById('vaktpostModal');
  modal.dataset.vaktpost = String(id);

  const tittel = document.getElementById('vaktpost-tittel');
  if (tittel) tittel.textContent = `Rediger skift — ${ressurs.navn}`;

  _fyll('vaktpost-mannskap', (aktivListe.mannskap || []).map((m) => ({
    id: m.id, navn: `${m.navn} — ${m.korps_navn}`,
  })), '— ledig plass —');
  _fyll('vaktpost-rolle', rollerForGruppe(ressurs.gruppe_id, vp.rolle_id),
        'Uten rolle');
  _fyll('vaktpost-korps', (aktivListe.korps || []).map((k) => ({
    id: k.id, navn: k.kortnavn || k.navn,
  })), '— som ressursen —');
  _settVerdi('vaktpost-korps', vp.plass_korps_id);

  _settVerdi('vaktpost-mannskap', vp.mannskap_id);
  _settVerdi('vaktpost-rolle', vp.rolle_id);
  _settTid('vaktpost-fra', vp.fra_tid);
  _settTid('vaktpost-til', vp.til_tid);
  _settVerdi('vaktpost-merknad', vp.merknad || '');

  new bootstrap.Modal(modal).show();
}


function _settVerdi(id, verdi) {
  const el = document.getElementById(id);
  if (el) el.value = verdi == null ? '' : String(verdi);
}


async function lagreVaktpost() {
  const id = document.getElementById('vaktpostModal')?.dataset.vaktpost;
  if (!id) return;
  _skjulFeil('vaktpost-feil');
  await withSubmitGuard('vaktpost-knapp', async () => {
    const fra = _tidFraFelt('vaktpost-fra');
    const til = _tidFraFelt('vaktpost-til');
    if (!fra || !til) {
      _visFeil('vaktpost-feil', 'Skiftet må ha både fra- og til-tidspunkt.');
      return;
    }

    const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        mannskap_id: document.getElementById('vaktpost-mannskap')?.value || null,
        korps_id: document.getElementById('vaktpost-korps')?.value || null,
        rolle_id: document.getElementById('vaktpost-rolle')?.value || null,
        merknad: document.getElementById('vaktpost-merknad')?.value || '',
        fra_tid: fra,
        til_tid: til,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('vaktpost-feil', d.message || 'Kunne ikke lagre skiftet.');
      return;
    }
    _lukkModal('vaktpostModal');
    await lastListe(aktivListe.vaktliste.id);
  });
}


async function slettVaktpost() {
  const id = Number(document.getElementById('vaktpostModal')?.dataset.vaktpost);
  if (!id) return;
  const vp = (aktivListe?.vaktposter || []).find((v) => v.id === id);
  const hvem = vp && !vp.ledig ? `«${vp.navn}»` : 'den ledige plassen';
  if (!confirm(`Fjerne skiftet for ${hvem}?\n\nDette kan ikke angres.`)) return;

  const res = await apiFetch(`/vaktliste/api/vaktposter/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) {
    _visFeil('vaktpost-feil', d.message || 'Kunne ikke fjerne skiftet.');
    return;
  }
  _lukkModal('vaktpostModal');
  await lastListe(aktivListe.vaktliste.id);
}




// ── MANNSKAPSREGISTERET ──────────────────────────────────────────────────
//
// Flyttet hit fra vaktliste-registre.js 30. aug. 2026, da registersiden ble
// lagt ned. Fanen er registeret; korps og kompetanser ligger i
// «Innstillinger», fordi de røres sjelden og er portalens oppsett.
//
// Alt som settes med innerHTML escapes: navn, telefon og notat er fritekst.

function kanRedigerePerson(person) {
  // Badgen. `skriv_handling` fører sitt eget korps og ingen andres.
  if (kanSkriveAlt()) return true;
  if (_nivaa() !== 'skriv_handling') return false;
  return window.MITT_KORPS_ID != null && person.korps_id === window.MITT_KORPS_ID;
}


function _passerPersonsok(m) {
  if (!personsok) return true;
  const n = personsok.toLowerCase();
  return [m.navn, m.korps_navn, m.telefon, m.brukernavn]
    .concat((m.alle_kompetanser || []).map((k) => k.navn))
    .some((v) => (v || '').toLowerCase().includes(n));
}


function _sorterMannskap(rader) {
  const nokkel = (m) => {
    if (personSortKol === 'navn') return m.navn.toLowerCase();
    if (personSortKol === 'telefon') return m.telefon || '\uffff';  // tomme sist
    return m.korps_navn.toLowerCase() + '\u0000' + m.navn.toLowerCase();
  };
  const ut = rader.slice().sort((a, b) => nokkel(a).localeCompare(nokkel(b)));
  return personSortStigende ? ut : ut.reverse();
}


function sorterMannskap(kolonne) {
  if (personSortKol === kolonne) personSortStigende = !personSortStigende;
  else { personSortKol = kolonne; personSortStigende = true; }
  tegnPanel();
}


function settPersonsok(verdi) {
  personsok = verdi;
  tegnPanel();
}


function _koblPersonsok() {
  // Egen lytter framfor `data-action`: delegeringen i portal-utils.js er
  // klikkbasert, og dette er et tastetrykk.
  const el = document.getElementById('vl-sok');
  if (el) el.addEventListener('input', () => settPersonsok(el.value));
}


function _personKolonne(kolonne, tekst) {
  // Pilen viser hvilken kolonne som styrer, og hvilken vei.
  const pil = personSortKol === kolonne ? (personSortStigende ? ' \u25b2' : ' \u25bc') : '';
  return `<th class="vlr-sortbar" data-action="sorterMannskap" data-arg="${escHtmlValue(kolonne)}">`
       + `${escapeHtml(tekst)}${escapeHtml(pil)}</th>`;
}


function mkMannskap() {
  if (!register) {
    return '<div class="vl-kort"><div class="vl-tom">Henter registeret\u2026</div></div>';
  }

  const nyKnapp = kanSkriveNoe()
    ? `<button class="btn btn-sm btn-primary" type="button"
               data-action="apneNyPerson">
         <i class="bi bi-person-plus me-1"></i>Nytt mannskap
       </button>`
    : '';
  const hode = `
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">
          <i class="bi bi-person-vcard me-1"></i>Mannskap
          <span class="vl-meta">${escHtmlValue(register.mannskap.length)} i registeret</span>
        </span>
        ${nyKnapp}
      </div>`;

  if (!register.korps.length) {
    // **Korpset først.** Det er badgen tilgangsmodellen hviler på, og uten
    // ett kan ingen person opprettes. Knappen sier derfor «Legg inn korps»
    // og ikke «Nytt mannskap»: en knapp som åpner noe annet enn det den
    // heter, er en knapp man klikker på én gang og aldri stoler på igjen.
    const tilKorps = kanSkriveAlt()
      ? `<button class="btn btn-sm btn-primary" type="button"
                 data-action="apneVerdier" data-arg="korps">
           <i class="bi bi-flag me-1"></i>Legg inn korps
         </button>`
      : '';
    return `
      <div class="vl-kort">
        <div class="vl-kort-topp">
          <span class="vl-kort-tittel">
            <i class="bi bi-person-vcard me-1"></i>Mannskap
          </span>
          ${tilKorps}
        </div>
        <div class="vl-tom">
          Ingen korps ennå. Et mannskap må høre til et korps — korpset er
          badgen tilgangsmodellen hviler på.
        </div>
      </div>`;
  }

  if (!register.mannskap.length) {
    return `<div class="vl-kort">${hode}`
         + '<div class="vl-tom">Ingen i registeret ennå. Trykk «Nytt mannskap».</div></div>';
  }

  // **Tabell, ikke merkelapper på rad.** Med én kompetanse så den gamle
  // visningen fin ut; med åtte brøt den om og skjøv telefonnummeret ut av
  // syne. Faste kolonner gjør at det du leter etter alltid står samme sted.
  const rader = _sorterMannskap(register.mannskap.filter(_passerPersonsok));

  const kropp = rader.length ? rader.map((m) => {
    const inaktiv = m.er_aktiv ? '' : ' vl-inaktiv';

    // Bare de synlige kompetansene — har hun AFØR, er VFØR implisert.
    // Hele settet ligger i `title`, så «har hun egentlig VFØR?» kan besvares
    // uten å åpne skjemaet.
    const alle = (m.alle_kompetanser || []).map((k) => k.navn).join(', ');
    const merker = m.kompetanser.length
      ? m.kompetanser.map((k) =>
          `<span class="vl-merkelapp">${escapeHtml(k.navn)}</span>`).join('')
      : '<span class="vl-meta">—</span>';

    // Ikoner, ikke tekst: to tekstknapper trenger ~150px og sprengte
    // handlingskolonnen på smale skjermer. `title` og `aria-label` bærer
    // betydningen — en ikonknapp uten dem er en gåte.
    const knapper = kanRedigerePerson(m)
      ? `<button class="btn btn-sm btn-outline-secondary" type="button"
                 title="Rediger ${escHtmlValue(m.navn)}" aria-label="Rediger ${escHtmlValue(m.navn)}"
                 data-action="apneRedigerPerson" data-id="${escHtmlValue(m.id)}"><i class="bi bi-pencil"></i></button>
         <button class="btn btn-sm btn-outline-danger" type="button"
                 title="Slett ${escHtmlValue(m.navn)}" aria-label="Slett ${escHtmlValue(m.navn)}"
                 data-action="slettPerson" data-id="${escHtmlValue(m.id)}"><i class="bi bi-trash"></i></button>`
      : '';

    const inaktivMerke = m.er_aktiv ? ''
      : ' <span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
    const konto = m.brukernavn
      ? escapeHtml(m.brukernavn) : '<span class="vl-meta">—</span>';

    return `
      <tr class="${escHtmlValue(inaktiv.trim())}">
        <td class="vl-navn">${escapeHtml(m.navn)}${inaktivMerke}</td>
        <td>${escapeHtml(m.korps_kort)}</td>
        <td class="vlr-komp" title="${escHtmlValue(alle)}">${merker}</td>
        <td class="vlr-tlf">${escapeHtml(m.telefon || '—')}</td>
        <td>${konto}</td>
        <td class="vlr-handling">${knapper}</td>
      </tr>`;
  }).join('')
    : `<tr><td colspan="6" class="vl-tom">Ingen treff på «${escapeHtml(personsok)}».</td></tr>`;

  const treff = document.getElementById('vl-treff');
  if (treff) {
    treff.textContent = personsok
      ? `${rader.length} av ${register.mannskap.length}` : `${rader.length}`;
  }

  return `
    <div class="vl-kort">
      ${hode}
      <div class="vlr-tabellramme">
        <table class="vlr-tabell">
          <colgroup>
            <col style="width: 26%"><col style="width: 9%">
            <col style="width: 31%"><col style="width: 12%">
            <col style="width: 10%"><col style="width: 12%">
          </colgroup>
          <thead>
            <tr>
              ${_personKolonne('navn', 'Navn')}
              ${_personKolonne('korps', 'Korps')}
              <th>Kompetanse</th>
              ${_personKolonne('telefon', 'Telefon')}
              <th>Konto</th>
              <th></th>
            </tr>
          </thead>
          <tbody>${kropp}</tbody>
        </table>
      </div>
    </div>`;
}


function _lesFelt(id) {
  return (document.getElementById(id)?.value || '').trim();
}


function _apneModal(id) {
  new bootstrap.Modal(document.getElementById(id)).show();
}


function _fyllPersonskjema(person) {
  // Inaktive korps og kompetanser tilbys ikke på nye rader, men beholdes på
  // dem som alt har dem — derfor filtreres det bare når feltet er tomt.
  const korps = register.korps.filter(
    (k) => k.er_aktiv || (person && person.korps_id === k.id));
  _fyll('person-korps', korps, '');
  _fyll('person-kompetanser', register.kompetanser.filter(
    (k) => k.er_aktiv || (person && person.kompetanser.some((x) => x.id === k.id))), '');

  // En konto kan bare kobles til én person (OneToOne). Vis de ledige, pluss
  // denne personens egen.
  const kontoer = register.kontoer
    .filter((u) => !u.mannskap_id || (person && u.mannskap_id === person.id))
    .map((u) => ({ id: u.id, navn: u.brukernavn }));
  _fyll('person-konto', kontoer, 'Ingen konto');

  _settVerdi('person-navn', person ? person.navn : '');
  _settVerdi('person-korps', person ? person.korps_id : '');
  _settVerdi('person-telefon', person ? person.telefon : '');
  _settVerdi('person-konto', person && person.user_id ? person.user_id : '');
  _settVerdi('person-notat', person ? person.notat : '');
  document.getElementById('person-aktiv').checked = person ? person.er_aktiv : true;
  document.getElementById('person-aktiv-rad').classList.toggle('d-none', !person);

  const valgte = new Set(person ? person.kompetanser.map((k) => k.id) : []);
  Array.from(document.getElementById('person-kompetanser').options).forEach((o) => {
    o.selected = valgte.has(Number(o.value));
  });
}


function apneNyPerson() {
  if (!register) return;
  if (!register.korps.length) { apneVerdier('korps'); return; }
  redigererPerson = null;
  _skjulFeil('person-feil');
  document.getElementById('person-tittel').textContent = 'Nytt mannskap';
  _fyllPersonskjema(null);
  _apneModal('personModal');
}


function apneRedigerPerson(id) {
  const person = register?.mannskap.find((m) => m.id === id);
  if (!person) return;
  redigererPerson = id;
  _skjulFeil('person-feil');
  document.getElementById('person-tittel').textContent = person.navn;
  _fyllPersonskjema(person);
  _apneModal('personModal');
}


async function lagrePerson() {
  _skjulFeil('person-feil');
  await withSubmitGuard('person-knapp', async () => {
    const navn = _lesFelt('person-navn');
    if (!navn) { _visFeil('person-feil', 'Personen må ha et navn.'); return; }
    const korpsId = _lesFelt('person-korps');
    if (!korpsId) {
      _visFeil('person-feil', 'Velg hvilket korps personen hører til.');
      return;
    }

    const kropp = {
      navn,
      korps_id: Number(korpsId),
      telefon: _lesFelt('person-telefon'),
      user_id: _lesFelt('person-konto') ? Number(_lesFelt('person-konto')) : null,
      notat: _lesFelt('person-notat'),
      kompetanse_ider: Array.from(
        document.getElementById('person-kompetanser').selectedOptions)
        .map((o) => Number(o.value)),
    };
    if (redigererPerson) {
      kropp.er_aktiv = document.getElementById('person-aktiv').checked;
    }

    const res = await apiFetch(
      redigererPerson ? `/vaktliste/api/mannskap/${redigererPerson}/`
                      : '/vaktliste/api/mannskap/',
      { method: redigererPerson ? 'PUT' : 'POST', body: JSON.stringify(kropp) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('person-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    _lukkModal('personModal');
    await _lastRegisterOgListe();
  });
}


async function slettPerson(id) {
  const person = register?.mannskap.find((m) => m.id === id);
  if (!person) return;
  if (person.i_bruk) {
    alert(`${person.navn} står på ${person.i_bruk} vaktpost(er) og kan ikke `
        + 'slettes.\n\nSett personen inaktiv i stedet — da skjules hun i '
        + 'nedtrekkslistene, men blir stående der hun gikk vakt.');
    return;
  }
  if (!confirm(`Slette ${person.navn} fra registeret?`)) return;

  const res = await apiFetch(`/vaktliste/api/mannskap/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { alert(d.message || 'Kunne ikke slette.'); return; }
  await _lastRegisterOgListe();
}


async function _lastRegisterOgListe() {
  // **Begge, ikke bare registeret.** Navn, korps og aktiv-flagget står i
  // nedtrekkene på planleggingssiden også — endres en person uten at lista
  // hentes på nytt, bemanner man fra en liste som er utdatert.
  await lastRegister();
  if (aktivListe) await lastListe(aktivListe.vaktliste.id);
}


// ── Korps og kompetanser (i «Innstillinger») ─────────────────────────────
//
// De to deler bygger og skjema, på samme måte som serveren deler fabrikk —
// kopier er kopier å glemme. Vinduet viser lista, og skjemaet folder seg ut
// inni det samme vinduet: en modal oppå en modal oppå en modal er tre lag
// man ikke finner tilbake fra.

function apneVerdier(navn) {
  aktivVerdiregister = navn;
  const reg = REGISTRE[navn];
  _skjulFeil('verdi-feil');
  _skjulVerdiskjema();
  const tittel = document.getElementById('verdi-tittel');
  if (tittel) tittel.textContent = reg.tittel;
  const ny = document.getElementById('verdi-ny-knapp');
  if (ny) {
    ny.textContent = reg.nyEtikett;
    ny.classList.toggle('d-none', !kanSkriveAlt());
  }
  if (!register) { lastRegister(); }
  tegnVerdiliste();
  _apneModal('verdiModal');
}


function tegnVerdiliste() {
  const el = document.getElementById('verdi-liste');
  if (!el) return;
  el.innerHTML = register ? mkVerdiliste(aktivVerdiregister)
    : '<div class="vl-tom">Henter\u2026</div>';
}


function mkVerdiliste(navn) {
  const rader = register[navn] || [];
  // Verdimengdene er organisasjonens oppsett — `skriv_full`. Korps-føreren
  // ser dem (nedtrekkslistene trenger dem), men endrer dem ikke.
  const full = kanSkriveAlt();
  if (!rader.length) return '<div class="vl-tom">Ingen ennå.</div>';

  return rader.map((r) => {
    const verdiKnapper = full
      ? `<button class="btn btn-sm btn-outline-secondary" type="button"
                 data-action="apneRedigerVerdi" data-id="${escHtmlValue(r.id)}">Rediger</button>
         <button class="btn btn-sm btn-outline-danger" type="button"
                 data-action="slettVerdi" data-id="${escHtmlValue(r.id)}">Slett</button>`
      : '';
    const inaktiv = r.er_aktiv ? '' : ' vl-inaktiv';
    const inaktivMerke = r.er_aktiv ? ''
      : '<span class="vl-merkelapp vl-ureservert">Inaktiv</span>';
    const kort = r.kortnavn
      ? `<span class="vl-merkelapp">${escapeHtml(r.kortnavn)}</span>` : '';
    // Stigen synliggjøres i lista: uten den må man åpne hver rad for å se
    // hvilke kurs som overordner hvilke.
    const stige = r.bygger_paa_navn
      ? `<span class="vl-meta">bygger på ${escapeHtml(r.bygger_paa_navn)}</span>`
      : '';
    // Tallet står i lista, ikke bare i feilmeldingen: en verdimengde man kan
    // slette uten å vite hva som henger i den, sletter man for lett.
    const bruk = r.i_bruk
      ? `<span class="vl-meta">${escHtmlValue(r.i_bruk)} i bruk</span>`
      : '<span class="vl-meta">ubrukt</span>';
    return `
      <div class="vl-rad${inaktiv}">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <span class="vl-navn">${escapeHtml(r.navn)}</span>
          ${inaktivMerke}${kort}${stige}${bruk}
        </div>
        <div class="d-flex gap-2">${verdiKnapper}</div>
      </div>`;
  }).join('');
}


function _skjulVerdiskjema() {
  document.getElementById('verdi-skjema')?.classList.add('d-none');
  document.getElementById('verdi-ny-knapp')?.classList.toggle(
    'd-none', !kanSkriveAlt());
}


function _visVerdiskjema(reg, rad) {
  document.getElementById('verdi-skjema')?.classList.remove('d-none');
  document.getElementById('verdi-ny-knapp')?.classList.add('d-none');
  _settVerdi('verdi-navn', rad ? rad.navn : '');
  _settVerdi('verdi-kortnavn', rad && rad.kortnavn ? rad.kortnavn : '');
  document.getElementById('verdi-aktiv').checked = rad ? rad.er_aktiv : true;
  document.getElementById('verdi-aktiv-rad').classList.toggle('d-none', !rad);
  document.getElementById('verdi-kortnavn-rad')
    .classList.toggle('d-none', !reg.kortnavn);
  _stigefelt(reg, rad);
}


function apneNyVerdi() {
  const reg = REGISTRE[aktivVerdiregister];
  redigererVerdi = null;
  _skjulFeil('verdi-feil');
  _visVerdiskjema(reg, null);
}


function _stigefelt(reg, rad) {
  // Kun kompetanser har en stige. En kompetanse kan ikke bygge på seg selv;
  // resten av ringene stoppes på serveren, som er den som kan se hele treet.
  const rad_el = document.getElementById('verdi-bygger-paa-rad');
  if (rad_el) rad_el.classList.toggle('d-none', !reg.stige);
  if (!reg.stige) return;
  const valg = ((register && register.kompetanser) || [])
    .filter((k) => !rad || k.id !== rad.id);
  _fyll('verdi-bygger-paa', valg, 'Ingen — står alene');
  _settVerdi('verdi-bygger-paa', rad && rad.bygger_paa_id ? rad.bygger_paa_id : '');
}


function apneRedigerVerdi(id) {
  const reg = REGISTRE[aktivVerdiregister];
  const rad = (register[aktivVerdiregister] || []).find((r) => r.id === id);
  if (!rad) return;
  redigererVerdi = id;
  _skjulFeil('verdi-feil');
  _visVerdiskjema(reg, rad);
}


function avbrytVerdi() {
  redigererVerdi = null;
  _skjulFeil('verdi-feil');
  _skjulVerdiskjema();
}


async function lagreVerdi() {
  const reg = REGISTRE[aktivVerdiregister];
  _skjulFeil('verdi-feil');
  await withSubmitGuard('verdi-knapp', async () => {
    const navn = _lesFelt('verdi-navn');
    if (!navn) { _visFeil('verdi-feil', 'Navn må fylles ut.'); return; }

    const kropp = { navn };
    if (reg.kortnavn) kropp.kortnavn = _lesFelt('verdi-kortnavn');
    if (reg.stige) kropp.bygger_paa_id = _lesFelt('verdi-bygger-paa') || null;
    if (redigererVerdi) {
      kropp.er_aktiv = document.getElementById('verdi-aktiv').checked;
    }

    const res = await apiFetch(
      redigererVerdi ? `/vaktliste/api/${reg.sti}/${redigererVerdi}/`
                     : `/vaktliste/api/${reg.sti}/`,
      { method: redigererVerdi ? 'PUT' : 'POST', body: JSON.stringify(kropp) });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      _visFeil('verdi-feil', d.message || 'Kunne ikke lagre.');
      return;
    }
    redigererVerdi = null;
    _skjulVerdiskjema();
    await _lastRegisterOgListe();
    tegnVerdiliste();
  });
}


async function slettVerdi(id) {
  const reg = REGISTRE[aktivVerdiregister];
  const rad = (register[aktivVerdiregister] || []).find((r) => r.id === id);
  if (!rad) return;
  if (!confirm(`Slette «${rad.navn}»?`)) return;

  const res = await apiFetch(`/vaktliste/api/${reg.sti}/${id}/`, { method: 'DELETE' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { alert(d.message || 'Kunne ikke slette.'); return; }
  await _lastRegisterOgListe();
  tegnVerdiliste();
}


document.addEventListener('DOMContentLoaded', () => {
  gateKnapper();
  _koblCellelytter();
  _koblPersonsok();
  document.getElementById('ny-vaktpost-mannskap')
    ?.addEventListener('change', _vaktpostModusSkifte);
  lastVaktlister();
});
