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
| Bilen rykker videre → oppdraget **trenger ny ressurs**, ikke ferdig | `Oppdrag.trenger_ressurs` + `trenger_ressurs_siden`, `services.start_oppdrag` |
| «Trenger ny ressurs» spør **to** ting: er noen på vei, *og* var noen framme | `services.trenger_ny_ressurs()` |
| Lista sorteres på hastegrad, så nummer; ferdige nederst | `_sorterOppdrag()` i `oppdrag-sentral.js` |
| Bilen melder Ledig bare fra Leverer og Behandlet; Avbryt i Rykker ut, Behandlet på sted i Fremme | `services.BILEN_KAN_LEDIG_FRA`, `ALTERNATIV`, `avbryt_oppdrag` |
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
og før Ledig fra Leverer, før Avreist når bryteren sier det, aldri på Drift — og på Drift finnes verken
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

**Bilens utganger (12. sep. 2026):** «Behandlet på sted» (`BEHANDLET`) er en sidegren
fra Fremme rett til Ledig — `KJEDEN` er fortsatt lineær, `neste_i_kjeden` gir Ledig etter
Leverer og Behandlet, og `alternativ_for()` gir den andre knappen (Avbryt i Rykker ut,
Behandlet i Fremme). **Ett trykk på Behandlet skriver Behandlet og Ledig** med samme
tidspunkt (`services.behandle_paa_sted`, Ledig ikke `automatisk`; Udefinert sjekkes før noe
skrives), og bilens projeksjon viser Ledig. Bilen har **ingen egen Ledig-knapp**; stemplingsviewet avviser Ledig
utenom `BILEN_KAN_LEDIG_FRA` med 400, mens sentralens føring følger `OVERGANGER` som før.
«Avbryt» (`choices.AVBRYT`) er en handling, ikke en status: den går i køen som en stempling
(`status/avbryt/`), `services.avbryt_oppdrag` setter raden Ledig (uten Udefinert-sperre —
hun så aldri pasienten), oppdraget til «trenger ny ressurs» og en `Enhetshendelse.AVBRUTT`.
`utledet_av_statuser` rangerer med `choices.AKTIVITET`, ikke `KJEDEN.index`, fordi
Behandlet ikke står i kjeden. Arkivraden har `behandlet_at`, som står i SHA-payloaden
**bare når satt** — eldre arkiv har ingen slik nøkkel i signaturen sin.

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
