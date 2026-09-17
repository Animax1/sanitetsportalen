# Teknisk dokumentasjon – Sanitetsportalen

> **Versjon:** 14. september 2026
> **Målgruppe:** Teknisk etterfølger (utvikler / IT-konsulent) som overtar drift eller videreutvikling.
> **Status:** Gjennomgått mot koden i dokumentrunden 14. sep. 2026 — appene etter at det
> portalvide flyttet til `core`, backup i to lag, og sikkerhetslaget etter rundene
> 11.–13. september.
>
> **Dokumentet het «Pasientregistreringssystemet» fram til nå, og beskrev tre apper.**
> Portalen har åtte: pasientregistrering er én av seks brukervendte moduler.
>
> **Hele dokumentet er gjennomgått.** Første runde tok kapittel 1, 3, 4, 6–10; andre runde
> tok 5, 8A–8E og 13–16 etter at André påpekte at halvveis verifisert dokumentasjon er
> verre enn tydelig uverifisert — merket forsvinner ved neste redigering, og da ser det
> uetterprøvde ut som resten.
>
> Tilleggene nederst (Fase 3, 4 og 5, mai 2026) står med vilje som **historiske**: de
> forklarer hvorfor ting ble som de ble, men detaljene er overtatt av senere kapitler. Er
> et tillegg og et kapittel uenige, vinner kapittelet.

---

## 1. Sammendrag

Sanitetsportalen er en nettbasert applikasjon for sanitetsvakt og beredskap ved
arrangementer. Den er bygget som et **rammeverk med moduler**, ikke som én applikasjon:
`core` er portalen, og hver modul melder seg inn i den.

Seks brukervendte moduler i dag:

| Modul | Hva den gjør |
|---|---|
| **Pasientregistrering** (`patients`) | Registrering og sporing av pasienter, triagering (Rød/Gul/Grønn), forløp fra ankomst til utskriving |
| **Oppdrag** (`oppdrag`) | Sentralbord og enhetsskjerm: utrykningsoppdrag, statusmeldinger, enhetshåndtering |
| **Vaktliste** (`vaktliste`) | Mannskap, korps, ressurser og skift; innsjekk i drift |
| **Statistikk** (`statistikk`) | Tall fra modulene. Eier ingen data selv |
| **KO** (`ko`) | Situasjonsbildet: ressursoversikt, oppdragsliste, logg og hendelser. Eier ingen ressurser selv — **skallet er alt som finnes i dag**, se `ko/CLAUDE.md` |
| **Backlog** (`backlog`) | Endringsønsker og bugs, med løst-flagg. Utviklingsverktøy, og den eneste modulen utenfor vaktscopet |

Django 5.2, PostgreSQL i produksjon (SQLite lokalt), vanlig JavaScript uten rammeverk og
uten bundler. Deployes på Railway. MFA (TOTP), tilgangsstyring per modul og audit-logging
på feltnivå, i tråd med GDPR-krav for helseopplysninger.

**Alt henger på en `Vakt`.** Pasienter og oppdrag scopes til den vakta som er aktiv, og
`core.vakt.hent_aktiv_vakt()` er det ene stedet som svarer på hvilken det er.

---

## 2. Teknologistack

| Komponent | Teknologi | Versjon | Formål |
|---|---|---|---|
| Backend-rammeverk | Django | >=5.2 | Webapplikasjon, ORM, admin |
| Database (produksjon) | PostgreSQL | Railway-administrert | Persistent lagring av alle data |
| Database (utvikling) | SQLite | Innebygd | Lokal testing, ingen oppsett nødvendig |
| Database-driver | psycopg2-binary | >=2.9 | Kobling Django–Postgres |
| Database-URL-parsing | dj-database-url | >=2.1 | Tolker `DATABASE_URL`-miljøvariabelen |
| WSGI-server | Gunicorn | >=21.2 | Produksjonsserver (default 1 worker × 4 tråder, parametrisert) |
| Prosessmålinger | `resource` + `/proc/self/status` | stdlib | RSS nå og topp for server-status-dashbordet — ingen psutil |
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
| Frontend-grid | Tabulator | 6.2.5, `static/vendor/` | Pasienttabell med sortering og filtrering |
| Frontend-diagram | Chart.js | 4.4.2, `static/vendor/` | Statistikk-diagrammer |
| Frontend-UI | Bootstrap 5 | 5.3.2, `static/vendor/` | Responsivt grensesnitt, modaler |
| Frontend-ikoner | Bootstrap Icons | 1.11.3, `static/vendor/` | UI-ikoner |
| Frontend-logikk | Vanlig JavaScript | – | Ingen rammeverk, ingen bundler; fire moduler i `static/js/` |

---

## 3. Arkitektur

### 3.1 Komponentdiagram

```
  Nettleser (Bootstrap 5 + Tabulator + Chart.js — alt fra static/vendor/, ingen CDN)
       |
       | HTTPS (TLS 1.2+)
       v
  Railway Gateway (terminerer TLS, setter X-Forwarded-Proto og X-Forwarded-For)
       |
       | HTTP (intern)
       v
  Gunicorn (workers/threads styrt av WEB_WORKERS/WEB_THREADS)
       |
       v
  Django 5.2 WSGI-app — middleware i denne rekkefølgen:
   ├── SecurityMiddleware                       (django)
   ├── core.MemoryLoggingMiddleware             RSS og responstid for tunge requests
   ├── WhiteNoiseMiddleware                     serverer /static/ med hashede navn
   ├── SessionMiddleware                        (django)
   ├── CommonMiddleware                         (django)
   ├── CsrfViewMiddleware                       (django)
   ├── AuthenticationMiddleware                 (django)
   ├── OTPMiddleware                            (django-otp)
   ├── MessageMiddleware                        (django)
   ├── XFrameOptionsMiddleware                  (django)
   ├── audit.RequestAuditMiddleware             request i thread-local, så signaler får bruker og IP
   ├── accounts.MustChangePasswordMiddleware
   ├── accounts.DynamicSessionTimeoutMiddleware
   ├── core.BackupSchedulerMiddleware           reservenett for backup-klokka
   ├── vaktliste.FilutsendingMiddleware         intervallsending av vaktlista på e-post
   ├── core.SecurityHeadersMiddleware           CSP, Referrer-Policy, Permissions-Policy
   └── core.RequestMetricsMiddleware            ringbuffer for p50/p95/max
       |
       ├── core        rammeverket: register, Vakt, backup, arkiv, adminflate
       ├── accounts    kontoer, ModulTilgang, MFA, innlogging
       ├── audit       AuditLog og purge
       ├── patients    pasientregistrering + arkiv
       ├── oppdrag     sentralbord, enhetsskjerm + arkiv
       ├── vaktliste   mannskap, ressurser, skift, offline drift
       └── statistikk  /statistikk/ — henter fra registeret, eier ingen data
       |
       v
  PostgreSQL (Railway, AES-256 at rest, TLS i transitt)
  Railway Volume /data/backups          gzip-komprimerte JSON-filer
       |                                 klokketråd i web-prosessen skriver hit
       v
  Scaleway Object Storage (nl-ams)      kryptert kopi, AES-256-GCM
       backups/  modulfilene, 730 dager
       full/     hele databasen, 90 dager
       |
       v
  Cache: LocMemCache, eller Redis når REDIS_URL er satt (vakt-modus)
```

**De to middlewarene som er klokker, ikke vakter.** `BackupSchedulerMiddleware` og
`FilutsendingMiddleware` bruker trafikken som tidtaker. Begge tas ut under test
(`settings.py`), og backupens egentlige klokke er en **tråd** i web-prosessen —
middlewaren er reservenettet, og det eneste stedet som kan varsle om at tråden har
stoppet. Et varsel om at klokka er død, sendt av klokka, kommer aldri fram.

### 3.2 Request-flyt

1. Nettleseren sender HTTPS til Railway-domenet.
2. Gatewayen terminerer TLS og videresender med `X-Forwarded-Proto: https`. Django er
   konfigurert med `SECURE_PROXY_SSL_HEADER` slik at dette tolkes riktig.
3. Middleware-kjeden over kjøres i rekkefølge.
4. **Klient-IP leses aldri direkte fra `REMOTE_ADDR`** i applikasjonskoden — den er
   proxyen i produksjon. `core.klientip.klient_ip(request)` er det ene stedet: siste ledd
   i `X-Forwarded-For`, det Railway selv la til, validert. *Første* ledd er klientens egen
   påstand og kan forfalskes.
5. Viewet gates av `core.auth_decorators` — `admin_required`, `modul_kreves` eller
   `har_tilgang`. Et udekorert view under en modul er en feil som `patients/tests_modul_dekorator.py` fanger.
6. Audit-signaler i `<app>/signals.py` fyrer på `pre_save`/`post_save`/`post_delete` og
   henter bruker og IP fra thread-local. Alle lagringssignaler har `@ikke_under_loaddata`,
   ellers ville en gjenoppretting skrevet en auditrad per lastede rad.
7. Data som skal inn i et `<script>`-element går gjennom `core.jsdata.js_json()`, aldri
   `json.dumps` + `|safe`: `json.dumps` escaper ikke `<`, og et navn med `</script>`
   lukker skriptet.

### 3.3 Applikasjoner

**Retningen er enveis: modulene kjenner `core`, `core` kjenner ingen modul.**
`accounts` og `audit` regnes som rammeverk. Håndheves av
`core/tests_avhengighetsretning.py`, som leser importene med AST.

| App | Rolle | Ansvar |
|---|---|---|
| `core` | Rammeverk | Modulregisteret, `Vakt` (portalens scope), `AppSetting`, `Backup`, `Backupplan`, `ModuleSettings`. All backup- og arkivlogikk. Adminflaten under `/portal-admin/`. CSP, metrikker, helsesjekk, server-status |
| `accounts` | Rammeverk | `CustomUser`, `ModulTilgang`, innloggingsflyt med MFA, brukeradmin, rate-limiting, `LoginEvent` |
| `audit` | Rammeverk | `AuditLog`, `RequestAuditMiddleware`, `purge_old_logs`, `check_ssl` |
| `patients` | Modul | `Patient`, `Forstehjelper`, `Helsepersonell`, `VaktArkiv`, `ArkivertPasient`. JSON-API delt i fire view-moduler |
| `oppdrag` | Modul | `Oppdrag`, `Statusmelding`, `Enhet`, `Lokasjon`, `Problemstilling`, `OppdragArkiv`. Sentralbord og enhetsskjerm |
| `vaktliste` | Modul | `Korps`, `Mannskap`, `Ressurs`, `Vaktpost`, `Vaktliste`, `Kompetanse`. Offline drift med service worker |
| `statistikk` | Modul | `/statistikk/`. Henter fra `core.stats`-registeret og **navngir ingen kildemodul** |

### 3.4 Registrene — hvordan en modul melder seg inn

En modul registrerer seg fra `apps.ready()`. `core` spør aldri etter en modul ved navn;
det er derfor rammeverket kan kjøre uten en eneste modul, og derfor en ny modul ikke
krever endringer i `core`.

| Register | Modulen melder inn | Fra |
|---|---|---|
| `core/modules.py` | Selve modulen og hvilke tilgangsnivåer den bruker | `<app>/module.py` |
| `core/backup/` | Hva som skal med i backupfila | `<app>/backup.py` |
| `core/arkiv/` | Hva som går inn i arkivets SHA-payload | `<app>/arkiv.py` |
| `core/stats.py` | Tall til `/statistikk/` | `<app>/statistikk.py` |
| `core/driftstatus.py` | Tall til `/portal-admin/server-status/` | `<app>/driftstatus.py` |
| `core/portalinnstillinger.py` | Modulens felter i portalinnstillingene | `<app>/portalinnstillinger.py` |
| `core/kontokobling.py` | Modulens kort i brukeradmin | `<app>/kontokobling.py` |

De tre siste kom 14. sep. 2026. Fram til da hentet `core` disse tallene ved å importere
`vaktliste` og `oppdrag` direkte — altså med retningen snudd.

**Hver innhenter fanger sine egne feil.** Et dashbord som gir 500 fordi én modul har en
treg spørring, er borte akkurat når man trenger det. Portalinnstillingene validerer
derimot *alle* handlere før noen lagrer: navnet skrives på `Vakt` og resten i
`AppSetting`, uten transaksjon mellom seg, så en modul som nekter skal stoppe hele
innsendingen.

---

## 4. Datamodell

### 4.1 `accounts.CustomUser`

Basert på `AbstractBaseUser` + `PermissionsMixin`. Definert i `accounts/models.py`.

