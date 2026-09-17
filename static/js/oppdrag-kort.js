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
// Krever portal-utils.js (escapeHtml, escHtmlValue, klokke).
// ════════════════════════════════════════════════════════════════════════════

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
         <span class="oppdrag-nr">#${escHtmlValue(e.oppdragsnummer)}</span>
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
