# KO-modulen (ko/)

> **Modulfil.** Den lastes når noen arbeider i `ko/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Levert: pulje 1 (skallet), 2 (loggen), 3 (ressursbildet), 4 (sentralbordet flyttet inn),
5 (hendelsene) og **6 (chat, ansvarsmerke, minimering, vaktlistas ressurser)**. Pulje 7
gjenstår — se `docs/FORSLAG_KO.md` §10, som er et **forslag**, ikke besluttet.

**Siden har ingen faner, og det er en regel og ikke en smakssak** (André, 17. sep. 2026).
Pulje 1 la de fire flatene i `nav-tabs`. En fane er riktig når flatene er *alternativer* —
man gjør det ene eller det andre. KOs flater brukes i **én** bevegelse: sambandet sier noe,
du fører linja, du ser hvem som er ledig, og du sender. Tre av fire trengs for å fullføre
én handling.

Den andre kostnaden er verre enn byttet: **en skjult fane er en fane du ikke vet har endret
seg.** Siden poller, så en annen operatørs logglinje, et nytt oppdrag eller en ressurs som
nettopp ble opptatt lander i en rute ingen ser på. Et merke sier *at* noe skjedde, ikke
*hva*, og det er enda et klikk midt i sambandstrafikk — mens hele grunnen til at KO finnes
er at situasjonsbildet skal være i ett blikk.

**Formen er tre kolonner: `Logg │ Ressurser │ Oppdrag`** (André, 17. sep. 2026: «Logg skal
være den sentrale delen. Ressursoversikt henger sammen med oppdragslisten. PC er hoved
måten en bruker dette på.»). Forholdet er 4 : 3 : 5, og de to siste er sentralbordets eget
`col-lg-4` + `col-lg-8` litt strammet — det er den blokka pulje 4 flytter hit.

**Rekkefølgen er arbeidsflyten fra venstre mot høyre:** du hører noe, fører linja, ser hvem
som er ledig, og sender. Loggen står derfor først, der øyet lander, og ikke i midten —
loggen i midten ville splittet paret som hører sammen, og den hyppigste handlingen på
skjermen er nettopp å matche en ledig ressurs mot et ventende oppdrag. «Sentral» er her
lest som *primær og permanent*, ikke som *midterste kolonne*, og det valget er
`SidenHarIngenFanerTests` sin rekkefølgeprøve.

**Sida ruller ikke — kolonnene gjør det.** Det er forskjellen på en konsoll og en
nettside: de tre flatene står på samme sted hele vakta, uansett hvor mye som er i dem.
Rulles sida, flytter skrivefeltet seg idet tavla får en rad til. Høyden **måles** av
`koKonsollhoyde()` og regnes ikke ut av en `calc()` med et fast tall — over konsollen står
header, nav og eventuelle meldinger, og alle tre kan brekke til to linjer. Gulvet
(`KO_MIN_HOYDE`) er en regel og ikke en margin: uten det gir et kort vindu tre ubrukelige
rullefelt, og da er det bedre at sida ruller.

**Sidebaren er et nedtrekk, ikke en kolonne.** «Hvem har KO oppe» er en håndfull navn man
kikker på; en fjerde kolonne ville tatt bredde fra oppdragslista, som trenger den mest.
Knappen har `data-bs-toggle="dropdown"` og **ingen** `data-action` — to lyttere på samme
klikk er fella `klikkSkalKjore()` finnes for.

**Under `xl` stables kolonnene**, loggen først, og sida ruller normalt. Akseptert, ikke
løst: KO brukes på en skjerm i et kommandopunkt. Kommer kravet om mobil, er svaret ikke faner.

**Tre kolonner er taket.** Det er også hvorfor hendelser ikke kan bli en fjerde region:
den er en gruppering av oppdragslista (§7), og layouten og puljeplanen peker samme vei.

**`/oppdrag/` er enhetsverktøyet, `/ko/` er situasjonsverktøyet.** Én bil, én
statusmaskin, én stempling om gangen — mot hva skjer på arrangementet, hvem er hvor, hva
vet vi. Forskjellen er tidsaksen: et oppdrag begynner når bilen får det; **en hendelse
begynner når noen sier noe over samband**, kan leve i tjue minutter før en ressurs sendes,
og kan bli avsluttet uten at noen rykket ut.

| Regel | Hvor |
|---|---|
| Hvem har KO oppe (sidebaren) | `ko/tilstede.py` |
| Sesjonsloopen den bygger på | `core/sesjoner.py` — delt med adminflaten |
| Modulens nivåer | `ko/module.py` — `les`, `skriv_full`, `skriv_leder` fra pulje 2 |
| Siden og endepunktene | `ko/views.py`, `ko/urls.py` |
| Sidebaren og loggen i nettleseren | `static/js/ko.js` |
| Logglinja og «nyeste i kjeden vinner» | `ko/models.py` |
| Reglene: tid, tekst, retting, sletting, frist | `ko/services.py` |
| **Hvilke systemhendelser som løftes inn, og hvorfor** | `ko/systemlinjer.py` |
| Løftet selv | `ko/signals.py` |
| Backup, opprydding, innstilling | `ko/backup.py`, `ko/opprydding.py`, `ko/portalinnstillinger.py` |
| **Hendelsene**: nummer, opprett, rediger, lukk, gjenåpne, knytt | `ko/services.py` (nederst), `ko/models.Hendelse` |
| Grupperingen på tavla og «H12»-merket | `koGrupperOppdrag()` i `static/js/ko.js`, `_oppdragRadHtml()` i sentralbordet |
| Chat-merket, bryteren, ansvarsmerket | `Logglinje.uformell`, `services.chat_tillatt`, `ko.Ansvarsmerke`, `ko/portalinnstillinger.py` |
| Minimerbare grupper på tavla | `gruppehode()`/`vippGruppe()` i `static/js/oppdrag-kort.js` |
| Vaktlistas ressurser uten enhet | `vaktliste.services.ressurser_uten_enhet`, `koRessurskort()` i `ko.js` |

## Retningen: KO er øverste lag

`ko` → `vaktliste` og `ko` → `oppdrag`. **Ingen av dem kjenner `ko`**, og det håndheves
med AST i `ko/tests_avhengighet.py` — samme grep som `OppdragImportererIkkeVaktlista`.
Testen bor her fordi det er KOs kant å forsvare: skriver noen `from ko.models import …` i
`oppdrag/`, er det KO som har fått en ny og usynlig forelder.

Den ene kanten som går andre veien er `Oppdrag.hendelse` (pulje 5) — en nullbar FK fra
oppdrag til hendelsen, som **strengreferanse** (`'ko.Hendelse'`) og uten en import: `oppdrag`
leser feltet i `oppdrag_til_dict` og skriver det aldri; `ko.services.knytt_oppdrag` er den ene
skriveren. `KJENTE_UNNTAK` i `ko/tests_avhengighet.py` står derfor fortsatt tom.

**Og kanten snur gjenopprettingsrekkefølgen.** KO er øverste lag i koden og nest først i
`GJENOPPRETTINGSREKKEFOLGE` (rett etter `portal`): oppdragsfila peker på hendelsene med et
heltall. `Hendelse.lokasjon` strippes i `ko/backup.py` av samme grunn — beholdt, var det en
sirkel — og navnet står frosset i `lokasjon_navn`, som forfatteren på linja.

`core` skal fortsatt kunne kjøre uten `ko`: `core/tests_avhengighetsretning.py` har `ko` i
`MODULAPPER`, og den ene tillatte importen er `core/modules.py` → `ko.module`, som er
registeret som navngir modulene sine.

## Modulen eier ingen ressurser, og skal aldri gjøre det

Ressursbildet er en **projeksjon** (§3.1): vaktlista sier hvem som finnes og hvem som er
på vakt, oppdragsmodulen sier status for dem som stempler selv, og KO fører status for dem
som ikke gjør det. Et eget ressursregister her ble forkastet i §9.1, og begrunnelsen er
verdt å huske fordi den ikke handler om opprettelse: feilen oppstår ved **endring**. Noen
retter kallesignalet ett sted, og tavla og enhetsskjermen viser ulike navn på samme bil
midt i en vakt.

Det gjelder også `oppdrag.Enhetstype` mot `vaktliste.Ressursgruppe` — samme taksonomi to
steder (§2.1). Skal **ikke** slås sammen i dette arbeidet, men er kjent.

## Sidebaren svarer på «hvem har KO oppe», ikke «hvem dekker samband»

`ko/tilstede.py`. Tre valg som hver for seg er en mulig feil:

- **Filteret er `har_tilgang`-semantikk, ikke en rå `ModulTilgang`-spørring.** Notatets
  §5.3 sier «`_list_active_sessions` filtrert på `ModulTilgang('ko')`», og det filteret
  ville utelatt global admin — som ingen rader har, og full tilgang. Altså nettopp den som
  sitter i KO og administrerer portalen.
- **Én rad per person, ikke per sesjon.** Adminlista på server-status lister *sesjoner*,
  fordi den skal kunne avslutte én av dem. Denne svarer på hvem som er der, og samme
  operatør med KO på PC-en og på telefonen er én person. `inaktiv_s` blir den ferskeste av
  fanene.
- **Ingen `session_key` ut.** Det er adminflatens håndtak for å avslutte en sesjon. En
  KO-operatør har ingenting med det å gjøre, og et felt hvis eneste bruk er destruktiv
  skal ikke ligge og vente på at noen finner ut hva det er.

**Pålogget er ikke til stede** — se rota. Derfor er `inaktiv_s` med som kolonne, og derfor
er `null` («vet ikke») noe annet enn `0`. `koInaktivTekst()` i `static/js/ko.js` tar det
samme valget på klientsida, og er en egen funksjon fordi den *avgjør* hva lista påstår om
en person.

## Nivåene legges til når de betyr noe

`Module.nivaaer` var `('les',)` i pulje 1. Skallet hadde ingen skriveendepunkter, og et
nivå som ikke gir noe er lett å dele ut i god tro — det er feilen den globale nivålista
gjorde mot `statistikk`, dokumentert i `core/modules.py`. Her hadde den vært verre enn der:
`statistikk` har aldri fått skriving, så et utdelt `skriv_full` ble bare liggende dødt,
mens et `skriv_full` delt ut på `ko` i pulje 1 ville ligget i basen og **trådt stille i
kraft** den dagen loggen landet.

Pulje 2 la til `skriv_full` og `skriv_leder` i samme commit som endepunktene som gir dem
mening, og delte dem der **skaden er ulik**:

| Nivå | Kan | Hvorfor skillet går her |
|---|---|---|
| `les` | Se loggen for **aktiv vakt** | «Denne vakta» er ikke et filter, det er nivåets betydning |
| `skriv_full` | Føre linjer, rette sine egne og andres | En retting er en ny rad som peker på den gamle — ingenting går tapt, og feil kan rettes tilbake |
| `skriv_leder` | Sletteinngangen, og tidligere vakters logg | En fjernet linje finnes etterpå bare i en backupfil ingen har en knapp til |

`skriv_handling` er **ikke** deklarert: nivået leser ikke request-kroppen, og å føre en
logglinje gjør nettopp det. Det ville sett ut som «får skrive litt», og vært en tilgang
uten et endepunkt bak seg.

**Historikken er `skriv_leder` av en annen grunn enn sletting: dataminimering** (André,
17. sep. 2026). En ny operatør på vakt i kveld har ingen operativ grunn til å lese
fjorårets helseopplysninger, og opplæring hører hjemme på en demo-vakt og ikke på ekte
linjer. Flata kommer i pulje 3; nivået står allerede, fordi det er det som gir `les` sin
betydning.

## Loggen: de fire valgene som låser konstruksjonen

Besvart av André 17. sep. 2026, **før koden**. De står her og ikke bare i CHANGELOG fordi
hvert av dem er noe den neste kommer til å ville gjøre om, og da skal prisen være synlig.

### 1. Ingen SHA-signatur. Lesbar historikk i stedet

`NOTAT_DPIA_OG_FRITEKST.md` §7: fritekst arkiveres bevisst ikke, og `Oppdrag.fritekst` er
alt holdt utenfor `ArkivertOppdrag` av den grunn. Et felt i en SHA-payload er **låst i 24
måneder ved konstruksjon** — sletteinngangen i §4.4 ville da fått arkivet til å melde
tukling. To funksjoner som spiser hverandre.

Loggen blir derfor stående som levende rader, scopet til vakta, og slettes av
`purge_old_logs`. Prisen, som skal være sagt: **loggen kan ikke bevise at den er urørt.**
Den kan spore hvem som gjorde hva, men ikke at teksten ikke er endret.

### 2. 730 dager, som en `AppSetting` — ikke en Railway-variabel

André foreslo en Railway-variabel. Fire grunner til at den ikke er det, og den første er at
prosjektet tok valget én gang før: `purge_old_logs` sin egen docstring sier at grensene
ligger i kode «slik at en endring av lagringstid skjer i kode som kan revideres, **ikke i
en skjult jobbkonfigurasjon**». En Railway-variabel er en skjult jobbkonfigurasjon.

| | Railway-variabel | `AppSetting` |
|---|---|---|
| Audit | Ingen. Fristen går fra 730 til 30 og portalen vet det ikke | `core/signals.py` logger den. Nøkkelen `ko.logg_dager` skal **aldri** inn i `NOKLER_UTEN_AUDIT` |
| To tjenester | Web og cron er separate. Settes den ett sted, viser web én frist og cron sletter etter en annen — `DATABASE_URL`-fella | Én rad begge leser |
| Synlighet | Må åpnes i Railway | Står på `/portal-admin/innstillinger/` |

730 fordi det er fristen audit-loggen, arkivkollapsen og `backups/`-prefikset alt har. Ett
tall å forklare i A.9 i stedet for fire.

**Fristen er ikke en sletterett**, og det står både i malbiten og i A.9: en fjernet linje
ligger i modulfila offsite i inntil 730 dager og i den hele fila i 90. Samme forbehold som
DPIA-notatet §6 tar for `Oppdrag.fritekst`.

### 3. Ni systemhendelser, kuratert

Lista og regelen bak den står i `ko/systemlinjer.py` — den er selve designarbeidet i denne
puljen, ikke en detalj. Kort: **løft det som endrer situasjonen, ikke det som endrer
oppsettet; løft hendelsen, ikke feltet; én linje per ting som skjedde.**

Vaktlistas stemplinger er grensesaken, og svaret er «ikke nå»: volumet ville druknet loggen
ved hvert vaktskifte. Tas opp i pulje 4, der lag-begrepet får et hjem.

### 4. Historikk krever `skriv_leder`

Se «Nivåene» over.

## Logglinja: tre valg i modellen som ser ut som detaljer

**Ingen FK til `Oppdrag`.** `oppdrag/arkiv.py` sier det selv: «oppdragene slettes fra tavla
og historikken når de er frosset, og telleren nullstilles». En peker hit hadde vært en
felle uansett `on_delete` — `PROTECT` blokkerer arkiveringen, `CASCADE` sletter halve
loggen stille, `SET_NULL` etterlater en linje som sier «meldte Fremme» uten å si hvem.
Linja fryser teksten i stedet, som §4.5 og §4.7 alt krever for brukernavn og kallesignal.

**`korrigerer` *og* `rot`, og de gjør hver sin jobb.** `korrigerer` er kjeden, som i
`Statusmelding`; `rot` er plassen i fortellingen. Med bare `korrigerer` ville ledd tre
arvet ledd to sin plass — altså bunnen av loggen — og §4.3 sier hvorfor det er galt:
linjene skal ikke hoppe rundt etter en korreksjon. `Coalesce('rot_id', 'id')` gjør de to
til én sortering uten en join.

**Sletteinngangen tømmer hele kjeden.** Rettes en linje og deretter fjernes den, ville den
opprinnelige teksten blitt stående i den overstyrte raden — usynlig i loggen, fullt lesbar
i basen og i backupen. En sletteinngang som lar en kopi ligge igjen er ikke en
sletteinngang.

## Løftet går med signaler, ikke med et register

`ko` → `oppdrag` er den tillatte retningen. Et push-register hadde krevd at
`oppdrag/services.py` meldte fra, og oppdragsmodulen røres så lite som mulig.
**Hendelseslinjene går ikke gjennom signaler:** de er operatørens handlinger, og
`ko/services.py` skriver dem selv — med operatøren frosset som forfatter.

Forbeholdet er ekte og står i `ko/systemlinjer.py`: **et signal ser raden, ikke
intensjonen.** «Avbrutt fordi ingen svarte» og «avbrutt fordi pasienten gikk hjem» er
samme rad. Trenger en linje intensjon, må kallstedet dytte — og *da* bygges registeret.

Mottakerne kaster aldri. **En KO-logg som ikke lar seg skrive skal ikke ta ned en stempling
i en bil**: bilen er det operative, loggen er dokumentasjonen.

**Fire av kodene fantes alt som `oppdrag.Enhetshendelse`** — sjekk om oppdragsmodulen har
begrepet før du designer det inn i KO (§2).

## Hendelsene (pulje 5) — en gruppering, ikke en flate

Besvart av André 18. sep. 2026, før koden: **en lukket hendelse kan åpnes igjen** (det er
en misforståelse eller et feilklikk når det skjer), **og det logges** — `HENDELSE_GJENAPNET`
er en egen systemlinje, aldri en stille statusendring. Og **`O45`/`H12` overalt** (§6):
formen på oppdragsnummeret bor i `oppdrag.services.oppdragsnr` og `oppdragsnr()` i
`oppdrag-kort.js` (enhetsskjermen har sin egen kopi), hendelsens i `ko.systemlinjer.hendelsesnr`.

Fem regler, alle i `ko/services.py`, alle prøvd med mutanter i `ko/tests_hendelser.py`:

| Regel | Hvorfor |
|---|---|
| Nummeret tildeles ved opprettelse og endres aldri; serien er uavhengig av O-serien | §6: nummeret identifiserer, FK-en relaterer. Telleren er unntatt audit |
| Lukking gir **409 med antallet** når hendelsen har åpne oppdrag, og går gjennom med `confirm` — og antallet står på linja | §4.6: en dør hun åpner bevisst, ikke en vegg. Ferdige oppdrag teller ikke |
| Hodet (tittel, lokasjon) redigeres med `versjon`, 409 ved uenighet | §7.1: det ene delte redigerbare. Ingen systemlinje — `audit/` fører feltendringer |
| `knytt_oppdrag` er den ene skriveren av `Oppdrag.hendelse`; lukket hendelse tar ikke imot | Ellers var «lukket» et ord uten mening, og 409-sperra omgått bakveien |
| En hendelse laget **fra** en linje lar linja stå; linja får hendelsen, hendelsen peker tilbake | §4.5: flyttes linja inn, får loggen et hull der det viktige skjedde |

**Lista følger med logg-pollen** (`hendelser` i `logg_view`), hele hver gang — som
`fjernede`: en lukking eller omdøping har ingen ny id og ville aldri kommet gjennom
`?siden=`. Ingen egen poller.

**Grupperingen er en bryter på tavla, og den skjuler ingenting** (§7.2): av og på viser de
samme radene. `koGrupperOppdrag()` er regelen — åpne hendelser nyeste først (også uten
oppdrag: det er hendelsen som lever før en ressurs sendes), lukkede bare mens de har rader,
«Uten hendelse» sist. `renderOppdrag()` i sentralbordet spør etter den gjennom en vakt
(`typeof koGrupperOppdrag === 'function'`), for den fila kjører også på `/oppdrag/`, der lista
er flat som før. Samme vakt for `koHendelseValg()` i detaljmodalen og `koEtterOpprettet()`
etter «Nytt oppdrag». `TavlaSpoerEtterGrupperingenTests` holder kallstedet i live.

**Knytting krever `skriv_full` i begge modulene**: det skriver på en oppdragsrad, og hvem
som får det er oppdragsmodulens sak (komposisjonsregelen). Dekoratøren gir KO-nivået,
viewet sjekker det andre.

## Chat, ansvar og tavla (pulje 6)

Besvart av André 18. sep. 2026, før koden. Tre av notatets ideer ble til noe annet enn
notatet sa, og det står i §4.5, §5.1 og §7.2 der.

**Chat er et merke på linja, ikke et sted** (§4.5). `Logglinje.uformell`, satt av en
avkryssing som bare finnes når `ko.chat_tillatt` (AppSetting, auditlogget, **av som
standard**) er på. Sperren står i `skriv_linje`, ikke bare i skjemaet. Bryteren styrer om
*nye* kan skrives — linjene som alt er skrevet vises uansett, ellers får loggen et hull.
Retting arver merket. Og **hendelseslinjene vises tydelig**: `koLinjeMerke()` gir
`hendelse` for `hendelse_*`-kodene, foran `system`, og linja er uthevet med den som
opprettet.

**Ansvarsmerket vises og styrer ingenting** (§5.1). `ko.Ansvarsmerke`, én rad per konto
(samme person på PC og telefon har ett ansvar), satt med `POST api/ansvar/` på `les`-nivå —
den som bare leser kan likevel ha samband. Fast liste (`ANSVARSOMRAADER`), fordi «samband»
og «Samband» skal være ett merke. `skriv_linje` stemper det når kallet ikke oppgir noe;
oppgitt verdi — også tom — vinner. `tilstede()` bærer det. **Ikke i backupen**: merket er
hva som gjelder nå.

**Filteret ble minimering** (§7.2, André: «ikke direkte filter … ressurstypene må kunne
minimeres»). Gruppeoverskriften på tavla er en knapp; lukket-tilstanden huskes per
nettleser under `tavle.grupper.lukket`, og **overskriften viser antallet når gruppa er
lukket** — det som er skjult er lesbart. Mekanismen bor i `oppdrag-kort.js` og gjelder
begge sidene; nøklene er `type:<id>` for enhetstypene og `gruppe:<id>` for vaktlistas
ressursgrupper.

**Vaktlistas ressurser uten oppdragsenhet står på tavla** — lag, samleplass, KO — under
enhetslista, i sin egen beholder (`#vaktliste-ressurser`): sentralbordet tegner
`#enhetsliste` om igjen ved hver poll, og to skrivere til samme element blir uenige. Data
fra `/vaktliste/api/ressurser/uten-enhet/`, gatet av vaktlista (komposisjonsregelen), tegnet
av `koRessurskort()`: hvem, og om de er møtt. **Ingen status** — hva en KO-ført status for
et lag skal hete er fortsatt ubesvart, og kortet sier bare det vaktlista vet.

