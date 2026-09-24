# Runbook – Beredskap under vakt

Konkrete handlingsregler når pasientregistreringssystemet er under belastning.
**Ingen improvisasjon under stress** – følg tabellen nedenfor.

---

## 1. Første ting før vakten starter

1. **Admin-dashbord åpent i egen fane**: [https://\<din-app\>.railway.app/portal-admin/server-status/](#)
2. **Railway-dashbord åpent i egen fane**: [https://railway.app](https://railway.app) → ditt prosjekt → Variables
3. **Denne runbooken tilgjengelig** (skriv ut eller hold på annen skjerm)
4. Sjekk at dashbordet oppdaterer seg (grønn pulserende prikk, "Oppdaterer hvert 10. sek")
5. Bekreft at "Siste backup" er < 30 min gammel
6. Noter start-tidspunkt og bakgrunns-rps som baseline (typisk 0.1–0.3 req/s ved oppstart)
7. **Ingen deploy fra nå til vakta er over.** Noter byggnummeret i footeren, så du vet hva
   som kjører hvis noe ser rart ut. Må du likevel deploye: §8c

### 1b. Driftsmodus — lavkostnad mellom vakter, vakt-modus før vakt

Appen kjøres i to ulike modus styrt av én env-variabel: `REDIS_URL`. Standardtilstand mellom vakter er **lavkostnad-modus** (1 worker, Redis frakoblet, LocMemCache). Før hver vakt veksles til **vakt-modus** (Railway Pro, 2 workers × 4 tråder, Redis aktivt). Etter vakt veksles tilbake.

| Modus | `REDIS_URL` | `WEB_WORKERS` × `WEB_THREADS` | Cache | Plan | Når |
|---|---|---|---|---|---|
| **Lavkostnad** (default) | tom / fjernet | 1 × 4 | LocMemCache | Hobby | Mellom vakter |
| **Vakt-modus** | satt til Redis-tjenestens variabel-referanse | **2 × 4** | RedisCache | **Pro** | Før og under vakt |

**Vakt-modus er grunnlinja tiltakene i §2 regnes fra** (24. sep. 2026). Til da regnet
tabellen fra 1 worker, og «oransje: oppgrader til 2 workers» var et tiltak som alt var
gjort. Dashbordet viser hvilken modus som faktisk kjører — «Worker-konfigurasjon»-kortet
sier «Vakt-modus: 2 workers, Redis OK», og rødt hvis det står 2+ workers uten Redis.

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

1. Åpne `https://<din-app>.railway.app/portal-admin/server-status/`
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

#### Steg 5: Railway Pro

Railway-prosjekt → Settings → Plan → **Pro**. Del av vakt-modus (André, 24. sep. 2026), ikke
et valg: tiltakene i §2 går til 3 og 4 workers, og det er på Pro de gir noe. Nedgraderes
etter vakt (§10c, proratert billing).

**Hvorfor:** Med 2+ workere uten Redis blir rate-limit-telleren per-prosess (effektivt doblet), stats-cache fragmentert og request-metrikker viser bare én workers tall. Vakt-modus fikser alle tre.

---

## 2. Terskler og handlinger

Les av **P95** — det store tallet på «Responstid siste 5 min». Kortet viser også trinnet
og tiltaket, regnet av `beredskapsnivaa()` i `core/admin_status.py`. **Tabellen under og
tabellen nederst på dashbordet er samme liste** (`BEREDSKAPSTRINN`); en test holder dem
i takt.

**Regnet fra vakt-modus: 2 workers × 4 tråder, Redis, Pro.** Det høyeste trinnet der
enten P95 eller 5xx har nådd grensen, gjelder — 5xx alene kan gi rødt.

| Trinn | P95 / 5xx siste 5 min | Tiltak |
|---|---|---|
| **Grønt** | < 300 ms, 0 feil | Ingen endring. Fortsett å observere. |
| **Gult** | 300–500 ms, 0 feil | Observer, og se «Tregeste stier». Varer det over 15 min: nedbremsing (§3). |
| **Oransje** | 500–1000 ms, eller 1–2 5xx | Se «Tregeste stier» og «Database» først — er databasen treg, hjelper ikke flere workers (§8). Ellers `WEB_WORKERS=3` (§4). |
| **Rødt** | > 1000 ms, eller ≥ 3 5xx | `WEB_WORKERS=4` (§4). Faller ikke P95 innen 3 min, er flaskehalsen noe annet enn workers (§5). |
| **Kritisk** | Fortsatt tregt etter alle tiltak | Last-shed (§9). |

**Under 20 forespørsler siste 5 min sier kortet «få målinger»**: da er P95 i praksis den
ene tregeste forespørselen, og trinnet er ikke noe å handle på. 5xx gjelder uansett.

**Én endring av gangen**, og se P95 i 3 minutter før neste. Hver endring er en redeploy
på ~60 sek, og to på rad gjør det umulig å si hvilken som virket.

**Rate-limit-nødbremsen (§7) er ikke et belastningstiltak.** Den stod i «Kritisk» til
24. sep. 2026, men den hjelper bare når rate-limitingen selv gir 429 til folk som skal
inn — ikke når serveren er treg.

---

## 3. Nedbremsing klientside (lett tiltak)

Hvis P95 ligger på 300–500 ms vedvarende, reduser polling-trykket:

1. Be brukere lukke faner de ikke aktivt trenger
2. Be leads lukke statistikk-fanen mellom oppslag
3. **Logg ut sesjoner som har vært inaktive over én time** (steg 3b). «Aktive sesjoner»
   viser hvor lenge siden hver fane ble brukt. **Ikke** en KO-operatør som er aktiv nå:
   med to skjermer er det to faner per person, og en utlogget operatør mister
   vaktbildet midt i jobben. Gevinsten er liten uansett — pollingen er billig (§3c).

Ingen redeploy trengs.

---

## 3b. Logg ut brukere via dashbordet

**Når:** Det står sesjoner som har vært inaktive i over én time — en glemt fane på en PC
ingen sitter ved. «Pålogget» er ikke «til stede»; se aktivitetskolonnen, ikke antallet.

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

## 3c. Hva koster én request? (målt 13. aug. 2026)

Tersklene i seksjon 2 er reaktive — de sier hva du skal gjøre når P95 stiger, ikke hva
som ryker først. Disse tallene er målt, ikke anslått:

| Endepunkt | Spørringer | Svar |
|---|---|---|
| `GET /api/patients/` (1000 pasienter) | 15 | 454 kB, eller **304 uten kropp** hvis uendret |
| `GET /api/forstehjelpere/` | 1 | 304 hvis uendret |
| `GET /api/helsepersonell/` | 1 | 304 hvis uendret |

Alle tre er ETag-sikret. Klienten poller hvert 30. sekund, men får bare data når noe
faktisk har endret seg — under en rolig time er trafikken nær null selv med mange
pålogget.

**Hvem poller egentlig?** Bare de som leser. Lag i park registrerer via lenke uten å lese
noe, og poller ikke. Ambulanser poller sitt eget, lille oppdragssett. Den tunge lesingen
er sykestua og 113, altså 15–25 klienter — ikke antallet pålogget totalt.

Regn derfor kapasitet på *pollende lesere*, ikke på brukertall. Tommelfingerregelen
«5–8 brukere per worker» i seksjon 4 ble kalibrert før ETag og `select_related`, og er
etter det for pessimistisk.

**Postgres-forbindelser:** appen bruker `workers × threads`, holdt åpne i 10 minutter av
`conn_max_age=600`. Ved 4 workers × 4 threads er det 16 mot grensen på 100. Sjekk faktisk
bruk under vakt med:

```sql
SHOW max_connections;
SELECT count(*), state FROM pg_stat_activity
 WHERE datname = current_database() GROUP BY state;
```

En connection pooler (PgBouncer) er vurdert og **ikke nødvendig** på denne skalaen — se
avklaringen av F8 i `TODO.md` og CHANGELOG.

**KO er ikke målt ennå** (24. sep. 2026). Tallene over er pasientsidens. KO-endepunktene
har **ingen ETag**: tavla henter hele bildet hvert 15. sekund fra hver fane som har den
framme, og loggen henter nye linjer hvert 15. sekund. I kjernetid er det 5 operatører med
to skjermer hver. Anslaget er noen få forespørsler i sekundet — lite for 2 × 4 — men det
er et anslag. Mål på staging, og før tallene inn her. Endringsnummeret (TODO) vil gjøre
en uendret tavle nesten gratis å spørre om.

---

## 4. Workers og threads — styring og tuning

### Hva er det?

- **Workers** = separate Python-prosesser. Egen minne, egen DB-pool. Hvis én krasjer, fortsetter de andre.
- **Threads** = parallelle spor inne i én worker. Deler minne. Bytter aktivt ved I/O-venting (DB-spørringer).
- **Total samtidig kapasitet** = workers × threads.

### Trinnene fra vakt-modus

| Når | `WEB_WORKERS` | `WEB_THREADS` | Samtidige forespørsler |
|---|---|---|---|
| Mellom vakter (lavkostnad) | 1 | 4 | 4 |
| **Vakt-modus** (grunnlinja) | **2** | 4 | 8 |
| Oransje (§2) | 3 | 4 | 12 |
| Rødt (§2) | 4 | 4 | 16 |

Workers gir mest gevinst; tråder er mindre viktig (behold 4). Regn kapasitet på
*pollende lesere*, ikke på antall pålogget (§3c).

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

**Sjekk først** i admin-dashbord at Cache-backend-kortet viser `REDIS / OK`. Hvis det viser `LOCMEM`, aktiver Redis først (§1c).

### Konsekvenser når du øker workers

**Det som funker automatisk:**
- PostgreSQL-tilkoblinger (~4 per worker, full pool er ~12 ved 3 workers — langt under DB-grensen)
- Sesjoner (lagret i DB, deles automatisk)
- Backup-scheduler (advisory lock i DB sørger for at kun én worker kjører)
- Rate-limit og stats-cache (delt via Redis)

**Det du må være obs på:**
- **Metrikkene er samlet fra alle workers når Redis er på** — kortet «Responstid» sier
  «Samlet fra 2 workers». Står det «Bare denne workeren», er Redis ikke i bruk, og tallet
  gjelder én prosess. (Til 24. sep. 2026 sto det her at metrikkene alltid var
  per prosess; det har ikke vært sant siden aggregeringen i Redis kom.)
- **Minnekortet er per prosess** — det viser workeren som svarte.
- **Memory-bruk øker lineært:** ~100–200 MB per worker ved oppstart; vokser gradvis over tid (reset ved redeploy eller worker-restart). 2 workers ~300–400 MB peak etter lengre drift, 3 workers ~450–600 MB. Hobby-planen har 8 GB — ikke et problem i praksis.
- **Oppstartstid:** 2 workers ~30 sek, 4 workers ~50 sek.

### Når skal du øke i løpet av en vakt?

**Når:** Trinnet på dashbordet er oransje eller rødt (§2).

**Steg:**
1. Åpne Railway → web-tjenesten → Variables
2. Sett `WEB_WORKERS` til trinnets tall — 3 på oransje, 4 på rødt
3. Save → vent 60 sek
4. Observer P95 i 3 minutter → skal falle

Gjør kun én endring av gangen. Hvis P95 ikke faller, er problemet noe annet enn worker-kapasitet (sjekk DB, Redis, eller eksterne tjenester).

### Over 4 workers

På vakt kjører dere Pro. Mer enn 4 workers er ikke et trinn i §2 med vilje: har ikke 3 og
4 hjulpet, er flaskehalsen nesten alltid databasen eller én treg side («Tregeste stier»),
og flere prosesser gir da bare flere som venter på det samme. Se §5.

---

## 5. Tyngre skalering (reserveplan)

**Når:** Rødt, og 4 workers hjalp ikke. P95 fortsatt > 1000 ms.

1. **Finn flaskehalsen før du skalerer mer.** «Tregeste stier» sier hvilken side;
   «Database» sier om svartiden på `SELECT 1` har steget. Er det databasen: §8.
2. Er det én side, og den ikke er nødvendig nå (statistikk, historikk): be folk lukke den.
3. Først da: `WEB_THREADS` = `6` (4 × 6 = 24 samtidige). Tråder hjelper når
   forespørslene venter på databasen, ikke når CPU-en er full.

---

## 6. Utgått

Dette var «skru av live-statistikk (feature-flag)». Flagget ble fjernet 13. sep. 2026 —
funksjonen ble aldri bygget. Nummeret står igjen så §7 og oppover peker riktig.

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

## 8b. Offsite-backup til Scaleway — oppsett, kontroll og gjenoppretting

Fra 13. sep. 2026 lastes hver ny backup-fil opp til Scaleway Object Storage, kryptert
før den forlater Railway. Volumet på Railway er første sikkerhetsnett; bucketen er det
som overlever at Railway er borte. Se `docs/TEKNISK_DOKUMENTASJON.md` §11 og
`docs/PERSONVERN_DOKUMENTASJON.md` A.2.

### Oppsett (gjøres én gang, bare i prod)

**Hos Scaleway** (allerede gjort 13. sep. 2026): bucketen `sanitetsportalen` i Amsterdam (nl-ams), One Zone,
privat, SSE på, versjonering av, og 7 dagers frist for uferdige
multipart-opplastinger. **Oppbevaringen er delt i to prefikser** (14. sep. 2026):
`backups/` 730 dager for modulfilene, `full/` 90 dager for den hele databasen. Regelen
sto først på «alle objekter i bucketen», og måtte snevres inn til `backups/` *før*
regelen på `full/` ble lagt til — to regler som treffer samme objekt er et sted å gjette.
Prefikset må skrives **nøyaktig** som `backups/` og `full/`: `/full` ser riktig ut i
konsollen og treffer ingenting, og da blir filene liggende for alltid.
IAM-applikasjon `sanitetsportalen-backup` med policy
`ObjectStorageObjectsWrite` + `ObjectStorageObjectsRead` + `ObjectStorageBucketsRead` —
**ikke** sletterett — og en API-nøkkel på den.

**Krypteringsnøkkelen** lages lokalt og legges i passordbehandleren *før* den settes i
Railway. Uten den er bucketen uleselig — det er meningen, men da må den finnes utenfor
Railway også:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Variablene på prod-tjenesten i Railway** (Variables). Staging skal ikke ha dem.

| Variabel | Verdi |
|---|---|
| `OFFSITE_S3_BUCKET` | bucketnavnet |
| `OFFSITE_S3_REGION` | `nl-ams` |
| `OFFSITE_S3_ENDPOINT` | `https://s3.nl-ams.scw.cloud` |
| `OFFSITE_S3_ACCESS_KEY` | access key fra IAM-nøkkelen |
| `OFFSITE_S3_SECRET_KEY` | secret key fra IAM-nøkkelen |
| `OFFSITE_BACKUP_KEY` | krypteringsnøkkelen fra passordbehandleren |

Tjenesten starter på nytt av seg selv når variablene lagres.

### Kontroll etter oppsett, og før hver vakt

1. Åpne `/portal-admin/backup/`. Kortet **«Offsite-kopi (Scaleway)»** øverst skal si
   «Aktiv» med bucketnavnet. Sier det «Ikke konfigurert», står det hvilke variabler
   som mangler.
2. Ta en manuell backup av én modul fra samme side. Last siden på nytt: kortet skal
   si «1 fil lastet opp» (eller ett mer enn før) med tidspunkt og filnavn.
3. I Scaleway-konsollen: bucketen → mappa `backups/` → fila ligger der med endelsen
   `.enc`. Innholdet er chiffertekst; det er riktig.
4. Sier kortet **«Siste opplasting feilet»**, står feilen under i rødt. De vanligste:
   feil endpoint eller region, en nøkkel uten skriverett på bucketen, feil bucketnavn.
   Backupen på volumet er tatt uansett — rett variabelen og ta en ny manuell backup.
5. Samme kort viser **«Oppbevaring i bucketen»**, lest fra Scaleway ved hver visning
   (cachet fem minutter). Det skal stå `backups/` 730 dager · `full/` 90 dager. Stemmer
   det ikke, står avviket i rødt med hva som er galt — regelen mangler, står på feil
   prefiks, er slått av, eller har feil antall dager. **Dette er ikke pynt:** portalens
   nøkkel har ikke sletterett, så livssyklusreglene er den eneste mekanismen som noen
   gang sletter en offsite-kopi. Rettes i konsollen; portalen kan lese bucket-oppsettet,
   men ikke skrive det. Står det «ukjent», mangler nøkkelen `ObjectStorageBucketsRead`.

Under vakt går opplastingen av seg selv: hver gang auto-backupen skriver en ny fil,
går den opp. Ingen endringer = ingen fil = ingen opplasting.

### Gjenoppretting fra bucketen

Prøv dette **én gang mens alt er friskt** — poenget er å ha sett at nøkkelen låser
opp det bucketen inneholder, før dagen det gjelder.

Fra Railway-terminalen (krever Railway CLI innlogget på prosjektet):

```powershell
railway ssh --service web -- python manage.py hent_offsite --list
railway ssh --service web -- python manage.py hent_offsite <filnavnet fra lista>
```

Den første lister filene i bucketen, nyeste først — både modulfilene under `backups/`
og de hele under `full/`. Den andre henter fila, dekrypterer den med
`OFFSITE_BACKUP_KEY`, og legger den i backup-mappa på volumet med en rad, så den dukker
opp på `/portal-admin/backup/`. Kommandoen rører ikke basen.

Svarer den «Kunne ikke dekryptere: feil OFFSITE_BACKUP_KEY», er nøkkelen i Railway en
annen enn den fila ble kryptert med. Sjekk mot passordbehandleren.

### Er backupen ekte? (`verifiser_backup`)

En backup ingen har gjenopprettet er en hypotese. Denne kommandoen laster filene
som faktisk ligger på volumet inn i en **engangsbase**, og sammenligner radene
mot det filene inneholder. Den rører ingenting: alt skjer i en flyktig
SQLite-fil i en midlertidig mappe, som slettes etterpå.

```powershell
railway ssh --service web -- python manage.py verifiser_backup
railway ssh --service web -- python manage.py verifiser_backup --full
```

Den første tar modulfilene i rekkefølge, den andre den hele databasefila alene.
Svarer den «N modell(er) kom tilbake med nøyaktig samme antall rader», er
filene gjenopprettbare. Svarer den «avvik», er de det ikke — og da vet du det
**før** du trenger dem.

Advarselen «inneholder ingen rader» er verdt å lese: enten er modulen tom, eller
så ble fila tatt før dataene fantes. En tom fil er ikke en bestått prøve.

Kjør den **etter første backup i en ny vakt**, og gjerne som en del av
kontrollen under. Den tar noen sekunder.

### Gjenoppretting fra kommandolinja

`hent_offsite` henter fila. **`gjenopprett` er den som rører basen** (13. sep. 2026) —
og den finnes nettopp fordi veien gjennom nettleseren ikke duger i en tom base: der er
det ingen å logge inn som.

```powershell
railway ssh --service web -- python manage.py gjenopprett --list
railway ssh --service web -- python manage.py gjenopprett --siste vaktliste --ja
railway ssh --service web -- python manage.py gjenopprett --hent <objekt> --ja
```

| Flagg | Hva det gjør |
|---|---|
| `--list` | Filene som ligger på volumet, nyeste først |
| `--siste <modul>` | Den nyeste fila for modulen. Hopper over pre-restore-øyeblikksbildene |
| `--hent <objekt>` | Henter fra Scaleway og gjenoppretter i ett |
| `--full` | **Kreves** når fila er hele databasen |
| `--ja` | Ikke spør |

**`--ja` er ikke bekvemmelighet.** `railway ssh -- <kommando>` kjører uten interaktiv
terminal, så et spørsmål ville hengt til noe ga opp — i en katastrofe. Uten flagget
sier kommandoen det med rene ord i stedet for å vente.

Kommandoen skriver hva som slettes før den gjør det, tar et
pre-restore-øyeblikksbilde, og legger én auditrad med kilden «kommandolinja».

### Ved fullt bortfall av Railway

Ny tjeneste, tom base. **Den korte veien er den hele fila:**

```powershell
railway ssh --service web -- python manage.py migrate
railway ssh --service web -- python manage.py hent_offsite --list
railway ssh --service web -- python manage.py gjenopprett --hent <full/-objektet> --full --ja
railway ssh --service web -- python manage.py purge_old_logs
railway ssh --service web -- python manage.py kollaps_arkiv
```

De to siste er ikke valgfrie: backupen har egen slettefrist, og det som var slettet i
basen skal ikke komme tilbake (`docs/BACKUP.md` §2). Alle logger inn på nytt med
passordene som gjaldt da backupen ble tatt.

**Mangler den hele fila**, tas modulfilene i rekkefølge — og rekkefølgen er bindende,
fordi alt peker på vakta:

```
portal → ko → patients → arkiv → oppdrag → oppdrag_arkiv → vaktliste
```

`portal` bærer `core.Vakt`. Tas den ikke først, feiler de andre med
«Key (vakt_id)=(1) is not present in table core_vakt». **Og `oppdrag` må tas før
`vaktliste`**: `Ressurs.enhet` peker på `oppdrag.Enhet` med et heltall, så motsatt
rekkefølge feiler med «vaktliste_ressurs.enhet_id contains a value '1' that does not
have a corresponding value in oppdrag_enhet.id». `backlog` står utenfor og kan tas
når som helst — den peker ingen steder. Deretter `create_admin` og kontoene for hånd,
siden modulfilene ikke inneholder brukere.

---

## 8c. Deployen knakk — rull tilbake

*Lagt til 14. sep. 2026. Runbooken dekket last, skalering, databaseproblemer og
gjenoppretting fra backup, men ikke det enkleste og mest sannsynlige: en dårlig commit i
prod. Railway auto-deployer fra `main`, så en feil er ute på noen minutter.*

**Ikke deploy under vakt.** Dette kapittelet er for når det likevel har skjedd.

### Steg 1: Er det deployen?

Sammenlign **byggnummeret i footeren** nederst på siden med commit-en du sist pushet.
Stemmer de, og begynte feilen ved den deployen, er det den. Står footeren på forrige bygg,
er problemet et annet — gå til §8 eller §2.

`/portal-admin/server-status/` viser samme bygg, sammen med minne og tregeste stier.

### Steg 2: Rull tilbake i Railway

1. Web-tjenesten → **Deployments**
2. Finn siste deploy som virket
3. **⋮** → **Redeploy**

Det bygger den commit-en på nytt. Raskeste vei tilbake, ingen kode, ingen CLI.

### Steg 3: Men sjekk migrasjonen først

**En redeploy ruller ikke tilbake databasen.** Kjørte release-fasen en migrasjon som
endret skjemaet, står basen igjen i ny form mens koden er gammel — og da får du en annen
feil enn den du startet med.

Se i **Deployments**-loggen fra den dårlige deployen, release-steget:

| Hva loggen viser | Hva du gjør |
|---|---|
| Ingen migrasjon kjørte | Redeploy er nok |
| `Applying …` på en ren tilstandsmigrasjon | Redeploy er nok — ingen SQL kjørte |
| `Applying …` som endret skjemaet | Rull migrasjonen tilbake *før* redeploy |

Tilbakerulling av en reversibel migrasjon:

```powershell
railway ssh --service web -- python manage.py migrate <app> <forrige_migrasjonsnavn>
```

Er den ikke reversibel, er backupen veien tilbake — §8b, «Gjenoppretting fra
kommandolinja». Ta et pre-restore-øyeblikksbilde først; `gjenopprett` gjør det selv.

### Steg 4: Eller rett framover i stedet

Er portalen **oppe, men feil**, er en ny commit som retter feilen som regel tryggere enn
et tilbakerull — særlig hvis migrasjonen har skrevet data. Rull tilbake når portalen er
**nede**.

### Hvorfor dette står her

Staging (`rollemodell`) fanger det meste, og gjorde det 14. sep. 2026: CSP-en som
blokkerte lydvarselet på iOS sto grønt i 2 744 tester og ble bare funnet ved å klikke.
Men staging fanger ikke alt, og forskjellen mellom staging og prod — ekte data, ekte last,
offsite-variablene som bare finnes i prod — er nettopp der de gjenværende feilene bor.

Se også `docs/DEPLOY_GUIDE.md` §10.

---

## 9. Hvis alt annet feiler: last-shed

Som absolutt siste utvei hvis systemet er utilgjengelig:

1. Meld fra til brukerne at de må registrere manuelt på papir
2. Redeploy med `DEBUG=true` midlertidig for bedre feilmeldinger i logs
3. Vaktlista: drifts-PC-en har siste liste lokalt (service worker) og stempler møtt/av vakt i kø;
   fila på e-post er reserven om PC-en også faller. Pasienter på Excel, oppdrag på nødnett.

---

## 10. Etter vakten — tilbake til lavkostnad-modus

### 10a. Avlesning og bevaring

1. Gå gjennom admin-dashbord – noter peak P95, peak RPS, peak memory og antall samtidige sesjoner
2. Sjekk at kortet «Offsite-kopi (Scaleway)» på `/portal-admin/backup/` viser en
   opplasting fra i dag uten feil (§8b). Fila på Railway Volume er da alt utenfor Railway
3. Verifiser at ingen 5xx-feil ligger uten forklaring (admin-dashbord → Metrikk-kort → errors_5xx)
4. **Arkiver vakta — begge modulene.** Arkiveringen ligger to steder inntil de slås
   sammen, og det er lett å ta den ene og tro man er ferdig:
   - **Pasienter:** `/pasienter/` → Vaktarkiv → «Lagre vakt som arkiv»
   - **Oppdrag:** `/oppdrag/` → Vaktarkiv → «Arkiver oppdragene»

   Begge krever global admin. Arkivering fjerner ingenting — den fryser en kopi med
   signatur, og pasientene slettes først når du senere velger «Avslutt vakt».
   Kryss av begge før du går videre til 10b: gjør du det ikke, står oppdragene igjen
   uten frosset kopi, og statistikken for vakta finnes bare så lenge radene gjør det.

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
2. **Pro → Hobby:** Settings → Plan → nedgrader (proratert billing). Pro er del av vakt-modus
   og skal ned igjen etter vakt, som Redis.
3. Noter erfaringer i en kort logg (dato, antall pasienter, peak-tall, eventuelle tiltak)

---

## 11. Når trenger jeg å tenke på skalering?

### Anbefalt oppsett etter forventet last

Se §1b og §4 — vakt-modus (Pro, 2 × 4, Redis) er oppsettet for hver vakt, og §2 sier
når dere går til 3 og 4 workers. Tabellen som sto her regnet på antall brukere og ga
Hobby for opptil 40; den er erstattet av trinnene, som regner på målt P95.

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
- `core/stats_cache.py` fanger alle cache-feil og regner statistikk direkte ved utfall
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
| Admin server-status | `https://<din-app>.railway.app/portal-admin/server-status/` |
| Railway-dashbord | [https://railway.app](https://railway.app) |
| Railway Volume backups | Railway → Volumes → Browse |
| Offsite-backup (Scaleway) | `/portal-admin/backup/` (kortet øverst) · konsollen: console.scaleway.com → Object Storage · §8b |
| Brukeradmin | `https://<din-app>.railway.app/portal-admin/brukere/` |
| Innloggingslogg | `https://<din-app>.railway.app/portal-admin/innloggingslogg/` |
| Reserve | `docs/TEKNISK_DOKUMENTASJON.md` §11 |
| Deploy-guide | `DEPLOY_GUIDE.md` i repoet |

---

## 13. Feilfinning i prod (uten Sentry)

Applikasjonen bruker IKKE en ekstern feilsporings-tjeneste. Feilsøking
skjer via to kilder:

### Railway-loggen (sanntid)

1. Railway → web-tjenesten → fanen **Logs** (eller **Service Logs** i nyere UI)
2. Filtrer på tid eller søkeord (`ERROR`, `Traceback`, `500`)
3. Stack-traces fra ubehandlede exceptions vises her i full lengde

### Admin-dashbord (/portal-admin/server-status/)

1. **Feilresponser** – antall 4xx/5xx siste 5 min
2. **Tregeste stier** – hvilken side som drar P95 opp
3. **Database** – svartid og tilkoblinger; nær taket betyr *ikke* øk `WEB_WORKERS`
4. **Konfigsjekk** – skal si «alt OK» i prod; et ✗ er noe som er satt feil i Railway
5. **Innlogging siste time** – mange feil fra én IP er et angrep, mange fra mange er
   et passord ingen husker
6. **Vaktbildet** – oppdrag som venter på ressurs, og siste vaktlistefil
7. **Cron-jobber** og **Offsite** – gult/rødt her er noe som har sluttet å virke i det
   stille; se §8b
8. **Audit-loggen** (`/portal-admin/auditlog/`) – hver feilet handling på pasient/bruker logges

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
- Kortet viser «nå» stort og toppen siden oppstart under. Det er «nå» som sier om noe
  lekker — toppen går aldri ned.
- 1 worker: ~100–200 MB (vokser gradvis; typisk 150–300 MB etter noen dagers drift uten redeploy)
- 2 workers: ~300–400 MB total. Over 500 MB per worker = vurder redeploy for å frigjøre minne.
- 3 workers: ~450–600 MB total.

**Cache-backend**
- `REDIS / OK`: delt cache aktiv, trygt å kjøre med 2+ workers
- `LOCMEM`: per-prosess cache, OK kun ved 1 worker
- `FEIL`: cache er nede, sjekk Redis-tjenestens status i Railway

**Worker-konfig**
- Merket øverst sier modusen: «Vakt-modus: 2 workers, Redis OK» (grønt), «Lavkostnad-modus»,
  eller rødt når det står 2+ workers uten virkende Redis. Under står `WEB_WORKERS` og
  `WEB_THREADS` (se §4).

**Siste backup**
- Skal være < 35 min gammel (backup-schedule er 30 min + litt slakk)
- > 60 min: sjekk Railway Volume og backup-siden

---

## 14. Sikkerhetssjekk utenfra — `scripts/sikkerhetssjekk.py`

**Når:** før en vakt, etter en deploy som rører innlogging, hoder eller tilgang, og
ellers et par ganger i året. Kjøres **mot staging**, fra din PC, i prosjektets venv:

```powershell
python scripts/sikkerhetssjekk.py https://testportal.sanitet.net
python scripts/sikkerhetssjekk.py https://testportal.sanitet.net --admin admin --leser kari --enhet bil1
```

Uten kontoer testes det som kan testes anonymt: HTTPS-omdirigering, HSTS, CSP og de
andre hodene, cookieflagg, at ingen av portalens sider og API-er svarer 200 uten
innlogging, CSRF på skriveendepunktene, rate-limiting på innlogging (12 feilede forsøk
med et tilfeldig brukernavn som ikke finnes), egen 404-side, og at Django-admin og
kjente filer ikke finnes. Med kontoer testes rollegrensene i tillegg: leseren nektes
admin-sidene og all skriving, enhetskontoen nektes sentralens oppsett, admin når alt —
og konfigsjekken fra server-status leses ut rad for rad. Passord og MFA-kode spørres
det om i terminalen; ingenting lagres.

Alt som står som `FEIL` skal forklares eller fikses. Lim hele utskriften inn i chatten.
Kjør den ikke mot prod under vakt — rate-limit-testen bruker 11 av IP-bøttas 50 forsøk.

**Drifts-PC-en er en enhet portalen legger data på.** Offline-driften på `/vaktliste/`
legger vaktlista og mannskapsregisteret (navn, telefon, e-post, ISSI) i nettleserens
lager, så lista er der når nettet er borte. **«Logg ut» er det som rydder** — knappen
sender `Clear-Site-Data`, og alt lokalt lager slettes. Lukk aldri bare vinduet på en delt
maskin; logg ut. En kopi eldre enn ett døgn brukes uansett ikke.

---

*Sist oppdatert: 13.09.2026*
