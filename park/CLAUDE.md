# Park-modulen (park/)

> **Modulfil.** Den lastes når noen arbeider i `park/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Lagenes utfallsregistrering: et lag ute på området registrerer hva det har gjort —
problemstilling × antall, sted og utfall — **uten konto**, gjennom én lenke i et
tiltakskort i Bliksund. Designet og Andrés beslutninger (B1–B23) står i
`docs/FORSLAG_PARK.md`; her står det som må vites før koden røres.

| Regel | Hvor |
|---|---|
| Hvilken lenke som er åpen — og at alle avslag ser like ut | `services.aapen_lenke()` |
| Hvilke lag som kan velges | `services.lagene()` + `Ressursgruppe.registrerer_i_park` |
| Forhåndsvalget av sted: nyeste vinner | `services.forhandsvalg()` |
| Hva som er en gyldig registrering | `services.registrer()` |
| Hva som kan angres, og hvor lenge | `services.kan_angres()`, `angrefrist_min()` |
| Porten uten innlogging og grensene | `views_lag.park_lenke_kreves` |
| Reglene i nettleseren | `park-lag.js` — `parkVelgSted()`, `parkKropp()` m.fl. |

## Portalens første side uten innlogging

`/park/r/` og API-et under svarer en anonym klient. **Alt under `/park/r/` bor i
`views_lag.py`, og den fila leser aldri `request.user`** — en portalbruker som åpner siden i
samme nettleser sender innloggingen sin med, og den skal ikke bety noe. `RuteneTests`
håndhever det på kilden, og at hver API-rute bærer `@park_lenke_kreves`.

- **Tokenet står i fragmentet** (`/park/r/#…`) og sendes i headeren `X-Park-Lenke`. Det
  havner aldri i Railways tilgangslogg. Siden fjerner det fra adressefeltet med
  `history.replaceState` — nettleserloggen lagrer ellers hele adressen.
- **Bare hashen lagres** (`Parklenke.hemmelighet_hash`). Tokenet vises én gang, når lenken
  lages (`manage.py park_lenke --lag …`; oppsettsiden er pulje 2).
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
| `park-ko-posisjon` | Forhåndsvalg fra KO-tavla viser hvor KO har plassert hvert lag | **Bryter**, `AppSetting['park_ko_posisjon']`; på uten rad. Feltet på portalinnstillingene er pulje 2 |
| `park-lenke-en-gang` | Bare hashen lagres, lenken vises én gang | Kode + migrasjon |

## Målingen (B21)

`forhandsvalg_kilde` og `forhandsvalg_endret` på hver registrering svarer på om «nyeste
vinner» treffer: endrer lagene ofte et forhåndsvalg som kom fra KO, er tavla for treg til å
være en god kilde. `forhandsvalg_endret` er `True` bare når klienten sender literal `true`.

## Tilgang

`les` og `skriv_leder` (`module.py`). `les` gir fanen «Lag» i `/statistikk/` (pulje 3) og en
henvisning på `/park/`; `skriv_leder` ser lenkene og registreringene. KO gjør ingenting med
registreringene (B15).
