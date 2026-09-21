# Statistikk-modulen (statistikk/)

> **Modulfil.** Den lastes når noen arbeider i `statistikk/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Egen app siden august 2026. Eier `/statistikk/`-siden og full statistikk
(`/statistikk/api/kilde/<slug>/full-stats/` og
`/statistikk/api/kilde/<slug>/arkiv/<pk>/full-stats/`; de gamle én-kilde-stiene
videresender).
`/pasienter/api/stats/` ble ikke flyttet — det ble **slettet** (28. aug. 2026). Det matet
aldri header-chipsene; de regnes ut i `patients-table.js` fra pasientlista. Endepunktet var
en rest fra Flask-porten uten kjent konsument. `basic_stats()` i `patients.services` står
igjen: den er live-siden av invarianten `StatsMatcher` måler, at arkivering ikke endrer
tallene.

**Avhengighetsretningen er statistikk → moduler, aldri motsatt.** Modulen som eier
dataene regner ut tallene; statistikk-appen henter, cacher og viser — og navngir ingen
kildemodul. Registeret er `core/stats.py`, samme idiom som `core.backup` og `core.arkiv`:
hver modul melder inn en `BaseStatistikkHandler` fra `apps.ready()`. Tre kilder i dag,
`patients/statistikk.py`, `oppdrag/statistikk.py` og `ko/statistikk.py`.

`hent_aktiv_vakt` bor i **`core.vakt`** (flyttet dit 14. sep. 2026, sammen med
`vakt_for_year`): den er portalens scope, delt av alle moduler, og lå i pasientmodulen
fordi `AppSetting`-pekeren gjorde det — så hver modul måtte importere *pasienter* for å
vite hvilken vakt den var i. `StatistikkappenNavngirIngenKilde` leser importene med AST
og håndhever resten.

Ett endepunkt **per kilde**, ikke ett samlet: en fane som ikke er åpnet skal ikke koste
noe, og cache-nøkkelen bærer både slug og vakt-ID. Delte de nøkkel, ville kilde nummer to
servert kilde éns tall i 60 sekunder.

Arkiv-endepunktet har **to gates**: statistikkgaten *og* `er_global_admin`. Arkivet er
strengere beskyttet enn live-statistikken, og hadde det arvet modulens gate ved flyttingen,
ville alle med `les` på statistikk fått innsyn i arkiverte vakter uten at noen bestemte det.

**Modulen komponerer tilgang, den eier den ikke** (§5). Den viser kun kilder brukeren har
minst `les` på i kildemodulen — ellers ville aggregatene gitt avledet innsyn i data
brukeren ikke har tilgang til. Regelen er **«vis det du har tilgang til»**, ikke «alt eller
ingenting»: med to kilder ville det siste tatt statistikken fra alle som leser pasienter
uten å ha oppdrag. Ingen lesbare kilder gir 403 på siden — en statistikkside uten tall er
en side som later som den virker.

**Oppdragstallene utelater varigheter som slutter i en automatisk stempling** (§12.2 i
oppdragsnotatet). Sluttiden er da avledet, ikke målt. Oppdraget telles i alle antall og
fordelinger, og både det og negative varigheter rapporteres i `summary['utelatt']` og vises
på siden.

## Frontend — to filer, og gaten mellom dem

Hva som lastes når står i rota; hva filene gjør står her.

| Fil | Ansvar |
|---|---|
| `statistikk.js` | Pasientstatistikk (Chart.js), arkivmodus, kildefanene |
| `statistikk-oppdrag.js` | Oppdragsfanen |
| `statistikk-ko.js` | KO-fanen (pulje 7a). Lastes kun med KO-tilgang; samme vakt |

**Chart.js lastes kun her.** Den er tung, og ingen annen side tegner grafer.

**`statistikk-oppdrag.js` lastes bare for den som har oppdragstilgang, og
`statistikk-ko.js` bare med KO-tilgang** — samme komposisjonsregel som endepunktene
følger. Kall fra `statistikk.js` går derfor gjennom `_kallOppdrag('navn')` (navnet er
historisk; vakten er felles), som sjekker at funksjonen finnes: et direkte kall ville vært en
`ReferenceError` for alle som ser pasientfanen uten å ha oppdrag, og siden ville dødd på
et faneskift i stedet for å vise den ene fanen brukeren faktisk har.

**Byggerne i begge filene skannes av `patients/tests_xss_stats.py`.** Legger du til en ny
bygger, skal den stå i lista der — en skanner som melder grønt om en dekning den ikke har,
er verre enn ingen skanner.

**Tabellene rulles på beholderen, ikke på tabellen** (`stats-rull`, 12. sep. 2026). De
bygges med `innerHTML`, og en tabell med `display: block` mister bredden sin.
`TabelleneRullerPaaTelefonTests` krever klassen på hver `tbl-*`/`xt-*`-beholder i begge
fanene.

## Oppdragsfanen etter pulje 7b (21. sep. 2026)

Utregningen bor i `oppdrag/statistikk.py`; det som står her er reglene som gjør at fanen
kan leses likt live og fra et arkiv. Forslaget og skissene: `docs/FORSLAG_KO_STATISTIKK.md`.

**Radformen bærer alt tallene trenger, og arkivet fryser den samme formen.** En rad er én
enhets innsats på ett oppdrag; radens egne felt er `varslet_at` og `avreist_til`, og
oppdragets — `grovsortering`, `enhetshendelser` — gjentas på hver rad som hastegraden gjør.
Hendelsene *må* stå på oppdraget: en enhet som ble tatt av har ingen rad, og «tildelt, men
rykket aldri ut» er nettopp henne. `avreist_til_tekst` er fritekst og finnes bare live.

**«Uten ressurs» rekonstrueres, ikke leses.** `trenger_ressurs_siden` tømmes når en ny
enhet varsles, så intervallene regnes av opprettelsen og av hver avgang som etterlot
oppdraget alene (`_andre_aktive` stiller `trenger_ny_ressurs`-spørsmålet i ettertid), fram
til neste varsling **eller** neste Rykker ut. Et åpent intervall slutter ved «nå» live og
ved `importert_at` i et arkiv — aldri ved nå for en vakt som er over.

**Ventetida = KO-ventetid + reaksjonstid.** Det gamle tallet står fortsatt; de to nye
summerer til det. Reaksjonstid går gjennom `_Varigheter`, så en negativ (klokke som gikk
feil) telles i `utelatt.negativ` som de andre. Passiv vakt holdes i eget ledd.

**Alle fem hastegradene, i AMK-rekkefølge, også på null** — `_i_hastegradrekkefolge` er
det ene stedet. Fargene i `statistikk-oppdrag.js` følger navnet; grått er for en verdi
ingen kjenner.

**Fiksturen må sette `varslet_at`.** `Oppdrag.save()` lager koblingsraden med nå, og en
test som skrur `created_at` tilbake uten å flytte varslingen får negativ reaksjonstid på
hvert oppdrag. `_oppdrag()`-hjelperne gjør det; en ny testfil skal også.

**Byggerne bygger celler med `+`, ikke mal-strenger**, og kolonnelister står inline: en
`${...}` i en bygger skal kunne leses som «escapet her», og testharnessen henter
navngitte funksjoner, så en toppnivå-`const` er en `ReferenceError` der. Et arkiv frosset
før 7b mangler nøklene; `_tegn7b` lar seksjonene stå tomme, og `_sdRad` tåler at `p90`
mangler.

## KO-fanen (pulje 7a, 21. sep. 2026)

Utregningen bor i `ko/statistikk.py`; retningen er `ko` → `oppdrag`, som ellers i modulen.
Ingen arkiv — KO-loggen fryses aldri — så `arkiv_full_stats` er `None`.

**Hendelser, ikke personer, og ikke per operatør.** Setningen øverst i fanen er det ene som
hindrer at tre registre summeres til «pasienter» (notatet §8). André, 21. sep.:
«ansvarsområde er ikke viktig, trenger ikke per person» — loggens tall går per time og per
slag (rettinger, fjerninger, deling, KO-førte og forsinkede stemplinger).

**Lag på hendelsen regnes av systemlinjene**, ikke av `HendelseLag`: raden slettes når
laget tas av, linjene `hendelse_lag_paa`/`_av` og laglista på `hendelse_opprettet` står.
`lagperioder()` er det ene stedet, og «bare lag» i «hvem løste hendelsen» avhenger av den —
ellers ble et lag som ble tatt av før lukkingen til «verken». Et `til`-felt på raden er
bevisst ikke tatt: det rører hvem tavla og skjemaet viser som «på hendelsen nå».

**Tid til første ressurs** starter når KO hørte om hendelsen; et oppdrag knyttet til fra
før den fantes teller som null. `alle` regnes av hendelsene, ikke av medianene per
prioritet — medianen av medianer er ikke en median.

**Stillhet** er hullet mellom to operatørlinjer, og fra den siste til nå, målt når minst
én hendelse sto åpen *da hullet begynte*; under ett minutt er ikke et hull. Tre vises.

**Fiksturen må sette `registrert_at`** på linjene: feltet er `auto_now_add`, og tid til
retting og til deling regnes av det. `_linje()` i `ko/tests_statistikk.py` gjør det.