| Feltnavn | Type | Beskrivelse | Constraints |
|---|---|---|---|
| `id` | BigAutoField | Intern primærnøkkel | PK, auto |
| `username` | CharField(64) | Brukernavn | `UNIQUE`, påkrevd |
| `email` | EmailField(120) | E-post (valgfritt) | `NULL` tillatt; unik hvis satt (`UniqueConstraint` med betingelse) |
| `role` | CharField(20) | **Kontotype, ikke tilgangsnivå** | Choices: `admin`, `bruker`; default `bruker`. Feltet krympet i deploy 2 — de fire verdiene som beskrev tilgang er borte, sammen med `has_role_at_least`, `role_required`, `write_required` og `stats_required`. Tilgang ligger i `ModulTilgang` (4.2) |
| `is_active` | BooleanField | Aktiv konto | Default `True` |
| `is_staff` | BooleanField | Django Admin-tilgang | Default `False` |
| `must_change_password` | BooleanField | Tving passordbytte | Default `True` (settes `False` etter bytte) |
| `mfa_required` | BooleanField | Krev TOTP-MFA | Default `False` |
| `failed_login_attempts` | IntegerField | Antall mislykkede forsøk siden sist reset | Default `0` |
| `locked_until` | DateTimeField | Konto låst til dette tidspunktet | `NULL` betyr ikke låst |
| `created_at` | DateTimeField | Opprettet | Auto, `auto_now_add` |
| `updated_at` | DateTimeField | Sist oppdatert | Auto, `auto_now` |
| `last_login_at` | DateTimeField | Tidspunkt for siste vellykkede innlogging | `NULL` tillatt |

`USERNAME_FIELD = 'username'`. Passordet lagres som en Django-hash — i dag PBKDF2-HMAC-SHA256. Argon2 er **ikke** installert; det krever `argon2-cffi` i `requirements.txt`.

### 4.2 `accounts.ModulTilgang`

**Dette er tilgangsstyringen.** Én rad per modul brukeren har tilgang til.

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `bruker` | ForeignKey → CustomUser | |
| `modul_slug` | CharField | Modulens slug, som i `core/modules.py` |
| `nivaa` | CharField | `les`, `les_alle`, `skriv_handling`, `skriv_full`, `skriv_leder` |

**Fravær av rad er ingen tilgang** — det finnes ingen `'ingen'`-verdi å lagre, og en
konto uten rader ser ingenting. Det er ikke en bivirkning, det er den trygge
standardtilstanden: en ny konto må aktivt få tilgang.

Nivåene er en **ordnet stige**, og `har_tilgang(bruker, slug, nivaa)` svarer på om
brukeren er på eller over trinnet. **Ukjent nivånavn gir `False`, ikke `True`** — en
skrivefeil i en dekoratør skal stenge døra, ikke åpne den. Global admin får toppen av
stigen fra `nivaa_for`; fram til 13. sep. 2026 fikk den `skriv_full`, og da måtte hvert
`skriv_leder`-kallsted huske `er_global_admin(...) or`.

**Hver modul deklarerer hvilke nivåer den bruker** (`Module.nivaaer`) og kan gi dem sin
egen etikett (`Module.nivaa_navn`). Det trengs fordi samme nivå betyr ulike ting:
`skriv_handling` er «stempling» i oppdrag og «fører sitt eget korps» i vaktlista. En
global liste hadde begge feil samtidig — den skjulte `skriv_handling` for
oppdragsmodulen, som er den nivået ble laget for, og tilbød `skriv_full` på statistikk,
der skriving ikke finnes.

### 4.3 `accounts.LoginEvent`

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

### 4.6 `core.Vakt` — portalens scope

**Alt annet henger på denne.** Pasienter og oppdrag scopes til en vakt, og
`core.vakt.hent_aktiv_vakt()` er det ene stedet som svarer på hvilken som er aktiv.

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `navn` | CharField(255) | «Landsskytterstevnet 2026». **Unikt** — to vakter med samme navn lar seg ikke skille i statistikken |
| `year` | IntegerField | Utledet, men lagret: sesongstatistikken grupperer på år |
| `startet` | DateTimeField | |
| `avsluttet` | DateTimeField | `NULL` mens vakta pågår |
| `er_aktiv` | BooleanField | |

**Én aktiv vakt om gangen**, pekt på av `AppSetting['aktiv_vakt_id']` — ikke av `er_aktiv`
alene. Flere samtidige vakter ville krevd et vaktvalg i hver eneste visning, og en feil i
det valget er en pasient registrert på feil vakt. Modellen sperrer det ikke for
framtiden; grensesnittet forutsetter én.

Modellen erstattet `year` som avgrensning (`docs/BESLUTNING_VAKT_SOM_SCOPE.md`). Den
ligger i `core` fordi **begge** modulene scopes på den; i `patients` ville den gitt
`oppdrag → patients` for noe som ikke er pasientdata.

### 4.7 `core.AppSetting`

Nøkkel-verdi for det portalvide. `key` er primærnøkkelen.

> **`db_table = 'patients_appsetting'`, og det er med vilje.** Modellen flyttet fra
> `patients` til `core` 14. sep. 2026 som en ren tilstandsmigrasjon. Railway kjører
> release-fasen *før* containerbyttet, så mellom `migrate` og byttet står gammel kode og
> serverer mot nytt skjema — en omdøpt tabell ville gitt 500 på tilnærmet hver
> forespørsel i det vinduet, fordi denne tabellen bærer pekeren til aktiv vakt. Fjernes
> `db_table`, lager Django en ny, tom tabell ved siden av den fulle.
>
> **Backupfilene bærer modellnavn**, så `core.backup.GAMLE_MODELLNAVN` oversetter
> `patients.appsetting` → `core.appsetting` ved innlasting. Uten den ville hver fil tatt
> før flyttingen svart «Invalid model identifier» — og de ligger 730 dager offsite.

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `key` | CharField(64) | Nøkkel (PK) |
| `value` | TextField | Verdi, alltid tekst |

Kjente nøkler:

| Nøkkel | Beskrivelse | Auditlogges? |
|---|---|---|
| `aktiv_vakt_id` | Peker på gjeldende `Vakt` | Ja |
| `session_timeout_hours` | Sesjonslevetid i timer (1–24), default 8 | Ja |
| `oppdrag_lyd_aktiv`, `oppdrag_lyd_nytt`, `oppdrag_krev_grov_avreist` | Bilinnstillinger | Ja |
| `vaktliste.fil.*` | Mottakere og intervall for vaktlista på e-post | Ja |
| `next_patient_nr_vakt_<id>` | Pasientteller, atomisk med `select_for_update` | **Nei** |
| `next_oppdrag_nr_vakt_<id>` | Oppdragsteller | **Nei** |
| `cron.<jobbnavn>` | Siste kjøring av en cron-jobb | **Nei** |

**De tre siste er unntatt audit med vilje** (`core/signals.py`, `NOKLER_UTEN_AUDIT`).
Telleren skrives ved *hver* pasientregistrering — uten unntaket ville en vakt med hundre
pasienter gitt hundre auditrader ingen har laget, blandet inn mellom de ekte. Regelen er
«logg det et menneske har bestemt, ikke det maskinen har talt», og lista er en
**unntaksliste**: en ny nøkkel logges som standard.

### 4.8 `core.Backup` og `core.Backupplan`

`Backup` er metadata om en fil på volumet. `db_table = 'patients_backup'`, samme
begrunnelse som 4.7.

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `filename` | CharField | Filnavn uten sti |
| `kind` | CharField | `manual`, `auto`, `pre_reset`, `pre_restore` |
| `module_slug` | CharField | Hvilken handler som lagde den. **Slugen er hele forskjellen på en pasientfil og en hel database** |
| `size_bytes` | IntegerField | |
| `created_at` / `created_by` | | `SET_NULL` på bruker |
| `note` | TextField | |

`Backupplan` er **én rad per modul** — den erstattet singletonen `patients.BackupConfig`,
som var ett intervall for hele portalen:

| Feltnavn | Type | Beskrivelse |
|---|---|---|
| `slug` | CharField | Modulens slug, eller `standard`/`full` |
| `folger_standard` | BooleanField | Default `True`. `full` og `standard` styrer alltid seg selv |
| `modus` | CharField | `av`, `ved_endring`, `alltid`. Default `ved_endring` |
| `intervall_verdi` / `intervall_enhet` | | Tall + `minutt`/`time`/`dogn`. Default 1 time |
| `behold` | IntegerField | Cap på filer **på volumet**, default 50. Offsite styres av bucketen |
| `sist_sjekket_at` | DateTimeField | Ved hver vurdering |
| `sist_fil_at` | DateTimeField | Bare når noe faktisk ble skrevet |

**To tidsstempler, og begge trengs.** Uten `sist_sjekket_at` er «ingenting har endret
seg» umulig å skille fra «jobben er død».

**Registeret er fasit for hvilke moduler som finnes, ikke plantabellen.** En modul uten
plan får en med standardverdier første gang klokka ser handleren. Leste vi tabellen
direkte, ville en nyregistrert modul stått uten backup til noen tilfeldigvis åpnet
`/portal-admin/backup/` — og for et arkiv betyr manglende backup at kollapsen nekter å
kjøre, altså en feil som først viser seg to år senere.

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

*Gjennomgått 14. sep. 2026. Kapittelet dokumenterte 16 endepunkter av 123, og
tilgangskravene sto oppgitt som `admin`, `lead`, `read_write` — roller som ble slettet i
deploy 2. Begge deler er rettet, men **strukturen er endret med vilje**: se 5.0.*

### 5.0 Hva dette kapittelet er, og ikke er

Portalen har **145 endepunkter** (utenom Django-admin, som bare rutes under `DEBUG`).
En håndskrevet liste over alle sammen ville rotnet fra dagen den ble skrevet — nøyaktig
slik den gamle lista gjorde, med 16 oppføringer og ingen som merket at resten manglet.

Derfor: **konvensjonene og tilgangsmønsteret står her, fullstendig og etterprøvd.
Den autoritative lista over stier står i `urls.py`-filene**, og kommandoen under skriver
den ut.

Kjør dette i `python manage.py shell`:

```python
from django.urls import get_resolver
def gaa(res, p=''):
    for m in res.url_patterns:
        sti = p + str(m.pattern)
        if hasattr(m, 'url_patterns'):
            yield from gaa(m, sti)
        else:
            yield '/' + sti.lstrip('^').replace('\\', ''), m.callback
for sti, view in sorted(gaa(get_resolver())):
    print(f'{sti:60} {view.__module__}.{view.__name__}')
```

**Kart over hvor endepunktene bor:**

| Prefiks | Antall | Rutet i | Innhold |
|---|---|---|---|
| `/pasienter/` | 17 | `patients/urls.py` | Pasient-CRUD, registre, arkiv, vaktstyring |
| `/oppdrag/` | 34 | `oppdrag/urls.py` | Sentralbord, enhetsskjerm, stemplinger, verdimengder |
| `/vaktliste/` | 29 | `vaktliste/urls.py` | Ressurser, vaktposter, mannskap, drift, service worker |
| `/portal-admin/` | 21 | `core/urls_admin.py` | Hele adminflaten. Navnerom `portaladmin` |
| `/accounts/` | 9 | `accounts/urls.py` | Innlogging, MFA, passord |
| `/statistikk/` | 5 | `statistikk/urls.py` | Full statistikk per kilde |
| `/ko/` | 8 | `ko/urls.py` | Situasjonsbildet: sidebaren, loggen (les, skriv, rett, fjern) og ressurstavla (les, før status) |
| `/backlog/` | 9 | `backlog/urls.py` | Endringsønsker og bugs: lista med filtre, innmelding, kommentartråd, løst/gjenåpne, og typene i «Backloginnstillinger» |
| `/varsler/`, `/api/`, rot | 13 | `core/urls.py` | Dashbord, varsler (3 sider + 4 API), «min profil», manifest, `robots.txt`, `/healthz/` og videresendingen fra `/api/` |

**Noen stier er rene videresendinger** fra flater som har flyttet, og de er med i
tallene over. De står der fordi et bokmerke eller en lenke i en e-post ikke skal gi 404
etter en omorganisering:

| Gammel sti | Går til |
|---|---|
| `/accounts/users/`, `/accounts/users/ny/`, `/accounts/users/<pk>/` | `/portal-admin/brukere/…` |
| `/admin/server-status/…` og `/pasienter/admin/server-status/…` | `/portal-admin/server-status/…` |
| `/pasienter/api/full-stats/` og arkivvarianten | `/statistikk/api/kilde/patients/…` |
| `/statistikk/api/full-stats/` (uten kilde) | `/statistikk/api/kilde/patients/full-stats/` |
| `/api/…` (rot) | `legacy_root_redirect` |

`patients/tests_modul_dekorator.py` går gjennom `urlpatterns` og krever at **hvert view
under en modul er dekorert**. Unntak må stå i lista der, med begrunnelse. Det er den
mekanismen som gjør at et udekorert endepunkt ikke kan snike seg inn — ikke denne
dokumentasjonen.

### 5.1 Svarformat

Alle JSON-endepunkter følger samme form:

```json
{"status": "ok", "data": ...}
{"status": "error", "message": "..."}
```

