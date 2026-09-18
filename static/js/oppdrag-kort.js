// ════════════════════════════════════════════════════════════════════════════
// Enhetskortet — innmaten og ordforrådet rundt den.
//
// **Lastes av både `/oppdrag/` (sentralbordet) og `/ko/` (ressursoversikten).**
// De to tegner samme kort, og den eneste måten det holder over tid er at det
// er samme kode som tegner det (André, 17. sep. 2026: «Det er ikke feature
// parity med /oppdrag. Jeg vil ha det likt feature messig inn her i /ko»).
// En kopi ville falt bak neste felt noen la til, uten at noe ble rødt — og
// nettopp det hadde skjedd: KOs første kort viste navn, besetning og status,
// og manglet passiv vakt, ventende, «ledig siden», sted og hele oppdragslinja.
//
// Serversiden har samme grep: `oppdrag.services.enhetskort()` er den ene
// serialiseringen, og begge endepunktene leser den.
//
// **`oppdrag-enhet.js` deler ikke dette.** Bilens egen skjerm har sine egne
// kopier av `hastegradKlasse` og `_problemMedAntall`, og de står igjen med
// vilje: den siden laster ikke denne fila, og å rive i enhetsskjermen hører
// til pulje 4. Står i TODO.
//
// Krever portal-utils.js (escapeHtml, escHtmlValue, klokke, apiFetch).
// ════════════════════════════════════════════════════════════════════════════

// ── Nummerformene ────────────────────────────────────────────────────────
//
// **`O45` og `H12`, ett sted** (18. sep. 2026, §6 i KO-notatet). Var `#45`
// til KO fikk hendelser: `#45` og `H12` på nabolinjer i loggen er ikke
// utvetydige, og det er i loggen de møtes. Samme regel som
// `oppdrag.services.oppdragsnr()` på serveren — de to skal aldri være uenige.
// Enhetsskjermen (`oppdrag-enhet.js`) har sin egen kopi, som for de andre
// hjelperne der: den laster ikke denne fila.

function oppdragsnr(nummer) {
  return 'O' + nummer;
}

function hendelsesnr(nummer) {
  return 'H' + nummer;
}

// Besetningspanelet er åpent for én enhet om gangen, og svarene caches til
// neste henting. Tilstanden ligger her og ikke hos sidene: panelet er delt, og
// to kopier ville gitt to ulike «hvilken er åpen».
let besetninger = {};
let apenBesetning = null;

// Den sist tegnede lista, og **reserven** — ikke fasit. Se under.
let sisteEnhetsliste = [];

// **Hvem som eier lista.** Sentralbordet henter enhetene selv og bytter ut
// `enheter` med en *ny* array ved hver runde (`lastEnheter`), uten å tegne i
// samme slengen. En `sisteEnhetsliste` ville derfor pekt på forrige runde til
// neste tegning kom — og en besetning som ble hentet i mellomtiden ville
// tegnet den gamle lista.
//
// Vinduet er kort og retter seg selv ved neste tegning, men forskjellen var
// ekte: før delingen (18. sep. 2026) leste `renderEnheter()` alltid den
// *levende* `enheter`. Sida melder derfor inn hvor lista bor, og den delte
// koden spør i stedet for å huske.
let enhetslisteKilde = null;

function settEnhetslisteKilde(fn) {
  enhetslisteKilde = fn;
}

function tegnEnhetslistePaaNytt() {
  tegnEnhetsliste(enhetslisteKilde ? enhetslisteKilde() : sisteEnhetsliste);
}

//: «Trenger ny ressurs» blir tydeligere jo lenger det står (minutter).
//  Brukes av oppdragslista; står her fordi den hører til samme ordforråd.

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


