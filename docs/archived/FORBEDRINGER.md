# Forbedringsforslag – mai-runden (arkiv)

> **Versjon:** Mai 2026, arkivert august 2026
> **Status:** Dette dokumentet er nå et **historisk arkiv** over forbedringsrunden fra mai
> 2026. Det beskriver hva som ble identifisert, hva som ble gjort og hvorfor.
>
> ### ➜ Aktiv backlog ligger i [`FORBEDRINGER_2026-08.md`](../FORBEDRINGER_2026-08.md)
>
> Alle punkter som fortsatt sto åpne er flyttet dit, sammen med nye funn fra
> kodegjennomgangen i august. **Nye forslag skal legges til der, ikke her.** Denne fila
> er arkiv og skal ikke oppdateres — heller ikke når et punkt fra den aktive backloggen
> blir ferdig. Da hører beskrivelsen hjemme i [`../../CHANGELOG.md`](../../CHANGELOG.md).

---

## Hva som ble gjennomført

| # | Tittel | Status |
|---|---|---|
| 0 | Backup-scheduler: hopp over identiske backups (hash-basert skip) | ✅ Implementert |
| 1 | Migrasjons-cleanup (`accounts`, `audit`) | ✅ Implementert (4. mai 2026) |
| 2 | Health-endepunkt for Railway (uten auth) | ✅ Implementert |
| 4 | Verifiser `cache_health` i prod etter siste deploy | ✅ Verifisert (6. mai 2026) |
| 5 | Management command: finn pasienter som mistet plassering | ⚪ Ikke aktuell |
| 6 | Backup-restore drill dokumentert prosess | ✅ Gjennomført |
| 11 | Pro-plan vurdering for store vakter | ✅ Besluttet — Pro-plan kjøpt |
| 15 | Aggregere request-metrikker over workers (Redis-tellere) | ✅ Implementert (6. mai 2026) |
| 16 | Dokumenter multi-worker-design i TEKNISK_DOKUMENTASJON | ✅ Implementert (6. mai 2026) |
| 17 | Custom Start Command vs Procfile-konflikt på Railway | ✅ Akseptert kompromiss |
| 19 | Hindre hopp i pasientnummer-serien ved validerings-feil | ✅ Implementert (3. mai 2026) |
| 20 | Klokkedrift mellom klient og server (`pabegynt` < `inntid`) | ✅ Implementert (3. mai 2026) |

### Flyttet til aktiv backlog

| Opprinnelig # | Tittel | Nytt nr. |
|---|---|---|
| 3 | E-postvarsel ved kritiske feil (uten Sentry) | F1 |
| 7 | Lasttest-script før stor vakt | F4 |
| 8 | CSP-headers stramming | F5 |
| 9 | Frontend bundle-størrelse / lazy loading | F7 |
| 10 | PgBouncer / Postgres connection pooler | F8 |
| 12 | Statistikk-utvidelse (live-dashbord + utvidet analyse) | F6 |
| 13 | Automatisert audit-purge i Procfile/scheduler | F2 |
| 14 | Kolonne-kryptering for følsomme felter | F9 |
| 18 | Server-side idempotency for pasient-opprettelse (Fix B) | F3 |

---

## 0. Backup-scheduler: hopp over identiske backups &nbsp;—&nbsp; ✅ IMPLEMENTERT

**Status:** Løst i `core/backup/service.py`. `_serialize_with_handler()` beregner SHA-256
over den ukomprimerte JSON-en (linje 56–82), og `create_backup()` slår opp siste
auto-backup for modulen og returnerer `None` hvis hashen er identisk (linje 133–147).
Hashen lagres på `Backup.content_hash` (`patients/models.py:350`).

Skip-logikken gjelder **kun** `kind='auto'` — manuelle, pre-restore og pre-reset lagres
alltid, slik det opprinnelig var spesifisert. `backup_scheduler.py:107–116` logger
eksplisitt at en kjøring ble hoppet over. Tester i `patients/tests_backup.py:297–340`.

