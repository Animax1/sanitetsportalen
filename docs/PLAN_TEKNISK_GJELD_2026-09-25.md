# Plan: funnene fra kodegjennomgangen 25. september 2026

Status: **plan, 25. september 2026.** Arbeidslista er fortsatt `TODO.md`. Der står én linje
per pulje, som peker hit. Dette notatet bærer funnene, hvorfor de er sortert som de er, og
hva som skal til for at en pulje er ferdig. Slettes når alle puljene er levert eller strøket.

## 0. Hva som ble gjort, og hva det er verdt

- **Omfang.** Hele appen ble lest, fordelt på fem områder:
  - `core`/`audit`/`accounts`/`myproject`
  - `patients`/`statistikk`/`backlog`
  - `oppdrag`/`ko`
  - `vaktliste`
  - frontend og oppsett
- **Grunnlag.** Revisjonen er gjort på **staging, bygg `7c21318`**.
- **Bare lesing.** Ingenting ble endret, og ingen tester ble kjørt.
- **Kontroll.** Alle funn merket «Høy» er kontrollert mot koden en gang til, av en annen
  leser enn den som fant dem. Resten bygger på én lesing med `fil:linje`, og skal leses på
  nytt før de rettes. Linjenumrene gjelder `7c21318`, og de flytter seg.

**Nesten alt ligger også i prod.** `main` står på `636e1f2`, tolv commits bak staging. Av
funnene under er det bare **C1 (overnattingen)** som finnes på staging og ikke i `main`.
Alt annet er prods oppførsel i dag.

**Pseudokode fantes nesten ikke.** Det er null `TODO`/`FIXME` i koden, null utkommentert
kode og null `console.log`, og alle `NotImplementedError` står i abstrakte baser. Det
nærmeste er flater som later som de gjør noe:

| Flate | Problem | Behandles i |
|---|---|---|
| `backup_enabled` | En bryter uten virkning | D4 |
| `Patient.is_active` | Et filter ingen setter | C3 |
| `Vaktpost.avmeldt_at` | Et felt uten skrivevei | C4 |
| `lokasjon`-kommandoen | Mener modulen mangler URL | F1 |

## 1. Rekkefølgen, og hvorfor

Puljene er sortert etter **hva en feil koster**, samme regel som puljene fra 16. sep.:

1. Først det som gir feil i drift eller i data.
2. Så sporene og tilgangen.
3. Så verifiseringen.
4. Til slutt vedlikeholdet.

**Én avhengighet binder:**
- **A1 før deploy 2.** Rettingen av bjella tar bort den ene koden som lager den første
  enhetens koblingsrad gjennom broen. Fjernes broen først, mister den første bilen raden
  sin helt.

**Tre ting er ikke bindende, men lønner seg:**
- **D1 (CI) tidlig.** A3 er en feil som bare finnes i PostgreSQL, og den ville vært rød i
  en CI med Postgres.
- **F2 før F-resten.** Rot-`CLAUDE.md` har rundt 170 tegn igjen av taket. Rettingen av
  audit-avsnittet må ikke gjøre den lengre.
- **C1 før neste `staging → main`.** Overnattingen går til prod med den merge-en.

**Tre rotårsaker går igjen.** De er verdt mer enn enkeltrettingene:

| Rotårsak | Funn den forklarer | Motmiddel |
|---|---|---|
| Lister som vedlikeholdes for hånd | A2 (ETag-felter), B5 (`STENGT_GET`), B3 (auditens feltlister) | Utled fra koden, slik `get_restore_models()` gjør |
| Tester som kaller hjelperen i stedet for inngangen | A1 (`VarselbjellaTests`), D2 (død kode som testene holder i live) | Minst én test per regel gjennom det ekte endepunktet |
| SQLite lokalt, og ingen CI | A3, og ~160 JS-tester som hopper stille over når node mangler | D1 |

---

## Pulje A: feil i drift (før neste vakt)

Hver retting skal ha en test **gjennom endepunktet** som er rød før rettingen. Laget er
tjenestelag og view, så mutasjonstestingen er **tung** for A1–A6 og **middels** for A7–A8.

**A1. Bjella ringer ikke for den første bilen på et oppdrag.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `oppdrag/views.py:496-506`.
- **Feilen:**
  - POST oppretter oppdraget med `enhet=enheter[0]` og varsler bare `enheter[1:]`.
  - Broen i `Oppdrag.save()` (`models.py:434-455`) lager koblingsraden uten
    `varsle_enhet`, og dermed uten `varsle_bjelle`.
  - Det vanligste tilfellet, én bil, gir ingen rad i bjella.