## Sentralbordet kjører i `/ko/` (pulje 4)

**KO laster `oppdrag-sentral-*.js` og treffer `/oppdrag/api/…`.** Ressurslista, oppdragslista,
verktøylinja, modalene og alle handlingene er oppdragsmodulens egne — samme kode, samme
endepunkter, samme sperrer. Det er en flytting, ikke en kopi.

| Hva | Hvor det bor | Delt av |
|---|---|---|
| Konteksten | `oppdrag.views.sentralbordkontekst()` | `/oppdrag/` og `/ko/` |
| Verktøylinja | `templates/oppdrag/_sentralbord_verktoy.html` | begge |
| Modalene | `templates/oppdrag/_sentralbord_modaler.html` | begge |
| Globaler og skript | `templates/oppdrag/_sentralbord_skript.html` | begge |
| Enhetskortet og lista | `static/js/oppdrag-kort.js` | begge |

**Oppdragsflata gates av `oppdrag`-modulen, ikke av `ko`** (André, 18. sep. 2026). Det er
komposisjonsregelen fra rollemodellen §5 — samme som `kan_se_besetning` bruker for vaktlista:
KO *viser* oppdragsmodulens data, og hvem som får se dem er oppdragsmodulens sak.
`kan_se_oppdrag` avgjør om flata tegnes i det hele tatt; `kan_skrive` og `kan_lede` avgjør
knappene, og begge er oppdragsnivåer.

