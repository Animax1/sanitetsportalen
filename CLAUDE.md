# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

Importér alltid dekoratorer fra `core.auth_decorators` (ikke `accounts.decorators`):

```python
from core.auth_decorators import admin_required, write_required, stats_required, role_required
```

Rollehierarki (lavest → høyest): `read_only → read_write → lead_view → lead → admin`

`has_role_at_least(user, 'lead')` sjekker hierarkisk. Dekoratorer gir 403 hvis rollen mangler.

### API-mønster (patients/views.py)

Alle endepunkter er JSON-API-er beskyttet med `@login_required` + rollesjekk. Responser følger mønsteret `{'status': 'ok', 'data': ...}` eller `{'status': 'error', 'message': ...}`.

### Audit-logging

Feltendringer logges automatisk via Django-signal i `audit/signals.py`. `RequestAuditMiddleware` lagrer request i thread-local slik at signaler kan hente bruker og IP uten å ta imot `request`-objektet direkte. Legg aldri til manuell audit-kode — signalet tar seg av det.

### Backup-system

`BackupSchedulerMiddleware` kjører automatisk backup in-process etter request. Backup-innhold er kun `patients`-appen (ikke brukere eller audit-logger). All backup-logikk ligger i `patients/backup_service.py` og `core/backup/`.

### Statistikk-caching (patients/stats_cache.py)

Basic stats caches 15 sek, full stats 60 sek. Støtter ETag/304. Invalideres ved pasientendringer via signal.

### Frontend

Én stor `static/js/script.js` (ingen bundler). CSRF-sikret fetch-wrapper brukes for alle API-kall. Tabulator for pasientgrid, Chart.js for statistikk.

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

## Deployment

Railway med PostgreSQL og persistent volume på `/data`. Auto-deploy fra GitHub `main`. Health-check: `GET /healthz/`.