# Personvern­dokumentasjon – Pasientregistrering (sanitetsvakt)

**Siste oppdatering:** 26. september 2026  
**Versjon:** 1.13  
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

| Felt | Opplysning |
|---|---|
| Navn | Scaleway SAS |
| Rolle | Databehandler (Object Storage for krypterte sikkerhetskopier, fra 13. sep. 2026) |
| Avtalegrunnlag | Scaleway Data Processing Agreement, https://www-uploads.scaleway.com/DPA_2024_ENG_b0abb5cc26.pdf |
| Databehandlingsregion | nl-ams (Amsterdam, Nederland, EU), One Zone |
| Innhold | **To slag filer, se tabellen under.** Alle **kryptert før de forlater Railway** (AES-256-GCM, nøkkel som Scaleway ikke har). Scaleway ser bare chiffertekst. I tillegg Scaleways egen kryptering på disk (SSE) |
| Sletting | Livssyklusregler per prefiks: `backups/` 730 dager, `full/` 90 dager. Se A.9 |
| Tilgang | Egen IAM-applikasjon med skrive- og leserett på objekter, **uten sletterett**. Bucketen er privat, uten versjonering |

**Hva som faktisk ligger i bucketen** (utvidet 14. sep. 2026 — fram til da lå bare
modulfilene der):

| Prefiks | Innhold | Personopplysninger | Frist |
|---|---|---|---|
| `backups/` | Åtte modulfiler: `portal`, `patients`, `arkiv`, `oppdrag`, `oppdrag_arkiv`, `vaktliste`, `ko`, `backlog` | Modulenes egne data — helseopplysninger i `patients`, `arkiv` og `ko`, mannskapsdata i `vaktliste`. **Ikke** brukerkontoer, ikke audit-logg | 730 dager |
| `full/` | Hele databasen i én fil | **Alt i A.6**, inkludert brukerkontoer med passord-hasher, TOTP-hemmeligheter, innloggingshendelser og audit-logg | 90 dager |

> **Den hele fila inneholder autentiseringsdata, og det er en bevisst utvidelse.**
> Fram til 14. sep. 2026 inneholdt bucketen kun modulenes data. Den hele fila må være
> selvbærende for å kunne gjenopprettes i en tom base — der finnes det ingen konto å logge
> inn som — og derfor er brukere, MFA-hemmeligheter og logg med. Utelatt er kun sesjoner,
> contenttypes, rettighetsrader, Django-admins egen logg og portalens backup-metadata.
>
> **Risikoen er håndtert i tre lag, ikke ved å la være:** fila krypteres med AES-256-GCM
> før opplasting med en nøkkel Scaleway ikke har og som også finnes i en passordbehandler
> utenfor Railway; oppbevaringstiden er **90 dager** mot modulfilenes 730, fordi
> autentiseringsdata ikke skal ligge i to år; og IAM-nøkkelen har ikke sletterett, så en
> kompromittert portal kan ikke slette sikkerhetskopiene.
>
> **Fristene håndheves av Scaleway, ikke av portalen.** Portalen leser reglene tilbake fra
> bucketen og viser avvik på `/portal-admin/backup/`. Prefikset må skrives nøyaktig:
> `/full` er ikke `full/`, og en regel som treffer ingenting er en oppbevaringstid som
> stille ble uendelig.
>
> **Backupfilene finnes ikke andre steder.** Portalen har ingen nedlastingsfunksjon, heller
> ikke for modulfilene — en `.json.gz` med hele pasientregisteret utenfor portalens
> kontroll er en spredning ingen har vurdert.

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

> **Railway databasebackup:** Abonnementet oppgraderes i forkant av det årlige arrangementet, og plattformens automatiske databasebackup er aktiv i denne perioden (omtrent én måned i året). Resten av året kjører prosjektet på hobby-abonnement uten plattformbackup. Railways backup omfatter **hele databasen**: brukerkontoer med passord-hasher, audit-logg, innloggingshendelser, varsler og arkiv. Lagringstid og sletting styres av Railways plattformvilkår, ikke av applikasjonen. Se A.9.

> *Merknad 14. sep. 2026:* denne teksten sa tidligere at applikasjonens egen backup «kun inneholder `patients`-data». Det er ikke lenger riktig på noen av punktene — portalen har seks modulfiler og i tillegg en hel databasebackup med samme innhold som Railways. Forskjellen er ikke lenger *hva* som sikkerhetskopieres, men *hvem som har nøkkelen*: portalens egne filer er kryptert med en nøkkel verken Railway eller Scaleway har.

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
| `role` | **Kontotype**, ikke tilgangsnivå: `admin` eller `bruker` | Vanlig personopplysning |
| `ModulTilgang` (egen tabell) | Én rad per modul brukeren har tilgang til, med nivå. Dette er den faktiske tilgangsstyringen — se A.10. Ingen rad betyr ingen tilgang | Vanlig personopplysning |
| `last_login_at` | Tidspunkt siste vellykkede innlogging | Vanlig personopplysning |
| `created_at` / `updated_at` | Systemtidsstempler | Vanlig personopplysning |

Passord lagres **ikke i klartekst** – se avsnitt A.10 om passord-hashing.

### Arkivdata (vaktarkiv)

Når en vakt avsluttes, kan admin lagre den som et **låst arkiv-snapshot**. Arkivet består av to modeller i `patients/models.py`:

**`VaktArkiv`** – én rad per arkivert vakt:

| Felt | Innhold | Kategori |
|---|---|---|
| `tittel` / `arrangement_navn` | Navn på arrangementet og arkiveringstidspunkt | Ikke personopplysning |
| `importert_at` | Når arkivet ble laget | Ikke personopplysning |
| `importert_av` / `importert_av_navn` | Hvilken bruker som arkiverte vakten. Navnet lagres frosset som tekst i tillegg til referansen, slik at det består om kontoen slettes | Vanlig personopplysning (appbruker) |
| `antall_pasienter` / `year_snapshot` / `notat` | Metadata om vakten | Ikke personopplysning |
| `sha256` | Integritetssjekksum over arkivinnholdet | Ikke personopplysning |

**`ArkivertPasient`** – én rad per pasient som var registrert da vakten ble arkivert. Inneholder pasientnummer og de samme kliniske feltene som `Patient` (problemstilling, årsak, transport, grovsortering, plassering, tidsfeltene, utskrevet_til, lege, medisiner, journal). Altså **helseopplysninger etter art. 9**, på samme nivå som den aktive pasienttabellen.

To forskjeller fra `Patient` er bevisste:

- Navn på personell lagres som **frossen tekst** (`forstehjelper_navn`, `helsepersonell_navn`), ikke som referanse. Arkivet viser dermed hvem som faktisk sto der den kvelden, selv om personen senere fjernes eller endrer navn i systemet.
- Radene er **uforanderlige ved design** og beskyttet av SHA-256-sjekksummen på `VaktArkiv`.

Radene er inngangsdata til statistikken som beregnes når et arkiv åpnes. De vises ikke enkeltvis i grensesnittet.

**Kollaps etter 24 måneder:** når et arkiv er eldre enn 24 måneder, slettes `ArkivertPasient`-radene permanent og erstattes av den ferdig beregnede statistikken, lagret som `VaktArkiv.aggregat`. Alle tall som vises i arkivvisningen bevares — sammendrag, triagefordeling, tidsstatistikk, krysstabeller og de statistiske testene. Det som forsvinner, er enhver opplysning om enkeltpasienter.

Etter kollaps kan ingen opplysning i arkivet føres tilbake til en person. Operasjonen er irreversibel og kjøres av `kollaps_arkiv` (Railway Cron). Den nekter å kollapse et arkiv med mindre det finnes en backup av modulen `arkiv` tatt etter at arkivet ble opprettet, og hver kollaps loggføres i `AuditLog`.