**En KO-operatør trenger derfor to rader:** `ko` for loggen og `oppdrag` for oppdragene.
Alternativet — egne KO-nivåer foran de samme endepunktene — ville lagt tilgangsmodellen to
steder, og to steder glir fra hverandre.

**KO har ingen egne oppdragsendepunkter.** `/ko/api/ressurser/` fantes en dag i pulje 3 og er
borte: den gatet oppdragsdata på `ko:les`. `ko.js` henter derfor verken ressurser eller
oppdrag — sentralfilene eier begge listene, med sin egen ETag og polling. En henter til
ville vært en andre poller mot de samme endepunktene, og to pollere som skriver til samme
`#enhetsliste` blir uenige.

**Loggen er fortsatt KOs egen**, og `ko:les` alene gir den. En operatør uten oppdragstilgang
ser loggen og en beskjed om hva som mangler — ikke en tom kolonne.

## Feature parity med sentralbordet — ved konstruksjon, ikke ved flid

André, 17. sep. 2026: «Jeg vil ha det likt feature messig inn her i /ko.» Det første kortet
her manglet passiv vakt, ventende, «ledig siden», sted og oppdragslinja. **Parity som
holder er den som følger av at det er samme kode**: fra pulje 4 leser `/oppdrag/` og `/ko/`
samme kontekst, maler, JS og endepunkter.

`ko/tests_sentralbord.py` håndhever tre ting: at KO får **hele** konteksten (ikke et
utvalg), at begge sidene laster **alle** sentralbordfilene i samme rekkefølge, og at de har
de samme flatene. Den midterste er en sperrehake: begge sidene leser samme malbit, så en fil
som faller ut faller ut begge steder — og likheten består mens flata er ødelagt. Fasiten er
`OPPDRAG_SENTRAL_JS`.
