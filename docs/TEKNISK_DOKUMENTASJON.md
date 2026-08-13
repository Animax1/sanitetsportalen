# Teknisk dokumentasjon – Pasientregistreringssystemet

> **Versjon:** April 2026 (revidert)  
> **Målgruppe:** Teknisk etterfølger (utvikler / IT-konsulent) som overtar drift eller videreutvikling.  
> **Status:** Revidert utgave – observability-lag, stats-cache/ETag, Redis-backend og Gunicorn workers/threads-konfigurasjon er dokumentert.

---

## 1. Sammendrag

Pasientregistreringssystemet er en nettbasert applikasjon for sanntids registrering og sporing av pasienter ved legesentre, sanitetsoppdrag og andre tidsbegrensede medisinske arrangementer. Appen gir personell mulighet til å opprette pasientposter, følge triagering (Rød/Gul/Grønn), spore behandlingsforløp fra ankomst til utskriving og generere statistikk over pasientstrømmen. Systemet er bygget med Django 5.2+, PostgreSQL som produksjonsdatabase og vanlig JavaScript uten rammeverk på klientsiden. Det deployeres på Railway-plattformen og benytter MFA (TOTP), rollebasert tilgangsstyring og audit-logging i tråd med GDPR-krav for helseopplysninger.

---

## 2. Teknologistack

| Komponent | Teknologi | Versjon | Formål |
|---|---|---|---|
| Backend-rammeverk | Django | >=5.2 | Webapplikasjon, ORM, admin |
| Database (produksjon) | PostgreSQL | Railway-administrert | Persistent lagring av alle data |
| Database (utvikling) | SQLite | Innebygd | Lokal testing, ingen oppsett nødvendig |
| Database (offline) | SQLite (`offline.sqlite3`) | Innebygd | Offline-modus ved nettverksutfall |
| Database-driver | psycopg2-binary | >=2.9 | Kobling Django–Postgres |
| Database-URL-parsing | dj-database-url | >=2.1 | Tolker `DATABASE_URL`-miljøvariabelen |
| WSGI-server | Gunicorn | >=21.2 | Produksjonsserver (default 1 worker × 4 tråder, parametrisert) |
| Prosessmålinger | psutil | >=5.9 | Henter `memory_mb` og prosessinfo for server-status-dashbordet |
| Statiske filer | WhiteNoise | >=6.6 | Serverer komprimerte statiske filer fra Django |
| Miljøvariabler | python-dotenv | >=1.0 | Laster `.env`-filer lokalt |
| MFA / OTP | django-otp + otp_totp + otp_static | >=1.5.0 | TOTP-enheter og backup-koder |
| QR-kode | qrcode[pil] | >=7.4 | Genererer QR-kode for MFA-oppsett |
| Rate-limiting | django-ratelimit | >=4.1 | Begrenser innloggingsforsøk per IP og brukernavn |
| Cache (rate-limit, stats) | LocMemCache eller Redis | Django innebygd / `redis>=5.0` | Backend velges automatisk: Redis når `REDIS_URL` er satt (prod med 2+ workers), ellers LocMemCache (in-process, lokal/single-worker) |
| Statistikk | scipy | >=1.11 | Chi-square og Kruskal-Wallis-tester |
| Stats-cache | Django cache-rammeverk | Innebygd | Basert på LocMemCache; dekoratøren `cached_stats_response` med ETag/304-støtte |
| Testing | Django TestCase | – | 178 tester totalt (145 opprinnelige + 19 admin server-status + 14 stats-cache/ETag) |
| Python-versjon | Python | 3.12 (runtime.txt) | Kjøretidsmiljø |
| Deploy-plattform | Railway | – | Hosting, Postgres, Volume, HTTPS |
| Frontend-grid | Tabulator | (CDN) | Pasienttabell med sortering og filtrering |
| Frontend-diagram | Chart.js | (CDN) | Statistikk-diagrammer |
| Frontend-UI | Bootstrap 5 | (CDN) | Responsivt grensesnitt, modaler |
| Frontend-ikoner | Bootstrap Icons | (CDN) | UI-ikoner |
| Frontend-logikk | Vanlig JavaScript | – | Ingen rammeverk, ingen bundler; fire moduler i `static/js/` |

---

## 3. Arkitektur

### 3.1 Komponentdiagram

```
  Nettleser (Bootstrap 5 + Tabulator + Chart.js + patients-*.js)
       |
       | HTTPS (TLS 1.2+)
       v
  Railway Gateway (edge-proxy, terminerer TLS, setter X-Forwarded-Proto: https)
       |
       | HTTP (intern)
       v
  Gunicorn (1 worker, 4 tråder, port $PORT)
       |
       v
  Django 5.2+ WSGI-app
   ├── SecurityMiddleware
   ├── MemoryLoggingMiddleware  (logger RSS og responstid for tunge requests)
   ├── WhiteNoiseMiddleware  (serverer /static/ direkte)
   ├── SessionMiddleware
   ├── CommonMiddleware
   ├── CsrfViewMiddleware
   ├── AuthenticationMiddleware
   ├── OTPMiddleware (django-otp)
   ├── MessageMiddleware
   ├── XFrameOptionsMiddleware
   ├── RequestAuditMiddleware  (lagrer request i thread-local)
   ├── MustChangePasswordMiddleware
   ├── DynamicSessionTimeoutMiddleware
   ├── BackupSchedulerMiddleware  (in-process cron for automatisk backup)
   ├── RequestMetricsMiddleware   (observability: ringbuffer 500 samples, p50/p95/max/errors)
   └── SecurityHeadersMiddleware  (CSP, Referrer-Policy, Permissions-Policy)
       |
       ├── accounts-app  (innlogging, MFA, brukeradmin, LoginEvent)
       ├── patients-app  (pasient-API, behandlere, helsepersonell, innstillinger, statistikk, backup)
       └── audit-app     (AuditLog-modell, purge-kommando, check_ssl)
       |
       v
  PostgreSQL (Railway-administrert, AES-256 at rest, TLS 1.2+ i transitt)
  Railway Volume /data/backups  (JSON-backup-filer)
       |
       v
  LocMemCache  (in-process, rate-limit-tellere)
```

### 3.2 Request-flyt

1. Nettleseren sender en HTTPS-forespørsel til Railway-domenet.
2. Railway-gatewayen terminerer TLS og videresender forespørselen til Gunicorn med `X-Forwarded-Proto: https`. Django er konfigurert med `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` (`settings.py`, linje 118) slik at Django tolker dette riktig.
3. Gunicorn mottar forespørselen og sender den gjennom Django-middleware-kjeden.
3b. `MemoryLoggingMiddleware` registrerer RSS-minne og starter timer; logger til `memory`-loggeren ved avslutning hvis request tok >200ms eller økte RSS med >1MB.
4. `OTPMiddleware` sjekker om brukeren har gjennomgått OTP-verifisering.
5. `RequestAuditMiddleware` legger request-objektet i thread-local slik at audit-signaler kan hente bruker og IP uten å sende request eksplisitt.
6. `MustChangePasswordMiddleware` omdirigerer til passordbytte-siden dersom `must_change_password=True`.
7. `DynamicSessionTimeoutMiddleware` leser `session_timeout_hours` fra `AppSetting` og setter sesjonens levetid per forespørsel.
8. `BackupSchedulerMiddleware` sjekker (throttlet til 60 sek per prosess) om et automatisk backup-intervall er passert og starter i så fall backup i en bakgrunnstråd etter at requesten er returnert.
9. `RequestMetricsMiddleware` tidsstempler requesten ved inngang, måler varighet ved utgang og skriver samplet (path, method, status, duration_ms) inn i en thread-safe ringbuffer med 500 plasser. Loggen inneholder ingen pasientdata.
10. `SecurityHeadersMiddleware` setter `Content-Security-Policy`, `Referrer-Policy` og `Permissions-Policy` på alle responser.
11. Django-viewet behandler forespørselen, utfører databaseoperasjoner via ORM og returnerer svar (HTML eller JSON).
12. Audit-signaler (`patients/signals.py`) trigges automatisk av ORM ved `pre_save`, `post_save` og `post_delete` på `Patient`.

### 3.3 Applikasjoner

| App | Ansvar |
|---|---|
| `accounts` | `CustomUser`-modell, innloggingsflyt (3-steg med MFA), MFA-håndtering (TOTP, backup-koder, trust-cookies), passordbytte, brukeradmin-panel, rate-limiting, sesjon-invalidering, `LoginEvent`-logging |
| `patients` | `Patient`-, `Forstehjelper`-, `Helsepersonell`-, `AppSetting`-, `Backup`- og `BackupConfig`-modeller, JSON-API for pasient-CRUD, førstehjelper-CRUD, backup-API, statistikk-beregning (`services.py`), arkivliste, backup-scheduler-middleware, sikkerhetstopptekster-middleware |
| `audit` | `AuditLog`-modell for alle feltendringer på pasienter, `RequestAuditMiddleware`, `purge_old_logs`-kommando, `check_ssl`-kommando |

---

## 4. Datamodell

### 4.1 `accounts.CustomUser`

Basert på `AbstractBaseUser` + `PermissionsMixin`. Definert i `accounts/models.py`.

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | Intern primærnøkkel | PK, auto |
| `username` | CharField(64) | Brukernavn | `UNIQUE`, påkrevd |
| `email` | EmailField(120) | E-post (valgfritt) | `NULL` tillatt; unik hvis satt (`UniqueConstraint` med betingelse) |
| `role` | CharField(20) | Brukerrolle | Choices: `admin`, `lead`, `lead_view`, `read_write`, `read_only`; default `read_only` |
| `is_active` | BooleanField | Aktiv konto | Default `True` |
| `is_staff` | BooleanField | Django Admin-tilgang | Default `False` |
| `must_change_password` | BooleanField | Tving passordbytte | Default `True` (settes `False` etter bytte) |
| `mfa_required` | BooleanField | Krev TOTP-MFA | Default `False`; settes `True` av data-migrasjon for admin/lead |
| `failed_login_attempts` | IntegerField | Antall mislykkede forsøk siden sist reset | Default `0` |
| `locked_until` | DateTimeField | Konto låst til dette tidspunktet | `NULL` betyr ikke låst |
| `created_at` | DateTimeField | Opprettet | Auto, `auto_now_add` |
| `updated_at` | DateTimeField | Sist oppdatert | Auto, `auto_now` |
| `last_login_at` | DateTimeField | Tidspunkt for siste vellykkede innlogging | `NULL` tillatt |

`USERNAME_FIELD = 'username'`. Passordet lagres som en Django-hash — i dag PBKDF2-HMAC-SHA256. Argon2 er **ikke** installert; det krever `argon2-cffi` i `requirements.txt`.

### 4.2 `accounts.LoginEvent`

Audit-tabell for innloggingshendelser og MFA-hendelser. Definert i `accounts/models.py`.

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | PK | Auto |
| `user` | ForeignKey → CustomUser | Brukeren hendelsen gjelder | `NULL` tillatt; `on_delete=SET_NULL` |
| `username_attempt` | CharField(64) | Brukernavn som ble forsøkt | Lagres alltid, også ved ukjent bruker |
| `success` | BooleanField | Om hendelsen var vellykket | – |
| `ip` | GenericIPAddressField | Klientens IP-adresse | `NULL` tillatt |
| `user_agent` | TextField | HTTP User-Agent | Blank tillatt |
| `event_type` | CharField(30) | Type hendelse | Choices: `login`, `mfa_setup_completed`, `mfa_verify_success`, `mfa_verify_failed`, `mfa_backup_used`, `mfa_trust_cookie_used`, `mfa_reset_by_admin`; default `login` |
| `created_at` | DateTimeField | Tidspunkt | `auto_now_add`, indeksert via `ordering = ['-created_at']` |

### 4.3 `patients.Patient`

Kliniske pasientdata. Definert i `patients/models.py`.

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | Intern DB-ID | PK |
| `pasientnummer` | IntegerField | Løpenummer innen aktivt år | `UNIQUE` |
| `year` | IntegerField | Årstall pasienten tilhører | `db_index=True`; default: inneværende år |
| `problemstilling` | CharField(255) | Innleggelsesårsak | Blank tillatt |
| `arsak` | CharField(255) | Årsak til henvendelse | Blank tillatt |
| `transport` | CharField(255) | Ankomsttransport | Blank tillatt |
| `inntid` | TextField | Ankomsttidspunkt (tekstformat `dd.mm.YYYY HH:MM`) | Blank tillatt |
| `grovsortering` | CharField(50) | Triagefarge: `Rød`, `Gul`, `Grønn` | Blank tillatt |
| `pabegynt` | TextField | Tidspunkt behandling påbegynt (auto-stemplet) | Blank tillatt |
| `plassering` | CharField(255) | Plassering i mottaket | Blank tillatt |
| `forstehjelper` | ForeignKey → Forstehjelper | Tilknyttet førstehjelper | `NULL` tillatt; `on_delete=PROTECT` |
| `helsepersonell_ref` | ForeignKey → Helsepersonell | Tilknyttet helsepersonell | `NULL` tillatt; `on_delete=PROTECT` |
| `lege` | CharField(50) | Lege | Blank tillatt |
| `medisiner` | CharField(50) | Medisiner gitt | Blank tillatt |
| `inn_obspost` | TextField | Tidspunkt innleggelse obspost (auto-stemplet) | Blank tillatt |
| `ut_obspost` | TextField | Tidspunkt utskriving obspost (auto-stemplet) | Blank tillatt |
| `utskrevet` | TextField | Tidspunkt utskriving (auto-stemplet) | Blank tillatt |
| `utskrevet_til` | CharField(255) | Utskrivningsdestinasjon | Blank tillatt |
| `journal` | CharField(50) | Journalnummer | Blank tillatt |
| `created_at` | DateTimeField | Opprettet | `auto_now_add` |
| `updated_at` | DateTimeField | Sist oppdatert | `auto_now` |
| `is_active` | BooleanField | Aktiv (soft-delete) | Default `True` |

