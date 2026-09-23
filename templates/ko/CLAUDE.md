# KO-flaten (templates/ko/)

> **Flatefil.** Den lastes når noen arbeider i `templates/ko/`. Modellene og reglene bak
> — retningen, nivåene, loggen, hendelsene — står i `ko/CLAUDE.md`, og rammeverket i
> `CLAUDE.md` i rota. `static/js/ko-*.js` ligger utenfor mappa og laster ingen av dem:
> les denne før du rører JS-en.

## Vinduene

**Siden har ingen faner, og det er en regel og ikke en smakssak** (André, 17. sep. 2026).
En fane er riktig når flatene er *alternativer*; KOs flater brukes i **én** bevegelse:
sambandet sier noe, du fører linja, du ser hvem som er ledig, og du sender. Og **en skjult
fane er en fane du ikke vet har endret seg**: siden poller, og andres linjer lander i en
rute ingen ser på.

**Formen er fire vinduer i 2×2** (André, 18. sep. 2026, etter åtte skisser som ble avtalt
før koden — de er målet): `Hendelseslogg │ Loggstrøm` øverst, `Ressursoversikt │
Oppdragsliste` nederst. «Tre kolonner er taket» fra 17. sep. ble opphevet av André samme
dag som hendelsene ble en egen flate. Prinsippet — alt synlig samtidig, ingen faner — står.
**Tavla er det femte vinduet og deler plass med ressursoversikten** (22. sep. 2026, `KO_PAR`):
den som ikke står i rutenettet står i stripa, og «⇄» i hodet bytter. **Konsertplanleggeren
er det sjette, og deler plass med oppdragslista** (23. sep. 2026 — André: «inni i ko
rutenettet med samme løsning som tavlen, at den er minimert»): parkert som standard, og da
kan tavla og planleggeren stå side om side i nederste rad. Den het «Planlegger» til runde 2.

**Hvert vindu kan åpnes for seg** (runde 2, André: «Den funksjonaliteten må gjelde alle
vinduer vi har i flaten vår»). Samme side med `?vindu=<navn>` (`koEgetVinduNavn`, bare et
kjent navn), ikke en egen mal — ett sted vinduet tegnes. Der vises bare det vinduet, og
oppsettet **lagres ikke**: det er hovedvinduets. I hovedvinduet skjules det og står i
stripa; det siste synlige blir stående, og står da to steder. Tidslinja synkes mellom
vinduene over `BroadcastChannel('ko-tid')`. **Står en hendelse åpen i loggvinduet, er det
hendelsen som åpnes** (`&hendelse=<id>`, ett nettleservindu per hendelse), og strømmen
står igjen i hovedvinduet — loggen og hendelsen deler vinduet, og ↗ åpnet strømmen til
André sa fra.

**Vinduene bytter plass, endrer størrelse og kan skjules** (`static/js/ko-layout.js`).
Håndtaket dras over et annet vindu for å bytte plass; skillelinjene endrer bredde per rad
og høyden mellom radene. Ikke frie vinduer, med vilje: et vindu som kan legges oppå et
annet kan forsvinne, og gulvet (`KO_MIN_PROSENT`, `min-width`/`min-height`) hindrer at en
flate dras bort. **Skjuling (21. sep. 2026) erstattet forbudet fra 18. sep.** («en ramme
som sperrer for at de kan gjemmes»): et skjult vindu står alltid i stripa over konsollen
med navnet sitt (`#ko-skjulte`), og `koKanSkjule()` nekter det siste synlige — skjult er
da en tilstand man ser. Naboen tar plassen; er begge i en rad skjult, forsvinner raden.
Oppsettet huskes **per nettleser** (`ko.oppsett`), `skjult` med: KO-PC-en beholder sitt
uansett hvem som logger på. `koGyldigOppsett()` leser det som brukerdata og avviser både
et oppsett som mangler et vindu og alle fire skjult.

**Sida ruller ikke — vinduene gjør det.** Høyden **måles** av `koKonsollhoyde()`, ikke
regnet ut av en `calc()`: header, nav og meldinger kan brekke til to linjer. Gulvet
(`KO_MIN_HOYDE`): uten det gir et kort vindu fire ubrukelige rullefelt.

