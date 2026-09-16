// ════════════════════════════════════════════════════════
// Sentralbordet i oppdragsmodulen (/oppdrag/).
//
// Laster KUN portal-utils.js. `patients-utils.js` gjør arbeid på toppnivå —
// Chart.defaults og `new bootstrap.Modal(...)` mot pasientskjemaene — og
// kaster på en side uten dem. Trengs en helper derfra, skal den flyttes til
// portal-utils.js, ikke kopieres. JsModulLastingTests håndhever det.
//
// All brukerdata som settes inn med innerHTML escapes: fritekst og
// lokasjonsnavn er de første virkelig frie feltene i portalen som ikke er en
// nedtrekksliste.
// ════════════════════════════════════════════════════════

let enheter = [];
let lokasjoner = [];
let oppdragsliste = [];
let enhetsadmin = [];

// ETag-verdiene fra forrige poll. Serveren svarer 304 når ingenting er
// endret, og da rendrer vi ikke på nytt — under en rolig time er trafikken
// nær null selv med mange pålogget.
let etagEnheter = null;
let etagOppdrag = null;
//: Om første henting har lykkes. Til da viser listene «kunne ikke hente»,
//: ikke «ingen enheter på vakt» — tom og ikke hentet er to ulike ting
//: (André, 13. sep. 2026: plassholderne sto tomme ved første besøk).
let enheterHentet = false;
let oppdragHentet = false;

// **Besetningen er vaktlistas data, lånt inn** (§6 i vaktlistenotatet).
// Oppdragsmodulen importerer ikke vaktlista i Python — koblingen ligger her,
// i nettleseren, som `Ressurs.enhet` peker sammen.
//
// Hentes **når operatøren spør**, ikke ved hver polling: enhetslista pollet
// hvert par sekund ville gitt ett kall per bil per runde, og svaret er
// dessuten bare interessant i det øyeblikket noen lurer.
let besetninger = {};
let apenBesetning = null;

const STATUS_REKKEFOLGE = ['venter', 'rykker_ut', 'fremme', 'avreist', 'leverer', 'ledig'];
//: Lista sorteres på hastegraden operatøren satte (André, 12. sep. 2026),
//: og innenfor den på nummer. Ferdige oppdrag står nederst.
const HASTEGRAD_REKKEFOLGE = ['Akutt', 'Haster', 'Vanlig', 'Drift'];
//: «Trenger ny ressurs» blir tydeligere jo lenger det står (minutter).
const MANGLER_TRINN = [[15, 'alvorlig'], [5, 'varsel'], [0, 'ny']];


function hastegradKlasse(h) {
  return 'hastegrad-' + (h || '').toLowerCase();
}


function _problemMedAntall(o) {
  // «Transport · 3 pasienter» — antallet bilen satte står ved
  // problemstillingen der den bærer et. Tomt betyr én (André, 12. sep.
  // 2026: «hvis den er blank så må det stå 1 pasient»).
  const p = o.problemstilling || '';
  if (!_medAntall(p)) return p;
  const n = o.antall == null ? 1 : Number(o.antall);
  return `${p} · ${n} ${n === 1 ? 'pasient' : 'pasienter'}`;
}


function _medAntall(problemstilling) {
  return (globalThis.window?.OPPDRAG_MED_ANTALL || []).includes(problemstilling);
}


function problemstillingerFor(hastegrad) {
  const kart = globalThis.window?.OPPDRAG_PROBLEMSTILLINGER_FOR || {};
  return kart[hastegrad] || [];
}


function fyllProblemstillinger(prefiks, hastegrad, valgt) {
  // Nedtrekket bygges om av hastegraden (André, 12. sep. 2026: «teknisk [nå Drift]
  // hastegrad endrer innholdet i problemstillinger»). Står den valgte ikke
  // i den nye lista, velges den første — «Udefinert». Antallet settes av
  // bilen, ikke her (12. sep. 2026).
  const sel = document.getElementById(`${prefiks}-problemstilling`);
  if (!sel) return;
  const liste = problemstillingerFor(hastegrad);
  const ny = liste.includes(valgt) ? valgt : (liste[0] || '');
  sel.innerHTML = liste.map((p) =>
    `<option value="${escHtmlValue(p)}"${p === ny ? ' selected' : ''}>${escapeHtml(p)}</option>`).join('');
}


