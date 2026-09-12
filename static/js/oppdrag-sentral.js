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
      const statusTid = e.status_tidspunkt
        ? ` ${klokke(e.status_tidspunkt)} · ${tidSiden(e.status_tidspunkt)}` : '';
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
      return `
      <div class="enhet-kort${klikkbar}" ${apner}>
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <div class="flex-grow-1">
          <div class="enhet-navn">${escapeHtml(e.navn)}</div>
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


// ── Oppdragsliste ───────────────────────────────────────

function renderOppdrag() {
  const el = document.getElementById('oppdragsliste');
  if (!el) return;

  if (!oppdragsliste.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen oppdrag i vakten ennå.</div>');
    return;
  }

  const sortert = _sorterOppdrag(oppdragsliste);

  el.innerHTML = (sortert.map((o) => {
    // Fragmentene bygges før mal-strengen, ikke inne i en ${...}. En nøstet
    // mal-streng inne i en interpolasjon er vanskelig å lese — og XSS-vernet
    // i tests_xss.py klarer ikke å se inn i den, så en uescapet verdi der
    // ville passert stille.
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    // «Fremme · 12 min» og «14:20 · 31 min siden» — ren tekst, escapet ved
    // innsetting. Uten statusmelding (venter) står bare ordet.
    const statusTekst = o.status_tidspunkt
      ? `${o.status_navn} · ${tidSiden(o.status_tidspunkt)}`
      : String(o.status_navn);
    const opprettetTekst = `${klokke(o.opprettet)} · ${tidSiden(o.opprettet)} siden`;
    // To vurderinger, to plasser: KO/AMKs hastegrad til venstre, bilens
    // grovsortering til høyre. Tom grovsortering vises som «—», fordi
    // «ikke vurdert ennå» er informasjon.
    const grovsortering = _grovMerke(o);
    const manglerKlasse = o.trenger_ressurs ? ' oppdrag-rad-mangler mangler-' + _manglerTrinn(o) : '';
    const venterKlasse = venterForbiTerskel(o) ? ' oppdrag-rad-venter-lenge' : '';
    return `
    <div class="oppdrag-rad${manglerKlasse}${venterKlasse}" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">#${escHtmlValue(o.nummer)}</span>
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        ${grovsortering}
        <span class="oppdrag-problem">${escapeHtml(_problemMedAntall(o))}</span>
        <span class="ms-auto d-flex align-items-center gap-1">
          <span class="status-prikk status-${escHtmlValue(o.status)}"></span>
          <span class="oppdrag-meta">${escapeHtml(statusTekst)}</span>
        </span>
      </div>
      <div class="enhetsmatrise mt-1">${_enhetsmatrise(o)}</div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(o.lokasjon_navn)} · ${escapeHtml(opprettetTekst)}
      </div>
      ${fritekstBlokk}
    </div>`;
  }).join(''));
}


function _sorterOppdrag(liste) {
  // Ferdige nederst; ellers hastegraden KO/AMK satte, og innenfor den
  // nummeret — «Akutt #3» over «Akutt #7», og alle Akutt over alle Haster.
  // Statusen sorterer ikke lenger: det er hastegraden som sier hva som er
  // viktigst, og nummeret som sier hva som kom først.
  const rang = (h) => {
    const i = HASTEGRAD_REKKEFOLGE.indexOf(h);
    return i < 0 ? HASTEGRAD_REKKEFOLGE.length : i;
  };
  return [...liste].sort((a, b) => {
    const af = a.status === 'ledig' ? 1 : 0;
    const bf = b.status === 'ledig' ? 1 : 0;
    if (af !== bf) return af - bf;
    const ah = rang(a.hastegrad);
    const bh = rang(b.hastegrad);
    if (ah !== bh) return ah - bh;
    return (Number(a.nummer) || 0) - (Number(b.nummer) || 0);
  });
}


function lydTerskler() {
  // Samme tabell som bilen leser (`OPPDRAG_LYDVARSEL`); fallet tilbake er
  // første utgaves tall. Som funksjon — se `koNokkel()` i enhetsskjermen.
  const fra = globalThis.window?.OPPDRAG_LYDVARSEL;
  if (fra && typeof fra === 'object' && Object.keys(fra).length) return fra;
  return { Akutt: [60, 10], Haster: [300, 60], Vanlig: [900, 60], Drift: [900, 60] };
}


function venterForbiTerskel(o, naaMs) {
  // Utheving hos operatør (André, 12. sep. 2026): et oppdrag som venter på
  // at en bil skal trykke Rykker ut, forbi første lydterskel for
  // hastegraden. Tida regnes fra da den *første* ventende bilen ble varslet;
  // et oppdrag uten bil («trenger ny ressurs») har sin egen utheving.
  if (o.status !== 'venter' || o.trenger_ressurs) return false;
  const ventende = (o.enheter || []).filter((e) => e.status === 'venter' && e.varslet_at);
  if (!ventende.length) return false;
  const tidligst = Math.min(...ventende.map((e) => new Date(e.varslet_at).getTime()));
  const alle = lydTerskler();
  const [forste] = alle[o.hastegrad] || alle.Vanlig || [900];
  return ((naaMs || Date.now()) - tidligst) / 1000 >= forste;
}


function _manglerMinutter(o, naa) {
  // Fra bilen rykket videre — `trenger_ressurs_siden`. Eldre svar uten
  // feltet regner fra siste status.
  const fra = o.trenger_ressurs_siden || o.status_tidspunkt || o.opprettet;
  if (!fra) return 0;
  const ms = (naa ? new Date(naa) : new Date()) - new Date(fra);
  return Math.max(0, Math.floor(ms / 60000));
}


function _manglerTrinn(o, naa) {
  // Trinnene er visuelle, ikke regler: raden skal skille seg mer ut jo
  // lenger oppdraget har stått uten noen (André, 12. sep. 2026: «gjerne som
  // blir tydeligere desto lenger tiden går»).
  const min = _manglerMinutter(o, naa);
  return (MANGLER_TRINN.find(([grense]) => min >= grense) || [0, 'ny'])[1];
}


function _enhetsmatrise(o) {
  // Én brikke per enhet: navn, status og tid siden — matrisen fra §4 i
  // notatet om flere enheter. Oppdragets egen status står fortsatt til
  // høyre i raden; den er utledet av disse. Uten `enheter` (eldre svar)
  // er det én brikke av toppnivåfeltene.
  const rader = (o.enheter && o.enheter.length) ? o.enheter : [{
    enhet_navn: o.enhet_navn, status: o.status, status_navn: o.status_navn,
    status_tidspunkt: o.status_tidspunkt,
  }];
  // Bilen rykket videre og ingen har tatt over (André, 12. sep. 2026):
  // merket står først, så det er det første 113 ser på raden — med egen
  // trekant, ikke statusprikken bilene har, og med tida det har stått.
  // Bilene som er ferdige med det står i loggen, ikke i lista: «den bilen
  // må vekk» — ellers ser oppdraget bemannet ut.
  const mangler = o.trenger_ressurs
    ? `<span class="enhet-brikke enhet-brikke-mangler mangler-${escHtmlValue(_manglerTrinn(o))}">
      <i class="bi bi-exclamation-triangle-fill"></i>
      <span>Trenger ny ressurs · ${escHtmlValue(_manglerMinutter(o))} min</span>
    </span>` : '';
  const synlige = o.trenger_ressurs ? rader.filter((e) => e.status !== 'ledig') : rader;
  return mangler + synlige.map((e) => {
    const statusTid = e.status_tidspunkt ? ` · ${tidSiden(e.status_tidspunkt)}` : '';
    const sted = e.sted_navn ? ` → ${e.sted_navn}` : '';
    const meta = `${e.status_navn}${sted}${statusTid}`;
    return `<span class="enhet-brikke">
      <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
      <span>${escapeHtml(e.enhet_navn)}</span>
      <span class="oppdrag-meta">${escapeHtml(meta)}</span>
    </span>`;
  }).join('');
}


// ── Detaljvisning ───────────────────────────────────────

function tidslinjeHtml(data) {
  // Unionen av statusmeldinger og enhetsbytter. De to er skilt i databasen
  // fordi et bytte ikke er en status og statistikken måler statusene; å slå
  // dem sammen her er en visningsjobb.
  const rader = [];

  const erstattet = new Set(
    (data.historikk || []).filter((m) => m.korrigerer).map((m) => m.korrigerer));
  const flere = (data.enheter || []).length > 1;
  // Siste gjeldende melding per enhet — den eneste som kan angres.
  const sisteFor = new Map();
  (data.historikk || []).forEach((m) => {
    if (erstattet.has(m.id)) return;
    const s = sisteFor.get(m.enhet_id);
    if (!s || m.tidspunkt > s.tid || (m.tidspunkt === s.tid && m.id > s.id)) {
      sisteFor.set(m.enhet_id, { id: m.id, tid: m.tidspunkt });
    }
  });
  sisteFor.forEach((v, k) => sisteFor.set(k, v.id));

  // Hvem som ble varslet, og hvem som ble tatt av (André, 12. sep. 2026).
  (data.enheter || []).forEach((e) => {
    if (!e.varslet_at) return;
    rader.push({
      tid: e.varslet_at,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(e.varslet_at))}</span>
          <span>Varslet: ${escapeHtml(e.enhet_navn)}</span>
        </div>`,
    });
  });
  (data.enhetshendelser || []).forEach((h) => {
    // «Rykket videre til #12: HGSD 56» — bilen dro til et annet oppdrag, og
    // dette trenger en ny ressurs. Ellers «Tatt av».
    const tekst = h.type === 'rykket_videre'
      ? 'Rykket videre' + (h.detalj ? ' til ' + h.detalj : '') + ': ' + h.enhet_navn
      : (h.type === 'avbrutt' ? 'Avbrutt: ' + h.enhet_navn : 'Tatt av: ' + h.enhet_navn);
    rader.push({
      tid: h.tidspunkt,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(h.tidspunkt))}</span>
          <span>${escapeHtml(tekst)}</span>
          <span class="tidslinje-notat">· ${escapeHtml(h.av)}</span>
        </div>`,
    });
  });

  (data.historikk || []).forEach((m) => {
    // Markøren for et avledet tidspunkt sitter på KLOKKESLETTET, ikke på
    // statusordet: det er tidspunktet som er utledet, ikke at oppdraget ble
    // ledig. Ingen badge — den ville konkurrert med statusen.
    const tidKlasse = m.automatisk ? 'tidslinje-tid tid-avledet' : 'tidslinje-tid';
    const tittel = m.automatisk
      ? ' title="Avsluttet automatisk da enheten startet neste oppdrag"'
      : '';
    const notat = [];
    if (m.automatisk) notat.push('avsluttet automatisk');
    if (m.forsinket) notat.push('meldt forsinket');
    if (m.korrigerer) notat.push('rettet av sentralen');
    // §9: sentralbordet førte statusen — og hvem, for det er ikke bilen.
    if (m.manuell) notat.push('endret av KO' + (m.meldt_av ? ` (${m.meldt_av})` : ''));
    const erErstattet = erstattet.has(m.id);
    const klasse = erErstattet ? 'tidslinje-rad tidslinje-erstattet' : 'tidslinje-rad';
    const notatBlokk = notat.length
      ? `<span class="tidslinje-notat">· ${escapeHtml(notat.join(', '))}</span>`
      : '';
    // Kun gjeldende rader kan rettes. En overstyrt rad beskriver ikke lenger
    // noe som gjelder, og serveren avviser den uansett — knappen skal ikke
    // tilby noe som er stengt.
    const rettKnapp = (OPPDRAG_TILGANG.kanSkrive && !erErstattet)
      ? `<button type="button" class="btn btn-link btn-sm tidslinje-rett p-0 ms-2"
                 data-action="visRettTid" data-id="${escHtmlValue(m.id)}">Rett tid</button>`
      : '';
    // «Angre» på enhetens siste gjeldende melding (André, 12. sep. 2026):
    // tar statusen tilbake til forrige, som en korreksjon.
    const angreKnapp = (OPPDRAG_TILGANG.kanSkrive && !erErstattet && sisteFor.get(m.enhet_id) === m.id)
      ? `<button type="button" class="btn btn-link btn-sm tidslinje-rett p-0 ms-2"
                 data-action="angreStatus" data-id="${escHtmlValue(m.enhet_id)}">Angre</button>`
      : '';
    // «Avreist → Sykehus» — stedet ved statusen, som på enhetsskjermen.
    // Og med flere enheter: hvem sin — «KARM 12: Fremme». Med én står
    // navnet alt i tittelen.
    const hvem = (flere && m.enhet_navn) ? m.enhet_navn + ': ' : '';
    const statusMedSted = hvem + (m.sted_navn ? `${m.status_navn} → ${m.sted_navn}` : String(m.status_navn));
    rader.push({
      tid: m.tidspunkt,
      html: `
        <div class="${klasse}" id="tidslinje-rad-${escHtmlValue(m.id)}">
          <span class="${tidKlasse}"${tittel}>${escapeHtml(klokke(m.tidspunkt))}</span>
          <span>${escapeHtml(statusMedSted)}</span>
          ${notatBlokk}
          ${rettKnapp}${angreKnapp}
        </div>`,
    });
  });

  // Opprettelsen er første hendelse (André, 12. sep. 2026). Den har ingen
  // «Rett tid»: den er ikke et stempel, og ingen melding kan rettes til før
  // den — serveren stopper det uansett.
  if (data.opprettet) {
    rader.push({
      tid: data.opprettet,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(data.opprettet))}</span>
          <span>Oppdrag opprettet</span>
        </div>`,
    });
  }

  (data.enhetsbytter || []).forEach((b) => {
    rader.push({
      tid: b.tidspunkt,
      html: `
        <div class="tidslinje-rad">
          <span class="tidslinje-tid">${escapeHtml(klokke(b.tidspunkt))}</span>
          <span>Flyttet ${escapeHtml(b.fra_enhet)} → ${escapeHtml(b.til_enhet)}</span>
          <span class="tidslinje-notat">· ${escapeHtml(b.byttet_av)}</span>
        </div>`,
    });
  });

  rader.sort((a, b) => new Date(a.tid) - new Date(b.tid));
  if (!rader.length) return '<div class="tom-melding">Ingen hendelser ennå.</div>';
  return rader.map((r) => r.html).join('');
}


