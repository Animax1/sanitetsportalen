# Teknisk gjeld — kartlagt 13. september 2026

Underlag for punktene under «Teknisk gjeld» i `TODO.md`. Dette dokumentet forklarer
*hva* som er gjeld, *hvorfor* det ble slik og *hva* som må til. Arbeidslista er TODO;
er et punkt her ikke der, blir det ikke gjort.

Kartlagt ved gjennomgang av apper, modeller, importer på kryss av apper, middleware og
ruter — ikke ved lesing av dokumentasjonen. Tallene og filnavnene under er fra koden
samme dag.

---

## 1. Hvordan appen er ment å henge sammen

Ett Django-prosjekt (`myproject`) med sju apper. Tanken er **rammeverk pluss moduler**:

| App | Rolle |
|---|---|
| `core` | Rammeverket: modulregisteret, tilgangsdekoratørene, og tre registre modulene melder seg inn i — backup, arkiv og statistikk. `Vakt` (scopet alt henger på), varsler, offsite, rate-limiting, idempotens, de fleste sidene under `/portal-admin/` |
| `accounts` | Kontoene: innlogging, MFA, passord, brukeradmin og `ModulTilgang` — hele tilgangsmekanismen |
| `audit` | Loggen, skrevet av signaler |
| `patients`, `oppdrag`, `vaktliste` | De tre modulene. Hver deklarerer `module.py` og melder inn handlerne sine fra `apps.ready()` |
| `statistikk` | En tynn leser som henter tall fra modulene og aldri navngir dem |

Registrene har én arbeidsdeling: `core` eier orkestreringen, modulen eier dataene.
Avhengighetsretningen er ment å være `core` nederst, modulene over, statistikk øverst, og
deler av det håndheves med AST-tester (`OppdragImportererIkkeVaktlista`,
`StatistikkappenNavngirIngenKilde`).

Frontenden er ti JS-filer uten bundler, én eller to per side, og tre stilark som hver
dekker sine sider. Testsuiten er større enn koden (2578 tester, mer testkode enn
produksjonskode i hver app) og er det som gjør en opprydding trygg.

---

## 2. Den store: `patients` er den gamle monolitten

`patients` var første app, portert fra Flask, og alt som var «portalen» havnet der
fordi det ikke fantes noe annet sted. Det ligger der fortsatt, og **retningen er snudd:
`core` peker opp på `patients`.**

| Hva | Hvor det bor | Hvem som avhenger av det |
|---|---|---|
| `AppSetting` — portalinnstillingene (aktiv vakt, lydvarsel-brytere, e-postmottakere for vaktlistefila, sesjonstimeout) | `patients/models.py` | `core/kommando.py`, `core/views.py`, `accounts/middleware.py`, `oppdrag/services.py`, `oppdrag/verdier.py`, `oppdrag/arkiv.py`, `oppdrag/views_verdier.py`, `vaktliste/fil.py` — rundt 20 importer på kryss |
| `Backup` og `BackupConfig` — backupsystemets egne tabeller | `patients/models.py` | `core/backup/service.py`, `core/arkiv/service.py`, `core/offsite.py`, `core/views.py`. **Rammeverket avhenger av modulen** |
| `hent_aktiv_vakt` — portalens scope | `patients/services.py` | `oppdrag`, `vaktliste`, `statistikk`, `core/views.py` |
| CSP-headerne (`SecurityHeadersMiddleware`), metrikkene (`RequestMetricsMiddleware`), backup-planleggeren | `patients/middleware.py` | `settings.MIDDLEWARE` |
| `/healthz/` | `patients/health.py` | `myproject/urls.py` |
| Server-status med sesjonsverktøyet | `patients/admin_status.py` | `myproject/urls.py` (tretten ruter koblet rett i prosjektet) |

Ingenting av dette er pasientdata. Konsekvensene er konkrete:

- **Backupen speiler hvor modellene bor.** Portalinnstillingene ligger i
  *pasient*-backupen fordi `AppSetting` ligger i `patients`. Vakta (`core.Vakt`)
  ligger ikke i noen backup, fordi ingen modul eier den. Se §4.
- En pasientmodul som ble tatt ut, ville tatt CSP, helsesjekken og backupsystemet med
  seg.
- Ny utvikler leter etter portalinnstillingene i `core` og finner dem ikke.

**Fiks:** flytt `AppSetting`, `Backup`, `BackupConfig`, `hent_aktiv_vakt`, middlewaren,
`healthz` og server-status til `core`. Tabellnavnene beholdes (`db_table`), så det blir
en tilstandsmigrasjon uten datamigrasjon. Én ting å passe på: **backupfilene bærer
modellnavn** (`patients.AppSetting`), så eldre filer må kunne lastes etter flyttingen —
en navnetabell i lasteren, med test som laster en fil i gammel form.
`patients/backup_service.py` (skimet for `db_backup`-kommandoen) legges ned i samme
runde; det er bare testene som bruker det, og `RETENTION_HOURS = 72` der er død kode
som personverndokumentasjonen alt måtte rette en feil for.