function hastegradEndret(prefiks) {
  const h = document.getElementById(`${prefiks}-hastegrad`)?.value || '';
  const valgt = document.getElementById(`${prefiks}-problemstilling`)?.value || '';
  fyllProblemstillinger(prefiks, h, valgt);
}




function _grovMerke(o) {
  // Bilens Rød/Gul/Grønn som merke; «—» når bilen ikke har vurdert ennå.
  // `grovsortering` er nøkkelen (rod/gul/gronn) og styrer fargen;
  // `grovsortering_navn` er teksten.
  // Drift har ingen pasient å sortere (12. sep. 2026): ingen merke.
  if (o.hastegrad === 'Drift') return '';
  if (!o.grovsortering) {
    return '<span class="grov-merke grov-tom" title="Bilen har ikke grovsortert ennå">Bil: —</span>';
  }
  return `<span class="grov-merke grov-${escHtmlValue(o.grovsortering)}">Bil: ${escapeHtml(o.grovsortering_navn || o.grovsortering)}</span>`;
}


function tidSiden(iso, naa) {
  // «12 min», «1 t 05 min» — hvor lenge siden et tidspunkt. Prosjektleder,
  // 11. sep. 2026: «tidspunkt siden oppdrag». Klokkeslettet står der alt;
  // dette er tallet man ellers regner ut i hodet, og det er det som sier om
  // bilen har stått lenge i Fremme. Under et minutt er «nå», ikke «0 min».
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const min = Math.floor(((naa ?? Date.now()) - t) / 60000);
  if (min < 1) return 'nå';
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const rest = min % 60;
  return `${h} t ${String(rest).padStart(2, '0')} min`;
}

// ════════════════════════════════════════════════════════
// oppdrag-sentral-kjerne.js
// ════════════════════════════════════════════════════════
//
// Tilstand, polling og enhetslista.
//
// **Denne fila må lastes først.** All toppnivå-tilstand står her, og
// `let`/`const` på toppnivå er skript-scopede: en fil som leser dem før
// denne er kjørt, treffer en temporal dead zone.
//
// Delt ut av `oppdrag-sentral.js` 14. sep. 2026 (gjeldspunkt 3.6).
// Fila var 1 991 linjer. Ingen bundler: filene lastes i rekkefølge fra
// `templates/oppdrag/sentral.html` og deler ett globalt navnerom som
// før. `JsSplittenErKompletTests` håndhever at ingen funksjon forsvant
// eller ble duplisert.
// ════════════════════════════════════════════════════════

// ── Enhetsliste ─────────────────────────────────────────

function renderEnheter() {
  const el = document.getElementById('enhetsliste');
  if (!el) return;

  // Tavla viser hvem som kan sendes nå. Antallet av vakt står på
  // Enheter-knappen, der hele lista ligger.
  const paVakt = enheter.filter((e) => e.pa_vakt);
  const antallAv = enheter.length - paVakt.length;

  if (!paVakt.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter på vakt.</div>';
  } else {
    // Gruppert på enhetstype, ambulansene først (André, 12. sep. 2026).
    // Overskriften står bare når det finnes mer enn én type å skille.
    const grupper = _grupperEnheter(paVakt);
    el.innerHTML = grupper.map((g) => {
      const hode = grupper.length > 1
        ? `<div class="enhet-gruppe">${escapeHtml(g.navn)}</div>` : '';
      return hode + g.enheter.map((e) => _enhetskort(e)).join('');
    }).join('');
  }

  const teller = document.getElementById('av-vakt-teller');
  if (teller) teller.textContent = antallAv ? ` (${antallAv} av vakt)` : '';
}


function _typeRekkefolge() {
  // Typenes ID-er i visningsrekkefølge — tabellen `Enhetstype`, sortert av
  // serveren (12. sep. 2026). `OPPDRAG_ENHETSTYPER` er `[[id, navn], …]`.
  return (globalThis.window?.OPPDRAG_ENHETSTYPER || []).map((t) => String(t[0]));
}


