# Vaktlisteflaten (templates/vaktliste/)

> **Flatefil.** Den lastes når noen arbeider i `templates/vaktliste/`. Modellene og reglene
> bak — tilgangen, plassen og skiftet, planleggeren, pausene, drift — står i
> `vaktliste/CLAUDE.md`, og rammeverket i `CLAUDE.md` i rota. `static/js/vaktliste-*.js`
> ligger utenfor mappa og laster ingen av dem: les denne før du rører JS-en.

## Planleggingsflatene: dager, kort og faner

Dagen er ytterste nivå, ressursgruppa er fanen, og ressursen er kortet inni.
Rekkefølgen er ikke kosmetikk — den er hva sida svarer på.

- **Utskriftslista grupperes på dag, så ressurs** (15. sep. 2026 — snudd fra
  ressurs-først). Den svarer nå på «hvem er på vakt i dag, og hvor», som er det den som
  møter om morgenen spør om; før svarte den på «hvem står på denne bilen, og når», med
  begrunnelsen at leseren sto ved bilen. Begge er gyldige — dette er et valg om hvem arket
  er for. Korpset er fortsatt en kolonne, og `_skiftrekkefolge()` har `til_tid` som andre
  ledd fordi skift som begynner samtidig ellers står i innsettingsrekkefølge, og et kort
  skift havner midt blant de lange.
- **`_dagnokkel()` er den ene regelen for hvilken dag et skift hører til: startdagen.**
  «fre. 20:00 – lør. 04:00» står under fredag — ikke under begge dager, ikke splittet
  (André, 15. sep. 2026). **Merk at rapportmodulen har landet motsatt for timer**
  (`FORSLAG_RAPPORTMODUL.md` §2.2, splitting ved midnatt): der er spørsmålet hvor mange
  timer, her er det hvem som er til stede. Forskjellen er bevisst og skal ikke «rettes».
  Nøkkelen er nullpolstret fordi den sorteres — `2026-9-15` < `2026-9-4` som tekst.
- **Dagen er ytterste nivå på begge planleggingsflatene** (15. sep. 2026 — André: «i
  ressursgruppene må det være likt som oversikt, ressurser per dag»). `_grupperPaaDag()`
  brukes av «Oversikt» *og* av `_gruppedagbolker()` i gruppefanen; i begge er dagen en
  seksjonsoverskrift og ressurskortene står under den. `mkRessurs(r, apen, egne)` tegner
  derfor **de skiftene den får**, og bruker `_blokkrader` — en dagrad inni kortet ville
  gjentatt tittelen rett over. **`_blokkerMedDager()` er nå bare «Mitt korps»**, som har én
  tabell på tvers av ressursene og altså ingen seksjon å legge dagen i.
- **Utskriftsvelgeren avgrenser til en dag, ikke til en ressurs** (15. sep. 2026).
  `utskriftDag` er en `_dagnokkel()`-streng eller `null` for hele vakta. Ressursvalget ga
  mening da arket var gruppert på ressurs; etter snuingen ville «Ambulanse 1» vært et snitt
  på tvers av det arket er bygget rundt. **En endagsvakt får ingen velger i det hele tatt** —
  ett valg i et nedtrekk er en kontroll som ikke gjør noe; utskriftsknappen står igjen alene.
  Filtreringen skjer **før** tallene regnes, så arkhodet sier den valgte dagens timer og
  ikke hele vaktas.
- **En ressurs uten skift hører til ingen dag, og får bolken «Uten skift».** Uten den ville
  kortet med «Opprett vakt» ikke finnes noe sted, og ingen kunne satt opp den første vakta
  på en ny bil. Bolken vises bare når noen faktisk står uten skift.
- **Rekkefølgen i dagbolken er ressursenes, ikke skiftenes.** `_gruppedagbolker()` leser
  skiftene i serverens rekkefølge (`fra_tid`) og filtrerer så *ressurslista* — samles de per
  ressurs først, er rekkefølgen garantert av hvordan lista ble bygget og ikke av regelen,
  og en mutasjon som fjerner regelen går grønn. Det skjedde 15. sep. 2026.
- **Dagoverskriften vises alltid, også på en endagsvakt** (15. sep. 2026). Fram til da sto
  den bare når vakta spente over mer enn én dag; da måtte planleggeren vite at *fraværet*
  av en dagrad betydde noe, og tabellen skiftet form når vakta ble forlenget.