- **Retting:** opprett med `enhet=None`, og kall `varsle_enhet` for **alle** enhetene. Den
  setter selv `oppdrag.enhet`.
- **Test:** POST med én enhet skal gi én rad i bjella.

**A2. ETag-ene er satt sammen av feltlister skrevet for hånd.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `oppdrag/views.py:191-199`, `:403-409` og `:436-441`.
- **Feilen:**
  - Hastegrad, problemstilling, lokasjon, antall, grovsortering, fritekst,
    `trenger_ressurs` og enhetslista mangler.
  - En redigering inne i oppdraget (levert 23. sep.) gir 304 hos de andre operatørene.
  - Det samme gjelder en enhet nummer to som varsles på et oppdrag som er i gang.
- **Retting:** hash hele den serialiserte payloaden (`json.dumps(..., sort_keys=True,
  default=str)`), ikke en liste med felt man må huske. Det lukker feilklassen, ikke bare
  dagens tilfeller.
- **Test:** PUT hastegrad og krev en ny ETag. Mutanten er å fjerne ett felt fra
  serialiseringen, og da skal testen bli rød.

**A3. `_trygt` fanger unntak uten savepoint.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `ko/signals.py:59-74`.
- **Feilen:** mottakerne kjører inne i `transaction.atomic()`. I PostgreSQL avbryter en
  databasefeil hele transaksjonen, og stemplingen feiler likevel. SQLite har ikke den
  oppførselen, så suiten er grønn.
- **Retting:** `with transaction.atomic():` rundt `fn(...)`, slik `varsle_bjelle` gjør.
- **Test:** krever PostgreSQL for å bli rød. Ta den med i D1, eller som en prøve i
  `core/migrasjonsprover.py`-stil.

**A4. «Flytt» i Venter tar med seg den gamle bilens varsling.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `oppdrag/services.py:1274-1276`.
- **Feilen:** `varslet_modus` og `varslet_at` blir stående.
  - Passiv-statistikken og lydterskelen regnes fra feil bil.
  - Den nye bilen får ingen rad i bjella.
  - `enhet_varslet` i KO fyrer ikke.
- **Retting:** `ta_av_enhet` pluss `varsle_enhet` med samme `rekkefolge`.

**A5. PUT i `oppdrag_detalj_view` lagrer uten `update_fields`.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `oppdrag/views.py:702`.
- **Feilen:** en stempling som kommer mellom lesingen og lagringen, blir overskrevet med
  gamle verdier.
- **Retting:** `update_fields` med feltene som faktisk endres.

**A6. En arkivert vaktliste i drift styrer fortsatt.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `vaktliste/views.py:345-348`.
- **Feilen:** lista er borte fra velgeren, men fire steder ser fortsatt den arkiverte:
  - besetningen på sentralbordet
  - «lista i bruk» i KO
  - e-postutsendingen, som sender telefonnumrene
  - driftstatus
- **Retting:**
  1. **Avvis arkivering av en liste i drift (409)**, i samme ånd som «knappen som fører
     til en vegg»: si fra, ikke gjør noe halvt.
  2. `arkivert_at__isnull=True` i `vaktliste_i_bruk()`, `besetning()`,
     `fil.send_planlagte()` og `driftstatus.vaktbilde()`, for lister som ble arkivert før
     sperra kom.
- **Samtidig:** `besetning()` skal sortere som `vaktliste_i_bruk()`
  (`-satt_i_drift_at`, `services.py:1483`). Ellers kan de to vise hver sin liste for samme
  bil når to lister står i drift.

**A7. `vaktposter_view` gir 500 på en ledig plass.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `vaktliste/views.py:1402-1408`.
- **Feilen:** `except IntegrityError` leser `mannskap.navn` når `mannskap` er `None`.
- **Samme mønster, feil melding:** `ressurser_view`, `ressurs_detalj_view` og
  `vaktpost_detalj_view` svarer «finnes allerede» når feilen er en ugyldig FK.
- **Retting:** slå opp FK-ene før skrivingen, og la grenen tåle `None`.

**A8. Tilstedeværelsen fra 16. sep. virker ikke for synlige faner.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:**
  - `static/js/notifications.js:50` har sin egen `fetch` uten `X-Portal-Inaktiv`, og
    kjører på alle portalsider.
  - Auto-refresh på pasientsiden og server-status bruker rå `fetch` på samme måte.
