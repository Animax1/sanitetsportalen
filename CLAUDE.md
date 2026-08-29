# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Arbeidsflyt ved commit/push

**Før enhver endring som skal commites og pushes: oppdater `CHANGELOG.md` og `TODO.md` i forkant.**
Legg endringen øverst i CHANGELOG (ny `## YYYY-MM-DD`-seksjon ved behov), og kryss av / flytt
relevante punkter i TODO. Dette skal gjøres som del av samme commit, ikke etterpå.

## Commands

```powershell
# Setup (første gang)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # rediger SECRET_KEY
python manage.py migrate
python manage.py create_admin --username admin --password "bytt-meg"

# Kjøre lokalt
python manage.py runserver           # http://127.0.0.1:8000/

# Tester – hele suiten
python manage.py test patients accounts audit core statistikk oppdrag vaktliste -v 2

# Én enkelt test
python manage.py test patients.tests.PatientAPITest.test_create_patient -v 2

# Migrasjoner
python manage.py makemigrations
python manage.py migrate
```

## Arkitektur

### Modulregistry (core/modules.py)

Portalens rammeverk. Hver app deklarerer sin modul i `<app>/module.py`, og registreres eksplisitt i `core/modules.py`. Moduler kontrolleres via `ModuleSettings`-tabellen (admin-toggle uten deploy).

Å legge til en ny modul:
1. Lag `<app>/module.py` med klasse som arver fra `Module`
2. Importer den i `_REGISTERED_MODULES` i `core/modules.py`
3. Legg til permission-flagg på `CustomUser` (via migrasjon) om nødvendig

En modul vises kun hvis `ModuleSettings.enabled=True` **og** brukeren har en
`ModulTilgang`-rad på modulen. Global admin ser alt.

### Tilgangskontroll

Importér alltid fra `core.auth_decorators`. `accounts/decorators.py` er en ren
re-eksport-shim som beholdes fordi `core/tests.py` verifiserer at den fortsatt virker —
ingen produksjonskode importerer fra den lenger (N11).

**Tre kategorier, ikke én.** Se `docs/BESLUTNING_ROLLEMODELLEN.md`:

1. **Global admin** (`role == 'admin'`) — brukeradmin, backup, moduloppsett, audit, arkiv,
   og alt irreversibelt. Står utenfor modulaksen og trenger ingen rader.
2. **Modulbasert** — `accounts.ModulTilgang(bruker, modul_slug, nivaa)`.
3. **Globalt uten admin** — innlogging, min profil, passordbytte, MFA.

```python
from core.auth_decorators import admin_required, har_tilgang, modul_kreves

@modul_kreves('patients', 'skriv_full', svar='json')
```

Nivåene er en ordnet stige. **Fravær av rad er ingen tilgang** — det finnes ingen
`'ingen'`-verdi å lagre:

| Nivå | Betyr |
|---|---|
| `les` | Kan se modulens data |
| `skriv_handling` | Navngitte overganger (stemplinger), leser ikke request-kroppen |
| `skriv_full` | Kan redigere felter |

**Hver modul deklarerer hvilke nivåer som betyr noe for den** — `Module.nivaaer`. Matrisen
tilbyr de nivåene og ingen andre. En global liste hadde begge feil samtidig: den skjulte
`skriv_handling` for oppdragsmodulen, som er den nivået ble laget for, og tilbød
`skriv_full` på statistikk, der skriving ikke finnes.

Ukjent nivånavn gir **False**, ikke True — en skrivefeil i en dekoratør skal stenge døra.
`ModuleSettings.enabled=False` gir 403 for alle andre enn global admin.

**Hvert view under en modul må være dekorert.** `patients/tests_modul_dekorator.py` går
gjennom `urlpatterns` og håndhever det — risikoen ved dekoratør framfor middleware er en
glemt dekoratør, og en manuell gjennomgang holder bare til neste endepunkt. Unntak må stå
i lista der, med begrunnelse.