**Bakgrunn:** Backup-scheduleren brukte tidligere kun tidsbasert intervall
(`interval_minutes`) for å avgjøre om backup skulle kjøres. To backups med identisk
innhold ble lagret som to separate filer så lenge intervallet hadde passert. I praksis
fungerte det greit fordi scheduleren kun trigges av HTTP-requests, men under aktiv bruk ga
det unødvendig diskbruk og støy i backup-listen.

---

## 1. Migrasjons-cleanup (`accounts`, `audit`) &nbsp;—&nbsp; ✅ IMPLEMENTERT (4. mai 2026)

**Status:** Løst. `accounts/migrations/0006_alter_customuser_groups_and_more.py` (no-op SQL)
og `audit/migrations/0002_rename_audit_auditlog_*.py` (DROP+CREATE indekser) generert
lokalt, deployet via git push, bekreftet i `railway logs --latest` — meldingen «have
changes that are not yet reflected» er borte.

**Bakgrunn:** Railway-loggen viste ved hver oppstart at modellene i `accounts` og `audit`
hadde ulagrede endringer som ikke var materialisert som migrasjonsfiler. Ikke akutt —
produksjonsdatabasen kjørte på forrige migrasjon — men en tikkende bombe: neste deploy som
skulle materialisere skjemaendringer kunne fått uventet diff.

---

## 2. Health-endepunkt for Railway (uten auth) &nbsp;—&nbsp; ✅ IMPLEMENTERT

**Status:** Løst. `patients/health.py` implementerer `/healthz/`, montert på root i
`myproject/urls.py` slik at Railways «Health Check Path» kan peke direkte dit.

Endepunktet er `@csrf_exempt`, `@require_safe`, `@never_cache` og krever ingen
innlogging. Det gjør en `SELECT 1` mot databasen og en skriv-les-slett-probe mot cachen,
og returnerer `{status, db, cache, version}` der `version` er de sju første tegnene av
`RAILWAY_GIT_COMMIT_SHA`.

To designvalg verdt å merke seg:

- **503 kun ved DB-feil.** Cache-feil gir 200 med `status: "degraded"` — appen er
  fortsatt brukbar uten cache (rate-limiting og metrikker har lokal fallback), og
  Railway skal ikke restarte en fungerende container fordi Redis hikster.
- **`SECURE_REDIRECT_EXEMPT = [r'^healthz/$']`** (`settings.py:231`) fordi Railways interne
  healthcheck ikke går via TLS-proxyen og derfor mangler `X-Forwarded-Proto`. Uten
  unntaket ville `SECURE_SSL_REDIRECT` svart 301 på hver eneste sjekk.

Endepunktet er også unntatt fra `RequestMetricsMiddleware` (`middleware.py:317`) slik at
hyppige helsesjekker ikke forurenser P95-tallene. Tester i `patients/tests_health.py`.

---

## 4. Verifiser `cache_health` i prod etter siste deploy &nbsp;—&nbsp; ✅ VERIFISERT (6. mai 2026)

**Status:** Verifisert via kodegjennomgang etter brukerens ønske om ikke å gi agenten
tilgang til prod-endepunkter. `_get_cache_health()` i `patients/admin_status.py:117–146`:

1. Leser `settings.CACHE_BACKEND_NAME` (`redis` / `locmem` / `unknown`)
2. Skriver tilfeldig probe-nøkkel, leser tilbake, sletter
3. Returnerer `{backend, healthy, latency_ms}` ved suksess
4. Ved exception: `{backend, healthy: False, error: <scrubbed>}` — credentials vasket via
   `_scrub_secrets`
5. `_build_status_payload()` inkluderer `cache_health` i hver respons
6. `templates/patients/admin_status.html` rendrer feltet i admin-dashbordet

Totalt: skriver, leser, sletter — en reell health-probe, ikke bare en ping. Skal aldri
kaste; alle exceptions fanges.

---

## 5. Management command: finn pasienter som mistet plassering &nbsp;—&nbsp; ⚪ IKKE AKTUELL