**Integritetssjekk:** feltet `sha256` er beregnet over pasientradene og kan ikke verifiseres etter kollaps. Ved kollaps beregnes derfor en ny sjekksum over det frosne aggregatet (`aggregat_sha256`), som overtar tuklingsdeteksjonen. Den opprinnelige sjekksummen beholdes som historisk fingeravtrykk av radene som fantes, men er ikke lenger etterprøvbar. Arkivvisningen skiller eksplisitt mellom de to tilstandene via feltet `kollapset`.

### Oppdragsdata (oppdragsmodulen – bil og beredskapsambulanse)

Oppdragsmodulen (`oppdrag/`) registrerer utrykningsoppdrag som tildeles bil- og
beredskapsambulanseenheter under vakt: hva slags hendelse, hvor på arrangementet, og
tidspunktene for enhetens statusmeldinger («Rykker ut», «Fremme», «Avreist», «Leverer»,
«Ledig»). Denne seksjonen er skrevet **før modulen settes i produksjon**, slik at
protokollen dekker behandlingen fra første dag.

**Personen oppdraget gjelder registreres uten noen identifikator.** Et oppdrag lagrer
verken pasientnummer, navn eller annen kobling til en person — heller ikke referanse til
pasientmodulen; det er et bevisst arkitekturvalg. `oppdragsnummer` identifiserer
*oppdraget*, ikke personen, og lar seg ikke koble til pasienttavlens løpenummer. Den registrerte er samme kategori som
«Pasienter» i A.5, men med enda sterkere dataminimering enn pasienttavlen: der pasienten
har et løpenummer, har oppdraget ingenting. Re-identifisering krever kunnskap utenfra
(hvem som var hvor når), på samme måte som for pasientnummer — se A.12.

Felter i `Oppdrag` (fra `oppdrag/models.py`):

| Felt (teknisk navn) | Beskrivelse | Datatype | Kategori | Hjemmel |
|---|---|---|---|---|
| `problemstilling` | Kategorisk angivelse av hendelsen (samme type liste som pasienttavlen, inkl. sensitive verdier som «Psykiatri» og «Mistanke overgrep») | Tekst (dropdown – fast verdimengde, håndhevet server-side i `oppdrag/choices.py`) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `hastegrad` | AMK-inndelingen Akutt / Haster / Vanlig | Tekst (dropdown – fast verdimengde, håndhevet server-side) | **Sensitiv – helseopplysning (art. 9)** | GDPR art. 9(2)(h) |
| `lokasjon` | Sted på arrangementet (referanse til admin-vedlikeholdt liste, `Lokasjon`-tabellen) | Referanse (dropdown) | Vanlig personopplysning (oppholdssted på arrangementet, ikke bosted) | GDPR art. 6(1)(d) |
| `fritekst` | Fritt tekstfelt for operativ tilleggsinformasjon til enheten | Fritekst | **Kan inneholde helseopplysninger (art. 9) og i verste fall identifikatorer** – se tiltakene under | GDPR art. 9(2)(h) |
| `status` | Gjeldende status (fast verdimengde) | Tekst (fast verdimengde) | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `oppdragsnummer` | Løpenummer for oppdraget innen året, brukt på samband og for gjenfinning. **Ikke koblet til pasientnummer** og ikke en identifikator for personen | Heltall, unikt per år | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `historikk_fra` / `historikk_av` | Når oppdraget ble ryddet bort fra den aktive tavla og over i historikken, og av hvem (NULL = flyttet automatisk da oppdraget ble ledig). **Ikke arkivering i `core.arkiv`-forstand** — ingenting fryses eller slettes, og handlingen er reversibel | Tidsstempel / referanse | Vanlig personopplysning (appbruker) | GDPR art. 6(1)(d) |
| `year` / `created_at` / `updated_at` | Årsscoping og systemtidsstempler | Heltall / tidsstempel | Vanlig personopplysning | GDPR art. 6(1)(d) |
| `opprettet_av` | Appbrukeren som opprettet oppdraget | Referanse | Vanlig personopplysning (appbruker) | GDPR art. 6(1)(d) |
| `enhet` | Enheten oppdraget er tildelt | Referanse | Ikke personopplysning i seg selv (se `Enhet` under) | – |

Øvrige modeller i modulen:

- **`Statusmelding`** – én rad per statusovergang: status, hendelsestidspunkt, hvem som
  meldte (`meldt_av`, appbruker), og tekniske flagg (`forsinket`, `automatisk`,
  `korrigerer`). Korreksjoner lagres som nye rader som peker på den gamle — sporet av hva
  som faktisk ble meldt bevares.
- **`Enhetsbytte`** – flytting av et oppdrag mellom enheter: fra/til-enhet, tidspunkt og
  hvem som flyttet (`byttet_av`, appbruker).
- **`Enhet`** – bilen/ambulansen: sambandsnavn (f.eks. «Haugesund 56») og kobling til
  kontoen enheten logger inn med (appbrukerdata; kontoen bør være en delt enhetskonto,
  ikke en personlig). Navnet er ikke en personopplysning.
- **`Lokasjon`** – stedsnavn på arrangementet. Ikke personopplysninger.

**`Leverer` registrerer ikke hvor det leveres.** Det er et bevisst valg for å holde
helseopplysning (at noen ble levert) og posisjon (hvor) fra hverandre.

**Tiltak rundt fritekstfeltet** — modulens eneste frie felt, og portalens første frie
tekstfelt som kan ses av flere enn den som skrev det:

1. **Unntatt verdilogging i audit-loggen.** `AuditLog` lagrer *at* feltet ble endret, av
   hvem og når, men verdien skrives som `(skjult)` — aldri innholdet. Uten unntaket ville
   hver versjon av teksten ligget i en tabell med 730 dagers lagring (A.9), også
   versjoner operatøren rettet nettopp fordi de var for detaljerte. Sletting av et
   oppdrag logger kun ID-en, uten innhold. Regelen har vært aktiv fra feltets første
   lagring og er låst med automatiske tester (`oppdrag/tests.py::AuditFritekstTests`).
2. **Server-side skjuling mot enhetskontoer.** Fritekst utelates fra serverens svar til
   enheten straks oppdraget er avsluttet, og hele oppdraget utelates 30 minutter etter.
   Skjulingen er et visningsfilter i API-svaret, ikke sletting — sentralbord og
   statistikk beholder raden — men en bil som blir stående ulåst eksponerer ikke gamle
   oppdragstekster.
3. **Veiledning i skjemaet.** Feltet har hjelpeteksten «Vises i bilen til oppdraget
   avsluttes. Innholdet lagres ikke i auditloggen», slik at operatøren vet hvem som ser
   teksten.
4. **Ingen mellomlagring.** Oppdragsdata caches ikke i Redis; avsnittet om cache-data
   under gjelder uendret.

### Mannskapsdata (vaktlistemodulen)

Vaktlistemodulen (fase 1 levert; se `docs/BESLUTNING_VAKTLISTE.md`) fører et
**globalt mannskapsregister**: de frivillige organisasjonen har, som hver vakt
bemanner fra. Dette er personopplysninger om **egne frivillige**, ikke om
pasienter — en annen registrertgruppe enn resten av protokollen, med berettiget
interesse (art. 6(1)(f)) som grunnlag: organisasjonen må vite hvem den kan
bemanne med, og hvordan de nås under vakt.

Følgende lagres om **mannskap** (basert på `Mannskap`-modellen i
`vaktliste/models.py`):

| Felt (teknisk navn) | Beskrivelse | Datatype | Kategori | Hjemmel |
|---|---|---|---|---|
| `navn` | Fullt navn | Tekst | Vanlig personopplysning | GDPR art. 6(1)(f) |
| `korps` | Korpset personen tilhører (FK til Korps-register) | Referanse | Vanlig personopplysning (organisasjonstilhørighet) | GDPR art. 6(1)(f) |
| `kompetanser` | Kompetanser (M2M mot admin-styrt register) | Referanser | Vanlig personopplysning | GDPR art. 6(1)(f) |
| `telefon` | Telefonnummer, brukes av KO/vaktleder under vakt | Tekst, valgfritt | Vanlig personopplysning | GDPR art. 6(1)(f) |
| `user` | Valgfri kobling til portalkonto | Referanse | Vanlig personopplysning | GDPR art. 6(1)(f) |
| `er_aktiv` | Aktiv-flagg; pensjonering er den normale veien ut av registeret | Boolsk | Vanlig personopplysning | GDPR art. 6(1)(f) |
| `notat` | Fritekst. **Unntatt verdilogging i audit** (som `Oppdrag.fritekst`) | Tekst, valgfritt | Vanlig personopplysning | GDPR art. 6(1)(f) |