- **Feilen:** middlewaren regner en manglende header som en handling. En glemt, synlig fane
  ser derfor «aktiv nå» ut hvert 30. sekund.
- **Retting:** la alle tre gå gjennom `apiFetch` i `portal-utils.js`, eller send headeren.
- **Test:** node-test som kjører `pollCount` og krever headeren.
- **Vurder:** en test som leter etter rå `fetch(` i `static/js/` utenfor `portal-utils.js`,
  med en unntaksliste.

**Ferdig når:** alle åtte har en test som er rød uten rettingen, mutantene er ført i
CHANGELOG, og det er verifisert på staging med byggnummer.

**Anslag:** 3–4 kvelder.

---

## Pulje B: spor, tilgang og lekkasjer

**B1. Låsemeldingen avslører at brukernavnet finnes.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `accounts/views.py:468-470`.
- **Feilen:** bare en konto som finnes kan få «Kontoen er låst». Kommentaren M14 rett over
  påstår det motsatte.
- **Retting:** alltid «Feil brukernavn eller passord.». Låsingen virker uansett.

**B2. Hull i auditloggen i brukeradministrasjonen.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:**
  - `reset_password` og `unlock` (`accounts/views.py:1278-1290`) logger ingenting.
  - `edit` logger bare `role` og modultilgang. Endringer av `mfa_required`,
    `er_delt_konto`, `email` og `fullt_navn` blir ikke logget.
  - Sletting av backup (`core/views_backup.py:191`) har verken audit eller bekreftelse.
- **Retting:**
  - Logg hver `action`-gren.
  - Diff hele `changed_data`.
  - Krev `confirm` og skriv audit ved sletting av backup.

**B3. Hull i auditloggen i vaktlista.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `vaktliste/signals.py`.
- **Feilen:** disse logges ikke:
  - opprettelse og sletting av en vaktliste
  - `timetak`, som ikke står i `VAKTLISTE_FELTER`
  - `Belastningsgrenser`
  - `Korps`, `Kompetanse`, `Ressursgruppe` og `Ressursrolle`
- **Retting:** mottakere gjennom `_logg_*`.
- **Bør vurderes:** å utlede feltlista fra modellen minus en unntaksliste, slik `AppSetting`
  gjør med `NOKLER_UTEN_AUDIT`. En ny kolonne bør logges som standard.

**B4. `accounts/admin.py` går utenom sperrene rundt superbruker og rolle.** *Levert 26. sep. 2026 (André: skrivebeskyttet), se CHANGELOG.*
- **Når:** bare når `DEBUG=True`, så risikoen er lav i prod.
- **Retting:**
  - Gjør ModelAdmin for `CustomUser` skrivebeskyttet, eller fjern den.
  - Utvid `RollenSettesBareGjennomSkjemaeneTests` til å fange `fields` med
    `role`/`is_superuser` og `.update(role=`.

**B5. `scripts/sikkerhetssjekk.py` mangler `/ko/`, `/backlog/` og `/api/endringer/`.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Retting:** utled `STENGT_GET` fra `urlpatterns`, som `tests_modul_dekorator` gjør.

**B6. Datofiltrene gir 500 på en ugyldig dato.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `core/views_admin.py:220-223` og `accounts/views.py:808-811`.
- **Retting:** én felles parser som ignorerer ugyldige verdier.

**B7. Rå unntakstekst fra e-postutsendingen vises for alle med `les`.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `Utsending.feil` (`vaktliste/fil.py:228-230`).
- **Retting:** vask teksten med samme funksjon som server-status bruker (se E6).
- **Samtidig:** `send_fil` lover «kaster aldri», men `rader_for` og `brannliste` kjøres
  utenfor `try`.

**B8. Pasient-POST og -PUT forkaster en ugyldig ID stille.** *Levert 26. sep. 2026, se CHANGELOG.*
- **Hvor:** `patients/views_patients.py:219-233` og `:391-409`.
- **Feilen:** svaret er 201/200 med tildelingen satt til `None`, og uten varsel.
- **Retting:** 400, og ett felles oppslag i stedet for fire kopier.

**Mutasjonstesting:** **tung** for B1–B3. Dette er tilgang og revisjonslogg, og en mutant
som overlever her blir ikke sett av noen.

**Anslag:** 2–3 kvelder.

---

## Pulje C: avgjørelser før koden kan skrives

Hvert punkt er et valg mellom å rette koden og å rette løftet. Anbefalingen står, men valget
er Andrés.