- **Ressurskortene i gruppefanen kan slås sammen**, og er det som standard når gruppa har
  mer enn én ressurs (André, 14.–15. sep. 2026). Tilstanden ligger i `ressursApen` i
  `vaktliste-kjerne.js`, **ikke i DOM-en** — `mkRessurs()` bygges på nytt ved hvert
  panelbytte, samme grunn til at `gateKnapper()` ikke kan gate den. **Map, ikke Set:**
  fraværende nøkkel betyr «som standarden», så et kort man åpnet ikke slår seg sammen igjen
  når noen legger til en bil i gruppa. Knappene blir stående i hodet på et sammenslått
  kort, og `apneVaktpost()` åpner kortet — ellers lagrer man et skift og ser ingenting
  skje. **Vippa sitter på ressursen, ikke på ressursen-den-dagen**: en bil som står i to
  dagbolker slås sammen begge steder, ellers hadde én ting hatt to tilstander.
  `map(mkRessurs)` sender indeksen som `apen` — den formen var harmløs til byggeren tok
  flere argumenter.
- **Hver enhet er sin egen `Ressurs` inne i gruppa** — bil A, bil B og bil C er tre
  rader i fanen «Ambulanse», hver med egne skift og egen `enhet`-kobling. Modellen var
  riktig fra første stund, men veien dit var usynlig: knappen lå sist i fanerekka og het
  «Ny ressurs». Gruppefanen har derfor et hode med antall enheter og en «Ny
  <gruppe>»-knapp, og ukoblede enheter viser «Ikke koblet» framfor ingenting.
- **Noen grupper finnes i ett eksemplar** (`Ressursgruppe.flere_enheter`, av
  for Samleplass og KO). «Samleplass 2» er ikke en ny samleplass, det er en
  delt vaktliste ingen leser riktig. Den *første* må man fortsatt kunne
  opprette, så plassen tar slutt først når den ene står der.
  `services`-siden er serverens sperre i `ressurser_view`, **per vaktliste** —
  var den global, kunne neste vakt ikke hatt samleplass. Klienten har regelen i
  **én** funksjon, `gruppaHarPlass()`, fordi den har to lesere: knappen i
  gruppehodet og nedtrekket i «Ny ressurs». Skjules bare knappen, kan man
  fortsatt velge gruppa i nedtrekket.
- **«Ny ressurs» spør bare om navn og gruppe.** Reservasjonen ligger på
  plassen og koblingen på den enkelte enheten, så begge settes i «Rediger».
  Skjemaet ba tidligere om dem, og da måtte man svare før man visste svaret —
  det leste som om gruppa *var* enheten. Nedtrekket fylles derfor i
  `apneNyRessurs()`, ikke i `fyllNedtrekk()`: hvilke grupper som har plass
  endrer seg hver gang en ressurs opprettes.
- **Et endepunkt uten flate finnes ikke for brukeren.** `/api/grupper/` sto en dag uten
  UI, og da kunne ingen lage en gruppe som ikke var seedet — samme feil som Django-admin
  ga oss i fase 1. Manageren ligger i «Innstillinger».
- **Fanerekka er tre bolker, ikke én liste** (16. sep. 2026, punkt 5 — André: «de faste
  fanene skal se annerledes ut enn ressursgruppefanene»): faste visninger foran,
  gruppefanene i midten med «Ny ressurs», faste visninger bak, med en `.vl-faneskille`
  mellom. Gruppefanene bærer `.vl-fane-gruppe` — fylt flate og tydeligere kant, **ikke en
  ny farge**: gult varsler, grønt er tilstede og blått er valgt, så en farge til ville
  konkurrert med signaler som alt betyr noe.
  - **De sto flettet i hverandre.** Rekka ble bygget med `push` og så `splice(2, …)` for
    «Mitt korps» og `splice(1, …)` for «Mannskap» — men indeks 2 var regnet mot en liste
    som ennå ikke hadde fått «Mannskap», så «Mitt korps» landet *inne* i gruppeblokka så
    snart det fantes to grupper: `Ambulanse · Mitt korps · Lag`. Ingen test så det, fordi
    ingen leste **rekkefølgen** — bare at hver fane fantes. To slags faner kan ikke gis
    hvert sitt utseende så lenge de står om hverandre.
  - `FanerekkaHarToBolkerTests` pinner hele rekka i sin helhet. En ny fane lagt til feil
    sted blir rød der, ikke oppdaget på staging.