Enkelte eldre endepunkter svarer `{"error": "..."}` med passende statuskode; det er den
formen `@modul_kreves(..., svar='json')` og `@rate_limit(on_limit='json')` selv
produserer ved avvisning.

### 5.2 Tilgangsmønsteret — dekoratøren gater lesing, viewet gater skriving

**Dette er det viktigste i kapittelet**, og det er grunnen til at et skriveendepunkt kan
se ut til å kreve bare `les`:

```python
@modul_kreves('patients', 'les', svar='json')      # porten inn
@rate_limit(group='patients:create', rate='60/m', method='POST')
def patients_list_view(request):
    if request.method == 'GET':
        ...                                         # lesing: dekoratøren holdt
    if not har_tilgang(request.user, 'patients', 'skriv_full'):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)
```

Grunnen er at det samme endepunktet betjener to ulike handlinger. Å sette `skriv_full` på
dekoratøren ville stengt lesing for dem som bare skal lese; å sette `les` og stoppe der
ville åpnet skriving for dem. **Metoden avgjør hvilket nivå som kreves, og den sjekken
hører derfor hjemme der metoden er kjent.**

Rate-limit-dekoratoren står **under** tilgangssjekken, og `group` oppgis alltid eksplisitt
— den er cache-nøkkelen, og to endepunkter må aldri dele teller.

### 5.3 Pasient-API-et (referanseeksempelet)

Verifisert mot `patients/urls.py` og dekoratørene 14. sep. 2026.

| Sti | Metoder | Lesing krever | Skriving krever |
|---|---|---|---|
| `/pasienter/` | GET | `patients:les` | — (HTML-side) |
| `/pasienter/api/settings/` | GET, POST | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/patients/` | GET, POST | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/patients/<pk>/` | GET, PUT, DELETE | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/forstehjelpere/` | GET, POST | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/forstehjelpere/<pk>/` | GET, PUT, DELETE | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/helsepersonell/` | GET, POST | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/helsepersonell/<pk>/` | GET, PUT, DELETE | `patients:les` | `patients:skriv_full` |
| `/pasienter/api/vakter/` | GET | `patients:les` **+ global admin** | |
| `/pasienter/api/avslutt-vakt/` | POST | `patients:les` **+ global admin** | |
| `/pasienter/api/gjenaapne-vakt/` | POST | `patients:les` **+ global admin** | |
| `/pasienter/api/innstillinger/arkiv/` | GET | `patients:les` | |
| `/pasienter/api/innstillinger/arkiv/lagre/` | POST | `patients:les` | **global admin** |
| `/pasienter/api/innstillinger/arkiv/<pk>/` | GET, DELETE | `patients:les` | **global admin** |
| `/pasienter/api/full-stats/` | GET | videresender til `/statistikk/…` | |
| `/pasienter/api/innstillinger/arkiv/<pk>/full-stats/` | GET | videresender | |

**De to registrene bygges av én fabrikk** (`patients/views_registre.py`) — førstehjelpere
og helsepersonell har identisk form, og fabrikken er grunnen til at dekoratøren ikke står
på en toppnivå-`def`.

**Vaktstyringen er global admin** fordi den er irreversibel i praksis: å avslutte en vakt
flytter pekeren, og pasientene som registreres etterpå havner et annet sted.

**Rate-limit-grupper i denne modulen:** `patients:create` (60/m POST),
`patients:detail-write` (120/m PUT/DELETE), `patients:arkiv` (10/m POST),
`patients:arkiv-slett` (10/m DELETE).

### 5.4 Statistikk

| Sti | Tilgang |
|---|---|
| `/statistikk/` | `les` på `statistikk` |
| `/statistikk/api/kilde/<slug>/full-stats/` | `les` på `statistikk` **og** `les` på kildemodulen |
| `/statistikk/api/kilde/<slug>/arkiv/<pk>/full-stats/` | Som over, **pluss global admin** |

**Modulen komponerer tilgang, den eier den ikke.** Den viser kun kilder brukeren har minst
`les` på i kildemodulen — ellers ville aggregatene gitt avledet innsyn i data brukeren
ikke har tilgang til. Regelen er «vis det du har tilgang til», ikke «alt eller ingenting»:
med to kilder ville det siste tatt statistikken fra alle som leser pasienter uten å ha
oppdrag.

**Arkiv-endepunktet har to gates**, og det er bevisst: arkivet er strengere beskyttet enn
live-statistikken, og hadde det arvet modulens gate ved flyttingen, ville alle med `les`
fått innsyn i arkiverte vakter uten at noen bestemte det.

Cachet 60 sekunder, med ETag/304. Cache-nøkkelen bærer **både slug og vakt-ID** — delte
de nøkkel, ville kilde nummer to servert kilde éns tall i et minutt.

### 5.5 Adminflaten (`/portal-admin/`)

21 ruter, alle i `core/urls_admin.py` under navnerommet `portaladmin`, og alle bak
`@admin_required`. `core/tests_sikkerhet_runde2.py` går gjennom hele prefikset med anonym
og vanlig bruker.

Hovedgruppene: innstillinger, moduler, auditlog (med CSV-eksport), backup (plan, kjør,
gjenopprett, slett), brukere (liste, ny, detalj, slett), innloggingslogg og server-status.

**Navnerommet ble samlet 14. sep. 2026.** Fram til da lå rutene spredt mellom `accounts:`
og `core:`, og en URL-snapshot som sammenlignet `pattern.name` uten navnerom meldte
«identisk» mens hver `{% url 'accounts:…' %}` var død. `core/tests_malenes_urler.py`
skanner nå hver `{% url %}` i hver mal.

### 5.6 Oppdrag og vaktliste

Disse to er de største flatene (31 og 28 ruter) og dokumenteres i sine egne
beslutningsnotater — `docs/BESLUTNING_OPPDRAGSMODULEN.md` og
`docs/BESLUTNING_VAKTLISTE.md` — som forklarer *hvorfor* endepunktene ser ut som de gjør.
`CLAUDE.md` har reglene som gjelder når man rører dem.

To ting som er verdt å kjenne herfra, fordi de er uvanlige:

**Bilens stemplinger er navngitte endepunkter, ikke en generell `PUT`.** Enhetskontoen har
`skriv_handling`, og hver overgang har sin egen URL (`status/<overgang>/`). Retningen står
i URL-en og ikke i kroppen, fordi et veksle-endepunkt gir et kappløp når to trykk kommer
tett. Samme grep i vaktlistas `drift/<start|stopp>/`.

**Besetningen går én vei: `vaktliste` → `oppdrag`.** Sentralbordet henter
`/vaktliste/api/enhet/<pk>/besetning/`; oppdragsmodulen importerer ikke vaktlista.
`OppdragImportererIkkeVaktlista` leser importene med AST og håndhever det.

### 5.7 Uten innlogging

| Sti | Hvorfor |
|---|---|
| `/healthz/` | Railways health-check |
| `/manifest.webmanifest` | Må være en view og ikke en statisk fil, fordi ikonstiene skal gjennom `{% static %}` — WhiteNoise hasher navnene |
| `/robots.txt` | Holder portalen ute av søk |
| `/vaktliste/sw.js` | En service worker styrer bare stier under sin egen, og kan ikke kreve sesjon. Egen CSP begrenset til `'self'` |
| `/accounts/login/`, passord-reset, invitasjon | Selvsagt |

Alle står som navngitte unntak i `patients/tests_modul_dekorator.py`, med begrunnelse.

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

### 6.3 Tilgangsmodellen

Tre kategorier, ikke én. Se `docs/BESLUTNING_ROLLEMODELLEN.md` for begrunnelsene.

1. **Global admin** (`CustomUser.role == 'admin'`) — brukeradmin, backup, moduloppsett, audit, arkiv, og alt irreversibelt. Står utenfor modulaksen og trenger ingen `ModulTilgang`-rader.
2. **Modulbasert** — `accounts.ModulTilgang(bruker, modul_slug, nivaa)`. **Fravær av rad er ingen tilgang**; det finnes ingen `'ingen'`-verdi å lagre.
3. **Globalt uten admin** — innlogging, min profil, passordbytte, MFA. Krever bare innlogging.

Nivåene er en ordnet stige:

| Nivå | Betyr |
|---|---|
| *(ingen rad)* | Modulen er usynlig, og URL-en gir 403 |
| `les` | Kan se modulens data — i vaktlista: **bare sitt eget korps** |
| `les_alle` | Vaktlista: ser alle korps. Deklareres kun der |
| `skriv_handling` | Navngitte overganger uten å lese request-kroppen. **I bruk siden oppdragsmodulen** (bilens stemplinger) og i vaktlista (fører sitt eget korps) |
| `skriv_full` | Kan redigere felter |
| `skriv_leder` | Kan sette opp — oppretter og fjerner det de andre redigerer |

**`skriv_leder` (30. aug. 2026)** deklareres av vaktlista og, fra 12. sep. 2026, av
oppdragsmodulen. Skillet mot `skriv_full` er *hva slags skade en feil gjør*: den som
bemanner setter folk på plasser og kan rette tilbake; den som setter opp fjerner en
ressurs, og bemanningen forsvinner med den. Uten trinnet måtte de to deles ut samlet,
eller oppsettet bli global admin — og da kunne ikke en vaktleder lage sin egen vaktliste
uten å få brukeradmin, backup og arkiv på kjøpet.

**Hver modul deklarerer hvilke nivåer den bruker** (`Module.nivaaer`) og gir dem sin egen
etikett (`Module.nivaa_navn`) — se 4.2. **Ukjent nivånavn gir `False`, ikke `True`.**

Håndhevet med `@modul_kreves('patients', 'skriv_full')` fra `core/auth_decorators.py`.
`patients/tests_modul_dekorator.py` går gjennom `urlpatterns` og krever at hvert view under
en modul er dekorert — risikoen ved dekoratør framfor middleware er en glemt dekoratør, og
den lukkes ikke av en manuell gjennomgang.

`ModuleSettings.enabled=False` gir 403 for alle andre enn global admin.

**`CustomUser.role` er kontotype, ikke tilgangsnivå.** Avviklingen er fullført: feltet
krympet til `admin`/`bruker` i deploy 2, sammen med `has_role_at_least`, `role_required`,
`write_required` og `stats_required`. De fem `kan_redigere_*`-flaggene ble slettet i
deploy 3.

Skal en ny modul gates, trengs **ingen kolonne** på `CustomUser` — en `ModulTilgang`-rad
er hele mekanismen. Det var nettopp det flaggene gjorde galt: de la tilgang i skjemaet i
stedet for i data, og en modul som ikke hadde noe flagg kunne ikke gates i det hele tatt.

*Tester lager brukere med `accounts.test_helpers.gi_standardtilgang(bruker, profil)`, og
profilen oppgis eksplisitt — en test som glemmer kallet tester 403-stien uten å vite det.*

Frontend gater på `window.MODUL_TILGANG` (satt av malen), ikke på rollen, og skjuler
`.write-only` og `.admin-only` via `applyRoleVisibility()` i `patients-utils.js`.
**Standarden er ingen tilgang:** mangler globalen, skjules alt som krever noe.

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

`SecurityHeadersMiddleware` (`core/middleware.py` — flyttet fra `patients` 14. sep. 2026)
setter følgende på alle responser:

| Direktiv / header | Verdi | Merknad |
|---|---|---|
| `default-src` | `'self'` | |
| `script-src` | `'self' 'nonce-…'` | **Ingen vertsnavn** (13. sep. 2026). Bootstrap, ikonene, Tabulator og Chart.js ligger under `static/vendor/`. Med `cdn.jsdelivr.net` i lista kunne én HTML-injeksjon lastet en vilkårlig npm-pakke, nonce eller ei |
| `style-src` | `'self' 'unsafe-inline'` | **Kjent avvik.** Markup har ~50 inline style-attributter; står som åpent punkt i `TODO.md` |
| `img-src` | `'self' data:` | QR-koder rendres som data-URL |
| `font-src` | `'self' data:` | |
| `media-src` | `'self' blob:` | **14. sep. 2026.** `_stilleLydbaerer()` i `oppdrag-enhet.js` bygger en stum WAV som Blob — uten den demper iOS' ringebryter lydvarselet, fordi Web Audio alene regnes som «ambient». `default-src` dekker ikke `blob:`, så direktivet må stå eksplisitt. Å slakke `default-src` i stedet ville sluppet blob-er inn i alt som arver |
| `connect-src` | `'self'` | |
| `frame-ancestors` | `'none'` | |
| `base-uri`, `form-action` | `'self'` | |
| `object-src` | `'none'` | |
| `Referrer-Policy` | `same-origin` | |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | |

**Nonce, ikke `unsafe-inline`.** Når CSP inneholder et nonce, *ignorerer* nettleseren
`'unsafe-inline'` for samme direktiv — det finnes ingen mellomting. Hver inline `<script>`
må ha riktig nonce, og inline event-handlere (`onclick=`) dekkes ikke av nonce i det hele
tatt; de er flyttet til `data-action`-delegering.

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
- XSS-beskyttelse via auto-escape i templates + manuell escaping i JavaScript: `escapeHtml()`/`_escHtml` i pasientskjemaet (`patients-forms.js`) og i admin-visningene (`patients-admin.js`), og `escHtmlValue()` i statistikk-tabellene (`statistikk.js`, `statistikk-oppdrag.js`).
  - `escHtmlValue()` skiller «ikke satt» (`null`/`undefined`) fra falsy verdier, slik at tallet 0 vises i tabellceller i stedet for å bli tom streng. Det er grunnen til at den finnes ved siden av de to eldre hjelperne.
  - `trustedHtml()` markerer markup koden bygger selv (signifikans-merker i `renderTester`, prosentbjelker i `mkObsTable`). `cellHtml()` slipper klarerte celler gjennom og escaper alt annet, så unntaket blir et bevisst valg per celle.
  - `patients/tests_xss_stats.py` kjører byggerne i node mot HTML-holdige feltverdier, og har i tillegg en statisk vaktpost som krever at hver `${...}` i byggerne er escapet eller står på en gjennomgått unntaksliste med begrunnelse.
- SQL-injection-beskyttelse via Django ORM (ingen raw SQL).
- Ingen path traversal i backup-filnavn – filnavn genereres server-side.
- Generisk feilmelding ved backup-restore (lekker ikke interne detaljer).
- **Data inn i et `<script>`-element går gjennom `core.jsdata.js_json()`**, aldri
  `json.dumps` + `|safe`. `json.dumps` escaper ikke `<`, så et arrangementsnavn eller et
  mannskapsnavn som inneholder `</script>` lukker skriptet og gjør resten til markup.

### 7.9b Klient-IP (`core/klientip.py`, 13. sep. 2026)

**`klient_ip(request)` er det ene stedet IP-en leses:** siste ledd i `X-Forwarded-For` —
det Railway selv la til — validert, ellers `REMOTE_ADDR`. **Første ledd er klientens egen
påstand** og kan settes fritt av den som ringer.

Innloggingsloggen, audit-signalene, arkivene og rate-limit-bøttene per IP bruker den.
`REMOTE_ADDR` direkte er proxyen i produksjon, altså samme adresse for alle — en
rate-limit-bøtte på den ville strupt hele portalen når én bruker gjettet passord.

### 7.9c Avhengigheter låst med hasher

`requirements.in` er ønskene, `requirements.txt` er det `pip-compile --generate-hashes
--strip-extras` løste dem til, og det er den Railway installerer. Uten hasher kan en
kompromittert pakke på PyPI bytte innhold under samme versjonsnummer uten at noe i
prosjektet merker det.

### 7.10 Audit

- Hver pasientendring logges på feltnivå (`AuditLog`). Feltlista utledes fra modellen
  selv, så et nytt felt kan ikke falle utenfor loggen stilltiende.
- Oppdrag, mannskap, skift, ressurser og vaktlistestatus logges på samme måte.
- **Portalens egne tabeller siden 14. sep. 2026** (`core/signals.py`): `AppSetting`,
  `ModuleSettings` og `Vakt`. Å slå av en modul for *alle*, eller flytte sesjonstimeouten,
  satte tidligere ingen spor. Tellere (`next_patient_nr_vakt_*`) og cron-status er
  unntatt — se 4.7.
- Fritekstfelter (`Oppdrag.fritekst`, `Mannskap.notat`, `Vaktpost.merknad`) logges som
  **endret, men uten verdier**: raden sier at feltet ble rørt, av hvem og når.
- Innlogging, MFA-hendelser og passordbytte logges som `LoginEvent`.
- Backup-opprettelse, gjenoppretting og sletting logges. **Gjenopprettingen logges av
  `restore_backup` selv**, ikke av viewet, slik at både nettleseren og kommandolinja
  etterlater nøyaktig én rad med hvem og hvorfra.
- *«Nedlasting» sto i denne lista fram til 14. sep. 2026. Funksjonen finnes ikke og skal
  ikke finnes — se 8.8.*

---

## 8. Backup-systemet

*Skrevet om 14. sep. 2026. Kapittelet beskrev fram til nå singletonen
`patients.BackupConfig`, konstanten `BACKUP_EXCLUDE` og en restore som «kun rører
pasientdata». Alle tre er borte — den første slettet i `patients/0017`.*

### 8.1 To lag, og de svarer på hvert sitt spørsmål

| Lag | Spørsmål det svarer på |
|---|---|
| **Modulfiler** (seks) | «Pasientlista ble slettet ved et uhell — kan jeg få den tilbake uten å røre noe annet?» |
| **Hel database** (`full`) | «Railway-prosjektet er borte — kan jeg reise portalen på nytt et annet sted?» |

Ni handlere i registeret:

| Slug | Fil | Innhold |
|---|---|---|
| `portal` | `core/backup/portal.py` | `core.Vakt`, `ModuleSettings`, `AppSetting`. **Først i gjenopprettingsrekkefølgen** |
| `patients` | `patients/backup.py` | Pasientdata. Arkivmodellene eksplisitt ekskludert |
| `arkiv` | `patients/backup.py` | `VaktArkiv` + `ArkivertPasient` |
| `oppdrag` | `oppdrag/backup.py` | Oppdrag, statusmeldinger, enheter, lokasjoner, verdimengdene |
| `oppdrag_arkiv` | `oppdrag/backup.py` | `OppdragArkiv` + `ArkivertOppdrag`. Er også **sperren** foran kollaps |
| `vaktliste` | `vaktliste/backup.py` | Korps, mannskap, kompetanser, ressurser, vaktposter, vaktlister |
| `ko` | `ko/backup.py` | KO-loggen. **Backup, ikke arkiv** — loggen fryses aldri med signatur |
| `backlog` | `backlog/backup.py` | Innspill. Eneste modulfil uten plass i rekkefølgen |
| `full` | `core/backup/full.py` | **Hele databasen** unntatt sesjoner, contenttypes, rettighetsrader, Django-admins logg og backup-metadata |

Gjenoppretting i tom base går i rekkefølge — **portal → patients → arkiv → oppdrag →
oppdrag_arkiv → vaktliste → ko**. Tas ikke `portal` først, feiler de andre med
«Key (vakt_id)=(1) is not present in table core_vakt», fordi alt utenom `backlog` peker på
vakta med et heltall.

**Men vakta er ikke den eneste bindingen, og det sto ikke skrevet noe sted før 17. sep.
2026.** `vaktliste.Ressurs.enhet` peker på `oppdrag.Enhet` — også et heltall, siden `Enhet`
ikke har noen natural key. Tas `vaktliste` før `oppdrag`, feiler lastingen med
«vaktliste_ressurs.enhet_id contains a value '1' that does not have a corresponding value in
oppdrag_enhet.id». Den som leste den gamle begrunnelsen og stokket om, ville lagt `vaktliste`
rett etter `portal`.

Fasiten står i `core.backup.GJENOPPRETTINGSREKKEFOLGE`; `bindinger()` i samme modul utleder
kantene fra modellene, og `AlleFileneGjenopprettesTests` krever at rekkefølgen holder dem.

**Den hele fila er selvbærende, og det er poenget.** Den inneholder brukere,
passord-hasher, MFA-hemmeligheter og audit-logg, fordi en tom base ikke har noen å logge
inn som. Modulfilene strippes derimot for FK-er ut av eget datasett (`strip_fields`): med
`natural_foreign` lagres de som brukernavn, og er kontoen slettet feiler hele
gjenopprettingen — altså akkurat når man trenger backupen.

### 8.2 `core.Backupplan` styrer hva som skjer når

Se 4.8 for feltene. Tre moduser (`av`, `ved_endring`, `alltid`), fritt intervall, og
`behold` som cap **på volumet**. Oppbevaringen offsite er noe helt annet og styres av
bucketens livssyklusregler.

### 8.3 Klokka er en tråd, ikke en cron-jobb

`core/backup/klokke.py` starter en tråd i web-prosessen. **Et Railway-volum kan bare
henge på én tjeneste**, og `/data` henger på web-tjenesten. En cron-tjeneste som tok
backup ville skrevet fila til sitt eget flyktige containerfilsystem, opprettet
`Backup`-raden, og forsvunnet med fila — og `core.arkiv.har_backup_etter()` spør bare
etter raden. Kollapssperra ville dermed åpnet seg på spøkelsesbackuper, og slettet
radnivået i et arkiv uten dekning.

`BackupSchedulerMiddleware` står igjen som reservenett gjennom samme `kjor_forfalte()`.
Den er også det eneste stedet som kan varsle om at tråden har stoppet — et varsel om at
klokka er død, sendt av klokka, kommer aldri fram.

### 8.4 Slettelista utledes, den skrives ikke

`get_restore_models()` regner ut lista topologisk fra `apps` minus `exclude`, barn før
foreldre. Den håndskrevne lista var et gjeldspunkt: `Lydvarsel` var med i dumpen, glemt i
slettelista, og radene ble stående igjen etter en gjenoppretting.
`SlettelistaDekkerDumpenTests` håndhever at hver modell som dumpes også tømmes.

### 8.5 `@ikke_under_loaddata` er ikke valgfritt

Django sender `raw=True` når `loaddata` skriver en rad. Uten vakten fyrer audit-signalene
under en gjenoppretting: de leser relaterte objekter som kanskje ikke er lastet ennå
(«Mannskap matching query does not exist» midt i en gjenoppretting), og de skriver en
auditrad per lastede rad. Selve gjenopprettingen logges av `restore_backup`, med hvem som
gjorde den og hvorfra.

`SignalerFyrerIkkeUnderLoaddataTests` leser alle `*/signals.py` og krever vakten. Den
scannet en håndskrevet liste over tre apper fram til 14. sep. 2026, og ville ikke sett
`core/signals.py` den dagen den ble skrevet.

### 8.6 Offsite til Scaleway

`create_backup` kaller `offsite.meld_ny_backup(backup, path)` etter at fila er skrevet.
Funksjonen er **inert** uten `OFFSITE_S3_BUCKET`, nøklene og `OFFSITE_BACKUP_KEY`, og
**kaster aldri**: volumet er første nett, og feilen står i `OffsiteKopi.feil` og på
`/portal-admin/backup/`.

**Komprimeres først, krypteres så.** Rekkefølgen er ikke vilkårlig — chiffertekst lar seg
ikke komprimere, mens gzip på dumpdata-JSON gir 5–15 % av rå størrelse. AES-256-GCM,
format `SPBK1` + nonce + chiffertekst.

**To prefikser, ett per oppbevaringstid:** `backups/` (730 dager) og `full/` (90 dager).
Fristene kan bare skilles i bucketen hvis filene ligger på hver sin sti, fordi
livssyklusreglene filtrerer på prefiks.

**Fristene håndheves av Scaleway, ikke av oss.** Nøkkelen har ikke sletterett, og
`enforce_cap` rører bare volumet. `offsite.livssyklus()` leser derfor reglene *tilbake*
fra bucketen, og `_avvik()` sammenligner dem med `FORVENTET_DAGER` på **nøyaktig**
prefiks: `/full` er ikke `full/`, og en regel som treffer ingenting er en oppbevaringstid
som stille ble uendelig.

### 8.7 Kommandolinja

| Kommando | Hva den gjør |
|---|---|
| `backup_kjor` | Manuell kjøring av klokkas arbeid |
| `hent_offsite --list` / `hent_offsite <fil>` | Henter og dekrypterer fra bucketen til volumet. **Rører ikke basen** |
| `gjenopprett --list`/`--siste <modul>`/`--hent <objekt>`/`--full`/`--ja` | **Den som rører basen.** Finnes fordi veien gjennom nettleseren ikke duger i en tom base |
| `verifiser_backup` [`--full`] | Laster filene inn i en engangsbase og sammenligner radene |

**`--ja` er nødvendig, ikke bekvemt:** `railway ssh -- <kommando>` har ingen terminal, så
et spørsmål ville hengt — i en katastrofe.

`verifiser_backup` kaller `gjenopprett`, ikke `restore_backup`: da er det veien man
faktisk ville brukt som er prøvd, ikke en nabo til den. Engangsbasen er en flyktig
SQLite-fil, og `PORTAL_ENGANGSBASE=1` er den ene navngitte åpningen i `settings.py`-sjekken
som ellers krever PostgreSQL på Railway.

### 8.8 Det finnes ingen nedlastingsknapp

Heller ikke for modulfilene. En `.json.gz` med hele pasientregisteret i nedlastingsmappa
er en helseopplysningsdump utenfor portalens kontroll, og den hele fila bærer i tillegg
passordhasher og TOTP-hemmeligheter. Kontroll av innhold gjøres med `verifiser_backup`.

