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
python manage.py test patients accounts audit core -v 2

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

En modul vises kun hvis `ModuleSettings.enabled=True` **og** brukeren har rett `permission_flag`.

### Tilgangskontroll

Importér alltid dekoratorer fra `core.auth_decorators`. `accounts/decorators.py` er en ren re-eksport-shim som beholdes fordi `core/tests.py` verifiserer at den fortsatt virker — ingen produksjonskode importerer fra den lenger (N11).

```python
from core.auth_decorators import admin_required, write_required, stats_required, role_required
```

Rollehierarki (lavest → høyest): `read_only → read_write → lead_view → lead → admin`

`has_role_at_least(user, 'lead')` sjekker hierarkisk. Dekoratorer gir 403 hvis rollen mangler.

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

### API-mønster (patients/views_*.py)

Viewene er delt i fem moduler (N13.3) — `views.py` finnes ikke lenger:

| Modul | Ansvar |
|-------|--------|
| `views_common.py` | `_json_body`, `_patient_to_dict`, `WRITE_ROLES` — delt av de andre |
| `views_patients.py` | Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD, nullstilling |
| `views_registre.py` | Førstehjelper- og helsepersonellregisteret (én fabrikk bygger begge) |
| `views_stats.py` | `/api/stats/` og `/api/full-stats/` |
| `views_arkiv.py` | Vaktarkivet |

Alle endepunkter er JSON-API-er beskyttet med `@login_required` + rollesjekk. Responser følger mønsteret `{'status': 'ok', 'data': ...}` eller `{'status': 'error', 'message': ...}`.

### Audit-logging

Feltendringer logges automatisk via Django-signal i `audit/signals.py`. `RequestAuditMiddleware` lagrer request i thread-local slik at signaler kan hente bruker og IP uten å ta imot `request`-objektet direkte. Legg aldri til manuell audit-kode — signalet tar seg av det.

### Backup-system

`BackupSchedulerMiddleware` kjører automatisk backup in-process etter request.

Backup er **per modul**, ikke én samlet dump. Hver modul registrerer en `BaseBackupHandler` i `core.backup`-registryet (fra `apps.ready()`). To handlere finnes i dag, begge i `patients/backup.py`:

| Slug | Innhold |
|------|---------|
| `patients` | Pasientdata. Arkivmodellene er eksplisitt ekskludert |
| `arkiv` | `VaktArkiv` + `ArkivertPasient` — endres sjelden, og skal aldri berøres av en pasient-restore |

Brukere, MFA-hemmeligheter og audit-spor er bevisst utelatt fra begge.

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

`patients/arkiv.py` er referanseeksempelet. `ArkivSignaturLaastTests` låser signaturene til literale hex-verdier — feiler den etter en refaktorering, er det refaktoreringen som er feil.

### Statistikk-caching (patients/stats_cache.py)

Basic stats caches 15 sek, full stats 60 sek. Støtter ETag/304.

Det finnes **ingen** eksplisitt invalidering — cachen utløper på TTL. De korte TTL-ene er valgt nettopp for å slippe invalideringslogikk, og alle cache-operasjoner er pakket i try/except slik at en død cache degraderer til vanlig beregning i stedet for å ta ned endepunktet.

### Frontend

Fem moduler i `static/js/` (ingen bundler). Fire lastes alltid, én betinget (F7):

| Modul | Lastes | Ansvar |
|-------|--------|--------|
| `patients-utils.js` | alltid | CSRF-fetch (`apiFetch`), `withSubmitGuard`, escaping, delt tilstand |
| `patients-table.js` | alltid | Tabulator-grid og tavle |
| `patients-forms.js` | alltid | Registrerings- og redigeringsskjema |
| `patients-app.js` | alltid | Oppstart (`DOMContentLoaded`), faneskift, auto-refresh, lastere for navneregistrene |
| `patients-stats.js` | **kun admin/lead/lead_view** | Statistikkfanen (Chart.js), arkiv, admin-handlinger |

**Alt en `read_only`- eller `read_write`-bruker kan nå, må ligge i en alltid-lastet modul.** `read_write` har skrivetilgang uten statistikktilgang — derfor bor f.eks. `saveEventName` i `patients-app.js`. Kall fra alltid-lastet kode til `patients-stats.js` må gå gjennom `_kall('navn')`, som sjekker at funksjonen finnes. `JsModulLastingTests` håndhever dette.

CSRF-sikret fetch-wrapper brukes for alle API-kall. Tabulator for pasientgrid, Chart.js for statistikk.

Brukerdata som settes inn med `innerHTML` **skal** escapes — `escHtmlValue()` i tabeller (tallsikker), `escapeHtml()`/`_escHtml()` ellers. Markup koden bygger selv merkes med `trustedHtml()`. `patients/tests_xss_stats.py` håndhever dette.

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