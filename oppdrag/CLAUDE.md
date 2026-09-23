# Oppdragsmodulen (oppdrag/)

> **Modulfil.** Den lastes når noen arbeider i `oppdrag/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Egen app siden august 2026 — se `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Alle sju fasene er
levert: sentralbord, enhetsskjerm, korreksjoner, offline-kø, statistikkfane og vaktarkiv.

Fem ting det er verdt å kjenne før man rører modulen:

| Regel | Hvor |
|---|---|
| Statusmaskinen er **data**, ikke `if`-er i views | `services.OVERGANGER` |
| Enhetens status **utledes**, den lagres ikke | `services.enhet_status()` |
| Korreksjoner er **nye rader** som peker på den gamle | `Statusmelding.objects.gjeldende()` |
| `fritekst` logges som endret, men **uten verdier** | `signals.FELT_UTEN_VERDILOGGING` |
| «Historikk» rydder tavla, **arkivet fryser og lukker vakta** | `Oppdrag.historikk_fra` vs. `oppdrag/arkiv.py` |
| Bilen rykker videre → oppdraget **trenger ressurs**, ikke ferdig | `Oppdrag.trenger_ressurs` + `trenger_ressurs_siden`, `services.start_oppdrag` |
| **Et oppdrag kan opprettes uten enhet** (19. sep.) — `Oppdrag.enhet` nullbar, flagget satt fra start, samme opptrapping; den første som varsles blir primær. `enhet_ider: []` er lov, kropp uten feltet er 400 | `views.oppdrag_liste_view` (POST), `_enheter_fra_kroppen`, `services.varsle_enhet`; arkivet gir én rad med tomt navn (`arkiv._per_enhet`) |
| **«Tildelt» er en visning, ingen status**: ingen påbegynt, minst ett ventende, ikke passiv vakt. Hul grønn ring; `tildelt_siden` fra første varsling | `services.enhet_status`, `TILDELT`; `.status-tildelt` |
| **Uten pasient: Drift og Plassering** — driftens problemstillinger, aldri grovsortering, intet grovmerke | `choices.UTEN_PASIENT`; JS har lista inne i `_kanGrovsortere`/`grovKrevesFor`/`_grovMerke` fordi harnessene henter funksjoner alene |
| Grovsorteringen har **«Ikke aktuelt»** (grått) — teller som satt | `choices.GROVSORTERING`, `.grov-ikke_aktuelt` |
| «Trenger ny ressurs» spør **to** ting: er noen på vei, *og* var noen framme | `services.trenger_ny_ressurs()` |
| Lista sorteres på hastegrad, så nummer; ferdige nederst | `_sorterOppdrag()` i `oppdrag-sentral.js` |
| Bilen melder Ledig bare fra Leverer og Behandlet; Avbryt i Rykker ut og Fremme, Behandlet på sted i Fremme — **«Utført»** på Drift og Plassering | `services.BILEN_KAN_LEDIG_FRA`, `AVBRYT_FRA`, `ALTERNATIV`, `alternativ_for()`, `choices.status_navn_for` |
| «Avreist → Annet sted» har et **fritekstfelt** (`Statusmelding.sted_tekst`, 19. sep.): bilen og føringen sender det i kroppen, bare ved `annet`; arves av korreksjon; aldri verdilogget | `_sted_tekst`, `STEMPLING_TILLATTE_NOKLER`, `choices.sted_navn_for`, `stempleAnnetSted` i bilen |
| «Nytt oppdrag» bygges **ikke om** mens operatøren står i det: `fyllNedtrekk` venter når fokus er i det viste skjemaet, og rører ikke uendret markup | `skjemaErIBruk()` i `oppdrag-sentral-lasting.js`; `koFyllHendelsevalg` samme regel |
| **Verdiene endres ett felt om gangen, og hver endring står i tidslinjen** (23. sep.). Hastegraden alene beholder problemstillingen om den passer, ellers «Udefinert» (merket `automatisk`). Notatet logges uten verdier | `Oppdragsendring`, `services.problemstilling_etter_hastegrad`, `logg_endringer`; PUT i `oppdrag_detalj_view` |
| Bilen ser bare det lista viser (30 min etter Ledig) — også på detalj, stempling, grovsortering og antall; og aldri flåten, flytting eller verdimengdene | `views._synlig_for_bilen`, `er_enhetskonto`-sjekkene |

