# Pasientregistreringssystem – Django

Et sanntids pasientregistreringssystem for legesenter og arrangementer.
Bygget med Django 5.2+, Bootstrap 5, Chart.js og Tabulator.

---

## Arkitektur

```
django_project/
├── accounts/       – Brukerhåndtering, roller, MFA, innlogging, LoginEvent
├── audit/          – AuditLog-modell og middleware
├── patients/       – Pasientregistrering (hoved-app)
│   ├── models.py   – Patient, Behandler, Helsepersonell, AppSetting, Backup, BackupConfig
│   ├── views.py    – REST-API (JSON), inkl. 6 backup-endepunkter
│   ├── services.py – Statistikk og filtrering
│   ├── backup_service.py   – Backup/restore-logikk
│   ├── backup_scheduler.py – In-process-scheduler (BackupSchedulerMiddleware)
│   ├── middleware.py        – BackupSchedulerMiddleware + SecurityHeadersMiddleware
│   ├── signals.py  – Audit-logging av feltendringer
│   └── tests*.py   – Kjernetester, backuptester, schedulertester, offline-tester
├── static/         – CSS og JavaScript (script.js)
└── templates/      – HTML-maler
```

### Datamodeller

**accounts**
- **CustomUser** – `AbstractBaseUser + PermissionsMixin` med roller og MFA-støtte
- **LoginEvent** – loggpost for inn-/utlogging, MFA og passordbytte

**audit**
- **AuditLog** – endringslogg på feltnivå for alle pasientoperasjoner

**patients**
- **Patient** – pasientnummer (globalt unikt), year, behandler (FK PROTECT),
  helsepersonell_ref (FK PROTECT), problemstilling, kliniske felt,
  pabegynt_at, obs_at, utskrevet_at, deleted_at (soft-delete)
- **Behandler** – name, is_active; FK med `PROTECT` bevarer historikk
- **Helsepersonell** – name, is_active
- **AppSetting** – nøkkel-verdi for konfigurasjon (event_name, next_patient_nr, session_timeout_hours)
- **Backup** – filename, kind (manual/auto/pre_reset/pre_restore), size_bytes, created_at, created_by, note
- **BackupConfig** – singleton (pk=1), interval_minutes, last_run_at

### Roller

| Rolle      | Lese pasienter | Skrive | Statistikk | Admin | Kan endre andres passord |
|------------|---------------|--------|------------|-------|--------------------------|
| read_only  | ✓             | –      | –          | –     | –                        |
| read_write | ✓             | ✓      | –          | –     | –                        |
| lead_view  | ✓             | –      | ✓          | –     | –                        |
| lead       | ✓             | ✓      | ✓          | –     | –                        |
| admin      | ✓             | ✓      | ✓          | ✓     | ✓                        |

---

## Lokalt på Windows (PowerShell)

```powershell
# 1. Klon eller hent prosjektet
cd C:\prosjekter\pasientregistrering

# 2. Opprett virtuelt miljø
python -m venv .venv

# 3. Aktiver
.\.venv\Scripts\Activate.ps1

# Hvis scripts er blokkert:
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 4. Installer avhengigheter
pip install -r requirements.txt

# 5. Konfigurer miljøvariabler
Copy-Item .env.example .env
# Rediger .env og sett SECRET_KEY til en lang tilfeldig streng

# 6. Kjør migrasjoner
python manage.py migrate

# 7. Opprett admin-bruker
python manage.py create_admin --username admin --password "bytt-meg"

# 8. Start utviklingsserver
python manage.py runserver
```

Åpne nettleseren på http://127.0.0.1:8000/

---

## GitHub Push

```powershell
# Initialiser repo (første gang)
git init
git add .

# Sjekk at .env IKKE er med
git status  # .env skal ikke vises (sjekk .gitignore)

# Commit og push
git commit -m "Initial commit"
git remote add origin https://github.com/<brukernavn>/<repo>.git
git branch -M main
git push -u origin main
```

Viktig: Sjekk at `.gitignore` inneholder:
```
.env
*.pyc
__pycache__/
db.sqlite3
arkiv/
```

---

## Railway Deploy

### Steg 1 – Nytt prosjekt