- **Fanen er ressursgruppa, ikke ressursen.** «Ambulanse» er alle ambulansene
  på vakta, med hver bil som sitt eget kort inni (`mkGruppe`). Én fane per bil
  ga ti faner på en vakt med ti biler, og ingen plass der man så dem i
  sammenheng. `aktivFane` bærer derfor en **gruppe-ID**. Det som er per
  ressurs — enhetskobling, reservasjon, roller — blir stående på ressursen.
- **Kurven står i fanen den gjelder** (`mkGruppekurve`), ikke i «Oversikt» —
  og timeaksen har én celle per søyle med samme flex-bredde, så
  klokkeslettet står under sin egen time uansett hvor lang vakta er. Tettheten
  glisner med lengden (`_timesteg`). Den hvite streken i kurven er **midnatt**
  (`vl-dogn`), ikke nåværende tidspunkt; den står i tegnforklaringen fordi en
  strek man må spørre om ikke forklarer noe.
- **Bemanningskurven tegnes per ressursgruppe, over ett felles spenn.** Én samlet kurve
  summerte samleplassen, ambulansene og KO til ett tall som ikke svarer på noe. Spennet er
  felles (`_vaktensSpenn()`) fordi to kurver man ikke kan sammenligne er verre enn én
  samlet.

## Pausene på kortet og i planleggeren (23. sep. 2026)

| Valg | Hvorfor |
|---|---|
| **En linje i hodet på ressurskortet**, ikke rader i tabellen (`_pauselinje`) | Pausen gjelder laget; en rad blant skiftene ville lest som en plass |
| `_pauserFor(id, poster)` viser pausene som **overlapper** kortets skift | Dagbolken skal ikke vise lørdagens pause, og en pause over et skiftbytte skal ikke forsvinne |
| Lederen får brikkene som knapper (`apnePause`) og «+ Pause»; andre ser tekst | En knapp som fører til en vegg er verre enn ingen. Brikkene er ikke `.btn`, fordi utskriften skjuler `.btn` |
| `vl-skjul-utskrift` når admin har skjult pausene, **og** når linja er tom | «Pauser: ingen» på papiret er en linje man må lese for å se at det ikke står noe |
| Planleggeren: «Pause (min) etter (timer)», og et **nedtrekk** for forskjøvet/samtidig (`_planleggerPause`) | «Etter» skrives i timer og sendes i minutter (`_planleggerLinjeverdi`). En avkryssing ville sendt «on» uansett — delegeringen leser `value` |

## Overnatting — skjermen og brannlista (25. sep. 2026)

Reglene står i `vaktliste/CLAUDE.md`; her står flaten. Fila er
`vaktliste-overnatting.js`, og dataene er `aktivListe.overnatting` fra hovedsvaret.

| Valg | Hvorfor |
|---|---|
| **Fanen står i bakre bolk, foran «Timeoversikt»**, og finnes når det er rom — eller når brukeren er leder (`_overnattingsfane()`) | En fane som alltid er tom for den som bare leser, er en fane man slutter å se. Lederen må se den for å sette opp det første rommet |
| **Natta velges med knapper, ikke et nedtrekk** (`_nattvelger`). Standard er natta vi er i, og før klokka tolv natta fra kvelden før (`overnattingStandardnatt`) | En vakt har to–tre netter; alle skal synes. Om morgenen er det fortsatt nattas liste nattevakta står med |
| **Natta sies med morgenens dag**: «Natt til lørdag 03.10» (`overnattingNattTekst`), men lagres som kvelden (fredag) | Det er slik folk sier det. Lagringen følger `_dagnokkel()` |
| **Brannlista tegnes i panelet, men vises bare på papiret** (`mkBrannliste`, `.vl-brannliste` i @media print). Skjermdelen er `d-print-none` | Samme utskriftsmekanikk som resten av siden. Én side per natt, avkryssing per person, rutinen i ramme øverst — og uten rutine en linje å skrive samleplassen på |
| «Brannliste» skriver ut natta som vises; «Alle netter» alle (`skrivUtBrannliste`, `overnattingUtskrift`) | Å skrive ut arkene før vakta er det vanlige; om natta vil man ha ett ark |
| **«Plasser» huker av alle vaktas netter**, og nedtrekket sier hvor personen alt sover den valgte natta | Samme seng hele vakta er det vanlige. 409 gir meldingen og en gul «Flytt hit» — aldri en stille flytting |
| Telleren: **overnatter · på vakt · skal være inne** | «Skal være inne» er tallet man teller mot. Den som står på skift i natta er ikke i rommet |
| «Har vakt dette døgnet, men ingen overnatting» står sammenslått nederst (`overnattingUtenSeng`) | Et hint, ikke en feil — mange sover hjemme. Døgnet er tolv til tolv rundt natta |
| Knappene gates som serveren: rom og rutine på `kanLede()`, «Plasser» på `kanPlassereNoen()`, ✕ per person på `kanPlassereKorps()` | En knapp som fører til en vegg er verre enn ingen |