**Knappene står i vinduet de gjelder**: «Ny hendelse» i hendelsesloggen, «Nytt oppdrag»
og «Historikk» i oppdragslista, «Enheter» i ressursoversikten. Verktøylinja har bare det
som gjelder hele sida. Sidebarknappen har `data-bs-toggle="dropdown"` og **ingen**
`data-action` — to lyttere på samme klikk er fella `klikkSkalKjore()` finnes for.

**Under 1200 px stables vinduene** og sida ruller normalt. Akseptert: KO brukes på en
skjerm i et kommandopunkt.

| Regel | Hvor |
|---|---|
| Sidebaren, loggstrømmen og oppstarten i nettleseren | `static/js/ko.js` — siste av fire filer, `KO_JS` |
| Tavla: reglene, byggerne, dra og slipp | `static/js/ko-tavle.js`; modellen og tjenestene i `ko/tavle.py` |
| Hendelsesloggen i nettleseren: tabellen, søket, hendelsen åpnet i vinduet, skjemaet | `static/js/ko-hendelser.js` |
| Rutenettet: bytte plass, skillelinjer, oppsettet i `localStorage` | `static/js/ko-layout.js` |
| «Vis»-menyen over ressurslista | `oppdaterSynlighetsmeny()` i `static/js/oppdrag-kort.js`, `templates/oppdrag/_synlighetsmeny.html` |
| Vaktlistas ressurser uten enhet | `vaktliste.services.ressurser_uten_enhet`, `koRessurskort()` i `ko.js` |

## Hendelsesloggen og loggstrømmen i nettleseren

**Sortering er oppdragslistas** (`koSorterHendelser`): lukkede nederst, prioritet, nummer.
**Søket** filtrerer lista som alt er hentet (nummer, tittel, sted, melder, logg, lag).
**Hendelsen åpnes i loggstrømmens vindu** (André, 21. sep. 2026), ikke i en modal og ikke
over lista: oversikten skal stå mens én hendelse er åpen. Strømmen og skrivefeltet
skjules imens (`koVisStrommen`; `les` får ikke feltet tilbake); raden vipper
(`koVippHendelse`), merkene i strømmen åpner bare. **Loggstrømmen viser linjene uten
hendelse pluss systemlinjene om hendelsene** (`koIStrommen`); kommentarene står i hendelsen.
Utskriften skal ha alt (TODO). **Alle | Meldinger | System** filtrerer strømmen
(`koLoggfilterTreffer`, huskes per nettleser); **festede står uansett**, og hodet teller
det filtrerte.

**KO-innstillinger er sentralbordets valgliste-modal med en fane til**, lagt inn gjennom
`verdifaner_ekstra` i konteksten og `window.VERDIFANER_EKSTRA` — en generell krok, ikke en
KO-referanse: oppdragsmodulen kjenner fortsatt ikke `ko`. Hver fane har sin egen dør
(`kan_lede` for oppdragsmodulens, `kan_lede_ko` for ansvarsområdene).

## Ressursoversikten (pulje 6)

**«Vis»-menyen avgjør hva som står** (23. sep. 2026, André: «istedenfor minimer som tar
plass … en synlighetsknapp»). Den erstattet to ting: minimerbare gruppeoverskrifter
(pulje 6) og Alle | Biler | Lag. Én avkrysning per gruppe, under seksjonene «Biler» og
«Lag» — seksjonen er den gamle snarveien. **En skjult gruppe tar null plass, men det skjulte
synes:** knappen bærer «· N skjult» (ressurser, ikke grupper) og er gul så lenge noe er
skjult. `tavle.grupper.skjult` per nettleser, nøkler `type:<id>` og `gruppe:<id>`; felles
for `/oppdrag/` og `/ko/`. Menyen bor i `oppdrag-kort.js`; vaktlistas grupper meldes inn av
`koSynlighetsgrupper()`, og `ko.js` kaller menyen gjennom en vakt (`koOppdaterSynlighet`) —
`oppdrag-kort.js` lastes bare med oppdragstilgang.

