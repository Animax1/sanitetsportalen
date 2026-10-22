# Avvikslogg — Sanitetsportalen og kart.sanitet.net

**Behandlingsansvarlig:** Kverneland Røde Kors
**Databehandler og systemansvarlig:** André Eritsland

Loggen fører sikkerhetsavvik og mulige avvik, også de som ikke meldes til Datatilsynet —
GDPR art. 33(5) krever at *alle* brudd på personopplysningssikkerheten dokumenteres, med
fakta, virkninger og tiltak. Som databehandler er systemansvarliges plikt etter art. 33(2) å
**varsle korpset uten ugrunnet opphold**. Det er korpset som vurderer og eventuelt melder
til Datatilsynet innen 72 timer. Vurderingene under er derfor **anbefalinger til korpset**,
ikke avgjørelser.

> **Merk:** Databehandleravtalen mellom korpset og systemansvarlig er ikke dokumentert
> (`docs/PERSONVERN_DOKUMENTASJON.md` A.1). Den regulerer nettopp hvordan et slikt varsel skal
> gis, og bør på plass.

---

## 2026-10-22 — Railway: miljøvariabler kan være dekryptert av en tredjepart

**Status:** Åpen — tiltak gjenstår til Railway åpner for deploy igjen.

### Hva skjedde

Railway (driftsleverandøren, underdatabehandler) varslet på e-post om morgenen 22. okt. 2026
at en uautorisert tredjepart kan ha fått tilgang til krypterte miljøvariabler på plattformen,
og for noen av dem det dekrypterte innholdet. Railway ber alle kunder trekke tilbake og utstede
alle nøkler på nytt. Bygg og deploy er stanset på hele plattformen inntil videre.

Det er ikke kjent at akkurat våre variabler er blant dem som ble dekryptert. Avviket føres
fordi variablene **kan** være kjent av en uvedkommende.

### Hva var eksponert

Miljøvariablene til portalen (`portal.sanitet.net`, `testportal.sanitet.net`) og kartet:

| Nøkkel | Hva den åpner for |
|---|---|
| `DATABASE_URL` / Postgres-passord | Hele databasen — men bare hvis basen kan nås. Se tiltak 1 |
| `SECRET_KEY` (portal), `DJANGO_SECRET_KEY` (kart) | Forfalske sesjoner, signerte lenker og MFA-tillit |
| `OFFSITE_S3_ACCESS_KEY` / `_SECRET_KEY` | Backupbøtta hos Scaleway |
| `OFFSITE_BACKUP_KEY` | Dekryptere backupfilene, *om* man også har filene |
| `AHASEND_*` | Sende e-post i portalens navn |
| `KART_HMAC_NOKKEL`, `KART_INNLOGGING_NOKKEL`, `PORTAL_*`-nøklene i kartet | Sende posisjoner og innloggingsbilletter mellom portal og kart |
| `MAPTILER_NOKKEL` | Kartfliser på vår regning |

### Hvilke personopplysninger det gjelder

- **I databasen nå:** kontoer (navn, brukernavn, e-post, passordhasher, TOTP-hemmeligheter),
  audit- og innloggingslogg. Bare utviklerkontoer bruker portalen i dag. Pasientdata fra
  forrige vakt er gjort om til statistikk og finnes ikke lenger som rader.
- **I backupene hos Scaleway:** krypterte filer, inntil 730 dager tilbake. Eldre filer kan
  inneholde pasientregistreringer fra tidligere vakter.

### Undersøkelser

- **Scaleway-loggene** (Cockpit, `resource_type="object_storage_bucket"`) gjennomgått
  22. okt. 2026, så langt de går tilbake (7 dager):
  - **19. okt. 2026 05:41 UTC:** `ListObjects` mot backupbøtta fra `104.199.26.126`,
    **avvist (403)**. Den lekkede nøkkelen hadde listerett; et forsøk med den ville lyktes.
    Forsøket kom altså ikke med vår nøkkel, og ga ingenting.
  - Ingen vellykket listing fra andre enn systemansvarlig (`79.161.43.76`).
  - **Operasjoner på enkeltobjekter logges ikke** av Scaleway: en testfil
    (`loggtest.txt`) som ble lastet opp, lest og slettet 22. okt. dukket aldri opp. At ingen
    har *lastet ned* en backup kan derfor ikke bevises fra loggen. Filnavnene er tidsstemplet
    til sekundet og kan ikke gjettes uten en listing — og ingen listing lyktes for andre.
- **Rettighetene til S3-nøkkelen** var bredere enn planen: IAM-applikasjonen
  `sanitetsportalen-backup` hadde `ObjectStorageFullAccess` i tillegg til BucketsRead,
  ObjectsRead og ObjectsWrite. `docs/RUNBOOK_VAKT.md` sier skriv + les, **uten** sletterett.
  Livssyklusreglene og filene er kontrollert og urørte.
