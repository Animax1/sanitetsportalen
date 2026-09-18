// ════════════════════════════════════════════════════════════════════════════
// ko-layout.js — rutenettet: fire vinduer i 2×2, bytte av plass og størrelse.
//
// Første av KOs tre filer (`KO_JS` i patients/js_test_utils.py). Ingen
// bundler, ett globalt navnerom, og **ingenting kjører på toppnivå her** —
// `koOppsettStart()` kalles fra `DOMContentLoaded`-kroken i ko.js, som er
// den siste fila.
//
// **Rammen holder alle fire synlige.** Det er hele forskjellen på dette og
// frie vinduer (André, 18. sep. 2026: «en ramme rundt som sperrer for at de
// kan gjemmes og forsvinnes»). Et vindu kan bytte plass med et annet og få
// mer eller mindre plass, men det kan ikke lukkes, legges oppå et annet
// eller dras forbi gulvet (`min-width`/`min-height` i ko.css og
// `KO_MIN_PROSENT` her). En flate ingen ser er en flate ingen vet har endret
// seg — siden poller, og det er det samme argumentet som mot faner.
//
// **Oppsettet huskes per nettleser** (`localStorage`), som gruppene på tavla
// (`tavle.grupper.lukket`). En KO-PC i kommandopunktet beholder da oppsettet
// sitt uansett hvem som logger på — og det er PC-en som er hovedflata.
// Prisen: oppsettet følger ikke deg til en annen maskin. Per bruker på
// serveren kan komme om noen savner det.
// ════════════════════════════════════════════════════════════════════════════

const KO_OPPSETT_NOKKEL = 'ko.oppsett';

//: De fire vinduene, ved navnet i `data-vindu`.
const KO_VINDUER = ['hendelser', 'logg', 'ressurser', 'oppdrag'];

//: Standardoppsettet: hendelsesloggen og loggstrømmen øverst, ressursene og
//: oppdragene nederst. `bredde` er venstre vindus andel per rad, `hoyde` er
//: øverste rads andel. Tallene er skissens.
const KO_OPPSETT_STANDARD = {
  rader: [['hendelser', 'logg'], ['ressurser', 'oppdrag']],
  bredde: [56, 34],
  hoyde: 56,
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

// Et lagret oppsett er brukerdata fra en annen versjon av sida, og leses
// deretter: to rader med to vinduer hver, hvert av de fire nøyaktig én gang,
// tallene klemt. Alt annet gir `null`, og da gjelder standarden — et oppsett
// som mangler et vindu ville vært nettopp det rammen skal hindre.
function koGyldigOppsett(raa) {
  if (!raa || !Array.isArray(raa.rader) || raa.rader.length !== 2) return null;
  const flate = [];
  for (const rad of raa.rader) {
    if (!Array.isArray(rad) || rad.length !== 2) return null;
    flate.push(...rad);
  }
  if ([...flate].sort().join(',') !== [...KO_VINDUER].sort().join(',')) return null;
  const bredde = Array.isArray(raa.bredde) && raa.bredde.length === 2
    ? raa.bredde.map(koKlemProsent) : [...KO_OPPSETT_STANDARD.bredde];
  return {
    rader: [[...raa.rader[0]], [...raa.rader[1]]],
    bredde,
    hoyde: koKlemProsent(raa.hoyde === undefined ? KO_OPPSETT_STANDARD.hoyde : raa.hoyde),
  };
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
  if (a === b || !KO_VINDUER.includes(a) || !KO_VINDUER.includes(b)) return ny;
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
  oppsett.rader.forEach((navn, i) => {
    const rad = rader[i];
    const splitter = rad.querySelector('.ko-splitter-v');
    const venstre = koVinduElement(navn[0]);
    const hoyre = koVinduElement(navn[1]);
    if (!venstre || !hoyre) return;
    rad.insertBefore(venstre, splitter);
    rad.appendChild(hoyre);
    venstre.style.flex = '1 1 ' + oppsett.bredde[i] + '%';
    hoyre.style.flex = '1 1 ' + (100 - oppsett.bredde[i]) + '%';
  });
  rader[0].style.flex = '1 1 ' + oppsett.hoyde + '%';
  rader[1].style.flex = '1 1 ' + (100 - oppsett.hoyde) + '%';
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
