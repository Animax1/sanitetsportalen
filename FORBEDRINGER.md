# Forbedringsforslag – Pasientregistrering

> **Versjon:** Mai 2026 (oppdatert etter etterarbeids-fase del 2)
> **Formål:** Samlet liste over forbedringspotensial som er identifisert i siste arbeidsperiode (sikkerhetsfix, Redis-integrasjon, sesjonsstyring, dokumentasjon). Hvert punkt er rangert etter **verdi** (høy/middels/lav) og **innsats** (timer).
> **Bruk:** Bruk dette som en utviklings-backlog. Plukk fra topp og ned. Lavt-hengende frukt (høy verdi, lav innsats) er listet først.

---

## Sammendrag — prioriterings-matrise

Status-kolonne: ✅ ferdig · 🔧 påbegynt · ⏳ pending · ⚪ ikke aktuell

| # | Tittel | Status | Verdi | Innsats | Anbefalt når |
|---|---|---|---|---|---|
| 0 | **Backup-scheduler: hopp over identiske backups (hash-basert skip)** | ⏳ | Høy | 1–2 t | Første oppgave neste sesjon |
| 1 | Migrasjons-cleanup (`accounts`, `audit`) | ✅ | Høy | 30 min | Innen 1 uke |
| 2 | Health-endepunkt for Railway (uten auth) | ⏳ | Høy | 1–2 t | Før neste store vakt |
| 3 | E-postvarsel ved kritiske feil (uten Sentry) | ⏳ | Høy | 2–3 t | Før neste store vakt |
| 4 | Verifiser cache_health i prod etter siste deploy | ✅ | Høy | 5 min | Umiddelbart |
| 5 | Management command: finn pasienter som mistet plassering | ⚪ | Middels | 2–3 t | Innen 1 måned |
| 6 | Backup-restore drill dokumentert prosess | ✅ | Høy | 2 t | Innen 1 måned |
| 7 | Lasttest-script før stor vakt | ⏳ | Middels | 3–4 t | Før første 15+-bruker-vakt |
| 8 | CSP-headers stramming | ⏳ | Middels | 2 t | Ved neste front-end-sprint |
| 9 | Frontend bundle-størrelse / lazy loading | ⏳ | Lav | 4–6 t | Når mobilytelse blir et reelt problem |
| 10 | PgBouncer / Postgres connection pooler | ⏳ | Lav | 2–3 t | Før 4+ Gunicorn-workers |
| 11 | Pro-plan vurdering for store vakter | ✅ | Middels | 30 min vurdering | Foran vakt med >20 brukere |
| 12 | **Statistikk-utvidelse (Live-dashbord + utvidet analyse)** | ⏳ | Middels–Høy | 25–35 t totalt (faseinndelt) | Når leads etterspør mer innsikt |
| 13 | Automatisert audit-purge i Procfile/scheduler | ⏳ | Middels | 1–2 t | Innen 6 måneder |
| 14 | Kolonne-kryptering for følsomme felter | ⏳ | Lav | 8–12 t | Kun ved skjerpede datakrav |
| 15 | Aggregere request-metrikker over workers (Redis-tellere) | ✅ | Lav | 2–3 t | Når admin-status-tall blir misvisende |
| 16 | Dokumenter multi-worker-design i TEKNISK_DOKUMENTASJON | ✅ | Lav | 30 min | Sammen med #15 eller neste dok-runde |
| 17 | Rydd opp i Custom Start Command vs Procfile-konflikt på Railway | ✅ (kompromiss) | Middels | 30 min | Innen 1 måned |
| 18 | Server-side idempotency for pasient-opprettelse (Fix B mot dobbel registrering) | ⏳ | Middels–Høy | 2–3 t | Innen 1 måned |
| 19 | Hindre hopp i pasientnummer-serien ved validerings-feil | ✅ | Lav–Middels | 30 min–1 t | Innen 1 måned |
| 20 | Klokkedrift mellom klient og server (pabegynt < inntid) | ✅ | Middels–Høy | 1 t | — |

---

## 0. Backup-scheduler: hopp over identiske backups

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 1–2 t

**Bakgrunn:** Backup-scheduleren (`patients/backup_scheduler.py` + `backup_service.py`) bruker bare tidsbasert intervall (`interval_minutes`) for å avgjøre om backup skal kjøres. Det er **ingen endrings-deteksjon** — to backups med identisk inneholdt blir lagret som to separate filer så lenge intervallet har passert.

I praksis fungerer dette greit fordi scheduleren kun trigges av HTTP-requests (passiv), så i perioder uten trafikk skjer ingen backup. Men når appen er aktivt i bruk får vi unodvendig disk-bruk og støy i Backup-listen.

**Tiltak:**

1. I `_serialize_db_to_json()`: beregn SHA256 av JSON-bytes før komprimering.
2. Lagre `content_hash` på `Backup`-modellen (ny migrasjon).
3. I `create_backup()` (eller en wrapper for auto-backup): hvis siste auto-backup har samme `content_hash`, oppdater bare `BackupConfig.last_run_at` og hopp over filskriving + DB-rad.
4. Tester:
   - Pasientendring → ny backup tas
   - Ingen endring → ny backup hoppes over, last_run_at oppdateres
   - Manuell backup respekterer ikke skip-logikken (alltid lagres)

**Kode-skisse:**
```python
import hashlib

def _serialize_db_to_json():
    # ... eksisterende kode ...
    raw = buf.getvalue().encode('utf-8')
    return raw, hashlib.sha256(raw).hexdigest()

def create_backup(kind='manual', user=None, note=''):
    raw, content_hash = _serialize_db_to_json()
    if kind == 'auto':
        last_auto = Backup.objects.filter(kind='auto').order_by('-created_at').first()
        if last_auto and last_auto.content_hash == content_hash:
            logger.info('backup_scheduler: identisk innhold som forrige, hopper over')
            return None  # signaliserer skip
    # ... resten som før ...
```

**Risiko:** Lav. Krever migrasjon for nytt felt og opp dater backup-tester. Kjør dry-run i staging først.

---

## 1. Migrasjons-cleanup (`accounts`, `audit`) &nbsp;—&nbsp; ✅ IMPLEMENTERT (4. mai 2026)

**Status:** Løst. `accounts/migrations/0006_alter_customuser_groups_and_more.py` (no-op SQL) og `audit/migrations/0002_rename_audit_auditlog_*.py` (DROP+CREATE indekser) generert lokalt, deployed via git push, bekreftet i `railway logs --latest` — "have changes that are not yet reflected"-meldingen er borte.

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 30 min

**Bakgrunn:** Railway-loggen viser ved hver oppstart:

```
Your models in app(s): 'accounts', 'audit' have changes that are not yet reflected in a migration.
```

Dette betyr at modellene har ulagrede endringer som ikke er materialisert som migrasjonsfiler. Det er **ikke akutt** — produksjonsdatabasen kjører på forrige migrasjon — men en tikkende bombe: neste deploy som skal materialisere skjemaendringer kan få uventet diff.

**Tiltak:**

1. Kjør lokalt:
   ```powershell
   cd C:\Programmering\Pasientregistrering
   python manage.py makemigrations accounts audit --dry-run --verbosity 2
   ```