`on_delete=PROTECT` på `forstehjelper`- og `helsepersonell_ref`-FK betyr at verken førstehjelper eller helsepersonell kan slettes dersom det finnes pasienter knyttet til dem – deaktivering benyttes i stedet.

### 4.4 `patients.Forstehjelper`

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | PK | Auto |
| `name` | CharField(120) | Førstehjelperens navn | `UNIQUE` |
| `user` | OneToOneField → CustomUser | Valgfri kobling til portalbruker (Fase 5) | `NULL` tillatt; `on_delete=SET_NULL`; `related_name='forstehjelper_profil'` |
| `is_active` | BooleanField | Aktiv i dropdown | Default `True` |
| `created_at` | DateTimeField | Opprettet | `auto_now_add` |

Inaktive forstehjelpere vises ikke i dropdown-menyer, men beholdes i databasen for å bevare referanseintegriteten på historiske pasienter. `user`-koblingen muliggjør «Mine pasienter»-filtrering og varsel ved tildeling (se Fase 5).

### 4.5 `patients.Helsepersonell`

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | PK | Auto |
| `name` | CharField(120) | Navn | `UNIQUE` |
| `is_active` | BooleanField | Aktiv i dropdown | Default `True` |
| `created_at` | DateTimeField | Opprettet | `auto_now_add` |

Brukes som FK-referanse (`helsepersonell_ref`) fra `Patient` med `on_delete=PROTECT`. Inaktive helsepersonell vises ikke i dropdown-menyer.

### 4.6 `patients.AppSetting`

Nøkkel-verdi-konfigurasjonstabellen. `key` er primærnøkkelen.

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `key` | CharField(64) | Nøkkel (PK) |
| `value` | TextField | Verdi (alltid lagret som tekst) |

Kjente nøkler i bruk:

| Nøkkel | Beskrivelse |
|---|---|
| `next_patient_nr` | Neste ledige pasientnummer (atomisk inkrement med `select_for_update`) |
| `active_year` | Aktivt år for filtrering og nye pasienter |
| `event_name` | Arrangementsnavnet (legacy-nøkkel) |
| `event_name_<år>` | Arrangementsnavn per år, f.eks. `event_name_2026` |
| `session_timeout_hours` | Sesjonslevetid i timer (1–24); default 8 |
| `feature.live_stats_enabled` | Feature-flagg for live-statistikk (`'true'`/`'false'`; default `'false'`). Funksjonen er ikke implementert ennå — default flyttes til `'true'` når koden lander. Styres via admin server-status. |

### 4.7 `patients.Backup`

Loggfører alle backup-operasjoner. Definert i `patients/models.py`.

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | PK | Auto |
| `filename` | CharField | Filnavn på backupfilen (uten sti) | – |
| `kind` | CharField | Type backup | Choices: `manual`, `auto`, `pre_reset`, `pre_restore` |
| `size_bytes` | IntegerField | Filstørrelse i bytes | – |
| `created_at` | DateTimeField | Opprettet | `auto_now_add` |
| `created_by` | ForeignKey → CustomUser | Brukeren som startet backup | `NULL` tillatt; `SET_NULL` |
| `note` | TextField | Valgfritt notat | Blank tillatt |

### 4.8 `patients.BackupConfig`

Singleton-konfigurasjon (pk=1) for automatisk backup-planlegging.

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `id` | IntegerField | Alltid 1 (singleton) |
| `interval_minutes` | IntegerField | Intervall i minutter mellom automatiske backuper |
| `last_run_at` | DateTimeField | Tidspunkt for siste gjennomførte automatiske backup |

### 4.9 `audit.AuditLog`

Loggfører alle feltendringer på `Patient`-objekter. Definert i `audit/models.py`.

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | PK | Auto |
| `table_name` | CharField(64) | Tabellnavn, f.eks. `patients_patient` | – |
| `record_id` | BigIntegerField | PK for raden som ble endret | – |
| `action` | CharField(10) | `CREATE`, `UPDATE` eller `DELETE` | – |
| `field_name` | CharField(64) | Feltnavnet som ble endret | `NULL` tillatt |
| `old_value` | TextField | Gammel verdi (tekst) | `NULL` tillatt |
| `new_value` | TextField | Ny verdi (tekst) | `NULL` tillatt |
| `user` | ForeignKey → CustomUser | Brukeren som utførte endringen | `NULL` tillatt; `on_delete=SET_NULL` |
| `ip` | GenericIPAddressField | Klientens IP | `NULL` tillatt |
| `created_at` | DateTimeField | Tidspunkt | `auto_now_add`; indeksert |

To DB-indekser er definert: `(table_name, record_id)` og `(created_at)` for effektiv purging og oppslag. Loggen skrives via Django-signaler i `patients/signals.py` (`pre_save` for UPDATE, `post_save` for CREATE, `post_delete` for hard-sletting).

---

## 5. API-referanse

Alle API-endepunkter returnerer JSON. `Content-Type: application/json` sendes alltid for skriveoperasjoner. CSRF-token sendes som `X-CSRFToken`-header (leses fra `csrftoken`-cookie). Alle endepunkter krever innlogget sesjon; uautoriserte forespørsler omdirigeres til `GET /accounts/login/` (302) eller returnerer 403 JSON der det er hensiktsmessig.

### 5.1 Hoved-side

| Metode | Path | Autentisering | Beskrivelse |
|---|---|---|---|
| GET | `/` | Innlogget | Rendrer `patients/index.html` (SPA-innholdet) |

### 5.2 Pasienter

#### `GET /api/patients/`

**Rolle:** Alle innloggede brukere.

**Query-parametre:**

| Parameter | Beskrivelse | Eksempel |
|---|---|---|
| `filter` | Filtrer på status | `rod`, `gul`, `gronn`, `rodgul`, `aktive`, `utskrevet`, `alle` (default) |
| `include_archived` | Inkluder soft-slettede pasienter | `1` |

**Respons:** JSON-array av pasientobjekter. Hvert objekt inneholder alle `Patient`-felt pluss `forstehjelper` som `{id, name}` eller `null`. `created_at` formatert som `dd.mm.YYYY HH:MM`.

**Statuskoder:** 200.

---

#### `POST /api/patients/`

**Rolle:** `admin`, `lead`, `read_write`. Returnerer 403 for andre roller.

**Request-body (JSON):**

```json
{
  "grovsortering": "Rød",
  "problemstilling": "Brystsmerter",
  "arsak": "Fall",
  "transport": "Ambulanse",
  "inntid": "01.05.2026 14:30",
  "plassering": "Mottak 1",
  "forstehjelper": 3
}
```

Alle felt er valgfrie i body; `pasientnummer` og `year` settes automatisk av serveren. `forstehjelper` er en heltalls-ID som refererer til en aktiv `Forstehjelper`.

Automatiske tidsstempler settes av `services.py` dersom relevante felt fylles ut:
- `pabegynt` settes hvis behandlingsrelaterte felt (behandler, medisiner osv.) inkluderes
- `inn_obspost` settes hvis `plassering` starter med `obs`
- `utskrevet` settes automatisk hvis `utskrevet_til` oppgis

**Respons:** 201 med det opprettede pasientobjektet.

**Statuskoder:** 201 (opprettet), 400 (ugyldig JSON), 403 (ingen tilgang).

---

#### `PUT /api/patients/<pk>/`

**Rolle:** `admin`, `lead`, `read_write`.

**Request-body (JSON):** Delmengde av pasientfelt som skal oppdateres. Samme logikk for automatiske tidsstempler som ved POST. `forstehjelper` oppgis som ID eller `null`.

**Respons:** 200 med oppdatert pasientobjekt.

**Statuskoder:** 200, 403, 404.

---

#### `DELETE /api/patients/<pk>/`

**Rolle:** Kun `admin`.

Utfører soft-delete: setter `is_active=False`. Pasienten forsvinner fra standard liste-API (med mindre `include_archived=1`), men beholdes i databasen for historikk og audit.

**Respons:** `{"ok": true}`

**Statuskoder:** 200, 403, 404.

---

### 5.3 Forstehjelpere

#### `GET /api/forstehjelpere/`

**Rolle:** Alle innloggede brukere.

**ETag-støtte:** Endepunktet beregner en SHA-256-hash av førstehjelper-listen og sender `ETag`-headeren. Klienten lagrer ETag og sender `If-None-Match` ved neste kall. Hvis listen er uendret, returneres 304 Not Modified uten kropp. Kombinert med `Cache-Control: private, must-revalidate` og `@never_cache` gir dette effektiv validering uten unødvendig dataoverføring. Implementert i `patients/views_registre.py` og `patients-stats.js`.

**Respons:** JSON-array: `[{"id": 1, "name": "Ola Nordmann", "is_active": true}, ...]`. Sortert: aktive først, deretter alfabetisk.

**Statuskoder:** 200, 304.

---

#### `POST /api/forstehjelpere/`

**Rolle:** Kun `admin`. Returnerer 403 for andre.

**Request-body:** `{"name": "Navn"}`

**Feil:** 400 hvis navn er tomt eller duplikat.

**Respons:** 201 med `{id, name, is_active}`.

---

#### `PUT /api/forstehjelpere/<pk>/`

**Rolle:** Kun `admin`.

**Request-body:** `{"name": "Nytt navn"}` og/eller `{"is_active": false}`.

**Respons:** 200 med oppdatert objekt.

**Statuskoder:** 200, 400, 403, 404.

---

#### `DELETE /api/forstehjelpere/<pk>/`

**Rolle:** Kun `admin`.

Blokkeres med 409 Conflict hvis førstehjelperen er knyttet til én eller flere pasienter (`PROTECT`-FK), med beskjed om å deaktivere i stedet.

**Statuskoder:** 200, 403, 404, 409.

---

### 5.4 Statistikk

#### `GET /api/stats/`

**Rolle:** Alle innloggede brukere.

Returnerer basis-statistikk for aktivt år: totaltall, tilstede, utskrevet, triagefordeling, transportfordeling, topp-problemstillinger, ankomster per time, gjennomsnittlige ventetider.

**Statuskoder:** 200.

---

#### `GET /api/full-stats/`

**Rolle:** `admin`, `lead`, `lead_view`. Returnerer 403 for andre.

Returnerer full statistikk inkludert krysstabeller, Chi-square-tester (scipy) og Kruskal-Wallis-tester per triage, transport og problemstilling.

**Statuskoder:** 200, 403.

---

### 5.5 Innstillinger

#### `GET /api/settings/`

**Rolle:** Alle innloggede.

Returnerer alle `AppSetting`-nøkler som et flatt JSON-objekt: `{"event_name": "...", "active_year": "2026", ...}`.

---

#### `PUT /api/settings/`

**Rolle:** `admin`, `lead`, `read_write`.

Kun `event_name` kan oppdateres via dette endepunktet (`SETTINGS_WRITE_WHITELIST` i `patients/views_patients.py`). GET har sin egen, litt videre liste — `SETTINGS_READ_WHITELIST`.

**Request-body:** `{"event_name": "Arrangement 2026"}`

**Statuskoder:** 200, 403.

---

### 5.6 Sesjonstimeout

#### `GET /api/session-timeout/`

**Rolle:** Alle innloggede. Returnerer `{"hours": 8}`.

#### `PUT /api/session-timeout/`

**Rolle:** Kun `admin`.

**Request-body:** `{"hours": 4}` (1–24).

**Statuskoder:** 200, 400 (ugyldig verdi / utenfor 1–24), 403.

---

### 5.7 Reset aktivt år

#### `POST /api/reset-active-year/`

**Rolle:** Kun `admin`.

Lager automatisk en `pre_reset`-backup før sletting. Sletter deretter **alle** pasienter i aktivt år (hard delete) og nullstiller `next_patient_nr` til 1. Krever eksplisitt bekreftelse i body:

**Request-body:** `{"confirm": true}`

**Respons:** `{"ok": true, "year": 2026, "antall_slettet": 42, "melding": "..."}`

**Statuskoder:** 200, 400 (manglende bekreftelse), 403.

---

### 5.8 Arkiver

`GET /api/archives/` er **fjernet** (august 2026). Endepunktet listet JSON-filer i `arkiv/`-mappen, men ingenting i applikasjonen skrev slike filer — mappen var alltid tom, og lå dessuten på containerens flyktige disk på Railway, ikke på `/data`-volumet. Det var en rest fra Flask-tiden, før det databasebaserte vaktarkivet overtok.

Arkivering skjer nå utelukkende via `VaktArkiv`/`ArkivertPasient`, se seksjon om vaktarkiv-endepunktene (`/api/innstillinger/arkiv/…`).

---

### 5.9 Backup-endepunkter

Backup administreres samlet på `/portal-admin/backup/`, med én rad per registrert
backup-modul (`patients` og `arkiv`). Hver modul har eget intervall og egen cap i
`ModuleBackupConfig`.

| Metode | Path | Rolle | Beskrivelse |
|---|---|---|---|
| `GET` | `/portal-admin/backup/` | `admin` | Oversikt over alle backup-moduler |
| `GET/POST` | `/portal-admin/backup/<slug>/` | `admin` | Backup-liste og konfigurasjon for modulen |
| `POST` | `/portal-admin/backup/<slug>/run/` | `admin` | Opprett manuell backup |
| `POST` | `/portal-admin/backup/<slug>/restore/<pk>/` | `admin` | Gjenopprett fra backup |
| `GET` | `/portal-admin/backup/<slug>/last-ned/<pk>/` | `admin` | Last ned backup-fil |
| `POST` | `/portal-admin/backup/<slug>/slett/<pk>/` | `admin` | Slett backup-post og fil |

Alle backup- og restore-operasjoner logges i `AuditLog`.

> **Fjernet august 2026:** pasientmodulen hadde tidligere sine egne
> `/pasienter/api/backup/`-endepunkter med et eget UI-panel under Innstillinger. De var
> to flater over samme backend — samme `Backup`-tabell, samme filer, samme
> `core.backup.restore_backup`. Verre: panelets intervall-innstilling skrev til den
> gamle singleton-modellen `patients.BackupConfig`, som scheduleren aldri leser. Den var
> altså uten virkning. Pasientmodulen lenker nå til `/portal-admin/backup/` i stedet.

