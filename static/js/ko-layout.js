// ════════════════════════════════════════════════════════════════════════════
// ko-layout.js — rutenettet: fire plasser i 2×2 (fem vinduer — tavla deler plass), bytte av plass og størrelse.
//
// Første av KOs fire filer (`KO_JS` i patients/js_test_utils.py). Ingen
// bundler, ett globalt navnerom, og **ingenting kjører på toppnivå her** —
// `koOppsettStart()` kalles fra `DOMContentLoaded`-kroken i ko.js, som er
// den siste fila.
//
// **Et vindu kan skjules, men ikke forsvinne.** Rammen holdt opprinnelig alle
// fire synlige (André, 18. sep. 2026: «en ramme rundt som sperrer for at de
// kan gjemmes og forsvinnes») — bekymringen var at en flate ingen ser er en
// flate ingen vet har endret seg, siden sida poller. 21. sep. 2026 ba han om
// skjuling likevel, og den bekymringen er besvart i konstruksjonen framfor
// med et forbud: **et skjult vindu står alltid som en knapp i stripa over
// konsollen**, med navnet sitt, og det siste synlige lar seg ikke skjule
// (`koKanSkjule`). Da er «skjult» en tilstand man ser, ikke en flate som er
// borte. Vinduet kan fortsatt ikke legges oppå et annet eller dras forbi
// gulvet (`min-width`/`min-height` i ko.css og `KO_MIN_PROSENT` her).
//
// **Oppsettet huskes per nettleser** (`localStorage`), som gruppene på tavla
// (`tavle.grupper.lukket`). En KO-PC i kommandopunktet beholder da oppsettet
// sitt uansett hvem som logger på — og det er PC-en som er hovedflata.
// Prisen: oppsettet følger ikke deg til en annen maskin. Per bruker på
// serveren kan komme om noen savner det.
// ════════════════════════════════════════════════════════════════════════════

const KO_OPPSETT_NOKKEL = 'ko.oppsett';

//: Vinduene, ved navnet i `data-vindu`. **Fem vinduer, fire plasser**
//: (22. sep. 2026): tavla og ressursoversikten deler én plass i rutenettet
//: (`KO_PAR`) — André: «den skal være med, selv om det kanskje ikke er plass
//: med de fire andre … som et skjult vindu som erstattes». Den som ikke står i
//: rutenettet, står i stripa over konsollen, som de skjulte: en flate man ikke
//: ser, skal være en tilstand man ser.
const KO_VINDUER = ['hendelser', 'logg', 'ressurser', 'oppdrag', 'tavle'];

//: Plassene i rutenettet — to rader med to.
const KO_PLASSER = 4;

//: Parene som deler en plass: den ene står i rutenettet, den andre er parkert.
const KO_PAR = { ressurser: 'tavle', tavle: 'ressurser' };

//: Standardoppsettet: hendelsesloggen og loggstrømmen øverst, ressursene og
//: oppdragene nederst. `bredde` er venstre vindus andel per rad, `hoyde` er
//: øverste rads andel. Tallene er skissens.
const KO_OPPSETT_STANDARD = {
  rader: [['hendelser', 'logg'], ['ressurser', 'oppdrag']],
  bredde: [56, 34],
  hoyde: 56,
  skjult: [],
};

//: Navnene i stripa og i menyen. Et skjult vindu skal stå med det det heter i
//: hodet sitt, ikke med nøkkelen sin.
const KO_VINDUSNAVN = {
  hendelser: 'Hendelseslogg',
  logg: 'Loggstrøm',
  ressurser: 'Ressursoversikt',
  oppdrag: 'Oppdragsliste',
  tavle: 'Tavle',
};

//: Gulvet, i prosent. Under dette kan en skillelinje ikke dras: et vindu på
//: fem prosent er et vindu som er borte, bare med en kant igjen.
const KO_MIN_PROSENT = 20;

// **Regelen, ikke tegningen.** Egen funksjon fordi den avgjør hva en
// skillelinje får lov til.
function koKlemProsent(prosent) {
  const p = Number(prosent);
  if (!Number.isFinite(p)) return 50;
  return Math.min(100 - KO_MIN_PROSENT, Math.max(KO_MIN_PROSENT, p));
}