1. Gå til [railway.app](https://railway.app) og logg inn
2. **New Project** → **Deploy from GitHub repo** → velg repo
3. Railway oppdager Django automatisk

### Steg 2 – PostgreSQL-database

1. I prosjektet: **+ New** → **Database** → **PostgreSQL**
2. Gå til databasetjenesten → **Variables** → kopier `DATABASE_URL`

### Steg 3 – Volume for backup-lagring

Backupfiler må lagres på et persistert volum, ellers slettes de ved ny deploy.

1. Trykk **Ctrl+K** i Railway og velg **Create Volume**
2. Sett mount path til `/data`
3. Koble volumet til **web**-tjenesten din

### Steg 4 – Miljøvariabler (i Railway GUI)

#### Obligatoriske

| Variabel               | Verdi                                          | Beskrivelse |
|------------------------|------------------------------------------------|-------------|
| `SECRET_KEY`           | Lang tilfeldig streng (50+ tegn)               | Django kryptografisk nøkkel |
| `DATABASE_URL`         | Limes fra PostgreSQL-pluginen                  | Settes automatisk når du kobler Postgres |
| `ALLOWED_HOSTS`        | `ditt-domene.up.railway.app`                   | Komma-separert liste av godkjente domener |
| `CSRF_TRUSTED_ORIGINS` | `https://ditt-domene.up.railway.app`           | Med `https://`-prefiks |
| `DEBUG`                | `false`                                        | Må være `false` i produksjon |
| `BACKUP_DIR`           | `/data/backups`                                | Må peke på Volume mount-stien |
| `RATELIMIT_ENABLE`     | `true`                                         | Nødbryter: sett til `false` ved event-problemer |

`BACKUP_DIR` må peke på mount-stien til volumet (`/data/backups`). Peker den et annet sted, vil filer ikke overleve mellom deploys.

#### Valgfrie – skalering og drift

Disse har fornuftige defaults og trenger **ikke** settes med mindre du
skal oppgradere kapasitet under høy last. Endringer trer i kraft ved
automatisk redeploy (~60s).

| Variabel           | Default | Når endre? |
|--------------------|---------|------------|
| `WEB_WORKERS`      | `1`     | Øk til `2` hvis P95 > 500 ms eller > 30 samtidige brukere |
| `WEB_THREADS`      | `4`     | Øk til `6` hvis P95 fortsatt høy etter `WEB_WORKERS=2` |
| `WEB_MAX_REQUESTS` | `1000`  | La stå. Worker-recycle etter 1000 requests (beskytter mot minnelekkasjer) |

**Observabilitet**: Admin-rollen kan åpne `/admin/server-status/` for
å se P50/P95 responstid, RPS, minnebruk, aktive sesjoner og toggle
feature-flags — uten redeploy. Se `RUNBOOK_VAKT.md` for konkrete
terskler og tiltak.

#### Valgfrie – superbruker ved første deploy

Brukes kun ved første deploy for å auto-opprette admin. Fjern etterpå.

| Variabel                      | Beskrivelse |
|-------------------------------|-------------|
| `DJANGO_SUPERUSER_USERNAME`   | Brukernavn for initial admin |
| `DJANGO_SUPERUSER_PASSWORD`   | Initialt passord (må byttes ved første innlogging) |

#### Feature-flags

Disse styres **ikke** via miljøvariabler, men via admin-dashbordet
(`/admin/server-status/`) og lagres i `AppSetting`-tabellen. Endringer
trer i kraft umiddelbart uten redeploy:

| Nøkkel                         | Default | Beskrivelse |
|--------------------------------|---------|-------------|
| `feature.live_stats_enabled`   | `false` | Planlagt funksjon — ikke implementert ennå. Default er `false` til funksjonen lander. |

### Steg 5 – Generer domene

I Railway-tjenesten: **Settings** → **Networking** → **Generate Domain**

### Steg 6 – Opprett admin

Via Railway Shell (tjenesten → **Shell**-fanen):
```bash
python manage.py create_admin --username admin --password "sikkert-passord"
```

Eller sett miljøvariablene `DJANGO_SUPERUSER_USERNAME` og `DJANGO_SUPERUSER_PASSWORD` – da kjøres `createsuperuser --noinput` automatisk ved release.

---

## Tester

```bash
# Kjør alle tester
python manage.py test patients accounts audit

# Med verbose output
python manage.py test patients accounts audit -v 2
```

### Testoversikt – 178 tester totalt

| Modul                  | Antall | Beskrivelse                                     |
|------------------------|--------|-------------------------------------------------|
| accounts               | 22     | Auth, MFA, sesjoner, rate-limit                 |
| backup                 | 18     | Create, restore, sikkerhet, purge               |
| scheduler              | 8      | In-process backup-scheduler                     |
| security headers       | 5      | CSP, HSTS, X-Frame-Options m.fl.                |
| patients core          | 58     | Filter, rolle, CRUD, statistikk                 |
| offline                | 34     | SQLite-isolasjon, import av offline-data        |
| admin server-status    | 19     | Metrics-ringbuffer, dashbord, feature-flags     |
| stats-cache + ETag     | 14     | Cache-TTL, ETag/304, invalidering               |

---

## Sikkerhet

### Autentisering

- CustomUser med sterk passord-hashing (argon2/pbkdf2)
- Brute-force-lås: 5 feil → 15 minutter utestengt
- **Dobbel rate-limit** på innlogging: 10 forsøk per brukernavn / 50 per IP per 5 minutter
- **Nødbryter:** sett `RATELIMIT_ENABLE=false` for å skru av rate-limiting ved behov
- **TOTP MFA** med engangskoder og backup-koder
- MFA trust-cookie (30 dager, signert, enhets-bundet)
- Sesjon-invalidering ved passord- og MFA-bytte

### HTTP-sikkerhet

Følgende innstillinger er aktive når `DEBUG=False`:

- `SECURE_SSL_REDIRECT = True` – tving HTTPS
- `SECURE_HSTS_SECONDS = 31536000` – HSTS 1 år med subdomener og preload
- `SESSION_COOKIE_SECURE = True` / `CSRF_COOKIE_SECURE = True` – cookies kun over HTTPS
- `X_FRAME_OPTIONS = 'DENY'` – forhindrer clickjacking
- `SECURE_CONTENT_TYPE_NOSNIFF = True` – forhindrer MIME-sniffing
- `Content-Security-Policy` – satt av `SecurityHeadersMiddleware`
- `Referrer-Policy: same-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### Audit

- Hver pasient-endring logges på feltnivå via `AuditLog`
- Inn-/utlogging, MFA-hendelser og passordbytte logges som `LoginEvent`
- Backup create/restore/download/delete logges

### Backup-sikkerhet

- Backup inneholder **kun pasientdata** (`BACKUP_APPS=['patients']`)
- Ekskluderer passord-hasher, audit-logg, sesjoner og LoginEvent
- Ekskluderer `Backup`- og `BackupConfig`-modeller (unngår selvreferanse)
- Restore rører **ikke** brukere, audit-logg eller sesjoner
- Pre-restore snapshot lages automatisk før gjenoppretting
- Filnavn genereres server-side (ingen path traversal mulig)
- Generisk feilmelding ved restore (lekker ikke interne detaljer)
- Automatisk sletting etter 72 timer

### Sesjonstimeout

Sesjonslevetid er 8 timer som standard og kan justeres av admin
under **Innstillinger → Sesjonstimeout** (1–24 timer).
Innstillingen lagres i `AppSetting` med nøkkelen `session_timeout_hours`.
`DynamicSessionTimeoutMiddleware` leser verdien ved hver forespørsel.

### Sesjonsinvalidering

- **Passordbytte:** Alle andre aktive sesjoner for brukeren slettes automatisk.
  Nåværende sesjon beholdes slik at brukeren ikke logges ut.
- **Admin-reset passord:** Alle aktive sesjoner for den berørte brukeren slettes.
  Admin-brukerens egen sesjon påvirkes ikke.

---

## API-endepunkter

### Pasienter og behandlere

| Metode   | URL                           | Tilgang                      | Beskrivelse                     |
|----------|-------------------------------|------------------------------|---------------------------------|
| GET      | `/api/patients/`              | Alle                         | Liste aktive pasienter          |
| POST     | `/api/patients/`              | write+                       | Ny pasient                      |
| PUT      | `/api/patients/<id>/`         | write+                       | Oppdater pasient                |
| DELETE   | `/api/patients/<id>/`         | admin                        | Soft-delete pasient             |
| GET      | `/api/behandlere/`            | Alle                         | Liste behandlere                |
| POST     | `/api/behandlere/`            | admin                        | Ny behandler                    |
| PUT      | `/api/behandlere/<id>/`       | admin                        | Oppdater behandler              |
| DELETE   | `/api/behandlere/<id>/`       | admin                        | Slett behandler                 |
| GET      | `/api/stats/`                 | Alle                         | Basis-statistikk (cachet 15s, ETag/304) |
| GET      | `/api/full-stats/`            | admin + lead + lead_view     | Full statistikk (cachet 60s, ETag/304)  |
| GET/PUT  | `/api/settings/`              | GET: alle / PUT: admin       | Appinnstillinger                |
| GET      | `/api/archives/`              | Alle                         | Liste JSON-arkivfiler           |
| POST     | `/api/reset-active-year/`     | admin                        | Slett all testdata i aktivt år  |
| GET/PUT  | `/api/session-timeout/`       | GET: alle / PUT: admin       | Sesjonstimeout (timer)          |

### Backup

| Metode   | URL                              | Tilgang | Beskrivelse                          |
|----------|----------------------------------|---------|--------------------------------------|
| GET      | `/api/backup/`                   | admin   | Liste alle backupfiler               |
| POST     | `/api/backup/create/`            | admin   | Lag ny manuell backup                |
| POST     | `/api/backup/restore/<pk>/`      | admin   | Gjenopprett fra backup               |
| GET      | `/api/backup/download/<pk>/`     | admin   | Last ned backup-fil                  |
| DELETE   | `/api/backup/delete/<pk>/`       | admin   | Slett backup-fil                     |
| GET/POST | `/api/backup/config/`            | admin   | Les/oppdater backup-konfigurasjon    |

### Admin-verktøy (kun admin-rolle)

| Metode   | URL                                   | Beskrivelse                          |
|----------|---------------------------------------|--------------------------------------|
| GET      | `/admin/server-status/`               | HTML-dashbord: metrics, RAM, sesjoner, feature-flags |
| GET      | `/admin/server-status/json/`          | Samme data som JSON (for polling)    |
| POST     | `/admin/server-status/flag/`          | Sett feature-flag (whitelistede nøkler) |
| GET      | `/admin/`                             | Django-admin (database-administrasjon) |

---

## Vanlige feil

### `Activate.ps1 kan ikke lastes inn`

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### `python åpner Microsoft Store`

Bruk `py` i stedet for `python`, eller juster PATH:
- Sjekk at Python er i `C:\Users\<navn>\AppData\Local\Programs\Python\Python3xx\`
- Legg til i PATH via Systeminnstillinger → Miljøvariabler

### `DisallowedHost at /`

Legg til i `.env`:
```
ALLOWED_HOSTS=localhost,127.0.0.1,ditt-domene.up.railway.app
```

### `CSRF verification failed`

Legg til i `.env` (Railway):
```
CSRF_TRUSTED_ORIGINS=https://ditt-domene.up.railway.app
```

### `psycopg2-binary feiler ved installasjon`

```powershell
python -m pip install --upgrade pip
pip install psycopg2-binary
```

### `Static files mangler (CSS/JS ikke lastet)`

Kjør før deploy:
```bash
python manage.py collectstatic --noinput
```
Legg til i `Procfile`:
```
release: python manage.py migrate && python manage.py collectstatic --noinput
```

### `Migrering feiler på Behandler-FK`

Pass på at migrasjonene kjøres i riktig rekkefølge:
```bash
python manage.py showmigrations patients
# Sjekk at 0001_initial er [X] (kjørt) før 0002_behandler_and_year kjøres
python manage.py migrate patients
```

### `Backup viser «Fil mangler på disk»`

Dette betyr at `BACKUP_DIR` ikke peker til Volume mount-stien.
Sjekk at miljøvariabelen er satt til `/data/backups` og at Railway Volume
er koblet til web-tjenesten med mount path `/data`.