---

### 5.10 Accounts-endepunkter (HTML-sider)

| Metode | Path | Beskrivelse | Tilgang |
|---|---|---|---|
| GET/POST | `/accounts/login/` | Innlogging (3-steg) | Anonym |
| GET | `/accounts/logout/` | Logg ut | Innlogget |
| GET/POST | `/accounts/change-password/` | Bytt passord | Innlogget |
| GET | `/portal-admin/brukere/` | Liste brukere | `admin` |
| GET/POST | `/portal-admin/brukere/ny/` | Opprett bruker | `admin` |
| GET/POST | `/portal-admin/brukere/<pk>/` | Detaljer og handlinger for bruker | `admin` |
| POST | `/portal-admin/brukere/<pk>/slett/` | Slett bruker permanent | `admin` |
| GET | `/portal-admin/innloggingslogg/` | Global LoginEvent-visning | `admin` |

De gamle stiene `/accounts/users/*` svarer med permanent redirect (301) til de nye.

`/django-admin/` er **ikke montert i produksjon** (S1). Django sin innebygde admin er en
parallell innloggingsflate som omgår rate-limiting, kontosperre, MFA-tvang, tvungent
passordbytte og `LoginEvent`-logging — alle sikringene ligger på
`accounts.views.login_view`. Flaten monteres kun når `DEBUG=True` eller `OFFLINE_MODE=True`,
altså som lokalt utviklerverktøy.

### 5.11 Admin server-status (observability)

| Metode | Path | Rolle | Beskrivelse |
|---|---|---|---|
| GET | `/portal-admin/server-status/` | `admin` | HTML-dashbord: metrics (p50/p95/max/errors), RAM, aktive sesjoner, siste backup, feature-flags, worker-config |
| GET | `/portal-admin/server-status/json/` | `admin` | Maskinlesbart JSON-snapshot av samme data (for automatisering og ekstern overvåkning) |
| POST | `/portal-admin/server-status/flag/` | `admin` | Oppdaterer en feature-flag i `AppSetting`. Krever CSRF-token og `admin`-rolle. Body: `key` og `value` (form-encoded) |

---

## 6. Autentisering og tilgangsstyring

### 6.1 Innloggingsflyt

Innloggingen er delt i tre faser håndtert av én view (`accounts/views.py`, `login_view`):

**Steg 1 – Brukernavn og passord**

- Brukeren sender `POST /accounts/login/` med `username` og `password`.
- Django `authenticate()` verifiserer passordet.
- Ved feil: `failed_login_attempts` inkrementeres. Etter 5 feil låses kontoen i 15 minutter (`locked_until`-feltet). `LoginEvent` opprettes for hvert forsøk.
- Ved suksess: feltet `last_login_at` settes og `failed_login_attempts` nullstilles.
- Hvis `mfa_required=False`: bruker logges inn direkte (steg 4).
- Hvis `mfa_required=True` og ingen bekreftet TOTP-enhet finnes: overgang til steg 2.
- Hvis `mfa_required=True` og bekreftet enhet finnes: sjekk trust-cookie. Hvis gyldig: logg inn direkte. Ellers: overgang til steg 3.

**Steg 2 – MFA-oppsett (kun ved første gang)**

- Lagres i sesjon via `mfa_setup_user_id`.
- En ubekreftet `TOTPDevice` opprettes for brukeren og dens `config_url` rendres som en base64-kodet QR-kode (`qrcode`-biblioteket via `_generate_qr_base64`).
- 10 engangs backup-koder (`StaticToken`) genereres med `secrets.token_hex(4).upper()` og vises for brukeren (8 hex-tegn per kode).
- Brukeren bekrefter ved å taste en gyldig TOTP-kode. Enheten markeres `confirmed=True`, og `LoginEvent(event_type='mfa_setup_completed')` opprettes.

**Steg 3 – MFA-verifisering (innlogging nr. 2+)**

- Lagres i sesjon via `mfa_verify_user_id`.
- Brukeren taster 6-sifret TOTP-kode fra authenticator-appen, eller en backup-kode.
- Backup-koder er engangs (`StaticToken`-objekt slettes etter bruk).
- Avmerkingsboks "Stol på denne enheten i 30 dager" setter en signert trust-cookie (se 6.3).
- `LoginEvent` opprettes med type `mfa_verify_success`, `mfa_verify_failed` eller `mfa_backup_used`.

**Steg 4 – Innlogging fullført**

- `login(request, user)` kalles.
- `_invalidate_other_sessions()` sletter alle andre aktive sesjoner for brukeren (single-session-policy).
- Brukeren omdirigeres til `next`-parameter eller `/`.

### 6.2 MFA-mekanisme

- **TOTP (RFC 6238):** `django-otp` med `TOTPDevice`. Utsteder: `OTP_TOTP_ISSUER = 'Sanitetsportalen'` (settes i `settings.py`). Standard 30-sekunders vindu.
- **Backup-koder:** 10 engangs `StaticToken`-objekter, 8 hex-tegn hver. Slettes ved bruk. Ny sett genereres ved MFA-oppsett (gamle slettes).
- **Trust-cookie:** Signert token med `django.core.signing.TimestampSigner`. Cookie-navn: `mfa_trusted_<user_pk>`. Verdi: `<user_pk>:<device_pk>` signert med `SECRET_KEY`. Max-age: 30 dager (`MFA_TRUST_DEVICE_DAYS = 30`). `httponly=True`, `secure=True` i produksjon, `samesite='Lax'`. Validering sjekker at signaturen er gyldig, ikke er utløpt, og at `TOTPDevice` fortsatt eksisterer og er bekreftet.
- **Nullstilling av MFA (admin):** `accounts/views.py`. Sletter alle `TOTPDevice`- og `StaticDevice`-objekter, setter `mfa_required=True`, invaliderer alle sesjoner og logger `mfa_reset_by_admin`.

### 6.3 Roller og tilganger

Rollehierarkiet er definert i `accounts/models.py` (`UserRole`) og håndhevet via `accounts/decorators.py`.

| Rolle | Lese pasienter | Opprette/redigere pasienter | Slette pasient (soft) | Full statistikk | Brukeradmin | Nullstill år |
|---|---|---|---|---|---|---|
| `read_only` | Ja | Nei | Nei | Nei | Nei | Nei |
| `read_write` | Ja | Ja | Nei | Nei | Nei | Nei |
| `lead_view` | Ja | Nei | Nei | Ja | Nei | Nei |
| `lead` | Ja | Ja | Nei | Ja | Nei | Nei |
| `admin` | Ja | Ja | Ja | Ja | Ja | Ja |

Dekoratorene `admin_required`, `write_required` og `stats_required` er snarveier i `accounts/decorators.py`. API-views håndhever rolle inline (f.eks. `if request.user.role not in WRITE_ROLES`).

Frontend bruker `window.USER_ROLE` (satt av templaten) til å skjule elementer med CSS-klasser `.write-only`, `.stats-only` og `.admin-only` via `applyRoleVisibility()` i `patients-utils.js`.

### 6.4 Rate-limiting

Dobbel rate-limit på `POST /accounts/login/`:

- **Per brukernavn:** 10 forsøk per 5 minutter (`@ratelimit(key='post:username', rate='10/5m', ...)`).
- **Per IP:** 50 forsøk per 5 minutter (`@ratelimit(key='ip', rate='50/5m', ...)`).
- Begge dekoratorene er stablet på `login_view` i `accounts/views.py`.
- Nødbryter: `RATELIMIT_ENABLE`-miljøvariabel (`true`/`false`). Settes til `false` for å skru av rate-limiting uten kodeendring.
- **Cache:** Bestemmes av `REDIS_URL` env-variabel. Med Redis er telleren delt mellom alle workers (korrekt rate-limiting). Med LocMemCache er telleren per-prosess; OK ved 1 worker, men med 2+ workers blir effektiv grense 2× satt verdi. Tellere nullstilles ved redeploy uansett backend.
- **Ved overskridelse:** `ratelimited_view` returnerer `accounts/ratelimited.html` med HTTP 429.
- **Individuell brukerlåsing:** I tillegg til IP/brukernavn-rate-limit: 5 feil passord → konto låst i 15 minutter (`locked_until`-feltet på `CustomUser`).

### 6.5 Single-session

`_invalidate_other_sessions()` (`accounts/views.py`) kjøres etter vellykket innlogging, passordbytte og MFA-bekreftelse. Den itererer over alle aktive `Session`-objekter, dekoder dem og sletter de som tilhører samme bruker og ikke er den nåværende sesjonen.

Sesjon-invalidering skjer også automatisk ved MFA-bytte og passordbytte.

### 6.6 Sesjonstimeout

- **Default:** 8 timer (`SESSION_COOKIE_AGE = 8 * 60 * 60` i `settings.py`).
- **Dynamisk:** `DynamicSessionTimeoutMiddleware` (`accounts/middleware.py`) leser `session_timeout_hours` fra `AppSetting` ved hver forespørsel og kaller `request.session.set_expiry(hours * 3600)`. Verdien kan justeres av admin (1–24 timer) via `PUT /api/session-timeout/`.
- **Sesjonskritt:** `SESSION_SAVE_EVERY_REQUEST = True` resetter timeren ved hver forespørsel, slik at aktive brukere ikke logges ut.

### 6.7 Passordbytte

- **Tvinget bytte:** `must_change_password=True` satt som standard for nye brukere. `MustChangePasswordMiddleware` omdirigerer alle forespørsler (unntatt passordbytte og logout) til `/accounts/change-password/`.
- **Frivillig bytte:** Brukeren må oppgi nåværende passord (`ChangePasswordForm`), med mindre `must_change_password=True`.
- **Admin-reset:** `user_detail_view` med `action=reset_password` genererer et 12-tegns midlertidig passord, setter `must_change_password=True`, invaliderer alle brukerens sesjoner og viser det midlertidige passordet til adminen.
- **Sesjonssikkerhet:** Etter passordbytte kalles `update_session_auth_hash()` for å beholde nåværende sesjon, og `_invalidate_other_sessions()` for å logge ut alle andre sesjoner.

---

## 7. Sikkerhetslag

### 7.1 Autentisering og brute-force-beskyttelse

- CustomUser med passord-hashing (PBKDF2-HMAC-SHA256; Argon2 er ikke installert i dag).
- Brute-force-lås: 5 feil passord → konto låst i 15 minutter (`locked_until`).
- Dobbel rate-limit: 10 forsøk per brukernavn / 50 forsøk per IP per 5 minutter.
- Nødbryter `RATELIMIT_ENABLE` (env-variabel) for å skru av rate-limiting i nødsituasjoner.

### 7.2 MFA

- TOTP via `django-otp` (`TOTPDevice`).
- 10 engangs backup-koder (`StaticToken`).
- Trust-cookie gyldig i 30 dager, signert med `SECRET_KEY` via `TimestampSigner`.
- Sesjon-invalidering ved passordbytte og MFA-nullstilling.

### 7.3 HTTPS og transportkryptering

- `SECURE_SSL_REDIRECT = not DEBUG`: tvungen HTTPS i produksjon.
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` for korrekt håndtering bak Railway-proxy.
- **Railway** terminerer TLS ved edge og gir automatisk HTTPS.
- **Databasekryptering i transitt:** TLS 1.2+ mellom Django og Postgres (verifiserbar med `python manage.py check_ssl`).

### 7.4 HSTS

Aktiveres kun i produksjon (`not DEBUG`):

```python
SECURE_HSTS_SECONDS = 31536000  # 1 år
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

### 7.5 CSRF

- `CsrfViewMiddleware` er aktivert.
- `CSRF_TRUSTED_ORIGINS` leses fra miljøvariabelen `CSRF_TRUSTED_ORIGINS` (kommaseparert).
- Klienten leser `csrftoken`-cookie og sender som `X-CSRFToken`-header.
- `CSRF_COOKIE_HTTPONLY = True` og `CSRF_COOKIE_SECURE = not DEBUG`.

### 7.6 Sikkerhetsheadere

`SecurityHeadersMiddleware` (`patients/middleware.py`) setter følgende headere på alle responser:

| Header | Verdi |
|---|---|
| `Content-Security-Policy` | Restriktiv policy tilpasset CDN-avhengighetene |
| `Referrer-Policy` | `same-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |

I tillegg settes:

| Innstilling | Verdi | Formål |
|---|---|---|
| `X_FRAME_OPTIONS` | `DENY` | Forhindrer clickjacking via iframes |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | Forhindrer MIME-type-sniffing |
| `SESSION_COOKIE_SECURE` | `not DEBUG` | Sesjonskake kun over HTTPS |
| `SESSION_COOKIE_HTTPONLY` | `True` | Sesjonskake ikke tilgjengelig fra JavaScript |
| `SESSION_COOKIE_SAMESITE` | `Lax` | CSRF-beskyttelse for navigasjon |

### 7.7 Databasesikkerhet

- **At rest:** Railway bruker AES-256-kryptering for Postgres-lagring.
- **I transitt:** TLS 1.2+ mellom Django og Postgres.
- **Verifisering:** `python manage.py check_ssl` kjører `SHOW ssl` og spør `pg_stat_ssl` for å bekrefte at gjeldende tilkobling er kryptert. Støtter `--fail-on-insecure` for å avbryte med exit-kode 1.
- Ingen raw SQL – all databasetilgang via Django ORM.

### 7.8 Passordvalidering

Fire validatorer er aktivert i `settings.py`:
- `UserAttributeSimilarityValidator`
- `MinimumLengthValidator`
- `CommonPasswordValidator`
- `NumericPasswordValidator`

### 7.9 Input/output-sikkerhet

- CSRF-beskyttelse på alle mutasjoner.
- XSS-beskyttelse via auto-escape i templates + manuell escaping i JavaScript: `escapeHtml()`/`_escHtml` i pasientskjemaet (`patients-forms.js`) og arkivvisningen (`patients-stats.js`), og `escHtmlValue()` i statistikk-tabellene.
  - `escHtmlValue()` skiller «ikke satt» (`null`/`undefined`) fra falsy verdier, slik at tallet 0 vises i tabellceller i stedet for å bli tom streng. Det er grunnen til at den finnes ved siden av de to eldre hjelperne.
  - `trustedHtml()` markerer markup koden bygger selv (signifikans-merker i `renderTester`, prosentbjelker i `mkObsTable`). `cellHtml()` slipper klarerte celler gjennom og escaper alt annet, så unntaket blir et bevisst valg per celle.
  - `patients/tests_xss_stats.py` kjører byggerne i node mot HTML-holdige feltverdier, og har i tillegg en statisk vaktpost som krever at hver `${...}` i byggerne er escapet eller står på en gjennomgått unntaksliste med begrunnelse.
- SQL-injection-beskyttelse via Django ORM (ingen raw SQL).
- Ingen path traversal i backup-filnavn – filnavn genereres server-side.
- Generisk feilmelding ved backup-restore (lekker ikke interne detaljer).

### 7.10 Audit

- Hver pasientendring logges på feltnivå (`AuditLog`).
- Innlogging, MFA-hendelser og passordbytte logges som `LoginEvent`.
- Backup-opprettelse, gjenoppretting, nedlasting og sletting logges.

---

## 8. Automatisk backup-system

### 8.1 Oversikt

Systemet tilbyr automatisk, periodisk backup av pasientdata uten behov for en ekstern cron-tjeneste eller separat Railway-service. Backup kjøres in-process via `BackupSchedulerMiddleware`.

### 8.2 BackupConfig (singleton)

`BackupConfig` (pk=1) i `patients`-appen lagrer konfigurasjon for automatisk backup:

- `interval_minutes`: Antall minutter mellom automatiske backuper.
- `last_run_at`: Tidspunkt for siste vellykkede automatiske backup.

Konfigurasjonen kan leses og oppdateres via `GET/PUT /api/backup-config/` (kun `admin`).

### 8.3 Backup-modellen

`Backup`-modellen (se seksjon 4.7) loggfører alle backup-operasjoner med:

- `filename`: Filnavnet (uten sti) til backup-filen lagret på Railway Volume.
- `kind`: Type backup – `manual`, `auto`, `pre_reset` eller `pre_restore`.
- `size_bytes`: Filstørrelse.

### 8.4 BackupSchedulerMiddleware

`patients.middleware.BackupSchedulerMiddleware` kjøres som siste middleware i kjeden og implementerer in-process cron:

1. **Throttle per prosess:** Mellom hver request-syklus venter middlewaren minimum 60 sekunder (per prosess, via en prosess-lokal `threading.Event`). Dette forhindrer unødvendig databasekommunikasjon ved høy trafikk.
2. **Running-lås per prosess:** En prosess-lokal lås (`threading.Lock`) sikrer at kun én bakgrunnstråd per worker-prosess kjører backup om gangen.
3. **Database-lås (multi-worker-safety):** Når backup skal kjøres, hentes `BackupConfig` med `select_for_update(nowait=True)`. Dersom en annen Gunicorn-worker allerede holder låsen, kastes `OperationalError` og backup hoppes over for denne forespørselen. Dette gjør systemet trygt for multi-worker-oppsett selv om 1 worker er anbefalt konfigurasjon.
4. **Bakgrunnstråd:** Backup-logikken kjøres i en `threading.Thread` etter at Django-responsen er returnert til klienten, slik at backupet ikke forsinker brukerens forespørsel.

### 8.5 Hva som inkluderes og ekskluderes

- **`BACKUP_APPS = ['patients']`** – kun pasientdata inkluderes.
- **`BACKUP_EXCLUDE = ['patients.Backup', 'patients.BackupConfig']`** – disse ekskluderes for å unngå selvreferanse ved restore.
- Passord-hasher, audit-logg, sesjoner og `LoginEvent` inkluderes **ikke** i backup.

### 8.6 Restore-semantikk

- Restore rører **kun** pasientdata (modeller i `patients`-appen, ekskludert `Backup` og `BackupConfig`).
- Brukere, audit-logg, sesjoner og LoginEvent-historikk berøres **ikke**.
- Før restore lages automatisk en `pre_restore`-backup av gjeldende tilstand.
- Restore-feil gir generisk feilmelding til bruker (ingen interne detaljer lekkes).

### 8.7 Lagring og retention

- Backup-filer lagres på Railway Volume under `/data/backups`.
- `purge_old_backups` sletter automatisk backup-filer eldre enn **72 timer**. Kjøres som del av backup-syklusen.

---

## 8A. Observability og drift

### 8A.1 Oversikt

Observability-laget er et lett, selvstendig rammeverk for teknisk telemetri. Det skal gi administrator svar på «hvordan har tjenesten det akkurat nå?» uten å logge pasientdata og uten å vedlikeholde ekstra infrastruktur (Prometheus, Grafana, Sentry osv.). Komponentene er:

- `RequestMetricsMiddleware` – samler per-request-telemetri i en in-memory ringbuffer.
- `/portal-admin/server-status/` – HTML-dashbord for administratoren.
- `/portal-admin/server-status/json/` – tilsvarende snapshot i JSON for automatisering og overvåkning.
- `AppSetting`-baserte feature-flags – brytere som admin kan justere uten deploy.

Alle komponenter er isolert til `patients`-appen og har ingen eksterne avhengigheter utover `psutil`.

### 8A.2 RequestMetricsMiddleware

Definert i `patients/middleware.py` som `RequestMetricsMiddleware`. Lagrer en thread-safe ringbuffer med de siste 500 requestene. Hver sample inneholder:

| Felt | Beskrivelse |
|---|---|
| `path` | Request-path (f.eks. `/api/patients/`) – ikke query string |
| `method` | HTTP-metode |
| `status` | HTTP-statuskoden responsen hadde |
| `duration_ms` | Målt varighet i millisekunder (`time.perf_counter`) |
| `ts` | Tidsstempel (Unix-epoch) |

**Viktig:** Middlewaren logger **ingen** request body, query-parametre, pasient-ID eller brukerinformasjon. Den er bevisst en driftslogger for teknisk telemetri og skiller seg fra `AuditLog` (som logger pasientendringer på feltnivå).

**Ringbufferen** er implementert som en `collections.deque(maxlen=500)` beskyttet av en `threading.Lock`. Når bufferen er full, forkastes den eldste samplet automatisk. Ingenting persisteres til disk – bufferen nullstilles ved prosess-restart (og dermed ved hver Railway-deploy).

**Aggregater** beregnes on-demand når dashbordet spør etter dem:

- **1-minutts-vindu:** Alle samples der `ts >= now - 60`. Returnerer p50, p95, max for `duration_ms`, samt antall samples og antall `status >= 500` (`errors`).
- **5-minutters-vindu:** Som over, men `ts >= now - 300`.

Fordi bufferen har 500 samples, vil 5-minutters-vinduet holde en realistisk oversikt også ved høy trafikk; ved høyere volum enn 500 requests per 5 minutter må kapasiteten økes.

### 8A.3 Admin server-status-dashbord

**URL:** `/portal-admin/server-status/`

**Tilgang:** Kun `admin`-rolle. Andre roller får 403.

Dashbordet viser følgende paneler:

| Panel | Innhold | Kilde |
|---|---|---|
| Requestmetrics | p50 / p95 / max / feil for 1-min og 5-min vindu | `RequestMetricsMiddleware`-ringbufferen |
| RAM-bruk | `memory_mb` for gjeldende prosess | `psutil.Process().memory_info().rss / 1024 / 1024` |
| Aktive sesjoner | Antall ikke-utgåtte `django.contrib.sessions.Session`-rader | DB-spørring |
| Siste backup | Filnavn, størrelse, tidspunkt og type | `Backup`-modellen (siste rad etter `created_at`) |
| Feature-flags | Alle nøkler med prefiks `feature.` og deres verdi | `AppSetting`-tabellen |
| Worker-config | `WEB_WORKERS`, `WEB_THREADS`, `WEB_MAX_REQUESTS` og faktisk prosessantall | Env-variabler og `os.getpid()` |

Dashbordet polles ikke automatisk; brukeren refresher manuelt. Dette er et bevisst valg slik at dashbordet ikke selv bidrar til trafikken det måler.

### 8A.4 JSON-endepunkt

**URL:** `/portal-admin/server-status/json/`

Returnerer nøyaktig samme data som HTML-dashbordet, men i maskinlesbart JSON-format. Tiltenkt bruk:

- Ekstern overvåkning (f.eks. UptimeRobot med nyere JSON-content check, eller en enkel bash-skript-cron).
- Automatiske alarmer basert på p95 / feil-antall.
- Innhenting av snapshot for feilsøking.

Endepunktet krever fortsatt `admin`-rolle og innlogget sesjon – det er **ikke** et åpent metrics-endepunkt.

### 8A.5 Feature-flag-systemet via AppSetting

Feature-flags er lagret som vanlige rader i `AppSetting`-tabellen. Konvensjonen er at nøkler som starter med prefikset `feature.` er flagg. Eksempler:

| Nøkkel | Default | Formål |
|---|---|---|
| `feature.live_stats_enabled` | `'false'` | Planlagt: skal skru live-statistikk-fanen inn/ut uten deploy. Funksjonen er ikke implementert ennå; default holdes på `'false'` for ikke å villede dashbordet. |

Verdiene er alltid tekst (`AppSetting.value` er `TextField`). En praktisk hjelpefunksjon `is_feature_enabled(key, default='false')` i `patients/stats_cache.py` tolker `'true'`/`'false'` case-insensitivt.

**Endring via dashbordet:** `POST /portal-admin/server-status/flag/` med `key=feature.live_stats_enabled&value=false`. Endepunktet krever CSRF-token og `admin`-rolle. Oppdateringen logges i `AuditLog`.

---

## 8B. Stats-cache og ETag/304

### 8B.1 Formål

`/api/stats/` og `/api/full-stats/` gjør betydelig arbeid (aggregeringer og i tilfellet `full_stats_view` også scipy-tester). Når flere brukere har statistikkfanen åpen samtidig, vil de samme beregningene kjøres for hver klient. Stats-cache-modulen reduserer dette til én beregning per TTL-vindu og tilbyr i tillegg `If-None-Match`/304 på klientsiden slik at nettleseren slipper å laste ned ubrukt respons-body.

### 8B.2 Modulen `patients/stats_cache.py`

Hovedkomponenten er dekoratøren:

```python
@cached_stats_response(ttl=15, key_prefix="statscache:basic")
def stats_view(request):
    ...

@cached_stats_response(ttl=60, key_prefix="statscache:full")
def full_stats_view(request):
    ...
```

Dekoratøren håndterer både server-side caching og client-side ETag-validering.

**Cache-nøkkelen** bygges fra `key_prefix`, aktivt år (fra `AppSetting['active_year']`) og rollen som ber om dataene. På den måten får ulike år og ulike rolle-visninger sin egen cache-linje.

**Cache-prefiks:** Alle nøkler starter med `statscache:` slik at de er enkle å identifisere og eventuelt flushe.

### 8B.3 SHA-256 weak ETag

Når et svar beregnes eller hentes fra cachen, genereres en ETag som følger:

```python
body = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
digest = hashlib.sha256(body).hexdigest()
etag = f'W/"{digest}"'
```

**`sort_keys=True`** er kritisk: Python-dictionary-iterasjonsrekkefølge kan variere mellom oppstart av prosesser, noe som ville ha gjort ETagen ustabil og dermed værdiløs som cache-valideringsmekanisme. Med `sort_keys` er digesten deterministisk for et gitt datasett.

**Weak ETag (`W/`-prefiks):** Signalet «semantically equivalent», som er riktig her – vi tillater at to teknisk ulike JSON-representasjoner (samme data i samme rekkefølge) regnes som like.

### 8B.4 Cache-TTL

| View | TTL | Begrunnelse |
|---|---|---|
| `stats_view` (`/api/stats/`) | 15 sekunder | Basisstatistikk endrer seg hyppig under aktiv vakt; 15 s gir god ferskhet og fanger likevel polling-bursten fra 10–20 samtidige brukere |
| `full_stats_view` (`/api/full-stats/`) | 60 sekunder | Full statistikk (scipy-tester) er vesentlig tyngre; 60 s er et akseptabelt kompromiss mellom ferskhet og CPU-kostnad |

### 8B.5 If-None-Match → 304-flyt

1. Klienten sender GET uten `If-None-Match`. Serveren beregner svaret, legger det i cachen med TTL og returnerer `200 OK` med `ETag: W/"<sha256>"`.
2. Klienten lagrer ETagen og sender `If-None-Match: W/"<sha256>"` ved neste kall.
3. Serveren slår opp i cachen. Hvis cache-treff og ETagen er lik → `304 Not Modified` uten body.
4. Ved cache-miss beregnes ny ETag; dersom den er lik klientens, svarer serveren fortsatt `304`. Ellers `200 OK` med ny body og ny ETag-header.
5. `Cache-Control: private, must-revalidate` settes for å hindre at proxy-er cacher responsen på tvers av brukere, men tillate klientens egen validering.

Resultat: når dataene er uendret, returneres et tomt 304-svar i stedet for full JSON – betydelig reduksjon i båndbredde ved polling.

---

## 8C. Cache-backend (LocMemCache vs Redis)

Django's `CACHES`-konfigurasjon i `myproject/settings.py` velger backend ved oppstart basert på `REDIS_URL`-miljøvariabelen:

```python
REDIS_URL = os.environ.get('REDIS_URL', '').strip()
if REDIS_URL:
    CACHES = {'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'pasientregistrering',
        'TIMEOUT': 300,
    }}
    CACHE_BACKEND_NAME = 'redis'
else:
    CACHES = {'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'pasientregistrering-ratelimit',
        'OPTIONS': {
            'MAX_ENTRIES': 200,
            'CULL_FREQUENCY': 4,
        },
    }}
    CACHE_BACKEND_NAME = 'locmem'