## Tabeller, tid og felter i grensesnittet

- **En `<td>` må forbli en `table-cell`.** `display: flex` direkte på en celle tar den ut
  av tabellens boksmodell, og alt etter den forskyves i forhold til overskriftene —
  `table-layout: fixed` hjelper ikke. Legg layouten på et element *inne* i cella.
  `TabellcellersLayoutTests` leser klassene som står på `<td>` **hvor som helst** i
  modulens JS og håndhever regelen for dem alle.
  - **Hvitliste, ikke svarteliste** (16. sep. 2026): en `<td>` får ha `display: table-cell`
    eller ingen `display`. Lista sto som fem *farlige* verdier og manglet `inline-block` —
    nøyaktig den `.vl-blokktid` har. En svarteliste må være komplett for å virke; en
    hvitliste er det av seg selv.
  - **Byggerne finnes ved å lete, ikke ved å stå i en liste.** Den håndholdte lista nevnte
    seks byggere, og «Oversikt»-tabellen sto utenfor. Samme forfall som XSS-skanneren hadde
    samme dag.
  - **En klasse som er laget for et element *inne* i cella skal ikke settes på cella.**
    `.vl-tidcelle` har `display: flex` og hører til en `<div>` i regnearkets tidskolonne;
    «Oversikt» har sin egen `.vl-oversikt-tid` uten `display`.
- **Markup som tegnes på nytt kan ikke gates av `gateKnapper()`.** Den setter
  `.d-none` én gang ved sidelasting; `tegnFaner()` og `mkRessurs()` bygger på
  nytt ved hvert panelbytte og må derfor spørre `kanLede()`/`kanBemanne()`
  selv. «Ny ressurs» sist i fanerekka er eksempelet.
- **Handlingskolonnen i ressurstabellen er `position: sticky`.** Tabellen
  ruller under 1280 px, og uten den var rediger-knappen det første som forsvant
  — altså den ene knappen raden finnes for. Bakgrunnen må settes eksplisitt,
  ellers ruller innholdet synlig under den.
- **Kolonnebredde i ressurstabellen er `min-width` + `<colgroup>`-andeler, og
  begge deler betyr noe.** Et `datetime-local`-felt har en gulvbredde nettleseren
  bestemmer; blir kolonnen smalere enn den, stikker feltet ut over nabocella —
  `table-layout: fixed` klipper ikke innholdet. `RessurstabellensBreddeTests`
  regner ut hva tidskolonnene faktisk blir og krever at de rommer feltet, altså
  regelen og ikke tallene.
- **Tidsfeltene er `datetime-local` med `step="300"`.** Fem minutters steg,
  ikke ett — en vakt planlegges ikke på minuttet. Steget må være et multiplum
  av 60, ellers får feltet et sekundsegment. «Opprett vakt» forhåndsutfyller
  fra- og til-feltet med **vaktas start**, ikke `new Date()`: en oktobervakt
  planlegges i august. Et eldre skift på 08:03 vises og leses tilbake som før;
  `step` styrer bare hva velgeren tilbyr, og ingenting leser `checkValidity()`.
- **Et tidsfelt står aldri tomt** (15. sep. 2026 — André: «lik tidsfelt som vi
  har i planleggeren … den i ny vaktliste er litt knotete»). `type` og `step`
  var like fra før; det som skilte «Ny vaktliste» fra planleggeren var at
  feltene startet tomme, og et tomt `datetime-local` må tastes inn segment for
  segment uten noe å nudge på. `apneNyVaktliste()` fyller dem ut **før**
  vinduet vises — derfor åpnes det av JS og ikke av `data-bs-toggle`; et skjema
  som fyller seg selv etterpå ser ut som om noe rettet det man skrev.
  **Starten settes til neste hele time** (`_nesteHeleTime()`): `new Date()` gir
  21:37, og nærmeste lovlige verdi med `step="300"` er 21:35, et tall ingen har
  ment. Planleggeren slipper spørsmålet fordi den har vaktas start å bygge på;
  her *er* feltet vaktas start. **Slutten følger starten til noen rører den**
  (`nyVaktSluttRort`) — samme idé som at et nytt skiftvindu begynner der det
  forrige sluttet, men en rettelse av startdatoen skal ikke spise et sluttidspunkt
  man alt har skrevet. Et tomt sluttfelt teller ikke som rørt. **Spennet leses
  tilbake under feltene** (`nyVaktSpenntekst()`), som tallet under et skiftvindu:
  det er den ene tilbakemeldingen som fanger riktig klokkeslett på feil dato.
  `_varighetstekst()` skriver «2 d 6 t» og ikke «54 t» — et skift er kort nok
  til at timetallet leses, en vakt er det ikke — og hele døgn uten timerest.