- **Utgående trafikk** fra prod og staging i Railway: normal.
- **GitHub** (innlogging, nøkler, tilganger): gjennomgått, ingenting uvanlig.

### Tiltak gjort (22. okt. 2026)

1. Offentlig tilgang til Postgres stengt i prod og staging — basen nås nå bare over
   Railways interne nett, så et lekket passord alene åpner ingenting.
2. Scaleway S3-nøkkelen trukket tilbake og erstattet.
3. `ObjectStorageFullAccess` fjernet fra `sanitetsportalen-backup`.
4. AhaSend-nøkkelen trukket tilbake og erstattet.
5. Nye verdier generert for resten — lagret i passordbehandleren, ikke i Railway ennå.
6. **Databasepassordet i kart.sanitet.net prod rotert** (ca. 11:40 UTC). Variabelen
   `POSTGRES_PASSWORD` ble endret først, og kartet krasjet på `password authentication failed`
   til passordet i basen ble satt til samme verdi. Se lærdommen under.

### Tiltak som gjenstår (blokkert av Railways deploystans)

En endret variabel tas først i bruk ved neste deploy. I denne rekkefølgen:

1. Prøv en variabelendring på staging.
2. `SECRET_KEY` og `DJANGO_SECRET_KEY` — alle logges ut.
3. Nøklene mellom portal og kart, med kort `_FORRIGE`-vindu i kartet.
4. Postgres-passordet (`ALTER USER`, så variablene, så deploy).
5. `OFFSITE_BACKUP_KEY`, så `backup_kjor` og `verifiser_backup`. **Den gamle nøkkelen beholdes i
   passordbehandleren** — den trengs for å lese backupene som alt ligger der.
6. MapTiler.
7. Staging.
8. **Kreve passordbytte for alle personlige kontoer** når `SECRET_KEY` er byttet
   («Krev passordbytte for alle» på `/admin/brukere/`, fra 22. okt. 2026).

### Vurdering — anbefaling til Kverneland Røde Kors

Sannsynligheten for at personopplysninger er kommet på avveie vurderes som **svært lav**:
databasen kunne ikke nås utenfra etter tiltak 1 og bærer i dag ingen pasientdata;
backupfilene er krypterte, ingen listing av dem lyktes for andre, og det eneste forsøket i
loggen ble avvist. Anbefalingen er å **dokumentere avviket og ikke melde det til
Datatilsynet**, med forbehold om at Railway ikke melder om mer. Avgjørelsen er korpsets.

- [ ] Korpset varslet (dato, hvem):
- [ ] Korpsets beslutning om melding til Datatilsynet (dato, hvem):

### Lærdom

- **På Railway endrer `POSTGRES_PASSWORD` ikke passordet i basen** — variabelen leses bare når
  basen opprettes. Endres den alene, får appen det nye passordet gjennom
  `${{Postgres.DATABASE_URL}}` mens basen har det gamle, og neste deploy eller restart krasjer
  (kartet, 22. okt.). Rekkefølgen er: ny verdi i variabelen, så samme verdi i basen fra
  Postgres-tjenestens konsoll — uten å lime inn passordet:
  `printf '%s\n' "SET log_statement = 'none';" '\getenv pw POSTGRES_PASSWORD' "ALTER USER postgres WITH PASSWORD :'pw';" | psql -h /var/run/postgresql -U postgres`,
  så `psql -c "select 1;"` for å bekrefte, så **Redeploy** av appen. Innliming i `\password`
  bommet første gang — et usynlig tegn fulgte med.
- **Restart bruker variablene deployment-en ble laget med; Redeploy henter de nye.**

- **Rettighetene glir uten at noe sier fra.** S3-nøkkelen hadde mer enn planen sa, og ingen
  så det før en hendelse. Kontroll av nøkkelens rettigheter bør inn i `/admin/backup/`.
- **Scaleway beholder loggene i 7 dager.** Skjermbilder av 19. okt.-linja må tas før
  ~26. okt. Loggene bør sendes et sted med lengre lagring.
- **Applikasjonsloggene ligger hos Railway**, og det er Railway som hadde hendelsen. Portalens
  egne spor (audit, innloggingslogg) ligger i databasen; de bør også sendes ut.
- **Én nøkkel kan ikke roteres uten å miste de gamle backupene** — portalen kjenner bare én
  `OFFSITE_BACKUP_KEY`. Støtte for en forrige nøkkel bør på plass.
- **Én leverandør er ett feilpunkt.** Med deploy stanset kunne ingen rettelse gå ut.
  Papirskjemaene er fortsatt førstelinja; en reserve hos en annen leverandør vurderes.