```

### 8C.1 Når brukes hva

| Backend | Brukes når | Egenskaper |
|---|---|---|
| `LocMemCache` | Lokal utvikling, tester, og når `REDIS_URL` ikke er satt | Per-prosess (in-memory). Raskeste mulig for 1 worker. Kan ikke deles mellom workers. Tellere nullstilles ved restart. |
| `RedisCache` (Django innebygd, krever `redis>=5.0`) | Prod med 2+ workers. `REDIS_URL` settes automatisk av Railway når en Redis-tjeneste legges til prosjektet. | Delt mellom workers. Tregere enn LocMemCache (~1–2 ms/op vs <0.1 ms), men gir korrekt rate-limiting og delt stats-cache. |

### 8C.2 Hvilke komponenter bruker cache

1. **`django-ratelimit`** — lagrer tellere per IP og brukernavn. Med LocMemCache + 2 workers blir grensen effektivt doblet (hver worker har sin egen teller).
2. **`patients/stats_cache.py`** — cacher `/api/stats/` (15s TTL) og `/api/full-stats/` (60s TTL). Med LocMemCache + 2 workers regnes statistikken to ganger.
3. **Cache-helsesjekk i `patients/admin_status.py`** — `_get_cache_health()` skriver, leser og sletter en probe-nøkkel for å verifisere at backenden funker. Resultatet vises på admin-dashbordet (Cache-backend-kort).
4. **RequestMetrics i `patients/middleware.py`** — Bruker Redis direkte (via `redis`-biblioteket, ikke `cache.set/get`-API-et) til å aggregere request-metrikker på tvers av workere når `REDIS_URL` er satt. I lavkostnad-modus (LocMem) brukes lokal deque per prosess. Se 8E for detaljer.

### 8C.3 Failsafe ved Redis-nedetid

Django's innebygde RedisCache (innført i Django 4.0) har **ikke** en innebygd `IGNORE_EXCEPTIONS`-option slik tredjepartspakken `django-redis` har. Det betyr at hvis Redis-tjenesten er helt nede, kan første cache-operasjon kaste en `ConnectionError` opp i request-stack-en.

Delvis avhjelping:

- **`django-ratelimit`** failopener av seg selv når cache-backenden kaster — requesten slippes gjennom uten å telles. Dette er innebygd i biblioteket.
- **Stats-cache** (`patients/stats_cache.py`) er pakket inn i try/except slik at endepunktet går tilbake til å regne statistikken direkte ved cache-feil. Både `cache.get`, `cache.set` og `cache.delete` er beskyttet, så feil i én operasjon stopper aldri request-flyten.
- **Brukerlåsing** (5 feil passord → `locked_until`) går mot DB og er IKKE påvirket av cache-feil.
- **Cache-helsesjekken** (`_get_cache_health()` i `patients/admin_status.py`) fanger alle exceptions og rapporterer `healthy=false` med `error`-streng på admin-dashbordet i stedet for å la feilen propagere.

Resultat ved Redis-utfall: noen få requests kan få 500-feil under selve utfallet, men sikkerhets-mekanismene som går mot DB står. Railway restarter Redis-tjenesten automatisk hvis den krasjer, og fallback til LocMemCache kan tvinges fram ved å fjerne `REDIS_URL`-variabelen (krever redeploy så Django re-evaluerer `CACHES`-blokken).

#### Sanering av credentials i feilmeldinger (`_scrub_secrets`)

Når en cache-operasjon mot Redis feiler, kan `redis-py`-biblioteket inkludere selve forbindelsesstrengen i `repr(exc)`. På Railway inneholder denne strengen Redis-passordet (`redis://default:<passord>@host:port`). For å unngå at passordet havner i HTTP-respons fra `/api/admin-status/` eller i logger, kjøres alle feilstrenger gjennom helperen `_scrub_secrets()`:

```python
# patients/admin_status.py
def _scrub_secrets(text: str) -> str:
    """Fjerner credentials fra strenger som kan inneholde URL-er."""
    # Erstatter user:password@ med ***:***@ i alle URL-aktige mønstre
    return re.sub(r'(\w+://)([^:@/\s]+):([^@/\s]+)@', r'\1***:***@', text)
```

Funksjonen kalles på `str(exc)` før verdien legges i admin-status-responsen. Dekkende mønstre:
- `redis://default:hemmelig@redis.railway.internal:6379` → `redis://***:***@redis.railway.internal:6379`
- `rediss://`, `postgres://`, `https://` osv. — alle URL-skjema med `user:password@` saneres likt.

Dette er en defensiv layer; ingen kjent bug i `redis-py` lekker passordet i exceptions per nå, men siden admin-statusen er skreddersydd for utvikler-/lead-eksponering ville et eventuelt fremtidig leak uansett bli fanget.

### 8C.4 Diagnostikk

`settings.CACHE_BACKEND_NAME` (`'redis'` eller `'locmem'`) er tilgjengelig i hele kodebasen og brukes av admin-dashbordet for å vise hvilken backend som er aktiv. Cache-helsesjekken (`_get_cache_health()`) måler også round-trip-latency (write+read+delete) og rapporterer det i ms.

### 8C.5 Tester

`myproject/tests_cache_config.py` (16 tester) verifiserer:
- Default-backend er LocMemCache uten `REDIS_URL` (ingen `redis>=5.0`-import kreves lokalt)
- Settings-modulen velger Redis-backend når `REDIS_URL` settes (testet via `importlib.reload`)
- Tom og whitespace-only `REDIS_URL` faller tilbake til LocMemCache
- `KEY_PREFIX='pasientregistrering'` og `TIMEOUT=300` er satt korrekt på Redis-backenden
- `_get_cache_health()` rapporterer `healthy=True` ved normal drift og `healthy=False` ved kastet exception
- `_scrub_secrets()` fjerner credentials fra `redis://`, `rediss://`, `postgres://` og `https://` URL-er (5 dedikerte tester)
- `stats_cache.get_or_set()` og `delete_pattern()` failsafer ved cache-exceptions (regner statistikk direkte uten å kaste)

---

## 8D. Gunicorn workers og threads

Deploy-konfigurasjonen styres av tre miljøvariabler i `Procfile` (se også seksjon 12):

```
web: gunicorn myproject.wsgi --workers ${WEB_WORKERS:-1} --threads ${WEB_THREADS:-4} --bind 0.0.0.0:$PORT --timeout 60 --max-requests ${WEB_MAX_REQUESTS:-1000} --max-requests-jitter 50
```

### 8D.1 Workers vs threads — prinsippforskjell

| Begrep | Hva det er | Konsekvens |
|---|---|---|
| **Worker** | Egen OS-prosess. Egen Python-tolk, egen minne-heap. | Skalerer CPU-bundne oppgaver. Kan IKKE dele in-memory state (LocMemCache, RequestMetrics-ringbuffer). |
| **Thread** | OS-tråd innenfor samme worker. Deler minne med andre tråder i samme worker. | Skalerer I/O-bundne oppgaver (DB-, cache-, http-kall). Begrenset av Python's GIL for ren CPU. |

Django-views i denne appen er tunge på I/O (Postgres-spørringer + cache + sjeldne ekstern-kall). Tråder gir derfor reell parallellitet selv med GIL.

### 8D.2 Anbefalte konfigurasjoner

| Scenario | `WEB_WORKERS` | `WEB_THREADS` | Forutsetninger |
|---|---|---|---|
| **Lokal utvikling** | 1 | 4 (default) | LocMemCache. Single-prosess gjør `print`/`pdb` enkelt å bruke. |
| **Liten vakt (≤5 brukere samtidig)** | 1 | 4 (default) | LocMemCache OK. Hobby-plan på Railway. |
| **Mellomstor vakt (5–15 brukere)** | 2 | 4 | **Krever Redis** (`REDIS_URL` satt). Hobby-plan tilstrekkelig. |
| **Stor vakt (15–20+ brukere)** | 2–3 | 4–6 | **Krever Redis**. Vurder Railway Pro-plan for høyere RAM-grense. |

Trådantall over 6 gir lite ekstra gevinst med dagens spørrings-mønster og kan føre til DB-connection-press (hver tråd åpner egen Postgres-connection ved samtidige requests).

### 8D.3 Hvorfor Redis er en harde forutsetning ved 2+ workers

Delt state mellom workers er nødvendig for tre ting:

1. **Rate-limiting (`django-ratelimit`)** — Uten Redis vil hver worker ha sine egne tellere. Med 2 workers blir effektiv grense per IP/bruker fordoblet, med 3 workers tredoblet osv. Kritisk for innloggings-endepunktet (default `5/m`).
2. **Stats-cache (`patients/stats_cache.py`)** — Uten Redis vil hver worker regne statistikken sin egen gang og produsere ulike ETag-er. Klienter får da ikke 304-respons konsistent, og DB-belastningen øker proporsjonalt med worker-antall.
3. **Konsistens i admin-dashbord** — Cache-backend-kortet leser `CACHE_BACKEND_NAME` fra settings og forventer at alle workers ser samme tilstand.

### 8D.4 RequestMetrics ved flere workers (løst via Redis-aggregering)

Tidligere lagret `RequestMetricsMiddleware` siste 500 requestmålinger i en in-memory ringbuffer per prosess, slik at admin-dashbordet kun viste målingene fra én worker av gangen. Dette er nå utbedret — se 8E for hvordan Redis-aggregering gir korrekt cluster-wide statistikk i vakt-modus, og hvordan lokal deque automatisk brukes som fallback i lavkostnad-modus.

### 8D.5 `--max-requests` og `--max-requests-jitter`

Gunicorn-workere restartes etter `WEB_MAX_REQUESTS` requests (default 1000) pluss et jitter-tilskudd på 0–50 requests. Dette beskytter mot gradvis minnelekkasje (i Django-extensjoner eller egen kode) ved å tvinge gjenoppstart med jevne mellomrom. Jitter forhindrer at alle workers restarter samtidig.

### 8D.6 Verifisering på admin-dashbord

Admin-dashbordet (`/portal-admin/server-status/`) viser i Worker-config-kortet:
- `WEB_WORKERS` og `WEB_THREADS` (env-verdier eller defaults)
- Antall faktiske Gunicorn-prosesser observert via `psutil`
- PID for nåværende worker

Hvis env-verdiene avviker fra observert prosessantall, har deployen ikke restartet etter endring — trigg en ny deploy via Railway eller `git commit --allow-empty -m "redeploy" && git push`.

---

## 8E. Multi-worker-design og lavkostnad-modus

Kodebasen kjøres i to ulike driftsmodus styrt av én env-variabel: `REDIS_URL`. Å slå av/på Redis krever ingen kodeændringer — alt skifter automatisk basert på om variabelen er satt.

### 8E.1 Driftsmodus

| Modus | `REDIS_URL` | `WEB_WORKERS` | Cache-backend | Når brukes |
|---|---|---|---|---|
| **Lavkostnad-modus** | tom (slettet eller satt til "") | 1 | LocMemCache | Default mellom vakter — lavest mulig løpende kostnad |
| **Vakt-modus** | satt (peker mot Railway Redis-tjenesten) | 2 (kan høynes) | RedisCache | Før og under vakt med flere samtidige brukere |

Umiddelbare endringer ved bytte mellom modusene:

- Cache-bytte: settings re-evalueres ved Django-oppstart (krever redeploy/restart)
- `_redis_is_available()` i `patients/middleware.py` leser `settings.CACHE_BACKEND_NAME` runtime og styrer dermed metrikk-aggregering på hver request
- Admin-dashbordet (`/api/admin-status/`) viser tydelig hvilken backend som er aktiv og om aggregering er live (felter `cache_health.backend` og `metrics_5min.source`)

Prosedyre for bytte mellom modusene er dokumentert i `RUNBOOK_VAKT.md` §4.

### 8E.2 State-mekanismer og deres beskyttelse

| Mekanisme | Hvor i kode | Per-worker eller delt? | Beskyttelse i multi-worker |
|---|---|---|---|
| Django cache (stats, rate-limit) | `settings.CACHES` | Delt via Redis i vakt-modus, per-prosess i lavkostnad | `KEY_PREFIX='pasientregistrering'` isolerer mot andre tjenester på samme Redis |
| Audit thread-local (current user) | `audit/utils.py` | Per-tråd (riktig) | `threading.local()` er semantisk per tråd — hver request får ren kontekst |
| Backup-scheduler `_is_running` | `patients/backup_scheduler.py` | Per-prosess (in-memory bool) | DB-lås (`select_for_update(nowait=True)`) er den ekte beskyttelsen — selv om to workere mener begge "jeg starter backup", er det DB-låsen som faktisk slipper bare én gjennom |
| Request-metrikker (lokal deque) | `patients/middleware._MetricsStore._samples` | Per-prosess (siste 500 samples per worker) | Brukes som fallback. Ved aggregering bidrar hver worker til Redis-listen i tillegg — se 8E.3 |
| Request-metrikker (Redis-liste) | Redis nøkkel `metrics:requests` (KEY_PREFIX prefikset av Django) | Delt | `LTRIM` holder maks 5000 entries; `EXPIRE` rydder hvis listen er ubrukt |
| Sessions | Database (`django.contrib.sessions.backends.db`) | Delt | Postgres som backend — ingen worker-avhengig state |

### 8E.3 Aggregert request-metrikker (FORBEDRINGER #15)

For at admin-dashbordet skal vise riktige tall når 2+ workere kjører parallelt, bruker `_MetricsStore` to lag:

1. **Lokal deque (alltid aktiv)** — Hver `record()`-kall legger en sample (timestamp, path, method, status, duration_ms) i en lokal `deque(maxlen=500)`. O(1)-append, tråd-trygt via `Lock`. Ingen avhengigheter, fungerer offline og i tester.

2. **Redis-liste (når `_redis_is_available()` returnerer True)** — Samme sample serialiseres til JSON med worker-PID lagt til, og pushes på Redis-listen `metrics:requests` via en pipeline:
   ```
   LPUSH  metrics:requests  <json>
   LTRIM  metrics:requests  0  4999
   EXPIRE metrics:requests  3600
   ```
   Pipeline gjør operasjonene atomisk og holder rundtur-latency på ~1 ms.