// Hvilke fire vinduer som står i rutenettet er gyldig: de tre uten partner
// hver én gang, og **nøyaktig én** av hvert par. Et oppsett lagret før tavla
// fantes (fire vinduer, ressursoversikten med) er dermed gyldig som det er —
// ingen KO-PC mister oppsettet sitt av en oppdatering.
function koGyldigePlasser(flate) {
  if (flate.length !== KO_PLASSER || new Set(flate).size !== KO_PLASSER) return false;
  if (!flate.every((v) => KO_VINDUER.includes(v))) return false;
  return Object.keys(KO_PAR).every((v) => flate.includes(v) !== flate.includes(KO_PAR[v]))
    && KO_VINDUER.filter((v) => !KO_PAR[v]).every((v) => flate.includes(v));
}

// Et lagret oppsett er brukerdata fra en annen versjon av sida, og leses
// deretter: to rader med to vinduer hver, gyldige plasser (`koGyldigePlasser`),
// tallene klemt. Alt annet gir `null`, og da gjelder standarden — et oppsett
// som mangler et vindu ville vært nettopp det rammen skal hindre.
function koGyldigOppsett(raa) {
  if (!raa || !Array.isArray(raa.rader) || raa.rader.length !== 2) return null;
  const flate = [];
  for (const rad of raa.rader) {
    if (!Array.isArray(rad) || rad.length !== 2) return null;
    flate.push(...rad);
  }
  if (!koGyldigePlasser(flate)) return null;
  const bredde = Array.isArray(raa.bredde) && raa.bredde.length === 2
    ? raa.bredde.map(koKlemProsent) : [...KO_OPPSETT_STANDARD.bredde];
  return {
    rader: [[...raa.rader[0]], [...raa.rader[1]]],
    bredde,
    hoyde: koKlemProsent(raa.hoyde === undefined ? KO_OPPSETT_STANDARD.hoyde : raa.hoyde),
    skjult: koGyldigSkjult(raa.skjult, flate),
  };
}

// Vinduene som står i rutenettet.
function koIRutenettet(oppsett) {
  return [...oppsett.rader[0], ...oppsett.rader[1]];
}

// Vinduet som er parkert fordi partneren har plassen.
function koParkerte(oppsett) {
  const i = koIRutenettet(oppsett);
  return KO_VINDUER.filter((v) => !i.includes(v));
}

// Skjultlista er brukerdata fra en annen versjon av sida, som resten: navn
// som står i rutenettet, hver én gang. **Alle fire skjult gir ingen** — en tom
// konsoll er ingen tilstand noen har bedt om, og lagringen skal ikke kunne
// bære den tilbake etter at `koKanSkjule()` har nektet den i grensesnittet.
function koGyldigSkjult(raa, flate) {
  if (!Array.isArray(raa)) return [];
  const rene = (flate || KO_VINDUER).filter((v) => raa.includes(v));
  return rene.length >= KO_PLASSER ? [] : rene;
}

function koErSkjult(oppsett, navn) {
  return (oppsett.skjult || []).includes(navn);
}

// **Det siste synlige vinduet lar seg ikke skjule.** Uten regelen kunne
// konsollen bli tom, og da er det ingenting igjen å hente noe tilbake fra
// utenom stripa — en tilstand det ikke er noen grunn til å tilby.
function koKanSkjule(oppsett, navn) {
  if (!koIRutenettet(oppsett).includes(navn) || koErSkjult(oppsett, navn)) return false;
  return (oppsett.skjult || []).length < KO_PLASSER - 1;
}

function koSkjul(oppsett, navn) {
  const ny = koGyldigOppsett(oppsett) || koStandardOppsett();
  if (!koKanSkjule(ny, navn)) return ny;
  ny.skjult = koIRutenettet(ny).filter((v) => v === navn || koErSkjult(ny, v));
  return ny;
}