2. Hvis output viser endringer: kjør uten `--dry-run`, sjekk inn migrasjonsfilen, deploy.
3. Hvis output viser "No changes": typisk årsak er en endring i `Meta.ordering` eller `default=callable` som Django regenererer hver oppstart — da må den eksplisitt materialiseres.

**Akseptansekriterium:** Railway-loggen er stille ved oppstart (ingen "have changes that are not yet reflected").

---

## 2. Health-endepunkt for Railway (uten auth)

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 1–2 timer

**Bakgrunn:** Dagens admin-status (`/api/admin-status/`) krever innlogging. Railway og eventuelle eksterne overvåkingstjenester (UptimeRobot, BetterStack) trenger et endepunkt som svarer 200 OK uten auth så lenge appen lever, og 5xx hvis noe har klikket.

**Tiltak:**

- Nytt endepunkt `/healthz/` som er fritatt fra `@login_required` og `OTPMiddleware`-redirect.
- Sjekker:
  - DB-tilkobling (`connections['default'].cursor().execute('SELECT 1')`)
  - Cache-skriving + lesing (samme probe som `_get_cache_health`)
  - Returnerer JSON `{status: ok, db: ok, cache: ok, version: ...}` eller HTTP 503 ved feil.
- Skriv 3–4 tester (200 ved healthy, 503 ved DB-feil, 503 ved cache-feil, 200 men advarsel ved degradert cache).
- Konfigurer i Railway-tjenesten: Settings → Health Check Path = `/healthz/`.

**Akseptansekriterium:** Railway viser grønn helse-indikator. Manuell `curl https://<app>/healthz/` returnerer 200 OK uten auth.

---

## 3. E-postvarsel ved kritiske feil (uten Sentry)

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** Sentry ble fjernet fra prosjektet etter brukerens ønske. Dermed har vi ikke lenger automatisk varsel ved 500-feil i prod. RUNBOOK §13 dekker manuell feilsøking, men proaktiv varsling mangler.

**Tiltak:**