`snapshot(window_seconds)` velger lese-vei runtime:

- Hvis Redis er aktiv og listen har samples i vinduet: aggregerer på tvers av alle workere. Returnerer `source='redis'` og `unique_workers=<antall ulike PID>`.
- Hvis Redis er av eller listen er tom: leser fra lokal deque. Returnerer `source='local'`. Korrekt, fordi lokal deque inneholder hele bildet i 1-worker-modus.

#### Failsafe

- `_get_redis_client()` bruker `socket_timeout=2` og `socket_connect_timeout=2` slik at en treg/død Redis ikke holder requesten.
- Både `_record_to_redis()` og `_read_from_redis()` har bred `try/except` — ingen Redis-feil skal forplante seg til request-pipeline-en.
- Hvis `redis`-biblioteket av en eller annen grunn ikke er installert (f.eks. lokal venv), returnerer klient-getteren `None` og koden faller stille tilbake til lokal deque.

#### Tester

`patients/tests_admin_status.MetricsRedisAggregeringTests` (8 tester) dekker: "Redis ikke tilgjengelig default", "flag aktiverer aggregering", record-feil-stillhet, snapshot-aggregering med to mockede workere, fallback ved tom Redis-liste, fallback ved `lrange`-exception, og vindu-filtrering. Alle tester kjører mot Mock-klient — ingen ekte Redis kreves.

### 8E.4 Sjekkliste: hvis du legger til ny global state

1. **Skal den deles mellom workere?** → Bruk Django cache-API (`cache.get/set`) eller `redis`-bibliotek direkte hvis du trenger atomic operasjoner som `LPUSH`, `INCR`, `SETNX`.
2. **Er den per-tråd (request-context)?** → Bruk `threading.local()`.
3. **Er per-prosess akseptabelt?** → Dokumenter eksplisitt hvorfor (typisk: cache-prefetch, statistikk som kan tilkjennes per-worker, in-memory deque som backup).
4. **Trenger den koordinering ved samtidige skrivere?** → Foretrekk DB-lås (`select_for_update(nowait=True)`) over `cache.add()`-baserte locks. DB-låsen er håndhevet på storage-laget og overlever cache-utfall.
5. **Trenger den å fungere i både lavkostnad- og vakt-modus?** → Implementer en `_is_available()`-vakt og en sti for hver modus, slik `_MetricsStore` gjør. Failsafe ved Redis-utfall i vakt-modus skal alltid være mulig.

### 8E.5 Diagnostikk

Når du åpner admin-dashbordet (`/portal-admin/server-status/`):

- **Cache-backend-kortet** viser `redis` eller `locmem` med latency — dette er kilde-modusen.
- **Metrikk-kortene** viser ny `source`-felt: `'redis'` betyr aggregering på tvers av alle workere, `'local'` betyr bare denne workeren (ev. fordi Redis er tom enda).
- **`unique_workers`** viser antall ulike PID-er som har bidratt med samples i vinduet — et tall som er høyere enn 1 bekrefter at aggregering er live og at alle workere skriver.

Hvis `cache_health.backend == 'redis'` men `metrics_5min.source == 'local'` over flere refreshes mens det er trafikk: sjekk om Redis-listen blir ryddet ufrivillig, eller om `_record_to_redis()` feiler stille (sjekk Railway-logs for typiske `redis.exceptions.*`-meldinger).

---

## 9. Middleware-stakken

Rekkefølgen i `MIDDLEWARE`-listen i `settings.py` er kritisk. Under vises rekkefølgen og formålet med hvert ledd:

| Rekkefølge | Middleware | Formål |
|---|---|---|
| 1 | `django.middleware.security.SecurityMiddleware` | HTTPS-redirect, HSTS, nosniff |
| 2 | `core.middleware.MemoryLoggingMiddleware` | Logger RSS-minne og responstid for requests >200ms eller >1MB delta |
| 3 | `whitenoise.middleware.WhiteNoiseMiddleware` | Serverer statiske filer direkte |
| 4 | `django.contrib.sessions.middleware.SessionMiddleware` | Sesjonshåndtering |
| 5 | `django.middleware.common.CommonMiddleware` | URL-normalisering (trailing slash) |
| 6 | `django.middleware.csrf.CsrfViewMiddleware` | CSRF-beskyttelse |
| 7 | `django.contrib.auth.middleware.AuthenticationMiddleware` | Setter `request.user` |
| 8 | `django_otp.middleware.OTPMiddleware` | Sjekker OTP-verifisering |
| 9 | `django.contrib.messages.middleware.MessageMiddleware` | Flash-meldinger |
| 10 | `django.middleware.clickjacking.XFrameOptionsMiddleware` | X-Frame-Options |
| 11 | `audit.middleware.RequestAuditMiddleware` | Lagrer request i thread-local for audit-signaler |
| 12 | `accounts.middleware.MustChangePasswordMiddleware` | Tvangsomdirigering ved krav om passordbytte |
| 13 | `accounts.middleware.DynamicSessionTimeoutMiddleware` | Dynamisk sesjonslevetid fra AppSetting |
| 14 | `patients.middleware.BackupSchedulerMiddleware` | In-process cron for automatisk backup |
| 15 | `patients.middleware.SecurityHeadersMiddleware` | CSP, Referrer-Policy, Permissions-Policy |
| 16 | `patients.middleware.RequestMetricsMiddleware` | Observability: ringbuffer med siste 500 requestmålinger (p50/p95/max/errors) |

`MemoryLoggingMiddleware` plasseres tidlig (etter SecurityMiddleware, før WhiteNoise) slik at den måler hele request inkludert statisk-fil-servering. `BackupSchedulerMiddleware` plasseres nær slutten slik at request allerede er ferdig behandlet når backup startes i bakgrunnstråd. `SecurityHeadersMiddleware` plasseres like før `RequestMetricsMiddleware` slik at sikkerhetsheadere settes på alle responser. `RequestMetricsMiddleware` plasseres sist slik at den måler den endelige responsen med alle headere inkludert.

---

## 10. Frontend

### 10.1 Arkitektur

Frontend er en SPA-lignende enkeltside-applikasjon i vanlig JavaScript (ingen React, Vue eller Angular). Siden rendres av Django-templaten `templates/patients/index.html`, som laster fire moduler fra `static/js/`:

| Modul | Ansvar |
|---|---|
| `patients-utils.js` | CSRF-fetch, `withSubmitGuard`, escaping-hjelpere, delt tilstand |
| `patients-table.js` | Tabulator-grid og tavlevisning |
| `patients-forms.js` | Registrerings- og redigeringsskjema |
| `patients-stats.js` | Statistikkfanen og arkivvisning |

Alle fire lastes ubetinget — det er ingen bundler og ingen betinget lasting. `patients-stats.js` er større enn de tre andre til sammen og brukes kun av roller med statistikktilgang; se F7 i `docs/FORBEDRINGER_2026-08.md`.

Monolitten `static/js/script.js` ble delt opp i disse fire i mai 2026 og slettet 13. aug. 2026 (N9). Referanser til den i eldre dokumenter er historiske.

**JS-testing:** det finnes ingen JS-testrunner. `patients/js_test_utils.py` klipper ut enkeltfunksjoner og kjører dem i node med stubbet miljø. Brukes av `patients/tests_xss_stats.py` (escaping) og `DoubleClickGuardTests` (dobbeltklikk-vernet). Testene hoppes over hvis node ikke finnes.

Brukerens rolle (`window.USER_ROLE`) injiseres i templaten og leses av JavaScript for å styre elementsynlighet via CSS-klasser.

### 10.2 Navigasjon og faner

Siden har tre faner:
- **Tabelloversikt** – Tabulator-grid med pasientliste og filtre
- **Tavle** – Kanban-lignende oversikt over aktive pasienter
- **Statistikk** – Diagrammer basert på `/api/stats/` og `/api/full-stats/` (kun synlig for `admin`, `lead`, `lead_view`)
- **Innstillinger** – Arrangementsnavn, behandlere, sesjonstimeout, arkivliste, backup-administrasjon (synlighet avhenger av rolle)

Fanenavigasjonen er implementert med `data-tab`-attributter og delegert event-lytting (ingen URLer endres).

I `templates/base.html` er det i tillegg to nav-lenker som kun vises for `admin`:

- **Server-status** – åpner `/portal-admin/server-status/` i samme fane.
- **Django-admin** – åpner `/admin/` i ny fane (`target="_blank"`), primaert for feilsøking og direkte tilgang til Django standard admin.

Lenkene er betinget av `USER_ROLE == 'admin'` i templaten og er ikke synlige i DOMen for andre roller.

### 10.3 Auto-refresh

Siden polls automatisk hvert 30. sekund for å holde pasientlisten og behandlerlisten oppdatert:

- `startRefreshInterval()` starter `setInterval(doAutoRefresh, 30000)`.
- Polling pauses automatisk når fanen er skjult (`document.visibilitychange`-hendelse + `document.hidden`-sjekk).
- Ved synlig igjen: umiddelbar oppdatering (`doAutoRefresh()`) etterfulgt av ny start av intervalltimer.

### 10.4 ETag-støtte for førstehjelper-listen

`loadForstehjelpere()` i `patients-stats.js` bruker `If-None-Match`-headeren med en lagret ETag. Serveren beregner ETag som SHA-256-hash av førstehjelper-listens innhold og returnerer 304 Not Modified hvis listen er uendret. Dette reduserer unødvendig nettverkstrafikk ved polling.

### 10.5 CSRF i API-kall

`apiFetch(url, options)` i `patients-utils.js` er en wrapper rundt `fetch()` som automatisk legger til `X-CSRFToken`-header for `POST`, `PUT`, `PATCH` og `DELETE`. Token leses fra `csrftoken`-cookie, med fallback til et skjult `{% csrf_token %}`-input.

### 10.6 Datahåndtering

- **Forstehjelpere** lastes ved oppstart og ved hver auto-refresh. Inaktive forstehjelpere filtreres fra dropdown-menyer, men vises for pasienter som allerede har dem.
- **Pasienter** lastes fra `/api/patients/`. Filtrering gjøres klientside mot det fullstendige datasettet (`allPatients`-array) for øyeblikkelig respons uten ny server-forespørsel.
- **Statistikk** lastes ved bytte til statistikk-fanen via `/api/full-stats/`.
- **Innstillinger** lastes via `/api/settings/` og `/api/session-timeout/`.

---

## 11. Offline-modus

Offline-modus gir mulighet til å kjøre systemet lokalt uten tilgang til Railway-produksjonsmiljøet, f.eks. ved nettverksutfall under et arrangement.

### 11.1 Oppsett

- **Egen database:** `offline.sqlite3` i prosjektmappen – separat fra produksjons-Postgres.
- **Egen konfigurasjonsfil:** `.env.offline` – inneholder `DATABASE_URL=sqlite:///offline.sqlite3` og lokale innstillinger. En eksempelfil finnes som `.env.offline.example` i repoet.
- **Oppstartsskript:** `start_offline.bat` (Windows) starter Django med `.env.offline`.

### 11.2 Brukerprovisjonering

`python manage.py create_offline_users` (fra `accounts/management/commands/`) oppretter forhåndsdefinerte offline-brukere:
- `admin-offline` (admin-rolle)
- `vakt-offline` (read_write-rolle)

Passordene lagres i `OFFLINE_PASSORD.md` lokalt – filen er ikke i git (`.gitignore`).

### 11.3 Tilbakesynkronisering til produksjon

Etter at nettverkstilgangen er gjenopprettet, importeres data fra offline-databasen til produksjon:

```bash
python manage.py import_offline_data
```

Kommandoen (`patients/management/commands/import_offline_data.py`) leser pasienter fra `offline.sqlite3` og skriver dem til produksjons-Postgres. Duplikathåndtering (basert på `pasientnummer`) er innebygd.

---

## 12. Deploy

Full steg-for-steg-guide for Railway-deploy finnes i `DEPLOY_GUIDE.md`. Denne seksjonen dokumenterer kritiske tekniske detaljer.

### 12.1 Deploy-arkitektur på Railway

| Tjeneste | Type | Formål |
|---|---|---|
| `web` | GitHub deploy | Django/Gunicorn-applikasjon |
| `Postgres` | Railway-addon | Produksjonsdatabase |
| `backup` (Volume) | Railway Volume mountet på `/data` | Lagring av backup-filer under `/data/backups` |

Det finnes **ingen separat backup-service** – automatisk backup håndteres in-process via `BackupSchedulerMiddleware`.

### 12.2 Procfile og start-kommandoer

`Procfile` (prosjektrot):

```
release: python manage.py migrate --noinput && python manage.py createcachetable && python manage.py collectstatic --noinput
web: gunicorn myproject.wsgi --workers ${WEB_WORKERS:-1} --threads ${WEB_THREADS:-4} --bind 0.0.0.0:$PORT --timeout 60 --max-requests ${WEB_MAX_REQUESTS:-1000} --max-requests-jitter 50
```

- `release` kjøres av Railway før hver ny deploy: oppdaterer databaseskjema, oppretter cache-tabell (nødvendig for `django-ratelimit`), samler statiske filer.
- `web` starter Gunicorn med parametriserte verdier. Defaulten er fortsatt 1 worker og 4 tråder for at `LocMemCache`-rate-limit-tellere skal fungere korrekt (se seksjon 15.1).
- `--max-requests ${WEB_MAX_REQUESTS:-1000}` gjør at hver worker resirkuleres etter angitt antall forespørsler. Procfile-fallback er 1000, men Railway-variabelen `WEB_MAX_REQUESTS` kan overstyre dette (se §12.3). `--max-requests-jitter 50` forhindrer at alle workers restarter samtidig. Beskytter mot gradvis minnefragmentering fra tredjepartsbiblioteker.
- `--timeout 60` avbryter en request som tar mer enn 60 sekunder og resirkulerer workeren.
- `WEB_WORKERS`, `WEB_THREADS` og `WEB_MAX_REQUESTS` er valgfrie miljøvariabler – se seksjon 12.3.

