# Personvern­dokumentasjon – Pasientregistrering (sanitetsvakt)

**Siste oppdatering:** 12. august 2026  
**Versjon:** 1.5  
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

Behandlingsansvarlig er ansvarlig for at personopplysninger behandles i tråd med gjeldende personvernregelverk, herunder EUs personvernforordning (GDPR) og lov om behandling av personopplysninger (personopplysningsloven) av 2018.

> **Merk om ansvarssubjekt:** Behandlingsansvaret er per i dag lagt til André Eritsland som privatperson, ikke til organisasjonen som gjennomfører sanitetsvaktene. Det innebærer at innsynskrav, avviksmelding til Datatilsynet og det rettslige ansvaret ligger hos behandlingsansvarlig personlig. Dette er et bevisst valg og bør revurderes ved den årlige revisjonen (se C.4).

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
| Railway databasebackup | Plattformens egne sikkerhetskopier av hele PostgreSQL-databasen | **Nei — krever oppgradert abonnement** | Ja | Ja — **hele databasen**, se merknad under |

> **Lavkostnad-modus (default):** Redis-tjenesten er pauset i Railway. Applikasjonen bruker da Djangos `LocMemCache` (lokal prosessminne). Det innebærer at Redis ikke er en aktiv databehandler-relasjon i denne modusen — ingen data sendes til eller lagres i Redis. Siden bare 1 Gunicorn-worker er aktiv, er per-prosess-cache tilstrekkelig.

> **Vakt-modus:** Redis aktiveres manuelt før hver vakt (se RUNBOOK_VAKT.md §1c) og pauses etter vakten (§10b). Kun i denne perioden behandles cache-data via Redis-tjenesten i Railway-prosjektet.

> **Railway databasebackup:** Abonnementet oppgraderes i forkant av det årlige arrangementet, og plattformens automatiske databasebackup er aktiv i denne perioden (omtrent én måned i året). Resten av året kjører prosjektet på hobby-abonnement uten plattformbackup. Til forskjell fra applikasjonens egen modul-backup — som kun inneholder `patients`-data — omfatter Railways backup **hele databasen**: brukerkontoer med passord-hasher, audit-logg, innloggingshendelser, varsler og arkiv. Lagringstid og sletting styres av Railways plattformvilkår, ikke av applikasjonen. Se A.9.

> **Underbehandlere:** Railway Corp. kan benytte egne underleverandører (bl.a. skyleverandører som Google Cloud eller AWS) for å levere infrastrukturtjenestene (inkludert Redis når denne er aktiv). Behandlingsansvarlig skal kontrollere at Railways DPA dekker slike underbehandlere i samsvar med GDPR art. 28(2)–(4). Se sjekkliste i avsnitt A.13.

---

## A.3 Navn og formål med behandlingen

**Applikasjonsnavn:** Pasientregistrering (sanitetsvakt)

**Formål:**

1. **Primærformål:** Registrering, triagering og fortløpende tracking av pasienter som mottar sanitetshjelp under arrangementer (events) med medisinsk beredskap.
2. **Sekundærformål:** Operativ oversikt under vakt — hvem har ansvaret, hvor er pasienten, hva er statusen (inn/ut-tider, transport, obspost) — slik at oppfølgingen henger sammen når flere pasienter håndteres samtidig.
3. **Tertiærformål:** Statistisk evaluering og erfaringslæring i etterkant av hvert event, for å forbedre fremtidige beredskapsopplegg.

> **Avgrensning mot journalføring:** Systemet er ikke et journalsystem, og erstatter ikke journalføringen av helsehjelp. Den skjer i et separat system. Se A.4.

---

## A.4 Rettslig grunnlag

