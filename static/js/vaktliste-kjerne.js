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
//: Planleggingstallene for den aktive lista, eller `null` før de er hentet.
//: Hentes for seg: en fane som ikke er åpnet skal ikke koste en spørring.
let belastning = null;
// Korpsvelgeren (11. sep. 2026): korps-ID for den som ser alle korps og vil
// se ett, ellers `null`. Brukes bare i nettleseren — serveren avgrenser
// korps-brukeren selv, og for henne finnes ikke velgeren.
let korpsfilter = null;
// Utskriftsutvalget (12. sep. 2026): ressurs-ID når «Oversikt» skal vise
// én ressurs, ellers `null` for hele vakten. Korpset styres av korpsvelgeren
// over — de to utvalgene kombineres.
//: **Utskriftsutvalget er en dag, ikke en ressurs** (André, 15. sep. 2026).
//: `null` er hele vakta; ellers en `_dagnokkel()`-streng. Ressursvalget ga
//: mening da arket var gruppert på ressurs — nå er dagen ytterste nivå, og
//: «Ambulanse 1» ville vært et snitt på tvers av det arket er bygget rundt.
let utskriftDag = null;
let personsok = '';              // fritekstfilter på mannskapstabellen
let personSortKol = 'korps';     // 'navn' | 'korps' | 'telefon'
let personSortStigende = true;
let redigererPerson = null;      // id-en som redigeres, eller null for «ny»
let redigererVerdi = null;
let aktivVerdiregister = 'korps';  // hvilket register verdivinduet står i
//: **Sammenslåtte ressurskort** (André, 14. sep. 2026). `tegnFaner()` og
//: `mkRessurs()` bygger markupen på nytt ved hvert panelbytte — det er samme
//: grunn til at `gateKnapper()` ikke kan gate dem — så tilstanden kan ikke bo
//: i DOM-en. Presedensen er `erDempet` i `oppdrag-enhet.js`.
//:
//: **Map, ikke Set**, fordi standarden avhenger av gruppa: fraværende nøkkel
//: betyr «som standarden», og standarden er sammenslått bare når gruppa har
//: mer enn én ressurs (André, 15. sep. 2026). Et Set kunne ikke skilt «ikke
//: rørt» fra «utvidet for hånd», og et kort man åpnet ville slått seg sammen
//: igjen neste gang noen la til en bil i gruppa.
//:
//: Ikke `localStorage`: en sidelasting er et nytt blikk på vakta, og et kort
//: man slo sammen i går skal ikke være skjult når man kommer tilbake for å
//: planlegge.
const ressursApen = new Map();

const OVERSIKT = 'oversikt';
const MANNSKAP = 'mannskap';
const TILSTEDE = 'tilstede';
const BELASTNING = 'belastning';
const IKKE_PLASSERT = 'ikke-plassert';
// «Mitt korps» (11. sep. 2026): plassene korpset har ansvar for, på tvers
// av ressursene — sine tildelte, og de som er tildelt alle.
const MITT_KORPS = 'mitt-korps';

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

// ════════════════════════════════════════════════════════
// vaktliste-kjerne.js
// ════════════════════════════════════════════════════════
//
// Tilstand, tilgang, tid, henting, korpsvelger og nedtrekk.
//
// **Denne fila må lastes først.** Alle `let`/`const` på toppnivå står her,
// og de er skript-scopede — de deles mellom filene, men en fil som leser
// dem før denne er kjørt, treffer en temporal dead zone.
//
// Delt ut av `vaktliste.js` 14. sep. 2026 (gjeldspunkt 3.6). Fila var
// 3 801 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/vaktliste/index.html`, og funksjonene deler ett globalt
// navnerom som før. `VaktlisteFileneDekkerAltTests` håndhever at
// ingen funksjon forsvant eller ble duplisert i delingen.
// ════════════════════════════════════════════════════════

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
  // Den som *setter opp* vakten: oppretter og fjerner ressurser og
  // vaktlister, endrer vaktas lengde, lager roller og grupper. Speiler
  // `services.kan_lede`.
  return _erAdmin() || _nivaa() === 'skriv_leder';
}