**Vaktlistas ressurser uten oppdragsenhet står på tavla** — lag, samleplass, KO — under
enhetslista i egen beholder (`#vaktliste-ressurser`; sentralbordet tegner `#enhetsliste`
om igjen ved hver poll). Fra `/vaktliste/api/ressurser/uten-enhet/`, gatet av vaktlista,
**bare ressurser med et skift som dekker nå** (`ressurser_paa_vakt_naa`, samme regel som
lagvelgeren) — tegnet av `koRessurskort()`: hvor mange som er møtt, og «På H14 · Hovedscene
· 23 min» når laget står på en åpen hendelse; biler viser oppdragets sted. «i» folder ut
fargeforklaringen (`ko.legende`); kolonneknappen gir to kolonner **inne i hver gruppe** — gruppene står under hverandre
(`ko.ressurskolonner`; 23. sep. 2026, «det overlappes litt»: CSS-`columns` med udelelige grupper
la alle lagene i én kolonne, og et rutenett fragmenterer ikke). Oppdragslistas hode teller aktive · ferdig (historikken
med); «Oppdrag uten ressurs» og «Tildelt» filtrerer, ett om gangen (`koOppdragFilter`).
**Besetningen — navn, møtt, telefon, ISSI — står bak et klikk**, én om gangen som bilens.

## Sentralbordet kjører i `/ko/` (pulje 4)

**KO laster `oppdrag-sentral-*.js` og treffer `/oppdrag/api/…`.** Ressurslista, oppdragslista,
verktøylinja, modalene og alle handlingene er oppdragsmodulens egne — samme kode, samme
endepunkter, samme sperrer. Det er en flytting, ikke en kopi.

**Og det er slik feature parity holder** (André, 17. sep. 2026: «Jeg vil ha det likt
feature messig inn her i /ko») — ved konstruksjon, ikke ved flid.
`ko/tests_sentralbord.py` håndhever at KO får **hele** konteksten, at begge sidene laster
**alle** sentralbordfilene i samme rekkefølge (fasit `OPPDRAG_SENTRAL_JS`), og at de har
de samme flatene.

Delt: `oppdrag.views.sentralbordkontekst()`, malbitene
`_sentralbord_{modaler,skript,oppsettvarsel}.html` og `oppdrag-kort.js`. `/ko/` har sin
egen verktøylinje; `_sentralbord_verktoy.html` er `/oppdrag/` sin.

**Oppdragsflata gates av `oppdrag`-modulen, ikke av `ko`** (André, 18. sep. 2026). Det er
komposisjonsregelen fra rollemodellen §5 — samme som `kan_se_besetning` bruker for vaktlista:
KO *viser* oppdragsmodulens data, og hvem som får se dem er oppdragsmodulens sak.
`kan_se_oppdrag` avgjør om flata tegnes i det hele tatt; `kan_skrive` og `kan_lede` avgjør
knappene, og begge er oppdragsnivåer.

**En KO-operatør trenger derfor to rader:** `ko` for loggen og `oppdrag` for oppdragene.
Egne KO-nivåer foran de samme endepunktene ville lagt tilgangsmodellen to steder.

**KO har ingen egne oppdragsendepunkter.** `/ko/api/ressurser/` fantes en dag og er borte:
den gatet oppdragsdata på `ko:les`, og to pollere mot samme `#enhetsliste` blir uenige.

**Loggen er fortsatt KOs egen**, og `ko:les` alene gir den. Uten oppdragstilgang ser
operatøren loggen og en beskjed om hva som mangler — ikke en tom kolonne.

## Tavla (22. sep. 2026)

Lokasjonene som rader, tida som kolonner, lagene i rutene — tavla på veggen i KO. Hva den
eier og hvor reglene står: `ko/CLAUDE.md`. Her er flaten.