### 12.3 Viktige miljøvariabler

| Variabel | Påkrevd | Beskrivelse |
|---|---|---|
| `SECRET_KEY` | Ja | Django secret key. Generer med `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Aldri gjenbruk dev-nøkkel. |
| `DATABASE_URL` | Ja (prod) | PostgreSQL connection string. Settes automatisk av Railway når Postgres-pluginen tilknyttes. |
| `DEBUG` | Ja | Sett `False` i produksjon. `True` kun lokalt. |
| `ALLOWED_HOSTS` | Ja | Kommaseparert liste over tillatte vertsnavn. Default (uten variabel): `.localhost,127.0.0.1`. Eksempel prod: `ditt-domene.up.railway.app`. |
| `CSRF_TRUSTED_ORIGINS` | Ja | Kommaseparert liste over tillatte CSRF-opprinnelser. Eksempel: `https://ditt-prosjekt.up.railway.app` |
| `BACKUP_DIR` | Anbefalt | Sti til backup-mappe. Eksempel: `/data/backups` (Railway Volume). |
| `RATELIMIT_ENABLE` | Anbefalt | `true` for å aktivere rate-limiting (default). Sett `false` som nødbryter. |
| `DJANGO_SUPERUSER_USERNAME` | Valgfri | For `create_superuser`-kommando ved oppstart. |
| `DJANGO_SUPERUSER_PASSWORD` | Valgfri | For `create_superuser`-kommando ved oppstart. |
| `DJANGO_SETTINGS_MODULE` | Anbefalt | `myproject.settings` |
| `WEB_WORKERS` | Valgfri | Antall Gunicorn-workers. Default `1`. Øk kun hvis LocMemCache byttes ut med Redis/Memcached (ellers spaltes rate-limit-tellerne per worker). |
| `WEB_THREADS` | Valgfri | Antall tråder per worker. Default `4`. Øk hvis I/O-profilen tilsier det – tråder deler minne innen samme worker, så rate-limit fungerer. |
| `WEB_MAX_REQUESTS` | Valgfri | Antall requests før en worker resirkuleres. Procfile-fallback: `1000`. Staging-miljøet kjører med `100` (satt i Railway Variables) for hyppigere minnefrigivelse. |

### 12.4 Migrasjoner

Migrasjoner kjøres automatisk av `release`-kommandoen i Procfile. For manuell kjøring:

```bash
python manage.py migrate
python manage.py showmigrations  # Se status
```

**Viktig:** Bruk alltid Django-migrasjoner (`RunPython` eller `migrations.AlterField`). Unngå rå SQL-`ALTER TABLE` direkte mot Postgres, da dette kan komme i konflikt med migrasjonshistorikken.

### 12.5 Opprette første admin ved deploy

```bash
python manage.py create_admin --username admin --password "sikkert-passord"
```

Kommandoen er idempotent: hvis brukeren allerede finnes, hopper den stille over. Kjøres via Railway-dashboardets "Run Command" eller Railway CLI.

### 12.6 Verifisere SSL

```bash
python manage.py check_ssl
```

Viser TLS-versjon, cipher og om tilkoblingen er kryptert. Med `--fail-on-insecure` avsluttes prosessen med exit-kode 1 ved ukryptert tilkobling.

### 12.7 Audit-purge som Cron Job

`purge_old_logs`-kommandoen er ikke integrert i Procfile. Sett opp som Railway Cron Job:

- **Schedule:** `0 3 * * *` (kl. 03:00 UTC daglig)
- **Kommando:** `python manage.py purge_old_logs`

Alternativt via `railway.toml`:

```toml
[[cron]]
name = "purge-audit-logs"
schedule = "0 3 * * *"
command = "python manage.py purge_old_logs"
```

Se `DEPLOY_GUIDE.md` (seksjon "Audit-retensjon") for full oppsett.

---

## 13. Vedlikehold og drift

### 13.1 Backup og gjenoppretting

Applikasjonen har et innebygd backup-system (se seksjon 8) som lagrer JSON-baserte backuper av pasientdata på Railway Volume.

For automatisk backup:
- Konfigurer intervall via `PUT /api/backup-config/`.
- `BackupSchedulerMiddleware` sørger for periodisk kjøring uten ekstern cron.

For manuell backup og gjenoppretting:
- Bruk backup-administrasjons-UI-et i Innstillinger-fanen (kun `admin`).
- API-endepunkter: se seksjon 5.9.

Railway håndterer i tillegg Postgres-backup automatisk:
- **Daglige snapshots:** Beholdes i 7 dager.
- **Gjenoppretting:** Railway-dashboard → PostgreSQL-tjenesten → "Backups".

### 13.2 Audit-retensjon

Standard retensjon er **2 år (730 dager)**. Kommandoen `purge_old_logs` sletter `AuditLog`- og `LoginEvent`-poster eldre enn grensen.

```bash
python manage.py purge_old_logs              # Standard 730 dager
python manage.py purge_old_logs --days 365   # Egendefinert
python manage.py purge_old_logs --dry-run    # Forhåndsvis uten sletting
```

### 13.3 Nullstille MFA for bruker som har mistet telefonen

1. Logg inn som `admin` og naviger til `/portal-admin/brukere/`.
2. Finn brukeren og åpne brukerprofilen.
3. Klikk **"Nullstill MFA"** (knappen vises kun dersom brukeren har MFA aktivt).
4. Bekreft dialogen.

Systemet sletter alle `TOTPDevice`- og `StaticDevice`-objekter, setter `mfa_required=True`, invaliderer alle aktive sesjoner og loggfører `mfa_reset_by_admin` i `LoginEvent`.

Brukeren vil ved neste innlogging bli tvunget gjennom MFA-oppsett på nytt.

### 13.4 Nullstille aktivt år / nytt arrangement

For å slette alle pasientdata i aktivt år og nullstille pasientnummer-telleren:

1. Logg inn som `admin`.
2. Gå til **Innstillinger**-fanen i applikasjonen.
3. Klikk **"Nullstill aktivt år"** og bekreft i dialogen.

Dette kaller `POST /api/reset-active-year/` med `{"confirm": true}`. Systemet lager en `pre_reset`-backup automatisk, og utfører deretter hard-sletting av alle `Patient`-objekter med `year = active_year` og setter `next_patient_nr = 1`.

**Merk:** Hard-sletting er bevisst her siden dette er testdata / forrige sesjon som skal fjernes. Audit-loggen for slettede poster beholdes.

### 13.5 Redeploy og persistens

Ved redeploy på Railway:
- **Databasedata:** Beholdes fullt ut (PostgreSQL er en separat Railway-tjeneste).
- **Backup-filer:** Beholdes på Railway Volume (vedvarer på tvers av deploy).
- **Statiske filer:** Gjenoppbygges av `release`-kommandoen (`collectstatic`).
- **LocMemCache:** Nullstilles (in-process). Rate-limit-tellere og andre cache-verdier tapes. Dette er akseptabelt.
- **Sesjoner:** Beholdes i databasen (`django.contrib.sessions`). Brukere forblir innlogget.
- **MFA-oppsett:** Beholdes (lagret i `TOTPDevice`-tabellen i PostgreSQL).
- **Migrasjoner:** Kjøres automatisk av `release`-kommandoen.

---

## 14. Testing

### 14.1 Kjøre tester

```bash
python manage.py test          # Alle tester
python manage.py test patients accounts audit -v 2  # Med verbose output
```

### 14.2 Testantall og fordeling

Totalt **178 tester** fordelt på følgende filer (145 opprinnelige + 19 admin server-status + 14 stats-cache/ETag):

| Fil / område | Antall tester | Dekker |
|---|---|---|
| `accounts/tests.py` + `accounts/tests_mfa.py` | 22 | Auth, MFA-oppsett, MFA-verifisering, backup-koder, trust-cookie, sesjon-invalidering, rate-limit |
| `patients/tests.py` | 58 | Filter, tidsstempling, behandler-FK, årsarkiv, tilgangskontroll, obs-stempling, utskrevet-stempling, lead_view, reset aktivt år |
| `patients/tests_backup.py` | 18 | Backup-opprettelse, gjenoppretting, tilgangskontroll, purge, pre_reset/pre_restore |
| `patients/tests_scheduler.py` | 8 | In-process scheduler, throttle, database-lås |
| `patients/tests_offline.py` | 34 | SQLite-isolasjon, create_offline_users, import_offline_data |
| `patients/tests_security_headers.py` | 5 | CSP, Referrer-Policy, Permissions-Policy |
| `patients/tests_server_status.py` | 19 | Admin server-status: tilgangskontroll (admin vs. andre roller), metrics-endepunkt, JSON-endepunkt, feature-flag-POST (CSRF + admin), RAM-rapportering, sesjonstelling |
| `patients/tests_stats_cache.py` | 14 | Stats-cache: TTL (15s/60s), cache-nøkkel per år, SHA-256 ETag-stabilitet, `If-None-Match` → 304, cache-bypass, `sort_keys` på JSON-serialisering, feature-flag av/på |

### 14.3 Testdekning – sentrale testklasser

| Testklasse | Hva testes |
|---|---|
| `FilterTests` | `apply_list_filter` – farge-filtrering utelukker utskrevne pasienter korrekt |
| `PabegyntTests` | `stamp_pabegynt_if_needed` – automatisk tidsstempel ved behandlingsstart |
| `ObsStampTests` | `stamp_obs_times_if_needed` – inn/ut-obspost-stempling ved plasseringsendring |
| `UtskrevetStampTests` | `stamp_utskrevet_if_needed` – autostempel ved utskriving |
| `ForsthjelperTests` | FK-integritet, `PROTECT`, `__str__` |
| `YearArchiveTests` | Arkivering og mulighet for å arbeide med separate år |
| `AccessControlTests` | Rollebasert tilgangsstyring på alle API-endepunkter |
| `LeadViewTests` | `lead_view`-rolle – kan lese statistikk, men ikke skrive |
| `ResetTests` | Nullstill aktivt år krever bekreftelse og `admin`-rolle |
| `MFASetupFlowTests` | Tvunget MFA-oppsett for `admin`- og `lead`-brukere ved første innlogging |
| `MFAVerifyTests` | TOTP-verifisering, backup-koder, feil kode |
| `MFATrustCookieTests` | Trust-cookie settes, valideres og avvises korrekt |
| `MFAAdminResetTests` | Admin-nullstilling av MFA |
| `SessionInvalidationOnPasswordChangeTests` | Andre sesjoner slettes ved passordbytte |
| `BackupCreateTests` | Manuell og automatisk backup-opprettelse |
| `BackupRestoreTests` | Gjenoppretting, pre_restore-snapshot, selvreferanse-ekskludering |
| `SchedulerThrottleTests` | 60-sekunders throttle per prosess |
| `SchedulerLockTests` | Database-lås forhindrer parallell backup på tvers av workers |
| `OfflineIsolationTests` | Offline SQLite-db er isolert fra prod |
| `ImportOfflineDataTests` | import_offline_data-kommandoen skriver korrekt til prod-DB |

---

## 15. Kjente begrensninger og fremtidig arbeid

### 15.1 LocMemCache og rate-limiting (LØST når Redis er aktivert)

`LocMemCache` er en in-process cache. Med Procfile-konfigurasjonen `WEB_WORKERS=1` er dette uproblematisk. Dersom antall Gunicorn-workers økes til 2 eller mer uten Redis, vil rate-limit-tellere ikke deles mellom workers, og effektiv grense per IP vil multipliseres med antall workers.

**Løst i prod april 2026:** Redis-tjenesten i Railway-prosjektet eksponerer `REDIS_URL` som settes automatisk på web-tjenesten via Reference-variabel. Da velger `settings.py` `RedisCache`-backend, og rate-limit + stats-cache deles på tvers av workers. Se seksjon 8C og 8D.

Fallback gjelder fortsatt for lokal utvikling og hvis Redis-tjenesten fjernes fra Railway-prosjektet.

### 15.2 Ingen WebSocket

Pasientlisten oppdateres ved polling hvert 30. sekund, ikke via push-meldinger. Ved høy brukeraktivitet (mange samtidige oppdateringer) kan data mellom polls bli utdaterte. WebSocket (f.eks. Django Channels) ville gitt sanntidsoppdateringer, men er per i dag ikke implementert.

### 15.3 Ingen kolonne-kryptering

Pasientdata lagres i klartekst i Postgres. Kryptering i transitt og at-rest-kryptering via Railway er implementert, men felt-for-felt applikasjonslagskryptering (f.eks. `django-encrypted-fields`) er ikke implementert. Vurder dette ved skjerpede datakrav.

### 15.4 Ingen IP-whitelist

Det finnes ingen IP-whitelist eller nettverkssegmentering på applikasjonsnivå. Rate-limiting og MFA er de primære tilgangskontrollmekanismene. Railway-nettverksregler kan brukes for å begrense tilgang til spesifikke IP-adresser på plattformnivå.

### 15.5 Audit-purge kjøres via ekstern cron, ikke via Procfile

`purge_old_logs` er ikke koblet til `Procfile` eller en in-process scheduler. Den kjøres som Railway Cron Job (se seksjon 12.7). Kommandoen håndhever lagringstidene i personvernprotokollen: 730 dager for `AuditLog`/`LoginEvent` og 30 dager for `Notification`. Grensene ligger som defaults i kommandoen, ikke som flagg i cron-jobben, slik at det finnes én sannhet.

Restrisiko: stopper cron-jobben uten at noen oppdager det, vokser loggene ubegrenset. Verifisering er lagt inn i den årlige revisjonssjekklisten (`PERSONVERN_DOKUMENTASJON.md` C.4).

### 15.6 Arkivfunksjonalitet — statistikk beregnes, ikke lagres

Vaktarkivet lagrer radnivå (`ArkivertPasient`) og beregner statistikken på nytt hver gang et arkiv åpnes. Radene vises aldri enkeltvis i grensesnittet.