> **Viktig avklaring (v1.5):** Sanitetsportalen er **ikke et behandlingsrettet helseregister** (journalsystem). Systemet er en **operativ pasienttavle** for koordinering under vakt — triagering, plassering, ansvarsfordeling og statusoppfølging. Den faktiske journalføringen av helsehjelp skjer i et **separat journalsystem** som helsepersonell benytter. Feltet `journal` i denne appen er et **Ja/Nei-flagg** som registrerer *om* journal er ført i det eksterne systemet; det inneholder ikke journalinnhold.
>
> Tidligere versjoner av dette dokumentet påberopte seg helsepersonelloven §§ 39–40 og pasientjournalloven som rettslig grunnlag. Det var uriktig og er fjernet i v1.5. Endringen forkorter flere lagringstider, se A.9.

Behandlingen hviler på følgende rettslige grunnlag:

| Grunnlag | Hjemmel | Anvendelse |
|---|---|---|
| Vitale interesser | GDPR art. 6(1)(d) | Registrering under akutt sanitetsoppdrag, der behandlingen er nødvendig for å verne den registrertes eller en tredjepersons liv eller helse |
| Administrasjon av helse- og omsorgstjenester | GDPR art. 9(2)(h) | Grunnlag for å behandle særlige kategorier personopplysninger (helseopplysninger). Bokstav h dekker uttrykkelig *«administrasjon av helse- og omsorgstjenester»*, ikke bare selve ytelsen av helsehjelp. Operativ koordinering av sanitetsberedskap faller inn under dette |

### Vilkåret om taushetsplikt (art. 9(3))

Art. 9(2)(h) kan bare påberopes når opplysningene behandles av — eller under ansvar av — en person som er underlagt taushetsplikt, jf. art. 9(3). Vilkåret er oppfylt slik:

| Personellgruppe | Grunnlag for taushetsplikt |
|---|---|
| Helsepersonell med autorisasjon | Taushetsplikt i kraft av helsepersonelloven § 21 |
| Frivillige førstehjelpere uten helsefaglig autorisasjon | Signert taushetserklæring gjennom organisasjonen som gjennomfører sanitetsvakten: **[fyll inn organisasjonsnavn]** |

Samtlige med tilgang til pasientregistreringen har signert taushetserklæring via organisasjonen. Erklæringene oppbevares hos organisasjonen, ikke hos behandlingsansvarlig. Ved behov for dokumentasjon overfor tilsynsmyndighet innhentes de derfra.

> **Merk:** Dette vilkåret bærer hele grunnlaget for å behandle helseopplysninger. Gis en bruker tilgang uten at taushetsplikt foreligger, faller hjemmelen bort for den brukerens vedkommende. Kontroll av dette er lagt inn i sjekklisten i C.1.

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
| `journal` | **Ja/Nei-flagg:** er det ført journal på pasienten i det eksterne journalsystemet? Inneholder ikke journalinnhold | Tekst (dropdown: Ja / Nei) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `is_active` | Aktiv-flagg (False = logisk slettet / soft-delete) | Boolsk | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `created_at` | Tidspunkt posten ble opprettet (systemgenerert) | Tidsstempel | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `updated_at` | Tidspunkt posten sist ble endret (systemgenerert) | Tidsstempel | Vanlig personopplysning | GDPR art. 6(1)(d) |

**Datakategorier (oppsummert):**

- **Helserelaterte data (art. 9):** problemstilling, årsak, transport, triagering, medisiner, utskrivningsdestinasjon
- **Skjermingsdata / pseudonymisering:** pasientnummer erstatter alle direkte identifikatorer

> **Prinsipp om dataminimering (GDPR art. 5(1)(c)):** Appen lagrer **ikke** navn, personnummer (fødselsnummer), fødselsdato, adresse, telefonnummer eller andre direkte identifikatorer for pasientene. Pasientene identifiseres utelukkende ved et sanitets-pasientnummer tildelt under vakten. Dette reduserer risikoen ved et eventuelt sikkerhetsbrudd betydelig.