**Kostbehov/matallergi lagres bevisst ikke.** Det er en helseopplysning
(særlig kategori, art. 9), og beslutningen ble å holde den utenfor portalen i
sin helhet — den samles inn utenfor systemet av den som bestiller mat.
Notatfeltet er unntatt verdilogging nettopp fordi fritekst er der slike
opplysninger havner når det ikke finnes et felt for dem: skriver noen det der
likevel og retter det, ligger ikke begge versjonene i revisjonsloggen i to år.
Feltets hjelpetekst sier eksplisitt at helseopplysninger ikke skal skrives der.

Registrene `Korps`, `Kompetanse` og `VaktRolle` er organisasjonsoppsett uten
personopplysninger. Vaktposter (hvem som var på vakt hvor, med tider) kommer i
modulens fase 2 og føres inn her da.

#### Overnatting (`Overnattingsrom`, `Overnatting`) — 25. september 2026

**Formålet er brannsikkerhet**: når brannalarmen går om natta, skal den som teller opp vite
hvem som skal være i hvilket rom. Det er en opplysning om **hvor en navngitt frivillig
befinner seg om natta** — vanlig personopplysning, ikke særlig kategori, men en som ikke
skal ligge lenger enn formålet varer. Grunnlag: berettiget interesse (art. 6(1)(f)), og
formålet er også i mannskapets egen interesse.

| Felt | Innhold | Kategori |
|---|---|---|
| `Overnatting.mannskap` | Hvem (peker på mannskapsregisteret — bare registrerte frivillige, ingen fritekstnavn) | Vanlig personopplysning |
| `Overnatting.rom` / `natt` | Hvilket rom, hvilken natt | Vanlig personopplysning (oppholdssted) |
| `Overnattingsrom` (navn, plassering, kapasitet, merknad) | Rommet. Merknaden er om rommet («nødutgang: vindu»), **aldri om en person** — hjelpeteksten sier det | Ikke personopplysning |
| `Vaktliste.brannrutine` | Stedets rutine ved alarm, skrevet av vaktleder | Ikke personopplysning |

**Tilgang:** alle med lesetilgang til vaktlista ser alle rom og navn — den som teller opp
trenger hele lista. **Telefonnummer og skiftdetaljer vises bare** for egne korps eller for
dem som ser alle korps, som ellers i modulen. Alle ser *at* en person er på vakt om natta
(opptellingen trenger det), men bare de samme ser på hvilken ressurs og når (26.09.2026).

**Lagringstid:** plasseringene slettes **30 dager etter natta**, automatisk (se A.9).
Rommene blir stående. **To steder lever opplysningen lenger, og det er bevisst:**
revisjonsloggen har en rad for hver plassering som ble opprettet, flyttet eller fjernet av
en person (hvem gjorde det, og hvem det gjaldt), med revisjonsloggens frist på 730 dager —
«hvem flyttet Per ut av rom 2B» er nettopp det man leter etter når opptellingen ikke
stemte. Og modulbackupen følger backupfristene. **Selve ryddingen skriver ingenting i
revisjonsloggen** — ellers ville den bevart i to år det som skulle bort etter 30 dager.

### KO-loggen (`ko.Logglinje`)

Hendelsesloggen i KO-modulen (KO pulje 2, 17. september 2026). Den dekker **det som skjer
utenfor samleplass og sykestue**; blir personen pasient, registreres hun i
pasientmodulen. Loggen er **ikke** audit-loggen: `audit/` er automatisk, på feltnivå og
finnes for sikkerhet, mens denne er menneskeskrevet og i praksis dokumentet man leser
etter et arrangement der noe gikk galt.

| Felt | Innhold | Kategori |
|---|---|---|
| `tekst` | **Fritekst** skrevet av en operatør: «mann, ca. 60, kollapset ved scene sør» | **Særlig kategori (art. 9)** – helseopplysning, indirekte identifiserende |
| `tidspunkt` / `registrert_at` | Når det skjedde, og når linja ble skrevet | Vanlig personopplysning |
| `forfatter` / `forfatter_navn` / `forfatter_delt_konto` | Hvem som førte linja, frosset på raden | Vanlig personopplysning (appbruker) |
| `ansvarsomraade` | Hva operatøren gjorde – samband, ressurser, logg | Vanlig personopplysning (appbruker) |
| `kilde` / `systemkode` / `systemdata` | Løftede systemhendelser: kallesignal, oppdragsnummer, statusnavn | Ikke særlig kategori – bygget av verdimengder, ingen fritekst |
| `korrigerer` / `rot` | Korreksjonskjeden – retting skjer som ny rad, aldri ved å endre | Ikke personopplysning |
| `fjernet_at` / `fjernet_av` / `fjernet_av_navn` | Sletteinngangen: hvem tømte innholdet, og når | Vanlig personopplysning (appbruker) |

**Opplæringen er at direkte identifiserende opplysninger ikke skrives i `tekst`.** Det er
den sterkeste formen for dataminimering som finnes, og den reduserer risikoen reelt — men
designet antar at opplæring forvitrer under press, og har derfor en sletteinngang. Se A.9
for oppbevaringstid, sletteinngangen og forbeholdet om backupene.

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
| Berørt felt | Feltnavn, gammel verdi, ny verdi (felt-nivå granularitet). **Unntak:** `Oppdrag.fritekst` logges uten verdier — raden viser `(skjult)`, se «Oppdragsdata» over |
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
| Oppdragsdata (`Oppdrag`, `Statusmelding`, `Enhetsbytte`) | Inneværende vakt i PostgreSQL, til vakta arkiveres | Manuell arkivering av admin | Aktiv bruk under vakt; statistikk og erfaringslæring etterpå |
| Arkiverte oppdrag (`ArkivertOppdrag`) | **24 måneder**, deretter kollaps til aggregert statistikk | Automatisk – `kollaps_arkiv` via Railway Cron | Samme begrunnelse som for arkiverte pasientrader: to hele sesonger til sammenligning, deretter er formålet uttømt og radnivået slettes permanent |
| Arkiv-metadata og aggregert statistikk (`OppdragArkiv`) | Ingen fast grense | Manuell sletting av admin | Aggregater uten radnivå; grunnlag for flerårig erfaringslæring |
| Arkiverte pasientrader (`ArkivertPasient`) | **24 måneder**, deretter kollaps til aggregert statistikk | Automatisk – `kollaps_arkiv` via Railway Cron | Dekker to hele sesonger, slik at årets vakt kan sammenlignes med fjorårets i planleggingen. Deretter er formålet uttømt og radnivået slettes permanent |
| Arkiv-metadata og aggregert statistikk (`VaktArkiv`) | Ingen fast grense | Manuell sletting av admin | Aggregater uten radnivå; grunnlag for flerårig erfaringslæring |
| Backup-filer på Railway-volumet – alle moduler | Antallsbegrenset: de nyeste **50** beholdes som standard, eldre slettes automatisk | Automatisk (`core.Backupplan.behold`, satt per modul) | Teknisk gjenoppretting. Antallsbasert og ikke tidsbasert: det som betyr noe er at det finnes nok kopier til å gå tilbake forbi en feil, ikke hvor gamle de er |
| Backup-filer offsite – modulfilene (`backups/`) | **730 dager (2 år)** | Scaleway livssyklusregel | Samme frist som arkivkollapsen og audit-loggen. Portalens nøkkel har ikke sletterett, så fristen kan bare håndheves av bucketen |
| Backup-filer offsite – hele databasen (`full/`) | **90 dager** | Scaleway livssyklusregel | Kortere med vilje: fila inneholder passord-hasher, TOTP-hemmeligheter og audit-logg (A.2), og autentiseringsdata skal ikke ligge i to år. 90 dager dekker gjenoppretting etter et bortfall, som er formålet |
| Railway databasebackup | Styres av Railways plattformvilkår | Railway (databehandler) | Kun aktiv i den perioden abonnementet er oppgradert, ca. én måned i året |
| Mannskapsregister (`Mannskap`) | Så lenge personen er aktiv frivillig; pensjoneres (`er_aktiv=False`) ved avgang og slettes manuelt når ingen vaktposter refererer | Manuell (admin) | Berettiget interesse opphører når personen slutter; historiske vaktposter (fase 2) krever PROTECT inntil arkivering |
| Korps/kompetanse/rolle-registre (vaktliste) | Ingen fast grense | Manuell | Organisasjonsoppsett uten personopplysninger |
| **Overnattingsplasseringer (`vaktliste.Overnatting`)** | **30 dager etter natta** | Automatisk – `purge_old_logs` via Railway Cron, gjennom `core.opprydding` | Brannsikkerhet mens folk sover på stedet; formålet er uttømt etter vakta. Tretti dager gir rom til å se hva som skjedde om en natt ble en hendelse. Rommene står. Revisjonsloggens rader om hvem som endret en plassering følger revisjonsloggens frist (A.6) |
| Varsler (`Notification`) | 30 dager | Automatisk – `purge_old_logs` via Railway Cron | Rent driftsvarsel uten dokumentasjonsverdi etter vakten |
| **KO-loggen (`ko.Logglinje`)** | **730 dager (2 år)**, justerbart 30–3650 av global admin | Automatisk – `purge_old_logs` via Railway Cron, gjennom `core.opprydding` | Menneskeskrevet fritekst om det som skjer utenfor samleplass og sykestue. Samme frist som revisjonsloggen og arkivkollapsen. **Arkiveres bevisst ikke** – se merknaden under |
| Audit-logger (`AuditLog`, `LoginEvent`) | **2 år (730 dager)** | Automatisk – `purge_old_logs` via Railway Cron | Hendelsesoppklaring og revisjon. Uten journalplikt er lengre oppbevaring ikke hjemlet |
| Sesjondata | 8 timer (justerbart 1–24) | Automatisk | Begrenses til nødvendig varighet per vakt |
| Brukerkontoer | Slettes manuelt når tilgang ikke lenger er nødvendig | Manuell | Lagringsbegrensning, art. 5(1)(e) |