**Status:** Brukerens vurdering 6. mai 2026: «Var før vakten» — plassering-bugen gjaldt en
kort periode før vakthelg-deployen, og det er ikke tegn til historiske tap som
rettferdiggjør en management command.

**Bakgrunn (beholdt som referanse):** Plassering-bugen — der en pasient kunne «miste»
plassering på grunn av unik-constraint-konflikt når behandler ble endret — er fikset i
både front- og backend. Det er teoretisk mulig at noen historiske pasienter allerede har
mistet plassering. Dataene ville i så fall ligget i `AuditLog`, og en kommando kunne
identifisert tilfeller der plassering gikk fra X → NULL i samme transaksjon som behandler
ble endret.

---

## 6. Backup-restore drill dokumentert prosess &nbsp;—&nbsp; ✅ GJENNOMFØRT

**Status:** Drill gjennomført og dokumentert. Restore-prosedyren ligger i
`RUNBOOK_VAKT.md` og ble verifisert mot en lokal kopi.

**Bakgrunn:** Vi har automatisk backup på Railway Volume og restore-funksjon i admin-UI,
men hadde aldri gjennomført en øvelse der vi reelt gjenopprettet en backup. Hvis verktøyet
feiler ved en reell krise, finner vi det ut på verst tenkelig tidspunkt.

Prosedyren som ble skrevet: last ned siste `backup.json.gz` fra prod-volumet, opprett en
tom database lokalt, kjør restore, og bekreft pasienttall, stikkprøver av enkeltposter og
arkivinnhold. Satt opp som halvårlig oppgave.

---

## 11. Pro-plan vurdering for store vakter &nbsp;—&nbsp; ✅ BESLUTTET

**Status:** Pro-plan aktivert i Railway. Gir høyere RAM- og CPU-grenser, samt mulighet for
2 workers + Redis under vakt. Mellom vakter kjøres «lavkostnad-modus» (1 worker, Redis
frakoblet, LocMem-cache) for å redusere løpende kostnad. Se `RUNBOOK_VAKT.md` for
prosedyre før og etter vakt.

**Bakgrunn:** Hobby-planen begrenser RAM (512 MB) og CPU. Med Redis + 2 Gunicorn-workers
var forbruket allerede betydelig.

---

## 15. Aggregere request-metrikker over workers &nbsp;—&nbsp; ✅ IMPLEMENTERT (6. mai 2026)

**Status:** Implementert som **Redis-aggregert liste med LocMem-fallback**. Fungerer
transparent i begge driftsmodus:

- **Vakt-modus** (`REDIS_URL` satt): hver request `LPUSH`-er en JSON-pakket sample
  (timestamp, path, method, status, duration_ms, pid) til Redis-listen `metrics:requests`.
  `LTRIM` holder listen på maks 5000 samples. `snapshot()` leser hele listen, filtrerer på
  vindu og aggregerer på tvers av alle workere.
- **Lavkostnad-modus** (`REDIS_URL` tom): hopper helt over Redis-veien. `snapshot()` bruker
  lokal deque — helt korrekte tall siden det bare er én worker.

**Endringer:** `patients/middleware.py` fikk `_redis_is_available()`, `_get_redis_client()`,
`_record_to_redis()`, `_read_from_redis()`, og oppdatert `record()`/`snapshot()`.
Snapshot returnerer to nye felter: `source` (`redis` eller `local`) og `unique_workers`
(antall ulike PID-er som bidro).

**Robusthet:** Bruker `redis`-biblioteket direkte (ikke `django_redis`) siden prosjektet
bruker Djangos innebygde `RedisCache`. `socket_timeout=2` sikrer at treg eller død Redis
ikke henger requesten. Alle Redis-feil fanges — i verste fall faller vi tilbake til lokal
deque uten brukermerkbar effekt. `MetricsRedisAggregeringTests` (8 tester) i
`patients/tests_admin_status.py`.