Planlagt endring: radene kollapser til frosne aggregater etter 24 måneder, se `docs/GDPR_TILTAKSPLAN.md` fase 3.1. Da må også SHA-256-integritetssjekken regnes over aggregatet i stedet for radene.

---

## 16. Feilsøkingsguide

### 16.1 HTTP 500 på innloggingssiden

**Symptom:** Server-feil ved POST til `/accounts/login/`.

**Vanlig årsak:** `django-ratelimit` prøver å bruke en cache-backend som ikke eksisterer, f.eks. `DatabaseCache` uten at `createcachetable` er kjørt.

**Løsning:**
1. Sjekk at `CACHES`-konfigurasjonen bruker `LocMemCache` (standard i `settings.py`).
2. Sjekk Railway-logger for spesifikk feilmelding.
3. Kjør `python manage.py createcachetable` manuelt via Railway Run Command.

### 16.2 Brukere eller data forsvinner

**Symptom:** Pasienter eller brukere som ble opprettet er borte etter redeploy.

**Vanlig årsak:** `DATABASE_URL` peker til SQLite (lokal fil) i stedet for Postgres, eller peker til feil Postgres-instans.

**Løsning:** Verifiser at miljøvariabelen `DATABASE_URL` er satt i Railway-tjenestens Variables-fane og refererer til den tilknyttede PostgreSQL-pluginen.

### 16.3 Migrasjon feiler ved deploy

**Symptom:** `release`-kommandoen feiler med `django.db.utils.ProgrammingError` eller `IntegrityError`.

**Vanlig årsak:**
- Manuell SQL er kjørt direkte mot Postgres og er i konflikt med migrasjonshistorikken.
- Ny migrasjon er avhengig av en annen migrasjon som ikke er merket `[X]`.

**Løsning:**
1. Kjør `python manage.py showmigrations` for å se status.
2. Bruk alltid Django-migrasjoner (`RunPython`) fremfor rå SQL for skjemaendringer.
3. Sjekk at `dependencies`-listen i migrasjoner er korrekt.

### 16.4 MFA-bruker låst ute

**Symptom:** Bruker kan ikke logge inn fordi de har mistet telefonen eller slettet authenticator-appen.

**Løsning:** Følg prosedyren i seksjon 13.3 (admin nullstiller MFA via `/portal-admin/brukere/<pk>/`).

### 16.5 "CSRF verification failed"

**Symptom:** HTTP 403 med "CSRF verification failed" ved POST/PUT/DELETE.

**Vanlig årsak:** `CSRF_TRUSTED_ORIGINS` inneholder ikke Railway-domenet.

**Løsning:** Legg til `https://ditt-prosjekt.up.railway.app` i `CSRF_TRUSTED_ORIGINS`-miljøvariabelen i Railway Variables.

### 16.6 "DisallowedHost at /"

**Symptom:** HTTP 400 med "Invalid HTTP_HOST header".

**Løsning:** Legg til domenet i `ALLOWED_HOSTS`-miljøvariabelen. `.railway.app` dekker alle subdomener. Merk: default uten variabel er `.localhost,127.0.0.1` (ikke lenger `*`).

### 16.7 Rate-limit trigger på riktig innlogging

**Symptom:** Bruker får "For mange forsøk"-side selv med riktig passord.

**Årsak:** IP- eller brukernavn-rate-limit er nådd. Grensene er 50 IP-forsøk / 10 brukernavnforsøk per 5 minutter.

**Løsning:** Vent 5 minutter, eller sett `RATELIMIT_ENABLE=false` midlertidig som nødbryter. Rate-limit-tellere nullstilles ved redeploy (LocMemCache er in-process).

### 16.8 Statiske filer mangler (CSS/JS ikke lastet)

**Symptom:** Siden vises uten styling eller JavaScript-funksjonalitet.

**Løsning:** `collectstatic` kjøres av `release`-kommandoen. Hvis dette feilet, kjør `python manage.py collectstatic --noinput` manuelt via Railway Run Command.

### 16.9 Backup-filer mangler etter redeploy

**Symptom:** Backup-lista er tom etter redeploy.

**Vanlig årsak:** Railway Volume er ikke mountet på `/data`, eller `BACKUP_DIR` peker til feil sti.

**Løsning:** Verifiser at `backup`-volumet er mountet på `/data` i Railway-dashboardet for web-tjenesten, og at `BACKUP_DIR=/data/backups` er satt i miljøvariablene.

---

*Dokumentet beskriver kodebasen slik den var ved siste commit april 2026 (revidert utgave). For deploy-detaljer, se `DEPLOY_GUIDE.md`. For operasjonelle rutiner, se `RUNBOOK_VAKT.md` (seksjon 11 om skalering). For endringer i kodebasen etter denne datoen, start med `git log` og relevante testfiler.*

**Revisjonshistorikk (april 2026):**
- Observability-lag lagt til: `RequestMetricsMiddleware`, `/admin/server-status/`, JSON-endepunkt og feature-flag-POST.
- `AppSetting` brukes nå også som feature-flag-store (`feature.live_stats_enabled`).
- `patients/stats_cache.py` og dekoratøren `cached_stats_response` med SHA-256 weak ETag og If-None-Match/304.
- Gunicorn parametrisert med `WEB_WORKERS`, `WEB_THREADS`, `WEB_MAX_REQUESTS` og `--max-requests-jitter 50`.
- Testantall økt fra 145 til 178.

## Tillegg: Fase 3 — Sanitetsportal (mai 2026)

Pasientregistrering er flyttet til `/pasienter/` og portal-skallet
serveres på `/`. Tre ekstra apper bygger ut admin-funksjonalitet:

### `core` — portal-skall og moduladministrasjon

- `core.modules`: register over alle moduler (slug, navn, ikon,
  permission_flag, is_core). Cachet etter første bygg.
- `core.models.ModuleSettings`: én rad per modul med `enabled`,
  `backup_enabled`, `note`. `ensure_defaults_exist()` kjøres ved
  app-start.
- `core.forms.ModuleSettingsForm`: validerer at kjernemoduler ikke
  kan deaktiveres.
- `core.views`:
  - `portal_dashboard_view` på `/`
  - `profile_view` på `/min-profil/`
  - `module_admin_list_view` / `module_admin_edit_view` på
    `/portal-admin/moduler/[<slug>/]`
  - `audit_log_list_view` / `audit_log_csv_export_view` på
    `/portal-admin/auditlog/[eksport.csv]`

### `accounts` — utvidet med 5 permission-flagg (Fase 3a)

`CustomUser` har nå `kan_redigere_pasienter`, `kan_redigere_vakter`,
`kan_redigere_utstyr`, `kan_se_rapport`, `kan_redigere_beredskap`.
Default `False` for alle nye brukere; eksisterende admins fikk
automatisk `True` via data-migrering i `0007_module_permission_flags`.

`AdminUserEditForm` (Fase 3b) eksponerer alle 5 felt for redigering.
Bulk-aksjoner i `user_list_view` lar admin sette eller fjerne
pasient-flagget på alle ledere/ikke-admins i én operasjon.

### `audit` — `app_label` på AuditLog (Fase 3a)

Hver `AuditLog`-rad får automatisk `app_label` (patients, accounts,
core osv.) basert på `table_name`-prefiks. `pre_save`-signal i
`audit/signals.py` håndterer dette idempotent. Indeks
`(app_label, created_at)` sikrer rask filtrering i admin-loggvisning.

### Revisjonshistorikk Fase 3

- **Fase 1 (april 2026)**: Pasientregistrering på `/pasienter/`,
  arkivering, backup-stack.
- **Fase 2 (april 2026)**: Portal-skall på `/`, modul-register,
  legacy-redirects.
- **Fase 3a (mai 2026)**: Datamodell-fundament — `ModuleSettings`,
  permission-flagg, `AuditLog.app_label`.
- **Fase 3b (mai 2026)**: Admin-UI for moduler/audit + Min profil
  + bulk-aksjoner. 37 nye tester, totalt 413.
- **Fase 4 (mai 2026)**: Per-modul backup med admin-UI. Sentral
  `core.backup`-pakke, `ModuleBackupConfig`-modell, `BaseBackupHandler`
  registry, restore-flyt med slug-bekreftelse + audit-log. 47 nye
  tester, totalt 460.

## Tillegg: Fase 4 — Per-modul backup (mai 2026)

Fase 4 modulariserer backup-løsningen. Hver modul kan ha egen av/på,
intervall og max-antall, og restore er tilgjengelig fra portal-admin
UI med slug-bekreftelse.

### `core.backup` — sentralt rammeverk

- `core.backup.handlers.BaseBackupHandler`: abstrakt baseklasse med
  `slug`, `display_name`, `apps`, `exclude` og `restore_models`.
  Hver modul registrerer en subklasse via `register(handler)` i
  `app.ready()`.
- `core.backup.service.create_backup(slug, kind, ...)`: serialiserer
  apps via `dumpdata` (natural keys), gzip-er og lagrer både fil og
  `Backup`-rad. Hash-skip kun for `KIND_AUTO`.
- `core.backup.service.restore_backup(backup, user)`: lager
  pre-restore-snapshot, sletter `restore_models` i FK-trygg rekkefølge,
  kjører `loaddata`. Steg 2-3 i atomisk transaksjon.
- `core.backup.service.enforce_cap(slug, max_backups)`: fjerner eldste
  ikke-pre_restore-backuper. Pre-restore-snapshots er beskyttet.
- Konstanter: `KIND_AUTO`, `KIND_MANUAL`, `KIND_PRE_RESTORE`,
  `KIND_PRE_RESET`, `PROTECTED_KINDS`, `VALID_KINDS`.

### `core.models.ModuleBackupConfig`

Én rad per modul med `module_slug` (unique), `enabled`,
`interval_minutes` (5/15/30/60/360/1440 min eller 0=Av), `max_backups`
(1–1000, default 50), `last_run_at`. Erstatter den gamle singleton
`patients.BackupConfig`. Data-migrering i
`core/migrations/0002_modulebackupconfig.py` kopierer eksisterende
intervall til `module_slug='patients'`.

### `patients.backup.PatientsBackupHandler`

Første konsumenten av rammeverket. `apps=['patients']`, ekskluderer
`Backup`, `BackupConfig` og `VaktArkiv` (det siste er låst arkiv som
aldri røres av restore). Restore-rekkefølge:
Patient → Forstehjelper → Helsepersonell → AppSetting (FK-trygg).

### Admin-UI

Under `/portal-admin/backup/`:

| URL | Funksjon |
| --- | --- |
| `/portal-admin/backup/` | Oversikt over moduler + status |
| `/portal-admin/backup/<slug>/` | Rediger config + se backup-liste |
| `/portal-admin/backup/<slug>/run/` | Start manuell backup (POST) |
| `/portal-admin/backup/<slug>/restore/<pk>/` | Restore med slug-bekreftelse |
| `/portal-admin/backup/<slug>/last-ned/<pk>/` | Last ned `.json.gz` |
| `/portal-admin/backup/<slug>/slett/<pk>/` | Slett enkelt-backup (POST) |

Alle admin-only via `@admin_required`. Restore-flyt logges i
`AuditLog` med `table_name='<slug>_backup_restore'`,
`action='UPDATE'`, `app_label='core'`.

### Scheduler

`patients.backup_scheduler.maybe_run_backup()` (kalt fra middleware)
itererer alle aktive `ModuleBackupConfig`-rader og kjører backup
uavhengig per modul. `select_for_update(nowait=True)` + dobbeltsjekk
on `last_run_at` hindrer at to Gunicorn-arbeidere tar samme backup
samtidig. Throttling: maks én DB-sjekk per 60 sekund per prosess.

### Bakoverkompatibilitet

`patients.backup_service` proxy-er nå mot `core.backup`. Eldre kall
(`create_backup(kind=...)` uten slug) defaulter til
`slug='patients'`. Management-kommandoen `db_backup` virker uendret.


## Fase 5: Bruker‑Førstehjelper‑kobling + varsel‑bjelle

### Generisk varsel‑system

`core.Notification` er en gjenbrukbar varsel‑modell knyttet til `CustomUser`. Andre moduler oppretter varsler via:

```python
from core.notifications import notify

notify(
    user=mottaker,
    module_slug='vakter',     # eller 'utstyr', 'beredskap', ...
    kind='vakt_endret',
    title='Vakt endret',
    message='Din vakt 12.06 er flyttet.',
    url='/vakter/123/',
    level='info',             # 'info' | 'warning' | 'critical'
)
```

24‑timers `(user, kind, message)`-dedup hindrer spamming ved gjentatte signals.

### Brukerkobling til pasientregistrering

`patients.Forstehjelper.user` og `patients.Helsepersonell.user` er nullbare
`OneToOneField` mot `CustomUser` (`SET_NULL`). Admin kobler i bruker‑detaljvisningen. En bruker kan kun ha **én** kobling (XOR‑validert i `accounts.forms.UserPatientLinkForm`).

### Pasient‑filter `?mine=1`

`patients.views.patients_list_view` filtrerer på
`Q(forstehjelper__user=request.user) | Q(helsepersonell_ref__user=request.user)`
når `?mine=1` er satt. Default AV — alle innloggede roller ser alle pasienter som standard. Server‑side filter (ikke klient‑side) slik at row‑count og search forblir konsistente.

### Tildelings‑signal

`patients.signals.patient_pre_save` lagrer `_orig_behandler_id` og
`_orig_helsepersonell_ref_id` på instansen. `patient_post_save` sammenligner mot originalen og kaller `core.notifications.notify()` for nye eiere og forrige eier ved flytting. Hele varsel‑koden er pakket inn i `try/except` — varsler skal aldri kunne hindre pasient‑lagring.

### Polling‑arkitektur

`base_portal.html` poller `GET /api/varsler/ulest-antall/` hvert 30. sekund. Polling pauser når `document.visibilityState !== 'visible'` for å spare server‑ressurser når brukeren bytter fane.

### Context processor

`core.context_processors.notification_unread_count` eksponerer
`notification_unread_count` til alle templates som arver fra `base_portal.html`. Defensiv mot ikke‑migrerte databaser (returnerer 0 ved unntak).