**C1. Overnattingsfanen viser skiftdetaljer fra andre korps til en ren `les`-bruker.** *Levert 26. sep. 2026 (André: «a»), se CHANGELOG.*
Punktet finnes **bare på staging**.
- **Hvor:** `vaktliste/overnatting.py:307-331` og `:363`.
- **Hva brukeren ser:** «Ola, Karmøy: Ambulanse 2, 22:00–06:00». Hovedkallet filtrerer de
  samme skiftene bort (`views.py:468`).
- **Anbefaling:** den som ikke ser alle korps, får bare «på vakt i natt: ja/nei». Detaljene
  følger `vis_telefon`.
- **Tidspunkt:** avgjøres **før neste `staging → main`**.

**C2. Planleggerens kladd er synlig for `les_alle` og `skriv_handling`.** *Levert 26. sep. 2026 (André: skjul, skriverett = `skriv_full`+), se CHANGELOG.*
- **Hvor:** `vaktliste/services.py:852`.
- **Løftene som brytes:** tre kommentarer og grensesnittet sier «usynlig for korpsene til du
  deler dem ut»:
  - `services.py:428-432`
  - `services.py:934-937`
  - `vaktliste-oversikt.js:1046`
- **Anbefaling:** filtrer kladden bort under `skriv_full`.
- **Uansett valg:** en test for synligheten. I dag er bare `er_planlagt()` prøvd.

**C3. Skal `Patient.is_active` inn eller ut?**
- **Status:** ingen kode setter feltet til `False`, ingen JS sender `?include_archived`, og
  DELETE-grenen i `patients/signals.py:132` kan ikke nås.
- **Anbefaling:** ut. Fjern parameteren og signalgrenen, og deretter feltet med en egen
  migrasjon.

**C4. Skal `Vaktpost.avmeldt_at` samles eller fjernes?**
- **Status:** feltet har ingen skrivevei, og fire lesere utelater avmeldte mens fire tar dem
  med.
- **Anbefaling:** ett predikat for «på vakt» (`Q`) i `services`, brukt overalt, før noen
  bygger avmeldingsknappen. Eller fjern feltet til flyten finnes.

---

## Pulje D: verifiseringen

**D1. CI med PostgreSQL og node.** Erstatter punktet «Vurder GitHub Actions» i TODO. *Levert 26. sep. 2026 (bare staging og main), se CHANGELOG.*
- **Jobbene:**
  - hele suiten mot PostgreSQL
  - migrasjonsprøvene
  - node-testene
- **Og:** med `KREV_NODE=1` skal en manglende node **feile**, ikke hoppe over.
- **Hvorfor:** ~160 JS-tester hopper stille over i dag (`skipUnless(node_available())`).
  En maskin uten node får en grønn suite der `avgjor()`, `klikkSkalKjore()` og de andre
  JS-reglene aldri har kjørt.

**D2. Død kode som testene holder i live.** *Levert 26. sep. 2026, se CHANGELOG.* Løgn nr. 3 i mutasjonsavsnittet i
`CLAUDE.md`, i praksis. Slett koden og testene, eller flytt funksjonen til den ideen den
hører til:
- `_posterPerGruppe()` (`vaktliste-oversikt.js:86`)
- `_koMedianP90()` (`statistikk-ko.js:49`)
- `services.vaktspenn()` (`vaktliste/services.py:1664`)
- `patients.services.kollaps_arkiv`
- `har_arkiv_backup_etter`
- re-eksporten av `core.validators` med `BakoverkompatibilitetTests`

**D3. XSS-skannerne.** *Levert 26. sep. 2026, se CHANGELOG.*
- `backlog.js` bygger markup med `+` og har ingen statisk skanner.
- KO har sin egen skanner for `+`. Utvid den til `backlog.js`, og løs vaktlistas kjente
  `+`-gap (eget punkt i TODO) med samme mekanisme.

**D4. Brytere og filtre uten virkning:** *Levert 26. sep. 2026 (`backup_enabled` i to deploys, den andre står i TODO), se CHANGELOG.*
- **`ModuleSettings.backup_enabled`:** fjern fra skjema, maler og admin, og deretter
  kolonnen. Fjern `BACKUP_APPS`-unntaket i `tests_dokumentråte.py` i samme commit.
- **`/api/`-fanger-alt i `core/urls.py:80`:** svar 404/410. En POST mister kroppen i en
  301.
- **`createcachetable` i `Procfile`:** fjern.

**Anslag:** D1 er 1–2 kvelder. D2–D4 er én til sammen.

---