async function visOppdrag(id) {
  apentOppdragId = id;
  const modalEl = document.getElementById('oppdragDetaljModal');
  const innhold = document.getElementById('detalj-innhold');
  innhold.innerHTML = ('<div class="tom-melding">Laster…</div>');
  bootstrap.Modal.getOrCreateInstance(modalEl).show();

  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/`);
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    innhold.innerHTML = (
      `<div class="text-danger">${escapeHtml(d.message || 'Kunne ikke hente oppdraget.')}</div>`);
    return;
  }

  const o = d.data;
  apentOppdrag = o;
  const navn = (o.enheter || []).map((e) => e.enhet_navn).join(', ') || o.enhet_navn;
  document.getElementById('detalj-tittel').textContent =
    `#${o.nummer} ${o.problemstilling} – ${navn}`;
  const enheterFeil = document.getElementById('enheter-feil');
  if (enheterFeil) enheterFeil.classList.add('d-none');
  innhold.classList.remove('foer-aapen');

  // Ferdigstilte oppdrag går til historikken av seg selv i `sett_status`, så
  // knappen her er for hånd-tilfellene: hent tilbake til tavla, og rydd bort
  // igjen etterpå. Vises bare når den kan brukes — et pågående oppdrag skal
  // ikke kunne ryddes bort, og en knapp som alltid feiler er verre enn ingen.
  const historikkKnapp = (OPPDRAG_TILGANG.kanSkrive && o.status === 'ledig')
    ? (o.historikk_fra
      ? `<button class="btn btn-outline-secondary btn-sm" type="button"
                 data-action="hentTilbakeOppdrag" data-id="${escHtmlValue(o.id)}">
           Hent tilbake til tavla</button>`
      : `<button class="btn btn-outline-secondary btn-sm" type="button"
                 data-action="flyttTilHistorikk" data-id="${escHtmlValue(o.id)}">
           <i class="bi bi-clock-history me-1"></i>Legg i historikk</button>`)
    : '';

  // Med flere enheter er «flytt» flytt av én rad — hvilken, spørres om.
  const flyttFra = (o.enheter || []).length > 1
    ? `<select id="flytt-fra" class="form-select" aria-label="Flytt fra">
        ${(o.enheter || []).map((e) => `<option value="${escHtmlValue(e.enhet_id)}">${escapeHtml(e.enhet_navn)}</option>`).join('')}
       </select><span class="input-group-text">→</span>`
    : '';
  const flyttValg = OPPDRAG_TILGANG.kanSkrive
    ? `
      <hr>
      <label class="form-label" for="flytt-enhet">Flytt til enhet</label>
      <div class="input-group">
        ${flyttFra}
        <select id="flytt-enhet" class="form-select">
          ${enheter.map((e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('')}
        </select>
        <button class="btn btn-outline-primary" type="button"
                data-action="flyttOppdrag" data-id="${escHtmlValue(o.id)}">Flytt</button>
      </div>
      <div id="flytt-feil" class="text-danger small mt-2 d-none"></div>`
    : '';

  const redigerKnapp = OPPDRAG_TILGANG.kanSkrive
    ? `<button type="button" class="btn btn-link btn-sm p-0 ms-2" data-action="visRedigerOppdrag">Rediger</button>`
    : '';
  const slettKnapp = o.kan_slettes
    ? `<button type="button" class="btn btn-outline-danger btn-sm" data-action="slettOppdrag"
               data-id="${escHtmlValue(o.id)}"><i class="bi bi-trash me-1"></i>Slett oppdrag</button>`
    : '';
  innhold.innerHTML = (`
    <div class="oppdrag-meta mb-2">
      <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
      <span class="ms-2">${escapeHtml(o.lokasjon_navn)}</span>
      <span class="ms-2">${escapeHtml(o.status_navn)}</span>
      ${redigerKnapp}
    </div>
    ${o.fritekst ? `<div class="oppdrag-fritekst mb-3">${escapeHtml(o.fritekst)}</div>` : ''}
    <div id="rediger-oppdrag"></div>
    <h6 class="text-muted">Enheter</h6>
    <div class="mb-3">${mkEnhetsrader(o)}${OPPDRAG_TILGANG.kanSkrive ? _varsleValg(o) : ''}</div>
    <h6 class="text-muted">Tidslinje</h6>
    ${tidslinjeHtml(o)}
    ${(historikkKnapp || slettKnapp) ? `<div class="mt-3 d-flex gap-2 flex-wrap">${historikkKnapp}${slettKnapp}</div>` : ''}
    ${flyttValg}`);
}