- Konfigurer Django's innebygde `AdminEmailHandler` i `LOGGING`-blokken i `settings.py`.
- Legg til `ADMINS = [('André', 'andre.eritsland@gmail.com')]` (allerede satt? sjekk).
- SMTP via Railway-variabler: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`. Bruk f.eks. SendGrid free tier (100 mail/dag).
- Throttling: `RateLimitFilter` på logging slik at én feil-burst ikke spammer 200 mailer. Begrens til én mail per feiltype per 15 min.
- Test ved å simulere en 500 i staging.

**Akseptansekriterium:** Når en uhåndtert exception kastes i prod, mottar `andre.eritsland@gmail.com` en e-post med stacktrace innen 1 minutt. Maks 1 mail per 15 min for samme feiltype.

---

## 4. Verifiser cache_health i prod etter siste deploy &nbsp;—&nbsp; ✅ VERIFISERT (kode-review, 6. mai 2026)

**Status:** Verifisert via kode-gjennomgang etter brukerens ønske om å ikke gi agent-tilgang til prod-endepunkt. `_get_cache_health()` i `patients/admin_status.py:117–146` gjør følgende:
1. Leser `settings.CACHE_BACKEND_NAME` ('redis' / 'locmem' / 'unknown')
2. Skriver tilfeldig probe-nøkkel via `cache.set(...)`, leser tilbake via `cache.get(...)`, sletter
3. Returnerer `{backend, healthy: bool, latency_ms}` ved suksess
4. Ved exception: `{backend, healthy: False, error: <scrubbed>}` (credentials vasket via `_scrub_secrets`)
5. `_build_status_payload()` (linje 159) inkluderer `cache_health` i hver respons
6. Templaten `templates/patients/admin_status.html:257` rendrer feltet i admin-dashbord

Totalt: skriver, leser, sletter — reell health-probe (ikke bare ping). Skal aldri kaste, alle exceptions fanges. Klar for bruk i prod når Redis kobles tilbake før vakt.

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 5 minutter

**Bakgrunn:** Etter siste sikkerhets-deploy (fjerning av `DJANGO_REDIS_IGNORE_EXCEPTIONS` + `_scrub_secrets`-helperen) er det ikke verifisert at `/api/admin-status/` rapporterer `backend=redis, healthy=true`.

**Tiltak:**

1. Logg inn som admin i prod.
2. Åpne admin-status-dashbordet.
3. Bekreft Cache-backend-kortet:
   - Backend = `redis`
   - Status = healthy / grønn
   - Latency innenfor f.eks. 1–5 ms (intern Redis i Railway)
4. Hvis ikke healthy: sjekk Railway-variabel `REDIS_URL` (skal være Reference til Redis-tjenestens `REDIS_URL`).

**Akseptansekriterium:** Skjermdump av healthy=true cache-backend lagret i prosjekt-mappen.

---

## 5. Management command: finn pasienter som mistet plassering &nbsp;—&nbsp; ⚪ IKKE AKTUELL

**Status:** Brukerens vurdering 6. mai 2026: "Var før vakten" — plassering-bug-en gjaldt en kort periode før vakthelg-deploy, og det er ikke tegn til historiske tap som rettferdiggjør en management command. Markert som ikke aktuell, men beskrivelsen beholdes nedenfor som referanse hvis det skulle bli relevant senere.

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** Plassering-bug-en (når behandler endres, kunne pasienten "miste" plassering pga. unike-constraint-konflikt) er fikset både i front- og backend, men det er teoretisk mulig at noen historiske pasienter allerede har mistet plassering. Dataene ligger i AuditLog.

**Tiltak:**

- Lag `patients/management/commands/find_lost_plassering.py`:
  - For hver pasient: hent alle `AuditLog`-poster der `field_name='plassering'`.
  - Identifiser tilfeller hvor plassering gikk fra X → NULL i samme transaksjon som behandler ble endret.
  - Output CSV med pasient-ID, dato, tidligere plassering, behandler-endring.
- Tester på dummy-data.
- Dokumenter i RUNBOOK §12: "Hvis lead rapporterer manglende plassering historisk, kjør `python manage.py find_lost_plassering`".

**Akseptansekriterium:** Kommandoen kjører feilfritt på prod-DB (lokal kopi) og produserer en lesbar rapport. Tester grønne.

---

## 6. Backup-restore drill dokumentert prosess &nbsp;—&nbsp; ✅ GJENNOMFØRT

**Status:** Drill gjennomført og dokumentert. Restore-prosedyre eksisterer i `RUNBOOK_VAKT.md` (oppdateres i #16-runden) og ble verifisert mot lokal kopi.

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 2 timer

**Bakgrunn:** Vi har backup hver 15. minutt på Railway Volume, og restore-funksjon i admin-UI, men det er ikke gjort en øvelse hvor vi reelt restorer en backup fra den siste måneden. Hvis verktøyet feiler ved en reell krise, finner vi det ut på verst tenkelig tidspunkt.

**Tiltak:**

- Skriv en restore-drill prosedyre i RUNBOOK_VAKT.md §14 (eller nytt vedlegg):
  1. Last ned siste backup.json.gz fra prod-volumet.
  2. Lokalt: opprett en tom Postgres-DB.
  3. Kjør `python manage.py loaddata backup.json` (eller egen restore-kommando).
  4. Bekreft pasient-tall, sjekk noen tilfeldige poster, sjekk archive-mappen.
- Gjennomfør drill én gang. Skriv ned hvor lang tid det tok og evt. snubl.
- Sett opp som halvårlig oppgave i kalenderen.

**Akseptansekriterium:** Drill gjennomført og dokumentert med dato, tidsbruk og resultat.

---

## 7. Lasttest-script før stor vakt

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 3–4 timer

**Bakgrunn:** Det er foreslått en lasttest før første vakt med 15–20 brukere for å verifisere at Redis + 2 workers + 4 tråder faktisk holder forventet last.

**Tiltak:**

- Bruk `locust` eller enklere `python -m http.client`-script som simulerer:
  - 20 samtidige innloggede brukere
  - Hver bruker poller pasientliste hvert 30. sekund
  - 5 brukere oppretter pasient hvert 2. minutt
  - 2 brukere endrer en eksisterende pasient hvert minutt
- Kjør mot staging-miljø (eller midlertidig spunnet opp lik prod).
- Sjekk:
  - Gj.snitt responsetid < 500 ms
  - Ingen 5xx
  - Cache_hit-ratio i admin-dashbord
  - Memory og CPU i Railway-metrics

**Akseptansekriterium:** Rapport som viser at konfigurasjonen tåler 25 samtidige brukere uten degradering.

---

## 8. CSP-headers stramming

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 2 timer

**Bakgrunn:** Dagens CSP er konfigurert i `SecurityHeadersMiddleware`, men bruker antageligvis `unsafe-inline` for stiler/scripts. En strengere CSP gir bedre XSS-beskyttelse.

**Tiltak:**

- Audit nåværende CSP. Sjekk om Tabulator, Chart.js og inline event-handlers krever `unsafe-inline`.
- Innfør nonces for inline scripts via Django-template tag.
- Flytt inline event-handlers (`onclick="..."`) til addEventListener i `script.js`.
- Test grundig i alle nettlesere brukere benytter (Chrome, Edge, Safari iOS).

**Akseptansekriterium:** CSP-header inneholder ikke `unsafe-inline` for `script-src`. Manuell QA på alle hovedflyt.

---

## 9. Frontend bundle-størrelse / lazy loading

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 4–6 timer

**Bakgrunn:** `script.js` er en monolitt på mange tusen linjer. Lastes ved hvert sidebesøk. På mobil over 4G kan første-paint være tregt.

**Tiltak:**

- Mål først: bundle-størrelse, Time to Interactive på mobil.
- Hvis problem: split i moduler (admin-funksjoner separat, statistikk separat).
- Bruk dynamic `import()` for funksjoner som kun brukes av admin/lead.

**Akseptansekriterium:** Første-paint på mobil 4G < 1.5 s. Read-only brukere laster < 50 % av admin-bundle.

> **Merk:** Lav prioritet med mindre brukere klager på ytelse. Dagens ytelse er trolig god nok.

---

## 10. PgBouncer / Postgres connection pooler

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** Med `WEB_WORKERS=2` og `WEB_THREADS=4` kan vi i verste tilfelle ha 8 samtidige Postgres-connections per app-instans. Hvis vi senere skalerer til `WEB_WORKERS=4`, blir det 16. Railway Hobby Postgres har en grense på ~100 connections, så dette er ikke akutt, men en pooler reduserer pres på DB.

**Tiltak:**

- Vurder `pgbouncer-railway` (community service) eller bruk `dj-database-url` med connection pooling-parametre.
- Test grundig at sesjon-pooling fungerer med Django (transaksjoner!).

**Akseptansekriterium:** Antall faktiske Postgres-connections åpent fra app-instansen ≤ 4 ved 16 inngående requests.

> **Merk:** Kun relevant ved 4+ workers. Ikke prioriter før vi faktisk skalerer.

---

## 11. Pro-plan vurdering for store vakter &nbsp;—&nbsp; ✅ BESLUTTET (Pro-plan kjøpt)

**Status:** Pro-plan aktivert i Railway. Gir høyere RAM- og CPU-grenser, samt mulighet for 2 workere + Redis under vakt. Mellom vakter kjøres "lavkostnad-modus" (1 worker, Redis frakoblet, LocMem-cache) for å redusere løpende kostnad. Se RUNBOOK_VAKT.md for prosedyre før/etter vakt.

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 30 min vurdering + ev. oppgradering

**Bakgrunn:** Hobby-plan har begrensninger på RAM (512 MB) og CPU. Med Redis + 2 Gunicorn-workers er forbruket allerede betydelig. Før en vakt med 20+ brukere bør vi vurdere midlertidig oppgradering til Pro.

**Tiltak:**

- Før hver stor vakt: sjekk Railway-metrics for siste lille vakt. Hvis RAM > 70 % toppbelastning eller CPU > 70 %, vurder Pro.
- Pro koster ca. $20/måned ekstra og kan nedgraderes igjen umiddelbart etterpå (proratert billing).

**Akseptansekriterium:** Beslutning dokumentert i RUNBOOK før hver vakt med >15 brukere.

---

## 12. Statistikk-utvidelse (Live-dashbord + utvidet analyse)

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 25–35 timer totalt, faseinndelt

**Bakgrunn:** Dette er den største enkeltforbedringen i listen. Den er forankret i to tidligere dokumenter som ligger i prosjektet:
- [`STATISTIKK_ANALYSE_FORSLAG.md`](./STATISTIKK_ANALYSE_FORSLAG.md) — analyse av hva vi samler i dag og hvilke statistikker vi kan utlede
- [`STATISTIKK_IMPLEMENTERINGSPLAN.md`](./STATISTIKK_IMPLEMENTERINGSPLAN.md) — full funksjonell + arkitektonisk plan med fasedeling

Forbedringen deles i to konseptuelle leveranser: **(12a) Live-statistikk for alle innloggede** og **(12b) Utvidet evalueringsstatistikk for admin/lead**. De har ulik personvernprofil og deployes uavhengig.

### 12.1 Tilgangsmodell og oppdeling

I dag finnes to endepunkter:
- `/api/stats/` — basic header-chips (alle innloggede)
- `/api/full-stats/` — avansert med scipy (admin / lead / lead_view)

Forslaget innfører et tredje endepunkt og en sub-tab "Sanntid":

| Endepunkt | Tilgang | Innhold | Polling |
|---|---|---|---|
| `/api/stats/` | Alle innloggede | Header-chips (eksisterende) | 30 s |
| **`/api/stats/live/`** (NY) | Alle innloggede | A1–A4 (operativ sanntid) | 30–60 s |
| `/api/full-stats/` | admin/lead/lead_view | B1–B6, C1–C2, D1–D5 (utvidet) | 60–120 s (senket fra dagens 30 s) |

| Rolle | Live-statistikk | Full statistikk |
|---|---|---|
| admin | ✅ | ✅ |
| lead | ✅ | ✅ |
| lead_view | ✅ | ✅ |
| read_write | ✅ | ❌ |
| read_only | ✅ | ❌ |

**Rasjonale:** Live-data er aggregert (antall, tid) og operativt — alle på vakten har nytte av kø-situasjonen. Full-stats inneholder personvernfølsomme krysstabeller og evalueringsdata som krever fagansvar.

### 12.2 Live-dashbord (12a) — A-nivå-funksjoner

Fire visualiseringer som svarer på "hvordan står det til akkurat nå?":

**A1 — Samtidighetskurve (occupancy)**
- For hvert 15-min bucket fra første `inntid` til nå: tell pasienter hvor `inntid ≤ bucket < utskrevet`
- Implementasjon: event-basert sweep O(n log n) med (tid, ±1)-eventer, sorter, kumulativ sum
- Output: bucket-rader + per-triage-fordeling + peak `{time, count}`
- Visualisering: Chart.js stacked area med rød/gul/grønn

**A2 — Tid-til-behandler (ikke tid-til-triage)**
- Tid fra `inntid` til behandler er **tildelt**. Vi har ikke timestamp-felt på `behandler_id`, men vi har AuditLog
- Tilnærming: første AuditLog-rad per pasient med `field_name='behandler_id'` og `new_value ≠ ''`. Beregn `timestamp - parse(inntid)`
- Edge cases: pasient opprettes med behandler direkte → fallback til `Patient.created_at`. Behandler fjernes og tildeles på nytt → bruk første tildeling
- Output: `{n, mean, median, p90, per_triage}`

**A3 — Gjennomstrømning**
- Bucket `utskrevet` per time. Parallelt bucket `inntid` per time. Plot to serier
- Output: ankomster + utskrevne + akkumulert netto-gap
- Visualisering: grupperte stolper + linje for netto

**A4 — Flaskehalsindikator** (begrenset til 3 reelle tilstander)
- Triage settes umiddelbart ved ankomst, så "venter triage" er ikke en reell tilstand
- "Venter utskrivelse" er fjernet — administrativ mellomtilstand med begrenset operativ verdi
- Tre kategorier blant `utskrevet=''`:
  - **Venter behandling**: `grovsortering!='' AND pabegynt=''`
  - **Under behandling**: `pabegynt!='' AND inn_obspost='' AND utskrevet=''`
  - **På obspost**: `inn_obspost!='' AND ut_obspost=''`
- Output: tilstede_total + tre kategori-tall + heuristiske warnings (f.eks. "venter_behandling > 30 % av tilstede")
- Visualisering: horisontal stacked stolpe med tre farger + store fargede tall

### 12.3 Utvidet evaluering (12b) — B/C/D-nivå-funksjoner

**B-serie (utfall og fordelinger):**
- **B1 Utfallsfordeling** — Sankey eller stacked bar fra triage → utskrevet_til. Anbefaling: stacked bar først, oppgrader til Sankey hvis savnet
- **B2 Behandler-produksjon** — **aggregert, IKKE per individ.** k-anonymitet: kun vis hvis n_behandlere ≥ 3. Output: mean/median pasienter per behandler, P10/P90, ingen mapping til navn. Krever egen personvernvurdering
- **B3 Plasseringsbelastning** — antall + median oppholdstid per plassering, andel av totalt volum
- **B4 Årsak × Problemstilling** — krysstabell, top-10 × top-10, Chi² + Cramér's V
- **B5 Medisiner og lege-konsultasjoner** — andel med `medisiner` / `lege` ikke-tom, fordelt per triage og per top-5 problemstillinger
- **B6 Journal-rate** — andel med `journal` ikke-tom. KPI-kort. Varsel hvis < 90 %

**C-serie (tidsanalyse utvidet):**
- **C1 Boxplot** — Q1/median/Q3/whiskers (1.5·IQR)/outliers. Bruk `chartjs-chart-boxplot`-plugin (~8 KB)
- **C2 Persentiler** — P50, P90, P95 integrert i eksisterende `sd()`-helper

**D-serie (statistiske tester):**
- **D1 Dunn post-hoc** etter signifikant Kruskal-Wallis. Egen 30-linjers implementasjon, IKKE ta inn `scikit-posthocs` for én funksjon
- **D2 Effektstørrelser** — Cramér's V (Chi²) og Epsilon² (KW). Tolkning: <0.1 liten, 0.1–0.3 moderat, >0.3 stor
- **D3 Konfidensintervall** — Wilson CI for andeler, Bootstrap CI for medianer (1000 resamples)
- **D4 Fisher's exact** — kun for 2×2-tabeller med forventede celler < 5. Generalisert r×c Fisher er for treg for polling
- **D5 Forbedret automatisk tolkning** — kombinerer p-verdi, effektstørrelse og n. Eksempler:
  - `p < 0.05, V = 0.35, n = 200` → "Sterk sammenheng. Datagrunnlag solid."
  - `p < 0.05, V = 0.08, n = 2000` → "Statistisk signifikant, men effekten er svak. Praktisk betydning trolig liten."
  - `p = 0.12, V = 0.25, n = 40` → "Ikke signifikant, men observert effekt er moderat. Datagrunnlaget er lite — vi kan ikke utelukke sammenheng."

### 12.4 Faseinndeling (fra implementeringsplanen)

| Fase | Innhold | Estimat |
|---|---|---|
| **1 — Infrastruktur** | `services_stats_live.py`, cache-wrapper, post_save-signal for cache-invalidering, `/api/stats/live/`-endepunkt (tomt skall), AuditLog-indeks, 3–5 smoke-tester | 4–6 t |
| **2 — Live-dashbord (12a)** | A1+A2+A3+A4 + ny "Sanntid"-sub-tab synlig for alle, Chart.js-rendering, tester | 6–8 t |
| **3 — B/C-utvidelser** | B1–B6, C1 boxplot-plugin, C2 persentiler i `sd()` | 6–8 t |
| **4 — Statistiske tester (D)** | D1–D5 + 7 nye krysstabeller (Plassering×Triage, Årsak×Grovsortering, Problemstilling×Medisiner osv.) | 4–6 t |
| **5 — Test og personvern** | Alle tester grønne (mål 240+ totalt), oppdater PERSONVERN_DOKUMENTASJON med B2 + krysstabell-begrensninger, oppdater TEKNISK_DOKUMENTASJON | 3–4 t |
| **6 — Deploy og overvåkning** | Deploy, overvåk CPU/RAM første uke, juster cache-TTL basert på faktisk bruk | 1–2 t |

**Total: ~25–35 timer** spredt over 2–4 uker i fornuftig tempo.

### 12.5 Kritiske forbehold (fra analysen)

1. **B2 må personvernvurderes.** Selv aggregert behandlerstatistikk kan re-identifisere ved få behandlere. Krev k≥3 og ingen histogrammer som kan lekke.
2. **Investér i caching fra dag 1.** Forskjellen på "elegant løsning" og "Railway-overraskelse på regningen". Redis-backenden vi nå har, gjør dette enkelt — bruk `cache.get_or_set()` med 30/60/120 s TTL avhengig av endepunkt.
3. **Hopp over Sankey i første versjon.** Stacked bar gir 80 % av verdien for 10 % av kompleksiteten.
4. **Sett "lite datagrunnlag"-merking når n < 30.** Alle KPI-kort bør ha subtil markering når grunnlaget er tynt.
5. **Polling-frekvens for live-fanen:** med Redis kan 30 brukere × 30 s polling håndteres. Med 30+ brukere, vurder å senke til 60 s for å spare DB-pres.
6. **Lasttest etter Fase 2.** Før Fase 3 deployes, kjør lasttest (se #7 over) for å bekrefte at nye endepunkt ikke degraderer eksisterende.

### 12.6 Åpne avklaringer (fra implementeringsplanen Del 9)

Disse må besvares før kode begynner:

1. **Bekreft tilgangsmodellen** i tabellen over (live = alle innloggede, full = admin/lead/lead_view).
2. **Sankey eller stacked bar for B1?** Anbefaling: stacked bar først.
3. **Er B2 OK med k≥3 aggregat**, eller skal den utelates inntil drøftet med verneombud?
4. **Hvilken fase vil du starte med?** Anbefaling: Fase 1 + smal Fase 2 (kun A1 + A4) som første leveranse for å se reell CPU-påvirkning før vi legger på mer.
5. **Polling-frekvens for live-fanen:** 30 s eller 60 s ved 20+ samtidige brukere?

### 12.7 Akseptansekriterium

- Live-dashbord (Fase 1+2) deployet, alle innloggede ser "Sanntid"-fanen, A1–A4 oppdateres uten manuell refresh
- CPU-bruk i Railway-metrics ikke høyere enn +10 % fra baseline når 20 brukere har fanen åpen
- Cache-hit-ratio for stats-endepunktene > 80 % under aktiv vakt
- Personvern-dokumentet oppdatert med B2-begrensning

---

## 13. Automatisert audit-purge i Procfile/scheduler

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 1–2 timer

**Bakgrunn:** `purge_old_logs`-kommandoen kjører ikke automatisk. AuditLog vokser ubegrenset til noen kjører kommandoen manuelt. 10-års retention er fastsatt, men sletting må skje aktivt.

**Tiltak:**

- Sett opp Railway Cron Job: `0 3 1 * *` (månedlig, 03:00 UTC den 1.) som kjører `python manage.py purge_old_logs`.
- Eller: legg til scheduler-middleware som også kjører purge én gang per døgn (samme mønster som BackupSchedulerMiddleware).
- Logg purge-resultat (antall slettede rader) til AuditLog.

**Akseptansekriterium:** Audit-tabellen vokser ikke ut over forventet rate. Purge-jobb synlig i Railway Cron Jobs.

---

## 14. Kolonne-kryptering for følsomme felter

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 8–12 timer

**Bakgrunn:** Pasientdata lagres i klartekst i Postgres. Kryptering at-rest leveres av Railway på disk-nivå, og kryptering i transitt er TLS. Felt-nivå-kryptering (f.eks. `django-encrypted-fields`) ville gitt ekstra forsvar mot DB-dump-eksponering, men er kompleks (queryability, indekser, nøkkel-rotasjon).

**Tiltak:** Kun ved skjerpet trusselbilde eller eksplisitt behov. Innfører betydelig vedlikeholdslast.

**Akseptansekriterium:** Ikke prioritert.

---

## 15. Aggregere request-metrikker over workers (Redis-tellere) &nbsp;—&nbsp; ✅ IMPLEMENTERT (6. mai 2026)

**Status:** Implementert som **Redis-aggregert liste med LocMem-fallback**. Fungerer transparent i begge driftsmodus:

- **Vakt-modus** (REDIS_URL satt): hver request `LPUSH`-er en JSON-pakket sample (timestamp, path, method, status, duration_ms, pid) til Redis-listen `metrics:requests`. `LTRIM` holder listen på maks 5000 samples. `snapshot()` leser hele listen, filtrerer på vindu, aggregerer på tvers av alle workere.
- **Lavkostnad-modus** (REDIS_URL tom): hopper helt over Redis-vei. `snapshot()` bruker lokal deque — helt korrekte tall siden det bare er én worker.

**Endringer:**
- `patients/middleware.py` — lagt til `_redis_is_available()`, `_get_redis_client()`, `_record_to_redis()`, `_read_from_redis()`, oppdatert `record()` og `snapshot()`. Snapshot returnerer to nye felter:
  - `source` — 'redis' eller 'local' (så admin kan se om aggregering er aktiv)
  - `unique_workers` — antall ulike PID-er som bidro til snapshot (verifiserer at alle workere skriver)
- `patients/tests_admin_status.py` — `MetricsRedisAggregeringTests` (8 nye tester). Mocker Redis-klient, verifiserer aggregering, fallback ved tom Redis, fallback ved lese-feil, vindu-filtrering, og at exceptions ikke lekker.

**Robusthet:** Bruker Pythons `redis`-bibliotek direkte (ikke `django_redis`) siden prosjektet bruker Django sin innebygde `RedisCache`-backend. `socket_timeout=2` og `socket_connect_timeout=2` sikrer at tregt/død Redis ikke henger requesten. Alle Redis-feil fanges — i verste fall faller vi tilbake til lokal deque uten brukermerkbar effekt.

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 2–3 timer (faktisk: ~2 t inkl. tester)

**Bakgrunn:** `RequestMetricsMiddleware` i `patients/middleware.py` lagrer request-metrikker (count, p50, p95, error-rate) i en in-memory `_MetricsStore` (deque med 500 samples). Hver Gunicorn-worker har sin egen instans. Med `WEB_WORKERS=2` viser admin-status-siden tallene fra **kun den workeren som tilfeldigvis svarer på admin-requesten**, ikke summen av begge.

Dette er ikke et trygghets- eller funksjonelt problem — backup, rate-limiting og audit fungerer riktig på tvers av workers (Redis + DB-låser sikrer det). Men diagnoseverktoyet kan vise misvisende tall:

- "Antall requests siste 5 min" lavere enn faktisk
- p95-tider hopper når man refresher (treffer ulike workers)
- 5xx-tellere viser kun den ene workerens feil

Snapshot inkluderer allerede `pid: os.getpid()`, så man kan se hvilken worker som svarte — men det er en kjørelettelse, ikke en løsning.

**Tiltak:**

- Erstatt `_MetricsStore.record()` med Redis-baserte tellere:
  - `INCR pasientregistrering:metrics:requests:5m_bucket:<unix_ts/60>` for telling
  - Sorted set eller list med TTL for varighets-samples
  - `EXPIRE` på buckets (f.eks. 600 s) slik at gamle data droppes
- `snapshot(window_seconds=300)` aggregerer over alle bucket-nøkler i vinduet
- Behold `LocMemCache`-fallback: hvis `REDIS_URL` mangler (lokal/test), fortsett med dagens per-prosess-store
- 4–6 tester: aggregering på tvers av simulerte worker-PIDs, fallback-oppførsel, TTL-utløp

**Akseptansekriterium:** Med 2 workers viser admin-status-siden konsistente tall uavhengig av hvilken worker som svarer. To browser-faner med admin-status på samme tidspunkt viser samme `count`/`rps`/`p95`.

> **Merk:** Lav prioritet. Cosmetic forbedring av diagnoseverktoyet — ikke nødvendig før tallene faktisk forvirrer i drift.

---

## 16. Dokumenter multi-worker-design i TEKNISK_DOKUMENTASJON &nbsp;—&nbsp; ✅ IMPLEMENTERT (6. mai 2026)

**Status:** Kapittel "Multi-worker-design og lavkostnad-modus" lagt til i `TEKNISK_DOKUMENTASJON.md`. Inneholder:
- State-tabell over alle in-memory mekanismer og deres beskyttelse
- Dokumentasjon av lavkostnad- vs vakt-modus (REDIS_URL-flagget styrer alt)
- Beskrivelse av #15 Redis-aggregert metrikker
- Sjekkliste for utviklere som legger til ny global state
- Krysshenvisning til RUNBOOK_VAKT §4

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 30 minutter

**Bakgrunn:** Kodebasen er bevisst designet for flere Gunicorn-workers (Redis-cache, DB-låser, thread-local audit), men dette er ikke samlet beskrevet ett sted. Hvis en fremtidig utvikler legger til ny in-memory state uten å vite om mønsteret, kan det skape subtile bugs når `WEB_WORKERS > 1`.

**Tiltak:**

- Legg til kapittel "Multi-worker-design" i `TEKNISK_DOKUMENTASJON.md` med tabell over hver state-mekanisme:

  | Mekanisme | Hvor | Per-worker eller delt? | Beskyttelse |
  |---|---|---|---|
  | Cache (stats, rate-limit) | `settings.CACHES` | Delt via Redis i prod | `KEY_PREFIX` isolerer |
  | Audit thread-local | `audit/utils.py` | Per-tråd (riktig) | `threading.local()` |
  | Backup-scheduler `_is_running` | `patients/backup_scheduler.py` | Per-prosess | DB-lås (`select_for_update(nowait=True)`) er den ekte beskyttelsen |
  | Request-metrikker `_MetricsStore` | `patients/middleware.py` | Per-prosess | Ikke aggregert (se #15) |
  | Sessions | Database (Django default) | Delt | Postgres som backend |

- Legg til en "Hvis du legger til ny global state"-sjekkliste:
  1. Trenger den å deles mellom workers? → Bruk Redis (`cache.get/set` eller direkte `INCR`)
  2. Er den per-tråd? → Bruk `threading.local()`
  3. Er den per-prosess akseptabel? → Dokumenter eksplisitt hvorfor
  4. Bruker den DB-lås for koordinering? → Foretrekk `select_for_update(nowait=True)` over avhør-loop

- Krysshenvis fra `RUNBOOK_VAKT.md §4 (workers/threads-guide)`.

**Akseptansekriterium:** TEKNISK_DOKUMENTASJON.md har et nytt kapittel som svarer på "er det trygt å øke `WEB_WORKERS`?" uten at man må lese kildekoden.

> **Merk:** Naturlig å ta sammen med #15 — hvis vi flytter metrikker til Redis er det også godt timing for å dokumentere det helhetlige mønsteret.

---

## 17. Rydd opp i Custom Start Command vs Procfile-konflikt på Railway &nbsp;—&nbsp; ✅ AKSEPTERT KOMPROMISS (Alt A delvis)

**Status:** Brukerens beslutning 6. mai 2026: "Vi går for A men lag en notat slik at vi kan se på det senere". Praktisk situasjon i dag:

- **Procfile** holdes versjonskontrollert som single source of truth for `web:`-kommandoen
- **Custom Start Command** beholdes på Railway, men er nå oppdatert til å bruke samme env-variabler (`${WEB_WORKERS:-1}`, `${WEB_THREADS:-4}`) slik at de to ikke divergerer
- Custom Start Command beholder release-fase-prefix (`migrate && createcachetable && collectstatic && create_admin && check_ssl`) fordi en feilende release-blokk i Procfile vil blokkere deploy hardere enn dagens oppførsel — dette ønsker brukeren å vurdere senere
- **Notat for senere vurdering:** Vurdere full overgang til Alt A (tom Custom Start Command, alt i Procfile `release:` + `web:`) når vi har bedre forståelse av hvor strenge release-failures bør være. Krever én stille deploy-testing utenom vakt.

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 30 minutter

**Bakgrunn:** Railway-tjenesten hadde en hardkodet **Custom Start Command** i dashbordet (Settings → Deploy → Custom Start Command) som overstyrte Procfile fullstendig. Den inneholdt `--workers 1 --threads 4` hardkodet, slik at `WEB_WORKERS=2`-env-variabelen ble ignorert i produksjon i lang tid — selv om både Procfile og env-variabel var korrekt satt opp.

Fix ble gjort 30. april 2026 ved å erstatte hardkodede verdier med `${WEB_WORKERS:-1}` og `${WEB_THREADS:-4}` i Custom Start Command.

**Problem:** Nå har vi to konfigurasjonssteder for start-kommandoen:

1. **`Procfile`** (i repo) — lett synlig for utviklere, versjonskontrollert
2. **Custom Start Command** (i Railway-dashbord) — usynlig fra repo, overstyrer Procfile

Dette er en typisk konfigurasjonsfelle. Hvis noen i fremtiden ønsker å endre start-kommandoen og redigerer Procfile, blir endringen ignorert i prod uten advarsel.

**Tiltak — to alternativer:**

### Alternativ A: Tom Custom Start Command, alt i Procfile (renest)

1. Flytt `migrate`, `collectstatic`, `create_admin`, `check_ssl` til `release:`-linjen i Procfile (de tre første er der allerede, kun `create_admin` og `check_ssl` mangler):

   ```
   release: python manage.py migrate --noinput && python manage.py createcachetable && python manage.py collectstatic --noinput && python manage.py create_admin --username $DJANGO_SUPERUSER_USERNAME --password $DJANGO_SUPERUSER_PASSWORD && python manage.py check_ssl
   web: gunicorn myproject.wsgi --workers ${WEB_WORKERS:-1} --threads ${WEB_THREADS:-4} --max-requests ${WEB_MAX_REQUESTS:-1000} --max-requests-jitter 50 --bind 0.0.0.0:$PORT --timeout 60
   ```

2. Tøm Custom Start Command-feltet i Railway-dashbordet helt.

3. Verifiser ny deploy via `railway logs --latest -n 50` — release-fasen skal kjøre alle managment-kommandoer, deretter starter web-prosessen med 2 workers.

**Fordeler:** All konfigurasjon er versjonskontrollert. Én source of truth.  
**Ulemper:** Hvis `release:` feiler (f.eks. `check_ssl`), blokkeres deploy helt — kan være strengere enn dagens "start uansett"-oppførsel.

### Alternativ B: Behold Custom Start Command, slett Procfile

1. Slett `Procfile` fra repo.
2. Behold Custom Start Command som single source of truth.
3. Dokumenter den i `TEKNISK_DOKUMENTASJON.md` med nøyaktig kommando-tekst.

**Fordeler:** Match med dagens fungerende oppsett. Mindre risiko for migrering.  
**Ulemper:** Konfigurasjon er ikke versjonskontrollert. Endringer må gjøres i Railway-UI.

**Anbefaling:** **Alternativ A** — versjonskontrollert konfigurasjon er bedre for langsiktig vedlikehold. Men gjør det på et stille tidspunkt (ikke før vakt).

**Akseptansekriterium:** Endringer i start-kommandoen kan gjøres via git-commit alene (Alt A) eller dokumenteres i ett kjent sted utenfor repo (Alt B). Ikke begge samtidig.

> **Erfaring å huske:** Hvis `WEB_WORKERS`/`WEB_THREADS` eller andre env-variabler ikke ser ut til å trekke i prod, sjekk **Custom Start Command først** (ikke Procfile). Den vinner alltid.

---

## 18. Server-side idempotency for pasient-opprettelse (Fix B)

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** 30. april 2026 ble en pasient registrert dobbelt opp på Grønn sone i prod fordi brukeren dobbeltklikket på "Registrer pasient"-knappen før serveren rakk å svare på første request. På delte soner (Grønn/Gul/blank plassering) finnes ingen unik-sjekk, så begge requests gikk gjennom og skapte to pasienter med forskjellig pasientnummer men identisk inndata.

**Fix A (frontend-side, allerede implementert):** `withSubmitGuard()` i `script.js` disabler knappen umiddelbart, viser spinner og holder lock i minst 250 ms. Beskytter mot dobbeltklikk fra UI.

**Fix A's begrensninger:**

- Beskytter ikke mot **API-klienter** (Postman, curl, malicious script) som sender to raske POST-er
- Beskytter ikke mot **to nettleserfaner** åpne med samme skjema (lock er per-fane)
- Beskytter ikke mot **nettverks-retry** der klient automatisk prøver på nytt etter timeout

**Tiltak — Fix B (server-side idempotency-token):**

### Frontend-endringer

```javascript
// Generer en UUID når nytt-pasient-skjemaet åpnes
function openNew() {
    // ... eksisterende kode ...
    window._currentPatientFormToken = crypto.randomUUID();
    bsNew.show();
}