> **Se N7 i den aktive backloggen:** klienten bygges i dag på nytt for hvert kall, som
> koster en TCP-handshake per request. Selve aggregeringsdesignet er uendret.

---

## 16. Dokumenter multi-worker-design i TEKNISK_DOKUMENTASJON &nbsp;—&nbsp; ✅ IMPLEMENTERT (6. mai 2026)

**Status:** Kapittelet «Multi-worker-design og lavkostnad-modus» er lagt til i
`TEKNISK_DOKUMENTASJON.md`. Det inneholder:

- State-tabell over alle in-memory-mekanismer og hvordan de er beskyttet
- Dokumentasjon av lavkostnad- vs. vakt-modus (`REDIS_URL`-flagget styrer alt)
- Beskrivelse av #15 Redis-aggregerte metrikker
- Sjekkliste for utviklere som legger til ny global state
- Krysshenvisning til `RUNBOOK_VAKT.md` §4

**Bakgrunn:** Kodebasen er bevisst designet for flere Gunicorn-workers (Redis-cache,
DB-låser, thread-local audit), men det var ikke samlet beskrevet noe sted. En fremtidig
utvikler som la til ny in-memory state uten å kjenne mønsteret kunne skapt subtile bugs
ved `WEB_WORKERS > 1`.

---

## 17. Custom Start Command vs. Procfile-konflikt på Railway &nbsp;—&nbsp; ✅ AKSEPTERT KOMPROMISS

**Status:** Brukerens beslutning 6. mai 2026: «Vi går for A, men lag et notat slik at vi
kan se på det senere.» Praktisk situasjon i dag:

- **Procfile** holdes versjonskontrollert som single source of truth for `web:`-kommandoen
- **Custom Start Command** beholdes på Railway, men bruker nå samme env-variabler
  (`${WEB_WORKERS:-1}`, `${WEB_THREADS:-4}`) slik at de to ikke divergerer
- Custom Start Command beholder release-fase-prefikset fordi en feilende release-blokk i
  Procfile vil blokkere deploy hardere enn dagens oppførsel

**Notat for senere vurdering:** Full overgang til alternativ A (tom Custom Start Command,
alt i Procfile `release:` + `web:`) når vi har bedre forståelse av hvor strenge
release-failures bør være. Krever én stille deploy-test utenom vakt.

**Bakgrunn:** Railway-tjenesten hadde en hardkodet Custom Start Command i dashbordet som
overstyrte Procfile fullstendig, med `--workers 1 --threads 4` hardkodet. `WEB_WORKERS=2`
ble derfor ignorert i produksjon i lang tid — selv om både Procfile og miljøvariabel var
korrekt satt opp. Fikset 30. april 2026.

> **Erfaring å huske:** Hvis `WEB_WORKERS`/`WEB_THREADS` eller andre miljøvariabler ikke
> ser ut til å trekke i prod, sjekk **Custom Start Command først** — ikke Procfile. Den
> vinner alltid.

---

## 19. Hindre hopp i pasientnummer-serien &nbsp;—&nbsp; ✅ IMPLEMENTERT (3. mai 2026)

**Status:** Løst i samme commit som #20, med begge de foreslåtte alternativene kombinert:

- Plassering-validering flyttet til **før** `next_patient_nr()` (alternativ A) —
  `patients/views.py:224–229`
- Pasient-opprettelse pakket i `transaction.atomic()` (alternativ B) — inkludert
  nummer-tildelingen, slik at en eventuell feil i `save()` ruller tilbake telleren
  (`patients/views.py:262–295`)
- Tester: `PatientNumberGapTests` (2 tester)

**Bakgrunn:** 2. mai 2026 ble det observert et hopp i pasientnummer-serien fra 125 → 127 i
prod. `next_patient_nr()` ble kalt **før** validering av plassering, så en feilet
validering «brukte opp» et nummer uten at en pasient ble opprettet.