// Hent et vindu fram. **Er det parkert, tar det partnerens plass** — og
// partneren parkeres, synlig i stripa. Det er hele «Tavle ⇄ Ressursoversikt».
function koVisIgjen(oppsett, navn) {
  const ny = koGyldigOppsett(oppsett) || koStandardOppsett();
  const partner = KO_PAR[navn];
  if (partner && koParkerte(ny).includes(navn)) {
    ny.rader = ny.rader.map((rad) => rad.map((v) => (v === partner ? navn : v)));
    ny.skjult = (ny.skjult || []).filter((v) => v !== partner);
  }
  ny.skjult = (ny.skjult || []).filter((v) => v !== navn);
  return ny;
}

function koStandardOppsett() {
  return koGyldigOppsett(KO_OPPSETT_STANDARD);
}

function koLesOppsett() {
  try {
    const raa = JSON.parse(globalThis.localStorage?.getItem(KO_OPPSETT_NOKKEL) || 'null');
    return koGyldigOppsett(raa) || koStandardOppsett();
  } catch (e) {
    return koStandardOppsett();
  }
}

function koLagreOppsett(oppsett) {
  try {
    globalThis.localStorage?.setItem(KO_OPPSETT_NOKKEL, JSON.stringify(oppsett));
  } catch (e) {
    // Uten lagring gjelder oppsettet til sida lastes på nytt. Ikke en feil.
  }
}

// **Bytt plass på to vinduer** — ren regel: nytt oppsett, det gamle rørt
// ikke. Samme vindu to ganger, eller et ukjent navn, gir oppsettet uendret.
function koBytt(oppsett, a, b) {
  const ny = koGyldigOppsett(oppsett) || koStandardOppsett();
  const i = koIRutenettet(ny);
  if (a === b || !i.includes(a) || !i.includes(b)) return ny;
  ny.rader = ny.rader.map((rad) => rad.map((v) => (v === a ? b : (v === b ? a : v))));
  return ny;
}

//: Det som gjelder nå. Settes av `koOppsettStart()`.
let koOppsett = null;

function koVinduElement(navn) {
  return document.querySelector('.ko-vindu[data-vindu="' + navn + '"]');
}

// Flytt vinduene dit oppsettet sier, og sett andelene. Skillelinjene blir
// stående mellom de to i hver rad; det er vinduene som flyttes rundt dem.
function koTegnOppsett(oppsett) {
  const rader = [document.getElementById('ko-rad-1'), document.getElementById('ko-rad-2')];
  if (!rader[0] || !rader[1]) return;
  // **Et skjult vindu gir plassen sin til naboen, ikke til et hull.** Er
  // begge i en rad skjult, forsvinner raden og den andre tar høyden — ellers
  // sto en tom stripe igjen der raden var.
  const radSynlig = [true, true];
  oppsett.rader.forEach((navn, i) => {
    const rad = rader[i];
    const splitter = rad.querySelector('.ko-splitter-v');
    const venstre = koVinduElement(navn[0]);
    const hoyre = koVinduElement(navn[1]);
    if (!venstre || !hoyre) return;
    rad.insertBefore(venstre, splitter);
    rad.appendChild(hoyre);
    const skjultV = koErSkjult(oppsett, navn[0]);
    const skjultH = koErSkjult(oppsett, navn[1]);
    venstre.classList.toggle('d-none', skjultV);
    hoyre.classList.toggle('d-none', skjultH);
    if (splitter) splitter.classList.toggle('d-none', skjultV || skjultH);
    venstre.style.flex = skjultH ? '1 1 100%' : '1 1 ' + oppsett.bredde[i] + '%';
    hoyre.style.flex = skjultV ? '1 1 100%' : '1 1 ' + (100 - oppsett.bredde[i]) + '%';
    radSynlig[i] = !(skjultV && skjultH);
  });
  // Den parkerte står ikke i noen rad, og vises ikke.
  koParkerte(oppsett).forEach((navn) => {
    const el = koVinduElement(navn);
    if (el) el.classList.add('d-none');
  });
  const vannrett = document.querySelector('.ko-splitter-h');
  if (vannrett) vannrett.classList.toggle('d-none', !(radSynlig[0] && radSynlig[1]));
  rader.forEach((rad, i) => rad.classList.toggle('d-none', !radSynlig[i]));
  if (radSynlig[0] && radSynlig[1]) {
    rader[0].style.flex = '1 1 ' + oppsett.hoyde + '%';
    rader[1].style.flex = '1 1 ' + (100 - oppsett.hoyde) + '%';
  } else {
    rader.forEach((rad) => { rad.style.flex = '1 1 100%'; });
  }
  koTegnSkjulte(oppsett);
  // Tavla som nettopp ble hentet fram skal vise nå (ko-tavle.js). Gjennom en
  // vakt: fila lastes etter denne, og kallet skjer først ved tegning.
  if (typeof koTavleSynligNaa === 'function') koTavleSynligNaa();
}