> **Merknad om feltyper:** Samtlige kliniske felter (inkludert `journal`, `problemstilling`, `arsak`, `transport`, `plassering`, `utskrevet_til`, `medisiner` og `grovsortering`) er implementert som **dropdown med fast verdimengde** i brukergrensesnittet. Tidsfeltene (`inntid`, `pabegynt`, `inn_obspost`, `ut_obspost`, `utskrevet`) er tekstinput, men er underlagt **streng serverside-validering** som kun aksepterer formatet `dd.mm.åååå tt:mm` (f.eks. `19.04.2026 14:30`). Forsøk på å sende inn annet format avvises med HTTP 400.
>
> **Serverside-validering av verdimengde:** Feltene `problemstilling`, `arsak`, `transport`, `grovsortering`, `plassering`, `utskrevet_til`, `lege`, `medisiner` og `journal` valideres mot en fast hviteliste i `patients/choices.py`, både ved opprettelse og oppdatering. Verdier utenfor listen avvises med HTTP 400, og pasienten lagres ikke. Det er dermed ikke lenger mulig å lagre fritekst — for eksempel et navn — i disse feltene ved å gå utenom brukergrensesnittet. En automatisk test sammenligner hvitelisten med nedtrekkslistene i skjemaet, slik at de to ikke kan komme i utakt.
>
> **Avgrensning:** Valideringen ligger i API-laget. Skriving direkte mot databasen — via `loaddata` ved gjenoppretting av backup, eller via Django-admin — går utenom den. Gjenoppretting kan derfor bringe tilbake verdier som ble lagret før valideringen ble innført.

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

### Arkivdata (vaktarkiv)

Når en vakt avsluttes, kan admin lagre den som et **låst arkiv-snapshot**. Arkivet består av to modeller i `patients/models.py`:

**`VaktArkiv`** – én rad per arkivert vakt:

| Felt | Innhold | Kategori |
|---|---|---|
| `tittel` / `arrangement_navn` | Navn på arrangementet og arkiveringstidspunkt | Ikke personopplysning |
| `importert_at` / `importert_av` | Når arkivet ble laget, og av hvilken bruker | Vanlig personopplysning (appbruker) |
| `antall_pasienter` / `year_snapshot` / `notat` | Metadata om vakten | Ikke personopplysning |
| `sha256` | Integritetssjekksum over arkivinnholdet | Ikke personopplysning |

**`ArkivertPasient`** – én rad per pasient som var registrert da vakten ble arkivert. Inneholder pasientnummer og de samme kliniske feltene som `Patient` (problemstilling, årsak, transport, grovsortering, plassering, tidsfeltene, utskrevet_til, lege, medisiner, journal). Altså **helseopplysninger etter art. 9**, på samme nivå som den aktive pasienttabellen.

To forskjeller fra `Patient` er bevisste:

- Navn på personell lagres som **frossen tekst** (`forstehjelper_navn`, `helsepersonell_navn`), ikke som referanse. Arkivet viser dermed hvem som faktisk sto der den kvelden, selv om personen senere fjernes eller endrer navn i systemet.
- Radene er **uforanderlige ved design** og beskyttet av SHA-256-sjekksummen på `VaktArkiv`.

Radene er inngangsdata til statistikken som beregnes når et arkiv åpnes. De vises ikke enkeltvis i grensesnittet. Lagringstid: se A.9.

### Varsler (Notification)

`core.Notification` gir beskjed i portalen når en bruker tildeles eller fratas ansvar for en pasient.

| Felt | Innhold | Kategori |
|---|---|---|
| `user` | Mottaker av varselet | Vanlig personopplysning (appbruker) |
| `title` / `message` | Varseltekst, f.eks. «Pasient #42 er flyttet fra deg som førstehjelper til Ola Nordmann» | Vanlig personopplysning – kobler navngitt appbruker til et pasientnummer |
| `module_slug` / `kind` / `level` | Teknisk kategorisering | Ikke personopplysning |
| `url` | Lenke til pasienten i grensesnittet (inneholder pasientnummer) | Vanlig personopplysning |
| `is_read` / `read_at` / `created_at` | Status og tidsstempler | Vanlig personopplysning |

Varslene inneholder ikke kliniske opplysninger — kun pasientnummer, rolle og personellnavn. De har kortest lagringstid av alle datakategoriene i systemet, se A.9.

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