> **Merk om KO-loggen (17. september 2026, KO pulje 2):** Loggen er i all hovedsak
> fritekst. Opplæringen er at direkte identifiserende opplysninger – navn, adresse,
> fødselsnummer, telefon – ikke skrives i feltet, og det reduserer risikoen reelt. To ting
> følger likevel, og begge er tatt hensyn til i konstruksjonen:
>
> **«Ingen direkte identifiserende» er ikke «ikke personopplysninger».** «Mann, ca. 60,
> kollapset ved scene sør 21:14» er indirekte identifiserende på et arrangement med kjent
> deltakerliste, og det er helseopplysninger uansett. Loggen har derfor **samme
> tilgangsnivå som pasientdata**, ikke et lettere, og tidligere vakters logg krever
> `skriv_leder` – en ny operatør på vakt har ingen operativ grunn til å lese fjorårets
> linjer.
>
> **Opplæring forvitrer under press.** En travel kveld skriver noen et navn. Det finnes
> derfor **én smal, logget sletteinngang** som tømmer innholdet i en linje og lar rada stå
> («fjernet av André, 22:10»). Handlingen krever `skriv_leder` og bekreftelse, og skriver
> en auditrad – **uten** den fjernede teksten, av samme grunn som `notat` i vaktlista står
> som `(skjult)`: lå teksten i auditloggen, ville den ligget der i 730 dager og inngangen
> vært et skuespill.
>
> **Loggen arkiveres bevisst ikke.** `ArkivertPasient` og `ArkivertOppdrag` fryses med en
> SHA-signatur, og et felt som inngår i signaturen er låst i 24 måneder ved konstruksjon –
> det kan ikke fjernes uten at arkivet melder tukling. Sletteinngangen over og et signert
> arkiv utelukker hverandre, og valget falt på sletteinngangen. Samme begrunnelse som
> `Oppdrag.fritekst`, som heller ikke arkiveres.
>
> **Fristen er ikke en sletterett, og det skal stå skrevet.** KO-loggen inngår i
> modulbackupen `ko` (`backups/`, 730 dager) og i den hele fila (`full/`, 90 dager). En
> linje som fjernes med sletteinngangen, eller som slettes når fristen løper ut, ligger
> fortsatt i disse filene til bucketens livssyklusregler sletter dem. Fristen på den
> levende raden er ekte beskyttelse mot «noen leser loggen tre måneder senere»; den er
> ikke mer enn det. Samme forbehold som `docs/NOTAT_DPIA_OG_FRITEKST.md` §6 tar for
> `Oppdrag.fritekst`.
>
> **Fristen er en `AppSetting` (`ko.logg_dager`), ikke en miljøvariabel.** Endringer
> auditlogges, verdien er synlig på `/portal-admin/innstillinger/`, og web- og
> cron-tjenesten leser den samme raden. En miljøvariabel ville gitt en oppbevaringstid som
> kan endres uten spor og settes ulikt på to tjenester.

> **Merk om audit-logg-retention:** Perioden var tidligere oppgitt som 10 år, begrunnet i journalrettslige hensyn. Da journalplikten ikke gjelder for dette systemet (se A.4), er den begrunnelsen bortfalt, og perioden er satt til 2 år i tråd med det `purge_old_logs` faktisk håndhever. Kommandoen kjøres av Railway Cron.

> **Merk – verifisert i drift 23. august 2026:** `purge_old_logs` kjøres av Railway Cron (`0 0 * * SUN`) i miljøet `production`. Ved første skarpe kjøring, natt til søndag 23. august 2026, slettet jobben 3 varsler eldre enn 30 dager — nøyaktig de tre en tørrkjøring dagen før hadde identifisert. Cron-tjenestens logg viser `Slettet 3 varsler eldre enn 30 dager`, altså den skarpe varianten, ikke tørrkjøringens `Ville slettet`. Lagringstidene i tabellen over er dermed dokumentert **håndhevet i produksjon**, ikke bare konfigurert. Tilsvarende bekreftelse for `kollaps_arkiv` (`0 4 1 * *`) står igjen: jobben har ennå ingenting å kollapse, siden arkivene er fra 2026 og grensen er 24 måneder.

> **Merk om oppdragsdata (revidert 29. august 2026, fase 7 levert):** Oppdragsmodulen
> har nå samme livsløp som pasientmodulen: frysing med signatur, 24 måneders radnivå,
> deretter kollaps til aggregat. `kollaps_arkiv` går gjennom `core.arkiv`-registeret og
> dekker begge arkivene i samme kjøring, med samme sperre foran den irreversible
> slettingen: den nekter med mindre det finnes en backup av modulens arkiv tatt etter at
> arkivet ble opprettet.
>
> To ting er verdt å holde fra hverandre. «Historikk» på sentralbordet rydder bare den
> aktive tavla: raden beholdes uendret og kan hentes tilbake, så den påvirker ingen
> lagringstid. Flaten het opprinnelig «Arkiver» og er omdøpt nettopp for ikke å
> forveksles med arkiveringen dette avsnittet beskriver.
>
> **`Oppdrag.fritekst` arkiveres ikke.** Feltet er unntatt verdilogging i audit (A.6),
> og å fryse det i et arkiv med 24 måneders lagringstid ville gjort unntaket
> meningsløst. Arkivet inneholder ellers de samme kategoriene som den aktive raden:
> problemstilling, hastegrad, lokasjon, enhetsnavn og tidspunkter.
>
> Oppdragsdata **inngår nå i applikasjonens modulbackup** — modulene `oppdrag` (aktiv
> data) og `oppdrag_arkiv` (arkivet). Fram til fase 7 var Railways databasebackup eneste
> dekning, og den er kun aktiv i oppgraderingsperioden. Audit-rader for oppdrag følger
> den eksisterende 2-årsregelen — `purge_old_logs` sletter på alder, uavhengig av tabell.
>
> **Arkiveringen ligger to steder** inntil videre: pasientene arkiveres under
> `/pasienter/`, oppdragene under `/oppdrag/`. Sammenslåingen er utsatt (§12.1 i
> beslutningsnotatet), og prisen er en operativ risiko: noen kan arkivere det ene og
> glemme det andre. Den håndteres med et punkt i `docs/RUNBOOK_VAKT.md` §10a, som leses
> ved vaktslutt.