// ── Enhetene på oppdraget (flere enheter, 11. sep. 2026) ───────────
// Radene i detaljvisningen, med handlingene per enhet: «Før status» (§9),
// «Gjenåpne» og «Ta av». Og «Varsle enhet til» under dem. Alle går på
// `apentOppdrag` — klikkdelegeringen sender ett argument, og det er enheten.

//: Oppdraget som står åpent i detaljmodalen, som data. `apentOppdragId`
//: under er ID-en alene; handlingene per enhet trenger radene.
let apentOppdrag = null;


function mkEnhetsrader(o) {
  const flere = (o.enheter || []).length > 1;
  return (o.enheter || []).map((e) => {
    const statusTid = e.status_tidspunkt
      ? ` ${klokke(e.status_tidspunkt)} · ${tidSiden(e.status_tidspunkt)}` : '';
    const sted = e.sted_navn ? ` → ${e.sted_navn}` : '';
    const meta = `${e.status_navn}${sted}${statusTid}`;
    const knapper = OPPDRAG_TILGANG.kanSkrive ? _enhetsknapper(e, flere) : '';
    return `
      <div class="enhet-rad" id="enhet-rad-${escHtmlValue(e.enhet_id)}">
        <span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <span class="enhet-rad-navn">${escapeHtml(e.enhet_navn)}</span>
        <span class="oppdrag-meta">${escapeHtml(meta)}</span>
        <span class="ms-auto d-flex gap-1 flex-wrap">${knapper}</span>
      </div>`;
  }).join('');
}


function _enhetsknapper(e, flere) {
  // Bare knappene som kan brukes: «Ta av» mens hun venter og ikke er den
  // siste, «Gjenåpne» når hun er ledig, «Før status» ellers. En knapp som
  // alltid feiler er verre enn ingen.
  const ut = [];
  if (e.status !== 'ledig') {
    ut.push(`<button type="button" class="btn btn-outline-primary btn-sm"
                     data-action="visFoerStatus" data-id="${escHtmlValue(e.enhet_id)}">Endre status</button>`);
  } else {
    ut.push(`<button type="button" class="btn btn-outline-secondary btn-sm"
                     data-action="gjenaapneEnhet" data-id="${escHtmlValue(e.enhet_id)}">Gjenåpne</button>`);
  }
  if (e.status === 'venter' && flere) {
    ut.push(`<button type="button" class="btn btn-outline-danger btn-sm"
                     data-action="taAvEnhet" data-id="${escHtmlValue(e.enhet_id)}">Ta av</button>`);
  }
  return ut.join('');
}


function _varsleValg(o) {
  // Enhetene på vakt som ikke alt står på oppdraget.
  const paa = new Set((o.enheter || []).map((e) => e.enhet_id));
  const ledige = enheter.filter((e) => e.pa_vakt && !paa.has(e.id));
  if (!ledige.length) return '';
  const valg = ledige.map(
    (e) => `<option value="${escHtmlValue(e.id)}">${escapeHtml(e.navn)}</option>`).join('');
  return `
    <div class="input-group input-group-sm mt-2">
      <select id="varsle-enhet" class="form-select" aria-label="Enhet å varsle">${valg}</select>
      <button class="btn btn-outline-primary" type="button"
              data-action="varsleEnhet" data-id="${escHtmlValue(o.id)}">Varsle enhet til</button>
    </div>`;
}


function _lovligeOverganger(status) {
  // Speiler `services.OVERGANGER`: neste ledd i kjeden, og «Ledig» fra alt.
  // Serveren avgjør uansett; dette er hva nedtrekket tilbyr.
  const kjede = STATUS_REKKEFOLGE.filter((s) => s !== 'ledig');
  const i = kjede.indexOf(status);
  const ut = [];
  if (i >= 0 && i + 1 < kjede.length) ut.push(kjede[i + 1]);
  // «Behandlet på sted» (12. sep. 2026): sidegrenen fra Fremme, rett til Ledig.
  if (status === 'fremme') ut.push('behandlet');
  if (status !== 'ledig') ut.push('ledig');
  return ut;
}


function _visEnhetsfeil(melding) {
  const el = document.getElementById('enheter-feil');
  if (!el) return;
  el.textContent = melding;
  el.classList.remove('d-none');
}


async function _enhetshandling(url, metode, feiltekst) {
  const res = await apiFetch(url, { method: metode });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    _visEnhetsfeil(d.message || feiltekst);
    return false;
  }
  if (apentOppdragId !== null) await visOppdrag(apentOppdragId);
  await lastAlt();
  return true;
}


async function varsleEnhet(oppdragId) {
  const valg = document.getElementById('varsle-enhet');
  if (!valg || !valg.value) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${oppdragId}/enheter/${Number(valg.value)}/`, 'POST',
    'Kunne ikke varsle enheten.');
}


async function taAvEnhet(enhetId) {
  if (apentOppdragId === null) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/`, 'DELETE',
    'Kunne ikke ta enheten av.');
}


