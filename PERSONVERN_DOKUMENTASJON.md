# Personvern­dokumentasjon – Pasientregistrering (sanitetsvakt)

**Siste oppdatering:** 5. juni 2026  
**Versjon:** 1.4  
**Behandlingsansvarlig:** André Eritsland

---

# DEL A: Behandlingsprotokoll (GDPR Art. 30)

> Formelt dokument i henhold til GDPR artikkel 30 – fortegnelse over behandlingsaktiviteter. Kan fremlegges for Datatilsynet eller annen tilsynsmyndighet.

---

## A.1 Behandlingsansvarlig

| Felt | Opplysning |
|---|---|
| Navn | André Eritsland |
| E-post | andre.eritsland@gmail.com |
| Rolle | Behandlingsansvarlig |
| Geografisk plassering | Rogaland, Norge |

Behandlingsansvarlig er ansvarlig for at personopplysninger behandles i tråd med gjeldende personvernregelverk, herunder EUs personvernforordning (GDPR), lov om behandling av personopplysninger (personopplysningsloven) av 2018, helsepersonelloven og pasientjournalloven.

---

## A.2 Databehandler og underbehandlere

| Felt | Opplysning |
|---|---|
| Navn | Railway Corp. |
| Rolle | Databehandler (infrastruktur og hosting for web-app, PostgreSQL og — kun i vakt-modus — Redis) |
| Avtalegrunnlag | Data Processing Addendum (DPA) signert |
| Databehandlingsregion | europe-west4 (Nederland, EU) |
| Kontakt / DPA-referanse | Railway Amsterdam Data Processing Addendum |

Databehandleravtale (DPA) er inngått i samsvar med GDPR artikkel 28. Data lagres utelukkende i EU-regionen europe-west4 (Nederland). Ingen behandling skjer utenfor EU/EØS.

**Tjenester driftet av Railway Corp. på vegne av behandlingsansvarlig:**

Applikasjonen kjøres i to driftsmoduser (se TEKNISK_DOKUMENTASJON.md kapittel 8E og RUNBOOK_VAKT.md §1b for detaljer). Hvilke tjenester som er aktive avhenger av modus:

| Tjeneste | Formål | Aktiv i lavkostnad-modus (default) | Aktiv i vakt-modus | Inneholder personopplysninger? |
|---|---|---|---|---|
| Web-applikasjon (Gunicorn/Django) | Kjører applikasjonskoden | Ja (1 worker) | Ja (flere workers) | Nei (kun i minnet under behandling, ikke persistert) |
| PostgreSQL | Persistent lagring av pasientdata, brukerkontoer, audit-logg | Ja | Ja | Ja (alle kategorier i A.6) |
| Redis | Delt cache for rate-limiting, statistikk-aggregat og metrikk-aggregering på tvers av workers (se A.6 "Cache-data") | **Nei — frakoblet** | Ja | Nei — ingen pasient-PII. Kun aggregerte tall og IP/brukernavn-tellere med max 10 min TTL |

> **Lavkostnad-modus (default):** Redis-tjenesten er pauset i Railway. Applikasjonen bruker da Djangos `LocMemCache` (lokal prosessminne). Det innebærer at Redis ikke er en aktiv databehandler-relasjon i denne modusen — ingen data sendes til eller lagres i Redis. Siden bare 1 Gunicorn-worker er aktiv, er per-prosess-cache tilstrekkelig.

> **Vakt-modus:** Redis aktiveres manuelt før hver vakt (se RUNBOOK_VAKT.md §1c) og pauses etter vakten (§10b). Kun i denne perioden behandles cache-data via Redis-tjenesten i Railway-prosjektet.

> **Underbehandlere:** Railway Corp. kan benytte egne underleverandører (bl.a. skyleverandører som Google Cloud eller AWS) for å levere infrastrukturtjenestene (inkludert Redis når denne er aktiv). Behandlingsansvarlig skal kontrollere at Railways DPA dekker slike underbehandlere i samsvar med GDPR art. 28(2)–(4). Se sjekkliste i avsnitt A.13.

---

## A.3 Navn og formål med behandlingen

**Applikasjonsnavn:** Pasientregistrering (sanitetsvakt)

**Formål:**

1. **Primærformål:** Registrering, triagering og fortløpende tracking av pasienter som mottar sanitetshjelp under arrangementer (events) med medisinsk beredskap.
2. **Sekundærformål:** Dokumentasjon av behandlingshistorikk under vakt (behandler, medisinering, transport, inn/ut-tider) for å sikre kontinuitet i helsehjelpen.
3. **Tertiærformål:** Statistisk evaluering og erfaringslæring i etterkant av hvert event, for å forbedre fremtidige beredskapsopplegg.

---

## A.4 Rettslig grunnlag

Behandlingen hviler på følgende rettslige grunnlag:

| Grunnlag | Hjemmel | Anvendelse |
|---|---|---|
| Vitale interesser | GDPR art. 6(1)(d) | Akutt medisinsk dokumentasjon der behandling er nødvendig for å verne den registrertes eller en tredjepersons liv eller helse |
| Helsefaglig behandling | GDPR art. 9(2)(h) | Behandling av særlige kategorier personopplysninger (helseopplysninger) for yrkesmessige helsefaglige formål, underlagt taushetsplikt |
| Nasjonal sektorlovgivning | Helsepersonelloven §§ 39–40, pasientjournalloven | Plikt til å nedtegne helsehjelp og oppbevare journal; gjelder helsepersonell som yter helsehjelp |

> **Merk:** I akutt beredskapssammenheng vil GDPR art. 6(1)(d) (vitale interesser) typisk være det primære grunnlaget for innledende registrering, supplert av art. 9(2)(h) for den løpende journalføringen. Der helsepersonell har en rettslig plikt til å føre journal, kan art. 6(1)(c) (rettslig forpliktelse) komme i tillegg.

---

## A.5 Kategorier registrerte

| Kategori registrerte | Beskrivelse |
|---|---|
| Pasienter | Alle som mottar sanitetshjelp under arrangementer der appen benyttes |
| Appbrukere (helsepersonell/frivillige) | Brukere med påloggingskonto i systemet; disse registrerer pasientdata |

