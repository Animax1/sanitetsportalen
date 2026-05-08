# Runbook – Beredskap under vakt

Konkrete handlingsregler når pasientregistreringssystemet er under belastning.
**Ingen improvisasjon under stress** – følg tabellen nedenfor.

---

## 1. Første ting før vakten starter

1. **Admin-dashbord åpent i egen fane**: [https://\<din-app\>.railway.app/admin/server-status/](#)
2. **Railway-dashbord åpent i egen fane**: [https://railway.app](https://railway.app) → ditt prosjekt → Variables
3. **Denne runbooken tilgjengelig** (skriv ut eller hold på annen skjerm)
4. Sjekk at dashbordet oppdaterer seg (grønn pulserende prikk, "Oppdaterer hvert 10. sek")
5. Bekreft at "Siste backup" er < 30 min gammel
6. Noter start-tidspunkt og bakgrunns-rps som baseline (typisk 0.1–0.3 req/s ved oppstart)

### 1b. Driftsmodus — lavkostnad mellom vakter, vakt-modus før vakt

Appen kjøres i to ulike modus styrt av én env-variabel: `REDIS_URL`. Standardtilstand mellom vakter er **lavkostnad-modus** (1 worker, Redis frakoblet, LocMemCache). Før hver vakt veksles til **vakt-modus** (2 workers + Redis aktivt). Etter vakt veksles tilbake.

| Modus | `REDIS_URL` | `WEB_WORKERS` | Cache | Når |
|---|---|---|---|---|
| **Lavkostnad** (default) | tom / fjernet | 1 | LocMemCache | Mellom vakter |
| **Vakt-modus** | satt til Redis-tjenestens variabel-referanse | 2 | RedisCache | Før og under vakt |

Kodebasen bytter automatisk — ingen kodeendring, ingen migrasjon. Detaljer i `TEKNISK_DOKUMENTASJON.md` §8E.

### 1c. Aktiver vakt-modus (gjør dagen før eller minst 1 time før vakt-start)

#### Steg 1: Slå på Redis-tjenesten på Railway

Hvis Redis-tjenesten allerede eksisterer i prosjektet, men er pauset:

1. Railway-dashbord → åpne prosjekt → klikk Redis-tjenesten i ressurs-listen
2. Hvis tjenesten er pauset: øverst høyre → "Start" / "Resume" → vent til status blir "Active" (~30 sek)

Hvis Redis-tjenesten ikke finnes:

1. Railway-prosjekt → øverst høyre "+ New" → **Database** → **Add Redis**
2. Vent til tjenesten er provisjonert (~1–2 min)

#### Steg 2: Koble web-tjenesten til Redis

1. Railway-prosjekt → klikk **web**-tjenesten
2. Faneblad **Variables** → finn `REDIS_URL` (eller "+ New Variable" hvis den ikke er der)
3. Klikk pencil-ikon → erstatt verdi med en **Reference Variable**:
   - Klikk "+ Add Reference" → velg Redis-tjenesten → velg `REDIS_URL`
   - Resultatet skal være noe som `${{Redis.REDIS_URL}}`
4. **Save** — web-tjenesten redeployer automatisk (~60 sek)

#### Steg 3: Sett 2 workers

1. Web-tjenesten → **Variables**
2. `WEB_WORKERS` → endre til `2` → Save
3. Triggeren ny redeploy automatisk

#### Steg 4: Verifiser i admin-dashbord

Når ny deploy er live (sjekk Deployments → siste "Active"):

1. Åpne `https://<din-app>.railway.app/admin/server-status/`
2. **Cache-backend-kort** skal vise:
   - Backend: `redis`
   - Status: healthy
   - Latency: < 10 ms (typisk 1–3 ms intern Railway-Redis)
3. **Worker-konfig-kort** skal vise:
   - `WEB_WORKERS = 2`
   - Antall faktiske Gunicorn-prosesser: minst 2
4. **Metrikk-kortene** (etter litt trafikk) — felter `metrics_5min.source` og `metrics_1min.source`:
   - Skal vise `'redis'` når aggregering er live
   - `unique_workers` skal høynes til 2 etter at begge workere har fått requests
5. **Test rate-limit funker delt**: prøv 11 mislykkede innlogginger — du skal låses ute uavhengig av hvilken worker som svarer.

#### Steg 5 (valgfritt): Vurder Pro-plan

Hvis du venter 20+ samtidige brukere: Railway-prosjekt → Settings → Plan → oppgrader til Pro. Kan nedgraderes igjen rett etter vakt (proratert billing).

**Hvorfor:** Med 2+ workere uten Redis blir rate-limit-telleren per-prosess (effektivt doblet), stats-cache fragmentert og request-metrikker viser bare én workers tall. Vakt-modus fikser alle tre.

---

## 2. Terskler og handlinger

Les av **P95** (Responstid siste 5 min → P95) på dashbordet. Dette er det viktigste tallet.

| P95 responstid | 5xx-feil | Tiltak |
|---|---|---|
| < 300 ms | 0 | **Grønt.** Ingen endring. Fortsett å observere. |
| 300–500 ms | 0 | **Gult.** Observer. Hvis vedvarer > 15 min, gjør nedbremsing (steg 3). |
| 500–1000 ms | 0 eller 1–2 | **Oransje.** Oppgrader til 2 workers (steg 4). |
| > 1000 ms | ≥ 3 | **Rødt.** Oppgrader til 2 workers + 6 threads (steg 5). |
| Systemet tregt etter alle tiltak | Vedvarende 5xx | **Kritisk.** Skru av live-statistikk (steg 6) og/eller nødbrems rate-limit (steg 7). |

---

## 3. Nedbremsing klientside (lett tiltak)

Hvis P95 ligger på 300–500 ms vedvarende, reduser polling-trykket:

1. Be brukere lukke faner de ikke aktivt trenger
2. Be leads lukke statistikk-fanen mellom oppslag
3. Hvis du har live-statistikk implementert: skru den av via dashbord → "Feature-flagg" → "Live statistikk" → `false`
4. **Logg ut inaktive brukere via dashbordet** (steg 3b). Hver aktiv sesjon koster minne og polling – å frigjøre glemt-innloggede faner gir umiddelbar effekt uten redeploy.

Ingen redeploy trengs.

---

## 3b. Logg ut brukere via dashbordet

**Når:** Du ser flere påloggede brukere enn det reelt er aktivt personell, eller du trenger å frigjøre ressurser raskt.

1. Admin-dashbord → “Aktive sesjoner”-kortet
2. Listen viser alle påloggede brukere med rolle
3. **Per bruker:** trykk “Logg ut” ved siden av navnet → bekreft
4. **Nødbrems (alle):** trykk “Nødbrems: logg ut alle (unntatt meg)” nederst i kortet → bekreft
   - Din egen sesjon påvirkes ikke
   - Alle andre må logge inn på nytt
   - Handlingen logges i AuditLog

**Effekt:** Sesjoner slettes umiddelbart fra databasen. Når brukerne prøver neste handling, omdirigeres de til innloggingsskjerm. Ingen redeploy.

**Når IKKE bruke nødbremsen:** Under aktiv pasientregistrering der personellet jobber. Sesjonsutlogging midt i registrering kan føre til at en pågående lagring går tapt. Bruk per-bruker-utlogging der du har oversikt.

---

## 4. Workers og threads — styring og tuning

### Hva er det?

- **Workers** = separate Python-prosesser. Egen minne, egen DB-pool. Hvis én krasjer, fortsetter de andre.
- **Threads** = parallelle spor inne i én worker. Deler minne. Bytter aktivt ved I/O-venting (DB-spørringer).
- **Total samtidig kapasitet** = workers × threads.

### Anbefalt konfigurasjon etter forventet last

| Samtidige aktive brukere | `WEB_WORKERS` | `WEB_THREADS` | Total kapasitet |
|---|---|---|---|
| 1–5 | 1 | 4 | 4 requests |
| 5–15 | 2 | 4 | 8 requests |
| 15–30 | 2–3 | 4 | 8–12 requests |
| 30–60 | 3–4 | 4 | 12–16 requests |
| 60+ | 4+ | 4 | 16+ requests (vurder Pro-plan) |

**Tommelfingerregel:** ca. 5–8 samtidige brukere per worker for denne appen. Workers gir mest gevinst; threads er mindre viktig (behold default 4).

### Slik endrer du verdiene

1. Railway → web-tjenesten → **Variables**
2. Sett `WEB_WORKERS` (og evt. `WEB_THREADS`) til ny verdi
3. **Save** → automatisk redeploy (~60 sek)
4. Verifiser i admin-dashbord → Worker-konfig-kortet viser ny verdi

Ingen kodeendring eller git-push nødvendig. Verdiene leses av Procfile ved hver oppstart.

### Krav før du øker workers ≥ 2

**Cache-backend MÅ være Redis** før du øker workers. Med LocMemCache + 2+ workers blir:

- Rate-limit-grensen effektivt doblet per worker
- Stats-cache fragmentert (lavere hit-rate, høyere DB-last)
- Innloggings-blokkering inkonsistent

**Sjekk først** i admin-dashbord at Cache-backend-kortet viser `REDIS / OK`. Hvis det viser `LOCMEM`, se seksjon 11 om Redis-aktivering først.

### Konsekvenser når du øker workers

**Det som funker automatisk:**
- PostgreSQL-tilkoblinger (~4 per worker, full pool er ~12 ved 3 workers — langt under DB-grensen)
- Sesjoner (lagret i DB, deles automatisk)
- Backup-scheduler (advisory lock i DB sørger for at kun én worker kjører)
- Rate-limit og stats-cache (delt via Redis)

**Det du må være obs på:**
- **RequestMetrics** i admin er per-prosess. Med 2 workers ser du metrikker fra én worker av gangen, og hvilken varierer mellom polls. RPS og latency kan hoppe litt — dette er normalt og betyr IKKE at appen har problemer.
- **Memory-bruk øker lineært:** ~60–150 MB per worker. 2 workers ~300 MB peak, 3 workers ~450 MB. Hobby-planen har 8 GB — ikke et problem før 20+ workers.
- **Oppstartstid:** 2 workers ~30 sek, 4 workers ~50 sek.

### Når skal du øke i løpet av en vakt?

**Når:** P95 500–1000 ms eller 5xx begynner å dukke opp i admin-dashbord.

**Steg:**
1. Åpne Railway → web-tjenesten → Variables
2. Sett `WEB_WORKERS` til én høyere enn nåværende verdi
3. Save → vent 60 sek
4. Observer P95 i 3 minutter → skal falle

Gjør kun én endring av gangen. Hvis P95 ikke faller, er problemet noe annet enn worker-kapasitet (sjekk DB, Redis, eller eksterne tjenester).

### Maks på Hobby-planen

- Realistisk maks: **4–5 workers**. Over det gir delt CPU lite gevinst.
- For høyere kapasitet: oppgrader til Pro-planen ($20/mnd, dedikert CPU). Kan downgrades igjen etter vakt.

---

## 5. Tyngre skalering (reserveplan)

**Når:** Steg 4 hjalp ikke tilstrekkelig. P95 fortsatt > 1000 ms.

1. Railway → Variables
2. `WEB_WORKERS` = `2`
3. `WEB_THREADS` = `6`
4. Save → redeploy

Total samtidig request-kapasitet: 2 × 6 = 12. RAM ~400–450 MB.

---

## 6. Skru av live-statistikk (feature-flag)

**Når:** Under høy last og du vil redusere polling-trafikk umiddelbart.

1. Admin-dashbord → "Feature-flagg"-kortet
2. Send en POST til `/admin/server-status/flag/` med `key=feature.live_stats_enabled`, `value=false` (eller bruk UI-knapp hvis lagt til senere)
3. Effekt: live-statistikk-fanen (hvis bygget) skjules for ikke-admin-brukere umiddelbart ved neste request. Ingen redeploy.

**Revert:** samme flagg → `true`.

---

## 7. Nødbrems rate-limit (siste utvei)

**Kun når:** Rate-limiting selv er årsaken til feil (401/429), ikke CPU/minne-problemer.

1. Railway → Variables
2. `RATELIMIT_ENABLE` = `false`
3. Save → redeploy

**VIKTIG:** Husk å sette tilbake til `true` så snart krisen er over. Permanent av = brute-force-sårbarhet.

---

## 8. Database-problemer

Symptomer: P95 stiger samtidig i alle endepunkter, 5xx med database errors i logs.

1. Sjekk Railway PostgreSQL → Metrics → CPU / Connections
2. Hvis CPU > 80 % vedvarende: PostgreSQL-instansen må oppgraderes (kontakt Railway-support eller oppgrader plan – ikke noe du ordner i løpet av minutter)
3. Hvis Connections nær maks: restart web-service en gang (Railway → Deployments → Redeploy) for å frigjøre lekkede koblinger

---

## 9. Hvis alt annet feiler: last-shed

Som absolutt siste utvei hvis systemet er utilgjengelig:

1. Meld fra til brukerne at de må registrere manuelt på papir
2. Redeploy med `DEBUG=true` midlertidig for bedre feilmeldinger i logs
3. Bruk offline-pakken på USB (se `OFFLINE_GUIDE.md`) som backup-registreringssystem

---

## 10. Etter vakten — tilbake til lavkostnad-modus

### 10a. Avlesning og bevaring

1. Gå gjennom admin-dashbord – noter peak P95, peak RPS, peak memory og antall samtidige sesjoner
2. Last ned siste backup fra Railway Volume (`/data/backups/`) som ekstern kopi
3. Verifiser at ingen 5xx-feil ligger uten forklaring (admin-dashbord → Metrikk-kort → errors_5xx)

### 10b. Veksle tilbake til lavkostnad-modus

#### Steg 1: Reduser web-tjenesten til 1 worker

1. Railway → web-tjenesten → **Variables**
2. `WEB_WORKERS` → endre til `1` (eller slett variabelen — default er 1)
3. **Save** — redeploy starter automatisk

#### Steg 2: Koble fra Redis (gjør etter steg 1 er live)

1. Railway → web-tjenesten → **Variables**
2. `REDIS_URL` → to alternativer:
   - **Anbefalt:** Klikk pencil → erstatt referanse-verdien med en tom streng `""` → Save. Dette beholder navnet på variabelen som dokumentasjon.
   - **Alternativ:** Slett variabelen helt med x-knapp → Save.
3. Web-tjenesten redeployer automatisk. Etter ~60 sek skal admin-dashbord vise:
   - Cache-backend: `locmem`
   - Worker-konfig: 1 worker

#### Steg 3: Pause Redis-tjenesten (sparer kostnad)

1. Railway → klikk Redis-tjenesten
2. Øverst høyre → **Pause Service** (eller "Stop")
3. Tjenesten beholder data og konfigurasjon, men slutter å belaste timer-pris. Restartes med ett klikk før neste vakt.

**Ikke-anbefalt:** Slett Redis-tjenesten helt med mindre du er sikker på at du ikke trenger den på lengre tid. Sletting tar bort tjenesten fra prosjektet, og du må opprette ny + sette opp variabel-referanse på nytt før neste vakt. Pause er nesten gratis og bevarer alt oppsett.

#### Steg 4: Verifiser at lavkostnad-modus er live

1. Åpne admin-dashbord etter ny deploy
2. Bekreft:
   - Cache-backend: `locmem`, healthy
   - Worker-konfig: `WEB_WORKERS = 1`
   - Metrikk-kort: `source = 'local'` (forventet siden Redis er av)
3. Prøv en vanlig pasient-flow (login, opprett dummy, slett) for å bekrefte at appen fungerer i lavkostnad-modus

### 10c. Andre opprydding

1. Sett variabler tilbake til default hvis du endret noe:
   - `WEB_THREADS` → fjern (default 4)
   - `RATELIMIT_ENABLE` → `true`
   - Feature-flag `feature.live_stats_enabled` → `false` (default; funksjonen er ikke implementert ennå)
2. Hvis du oppgraderte til Pro-plan: Settings → Plan → nedgrader til Hobby (proratert billing)
3. Noter erfaringer i en kort logg (dato, antall pasienter, peak-tall, eventuelle tiltak)

---

## 11. Når trenger jeg å tenke på skalering?

### Anbefalt oppsett etter forventet last

| Samtidige brukere | Workers | Cache | Plan |
|---|---|---|---|
| 1–10 | 1 | LocMemCache | Hobby |
| 10–20 | 2 | **Redis** | Hobby |
| 20–40 | 2–3 | **Redis** | Hobby/Pro |
| 40–100 | 3–4 | **Redis** | Pro |
| 100–300 | 4+ | **Redis** | Pro + ev. egen DB |

**Tommelfingerregel:** ca. 5–10 samtidige brukere per worker for typisk Django-webapp.

### Hvorfor Redis når workers ≥ 2

LocMemCache er per-prosess. Med 2+ workers blir:

- **Rate-limit-tellere fragmentert** — grensen for innloggings-forsøk effektivt dobles per worker. En angriper kan få dobbelt så mange forsøk.
- **Stats-cache regnes per worker** — hver worker bygger sin egen cache, lavere hit-rate, mer DB-last.
- **Admin-dashbord viser inkonsistente metrikker** — hver worker rapporterte tidligere bare sine egne tall.

Redis fikser alle tre i vakt-modus. Request-metrikker aggregeres nå også via Redis (FORBEDRINGER #15) — admin-dashbordet viser cluster-wide tall når Redis er aktivt, og felter `source` og `unique_workers` bekrefter at aggregering er live.

### Aktivering av Redis (innebygd i koden fra v.X)

Koden støtter allerede Redis. Aktivering krever **kun** å opprette tjenesten på Railway — ingen kodeendring eller deploy er nødvendig.

1. Railway → **Add Service** → **Database** → **Redis** (~$5/mnd)
2. Railway setter `REDIS_URL` automatisk som miljøvariabel på web-tjenesten
3. Web-tjenesten redeployer automatisk (ca. 60 sek)
4. Verifiser i admin-dashbord → Cache-backend-kort skal vise `REDIS / OK`

**Slik fungerer fallback:** Hvis `REDIS_URL` ikke er satt (lokal utvikling, eller Redis-tjenesten er fjernet), faller systemet automatisk tilbake til LocMemCache. Ingen feilmeldinger, ingen krasj.

**Hvis Redis går ned midt i en vakt:** Django sin innebygde `RedisCache` har IKKE en innebygd `IGNORE_EXCEPTIONS`-option (det var en `django-redis`-feature). Vi har derfor app-spesifikke try/except rundt cache-operasjoner som tråkker tyngst:
- `patients/stats_cache.py` fanger alle cache-feil og regner statistikk direkte ved utfall
- `django-ratelimit` failopener av seg selv ved cache-feil (slipper requests gjennom)
- `_get_cache_health()` rapporterer `healthy=false` på admin-dashbord uten å kaste
- `RequestMetricsMiddleware` har bred try/except rundt både Redis-skriving og -lesing — faller stille tilbake til lokal deque

Noen sjeldne kodeveier (sesjon-relatert når Django selv treffer cache) kan kaste 500 — men hovedfunksjonen i appen står.

**Fiks ved Redis-utfall midt i vakt:** Restart Redis-tjenesten i Railway-dashbordet (klikk tjenesten → Settings → Restart), eller — hvis det haster og Redis ikke kommer opp — sett `REDIS_URL` til tom streng på web-tjenesten og redeploy. Det tvinger app til lavkostnad-modus midt i vakten. Du mister Redis-aggregert statistikk og delt rate-limit, men appen er stabil.

Forventet effekt med Redis aktivt: konsistent rate-limiting på tvers av workers, delt stats-cache (høyere hit-rate), og en solid plattform for 100–300 samtidige brukere.

---

## 12. Kontaktinfo og lenker

| Ressurs | Lenke/handling |
|---|---|
| Admin server-status | `https://<din-app>.railway.app/admin/server-status/` |
| Railway-dashbord | [https://railway.app](https://railway.app) |
| Railway Volume backups | Railway → Volumes → Browse |
| Django Admin | `https://<din-app>.railway.app/django-admin/` |
| Offline-guide | `OFFLINE_GUIDE.md` i repoet |
| Deploy-guide | `DEPLOY_GUIDE.md` i repoet |

---

## 13. Feilfinning i prod (uten Sentry)

Applikasjonen bruker IKKE en ekstern feilsporings-tjeneste. Feilsøking
skjer via to kilder:

### Railway-loggen (sanntid)

1. Railway → web-tjenesten → fanen **Logs** (eller **Service Logs** i nyere UI)
2. Filtrer på tid eller søkeord (`ERROR`, `Traceback`, `500`)
3. Stack-traces fra ubehandlede exceptions vises her i full lengde

### Admin-dashbord (/admin/server-status/)

1. **Feilteller** – antall 4xx/5xx siste 5/15/60 min
2. **Sist sette feil** – endepunkt, tidspunkt og status-kode
3. **AuditLog** (Django-admin) – hver feilet handling på pasient/bruker logges

### Vakt-prosedyre når en bruker rapporterer feil

1. Spør bruker om nøyaktig tidspunkt og hva de prøvde å gjøre
2. Sjekk admin-dashbord → Feilteller stiger? Match tidspunktet i "Sist sette feil"
3. Åpne Railway-logg → filtrer på tidspunkt ± 1 minutt → let etter `Traceback`
4. Stack-trace viser fil + linjenummer der feilen oppstod

---

## Vedlegg – tolkning av dashbord-tall

**Requests/sek (1 min)**
- < 1: stille periode
- 1–3: normal belastning
- 3–5: høy belastning (peak under arrangement)
- > 5: svært høy – sjekk P95

**Responstid P95 (5 min)**
- Det tallet 95 % av requests ligger UNDER. Mer representativt enn snitt fordi det fanger halen.

**Aktive sesjoner**
- Antall unike pålogginger som ikke har utløpt. Gir deg et pålitelig estimat på samtidige brukere (selv om noen kan ha flere faner).

**Minne (RSS)**
- 1 worker: normal 60–150 MB
- 2 workers: ~300 MB total. Over 800 MB totalt per worker = vurder å starte workeren på nytt.
- 3 workers: ~450 MB total.

**Cache-backend**
- `REDIS / OK`: delt cache aktiv, trygt å kjøre med 2+ workers
- `LOCMEM`: per-prosess cache, OK kun ved 1 worker
- `FEIL`: cache er nede, sjekk Redis-tjenestens status i Railway

**Worker-konfig**
- Viser nåværende `WEB_WORKERS` og `WEB_THREADS`. Match med ditt tiltenkte oppsett (se seksjon 4).

**Siste backup**
- Skal være < 35 min gammel (backup-schedule er 30 min + litt slakk)
- > 60 min: sjekk Railway Volume og backup-siden

---

*Sist oppdatert: 26.04.2026*