async function gjenaapneEnhet(enhetId) {
  if (apentOppdragId === null) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/gjenaapne/`, 'POST',
    'Kunne ikke gjenåpne.');
}


function visFoerStatus(enhetId) {
  const rad = document.getElementById(`enhet-rad-${enhetId}`);
  if (!rad || rad.querySelector('.foer-skjema')) return;
  const e = ((apentOppdrag && apentOppdrag.enheter) || [])
    .find((x) => Number(x.enhet_id) === Number(enhetId));
  if (!e) return;

  const navn = window.OPPDRAG_STATUS_NAVN || {};
  const overganger = _lovligeOverganger(e.status);
  const statusvalg = overganger.map(
    (st) => `<option value="${escHtmlValue(st)}">${escapeHtml(navn[st] || st)}</option>`).join('');
  const stedvalg = (window.OPPDRAG_AVREIST_TIL || []).map(
    ([nokkel, tekst]) => `<option value="${escHtmlValue(nokkel)}">${escapeHtml(tekst)}</option>`).join('');
  // Stedet hører til «Avreist» og vises bare når det er valgt (André,
  // 12. sep. 2026). Nedtrekket melder `change`, og `foerStatusEndret`
  // slår stedet av og på.
  const stedSkjult = overganger[0] === 'avreist' ? '' : ' hidden';
  // Ett skjema om gangen: de andre radenes knapper skjules mens dette står,
  // og radens egen «Endre status» låses (André, 12. sep. 2026).
  document.getElementById('detalj-innhold')?.classList.add('foer-aapen');
  rad.querySelectorAll('[data-action="visFoerStatus"]').forEach((b) => { b.disabled = true; });

  const skjema = document.createElement('div');
  skjema.className = 'foer-skjema mt-1 d-flex gap-2 align-items-center flex-wrap w-100';
  skjema.innerHTML = (`
    <select id="foer-status" class="form-select form-select-sm w-auto" aria-label="Status"
            data-action="foerStatusEndret" data-hendelse="change">${statusvalg}</select>
    <select id="foer-sted" class="form-select form-select-sm w-auto" aria-label="Sted ved Avreist"${stedSkjult}>
      <option value="">Velg sted</option>${stedvalg}</select>
    <input type="datetime-local" class="form-control form-control-sm w-auto"
           id="foer-tid" value="${_lokalNaa()}" step="60">
    <button type="button" class="btn btn-sm btn-primary"
            id="foer-lagre" data-action="lagreFoerStatus" data-id="${escHtmlValue(enhetId)}">Endre</button>
    <button type="button" class="btn btn-sm btn-outline-secondary"
            data-action="avbrytFoerStatus">Avbryt</button>
    <span id="foer-feil" class="text-danger small"></span>`);
  rad.appendChild(skjema);
  document.getElementById('foer-tid').focus();
}


function avbrytFoerStatus() {
  document.querySelectorAll('.foer-skjema').forEach((el) => el.remove());
  document.getElementById('detalj-innhold')?.classList.remove('foer-aapen');
  document.querySelectorAll('#detalj-innhold [data-action="visFoerStatus"]')
    .forEach((b) => { b.disabled = false; });
}


async function angreStatus(enhetId) {
  if (apentOppdragId === null) return;
  await _enhetshandling(
    `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/angre/`, 'POST',
    'Kunne ikke angre.');
}


async function slettOppdrag(id) {
  // Sletting mens alle biler venter (sentralbord), eller i historikken
  // (global admin). Dialogen stopper feilklikket; `confirm: true` i kroppen
  // stopper et kall som treffer URL-en uten å mene det.
  if (!confirm('Slette oppdraget? Det kan ikke angres.')) return;
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/`, {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    _visEnhetsfeil(d.message || 'Kunne ikke slette oppdraget.');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  await lastAlt();
  if (historikkliste.length) await lastHistorikk();
}


async function slettHistorikk() {
  const feil = document.getElementById('historikk-feil');
  if (!confirm('Slette alle oppdragene i historikken for vakten? Det kan ikke angres.')) return;
  const res = await apiFetch('/oppdrag/api/historikk/', {
    method: 'DELETE', body: JSON.stringify({ confirm: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') {
    if (feil) { feil.textContent = d.message || 'Kunne ikke slette.'; feil.classList.remove('d-none'); }
    return;
  }
  await lastHistorikk();
  await lastAlt();
}


function visRedigerOppdrag() {
  // Sentralbordet retter oppdraget (André, 12. sep. 2026): lokasjon,
  // hastegrad, problemstilling og fritekst. Valgene hentes fra
  // «Nytt oppdrag»-skjemaet, som finnes for alle med skrivetilgang — én
  // kilde for verdimengdene.
  const o = apentOppdrag;
  const boks = document.getElementById('rediger-oppdrag');
  if (!o || !boks) return;
  if (boks.innerHTML) { boks.innerHTML = ''; return; }
  const kopier = (fraId, valgt) => Array.from(document.querySelectorAll(`#${fraId} option`))
    .map((op) => `<option value="${escHtmlValue(op.value)}"${op.value === valgt ? ' selected' : ''}>${escapeHtml(op.textContent)}</option>`)
    .join('');
  const lokvalg = lokasjoner.filter((l) => l.er_aktiv || l.id === o.lokasjon_id).map(
    (l) => `<option value="${escHtmlValue(l.id)}"${l.id === o.lokasjon_id ? ' selected' : ''}>${escapeHtml(l.navn)}</option>`).join('');
  boks.innerHTML = (`
    <div class="row g-2 mt-1">
      <div class="col-md-6"><label class="form-label" for="red-hastegrad">Hastegrad</label>
        <select id="red-hastegrad" class="form-select form-select-sm"
                data-action="hastegradEndret" data-hendelse="change" data-arg="red">${kopier('nytt-hastegrad', o.hastegrad)}</select></div>
      <div class="col-md-6"><label class="form-label" for="red-lokasjon">Lokasjon</label>
        <select id="red-lokasjon" class="form-select form-select-sm">${lokvalg}</select></div>
      <div class="col-md-6"><label class="form-label" for="red-problemstilling">Problemstilling</label>
        <select id="red-problemstilling" class="form-select form-select-sm"></select></div>
      <div class="col-12"><label class="form-label" for="red-fritekst">Fritekst</label>
        <textarea id="red-fritekst" class="form-control form-control-sm" rows="2">${escapeHtml(o.fritekst || '')}</textarea></div>
      <div class="col-12 d-flex gap-2 align-items-center">
        <button type="button" class="btn btn-sm btn-primary" id="red-lagre"
                data-action="lagreOppdrag" data-id="${escHtmlValue(o.id)}">Lagre</button>
        <button type="button" class="btn btn-sm btn-outline-secondary" data-action="visRedigerOppdrag">Avbryt</button>
        <span id="red-feil" class="text-danger small"></span>
      </div>
    </div>`);
  fyllProblemstillinger('red', o.hastegrad, o.problemstilling);
}


async function lagreOppdrag(id) {
  const feil = document.getElementById('red-feil');
  await withSubmitGuard('red-lagre', async () => {
    const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({
        problemstilling: document.getElementById('red-problemstilling').value,
        hastegrad: document.getElementById('red-hastegrad').value,
        lokasjon_id: Number(document.getElementById('red-lokasjon').value),
        fritekst: document.getElementById('red-fritekst').value,
      }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      if (feil) feil.textContent = d.message || 'Kunne ikke lagre.';
      return;
    }
    await visOppdrag(id);
    await lastAlt();
  });
}


function foerStatusEndret() {
  // Stedet finnes bare for «Avreist».
  const status = document.getElementById('foer-status');
  const sted = document.getElementById('foer-sted');
  if (!status || !sted) return;
  sted.hidden = status.value !== 'avreist';
  if (sted.hidden) sted.value = '';
}


function _lokalNaa() {
  // `datetime-local` vil ha lokal tid uten sone.
  const naa = new Date();
  return new Date(naa.getTime() - naa.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 16);
}


async function lagreFoerStatus(enhetId) {
  const status = document.getElementById('foer-status');
  const sted = document.getElementById('foer-sted');
  const tid = document.getElementById('foer-tid');
  const feil = document.getElementById('foer-feil');
  if (!status || !tid || !tid.value || apentOppdragId === null) return;

  await withSubmitGuard('foer-lagre', async () => {
    // Stedet hører til «Avreist» og ingen annen status — sendes bare da.
    const stedLedd = (status.value === 'avreist' && sted && sted.value) ? `${sted.value}/` : '';
    const res = await apiFetch(
      `/oppdrag/api/oppdrag/${apentOppdragId}/enheter/${Number(enhetId)}/status/${status.value}/${stedLedd}`, {
        method: 'POST',
        // Ingen sone på `datetime-local`; serveren tolker den som lokal tid.
        body: JSON.stringify({ tidspunkt: tid.value }),
      });
    const d = await res.json();
    if (!res.ok || d.status !== 'ok') {
      feil.textContent = d.message || 'Kunne ikke føre statusen.';
      // Et avvist klokkeslett settes tilbake til nå (André, 12. sep. 2026):
      // det som sto der var galt, og nå er det tryggeste utgangspunktet.
      tid.value = _lokalNaa();
      return;
    }
    await visOppdrag(apentOppdragId);
    await lastAlt();
  });
}


// ── Korreksjon av tidspunkt ─────────────────────────────
// Rettingen skriver en NY rad som peker på den gamle; begge blir stående i
// tidslinjen. Se §4.4 i beslutningsnotatet — `Statusmelding` er et spor av
// hva som ble meldt, ikke en tilstand som overskrives.

//: Oppdraget som står åpent i detaljmodalen. Trengs fordi tidslinjen må
//: tegnes på nytt etter en retting, og rettingen kjenner bare meldings-ID-en.
let apentOppdragId = null;


function visRettTid(meldingId) {
  const rad = document.getElementById(`tidslinje-rad-${meldingId}`);
  if (!rad || rad.querySelector('.rett-tid-skjema')) return;

  // Klokkeslettet som allerede står i raden er utgangspunktet — operatøren
  // retter et minutt eller to, hun skriver ikke inn datoen på nytt.
  const lokal = _lokalNaa();

  const skjema = document.createElement('div');
  skjema.className = 'rett-tid-skjema mt-1 d-flex gap-2 align-items-center flex-wrap';
  // En streng, ikke `trustedHtml(...)`: den pakker inn i et objekt for
  // `cellHtml()`, og som innerHTML blir det «[object Object]». Skjemaet sto
  // slik fra fase 3 til 11. sep. 2026 — «Rett tid» viste ingenting.
  skjema.innerHTML = (`
    <input type="datetime-local" class="form-control form-control-sm w-auto"
           id="rett-tid-verdi" value="${lokal}">
    <button type="button" class="btn btn-sm btn-primary"
            id="rett-tid-lagre" data-action="lagreRettTid" data-id="${meldingId}">Lagre</button>
    <button type="button" class="btn btn-sm btn-outline-secondary"
            data-action="avbrytRettTid">Avbryt</button>
    <span id="rett-tid-feil" class="text-danger small"></span>`);
  rad.appendChild(skjema);
  document.getElementById('rett-tid-verdi').focus();
}


function avbrytRettTid() {
  document.querySelectorAll('.rett-tid-skjema').forEach((el) => el.remove());
}


async function lagreRettTid(meldingId) {
  const felt = document.getElementById('rett-tid-verdi');
  const feil = document.getElementById('rett-tid-feil');
  if (!felt || !felt.value) return;

  await withSubmitGuard('rett-tid-lagre', async () => {
    const res = await apiFetch(`/oppdrag/api/statusmelding/${meldingId}/korriger/`, {
      method: 'POST',
      // Ingen sone på `datetime-local`; serveren tolker den som lokal tid.
      body: JSON.stringify({ tidspunkt: felt.value }),
    });
    const d = await res.json();
    if (!res.ok || d.status !== 'ok') {
      // Feilen navngir hvilken nabo som er i veien, så den skal stå i
      // skjemaet der operatøren kan handle på den — ikke i en alert.
      feil.textContent = d.message || 'Kunne ikke rette tidspunktet.';
      return;
    }
    // Tegn detaljvisningen på nytt: både tidslinjen og den gjeldende raden
    // har endret seg, og å flikke på DOM-en her ville duplisert regelen om
    // hvilken rad som vinner.
    if (apentOppdragId !== null) await visOppdrag(apentOppdragId);
    await lastAlt();
  });
}


async function flyttOppdrag(id) {
  const valg = document.getElementById('flytt-enhet');
  const fra = document.getElementById('flytt-fra');
  const feil = document.getElementById('flytt-feil');
  const kropp = { enhet_id: Number(valg.value) };
  if (fra) kropp.fra_enhet_id = Number(fra.value);
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/flytt/`, {
    method: 'POST',
    body: JSON.stringify(kropp),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    feil.textContent = d.message || 'Kunne ikke flytte oppdraget.';
    feil.classList.remove('d-none');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  await lastAlt();
}


// ── Historikk (ferdigstilte oppdrag) ────────────────────
// Rydding av tavla, ikke vaktarkivet: radene er urørt, og «Hent tilbake»
// angrer. Ordet «arkiv» er reservert core.arkiv, som fryser hele vakter —
// se kommentaren i oppdrag/services.py.

let historikkliste = [];


function renderHistorikk() {
  const el = document.getElementById('historikkliste');
  if (!el) return;
  if (!historikkliste.length) {
    el.innerHTML = '<div class="tom-melding">Ingen ferdigstilte oppdrag.</div>';
    return;
  }
  el.innerHTML = (historikkliste.map((o) => {
    const fritekstBlokk = o.fritekst
      ? `<div class="oppdrag-fritekst">${escapeHtml(o.fritekst)}</div>`
      : '';
    // Alle bilene, ikke bare den primære — historikken viste én til
    // 12. sep. 2026.
    const enhetsnavn = (o.enheter || []).map((e) => e.enhet_navn).join(', ') || o.enhet_navn;
    // Sletting i historikken er global admin. Knappen er sin egen rad-
    // handling: klikk på resten av raden åpner oppdraget.
    const slett = OPPDRAG_TILGANG.erAdmin
      ? `<button type="button" class="btn btn-sm btn-outline-danger mt-2"
                 data-action="slettOppdrag" data-id="${escHtmlValue(o.id)}">Slett</button>`
      : '';
    return `
    <div class="oppdrag-rad" data-action="visOppdrag" data-id="${escHtmlValue(o.id)}"
         role="button" tabindex="0">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-nr">#${escHtmlValue(o.nummer)}</span>
        <span class="hastegrad ${escHtmlValue(hastegradKlasse(o.hastegrad))}">${escapeHtml(o.hastegrad)}</span>
        <span class="oppdrag-problem">${escapeHtml(o.problemstilling)}</span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(enhetsnavn)} · ${escapeHtml(o.lokasjon_navn)} · ferdig ${escapeHtml(klokke(o.historikk_fra))}
      </div>
      ${fritekstBlokk}
      ${slett}
    </div>`;
  }).join(''));
}


async function lastHistorikk() {
  const felt = document.getElementById('historikk-sok');
  const sok = felt ? (felt.value || '').trim() : '';
  const url = sok
    ? `/oppdrag/api/historikk/?sok=${encodeURIComponent(sok)}`
    : '/oppdrag/api/historikk/';
  const res = await apiFetch(url);
  if (!res.ok) return;
  historikkliste = (await res.json()).data || [];
  renderHistorikk();
}


async function flyttTilHistorikk(id) {
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/historikk/`, { method: 'POST' });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    alert(d.message || 'Kunne ikke legge oppdraget i historikken.');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  etagOppdrag = null;   // raden forsvinner fra den aktive lista
  await lastAlt();
  if (document.getElementById('historikkliste')) await lastHistorikk();
}


async function hentTilbakeOppdrag(id) {
  const res = await apiFetch(`/oppdrag/api/oppdrag/${id}/historikk/`, { method: 'DELETE' });
  if (!res.ok) return;
  bootstrap.Modal.getInstance(document.getElementById('oppdragDetaljModal'))?.hide();
  etagOppdrag = null;
  await lastAlt();
  if (document.getElementById('historikkliste')) await lastHistorikk();
}


// ── Oppretting ──────────────────────────────────────────

async function opprettOppdrag() {
  const feil = document.getElementById('nytt-feil');
  feil.classList.add('d-none');

  const enhetIder = _valgteEnheter();
  if (!enhetIder.length) {
    feil.textContent = 'Kryss av minst én enhet.';
    feil.classList.remove('d-none');
    return;
  }

  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    method: 'POST',
    body: JSON.stringify({
      enhet_ider: enhetIder,
      lokasjon_id: Number(document.getElementById('nytt-lokasjon').value),
      problemstilling: document.getElementById('nytt-problemstilling').value,
      hastegrad: document.getElementById('nytt-hastegrad').value,
      fritekst: document.getElementById('nytt-fritekst').value,
    }),
  });
  const d = await res.json();
  if (!res.ok || d.status !== 'ok') {
    feil.textContent = d.message || 'Kunne ikke opprette oppdraget.';
    feil.classList.remove('d-none');
    return;
  }
  bootstrap.Modal.getInstance(document.getElementById('nyttOppdragModal'))?.hide();
  document.getElementById('nytt-fritekst').value = '';
  document.querySelectorAll('input[name="nytt-enhet"]:checked').forEach((i) => { i.checked = false; });
  await lastAlt();
}