| Valg | Hvorfor |
|---|---|
| **Pekerhendelser, ikke HTML5-dra** | HTML5-dra virker dårlig på nettbrett. Under `KO_TAVLE_DRAGRENSE_PX` er et trykk et klikk |
| **Klikk laget, så raden** — og Enter, og Esc | Samme handling for den som ikke kan dra. `koTavleKlikk` er den ene inngangen |
| **Klikket etter et drag svelges** (`koTavleSvelgKlikk`) | Det lander på felles forelder og ville ellers valgt noe |
| Bare `koTavleKanDras` får `data-dras` | En knapp som fører til en vegg er verre enn ingen knapp — `les` og de opptatte får ingen |
| **¼ før nå som standard** (`koTavleVindu`, `andel_bak` fra KO-leder); var ⅔ til runde 2 | «se lenger frem i tid enn bakover» (André) |
| **Ett tidsvindu for tavla og konsertplanleggeren**: `koTidAnker` er starten når noen har rullet, `null` følger nå. ◀ Nå ▶ (`koTidNyttAnker`, `steg_min`), dra på aksen (`[data-tid-akse]`, `koTidEtterDrag`). Nå utenfor gir «Du ser ikke nå · Tilbake til nå», og ingen nå-strek klemt til kanten | «går jeg frem i tid på planleggeren, skjer det samme med tavlen». Ikke i `localStorage`: en fane som lastes, følger nå |
| Stolpene **vokser framover** fra starten til `max(72px, …)`; den åpne ligger over sin stiplede slutt | Til runde 2 vokste de bakover, og navnet sto «i fortid» |
| **Ingen `min-width` på rutenettet** | Tavla står ofte i den smale plassen; rullet tidslinja vannrett, forsvant nå-streken |
| Poller hvert 15. s **bare når den står framme**, tegner nå-streken hvert minutt | `koTegnOppsett` kaller `koTavleSynligNaa`, så en tavle som hentes fram viser nå |
| Filteret er vaktlistas ressursgrupper, huskes per nettleser (`ko.tavle.filter`) | Gruppene finnes alt; fire faste valg ville vært en taksonomi til |
| **Et klikk er en flytting når et lag er valgt**; ellers åpner det skjemaet til en planlagt pause eller en lukket plassering. Den åpne rettes fra «Rett tidene» i linja over | `koTavleKlikk` — rekkefølgen er regelen. En knapp (`data-action`) velger aldri noe |
| **Retting er et skjema, ikke et dra i kanten** (skisse 3). Klokkeslett, ikke dato: `koTavleTidNaer` gir nærmeste tidspunkt rundt det som rettes | Et feildrag på en travel tavle skal ikke flytte historikken stille; «20:00» på en vakt over midnatt betyr nesten alltid den nærmeste |
| «Til» er låst på den åpne og der en hendelse tok over (`koTavleSkjemaData`) | Hendelsen eier tida videre |
| Et åpent skjema tegnes ikke om av pollen | Ellers tømmes feltet under fingrene |
| **«+ Planlegg» i hver rad** (runde 2): stiplet i raden den skal til — Pause-raden eller stedet. «Pause nå»/«Flytt nå» fra ti minutter før (`koTavlePauseStatus`), på stolpen og kortet i «Uten plass». Lagene er hele vaktlista (`alle_ressurser`), biler bare på et sted; klokkeslettene leses nær der tidslinja står (`ref`) | KO trykker; tavla flytter ingen. Rød kant når tida gikk |
| Vaktlistas pause har id `v<pk>` — `koTavlePauseRef()` leser begge formene; `title` sier «fra vaktlista» eller «endret i drift» (prikket kant) | `Number('v12')` er NaN, og da åpnet klikket ingenting |
| **Planlagt slutt**: stiplet fra nå til slutten (`koTavleSluttHtml`), klikk åpner skjemaet; ute av tida gir rød kant, «N min over» og «N over» på raden. `koTavleSlutt` er regelen. Feltet står i «Tider og slutt» for den åpne, og tomt er ingen plan | Overtid er et tegn, ikke en handling. Den stiplede holder banen, så neste stolpe ikke legges oppå |
| **«Besøk»** er en visning i samme vindu, regnet i nettleseren av vaktas plasseringer (`koTavleBesok`). Døgnet fra døgnstarten; nuller øverst på et fulgt sted | Alt ligger alt i svaret — ingen egen spørring å holde i takt |
| «Ikke vært på \<fulgt sted\>» under tavla (`koTavleIkkeVaert`) | «Hvem skal få gå neste» uten å åpne noe |
| Fanen «Tavla» i KO-innstillinger tegnes av `koTegnTavleOppsett` gjennom kroken `tegn` | Oppdragsmodulens JS kjenner ikke KO |

