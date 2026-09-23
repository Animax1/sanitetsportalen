// ════════════════════════════════════════════════════════
// vaktliste-oversikt.js
// ════════════════════════════════════════════════════════
//
// Oppsummeringspanelene: bemanningskurvene, utskriftslista, belastningen,
// «Tilstede nå», «Mitt korps» og «Ikke plassert».
//
// **Skilt fra `vaktliste-tegning.js` 15. sep. 2026**, da den passerte 1 800
// linjer og `test_hver_del_er_mindre_enn_den_var` sa fra. Skjøten er ikke
// vilkårlig: alt over den tegner *regnearket* — fanene, ressurskortene og
// radene man redigerer i — og alt her leser de samme skiftene og svarer på
// noe annet: hvor mange er på vakt, hvem er dobbeltbooket, hva skal skrives
// ut. De to sidene deler `_posterFor()`, `_sumTimer()` og `_skifttimer()`,
// som blir stående i tegningsfila der de hører hjemme.
//
// Ingen bundler: filene lastes i rekkefølge fra
// `templates/vaktliste/index.html` og deler ett globalt navnerom.
// **Ingenting her kjører på toppnivå** — det står i den sist lastede fila,
// og `core/tests_js_splitt.py` håndhever begge deler.
//
// **Alt som kommer fra data escapes** — `escapeHtml()` for tekst,
// `escHtmlValue()` i attributter og tabeller, `trustedHtml()` for markup
// koden bygger selv. `vaktliste/tests_xss.py` håndhever det bygger for bygger.
// ════════════════════════════════════════════════════════