// Stripa over konsollen: ett kort per skjult vindu, med navnet sitt. Den er
// hele svaret på «en flate ingen ser» — skjult skal være en tilstand man ser,
// og veien tilbake skal stå der tilstanden står.
function koSkjulteHtml(oppsett) {
  return (oppsett.skjult || []).concat(koParkerte(oppsett)).map((v) => '<button type="button"'
    + ' class="btn btn-sm btn-outline-secondary ko-hent-tilbake"'
    + ' data-action="koVisVindu" data-arg="' + escapeHtml(v) + '">'
    + '<i class="bi bi-eye me-1"></i>' + escapeHtml(KO_VINDUSNAVN[v] || v) + '</button>').join('');
}

function koTegnSkjulte(oppsett) {
  const stripe = document.getElementById('ko-skjulte');
  if (!stripe) return;
  const skjult = (oppsett.skjult || []).concat(koParkerte(oppsett));
  stripe.classList.toggle('d-none', !skjult.length);
  stripe.innerHTML = skjult.length
    ? '<span class="ko-skjulte-tekst">Skjult:</span>' + koSkjulteHtml(oppsett) : '';
}

// Knappen i vinduets eget hode. Den siste synlige nekter — og sier det.
function koSkjulVindu(navn) {
  const ny = koSkjul(koOppsett || koLesOppsett(), navn);
  if (ny.skjult.length === (koOppsett ? (koOppsett.skjult || []).length : 0)) return;
  koOppsett = ny;
  koLagreOppsett(koOppsett);
  koTegnOppsett(koOppsett);
}

function koVisVindu(navn) {
  koOppsett = koVisIgjen(koOppsett || koLesOppsett(), navn);
  koLagreOppsett(koOppsett);
  koTegnOppsett(koOppsett);
}

// «⇄» i hodet til tavla og ressursoversikten: bytt til partneren.
function koByttPar(navn) {
  if (KO_PAR[navn]) koVisVindu(KO_PAR[navn]);
}

function koTilbakestillOppsett() {
  koOppsett = koStandardOppsett();
  koLagreOppsett(koOppsett);
  koTegnOppsett(koOppsett);
}

// ── Bytte av plass: dra håndtaket over et annet vindu ───────────────────────

function koDraLyttere() {
  document.querySelectorAll('.ko-grip').forEach((grip) => {
    grip.addEventListener('dragstart', (e) => {
      const vindu = grip.closest('.ko-vindu');
      if (!vindu) return;
      e.dataTransfer.setData('text/plain', vindu.dataset.vindu);
      e.dataTransfer.effectAllowed = 'move';
      vindu.classList.add('ko-vindu-dras');
    });
    grip.addEventListener('dragend', () => {
      document.querySelectorAll('.ko-vindu-dras, .ko-vindu-mal')
        .forEach((el) => el.classList.remove('ko-vindu-dras', 'ko-vindu-mal'));
    });
  });
  document.querySelectorAll('.ko-vindu').forEach((vindu) => {
    vindu.addEventListener('dragover', (e) => {
      // `preventDefault` er det som gjør vinduet til et gyldig mål.
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      if (!vindu.classList.contains('ko-vindu-dras')) vindu.classList.add('ko-vindu-mal');
    });
    vindu.addEventListener('dragleave', () => vindu.classList.remove('ko-vindu-mal'));
    vindu.addEventListener('drop', (e) => {
      e.preventDefault();
      vindu.classList.remove('ko-vindu-mal');
      const fra = e.dataTransfer.getData('text/plain');
      const til = vindu.dataset.vindu;
      if (!fra || fra === til) return;
      koOppsett = koBytt(koOppsett || koLesOppsett(), fra, til);
      koLagreOppsett(koOppsett);
      koTegnOppsett(koOppsett);
    });
  });
}

