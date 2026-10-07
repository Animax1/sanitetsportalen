# Park-modulen (park/)

> **Modulfil.** Den lastes når noen arbeider i `park/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

**Brukerne ser «Lagregistrering» på `/lag/`; koden heter `park`** (André, 28. sep. 2026:
«Lagregistrering og /lag/»). Portalen brukes på flere arrangementer enn et med en park. Bare det
synlige ble byttet — menyen, overskriftene, adressen. Appnavnet, tabellene, modul-sluggen i
`ModulTilgang`, `AppSetting`-nøklene og backup-sluggen står som `park`, fordi å gi en Django-app
nytt navn rører migrasjoner, tabeller, tilgangsrader og backupfiler offsite — uten at noen
bruker ser forskjell. Samme skille som `patients` på `/pasienter/`. Det er ikke en glipp.

Lagenes utfallsregistrering: et lag ute på området registrerer hva det har gjort —
problemstilling × antall, sted og utfall — **uten konto**, gjennom én lenke i et
tiltakskort i Bliksund. Designet og Andrés beslutninger (B1–B23) står i
`docs/FORSLAG_PARK.md`; her står det som må vites før koden røres.

| Regel | Hvor |
|---|---|
| Hvilken lenke som er åpen — og at alle avslag ser like ut | `services.aapen_lenke()` |
| Hvilke lag som kan velges | `services.lagene()` + `Ressursgruppe.registrerer_i_park` |
| Hvilke steder lagene ser — oppdragsmodulens, minus `SkjultSted` | `services.steder()`, den ene lista nedtrekket, valideringen og forhåndsvalget går gjennom |
| Forhåndsvalget av sted: nyeste vinner | `services.forhandsvalg()` |
| Hva som er en gyldig registrering | `services.registrer()` |
| Hva som kan angres, og hvor lenge | `services.kan_angres()`, `angrefrist_min()` |
| Porten uten innlogging og grensene | `views_lag.park_lenke_kreves` |
| Sletting av feilregistreringer, én og alt fra en lenke | `services.slett_registrering()`, `slett_fra_lenke()` |
| Lagringstiden: 730 dager, så slettes raden | `services.utlopte()`, `slett_utlopte()`, `opprydding.py` |
| Hvem som setter opp hva på `/lag/` | `views.py`, tabellen i docstringen |
| Registreringslista på `/lag/`: hele vakta hentes, 200 tegnes, filteret søker i alt | `park-oppsett.js` — `parkFiltrer()`, `parkTellertekst()` |
| Tallene i fanen «Lag»: kontakter, ikke pasienter; slettede utelatt | `statistikk.py` |
| Reglene i nettleseren | `park-lag.js` (lagene), `park-oppsett.js` (oppsettet) |
| «Vi finner ikke fram»: lagets posisjon til kartet, midlertidig | `views_lag.hjelp_view`, `services.hjelp_varighet_min()`, `parkSendHjelp()` |

## Portalens første side uten innlogging

`/lag/r/` og API-et under svarer en anonym klient. **Alt under `/lag/r/` bor i
`views_lag.py`, og den fila leser aldri `request.user`** — en portalbruker som åpner siden i
samme nettleser sender innloggingen sin med, og den skal ikke bety noe. `RuteneTests`
håndhever det på kilden, og at hver API-rute bærer `@park_lenke_kreves`.

- **Tokenet står i fragmentet** (`/lag/r/#…`) og sendes i headeren `X-Park-Lenke`. Det
  havner aldri i Railways tilgangslogg. Siden fjerner det fra adressefeltet med
  `history.replaceState` — nettleserloggen lagrer ellers hele adressen.
- **Bare hashen lagres** (`Parklenke.hemmelighet_hash`). Tokenet vises én gang, når lenken
  lages — på `/lag/` eller med `manage.py park_lenke --lag …`, som står igjen som reserve.
- **Ugyldig, fjernet, stengt lenke, modulen av og ingen åpen vakt gir samme 403.**
- **Svarene inneholder aldri registreringer** — heller ikke lagets egne. Kvitteringen er det
  klienten sendte, pluss en teller.
- **`csrf_exempt` er riktig her**, og begrunnet ved dekoratøren: ingen sesjon å verne, og en
  egen header utløser en CORS-preflight serveren ikke besvarer.
- **Siden laster ikke `portal-utils.js`**, og bruker derfor rå `fetch` — unntaket står i
  `core/tests_brukeraktivitet.py`.

**Tre bøtter for rate-limit:** per telefon (tilfeldig ID fra `localStorage`, ingen person),
et tak per lenke, og per IP **bare** for ugyldige tokens. Ikke per IP på gyldige: telefoner
på mobilnett deler adresse bak operatørens NAT, og ti lag kan stå bak samme.

## «Vi finner ikke fram» (7. okt. 2026)

«En help me I'm lost-knapp» (André): et lag som har gått seg bort, sender posisjonen sin til
kart.sanitet.net, og KO ser den **oransje** — atskilt fra der KO har plassert laget. Egen boks
under registreringen, og bare med kartkoblingen satt opp.

- **Telefonen spør først ved trykket.** Ingen `watchPosition`, ingen spørsmål ved lasting;
  `parkHentPosisjon()` kalles bare fra knappens handler. `PosisjonSpoerresBareVedTrykketTests`
  leser kilden, fordi siden ikke lar seg kjøre hel i node. `side_view` gir `geolocation=(self)`
  bare med koblingen satt opp; resten av portalen har `()`.