### 8.9 Ingen vei utenom `core/backup/`

`core/backup/service.py`, `db_backup`-kommandoen og `patients.BackupConfig` er slettet
(14. sep. 2026). Proxyen lot en modul ta backup **uten å oppgi slug**, og slugen er hele
forskjellen på en pasientfil og en hel database. Enhver modul, pasientmodulen inkludert,
registrerer en handler og kaller `core.backup.create_backup(slug=...)`.
`patients/tests_backup.py` håndhever at de tre ikke kommer tilbake.

---

## 8A. Observability og drift

### 8A.1 Oversikt

Observability-laget er et lett, selvstendig rammeverk for teknisk telemetri. Det skal gi administrator svar på «hvordan har tjenesten det akkurat nå?» uten å logge pasientdata og uten å vedlikeholde ekstra infrastruktur (Prometheus, Grafana, Sentry osv.). Komponentene er:

- `RequestMetricsMiddleware` – samler per-request-telemetri i en in-memory ringbuffer.
- `/portal-admin/server-status/` – HTML-dashbord for administratoren.
- `/portal-admin/server-status/json/` – tilsvarende snapshot i JSON for automatisering og overvåkning.

Alle komponenter er isolert til `patients`-appen og har ingen eksterne avhengigheter.

### 8A.2 RequestMetricsMiddleware

Definert i `core/middleware.py` som `RequestMetricsMiddleware`. Lagrer en thread-safe ringbuffer med de siste 500 requestene. Hver sample inneholder:

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

**Tilgang:** Global admin (`@admin_required`). Alle andre får 403, også de med
`skriv_leder` på en modul — dashbordet viser tall på tvers av alle moduler.
`core/tests_sikkerhet_runde2.py` går gjennom hele `/portal-admin/`-prefikset med anonym
og vanlig bruker.

Dashbordet viser følgende paneler:

| Panel | Innhold | Kilde |
|---|---|---|
| Requestmetrics | p50 / p95 / max / feil for 1-min og 5-min vindu | `RequestMetricsMiddleware`-ringbufferen (Redis på tvers av workere når den finnes) |
| Tregeste stier | P95 og antall per sti siste 5 min, stier med under tre treff utelatt | `metrics_store.tregeste_stier()` |
| Minne (RSS) | Nå og topp siden oppstart, i MB | `/proc/self/status` (`VmRSS`) og `resource.getrusage().ru_maxrss` |
| Database | Type, svartid på `SELECT 1`, tilkoblinger mot `max_connections` (PostgreSQL) | `connection.cursor()`, `pg_stat_activity`, `pg_settings` |
| Disk | Brukt/ledig på volumet, størrelsen på backupfilene | `shutil.disk_usage(BACKUP_DIR)` |
| Aktive sesjoner | Antall ikke-utgåtte `django.contrib.sessions.Session`-rader, med liste og utlogging | DB-spørring |
| Siste backup | Filnavn, størrelse, tidspunkt og type, pluss offsite-kopien (konfigurert, antall, sist, siste feil) | `Backup`-modellen og `core.offsite.status()` |
| Vaktbildet | Aktiv vakt, vaktlister i drift, oppdrag på tavla/ventende/trenger ressurs, siste vaktlistefil | `hent_aktiv_vakt()`, `Vaktliste`, `Oppdrag`, `Utsending` |
| Konfigsjekk | DEBUG, RATELIMIT_ENABLE, HTTPS, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, cache, e-posttransport, ADMINS, offsite — ✓/✗ per rad, og versjon | `settings`, `core.versjon.hent_versjon()` |
| Innlogging siste time | Feilede og vellykkede innlogginger, brukernavn/IP-er bak feilene, avviste MFA-koder | `LoginEvent` |
| Cron-jobber | Siste kjøring av `purge_old_logs` og `kollaps_arkiv` — tid, ok/feil, melding. «Aldri» til jobben har kjørt én gang | `AppSetting['cron.<navn>']` via `core.kommando.siste_kjoringer()`. Lista er `CRON_JOBBER`; **`db_backup` sto der uten å være satt opp i Railway og ble fjernet 13. sep. 2026** — se 8.3 for hvorfor backup ikke kan være en cron-jobb |
| E-post | Transport (AHASend/SMTP/konsoll), siste vellykkede og feilede utsending | `settings.EMAIL_BACKEND`, `Utsending` |
| Worker-config | `WEB_WORKERS`, `WEB_THREADS`, `WEB_MAX_REQUESTS` og PID | Env-variabler og `os.getpid()` |

Dashbordet polles hvert 10. sekund fra JSON-endepunktet; requestene til
server-status er unntatt fra metrikkene, så det bidrar ikke til tallene det
viser. Hver innhenter fanger sine egne feil og legger dem i svaret, så én
del som er nede tar ikke ned siden.

### 8A.4 JSON-endepunkt

**URL:** `/portal-admin/server-status/json/`

Returnerer nøyaktig samme data som HTML-dashbordet, men i maskinlesbart JSON-format. Tiltenkt bruk:

- Ekstern overvåkning (f.eks. UptimeRobot med nyere JSON-content check, eller en enkel bash-skript-cron).
- Automatiske alarmer basert på p95 / feil-antall.
- Innhenting av snapshot for feilsøking.

Endepunktet krever fortsatt global admin og innlogget sesjon – det er **ikke** et åpent metrics-endepunkt. **Feilmeldinger går gjennom `_scrub_secrets()`** før de sendes til klienten, så et Redis- eller Postgres-passord i en URL-streng ikke havner i svaret.

### 8A.5 Feature-flag-systemet — fjernet

Flagget `feature.live_stats_enabled` og endepunktet `/portal-admin/server-status/flag/`
ble fjernet 13. sep. 2026. Funksjonen det skulle styre ble aldri bygget, og et kort for et
flagg uten funksjon var støy på dashbordet. Trengs en bryter senere, er `AppSetting`
fortsatt stedet — se portalinnstillingene for mønsteret.

> *Ryddet 14. sep. 2026:* under dette avsnittet sto en **hengende tabellrest** og to
> avsnitt som beskrev flagget som om det fantes — med en `is_feature_enabled()` i
> `core/stats_cache.py` og en POST-rute for å endre det. Ingen av delene finnes. Det er
> den vanligste formen for dokumentråte: slettingen ble gjort i overskriften, men ikke i
> kroppen, så avsnittet motsa seg selv fra én linje til den neste. Eneste spor som står
> igjen i koden er `patients/tests.py`, som bruker nøkkelen som en vilkårlig
> `AppSetting`-verdi i en test — den har ingenting med noe flagg å gjøre.

---

## 8B. Stats-cache og ETag/304

### 8B.1 Formål

`/api/stats/` og `/api/full-stats/` gjør betydelig arbeid (aggregeringer og i tilfellet `full_stats_view` også scipy-tester). Når flere brukere har statistikkfanen åpen samtidig, vil de samme beregningene kjøres for hver klient. Stats-cache-modulen reduserer dette til én beregning per TTL-vindu og tilbyr i tillegg `If-None-Match`/304 på klientsiden slik at nettleseren slipper å laste ned ubrukt respons-body.

### 8B.2 Modulen `core/stats_cache.py`

*Rettet 14. sep. 2026: signaturen under sto feil. Dokumentasjonen viste
`@cached_stats_response(ttl=15, key_prefix=...)`, som ville gitt `TypeError` — parameteren
heter `cache_key` og kommer først. Og påstanden om at nøkkelen bygges av «aktivt år og
rollen som ber om dataene» stemte ikke: `active_year` finnes ikke lenger (vakt erstattet
år), og rollen inngår **ikke** i nøkkelen. Den feilen var farlig i begge retninger — den
lovet en isolasjon per rolle som ikke finnes, og skjulte kravet som faktisk gjelder.*

Hovedkomponenten er dekoratøren:

```python
def cached_stats_response(cache_key: str, ttl: int):
    ...

# Ekte kallsted, statistikk/views.py:
@cached_stats_response(cache_key=f'full:{handler.slug}:vakt:{vakt.pk}', ttl=60)
def _full_stats(request):
    ...
```

Dekoratøren håndterer både server-side caching og client-side ETag-validering.

**`cache_key` må bære variasjonen selv.** Den fulle nøkkelen er bare
`f'{CACHE_PREFIX}:{cache_key}'`, altså `statscache:` + det kallstedet oppgir. Dekoratøren
vet ingenting om vakt, kilde eller bruker.

Det er et bevisst valg, og det legger ansvaret på den som dekorerer:

- **Slug og vakt-ID er begge med** i nøkkelen for full statistikk. Delte to kilder nøkkel,
  ville kilde nummer to servert kilde éns tall i 60 sekunder. Og uten vakt-ID ville et
  vaktbytte servert forrige vakts tall.
- **Rollen er ikke med, og skal ikke være det.** Tilgangen avgjøres av gaten *før*
  dekoratoren; to brukere som begge slipper inn skal se de samme tallene. Å legge rollen i
  nøkkelen ville multiplisert cachelinjene uten å beskytte noe.

**Cache-prefiks:** alle nøkler starter med `statscache:`, så de er enkle å kjenne igjen.

**Det finnes ingen eksplisitt invalidering** — cachen utløper på TTL. De korte TTL-ene er
valgt nettopp for å slippe invalideringslogikk, og **alle cache-operasjoner er pakket i
try/except**, slik at en død cache degraderer til vanlig beregning i stedet for å ta ned
endepunktet.

### 8B.3 SHA-256 weak ETag

Når et svar beregnes eller hentes fra cachen, genereres en ETag som følger:

```python
body = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
digest = hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]
return f'W/"{digest}"'
```

*(Gjengitt ordrett fra `core/stats_cache.py` 14. sep. 2026. Avviket fra det som sto her
før: `separators` og `default=str` er med — det siste fordi payloaden inneholder
`datetime`-verdier som ellers ville gitt `TypeError` — og digesten kortes til 16 tegn.)*

**`sort_keys=True`** er kritisk: iterasjonsrekkefølgen i en dict kan variere mellom
prosesser, og en ustabil ETag er verdiløs som valideringsmekanisme — den ville gitt 200
der 304 var riktig, hver gang svaret kom fra en annen worker. Med `sort_keys` er digesten
deterministisk for et gitt datasett.

**16 tegn av digesten** holder her: ETagen skal skille to versjoner av samme endepunkt fra
hverandre, ikke motstå en angriper som konstruerer kollisjoner. En kollisjon ville i verste
fall gitt en klient et minutt gamle tall.

**Weak ETag (`W/`-prefiks):** Signalet «semantically equivalent», som er riktig her – vi tillater at to teknisk ulike JSON-representasjoner (samme data i samme rekkefølge) regnes som like.

### 8B.4 Cache-TTL

| View | TTL | Begrunnelse |
|---|---|---|
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
2. **`core/stats_cache.py`** — cacher full statistikk per kilde og vakt (60s TTL). Med LocMemCache + 2 workers regnes statistikken to ganger. *(`/api/stats/` sto her; endepunktet ble **slettet** 28. aug. 2026 — det matet aldri header-chipsene, som regnes ut i `patients-table.js` fra pasientlista, og var en rest fra Flask-porten uten kjent konsument.)*
3. **Cache-helsesjekk i `core/admin_status.py`** — `_get_cache_health()` skriver, leser og sletter en probe-nøkkel for å verifisere at backenden funker. Resultatet vises på admin-dashbordet (Cache-backend-kort).
4. **RequestMetrics i `core/middleware.py`** — Bruker Redis direkte (via `redis`-biblioteket, ikke `cache.set/get`-API-et) til å aggregere request-metrikker på tvers av workere når `REDIS_URL` er satt. I lavkostnad-modus (LocMem) brukes lokal deque per prosess. Se 8E for detaljer.

### 8C.3 Failsafe ved Redis-nedetid

Django's innebygde RedisCache (innført i Django 4.0) har **ikke** en innebygd `IGNORE_EXCEPTIONS`-option slik tredjepartspakken `django-redis` har. Det betyr at hvis Redis-tjenesten er helt nede, kan første cache-operasjon kaste en `ConnectionError` opp i request-stack-en.

Delvis avhjelping:

- **`django-ratelimit`** failopener av seg selv når cache-backenden kaster — requesten slippes gjennom uten å telles. Dette er innebygd i biblioteket.
- **Stats-cache** (`core/stats_cache.py`) er pakket inn i try/except slik at endepunktet går tilbake til å regne statistikken direkte ved cache-feil. Både `cache.get`, `cache.set` og `cache.delete` er beskyttet, så feil i én operasjon stopper aldri request-flyten.
- **Brukerlåsing** (5 feil passord → `locked_until`) går mot DB og er IKKE påvirket av cache-feil.
- **Cache-helsesjekken** (`_get_cache_health()` i `core/admin_status.py`) fanger alle exceptions og rapporterer `healthy=false` med `error`-streng på admin-dashbordet i stedet for å la feilen propagere.