// Send token med i POST
async function _saveNewImpl() {
    // ... eksisterende kode ...
    const body = {
        // ... eksisterende felter ...
        idempotency_key: window._currentPatientFormToken,
    };
    // ... rest ...
}
```

### Backend-endringer (`patients/views.py`)

```python
from django.core.cache import cache

def _patient_create(request, data):
    # ... eksisterende validering ...

    # Idempotency-sjekk før vi går videre
    idempotency_key = data.get('idempotency_key')
    if idempotency_key:
        cache_key = f'patient_create:{request.user.id}:{idempotency_key}'
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            # Returner samme respons som første gang — idempotent
            return JsonResponse(cached_response, status=200)

    # ... opprett pasient som vanlig ...
    response_data = _patient_to_dict(patient)

    # Lagre respons under token i 5 min
    if idempotency_key:
        cache.set(cache_key, response_data, timeout=300)

    return JsonResponse(response_data, status=201)
```

### Tester (utvider `DoubleClickGuardTests`)

- `test_idempotent_create_returns_same_patient`: To POST-er med samme `idempotency_key` skal returnere samme pasient (kun én opprettet i DB)
- `test_idempotency_token_expires_after_5min`: Etter 5 min skal samme token kunne brukes på nytt (mocket cache)
- `test_no_idempotency_key_falls_back_to_legacy_behavior`: Bakoverkompatibilitet — klienter uten token får dagens oppførsel
- `test_idempotency_key_isolated_per_user`: Bruker A's token kan ikke brukes av bruker B
- `test_concurrent_requests_with_same_token`: To samtidige requests (race) gir kun én pasient — krever DB-lås eller Redis-INCR på token

### Race-condition-håndtering

`cache.get()` + `cache.set()` er ikke atomic. To samtidige requests med samme token kan begge se `None` og begge opprette pasient. Løsning:

```python
# Bruk cache.add() som er atomic (returnerer False hvis nøkkel finnes)
lock_key = f'patient_create_lock:{idempotency_key}'
if not cache.add(lock_key, '1', timeout=10):
    # Annen request er allerede i gang — vent litt og hent svaret
    time.sleep(0.5)
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached, status=200)
    return JsonResponse({'error': 'Prøv på nytt'}, status=409)