function nullstillNyttOppdrag() {
  // Ved hver åpning (André, 12. sep. 2026: «husker den avhukede enheter fra
  // forrige opprettelse», og senere «nedtrekksfeltene … må starte øverst på
  // hver»). Uavhengig av hvilken vei forrige forsøk gikk.
  document.querySelectorAll('input[name="nytt-enhet"]').forEach((i) => { i.checked = false; });
  document.getElementById('nytt-feil')?.classList.add('d-none');
  ['nytt-hastegrad', 'nytt-lokasjon', 'nytt-problemstilling'].forEach((id) => {
    const sel = document.getElementById(id);
    if (sel && sel.options.length) sel.selectedIndex = 0;
  });
  ['nytt-fritekst'].forEach((id) => {
    const felt = document.getElementById(id);
    if (felt) felt.value = '';
  });
  // Problemstillingene følger hastegraden som står valgt — den første nå.
  hastegradEndret('nytt');
}


function _valgteEnheter() {
  // I avkryssingsrekkefølge = listas rekkefølge; den første blir primær.
  return Array.from(document.querySelectorAll('input[name="nytt-enhet"]:checked'))
    .map((i) => Number(i.value));
}


function mkEnhetsvalg() {
  // Avkryssing, ikke nedtrekk: operatøren sender gjerne to biler på samme
  // hendelse. Bare enhetene på vakt — gruppert på type, ambulansene først
  // (André, 12. sep. 2026).
  const grupper = _grupperEnheter(enheter.filter((e) => e.pa_vakt));
  return grupper.map((g) => {
    const hode = grupper.length > 1
      ? `<div class="enhet-gruppe">${escapeHtml(g.navn)}</div>` : '';
    return hode + g.enheter.map((e) => `
    <label class="form-check nytt-enhet-valg">
      <input class="form-check-input" type="checkbox" name="nytt-enhet" value="${escHtmlValue(e.id)}">
      <span class="form-check-label">${escapeHtml(e.navn)}</span>
    </label>`).join('');
  }).join('');
}


// ── Verdimengdene: lokasjoner, enhetstyper, problemstillinger ────────────
//
// Tre tabeller, ett vindu med tre faner (André, 12. sep. 2026: «Admin må
// kunne redigere listen over problemstillinger blant annet hvor de skal stå i
// rekkefølgen i nedtrekksvinduet. Samme gjelder med rekkefølge på lokasjoner
// og grupperinger.»). Serveren svarer likt for alle tre (`views_verdier`), så
// klienten har én bygger og én sett handlinger med tabellen i argumentet.
// Rekkefølgen sendes som hele lista etter et flytt, ikke som «opp» per rad.

const VERDIMENGDER = {
  lokasjoner: { tittel: 'Lokasjoner', ny: 'Ny lokasjon' },
  enhetstyper: { tittel: 'Enhetstyper', ny: 'Ny enhetstype' },
  problemstillinger: { tittel: 'Problemstillinger', ny: 'Ny problemstilling' },
  // Ikke en liste, men et skjema (12. sep. 2026): lydvarsel og krav i bilen.
  bilinnstillinger: { tittel: 'Bilen', ny: '' },
};
const PROBLEM_KATEGORIER = [
  ['medisinsk', 'Medisinsk'], ['drift', 'Drift'], ['begge', 'Begge'],
];
let verdiFane = 'lokasjoner';
let verdier = { lokasjoner: [], enhetstyper: [], problemstillinger: [], bilinnstillinger: null };


function _verdiArg(arg) {
  // «slug:id[:hva]» — klikkdelegeringen sender ett argument.
  const [slug, id, hva] = String(arg).split(':');
  return { slug, id: Number(id), hva, rad: (verdier[slug] || []).find((r) => r.id === Number(id)) };
}


function _byggProblemkart(rader) {
  // Speiler `Problemstilling.passer()` på serveren: begge → alle
  // hastegrader, drift → Drift, medisinsk → resten. Udefinert først.
  // Bygges her, ikke hentet, så nedtrekket følger med idet noen endrer lista.
  const aktive = rader.filter((r) => r.er_aktiv);
  const passer = (r, h) => r.kategori === 'begge' || (r.kategori === 'drift') === (h === 'Drift');
  const kart = {};
  HASTEGRAD_REKKEFOLGE.forEach((h) => {
    kart[h] = aktive.filter((r) => passer(r, h)).map((r) => r.navn);
  });
  return { kart, medAntall: aktive.filter((r) => r.med_antall).map((r) => r.navn) };
}