- **Tid vises med dag når skiftet krysser et døgn.** `_tidsspenn()` i
  `vaktliste.js` nevner dagen én gang innenfor ett døgn og to ganger ellers —
  «20:00–04:00» alene sier ikke at skiftet går over midnatt, og arrangementer
  varer flere dager. Vaktas spenn utledes av skiftene, ikke av et felt.
- **Vaktlistevelgeren må ha `data-hendelse="change"`** (16. sep. 2026). Uten den fyrer
  klikkdelegeringen i `portal-utils.js` på *klikk* — med verdien som alt sto der — og
  ikke når man velger. Symptomet var «treg»: hvert forsøk på å åpne nedtrekket hentet
  lista man allerede så, og byttet skjedde først ved neste klikk på velgeren.
  `VelgerenFyrerPaaEndringTests` skanner malene: et `<select>` eller `<textarea>` med
  `data-action` skal alltid oppgi hendelsen sin. `<input>` er utenfor med vilje — en
  knapp er et `<input>` også, og der *er* klikk riktig hendelse.
- **Sida kommer tilbake til lista man sto på**, ikke til den øverste
  (`forsteListe()`/`huskListe()`, `localStorage`). ID-en sjekkes mot lista serveren
  faktisk sendte: en vaktliste kan være slettet, eller tilgangen borte, siden sist — og
  da er øverst riktig, som første gang. **Per nettleser, ikke per konto:** det er en
  bekvemmelighet, ikke en innstilling, og «Logg ut» sender `Clear-Site-Data`, som rydder
  den på en delt drifts-PC. Lagringen kaster i privat modus, så begge kallene står i
  `try/catch` — en glemt liste er en bagatell, en side som dør på oppstart er det ikke.

## Frontend — sju filer, og hvor skjøtene går

Hva som lastes når står i rota; hva filene gjør står her. Siden var **én fil på 3 801
linjer** til 14. sep. 2026. Uten bundler deler delene ett globalt navnerom, så delingen er
billig — `core/tests_js_splitt.py` håndhever at ingen funksjon faller mellom to filer,
dupliseres, eller havner i utakt med `<script>`-rekkefølgen i malen.

| Fil | Ansvar |
|---|---|
| `vaktliste-kjerne.js` | Tilstand og regler. **Må lastes først** — all `let`/`const` på toppnivå bor her |
| `vaktliste-tegning.js` | Regnearket: fanene, ressurskortene og radene man redigerer i |
| `vaktliste-oversikt.js` | Oppsummeringene: bemanningskurvene, utskriftslista, belastningen, «Tilstede nå», «Mitt korps» |
| `vaktliste-handlinger.js` | Det som skriver |
| `vaktliste-offline.js` | Service worker og kopien |
| `vaktliste-overnatting.js` | Fanen «Overnatting»: rommene, plasseringene og brannlista på papiret |
| `vaktliste-register.js` | Mannskapsregisteret. **Sist** — `DOMContentLoaded`-kroken står her |

**Skjøten mellom `tegning` og `oversikt` går mellom regnearket og oppsummeringene**
(15. sep. 2026). De leser de samme skiftene og svarer på noe helt annet: det ene er der du
fører, det andre er der du ser hva føringen ble. Skillet er ikke kosmetisk — det er
grunnen til at `tegning` ikke vokser tilbake over 1 800 linjer.

**Siden er én fane per ressursgruppe**, bygget av dataene og ikke av kode: fanene tilpasser
seg vaktas art av seg selv. Hver ressurs er et regneark med redigering i raden. «Oversikt»
er utskriftslista, «Mannskap» er personellregisteret, og roller, grupper, korps og
kompetanser administreres i modaler på siden.

**Vaktlinja (`.vl-vaktvelger`) er tre linjer under 992 px.** Statusmerket slipper `nowrap`
for spennet, og spaceren foran knappene tar hele linja.