```

**Akseptansekriterium:**

1. To raske POST-er fra samme bruker med samme `idempotency_key` skaper kun én pasient
2. Andre POST returnerer same pasient-data med status 200 (ikke 201)
3. Etter 5 min utløper token og kan brukes på nytt
4. Klienter uten `idempotency_key` får dagens oppførsel (bakoverkompatibel)
5. Tester demonstrerer race-håndtering med simulerte samtidige requests

**Risiko ved implementasjon:**

- Krever Redis (allerede på plass i prod)
- Endringer i `patients/views.py` — må deployes utenom vakt-tid
- Cache-feil må graceful fallback til "opprett uansett" (bedre dobbel registrering enn ingen registrering)
- Verifiser at `apiFetch()` ikke retryer automatisk på nettverksfeil og dermed sender token tilbake — hvis den gjør det, må token-respons-cache vare lengre enn typisk retry-intervall

**Anbefalt timing:** Innen 1 måned. Frontend-fixen (Fix A) dekker 99% av reelle scenarioer på vakt; Fix B er forsvar mot API-misbruk og avanserte race conditions.

> **Hvorfor Middels–Høy verdi:** Pasient-data er kritisk og audit-loggen er pr-pasient — dobbel registrering rotter til statistikk og krever manuell sletting. Permanent fix er verdt 2–3 t.

---

## 19. Hindre hopp i pasientnummer-serien ved validerings-feil &nbsp;—&nbsp; ✅ IMPLEMENTERT (3. mai 2026)

**Status:** Løst i samme commit som #20. Implementert som **Alternativ B** (`transaction.atomic`).

**Verdi:** Lav–Middels &nbsp;|&nbsp; **Innsats:** 30 min–1 time

**Bakgrunn:** 2. mai 2026 ble det observert et hopp i pasientnummer-serien fra 125 → 127 i prod. Ettersøking i koden viste at `next_patient_nr()` kalles **før** validering av plassering og andre felter:

```python
# patients/views.py linje 175
nr = next_patient_nr()           # ← telleren økes!
active = get_active_year()