async function lastVerdier(slug) {
  const res = await apiFetch(`/oppdrag/api/${slug}/`);
  if (!res.ok) return false;
  verdier[slug] = (await res.json()).data || [];
  if (slug === 'bilinnstillinger') {
    if (globalThis.window && verdier.bilinnstillinger?.terskler) {
      globalThis.window.OPPDRAG_LYDVARSEL = verdier.bilinnstillinger.terskler;
    }
    return true;
  }
  // Det som ellers på siden leser tabellen, følger med.
  if (slug === 'lokasjoner') {
    lokasjoner = verdier[slug];
    fyllNedtrekk();
  } else if (slug === 'enhetstyper') {
    if (globalThis.window) {
      globalThis.window.OPPDRAG_ENHETSTYPER = verdier[slug]
        .filter((t) => t.er_aktiv).map((t) => [t.id, t.navn]);
    }
    renderEnheter();
    fyllNedtrekk();
    renderEnhetsadmin();
  } else if (slug === 'problemstillinger') {
    const { kart, medAntall } = _byggProblemkart(verdier[slug]);
    if (globalThis.window) {
      globalThis.window.OPPDRAG_PROBLEMSTILLINGER_FOR = kart;
      globalThis.window.OPPDRAG_MED_ANTALL = medAntall;
    }
    hastegradEndret('nytt');
  }
  return true;
}


async function lastLokasjoner() {
  await lastVerdier('lokasjoner');
}


async function lastVerdiadmin() {
  // Bilinnstillingene hentes bare for admin — fanen finnes ikke for andre.
  const slugs = Object.keys(VERDIMENGDER).filter(
    (slug) => slug !== 'bilinnstillinger' || globalThis.window?.OPPDRAG_TILGANG?.erAdmin);
  await Promise.all(slugs.map((slug) => lastVerdier(slug)));
  renderVerdiadmin();
}


function _lydvarselSkjema(d) {
  // Én rad per hastegrad: første varsel og gjentakelse, i sekunder. Og
  // bryteren for pip ved nytt oppdrag. Lagres samlet med «Lagre».
  const rader = HASTEGRAD_REKKEFOLGE.map((h) => {
    const [forste, gjenta] = (d.terskler || {})[h] || [900, 60];
    const paa = (d.aktive || {})[h] !== false;
    return `
      <tr>
        <td><input type="checkbox" class="form-check-input me-1" id="lyd-aktiv-${escHtmlValue(h)}"${paa ? ' checked' : ''}
                   aria-label="Lydvarsel på for ${escHtmlValue(h)}"> ${escapeHtml(h)}</td>
        <td><input type="number" class="form-control form-control-sm lyd-felt" min="0" max="86400" step="5"
                   id="lyd-forste-${escHtmlValue(h)}" value="${escHtmlValue(forste)}" aria-label="Første varsel"></td>
        <td><input type="number" class="form-control form-control-sm lyd-felt" min="5" max="86400" step="5"
                   id="lyd-gjenta-${escHtmlValue(h)}" value="${escHtmlValue(gjenta)}" aria-label="Gjenta hvert"></td>
      </tr>`;
  }).join('');
  return `
    <h6 class="mb-2">Lydvarsel</h6>
    <div class="form-check mb-2">
      <input class="form-check-input" type="checkbox" id="lyd-aktiv"${d.lyd_aktiv !== false ? ' checked' : ''}>
      <label class="form-check-label" for="lyd-aktiv">Lydvarsel i bilene er på</label>
    </div>
    <table class="table table-sm mb-2 lyd-tabell">
      <thead><tr><th>På · hastegrad</th><th>Første varsel etter (s)</th><th>Gjenta hvert (s)</th></tr></thead>
      <tbody>${rader}</tbody>
    </table>
    <div class="form-check mb-3">
      <input class="form-check-input" type="checkbox" id="lyd-nytt"${d.nytt_oppdrag ? ' checked' : ''}>
      <label class="form-check-label" for="lyd-nytt">Pip i bilen når den får et nytt oppdrag</label>
    </div>
    <h6 class="mb-2">Grovsortering</h6>
    <p class="form-text mt-0 mb-2">Kreves alltid før «Behandlet på sted» og før Ledig etter Leverer. Ikke på Drift.</p>
    <div class="form-check mb-3">
      <input class="form-check-input" type="checkbox" id="krev-grov-avreist"${d.krev_grov_avreist ? ' checked' : ''}>
      <label class="form-check-label" for="krev-grov-avreist">Krev grovsortering også før Avreist</label>
    </div>
    <button type="button" class="btn btn-sm btn-primary" id="lyd-lagre" data-action="lagreLydvarsel">Lagre</button>
    <span class="form-text ms-2">Gjelder alle biler; bilen henter innstillingene innen fem minutter.</span>`;
}


async function lagreLydvarsel() {
  const terskler = {};
  const aktive = {};
  HASTEGRAD_REKKEFOLGE.forEach((h) => {
    terskler[h] = [Number(document.getElementById(`lyd-forste-${h}`)?.value),
                   Number(document.getElementById(`lyd-gjenta-${h}`)?.value)];
    aktive[h] = !!document.getElementById(`lyd-aktiv-${h}`)?.checked;
  });
  const kropp = {
    terskler,
    aktive,
    nytt_oppdrag: !!document.getElementById('lyd-nytt')?.checked,
    lyd_aktiv: !!document.getElementById('lyd-aktiv')?.checked,
    krev_grov_avreist: !!document.getElementById('krev-grov-avreist')?.checked,
  };
  await withSubmitGuard('lyd-lagre', async () => {
    if (await _verdiKall('/oppdrag/api/bilinnstillinger/',
                         { method: 'PUT', body: JSON.stringify(kropp) },
                         'Kunne ikke lagre bilinnstillingene.')) {
      await lastVerdier('bilinnstillinger');
      renderVerdiadmin();
    }
  });
}


async function velgVerdifane(slug) {
  if (!VERDIMENGDER[slug]) return;
  verdiFane = slug;
  renderVerdiadmin();
}


function _verdirad(slug, r, forste, siste) {
  const arg = (hva) => escHtmlValue(slug + ':' + r.id + ':' + hva);
  const dempet = r.er_aktiv ? '' : ' text-muted';
  const knappAktiv = r.fast ? '' : (r.er_aktiv
    ? `<button class="btn btn-sm btn-outline-secondary" data-action="settVerdiAktiv" data-arg="${arg('0')}">Deaktiver</button>`
    : `<button class="btn btn-sm btn-outline-success" data-action="settVerdiAktiv" data-arg="${arg('1')}">Aktiver</button>`);
  const endre = r.fast ? ''
    : `<button class="btn btn-sm btn-outline-secondary" data-action="endreVerdinavn" data-arg="${arg('navn')}" title="Endre navn"><i class="bi bi-pencil"></i></button>`;
  const slett = (globalThis.window?.OPPDRAG_TILGANG?.erAdmin && !r.fast)
    ? `<button class="btn btn-sm btn-outline-danger" data-action="slettVerdi" data-arg="${arg('slett')}" title="Slett"><i class="bi bi-trash"></i></button>`
    : '';
  // Opp/ned: «Udefinert» er fast øverst, og flyttes ikke — knappene ligger
  // der, men er avslått, så raden ikke hopper i høyde.
  const opp = `<button class="btn btn-sm btn-outline-secondary" data-action="flyttVerdi" data-arg="${arg('opp')}" title="Flytt opp"${(forste || r.fast) ? ' disabled' : ''}><i class="bi bi-chevron-up"></i></button>`;
  const ned = `<button class="btn btn-sm btn-outline-secondary" data-action="flyttVerdi" data-arg="${arg('ned')}" title="Flytt ned"${(siste || r.fast) ? ' disabled' : ''}><i class="bi bi-chevron-down"></i></button>`;
  let ekstra = '';
  if (slug === 'problemstillinger' && !r.fast) {
    const kategorivalg = PROBLEM_KATEGORIER.map(([v, n]) =>
      `<option value="${escHtmlValue(v)}"${v === r.kategori ? ' selected' : ''}>${escapeHtml(n)}</option>`).join('');
    ekstra = `
      <select class="form-select form-select-sm verdi-kategori" aria-label="Kategori"
              data-action="settVerdifelt" data-hendelse="change" data-felt="kategori" data-id="${escHtmlValue(r.id)}">${kategorivalg}</select>
      <select class="form-select form-select-sm verdi-antall" aria-label="Bærer antall"
              data-action="settVerdifelt" data-hendelse="change" data-felt="med_antall" data-id="${escHtmlValue(r.id)}">
        <option value="0"${r.med_antall ? '' : ' selected'}>Uten antall</option>
        <option value="1"${r.med_antall ? ' selected' : ''}>Med antall</option>
      </select>`;
  }
  const iBruk = r.i_bruk ? `<span class="oppdrag-meta">· ${escHtmlValue(r.i_bruk)} i bruk</span>` : '';
  const fast = r.fast ? '<span class="oppdrag-meta">· fast</span>' : '';
  return `
    <div class="d-flex align-items-center gap-2 py-1 verdi-rad">
      <span class="btn-group">${opp}${ned}</span>
      <span class="flex-grow-1${dempet}">${escapeHtml(r.navn)} ${iBruk}${fast}</span>
      ${ekstra}${endre}${knappAktiv}${slett}
    </div>`;
}


