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

### Statistikk-caching (patients/stats_cache.py)

Basic stats caches 15 sek, full stats 60 sek. Støtter ETag/304.

Det finnes **ingen** eksplisitt invalidering — cachen utløper på TTL. De korte TTL-ene er valgt nettopp for å slippe invalideringslogikk, og alle cache-operasjoner er pakket i try/except slik at en død cache degraderer til vanlig beregning i stedet for å ta ned endepunktet.

### Frontend

Fire moduler i `static/js/`, lastet ubetinget av `templates/patients/index.html` (ingen bundler):

| Modul | Ansvar |
|-------|--------|
| `patients-utils.js` | CSRF-fetch (`apiFetch`), `withSubmitGuard`, escaping, delt tilstand |
| `patients-table.js` | Tabulator-grid og tavle |
| `patients-forms.js` | Registrerings- og redigeringsskjema |
| `patients-stats.js` | Statistikkfanen (Chart.js) og arkivvisning |

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
| `EMAIL_HOST` m.fl. | SMTP for feilvarsel. Uten den skrives mail til konsoll |

## Deployment

Railway med PostgreSQL og persistent volume på `/data`. Auto-deploy fra GitHub `main`. Health-check: `GET /healthz/`.