## Pulje E: duplisering som alt har glidd

Rekkefølgen innad følger hvor mye kopiene allerede er forskjellige.

**E1. Statistikkutregningen i pasientmodulen finnes to ganger, og de gir ulike svar.**
- **Hvor:** `patients/services.py`, `_compute_stats_from_dicts` og
  `_compute_full_stats_from_dicts`.
- **Feilen:** full statistikk grupperer ankomst på `'%H:00'`, mens den andre bruker
  `'%d.%m %H:00'`. En vakt over flere døgn slår da sammen samme klokketime på tvers av
  døgnene.
- **Retting:** avgjør hvilken nøkkel som er riktig, trekk ut én felles kjerne, og la én
  test holde begge.

**E2. Verdilistefabrikken.**
- **Hvor:** `ko/views.py:718-853` og `oppdrag/views_verdier.py:131-277`. Omtrent 130 like
  linjer.
- **Glidningen:** navneunikheten er `iexact` i den ene og eksakt i den andre, og
  `ProtectedError` fanges bare i oppdrag.
- **Retting:** én fabrikk i `core`.

**E3. Arkivverifiseringen er skrevet på nytt i viewet.**
- **Hvor:** `patients/views_arkiv.py:124-140`.
- **Retting:** kall `core.arkiv.verifiser()`, slik oppdrag gjør.
- **Samtidig:** arkivhendelsene logges med `table_name='backup'`. Lag én felles
  loggehjelper i `core.arkiv`.

**E4. Tilgangsgatene.**
- **Hvor:** tre steder skriver fortsatt `er_global_admin(...) or har_tilgang(...,
  'skriv_leder')`, som er overflødig siden `nivaa_for` ga admin toppen av stigen.
- **Hvorfor det er mer enn pynt:** «kan lede oppdrag» er skrevet to ulike steder, og bare
  det ene utelukker enhetskontoer. Knappen kan da vises for noen som får 403.

**E5. Småhjelpere:**
- `_json_body`/`_feil` (fem kopier)
- sesjonsdekodingen (fire kopier, med ulik feilhåndtering)
- escape-funksjonene (fem varianter)
- intervallsammenslåingen i vaktlista (tre kopier)
- hjelperne mellom `oppdrag-kort.js` og `oppdrag-enhet.js`

**E6. Vaskingen og helseprobene.**
- `_scrub_secrets` og `offsite._vask` gjør nesten det samme. Samle dem i én `core/vask.py`.
- `core/health.py` og `core/admin_status.py` har hver sin DB- og cache-probe.

---

## Pulje F: dokumentasjon som motsier koden

**F1. Tilgangsregler i docstrings som sier det motsatte av koden.** *Levert 26. sep. 2026, se CHANGELOG.* Disse skal først,
fordi den som leser dem før hun endrer en port, leser feil regel:
- `vaktliste/views.py:11`
- `vaktliste/services.py:645`
- `vaktliste/module.py:33`
- `accounts/models.py:153,167`

Samme pulje:
- `lokasjon`-kommandoen og testen for den (`oppdrag/tests.py:489,592`) sier «ingen URL
  ennå». Enten fjernes kommandoen, eller så skrives den om som et verktøy, og da skal den
  døde `skipTest`-grenen ut.

**F2. Rot-`CLAUDE.md`.**
- **Audit-avsnittet er galt.** Det sier at feltendringer logges automatisk av
  `audit/signals.py`, og at man aldri skal skrive manuell audit. I virkeligheten fyller
  `audit/signals.py` bare ut `app_label`, og loggingen skjer i hver modul. Den som følger
  regelen, lager hull som B2 og B3.
- **To mindre feil:**
  - `_REGISTERED_MODULES` finnes ikke (funksjonen heter `_build_registry`). Legg navnet i
    symbolsjekken.
  - Lista over moduler som deklarerer `skriv_leder` mangler `ko` og `backlog`.
- **Taket:** rettingen må ikke gjøre fila lengre. Ta den sammen med TODO-punktet om at rota
  har ~170 tegn igjen.

**F3. TODO som ikke stemmer:**
- Punktet om å flytte `hent_aktiv_vakt` ut av pasientmodulen er **gjort**. Funksjonen bor i
  `core/vakt.py`. Slett punktet, og rydd restene:
  - re-eksporten i `patients/services.py`
  - `TILLATT` i `core/tests_stats_registry.py`
  - kommentarene i `statistikk/views.py`