# Linje 180
try:
    validate_plassering_unique(...)  # ← KAN feile
except ValidationError:
    return JsonResponse({...}, status=400)
    # Pasientnummer 126 er nå "brukt opp" i telleren
    # uten at en pasient er opprettet → hopp i serien
```

**Sannsynlige trigger-scenarioer:**

1. Bruker prøver å registrere pasient på opptatt Rød/Blå sone-plassering → plassering-validering feiler
2. Tids-felt skrevet i feil format → tids-validering feiler
3. Annen exception under behandler/helsepersonell-oppslag eller `patient.save()`

**Funksjonell innvirkning:** Ingen — pasienter får fortsatt unike nummer, ingen data går tapt. Men:

- Estetisk merkelig for brukere som ser hull i nummerserien
- Statistikk-rapporter som teller "pasienter behandlet" via nummer-range blir misvisende
- Kan skape forvirring i kvalitetskontroll/audit ("hvor er pasient 126?")

**Tiltak — to alternativer:**

### Alternativ A: Flytt `next_patient_nr()` til etter all validering (anbefalt, enkel)

```python
# patients/views.py i POST-handler

# 1. Valider ALT først
try:
    validate_patient_time_fields(data)
except ValidationError as exc:
    return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

active = get_active_year()

try:
    validate_plassering_unique(data.get('plassering', ''), active)