Funksjonelt var det uproblematisk — pasienter fikk fortsatt unike numre og ingen data gikk
tapt — men hull i serien er forvirrende for brukerne, gjør nummer-baserte opptellinger
misvisende og skaper spørsmål i kvalitetskontroll («hvor er pasient 126?»).

---

## 20. Klokkedrift mellom klient og server (`pabegynt` < `inntid`) &nbsp;—&nbsp; ✅ IMPLEMENTERT (3. mai 2026)

**Status:** Løst.

**Bakgrunn:** 3. mai 2026 oppdaget brukeren at `pabegynt` i mange tilfeller lå **før**
`inntid` — fra 1 til 8 minutter, avhengig av hvilken klient som registrerte. Det gir
negative ventetider i statistikken og er klinisk meningsløst.

**Rotårsak:** Frontend brukte klient-PC-ens klokke som fallback for `inntid`, mens serveren
stemplet `pabegynt` med sin egen `datetime.now()`. Klienter uten NTP-synk kan drive flere
minutter foran serveren.

I tillegg ble det avdekket at `datetime.now()` i Django-koden ikke honorerer
`TIME_ZONE='Europe/Oslo'` — den returnerer naiv container-lokaltid (UTC på Railway). Det
var ikke årsaken til de observerte tilfellene, men en latent bug som ville slått inn ved
enhver fremtidig endring av container-TZ.

**Implementert løsning:**

1. Ny helper `now_local_str()` (nå i `core/validators.py`) som bruker
   `django.utils.timezone.localtime(timezone.now())` og garanterer Europe/Oslo uavhengig av
   container-TZ
2. Alle `datetime.now().strftime(...)` i `stamp_pabegynt_if_needed`,
   `stamp_obs_times_if_needed` og `stamp_utskrevet_if_needed` erstattet
3. **Én felles tidsstempel per request** — `views.py` setter `data['_now_str']` tidlig, og
   alle stamp-funksjoner leser fra samme verdi (hindrer mikrodrift mellom kall)
4. Blank-fallback for `inntid` — endret fra `data.get('inntid', now)` til
   `data.get('inntid') or now_str`, som også håndterer tom streng
5. Sikkerhetsnett `_ensure_pabegynt_not_before_inntid()` i `views.py:52–76` — justerer
   `pabegynt` opp til `inntid` hvis den likevel skulle ligge før. Kalles i både POST og PUT

**Tester:** `PabegyntNotBeforeInntidTests` (5), `BlankInntidFallbackTests` (1),
`NowLocalStrTests` (2).

**Effekt på historiske data:** Eksisterende rader med `pabegynt` < `inntid` korrigeres
ikke automatisk — fixen virker kun fremover.

> **Se N5 i den aktive backloggen:** to steder slapp unna denne oppryddingen —
> `get_active_year()` og `Patient.save()` bruker fortsatt `datetime.now().year`.

---

## Avsluttede forslag fra tidligere runder

| Tittel | Status |
|---|---|
| Sentry-integrasjon | Avbrutt etter brukerens valg — fullstendig fjernet |
| Redis for delt cache | Implementert og verifisert (april 2026) |
| `_scrub_secrets()`-helper | Implementert (5 tester) |
| Workers/threads-parametrisering | Implementert via `Procfile`-miljøvariabler |
| Plassering-bug fix (front + back) | Implementert + 4 nye tester |
| Admin-sesjonshåndtering (force logout) | Implementert (16 tester) |
| CSRF-bug i admin-status | Fikset (lokal `_getCsrfToken()` i `admin_status.html`) |
| Stats-cache failsafe (try/except) | Implementert |
| Cache-helsesjekk i admin-dashbord | Implementert |
| RUNBOOK §4 (workers/threads-guide) | Implementert |
| Backup-kort i admin-dashbord | Bug fikset (filter på ikke-eksisterende `status`-felt) + 4 tester |
| Live-stats feature-flag default | Endret til `'false'` siden funksjonen ikke er implementert |
| Beredskap-tabell i admin-status | Synkronisert med RUNBOOK §2 (P95-terskler, Redis-krav) |