function kanSetteTak() {
  // **Serveren svarer, klienten spør ikke selv.** Taket settes i den samme
  // PUT-en som vaktas spenn og er derfor `skriv_leder` — men det er
  // serveren som eier den regelen, og `belastning.kan_sette_tak` er dens
  // svar. Regnet vi den ut her av `MODUL_TILGANG`, ville knappen og
  // endepunktet kunne komme i utakt, og da er vi tilbake til en knapp som
  // fører til en vegg.
  return !!(belastning && belastning.kan_sette_tak);
}


function kanSkriveNoe() {
  return kanSkriveAlt() || _nivaa() === 'skriv_handling';
}


function kanBemannePlass(vp, ressurs) {
  // Plassens svar på reservasjonshalvdelen — speiler `services.kan_bemanne_plass`.
  // Plassen kan være satt av til et annet korps enn ressursen, eller til
  // alle; ressursen alene visste ikke det, og korps-brukeren så ingen
  // nedtrekk på nettopp den plassen som var hennes.
  if (kanSkriveAlt()) return true;
  if (_nivaa() !== 'skriv_handling' || window.MITT_KORPS_ID == null) return false;
  if (vp.alle_korps) return true;
  const reservert = vp.reservert_korps_id != null ? vp.reservert_korps_id : (ressurs ? ressurs.korps_id : null);
  return reservert === window.MITT_KORPS_ID;
}


function kanRoreRad(vp, ressurs, kanRoreRessurs) {
  // Speiler `services.kan_rore_vaktpost`: står en av korpsets egne på
  // raden, er raden korpsets — uansett hvem plassen er satt av til (André,
  // 12. sep. 2026). Ellers gjelder reservasjonen på plassen.
  if (!vp.ledig) {
    // En fylt rad følger personen: egen person er egen rad, andres er deres
    // — også på egen ressurs. Den som skriver alt, skriver alt.
    if (kanSkriveAlt()) return true;
    return _nivaa() === 'skriv_handling'
      && window.MITT_KORPS_ID != null && vp.korps_id === window.MITT_KORPS_ID;
  }
  if (kanRoreRessurs) return true;
  return kanBemannePlass(vp, ressurs);
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
  document.querySelectorAll('.vl-krev-admin')
    .forEach((el) => el.classList.toggle('d-none', !_erAdmin()));
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
  // Offline drift (13. sep. 2026): svarer ikke serveren, gir service
  // workeren siste kopi med headeren `X-Vl-Kopi`; finnes ingen kopi, kaster
  // fetch, og lista som alt står på skjermen blir stående.
  let res;
  try {
    res = await apiFetch(`/vaktliste/api/vaktlister/${id}/`);
  } catch (e) {
    offlineTilstand.frakoblet = true;
    tegnOffline();
    return;
  }
  if (_sesjonUtgaatt(res)) { offlineTilstand.sesjonUtgaatt = true; tegnOffline(); return; }
  if (!res.ok) return;
  const kopi = res.headers.get('X-Vl-Kopi');
  offlineTilstand.kopiFra = kopi || null;
  offlineTilstand.frakoblet = !!kopi;
  if (!kopi) offlineTilstand.sesjonUtgaatt = false;
  aktivListe = (await res.json()).data;
  // Alt serveren sendte beholdes i `alle_vaktposter`; `vaktposter` er det
  // korpsvelgeren lar stå igjen. Byggerne leser `vaktposter` som før, så
  // filteret gjelder alle fanene uten at noen av dem vet om det.
  aktivListe.alle_vaktposter = aktivListe.vaktposter;
  _projiserKo();
  fyllKorpsvelger();
  brukKorpsfilter();
  // **Tallene er utdaterte i det et skift endres.** De hentes derfor på nytt
  // sammen med lista, ikke bufres over en endring — en belastningstabell som
  // viser gårsdagens oppsett er verre enn ingen.
  belastning = null;
  const velger = document.getElementById('vaktliste-velger');
  if (velger) velger.value = String(id);

  tegnManglerMannskap();

  fyllNedtrekk();
  tegn();
  tegnOffline();
}