Resultat ved Redis-utfall: noen få requests kan få 500-feil under selve utfallet, men sikkerhets-mekanismene som går mot DB står. Railway restarter Redis-tjenesten automatisk hvis den krasjer, og fallback til LocMemCache kan tvinges fram ved å fjerne `REDIS_URL`-variabelen (krever redeploy så Django re-evaluerer `CACHES`-blokken).

#### Sanering av credentials i feilmeldinger (`_scrub_secrets`)

En feil fra en cache- eller databasedriver kan bære forbindelsesstrengen i
`repr(exc)`, og på Railway inneholder den passordet
(`redis://default:<passord>@host:port`). Admin-status-data ender dessuten ofte i logger,
skjermbilder og support-e-poster. Derfor kjøres feilstrenger gjennom `_scrub_secrets()`
før de forlater serveren:

```python
# core/admin_status.py — gjengitt ordrett 14. sep. 2026
_URL_CREDS_RE = re.compile(r'([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@\s]*@)')


def _scrub_secrets(text: str) -> str:
    if not text:
        return text
    return _URL_CREDS_RE.sub(r'\1[scrubbed]@', text)
```

*Koden som sto her før var ikke implementasjonen — den hadde et annet mønster
(`(\w+://)(bruker):(passord)@`) og en annen erstatning (`***:***@`), og den pekte på
`patients/admin_status.py` og et endepunkt `/api/admin-status/` som ikke finnes. Det er
verdt å merke seg forskjellen: **den ekte regexen krever ikke kolon i credential-delen**,
så den treffer også `redis://token@host`, som den dokumenterte formen ville sluppet
gjennom.*

Resultat: `redis://default:hemmelig@redis.railway.internal:6379` blir
`redis://[scrubbed]@redis.railway.internal:6379`. Alle URL-skjema behandles likt.

**Funksjonen dekker bare URL-credentials.** Den fjerner ikke hemmeligheter i andre
former — et API-token i en feilmelding uten URL står igjen. Det er en kjent grense, ikke
en glipp: hver innhenter på dashbordet fanger sine egne feil, og det er der man vurderer
hva som er trygt å vise.

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

1. **Rate-limiting (`django-ratelimit`)** — uten Redis har hver worker sine egne tellere.
   Med 2 workers blir effektiv grense per IP/bruker fordoblet, med 3 tredoblet.
   Innloggingen håndheves med eksplisitte kall i `accounts/views.py`: **`10/5m` per
   brukernavn og `50/5m` per IP** (`login:username` og `login:ip`). Samme `10/5m` gjelder
   MFA-oppsett, MFA-verifisering og gjetting av gammelt passord ved passordbytte.
   *(Dokumentet oppga tidligere `5/m` — den raten finnes ikke noe sted i koden.)*
2. **Stats-cache (`core/stats_cache.py`)** — uten Redis regner hver worker statistikken
   sin egen gang og produserer ulike ETag-er. Klienter får da ikke 304 konsistent, og
   DB-belastningen vokser med worker-antallet.
3. **Konsistens i admin-dashbordet** — metrikkene aggregeres over Redis når den finnes;
   uten den ser hvert kall bare den workeren som svarte.

**Backup-klokka er trygg ved flere workers, og det er ikke tilfeldig.** Hver worker
starter sin egen tråd (`skal_starte()` sier ja i alle gunicorn-prosesser), men før noe
skrives tas `Backupplan`-raden med `select_for_update(nowait=True)`. Taper en tråd
kappløpet, får den `OperationalError` og hopper over i stillhet. **Databasen er låsen, og
det er med vilje** — en lås i minnet ville bare dekket én prosess, og en lås i cachen
ville forsvunnet med Redis.

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
- `_redis_is_available()` i `core/middleware.py` leser `settings.CACHE_BACKEND_NAME` runtime og styrer dermed metrikk-aggregering på hver request
- Admin-dashbordet (`/api/admin-status/`) viser tydelig hvilken backend som er aktiv og om aggregering er live (felter `cache_health.backend` og `metrics_5min.source`)

Prosedyre for bytte mellom modusene er dokumentert i `RUNBOOK_VAKT.md` §4.

### 8E.2 State-mekanismer og deres beskyttelse

| Mekanisme | Hvor i kode | Per-worker eller delt? | Beskyttelse i multi-worker |
|---|---|---|---|
| Django cache (stats, rate-limit) | `settings.CACHES` | Delt via Redis i vakt-modus, per-prosess i lavkostnad | `KEY_PREFIX='pasientregistrering'` isolerer mot andre tjenester på samme Redis |
| Audit thread-local (current user) | `audit/utils.py` | Per-tråd (riktig) | `threading.local()` er semantisk per tråd — hver request får ren kontekst |
| Backup-scheduler `_is_running` | `core/backup/klokke.py` | Per-prosess (in-memory bool) | DB-lås (`select_for_update(nowait=True)`) er den ekte beskyttelsen — selv om to workere mener begge "jeg starter backup", er det DB-låsen som faktisk slipper bare én gjennom |
| Request-metrikker (lokal deque) | `core/middleware._MetricsStore._samples` | Per-prosess (siste 500 samples per worker) | Brukes som fallback. Ved aggregering bidrar hver worker til Redis-listen i tillegg — se 8E.3 |
| Request-metrikker (Redis-liste) | Redis nøkkel `metrics:requests` (KEY_PREFIX prefikset av Django) | Delt | `LTRIM` holder maks 5000 entries; `EXPIRE` rydder hvis listen er ubrukt |
| Backup-klokketråden | `core/backup/klokke.py` | **Én per worker** | Alle starter, men bare den som vinner `select_for_update(nowait=True)` på `Backupplan`-raden skriver. Databasen er låsen — en lås i minnet dekket bare én prosess, og en i cachen forsvant med Redis |
| Filutsendingsklokka | `vaktliste/middleware.py` | Per request | Sammenligner `Utsending.innhold_sha256` mot den sist **sendte**; klokka går fra forrige *forsøk*. Databasen er fasit, ikke prosessminnet |
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
| 14 | `core.middleware.BackupSchedulerMiddleware` | **Reservenett** for backup-klokka, som er en tråd — se 8.3 |
| 15 | `vaktliste.middleware.FilutsendingMiddleware` | Intervallsending av vaktlista på e-post (13. sep. 2026). Samme prinsipp: trafikken er klokka |
| 16 | `core.middleware.SecurityHeadersMiddleware` | CSP, Referrer-Policy, Permissions-Policy |
| 17 | `core.middleware.RequestMetricsMiddleware` | Observability: ringbuffer med siste 500 requestmålinger (p50/p95/max/errors) |

**De to klokkene tas ut under test** (`settings.py`), og `MIDDLEWARE_I_DRIFT` bevarer
driftslista slik at tester kan påstå noe om den uten å lese `settings.py` som tekst.

`MemoryLoggingMiddleware` plasseres tidlig (etter SecurityMiddleware, før WhiteNoise) slik at den måler hele request inkludert statisk-fil-servering. `BackupSchedulerMiddleware` plasseres nær slutten slik at request allerede er ferdig behandlet når backup startes i bakgrunnstråd. `SecurityHeadersMiddleware` plasseres like før `RequestMetricsMiddleware` slik at sikkerhetsheadere settes på alle responser. `RequestMetricsMiddleware` plasseres sist slik at den måler den endelige responsen med alle headere inkludert.

---

## 10. Frontend

### 10.1 Arkitektur

Vanlig JavaScript, **ingen rammeverk og ingen bundler**. 25 filer i `static/js/`, fordelt
på sju sider: pasientsiden, `/statistikk/`, `/vaktliste/`, `/ko/`, `/backlog/` og de to
grensesnittene under `/oppdrag/`.

| Modul | Lastes | Ansvar |
|---|---|---|
| `portal-utils.js` | **alle sider** | CSRF-fetch (`apiFetch`), `withSubmitGuard`, escaping, `fmtMin`, `data-action`-delegeringen, fokusvakten for modaler |
| `patients-utils.js` | pasientsiden, alltid | Tilgangssynlighet, delt tilstand, skjemahjelpere |
| `patients-table.js` | pasientsiden, alltid | Tabulator-grid og tavle |
| `patients-forms.js` | pasientsiden, alltid | Registrerings- og redigeringsskjema |
| `patients-app.js` | pasientsiden, alltid | Oppstart, faneskift, auto-refresh |
| `patients-admin.js` | pasientsiden, **kun admin** | Registeradmin, sesjonstimeout, vaktavslutning, vaktarkiv |
| `statistikk.js` | **kun** `/statistikk/` | Pasientstatistikk (Chart.js), arkivmodus, kildefanene |
| `statistikk-oppdrag.js` | `/statistikk/`, kun med oppdragstilgang | Oppdragsfanen |
| `oppdrag-sentral-*.js` (fire) | `/oppdrag/`, kontoer **uten** enhet | Sentralbordet |
| `oppdrag-enhet.js` | `/oppdrag/`, **enhetskontoer** | Bilens skjerm, offline-kø, lydvarsel |
| `vaktliste-*.js` (fem) | **kun** `/vaktliste/` | Hele vaktlistesiden |
| `vaktliste-sw.js` | service worker på `/vaktliste/sw.js` | Offline drift |

**To sider er delt i flere filer** (14. sep. 2026): `vaktliste.js` var 3 801 linjer og
`oppdrag-sentral.js` 1 991. Uten bundler deler filene **ett globalt navnerom**, så
delingen er billig — men den gjør tre feil mulige som ikke fantes før: en funksjon som
faller mellom to filer, en som dupliseres (den sist lastede vinner i stillhet), og en mal
som kommer i utakt med lasterekkefølgen. `core/tests_js_splitt.py` håndhever alle tre.

**Regelen for rekkefølgen er ikke «all tilstand i den første fila».** `let`/`const` på
toppnivå er skript-scopede og deles mellom filene, så det ville vært et krav ingen holder.
Den ekte regelen er: **alt som *kjører* på toppnivå står i den siste fila** — i praksis
`DOMContentLoaded`-krokene. Kjører en tidlig fil noe, kan den lese en binding som ikke er
nådd, og siden dør på en `ReferenceError` før noe er tegnet.

**Grensesnittet gates på `window.MODUL_TILGANG`, ikke på rollen.** Globalen settes av
malen fra brukerens faktiske `ModulTilgang`-rader. Gjør vi det ikke, viser vi knapper som
fører til 403 — og en knapp som fører til en vegg er verre enn ingen knapp. *Den gamle
`window.USER_ROLE` er borte sammen med rollemodellen den leste.*

**`patients-utils.js` kan ikke lastes utenfor pasientsiden.** Den gjør arbeid på toppnivå
— `Chart.defaults` og `new bootstrap.Modal(...)` — og kaster på en side uten
pasientskjemaene. Trenger en ny modulside en helper derfra, skal helperen **flyttes** til
`portal-utils.js`, ikke kopieres. `JsModulLastingTests` håndhever det.

**Alt en ikke-admin kan nå på pasientsiden må ligge i en alltid-lastet modul.** Kall fra
alltid-lastet kode til `patients-admin.js` går gjennom `_kall('navn')`, som sjekker at
funksjonen finnes.

**Alle biblioteker ligger under `static/vendor/`**, ikke på CDN (13. sep. 2026) —
Bootstrap, ikonene, Tabulator og Chart.js. Chart.js lastes kun på `/statistikk/`.

**Brukerdata som settes inn med `innerHTML` skal escapes:** `escHtmlValue()` i tabeller
(tallsikker — skiller «ikke satt» fra `0`), `escapeHtml()`/`_escHtml()` ellers. Markup
koden bygger selv merkes med `trustedHtml()`, slik at unntaket er et bevisst valg per
celle.

**JS-testing:** det finnes ingen JS-testrunner. `patients/js_test_utils.py` klipper ut
enkeltfunksjoner og kjører dem i node med stubbet miljø. Testene hoppes over hvis node
ikke finnes. **Ikke skriv tester som bare grep-er etter kodelinjer** — skillet går på hva
assertionen påstår: å lese kilden for å *finne* en funksjon er greit, å påstå at en
literal kodelinje står der er det ikke. Den går i stykker av en omskriving som gjør det
samme, og går grønn når noen skriver det samme feil et annet sted.

*Monolitten `static/js/script.js` ble delt opp i mai 2026 og slettet 13. aug. 2026 (N9).
Referanser til den i eldre dokumenter er historiske.*

### 10.2 Navigasjon og faner

Pasientsiden har disse fanene:
- **Tabelloversikt** – Tabulator-grid med pasientliste og filtre
- **Tavle** – Kanban-lignende oversikt over aktive pasienter
- **Innstillinger** – Arrangementsnavn, registre, sesjonstimeout, arkivliste, backup (synlighet avhenger av tilgangsnivå)