Audit-logg-data lagres for sikkerhets- og revisjonsformål og slettes etter 2 år (se A.9).

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

Lagringstidene er fastsatt etter GDPR art. 5(1)(e): opplysningene skal ikke oppbevares lenger enn nødvendig for formålet. Ettersom systemet **ikke** er et journalsystem (se A.4), foreligger ingen journalrettslig oppbevaringsplikt som forlenger fristene.

| Datakategori | Lagringstid | Håndheves av | Begrunnelse |
|---|---|---|---|
| Cache-data lavkostnad-modus (LocMemCache i prosess) | Maks 60 sekunder, eller til prosess-omstart | Automatisk (TTL) | Kortvarig drift; per-prosess minne; ingen pasient-PII |
| Cache-data vakt-modus (Redis) | Maks 10 minutter | Automatisk (`EXPIRE`/TTL) | Kortvarig drift; ingen pasient-PII; Redis kun aktiv under vakt |
| Pasientdata (aktiv innsamling) | Inneværende år i PostgreSQL | Manuell nullstilling / arkivering | Aktiv bruk under arrangementssesong |
| Arkiverte pasientrader (`ArkivertPasient`) | **24 måneder**, deretter kollaps til aggregert statistikk | *Planlagt – se tiltaksplan fase 3.1* | Dekker to hele sesonger, slik at årets vakt kan sammenlignes med fjorårets i planleggingen. Deretter er formålet uttømt og radnivået slettes permanent |
| Arkiv-metadata og aggregert statistikk (`VaktArkiv`) | Ingen fast grense | Manuell sletting av admin | Aggregater uten radnivå; grunnlag for flerårig erfaringslæring |
| Backup-filer (applikasjonens modul-backup) | Antallsbegrenset: de nyeste **50** beholdes per modul, eldre slettes automatisk | Automatisk (`ModuleBackupConfig.max_backups`) | Teknisk gjenoppretting |
| Railway databasebackup | Styres av Railways plattformvilkår | Railway (databehandler) | Kun aktiv i den perioden abonnementet er oppgradert, ca. én måned i året |
| Varsler (`Notification`) | 30 dager | Automatisk – `purge_old_logs` via Railway Cron | Rent driftsvarsel uten dokumentasjonsverdi etter vakten |
| Audit-logger (`AuditLog`, `LoginEvent`) | **2 år (730 dager)** | Automatisk – `purge_old_logs` via Railway Cron | Hendelsesoppklaring og revisjon. Uten journalplikt er lengre oppbevaring ikke hjemlet |
| Sesjondata | 8 timer (justerbart 1–24) | Automatisk | Begrenses til nødvendig varighet per vakt |
| Brukerkontoer | Slettes manuelt når tilgang ikke lenger er nødvendig | Manuell | Lagringsbegrensning, art. 5(1)(e) |

> **Merk om audit-logg-retention:** Perioden var tidligere oppgitt som 10 år, begrunnet i journalrettslige hensyn. Da journalplikten ikke gjelder for dette systemet (se A.4), er den begrunnelsen bortfalt, og perioden er satt til 2 år i tråd med det `purge_old_logs` faktisk håndhever. Kommandoen kjøres av Railway Cron.

> **Merk om backup-retention:** Applikasjonens backup-opprydding er **antallsbasert**, ikke tidsbasert. Konstanten `RETENTION_HOURS = 72` finnes fortsatt i koden, men er ikke i bruk — den er erstattet av `ModuleBackupConfig.max_backups` (standard 50). Tidligere versjoner av dette dokumentet oppga «72 timer, deretter automatisk slettet», noe som ikke stemte med implementasjonen.

> **Merk om backup-innhold:** Applikasjonens modul-backup inneholder **kun `patients`-data**. Passord-hasher, audit-logg, sesjoner og `LoginEvent` inngår ikke, og en restore påvirker dermed ikke brukerkontoer eller logger. Dette gjelder **ikke** Railways databasebackup, som omfatter hele databasen — se A.2.