async function lastRegister() {
  // Registeret er globalt, ikke vaktas. Det hentes for seg, og lastes på
  // nytt etter hver endring — navn og korps står i nedtrekkene på
  // planleggingssiden, så `lastListe()` må med når personer endres.
  const res = await apiFetch('/vaktliste/api/mannskap/');
  if (!res.ok) return;
  register = (await res.json()).data;
  register.alle_mannskap = register.mannskap;
  brukKorpsfilter();
  tegnManglerMannskap();
  tegn();
}


function registeretErTomt(reg) {
  // **Registeret, ikke lista i vakta.** `aktivListe.mannskap` er dem
  // brukeren får *sette* (`mannskap_brukeren_kan_sette`) — for korps-føreren
  // uten badge er den tom, mens registeret hun *ser* har alle korps. Sida sa
  // «Mannskapsregisteret er tomt» til henne (André, 13. sep. 2026), og det
  // var det ikke. Til registeret er hentet, vet vi ingenting: ingen melding.
  if (!reg || !Array.isArray(reg.alle_mannskap || reg.mannskap)) return false;
  return (reg.alle_mannskap || reg.mannskap).length === 0;
}


function tegnManglerMannskap() {
  document.getElementById('vl-mangler-mannskap')
    ?.classList.toggle('d-none', !registeretErTomt(register));
}


// ── Korpsvelgeren ────────────────────────────────────────────────────────

function _synligePoster(poster, korpsId) {
  // **Samme regel som serverens `poster_for_korps()`**: personene med
  // badgen, og de ledige plassene satt av til korpset — via plassen eller
  // ressursen, ferdig slått sammen i `reservert_korps_id`. Uten valg er
  // alt synlig.
  if (korpsId == null) return poster;
  // En ledig plass tildelt alle korps er hennes å fylle, altså hennes å se.
  return (poster || []).filter((vp) => (vp.ledig
    ? (vp.alle_korps || vp.reservert_korps_id === korpsId)
    : vp.korps_id === korpsId));
}


function _mittKorpsId() {
  // Korpset «Mitt korps» viser: korpsvelgeren for den som ser alle, badgen
  // for korps-brukeren. `null` når ingen av delene finnes — da er det ingen
  // fane å vise.
  if (korpsfilter != null) return korpsfilter;
  const mitt = globalThis.window?.MITT_KORPS_ID;
  return mitt == null ? null : mitt;
}


function brukKorpsfilter() {
  if (aktivListe && aktivListe.alle_vaktposter) {
    aktivListe.vaktposter = _synligePoster(aktivListe.alle_vaktposter, korpsfilter);
  }
  if (register && register.alle_mannskap) {
    register.mannskap = korpsfilter == null ? register.alle_mannskap
      : register.alle_mannskap.filter((m) => m.korps_id === korpsfilter);
  }
}


function fyllKorpsvelger() {
  const el = document.getElementById('vl-korpsvalg');
  if (!el) return;
  _fyll('vl-korpsvalg', (aktivListe.korps || []).map((k) => ({
    id: k.id, navn: k.kortnavn ? `${k.kortnavn} — ${k.navn}` : k.navn,
  })), 'Alle korps');
  // Valget overlever en ny lasting av lista; forsvant korpset, faller
  // velgeren tilbake til alle framfor å stå på et valg som ikke finnes.
  // Sjekket mot lista, ikke mot hva `<select>` gjør med en ukjent verdi —
  // det er regelen, og den skal kunne kjøres uten en nettleser.
  const finnes = (aktivListe.korps || []).some((k) => k.id === korpsfilter);
  if (!finnes) korpsfilter = null;
  el.value = korpsfilter == null ? '' : String(korpsfilter);
}


function velgUtskrift() {
  const el = document.getElementById('vl-utskriftsvalg');
  utskriftDag = el && el.value ? el.value : null;
  tegnPanel();
}