---

## A.6 Kategorier personopplysninger

### Pasientdata

Pasienten identifiseres ved et **sanitets-pasientnummer** (løpenummer tildelt under vakten). Det lagres **ikke** navn, personnummer (fødselsnummer), fødselsdato, adresse eller annen direkte identifikator. Dette er et bevisst valg for dataminimering i henhold til GDPR art. 5(1)(c).

Følgende opplysninger lagres om **pasienter** (basert på `Patient`-modellen i `patients/models.py`):

| Felt (teknisk navn) | Beskrivelse | Datatype | Kategori | Hjemmel |
|---|---|---|---|---|
| `pasientnummer` | Sanitets-pasientnummer (løpenummer, globalt unikt) – **ikke** navn eller fødselsnummer | Heltall, unikt | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `year` | Årstall vakten tilhører | Heltall | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `problemstilling` | Kategorisk angivelse av pasientens presenterende problem | Tekst (dropdown – fast verdimengde) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `arsak` | Årsaksangivelse for henvendelsen | Tekst (dropdown – fast verdimengde) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `transport` | Transportmåte (gående, båre, ambulanse m.m.) | Tekst (dropdown – fast verdimengde) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `inntid` | Tidspunkt pasienten ble registrert inn | Tekst (validert format `dd.mm.åååå tt:mm`) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `grovsortering` | Triagekategori: rød / gul / grønn | Tekst (dropdown – begrenset verdimengde) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `pabegynt` | Tidspunkt behandling ble påbegynt | Tekst (validert format `dd.mm.åååå tt:mm`) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `plassering` | Fysisk plassering i sanitetsområdet | Tekst (dropdown – fast verdimengde) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `forstehjelper` | Tilknyttet førstehjelper (FK til Førstehjelper-tabell) | Referanse (dropdown fra Førstehjelper-tabell) | Vanlig personopplysning (behandlerpersonell) | GDPR art. 6(1)(d) |
| `helsepersonell_ref` | Helsepersonell involvert i behandlingen (FK til Helsepersonell-tabell) | Referanse (dropdown fra Helsepersonell-tabell) | Vanlig personopplysning (behandlerpersonell) | GDPR art. 6(1)(d) |
| `lege` | Eventuell lege involvert | Tekst | Vanlig personopplysning (behandlerpersonell) | GDPR art. 6(1)(d) |
| `medisiner` | Indikasjon på om medikamenter er gitt | Tekst (dropdown – fast verdimengde) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `inn_obspost` | Tidspunkt for innleggelse til observasjonspost | Tekst (validert format `dd.mm.åååå tt:mm`) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `ut_obspost` | Tidspunkt for utskrivning fra observasjonspost | Tekst (validert format `dd.mm.åååå tt:mm`) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `utskrevet` | Tidspunkt pasienten ble utskrevet | Tekst (validert format `dd.mm.åååå tt:mm`) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `utskrevet_til` | Destinasjon ved utskrivning (hjem, legevakt, sykehus m.m.) | Tekst (dropdown – fast verdimengde) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `journal` | Journalkategori (dropdown – fast verdimengde, ikke fritekst) | Tekst (dropdown) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `is_active` | Aktiv-flagg (False = logisk slettet / soft-delete) | Boolsk | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `created_at` | Tidspunkt posten ble opprettet (systemgenerert) | Tidsstempel | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `updated_at` | Tidspunkt posten sist ble endret (systemgenerert) | Tidsstempel | Vanlig personopplysning | GDPR art. 6(1)(d) |

**Datakategorier (oppsummert):**
- **Helserelaterte data (art. 9):** problemstilling, årsak, transport, triagering, medisiner, utskrivningsdestinasjon, journalkategori
- **Skjermingsdata / pseudonymisering:** pasientnummer erstatter alle direkte identifikatorer

> **Prinsipp om dataminimering (GDPR art. 5(1)(c)):** Appen lagrer **ikke** navn, personnummer (fødselsnummer), fødselsdato, adresse, telefonnummer eller andre direkte identifikatorer for pasientene. Pasientene identifiseres utelukkende ved et sanitets-pasientnummer tildelt under vakten. Dette reduserer risikoen ved et eventuelt sikkerhetsbrudd betydelig.

> **Merknad om feltyper:** Samtlige kliniske felter (inkludert `journal`, `problemstilling`, `arsak`, `transport`, `plassering`, `utskrevet_til`, `medisiner` og `grovsortering`) er implementert som **dropdown med fast verdimengde** i brukergrensesnittet. Dette hindrer utilsiktet registrering av fritekst-opplysninger utover det som er nødvendig for formålet. Tidsfeltene (`inntid`, `pabegynt`, `inn_obspost`, `ut_obspost`, `utskrevet`) er tekstinput, men er underlagt **streng serverside-validering** som kun aksepterer formatet `dd.mm.åååå tt:mm` (f.eks. `19.04.2026 14:30`). Forsøk på å sende inn annet format blir avvist med HTTP 400 og feilmelding.

### Appbrukerdata

Følgende opplysninger lagres om **appbrukere** (basert på `CustomUser`-modellen i `accounts/models.py`):

| Felt | Beskrivelse | Kategori |
|---|---|---|
| `username` | Brukernavn (innloggingsnavn) | Vanlig personopplysning |
| `email` | E-postadresse (valgfritt) | Vanlig personopplysning |
| `role` | Tilgangsnivå: `admin`, `lead`, `lead_view`, `read_write`, `read_only` | Vanlig personopplysning |
| `last_login_at` | Tidspunkt siste vellykkede innlogging | Vanlig personopplysning |
| `created_at` / `updated_at` | Systemtidsstempler | Vanlig personopplysning |

Passord lagres **ikke i klartekst** – se avsnitt A.10 om passord-hashing.

### Audit-logg

`AuditLog` (felt-nivå endringer) og `LoginEvent` (innloggingshendelser) lagrer:

| Felt | Innhold |
|---|---|
| Hendelsestype | Hva skjedde (opprett, endre, slette, innlogging, MFA-hendelse m.m.) |
| Berørt post-ID / tabell | Hvilken post og hvilken tabell som ble berørt |
| Berørt felt | Feltnavn, gammel verdi, ny verdi (felt-nivå granularitet) |
| Bruker | Hvem utførte handlingen |
| IP-adresse | Klientens IP-adresse |
| Brukeragent | Nettleser/klient-streng |
| Tidspunkt | Når hendelsen inntraff |

Audit-logg-data lagres for sikkerhets- og revisjonsformål og slettes etter 10 år (se A.9).

### Cache-data (Redis – kun aktiv i vakt-modus)

Applikasjonen har to driftsmoduser med ulik cache-strategi:

- **Lavkostnad-modus (default):** Cache-backend er Djangos `LocMemCache` (per-prosess minne). Ingen data forlater applikasjons-prosessen via cache-laget. Ved omstart av prosessen tømmes cachen fullstendig. Det er **ingen Redis-tjeneste i bruk** i denne modusen, og dermed ingen cache-relatert databehandling utenfor selve web-prosessen.
- **Vakt-modus (aktiveres manuelt før vakt):** Redis-tjenesten i Railway-prosjektet aktiveres som delt cache for å støtte flere samtidige Gunicorn-workers og aggregere driftsmetrikker på tvers av workers (forbedring #15).

Når Redis er aktiv (vakt-modus), lagres følgende data i Redis:

| Felt | Innhold | TTL |
|---|---|---|
| Rate-limit-tellere | IP-adresser og brukernavn med antall innloggings-/forespørselsforsøk siste tidsvindu | 60–300 sekunder (auto-utløp) |
| Statistikk-cache (`stats_cache`) | **Aggregerte tall** for åpningssiden (totalt antall pasienter, fordeling pr. triagering, gjennomsnittstider) | 15 sekunder (basic), 60 sekunder (full) |
| Metrikk-aggregat (`metrics:requests`) | Aggregerte forespørsels-samples for admin-dashbordet (latens, status, sti, worker-id). Maks 5000 samples (`LTRIM`), liste-TTL 600 sekunder (`EXPIRE`). Per-sample inneholder ikke pasientdata | Maks 10 minutter (auto-utløp via `EXPIRE`) |
| Cache-helsesjekk-prober | Engangs probe-nøkler skrevet og slettet av admin-dashbordet | <1 sekund |

**Eksplisitt:** Pasient-PII (navn, fødselsdato, diagnose, fritekst, behandler, plassering, journalnotater osv.) lagres **aldri** i Redis — verken i lavkostnad- eller vakt-modus. Statistikkene som mellomlagres er aggregater som ikke lar seg re-identifisere til enkeltpasienter. Metrikk-samples inneholder kun teknisk drifts-informasjon (HTTP-sti, status, varighet, worker-PID) og inneholder ikke pasientdata. Rate-limit-tellerne inneholder klient-IP og brukernavn (samme kategori som allerede logges i AuditLog), men ingen pasientdata.

Key-prefiks `pasientregistrering:` brukes for å isolere applikasjonens nøkler fra eventuelle andre tjenester på samme Redis-instans. Redis-instansen i Railway-prosjektet er i tillegg dedikert til pasientregistreringsapplikasjonen og nås kun via interne (ikke-offentlige) Railway-nettverksendepunkter.

---

## A.7 Mottakere av personopplysninger

| Mottaker | Grunnlag for tilgang | Datatype som deles |
|---|---|---|
| Interne appbrukere (helsepersonell/frivillige med konto) | Tjenestlig behov, rollebasert tilgangsstyring | Pasientdata i henhold til tildelt rolle |
| Railway Corp. (databehandler) | Databehandleravtale (DPA), art. 28 | All data lagret i databasen (infrastrukturtilgang, ikke applikasjonsnivå) |

Det foretas **ingen videreformidling** til tredjeparter, kommersielle aktører, offentlige myndigheter (med unntak av eventuelle lovpålagte utleveringer) eller andre organisasjoner.

---

## A.8 Overføring til tredjeland

Det foretas **ingen overføring av personopplysninger til land utenfor EU/EØS.** All data lagres og behandles i Railway-region europe-west4 (Nederland), som er beliggende i EU. Railway Corp. er underlagt EU-regelverket gjennom DPA og sin Amsterdam Data Processing Addendum.

---

## A.9 Lagringstid og sletting

| Datakategori | Lagringstid | Begrunnelse |
|---|---|---|
| Cache-data lavkostnad-modus (LocMemCache i prosess) | Maks 60 sekunder (auto-utløp) eller til prosess-omstart | Kortvarig drift; per-prosess minne; ingen pasient-PII |
| Cache-data vakt-modus (Redis aggregater, tellere og metrikk-samples) | Maks 10 minutter (auto-utløp via `EXPIRE`/TTL) | Kortvarig drift; ingen pasient-PII; Redis er kun aktiv under vakt |
| Pasientdata (aktiv innsamling) | Inneværende år i PostgreSQL (produksjon) | Aktiv bruk under arrangementssesong |
| Pasientdata (arkiv) | Arkiveres til JSON-filer ved årsskifte | Langtidsoppbevaring; minimum 3 år etter event, jf. pasientjournalloven |
| Backup-filer (automatisk og manuell) | 72 timer, deretter automatisk slettet | Teknisk gjenoppretting; kortvarig behov |
| Audit-logger (AuditLog, LoginEvent) | 10 år (anbefalt for helserelaterte data) | Revisjon, hendelsesoppklaring og faglig dokumentasjon |
| Sesjondata | 8 timer (standard), konfigurerbart mellom 1 og 24 timer | Begrenses til nødvendig varighet per vakt |
| Brukerkontoer | Slettes manuelt av admin når tilgang ikke lenger er nødvendig | Prinsippet om lagringsbegrensning, art. 5(1)(e) |

> **Merk om audit-logg-retention:** 10-årsperioden for audit-loggen er valgt i tråd med anbefalinger for helserelatert dokumentasjon. Behandlingsansvarlig bør verifisere at dette er i overensstemmelse med gjeldende faglig og lovmessig krav i den aktuelle konteksten, herunder helsepersonelloven og pasientjournalloven.

> **Merk om backup-innhold:** Backup-filer inneholder **utelukkende pasientdata** (`BACKUP_APPS=['patients']`). Passord-hasher, audit-logg, sesjoner og LoginEvent inngår ikke i backup. En gjenoppretting (restore) påvirker dermed ikke brukerkontoer, audit-logg eller sesjonsdata – det er ingen risiko for å eksponere historisk MFA- eller innloggingsdata gjennom en restore-operasjon.

---

## A.10 Tekniske og organisatoriske sikringstiltak (GDPR art. 32)

### Tekniske tiltak

| Tiltak | Beskrivelse |
|---|---|
| Kryptering i hvile | AES-256 (Railway infrastruktur, PostgreSQL-database) |
| Kryptering i transitt | TLS tvunget i produksjon (`SECURE_SSL_REDIRECT`); HSTS aktivert med 1 års varighet, subdomener og preload |
| Passord-hashing | Django passord-hashing via argon2 / pbkdf2; passord lagres aldri i klartekst |
| Multifaktorautentisering (MFA) | TOTP (tidsbasert engangspassord) med backup-koder (engangs). MFA trust-cookie (30 dager, signert, enhets-bundet). MFA-hendelser logges |
| Brute-force-lås | Konto låses etter 5 feilede innloggingsforsøk i 15 minutter |
| Rate-limiting | Dobbel rate-limit: maks 10 forsøk per brukernavn / 50 forsøk per IP i 5 minutter. Nødbryter: `RATELIMIT_ENABLE`-miljøvariabel |
| Sesjon-invalidering | Sesjoner ugyldiggjøres ved passord- eller MFA-bytte |
| Sesjonstimeout | Standard 8 timer, admin-justerbar mellom 1 og 24 timer |
| Rollebasert tilgangskontroll (RBAC) | 5 roller med granulerte rettigheter: `read_only`, `read_write`, `lead_view`, `lead`, `admin` (se tabell nedenfor) |
| CSRF-beskyttelse | Django CSRF-middleware aktivert på alle tilstandsendrende forespørsler |
| Content-Security-Policy | Aktiv via `SecurityHeadersMiddleware`; begrenser hvilke ressurser nettleseren kan laste |
| Sikre informasjonskapsler | Cookies satt med `Secure`, `HttpOnly` og `SameSite=Lax`-flagg |
| Clickjacking-beskyttelse | `X-Frame-Options: DENY` på alle svar |
| Innholdstype-beskyttelse | `X-Content-Type-Options: nosniff` |
| Referrer-policy | `Referrer-Policy: same-origin` |
| Permissions-policy | `camera=(), microphone=(), geolocation=()` |
| XSS-beskyttelse | Auto-escape i Djangos template-motor; manuell `escapeHtml()` i JavaScript |
| SQL-injection-beskyttelse | Django ORM benyttes; ingen rå SQL-spørringer |
| Audit-logging | Alle pasient-endringer logges på felt-nivå (bruker, IP, tidspunkt, tabell, felt, gammel/ny verdi). Innloggingsforsøk logges med IP og user-agent (LoginEvent). Backup-hendelser (opprettelse, restore, nedlasting, sletting) logges |
| Backup og gjenoppretting | Automatisk backup in-process via `BackupSchedulerMiddleware` (ingen separat tjeneste). Backup lagres som gzip-komprimert JSON på Railway Volume `/data/backups`. Retention 72 timer med automatisk sletting. Pre-restore snapshot lages før gjenoppretting for mulig rollback |
| Generisk feilhåndtering | Restore-feil gir generisk feilmelding til bruker – interne stacktraces lekkes ikke |
| Cache-isolasjon | I **lavkostnad-modus** brukes Djangos `LocMemCache` (lokal til hver Gunicorn-worker), og ingen cache-data forlater prosessen. I **vakt-modus** benytter Redis key-prefiks `pasientregistrering:` og dedikert tjeneste i Railway-prosjektet, med tilgang kun via internt Railway-nettverk (ikke offentlig). Ingen pasient-PII lagres i cachen i noen modus — kun aggregater, rate-limit-tellere og metrikk-samples uten PII |
| Auto-fallback ved Redis-utfall | Hvis Redis blir utilgjengelig under vakt-modus, fortsetter applikasjonen å fungere. Metrikk-aggregeringen (#15) skriver lokalt først (per-prosess `deque`) og supplerer Redis kun best-effort med kort socket-timeout (2 s); ved feil faller `snapshot()` automatisk tilbake til lokal kilde. Cache-helsesjekken oppdager utilgjengelig Redis og rapporterer i admin-dashbordet uten å eksponere internt feil-traceback |
| Sanering av credentials i feilmeldinger | Helperen `_scrub_secrets()` fjerner `user:password@` fra eventuelle URL-strenger som havner i feilmeldinger fra cache-/database-driverne, slik at admin-status-responsen og logger ikke kan eksponere Redis- eller Postgres-passord |
| Dataminimering | Ingen direkte identifikatorer (navn, personnummer) lagres for pasienter |
| MFA-gjenoppretting | Admin kan nullstille MFA for bruker; hendelsen loggføres som `mfa_reset_by_admin` |

**Rollematrise:**

| Rolle | Lese pasienter | Skrive pasienter | Statistikk | Admin-funksjoner | Endre andres passord |
|---|---|---|---|---|---|
| `read_only` | ✓ | – | – | – | – |
| `read_write` | ✓ | ✓ | – | – | – |
| `lead_view` | ✓ | – | ✓ | – | – |
| `lead` | ✓ | ✓ | ✓ | – | – |
| `admin` | ✓ | ✓ | ✓ | ✓ | ✓ |

### Organisatoriske tiltak

| Tiltak | Beskrivelse |
|---|---|
| Rollebasert tilgangsstyring | Fem rollenivåer som begrenser tilgang til det nødvendige (se rollematrise ovenfor) |
| Databehandleravtale | DPA signert med Railway; EU-region bekreftet |
| Behandlingsprotokoll | Dette dokumentet vedlikeholdes og oppdateres ved endringer |
| Tilbakekalling av tilgang | Brukerkontoer deaktiveres umiddelbart når tilgang ikke lenger er nødvendig |
| Sikkerhetshendelsesprosedyre | Skriftlig prosedyre for oppdagelse, vurdering og melding (se A.12) |
| Privat kodearkiv | Kildekode lagres i privat GitHub-repositorium |

---

## A.11 Offline-modus og personvern

Systemet støtter en **offline-modus** for bruk under nettverksutfall. Dette innebærer:

| Aspekt | Beskrivelse |
|---|---|
| Lokal database | Egne SQLite-database (`offline.sqlite3`) på lokal maskin |
| Lokale brukere | Genereres automatisk med egne passord (`admin-offline`, `vakt-offline`) ved oppstart av offline-modus |
| Passord-håndtering | Offline-passord dokumenteres i `OFFLINE_PASSORD.md` – lagres lokalt, ikke i kodearkiv (git) |
| Import ved reetablering | Etter nettverksutfall importeres pasientdata til produksjonsdatabasen via `python manage.py import_offline_data` |

> **Personvernrisiko ved offline-bruk:** `offline.sqlite3`-filen inneholder personopplysninger om pasienter. Filen **må slettes fra offline-enheten** etter at dataene er importert til produksjonsdatabasen og bruken er avsluttet. Enheten der offline-filen oppbevares, skal behandles med samme krav til informasjonssikkerhet som produksjonssystemet. Tap eller uautorisert tilgang til enheten utgjør et potensielt brudd på personopplysningssikkerheten som skal håndteres i henhold til prosedyren i A.12.

---

## A.12 Risikovurdering – sammendrag

| Risikoparameter | Vurdering |
|---|---|
| Sannsynlighet for sikkerhetsbrudd | Lav til moderat (begrenset eksponering, MFA, rate-limiting, brute-force-lås) |
| Konsekvens ved sikkerhetsbrudd | Moderat til høy (helseopplysninger som er særlige kategorier etter art. 9, men uten direkte identifikatorer) |
| Samlet risikonivå | Moderat – akseptabelt gitt gjennomførte tiltak |

**Identifiserte sårbarheter og begrensninger:**

- Systemet er avhengig av at brukere opptrer i henhold til tildelt rolle. Misbruk av gyldige brukerkontoer kan ikke utelukkes.
- Kliniske felter er implementert som dropdown med fast verdimengde, slik at risikoen for utilsiktet registrering av fritekst er eliminert på applikasjonsnivå.
- Pasientnummer brukes som pseudonym, men kan i prinsippet kobles til person dersom annen informasjon fra arrangementsstedet foreligger (re-identifikasjonsrisiko er vurdert som lav).
- Offline-modus innebærer at personopplysninger lagres lokalt på en enhet utenfor den kontrollerte skyinfrastrukturen – dette øker risikoen for uautorisert tilgang ved tap av enhet.
- Det foretas ingen automatisert DPIA (Data Protection Impact Assessment); ved vesentlige endringer i behandlingens art, omfang eller formål bør en full DPIA gjennomføres i henhold til GDPR art. 35.

---

## A.13 Sikkerhetsfikser foretatt pre-launch (april 2026)

Følgende sikkerhetsmessige tiltak ble gjennomført i forbindelse med klargjøring for produksjonslansering:

| Tiltak | Beskrivelse |
|---|---|
| Django 5.2+ oppgradering | Oppgradering fra Django 5.1.x for å lukke 9 kjente CVE-er i rammeverket |
| Backup ekskluderer sensitive data | `BACKUP_APPS` er satt til `['patients']` – backup inkluderer ikke `CustomUser`, `AuditLog`, `LoginEvent` eller sesjoner |
| Generisk feilmelding ved restore | Restore-operasjoner returnerer generisk feilmelding ved feil; interne stacktraces lekkes ikke til brukergrensesnittet |
| `ALLOWED_HOSTS` sikker default | Default er endret fra `*` til `.localhost,127.0.0.1`; produksjonsmiljø setter eksplisitt verdi |
| Content-Security-Policy | Lagt til via `SecurityHeadersMiddleware` |
| SHA-256 for ETag | ETag-generering endret fra MD5 til SHA-256 |

---

## A.14 Rutiner for håndtering av de registrertes rettigheter

De registrerte (pasienter og appbrukere) har rettigheter etter GDPR kapittel III. Følgende rutiner gjelder:

| Rettighet | Innhold | Rutine |
|---|---|---|
| **Innsyn / kopi (art. 15)** | Registrert kan be om å få vite hvilke opplysninger som er lagret | Henvendelse til behandlingsansvarlig. Pasienter identifiseres via sanitets-pasientnummer, tidspunkt og arrangementsopplysninger. Svar gis innen 30 dager |
| **Retting (art. 16)** | Registrert kan be om korrigering av uriktige opplysninger | Henvendelse til behandlingsansvarlig. Admin-bruker retter i systemet; endringen logges i audit-logg |
| **Sletting (art. 17)** | Registrert kan i visse tilfeller be om sletting | Vurderes konkret av behandlingsansvarlig. **Obs:** Audit-logg kan kreves bevart av faglige og/eller rettslige grunner og er ikke nødvendigvis gjenstand for sletting. Pasientdata soft-slettes; permanent sletting på forespørsel |
| **Begrensning (art. 18)** | Behandling kan begrenses midlertidig | Henvendelse behandles av behandlingsansvarlig |
| **Dataportabilitet (art. 20)** | Registrert kan be om utlevering i maskinlesbart format | Eksport av relevante data kan gjøres av admin; format JSON eller CSV |
| **Protest (art. 21)** | Registrert kan protestere mot behandlingen | Henvendelse vurderes av behandlingsansvarlig |
| **Klage** | Klage kan rettes til Datatilsynet | www.datatilsynet.no, tlf. 74 07 70 00 |

> **Praktisk merk:** Ettersom pasienter kun er registrert med løpenummer og ikke med navn eller personnummer, forutsetter utøvelse av rettigheter at den registrerte kan identifisere seg på en annen måte (f.eks. tidspunkt for besøket og arrangementsnavnet).

**Alle henvendelser om rettigheter rettes til:**  
André Eritsland – andre.eritsland@gmail.com

---

## A.15 Rutiner for håndtering av brudd på personopplysningssikkerhet (GDPR art. 33–34)

### Oppdagelse

- Audit-logger, innloggingslogger og Railway-varsler overvåkes ved mistanke om avvik.
- Brukere og administratorer oppfordres til å melde fra umiddelbart ved mistanke om uautorisert tilgang.

### Vurdering innen 72 timer

Behandlingsansvarlig skal innen 72 timer fra oppdagelse av et brudd vurdere:

1. Hva har skjedd (type og omfang av bruddet)?
2. Hvilke kategorier og antall registrerte er berørt?
3. Hvilke kategorier og mengder data er berørt?
4. Sannsynlige konsekvenser for de registrerte?
5. Tiltak som er eller vil bli gjennomført?

### Melding til Datatilsynet (art. 33)

Dersom bruddet sannsynligvis innebærer en risiko for de registrertes rettigheter og friheter, skal Datatilsynet varsles uten unødig opphold og om mulig innen 72 timer. Melding sendes via Datatilsynets varslingsportal (www.datatilsynet.no). Dersom meldingen ikke kan sendes innen 72 timer, skal grunnen til forsinkelsen oppgis.

### Melding til berørte registrerte (art. 34)

Dersom bruddet sannsynligvis medfører høy risiko for de registrertes rettigheter og friheter, skal de berørte varsles direkte uten unødig opphold. Gitt at pasientene ikke er registrert med kontaktinformasjon, vil varsling i praksis skje via arrangøren av det aktuelle eventet.

### Loggføring

Alle brudd, uavhengig av om de medfører meldeplikt, skal loggføres skriftlig med:
- Dato og tidspunkt for oppdagelse
- Beskrivelse av hendelsen
- Konsekvenser og berørte data
- Gjennomførte tiltak
- Vurdering av meldeplikt og beslutning

---

---

# DEL B: Personvernerklæring

> Denne erklæringen er ment for pasienter og brukere av systemet, og er skrevet i et lettlest språk.

---

## B.1 Hvem er vi?

Denne appen brukes av sanitetsvakter ved arrangementer for å registrere og følge opp pasienter som trenger medisinsk hjelp på stedet.

**Ansvarlig for opplysningene (behandlingsansvarlig):**  
André Eritsland, Rogaland  
E-post: andre.eritsland@gmail.com

---

## B.2 Hvilke opplysninger samler vi inn?

Vi registrerer opplysninger som er nødvendige for å gi deg god helsehjelp under arrangementet. Det er viktig å merke seg hva vi **ikke** samler inn:

**Vi samler ikke inn:**
- Navn
- Personnummer eller fødselsnummer
- Fødselsdato
- Adresse eller annen kontaktinformasjon

Du registreres kun med et sanitets-pasientnummer (løpenummer) som tildeles under vakten.

**Vi registrerer:**
- Et pasientnummer (løpenummer, ikke koblet til navn)
- Hva du oppsøkte sanitetsposten for (problemstilling/årsak) – valgt fra fast liste
- Triagekategori (rød/gul/grønn) – alvorlighetsgrad av tilstanden
- Transport til og fra sanitetsposten – valgt fra fast liste
- Hvem som behandlet deg (førstehjelper og helsepersonell)
- Om du fikk medisiner
- Kliniske observasjoner og problemstilling etter fast verdimengde
- Tidspunkter: ankomst, behandlingsstart, utskrivning (format `dd.mm.åååå tt:mm`)
- Journalkategori – valgt fra fast liste (ikke fritekst)

---

## B.3 Hvorfor registrerer vi disse opplysningene?

Opplysningene brukes til:

1. **Gi deg helsehjelp:** Behandlerne på stedet trenger en oversikt for å gi deg riktig og trygg hjelp, spesielt ved mange pasienter.
2. **Sikre kontinuitet:** Hvis du har vært inne til behandling og kommer tilbake, kan saniteten raskt se hva som er gjort.
3. **Lære og forbedre:** Etter arrangementet brukes anonymisert statistikk til å planlegge bedre beredskap ved fremtidige arrangementer.

**Rettslig grunnlag:** Behandlingen er nødvendig for å verne din helse (GDPR art. 6(1)(d) og art. 9(2)(h)), og gjennomføres av kvalifisert helsepersonell med taushetsplikt.

---

## B.4 Hvem kan se opplysningene?

| Hvem | Tilgang |
|---|---|
| Helsepersonell/frivillige på vakten | Kan registrere og se pasientopplysninger i henhold til tildelt rolle |
| Administrator (teknisk drift) | Begrenset tilgang for å drifte systemet |
| Alle andre | Ingen tilgang |

Opplysningene deles **ikke** med tredjeparter, forsikringsselskaper, arbeidsgivere, markedsføringsaktører eller andre.

---

## B.5 Hvor lenge lagres opplysningene?

| Type opplysning | Lagringstid |
|---|---|
| Pasientjournal (aktiv) | Inneværende år i produksjonsdatabasen |
| Pasientjournal (arkiv) | Minimum 3 år etter arrangementet |
| Backup-filer | 72 timer, deretter automatisk slettet |
| Innloggings- og hendelseslogger | 10 år |
| Sesjondata | Slettes automatisk etter 8 timer (eller ved utlogging) |

Etter at lagringstiden er utløpt slettes opplysningene permanent.

---

## B.6 Hvor lagres opplysningene?

Opplysningene lagres hos **Railway** (infrastrukturpartner) i en EU-region (Nederland). Dette betyr:

- Data forlater aldri EU/EØS-området.
- Alle opplysninger er kryptert med AES-256 i databasen.
- Overføring mellom deg og systemet skjer alltid kryptert via HTTPS/TLS.
- Railway er bundet av en databehandleravtale som regulerer deres bruk av dataene.

---

## B.7 Dine rettigheter

Som registrert person har du følgende rettigheter etter GDPR:

| Rettighet | Innhold |
|---|---|
| **Innsyn (art. 15)** | Du kan be om å få vite hvilke opplysninger vi har registrert om deg. |
| **Retting (art. 16)** | Du kan be om at feilaktige opplysninger rettes. |
| **Sletting (art. 17)** | Du kan i visse tilfeller be om at opplysningene slettes. Merk at deler av loggen kan kreves bevart av faglige grunner. |
| **Begrensning (art. 18)** | Du kan be om at bruken av opplysningene dine begrenses midlertidig. |
| **Dataportabilitet (art. 20)** | Du kan be om å få opplysningene dine utlevert i et maskinlesbart format. |
| **Protest (art. 21)** | Du kan protestere mot behandlingen av dine opplysninger. |
| **Klage** | Du kan klage til **Datatilsynet** (www.datatilsynet.no, tlf. 74 07 70 00). |

> **Merk:** Siden pasientene kun er registrert med løpenummer og ikke med navn eller personnummer, forutsetter utøvelse av rettigheter at du kan identifisere deg på en annen måte (f.eks. tidspunkt for besøket og arrangementsnavnet).

---

## B.8 Kontakt

Har du spørsmål om personvern, ønsker innsyn eller vil utøve andre rettigheter, ta kontakt med behandlingsansvarlig:

**André Eritsland**  
E-post: andre.eritsland@gmail.com

---

---

# DEL C: Interne rutiner og sjekklister

> Disse rutinene er til internt bruk for administratorer og ledere av sanitetsvakten.

---

## C.1 Sjekkliste før hvert event

- [ ] Verifiser at alle aktive brukere har korrekte roller (admin, lead, lead_view, read_write, read_only)
- [ ] Deaktiver eller slett brukerkontoer som ikke skal ha tilgang til dette arrangementet
- [ ] Endre aktivt år / event-navn i appinnstillinger (AppSetting)
- [ ] Verifiser at MFA er aktivert og satt opp for alle brukere med rolle `admin` og `lead`
- [ ] Test innlogging med minst én bruker fra hver rolle
- [ ] Verifiser at brute-force-lås og rate-limiting fungerer (5 feilede pålogginger gir blokkering i 15 min)
- [ ] Bekreft at sesjonstimeout er satt korrekt for vakten
- [ ] Sjekk at Railway-tjenesten kjører og at siste backup er vellykket
- [ ] Dersom offline-modus skal benyttes: klargjør offline-enhet, verifiser at `OFFLINE_PASSORD.md` er tilgjengelig lokalt

---

## C.2 Sjekkliste etter hvert event

- [ ] Eksporter pasientdata til sikker langtidslagring (arkivfil)
- [ ] Vurder om arbeidsdata skal nullstilles for neste event (ny triagering fra null) – ta backup/pre-reset snapshot først
- [ ] Verifiser at audit-logger er intakte og fullstendige for vakten
- [ ] Gå gjennom innloggingslogger: kontroller at ingen uautoriserte innlogginger har skjedd
- [ ] Deaktiver midlertidige brukere som kun var aktive for dette arrangementet
- [ ] Dokumenter eventuelle avvik eller hendelser fra vakten skriftlig
- [ ] Dersom offline-modus ble benyttet: importer data med `python manage.py import_offline_data`, og **slett `offline.sqlite3` fra offline-enheten**

---

## C.3 Databehandleravtale-sjekkliste (GDPR art. 28)

Denne sjekklisten skal gjennomgås ved etablering av ny databehandleravtale og ved den årlige revisjonen.

**Railway Corp. som databehandler:**

- [ ] DPA signert med Railway Corp. (Railway Amsterdam Data Processing Addendum)
- [ ] Bekreftet at datalagring skjer i EU-regionen europe-west4 (Nederland)
- [ ] Verifisert at Railways DPA dekker kravene i GDPR art. 28(3), herunder:
  - [ ] Behandling kun etter instruks fra behandlingsansvarlig
  - [ ] Konfidensialitetsplikt for personell med tilgang til dataene
  - [ ] Egnede tekniske og organisatoriske sikringstiltak (art. 32)
  - [ ] Bruk av underbehandlere kun med skriftlig forhåndssamtykke
  - [ ] Bistå behandlingsansvarlig med å oppfylle de registrertes rettigheter
  - [ ] Sletting eller tilbakelevering av data etter avtalens slutt
  - [ ] Tilgjengeliggjøring for revisjon

**Underbehandlere (Railways underleverandører):**

- [ ] Kartlagt hvilke underleverandører Railway benytter (f.eks. Google Cloud, AWS eller tilsvarende)
- [ ] Verifisert at Railways DPA dekker disse underbehandlerne i samsvar med GDPR art. 28(2)–(4)
- [ ] Bekreftet at underbehandlerne ikke behandler data utenfor EU/EØS, eventuelt at overføringsgrunnlag foreligger (f.eks. standardkontraktsklausuler)

**Eventuelle andre tredjepartstjenester:**

- [ ] Ingen andre databehandlere er for øyeblikket i bruk
- [ ] Ved fremtidig integrasjon av ny tjeneste: inngå DPA før data overføres

---

## C.4 Sjekkliste for årlig revisjon

- [ ] Gjennomgå og oppdater behandlingsprotokollen (Del A i dette dokumentet)
- [ ] Verifiser at Railway sin databehandleravtale og sikkerhetsdokumentasjon fortsatt er gjeldende
- [ ] Kontroller at Railway-region fortsatt er satt til EU (europe-west4 eller tilsvarende)
- [ ] Gjennomgå databehandleravtale-sjekklisten i C.3
- [ ] Test MFA-recovery-prosedyre: nullstill MFA for en testbruker og verifiser at ny oppsett fungerer
- [ ] Verifiser at automatisk sletting av backup-filer faktisk kjører (retention 72 timer)
- [ ] Verifiser at audit-logger oppbevares korrekt (ikke eldre enn 10 år uten faglig begrunnelse)
- [ ] Test SSL/TLS: verifiser at sertifikater er gyldige og at HSTS er aktivt
- [ ] Gjennomgå sikkerhetsfikser og oppgraderinger siden forrige revisjon; vurder om nye CVE-er i avhengigheter er adressert
- [ ] Vurder om det har skjedd endringer i behandlingens art, omfang eller formål som utløser behov for DPIA (art. 35)
- [ ] Gjennomgå brukerrollen til alle aktive kontoer – fjern kontoer som ikke lenger er i bruk

---

## C.5 Prosedyre ved mistanke om sikkerhetsbrudd

**Følg disse trinnene i angitt rekkefølge:**

**Trinn 1 – Oppdagelse og innledende vurdering**
- Dokumenter tidspunkt og hvordan bruddet ble oppdaget.
- Vurder omfang: hvilke data kan være berørt, og hvor mange pasienter/brukere?
- Sett tidspunkt for «awareness» – 72-timersfristen begynner her.

**Trinn 2 – Umiddelbar skadestopping (innen 1–2 timer)**
- Deaktiver berørte brukerkontoer ved behov.
- Logg alle observasjoner og handlinger fortløpende.
- Kontakt Railway support hvis bruddet skyldes infrastruktur (status.railway.app).

**Trinn 3 – Risikovurdering (innen 24 timer)**
- Er opplysninger eksponert utenfor autoriserte brukere?
- Foreligger det risiko for de registrerte (skade, diskriminering, tap av kontroll over egne opplysninger)?
- Involver eventuelt ekstern personvernkompetanse.

**Trinn 4 – Melding til Datatilsynet (innen 72 timer fra trinn 1)**
- Dersom bruddet medfører risiko for de registrerte: send melding via www.datatilsynet.no.
- Meldingen skal inneholde: beskrivelse av bruddet, berørte kategorier og antall registrerte, sannsynlige konsekvenser, gjennomførte og planlagte tiltak.
- Dersom meldingen sendes etter 72 timer, må forsinkelsen begrunnes.

**Trinn 5 – Varsling av berørte (ved høy risiko)**
- Dersom bruddet medfører høy risiko for de registrerte: varsle berørte direkte.
- Ettersom pasienter ikke er registrert med kontaktinformasjon, skjer varsling via arrangøren.
- Gi klare opplysninger om hva som har skjedd og hva de berørte kan gjøre.

**Trinn 6 – Etterhåndsdokumentasjon**
- Skriv en hendelsesrapport med: tidslinje, årsak, omfang, tiltak og vurdering av meldeplikt.
- Oppbevar rapporten i minst 5 år.
- Gjennomfør tiltak for å hindre gjentakelse.

---

---

## Signatur og godkjenning

Dette dokumentet er utarbeidet og godkjent av behandlingsansvarlig.

| | |
|---|---|
| **Navn:** | André Eritsland |
| **Dato:** | 5. juni 2026 |
| **Signatur:** | ________________________________ |

---

*Dokument: PERSONVERN_DOKUMENTASJON.md – versjon 1.4 – sist oppdatert 5. juni 2026*

**Endringslogg:**
- **v1.4 (05.06.2026):** A.6: `behandler`-felt omdøpt til `forstehjelper` (FK til Førstehjelper-tabell); `helsepersonell` omdøpt til `helsepersonell_ref` (FK); `deleted_at` erstattet med `is_active` (BooleanField, False = soft-delete). B.2: oppdatert feltbeskrivelse til «førstehjelper». Dato- og versjonsinkonsekvens rettet.
- **v1.3 (30.04.2026):** Revidert utgave. Lagt til beskrivelse av `RequestMetricsMiddleware` som ren driftslogger (teknisk telemetri uten persondata), `AppSetting` som feature-flag-store uten persondata, og tilgangsbegrensninger på admin server-status (admin-rolle + CSRF for flag-endringer). Skillet mellom `AuditLog` (persondatalogg) og driftsloggen tydeliggjort. Kolonne for Server-status lagt til i rollematrisen. A.13 oppdatert med tilsvarende sikkerhetsfikser.
- **v1.2 (25.04.2026):** Omfattende oppdatering for å reflektere prosjektets faktiske tilstand. Se sammendrag nedenfor.
- **v1.1 (19.04.2026):** Korrigert beskrivelse av feltyper — `journal` og øvrige kliniske felter er dropdown, ikke fritekst. Tidsfelter er validert serverside til formatet `dd.mm.åååå tt:mm`. Fjernet yrke fra behandlingsansvarlig-seksjonen.
- **v1.0 (19.04.2026):** Første versjon.

**Sammendrag av endringer i v1.2:**
- A.2: Presisert at Railway kan benytte underbehandlere; krav om kartlegging lagt til
- A.6: Sanitets-pasientnummer presisert (ikke navn/fnr); `helsepersonell_ref` lagt til; `deleted_at` lagt til; kategorier (helserelaterte data, skjermingsdata) tydeliggjort; audit-logg beskrevet på felt-nivå
- A.9: Backup-retention satt til 72 timer (ikke 7 dager); audit-retention endret til 10 år; arkivering ved årsskifte lagt til; presisering om at backup KUN inneholder pasientdata, ikke passord/audit/sesjoner
- A.10: Tekniske tiltak oppdatert: TLS/HSTS, argon2/pbkdf2 passord-hashing, dobbel rate-limit, brute-force-lås (5 forsøk/15 min), Content-Security-Policy, SHA-256 ETag, generisk feilmelding ved restore, pre-restore snapshot; rollematrise lagt til; referanser til django-apscheduler og separat cron-service fjernet
- A.11 (ny): Offline-modus og personvernrisiko dokumentert
- A.13 (ny): Sikkerhetsfikser foretatt pre-launch april 2026
- A.14 (ny): Rutiner for de registrertes rettigheter (innsyn, sletting, retting m.m.)
- Gammel A.11 → A.15: Bruddprosedyre (uendret innhold)
- B.2: Behandler-navn og helsepersonell-navn nevnt eksplisitt; kliniske observasjoner lagt til
- B.5: Backup-retention oppdatert til 72 timer; audit-logg til 10 år
- C.1: Oppdatert brute-force-formulering (5 forsøk/15 min); offline-sjekkliste lagt til
- C.2: Offline-importrutine og sletting av offline-fil lagt til
- C.3 (ny): Databehandleravtale-sjekkliste (GDPR art. 28)
- C.4: Oppdatert revisjonssjekkliste; referanse til backup-retention og audit-retention