function renderVerdiadmin() {
  const el = document.getElementById('verdiliste');
  if (!el) return;
  document.querySelectorAll('[data-verdifane]').forEach((k) => {
    k.classList.toggle('active', k.dataset.verdifane === verdiFane);
  });
  const nyFelt = document.getElementById('ny-verdi');
  if (nyFelt) nyFelt.placeholder = VERDIMENGDER[verdiFane].ny;
  const nyKategori = document.getElementById('ny-verdi-kategori');
  if (nyKategori) nyKategori.classList.toggle('d-none', verdiFane !== 'problemstillinger');
  const nyRad = document.getElementById('ny-verdi-rad');
  if (nyRad) nyRad.classList.toggle('d-none', verdiFane === 'bilinnstillinger');
  if (verdiFane === 'bilinnstillinger') {
    el.innerHTML = _lydvarselSkjema(verdier.bilinnstillinger || {});
    return;
  }
  const rader = verdier[verdiFane] || [];
  if (!rader.length) {
    el.innerHTML = ('<div class="tom-melding">Ingen ennå.</div>');
    return;
  }
  el.innerHTML = (rader.map((r, i) => _verdirad(verdiFane, r, i === 0, i === rader.length - 1)).join(''));
}


async function _verdiKall(url, valg, feilmelding) {
  const res = await apiFetch(url, valg);
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d.status !== 'ok') { alert(d.message || feilmelding); return false; }
  return true;
}


async function leggTilVerdi() {
  const felt = document.getElementById('ny-verdi');
  const navn = (felt?.value || '').trim();
  if (!navn) return;
  const kropp = { navn };
  if (verdiFane === 'problemstillinger') {
    kropp.kategori = document.getElementById('ny-verdi-kategori')?.value || 'medisinsk';
  }
  if (await _verdiKall(`/oppdrag/api/${verdiFane}/`, { method: 'POST', body: JSON.stringify(kropp) },
                       'Kunne ikke legge til.')) {
    felt.value = '';
    await lastVerdier(verdiFane);
    renderVerdiadmin();
  }
}