// **Innmaten i et enhetskort — alt to sider skal si likt om en enhet.**
//
// Rammen rundt er sidas egen: sentralbordet legger klikket som åpner
// besetningen utenpå, KO legger sine statusknapper og korpsmerke rundt.
// Skillet går ved det som er *enhetens* opplysninger mot det som er sidas
// handlinger.
function enhetskortInnmat(e) {
  // «Ledig (2 venter)» er distinksjonen 113 trenger: enheten har fått
  // oppdrag, men ikke rykket ut, og kan fortsatt sendes.
  // Statusen med klokkeslett og tid siden: «Fremme 14:32 · 12 min».
  // Prosjektleder, 11. sep. 2026 — «på statusen så må tidsstemplet og vise».
  // **«Ledig siden» fyller tomrommet** (André, 15. sep. 2026): en ledig enhet
  // har ingen aktiv koblingsrad, så `status_tidspunkt` er tomt og statusen sto
  // som et ord uten tid. Operatøren som skal sende noen vil vite hvem som har
  // stått lengst.
  const siden = e.status_tidspunkt || e.ledig_siden;
  const statusTid = siden ? ` ${klokke(siden)} · ${tidSiden(siden)}` : '';
  // «Avreist → Sykehus» — hvor bilen dro skal synes her også.
  const sted = e.sted_navn ? ` → ${e.sted_navn}` : '';
  const meta = e.antall_ventende
    ? `${e.status_navn}${sted}${statusTid} · ${e.antall_ventende} venter`
    : `${e.status_navn}${sted}${statusTid}`;
  // Det aktive oppdraget i ett blikk: nummer, hastegrad, problemstilling.
  // Hoistet ut av mal-strengen, som resten — en nøstet mal-streng inne i en
  // `${...}` er usynlig for XSS-skannerne.
  const grov = e.oppdragsnummer != null ? _grovMerke(e) : '';
  const oppdragslinje = e.oppdragsnummer != null
    ? `<div class="enhet-oppdrag">
         <span class="oppdrag-nr">${escHtmlValue(oppdragsnr(e.oppdragsnummer))}</span>
         <span class="hastegrad ${escHtmlValue(hastegradKlasse(e.hastegrad))}">${escapeHtml(e.hastegrad || '')}</span>
         ${grov}
         <span class="enhet-oppdrag-problem">${escapeHtml(_problemMedAntall(e))}</span>
       </div>`
    : '';
  // **Passiv-merket vises bare der det betyr noe** (André, 16. sep. 2026):
  // enhetstypen må tillate passiv vakt. «Aktiv» skrives ikke — det er
  // normaltilstanden, og et merke på hver ambulanse er støy. Merket er dempet,
  // ikke en advarsel: enheten *er* på vakt, hun sover.
  //
  // **En streng, ikke `trustedHtml(...)`.** Den pakker verdien i
  // `{__trustedHtml: …}` for `cellHtml()` i en Tabulator-celle; i en mal-streng
  // blir objektet til «[object Object]» — på *hvert* kort, for
  // `trustedHtml('')` er et objekt like fullt. Meldt fra staging 16. sep. 2026.
  const passiv = (e.kan_passiv_vakt && e.passiv_vakt)
    ? '<span class="enhet-passivmerke">passiv vakt</span>' : '';
  return `<span class="status-prikk status-${escHtmlValue(e.status)}"></span>
        <div class="flex-grow-1">
          <div class="enhet-navn">${escapeHtml(e.navn)}${passiv}</div>
          <div class="enhet-meta">${escapeHtml(meta)}</div>
          ${oppdragslinje}
        </div>`;
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
  // **Innmaten er delt med KO** (17. sep. 2026, André: «Jeg vil ha det likt
  // feature messig inn her i /ko»). Status, tid siden, passiv-merket og
  // oppdragslinja ligger i `oppdrag-kort.js` og tegnes av begge sidene; det
  // som står igjen her er sentralbordets egen ramme — klikket som åpner
  // besetningen, og panelet under kortet.
  //
  // En kopi ville falt bak neste felt noen la til, uten at noe ble rødt.
  // Samme grep som `oppdrag.services.enhetskort()` på serversiden.
  const klikkbar = kanSeBesetning() ? ' enhet-kort-klikkbar' : '';
  const apner = kanSeBesetning()
    ? `data-action="visBesetning" data-id="${escHtmlValue(e.id)}"` : '';
  // Hoistet ut av mal-strengen, som resten i denne fila: en nøstet mal-streng
  // inne i en `${...}` er usynlig for XSS-skanneren.
  const innmat = enhetskortInnmat(e);
  const besetning = mkBesetning(e.id);
  return `
      <div class="enhet-kort${klikkbar}" ${apner}>
        ${innmat}
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
  if (apenBesetning === enhetId) { apenBesetning = null; tegnEnhetslistePaaNytt(); return; }
  apenBesetning = enhetId;
  tegnEnhetslistePaaNytt();
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
  tegnEnhetslistePaaNytt();
}


// **Ressurslista, tegnet én gang for begge sidene.**
//
// `/oppdrag/` og `/ko/` viser de samme enhetene, med de samme statusene, i den
// samme rekkefølgen. Det er ikke en likhet som skal vedlikeholdes — det er
// samme funksjon (André, 18. sep. 2026: «Vi vil ha det likt i funksjonalitet
// som vi hadde det i /oppdrag»).
//
// Begge sidene bruker `#enhetsliste` og `#av-vakt-teller`.
// ── Minimerbare grupper (KO pulje 6, André 18. sep. 2026: «ressurstypene må
// kunne minimeres») ─────────────────────────────────────────────────────────
//
// Lukket-tilstanden huskes per nettleser: det er et visningsvalg, ikke data.
// **En lukket gruppe skjuler ingenting stille** (§7.2 i KO-notatet):
// overskriften står med antallet, og ett klikk åpner. Nøkkelen er
// `type:<id>` for enhetstypene og `gruppe:<id>` for vaktlistas ressursgrupper,
// så de to listene deler mekanismen uten å dele tilstand.

const GRUPPER_LUKKET_NOKKEL = 'tavle.grupper.lukket';

function _lukkedeGrupper() {
  try {
    const raa = globalThis.localStorage?.getItem(GRUPPER_LUKKET_NOKKEL);
    const liste = raa ? JSON.parse(raa) : [];
    return new Set(Array.isArray(liste) ? liste : []);
  } catch (e) {
    return new Set();
  }
}

function gruppeErLukket(nokkel) {
  return _lukkedeGrupper().has(nokkel);
}

function vippGruppe(nokkel) {
  const lukkede = _lukkedeGrupper();
  if (lukkede.has(nokkel)) lukkede.delete(nokkel); else lukkede.add(nokkel);
  try {
    globalThis.localStorage?.setItem(GRUPPER_LUKKET_NOKKEL, JSON.stringify(Array.from(lukkede)));
  } catch (e) { /* privat modus e.l. — da huskes ikke valget, og det er alt */ }
  tegnEnhetslistePaaNytt();
  if (typeof koTegnRessurserPaaNytt === 'function') koTegnRessurserPaaNytt();
}

function gruppehode(nokkel, navn, antall, sammendrag) {
  // Overskriften er knappen. Lukket: navn, antall og et kort sammendrag
  // («2 ledig»), så det som er skjult likevel er lesbart.
  const lukket = gruppeErLukket(nokkel);
  const tall = lukket
    ? ' <span class="enhet-gruppe-tall">' + escapeHtml(String(antall))
      + (sammendrag ? ' · ' + escapeHtml(sammendrag) : '') + '</span>'
    : '';
  return '<div class="enhet-gruppe enhet-gruppe-knapp' + (lukket ? ' enhet-gruppe-lukket' : '')
    + '" role="button" tabindex="0" data-action="vippGruppe" data-arg="' + escapeHtml(nokkel) + '">'
    + '<i class="bi ' + (lukket ? 'bi-chevron-right' : 'bi-chevron-down') + ' me-1"></i>'
    + escapeHtml(navn) + tall + '</div>';
}

function _ledigSammendrag(enheter) {
  const ledige = enheter.filter((e) => e.status === 'ledig').length;
  return ledige ? ledige + ' ledig' : '';
}


function tegnEnhetsliste(liste) {
  sisteEnhetsliste = liste || [];
  const el = document.getElementById('enhetsliste');
  if (!el) return;

  // Tavla viser hvem som kan sendes nå. Antallet av vakt står på
  // Enheter-knappen, der hele lista ligger.
  const paVakt = sisteEnhetsliste.filter((e) => e.pa_vakt);
  const antallAv = sisteEnhetsliste.length - paVakt.length;

  if (!paVakt.length) {
    el.innerHTML = '<div class="tom-melding">Ingen enheter på vakt.</div>';
  } else {
    // Gruppert på enhetstype, ambulansene først (André, 12. sep. 2026).
    // Overskriften står bare når det finnes mer enn én type å skille — og
    // fra pulje 6 er den en knapp som lukker gruppa.
    const grupper = _grupperEnheter(paVakt);
    el.innerHTML = grupper.map((g) => {
      const nokkel = 'type:' + g.type;
      const hode = grupper.length > 1
        ? gruppehode(nokkel, g.navn, g.enheter.length, _ledigSammendrag(g.enheter)) : '';
      if (grupper.length > 1 && gruppeErLukket(nokkel)) return hode;
      return hode + g.enheter.map((e) => _enhetskort(e)).join('');
    }).join('');
  }

  const teller = document.getElementById('av-vakt-teller');
  if (teller) teller.textContent = antallAv ? ` (${antallAv} av vakt)` : '';
}