**Grensesnittet gater på `window.MODUL_TILGANG`, ikke på rollen.** Gjør det ikke det, viser
vi knapper som fører til 403 — og en knapp som fører til en vegg er verre enn ingen knapp.

**`CustomUser.role` er kontotype, ikke tilgangsnivå.** Feltet krympet i deploy 2 til
`admin` og `bruker`; de fire verdiene som beskrev tilgang er borte, sammen med
`has_role_at_least`, `role_required`, `write_required` og `stats_required`. Gate på
`er_global_admin(user)` for admin, og på `@modul_kreves`/`har_tilgang` for alt annet.
Ordet «bruker» i grensesnittet betyr *ikke* «vanlig tilgang» — kontoen ser ingenting før
den har en `ModulTilgang`-rad.

De fem `kan_redigere_*`-flaggene er **borte** (deploy 3). Skal en ny modul gates, trengs
ingen kolonne på `CustomUser` — en `ModulTilgang`-rad er hele mekanismen. Det var nettopp
det flaggene gjorde galt: de la tilgang i skjemaet i stedet for i data, og en modul som
ikke hadde noe flagg kunne ikke gates i det hele tatt.

**Tester lager brukere med `accounts.test_helpers.gi_standardtilgang(bruker, profil)`.**
Profilen oppgis eksplisitt — `leser`, `skriver`, `leder_les`, `leder`, `admin` — fordi
rollen ikke lenger sier noe om tilgang. En bruker uten rader er stengt ute av modulen, så
en test som glemmer kallet tester 403-stien uten å vite det.

### Rate-limiting (core/ratelimit.py)

Innlogging og MFA håndheves med eksplisitte `is_ratelimited`-kall i `accounts/views.py`
(N4). Alt annet bruker `@rate_limit(...)` fra `core.ratelimit` (S3).

```python
from core.ratelimit import rate_limit

@rate_limit(group='patients:create', rate='60/m', method='POST')
```

**Gruppen skal alltid oppgis eksplisitt** — den er cache-nøkkelen, og to endepunkter må
aldri dele teller. Sett dekoratoren under tilgangssjekken; `key='user'` forutsetter
innlogget bruker. `on_limit='json'` (default) gir `{'error': ...}` med 429, `'html'` gir
429-siden.

**Tell riktig hendelse, ikke bare riktig endepunkt.** En dekoratør teller alle forespørsler
mot viewet. Er det bare én av dem som er verdt å bremse — et feilet gjett, ikke en avvist
skjemainnsending — hører tellingen hjemme inne i viewet, ved siden av den sjekken. Se
`change_password_view`; N4 og S3 gikk begge i den fella.

Bremsen faller åpen ved cache-feil, med vilje. Både `RATELIMIT_FAIL_OPEN=True` og
try/except i `er_rate_limited` trengs — se modulens docstring. Nød-bryter:
`RATELIMIT_ENABLE=False`.

### Idempotens (core/idempotency.py)

Skriveendepunkter som kan treffes to ganger med samme intensjon — dobbeltinnsending,
nettverks-retry — reserverer en klientgenerert nøkkel før de oppretter noe.

```python
idem = bygg_nokkel('patient_create', request.user.pk, data.get('idempotency_key'))
if idem:
    status, verdi = reserver(idem)   # 'ny' | 'pagar' | 'ferdig'
...
fullfor(idem, patient.pk)            # eller forkast(idem) hvis noe feilet
```

**Reserver etter all validering, aldri før** — ellers brenner en avvist innsending
nøkkelen. Frigi med `forkast()` når opprettelsen feiler. Cache-feil betyr «opprett
uansett»; se modulens docstring.

### API-mønster (patients/views_*.py)

Viewene er delt i fem moduler (N13.3) — `views.py` finnes ikke lenger:

| Modul | Ansvar |
|-------|--------|
| `views_common.py` | `_json_body`, `_patient_to_dict` — delt av de andre |
| `views_patients.py` | Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD, vaktavslutning/-gjenåpning |
| `views_registre.py` | Førstehjelper- og helsepersonellregisteret (én fabrikk bygger begge) |
| `views_arkiv.py` | Vaktarkivet |