function _grupperEnheter(liste) {
  // [{type, navn, enheter}] i typenes rekkefølge — ambulanse først — og
  // bare typene som faktisk finnes i lista. Enheter uten type, eller med en
  // type som er tatt ut av lista, står sist. Innenfor gruppa alfabetisk
  // (André, 12. sep. 2026). Én regel, to lesere: tavla og avkryssingen i
  // «Nytt oppdrag».
  const rekkefolge = _typeRekkefolge();
  const navn = Object.fromEntries(
    (globalThis.window?.OPPDRAG_ENHETSTYPER || []).map(([id, n]) => [String(id), n]));
  const grupper = new Map();
  liste.forEach((e) => {
    const t = e.type == null ? '' : String(e.type);
    if (!grupper.has(t)) grupper.set(t, []);
    grupper.get(t).push(e);
  });
  const alfabetisk = (a, b) => String(a.navn).localeCompare(String(b.navn), 'nb', { sensitivity: 'base' });
  return Array.from(grupper.entries())
    .sort((a, b) => {
      const ai = rekkefolge.indexOf(a[0]); const bi = rekkefolge.indexOf(b[0]);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    })
    .map(([type, enheter]) => ({
      type,
      navn: navn[type] || (type === '' ? 'Uten type' : (enheter[0].type_navn || 'Annet')),
      enheter: [...enheter].sort(alfabetisk),
    }));
}


function _enhetskort(e) {
      // «Ledig (2 venter)» er distinksjonen 113 trenger: enheten har fått
      // oppdrag, men ikke rykket ut, og kan fortsatt sendes.
      // Statusen med klokkeslett og tid siden: «Fremme 14:32 · 12 min».
      // Prosjektleder, 11. sep. 2026 — «på statusen så må tidsstemplet og
      // vise». Ledig har ingen melding bak seg, så der står bare ordet.
      // **«Ledig siden» fyller tomrommet** (André, 15. sep. 2026): en ledig
      // enhet har ingen aktiv koblingsrad, så `status_tidspunkt` er tomt og
      // statusen sto som et ord uten tid. Operatøren som skal sende noen vil
      // vite hvem som har stått lengst. Samme form som de andre statusene,
      // klokkeslett og tid siden — to måter å vise «siden når» er én for mye.
      const siden = e.status_tidspunkt || e.ledig_siden;
      const statusTid = siden ? ` ${klokke(siden)} · ${tidSiden(siden)}` : '';
      // «Avreist → Sykehus» — hvor bilen dro skal synes her også.
      const sted = e.sted_navn ? ` → ${e.sted_navn}` : '';
      const meta = e.antall_ventende
        ? `${e.status_navn}${sted}${statusTid} · ${e.antall_ventende} venter`
        : `${e.status_navn}${sted}${statusTid}`;
      // Det aktive oppdraget i ett blikk: nummer, hastegrad, problemstilling.
      // Hoistet ut av mal-strengen, som resten.
      const grov = e.oppdragsnummer != null ? _grovMerke(e) : '';
      const oppdragslinje = e.oppdragsnummer != null
        ? `<div class="enhet-oppdrag">
             <span class="oppdrag-nr">#${escHtmlValue(e.oppdragsnummer)}</span>
             <span class="hastegrad ${escHtmlValue(hastegradKlasse(e.hastegrad))}">${escapeHtml(e.hastegrad || '')}</span>
             ${grov}
             <span class="enhet-oppdrag-problem">${escapeHtml(_problemMedAntall(e))}</span>
           </div>`
        : '';
      // Hoistet ut av mal-strengen: en nøstet mal-streng inne i en `${...}`
      // er usynlig for XSS-skanneren i tests_xss.py, og vanskelig å lese.
      const klikkbar = kanSeBesetning() ? ' enhet-kort-klikkbar' : '';
      const apner = kanSeBesetning()
        ? `data-action="visBesetning" data-id="${escHtmlValue(e.id)}"` : '';
      const besetning = mkBesetning(e.id);
      // **Passiv-merket vises bare der det betyr noe** (André, 16. sep.
      // 2026): enhetstypen må tillate passiv vakt. «Aktiv» skrives ikke —
      // det er normaltilstanden, og et merke på hver ambulanse er støy.
      // Merket er dempet, ikke en advarsel: enheten *er* på vakt, hun sover.
      // **En streng, ikke `trustedHtml(...)`.** Den pakker verdien i
      // `{__trustedHtml: …}` for `cellHtml()` i en Tabulator-celle; i en
      // mal-streng blir objektet til «[object Object]» — på *hvert* kort, for
      // `trustedHtml('')` er et objekt like fullt. Meldt fra staging 16. sep.
      // 2026. Samme felle tok «Rett tid» 11. sep.; `tests_xss.py` håndhever
      // den nå for alle filene, i stedet for én kommentar per kallsted.
      const passiv = (e.kan_passiv_vakt && e.passiv_vakt)
        ? '<span class="enhet-passivmerke">passiv vakt</span>' : '';
      return `
      <div class="enhet-kort${klikkbar}" ${apner}>
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <div class="flex-grow-1">
          <div class="enhet-navn">${escapeHtml(e.navn)}${passiv}</div>
          <div class="enhet-meta">${escapeHtml(meta)}</div>
          ${oppdragslinje}
        </div>
      </div>${besetning}`;
}