except ValidationError as exc:
    return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

# Konverter behandler/helsepersonell-ID-er
behandler_obj = ...
helsepersonell_obj = ...

# 2. DERETTER hent nummer (alt nå validert OK)
nr = next_patient_nr()

# 3. Opprett pasient
patient = Patient(pasientnummer=nr, ...)
patient.save()
```

**Fordeler:** Liten endring (flytter én linje), svak innvirkning på eksisterende kode  
**Ulemper:** Hvis `patient.save()` selv kaster (sjeldent: DB-feil), kan det fortsatt skje hopp — men da er hoppet symptom på ekte DB-problem som bør logges og varsles

### Alternativ B: Wrappe alt i `transaction.atomic()` med rollback (sterkest)

```python
with transaction.atomic():
    nr = next_patient_nr()  # tellerinkrement
    patient = Patient(pasientnummer=nr, ...)
    patient.save()
    # Hvis ANYthing kaster i blokken, rulles BEGGE deler tilbake
```

**Fordeler:** 100% garantert ingen hopp — enten lykkes alt eller intet  
**Ulemper:** Holder DB-rad-låsen på `AppSetting('next_patient_nr')` lenger (under hele requesten, inkl. behandler-oppslag, save osv.). Ved høy last kan dette skape kontensjon mellom samtidige registreringer — men i praksis er last på sanitetsvakt så lav at det ikke er målbart.

### Tester (utvider eksisterende suite)

- `test_invalid_plassering_does_not_increment_nr`: POST med opptatt plassering returnerer 400 og tellerstand er uændret
- `test_invalid_time_does_not_increment_nr`: POST med ugyldig tids-felt returnerer 400 og tellerstand er uændret
- `test_successful_create_increments_by_one`: To påfolgende vellykkede registreringer får nr N og N+1 (ingen hopp)
- `test_db_error_during_save_rolls_back_counter` (kun Alt B): Mock `patient.save()` til å kaste, verifiser at telleren er rullet tilbake

**Akseptansekriterium:** Etter fixen skaper en validerings-feil under POST `/api/patients/` ikke et hopp i nummerserien. Telleren oppdateres kun ved vellykket lagring.

**Anbefaling:** **Alternativ A** — enkel, løser 99% av tilfellene, lav risiko. Alternativ B kan vurderes senere hvis vi ser ekte DB-feil-relaterte hopp i loggen.

> **Merk:** Ikke akutt. Funksjonelt korrekt oppførsel — bare estetisk forvirrende. Sammenlignbart med SQL auto-increment som hopper over ID-er ved rollback.

**Implementert løsning (3. mai 2026):**
- Plassering-validering flyttet til **før** `next_patient_nr()` (Alt A-del)
- Pasient-opprettelse pakket i `transaction.atomic()` (Alt B-del) — inkludert nummer-tildeling, slik at en eventuell `save()`-feil ruller tilbake telleren
- Tester: `PatientNumberGapTests` (2 tester)

---

## 20. Klokkedrift mellom klient og server (pabegynt < inntid) &nbsp;—&nbsp; ✅ IMPLEMENTERT (3. mai 2026)

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 1 time (gjort)

**Bakgrunn:** 3. mai 2026 oppdaget bruker at `pabegynt` i mange tilfeller var **før** `inntid` — fra 1 minutt til 8 minutter avhengig av hvilken klient som registrerte. Dette gir negative ventetider i statistikken og er klinisk meningsløst.

**Rotårsak:** Frontend (`script.js` linje 505) bruker klient-PCens klokke som fallback for `inntid`:
```js
inntid: document.getElementById('n-inntid').value || nowStr()
// nowStr() = new Date() i nettleseren
```
Server derimot stempler `pabegynt` med sin egen `datetime.now()` når behandler-felt fylles ut. Klient-PCer som ikke er NTP-synkronisert kan drive flere minutter foran serveren, og resultatet blir at `pabegynt` (server) < `inntid` (klient).

I tillegg ble det avdekket at `datetime.now()` i Django-koden ikke honorerer `TIME_ZONE='Europe/Oslo'` — den returnerer naiv container-lokaltid (UTC på Railway). Selv om dette ikke var årsaken til konkrete observerte tilfeller, er det en latent bug som ville slått inn ved enhver fremtidig endring av container-TZ.

**Implementert løsning:**

1. **Ny helper `now_local_str()` i `services.py`** — bruker `django.utils.timezone.localtime(timezone.now())` for å garantere Europe/Oslo uavhengig av container-TZ
2. **Erstattet alle `datetime.now().strftime(...)`** i `stamp_pabegynt_if_needed`, `stamp_obs_times_if_needed`, `stamp_utskrevet_if_needed` med `now_local_str()`
3. **Én felles tidsstempel per request** — `views.py` legger `data['_now_str']` tidlig, alle stamp-funksjoner leser fra samme verdi (hindrer mikrodrift mellom kall i samme request)
4. **Blank-fallback for inntid** — endret fra `data.get('inntid', now)` til `data.get('inntid') or now_str` (håndterer også tom streng, ikke bare manglende nøkkel)
5. **Sikkerhetsnett `_ensure_pabegynt_not_before_inntid()` i `views.py`** — hvis `pabegynt < inntid` (f.eks. på grunn av klient-klokkedrift), justeres `pabegynt` opp til `inntid`. Kalles i både POST og PUT.

**Tester (lagt til i `tests.py`):**
- `PabegyntNotBeforeInntidTests` (5 tester) — unit + end-to-end
- `BlankInntidFallbackTests` (1 test) — verifiserer server-now-fallback
- `NowLocalStrTests` (2 tester) — format og TZ-respekt

**Endrede filer:**
- `patients/services.py` — ny `now_local_str()`, oppdaterte stamp-funksjoner
- `patients/views.py` — ny `_ensure_pabegynt_not_before_inntid`, oppdaterte POST og PUT
- `patients/tests.py` — ~110 nye linjer med tester

**Effekt på historiske data:** Eksisterende rader med `pabegynt < inntid` blir ikke automatisk korrigert — fixen virker kun fremover. Hvis vi senere vil rydde i historisk data, kan en management command kjøre samme logikk over hele `Patient`-tabellen (vurderes som egen, valgfri oppgave).

---

## Avsluttede / løste forslag (referansegrunnlag)

Disse er allerede gjennomført og listes for sporbarhet:

| Tittel | Status |
|---|---|
| Sentry-integrasjon | Avbrutt etter brukerens valg — fullstendig fjernet |
| Redis for delt cache | Implementert og verifisert (April 2026) |
| `_scrub_secrets()` helper | Implementert (5 tester) |
| Workers/threads parametrisering | Implementert via `Procfile` env-variabler |
| Plassering-bug fix (front + back) | Implementert + 4 nye tester |
| Admin-sesjonshåndtering (force logout) | Implementert (16 tester) |
| CSRF-bug i admin-status | Fikset (lokal `_getCsrfToken()` i admin_status.html) |
| Stats-cache failsafe (try/except) | Implementert |
| Cache-helsesjekk i admin-dashbord | Implementert |
| RUNBOOK §4 (workers/threads-guide) | Implementert |
| Backup-kort i admin-dashbord | Bug fikset (filter på ikke-eksisterende `status`-felt) + 4 tester |
| Live-stats feature-flag default | Endret til `'false'` siden funksjonen ikke er implementert |
| Beredskap-tabell i admin-status | Synkronisert med RUNBOOK §2 (P95-terskler, Redis-krav) |

---

> **Vedlikehold av dette dokumentet:** Når et forslag er gjennomført, flytt det fra "matrise" og hovedseksjon ned til "Avsluttede". Når nye forslag dukker opp i samtaler, legg dem til med rangering. Hold dokumentet kort — ikke list alle "kunne være fint" — kun det som faktisk vurderes.