Alle endepunkter er JSON-API-er beskyttet med `@login_required` + rollesjekk. Responser følger mønsteret `{'status': 'ok', 'data': ...}` eller `{'status': 'error', 'message': ...}`.

### Audit-logging

Feltendringer logges automatisk via Django-signal i `audit/signals.py`. `RequestAuditMiddleware` lagrer request i thread-local slik at signaler kan hente bruker og IP uten å ta imot `request`-objektet direkte. Legg aldri til manuell audit-kode — signalet tar seg av det.

### Backup-system

`BackupSchedulerMiddleware` kjører automatisk backup in-process etter request.

Backup er **per modul**, ikke én samlet dump. Hver modul registrerer en `BaseBackupHandler` i `core.backup`-registryet (fra `apps.ready()`). Fire handlere finnes i dag:

| Slug | Fil | Innhold |
|------|-----|---------|
| `patients` | `patients/backup.py` | Pasientdata. Arkivmodellene er eksplisitt ekskludert |
| `arkiv` | `patients/backup.py` | `VaktArkiv` + `ArkivertPasient` — endres sjelden, og skal aldri berøres av en pasient-restore |
| `oppdrag` | `oppdrag/backup.py` | Oppdrag, statusmeldinger, enhetsbytter, enheter og lokasjoner |
| `oppdrag_arkiv` | `oppdrag/backup.py` | `OppdragArkiv` + `ArkivertOppdrag`. Er også **sperren** foran kollaps |

Brukere, MFA-hemmeligheter og audit-spor er bevisst utelatt fra alle fire. FK-er ut av
modulens eget datasett strippes (`strip_fields`): med `natural_foreign` lagres de som
brukernavn, og er kontoen slettet feiler hele gjenopprettingen — altså akkurat når man
trenger backupen.

**Scheduleren finner moduler gjennom registeret**, ikke gjennom
`ModuleBackupConfig`-tabellen: en modul uten konfigrad får en med standardverdier
første gang scheduleren ser den. Leste den tabellen direkte — slik den gjorde fram til
fase 7 — var en nyregistrert modul uten backup til noen tilfeldigvis åpnet
`/portal-admin/backup/`, og for et arkiv betyr manglende backup at kollapsen nekter å
kjøre, altså en feil som først viser seg to år senere.

En test som kaller `clear_registry()` må rydde opp med
`core.backup.registrer_alle_moduler()`, ikke med én moduls `register_handlers()`. Gjør den
det siste, mister resten av testkjøringen de andre modulenes handlere, og feilen dukker
opp i en helt annen fil.

Logikken ligger i `core/backup/`. `patients/backup_service.py` er en tynn proxy som beholder bakoverkompatibelt API for `db_backup`-kommandoen, `views_patients.py` og eldre tester — nye moduler skal registrere en handler og kalle `core.backup.create_backup(slug=...)` direkte.

### Arkivmønster (core/arkiv/)

Frysing, integritetssjekk og kollaps er modul-agnostisk. Hver modul som arkiverer data registrerer en `BaseArkivHandler` (fra `apps.ready()`), på samme måte som backup-handlerne.

**Arbeidsdelingen er bevisst:** `core.arkiv` eier kanonisering, hashing og orkestrering av kollaps. Handleren eier *hva* som går inn i SHA-payloaden. Grunnen er at payloadens form er del av signaturen som ligger lagret på hvert arkiv i prod — bestemte core formen, ville hvert eksisterende arkiv meldt tukling.

| Funksjon | Ansvar |
|---|---|
| `beregn_sha256(handler, arkiv)` | Signatur over radnivået |
| `verifiser(handler, arkiv)` | True hvis signaturen ikke stemmer. Velger aggregat-signatur etter kollaps |
| `kollaps(handler, arkiv)` | **Irreversibel.** Frys aggregat, slett rader. Idempotent |
| `har_backup_etter(handler, tid)` | Sperre før kollaps — slettingen må være gjenopprettbar |