function kanSeBesetning() {
  // Speiler `har_tilgang(bruker, 'vaktliste', 'les')`, satt av malen.
  // **Komposisjonsregelen fra rollemodellen §5:** en modul viser bare kilder
  // brukeren har tilgang til, framfor å gi avledet innsyn. Serveren nekter
  // uansett — dette avgjør bare om panelet finnes.
  return globalThis.window?.KAN_SE_BESETNING === true;
}


function mkBesetning(enhetId) {
  // Panelet ligger *under* enhetskortet, ikke inni: kortet er en linje 113
  // skummer, og en besetning på fire ville sprengt den.
  if (apenBesetning !== enhetId) return '';
  const b = besetninger[enhetId];
  if (b === undefined) {
    return '<div class="besetning"><span class="enhet-meta">Henter…</span></div>';
  }
  if (b.feil) {
    // **Serverens forklaring, ikke vår egen.** Den vanligste grunnen til at
    // en besetning ikke finnes er at bilen er koblet i en vakt man har
    // *planlagt*, mens sentralbordet står i den aktive — og da er ikke
    // oppsettet feil, det er feil vakt som er aktiv. Skrev vi vår egen
    // generiske «ikke koblet» her, sendte vi operatøren ut på jakt etter en
    // feil som ikke finnes.
    return `<div class="besetning"><span class="enhet-meta">${escapeHtml(b.feil)}</span></div>`;
  }
  if (!b.mannskap.length) {
    // Neste skift når ingen dekker nå: «ingen» alene sa ikke om bilen var
    // ubemannet eller bare ikke begynt ennå (André, 12. sep. 2026).
    const neste = (b.neste || []).length
      ? ` Neste skift ${escapeHtml(klokke(b.neste_fra))}: `
        + escapeHtml(b.neste.map((m) => m.navn).join(', ')) + '.'
      : '';
    return `<div class="besetning"><span class="enhet-meta">`
         + `Ingen på vakt på ${escapeHtml(b.ressurs_navn)} nå.${neste}</span></div>`;
  }

  const rader = b.mannskap.map((m) => {
    // Tre tilstander, ikke to: «møtt» og «av vakt» er begge stemplet, men
    // bare den ene er til stede nå.
    const merke = m.tilstede
      ? '<span class="besetning-inne" title="Møtt">●</span>'
      : (m.mott
          ? '<span class="besetning-ute" title="Av vakt">○</span>'
          : '<span class="besetning-ute" title="Ikke møtt">○</span>');
    const rolle = m.rolle
      ? `<span class="enhet-meta">${escapeHtml(m.rolle)}</span>` : '';
    // Telefon og ISSI (André, 12. sep. 2026): operatøren skal kunne ringe
    // bilen uten å åpne vaktlista. Telefonen er en `tel:`-lenke, ISSI ren
    // tekst — nødnettet ringes fra terminalen, ikke fra nettleseren.
    const kontakt = _besetningKontakt(m);
    return `<div class="besetning-rad">${merke}
              <span>${escapeHtml(m.navn)}</span>${rolle}${kontakt}</div>`;
  }).join('');

  const status = b.i_drift
    ? `${escHtmlValue(b.tilstede)} av ${escHtmlValue(b.antall)} møtt`
    : `${escHtmlValue(b.antall)} satt opp · innsjekk ikke åpnet`;

  return `<div class="besetning">
      <div class="besetning-topp">
        <span>${escapeHtml(b.ressurs_navn)}</span>
        <span class="enhet-meta">${status}</span>
      </div>
      ${rader}
    </div>`;
}