async function endreVerdinavn(arg) {
  const { slug, id, rad } = _verdiArg(arg);
  if (!rad) return;
  const navn = (prompt('Nytt navn:', rad.navn) || '').trim();
  if (!navn || navn === rad.navn) return;
  if (await _verdiKall(`/oppdrag/api/${slug}/${id}/`, { method: 'PUT', body: JSON.stringify({ navn }) },
                       'Kunne ikke endre navnet.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


async function settVerdiAktiv(arg) {
  const { slug, id, hva } = _verdiArg(arg);
  if (await _verdiKall(`/oppdrag/api/${slug}/${id}/`,
                       { method: 'PUT', body: JSON.stringify({ er_aktiv: hva === '1' }) },
                       'Kunne ikke endre.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


async function settVerdifelt(id, felt, verdi) {
  // Kategori og antall på en problemstilling — nedtrekk i raden, som
  // enhetstypen i enhetspanelet. Bare problemstillinger har slike felt.
  const kropp = felt === 'med_antall' ? { med_antall: verdi === '1' } : { [felt]: verdi };
  if (await _verdiKall(`/oppdrag/api/problemstillinger/${id}/`,
                       { method: 'PUT', body: JSON.stringify(kropp) }, 'Kunne ikke endre.')) {
    await lastVerdier('problemstillinger');
    renderVerdiadmin();
  }
}


async function flyttVerdi(arg) {
  const { slug, id, hva } = _verdiArg(arg);
  const ider = (verdier[slug] || []).map((r) => r.id);
  const i = ider.indexOf(id);
  const j = hva === 'opp' ? i - 1 : i + 1;
  if (i < 0 || j < 0 || j >= ider.length) return;
  [ider[i], ider[j]] = [ider[j], ider[i]];
  if (await _verdiKall(`/oppdrag/api/${slug}/rekkefolge/`,
                       { method: 'PUT', body: JSON.stringify({ ider }) }, 'Kunne ikke flytte.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


async function slettVerdi(arg) {
  const { slug, id, rad } = _verdiArg(arg);
  if (!rad) return;
  if (!confirm(`Slette «${rad.navn}» for godt?`)) return;
  if (await _verdiKall(`/oppdrag/api/${slug}/${id}/`,
                       { method: 'DELETE', body: JSON.stringify({ confirm: true }) }, 'Kunne ikke slette.')) {
    await lastVerdier(slug);
    renderVerdiadmin();
  }
}


// ── Enhetsadmin ─────────────────────────────────────────

function renderEnhetsadmin() {
  const el = document.getElementById('enhetsadminliste');
  if (!el) return;
  if (!enhetsadmin.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter ennå.</div>';
    return;
  }

  // Kontokoblingen vises, men redigeres ikke: enheten får den ved oppretting
  // av kontoen, og mister den når kontoen slettes. Står det «Ingen konto
  // knyttet», er det en ekte feiltilstand og verdt å se.
  el.innerHTML = (enhetsadmin.map((e) => {
    const vaktKlasse = e.pa_vakt ? 'btn-outline-secondary' : 'btn-outline-success';
    const vaktHandling = e.pa_vakt ? 'taAvVakt' : 'settPaaVakt';
    const vaktTekst = e.pa_vakt ? 'Av vakt' : 'På vakt';
    const vaktKnapp = e.er_aktiv
      ? `<button class="btn btn-sm ${vaktKlasse}" data-action="${vaktHandling}" data-id="${escHtmlValue(e.id)}">${vaktTekst}</button>`
      : '';

    const koblingTekst = e.username
      ? `Logger inn som ${e.username}`
      : 'Ingen konto knyttet';
    const koblingKlasse = e.username ? 'enhet-meta' : 'enhet-meta text-danger';

    const status = e.er_aktiv
      ? (e.pa_vakt ? 'På vakt' : 'Ikke på vakt')
      : 'Pensjonert';
    const radKlasse = e.er_aktiv && e.pa_vakt
      ? 'enhet-kort' : 'enhet-kort enhet-av-vakt';
    // Typen settes her (12. sep. 2026): kontoskjemaet vet ikke hva bilen er.
    const typer = (globalThis.window?.OPPDRAG_ENHETSTYPER || []).map(([id, navn]) => [String(id), navn]);
    const valgt = e.type == null ? '' : String(e.type);
    // En type som er deaktivert står fortsatt på bilen som har den — nedtrekket
    // må tilby den, ellers velges den bort i stillhet ved neste tegning.
    if (valgt && !typer.some(([id]) => id === valgt)) typer.push([valgt, e.type_navn || 'Inaktiv type']);
    const typevalg = [['', 'Uten type'], ...typer].map(([verdi, navn]) =>
      `<option value="${escHtmlValue(verdi)}"${verdi === valgt ? ' selected' : ''}>${escapeHtml(navn)}</option>`).join('');
    const typeNedtrekk = `<select class="form-select form-select-sm enhet-type" aria-label="Enhetstype"
              data-action="settEnhetstype" data-hendelse="change" data-felt="type" data-id="${escHtmlValue(e.id)}">${typevalg}</select>`;

    return `
    <div class="${radKlasse} mb-2">
      <div class="flex-grow-1">
        <div class="enhet-navn">${escapeHtml(e.navn)} <span class="enhet-meta">· ${escapeHtml(status)}</span></div>
        <div class="${koblingKlasse}">${escapeHtml(koblingTekst)}</div>
      </div>
      ${typeNedtrekk}
      ${vaktKnapp}
    </div>`;
  }).join(''));
}


async function settEnhetstype(id, felt, verdi) {
  const res = await apiFetch(`/oppdrag/api/enheter/${id}/`, {
    method: 'PUT', body: JSON.stringify({ type: verdi ? Number(verdi) : null }),
  });
  if (!res.ok) { alert('Kunne ikke endre enhetstypen.'); return; }
  await lastEnhetsadmin();
  await lastEnheter();
}


async function lastEnhetsadmin() {
  // `?alle=1` tar med pensjonerte enheter. Tavla skal ikke se dem, men lista
  // skal: en pensjonert bil er ikke borte, den venter på at kontoen sin
  // opprettes igjen.
  const res = await apiFetch('/oppdrag/api/enheter/?alle=1');
  if (res.ok) enhetsadmin = (await res.json()).data || [];
  renderEnhetsadmin();
}


// ── Lasting ─────────────────────────────────────────────

async function lastEnheter() {
  const res = await apiFetch('/oppdrag/api/enheter/', {
    headers: etagEnheter ? { 'If-None-Match': etagEnheter } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagEnheter = res.headers.get('ETag');
  enheter = (await res.json()).data || [];

  // **Bufferet tømmes bare når noe faktisk endret seg** — etter 304-sjekken,
  // ikke før. Tømte vi det på hver runde, ville et åpent panel stått på
  // «Henter…» for alltid: `undefined` betyr «ikke hentet», og ingenting
  // ville hentet det på nytt.
  //
  // Står et panel åpent, hentes det på nytt her. Et tall om hvem som er i
  // bilen skal ikke bli stående fra forrige time.
  besetninger = {};
  if (apenBesetning !== null) hentBesetning(apenBesetning);
  return true;
}


async function lastOppdrag() {
  const res = await apiFetch('/oppdrag/api/oppdrag/', {
    headers: etagOppdrag ? { 'If-None-Match': etagOppdrag } : {},
  });
  if (res.status === 304) return false;
  if (!res.ok) return false;
  etagOppdrag = res.headers.get('ETag');
  oppdragsliste = (await res.json()).data || [];
  return true;
}


function fyllNedtrekk() {
  // Kalles fra pollingen hver gang enhetslista har endret seg — og en
  // statusendring på en bil er en endring. Mens operatøren fyller ut «Nytt
  // oppdrag» bygges avkryssingen altså om under henne; det som sto krysset
  // av og valgt må derfor settes tilbake (André, 12. sep. 2026: «krysset
  // forsvinner når jeg går nedover i listen»).
  const enhetsvalg = document.getElementById('nytt-enheter');
  if (enhetsvalg) {
    const krysset = _valgteEnheter();
    enhetsvalg.innerHTML = mkEnhetsvalg()
      || '<div class="tom-melding">Ingen enheter på vakt.</div>';
    enhetsvalg.querySelectorAll('input[name="nytt-enhet"]').forEach((i) => {
      if (krysset.includes(Number(i.value))) i.checked = true;
    });
  }
  const lokvalg = document.getElementById('nytt-lokasjon');
  if (lokvalg) {
    const valgt = lokvalg.value;
    const aktive = lokasjoner.filter((l) => l.er_aktiv);
    lokvalg.innerHTML = (aktive.map(
      (l) => `<option value="${escHtmlValue(l.id)}">${escapeHtml(l.navn)}</option>`).join(''));
    if (valgt && aktive.some((l) => String(l.id) === String(valgt))) lokvalg.value = valgt;
  }
}


function visManglendeOppsett() {
  // Et skjema som lar deg trykke «Opprett» og så feiler med «Ukjent enhet» er
  // verre enn et som sier fra på forhånd hva som mangler.
  const boks = document.getElementById('mangler-oppsett');
  if (!boks) return;
  const mangler = [];
  if (!enheter.filter((e) => e.pa_vakt).length) mangler.push('ingen enheter på vakt');
  if (!lokasjoner.filter((l) => l.er_aktiv).length) mangler.push('ingen aktive lokasjoner');

  const knapp = document.querySelector('[data-bs-target="#nyttOppdragModal"]');
  if (mangler.length) {
    document.getElementById('mangler-hva').textContent = ' Portalen har ' + mangler.join(' og ') + '.';
    boks.classList.remove('d-none');
    if (knapp) knapp.disabled = true;
  } else {
    boks.classList.add('d-none');
    if (knapp) knapp.disabled = false;
  }
}


async function lastAlt() {
  const [nyeEnheter, nyeOppdrag] = await Promise.all([lastEnheter(), lastOppdrag()]);
  if (nyeEnheter) renderEnheter();
  if (nyeOppdrag) renderOppdrag();
  if (nyeEnheter) fyllNedtrekk();
  visManglendeOppsett();
}


// ── Vaktarkiv (fase 7) ───────────────────────────────────────────────────
//
// Kun global admin ser knappen, og serveren gater alle fire endepunktene på
// nytt. Arkivering fryser vakten med signatur; historikken over rydder tavla
// og er reversibel. To handlinger, to knapper.

let arkivliste = [];

function _arkivTittel(a) {
  // Eldre arkiv har «Vaktnavn — arkivert …» som tittel; navnet står alt på
  // raden under, så det klippes her. Nye arkiv lages uten det.
  const prefiks = `${a.vakt_navn} — `;
  const t = String(a.tittel || '');
  if (a.vakt_navn && t.startsWith(prefiks)) {
    const rest = t.slice(prefiks.length);
    return rest.charAt(0).toUpperCase() + rest.slice(1);
  }
  return t;
}


function renderArkiv() {
  const el = document.getElementById('arkivliste');
  if (!el) return;
  if (!arkivliste.length) {
    el.innerHTML = '<div class="tom-melding">Ingen arkiverte vakter ennå.</div>';
    return;
  }
  el.innerHTML = arkivliste.map((a) => {
    const kollaps = a.kollapset
      ? '<span class="oppdrag-meta">· radene er slettet, kun tall igjen</span>'
      : '';
    return `
    <div class="oppdrag-rad">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="oppdrag-problem">${escapeHtml(_arkivTittel(a))}</span>
        <span class="oppdrag-nr">${escHtmlValue(a.antall_oppdrag)} oppdrag</span>
      </div>
      <div class="oppdrag-meta mt-1">
        ${escapeHtml(a.vakt_navn)} · arkivert av ${escapeHtml(a.importert_av)}
        ${kollaps}
      </div>
      ${a.notat ? `<div class="oppdrag-fritekst">${escapeHtml(a.notat)}</div>` : ''}
      <div class="mt-2 d-flex gap-2">
        <button class="btn btn-sm btn-outline-primary" type="button"
                data-action="visArkivStatistikk" data-id="${escHtmlValue(a.id)}">Vis statistikk</button>
        <button class="btn btn-sm btn-outline-secondary" type="button"
                data-action="visArkiv" data-id="${escHtmlValue(a.id)}">Signatur</button>
        <button class="btn btn-sm btn-outline-danger" type="button"
                data-action="slettArkiv" data-id="${escHtmlValue(a.id)}">Slett</button>
      </div>
      <div id="arkiv-detalj-${escHtmlValue(a.id)}" class="mt-2"></div>
    </div>`;
  }).join('');
}


async function lastArkiv() {
  const res = await apiFetch('/oppdrag/api/arkiv/');
  if (!res.ok) return;
  arkivliste = (await res.json()).data || [];
  renderArkiv();
}


async function arkiverVakt() {
  const feil = document.getElementById('arkiv-feil');
  feil?.classList.add('d-none');
  await withSubmitGuard('arkiv-knapp', async () => {
    const notat = (document.getElementById('arkiv-notat')?.value || '').trim();
    const res = await apiFetch('/oppdrag/api/arkiv/', {
      method: 'POST',
      body: JSON.stringify({ notat }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok || d.status !== 'ok') {
      // Inline, ikke alert(): meldingen hører hjemme ved knappen som
      // feilet, og en alert forsvinner før man rekker å lese den.
      if (feil) {
        feil.textContent = d.message || 'Arkivering feilet.';
        feil.classList.remove('d-none');
      }
      return;
    }
    const notatfelt = document.getElementById('arkiv-notat');
    if (notatfelt) notatfelt.value = '';
    // Vakta er lukket: tavla og historikken er tomme, og nummeret starter
    // på nytt. Alt som viser oppdrag må tegnes på nytt.
    await lastArkiv();
    await lastAlt();
  });
}


function visArkivStatistikk(id) {
  // Som pasientarkivet: tallene tegnes på /statistikk/, ikke som en linje
  // her (André, 12. sep. 2026: «viser i ren tekst»). Arkiv-id-en i URL-en,
  // så sida kan lastes på nytt og deles.
  window.location.href = `/statistikk/?kilde=oppdrag&arkiv=${encodeURIComponent(id)}`;
}


async function visArkiv(id) {
  const boks = document.getElementById(`arkiv-detalj-${id}`);
  if (!boks) return;
  if (boks.innerHTML) { boks.innerHTML = ''; return; }   // klikk igjen = lukk

  const res = await apiFetch(`/oppdrag/api/arkiv/${id}/`);
  if (!res.ok) return;
  const a = (await res.json()).data || {};
  const s = a.stats && a.stats.summary ? a.stats.summary : null;
  if (!s) { boks.innerHTML = '<div class="tom-melding">Ingen tall.</div>'; return; }

  // Signaturen er hele poenget med et arkiv: stemmer den ikke, skal det stå
  // først og tydelig, ikke som en detalj under tallene.
  const tukling = a.tamper_detected
    ? '<div class="text-danger fw-bold mb-1">Signaturen stemmer ikke — arkivet kan være endret.</div>'
    : '';
  boks.innerHTML = `
    ${tukling}
    <div class="oppdrag-meta">
      ${escHtmlValue(s.total)} oppdrag · ${escHtmlValue(s.fullforte)} fullført ·
      median responstid ${escHtmlValue(fmtMin(s.responstid.median))} ·
      median oppdragstid ${escHtmlValue(fmtMin(s.oppdragstid.median))}
    </div>
    <div class="oppdrag-meta">SHA-256: ${escapeHtml((a.sha256 || '').slice(0, 16))}…</div>`;
}


async function slettArkiv(id) {
  if (!confirm('Slette arkivet? Det kan ikke angres, og arkivet er det '
             + 'eneste som står igjen etter at vakten er avsluttet.')) return;
  const res = await apiFetch(`/oppdrag/api/arkiv/${id}/`, {
    method: 'DELETE',
    body: JSON.stringify({ confirm: true }),
  });
  if (!res.ok) return;
  await lastArkiv();
}


document.addEventListener('DOMContentLoaded', async () => {
  await lastLokasjoner();
  await lastAlt();
  renderEnheter();
  renderOppdrag();
  fyllNedtrekk();
  visManglendeOppsett();
  // Samme kadens som pasientlista. ETag gjør at et poll uten endring koster
  // en 304 uten kropp.
  setInterval(lastAlt, 30000);
  // «12 min siden» eldes uten at serveren sier noe — lista svarer 304 når
  // ingenting er endret. Én tegning i minuttet holder tallene ærlige.
  setInterval(() => { renderOppdrag(); renderEnheter(); }, 60000);
});


// «Nytt oppdrag» begynner tomt hver gang det åpnes — se `nullstillNyttOppdrag`.
document.getElementById('nyttOppdragModal')
  ?.addEventListener('show.bs.modal', nullstillNyttOppdrag);
