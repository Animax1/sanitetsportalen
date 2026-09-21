# KO-modulen (ko/)

> **Modulfil.** Den lastes når noen arbeider i `ko/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Levert: pulje 1 (skallet), 2 (loggen), 3 (ressursbildet), 4 (sentralbordet flyttet inn),
5 (hendelsene), 6 (chat, ansvarsmerke, minimering, vaktlistas ressurser), **omleggingen
18. sep. 2026: fire flater i 2×2, hendelsesloggen som egen flate**, og 19. sep.: lagene på
hendelsen, loggen i hendelsen med deling, melder. Pulje 7 gjenstår — `docs/FORSLAG_KO.md`
§10, et **forslag**.

**Siden har ingen faner, og det er en regel og ikke en smakssak** (André, 17. sep. 2026).
En fane er riktig når flatene er *alternativer*; KOs flater brukes i **én** bevegelse:
sambandet sier noe, du fører linja, du ser hvem som er ledig, og du sender. Og **en skjult
fane er en fane du ikke vet har endret seg**: siden poller, og andres linjer lander i en
rute ingen ser på.

**Formen er fire vinduer i 2×2** (André, 18. sep. 2026, etter åtte skisser som ble avtalt
før koden — de er målet): `Hendelseslogg │ Loggstrøm` øverst, `Ressursoversikt │
Oppdragsliste` nederst. «Tre kolonner er taket» fra 17. sep. ble opphevet av André samme
dag som hendelsene ble en egen flate. Prinsippet — alt synlig samtidig, ingen faner — står.

**Vinduene bytter plass og endrer størrelse, og rammen holder alle fire synlige**
(`static/js/ko-layout.js`). Håndtaket i hvert vindu dras over et annet for å bytte plass,
skillelinjene endrer bredde per rad og høyden mellom radene. Ikke frie vinduer, med vilje:
et vindu som kan legges oppå et annet er et vindu som kan forsvinne. Gulvet
(`KO_MIN_PROSENT`, `min-width`/`min-height`) gjør det umulig å dra en flate bort. Oppsettet
huskes **per nettleser** (`ko.oppsett`): KO-PC-en beholder sitt uansett hvem som logger
på. Et lagret oppsett leses som brukerdata — `koGyldigOppsett()` avviser alt som mangler
et vindu.

**Sida ruller ikke — vinduene gjør det.** Høyden **måles** av `koKonsollhoyde()`, ikke
regnet ut av en `calc()`: header, nav og meldinger kan brekke til to linjer. Gulvet
(`KO_MIN_HOYDE`): uten det gir et kort vindu fire ubrukelige rullefelt.

**Knappene står i vinduet de gjelder**: «Ny hendelse» i hendelsesloggen, «Nytt oppdrag»
og «Historikk» i oppdragslista, «Enheter» i ressursoversikten. Verktøylinja har bare det
som gjelder hele sida. Sidebarknappen har `data-bs-toggle="dropdown"` og **ingen**
`data-action` — to lyttere på samme klikk er fella `klikkSkalKjore()` finnes for.

**Under 1200 px stables vinduene** og sida ruller normalt. Akseptert: KO brukes på en
skjerm i et kommandopunkt.

**`/oppdrag/` er enhetsverktøyet, `/ko/` er situasjonsverktøyet.** Et oppdrag begynner når
bilen får det; **en hendelse begynner når noen sier noe over samband**, og kan avsluttes
uten at noen rykket ut.

| Regel | Hvor |
|---|---|
| Hvem har KO oppe (sidebaren) | `ko/tilstede.py` |
| Sesjonsloopen den bygger på | `core/sesjoner.py` — delt med adminflaten |
| Modulens nivåer | `ko/module.py` — `les`, `skriv_full`, `skriv_leder` fra pulje 2 |
| Siden og endepunktene | `ko/views.py`, `ko/urls.py` |
| Sidebaren, loggstrømmen og oppstarten i nettleseren | `static/js/ko.js` — siste av tre filer, `KO_JS` |
| Logglinja og «nyeste i kjeden vinner» | `ko/models.py` |
| Reglene: tid, tekst, retting, sletting, frist | `ko/services.py` |
| **Hvilke systemhendelser som løftes inn, og hvorfor** | `ko/systemlinjer.py` |
| Løftet selv | `ko/signals.py` |
| Backup, opprydding, innstilling | `ko/backup.py`, `ko/opprydding.py`, `ko/portalinnstillinger.py` |
| **Hendelsene**: nummer, opprett, rediger, prioritet, bli med, lukk, gjenåpne, knytt | `ko/services.py` (nederst), `ko/models.Hendelse`, `HendelseDeltaker` |
| Hendelsesloggen i nettleseren: tabellen, søket, hendelsen åpnet i vinduet, skjemaet | `static/js/ko-hendelser.js` |
| Rutenettet: bytte plass, skillelinjer, oppsettet i `localStorage` | `static/js/ko-layout.js` |
| Festede linjer i loggstrømmen | `Logglinje.festet_*`, `services.fest_linje`/`losne_linje`, `festede` i `logg_view` |
| KO-innstillinger: ansvarsområder, «Nullstill» (admin) | `VERDILISTER` og `NULLSTILL` i `ko/views.py`, fanene via `verdifaner_ekstra` |
| «H12»-merket, lagene og de delte linjene på oppdraget og i bilen | `oppdrag_til_dict` (`hendelse_prioritet`, `hendelse_lag`, `delte_linjer`), lest gjennom `Hendelse.lag_navn()` / `delte_linjer_for()` |
| **Lagene på hendelsen**, deling av linjer, melderen | `ko.HendelseLag`, `Logglinje.delt_*`, `ko.Linjedeling`, `MELDER_VALG`; `sett_lag`, `del_linje`, `angre_deling`, `delte_for_vakt`, `rens_melder` i `ko/services.py` |
| Chat-merket, bryteren, ansvarsmerket | `Logglinje.uformell`, `services.chat_tillatt`, `ko.Ansvarsmerke`, `ko/portalinnstillinger.py` |
| Minimerbare grupper på tavla | `gruppehode()`/`vippGruppe()` i `static/js/oppdrag-kort.js` |
| Vaktlistas ressurser uten enhet | `vaktliste.services.ressurser_uten_enhet`, `koRessurskort()` i `ko.js` |

## Retningen: KO er øverste lag

`ko` → `vaktliste` og `ko` → `oppdrag`. **Ingen av dem kjenner `ko`**, og det håndheves
med AST i `ko/tests_avhengighet.py` — samme grep som `OppdragImportererIkkeVaktlista`.
Testen bor her fordi det er KOs kant å forsvare: skriver noen `from ko.models import …` i
`oppdrag/`, er det KO som har fått en ny og usynlig forelder.

Den ene kanten andre veien er `Oppdrag.hendelse` (pulje 5) — en nullbar FK som
**strengreferanse** (`'ko.Hendelse'`), uten import: `oppdrag` leser feltet i
`oppdrag_til_dict` og skriver det aldri; `ko.services.knytt_oppdrag` er den ene skriveren.
`KJENTE_UNNTAK` i `ko/tests_avhengighet.py` står derfor tom.

**Og kanten snur gjenopprettingsrekkefølgen.** KO er øverste lag i koden og nest først i
`GJENOPPRETTINGSREKKEFOLGE` (rett etter `portal`): oppdragsfila peker på hendelsene med et
heltall. `Hendelse.lokasjon` og `HendelseLag.ressurs` strippes i `ko/backup.py` av samme
grunn — beholdt, var det en sirkel — og navnene står frosset ved siden av.

`core` kjører uten `ko`: `core/tests_avhengighetsretning.py` har `ko` i `MODULAPPER`; den
ene tillatte importen er `core/modules.py` → `ko.module`.

## Modulen eier ingen ressurser, og skal aldri gjøre det

Ressursbildet er en **projeksjon** (§3.1): vaktlista sier hvem som finnes og hvem som er
på vakt, oppdragsmodulen sier status for dem som stempler selv. Et eget ressursregister ble
forkastet i §9.1: feilen oppstår ved **endring** — noen retter kallesignalet ett sted, og
tavla og enhetsskjermen viser ulike navn på samme bil midt i en vakt.

Det gjelder også `oppdrag.Enhetstype` mot `vaktliste.Ressursgruppe` — samme taksonomi to
steder (§2.1). Kjent, ikke slått sammen.

## Sidebaren svarer på «hvem har KO oppe», ikke «hvem dekker samband»

`ko/tilstede.py`. Tre valg som hver for seg er en mulig feil:

- **Filteret er `har_tilgang`-semantikk, ikke en rå `ModulTilgang`-spørring** — en rå
  spørring ville utelatt global admin, som ingen rader har.
- **Én rad per person, ikke per sesjon.** PC og telefon er én person; `inaktiv_s` er den
  ferskeste fanen. Adminlista lister sesjoner fordi den avslutter dem.
- **Ingen `session_key` ut.** Et felt hvis eneste bruk er destruktiv skal ikke ligge og vente.

**Pålogget er ikke til stede** — se rota. Derfor er `inaktiv_s` med som kolonne, og derfor
er `null` («vet ikke») noe annet enn `0`. `koInaktivTekst()` i `static/js/ko.js` tar det
samme valget på klientsida, og er en egen funksjon fordi den *avgjør* hva lista påstår om
en person.

## Nivåene legges til når de betyr noe

`Module.nivaaer` var `('les',)` i pulje 1: et nivå som ikke gir noe er lett å dele ut i god
tro, og ville **trådt stille i kraft** den dagen loggen landet (feilen den globale
nivålista gjorde mot `statistikk`). Pulje 2 la til `skriv_full` og `skriv_leder` i samme
commit som endepunktene, delt der **skaden er ulik**:

| Nivå | Kan | Hvorfor skillet går her |
|---|---|---|
| `les` | Se loggen for **aktiv vakt** | «Denne vakta» er ikke et filter, det er nivåets betydning |
| `skriv_full` | Føre linjer, rette sine egne og andres | En retting er en ny rad som peker på den gamle — ingenting går tapt, og feil kan rettes tilbake |
| `skriv_leder` | Sletteinngangen, og tidligere vakters logg | En fjernet linje finnes etterpå bare i en backupfil ingen har en knapp til |

`skriv_handling` er **ikke** deklarert: nivået leser ikke request-kroppen, og å føre en
logglinje gjør nettopp det — en tilgang uten et endepunkt bak seg.

**Historikken er `skriv_leder` av en annen grunn enn sletting: dataminimering** (André,
17. sep. 2026). En ny operatør på vakt i kveld har ingen operativ grunn til å lese
fjorårets helseopplysninger; opplæring hører hjemme på en demo-vakt.

## Loggen: de fire valgene som låser konstruksjonen

Besvart av André 17. sep. 2026, **før koden** — prisen skal være synlig.

### 1. Ingen SHA-signatur. Lesbar historikk i stedet

`NOTAT_DPIA_OG_FRITEKST.md` §7: fritekst arkiveres bevisst ikke, og `Oppdrag.fritekst` er
alt holdt utenfor `ArkivertOppdrag` av den grunn. Et felt i en SHA-payload er **låst i 24
måneder ved konstruksjon** — sletteinngangen i §4.4 ville da fått arkivet til å melde
tukling. To funksjoner som spiser hverandre.

Loggen står som levende rader i vakta, slettet av `purge_old_logs`. Prisen:
**loggen kan ikke bevise at den er urørt** — bare hvem som gjorde hva.

### 2. 730 dager, som en `AppSetting` — ikke en Railway-variabel

André foreslo en Railway-variabel: skjult jobbkonfigurasjon, uten audit, settes likt på
web og cron, usynlig i portalen. `AppSetting` er én rad begge leser, auditlogget av
`core/signals.py` — nøkkelen `ko.logg_dager` skal **aldri** inn i `NOKLER_UTEN_AUDIT`. 730
fordi det er fristen audit-loggen, arkivkollapsen og `backups/` alt har.

**Fristen er ikke en sletterett**, og det står både i malbiten og i A.9: en fjernet linje
ligger i modulfila offsite i inntil 730 dager og i den hele fila i 90. Samme forbehold som
DPIA-notatet §6 tar for `Oppdrag.fritekst`.

### 3. Ni systemhendelser, kuratert

Lista og regelen bak den står i `ko/systemlinjer.py` — den er selve designarbeidet i denne
puljen, ikke en detalj. Kort: **løft det som endrer situasjonen, ikke det som endrer
oppsettet; løft hendelsen, ikke feltet; én linje per ting som skjedde.**

Vaktlistas stemplinger: «ikke nå» — volumet drukner loggen.

### 4. Historikk krever `skriv_leder` — se «Nivåene» over.

## Logglinja: tre valg i modellen som ser ut som detaljer

**Ingen FK til `Oppdrag`.** Oppdragene slettes ved arkivering, og en peker hit ville vært en
felle uansett `on_delete` — `PROTECT` blokkerer arkiveringen, `CASCADE` sletter halve
loggen, `SET_NULL` etterlater «meldte Fremme» uten hvem. Linja fryser teksten (§4.5, §4.7).

**`korrigerer` *og* `rot`.** `korrigerer` er kjeden, `rot` er plassen i fortellingen: med
bare `korrigerer` ville ledd tre arvet ledd to sin plass, og linjene skal ikke hoppe rundt
etter en korreksjon (§4.3). `Coalesce('rot_id', 'id')` gjør de to til én sortering.

**Sletteinngangen tømmer hele kjeden.** Ellers sto den opprinnelige teksten igjen i den
overstyrte raden — usynlig i loggen, lesbar i basen og backupen.

## Løftet går med signaler, ikke med et register

`ko` → `oppdrag` er den tillatte retningen; et push-register hadde krevd at
`oppdrag/services.py` meldte fra. **Hendelseslinjene går ikke gjennom signaler:** de er
operatørens handlinger, og `ko/services.py` skriver dem selv. `ko/systemlinjer.py`: **et
signal ser raden, ikke intensjonen.** Mottakerne kaster aldri — **en KO-logg som ikke lar
seg skrive skal ikke ta ned en stempling i en bil.**

**Fire av kodene fantes alt som `oppdrag.Enhetshendelse`** — sjekk før du designer.

## Hendelsene — reglene som står

André 18. sep. 2026: **en lukket hendelse kan åpnes igjen, og det logges**
(`HENDELSE_GJENAPNET`). **`O45`/`H12` overalt** (§6): `oppdrag.services.oppdragsnr`,
`oppdragsnr()` i `oppdrag-kort.js` (enhetsskjermen har egen kopi), `ko.systemlinjer.hendelsesnr`.

Fem regler i `ko/services.py`, mutanter i `ko/tests_hendelser.py`:

| Regel | Hvorfor |
|---|---|
| Nummeret tildeles ved opprettelse og endres aldri; serien er uavhengig av O-serien | §6: nummeret identifiserer, FK-en relaterer. Telleren er unntatt audit |
| Lukking gir **409 med antallet** når hendelsen har åpne oppdrag, går gjennom med `confirm`, og antallet står på linja | §4.6: en dør hun åpner bevisst, ikke en vegg |
| Hodet (tittel, lokasjon, melder) redigeres med `versjon`, 409 ved uenighet | §7.1: det ene delte redigerbare. Ingen systemlinje — `audit/` fører feltendringer |
| `knytt_oppdrag` er den ene skriveren av `Oppdrag.hendelse`; lukket hendelse tar ikke imot | Ellers betyr «lukket» ingenting |
| En hendelse laget **fra** en linje lar linja stå; linja får hendelsen, hendelsen peker tilbake | §4.5: flyttes linja inn, får loggen et hull der det viktige skjedde |

**Lista følger med logg-pollen** (`hendelser` i `logg_view`), hel — som `fjernede`: en
lukking har ingen ny id og kommer aldri gjennom `?siden=`.

**Grupperingen på tavla er borte** (André, 18. sep. 2026: «ikke noen hendelser i
oppdragslisten»). H-merket på raden bærer koblingen — rød trekant når hendelsen er Viktig —
og hendelsene har sitt eget vindu. `renderOppdrag()` sier fra til KO etter
tegningen gjennom `koEtterOppdragTegnet()` (vakt: fila kjører også på `/oppdrag/`);
`TavlaSierFraTilKoTests` holder kallstedet. Samme vakt for `koHendelseValg()` i
detaljmodalen og `koEtterOpprettet()` etter «Nytt oppdrag».

**Knytting krever `skriv_full` i begge modulene**: det skriver på en oppdragsrad, og hvem
som får det er oppdragsmodulens sak. Dekoratøren gir KO-nivået, viewet det andre.

**Statistikken (`ko/statistikk.py`) leser lagene av systemlinjene, ikke `HendelseLag`**;
se `statistikk/CLAUDE.md`.

## Hendelsesloggen som egen flate (18. sep. 2026)

Besvart av André før koden, med de åtte skissene som fasit. Reglene bor i `ko/services.py`,
mutanter i `ko/tests_hendelseslogg.py` og `tests_nullstill.py`.

| Regel | Hvorfor |
|---|---|
| **Prioritet**: Viktig, Rød, Gul, Grønn, Drift, i den rangen. Standard Grønn. Ukjent verdi avvises, rettes ikke | Samme ordforråd som bilens grovsortering og hastegraden. «Kritisk» fra en gammel klient skal ikke stille bli Grønn |
| Prioritetsendring er en **systemlinje** med fra, til og hvem (`HENDELSE_PRIORITET`), aldri stille | «H14 satt til Viktig av Kari» er avgjørelsen man leter etter når man spør hvorfor to biler ble sendt |
| **Den som registrerer noe i hendelsen er på den** — kommentar, oppdrag, prioritet, redigering, og «Bli med». Lesing melder ingen inn | «Hvem jobber med H14 nå», så to operatører ikke sender hver sin bil. Vises, styrer ingenting — som ansvarsmerket. Navnet fryses |
| En kommentar er en logglinje med `hendelse_id`. Vakta må stemme; lukket hendelse tar imot | §4.1: én logg. En etterskrift etter lukking hører til hendelsen |
| Alt i hodet valideres **før** nummeret trekkes | Telleren lar seg ikke rulle tilbake av en 400; et hull i H-serien er et spørsmål i etterkant |
| **Lagene på hendelsen er vaktlistas ressurser uten enhet** (`HendelseLag`, 19. sep.), valgt i skjemaet eller med «Legg til»; hvert lag som kommer til eller går er en systemlinje. Lukket hendelse tar ikke imot. Følger oppdragene til bilen (`hendelse_lag`, i ETag-en) | «Lag får ikke oppdrag, de får oppdrag muntlig … og blir registrert på hendelsen» (André). Kortet i ressursoversikten viser «På H14 · 23 min» ved å slå laget opp i de **åpne** hendelsene (`koLagPaa`) — ingen egen status. `ressurs` strippes i backupen, navnet fryses |
| **Loggen i hendelsen er intern til den deles** (19. sep.): beskrivelsen fra «Ny hendelse» er første linje; «Del» (`delt_at`) gir linja til *alle* oppdrag i hendelsen, også senere; «Del med \<enhet\>» i oppdraget (`Linjedeling`) gir den til ett. Begge angres; ingen systemlinje. Bilen ser bare det delte (`delte_linjer`, gul ett minutt fra `delt_at`); «Nytt oppdrag» arver hastegrad av prioriteten og beskrivelsen som oppdragsnotat | «Sendes internt som standard … ettersendes til ressurs» (André). En retting arver delingen. `Linjedeling` er **ikke** i backupen: den peker på et oppdrag, som gjenopprettes etter KO |
| **Melder** er avkryssing over `MELDER_VALG` (fast i kode), flere er lov; «Andre» krever tekst, og teksten tømmes uten «Andre» | Nødetatene endrer seg ikke per arrangement; en valgliste var én ting til å vedlikeholde |
| **Festing** i loggstrømmen: `skriv_full`, idempotent, aldri systemlinjer eller fjernede. `festede` sendes hele med pollen | Festing endrer en rad uten ny id og ville aldri kommet gjennom `?siden=` — som `fjernede` |

**Sortering er oppdragslistas** (`koSorterHendelser`): lukkede nederst, prioritet, nummer.
**Søket** filtrerer lista som alt er hentet (nummer, tittel, sted, melder, logg, lag).
**Hendelsen åpnes i loggstrømmens vindu** (André, 21. sep. 2026), ikke i en modal og ikke
over lista: oversikten skal stå mens én hendelse er åpen. Strømmen og skrivefeltet
skjules imens (`koVisStrommen`; `les` får ikke feltet tilbake); raden vipper
(`koVippHendelse`), merkene i strømmen åpner bare. **Loggstrømmen viser linjene uten
hendelse pluss systemlinjene om hendelsene** (`koIStrommen`); kommentarene står i hendelsen.
Utskriften skal ha alt (TODO).

**KO-innstillinger er sentralbordets valgliste-modal med en fane til**, lagt inn gjennom
`verdifaner_ekstra` i konteksten og `window.VERDIFANER_EKSTRA` — en generell krok, ikke en
KO-referanse: oppdragsmodulen kjenner fortsatt ikke `ko`. Hver fane har sin egen dør
(`kan_lede` for oppdragsmodulens, `kan_lede_ko` for ansvarsområdene).

## Chat, ansvar og tavla (pulje 6)

Besvart av André 18. sep. 2026, før koden. Tre ideer ble til noe annet enn notatet sa
(§4.5, §5.1, §7.2).

**Chat er et merke på linja, ikke et sted** (§4.5). `Logglinje.uformell`, satt av en
avkryssing som bare finnes når `ko.chat_tillatt` (AppSetting, auditlogget, **av som
standard**) er på. Sperren står i `skriv_linje`, ikke bare i skjemaet. Bryteren styrer om
*nye* kan skrives — linjene som alt er skrevet vises uansett, ellers får loggen et hull.
Retting arver merket. **Hendelseslinjene vises tydelig**: `koLinjeMerke()` gir
`hendelse` for `hendelse_*`-kodene, foran `system`; linja er uthevet med den som opprettet.

**Ansvarsmerket vises og styrer ingenting** (§5.1). `ko.Ansvarsmerke`, én rad per konto
(samme person på PC og telefon har ett ansvar), satt med `POST api/ansvar/` på `les` —
den som bare leser kan likevel ha samband. Lista er `ko.Ansvarsomraade` (redigeres under
KO-innstillinger fra 18. sep. 2026); merket er tekst, så omdøping rører ikke loggen. `skriv_linje` stemper det når kallet ikke oppgir noe;
oppgitt verdi — også tom — vinner. `tilstede()` bærer det. **Ikke i backupen**: merket er
hva som gjelder nå.

**Filteret ble minimering** (§7.2, André: «ressurstypene må kunne minimeres»).
Gruppeoverskriften er en knapp; lukket-tilstanden huskes per nettleser under
`tavle.grupper.lukket`, og **overskriften viser antallet når gruppa er lukket**. I
`oppdrag-kort.js`, begge sidene; nøkler `type:<id>` og `gruppe:<id>`.

**Vaktlistas ressurser uten oppdragsenhet står på tavla** — lag, samleplass, KO — under
enhetslista i egen beholder (`#vaktliste-ressurser`; sentralbordet tegner `#enhetsliste` om
igjen ved hver poll). Data fra `/vaktliste/api/ressurser/uten-enhet/`, gatet av vaktlista,
**bare ressurser med et skift som dekker nå** (`ressurser_paa_vakt_naa`, samme regel som
lagvelgeren) — tegnet av `koRessurskort()`: hvor mange som er møtt, og «På H14 · Hovedscene
· 23 min» når laget står på en åpen hendelse; biler viser oppdragets sted. «i» folder ut
fargeforklaringen (`ko.legende`); kolonneknappen gir to kolonner, hele grupper per kolonne
(`ko.ressurskolonner`). Oppdragslistas hode teller aktive · ferdig (historikken
med); «Oppdrag uten ressurs» og «Tildelt» filtrerer, ett om gangen (`koOppdragFilter`).
**Besetningen — navn, møtt, telefon, ISSI — står bak et klikk**, én om
gangen som bilens. Alle | Biler | Lag i
vinduets hode huskes per nettleser (`ko.ressursvisning`); det skjulte står som et tall.

## Sentralbordet kjører i `/ko/` (pulje 4)

**KO laster `oppdrag-sentral-*.js` og treffer `/oppdrag/api/…`.** Ressurslista, oppdragslista,
verktøylinja, modalene og alle handlingene er oppdragsmodulens egne — samme kode, samme
endepunkter, samme sperrer. Det er en flytting, ikke en kopi.

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

## Feature parity med sentralbordet — ved konstruksjon, ikke ved flid

André, 17. sep. 2026: «Jeg vil ha det likt feature messig inn her i /ko.» **Parity som
holder er den som følger av at det er samme kode.** `ko/tests_sentralbord.py` håndhever at
KO får **hele** konteksten, at begge sidene laster **alle** sentralbordfilene i samme
rekkefølge (fasit `OPPDRAG_SENTRAL_JS`), og at de har de samme flatene.