**Historikk og arkiv er to helt ulike handlinger**, og har derfor hver sin knapp.
Historikk flytter ett oppdrag ut av den aktive tavla og er fullt reversibel; arkivering
fryser hele vakta med signatur, **sletter så oppdragene fra tavla og historikken og
nullstiller telleren** (12. sep. 2026 — neste oppdrag får #1), og starter klokka mot en
kollaps som sletter radnivået etter 24 måneder. Viewet avviser arkivering mens noe står
på tavla. Pasientarkivet gjør *ikke* dette — der står pasientene igjen etter frysing. `fritekst` arkiveres **ikke** — feltet er unntatt verdilogging i audit,
og å fryse det i 24 måneder ville uthult unntaket.

**Verdimengdene (12. sep. 2026):** `HASTEGRAD` har fått «Drift» (het «Teknisk» én dag) — et oppdrag uten
pasient — og problemstillingene avhenger av hastegraden. **Problemstillinger, enhetstyper
og lokasjoner er tabeller** (`Problemstilling`, `Enhetstype`, `Lokasjon`; migrasjon
`0019`–`0021` seedet de to første fra listene i `choices.py`, som nå bare er seed-data).
`oppdrag/verdier.py` er det ene stedet som leser dem: `problemstillinger_for(hastegrad)`
(Udefinert alltid først), `problemstilling_passer()` med `gjeldende` — et oppdrag beholder
en deaktivert problemstilling ved redigering — og `baerer_antall()`.
`Problemstilling.kategori` (medisinsk/drift/begge) sier hvilke hastegrader raden tilbys
for; **«Udefinert» er en fast rad** som ikke kan endres, deaktiveres eller slettes, fordi
`sett_status` sperrer på navnet. `Oppdrag.problemstilling` er fortsatt tekst — arkivets
radform er signert. `views_verdier.py` er én fabrikk for de tre: liste for `les`,
opprett/endre/omsortere for **`skriv_leder`** (André: «La oss ha skriv_leder rolle på
dette»; enhetskontoer får 403 uansett nivå),
sletting for global admin med `{"confirm": true}`, PROTECT/i bruk gir 409. **Rekkefølgen
settes med hele lista** (`PUT …/rekkefolge/`), ikke «opp» per rad. Klienten har ett vindu
med tre faner («Valglister», `renderVerdiadmin`) og bygger `OPPDRAG_PROBLEMSTILLINGER_FOR`
selv fra radene (`_byggProblemkart`), så nedtrekkene følger med uten sidelasting.
**Bilinnstillingene (12. sep. 2026):** `verdier.bilinnstillinger()` samler lydvarselets
terskler per hastegrad (tabellen `Lydvarsel`, seedet av `0024`; `Lydvarsel.aktiv` slår
ventevarselet av per hastegrad, `0025`, uten å røre pipet ved nytt oppdrag), og tre brytere i
`AppSetting`: `oppdrag_lyd_aktiv` (lyden av for alle biler), `oppdrag_lyd_nytt` (pip ved
nytt oppdrag) og `oppdrag_krev_grov_avreist`. `views_verdier.bilinnstillinger_view`: GET for
`les`, PUT for **global admin** (fanen «Bilen» i «Valglister» vises bare for admin). I bilen
er lyden **på som standard**; dempeikonet husker per enhet (`erDempet`), og
`lydSkalSpille()` er det ene stedet som slår sammen klar/admin/dempet. **Grovsortering
kreves** (`verdier.grov_kreves_for`, speilet i `grovKrevesFor` i JS) før Behandlet på sted
og før Ledig fra Leverer, før Avreist når bryteren sier det, aldri på Drift og Plassering — og der finnes verken
grovsorteringsraden i bilen (`_kanGrovsortere`) eller merket hos operatøren (`_grovMerke`) — sjekket i
`stempling_view` etter at overgangen er lovlig, så 409 fortsatt vinner. Sentralbordet leser
tersklene for **uthevingen** av ventende oppdrag forbi første terskel
(`venterForbiTerskel()`, `.oppdrag-rad-venter-lenge`).
«Udefinert» kan opprettes, men **`sett_status` avviser `Ledig` så lenge den står**
(`ProblemstillingUdefinert`, 400 med melding til bilen, og kortet i bilen varsler før
hun trykker); den automatiske lukkingen slipper. **`Oppdrag.antall` settes av bilen**, ikke
operatøren (`POST api/oppdrag/<pk>/antall/<n>/`, `skriv_handling`, som grovsorteringen),
bare der problemstillingen bærer et antall; tomt vises som «1 pasient», ellers «N
pasienter». Tømmes for problemstillinger uten — ikke i arkivet. `Enhet.enhetstype` (FK,
null = «Uten type») grupperer tavla og «Nytt oppdrag» i typenes rekkefølge, alfabetisk
innenfor gruppa (`_grupperEnheter()` i JS; serveren sorterer på `Lower(navn)`), og settes
i enhetspanelet (`PUT api/enheter/<pk>/` med `type` = ID, `skriv_full`).

**Ressurslista viser «ledig siden»** (16. sep. 2026, André). En ledig enhet har ingen aktiv
koblingsrad, så `status_tidspunkt` er tomt og statusen sto som et ord uten tid — mens
operatøren som skal sende noen vil vite hvem som har stått lengst. `services.ledig_siden_bulk()`
leser siste **gjeldende** `Ledig`-melding per enhet, **i denne vakta**: uten scopet ville
fjorårets arrangement stått der som om det var i dag. Bulk, som `avbrutt_av_bulk` — lista
pollet hvert tiende sekund. Feltet sendes bare når enheten faktisk *er* ledig, står i
ETag-en, og klienten viser det gjennom samme `status_tidspunkt || ledig_siden` som alle de
andre statusene: to måter å vise «siden når» er én for mye.

**Enhetskontoen får en rad i varselbjella når hun varsles** (16. sep. 2026):
`services.varsle_bjelle()`, med nummer, hastegrad og klokkeslett — **ikke
problemstillingen**, som er helseopplysning og ikke hører hjemme i en varselrad som blir
stående i 30 dager. **Nøkkelen bærer oppdrags-ID-en** (`bjellenokkel()`), fordi `notify()`
dedupliserer på `kind` i 24 timer: med en fast verdi ville oppdrag nummer to blitt svelget,
og det er nettopp det andre oppdraget hun trenger å se. `les_bjellevarselet()` merker raden
lest når hun rykker ut — ellers hoper bjella seg opp gjennom vakta. Begge kaster aldri, og
begge har `transaction.atomic()` rundt seg: `varsle_enhet` kan kjøre inne i en transaksjon,
og en databasefeil fanget uten savepoint etterlater den ubrukelig.

**Bilens utganger (12. sep. 2026):** «Behandlet på sted» (`BEHANDLET`) er en sidegren
fra Fremme rett til Ledig — `KJEDEN` er lineær, `neste_i_kjeden` gir Ledig etter
Leverer og Behandlet, og `alternativ_for()` gir den andre knappen (Behandlet i Fremme);
Avbryt er egen knapp, i `AVBRYT_FRA`. **Ett trykk på Behandlet skriver Behandlet og Ledig** med samme
tidspunkt (`services.behandle_paa_sted`, Ledig ikke `automatisk`; Udefinert sjekkes før noe
skrives), og bilens projeksjon viser Ledig. Bilen har **ingen egen Ledig-knapp**; stemplingsviewet avviser Ledig
utenom `BILEN_KAN_LEDIG_FRA` med 400. Sentralen (`foer_status`) setter
alle statuser: bakover trekkes meldingene tilbake, aldri slettet; `gjeldende()` siler dem.
«Avbryt» (`choices.AVBRYT`) er en handling, ikke en status: den går i køen som en stempling
(`status/avbryt/`), `services.avbryt_oppdrag` setter raden Ledig (uten Udefinert-sperre —
hun så aldri pasienten), oppdraget til «trenger ny ressurs» og en `Enhetshendelse.AVBRUTT`.
**Sentralen fører «Avbrutt» for bilen** (`foer_avbrutt`, 23. sep. 2026) når den melder det
på samband — samme `AVBRYT_FRA` og samme tjeneste, `manuell`, med operatøren som meldt av og
tidspunktet prøvd som en ny melding. Nedtrekket leser `OPPDRAG_AVBRYT_FRA` fra serveren.
`utledet_av_statuser` rangerer med `choices.AKTIVITET`, ikke `KJEDEN.index`, fordi
Behandlet ikke står i kjeden.

**«Avbrutt» og «trenger ny ressurs» er to ulike beskjeder** (15. sep. 2026). Regelen sto
som ett spørsmål — «finnes det andre enheter som ikke er ledige» — og den kan ikke skille en
bil som ble ledig fordi hun *ble ferdig* fra en som ble ledig fordi hun *avbrøt*: begge er
`Ledig` på koblingsraden. Behandlet Bil A på stedet og Bil B avbrøt, sto det «trenger ny
ressurs» på et ferdig oppdrag. `services.trenger_ny_ressurs()` spør nå begge, og
`LOSER_OPPDRAGET` er `(Behandlet, Leverer)` — **`Ledig` står bevisst ikke der**. Svaret
leses av **statusmeldingene, ikke koblingsradene**: `behandle_paa_sted` sender raden videre
til `Ledig`, så raden bærer ikke spor av at jobben ble gjort. Både `avbryt_oppdrag` og
`start_oppdrag` bruker funksjonen; feilen sto begge steder.

**Avbrytelsen vises som eget merke** (`avbrutt_av` i svaret, `services.avbrutt_av_bulk` for
lista — tavla polles hvert tiende sekund). Merket er **dempet, ikke alarmerende**: en
avbrytelse sier hva som skjedde, «trenger ny ressurs» krever handling nå, og samme farge
ville lært operatøren å overse den ene. Begge kan stå samtidig. **Merket er med i ETag-en** —
en bil som avbryter på et oppdrag noen alt har løst endrer verken status eller tidspunkt, og
det ville ellers druknet i en 304.

Den er den første modulen som tar `skriv_handling` i bruk: bilen får smale, navngitte
stemplingsendepunkter, ikke en feltwhitelist inne i en generell `PUT`. Og skillet mellom de
to grensesnittene er **ikke nivået** — det er om kontoen er knyttet til en `Enhet`. Å knytte
en konto til en enhet gir ingen tilgang; det er domenedata, som `Forstehjelper.user`.

**Aktiv og passiv vakt, og «avvente» (16. sep. 2026, André).** Tre begreper som henger
sammen, og som alle tre er *flagget på enhetstypen*, ikke på enheten:

| Hvor | Felt | Betyr |
|---|---|---|
| `Enhetstype` | `kan_passiv_vakt` | Gruppa kan settes i passiv vakt i det hele tatt |
| `Enhetstype` | `kan_avvente` | Gruppa kan melde «avventer» på et oppdrag |
| `Enhet` | `passiv_vakt` | Står hun i passiv vakt *nå* |
| `Oppdragsenhet` | `varslet_modus` | Modusen **frosset** i det hun ble varslet |
| `Vaktmodusperiode` | `modus`, `fra`, `til` | Hvor lenge hun sto slik |

**Flagget står på typen fordi det er en egenskap ved *slaget* ressurs, ikke ved bilen.**
Spesialressurser (lege, psykososialt) går bakvakt; ambulanser gjør det ikke. Sto flagget
på hver enhet, måtte det settes for hver bil som opprettes, og en glemt avkryssing ville
sett ut som en beslutning. To *separate* flagg, ikke ett: å avvente et
oppdrag og å sove i bakvakt er to ulike ting, og en ressurs kan gjøre det ene uten det
andre.

**Passiv vakt er ikke «av vakt».** Hun *kan* varsles, hun *teller* i beredskapen — hun
holder en 24/7-vakt gjennom hele arrangementet. Passiv tid er der for å **dokumentere**
hvor mange timer og hvor mange oppdrag som falt i tida hun helst skulle sovet. Derfor er
grensesnittet dempet: et merke på ressurskortet, og `Lege 02 (passiv vakt)` på brikka når
hun står på et oppdrag. Er hun aktiv, står det ingenting ekstra.

**Modusen fryses ved varsling, den utledes ikke.** `varsle_enhet` stempler
`gjeldende_modus(enhet)` på koblingsraden. Leste vi enhetens `passiv_vakt` når statistikken
ble regnet ut, ville et oppdrag hun kjørte i passiv vakt hoppet over til «aktiv» i det hun
gikk aktiv neste morgen — og hele poenget med å dokumentere passiv tid ville vært borte.
**Broen i `Oppdrag.save()` stempler den også** — den lager den *første* koblingsraden, og
uten stempelet talte `oppdrag_i_passiv` bare enheter lagt til etterpå (funnet av en mutant).

**`Vaktmodusperiode` er den andre halvparten av svaret.** Stempelet sier hva som gjaldt for
*ett oppdrag*; perioden sier hvor mange *timer* hun sto passiv, også de timene ingenting
skjedde — som er akkurat de timene man vil dokumentere. `sett_vaktmodus()` lukker den åpne
perioden og åpner en ny, er idempotent (samme modus to ganger skriver ingenting), og en
databasesperre (`en_apen_vaktmodus_per_enhet`) holder at det aldri finnes to åpne perioder
for samme enhet i samme vakt. `statistikk.passiv_timer_for(vakt)` summerer dem, og en åpen
periode regnes **fram til nå** — ellers ville vakta som pågår vist null.

**«Avvente» er en beskjed, ikke en status.** En spesialressurs som varsles kan svare at hun
ikke rykker ut nå (`Enhetshendelse.AVVENTER`) — hun **blir stående varslet** på oppdraget,
og operatøren kan trykke «Rykk ut» senere. Begge deler står i loggen. Derfor teller hun
**ikke** som «noen er på vei» i `trenger_ny_ressurs`: står hun avventende alene på
oppdraget, skal det stå «trenger ny ressurs», som er hele grunnen til at spørsmålet stilles.
`avventende_enhet_ider()` leser siste hendelse per enhet, så den som avventet og så rykket
ut ikke blir stående merket. `avventer_av_bulk()` finnes fordi tavla polles
hvert tiende sekund, samme grunn som `avbrutt_av_bulk`.

**Og fordi hun blir stående, er avventingen et merke *på* brikken hennes**
(`enhetAvventer()`, 21. sep.): `avventer_av` bærer nøyaktig de radene som også står i
`enheter`, så et merke ved siden av tegnet henne to ganger. «Avvent» tilbys ikke på en som
alt avventer, og `avvent_oppdrag` er **idempotent** imens: raden står, så ingen av
sjekkene stoppet trykk nummer to.

**Tidslinjen navngir hver type og har ingen «ellers»** (`enhetshendelseTekst()`): grenen
endte på «Tatt av», så avvent sto som tatt av. En ny type skal se rar ut, ikke lyve.
**Og «Fra» i «Flytt oppdrag» er de som fortsatt *har* oppdraget** (`flyttFraEnheter()`):
raden blir stående når en bil melder seg `Ledig`, så hun sto igjen på et oppdrag hun var
ferdig med. «Til» er uendret; knappen heter «Legg til».

**Avbrutt-merket kvitteres** (`kvittert_at`/`kvittert_av` på `Enhetshendelse`). Det forsvant
aldri av seg selv før, og et merke som blir stående gjennom vakta er et merke man slutter å
se. To veier ut: operatøren trykker «Kvitter» i merket, eller **en ny enhet varsles** —
`varsle_enhet` kvitterer, fordi det å sende noen ny *er* svaret på avbrytelsen. `avbrutt_av`
og `avbrutt_av_bulk` filtrerer på `kvittert_at__isnull=True`.

**Arkivet bærer modusen** (`ArkivertOppdrag.varslet_modus`). Den, `behandlet_at` og
`varslet_at`/`grovsortering`/`avreist_til`/`enhetshendelser` fra statistikk 7b står i
SHA-payloaden **bare når de er satt**, så eldre signaturer verifiserer uendret. `Enhetshendelse.varslet_at` settes for alle typer:
raden slettes ved tatt av, og hendelsen må selv huske hvor lenge hun sto bundet.
Statistikken har `enheter_passiv`, `passiv_timer` og `oppdrag_i_passiv`; de to første er
**live-tall** og finnes ikke i arkivet, det tredje overlever fordi stempelet ligger på radene.

**Flaggene krysses av i «Valglister» → Enhetstyper**, gjennom `Verdimengde.ekstra` —
samme mekanisme som `kategori` og `med_antall` på en problemstilling. Å *sette opp* hva en
gruppe ressurser har lov til er `skriv_leder`, mens `skriv_full` styrer beredskapen: samme
skille som i vaktlista mellom å bemanne og å opprette. Klienten har en egen handler,
`settTypeflagg`, og **ikke** `settVerdifelt` med en slug i argumentet — `hendelseArgumenter()`
sender `(id, felt, verdi)` og gjør `data-id` om til et tall, så slugen har ingen vei inn, og
to ID-er kan være like i to verdimengder.

`enhet_vaktmodus_view`, `avvent_view` og `kvitter_avbrutt_view` krever alle `skriv_full`:
de sier noe om beredskapen, ikke om ett oppdrags framdrift, og de er derfor operatørens —
ikke bilens `skriv_handling`.

**Flaten — de to grensesnittene, ressurslista delt med `/ko/`, og sentralbordet i `/ko/` —
står i `templates/oppdrag/CLAUDE.md`** (delt 23. sep. 2026, som KO-fila dagen før). Den
lastes når noen arbeider i `templates/oppdrag/`; `static/js/oppdrag-*.js` laster ingen av dem.