- **Egen frist rundt spørsmålet** (`parkMedFrist`, 25 s): `timeout` i `getCurrentPosition` teller
  først når tilgangen er gitt, så et spørsmål som aldri vises eller besvares, ga aldri svar — knappen
  sto på «Henter posisjon…» (André, 7. okt.). `parkPosisjonstilgang()` sier et nei med en gang.
- **Laget er det som står valgt i skjemaet over** — uten valgt lag spørres ikke telefonen.
  ID inn, `Ressurs.navn` fra basen ut, som alt annet her.
- **Midlertidig:** `utloper` = nå + `hjelp_varighet_min()` (15 som standard, 1–120 på
  portalinnstillingene) sendes som **tidspunkt**, så kartet ikke trenger å kjenne innstillingen.
  Kartet sletter raden da (`Laghjelp` i `kart-sanitet`).
- **Lagres ikke i portalen**, og er ingen registrering. Sendes direkte, ikke i `on_commit`:
  ingenting skrives, og laget skal få vite om kartet tok imot (502 → «meld på samband»).
- **Bremsen teller sendingene, ikke avslagene** — 6/min per telefon, etter valideringen.

## Ingen fritekst

Registreringene kommer fra noen vi ikke vet hvem er. Et fritt felt ville vært der et navn
havner en travel kveld. Alt er ID-er validert mot det siden selv tilbyr, og navnene fryses
som tekst på raden — en omdøpt problemstilling skal ikke skrive om historikken.

## Forhåndsvalget: det nyeste vinner (B19)

KOs åpne plassering på tavla (`fra`) mot lagets siste registrering (`registrert_at`) —
**begge med serverens klokke**. Telefonens eget minne brukes bare når serveren ikke har noe,
og aldri i en sammenligning: telefonklokka kan stå hvor som helst. Står de likt, vinner
registreringen (et faktum, ikke en beslutning).

**Park importerer ikke `ko`.** KO melder plasseringene inn i `core/ressursplassering.py`
(`ko/ressursplassering.py`), og park spør registeret. En avslått KO spørres ikke, og en
feilende kilde gir `None`, ikke 500. `RuteneTests.test_ingen_annen_modul_importerer_park`
holder den andre retningen: park leser `vaktliste` og `oppdrag`, ingen av dem kjenner park.

## Risikovalgene

Merket i koden med `# RISIKOVALG(park-<navn>)` — `grep RISIKOVALG` finner alle, og hvert
merke peker til `docs/FORSLAG_PARK.md` §4.7, der alternativet står.

| Merke | Hva | Byttes |
|---|---|---|
| `park-ko-posisjon` | Forhåndsvalg fra KO-tavla viser hvor KO har plassert hvert lag | **Bryter** på `/portal-admin/innstillinger/` (`park/portalinnstillinger.py`); på uten rad |
| `park-lenke-en-gang` | Bare hashen lagres, lenken vises én gang | Kode + migrasjon |

## Målingen (B21)

`forhandsvalg_kilde` og `forhandsvalg_endret` på hver registrering svarer på om «nyeste
vinner» treffer: endrer lagene ofte et forhåndsvalg som kom fra KO, er tavla for treg til å
være en god kilde. `forhandsvalg_endret` er `True` bare når klienten sender literal `true`.

## Steder skjult for lagene (B24)

«Det er enkelte lokasjoner som er uaktuelt for dem men ikke bil ressurser» (André, 28. sep.
2026). **Parks egen tabell, `SkjultSted`, ikke et flagg på `oppdrag.Lokasjon`** — hvilke steder
som er aktuelle for lagene er parks spørsmål. En rad betyr skjult; **nye steder vises til noen
skjuler dem**, fordi et lag som ikke finner stedet sitt ikke får registrert. Pekeren til
lokasjonen strippes *ikke* i backupen — uten den er raden meningsløs — og park står alt etter
`oppdrag` i gjenopprettingen.

## Sletting, ikke retting (B20)

En feilregistrering **slettes** av `skriv_leder`, med en grunn — den rettes ikke. En sletting
og en ny registrering fra laget er ærligere enn at noen andre skriver om det laget sa. Raden
blir stående merket, og statistikken utelater den.

**«Slett alt fra denne lenken etter kl. X»** er oppryddingen etter en lekket lenke (§4.6).
Uten `confirm` svarer den **409 med antallet** og sletter ingenting — den som rydder skal se
hvor mye som går før det går. Én auditrad for hele slettingen, ikke én per rad.

## Lagringstiden

Registreringene slettes **730 dager** etter `registrert_at` — `services.OPPBEVARING_DAGER`,
håndhevet av `purge_old_logs` gjennom `park/opprydding.py` (`core/opprydding.py`). **En
konstant, ikke en innstilling:** fristen er det personvernbeskrivelsen lover, og et tall som
kan flyttes i portalen er et løfte dokumentet ikke kan holde. Rader merket slettet (B20)
følger samme frist. Ingen auditrad per slettet rad — registreringene logges ikke når de kommer
inn heller. `park/tests_opprydding.py` går gjennom kommandoen, ikke hjelperen.

## Tilgang

`les` og `skriv_leder` (`module.py`). `les` gir fanen «Lag» i `/statistikk/` (sammen med
`statistikk: les`, B17 — `park/statistikk.py`) og en
henvisning på `/lag/`; `skriv_leder` setter opp lenkene og problemstillingene og sletter.
**Utfallene er global admin** (B7), og å slette en rad fra en verdimengde likeså
(`core.verdilister`). KO gjør ingenting med registreringene (B15).