function _besetningKontakt(m) {
  const deler = [];
  if (m.telefon) {
    const tlf = String(m.telefon);
    deler.push(`<a class="besetning-tlf" href="tel:${escHtmlValue(tlf.replace(/\s+/g, ''))}">`
             + `<i class="bi bi-telephone"></i> ${escapeHtml(tlf)}</a>`);
  }
  if (m.issi) {
    deler.push(`<span class="besetning-issi" title="ISSI (nødnett)">`
             + `<i class="bi bi-broadcast"></i> ${escapeHtml(m.issi)}</span>`);
  }
  return deler.length ? `<span class="besetning-kontakt">${deler.join('')}</span>` : '';
}


async function visBesetning(enhetId) {
  if (apenBesetning === enhetId) { apenBesetning = null; renderEnheter(); return; }
  apenBesetning = enhetId;
  renderEnheter();
  await hentBesetning(enhetId);
}


async function hentBesetning(enhetId) {
  const res = await apiFetch(`/vaktliste/api/enhet/${enhetId}/besetning/`);
  const d = await res.json().catch(() => ({}));
  // Serveren skiller mellom «koblet i en annen vakt» og «ikke koblet noe
  // sted», og meldingen bæres uendret hit — se `mkBesetning`.
  besetninger[enhetId] = res.ok
    ? d.data
    : { feil: d.message || 'Kunne ikke hente besetningen.' };
  renderEnheter();
}


async function _settVakt(id, paVakt) {
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/vakt/`, {
    method: 'POST',
    body: JSON.stringify({ pa_vakt: paVakt }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke endre vaktstatus.');
    return;
  }
  etagEnheter = null;   // tving ny henting, ellers svarer serveren 304
  await lastAlt();
  if (document.getElementById('enhetsadminliste')) await lastEnhetsadmin();
}

async function taAvVakt(id) { await _settVakt(id, false); }
async function settPaaVakt(id) { await _settVakt(id, true); }


async function _settVaktmodus(id, passiv) {
  // **Passiv er ikke «av vakt»** (André, 16. sep. 2026), og derfor et eget
  // endepunkt: «kan ikke få nye oppdrag» er noe helt annet enn «ligger og
  // sover, men kommer».
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/vaktmodus/`, {
    method: 'POST',
    body: JSON.stringify({ passiv }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke endre vaktmodus.');
    return;
  }
  etagEnheter = null;   // tving ny henting, ellers svarer serveren 304
  await lastAlt();
}

async function settPassivVakt(id) { await _settVaktmodus(id, true); }
async function settAktivVakt(id) { await _settVaktmodus(id, false); }


async function avventOppdrag(arg) {
  // `arg` er «<oppdrag>:<enhet>» — klikkdelegeringen sender ett argument.
  const [oppdragId, enhetId] = String(arg).split(':');
  const res = await apiFetch(
    `/oppdrag/api/oppdrag/${oppdragId}/avvent/${enhetId}/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke sette avventer.');
    return;
  }
  etagOppdrag = null;
  await lastAlt();
}


async function kvitterAvbrutt(oppdragId) {
  // Den andre veien — å sende en ny enhet — kvitterer av seg selv på
  // serveren. Denne finnes for tilfellet der ingen skal sendes.
  const res = await apiFetch(
    `/oppdrag/api/oppdrag/${oppdragId}/kvitter-avbrutt/`, { method: 'POST' });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke kvittere.');
    return;
  }
  etagOppdrag = null;
  await lastAlt();
}