*Statistikken er en egen side, `/statistikk/`, siden august 2026 — ikke en fane her. Den
gates på `les` i den modulen, og viser kun de kildene brukeren har `les` på i
kildemodulen.*

Fanenavigasjonen er implementert med `data-tab`-attributter og delegert event-lytting (ingen URLer endres).

Portalmenyen viser **Server-status** (`/portal-admin/server-status/`) kun for global
admin, betinget i malen slik at lenken ikke finnes i DOMen for andre.

**Django-admin rutes kun under `DEBUG`** (S1). Flaten er et utviklerverktøy, ikke en
brukerflate: et register som *bare* finnes der, finnes ikke for brukeren.
`SjekkAtIngenPekerPaaDjangoAdminTests` skanner alle maler for lenker dit.

### 10.3 Auto-refresh

Siden polls automatisk hvert 30. sekund for å holde pasientlisten og behandlerlisten oppdatert:

- `startRefreshInterval()` starter `setInterval(doAutoRefresh, 30000)`.
- Polling pauses automatisk når fanen er skjult (`document.visibilitychange`-hendelse + `document.hidden`-sjekk).
- Ved synlig igjen: umiddelbar oppdatering (`doAutoRefresh()`) etterfulgt av ny start av intervalltimer.

### 10.4 ETag-støtte for førstehjelper-listen

`loadForstehjelpere()` i `patients-admin.js` bruker `If-None-Match`-headeren med en lagret ETag. Serveren beregner ETag som SHA-256-hash av førstehjelper-listens innhold og returnerer 304 Not Modified hvis listen er uendret. Dette reduserer unødvendig nettverkstrafikk ved polling.

### 10.5 CSRF i API-kall

`apiFetch(url, options)` i `patients-utils.js` er en wrapper rundt `fetch()` som automatisk legger til `X-CSRFToken`-header for `POST`, `PUT`, `PATCH` og `DELETE`. Token leses fra `csrftoken`-cookie, med fallback til et skjult `{% csrf_token %}`-input.

### 10.6 Datahåndtering

- **Forstehjelpere** lastes ved oppstart og ved hver auto-refresh. Inaktive forstehjelpere filtreres fra dropdown-menyer, men vises for pasienter som allerede har dem.
- **Pasienter** lastes fra `/api/patients/`. Filtrering gjøres klientside mot det fullstendige datasettet (`allPatients`-array) for øyeblikkelig respons uten ny server-forespørsel.
- **Statistikk** lastes ved bytte til statistikk-fanen via `/api/full-stats/`.
- **Innstillinger** lastes via `/api/settings/` og `/api/session-timeout/`.

---

## 11. Reserve når portalen er nede

Den gamle offline-modusen — egen SQLite på en laptop, `OFFLINE_MODE`, egne brukere,
USB-pakke og tilbakesynkronisering — ble lagt ned 13. sep. 2026. Den dekket et
scenario som ikke finnes: det deployes ikke under vakt, og pasienter har Excel mens
oppdrag går på nødnett. Det som skal overleve at Railway er nede, er **vaktlista i
drift**, og den dekkes av to ting:

- **Vaktlista som fil på e-post** (`vaktliste/fil.py`): én selvstendig HTML-fil,
  sendt ved «Sett i drift», på knapp, og på intervall mens lista er i drift.
  Mottakere settes under portalinnstillingene. Se `docs/BESLUTNING_VAKTLISTE.md` §12.
- **Offline drift på `/vaktliste/`** (`static/js/vaktliste-sw.js`, servert av
  `vaktliste.views.sw_view`): en service worker holder siden og siste liste lokalt,
  og møtt/av vakt legges i kø på drifts-PC-en når serveren ikke svarer, med tida
  trykket skjedde. Køen sendes når serveren svarer igjen.

`python manage.py import_offline_data` står igjen som **importverktøy** for den
gamle appens SQLite-filer — se `docs/archived/DATAIMPORT_FRA_GAMMEL_PROD.md` (utført 22. aug. 2026).

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

*Gjennomgått 14. sep. 2026. Kapittelet viste til `PUT /api/backup-config/` og
`POST /api/reset-active-year/` — **ingen av dem finnes**, og den siste beskrev en
nullstilling av «aktivt år» som ble erstattet av vakt-modellen.*

### 13.1 Backup og gjenoppretting

Se kapittel 8 for hvordan systemet er bygget. Til daglig drift:

| Oppgave | Hvor |
|---|---|
| Se status, endre plan per modul, kjøre manuelt | `/portal-admin/backup/` (global admin) |
| Kjøre fra kommandolinja | `python manage.py backup_kjor` |
| Kontrollere at filene faktisk er gjenopprettbare | `python manage.py verifiser_backup` |
| Hente en fil fra Scaleway | `python manage.py hent_offsite --list` / `hent_offsite <fil>` |
| Gjenopprette | `python manage.py gjenopprett …` — se `docs/RUNBOOK_VAKT.md` §8b |

**Planen settes per modul** (`core.Backupplan`): modus `av`/`ved_endring`/`alltid`,
fritt intervall, og `behold` som cap på volumet. Modulene arver en `standard`-plan;
`full` og `standard` styrer alltid seg selv.

**Railways egen Postgres-backup er ikke alltid på.** Den krever oppgradert abonnement, og
prosjektet kjører hobby-plan mellom vaktene. Portalens egne filer er derfor den dekningen
som faktisk finnes hele året — se `docs/PERSONVERN_DOKUMENTASJON.md` A.2.

### 13.2 Audit-retensjon

Standard retensjon er **2 år (730 dager)** for `AuditLog` og `LoginEvent`, og **30 dager**
for varsler. `purge_old_logs` kjøres av Railway Cron søndag natt (`0 0 * * SUN`).

```bash
python manage.py purge_old_logs                       # 730 dager / 30 dager varsler
python manage.py purge_old_logs --days 365            # egendefinert for logg
python manage.py purge_old_logs --notification-days 7  # egendefinert for varsler
python manage.py purge_old_logs --dry-run             # forhåndsvis uten å slette
```

Siste kjøring vises på `/portal-admin/server-status/`. **«Aldri» betyr at jobben ikke har
kjørt én eneste gang** — det er forskjellen mellom «ingenting å slette» og «jobben er
død», og den var umulig å se før tidsstemplene kom 13. sep. 2026.

### 13.3 Nullstille MFA for bruker som har mistet telefonen

1. Global admin → `/portal-admin/brukere/`
2. Åpne brukeren, klikk **«Nullstill MFA»** (vises kun når brukeren har MFA aktivt)
3. Bekreft

Systemet sletter alle `TOTPDevice`- og `StaticDevice`-objekter, setter `mfa_required=True`,
invaliderer brukerens aktive sesjoner og loggfører `mfa_reset_by_admin` i `LoginEvent`.
Brukeren tvinges gjennom MFA-oppsett ved neste innlogging.

### 13.4 Avslutte en vakt og starte en ny

*Dette erstattet «nullstill aktivt år» (§3.4 i vakt-notatet). Navnet betyr noe: «nullstill
år» ville slettet for mye den dagen ett år rommer flere vakter.*

`POST /pasienter/api/avslutt-vakt/` med `{"confirm": true}`, fra Innstillinger på
pasientsiden. **Global admin.** Operasjonen gjør fire ting i rekkefølge:

1. Tar en `pre_reset`-backup
2. Sletter vaktas pasienter
3. Merker vakta avsluttet
4. Oppretter en ny vakt i samme flyt, så portalen aldri står uten aktiv vakt

**Vaktnavnet er påkrevd, fritekst og unikt** — to vakter med samme navn lar seg ikke
skille i statistikken.

**Oppdragene røres ikke.** De scopes bort fra alle visninger i samme øyeblikk som pekeren
flytter, og har sin egen livssyklus (arkivering, kollaps).

**Gjenåpning finnes** (`/pasienter/api/gjenaapne-vakt/`), men **den henter ikke rader
tilbake** — den setter vakta aktiv igjen. Pasientslettingen kan bare angres via backupen.

### 13.5 Arkivering og kollaps

Arkivering fryser en vakts data med signatur. Etter **24 måneder** kollapser
`kollaps_arkiv` radnivået til aggregat, irreversibelt.

```bash
python manage.py kollaps_arkiv --dry-run     # hva som ville blitt kollapset
python manage.py kollaps_arkiv               # skarpt; Railway Cron 0 4 1 * *
python manage.py kollaps_arkiv --modul oppdrag
```

**Sperren foran kollaps er en backup.** Kommandoen nekter med mindre det finnes en backup
av modulens arkiv tatt *etter* at arkivet ble opprettet — slettingen skal være
gjenopprettbar. Det er også grunnen til at backup-klokka ikke kan være en cron-tjeneste:
en fil som forsvant med containeren ville etterlatt databaseraden, og sperren spør bare
etter raden.

Kommandoen går gjennom `core.arkiv`-registeret og kjenner ingen modul ved navn.

---

## 14. Testing

*Gjennomgått 14. sep. 2026. Kapittelet oppga «178 tester» og listet antall per fil —
begge deler råtnet fra dagen de ble skrevet. Her står prinsippene i stedet, og de
holder.*

### 14.1 Kjøre tester

```bash
python manage.py test patients accounts audit core statistikk oppdrag vaktliste myproject -v 2
python manage.py test patients.tests.PatientAPITest.test_create_patient -v 2
```

**`myproject` skal med.** Den bærer testene på databasevalg, cache, `_env_bool`, statiske
filer og migrasjoner — vaktene rundt «`DATABASE_URL` må peke på PostgreSQL på Railway» og
rundt den `_env_bool` som hadde rate-limitingen av i prod. Kommandoen utelot den i lang
tid uten at noe sa fra; `core/tests_testkommandoen.py` håndhever nå at hver pakke med
tester står i den.

**Et antall her ville råtnet** — kjør kommandoen.

**Behold loggen.** `2>&1 | tee` på en full kjøring. En intermitterende feil som blir
grep-et bort er en feil man ikke kan fikse, og det kostet flere dagers leting 14. sep. 2026.

### 14.2 Migrasjonsprøver mot ekte PostgreSQL

```powershell
$env:MIGRASJONSPROVE_DATABASE_URL = "postgres://postgres:PASSORD@localhost:5432/postgres"
python manage.py verifiser_migrasjoner
```

**Å kjøre suiten mot PostgreSQL er ikke det samme, og holder ikke.** Djangos testbase
lages ved å kjøre migrasjonene mot en *tom* base: et dataskritt uten data skriver
ingenting, fyller ingen triggerkø, og feilen viser seg aldri. Feilen krever PostgreSQL
**og** rader **og** en skjemaendring etter skrivingen — se «Migrasjoner» i `CLAUDE.md`.

Prøvene hoppes over uten variabelen. De skal kjøres før en migrasjon som rører data pushes.

### 14.3 JS testes ved å kjøre koden, ikke ved å lese den

Det finnes ingen JS-testrunner. `patients/js_test_utils.py` klipper ut enkeltfunksjoner og
kjører dem i node med stubbet miljø.

**Skillet går på hva assertionen påstår**, ikke på om fila leses:

| I stedet for | Skriv |
|---|---|
| `assertIn("if (metode !== 'GET')", kilde)` | Kjør `avgjor()` for hver metode og krev `null` |
| `assertIn('mannskap.sort(', kilde)` | Krev rekkefølgen i svaret, med data som avslører databasens alfabet |
| `assertIn("classList.toggle('active-mine'", js)` | Kall funksjonen mot et minimalt DOM og se at klassen kommer og går |
| `assertNotIn('fjernRessurs', kilde)` | Tegn kortet og krev at sletteknappen ikke er i markupen |

Å lese kilden for å *finne* en funksjon, eller for å håndheve en regel som ikke har noen
kjøretid, er riktig. Å påstå at en literal kodelinje står der er det ikke: den går i
stykker av en omskriving som gjør det samme, og **går grønn** når noen skriver det samme
feil et annet sted.

**En regel som skal prøves må være en navngitt funksjon.** `klikkSkalKjore()`,
`avgjor()`, `skalKastes()`, `slippFokusFoerSkjul()` og `nokkel_logges()` ligger alle
utenfor lytteren eller løkka som bruker dem, nettopp fordi en anonym `if` ikke lar seg
kalle fra en test.

### 14.4 Rate-limit-tester må tåle vinduskanten

`django_ratelimit._get_window` legger vinduskanten et fast antall sekunder inn i hver
periode, **jitret per nøkkel**. En serie forsøk som straddler kanten deles i to bøtter, og
med bare litt over grensen når ingen av dem fram — testen feiler da omtrent én kjøring av
seksti, på en annen maskin enn din.

Bruk `nok_til_a_bryte(grense)` fra `core/tests_ratelimit.py`, som er `2 × grense + 1`.
Duebolprinsippet, ikke flaks.

### 14.5 Testene som håndhever regler

