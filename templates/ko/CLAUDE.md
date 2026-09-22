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
den som ikke står i rutenettet står i stripa, og «⇄» i hodet bytter.

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
| Minimerbare grupper på tavla | `gruppehode()`/`vippGruppe()` i `static/js/oppdrag-kort.js` |
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

**Filteret ble minimering** (§7.2, André: «ressurstypene må kunne minimeres»).
Gruppeoverskriften er en knapp; tilstanden huskes under `tavle.grupper.lukket`, og
**overskriften viser antallet når gruppa er lukket**. I `oppdrag-kort.js`, begge sidene;
nøkler `type:<id>` og `gruppe:<id>`.

**Vaktlistas ressurser uten oppdragsenhet står på tavla** — lag, samleplass, KO — under
enhetslista i egen beholder (`#vaktliste-ressurser`; sentralbordet tegner `#enhetsliste`
om igjen ved hver poll). Fra `/vaktliste/api/ressurser/uten-enhet/`, gatet av vaktlista,
**bare ressurser med et skift som dekker nå** (`ressurser_paa_vakt_naa`, samme regel som
lagvelgeren) — tegnet av `koRessurskort()`: hvor mange som er møtt, og «På H14 · Hovedscene
· 23 min» når laget står på en åpen hendelse; biler viser oppdragets sted. «i» folder ut
fargeforklaringen (`ko.legende`); kolonneknappen gir to kolonner, hele grupper per kolonne
(`ko.ressurskolonner`). Oppdragslistas hode teller aktive · ferdig (historikken
med); «Oppdrag uten ressurs» og «Tildelt» filtrerer, ett om gangen (`koOppdragFilter`).
**Besetningen — navn, møtt, telefon, ISSI — står bak et klikk**, én om gangen som bilens.
Alle | Biler | Lag huskes per nettleser (`ko.ressursvisning`); det skjulte står som et tall.

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
| **Nå står ved to tredjedeler** (`koTavleVindu`) | Det meste av vinduet er det som har skjedd |
| Åpne og opptatte stolper **slutter ved nå** og vokser bakover til `max(72px, …)` | En stolpe forbi nå-streken ser ut som en plan |
| **Ingen `min-width` på rutenettet** | Tavla står ofte i den smale plassen; rullet tidslinja vannrett, forsvant nå-streken |
| Poller hvert 15. s **bare når den står framme**, tegner nå-streken hvert minutt | `koTegnOppsett` kaller `koTavleSynligNaa`, så en tavle som hentes fram viser nå |
| Filteret er vaktlistas ressursgrupper, huskes per nettleser (`ko.tavle.filter`) | Gruppene finnes alt; fire faste valg ville vært en taksonomi til |

**Gaten er komposisjonsregelen**: tavla krever `les` i vaktlista (403 ellers), bilene
bare med `les` i oppdragsmodulen — både i svaret og ved flytting (404: en bil man ikke får
se, finnes ikke). Flytting er `skriv_full` i KO.