Størrelse: en kveld for flyttingen, en til for navnetabellen og testene. Gjøres
**før** backup-omleggingen i §4, ellers bygges den på feil grunnlag.

---

## 3. De mindre

| # | Hva | Hvor | Hvorfor det er gjeld | Fiks |
|---|---|---|---|---|
| 3.1 | Brukeradmin kjenner én modul ved navn | `accounts/forms.py:599, 611` importerer `Forstehjelper` og `Helsepersonell` | `accounts` → `patients`. Kobling av konto til registerperson er modulens sak, ikke kontoens | La pasientmodulen eie koblingen (som `Mannskap.user` i vaktlista), eller gå gjennom en krok i `core.modules` |
| 3.2 | `/portal-admin/` er fordelt på fire filer | `myproject/urls.py` (13), `core/urls.py` (15), `accounts/urls.py` (10), `patients/urls.py` (4) | Ingen finner alle adminsidene ett sted; `PortalAdminRuteneErStengtTests` måtte skrives over `urlpatterns` for å være sikker | Én `core/urls_admin.py`, inkludert fra prosjektet. Faller delvis ut av §2 |
| 3.3 | To bakoverkompatible skim | `accounts/decorators.py`, `patients/backup_service.py` | Beholdes bare fordi tester verifiserer dem | Slett skim og tester i samme commit |
| 3.4 | `Lydvarsel` er med i oppdragsdumpen, men ikke i `restore_models` | `oppdrag/backup.py` | Gjenoppretting lar rader som ikke finnes i fila stå igjen; de andre modellene slettes først | Legg den i lista |
| 3.5 | `VaktArkiv` gjentar feltene i `AbstractArkiv` | `patients/models.py` | **Bevisst**: `year_snapshot` og `arrangement_navn` inngår i signaturen til hvert arkiv i prod. Ikke rør | Ingen. Står her så ingen «rydder» den |
| 3.6 | `vaktliste.js` er 3 800 linjer i én fil, `oppdrag-sentral.js` 1 950 | `static/js/` | Bevisst valg uten bundler, men fila er blitt vanskelig å navigere | Del på ansvar (registeret, regnearket, kurven, offline) når neste større endring kommer. Ikke som eget prosjekt |
| 3.7 | `core/views.py` er 860 linjer og 24 views om alt fra backup til varsler | `core/views.py` | Samme grep som `patients/views.py` fikk i N13.3 | Del i `views_backup.py`, `views_admin.py`, `views_varsler.py` |
| 3.8 | En del eldre tester grep-er etter kodelinjer i JS og maler | `*/tests*.py` | Skjøre: en omformulering bryter dem uten at oppførselen er endret. CLAUDE.md forbyr nye, de gamle står | Skriv om til node-kjøring når de knekker; ingen egen runde |

Sjekket og **ikke** gjeld: `AppSetting`-nøklene `active_year`, `event_name` og
`next_patient_nr` er borte siden deploy 2 av vakt-scopingen; bare kommentarer nevner dem.

---

## 4. Backup: hullene som ble synlige

Kartlagt 13. sep. 2026 på spørsmål om hva som faktisk går til Scaleway. Fire filer i
dag: `patients`, `arkiv`, `oppdrag`, `oppdrag_arkiv`.

| Hull | Konsekvens |
|---|---|
| **`core.Vakt` er ikke i noen fil.** Pasienter og oppdrag peker på den med FK uten `natural_key` | Gjenoppretting i **tom** base — det offsite-kopien finnes for — feiler på fremmednøkkelen, eller kobler radene på feil vakt hvis ID-ene tilfeldigvis finnes. Ingen test gjenoppretter i tom base i dag |
| **Vaktlista har ingen handler** | Korps, mannskap (telefon, e-post, ISSI, notat), kompetanser, grupper, ressurser, vaktposter, vaktlistene og belastningsgrensene ligger utenfor all dekning. Samme feil oppdragsmodulen hadde fram til fase 7 |
| Brukere, MFA, `ModulTilgang`, audit- og innloggingslogg er utelatt | Bevisst da det ble skrevet (ukryptert fil på volumet). Med kryptert offsite er argumentet svakere. Beslutning 13. sep.: se TODO |
| Modulen `arkiv` heter «Vaktarkiv» i grensesnittet | Sier ikke hva den er. Skal hete «Pasientregistreringsarkiv» |
| Railway Pro-backupen finnes bare under vakt | Mellom vaktene er Scaleway-filene eneste kopi — og de er ikke gjenopprettbare alene (første rad) |

Rekkefølgen står i TODO: §2 først, så dette.

---

## 5. Hva som ikke er gjeld

- Modulregisteret, tilgangsmodellen, arkiv- og backup-registrene: mønsteret er riktig,
  og de to nye modulene (`oppdrag`, `vaktliste`) gikk inn i det uten endringer i `core`.
- Testdekningen. Den er tung, men den er grunnen til at §2 lar seg gjøre trygt.
- Vendor-bibliotekene i repoet og hash-låste avhengigheter (sikkerhetsrunde 2).