> **Merk om backup-retention (revidert 14. sep. 2026):** De to lagene styres av hver sin
> mekanisme, og det er et poeng at de ikke er samme tall.
>
> **På Railway-volumet** er oppryddingen **antallsbasert**: `core.Backupplan.behold`,
> standard 50, satt per modul. Spørsmålet der er «har jeg nok kopier til å gå tilbake
> forbi feilen», ikke «hvor gammel er den eldste».
>
> **Offsite hos Scaleway** er den **tidsbasert**, og håndheves av bucketens
> livssyklusregler — ikke av portalen. Det er ikke en forenkling: IAM-nøkkelen portalen
> bruker har *ikke* sletterett, nettopp for at en kompromittert portal ikke skal kunne
> slette sikkerhetskopiene. Konsekvensen er at fristen bare finnes ett sted, i bucketens
> oppsett, og at en feilskrevet regel er en oppbevaringstid som stille blir uendelig.
> Portalen leser derfor reglene *tilbake* fra Scaleway og viser avvik på
> `/portal-admin/backup/`.
>
> *Historikk:* dokumentet oppga tidligere «72 timer, deretter automatisk slettet»
> (`RETENTION_HOURS`), som aldri stemte med implementasjonen, og deretter
> `ModuleBackupConfig.max_backups`. Begge er nå slettet fra koden — `RETENTION_HOURS` og
> `patients.BackupConfig` 14. sep. 2026.