- De to punktene om `style-src 'unsafe-inline'` slås sammen. Riktig tall er **315** inline
  stiler (211 i maler og 104 i JS), ikke «~50» eller 271.
- **Nytt punkt:** `core.vakt.opprett_vakt()` som eneste fabrikk for `Vakt`-rader. I dag er
  det tre steder. I tillegg gir to samtidige innsendinger i vaktlista 500, fordi
  `IntegrityError` ikke fanges og `kopier_oppsett` kjører utenfor transaksjonen.

**F4. Rundt 40 utdaterte kommentarer.** Rettes i filen når noen likevel er der, ikke som en
egen runde. Eksempler:
- «fase 3 gjenstår»
- `patients/admin_status.py` i `settings.py`
- «hvert 15. sekund» i `ko/views.py`
- `_should_run_now()`
- `base.html`
- «Behandler»

---

## Pulje G: struktur (når man likevel er i filene)

Ingen av disse gjør skade i dag. Hver av dem gjør neste endring dyrere.

**G1. `patients` bærer rammeverk.** Flyttes til `core`:
- **Server-status:** malen `patients/admin_status.html` (843 linjer, med 531 linjer
  inline-JS som ingen skanner eller node-test ser) flyttes til `core/templates/core/`.
  Skriptet flyttes til `static/js/portal-status.js`.
- **`AppSetting`:** admin-registreringen og `appsetting`-kommandoen.
- **Vaktas livssyklus:** `avslutt_vakt_view`, `vakter_view` og `gjenaapne_vakt_view`.
- **Testinfrastrukturen:** `js_test_utils` og `tests_modul_dekorator`.

**G2. Store filer.**

| Fil | Linjer | Merknad |
|---|---|---|
| `vaktliste/views.py` | 1 692 | |
| `vaktliste/services.py` | 1 678 | |
| `oppdrag/services.py` | 1 619 | |
| `accounts/views.py` | 1 463 | `user_detail_view` er 216 linjer med åtte `action`-grener, og bør bli en dispatch-tabell |
| `ko/views.py` | 1 394 | Deles etter flate, som `views_verdier` i oppdrag |

**G3. Pasientsiden er et eget skall.** Den har egen header, klokke og bjelle. Funn A8 er ett
eksempel på hva det koster. Fjern `updateClock` og last `portal-clock.js` nå. På sikt:
arv `base_portal`.

**G4. N+1 i endepunkter som polles:**
- `enhetskort()`/`enhet_status()` (2–4 spørringer per enhet), kalt fra `enheter_view` og KO
  sin tavle
- hendelsesfeltene i oppdragslista
- `historikk_liste_view`

**G5. Oppsett og drift:**
- **`requirements.txt`:** kompilert med Python 3.11 mens `runtime.txt` sier 3.13. Kompiler
  på nytt under 3.13.
- **scipy og numpy:** vurder dem som valgfrie. De brukes av to statistiske tester.
- **Service workerens skallcache** vokser for hver deploy.
- **Pollingen i skjulte faner:** sikkerhetsnettene poller fortsatt. Lag én
  `naarSynlig(fn)` i `portal-utils.js`.
- **Død CSS:** blant annet `.role-*`, `.hendelse-hode*` og `.vl-fanerad`.

**G6. Deploy 2 i oppdragsmodulen** står allerede i TODO.
- **Omfang:** kartlagt til omtrent 80–100 produksjonslinjer og rundt 70 teststeder.
- **Skjult feil i dag:** historikksøket `enhet__navn__icontains` (`oppdrag/views.py:1265`)
  treffer bare den primære enheten.
- **Forutsetning:** A1.

---

## Det som ble sjekket og funnet i orden

Tatt med så det ikke må sjekkes på nytt:

- **Dekoratører:** alle views er dekorert.
- **Rate-limiting:** alle `@rate_limit` har eksplisitt `group`.
- **Data inn i `<script>`:** ingen `json.dumps|safe`.
- **Avhengighetsretningen:** holder.
- **Gamle navn:** ingen rester av `get_active_year`, `BackupConfig`, `has_role_at_least` eller
  `kan_redigere_*` i levende kode.
- **`data-action`:** alle 236 navn slår opp i en funksjon som finnes på den siden de
  brukes.
- **Navnekollisjoner:** ingen globale navn er definert to ganger på samme side.
- **Maler:** alle inline-skript har nonce, og det er ingen `onclick=`.
- **Idempotens:** nøkkelen reserveres etter validering.
- **Korpsfilteret:** på plass i hovedkallet og belastningen, med unntak av C1 og C2.