function _utvalgstekst() {
  // Det arket sier om seg selv: korpset og/eller dagen det er avgrenset til.
  // Tomt når det er hele vakten. Korpset er velgerens for den som ser alle,
  // badgen for korps-brukeren — samme regel som «Mitt korps».
  const deler = [];
  const korpsId = _mittKorpsId();
  if (korpsId != null) {
    const k = (aktivListe.korps || []).find((x) => x.id === korpsId);
    if (k) deler.push(k.navn);
  }
  if (utskriftDag != null) {
    // Teksten hentes fra en post på dagen, ikke av nøkkelen: `_dagtekst()`
    // er det ene stedet som formulerer «Fredag 4. sep», og to formuleringer
    // av samme dato ville før eller siden skrevet den ulikt.
    const vp = (aktivListe.vaktposter || []).find((x) => _dagnokkel(x.fra_tid) === utskriftDag);
    if (vp) deler.push(_dagtekst(vp.fra_tid));
  }
  return deler.join(' · ');
}


function _utskriftsdager() {
  // Dagene arket kan avgrenses til. **Én dag gir ingen valg** — da er «hele
  // vakten» og «den ene dagen» samme ark, og et nedtrekk med ett valg er en
  // kontroll som ikke gjør noe.
  const dager = _grupperPaaDag(aktivListe.vaktposter || []);
  return dager.length > 1 ? dager : [];
}


function mkUtskriftsverktoy() {
  // Velgeren og knappen over utskriftslista. Skjules på papiret
  // (`.vl-utskriftsverktoy` i @media print) — det som står der er utvalget,
  // og det står i arkhodet. Tegnes på nytt med panelet, så det valgte
  // merkes fra `utskriftDag`, ikke fra hva `<select>` husker.
  // **Dagene, ikke ressursene** (André, 15. sep. 2026): «vi beholder hele
  // vakten, men fjerner ressursene og bytter med dag. Går vakta én dag får du
  // ikke flere valg; går den over flere dager får du den enkelte dag.»
  const dager = _utskriftsdager();
  const valg = dager.map((dag) => {
    const merke = dag.nokkel === utskriftDag ? ' selected' : '';
    return `<option value="${escHtmlValue(dag.nokkel)}"${merke}>${escapeHtml(_dagtekst(dag.fra_tid))}</option>`;
  }).join('');
  // **Ingen velger på en endagsvakt.** Ett valg i et nedtrekk er en kontroll
  // som ikke gjør noe; knappen står igjen alene.
  const velger = dager.length ? `
      <label class="vl-meta mb-0" for="vl-utskriftsvalg">Vis</label>
      <select id="vl-utskriftsvalg" class="form-select form-select-sm w-auto"
              data-action="velgUtskrift" data-hendelse="change">
        <option value="">Hele vakten</option>${valg}
      </select>` : '';
  return `
    <div class="vl-utskriftsverktoy d-flex align-items-center gap-2 flex-wrap mb-2">${velger}
      <button type="button" class="btn btn-outline-secondary btn-sm" data-action="skrivUt">
        <i class="bi bi-printer me-1"></i>Skriv ut
      </button>
    </div>`;
}


function velgKorps() {
  const el = document.getElementById('vl-korpsvalg');
  const valgt = el && el.value ? Number(el.value) : null;
  korpsfilter = Number.isFinite(valgt) ? valgt : null;
  brukKorpsfilter();
  // Tallene regnes på serveren og må hentes på nytt for det valgte korpset;
  // fanen henter dem selv når den åpnes.
  belastning = null;
  if (aktivFane === BELASTNING) lastBelastning();
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
  _fyll('ny-vaktpost-korps', [{ id: 'alle', navn: 'Åpen for alle' }].concat(
    (aktivListe.korps || []).map((k) => ({
      id: k.id, navn: k.kortnavn || k.navn,
    }))), '— som ressursen —');

  // Rollenedtrekket i «Sett på vakt» fylles når vinduet åpnes: det som
  // tilbys avhenger av hvilken ressurs man står på, altså av gruppa.
}