> **Merk om backup-innhold:** Applikasjonens backup er delt i fire uavhengige moduler:
>
> - **`patients`** — aktiv vaktdata (pasienter, førstehjelpere, helsepersonell, innstillinger)
> - **`arkiv`** — vaktarkivet (`VaktArkiv` + `ArkivertPasient` samlet)
> - **`oppdrag`** — aktiv oppdragsdata (oppdrag, statusmeldinger, enhetsbytter, enheter, lokasjoner)
> - **`oppdrag_arkiv`** — oppdragsarkivet (`OppdragArkiv` + `ArkivertOppdrag` samlet)
>
> En gjenoppretting av den ene rører aldri den andre. Arkivet har egen modul fordi Railways databasebackup kun er aktiv den måneden abonnementet er oppgradert; resten av året er dette den eneste dekningen arkivet har.
>
> Ingen av modulene inneholder passord-hasher, audit-logg, sesjoner eller `LoginEvent`. En restore påvirker dermed ikke brukerkontoer eller logger. Dette gjelder **ikke** Railways databasebackup, som omfatter hele databasen — se A.2.
>
> I arkiv-backupene utelates referansene `VaktArkiv.importert_av` og `OppdragArkiv.importert_av` bevisst. De peker på en brukerkonto som ikke er del av dumpen, og ville gjort gjenoppretting umulig dersom kontoen var slettet. Brukernavnet er uansett bevart frosset i `importert_av_navn`. Av samme grunn utelates `meldt_av`, `opprettet_av`, `historikk_av` og `byttet_av` i oppdragsbackupen.

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
| Tilgangskontroll per modul | Tilgang gis som rader, ikke som roller: `ModulTilgang(bruker, modul_slug, nivaa)`. **Fravær av rad er ingen tilgang** — det finnes ingen «ingen»-verdi å lagre, så en konto uten rader ser ingenting. Nivåene er en ordnet stige, og hver modul deklarerer hvilke av dem den bruker (se tabell nedenfor). `CustomUser.role` er kontotype (`admin`/`bruker`), ikke tilgangsnivå |
| Hvert endepunkt er gatet, og det håndheves | `patients/tests_modul_dekorator.py` går gjennom `urlpatterns` og krever at hvert view under en modul er dekorert; unntak må stå i lista der med begrunnelse. Risikoen ved dekoratør framfor middleware er en glemt dekoratør, og en manuell gjennomgang holder bare til neste endepunkt. Ukjent nivånavn i en dekoratør gir **False**, ikke True — en skrivefeil skal stenge døra |
| Grensesnittet gates på samme data | Knapper vises ut fra brukerens faktiske nivåer, ikke ut fra kontotypen. En knapp som fører til 403 er verre enn ingen knapp, fordi den inviterer til forsøk |
| CSRF-beskyttelse | Django CSRF-middleware aktivert på alle tilstandsendrende forespørsler |
| Content-Security-Policy | Aktiv via `SecurityHeadersMiddleware`; begrenser hvilke ressurser nettleseren kan laste. `script-src` bruker nonce per request og tillater ikke `unsafe-inline` — inline skript kan dermed ikke injiseres og kjøres. `style-src` tillater fortsatt `unsafe-inline` (kjent avvik, står som åpent punkt i `TODO.md`) |
| Sikre informasjonskapsler | Cookies satt med `Secure`, `HttpOnly` og `SameSite=Lax`-flagg |
| Clickjacking-beskyttelse | `X-Frame-Options: DENY` på alle svar |
| Innholdstype-beskyttelse | `X-Content-Type-Options: nosniff` |
| Referrer-policy | `Referrer-Policy: same-origin` |
| Permissions-policy | `camera=(), microphone=(), geolocation=()` |
| XSS-beskyttelse | Auto-escape i Djangos template-motor. I JavaScript escapes brukerdata manuelt: `escapeHtml()`/`_escHtml` i pasientskjemaet og arkivvisningen, `escHtmlValue()` i statistikk-tabellene. Markup som koden bygger selv (signifikans-merker, prosentbjelker) må merkes eksplisitt med `trustedHtml()` for å slippe gjennom, slik at unntakene er synlige per celle. `patients/tests_xss_stats.py` kjører tabell-byggerne i node og krever i tillegg at hver interpolasjon i dem er escapet eller står på en gjennomgått unntaksliste. I andre lag valideres alle kliniske felt mot en serverside-whitelist (`patients/choices.py`) før lagring — også ved offline-import |
| SQL-injection-beskyttelse | Django ORM benyttes; ingen rå SQL-spørringer |
| Audit-logging | Alle pasient-endringer logges på felt-nivå (bruker, IP, tidspunkt, tabell, felt, gammel/ny verdi). Feltlista utledes fra modellen selv, slik at et nytt felt ikke kan falle utenfor loggen stilltiende; en test feiler hvis et felt verken spores eller er eksplisitt unntatt. Innloggingsforsøk logges med IP og user-agent (LoginEvent). Backup-hendelser (opprettelse, gjenoppretting, sletting) logges — gjenopprettingen av `restore_backup` selv, slik at både nettleseren og kommandolinja etterlater nøyaktig én rad med hvem og hvorfra. «Nedlasting» sto i denne lista fram til 14. sep. 2026; funksjonen finnes ikke og skal ikke finnes. **Portalens egne innstillinger logges fra samme dato** (`core/signals.py`): endring av sesjonstimeout, e-postmottakere og av/på-bryteren for en hel modul. Tellere og cron-status er unntatt — loggen skal si hva et menneske bestemte, ikke hva maskinen talte |
| Backup og gjenoppretting | Automatisk backup kjøres av en **klokketråd i web-prosessen** (`core/backup/klokke.py`), ikke av en cron-tjeneste: Railway-volumet kan bare henge på én tjeneste, og en cron-jobb ville skrevet fila til sitt eget flyktige filsystem og forsvunnet med den. Filene lagres gzip-komprimert på `/data/backups`. Opprydding på volumet er antallsbasert (`core.Backupplan.behold`, standard 50 per modul); offsite styres av bucketens livssyklusregler (A.9). Pre-restore-øyeblikksbilde lages før hver gjenoppretting |
| Kryptering av sikkerhetskopier ut av Railway | Hver fil **komprimeres først og krypteres så** (AES-256-GCM, format `SPBK1` + nonce + chiffertekst) før den forlater Railway. Rekkefølgen er ikke vilkårlig: chiffertekst lar seg ikke komprimere. Nøkkelen (`OFFSITE_BACKUP_KEY`) finnes i Railway og i en passordbehandler utenfor — **ikke** hos Scaleway, som derfor bare ser chiffertekst |
| Ingen nedlasting av sikkerhetskopier | Portalen har **ingen nedlastingsfunksjon** for backupfiler, heller ikke for modulfilene. En `.json.gz` med hele pasientregisteret i en nedlastingsmappe er en spredning utenfor portalens kontroll, og den hele fila bærer i tillegg passord-hasher og TOTP-hemmeligheter. Kontroll av innhold skjer med `verifiser_backup`, som laster filene inn i en flyktig engangsbase uten å flytte dem |
| Ingen eksterne skript- eller stilkilder | `script-src` er `'self'` + nonce, **uten vertsnavn**. Bootstrap, ikonene, Tabulator og Chart.js serveres fra portalen selv (`static/vendor/`), ikke fra CDN: med en CDN-vert i lista kunne én HTML-injeksjon lastet en vilkårlig pakke, nonce eller ei. En test håndhever at ingen mal peker på et CDN |
| Låste avhengigheter | `requirements.txt` er generert med `pip-compile --generate-hashes`, og det er den som installeres i produksjon. Uten hasher kan en kompromittert pakke på PyPI bytte innhold under samme versjonsnummer |
| Én kilde for klient-IP | `core/klientip.py` er det eneste stedet IP-en leses: siste ledd i `X-Forwarded-For` — det Railway la til — validert, ellers `REMOTE_ADDR`. Første ledd er klientens egen påstand. Innloggingslogg, audit, arkiv og rate-limit-bøtter bruker alle denne |
| Sletting av lokale data ved utlogging | «Logg ut» sender `Clear-Site-Data: "cache", "storage"`. På en delt drifts-PC med offline-vaktliste ryddes Cache Storage, localStorage og service workeren i én operasjon, slik at neste bruker ikke arver forrige brukers lokale kopi av mannskapslista |
| Ingen lokal kopi eldre enn ett døgn | Service workeren for offline drift nekter å servere en datakopi som er mer enn 24 timer gammel. En vakt varer ikke lenger, og en kopi av mannskapsregisteret skal ikke ligge klar for den som åpner siden uker senere |
| Generisk feilhåndtering | Restore-feil gir generisk feilmelding til bruker – interne stacktraces lekkes ikke |
| Cache-isolasjon | I **lavkostnad-modus** brukes Djangos `LocMemCache` (lokal til hver Gunicorn-worker), og ingen cache-data forlater prosessen. I **vakt-modus** benytter Redis key-prefiks `pasientregistrering:` og dedikert tjeneste i Railway-prosjektet, med tilgang kun via internt Railway-nettverk (ikke offentlig). Ingen pasient-PII lagres i cachen i noen modus — kun aggregater, rate-limit-tellere og metrikk-samples uten PII |
| Auto-fallback ved Redis-utfall | Hvis Redis blir utilgjengelig under vakt-modus, fortsetter applikasjonen å fungere. Metrikk-aggregeringen (#15) skriver lokalt først (per-prosess `deque`) og supplerer Redis kun best-effort med kort socket-timeout (2 s); ved feil faller `snapshot()` automatisk tilbake til lokal kilde. Cache-helsesjekken oppdager utilgjengelig Redis og rapporterer i admin-dashbordet uten å eksponere internt feil-traceback |
| Sanering av credentials i feilmeldinger | Helperen `_scrub_secrets()` fjerner `user:password@` fra eventuelle URL-strenger som havner i feilmeldinger fra cache-/database-driverne, slik at admin-status-responsen og logger ikke kan eksponere Redis- eller Postgres-passord |
| Dataminimering | Ingen direkte identifikatorer (navn, personnummer) lagres for pasienter |
| Validering av verdimengde | Kliniske felt valideres serverside mot fast hviteliste (`patients/choices.py`) ved både opprettelse og oppdatering. Hindrer at fritekst — f.eks. et navn — lagres i felt som skal være ikke-identifiserende. Automatisk test hindrer at hviteliste og skjema kommer i utakt |
| Hard-fail på manglende `SECRET_KEY` | Applikasjonen nekter å starte med `DEBUG=False` hvis `SECRET_KEY` mangler eller er satt til en kjent eksempelverdi. Hindrer at produksjon kjører på en offentlig kjent nøkkel, som ville latt sesjonscookies og MFA trust-cookies forfalskes |
| MFA-gjenoppretting | Admin kan nullstille MFA for bruker; hendelsen loggføres som `mfa_reset_by_admin` |

**Tilgangsmodellen (revidert 14. sep. 2026).**

> Dette dokumentet beskrev fram til nå fem roller — `read_only`, `read_write`,
> `lead_view`, `lead`, `admin` — med en matrise over hva hver av dem kunne. **De fire
> første finnes ikke**, og ble fjernet i deploy 2 sammen med `has_role_at_least`,
> `role_required`, `write_required` og `stats_required`. Beskrivelsen var altså ikke bare
> foreldet: den dokumenterte en annen tilgangsmekanisme enn den som håndhever tilgangen.

**Tre kategorier, ikke én** (se `docs/BESLUTNING_ROLLEMODELLEN.md`):

1. **Global admin** (`role == 'admin'`) — brukeradmin, backup, moduloppsett, audit, arkiv
   og alt irreversibelt. Står utenfor modulaksen og trenger ingen rader
2. **Modulbasert** — `ModulTilgang(bruker, modul_slug, nivaa)`, én rad per modul
3. **Globalt uten admin** — innlogging, min profil, passordbytte, MFA

**Nivåstigen:**

| Nivå | Betyr | Personvernkonsekvens |
|---|---|---|
| `les` | Ser modulens data. I vaktlista: **bare sitt eget korps** | Minste tilgang som gir innsyn |
| `les_alle` | Vaktlista: ser alle korps. Deklareres kun der | Utvider innsyn på tvers av korps |
| `skriv_handling` | Navngitte overganger (stemplinger). **Leser ikke request-kroppen** | Kan ikke endre vilkårlige felter, bare utløse definerte tilstandsskift |
| `skriv_full` | Kan redigere felter | |
| `skriv_leder` | Kan sette opp — oppretter og fjerner det de andre redigerer | |

**Hver modul deklarerer hvilke nivåer som gjelder for den**, og gir dem sin egen etikett:
`skriv_handling` er «stempling» i oppdrag og «fører sitt eget korps» i vaktlista. Uten
etiketten deles nivået ut i god tro med feil modul i hodet — og det er en tilgangsfeil,
ikke en tekstfeil.

| Modul | Nivåer den tilbyr |
|---|---|
| `patients` | `les`, `skriv_full` |
| `oppdrag` | `les`, `skriv_handling`, `skriv_full`, `skriv_leder` |
| `vaktliste` | `les`, `les_alle`, `skriv_handling`, `skriv_full`, `skriv_leder` |
| `statistikk` | `les` |
| `core`, `accounts` | `les`, `skriv_full` |

**Statistikkmodulen komponerer tilgang, den eier den ikke.** Den viser kun kilder
brukeren har minst `les` på i *kildemodulen* — ellers ville aggregatene gitt avledet
innsyn i data brukeren ikke har tilgang til. Arkiv-statistikken har i tillegg en egen
gate på global admin.

### Organisatoriske tiltak

| Tiltak | Beskrivelse |
|---|---|
| Tilgangsstyring etter behov | Tilgang deles ut per modul og nivå, ikke som en samlet rolle (se tilgangsmodellen ovenfor). En ny konto starter uten noen tilgang, og hver utvidelse er en bevisst handling som logges |
| Databehandleravtale | DPA signert med Railway; EU-region bekreftet |
| Behandlingsprotokoll | Dette dokumentet vedlikeholdes og oppdateres ved endringer |
| Tilbakekalling av tilgang | Brukerkontoer deaktiveres umiddelbart når tilgang ikke lenger er nødvendig |
| Sikkerhetshendelsesprosedyre | Skriftlig prosedyre for oppdagelse, vurdering og melding (se A.12) |
| Privat kodearkiv | Kildekode lagres i privat GitHub-repositorium |

---

## A.11 Reserve ved bortfall av portalen og personvern

Den gamle offline-modusen (lokal SQLite-kopi av pasientdata på en laptop) ble lagt ned
13. sep. 2026. Reserven er nå avgrenset til **vaktlista**:

| Aspekt | Beskrivelse |
|---|---|
| Vaktlista som fil på e-post | Én HTML-fil med navn, korps, rolle, skift, telefon og ISSI — ikke e-post, notat eller merknad. Fra 25. sep. 2026 også **brannlista**: hvem som sover i hvilket rom per natt, med telefon. Sendes ukryptert til en fast mottakerliste satt av global admin, ved «Sett i drift», på knapp og på intervall mens lista er i drift. Hver utsending logges (hvem, når, hvilke adresser). Fila sier selv «slett etter vakta». Vurdering: alminnelige personopplysninger, se `docs/BESLUTNING_VAKTLISTE.md` §12 |
| Offline drift på drifts-PC-en | Nettleseren holder siden og siste vaktliste lokalt (service worker). Møtt/av vakt legges i kø når serveren ikke svarer og sendes når den svarer igjen. Kopien inneholder de samme opplysningene som fila, i nettleserens cache på den PC-en |
| Pasientdata | Ingen lokal kopi. Ved bortfall føres pasienter på papir/Excel etter organisasjonens rutine |

**To tekniske begrensninger på den lokale kopien** (13. sep. 2026), som er grunnen til at
risikoen under er vurdert som håndterbar og ikke bare akseptert:

| Tiltak | Virkning |
|---|---|
| **Ingen datakopi eldre enn 24 timer** | Service workeren nekter å servere en lagret liste som er mer enn ett døgn gammel, og sletter den i stedet. En vakt varer ikke lenger, og et mannskapsregister skal ikke ligge klart for den som åpner siden uker senere |
| **«Logg ut» rydder maskinen** | Utlogging sender `Clear-Site-Data: "cache", "storage"`, som tømmer Cache Storage, localStorage og service workeren i én operasjon. På en delt drifts-PC arver ikke neste bruker forrige brukers lokale kopi |

Workeren lagrer dessuten **aldri en omdirigering**: en utløpt sesjon gir innloggingssiden,
og den skal ikke bli stående som «vaktlista». Og den rører ingen POST — stemplinger går i
kø i klienten, ikke gjennom cachen.

> **Personvernrisiko:** fila og nettleserkopien inneholder personopplysninger om mannskapet.
> Mottakere skal slette fila etter vakta, og drifts-PC-en skal behandles med samme krav til
> informasjonssikkerhet som produksjonssystemet. Tap av enheten håndteres etter A.12.
>
> **E-postfila er det svakeste leddet, og det er en bevisst avveining.** Den sendes
> ukryptert, og portalen har ingen kontroll over mottakerens innboks eller over hvor lenge
> den blir liggende. Alternativet — ingen reserve — ble vurdert som verre: uten lista på
> papir eller skjerm vet ingen hvem som er på vakt når serveren er nede, og det er en
> beredskapssvikt. Risikoen begrenses ved at mottakerlista settes av global admin og ikke
> av den enkelte, at hver utsending logges med adresser og tidspunkt, at fila ikke
> inneholder e-post, notat eller merknad, og at den selv sier at den skal slettes.

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
- Fritekstfeltet i oppdragsmodulen er portalens første frie tekstfelt. En operatør *kan*
  skrive personopplysninger der, også direkte identifikatorer — feltet finnes fordi
  enheten trenger operativ kontekst som ikke lar seg uttrykke i faste lister. Tiltakene
  (unntak fra verdilogging i audit, server-side skjuling mot enhetskontoer etter
  avslutning, veiledning i skjemaet) er beskrevet i A.6. Restrisiko: selve feltverdien
  står i oppdragstabellen til oppdraget slettes eller arkiveres.
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
| Backup ekskluderer sensitive data | *(Tiltaket slik det var i april 2026: `BACKUP_APPS` var satt til `['patients']`, og backup inkluderte ikke `CustomUser`, `AuditLog`, `LoginEvent` eller sesjoner.)* **Overtatt av senere arbeid — se A.2 og A.9.** Innstillingen er fjernet, og portalen tar nå både seks modulfiler og én hel databasebackup. Den hele fila **inneholder** brukere, passord-hasher, MFA-hemmeligheter og audit-logg, med vilje: den må være selvbærende for å kunne gjenopprettes i en tom base. Beskyttelsen er flyttet fra *utelatelse* til *kryptering* (AES-256-GCM med en nøkkel verken Railway eller Scaleway har), kortere frist (90 dager mot 730) og en lagringsnøkkel uten sletterett |
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

> **Om sletting av brukerkontoer:** En bruker som har arkivert en vakt kan slettes. Referansen fra `VaktArkiv` nulles ut, mens brukernavnet beholdes frosset i `importert_av_navn`. Arkivet viser dermed fortsatt hvem som arkiverte vakten, uten at kontoen må bevares. Dette er samme mønster som `forstehjelper_navn` på arkiverte pasienter, og er nødvendig for at sletterett etter art. 17 ikke skal være blokkert på databasenivå.
>
> Det innebærer at brukernavnet til en frivillig består i arkivet også etter at kontoen er slettet. Opplysningen er nødvendig for at dokumentasjonen av vakten skal være etterrettelig, og de registrerte informeres om det i B.8.

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

> **Om utrykning med bil eller beredskapsambulanse:** Sendes en enhet ut til deg,
> registreres selve oppdraget — hendelsestype fra fast liste, hastegrad, sted på
> arrangementet og tidspunktene for enhetens statusmeldinger. Oppdraget registreres
> **helt uten identifikator**: ikke noe pasientnummer, ikke noe navn, og ingen kobling
> til pasienttavlen. Et eventuelt fritekstfelt med beskjed til mannskapet skjules for
> enheten når oppdraget er avsluttet, og innholdet lagres aldri i endringsloggen.

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

Når en vakt arkiveres, **fryses navnet ditt** — både på de pasientene du hadde ansvar for, og på selve arkivet dersom det var du som arkiverte vakten. Det gjøres med vilje: arkivet skal vise hvem som faktisk var på jobb den kvelden, også flere år etterpå. Sletter du brukerkontoen din senere, blir navnet stående i arkivet.

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
- [ ] Verifiser at alle aktive brukere har riktig tilgang: kontotype (`admin`/`bruker`) **og** modultilgangene under «Brukere» i portaladmin. Gjennomgangen gjelder radene, ikke kontotypen — en konto uten rader ser ingenting, og det er den trygge tilstanden
- [ ] Deaktiver eller slett brukerkontoer som ikke skal ha tilgang til dette arrangementet
- [ ] Endre aktivt år / event-navn i appinnstillinger (AppSetting)
- [ ] Verifiser at MFA er aktivert og satt opp for alle med kontotype `admin`, og for alle med `skriv_leder` på en modul
- [ ] Test innlogging med minst én bruker per tilgangsnivå som faktisk er i bruk denne vakta
- [ ] Verifiser at brute-force-lås og rate-limiting fungerer (5 feilede pålogginger gir blokkering i 15 min)
- [ ] Bekreft at sesjonstimeout er satt korrekt for vakten
- [ ] Sjekk at Railway-tjenesten kjører og at siste backup er vellykket
- [ ] Sjekk at mottakerlista for vaktlista på e-post er riktig, og at drifts-PC-en viser «Klar for offline»

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

*Dokument: PERSONVERN_DOKUMENTASJON.md – versjon 1.13 – sist oppdatert 26. september 2026*

**Endringslogg:**

- **v1.13 (26.09.2026):** **A.6, overnatting:** skiftdetaljene («Ambulanse 2, 22:00–06:00»)
  følger nå telefonen og vises bare for eget korps eller for dem som ser alle korps. En ren
  lesetilgang fikk dem for alle korps via overnattingsfanen, selv om vaktlista ellers
  filtrerer de samme skiftene bort. Alle ser fortsatt *at* en person er på vakt.

- **v1.12 (25.09.2026):** **A.6:** ny underseksjon for overnatting i vaktlista — hvem
  som sover i hvilket rom per natt, for brannsikkerheten. **A.9:** plasseringene slettes
  30 dager etter natta av `purge_old_logs`, uten å skrive navnene inn i revisjonsloggen.
  Vaktlista som fil på e-post inneholder nå også brannlista. Versjonshodet sto på 1.10
  mens endringsloggen var på 1.11; rettet.

- **v1.11 (14.09.2026):** **Gjennomgang mot faktisk kode, del av dokumentrunden.** Tre
  materielle rettelser og ett dokumentert hull.

  **A.10 beskrev en tilgangsmodell som ikke finnes.** Rollematrisen listet `read_only`,
  `read_write`, `lead_view`, `lead` og `admin` med hver sine rettigheter. **De fire
  første ble fjernet i deploy 2**, sammen med `has_role_at_least`, `role_required`,
  `write_required` og `stats_required`. Protokollen dokumenterte altså ikke en foreldet
  utgave av mekanismen, men en *annen* mekanisme enn den som faktisk håndhever tilgang.
  Erstattet med den ekte modellen: `ModulTilgang(bruker, modul_slug, nivaa)`, fem nivåer
  i en ordnet stige, og hver modul deklarerer hvilke den bruker. Samme feil rettet i A.6
  (`role` er kontotype, ikke tilgangsnivå — `admin` eller `bruker`) og i sjekklista C.1.

  **A.2: bucketen hos Scaleway inneholder nå hele databasen, ikke bare modulenes data.**
  Den hele fila bærer brukerkontoer med passord-hasher, TOTP-hemmeligheter,
  innloggingshendelser og audit-logg — den må være selvbærende for å kunne gjenopprettes
  i en tom base. Utvidelsen er ført inn med hva som ligger under hvert prefiks, og med
  de tre tiltakene risikoen håndteres med: kryptering med en nøkkel Scaleway ikke har,
  **90 dagers** frist mot modulfilenes 730, og en IAM-nøkkel uten sletterett.

  **A.9: retensjonstabellen viste til mekanismer som er slettet.** `RETENTION_HOURS` og
  `ModuleBackupConfig.max_backups` er borte fra koden (14. sep. 2026); oppryddingen på
  volumet styres av `core.Backupplan.behold`. Nye rader for begge offsite-fristene, og
  en merknad om at de håndheves av bucketens livssyklusregler og ikke av portalen —
  IAM-nøkkelen har ikke sletterett, så fristen finnes bare ett sted.

  **A.10 ellers:** krypteringen av sikkerhetskopier, at det ikke finnes noen
  nedlastingsfunksjon (og at «nedlasting» sto i audit-lista for en funksjon som ikke
  finnes), at ingen skript lastes fra CDN, hash-låste avhengigheter, én kilde for
  klient-IP, `Clear-Site-Data` ved utlogging, og 24-timersgrensen på den lokale kopien.
  **A.11:** de to tekniske begrensningene på offline-kopien, og en åpen avveining om
  at e-postfila er det svakeste leddet — bevisst valgt framfor ingen reserve.

  **Hullet:** dette dokumentets endringslogg hoppet fra 29. august til i dag, mens
  Scaleway-avsnittet ble skrevet 13. september. Versjonshodet sto dessuten på «1.8» mens
  siste oppføring var v1.10. Begge rettet; endringen fra 13. september er beskrevet
  under A.2 og i punktet over, ikke som en egen etterdatert oppføring.
- **v1.10 (29.08.2026):** **A.6:** ny seksjon for mannskapsdata — vaktlistemodulens
  fase 1 fører et globalt register over egne frivillige (navn, korps, kompetanser,
  telefon, valgfri kontokobling), med berettiget interesse som grunnlag. Kostbehov/
  matallergi lagres **bevisst ikke** (art. 9 — besluttet holdt utenfor portalen), og
  `notat` er unntatt verdilogging i audit fra første lagring, etter mønster av
  `Oppdrag.fritekst`. **A.9:** rader for mannskapsregisteret (manuell rydding,
  pensjonering som normal vei ut) og registrene.
- **v1.9 (29.08.2026):** **A.9:** oppdragsmodulens arkivering er levert (fase 7), og
  raden merknaden ba om å revidere er revidert. Nye rader for `ArkivertOppdrag` (24
  måneder, deretter kollaps), `OppdragArkiv` (aggregat uten radnivå) og
  backup-modulene `oppdrag` og `oppdrag_arkiv` — modulen var uten applikasjonsbackup
  fram til nå. Presisert at `Oppdrag.fritekst` **ikke** arkiveres: feltet er unntatt
  verdilogging i audit, og et arkiv med 24 måneders lagringstid ville uthult unntaket.
  Notert at arkiveringen fortsatt ligger to steder, og at den operative risikoen
  håndteres i runbooken §10a.
- **v1.8 (29.08.2026):** **A.6:** to nye felt i oppdragstabellen — `oppdragsnummer`
  (løpenummer per år for gjenfinning; identifiserer oppdraget, ikke personen, og lar seg
  ikke koble til pasientnummer) og `arkivert_at`/`arkivert_av`. **A.9:** presisert at
  «Arkiver»-knappen rydder den aktive tavla og ikke er arkivering i `core.arkiv`-forstand
  — raden beholdes uendret, handlingen er reversibel, og ingen lagringstid påvirkes.
  Skillet er ført inn fordi ordet «arkiv» ellers ville lest som frysingen A.6 beskriver
  for vaktarkivet.
- **v1.7 (29.08.2026):** **Oppdragsmodulen dokumentert, før produksjonssetting.** Ny
  seksjon i A.6 (kategorier, hjemler og fritekst-tiltakene: unntak fra verdilogging i
  audit, server-side skjuling mot enhetskontoer, veiledning i skjemaet), ny rad og
  merknad i A.9 (ingen automatisk sletting ennå — arkiveringsfasen skal revidere raden;
  oppdragsdata står utenfor applikasjonens modulbackup inntil en handler registreres),
  ny sårbarhet i A.12 (fritekst som portalens første frie tekstfelt, med restrisiko),
  unntaket ført inn i A.6s audit-tabell, og en merknad i B.2 om at utrykningsoppdrag
  registreres uten identifikator. Dokumentet er oppdatert som del av modulens fase 2 —
  gjennomført **før** fritekstfeltet når produksjon, slik at verdilogging aldri har
  vært aktiv for det.
- **v1.6 (23.08.2026):** **A.9:** lagringstidene er ikke lenger bare konfigurert, men verifisert håndhevet i produksjon. `purge_old_logs` kjørte som Railway Cron natt til søndag 23. august og slettet 3 varsler eldre enn 30 dager. Ny merknad under retensjonstabellen dokumenterer beviset og skiller det fra tørrkjøringen dagen før. Ingen lagringstid er endret — kun grunnlaget for påstanden om at de etterleves. Merknaden noterer også at tilsvarende bekreftelse for `kollaps_arkiv` fortsatt står igjen.
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