// ── Størrelse: dra i skillelinjene ──────────────────────────────────────────

// Hvor mange prosent av beholderen pekeren står på, langs én akse. Ren
// regel, prøvd for seg: klemt til gulvet i begge ender.
function koProsentAv(pos, start, lengde) {
  if (!lengde) return 50;
  return koKlemProsent(((pos - start) / lengde) * 100);
}

function koSplitterLyttere() {
  const konsoll = document.getElementById('ko-konsoll');
  if (!konsoll) return;
  document.querySelectorAll('.ko-splitter-v, .ko-splitter-h').forEach((splitter) => {
    const loddrett = splitter.classList.contains('ko-splitter-v');
    splitter.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      splitter.setPointerCapture(e.pointerId);
      splitter.classList.add('ko-splitter-aktiv');
      document.body.classList.add('ko-drar', loddrett ? 'ko-drar-v' : 'ko-drar-h');
      const rad = splitter.closest('.ko-rad');
      const radIndeks = rad && rad.id === 'ko-rad-2' ? 1 : 0;
      const flytt = (ev) => {
        if (!koOppsett) koOppsett = koLesOppsett();
        if (loddrett) {
          const r = rad.getBoundingClientRect();
          koOppsett.bredde[radIndeks] = koProsentAv(ev.clientX, r.left, r.width);
        } else {
          const r = konsoll.getBoundingClientRect();
          koOppsett.hoyde = koProsentAv(ev.clientY, r.top, r.height);
        }
        koTegnOppsett(koOppsett);
      };
      const slipp = () => {
        splitter.removeEventListener('pointermove', flytt);
        splitter.removeEventListener('pointerup', slipp);
        splitter.removeEventListener('pointercancel', slipp);
        splitter.classList.remove('ko-splitter-aktiv');
        document.body.classList.remove('ko-drar', 'ko-drar-v', 'ko-drar-h');
        if (koOppsett) koLagreOppsett(koOppsett);
      };
      splitter.addEventListener('pointermove', flytt);
      splitter.addEventListener('pointerup', slipp);
      splitter.addEventListener('pointercancel', slipp);
    });
  });
}

// ── Konsollhøyden ───────────────────────────────────────────────────────────
//
// **Sida skal ikke rulle — vinduene skal.** Høyden **måles**, den regnes ikke
// ut av en `calc()` med et fast tall: over konsollen står portalheaderen,
// navigasjonen og eventuelle meldinger, og alle tre kan brekke til to linjer.

// Luft under konsollen, så footeren ikke klistrer seg inntil.
const KO_BUNNMARG = 16;

// **Gulvet er en regel, ikke en forsiktighetsmargin.** Uten det gir et kort
// vindu en konsoll på nitti piksler, og da er alle fire ubrukelige samtidig.
// Da er det bedre at sida ruller: det ser rart ut, men alt er lesbart.
const KO_MIN_HOYDE = 480;

function koKonsollhoyde(toppOffset, vindushoyde) {
  return Math.max(vindushoyde - toppOffset - KO_BUNNMARG, KO_MIN_HOYDE);
}

function koSettKonsollhoyde() {
  const konsoll = document.querySelector('.ko-konsoll');
  if (!konsoll) return;
  const topp = konsoll.getBoundingClientRect().top;
  konsoll.style.setProperty(
    '--ko-hoyde', koKonsollhoyde(topp, window.innerHeight) + 'px');
}

// Kalles fra ko.js sin `DOMContentLoaded`.
function koOppsettStart() {
  koOppsett = koLesOppsett();
  koTegnOppsett(koOppsett);
  koDraLyttere();
  koSplitterLyttere();
  koSettKonsollhoyde();
  window.addEventListener('resize', koSettKonsollhoyde);
}