Dette er den delen av suiten som er verdt å kjenne: tester som ikke prøver en funksjon,
men **en regel om kodebasen**. De feiler når noen bryter en beslutning uten å vite om den.

| Test | Regelen den holder |
|---|---|
| `DataOgSkjemaISammeTransaksjonTests` | En migrasjon som skriver rader og så endrer skjema må tømme PostgreSQLs triggerkø |
| `SlettelistaDekkerDumpenTests` | Hver modell som dumpes i en backup må også tømmes ved gjenoppretting |
| `SignalerFyrerIkkeUnderLoaddataTests` | Hvert lagringssignal har `@ikke_under_loaddata`. Leter i **alle** `*/signals.py`, ikke en håndskrevet liste |
| `AlleFileneGjenopprettesTests` | Rekkefølgen portal → patients → arkiv → oppdrag → oppdrag_arkiv → vaktliste → ko virker i en tom base, og kantene den bygger på utledes av modellene |
| `ArkivSignaturLaastTests` | Arkivsignaturene er låst til literale hex-verdier. Feiler de etter en refaktorering, er det refaktoreringen som er feil |
| `JsModulLastingTests` | Ingen side kaller en funksjon fra en modul den ikke laster |
| `MorkTekstPaaMorkBakgrunnTests` | Hver Bootstrap-klasse for dempet tekst er overstyrt der malen kan se den |
| `SjekkAtIngenPekerPaaDjangoAdminTests` | Ingen mal lenker til Django-admin, som bare rutes under `DEBUG` |
| `OppdragImportererIkkeVaktlista` | Oppdragsmodulen importerer ikke vaktlista. Leser importene med AST |
| `StatistikkappenNavngirIngenKilde` | Statistikkappen navngir ingen kildemodul |
| `TabellcellersLayoutTests` | En `<td>` forblir en `table-cell` — `display: flex` tar den ut av tabellens boksmodell |
| `RessurstabellensBreddeTests` | Tidskolonnene rommer et `datetime-local`-felt i begge tabellformer |
| `StemplingsnavnTests` | `STEMPLINGER` i JS og i `services.py` holdes like |

I tillegg, fra dokumentrunden: `core/tests_avhengighetsretning.py` (retningen modul →
`core`), `core/tests_js_splitt.py` (de delte JS-filene), `core/tests_malenes_urler.py`
(hver `{% url %}` i hver mal), `core/tests_testkommandoen.py` og
`core/tests_dokumentråte.py`.

**Dette er mønsteret som er verdt å videreføre:** når en beslutning tas og begrunnelsen
skrives ned, skriv også testen som fanger at noen bryter den uten å ha lest begrunnelsen.

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

Restrisikoen — at jobben stopper uten at noen oppdager det — er **dempet siden
13. sep. 2026**: hver kjøring skriver `AppSetting['cron.<navn>']` med tid, utfall og
melding, og `/portal-admin/server-status/` viser det. **«Aldri» betyr at jobben ikke har
kjørt én eneste gang**, og det er forskjellen mellom «ingenting å slette» og «jobben er
død». Verifiseringen står fortsatt i den årlige revisjonssjekklisten
(`PERSONVERN_DOKUMENTASJON.md` C.4), men nå kan den gjøres med et blikk.

### 15.6 `style-src` tillater fortsatt `unsafe-inline`

`script-src` bruker nonce uten `unsafe-inline` og uten vertsnavn. `style-src` gjør det
ikke: markup har rundt femti inline `style`-attributter, og statistikk-tabellene bygger
flere. Det sto utenfor akseptansekriteriet da CSP-en ble strammet, og står som åpent punkt
i `TODO.md`.

Konsekvensen er avgrenset: en injeksjon kan påvirke *utseende*, ikke kjøre skript. Men
det er en reell forskjell fra `script-src`, og den bør ikke leses som at CSP-en er ferdig.

### 15.7 Kontoopprettelsen har en sideeffekt i oppdragsmodulen

`core` kjenner ingen modul ved navn, og det håndheves. **Ett unntak står igjen**, i
`KJENTE_UNNTAK_RAMMEVERK`: når kontotypen er «bil», validerer `accounts/forms.py`
enhetsnavnet og `accounts/views.py` oppretter eller gjenoppliver en `oppdrag.Enhet`.

Det er samme slags kobling som pasientrollen, men en annen form: det er *selve
opprettelsen* som får sideeffekten, ikke et skjema ved siden av. Den hører hjemme i
`core/kontokobling.py` med en lagringskrok, men det er kirurgi i brukeropprettelsen.
**Lista skal ikke vokse.**

### 15.8 Gjerdet mot dokumentråte fanger form, ikke mening

`core/tests_dokumentråte.py` fanger tre ting: at en filsti finnes, at en `manage.py`-
kommando finnes, og — fra 14. sep. 2026 — at **tall i dokumentene stemmer med tall regnet
ut fra koden** (`core/tallfasit.py`, `python manage.py tallfasit`).

Det siste dekker den halvdelen av dokumentråte som oppstår **uten at noen gjør noe galt**:
«178 tester totalt» var sant da det ble skrevet, og «16 endepunkter» var sant da det var
alt som fantes. Legger noen til en rute, feiler testen til dokumentet følger etter.

**To kjente grenser, og begge er bevisste:**

**Den kan ikke lese mening.** Det er verdt å se hvor lite den ville fanget av
dokumentrunden 14. sep. 2026:

| Funn | Fanget? |
|---|---|
| A.10 beskrev en rollemodell slettet i deploy 2 | Ja — symbollista |
| Kap. 5 dokumenterte 16 av 124 endepunkter | Ja — tallgjerdet, fra nå |
| Deploy-guiden ba deg laste ned en backupfil | **Nei** |
| 8B viste en signatur som ville gitt `TypeError` | **Nei** |
| `_scrub_secrets` gjengitt med feil regex | **Nei** |

**Et avsnitt som erklærer seg historisk tier regelen til neste kapittel.** Luken er
nødvendig — historiske avsnitt *skal* kunne nevne slettede navn — men den skiller ikke
mellom «dette beskriver fortida» og «jeg vil ha ro». Den ble oppdaget ved at
«ikke gjennomgått»-markører fra første dokumentrunde slo av kontrollen for fem kapitler.

Begge løses av at noen leser diffen, ikke av at testen blir strengere.

### 15.9 Arkivfunksjonalitet — statistikk beregnes, ikke lagres

Vaktarkivet lagrer radnivå (`ArkivertPasient`) og beregner statistikken på nytt hver gang et arkiv åpnes. Radene vises aldri enkeltvis i grensesnittet.

Implementert (GDPR fase 3.1, aug. 2026): radene kollapser til frosne aggregater etter 24 måneder, og SHA-256-integritetssjekken regnes da over aggregatet i stedet for radene. Se `core/arkiv/` og CHANGELOG.

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
- `core/stats_cache.py` og dekoratøren `cached_stats_response` med SHA-256 weak ETag og If-None-Match/304.
- Gunicorn parametrisert med `WEB_WORKERS`, `WEB_THREADS`, `WEB_MAX_REQUESTS` og `--max-requests-jitter 50`.
- Testantall økt fra 145 til 178.

### 16.10 Bilen piper ikke på iPhone

**Symptom:** Lydvarselet for ventende oppdrag kommer på Android og PC, men ikke på iPhone
med ringebryteren på lydløs. Konsollen viser en CSP-advarsel om `blob:`.

**Årsak:** `_stilleLydbaerer()` bygger en stum WAV som Blob for å flytte lydøkta fra
«ambient» til «playback» — uten den demper iOS' bryter Web Audio. `default-src 'self'`
dekker ikke `blob:`.

**Løsning:** `media-src 'self' blob:` må stå i CSP-en (`core/middleware.py`). Rettet
14. sep. 2026. **Merk formen på feilen:** siden virket, oppdraget lastet, og det eneste
tegnet var en linje i konsollen — mens bilen ikke pep.

### 16.11 Offsite-backup skjer ikke

**Symptom:** Filene ligger på volumet, men ikke i Scaleway-bucketen.

**Vanlig årsak:** `OFFSITE_*`-variablene mangler. Modulen er da **inert med vilje** —
ingen feil, ingen forsøk. Det er normalt på staging.

**Løsning:** `/portal-admin/backup/` lister nøyaktig hvilke variabler som mangler. Feilet
opplastingen i stedet, står feilen samme sted, i `OffsiteKopi.feil`.

### 16.12 Cron-jobben gjør ingenting, og feiler ikke

**Symptom:** `purge_old_logs` eller `kollaps_arkiv` står som kjørt, men ingenting skjer.
Eller server-status sier «Aldri».

**Vanlig årsak:** `startCommand` er ikke satt eksplisitt på Railway-tjenesten. Uten den
arver tjenesten `Procfile`-ens `web:`-linje og starter **gunicorn** i stedet for
kommandoen. Jobben gjør da ingenting og feiler ikke. Begge manglet den i første oppsett.

**Løsning:** Sett `startCommand` på tjenesten. Se `docs/DEPLOY_GUIDE.md` kapittel 7.

### 16.13 En deploy tok ned portalen

Se `docs/RUNBOOK_VAKT.md` §8c og `docs/DEPLOY_GUIDE.md` kapittel 10. Kjernepunktet:
**en redeploy i Railway ruller ikke tilbake databasen**, så les release-loggen og finn ut
om migrasjonen endret skjemaet før du redeployer.

### 16.14 Siden er blank etter en JS-endring

**Symptom:** `/vaktliste/` eller `/oppdrag/` viser ingenting. Konsollen har en
`ReferenceError`.

**Vanlig årsak:** De to sidene laster flere JS-filer i rekkefølge, uten bundler. Kode som
**kjører** på toppnivå i en tidlig fil kan lese en binding som ikke er nådd ennå.

**Løsning:** Alt som kjører på toppnivå skal stå i den **siste** fila —
`core/tests_js_splitt.py` håndhever det. Sjekk også at `<script>`-rekkefølgen i malen
stemmer med rekkefølgen i `patients/js_test_utils.py`.

### 16.15 Et testtall stemmer ikke

**Symptom:** Suiten rapporterer færre tester enn sist.

**Sjekk først om kommandoen er den fulle.** `myproject` ble utelatt fra den dokumenterte
kommandoen i lang tid, og de 32 testene der ble aldri kjørt.
`core/tests_testkommandoen.py` fanger det nå.

**Og behold loggen.** `2>&1 | tee` — en intermitterende feil som blir grep-et bort er en
feil man ikke kan fikse.


## Tillegg: Fase 3 — Sanitetsportal (mai 2026)

> **Historisk (mai 2026).** Beskriver tilstanden da fasen ble levert, og er beholdt fordi begrunnelsene fortsatt forklarer *hvorfor*. **Detaljene er overtatt av senere arbeid** — særlig `ModuleBackupConfig`, som er erstattet av `core.Backupplan` (se 4.8 og kap. 8), og modulregisteret, som har fått fire registre til (se 3.4). Er dette og et tidligere kapittel uenige, vinner det tidligere kapittelet.


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
- `core.views_portal`:
  - `portal_dashboard_view` på `/`
  - `profile_view` på `/min-profil/`
- `core.views_admin` (14. sep. 2026 — `core/views_portal.py` / `views_admin.py` / `views_backup.py` / `views_varsler.py` var 830 linjer og 24 views):
  - `portal_settings_view` på `/portal-admin/innstillinger/`
  - `module_admin_list_view` / `module_admin_edit_view` på
    `/portal-admin/moduler/[<slug>/]`
  - `audit_log_list_view` / `audit_log_csv_export_view` på
    `/portal-admin/auditlog/[eksport.csv]`
- `core.views_backup` — backup-admin på `/portal-admin/backup/...`
- `core.views_varsler` — varsler på `/varsler/...`

Alle rutene under `/portal-admin/` er samlet i `core/urls_admin.py` med
navnerommet `portaladmin` (14. sep. 2026, gjeldspunkt 3.2). De lå i tre filer,
med to ulike navnerom for samme flate.

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

> **Historisk (mai 2026).** Beskriver tilstanden da fasen ble levert, og er beholdt fordi begrunnelsene fortsatt forklarer *hvorfor*. **Detaljene er overtatt av senere arbeid** — særlig `ModuleBackupConfig`, som er erstattet av `core.Backupplan` (se 4.8 og kap. 8), og modulregisteret, som har fått fire registre til (se 3.4). Er dette og et tidligere kapittel uenige, vinner det tidligere kapittelet.


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

> **Historisk (mai 2026).** Beskriver tilstanden da fasen ble levert, og er beholdt fordi begrunnelsene fortsatt forklarer *hvorfor*. **Detaljene er overtatt av senere arbeid** — særlig `ModuleBackupConfig`, som er erstattet av `core.Backupplan` (se 4.8 og kap. 8), og modulregisteret, som har fått fire registre til (se 3.4). Er dette og et tidligere kapittel uenige, vinner det tidligere kapittelet.


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