---

## A.10 Tekniske og organisatoriske sikringstiltak (GDPR art. 32)

### Tekniske tiltak

| Tiltak | Beskrivelse |
|---|---|
| Kryptering i hvile | AES-256 (Railway infrastruktur, PostgreSQL-database) |
| Kryptering i transitt | TLS tvunget i produksjon (`SECURE_SSL_REDIRECT`); HSTS aktivert med 1 års varighet, subdomener og preload |
| Passord-hashing | Djangos standard PBKDF2-HMAC-SHA256 med 1 000 000 iterasjoner; passord lagres aldri i klartekst. Argon2 er ikke installert i dag, men kan aktiveres ved å legge til `argon2-cffi`. Under testkjøring byttes hasheren til MD5 for fart — betingelsen er snever (`manage.py test`) og påvirker ikke drift |
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
| Backup og gjenoppretting | Automatisk backup in-process via `BackupSchedulerMiddleware` (ingen separat tjeneste). Backup lagres som gzip-komprimert JSON på Railway Volume `/data/backups`. Opprydding er antallsbasert: de nyeste 50 per modul beholdes (`ModuleBackupConfig.max_backups`). Pre-restore snapshot lages før gjenoppretting for mulig rollback |
| Generisk feilhåndtering | Restore-feil gir generisk feilmelding til bruker – interne stacktraces lekkes ikke |
| Cache-isolasjon | I **lavkostnad-modus** brukes Djangos `LocMemCache` (lokal til hver Gunicorn-worker), og ingen cache-data forlater prosessen. I **vakt-modus** benytter Redis key-prefiks `pasientregistrering:` og dedikert tjeneste i Railway-prosjektet, med tilgang kun via internt Railway-nettverk (ikke offentlig). Ingen pasient-PII lagres i cachen i noen modus — kun aggregater, rate-limit-tellere og metrikk-samples uten PII |
| Auto-fallback ved Redis-utfall | Hvis Redis blir utilgjengelig under vakt-modus, fortsetter applikasjonen å fungere. Metrikk-aggregeringen (#15) skriver lokalt først (per-prosess `deque`) og supplerer Redis kun best-effort med kort socket-timeout (2 s); ved feil faller `snapshot()` automatisk tilbake til lokal kilde. Cache-helsesjekken oppdager utilgjengelig Redis og rapporterer i admin-dashbordet uten å eksponere internt feil-traceback |
| Sanering av credentials i feilmeldinger | Helperen `_scrub_secrets()` fjerner `user:password@` fra eventuelle URL-strenger som havner i feilmeldinger fra cache-/database-driverne, slik at admin-status-responsen og logger ikke kan eksponere Redis- eller Postgres-passord |
| Dataminimering | Ingen direkte identifikatorer (navn, personnummer) lagres for pasienter |
| Validering av verdimengde | Kliniske felt valideres serverside mot fast hviteliste (`patients/choices.py`) ved både opprettelse og oppdatering. Hindrer at fritekst — f.eks. et navn — lagres i felt som skal være ikke-identifiserende. Automatisk test hindrer at hviteliste og skjema kommer i utakt |
| Hard-fail på manglende `SECRET_KEY` | Applikasjonen nekter å starte med `DEBUG=False` hvis `SECRET_KEY` mangler eller er satt til en kjent eksempelverdi. Hindrer at produksjon kjører på en offentlig kjent nøkkel, som ville latt sesjonscookies og MFA trust-cookies forfalskes |
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
- Verdimengden i de kliniske feltene håndheves serverside fra august 2026 (se A.6). Restrisiko: valideringen ligger i API-laget, så gjenoppretting av en backup tatt før innføringen kan bringe tilbake verdier som ikke ville blitt godtatt i dag.
- Pasientnummer brukes som pseudonym, men kan i prinsippet kobles til person dersom annen informasjon fra arrangementsstedet foreligger (re-identifikasjonsrisiko er vurdert som lav). Personell som var på vakt vil normalt kunne knytte nummer til person i minnet.
- Offline-modus innebærer at personopplysninger lagres lokalt på en enhet utenfor den kontrollerte skyinfrastrukturen – dette øker risikoen for uautorisert tilgang ved tap av enhet.
- Behandlingsansvaret ligger hos en privatperson, ikke hos organisasjonen som gjennomfører vaktene. Se merknad i A.1.

### Vurderte og fravalgte tiltak

Følgende tiltak er vurdert og bevisst ikke innført. Dokumentasjonen av vurderingen følger av ansvarlighetsprinsippet i GDPR art. 5(2).

#### Innsynslogg (logging av lesetilgang) – fravalgt

Vurderingen bygger på tre forhold:

1. Systemet er ikke et behandlingsrettet helseregister (se A.4), så den sektorspesifikke loggplikten for journalsystemer kommer ikke til anvendelse.
2. Pasienter registreres kun med løpenummer, uten navn eller fødselsnummer. Det er dermed ikke mulig å søke seg fram til en bestemt person i systemet, noe som fjerner det praktiske motivet for urettmessige oppslag.
3. Systemet har teknisk sett ingen oppslag per pasient å logge. Lesing skjer som én samlet listevisning (`GET /api/patients/`) som returnerer hele oversikten til grensesnittet; det finnes ikke noe endepunkt for å hente én enkelt pasient. En logg per post ville derfor registrert den samme hendelsen gjentatte ganger uten informasjonsverdi.

Tiltaket vurderes på nytt dersom systemet får oppslag på enkeltpasienter, dersom direkte identifikatorer tas inn, eller dersom brukergruppen utvides vesentlig.

#### Begrenset lesetilgang («Mine pasienter» som tilgangsgrense) – fravalgt

Alle med tilgang til pasientregistreringen har tjenstlig behov for hele oversikten for å utøve rollen sin: triagering, ressursfordeling og overlevering forutsetter at man ser alle pasienter på posten, ikke bare egne. Filteret «Mine pasienter» beholdes derfor som et visningsvalg, ikke som en tilgangsgrense. Tilgang styres i stedet gjennom hvem som får konto, rollenivået deres, og taushetsplikten i A.4.

#### DPIA (art. 35) – vurdert som ikke påkrevd

Behandlingen omfatter særlige kategorier personopplysninger, men i begrenset omfang, uten direkte identifikatorer, uten profilering eller automatiserte avgjørelser, og uten systematisk overvåking av offentlig område. Vilkåret om behandling «i stor skala» anses ikke oppfylt. En full DPIA er derfor ikke gjennomført. Vurderingen tas opp igjen ved den årlige revisjonen og ved vesentlige endringer i behandlingens art, omfang eller formål — særlig dersom nye moduler tar inn direkte identifikatorer.

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
| **Sletting (art. 17)** | Registrert kan i visse tilfeller be om sletting | Vurderes konkret av behandlingsansvarlig. Pasientdata soft-slettes; permanent sletting på forespørsel. **Obs:** opplysningene kan også finnes i arkiv og i backup-filer — sletting er ikke fullført før disse er ryddet, se C.2. Audit-logg kan bevares der det er nødvendig for informasjonssikkerheten |
| **Begrensning (art. 18)** | Behandling kan begrenses midlertidig | Henvendelse behandles av behandlingsansvarlig |
| **Dataportabilitet (art. 20)** | Registrert kan be om utlevering i maskinlesbart format | Eksport av relevante data kan gjøres av admin; format JSON eller CSV |
| **Protest (art. 21)** | Registrert kan protestere mot behandlingen | Henvendelse vurderes av behandlingsansvarlig |
| **Klage** | Klage kan rettes til Datatilsynet | www.datatilsynet.no, tlf. 74 07 70 00 |

> **Praktisk merk:** Ettersom pasienter kun er registrert med løpenummer og ikke med navn eller personnummer, forutsetter utøvelse av rettigheter at den registrerte kan identifisere seg på en annen måte (f.eks. tidspunkt for besøket og arrangementsnavnet).

> **Kjent begrensning ved sletting av brukerkontoer (per v1.5):** En bruker som har arkivert en vakt kan foreløpig ikke slettes — feltet `VaktArkiv.importert_av` har `on_delete=PROTECT`, og databasen avviser slettingen. Inntil dette er endret (se tiltaksplan fase 4.1) må slike kontoer deaktiveres i stedet for å slettes, og behandlingsansvarlig må vurdere om deaktivering er tilstrekkelig i det konkrete tilfellet.

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
- Om det er skrevet journal på deg i helsetjenestens ordinære journalsystem (kun «ja» eller «nei»)

> **Merk:** Denne appen er en arbeidstavle for sanitetsvakten under arrangementet — den er ikke din pasientjournal. Får du helsehjelp som journalføres, skjer det i helsetjenestens eget journalsystem. Her lagres bare oversikten vakten trenger for å holde styr på hvem som er hvor og hvem som har ansvaret.

---

## B.3 Hvorfor registrerer vi disse opplysningene?

Opplysningene brukes til:

1. **Gi deg helsehjelp:** Behandlerne på stedet trenger en oversikt for å gi deg riktig og trygg hjelp, spesielt ved mange pasienter.
2. **Sikre kontinuitet:** Hvis du har vært inne til behandling og kommer tilbake, kan saniteten raskt se hva som er gjort.
3. **Lære og forbedre:** Etter arrangementet brukes anonymisert statistikk til å planlegge bedre beredskap ved fremtidige arrangementer.

**Rettslig grunnlag:** Behandlingen er nødvendig for å verne din helse (GDPR art. 6(1)(d)) og for å administrere helsehjelpen som ytes under arrangementet (GDPR art. 9(2)(h)). Alle som har tilgang til opplysningene er underlagt taushetsplikt — helsepersonell i kraft av loven, øvrige gjennom signert taushetserklæring.

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
| Opplysningene om deg (aktiv vakt) | Inneværende år i produksjonsdatabasen |
| Arkivert vakt – opplysninger om deg | 24 måneder. Deretter slettes de permanent, og bare anonym statistikk beholdes |
| Arkivert vakt – anonym statistikk | Beholdes for å planlegge framtidige arrangementer. Kan ikke spores tilbake til deg |
| Sikkerhetskopier | De nyeste 50 beholdes; eldre slettes automatisk |
| Innloggings- og hendelseslogger | 2 år |
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

## B.8 For deg som har brukerkonto (frivillig eller helsepersonell)

Denne delen gjelder deg som logger inn i systemet og registrerer pasienter — ikke pasientene. Også du er registrert, og har de samme rettighetene.

### Hva vi lagrer om deg

| Opplysning | Hvor lenge |
|---|---|
| Brukernavn, e-postadresse (valgfritt) og rollenivå | Så lenge kontoen er aktiv |
| Tidspunkt for siste innlogging | Så lenge kontoen er aktiv |
| Innloggingshendelser: tidspunkt, IP-adresse, nettleser, om innloggingen lyktes, MFA-hendelser | 2 år |
| Endringslogg: hvilke endringer du har gjort på pasientopplysninger, med tidspunkt og IP | 2 år |
| Varsler du har fått i portalen | 30 dager |
| Navnet ditt på pasienter du har hatt ansvar for under en arkivert vakt | Følger arkivet |

### Hvorfor

Innloggings- og endringsloggen føres for å ivareta informasjonssikkerheten: den gjør det mulig å oppklare hendelser og avdekke uautorisert bruk. Rollen din styrer hva du får tilgang til. Navnet ditt registreres på pasienter du har ansvar for, slik at vakten vet hvem som følger opp hvem.

### Én ting du bør være klar over

Når en vakt arkiveres, **fryses navnet ditt** på de pasientene du hadde ansvar for. Det gjøres med vilje: arkivet skal vise hvem som faktisk var på jobb den kvelden, også flere år etterpå. Sletter du brukerkontoen din senere, blir navnet stående i arkivet.

Det betyr at retten til sletting ikke omfatter denne opplysningen fullt ut — den er nødvendig for at dokumentasjonen av vakten skal være etterrettelig. Alt annet vi lagrer om deg kan slettes.

### Dine rettigheter

Du har de samme rettighetene som er beskrevet i B.7 — innsyn, retting, sletting, begrensning, dataportabilitet, protest og klage til Datatilsynet. Henvend deg til kontakten under.

---

## B.9 Kontakt

Har du spørsmål om personvern, ønsker innsyn eller vil utøve andre rettigheter, ta kontakt med behandlingsansvarlig:

**André Eritsland**  
E-post: andre.eritsland@gmail.com

---

---

# DEL C: Interne rutiner og sjekklister

> Disse rutinene er til internt bruk for administratorer og ledere av sanitetsvakten.

---

## C.1 Sjekkliste før hvert event

- [ ] **Bekreft at alle med tilgang har signert taushetserklæring** (eller har taushetsplikt som autorisert helsepersonell). Dette bærer det rettslige grunnlaget etter art. 9(3) – se A.4
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

> **Ved sletting av et arkiv etter krav om sletting (art. 17):** husk at arkivet også kan finnes i backup-filer. Sletting er ikke fullført før backuper som inneholder de aktuelle radene er ryddet eller utløpt. Gjelder både applikasjonens modul-backup og eventuell aktiv Railway-databasebackup.

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
- [ ] Verifiser at automatisk opprydding av backup-filer faktisk kjører (antallscap, standard 50 per modul)
- [ ] Verifiser at `purge_old_logs` kjører som planlagt, og at ingen audit-logger er eldre enn 2 år
- [ ] Verifiser at arkiverte pasientrader eldre enn 24 måneder er kollapset til aggregert statistikk
- [ ] Vurder om behandlingsansvaret fortsatt bør ligge hos privatperson, eller om det bør overføres til organisasjonen (se A.1)
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
| **Dato:** | 12. august 2026 |
| **Signatur:** | ________________________________ |

---

*Dokument: PERSONVERN_DOKUMENTASJON.md – versjon 1.5 – sist oppdatert 12. august 2026*

**Endringslogg:**

- **v1.5 (12.08.2026):** Gjennomgang mot faktisk kode. **Rettslig grunnlag omskrevet:** systemet er ikke et behandlingsrettet helseregister — journalføring skjer i eksternt system, og feltet `journal` er kun et Ja/Nei-flagg. Helsepersonelloven §§ 39–40 og pasientjournalloven fjernet som grunnlag; art. 6(1)(d) og 9(2)(h) står igjen, med taushetspliktvilkåret i art. 9(3) dokumentert. **Lagringstider forkortet** som følge av bortfalt journalplikt: audit-logg 10 år → 2 år (samsvarer nå med `purge_old_logs`), arkiverte pasientrader 24 mnd med påfølgende kollaps til aggregat, varsler 30 dager. **Backup-retention korrigert:** oppryddingen er antallsbasert (`max_backups`, standard 50), ikke 72 timer — `RETENTION_HOURS` er død kode. **Nye datakategorier dokumentert:** `VaktArkiv`, `ArkivertPasient` og `core.Notification`. **Railway databasebackup** lagt inn som egen behandling i A.2, med presisering av at den omfatter hele databasen. **A.12:** påstanden om at fritekst-risiko er eliminert er korrigert — verdimengden håndheves foreløpig kun i grensesnittet; nytt underkapittel dokumenterer fravalg av innsynslogg, fravalg av begrenset lesetilgang og vurderingen av DPIA. **Del B:** ny B.8 med informasjon til appbrukere (frivillige og helsepersonell), som tidligere manglet helt; Kontakt flyttet til B.9. **A.1:** merknad om at behandlingsansvaret ligger hos privatperson. Sjekklistene i C.1, C.2 og C.4 oppdatert tilsvarende.
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