**Gaten er komposisjonsregelen**: tavla krever `les` i vaktlista (403 ellers), bilene
bare med `les` i oppdragsmodulen — både i svaret og ved flytting (404: en bil man ikke får
se, finnes ikke). Flytting er `skriv_full` i KO.

## Konsertplanleggeren og programmet på tavla (23. sep. 2026)

`static/js/ko-plan.js`, vinduet `plan`. Reglene i `ko/program.py` (se `ko/CLAUDE.md`).
**Tidslinja er tavlas** (`koTidVindu`) fra runde 2; døgnknappene er borte, og «Liste»
viser hele programmet døgn for døgn (`koPlanDognListe`).

| Valg | Hvorfor |
|---|---|
| **Døgnet og klokkeslettet, ikke dato-og-tid**: `koPlanTid` legger et klokkeslett før døgnstarten i natta etter; `koTavleTilEtter` er første gang klokka viser «til» etter «fra» | «01:00 fredag» er natt til lørdag, som i «Besøk». 22:00–22:00 er et døgn, ikke null |
| Skjemaets døgnvalg: noen døgn fra vaktstart, **hvert døgn med en konsert**, og døgnet tidslinja står i (`koPlanValgtDogn`). «Artist» er nedtrekket, navnet valgfritt | Ingenting i programmet skal stå utenfor det man kan velge |
| Stedene kommer med programsvaret (`steder`), ikke fra sentralbordets `lokasjoner` | Den som har KO uten oppdragstilgang skal kunne se programmet. Et inaktivt sted posten alt står på, tilbys likevel |
| `koPlanKropp` sier fra ved knappen (`{feil}`); tomt antall er null og tas ut | Samme regel som «Velg…» ellers |
| Bare KO-leder får «+ Konsert» og klikk på en post (`koPlanKanLede` → `koKanFjerne`) | En knapp som fører til en vegg er verre enn ingen |
| **Båndene bak radene** (`koTavleProgram`, `koTavleKonsertHtml`): skravur og kant i beredskapsfargen, `ko-beredskap-<nivå>`; ukjent nivå får ingen farge | Samme form som skissene, og en annen enn prioriteten på hendelsene — så «rødt» ikke betyr to ting |
| **Behovet i drift** (`koTavleBehovNaa`, steg 3): «Lag 2/4» under stedsnavnet for konsertene som pågår eller begynner innen `KO_TAVLE_BEHOV_FORVARSEL_MIN` (30). Teller åpne plasseringer på stedet **og** de som er opptatt der (hendelse, oppdrag); to konserter samtidig legges sammen; gruppa matches på navn når id-en er borte | Lagene skal være på plass når konserten starter. Opptatt der er fortsatt der |
| **«Følg konserten»** i «Tider og slutt»: konsertene på stedet som ikke er over; valgt sendes `folger_id`, ikke en egen tid | Flyttes konserten, følger slutten med |
| **Tidslinja** (standardvisningen): tavlas vindu, **bare stedene som har noe i det**, i stedslistas rekkefølge; overlappende konserter på samme sted får hver sin bane (`koPlanTidslinje`) | Samme form og samme tid som tavla |
| **Dekningsstripa**: behovet per hele time i vinduet (`koPlanTimene`, `koPlanBehovPerTime`) mot vaktlistas tall (`…/dekning/?fra=&timer=`), søylene plassert i prosent under tidslinja. Hentes ikke mens aksen dras. **En konsert teller i hver time den berører** | Heller «for få» enn «nok» i tvil. Uten vaktlistetilgang sier den hvorfor |
| **«Etterpå»** (steg 5, tredje visning, `koPlanEtterpaaHtml`): konsert, beredskap, behov (med «opprinnelig» bare når det er endret), faktisk på stedet, oppdrag og antall endringer; historikken under, nyeste først. Vaktvelgeren og «Kopier programmet hit» bare for KO-leder, og kopien ikke fra aktiv vakt | Plan mot faktisk er der man ser om behovet holdt. Kopiering fra seg selv er et feilklikk |
| Standardfargen står i `var(--bf, …)`, ikke som `--bf` på grunnregelen | Satt der, vant den over `.ko-beredskap-*` senere i fila, og merket ble grått |