**`AbstractArkiv` (core/arkiv/models.py) bærer feltene**, slik at modul nummer tre slipper
å skrive dem på nytt: `tittel`, `vakt`/`vakt_navn`, `antall_rader`, `importert_av` med
frosset navn, `sha256`, `kollapset_at`, `aggregat` og `aggregat_sha256`.
`OppdragArkiv` arver den. **`VaktArkiv` gjør det ikke, og skal ikke gjøre det:** feltene
`year_snapshot` og `arrangement_navn` inngår i SHA-payloaden til hvert arkiv i prod, og
et arkiv som byttet feltnavn ville meldt tukling. Duplikatet er prisen for at
signaturene fortsatt verifiserer.

Handleren setter `arkiv_model`, og `kollaps_arkiv`-kommandoen finner kandidater gjennom
registeret — den kjenner ingen modul ved navn, og `--modul <slug>` avgrenser.

To arkiver i dag: `patients/arkiv.py` (referanseeksempelet) og `oppdrag/arkiv.py`.
`ArkivSignaturLaastTests` i begge moduler låser signaturene til literale hex-verdier —
feiler de etter en refaktorering, er det refaktoreringen som er feil.

### Oppdragsmodulen (oppdrag/)

Egen app siden august 2026 — se `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Alle sju fasene er
levert: sentralbord, enhetsskjerm, korreksjoner, offline-kø, statistikkfane og vaktarkiv.

Fem ting det er verdt å kjenne før man rører modulen:

| Regel | Hvor |
|---|---|
| Statusmaskinen er **data**, ikke `if`-er i views | `services.OVERGANGER` |
| Enhetens status **utledes**, den lagres ikke | `services.enhet_status()` |
| Korreksjoner er **nye rader** som peker på den gamle | `Statusmelding.objects.gjeldende()` |
| `fritekst` logges som endret, men **uten verdier** | `signals.FELT_UTEN_VERDILOGGING` |
| «Historikk» rydder tavla, **arkivet fryser vakta** | `Oppdrag.historikk_fra` vs. `oppdrag/arkiv.py` |

**Historikk og arkiv er to helt ulike handlinger**, og har derfor hver sin knapp.
Historikk flytter ett oppdrag ut av den aktive tavla og er fullt reversibel; arkivering
fryser hele vakta med signatur og starter klokka mot en kollaps som sletter radnivået
etter 24 måneder. `fritekst` arkiveres **ikke** — feltet er unntatt verdilogging i audit,
og å fryse det i 24 måneder ville uthult unntaket.

Den er den første modulen som tar `skriv_handling` i bruk: bilen får smale, navngitte
stemplingsendepunkter, ikke en feltwhitelist inne i en generell `PUT`. Og skillet mellom de
to grensesnittene er **ikke nivået** — det er om kontoen er knyttet til en `Enhet`. Å knytte
en konto til en enhet gir ingen tilgang; det er domenedata, som `Forstehjelper.user`.

### Vaktlistemodulen (vaktliste/)

Fase 1 levert (registre + mannskap); side og resten kommer i fase 2–7 — se
`docs/BESLUTNING_VAKTLISTE.md`, som er besluttet i sin helhet. Tre ting å vite:

- **`Mannskap.korps` er badgen** tilgangsmodellen hviler på fra fase 3:
  `skriv_handling` betyr her «fører sitt eget korps» (avgrenset av badgen, ingen
  innsjekk), ikke stempling som i oppdrag. Matrisen trenger derfor en etikett per
  modul per nivå (§4.5) før nivået deles ut.
- **Kostbehov/matallergi lagres ikke** (art. 9 — besluttet holdt utenfor portalen), og
  `Mannskap.notat` er unntatt verdilogging i audit (`signals.FELT_UTEN_VERDILOGGING`).
- Modulen står med `url=None` og `show_*`-flaggene av til fase 2 — samme regel som
  oppdragsmodulen fulgte: et modulkort som fører til 404 er en knapp mot en vegg.

### Statistikk-modulen (statistikk/)

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
hver modul melder inn en `BaseStatistikkHandler` fra `apps.ready()`. To kilder i dag,
`patients/statistikk.py` og `oppdrag/statistikk.py`.

`hent_aktiv_vakt` er den ene importen fra en modul som står igjen, og den handler ikke om
tall: den er portalens scope, delt av alle moduler, og ble liggende i pasientmodulen fordi
`AppSetting`-pekeren gjør det. `StatistikkappenNavngirIngenKilde` leser importene med AST
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

### Statistikk-caching (core/stats_cache.py)

Ligger i `core` fordi to apper bruker den: `patients` for header-chipsene og `statistikk`
for full statistikk. Full stats caches 60 sek. Støtter ETag/304.

Det finnes **ingen** eksplisitt invalidering — cachen utløper på TTL. De korte TTL-ene er valgt nettopp for å slippe invalideringslogikk, og alle cache-operasjoner er pakket i try/except slik at en død cache degraderer til vanlig beregning i stedet for å ta ned endepunktet.

### Frontend

**Tre stilark, og de dekker hver sine sider.** Å legge en regel i feil fil ser ut som en
virkningsløs endring, ikke som en feil:

| Fil | Lastes av | Variabler |
|-----|-----------|-----------|
| `static/css/style.css` | **kun** `templates/patients/index.html` | `--text-muted` m.fl. |
| `static/css/portal.css` | alt som arver `core/templates/core/base_portal.html` | `--portal-text-muted` m.fl. |
| `static/css/statistikk.css` | **kun** `templates/statistikk/index.html` | definerer selv de fire `base_portal` mangler |

Noen frittstående sider (`403.html`, `mfa_setup.html`, `mfa_verify.html`, innlogging)
laster ingen av dem — de har egen `<style>`-blokk og må overstyre selv.

**`base_portal.html` aliaser ikke alle variablene `style.css` definerer.** Den setter
`--surface-1`, `--surface-2`, `--border-color` og `--text-main`, men *ikke* `--text-muted`,
`--text-soft`, `--surface-3` eller `--header-bg`. En udefinert custom property gjør ikke
regelen ugyldig — den gjør fargen arvet, så teksten blir lesbar eller uleselig tilfeldig
uten at noe feiler. Et nytt modulstilark må derfor definere de fire selv, og *ikke* gjenta
de fire portalen faktisk aliaser (da kan temaene komme i utakt). `statistikk.css` er
mønsteret.

Alle temaene er mørke, så **enhver Bootstrap-klasse for dempet tekst må overstyres** der
malen kan se den. `MorkTekstPaaMorkBakgrunnTests` løser `{% extends %}` og `{% static %}`
og håndhever det.

Ni moduler i `static/js/` (ingen bundler), fordelt på fire sider — pasientsiden,
`/statistikk/` og de to grensesnittene under `/oppdrag/`:

| Modul | Lastes | Ansvar |
|-------|--------|--------|
| `portal-utils.js` | **alle sider** | CSRF-fetch (`apiFetch`), `withSubmitGuard`, escaping, `fmtMin`, `klokke`, `data-action`-delegeringen |
| `patients-utils.js` | pasientsiden, alltid | Rollesynlighet, delt tilstand, klokke, skjemahjelpere |
| `patients-table.js` | pasientsiden, alltid | Tabulator-grid og tavle |
| `patients-forms.js` | pasientsiden, alltid | Registrerings- og redigeringsskjema |
| `patients-app.js` | pasientsiden, alltid | Oppstart (`DOMContentLoaded`), faneskift, auto-refresh, lastere for navneregistrene |
| `patients-admin.js` | pasientsiden, **kun admin** | Registeradmin, sesjonstimeout, vaktavslutning/-gjenåpning, vaktarkiv |
| `statistikk.js` | **kun** `/statistikk/` | Pasientstatistikk (Chart.js), arkivmodus, kildefanene |
| `statistikk-oppdrag.js` | `/statistikk/`, **kun** med oppdragstilgang | Oppdragsfanen. Kall hit fra `statistikk.js` går gjennom `_kallOppdrag('navn')` |
| `oppdrag-sentral.js` | `/oppdrag/`, kontoer uten enhet | Sentralbordet: enhetsliste, oppdragsliste, tidslinje, lokasjonsadmin |
| `oppdrag-enhet.js` | `/oppdrag/`, enhetskontoer | Enhetsskjermen: to knapper mot de navngitte stemplingsendepunktene, og offline-køen i `localStorage`. Serveren sender `neste_overgang` per rad; kjeden følger med som data kun for å projisere neste steg mens noe ligger usendt |

**`patients-utils.js` kan ikke lastes utenfor pasientsiden.** Den gjør arbeid på toppnivå
— `Chart.defaults` og `new bootstrap.Modal(document.getElementById('newModal'))` — og
kaster på en side uten pasientskjemaene. Trenger en ny modulside en helper derfra, skal
helperen flyttes til `portal-utils.js`, ikke kopieres. `JsModulLastingTests` håndhever det
ved å sammenligne hva `statistikk.js` kaller mot hva den faktisk laster.

**Alt en ikke-admin kan nå på pasientsiden, må ligge i en alltid-lastet modul.**
`read_write` har skrivetilgang uten admin-tilgang — derfor bor f.eks. `saveEventName` i
`patients-app.js`. Kall fra alltid-lastet kode til `patients-admin.js` må gå gjennom
`_kall('navn')`, som sjekker at funksjonen finnes. `JsModulLastingTests` håndhever dette.

CSRF-sikret fetch-wrapper brukes for alle API-kall. Tabulator for pasientgrid, Chart.js for
statistikk — og Chart.js lastes **kun** på `/statistikk/`.

Brukerdata som settes inn med `innerHTML` **skal** escapes — `escHtmlValue()` i tabeller (tallsikker), `escapeHtml()`/`_escHtml()` ellers. Markup koden bygger selv merkes med `trustedHtml()`. `patients/tests_xss_stats.py` håndhever dette,
og leser `statistikk.js`, `patients-admin.js` og `statistikk-oppdrag.js` — byggerne er
fordelt på de tre.

JS-oppførsel testes ved å kjøre funksjonene i node, se `patients/js_test_utils.py`. Ikke skriv nye tester som bare grep-er etter kodelinjer i JS-filer.

## Miljøvariabler

Settes i `.env` lokalt. Nøkler å kjenne til:

| Variabel | Formål |
|----------|--------|
| `SECRET_KEY` | Kryptografisk Django-nøkkel |
| `DEBUG` | `True` lokalt, `False` i prod |
| `OFFLINE_MODE` | `True` for feltbruk uten TLS (ALDRI på Railway) |
| `RATELIMIT_ENABLE` | Nød-bryter for rate-limiting |
| `REDIS_URL` | Aktiverer Redis-cache (ellers LocMemCache) |
| `BACKUP_DIR` | Sti til backup-mappe (Railway: `/data/backups`) |
| `LOG_LEVEL` | Loggnivå for rot-loggeren (default `INFO`) |
| `ADMINS` | Mottakere av feilvarsel, format `Navn:epost`, komma-separert |
| `AHASEND_API_KEY` + `AHASEND_ACCOUNT_ID` | AHASends HTTP-API v2 (`core/mail_backends.py`). **Dette er transporten i prod** — Railway sperrer utgående SMTP på alle porter |
| `EMAIL_HOST` m.fl. | SMTP for feilvarsel. Brukes kun lokalt og i offline-modus |
| `EMAIL_TIMEOUT` | Tidsgrense for utsending, default 10 s. Må aldri være `None` |

## Deployment

Railway med PostgreSQL og persistent volume på `/data`. Auto-deploy fra GitHub `main`. Health-check: `GET /healthz/`.