function _vaktensSpenn() {
  // Spennet kurvene tegnes over. Ett sted, fordi alle gruppenes kurver må
  // dekke *samme* timer — ellers ligger ikke søylene under hverandre, og to
  // kurver man ikke kan sammenligne er verre enn én samlet.
  const poster = aktivListe.vaktposter || [];
  const vl = aktivListe.vaktliste || {};
  const TIME = 3600 * 1000;

  let start = vl.startet ? _d(vl.startet)?.getTime() : null;
  let slutt = vl.planlagt_slutt ? _d(vl.planlagt_slutt)?.getTime() : null;

  // Mangler spennet — eller er det urimelig langt — faller vi tilbake på
  // skiftene. Bedre en kurve som dekker for lite enn ingen kurve. Kurven
  // forsvant helt på en vaktliste der vaktens start lå uker før slutten
  // (André, 12. sep. 2026: «fullstendig vekke»).
  const MAKS = 24 * 14;
  const rimelig = (a, b) => a != null && b != null && b > a && (b - a) / TIME <= MAKS;
  if (!rimelig(start, slutt)) {
    if (!poster.length) return null;
    start = Math.min(...poster.map((v) => _d(v.fra_tid).getTime()));
    slutt = Math.max(...poster.map((v) => _d(v.til_tid).getTime()));
    if (!rimelig(start, slutt)) return null;   // et feiltastet årstall: ikke tegn
  }

  return { start, steg: Math.ceil((slutt - start) / TIME) };
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
    const bemannet = paa.filter((v) => !v.ledig);
    ut.push({
      tid: new Date(t).toISOString(),
      // To tall, ikke ett: `planlagt` er alle plassene, `antall` er de som
      // faktisk har en person. Avstanden mellom dem er det som gjenstår.
      antall: bemannet.length,
      planlagt: paa.length,
      // Probono for seg (André, 12. sep. 2026): de er med i `antall`, og
      // tegnes som den øverste delen av søylen i egen farge.
      probono: bemannet.filter((v) => v.probono).length,
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


function _mkEnKurve(tittel, poster) {
  const punkter = _bemanningPerTime(poster);
  if (!punkter.length) {
    // Ingen tom flate: en kurve som mangler uten et ord ser ut som en feil
    // (og var det, 12. sep. 2026). Si hva som mangler.
    return '<div class="vl-meta">Kurven trenger vaktens start og slutt — sett dem i «Innstillinger» (høyst 14 dager), eller legg inn et skift.</div>';
  }
  const topp = Math.max(...punkter.map((p) => p.planlagt)) || 1;
  // Bunnlinja teller folk, ikke plasser (André, 12. sep. 2026: «N personell
  // på det meste»). Skalaen er fortsatt planlagte plasser.
  const flest = Math.max(...punkter.map((p) => p.antall));
  const ledige = punkter.reduce((n, p) => n + (p.planlagt - p.antall), 0);

  // Rene CSS-søyler framfor Chart.js: biblioteket lastes kun på
  // /statistikk/, og en bemanningskurve er ett tall per time. Den lyse delen
  // er plasser uten person — hullene man planlegger for å tette.
  const soyler = punkter.map((p) => {
    const hBemannet = Math.round((p.antall / topp) * 100);
    const hPlanlagt = Math.round((p.planlagt / topp) * 100);
    const probono = p.probono || 0;
    const hProbono = Math.round((probono / topp) * 100);
    const bunnProbono = Math.round(((p.antall - probono) / topp) * 100);
    const skille = _d(p.tid).getHours() === 0 ? ' vl-dogn' : '';
    const tittelTekst = `${_dag(p.tid)} kl. ${_kl(p.tid)}: `
                      + `${p.antall} av ${p.planlagt} plasser fylt`
                      + (probono ? ` (${probono} probono)` : '');
    const probonoDel = probono
      ? `<div class="vl-probonodel" style="height: ${escHtmlValue(hProbono)}%; bottom: ${escHtmlValue(bunnProbono)}%"></div>`
      : '';
    return `<div class="vl-stolpe${skille}" title="${escHtmlValue(tittelTekst)}">
              <div class="vl-planlagt" style="height: ${escHtmlValue(hPlanlagt)}%"></div>
              <div class="vl-bemannet" style="height: ${escHtmlValue(hBemannet)}%"></div>
              ${probonoDel}
            </div>`;
  }).join('');

  // Klokkeslettene ligger i sin egen rad med én celle per søyle, ikke som
  // tekst inni søylen: cellene arver samme flex-bredde, så tallet står
  // under den timen det gjelder uansett hvor mange timer vakten er.
  const steg = _timesteg(punkter.length);
  const timeakse = punkter.map((p, i) => {
    const vis = i % steg === 0;
    return `<span class="vl-time">${vis ? escapeHtml(_kl(p.tid)) : ''}</span>`;
  }).join('');

  const bunn = `${escapeHtml(_dag(punkter[0].tid))} → `
             + `${escapeHtml(_dag(punkter[punkter.length - 1].tid))}`;
  // Tre tall og ikke mer (André, 12. sep. 2026: «Holder med ledige plasser:
  // N og N plasser på det meste og N plasser dekket. Blir for mye clutter
  // hvis ikke»). Plasser, ikke plasstimer — skiftene står i tabellen under.
  const ledigePlasser = poster.filter((vp) => vp.ledig).length;
  const dekket = poster.length - ledigePlasser;
  const ledigTekst = ledigePlasser ? 'Ledige plasser: ' + ledigePlasser : 'Alle plasser fylt';
  const dekketTekst = dekket + (dekket === 1 ? ' plass dekket' : ' plasser dekket');
  const rest = `<span class="vl-meta">${escapeHtml(ledigTekst)} · ${escapeHtml(dekketTekst)}</span>`;

  return `
    <div class="vl-kurvegruppe">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">${escapeHtml(tittel)}</span>
        <div class="d-flex align-items-center gap-3">${rest}</div>
      </div>
      <div class="vl-kurve">${soyler}</div>
      <div class="vl-timeakse">${timeakse}</div>
      <div class="vl-meta">${bunn} · ${escHtmlValue(flest)} personell på det meste</div>
    </div>`;
}


function _tegnforklaring() {
  // Døgnskillet står i forklaringen fordi André spurte hva den hvite streken
  // var. En strek man må spørre om, er en strek som ikke forklarer noe.
  return `
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-bemannet"></i>Bemannet</span>
    <span class="vl-tegnforklaring"><i class="vl-prikk vl-prikk-probono"></i>Probono</span>
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


function _tidsblokker(poster) {
  // **Skift med samme fra–til er én blokk.** Andrés punkt 11. sep. 2026:
  // mange på en vakt deler tid, og en liste der «fre. 20:00 – lør. 04:00»
  // står på fire rader under hverandre er lang og lik — man ser ikke
  // skiftbyttet før man har lest hver rad. Tiden skrives derfor én gang, på
  // en blokklinje, og radene under er hvem.
  //
  // Sortert med `_skiftrekkefolge` først, så blokkene kommer kronologisk og
  // radene i hver blokk alfabetisk. Nøkkelen er ISO-strengene som de kom fra
  // serveren: to skift er i samme blokk når de er *like*, ikke når de
  // overlapper — et skift som slutter en time før de andre er sitt eget.
  const blokker = [];
  poster.slice().sort(_skiftrekkefolge).forEach((vp) => {
    const sist = blokker[blokker.length - 1];
    if (sist && sist.fra_tid === vp.fra_tid && sist.til_tid === vp.til_tid) {
      sist.poster.push(vp);
    } else {
      blokker.push({ fra_tid: vp.fra_tid, til_tid: vp.til_tid, poster: [vp] });
    }
  });
  return blokker;
}


function _telling(poster, skift) {
  // «2 skift · 5 mannskap» som ren tekst — escapes der den settes inn.
  // Mannskap utelates når ingen er satt opp: «0 mannskap» ved siden av
  // «3 ledige» sier det samme to ganger.
  const mannskap = poster.filter((vp) => !vp.ledig).length;
  const deler = [skift + ' skift'];
  if (mannskap) deler.push(mannskap + ' mannskap');
  return deler.join(' · ');
}


function _dagnokkel(iso) {
  // **Den ene regelen for hvilken dag et skift hører til: startdagen.**
  // Lokal dato — «hvilken dag» er et spørsmål om lokal tid, og et skift som
  // starter 00:30 lørdag er lørdagens, ikke fredagens. «fre. 20:00 – lør.
  // 04:00» står under fredag (André, 15. sep. 2026), også etter at
  // «Oversikt» fikk dagen ytterst.
  //
  // **Nullpolstret, fordi nøkkelen sorteres.** `2026-8-15` og `2026-8-4`
  // sorterer feil vei som tekst; `2026-09-15` og `2026-09-04` gjør ikke det.
  // `_grupperPaaDag()` sorterer på nøkkelen framfor å hvile på at den som
  // kaller har sortert — samme grunn som `_hviletider()` sorterer selv.
  const d = _d(iso);
  if (!d) return '';
  const to = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${to(d.getMonth() + 1)}-${to(d.getDate())}`;
}


function _grupperPaaDag(poster) {
  // Skiftene samlet per dag, i kronologisk rekkefølge. Brukes av «Oversikt»,
  // der dagen er ytterste nivå; `_blokkerMedDager()` gjør det samme inne i
  // en tabell. Begge spør `_dagnokkel()`, så de kan ikke svare ulikt på
  // hvilken dag et skift hører til.
  const indeks = new Map();
  (poster || []).forEach((vp) => {
    const nokkel = _dagnokkel(vp.fra_tid);
    if (!indeks.has(nokkel)) indeks.set(nokkel, { nokkel, fra_tid: vp.fra_tid, poster: [] });
    indeks.get(nokkel).poster.push(vp);
  });
  return [...indeks.values()].sort((a, b) => (a.nokkel < b.nokkel ? -1 : a.nokkel > b.nokkel ? 1 : 0));
}


function _dagtekst(iso) {
  // «Fredag 2. okt». Lang ukedag, fordi dette er en overskrift og ikke et
  // merke; lista er lokal så byggerne kan kjøres uten mer enn `MND` fra sida.
  // Heves ut av `_dagoverskrift()` fordi «Oversikt» trenger den samme teksten
  // uten `<tr>` rundt — to formuleringer av samme dato ville før eller siden
  // skrevet dagen ulikt på de to flatene.
  const DAGER_LANGE = ['Søndag', 'Mandag', 'Tirsdag', 'Onsdag', 'Torsdag',
                       'Fredag', 'Lørdag'];
  const d = _d(iso);
  if (!d) return '';
  const mnd = (globalThis.MND || [])[d.getMonth()] || '';
  return `${DAGER_LANGE[d.getDay()]} ${d.getDate()}. ${mnd}`;
}


function _dagoverskrift(iso, kolonner) {
  // Dagraden inne i en tabell (prosjektleder, 11. sep. 2026: «starttid
  // definerer hvilken dag»).
  const tekst = _dagtekst(iso);
  if (!tekst) return '';
  return `
        <tr class="vl-dag">
          <td colspan="${escHtmlValue(kolonner)}">${escapeHtml(tekst)}</td>
        </tr>`;
}


function _blokkrader(blokker, kolonner, radbygger) {
  // Blokkene uten dagoverskrifter. «Oversikt» bruker denne, fordi dagen der
  // står som overskrift *over* tabellen — en dagrad inni ville sagt det samme
  // to ganger på rad.
  return blokker.map((blokk) =>
    _blokklinje(blokk, kolonner) + blokk.poster.map(radbygger).join('')).join('');
}


function _blokkerMedDager(blokker, kolonner, radbygger) {
  // Blokkene, med en dagoverskrift der dagen skifter — **også når vakten bare
  // varer én dag** (André, 15. sep. 2026: «alltid»).
  //
  // Fram til da sto overskriften bare på flerdagsvakter, med begrunnelsen at
  // «én overskrift over alt sier ingenting». Det er fortsatt sant om selve
  // linja, men den koster lite, og regelen kostet mer: planleggeren måtte
  // vite at fraværet av en dagrad *betydde* noe, og en tabell som skifter
  // form når vakta forlenges er en tabell man må lære to ganger.
  let forrige = null;
  return blokker.map((blokk) => {
    const dag = _dagnokkel(blokk.fra_tid);
    const overskrift = dag !== forrige ? _dagoverskrift(blokk.fra_tid, kolonner) : '';
    forrige = dag;
    return overskrift + _blokkrader([blokk], kolonner, radbygger);
  }).join('');
}


function _blokklinje(blokk, kolonner) {
  // Linja over en blokk: tiden, timene og hvor mange som står der. **Ordene
  // er Andrés (11. sep. 2026): et skift er en vakttid, og de som går det er
  // mannskap.** «4 satt opp» kunne leses som fire skift.
  // Blokka
  // har samme form som et skift (`fra_tid`/`til_tid`), så `_tidsspenn` og
  // `_varighet` leser den rett. Tellingen bygges med `+`, ikke i en
  // template-literal — XSS-skanneren leser hvert `${}` i byggerne, og et
  // tall den ikke kan se er escapet er et funn den må avvise.
  const ledige = blokk.poster.filter((vp) => vp.ledig).length;
  const bemannet = blokk.poster.length - ledige;
  const deler = [];
  if (bemannet) deler.push(bemannet + ' mannskap');
  if (ledige) deler.push(ledige + (ledige === 1 ? ' ledig' : ' ledige'));
  return `
        <tr class="vl-blokk">
          <td colspan="${escHtmlValue(kolonner)}">
            <span class="vl-blokktid">${escapeHtml(_tidsspenn(blokk))}</span>
            <span class="vl-blokktimer">${escapeHtml(_varighet(blokk))}</span>
            <span class="vl-meta">${escapeHtml(deler.join(' · '))}</span>
          </td>
        </tr>`;
}


function mkOversikt() {
  // **Utskriftslista.** Hele vakten på ett ark, gruppert på **ressurs** — den
  // man henger opp.
  //
  // Gruppert på korps fram til 30. aug. 2026, og det var feil bord: den som
  // leser lista står på samleplassen eller ved bilen og spør «hvem er her, og
  // når?». Korpset er et kjennetegn ved personen, ikke et sted — det er en
  // kolonne, ikke en overskrift.
  // **Utvalget** (12. sep. 2026): korpset kommer ferdig filtrert i
  // `aktivListe.vaktposter` (korpsvelgeren, eller serveren for korps-
  // brukeren); ressursen velges her. Arket skal kunne henges opp på bilen
  // eller gis til ett korps, og da er resten av vakten bare sider å bla forbi.
  const verktoy = mkUtskriftsverktoy();
  // **Utvalget er en dag** (15. sep. 2026). Filtreringen står her og ikke i
  // dagbolkene, så tallene i arkhodet følger utvalget: skriver man ut lørdag,
  // skal hodet si lørdagens timer og ikke hele vaktas.
  const poster = (aktivListe.vaktposter || [])
    .filter((vp) => utskriftDag == null || _dagnokkel(vp.fra_tid) === utskriftDag);
  if (!poster.length) {
    return `${verktoy}<div class="vl-kort"><div class="vl-tom">Ingen er satt opp ennå.</div></div>`;
  }

  // **Dagen er ytterste nivå** (André, 14. sep. 2026): «oversikten skal bare
  // vise hvem som er på vakt og hvilken ressurs de er på, på dag — ikke silt
  // etter ressurs først og så dag».
  //
  // **Lesemodellen er en annen enn før.** Fram til nå svarte lista på «hvem
  // står på denne bilen, og når» — den som leser sto ved bilen. Snudd svarer
  // den på «hvem er på vakt i dag, og hvor», som er det den som møter om
  // morgenen spør om. Begge er gyldige; dette er et valg om hvem arket er for.
  //
  // Et skift som krysser midnatt står under **startdagen**, ikke under begge
  // og ikke splittet (André, 15. sep. 2026) — `_dagnokkel()` er regelen.
  // Merk at rapportmodulen har landet motsatt for *timer* (§2.2 der):
  // fakturagrunnlag splittes ved midnatt. Det er ikke en motsigelse — der er
  // spørsmålet hvor mange timer, her er det hvem som er til stede — men
  // forskjellen er bevisst og skal ikke «rettes».
  const perRessursDag = (dagposter) => {
    const kart = new Map();
    (aktivListe.ressurser || []).forEach((r) => kart.set(r.id, []));
    dagposter.forEach((vp) => {
      if (kart.has(vp.ressurs_id)) kart.get(vp.ressurs_id).push(vp);
    });
    return kart;
  };

  // ── Radene er **blokker, ikke personer** (André, 16. sep. 2026) ─────────
  //
  // «Ressursfanen som heter Oversikt viser mye av det som allerede er i de
  // respektive ressursfanene. Må være en faktisk oversikt.» Fram til nå sto
  // hver person på sin egen linje med navn, korps, rolle og merknad — altså
  // nøyaktig de fire kolonnene man alt hadde lest i gruppefanen. Arket ble
  // langt, og det svarte ikke på det en oversikt skal svare på: **hvor mange
  // plasser finnes, hvor mange er fylt, og hva koster det i timer.**
  //
  // Navnene er ikke borte — de står i gruppefanen, som er den man arbeider i,
  // og utskrifts-CSS-en er generisk, så et navneark skrives ut derfra.
  //
  // Én rad per ressurs per tidsblokk. Blokken er alt definert av
  // `_tidsblokker()`: skift med *samme* fra–til, ikke overlappende.
  const blokkrad = (ressurs, gruppe, blokk) => {
    const plasser = blokk.poster.length;
    const besatt = blokk.poster.filter((vp) => !vp.ledig).length;
    const ledige = plasser - besatt;
    // **`_sumTimer` og ikke `timer × plasser`.** Probono-skift teller null
    // (11. sep. 2026: timene går, men de er ikke organisasjonens), og et
    // skift uten gyldig spenn teller null. Regner man i stedet lengden ganger
    // antallet, er totalen et annet tall enn budsjettlinja og enn
    // `belastning_per_person` — tre steder som skal si det samme.
    const totalt = _sumTimer(blokk.poster);
    // Tomme celler framfor «0»: en kolonne full av nuller er støy man leser
    // forbi, og det er nettopp de som *ikke* er null man leter etter.
    const ledigcelle = ledige
      ? `<td class="vl-ledigtall">${escHtmlValue(ledige)}</td>` : '<td>—</td>';
    // **Pausene står under tida** (23. sep. 2026) — det er arket som henges
    // opp, og «når har laget pause» er et spørsmål den som møter stiller.
    // Admin kan skjule dem på papiret; på skjermen står de.
    const pausetekst = _pauserFor(ressurs.id, blokk.poster).map(_pausetekst).join(', ');
    const pausemerke = pausetekst
      ? `<span class="vl-meta d-block${escHtmlValue(_pauserPaaUtskrift() ? '' : ' vl-skjul-utskrift')}">pause ${escapeHtml(pausetekst)}</span>`
      : '';
    return `
        <tr class="${escHtmlValue(ledige ? 'vl-har-ledige' : '')}">
          <td class="vl-navn">${escapeHtml(ressurs.navn)}
            <span class="vl-meta">${escapeHtml(gruppe.navn)}</span></td>
          <td class="vl-oversikt-tid">${escapeHtml(_tidsspenn(blokk))}${pausemerke}</td>
          <td class="vl-timer">${escapeHtml(_varighet(blokk))}</td>
          <td class="vl-timer">${escHtmlValue(plasser)}</td>
          <td class="vl-timer">${escHtmlValue(besatt)}</td>
          ${ledigcelle}
          <td class="vl-timer">${escapeHtml(_tall(totalt))} t</td>
        </tr>`;
  };

  const sumrad = (dagposter) => {
    const plasser = dagposter.length;
    const besatt = dagposter.filter((vp) => !vp.ledig).length;
    const ledige = plasser - besatt;
    return `
        <tr class="vl-sumrad">
          <td class="vl-navn">Sum</td>
          <td></td>
          <td></td>
          <td class="vl-timer">${escHtmlValue(plasser)}</td>
          <td class="vl-timer">${escHtmlValue(besatt)}</td>
          <td class="vl-timer">${ledige ? escHtmlValue(ledige) : '—'}</td>
          <td class="vl-timer">${escapeHtml(_tall(_sumTimer(dagposter)))} t</td>
        </tr>`;
  };

  // Rekkefølgen er gruppas, så ressursens — samme som fanene. Ressurser uten
  // skift *den dagen* utelates: en tom rad på papiret er en linje man må
  // lese for å se at det ikke står noe der.
  const ressursdeler = (kart) => _grupperMedRessurser().flatMap((g) =>
    _ressurserIGruppe(g.id)
      .filter((r) => (kart.get(r.id) || []).length)
      .flatMap((r) => _tidsblokker(kart.get(r.id)).map(
        (blokk) => blokkrad(r, g, blokk))));

  // **Dagbolken er en `<section>` med sin egen overskrift.** Utskriften har
  // `break-inside: avoid` på den der det får plass — en dagoverskrift alene
  // nederst på et ark er en side ingen kan bruke.
  const deler = _grupperPaaDag(poster).map((dag) => `
      <section class="vl-dagbolk">
        <h2 class="vl-dagtittel">${escapeHtml(_dagtekst(dag.fra_tid))}</h2>
        <div class="vl-tabellramme">
        <table class="vl-tabell vl-utskrift vl-oversiktstabell">
          <colgroup>
            <col style="width: 28%"><col style="width: 20%"><col style="width: 10%">
            <col style="width: 10%"><col style="width: 10%"><col style="width: 10%">
            <col style="width: 12%">
          </colgroup>
          <thead>
            <tr>
              <th>Ressurs</th><th>Tid</th><th>Timer</th>
              <th>Plasser</th><th>Besatt</th><th>Ledige</th><th>Totalt</th>
            </tr>
          </thead>
          <tbody>${ressursdeler(perRessursDag(dag.poster)).join('')}${sumrad(dag.poster)}</tbody>
        </table>
        </div>
      </section>`);

  const tittel = aktivListe.vaktliste.vakt_navn;
  const spenn = _vaktspenn();
  const antallLedige = poster.filter((vp) => vp.ledig).length;
  const ledigtekst = antallLedige
    ? ` · ${escHtmlValue(antallLedige)} ${escapeHtml(antallLedige === 1 ? 'ledig plass' : 'ledige plasser')}` : '';
  const sumTimer = `${escapeHtml(_tall(_sumTimer(poster)))} t`;
  // Skiftene over hele vakten er de *ulike* vakttidene — samme spenn på
  // samleplassen og på bilen er ett skift, ikke to.
  const vaktTall = _telling(poster, _tidsblokker(poster).length);
  // **Ingen kurve her.** Den står i fanen den gjelder, og to steder å lese
  // den samme kurven er ett for mye. «Oversikt» er utskriftslista, og bare det.
  // Utvalget står i arkhodet, for det er arket som skal si hva det er —
  // «HGSD · Ambulanse 1» — ikke velgeren, som ikke kommer med på papiret.
  const utvalg = _utvalgstekst();
  const utvalgslinje = utvalg
    ? `<div class="vl-utvalg">${escapeHtml(utvalg)}</div>` : '';
  return `${verktoy}
    <div class="vl-kort vl-utskriftsark">
      <div class="vl-arkhode">
        <h2>${escapeHtml(tittel)}</h2>
        ${utvalgslinje}
        <div class="vl-meta">${escapeHtml(spenn)} ·
          ${escapeHtml(vaktTall)} · ${sumTimer}${escapeHtml(ledigtekst)}</div>
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


async function lastBelastning() {
  if (!aktivListe) return;
  const korps = korpsfilter == null ? '' : `?korps=${encodeURIComponent(korpsfilter)}`;
  const res = await apiFetch(
    `/vaktliste/api/vaktlister/${aktivListe.vaktliste.id}/belastning/${korps}`);
  if (!res.ok) return;
  belastning = (await res.json()).data;
  tegn();
}


function _tall(n) {
  // **Ett format for timer, overalt: «8,5», ikke «8.5».** Én desimal, komma
  // som desimaltegn, og uten «,0» på hele tall — «14 t» leses raskere enn
  // «14,0 t» i en kolonne man skummer. Planleggingsfanen skrev «8.5» fram
  // til 11. sep. 2026, mens ressurstabellen skrev «8,5»; André ba om komma.
  const rundet = Math.round(n * 10) / 10;
  return Number.isInteger(rundet) ? String(rundet)
    : rundet.toFixed(1).replace('.', ',');
}


function _kolonneandeler(vekter) {
  // Hele prosenter som summerer til nøyaktig 100, uansett hvor mange
  // kolonner som er med.
  //
  // **Restene fordeles etter størrelse, ikke rekkefølge.** Runder man hver
  // andel for seg, blir summen 98 eller 101 — og med `table-layout: fixed`
  // gir det ingen feilmelding, bare en tabell som er litt gal. Å legge hele
  // resten på den første kolonnen ville i stedet gjort navnekolonnen bredere
  // for hver kolonne som kom til.
  const sum = vekter.reduce((a, b) => a + b, 0);
  if (!sum) return vekter.map(() => 0);
  const raa = vekter.map((v) => (v * 100) / sum);
  const andeler = raa.map((v) => Math.floor(v));
  let rest = 100 - andeler.reduce((a, b) => a + b, 0);
  // Indeksene sortert på hvor mye de tapte på nedrundingen, størst først.
  const koe = raa
    .map((v, i) => ({ i, brok: v - Math.floor(v) }))
    .sort((a, b) => b.brok - a.brok || a.i - b.i);
  for (let k = 0; rest > 0; k += 1, rest -= 1) andeler[koe[k % koe.length].i] += 1;
  return andeler;
}


function _budsjettpost(tall, etikett, klasse = '') {
  // Klassen kommer fra kallstedet og er hardkodet der, men den går inn i et
  // `class`-attributt — og en verdi i et attributt escapes, uansett hvor
  // sikker man er på hvor den kom fra. Det er billigere enn å måtte lese
  // kallstedene på nytt neste gang noen legger til et argument.
  const b = klasse
    ? `<b class="${escHtmlValue(klasse)}">${escapeHtml(_tall(tall))} t</b>`
    : `<b>${escapeHtml(_tall(tall))} t</b>`;
  return `<div>${b}<span class="vl-meta">${escapeHtml(etikett)}</span></div>`;
}


function mkBudsjett() {
  // Vaktas budsjett: taket, det som er satt opp, og timene per dag.
  // `docs/FORSLAG_PLANLEGGERFANE.md` §6.
  //
  // **Står bare for den som ser alle korps.** Tallene er hele vaktas, fordi
  // taket er det — serveren sender `planlegging: null` til alle andre, og
  // da finnes ikke linja. Å tegne en tom ramme i stedet ville sagt «her er
  // noe du ikke får se», som er en dårligere beskjed enn ingen beskjed.
  const p = belastning && belastning.planlegging;
  if (!p) return '';

  // **Taket først eller ikke i det hele tatt.** Uten et tak er «Igjen»
  // meningsløst, og de to andre tallene står like godt alene.
  const harTak = p.timetak !== null && p.timetak !== undefined;
  const tak = harTak ? _budsjettpost(p.timetak, 'tak') : '';
  // `over_taket` regnes på serveren, der taket bor — ikke her. To steder å
  // sammenligne er ett sted for mye, samme grunn som for `langt_skift`.
  const igjen = harTak
    ? _budsjettpost(p.igjen, p.over_taket ? 'over taket' : 'igjen',
                    p.over_taket ? 'vl-advarsel' : '')
    : '';
  // **Probono vises bare når det finnes.** Posten er der for at summen ikke
  // skal utelate noe i stillhet (beslutning 9); står den på null, utelater
  // den ingenting, og da er den bare en post til å lese forbi.
  const probono = p.probono > 0 ? _budsjettpost(p.probono, 'probono') : '';

  const knapp = kanSetteTak()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneTimetak">
         <i class="bi bi-cash-coin me-1"></i>${harTak ? 'Endre tak' : 'Sett tak'}
       </button>`
    : '';

  // **«Mangler folk» er avstanden mellom de to første**, og den er selve
  // arbeidslista: 312 satt opp mot 244 bemannet er 68 timer uten navn.
  // Regnes her fordi den ikke er en ny opplysning, bare en subtraksjon
  // leseren ellers måtte gjøre i hodet.
  const mangler = Math.round((p.satt_opp - p.bemannet) * 100) / 100;
  const manglerPost = mangler > 0
    ? _budsjettpost(mangler, 'mangler folk') : '';

  return `
    <div class="vl-kort vl-belastningshode">
      <div class="vl-noekkeltall">
        ${tak}
        ${_budsjettpost(p.satt_opp, 'satt opp')}
        ${_budsjettpost(p.bemannet, 'bemannet')}
        ${manglerPost}
        ${probono}
        ${igjen}
      </div>
      ${mkDagslinje(p.dager)}
      ${knapp}
    </div>`;
}


function mkDagslinje(dager) {
  // **Timene per dag, uten egne tak** (beslutning 2). Dagene sier hvilken
  // dag som bærer vekten; grensa er fortsatt én, for hele vakta.
  //
  // **Overskriften sier «satt opp per dag» med vilje.** Linja bryter ned
  // `satt_opp`, ikke `bemannet`, og uten etiketten måtte leseren gjette
  // hvilket av de to tallene over den summerer til.
  if (!dager || dager.length < 2) return '';
  const celler = dager.map((d) => `
    <div class="vl-dagtall">
      <b>${escapeHtml(_tall(d.timer))} t</b>
      <span class="vl-meta">${escapeHtml(_dagtekst(d.fra_tid))}</span>
    </div>`).join('');
  return `
    <div class="vl-dagslinje">
      <span class="vl-meta vl-dagslinje-merke">Satt opp per dag</span>
      ${celler}
    </div>`;
}


// **Linjer og vinduer har stabile klient-ID-er, ikke indekser** (15. sep. 2026).
//
// Første utgave adresserte feltene med `data-arg="0:1:fra"` og tok imot
// `(arg, verdi)`. Den signaturen finnes ikke: klikk- og change-delegeringen i
// `portal-utils.js` sender **ett** argument — med mindre elementet bærer
// `data-felt`, og da sender den `(id, felt, verdi)`. Så `verdi` var alltid
// `undefined`, hvert tastetrykk skrev `undefined` inn i tilstanden, og feltet
// ble blankt ved neste tegning. Regelen står i `CLAUDE.md`; jeg skrev koden
// som om den ikke gjorde det.
//
// Feltene bruker nå samme idiom som cellene i ressurstabellen — `data-felt` +
// `data-id` — og ID-en er en stabil teller og ikke en indeks: `splice()` ville
// ellers flyttet adressen til alle radene under den man fjernet.
function _planleggerVindutall(vindu) {
  // Ett vindu er ett skift (`skiftlengde` er borte, 15. sep. 2026), så det
  // som gjenstår er spennet og plassene.
  //
  // **Regnet her bare for å vise tallet mens man skriver.** Fasiten er
  // serverens forhåndsvisning — `planleggerfasit` — og den hentes før noe
  // genereres. To steder å regne er ett sted å komme i utakt, så dette er
  // bevisst den *uforpliktende* siden.
  const fra = _d(vindu.fra);
  const til = _d(vindu.til);
  const plasser = Math.max(1, Number(vindu.plasser) || 1);
  if (!fra || !til || til <= fra) return { gyldig: false, plasser, timer: 0 };
  const spenn = (til.getTime() - fra.getTime()) / 3600000;
  return { gyldig: true, plasser, timer: spenn * plasser, spenn };
}


function _planleggerLinjetall(linje) {
  // Summen for én linje. Tallet står under raden fordi André tenker i folk
  // («4 stk fordelt på 2 lag») mens modellen trenger plasser per skift, og
  // den oversettelsen skal være synlig før man trykker.
  const antall = Math.max(1, Number(linje.antall) || 1);
  let skift = 0;
  let plasser = 0;
  let timer = 0;
  (linje.vinduer || []).forEach((v) => {
    const t = _planleggerVindutall(v);
    if (!t.gyldig) return;
    skift += 1;
    plasser += t.plasser;
    timer += t.timer;
  });
  return {
    skift: skift * antall,
    plasser: plasser * antall,
    timer: timer * antall,
  };
}


function planleggerTotal() {
  return (planleggerlinjer || []).reduce((sum, linje) => {
    const t = _planleggerLinjetall(linje);
    return {
      ressurser: sum.ressurser + Math.max(1, Number(linje.antall) || 1),
      plasser: sum.plasser + t.plasser,
      timer: sum.timer + t.timer,
    };
  }, { ressurser: 0, plasser: 0, timer: 0 });
}


function _vindutallTekst(t) {
  // Teksten under skiftvinduet, som ren tekst. **Ingen markup**, fordi den
  // også settes med `textContent` når tallene oppdateres uten omtegning —
  // se `planleggerTegnTall()`. To former av samme tekst ville kommet i utakt.
  return t.gyldig
    ? `${_tall(t.spenn)} t · ${_tall(t.timer)} t i alt`
    : 'ugyldig tidsrom';
}


function _gruppeFor(id) {
  return (aktivListe?.grupper || []).find((g) => String(g.id) === String(id))
      || null;
}


function _planleggerVindu(linje, vindu) {
  // **Skiftlengden står som et eget felt, ikke som et valg mellom to
  // former.** Tom = ett skift (Sola 56, 15–03 i ett strekk), et tall = del
  // vinduet (Haugesund 56, 8 timer på og 8 av). Ett felt med to betydninger
  // er her enklere enn to kontroller som utelukker hverandre.
  const t = _planleggerVindutall(vindu);
  const fasitklasse = t.gyldig ? '' : ' vl-advarsel';
  // Det første vinduet kan ikke fjernes — en ressurs uten skiftvindu er
  // ingenting, og serveren avviser det. En knapp som fører til en vegg er
  // verre enn ingen knapp.
  const slett = linje.vinduer[0] !== vindu
    ? `<button type="button" class="btn btn-sm btn-outline-secondary"
               data-action="planleggerFjernVindu" data-id="${escHtmlValue(vindu.id)}"
               title="Fjern skiftvinduet">
         <i class="bi bi-x-lg"></i>
       </button>`
    : '';
  return `
    <div class="vl-pl-vindu">
      <label class="vl-meta">Fra
        <input type="datetime-local" class="form-control form-control-sm"
               step="300" value="${escHtmlValue(_iso16(vindu.fra))}"
               data-action="planleggerSettVindu" data-hendelse="change"
               data-felt="fra" data-id="${escHtmlValue(vindu.id)}"></label>
      <label class="vl-meta">Til
        <input type="datetime-local" class="form-control form-control-sm"
               step="300" value="${escHtmlValue(_iso16(vindu.til))}"
               data-action="planleggerSettVindu" data-hendelse="change"
               data-felt="til" data-id="${escHtmlValue(vindu.id)}"></label>
      <label class="vl-meta">Plasser
        <input type="number" class="form-control form-control-sm" min="1" step="1"
               value="${escHtmlValue(vindu.plasser)}"
               data-action="planleggerSettVindu" data-hendelse="change"
               data-felt="plasser" data-id="${escHtmlValue(vindu.id)}"></label>
      <span class="vl-meta vl-pl-vindutall${fasitklasse}"
            data-vindutall="${escHtmlValue(vindu.id)}">${escapeHtml(_vindutallTekst(t))}</span>
      ${slett}
    </div>`;
}


function _planleggerStaar(linje) {
  // **En rad som peker på en ressurs redigerer den**, og ser derfor annerledes
  // ut enn en rad som lager en ny: navnet står der nedtrekket ellers står.
  //
  // Formen er hele forklaringen på hva raden gjør. Med et gruppenedtrekk på
  // en rad som alt har en ressurs, ville man trodd man kunne flytte bilen til
  // en annen gruppe herfra — og serveren leser gruppa fra ressursen, så
  // valget hadde ikke gjort noe. Omdøping og gruppebytte hører hjemme i
  // «Rediger ressurs», der sletting og enhetskobling alt ligger.
  return linje.ressurs_id != null;
}


function _planleggerHode(linje) {
  if (_planleggerStaar(linje)) {
    const gruppe = _gruppeFor(linje.gruppe_id);
    const gruppenavn = gruppe ? gruppe.navn : '';
    return `
        <span class="vl-navn vl-pl-navn">${escapeHtml(linje.navn || '')}</span>
        <span class="vl-meta vl-pl-eneste">
          <i class="bi bi-check2-circle me-1"></i>${escapeHtml(gruppenavn)} · står på lista
        </span>
        <span class="vl-pl-spacer"></span>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                data-action="planleggerFjernLinje" data-id="${escHtmlValue(linje.id)}"
                title="Ta raden ut av oppsettet. Ressursen og plassene blir stående.">
          <i class="bi bi-eye-slash me-1"></i>Ta ut
        </button>`;
  }

  const grupper = (aktivListe.grupper || []).map((g) => {
    const valgt = String(g.id) === String(linje.gruppe_id) ? ' selected' : '';
    return `<option value="${escHtmlValue(g.id)}"${valgt}>${escapeHtml(g.navn)}</option>`;
  }).join('');

  // **«Antall» finnes ikke for grupper som finnes i ett eksemplar** (André,
  // 15. sep. 2026: «for samleplass og KO ble antall forvirrende»). Det kan
  // bare være én, serveren avviser alt annet, og en kontroll som ikke gjør
  // noe er en kontroll man lurer på.
  const gruppe = _gruppeFor(linje.gruppe_id);
  const enEneste = gruppe && gruppe.flere_enheter === false;
  const antallFelt = enEneste ? `
        <div class="vl-meta vl-pl-eneste">
          <i class="bi bi-1-circle me-1"></i>Finnes i ett eksemplar
        </div>` : `
        <label class="vl-meta">Antall
          <input type="number" class="form-control form-control-sm" min="1" step="1"
                 value="${escHtmlValue(linje.antall)}"
                 data-action="planleggerSettLinje" data-hendelse="change"
                 data-felt="antall" data-id="${escHtmlValue(linje.id)}"></label>`;

  return `
        <label class="vl-meta">Gruppe
          <select class="form-select form-select-sm"
                  data-action="planleggerSettLinje" data-hendelse="change"
                  data-felt="gruppe_id" data-id="${escHtmlValue(linje.id)}">${grupper}</select></label>
        ${antallFelt}
        <span class="vl-pl-spacer"></span>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                data-action="planleggerFjernLinje" data-id="${escHtmlValue(linje.id)}">
          <i class="bi bi-trash me-1"></i>Fjern
        </button>`;
}


function _planleggerPause(linje) {
  // **Pauseregelen** (André, 23. sep. 2026: «regel i planleggeren — nå»).
  // «30 min etter 4 t» i hvert skiftvindu som er langt nok. **Forskjøvet**
  // er standard: tre lag som starter 14:00 tar pause 18:00, 18:30 og 19:00,
  // ikke alle tre samtidig. Et skift for kort til regelen får ingen pause.
  const etterT = linje.pause_etter_min === '' || linje.pause_etter_min == null
    ? '' : Number(linje.pause_etter_min) / 60;
  const forskyv = linje.pause_forskyv !== false;
  return `
      <div class="vl-pl-pause">
        <label class="vl-meta"><i class="bi bi-cup-hot me-1"></i>Pause (min)
          <input type="number" class="form-control form-control-sm" min="5" step="5"
                 value="${escHtmlValue(linje.pause_min ?? '')}" placeholder="ingen"
                 data-action="planleggerSettLinje" data-hendelse="change"
                 data-felt="pause_min" data-id="${escHtmlValue(linje.id)}"></label>
        <label class="vl-meta">etter (timer)
          <input type="number" class="form-control form-control-sm" min="0" step="0.5"
                 value="${escHtmlValue(etterT)}"
                 data-action="planleggerSettLinje" data-hendelse="change"
                 data-felt="pause_etter_min" data-id="${escHtmlValue(linje.id)}"></label>
        <label class="vl-meta">Lagene
          <select class="form-select form-select-sm"
                  data-action="planleggerSettLinje" data-hendelse="change"
                  data-felt="pause_forskyv" data-id="${escHtmlValue(linje.id)}">
            <option value="1"${forskyv ? ' selected' : ''}>forskjøvet</option>
            <option value="0"${forskyv ? '' : ' selected'}>samtidig</option>
          </select></label>
      </div>`;
}


function _planleggerLinje(linje) {
  const t = _planleggerLinjetall(linje);
  const vinduer = (linje.vinduer || [])
    .map((v) => _planleggerVindu(linje, v)).join('');

  return `
    <div class="vl-kort vl-pl-linje">
      <div class="vl-pl-topp">${_planleggerHode(linje)}</div>
      <div class="vl-pl-vinduer">${vinduer}</div>
      ${_planleggerPause(linje)}
      <div class="vl-pl-bunn">
        <button type="button" class="btn btn-sm btn-outline-secondary"
                data-action="planleggerNyttVindu" data-id="${escHtmlValue(linje.id)}">
          <i class="bi bi-plus-lg me-1"></i>Nytt skiftvindu
        </button>
        <span class="vl-meta vl-pl-regnestykke"
              data-linjetall="${escHtmlValue(linje.id)}">${escapeHtml(_planleggerRegnestykke(linje, t))}</span>
      </div>
    </div>`;
}


function _planleggerRegnestykke(linje, t) {
  // «2 skift × 1 ressurs = 12 plasser, 96 t». Skrevet ut som et regnestykke
  // og ikke bare som summen: den som leser skal kunne se hvilket ledd som er
  // feil når tallet ikke stemmer med det hun tenkte.
  //
  // **Plassene står ikke som et ledd lenger**, fordi de kan være ulike fra
  // vindu til vindu. Hvert vindu viser sitt eget tall; raden viser summen.
  const antall = Math.max(1, Number(linje.antall) || 1);
  if (!t.skift) return 'Fyll ut et gyldig tidsrom.';
  const skiftord = t.skift === 1 ? 'skift' : 'skift';
  const ledd = antall > 1
    ? `${_tall(t.skift / antall)} ${skiftord} × ${_tall(antall)} ressurser`
    : `${_tall(t.skift)} ${skiftord}`;
  return `${ledd} = ${_tall(t.plasser)} plasser, ${_tall(t.timer)} t`;
}


function mkPlanlegger() {
  // **Planleggeren lager grunnlaget for vaktlista** (André, 15. sep. 2026).
  // Du sier «tre firemannslag 14–22, én ambulanse 15–03, én på åttetimers
  // rotasjon», og etterpå finnes ressursene og de tomme plassene — klare til
  // å fordeles og spisses i fanene som alt virker.
  //
  // Budsjettlinja står her, ikke i «Planlegging»: «sette inn total timer og
  // jobbe overordnet» er planleggerens verktøy, og den som bemanner sitt eget
  // korps har ikke bruk for vaktas budsjett.
  if (!kanPlanlegge()) {
    return '<div class="vl-kort"><div class="vl-tom">Planleggeren er for '
         + 'vaktledere og administratorer.</div></div>';
  }

  const total = planleggerTotal();
  const linjer = (planleggerlinjer || []).map(_planleggerLinje).join('');

  // **Uten starttid på vakta har standardvinduene ingenting å bygge på.**
  // Da faller de tilbake til nå, og «dagens dato» ser ut som et valg noen har
  // tatt framfor et fravær. Beskjeden står over oppsettet og peker dit man
  // retter det.
  const utenStart = _d(aktivListe?.vaktliste?.startet) ? '' : `
    <div class="vl-kort"><div class="vl-tom">
      <i class="bi bi-exclamation-triangle me-1"></i>Vakten har ingen
      <strong>starttid</strong>. Skiftvinduene fylles derfor ut med dagens dato.
      Sett starten under «Innstillinger» først, så treffer de.
    </div></div>`;

  const tomt = planleggerlinjer.length ? '' : `
    <div class="vl-kort"><div class="vl-tom">
      Legg til en ressurs for å begynne. Et lag på fire som går 14–22 er én
      rad med ett skiftvindu. En samleplass med seks på dagtid og to om natta
      er én rad med to vinduer — og et nytt vindu begynner der det forrige
      sluttet.
    </div></div>`;

  // **Tallene er oppsettet, ikke endringen.** Panelet viser hva lista skal
  // være når du er ferdig; hva som faktisk blir laget og fjernet står i
  // bekreftelsen, som er stedet beslutningen tas. Sto endringen her, ville
  // «tomme plasser» talt ned mot null etter hvert som du genererte — og et
  // tall som går mot null mens oppsettet blir større er ikke til å lese.
  const staaende = (planleggerlinjer || []).filter(_planleggerStaar).length;

  const oppsummering = planleggerlinjer.length ? `
    <div class="vl-kort vl-belastningshode">
      <div class="vl-noekkeltall">
        <div><b data-plantall="ressurser">${escHtmlValue(total.ressurser)}</b><span class="vl-meta">ressurser</span></div>
        <div><b data-plantall="plasser">${escHtmlValue(total.plasser)}</b><span class="vl-meta">plasser</span></div>
        <div><b data-plantall="timer">${escapeHtml(_tall(total.timer))} t</b><span class="vl-meta">til sammen</span></div>
      </div>
      <span class="vl-pl-spacer"></span>
      <button type="button" class="btn btn-primary" id="planlegger-knapp"
              data-action="apneGenerer">
        <i class="bi bi-magic me-1"></i>Lag grunnlaget
      </button>
    </div>` : '';

  // **«Legg til ressurs» står mellom siste ressurs og «Lag grunnlaget»**
  // (André, 15. sep. 2026: «for nå er det lett å tro at man bare lager en
  // ressurs og så er man ferdig»).
  //
  // Den sto først i hodet, over radene. Der leser den som «start her» — og
  // når du har laget den ene raden, er neste ting du ser generer-knappen.
  // Mellom radene og knappen leser den i stedet som «legg til én til», og
  // rekkefølgen i panelet blir den man arbeider i: sett opp, legg til flere,
  // og til slutt lag grunnlaget.
  const leggTil = `
    <div class="vl-pl-legg-til">
      <button type="button" class="btn btn-outline-secondary"
              data-action="planleggerNyLinje">
        <i class="bi bi-plus-lg me-1"></i>Legg til ressurs
      </button>
    </div>`;

  const staarTekst = staaende ? `
      <span class="vl-meta">${escHtmlValue(staaende)} av radene står allerede
        på lista og blir <strong>rettet</strong>, ikke laget på nytt.</span>` : '';

  return mkBudsjett() + `
    <div class="vl-kort vl-kort-topp">
      <span class="vl-kort-tittel">Oppsett</span>
      <span class="vl-meta">Én rad per ressurs. Plassene fødes som
        <strong>planlagt</strong> — usynlige for korpsene til du deler dem ut.</span>
      ${staarTekst}
    </div>` + utenStart + linjer + tomt + leggTil + oppsummering;
}


function mkBelastning() {
  // **Belastningen før vakten, ikke bemanningen** (§8b). Bemanningskurvene
  // svarer på «er plassene fylt»; denne svarer på «hva koster det dem som
  // fyller dem».
  //
  // **Varsler, ikke sperrer.** Ingenting her nekter noe — et langt skift
  // merkes, og det er alt. Noen ganger *må* noen ta et langt skift, og da
  // skal lista si det høyt framfor å tvinge planleggeren til å lyve om
  // tidene for å komme videre.
  if (!belastning) {
    return '<div class="vl-kort"><div class="vl-tom">Regner\u2026</div></div>';
  }
  const s = belastning.sammendrag;
  const g = belastning.grenser;

  // Hvert ledd heves ut i sin egen variabel framfor å stå som en ternær med
  // en template-literal inni en annen: den formen er vanskelig å lese, og
  // XSS-skanneren i `tests_xss.py` kan ikke se inn i den.
  const varsel = (antall, tekst) => antall
    ? `<div class="vl-varseltall"><span class="vl-varselantall">${escHtmlValue(antall)}</span>
         <span class="vl-meta">${escapeHtml(tekst)}</span></div>`
    : '';
  const langeSkift = varsel(s.lange_skift, `skift over ${g.maks_skift_timer} t`);
  const korteHviler = varsel(s.korte_hviler, `hviler under ${g.min_hvile_timer} t`);
  // **Overlappet har ingen grense å måle mot, og det er poenget.** Et langt
  // skift er en vurdering — organisasjonen setter hvor grensen går. To skift
  // på samme person samtidig er en planleggingsfeil uansett hva grensene
  // sier, og teksten sier derfor timene framfor en terskel.
  const overlappVarsel = varsel(
    s.overlappende_personer,
    s.overlappende_personer === 1
      ? `dobbeltbooket — ${_tall(s.overlapp)} t`
      : `dobbeltbooket — ${_tall(s.overlapp)} t til sammen`);
  const ingenVarsler = (!s.lange_skift && !s.korte_hviler && !s.overlappende_personer)
    ? '<span class="vl-meta">Ingen varsler</span>' : '';
  const grenseknapp = kanLede()
    ? `<button class="btn btn-sm btn-outline-secondary" type="button"
               data-action="apneGrenser">
         <i class="bi bi-sliders me-1"></i>Grenser
       </button>`
    : '';

  // **Budsjettlinja står i «Planlegger», ikke her** (15. sep. 2026). Den
  // ble først lagt i denne fanen; André: «Jeg ba om en planlegger … Den skal
  // bare admin og leder ha tilgang til.» Vaktas budsjett er lederens
  // verktøy, og denne fanen er `les` — lista regnet sammen, for alle som ser
  // den.
  const hode = `
    <div class="vl-kort vl-belastningshode">
      <div class="vl-noekkeltall">
        <div><b>${escHtmlValue(s.personer)}</b><span class="vl-meta">personer</span></div>
        <div><b>${escHtmlValue(s.skift)}</b><span class="vl-meta">skift</span></div>
        <div><b>${escapeHtml(_tall(s.timer))}</b><span class="vl-meta">timer totalt</span></div>
        <div><b>${escHtmlValue(s.ledige_plasser)}</b><span class="vl-meta">ledige plasser</span></div>
      </div>
      <div class="vl-varsler">
        ${langeSkift}${korteHviler}${overlappVarsel}${ingenVarsler}
      </div>
      ${grenseknapp}
    </div>`;

  if (!belastning.personer.length) {
    return hode + '<div class="vl-kort"><div class="vl-tom">Ingen er satt '
         + 'opp på vakten ennå. Tallene fylles ut etter hvert som plassene '
         + 'bemannes.</div></div>';
  }

  // Faktisk-kolonnen står bare når det finnes noe å vise. I planlegging er
  // den tom for alle, og en kolonne med bare streker er en kolonne som
  // stjeler bredde fra dem som betyr noe.
  const harFaktisk = belastning.personer.some((r) => r.faktiske_timer !== null);
  // Samme regel som Faktisk-kolonnen: en kolonne der alle rader står på
  // null stjeler bredde fra dem som betyr noe. Og i den normale lista er
  // det nettopp null for alle — overlapp er unntaket, ikke tilstanden.
  const harOverlapp = belastning.personer.some((r) => r.har_overlapp);

  const merket = (paa) => (paa ? 'vl-advarsel' : '');
  const strek = '<span class="vl-meta">—</span>';

  const rader = belastning.personer.map((r) => {
    const hvileklasse = merket(r.kort_hvile);
    const hvile = r.korteste_hvile === null ? strek
      : `<span class="${hvileklasse}">${escapeHtml(_tall(r.korteste_hvile))} t</span>`;
    const lengsteklasse = merket(r.langt_skift);
    const lengste = `<span class="${lengsteklasse}">${escapeHtml(_tall(r.lengste_skift))} t</span>`;
    const faktiskTall = r.faktiske_timer === null
      ? strek : `${escapeHtml(_tall(r.faktiske_timer))} t`;
    const faktisk = harFaktisk ? `<td>${faktiskTall}</td>` : '';
    // Streken framfor «0 t» på radene uten overlapp: null er her det
    // normale, og en kolonne full av nuller drukner den ene raden som
    // faktisk har et tall.
    const overlappTall = r.har_overlapp
      ? `<span class="vl-advarsel">${escapeHtml(_tall(r.overlapp))} t</span>` : strek;
    const overlapp = harOverlapp ? `<td>${overlappTall}</td>` : '';
    return `
      <tr>
        <td class="vl-navn">${escapeHtml(r.navn)}</td>
        <td>${escapeHtml(r.korps_kort)}</td>
        <td>${escHtmlValue(r.antall_skift)}</td>
        <td><b>${escapeHtml(_tall(r.timer))} t</b></td>
        ${faktisk}
        <td>${lengste}</td>
        <td>${hvile}</td>
        ${overlapp}
      </tr>`;
  }).join('');

  const faktiskHode = harFaktisk ? '<th>Faktisk</th>' : '';
  const overlappHode = harOverlapp ? '<th>Overlapp</th>' : '';
  // **Andelene regnes, de skrives ikke av.** To valgfrie kolonner gir fire
  // former, og fire håndskrevne `<colgroup>`-blokker er fire steder å
  // glemme når en kolonne kommer til — den femte formen ville fått feil
  // antall `<col>`, og `table-layout: fixed` deler da resten likt uten å
  // feile. Vektene er de samme tallene som sto der før; `_kolonneandeler()`
  // normaliserer dem til hele prosenter som summerer til 100.
  const vekter = [27, 11, 9, 15];
  if (harFaktisk) vekter.push(13);
  vekter.push(19, 19);
  if (harOverlapp) vekter.push(13);
  // **Tabellen får ikke krympes under det navnet trenger.** Med
  // `table-layout: fixed` og ingen kolonnebredder delte nettleseren 308 px
  // likt på seks kolonner — 51 px hver, og «Korteste hvile» sto i tre
  // linjer over et tall. André: «veldig tett på mobil». Kolonnene får
  // andeler, og stilarket gir tabellen en gulvbredde så den ruller i ramma
  // på en telefon i stedet for å klemmes.
  const bredder = _kolonneandeler(vekter)
    .map((a) => `<col style="width: ${escHtmlValue(a)}%">`).join('');
  const kolonner = `
          <colgroup>${bredder}</colgroup>`;
  return hode + `
    <div class="vl-kort">
      <div class="vl-kort-topp">
        <span class="vl-kort-tittel">Per person</span>
        <span class="vl-meta">Sortert på timer — den som er i ferd med å bli
          brukt opp ligger øverst</span>
      </div>
      <div class="vl-tabellramme">
        <table class="vl-tabell vl-tabell-belastning vl-utskrift">
          ${kolonner}
          <thead>
            <tr>
              <th>Navn</th><th>Korps</th><th>Skift</th><th>Planlagt</th>
              ${faktiskHode}
              <th>Lengste skift</th><th>Korteste hvile</th>
              ${overlappHode}
            </tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
      </div>
    </div>`;
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
        <div>${escHtmlValue(alle.length)} satt opp på vakten</div>
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


function mkMittKorps() {
  // Prosjektleder, 11. sep. 2026: «Mitt korps som viser alle vaktene som
  // skal dekkes» — «dine tildelte vakter og de vakter som er satt universal
  // tildelt». Ledige først i hver blokk (sorteringen setter tomt navn
  // først), dagoverskrifter som ellers, og det som gjenstår å dekke øverst.
  const korpsId = _mittKorpsId();
  if (korpsId == null) {
    return '<div class="vl-kort"><div class="vl-tom">Velg et korps for å se plassene det har ansvar for.</div></div>';
  }
  const korps = (aktivListe.korps || []).find((k) => k.id === korpsId);
  const korpsnavn = korps ? korps.navn : 'korpset';
  const poster = _synligePoster(aktivListe.alle_vaktposter || aktivListe.vaktposter, korpsId);
  const ledige = poster.filter((vp) => vp.ledig).length;
  const bemannet = poster.length - ledige;
  // Timene, delt slik André leste dem (12. sep. 2026): bemannet er
  // korpsets egne folk, å dekke er de ledige plassene korpset har fått,
  // åpent for alle er dem alle korps kan fylle, probono for seg. Ett samlet
  // «å dekke» leste som at korpset skyldte alle de åpne timene.
  const bemannet_t = _tall(_sumTimer(poster.filter((vp) => !vp.ledig)));
  const dekke_t = _tall(_sumTimer(poster.filter((vp) => vp.ledig && !vp.alle_korps)));
  const aapent_t = _tall(_sumTimer(poster.filter((vp) => vp.ledig && vp.alle_korps)));
  const probono = _tall(poster.reduce((sum, vp) => sum + (vp.probono ? (_skifttimer(vp) || 0) : 0), 0));

  const hode = `
    <div class="vl-kort vl-belastningshode">
      <div class="vl-noekkeltall">
        <div><b>${escHtmlValue(ledige)}</b><span class="vl-meta">${escapeHtml(ledige === 1 ? 'plass å dekke' : 'plasser å dekke')}</span></div>
        <div><b>${escHtmlValue(bemannet)}</b><span class="vl-meta">mannskap satt opp</span></div>
        <div><b>${escapeHtml(bemannet_t)} t</b><span class="vl-meta">bemannet</span></div>
        <div><b>${escapeHtml(dekke_t)} t</b><span class="vl-meta">å dekke for korpset</span></div>
        <div><b>${escapeHtml(aapent_t)} t</b><span class="vl-meta">åpent for alle</span></div>
        <div><b>${escapeHtml(probono)} t</b><span class="vl-meta">probono</span></div>
      </div>
      <span class="vl-meta">${escapeHtml(korpsnavn)} — tildelte plasser og plasser åpne for alle</span>
    </div>`;

  if (!poster.length) {
    return hode + '<div class="vl-kort"><div class="vl-tom">Ingen plasser er tildelt korpset ennå.</div></div>';
  }

  const ressursnavn = {};
  (aktivListe.ressurser || []).forEach((r) => { ressursnavn[r.id] = r; });
  const rad = (vp) => {
    const r = ressursnavn[vp.ressurs_id];
    const hvem = vp.ledig
      ? _fyllValgFor(vp, kanBemannePlass(vp, r)) + _probonoMerke(vp)
      : escapeHtml(vp.navn) + _probonoMerke(vp);
    const tildelt = vp.ledig
      ? (vp.alle_korps ? 'Åpen for alle' : (korps ? (korps.kortnavn || korps.navn) : ''))
      : (vp.korps_kort || '');
    return `
        <tr class="${escHtmlValue(vp.ledig ? 'vl-ledig' : '')}">
          <td class="vl-navn">${escapeHtml(r ? r.navn : '')}</td>
          <td>${hvem}</td>
          <td>${escapeHtml(tildelt || '—')}</td>
          <td>${escapeHtml(vp.rolle || '—')}</td>
          <td>${escapeHtml(vp.merknad || '')}</td>
        </tr>`;
  };
  const rader = _blokkerMedDager(_tidsblokker(poster), 5, rad);
  return hode + `
    <div class="vl-kort">
      <div class="vl-tabellramme">
        <table class="vl-tabell vl-utskrift">
          <colgroup>
            <col style="width: 22%"><col style="width: 30%"><col style="width: 14%">
            <col style="width: 16%"><col style="width: 18%">
          </colgroup>
          <thead>
            <tr><th>Ressurs</th><th>Hvem</th><th>Tildelt</th><th>Rolle</th><th>Merknad</th></tr>
          </thead>
          <tbody>${rader}</tbody>
        </table>
      </div>
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
