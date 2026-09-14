# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Arbeidsflyt ved commit/push

**Før enhver endring som skal commites og pushes: oppdater `CHANGELOG.md` og `TODO.md` i forkant.**
Legg endringen øverst i CHANGELOG (ny `## YYYY-MM-DD`-seksjon ved behov), og kryss av / flytt
relevante punkter i TODO. Dette skal gjøres som del av samme commit, ikke etterpå.

## Commands

```powershell
# Migrasjonsprøver mot ekte PostgreSQL (se «Migrasjoner» under).
# Krever PostgreSQL lokalt — én gang:  winget install PostgreSQL.PostgreSQL.16
$env:MIGRASJONSPROVE_DATABASE_URL = "postgres://postgres:DITT_PASSORD@localhost:5432/postgres"
python manage.py verifiser_migrasjoner
```

```powershell
# Setup (første gang)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # låst med hasher; ny pakke går i requirements.in + pip-compile
Copy-Item .env.example .env          # rediger SECRET_KEY
python manage.py migrate
python manage.py create_admin --username admin --password "bytt-meg"

# Kjøre lokalt
python manage.py runserver           # http://127.0.0.1:8000/

# Tester – hele suiten
python manage.py test patients accounts audit core statistikk oppdrag vaktliste -v 2

# Én enkelt test
python manage.py test patients.tests.PatientAPITest.test_create_patient -v 2

# Migrasjoner
python manage.py makemigrations
python manage.py migrate
```

## Arkitektur

### Modulregistry (core/modules.py)

Portalens rammeverk. Hver app deklarerer sin modul i `<app>/module.py`, og registreres eksplisitt i `core/modules.py`. Moduler kontrolleres via `ModuleSettings`-tabellen (admin-toggle uten deploy).

Å legge til en ny modul:
1. Lag `<app>/module.py` med klasse som arver fra `Module`
2. Importer den i `_REGISTERED_MODULES` i `core/modules.py`
3. Legg til permission-flagg på `CustomUser` (via migrasjon) om nødvendig

En modul vises kun hvis `ModuleSettings.enabled=True` **og** brukeren har en
`ModulTilgang`-rad på modulen. Global admin ser alt.

### Tilgangskontroll

**Kontoappen kjenner ingen modul ved navn.** Hva en konto *betyr* hos en modul —
førstehjelper, helsepersonell, bil — er modulens sak, og meldes inn gjennom
`core/kontokobling.py`. Se «Avhengighetsretningen».

Importér alltid fra `core.auth_decorators`. **`accounts/decorators.py` er slettet**
(14. sep. 2026, gjeldspunkt 3.3): den var en ren re-eksport av `admin_required`, og den
eneste leseren var testen som verifiserte at den virket.

*Og slettingen avdekket at regelen sto brutt.* Testen som håndhevet N11 lette bare etter
den absolutte formen `from accounts.decorators import`. `accounts/views.py` brukte den
relative, `from .decorators import`, og slapp unna i et år med testen grønn — en regel som
bare dekker halve syntaksen måler noe annet enn den later som. Testen i `core/tests.py`
dekker nå begge.

**Tre kategorier, ikke én.** Se `docs/BESLUTNING_ROLLEMODELLEN.md`:

1. **Global admin** (`role == 'admin'`) — brukeradmin, backup, moduloppsett, audit, arkiv,
   og alt irreversibelt. Står utenfor modulaksen og trenger ingen rader.
2. **Modulbasert** — `accounts.ModulTilgang(bruker, modul_slug, nivaa)`.
3. **Globalt uten admin** — innlogging, min profil, passordbytte, MFA.

```python
from core.auth_decorators import admin_required, har_tilgang, modul_kreves

@modul_kreves('patients', 'skriv_full', svar='json')
```

Nivåene er en ordnet stige. **Fravær av rad er ingen tilgang** — det finnes ingen
`'ingen'`-verdi å lagre:

| Nivå | Betyr |
|---|---|
| `les` | Kan se modulens data — i vaktlista: **sitt eget korps** |
| `les_alle` | Vaktlista: ser alle korps. Deklareres kun der |
| `skriv_handling` | Navngitte overganger (stemplinger), leser ikke request-kroppen |
| `skriv_full` | Kan redigere felter |
| `skriv_leder` | Kan sette opp — oppretter og fjerner det de andre redigerer |

**`skriv_leder` (30. aug. 2026) deklareres av vaktlista og, fra 12. sep. 2026, av
oppdragsmodulen** (der betyr det «setter opp verdimengdene» — lokasjoner, enhetstyper,
problemstillinger). Skillet mot `skriv_full`
er *hva slags skade en feil gjør*: den som bemanner setter folk på plasser og kan rette
tilbake; den som setter opp fjerner en ressurs, og bemanningen forsvinner med den. Uten
trinnet måtte de to deles ut samlet, eller oppsettet bli global admin — og da kunne ikke en
vaktleder lage sin egen vaktliste uten å få brukeradmin, backup og arkiv på kjøpet. Et nytt
trinn er additivt: modulene som ikke deklarerer det, tilbyr det ikke i matrisen.

**Hver modul deklarerer hvilke nivåer som betyr noe for den** — `Module.nivaaer`. Matrisen
tilbyr de nivåene og ingen andre. **Og hver modul kan gi dem sin egen etikett** —
`Module.nivaa_navn`, brukt av matrisen og «Min profil». Det trengs fordi samme nivå betyr
ulike ting: `skriv_handling` er «stempling» i oppdrag og «fører sitt eget korps» i
vaktlista. Uten etiketten deles nivået ut i god tro med feil modul i hodet. En global liste hadde begge feil samtidig: den skjulte
`skriv_handling` for oppdragsmodulen, som er den nivået ble laget for, og tilbød
`skriv_full` på statistikk, der skriving ikke finnes.

Ukjent nivånavn gir **False**, ikke True — en skrivefeil i en dekoratør skal stenge døra.
**Global admin får toppen av stigen** fra `nivaa_for` (13. sep. 2026 — var `skriv_full`,
og da måtte hvert `skriv_leder`-kallsted huske `er_global_admin(...) or`).
`admin_required` setter `_admin_required` på viewet, og `core/tests_sikkerhet_runde2.py`
går gjennom alt under `/portal-admin/`, `/varsler/` og `/min-profil/` med anonym og
vanlig bruker — dekoratørtesten dekket bare modulprefiksene.
`ModuleSettings.enabled=False` gir 403 for alle andre enn global admin.

**Hvert view under en modul må være dekorert.** `patients/tests_modul_dekorator.py` går
gjennom `urlpatterns` og håndhever det — risikoen ved dekoratør framfor middleware er en
glemt dekoratør, og en manuell gjennomgang holder bare til neste endepunkt. Unntak må stå
i lista der, med begrunnelse.

**Grensesnittet gater på `window.MODUL_TILGANG`, ikke på rollen.** Gjør det ikke det, viser
vi knapper som fører til 403 — og en knapp som fører til en vegg er verre enn ingen knapp.

**`CustomUser.role` er kontotype, ikke tilgangsnivå.** Feltet krympet i deploy 2 til
`admin` og `bruker`; de fire verdiene som beskrev tilgang er borte, sammen med
`has_role_at_least`, `role_required`, `write_required` og `stats_required`. Gate på
`er_global_admin(user)` for admin, og på `@modul_kreves`/`har_tilgang` for alt annet.
Ordet «bruker» i grensesnittet betyr *ikke* «vanlig tilgang» — kontoen ser ingenting før
den har en `ModulTilgang`-rad.

De fem `kan_redigere_*`-flaggene er **borte** (deploy 3). Skal en ny modul gates, trengs
ingen kolonne på `CustomUser` — en `ModulTilgang`-rad er hele mekanismen. Det var nettopp
det flaggene gjorde galt: de la tilgang i skjemaet i stedet for i data, og en modul som
ikke hadde noe flagg kunne ikke gates i det hele tatt.

**Tester lager brukere med `accounts.test_helpers.gi_standardtilgang(bruker, profil)`.**
Profilen oppgis eksplisitt — `leser`, `skriver`, `leder_les`, `leder`, `admin` — fordi
rollen ikke lenger sier noe om tilgang. En bruker uten rader er stengt ute av modulen, så
en test som glemmer kallet tester 403-stien uten å vite det.

### Klient-IP og data inn i `<script>` (core/klientip.py, core/jsdata.py)

**`klient_ip(request)` er det ene stedet IP-en leses** (13. sep. 2026): siste ledd i
`X-Forwarded-For` — det Railway la til — validert, ellers `REMOTE_ADDR`. Første ledd er
klientens påstand. Innloggingsloggen, audit-signalene, arkivene og rate-limit-bøttene per
IP (`ratelimit_nokkel`) bruker den; `REMOTE_ADDR` direkte er proxyen i prod.

**Data inn i et `<script>`-element går gjennom `js_json()`**, aldri `json.dumps` + `|safe`:
`json.dumps` escaper ikke `<`, og et navn med `</script>` lukker skriptet.

**Bootstrap, ikonene, Tabulator og Chart.js ligger under `static/vendor/`** (13. sep. 2026,
H3) — ikke på CDN. CSP-ens `script-src` er `'self'` + nonce, uten verter: med
`cdn.jsdelivr.net` i lista kunne én HTML-injeksjon laste en hvilken som helst npm-pakke.
Oppdatering av bibliotekene står i `static/vendor/README.md`; `tests_security_headers`
håndhever at ingen mal peker på et CDN.

**Avhengighetene er låst med hasher** (M16): `requirements.in` er ønskene, `requirements.txt`
er det `pip-compile --generate-hashes --strip-extras` løste dem til, og det er den Railway
installerer. Ny pakke: legg den i `.in`, kjør `pip-compile`, commit begge.

### Rate-limiting (core/ratelimit.py)

Innlogging og MFA håndheves med eksplisitte `is_ratelimited`-kall i `accounts/views.py`
(N4). Alt annet bruker `@rate_limit(...)` fra `core.ratelimit` (S3).

```python
from core.ratelimit import rate_limit

@rate_limit(group='patients:create', rate='60/m', method='POST')
```

**Gruppen skal alltid oppgis eksplisitt** — den er cache-nøkkelen, og to endepunkter må
aldri dele teller. Sett dekoratoren under tilgangssjekken; `key='user'` forutsetter
innlogget bruker. `on_limit='json'` (default) gir `{'error': ...}` med 429, `'html'` gir
429-siden.

**Tell riktig hendelse, ikke bare riktig endepunkt.** En dekoratør teller alle forespørsler
mot viewet. Er det bare én av dem som er verdt å bremse — et feilet gjett, ikke en avvist
skjemainnsending — hører tellingen hjemme inne i viewet, ved siden av den sjekken. Se
`change_password_view`; N4 og S3 gikk begge i den fella.

Bremsen faller åpen ved cache-feil, med vilje. Både `RATELIMIT_FAIL_OPEN=True` og
try/except i `er_rate_limited` trengs — se modulens docstring. Nød-bryter:
`RATELIMIT_ENABLE=false` (leses uavhengig av store og små bokstaver — `_env_bool` i `settings.py`; `== 'True'` hadde rate-limitingen av i prod til 13. sep. 2026).

### Idempotens (core/idempotency.py)

Skriveendepunkter som kan treffes to ganger med samme intensjon — dobbeltinnsending,
nettverks-retry — reserverer en klientgenerert nøkkel før de oppretter noe.

```python
idem = bygg_nokkel('patient_create', request.user.pk, data.get('idempotency_key'))
if idem:
    status, verdi = reserver(idem)   # 'ny' | 'pagar' | 'ferdig'
...
fullfor(idem, patient.pk)            # eller forkast(idem) hvis noe feilet
```

**Reserver etter all validering, aldri før** — ellers brenner en avvist innsending
nøkkelen. Frigi med `forkast()` når opprettelsen feiler. Cache-feil betyr «opprett
uansett»; se modulens docstring.

### API-mønster (patients/views_*.py)

Viewene er delt i fem moduler (N13.3) — `views.py` finnes ikke lenger:

| Modul | Ansvar |
|-------|--------|
| `views_common.py` | `_json_body`, `_patient_to_dict` — delt av de andre |
| `views_patients.py` | Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD, vaktavslutning/-gjenåpning |
| `views_registre.py` | Førstehjelper- og helsepersonellregisteret (én fabrikk bygger begge) |
| `views_arkiv.py` | Vaktarkivet |

Alle endepunkter er JSON-API-er beskyttet med `@login_required` + rollesjekk. Responser følger mønsteret `{'status': 'ok', 'data': ...}` eller `{'status': 'error', 'message': ...}`.

### Audit-logging

Feltendringer logges automatisk via Django-signal i `audit/signals.py`. `RequestAuditMiddleware` lagrer request i thread-local slik at signaler kan hente bruker og IP uten å ta imot `request`-objektet direkte. Legg aldri til manuell audit-kode — signalet tar seg av det.

### Backup-system

Backup er **per modul**, ikke én samlet dump — pluss én hel databasebackup ved
siden av. Hver modul registrerer en `BaseBackupHandler` i `core.backup`-registeret
(fra `apps.ready()`). Sju handlere i dag:

| Slug | Fil | Innhold |
|------|-----|---------|
| `portal` | `core/backup/portal.py` | `core.Vakt` + `ModuleSettings`. **Først i gjenopprettingsrekkefølgen** — uten den feiler alle modulfilene i en tom base, fordi de peker på vakta med et heltall |
| `patients` | `patients/backup.py` | Pasientdata. Arkivmodellene er eksplisitt ekskludert |
| `arkiv` | `patients/backup.py` | `VaktArkiv` + `ArkivertPasient`. Heter «Pasientregistreringsarkiv» |
| `oppdrag` | `oppdrag/backup.py` | Oppdrag, statusmeldinger, enhetsbytter, enheter, lokasjoner og verdimengdene |
| `oppdrag_arkiv` | `oppdrag/backup.py` | `OppdragArkiv` + `ArkivertOppdrag`. Er også **sperren** foran kollaps |
| `vaktliste` | `vaktliste/backup.py` | Korps, mannskap, kompetanser, ressurser, vaktposter, vaktlister |
| `full` | `core/backup/full.py` | **Hele databasen** unntatt sesjoner, contenttypes, permissions og backup-metadata. Brukere, MFA og logg er med. Eget prefiks og egen frist offsite |

Gjenoppretting i tom base går i rekkefølge: **portal → patients → arkiv →
oppdrag → oppdrag_arkiv → vaktliste**, eller `full` alene.
`AlleFileneGjenopprettesTests` håndhever at det virker.

**`restore_models` skrives ikke for hånd.** `get_restore_models()` utleder lista
topologisk fra `apps` minus `exclude`, barn før foreldre. Den håndskrevne lista
var gjeldspunkt 3.4: `Lydvarsel` var med i dumpen, glemt i slettelista, og
radene ble stående igjen etter en gjenoppretting. `SlettelistaDekkerDumpenTests`
håndhever at hver modell som dumpes også tømmes.

**Lagringssignaler må ha `@ikke_under_loaddata`** (`audit/utils.py`). Django
sender `raw=True` når `loaddata` skriver en rad, og uten vakten fyrer
audit-signalene: de leser relaterte objekter som kanskje ikke er lastet ennå
(«Mannskap matching query does not exist» midt i en gjenoppretting), og de
skriver en auditrad per lastede rad. Selve gjenopprettingen logges av viewet,
med hvem som gjorde den. `SignalerFyrerIkkeUnderLoaddataTests` leser alle
mottakerne og krever vakten.

FK-er ut av modulens eget datasett strippes (`strip_fields`): med
`natural_foreign` lagres de som brukernavn, og er kontoen slettet feiler hele
gjenopprettingen — altså akkurat når man trenger backupen. Den hele fila
strippes **ikke**: brukerne er med i den, så den er selvbærende.

**Klokka er en tråd i web-prosessen** (`core/backup/klokke.py`), ikke en
cron-jobb: et Railway-volum kan bare henge på én tjeneste, og `/data` henger på
web-tjenesten. Se «Cron-jobbene» under for hva en cron-tjeneste uten volum ville
gjort. `BackupSchedulerMiddleware` står igjen som reservenett gjennom samme
`kjor_forfalte()`, og er det eneste stedet som varsler om at tråden har stoppet
— et varsel om at klokka er død, sendt av klokka, kommer aldri fram.

**`core.Backupplan` styrer hva som skjer når.** Tre moduser — `av`,
`ved_endring`, `alltid` — og intervallet settes fritt som tall + enhet
(minutt/time/døgn). `behold` er cap på filer **på volumet**; oppbevaringen
offsite styres av bucketens livssyklusregel og er noe helt annet.
Modulene arver en `standard`-plan; `full` og `standard` styrer alltid seg selv.
Raden har **to** tidsstempler: `sist_sjekket_at` ved hver vurdering,
`sist_fil_at` bare når noe ble skrevet — uten det første er «ingenting har
endret seg» umulig å skille fra «jobben er død».

**Registeret er fasit for hvilke moduler som finnes, ikke plantabellen.** En
modul uten plan får en med standardverdier første gang klokka ser handleren.
Leste vi tabellen direkte, var en nyregistrert modul uten backup til noen
tilfeldigvis åpnet `/portal-admin/backup/` — og for et arkiv betyr manglende
backup at kollapsen nekter å kjøre, altså en feil som først viser seg to år
senere.

En test som kaller `clear_registry()` må rydde opp med
`core.backup.registrer_alle_moduler()`, ikke med én moduls `register_handlers()`.
Gjør den det siste, mister resten av testkjøringen de andre modulenes handlere,
og feilen dukker opp i en helt annen fil. `core/backup/__init__.py` har derfor
sin egen `register_handlers()` som tar **både** portalfila og den hele.

**Offsite til Scaleway (13. sep. 2026, `core/offsite.py`):** `create_backup`
kaller `offsite.meld_ny_backup(backup, path)` etter at fila er skrevet — inert
uten `OFFSITE_S3_BUCKET`/nøklene/`OFFSITE_BACKUP_KEY`, og **kaster aldri**:
volumet er første nett, og feilen står i `OffsiteKopi.feil` og på
`/portal-admin/backup/`. Fila **komprimeres først, krypteres så** — chiffertekst
lar seg ikke komprimere, mens gzip på dumpdata-JSON gir 5–15 % av rå størrelse.
AES-256-GCM, format `SPBK1`+nonce+chiffer. **To prefikser, ett per
oppbevaringstid:** `backups/` for modulfilene (730 dager) og `full/` for den
hele (90 dager) — fristene kan bare skilles i bucketen hvis filene ligger på
hver sin sti, fordi livssyklusreglene filtrerer på prefiks. **Fristene håndheves
av Scaleway, ikke av oss** — nøkkelen har ikke sletterett, og `enforce_cap` rører
bare volumet — så `offsite.livssyklus()` leser reglene *tilbake* fra bucketen og
`_avvik()` sammenligner dem med `FORVENTET_DAGER` på **nøyaktig** prefiks;
`/full` er ikke `full/`, og en regel som treffer ingenting er en oppbevaringstid
som stille ble uendelig. Avviket står på `/portal-admin/backup/`; funksjonen
kaster aldri og cacher i fem minutter. `hent_offsite --list`
/ `hent_offsite <filnavn>` henter, dekrypterer og legger fila i `BACKUP_DIR` med
en `Backup`-rad; prefikset utledes av slugen i filnavnet. **`gjenopprett` er den
som rører basen** (`--list`, `--siste <modul>`, `--hent <objekt>`, `--full`,
`--ja`) — den finnes fordi veien gjennom nettleseren ikke duger i en tom base,
der det ikke er noen å logge inn som. `--ja` er nødvendig og ikke bekvemt:
`railway ssh -- <kommando>` har ingen terminal, så et spørsmål ville hengt.
**Auditraden skrives av `restore_backup`, ikke av viewet**, slik at begge
inngangene etterlater nøyaktig én rad med hvem og hvorfra.

**`verifiser_backup` laster filene som ligger på volumet inn i en engangsbase**
og sammenligner radene mot det filene inneholder — suiten svarer på om koden
virker, denne på om *innholdet* gjør det. Engangsbasen er en flyktig SQLite-fil
i en midlertidig mappe, og `PORTAL_ENGANGSBASE=1` er den ene, navngitte
åpningen i `settings.py`-sjekken som ellers krever PostgreSQL på Railway.
Filene kopieres dit først, så pre-restore-øyeblikksbildene havner i søpla.
Kommandoen kaller `gjenopprett`, ikke `restore_backup`: da er det veien man
faktisk ville brukt som er prøvd, ikke en nabo til den. S3 mockes i
`core/tests_offsite.py` ved å bytte ut `_klient`. Nøkkelen skal også ligge i en
passordbehandler — uten den er bucketen uleselig, og det er meningen.

**Backupfilene skal ikke finnes andre steder enn hos Scaleway eller på Railway.**
Det finnes ingen nedlastingsknapp, heller ikke for modulfilene: en `.json.gz`
med hele pasientregisteret i nedlastingsmappa er en helseopplysningsdump utenfor
portalens kontroll, og den hele fila bærer i tillegg passordhasher og
TOTP-hemmeligheter.

**All logikk ligger i `core/backup/`, og det finnes ingen vei utenom.**
`patients/backup_service.py`, `db_backup`-kommandoen og singletonen
`patients.BackupConfig` er slettet (14. sep. 2026, `patients/0017`) — proxyen
lot en modul ta backup uten å oppgi slug, og slugen er hele forskjellen på en
pasientfil og en hel database. Enhver modul, pasientmodulen inkludert,
registrerer en handler og kaller `core.backup.create_backup(slug=...)`.
`patients/tests_backup.py` håndhever at de tre ikke kommer tilbake.

### Avhengighetsretningen (core/tests_avhengighetsretning.py)

**`core` er rammeverket og skal kunne kjøre uten en eneste modul.** Retningen var snudd
fram til 14. sep. 2026: `core.backup`, `core.arkiv` og `core.offsite` importerte alle
`patients.models`, fordi `AppSetting` og `Backup` bodde der. Ingenting gikk i stykker av
det — derfor sto det i et år, og derfor holdes det nå av en test og ikke av en intensjon.

| Hva | Hvor | Merk |
|---|---|---|
| Portalinnstillingene | `core.AppSetting` | `db_table = 'patients_appsetting'` |
| Backup-metadata | `core.Backup` | `db_table = 'patients_backup'` |
| Portalens scope | `core.vakt.hent_aktiv_vakt`, `vakt_for_year` | |
| CSP, metrikker, backupklokka | `core/middleware.py` | |
| `/healthz/`, server-status | `core/health.py`, `core/admin_status.py` | |

**Tabellnavnene ble beholdt med vilje.** Railway kjører release-fasen *før* den bytter
container, så mellom `migrate` og byttet står gammel kode og serverer mot nytt skjema. En
omdøpt `patients_appsetting` ville gitt 500 på tilnærmet hver forespørsel i det vinduet,
fordi tabellen bærer pekeren til aktiv vakt. Fjernes `db_table`, lager Django en ny, tom
tabell ved siden av den fulle.

**Backupfilene bærer modellnavn**, så `core.backup.GAMLE_MODELLNAVN` oversetter
`patients.appsetting` → `core.appsetting` ved innlasting. Uten den ville hver fil tatt før
flyttingen svart «Invalid model identifier» — og de ligger 730 dager offsite. Tabellen
fylles **i samme commit** som en modell flytter, og `core/tests_modellnavn.py` krever at
venstresida er borte og høyresida finnes.

**`audit/signals.py` utleder `app_label` av tabellnavnet**, så `EKSPLISITT_MAPPING` har
`patients_appsetting` og `patients_backup` → `core`. Uten dem ville hver framtidig
auditrad stått som «patients». Gamle rader endres ikke; bruddet er datert.

**`KJENTE_UNNTAK` er tom, og skal forbli det.** Den sto med fem rader en dag:
`admin_status` hentet modultall ved å importere `vaktliste` og `oppdrag`, og
portalinnstillingene importerte `vaktliste.fil` for å tegne, validere og lagre modulens
egne felter. Begge er nå registre etter samme idiom som `core/stats.py`:

| Register | Hva modulen melder inn | Fra |
|---|---|---|
| `core/driftstatus.py` | Tall til `/portal-admin/server-status/` (`vaktbilde`, `epost`) | `<app>/driftstatus.py` |
| `core/portalinnstillinger.py` | Felter på `/portal-admin/innstillinger/` — `mal`, `kontekst()`, `valider()`, `lagre()` | `<app>/portalinnstillinger.py` |
| `core/kontokobling.py` | Kort på `/portal-admin/brukere/<pk>/` — `handling`, `mal`, `skjema()` | `<app>/kontokobling.py` |

**Regelen gjelder `accounts` og `audit` også** — de er rammeverk (`TEKNISK_GJELD.md` §1).
Kontoappen importerte `patients.models` for å tegne kortet «Pasientregistrering»; det går
nå gjennom `core/kontokobling.py`, og **koblingen er domenedata, ikke tilgang** — samme
skille som `Mannskap.user` i vaktlista. `handling` (verdien i skjemaets `action`) må være
unik: viewet finner handleren på den, og delte to moduler den, ville den ene lagret den
andres skjema. Registeret avviser det.

`KJENTE_UNNTAK_RAMMEVERK` har to rader igjen: kontoopprettelsen lager en `oppdrag.Enhet`
når kontotypen er «bil». Samme slags kobling, men en annen form — det er *selve
opprettelsen* som får en sideeffekt i en modul, ikke et skjema ved siden av. Lista skal
aldri vokse.

**Nøklene og malbiten er modulens, ikke registerets.** Vaktlista leverer
`vaktlister_i_drift`, oppdrag leverer `oppdrag`, og hver tegner sine egne felter fra en
mal i sin egen app — de skal ikke presses inn i ett skjema for å se like ut. Samme
arbeidsdeling som i `core.arkiv`.

**Driftsstatus fanger hver handler for seg** (`samle()`): et dashbord som gir 500 fordi
én modul har en treg spørring, er borte akkurat når man trenger det. Feilen havner i
`error`, vasket med `_scrub_secrets`, og de andre kortene tegnes. Standardnøklene
(`vaktlister_i_drift`, `siste_utsending`, `oppdrag`) settes i `core`, ikke i handlerne —
er en modul av, skal kortet vise «–» og ikke forsvinne.

**Portalinnstillingene validerer alt før noe lagres.** `valider()` og `lagre()` er delt i
to nettopp fordi navnet skrives på `Vakt` og resten i `AppSetting`, uten transaksjon
mellom seg: en modul som nekter skal stoppe hele innsendingen, også portalens egne felter.
`core/tests_registre.py` prøver begge egenskapene med oppdiktede handlere.

### Arkivmønster (core/arkiv/)

Frysing, integritetssjekk og kollaps er modul-agnostisk. Hver modul som arkiverer data registrerer en `BaseArkivHandler` (fra `apps.ready()`), på samme måte som backup-handlerne.

**Arbeidsdelingen er bevisst:** `core.arkiv` eier kanonisering, hashing og orkestrering av kollaps. Handleren eier *hva* som går inn i SHA-payloaden. Grunnen er at payloadens form er del av signaturen som ligger lagret på hvert arkiv i prod — bestemte core formen, ville hvert eksisterende arkiv meldt tukling.

| Funksjon | Ansvar |
|---|---|
| `beregn_sha256(handler, arkiv)` | Signatur over radnivået |
| `verifiser(handler, arkiv)` | True hvis signaturen ikke stemmer. Velger aggregat-signatur etter kollaps |
| `kollaps(handler, arkiv)` | **Irreversibel.** Frys aggregat, slett rader. Idempotent |
| `har_backup_etter(handler, tid)` | Sperre før kollaps — slettingen må være gjenopprettbar |

**`AbstractArkiv` (core/arkiv/models.py) bærer feltene**, slik at modul nummer tre slipper
å skrive dem på nytt: `tittel`, `vakt`/`vakt_navn`, `antall_rader`, `importert_av` med
frosset navn, `sha256`, `kollapset_at`, `aggregat` og `aggregat_sha256`.
`OppdragArkiv` arver den. **`VaktArkiv` gjør det ikke, og skal ikke gjøre det:** feltene
`year_snapshot` og `arrangement_navn` inngår i SHA-payloaden til hvert arkiv i prod, og
et arkiv som byttet feltnavn ville meldt tukling. Duplikatet er prisen for at
signaturene fortsatt verifiserer.

Handleren setter `arkiv_model`, og `kollaps_arkiv`-kommandoen finner kandidater gjennom
registeret — den kjenner ingen modul ved navn, og `--modul <slug>` avgrenser.

To arkiver i dag: `patients/arkiv.py` (referanseeksempelet) og `oppdrag/arkiv.py`.
`ArkivSignaturLaastTests` i begge moduler låser signaturene til literale hex-verdier —
feiler de etter en refaktorering, er det refaktoreringen som er feil.

### Oppdragsmodulen (oppdrag/)

Egen app siden august 2026 — se `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Alle sju fasene er
levert: sentralbord, enhetsskjerm, korreksjoner, offline-kø, statistikkfane og vaktarkiv.

Fem ting det er verdt å kjenne før man rører modulen:

| Regel | Hvor |
|---|---|
| Statusmaskinen er **data**, ikke `if`-er i views | `services.OVERGANGER` |
| Enhetens status **utledes**, den lagres ikke | `services.enhet_status()` |
| Korreksjoner er **nye rader** som peker på den gamle | `Statusmelding.objects.gjeldende()` |
| `fritekst` logges som endret, men **uten verdier** | `signals.FELT_UTEN_VERDILOGGING` |
| «Historikk» rydder tavla, **arkivet fryser og lukker vakta** | `Oppdrag.historikk_fra` vs. `oppdrag/arkiv.py` |
| Bilen rykker videre → oppdraget **trenger ny ressurs**, ikke ferdig | `Oppdrag.trenger_ressurs` + `trenger_ressurs_siden`, `services.start_oppdrag` |
| Lista sorteres på hastegrad, så nummer; ferdige nederst | `_sorterOppdrag()` i `oppdrag-sentral.js` |
| Bilen melder Ledig bare fra Leverer og Behandlet; Avbryt i Rykker ut, Behandlet på sted i Fremme | `services.BILEN_KAN_LEDIG_FRA`, `ALTERNATIV`, `avbryt_oppdrag` |
| Bilen ser bare det lista viser (30 min etter Ledig) — også på detalj, stempling, grovsortering og antall; og aldri flåten, flytting eller verdimengdene | `views._synlig_for_bilen`, `er_enhetskonto`-sjekkene |

**Historikk og arkiv er to helt ulike handlinger**, og har derfor hver sin knapp.
Historikk flytter ett oppdrag ut av den aktive tavla og er fullt reversibel; arkivering
fryser hele vakta med signatur, **sletter så oppdragene fra tavla og historikken og
nullstiller telleren** (12. sep. 2026 — neste oppdrag får #1), og starter klokka mot en
kollaps som sletter radnivået etter 24 måneder. Viewet avviser arkivering mens noe står
på tavla. Pasientarkivet gjør *ikke* dette — der står pasientene igjen etter frysing. `fritekst` arkiveres **ikke** — feltet er unntatt verdilogging i audit,
og å fryse det i 24 måneder ville uthult unntaket.

**Verdimengdene (12. sep. 2026):** `HASTEGRAD` har fått «Drift» (het «Teknisk» én dag) — et oppdrag uten
pasient — og problemstillingene avhenger av hastegraden. **Problemstillinger, enhetstyper
og lokasjoner er tabeller** (`Problemstilling`, `Enhetstype`, `Lokasjon`; migrasjon
`0019`–`0021` seedet de to første fra listene i `choices.py`, som nå bare er seed-data).
`oppdrag/verdier.py` er det ene stedet som leser dem: `problemstillinger_for(hastegrad)`
(Udefinert alltid først), `problemstilling_passer()` med `gjeldende` — et oppdrag beholder
en deaktivert problemstilling ved redigering — og `baerer_antall()`.
`Problemstilling.kategori` (medisinsk/drift/begge) sier hvilke hastegrader raden tilbys
for; **«Udefinert» er en fast rad** som ikke kan endres, deaktiveres eller slettes, fordi
`sett_status` sperrer på navnet. `Oppdrag.problemstilling` er fortsatt tekst — arkivets
radform er signert. `views_verdier.py` er én fabrikk for de tre: liste for `les`,
opprett/endre/omsortere for **`skriv_leder`** (André: «La oss ha skriv_leder rolle på
dette»; enhetskontoer får 403 uansett nivå),
sletting for global admin med `{"confirm": true}`, PROTECT/i bruk gir 409. **Rekkefølgen
settes med hele lista** (`PUT …/rekkefolge/`), ikke «opp» per rad. Klienten har ett vindu
med tre faner («Valglister», `renderVerdiadmin`) og bygger `OPPDRAG_PROBLEMSTILLINGER_FOR`
selv fra radene (`_byggProblemkart`), så nedtrekkene følger med uten sidelasting.
**Bilinnstillingene (12. sep. 2026):** `verdier.bilinnstillinger()` samler lydvarselets
terskler per hastegrad (tabellen `Lydvarsel`, seedet av `0024`; `Lydvarsel.aktiv` slår
ventevarselet av per hastegrad, `0025`, uten å røre pipet ved nytt oppdrag), og tre brytere i
`AppSetting`: `oppdrag_lyd_aktiv` (lyden av for alle biler), `oppdrag_lyd_nytt` (pip ved
nytt oppdrag) og `oppdrag_krev_grov_avreist`. `views_verdier.bilinnstillinger_view`: GET for
`les`, PUT for **global admin** (fanen «Bilen» i «Valglister» vises bare for admin). I bilen
er lyden **på som standard**; dempeikonet husker per enhet (`erDempet`), og
`lydSkalSpille()` er det ene stedet som slår sammen klar/admin/dempet. **Grovsortering
kreves** (`verdier.grov_kreves_for`, speilet i `grovKrevesFor` i JS) før Behandlet på sted
og før Ledig fra Leverer, før Avreist når bryteren sier det, aldri på Drift — og på Drift finnes verken
grovsorteringsraden i bilen (`_kanGrovsortere`) eller merket hos operatøren (`_grovMerke`) — sjekket i
`stempling_view` etter at overgangen er lovlig, så 409 fortsatt vinner. Sentralbordet leser
tersklene for **uthevingen** av ventende oppdrag forbi første terskel
(`venterForbiTerskel()`, `.oppdrag-rad-venter-lenge`).
«Udefinert» kan opprettes, men **`sett_status` avviser `Ledig` så lenge den står**
(`ProblemstillingUdefinert`, 400 med melding til bilen, og kortet i bilen varsler før
hun trykker); den automatiske lukkingen slipper. **`Oppdrag.antall` settes av bilen**, ikke
operatøren (`POST api/oppdrag/<pk>/antall/<n>/`, `skriv_handling`, som grovsorteringen),
bare der problemstillingen bærer et antall; tomt vises som «1 pasient», ellers «N
pasienter». Tømmes for problemstillinger uten — ikke i arkivet. `Enhet.enhetstype` (FK,
null = «Uten type») grupperer tavla og «Nytt oppdrag» i typenes rekkefølge, alfabetisk
innenfor gruppa (`_grupperEnheter()` i JS; serveren sorterer på `Lower(navn)`), og settes
i enhetspanelet (`PUT api/enheter/<pk>/` med `type` = ID, `skriv_full`).

**Bilens utganger (12. sep. 2026):** «Behandlet på sted» (`BEHANDLET`) er en sidegren
fra Fremme rett til Ledig — `KJEDEN` er fortsatt lineær, `neste_i_kjeden` gir Ledig etter
Leverer og Behandlet, og `alternativ_for()` gir den andre knappen (Avbryt i Rykker ut,
Behandlet i Fremme). **Ett trykk på Behandlet skriver Behandlet og Ledig** med samme
tidspunkt (`services.behandle_paa_sted`, Ledig ikke `automatisk`; Udefinert sjekkes før noe
skrives), og bilens projeksjon viser Ledig. Bilen har **ingen egen Ledig-knapp**; stemplingsviewet avviser Ledig
utenom `BILEN_KAN_LEDIG_FRA` med 400, mens sentralens føring følger `OVERGANGER` som før.
«Avbryt» (`choices.AVBRYT`) er en handling, ikke en status: den går i køen som en stempling
(`status/avbryt/`), `services.avbryt_oppdrag` setter raden Ledig (uten Udefinert-sperre —
hun så aldri pasienten), oppdraget til «trenger ny ressurs» og en `Enhetshendelse.AVBRUTT`.
`utledet_av_statuser` rangerer med `choices.AKTIVITET`, ikke `KJEDEN.index`, fordi
Behandlet ikke står i kjeden. Arkivraden har `behandlet_at`, som står i SHA-payloaden
**bare når satt** — eldre arkiv har ingen slik nøkkel i signaturen sin.

Den er den første modulen som tar `skriv_handling` i bruk: bilen får smale, navngitte
stemplingsendepunkter, ikke en feltwhitelist inne i en generell `PUT`. Og skillet mellom de
to grensesnittene er **ikke nivået** — det er om kontoen er knyttet til en `Enhet`. Å knytte
en konto til en enhet gir ingen tilgang; det er domenedata, som `Forstehjelper.user`.

### Vaktlistemodulen (vaktliste/)

Fase 1–2 levert (registre, mannskap, oppsett og planleggingsside på `/vaktliste/`);
fase 3–7 gjenstår — se `docs/BESLUTNING_VAKTLISTE.md`, som er besluttet i sin helhet.

| Regel | Hvor |
|---|---|
| Badgen på personen | `Mannskap.korps`, arvet av kontoen via `Mannskap.user` |
| Reservasjonen på ressursen | `Ressurs.korps` — tom betyr **vaktlederens bord**, ikke fritt fram |
| Reservasjonen på plassen | `Vaktpost.korps` — overstyrer ressursens, `services.reservert_korps()` |
| Begge halvdelene sjekkes samlet | `services.kan_sette_vaktpost()` |
| Ett skift er én rad | `Vaktpost`, med plan og faktisk i hvert sitt feltpar |
| Planlagt vakt rører ikke pekeren | `services.opprett_planlagt_vakt()` |

- **`Mannskap.korps` er badgen** tilgangsmodellen hviler på fra fase 3:
  `skriv_handling` betyr her «fører sitt eget korps» (avgrenset av badgen, ingen
  innsjekk), ikke stempling som i oppdrag. Matrisen trenger derfor en etikett per
  modul per nivå (§4.5) før nivået deles ut.
- **Den doble regelen er skrevet som én funksjon**, `kan_sette_vaktpost()`, nettopp for
  at et endepunkt ikke skal kunne huske badgen og glemme reservasjonen.
- **Reservasjonen finnes på to nivåer, og plassen vinner** (30. aug. 2026).
  `Ressurs.korps` er standarden; `Vaktpost.korps` overstyrer den for én plass, fordi en
  samleplass bemannes av flere korps. `services.reservert_korps()` er det ene stedet som
  slår dem sammen — leses de hver for seg, vil ett endepunkt før eller siden huske
  ressursen og glemme plassen. **Tom verdi betyr «som ressursen», ikke «ingen»**: en
  annen tolkning ville gjort alle eksisterende plasser fritt vilt ved oppgraderingen.
  Å *sette* reservasjonen er å dele ut, og krever `skriv_full`.
- **Korpsfilteret (11.–12. sep. 2026): bare `les` ser sitt eget korps på `/vaktliste/`;
  `les_alle`, `skriv_handling` og oppover ser alle.** `skriv_handling` så én dag bare sitt
  eget; André snudde det 12. sep. («inkludere lese: alle korps»). **Å se er ikke å
  redigere**: korps-føreren redigerer fortsatt bare eget korps (`kan_fore_korps`), og
  nedtrekkene tilbyr bare hennes folk (`mannskap_brukeren_kan_sette`).
  `services.ser_alle_korps()` er det ene stedet; `synlige_vaktposter()` og
  `synlig_mannskap()` filtrerer i svaret sida bygges av, så alle fanene følger med.
  Uten badge er lista tom, og malen sier hvorfor. Sentralbordets besetning i
  `/oppdrag/` er **ikke** filtrert — der er spørsmålet «er bilen klar» — men
  endepunktet krever derfor `ser_alle_korps` eller `oppdrag:les` (13. sep. 2026):
  en ren `les` skal ikke kunne iterere `<pk>` og få telefon og ISSI for alle korps.
  **Den som ser alle får en korpsvelger** i vaktlinja: `_synligePoster()` i
  `vaktliste.js` speiler `poster_for_korps()` og legges på `aktivListe.vaktposter`
  og `register.mannskap` i `brukKorpsfilter()`, så byggerne følger med uten å vite om
  den. Planleggingstallene regnes på serveren og får `?korps=` — bare honorert for den
  som ser alle; for korps-brukeren ville parameteret vært en dør rundt badgen.
- **Tre terskler, og skillet er hva slags utsagn nivået får avgi.** Badge + reservasjon bemanner. `skriv_full` deler
  *ut*: ressurser, reservasjoner, nye vakter og verdimengdene — kunne korps-brukeren
  opprette et korps eller omreservere KO, ville badgen sluttet å avgrense noe. Sletting av
  en vaktliste er global admin.
- **`Mannskap.korps_id` og `Mannskap.user_id` er unntatt badgen.** Flytting sjekkes mot
  *begge* korps, og kontokobling **for hånd er global admin** (12. sep. 2026) fordi den
  flytter en badge — kontoen arver korpset, og dermed hva den kontoen får redigere. Alle
  andre kobler gjennom **`Mannskap.epost`**: finnes en aktiv, ledig portalkonto med samme
  e-post, kobles den av seg selv ved lagring (`views_registre._koble_paa_epost`) — men
  **bare når den som lagrer er `skriv_leder` eller global admin** (13. sep. 2026, M5 —
  først `skriv_full`+, snevret samme kveld: «Fiks alt inkludert kobling»): koblingen
  flytter en badge, og den som bemanner skal ikke velge hvilken konto som blir hvem.
  Alle andre lagrer e-posten; merket sier at kontoen finnes, og lederen kobler.
  **Korps-føreren uten badge** ser alle korps, men fører ingen — sida sier det
  (`mangler_badge`), og «Mannskapsregisteret er tomt» leser registeret hun *ser*
  (`registeretErTomt`), ikke lista over dem hun får sette.
  **Adminkontoer er aldri mannskap** (12. sep. 2026: «Den er utenfor.») —
  `_koblbare_kontoer()` er det ene stedet som sier hvem som kan kobles, og e-postmerket,
  autokoblingen og kontolista leser alle derfra; kobling for hånd til en adminkonto gir
  400. `konto_finnes` i svaret sier om en bruker med adressen finnes, regnet av ett sett
  e-poster, ikke én spørring per rad.
- **Vaktlista som fil på e-post er reserven** (12. sep. 2026, notatet §12):
  `vaktliste/fil.py` bygger `templates/vaktliste/fil.html` — selvstendig, uten
  `{% static %}` og uten ikon-partialen (unntatt i `core/tests_manifest.py`). Telefon og
  ISSI er med, **ikke** e-post, notat eller merknad. Mottakerne og bryteren for «Sett i
  drift» er `AppSetting`-nøkler (`fil.MOTTAKERE_NOKKEL`, `fil.VED_DRIFT_NOKKEL`) satt
  under portalinnstillingene; `send_fil()` kaster aldri og lager alltid en
  `Utsending`-rad (auditlogget), og drift-viewet sender *etter* at drift er lagret —
  e-post nede skal ikke stenge innsjekken. AHASend-transporten sender vedlegg som
  base64 (`_vedlegg`). **Intervallsendingen** (13. sep. 2026, `fil.send_planlagte()`,
  `INTERVALL_NOKKEL`/`BARE_ENDRET_NOKKEL`) kjøres av
  `vaktliste.middleware.FilutsendingMiddleware` — trafikken er klokka, som for
  backup — og sammenligner `Utsending.innhold_sha256` mot den sist *sendte*; klokka går
  fra forrige *forsøk*. Middlewaren tas ut under test i `settings.py`, som
  backup-planleggeren.
- **Offline drift på `/vaktliste/`** (13. sep. 2026, notatet §13): service workeren
  `static/js/vaktliste-sw.js` serveres av `vaktliste.views.sw_view` på `/vaktliste/sw.js`
  (en worker styrer bare stier under sin egen; uten innlogging, unntatt i
  `patients/tests_modul_dekorator.py`, med egen CSP begrenset til `'self'`).
  `avgjor()` er den ene regelen: API-GET nett først med kopi som reserve (header
  `X-Vl-Kopi`), siden nett først, statisk kopi først; **aldri POST, aldri en
  omdirigering** (innloggingssiden), og **ingen datakopi eldre enn 24 timer**
  (`erForGammel`). **«Logg ut» sender `Clear-Site-Data: "cache", "storage"`** (13. sep.
  2026) — Cache Storage, localStorage og workeren ryddes i ett på en delt drifts-PC;
  cookies røres ikke. Køen for møtt/av vakt ligger i `vaktliste.js`
  (`koLes`/`koSkriv`, `_leggIKo`, `_projiserKo`, `synkKo`, `tegnOffline`) — samme
  mønster som bilens kø i `oppdrag-enhet.js`. **Står noe i kø, går alt i kø** —
  rekkefølgen er regelen. `stempling_view` leser `tidspunkt` i kroppen, og
  `services.vurder_klienttid` klipper det urimelige. Den gamle `OFFLINE_MODE`-en er
  borte; Django-admin rutes bare under `DEBUG`.
- **Kostbehov/matallergi lagres ikke** (art. 9 — besluttet holdt utenfor portalen), og
  `Mannskap.notat` er unntatt verdilogging i audit (`signals.FELT_UTEN_VERDILOGGING`).
- **En ledig plass har tre tilstander** (11.–12. sep. 2026): tildelt ett korps
  (`Vaktpost.korps`/ressursens), **åpen for alle** (`Vaktpost.alle_korps` — alle ser og kan
  fylle; het «utildelt» én dag), eller **planlagt** — lederens kladd, som `les` ikke ser og
  som ingen under `skriv_full` kan fylle (`services.er_planlagt`). `alle_korps` vinner over `korps`. Å dele ut er `skriv_full`,
  og **planlagt går én vei**: en plass som er delt ut tas ikke tilbake til kladden —
  viewet avviser det, og nedtrekket tilbyr «Planlagt» bare så lenge plassen står der. Fanen «Mitt korps» (`mkMittKorps`) viser korpsets tildelte og
  universale plasser på tvers av ressursene; `kanBemannePlass()` i JS speiler serveren
  plass for plass, og `_korpsKropp()` oversetter nedtrekkets tre tilstander til to felt.
- **En ledig plass er en `Vaktpost` uten `mannskap`.** Planlegging begynner med
  behovet, og «å fylle plassen» er én feltendring. Å *opprette* en ledig plass er
  `skriv_full` (vaktleder setter behovet), å *fylle* den krever badge og
  reservasjon som ellers — de to spørsmålene er `services.kan_sette_vaktpost()`
  og `services.kan_rore_vaktpost()`, og de må ikke slås sammen.
- **Vaktas lengde: start på `Vakt.startet`, slutt på `Vaktliste.planlagt_slutt`.**
  `Vakt.avsluttet` betyr «vakta ble avsluttet» — en hendelse — og kan ikke bære
  et anslag man flytter på. Spennet er det bemanningskurven tegnes over.
- **Plan og faktisk er fire felter, ikke to.** `fra_tid`/`til_tid` er planen,
  `mott_at`/`av_vakt_at` hva som skjedde. Avviket er informasjonen. Stemplene settes
  først i fase 4, og da bak `skriv_full`.
- **«Ny planlagt vakt» lager en `core.Vakt` med `er_aktiv=False` og lar `aktiv_vakt_id`
  stå.** Oktobervakta skal kunne planlegges i august uten at pasienter og oppdrag
  registrert i dag scopes til den. Kopiering av oppsett tar ressursene, **aldri**
  personene — en liste ingen har sagt ja til ser ferdig ut.
- **Skrivinger som kan bryte en unik-skranke står i `transaction.atomic()`.** Databasen
  er fasit for duplikater, men en `IntegrityError` som fanges uten savepoint etterlater
  transaksjonen ubrukelig: sesjonslagringen feiler på vei ut, og brukeren får en naken
  400-side i stedet for feilmeldingen viewet formulerte.
- **Registrene administreres på `/vaktliste/`, ikke i Django-admin.** Den
  flaten er kun rutet under `DEBUG` (S1), så `vaktliste/admin.py` er et
  utviklerverktøy — et register som *bare* finnes der, finnes ikke for brukeren.
  `SjekkAtIngenPekerPaaDjangoAdminTests` skanner alle maler for lenker dit.
- **Mannskapet er en fane på planleggingssiden; korps og kompetanser ligger i
  «Innstillinger»** (30. aug. 2026). `/vaktliste/registre/` er lagt ned.
  Argumentet for en egen side — registrene er globale, fanene gjelder én vakt —
  holdt ikke i bruk: et klikk dit kostet plassen i planleggingen, og mannskap
  og ressurser er nettopp de to man veksler mellom. **Både fanen og
  «Innstillinger» står uten vaktliste**, og fanen velges automatisk da: korps
  må inn før mannskap, og mannskap før noen kan settes på vakt.
  `mkMannskap()` tegner registeret, `apneVerdier(navn)` åpner korps eller
  kompetanser — lista og skjemaet i **samme** vindu, siden vinduet selv åpnes
  fra «Innstillinger». En lagring kaller `_lastRegisterOgListe()`: navnene
  står i planleggingens nedtrekk også.
- **`Ressursgruppe` er typen, og den er en tabell** (30. aug. 2026 — lå i `choices.py`
  før det). Gruppa gjør tre ting samtidig, og det er derfor den er én ting og ikke tre:
  ikonlegger fanen, samler bemanningskurven, og avgrenser rollene. Ikonet er et felt —
  feil ikon er en skjønnhetsfeil, en manglende gruppe er en vaktliste man ikke får satt
  opp. Migrasjon `0007` seeder de seks standardgruppene; testene slår dem opp med
  `test_helpers.gruppe()` framfor å lage sine egne, slik at seeding som slutter å virke
  blir synlig.
- **Rollen heter `Ressursrolle`, hører til en `Ressursgruppe`, og administreres inne i
  ressursen.** Den gjelder plassen på ressursen — lagleder *på bilen* — ikke vakta;
  «vaktrolle» leste som noe man har på hele vakta. Gruppa er riktig nivå og ikke den
  enkelte ressursen: «Sjåfør» hører hjemme på hver ambulanse, og har du tre av dem vil du
  lage rollen én gang. Navnet er derfor unikt *per gruppe*. Nedtrekket i raden filtrerer
  på tre ting, og hvert ledd er en egen feil å gjøre: gruppa, `er_aktiv`, **og den rollen
  raden alt står på** — uten det siste forsvinner en deaktivert rolle fra sin egen rad ved
  neste tegning, og velges bort i stillhet.
- **Sletting av en ressurs ligger bak «Rediger ressurs» og krever bekreftelse to ganger.**
  CASCADE tar skiftene. Dialogen stopper feilklikket; `{"confirm": true}` i kroppen stopper
  et kall som treffer URL-en uten å mene det. De to er ikke samme sperre.
- **En `<td>` må forbli en `table-cell`.** `display: flex` direkte på en celle tar den ut
  av tabellens boksmodell, og alt etter den forskyves i forhold til overskriftene —
  `table-layout: fixed` hjelper ikke. Legg layouten på et element *inne* i cella.
  `TabellcellersLayoutTests` leser hvilke klasser som står på `<td>`-ene i `mkRessurs()`
  og håndhever regelen for dem alle.
- **Et skift redigeres i et vindu, ikke ved å settes opp på nytt.**
  `apneRedigerVaktpost()` endrer mannskap, rolle, tider og merknad i én PUT;
  serveren sjekker den doble regelen på nytt mot personen som skal inn. Å
  bytte person ved å slette raden mistet tidene og rollen som sto der.
  Sletting ligger inne i vinduet bak en bekreftelse, som på ressursen.
- **Utskriftslista grupperes på ressurs og sorteres på fra, til, navn.** Den som
  leser den står ved bilen og spør «hvem er her, og når?» — korpset er en kolonne.
  `_skiftrekkefolge()` har `til_tid` som andre ledd fordi skift som begynner samtidig
  ellers står i innsettingsrekkefølge, og et kort skift havner midt blant de lange.
- **Hver enhet er sin egen `Ressurs` inne i gruppa** — bil A, bil B og bil C er tre
  rader i fanen «Ambulanse», hver med egne skift og egen `enhet`-kobling. Modellen var
  riktig fra første stund, men veien dit var usynlig: knappen lå sist i fanerekka og het
  «Ny ressurs». Gruppefanen har derfor et hode med antall enheter og en «Ny
  <gruppe>»-knapp, og ukoblede enheter viser «Ikke koblet» framfor ingenting.
- **Noen grupper finnes i ett eksemplar** (`Ressursgruppe.flere_enheter`, av
  for Samleplass og KO). «Samleplass 2» er ikke en ny samleplass, det er en
  delt vaktliste ingen leser riktig. Den *første* må man fortsatt kunne
  opprette, så plassen tar slutt først når den ene står der.
  `services`-siden er serverens sperre i `ressurser_view`, **per vaktliste** —
  var den global, kunne neste vakt ikke hatt samleplass. Klienten har regelen i
  **én** funksjon, `gruppaHarPlass()`, fordi den har to lesere: knappen i
  gruppehodet og nedtrekket i «Ny ressurs». Skjules bare knappen, kan man
  fortsatt velge gruppa i nedtrekket.
- **«Ny ressurs» spør bare om navn og gruppe.** Reservasjonen ligger på
  plassen og koblingen på den enkelte enheten, så begge settes i «Rediger».
  Skjemaet ba tidligere om dem, og da måtte man svare før man visste svaret —
  det leste som om gruppa *var* enheten. Nedtrekket fylles derfor i
  `apneNyRessurs()`, ikke i `fyllNedtrekk()`: hvilke grupper som har plass
  endrer seg hver gang en ressurs opprettes.
- **Et endepunkt uten flate finnes ikke for brukeren.** `/api/grupper/` sto en dag uten
  UI, og da kunne ingen lage en gruppe som ikke var seedet — samme feil som Django-admin
  ga oss i fase 1. Manageren ligger i «Innstillinger».
- **Fanen er ressursgruppa, ikke ressursen.** «Ambulanse» er alle ambulansene
  på vakta, med hver bil som sitt eget kort inni (`mkGruppe`). Én fane per bil
  ga ti faner på en vakt med ti biler, og ingen plass der man så dem i
  sammenheng. `aktivFane` bærer derfor en **gruppe-ID**. Det som er per
  ressurs — enhetskobling, reservasjon, roller — blir stående på ressursen.
- **Kurven står i fanen den gjelder** (`mkGruppekurve`), ikke i «Oversikt» —
  og timeaksen har én celle per søyle med samme flex-bredde, så
  klokkeslettet står under sin egen time uansett hvor lang vakta er. Tettheten
  glisner med lengden (`_timesteg`). Den hvite streken i kurven er **midnatt**
  (`vl-dogn`), ikke nåværende tidspunkt; den står i tegnforklaringen fordi en
  strek man må spørre om ikke forklarer noe.
- **Bemanningskurven tegnes per ressursgruppe, over ett felles spenn.** Én samlet kurve
  summerte samleplassen, ambulansene og KO til ett tall som ikke svarer på noe. Spennet er
  felles (`_vaktensSpenn()`) fordi to kurver man ikke kan sammenligne er verre enn én
  samlet.
- **Markup som tegnes på nytt kan ikke gates av `gateKnapper()`.** Den setter
  `.d-none` én gang ved sidelasting; `tegnFaner()` og `mkRessurs()` bygger på
  nytt ved hvert panelbytte og må derfor spørre `kanLede()`/`kanBemanne()`
  selv. «Ny ressurs» sist i fanerekka er eksempelet.
- **Handlingskolonnen i ressurstabellen er `position: sticky`.** Tabellen
  ruller under 1280 px, og uten den var rediger-knappen det første som forsvant
  — altså den ene knappen raden finnes for. Bakgrunnen må settes eksplisitt,
  ellers ruller innholdet synlig under den.
- **Kolonnebredde i ressurstabellen er `min-width` + `<colgroup>`-andeler, og
  begge deler betyr noe.** Et `datetime-local`-felt har en gulvbredde nettleseren
  bestemmer; blir kolonnen smalere enn den, stikker feltet ut over nabocella —
  `table-layout: fixed` klipper ikke innholdet. `RessurstabellensBreddeTests`
  regner ut hva tidskolonnene faktisk blir og krever at de rommer feltet, altså
  regelen og ikke tallene.
- **Tidsfeltene er `datetime-local` med `step="300"`.** Fem minutters steg,
  ikke ett — en vakt planlegges ikke på minuttet. Steget må være et multiplum
  av 60, ellers får feltet et sekundsegment. «Opprett vakt» forhåndsutfyller
  fra- og til-feltet med **vaktas start**, ikke `new Date()`: en oktobervakt
  planlegges i august. Et eldre skift på 08:03 vises og leses tilbake som før;
  `step` styrer bare hva velgeren tilbyr, og ingenting leser `checkValidity()`.
- **Tid vises med dag når skiftet krysser et døgn.** `_tidsspenn()` i
  `vaktliste.js` nevner dagen én gang innenfor ett døgn og to ganger ellers —
  «20:00–04:00» alene sier ikke at skiftet går over midnatt, og arrangementer
  varer flere dager. Vaktas spenn utledes av skiftene, ikke av et felt.
- **`Kompetanse.bygger_paa` er en stige.** Har personen AFØR, skjules VFØR og
  GFØR i alle lister — `services.synlige_kompetanser()`. Ringer stoppes ved
  skriving; en ring som likevel finnes gir avkortet kjede, ikke evig løkke.
- **Verdimengdene sorteres alfabetisk — det finnes ingen `rekkefolge` å
  vedlikeholde.** `Ressurs` er unntaket, fordi der styrer den fanerekkefølgen, og
  der settes den automatisk til opprettelsesrekkefølgen. Sorteringen bruker
  `Lower(...)`: uten den er «alfabetisk» databasens alfabet, og SQLite (dev) og
  PostgreSQL (prod) svarer ulikt på store/små bokstaver. Æ/Ø/Å er fortsatt
  databasens svar.
- **ID-er fra klienten går gjennom `views._int()`.** Et nedtrekk med «Ingen valgt»
  sender `''`, ikke `null`, og den strengen i et FK-filter gir `ValueError` — altså 500
  der brukeren skulle fått «velg korps». `or None` dekker den tomme strengen, men ikke
  en ikke-numerisk.

**Besetningen i sentralbordet (fase 6) går én vei: `vaktliste` → `oppdrag`.**
Oppdragsmodulen importerer **ikke** vaktlista; `oppdrag-sentral.js` henter
`/vaktliste/api/enhet/<pk>/besetning/` og rendrer svaret.
`OppdragImportererIkkeVaktlista` leser importene med AST og håndhever det.

- **Gatet på `les` i vaktliste**, ikke i oppdrag — komposisjonsregelen fra
  rollemodellen §5. Malen får et flagg via `har_tilgang(..., 'vaktliste', ...)`:
  en slug gjennom `core`, ikke en import.
- **Svaret bærer navn, rolle, innsjekkstatus, telefon og ISSI** (telefon og ISSI
  fra 12. sep. 2026 — «på koblede enheter i /oppdrag skal det vises telefon nummer
  og ISSI»). Ikke kompetanser, ikke `notat`, ikke e-post eller konto — sentralbordet
  skal kunne ringe bilen, ikke lese personalmapper. `Mannskap.issi` (`0015`) er
  nødnettsterminalens nummer, tekst med ledende nuller, etter telefon og e-post i
  registeret.
- **Bare skiftene som dekker nå**, og **404 når enheten er ukoblet**: ubemannet
  og ukoblet er ulike svar på ulike problemer.
- **Lista i drift vinner; ellers portalens aktive vakt** (12. sep. 2026 — «koblingen
  fungerer ikke»: vaktlista som kjørte lå på en annen vakt enn den aktive). Dekker
  ingen skift nå, sendes **neste skift** med (`neste`, `neste_fra`), så svaret er «ingen
  nå, Kari fra 16:00». 404-meldingen skiller fortsatt «koblet i en annen vakt» fra «ikke
  koblet noe sted» (`services.koblet_i_annen_vakt`) — det kostet André en kveld 30. aug.
- **Rekkefølgen sorteres i Python.** `rolle` er nullbar, og SQLite (dev) og
  PostgreSQL (prod) plasserer NULL i hver sin ende.

**Planleggingstall (fase 5) varsler, de sperrer ikke.** `services`
regner ut timer, skift, lengste skift og korteste hvile per person;
`Belastningsgrenser` (én rad) bærer grensene varslene måles mot.

- **Grensene er organisasjonens**, ikke portalens — derfor data og ikke tall i
  en `if`. `skriv_leder` flytter dem: det endrer hva *alle* vaktlister varsler
  om.
- **Ingenting avvises.** Noen ganger må noen ta et langt skift, og da skal
  lista si det høyt. Fargen er gul (`--vl-varsel`), ikke rød.
- **Overlappende skift gir hvile 0**, ikke et negativt tall — et negativt tall
  i en «korteste hvile»-kolonne ser ut som en regnefeil.
- **Faktisk tid regnes bare av ferdige skift** (både `mott_at` og
  `av_vakt_at`). Et pågående skift ville gitt et tall som endrer seg mens man
  ser på det.
- `_hviletider()` **sorterer selv**, selv om `Vaktpost.Meta.ordering` gjør det
  også: en hjelper skal ikke hvile på at den som kaller den har sortert. Uten
  den egne sorteringen målte testene modellens ordering.

**Drift (fase 4) er en innsjekk-port, ikke en livssyklus.** `Vaktliste.status`
har to verdier, og `drift` betyr én ting: møtt/av vakt er åpen. Overgangen går
begge veier og rører ingen stempler.

- **Retningen og overgangen står i URL-en**, ikke i kroppen —
  `drift/<start|stopp>/` og `stempling/<handling>/`. Et veksle-endepunkt gir et
  kappløp når to trykk kommer tett. Samme grep som oppdragsmodulen.
- **Stemplingsreglene er data**, `services.STEMPLINGER`, med forutsetninger:
  «av vakt» krever «møtt», og «angre møtt» krever at «av vakt» ikke står. Uten
  dem finnes rader der `er_tilstede` ikke svarer på noe.
- **`kan_stemple()` er ikke `skriv_handling`** (avklaring 11.3). Korps-føreren
  fører sitt eget korps, men «Tilstede nå» skal ha én ansvarlig. Funksjonen er
  et kall videre til `kan_skrive_alt`, og finnes for at beslutningen skal ha et
  sted.
- **Tilgangsporten svares før driftporten.** En korps-fører som trykker skal
  få vite at hun ikke har lov, ikke at lista ikke er i drift.
- **«Tilstede nå» utledes, aldri lagres** (`Vaktpost.er_tilstede`). To kilder
  til samme sannhet går i utakt første gang noe feiler halvveis — og denne
  brukes til å telle hoder ved brann.
- **Drift er planleggingsraden pluss innsjekken foran** (12. sep. 2026 — André:
  «Kunne redigere mannskaper selv om vi er i drift modus»). Fram til da var
  driftraden en egen, smal form uten tidsfelt, kompetanse og merknad, med
  redigering bak blyanten; det holdt ikke i bruk. `_driftrad` er stempelet (44 px
  høy knapp, først i raden) + `_plancellene`, som `_planrad` også bruker.
  Prisen er bredden: `.vl-tabell-drift` har eget `min-width` over regnearkets, og
  `RessurstabellensBreddeTests` regner ut at tidskolonnene rommer feltet i begge
  former.
- **«Sett i drift» bor i «Innstillinger»** (12. sep. 2026), i bolken for én liste,
  og tegnes av `tegnDriftknapp()` både ved lasting og når vinduet åpnes. Statusmerket
  i vaktlinja (`tegnStatus`, `.vl-status.vl-drift`/`.vl-planlegging`) sier formen med
  ikon og fet skrift, i drift med pulserende prikk. Drift inn og ut auditlogges på
  feltnivå (`vaktliste/signals.py`, `vaktliste_vaktliste`).
- **Skift og ressurser auditlogges på feltnivå** (12. sep. 2026 — «for å få logget det
  meste»): `vaktliste_vaktpost` og `vaktliste_ressurs`, opprettet/endret/slettet med hvem.
  Stemplene er feltendringer på `mott_at`/`av_vakt_at` og trenger ingen egen kode.
  `Vaktpost.merknad` er fritekst og logges uten verdier, som `Mannskap.notat`. Derfor
  **ingen `bulk_create` på disse modellene** — den hopper over signalene; `kopier_oppsett`
  gikk i den fella.
- **Klienten har én `data-action` per overgang**, ikke én generisk:
  klikkdelegeringen i `portal-utils.js` sender ett argument. `STEMPLINGER` i
  `vaktliste.js` og i `services.py` holdes like av `StemplingsnavnTests`.

### Statistikk-modulen (statistikk/)

Egen app siden august 2026. Eier `/statistikk/`-siden og full statistikk
(`/statistikk/api/kilde/<slug>/full-stats/` og
`/statistikk/api/kilde/<slug>/arkiv/<pk>/full-stats/`; de gamle én-kilde-stiene
videresender).
`/pasienter/api/stats/` ble ikke flyttet — det ble **slettet** (28. aug. 2026). Det matet
aldri header-chipsene; de regnes ut i `patients-table.js` fra pasientlista. Endepunktet var
en rest fra Flask-porten uten kjent konsument. `basic_stats()` i `patients.services` står
igjen: den er live-siden av invarianten `StatsMatcher` måler, at arkivering ikke endrer
tallene.

**Avhengighetsretningen er statistikk → moduler, aldri motsatt.** Modulen som eier
dataene regner ut tallene; statistikk-appen henter, cacher og viser — og navngir ingen
kildemodul. Registeret er `core/stats.py`, samme idiom som `core.backup` og `core.arkiv`:
hver modul melder inn en `BaseStatistikkHandler` fra `apps.ready()`. To kilder i dag,
`patients/statistikk.py` og `oppdrag/statistikk.py`.

`hent_aktiv_vakt` bor i **`core.vakt`** (flyttet dit 14. sep. 2026, sammen med
`vakt_for_year`): den er portalens scope, delt av alle moduler, og lå i pasientmodulen
fordi `AppSetting`-pekeren gjorde det — så hver modul måtte importere *pasienter* for å
vite hvilken vakt den var i. `StatistikkappenNavngirIngenKilde` leser importene med AST
og håndhever resten.

Ett endepunkt **per kilde**, ikke ett samlet: en fane som ikke er åpnet skal ikke koste
noe, og cache-nøkkelen bærer både slug og vakt-ID. Delte de nøkkel, ville kilde nummer to
servert kilde éns tall i 60 sekunder.

Arkiv-endepunktet har **to gates**: statistikkgaten *og* `er_global_admin`. Arkivet er
strengere beskyttet enn live-statistikken, og hadde det arvet modulens gate ved flyttingen,
ville alle med `les` på statistikk fått innsyn i arkiverte vakter uten at noen bestemte det.

**Modulen komponerer tilgang, den eier den ikke** (§5). Den viser kun kilder brukeren har
minst `les` på i kildemodulen — ellers ville aggregatene gitt avledet innsyn i data
brukeren ikke har tilgang til. Regelen er **«vis det du har tilgang til»**, ikke «alt eller
ingenting»: med to kilder ville det siste tatt statistikken fra alle som leser pasienter
uten å ha oppdrag. Ingen lesbare kilder gir 403 på siden — en statistikkside uten tall er
en side som later som den virker.

**Oppdragstallene utelater varigheter som slutter i en automatisk stempling** (§12.2 i
oppdragsnotatet). Sluttiden er da avledet, ikke målt. Oppdraget telles i alle antall og
fordelinger, og både det og negative varigheter rapporteres i `summary['utelatt']` og vises
på siden.

### Statistikk-caching (core/stats_cache.py)

Ligger i `core` fordi to apper bruker den: `patients` for header-chipsene og `statistikk`
for full statistikk. Full stats caches 60 sek. Støtter ETag/304.

Det finnes **ingen** eksplisitt invalidering — cachen utløper på TTL. De korte TTL-ene er valgt nettopp for å slippe invalideringslogikk, og alle cache-operasjoner er pakket i try/except slik at en død cache degraderer til vanlig beregning i stedet for å ta ned endepunktet.

### Frontend

**Tre stilark, og de dekker hver sine sider.** Å legge en regel i feil fil ser ut som en
virkningsløs endring, ikke som en feil:

| Fil | Lastes av | Variabler |
|-----|-----------|-----------|
| `static/css/style.css` | **kun** `templates/patients/index.html` | `--text-muted` m.fl. |
| `static/css/portal.css` | alt som arver `core/templates/core/base_portal.html` | `--portal-text-muted` m.fl. |
| `static/css/statistikk.css` | **kun** `templates/statistikk/index.html` | definerer selv de fire `base_portal` mangler |
| `static/css/vaktliste.css` | **kun** `templates/vaktliste/index.html` | samme — `statistikk.css` er mønsteret |

Noen frittstående sider (`403.html`, `mfa_setup.html`, `mfa_verify.html`, innlogging)
laster ingen av dem — de har egen `<style>`-blokk og må overstyre selv.

**Hver mal med eget `<head>` tar med `partials/_ikoner.html`** — manifest, fanikon
(`logo.svg`, merket på blått — en lys utgave uten bakgrunn ble prøvd 12. sep. 2026 og tatt
tilbake dagen etter), apple-touch-icon og `theme-color`. Manifestet er en view (`core/manifest.py`, uten
innlogging), ikke en statisk fil, fordi ikonstiene må gjennom `{% static %}`: WhiteNoise
hasher navnene. Merket i `static/img/logo.svg` er et skjold med en person i, bevisst uten
kors og uten rødt; PNG-ene rendres med `python scripts/lag_ikoner.py` (Playwright), aldri
for hånd. `core/tests_manifest.py` håndhever alle tre og leser hjørnepikslene i PNG-ene.

**`base_portal.html` aliaser ikke alle variablene `style.css` definerer.** Den setter
`--surface-1`, `--surface-2`, `--border-color` og `--text-main`, men *ikke* `--text-muted`,
`--text-soft`, `--surface-3` eller `--header-bg`. En udefinert custom property gjør ikke
regelen ugyldig — den gjør fargen arvet, så teksten blir lesbar eller uleselig tilfeldig
uten at noe feiler. Et nytt modulstilark må derfor definere de fire selv, og *ikke* gjenta
de fire portalen faktisk aliaser (da kan temaene komme i utakt). `statistikk.css` er
mønsteret.

**Statistikktabellene bygges med `innerHTML`, så rullingen ligger på beholderen i malen**
(`stats-rull`, 12. sep. 2026), ikke på tabellen — en tabell med `display: block` mister
bredden sin. `TabelleneRullerPaaTelefonTests` krever klassen på hver `tbl-*`/`xt-*`-beholder
i begge fanene. Vaktlinja (`.vl-vaktvelger`) er tre linjer under 992 px: statusmerket
slipper `nowrap` for spennet, og spaceren foran knappene tar hele linja.

Alle temaene er mørke, så **enhver Bootstrap-klasse for dempet tekst må overstyres** der
malen kan se den. `MorkTekstPaaMorkBakgrunnTests` løser `{% extends %}` og `{% static %}`
og håndhever det.

Sytten filer i `static/js/` (ingen bundler), fordelt på fem sider — pasientsiden,
`/statistikk/`, `/vaktliste/` og de to grensesnittene under `/oppdrag/`.

**To av sidene er delt i flere filer** (14. sep. 2026, gjeldspunkt 3.6): `vaktliste.js`
var 3 801 linjer og `oppdrag-sentral.js` 1 991. Uten bundler deler filene **ett globalt
navnerom**, så delingen er billig — men den gjør tre feil mulige som ikke fantes før: en
funksjon som faller mellom to filer, en som dupliseres (den sist lastede vinner i
stillhet), og en mal som kommer i utakt med lasterekkefølgen.

`core/tests_js_splitt.py` håndhever alle tre. **Regelen for rekkefølgen er ikke «all
tilstand i den første fila»** — `let`/`const` på toppnivå er skript-scopede og deles
mellom filene, så det ville vært et krav ingen holder. Den ekte regelen er: **alt som
*kjører* på toppnivå står i den siste fila** (i praksis `DOMContentLoaded`-krokene).
Kjører en tidlig fil noe, kan den lese en binding som ikke er nådd, og siden dør på en
`ReferenceError` før noe er tegnet.

`VAKTLISTE_JS` og `OPPDRAG_SENTRAL_JS` i `patients/js_test_utils.py` er derfor **tupler**,
og `read_js()` skjøter dem i lasterekkefølge — for alt som leser kilden er de én fil, som
de er i nettleseren.

| Modul | Lastes | Ansvar |
|-------|--------|--------|
| `portal-utils.js` | **alle sider** | CSRF-fetch (`apiFetch`), `withSubmitGuard`, escaping, `fmtMin`, `klokke`, `data-action`-delegeringen |
| `patients-utils.js` | pasientsiden, alltid | Rollesynlighet, delt tilstand, klokke, skjemahjelpere |
| `patients-table.js` | pasientsiden, alltid | Tabulator-grid og tavle |
| `patients-forms.js` | pasientsiden, alltid | Registrerings- og redigeringsskjema |
| `patients-app.js` | pasientsiden, alltid | Oppstart (`DOMContentLoaded`), faneskift, auto-refresh, lastere for navneregistrene |
| `patients-admin.js` | pasientsiden, **kun admin** | Registeradmin, sesjonstimeout, vaktavslutning/-gjenåpning, vaktarkiv |
| `statistikk.js` | **kun** `/statistikk/` | Pasientstatistikk (Chart.js), arkivmodus, kildefanene |
| `statistikk-oppdrag.js` | `/statistikk/`, **kun** med oppdragstilgang | Oppdragsfanen. Kall hit fra `statistikk.js` går gjennom `_kallOppdrag('navn')` |
| `oppdrag-sentral-*.js` (fire: kjerne, oppdrag, admin, lasting) | `/oppdrag/`, kontoer uten enhet | Sentralbordet: enhetsliste, oppdragsliste, tidslinje, lokasjonsadmin. `oppstart()` tegner listene uansett hva første henting ga (`LASTEFEIL` til den lykkes), og pollingen settes i `finally` |
| `oppdrag-enhet.js` | `/oppdrag/`, enhetskontoer | Enhetsskjermen: «neste» og statusens andre knapp (Avbryt/Behandlet på sted) mot de navngitte stemplingsendepunktene, offline-køen i `localStorage` (og «venter på dekning» først når eldste rad er 3 s gammel — `usendtAlder`, `USENDT_VENTETID_MS`), antall-knappene, og **lydvarselet** for ventende oppdrag (`lydTerskler()` leser `OPPDRAG_LYDVARSEL` fra tabellen `Lydvarsel`, hentet på nytt hvert 5. min; `skalPipe()`, `lydTikk()` hvert 5. s; Web Audio, **alltid på** — vekket av det første trykket på siden, `lydErKlar()`; `nyeOppdrag()` + `pipNytt()` for nytt oppdrag om admin ikke har slått det av; tida fra bilens `varslet_at`, og et usendt trykk i køen teller som svart). Serveren sender `neste_overgang`/`alternativ_overgang` per rad; kjeden og alternativene følger med som data kun for å projisere neste steg mens noe ligger usendt |
| `vaktliste-*.js` (fem: kjerne, tegning, handlinger, offline, register) | **kun** `/vaktliste/` | Hele vaktlistesiden: **én fane per ressursgruppe**, hver ressurs er et regneark med redigering i raden, «Oversikt» er utskriftslista, «Mannskap» er personellregisteret, og roller, grupper, korps og kompetanser administreres i modaler på siden |

**`data-action` + `data-hendelse` er to lyttere, og bare én skal fyre.** Klikk­delegeringen
i `portal-utils.js` treffer *alle* `[data-action]`. Et element som melder sin egen hendelse
— `<select data-action="…" data-hendelse="change">` i vaktlistas ressurstabell — ble derfor
kalt både på klikk og på endring: klikket som åpnet nedtrekket kalte handlingen uten felt og
verdi, sendte en tom PUT, og tegnet panelet på nytt, så lista forsvant idet den kom.
`klikkSkalKjore()` er regelen, og den ligger som en egen funksjon nettopp fordi en anonym
`if` inne i en lytter ikke lar seg kjøre i en test.

**`patients-utils.js` kan ikke lastes utenfor pasientsiden.** Den gjør arbeid på toppnivå
— `Chart.defaults` og `new bootstrap.Modal(document.getElementById('newModal'))` — og
kaster på en side uten pasientskjemaene. Trenger en ny modulside en helper derfra, skal
helperen flyttes til `portal-utils.js`, ikke kopieres. `JsModulLastingTests` håndhever det
ved å sammenligne hva `statistikk.js` kaller mot hva den faktisk laster.

**Alt en ikke-admin kan nå på pasientsiden, må ligge i en alltid-lastet modul.**
`read_write` har skrivetilgang uten admin-tilgang — derfor bor f.eks. `saveEventName` i
`patients-app.js`. Kall fra alltid-lastet kode til `patients-admin.js` må gå gjennom
`_kall('navn')`, som sjekker at funksjonen finnes. `JsModulLastingTests` håndhever dette.

CSRF-sikret fetch-wrapper brukes for alle API-kall. Tabulator for pasientgrid, Chart.js for
statistikk — og Chart.js lastes **kun** på `/statistikk/`.

Brukerdata som settes inn med `innerHTML` **skal** escapes — `escHtmlValue()` i tabeller (tallsikker), `escapeHtml()`/`_escHtml()` ellers. Markup koden bygger selv merkes med `trustedHtml()`. `patients/tests_xss_stats.py` håndhever dette,
og leser `statistikk.js`, `patients-admin.js` og `statistikk-oppdrag.js` — byggerne er
fordelt på de tre.

JS-oppførsel testes ved å kjøre funksjonene i node, se `patients/js_test_utils.py`. Ikke
skriv nye tester som bare grep-er etter kodelinjer i JS-filer.

**Skillet går på hva assertionen påstår, ikke på om fila leses** (14. sep. 2026,
gjeldspunkt 3.8). Å lese kilden for å *finne* en funksjon, eller for å håndheve en regel
som ikke har noen kjøretid — «ingen mal peker på et CDN», «hver bygger escaper» — er
riktig. Å påstå at en literal kodelinje står der, er ikke: den går i stykker av en
omskriving som gjør det samme, og **går grønn** når noen skriver det samme feil et annet
sted. Fem slike ble skrevet om denne dagen; mønsteret de fikk:

| I stedet for | Skriv |
|---|---|
| `assertIn("if (metode !== 'GET')", kilde)` | Kjør `avgjor()` for hver metode og krev `null` |
| `assertIn('mannskap.sort(', kilde)` | Krev rekkefølgen i svaret, med data som avslører databasens alfabet |
| `assertIn("classList.toggle('active-mine'", js)` | Kall funksjonen mot et minimalt DOM og se at klassen kommer og går |
| `assertNotIn('fjernRessurs', kilde)` | Tegn kortet og krev at sletteknappen ikke er i markupen |
| `assertIn("'…Middleware',\n", settings_py)` | `assertIn(..., settings.MIDDLEWARE_I_DRIFT)` |

**Rate-limit-tester må tåle vinduskanten.** `django_ratelimit._get_window` legger kanten
et fast antall sekunder inn i hver periode, jittret per nøkkel. Tolv forsøk mot `10/m` som
straddler den deles i to bøtter der ingen når ti — testen feiler da omtrent én kjøring av
seksti. Bruk **2 × grensen + 1** forsøk, så bryter den ene siden uansett hvor oppdelingen
faller.

## Migrasjoner

**Prod er PostgreSQL, dev er SQLite — og det er ikke bare en detalj.** En
migrasjon som først skriver rader (`RunPython`/`RunSQL`) og deretter endrer
skjema, må tømme PostgreSQLs triggerkø imellom:

```python
if schema_editor.connection.vendor == 'postgresql':
    schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE')
```

Djangos fremmednøkler er `DEFERRABLE INITIALLY DEFERRED`, så hver skriving
legger en hendelse i kø som først fyres ved commit — og migrasjonen er én
transaksjon. `ALTER TABLE` på en tabell med hendelser i køen avvises med
`cannot ALTER TABLE … because it has pending trigger events`, og release-fasen
crash-looper containeren. **SQLite har ingen utsatte triggere**, så suiten er
grønn uansett; det tok ned deployen 30. aug. 2026.
`DataOgSkjemaISammeTransaksjonTests` håndhever regelen — de tre veiene ut er å
tømme køen, sette `atomic = False`, eller dele migrasjonen i to.
`vaktliste/migrations/0007` er mønsteret.

**Og en migrasjon som har mønsteret må ha en prøve i `core/migrasjonsprover.py`.**
Den statiske regelen ser at kallet *står* i fila, ikke at det kjøres — fjern
kallstedet og la hjelperen bli stående, og den går grønn. Prøven kjører
migrasjonen mot en engangsbase på ekte PostgreSQL, med rader i den historiske
formen, og sjekker hva den gjorde med dem.

**Å kjøre testsuiten mot PostgreSQL er ikke det samme, og holder ikke.**
Djangos testbase lages ved å kjøre migrasjonene mot en *tom* base: et
dataskritt uten data skriver ingenting, fyller ingen triggerkø, og feilen
viser seg ikke. Feilen krever PostgreSQL **og** rader **og** en skjemaendring
etter skrivingen.

Prøvene hoppes over uten `MIGRASJONSPROVE_DATABASE_URL` — de er ikke en del av
den vanlige kjøringen, men skal kjøres før en migrasjon som rører data pushes.
**Serveren kan være hvilken som helst PostgreSQL du får lage baser på**: en
lokal installasjon (`winget install PostgreSQL.PostgreSQL.16`), eller en egen
Postgres-tjeneste i Railway. Ikke pek den på prod-basen — kommandoen rører den
riktignok ikke, men den lager og sletter baser på serveren, og det er ikke noe
man gjør på siden av produksjonsdata.
Kommandoen lager og sletter sin egen engangsbase, og rører aldri basen URL-en
peker på. Den kjører `migrate` i en **underprosess** mot `default`, ikke som et
databasealias: atten migrasjoner i dette prosjektet gjør ORM-kall i `RunPython`
uten `schema_editor.connection.alias`, og ville med et alias skrevet til din
egen base i stedet for prøvebasen.

### Cron-jobbene (core/kommando.py)

**To** jobber kjøres av Railway Cron: `purge_old_logs` og `kollaps_arkiv`.
Ingen har en bruker som ser på mens de kjører, så **begge pakker arbeidet i
`lesbar_dbfeil('hva som ikke ble gjort')`** — en `OperationalError` blir da til
én lesbar linje med årsak og råd, i stedet for fire stablede tracebacks. Jobben
avslutter fortsatt med kode 1.

**Backup er ikke en cron-jobb** (13. sep. 2026). `db_backup` sto i
`CRON_JOBBER` uten å være satt opp i Railway, og ble fjernet uten erstatning
(kommandoen selv er slettet 14. sep. 2026):
**et Railway-volum kan bare henge på én tjeneste**, og `/data` henger på
web-tjenesten. En cron-tjeneste som tok backup ville skrevet fila til sitt eget
flyktige containerfilsystem, opprettet `Backup`-raden, og forsvunnet med fila —
og `core.arkiv.har_backup_etter()` spør bare etter raden, så kollapssperra
ville åpnet seg på spøkelsesbackuper. De to jobbene som står der rører bare
databasen og trenger derfor ikke volumet. Klokka er `core/backup/klokke.py`,
en tråd i web-prosessen; `backup_kjor` er den manuelle inngangen.

**`DATABASE_URL` må peke på PostgreSQL når `RAILWAY_ENVIRONMENT` er satt.**
`dj_database_url.config()` faller ellers stille tilbake til en SQLite-fil i
den flyktige containeren, og da ville `purge_old_logs` talt null rader,
skrevet «Slettet 0 audit-logger» og avsluttet med kode 0 — en grønn jobb som
aldri håndhever A.9. Sjekken står i `settings.py` og henger på
`RAILWAY_ENVIRONMENT`, ikke på `DEBUG`: utenfor Railway er SQLite lov.

Sett variabelen som referansen `${{Postgres.DATABASE_URL}}`, ikke som en
kopiert verdi — en kopi blir stående igjen når passordet roteres, og da
feiler bare cron-jobbene mens websiden går videre som før.

**Hver jobb registrerer sin siste kjøring** (13. sep. 2026): `lesbar_dbfeil(..., navn='db_backup')`
skriver `AppSetting['cron.<navn>']` med tid, ok/feil og melding, både når det
gikk og når det ikke gikk — `core.kommando.registrer_kjoring()` kaster aldri.
`/portal-admin/server-status/` leser `siste_kjoringer()` og viser «Aldri» til
jobben har kjørt én gang. En ny cron-jobb skal ha navnet sitt i `CRON_JOBBER`
og sende det inn, ellers finnes den ikke for dashbordet.

### Server-status (core/admin_status.py)

`/portal-admin/server-status/` polles hvert 10. sekund fra `…/json/`, og
`_build_status_payload()` er én dict med én innhenter per kort. **Hver
innhenter fanger sine egne feil og legger dem i svaret** — et dashbord som
selv gir 500 når databasen er treg, er borte akkurat når man trenger det.
Minne er `{'naa', 'topp'}` (13. sep. 2026): `ru_maxrss` er toppen og går aldri
ned, så «nå» leses fra `/proc/self/status`. Tregeste stier kommer fra
`metrics_store.tregeste_stier()` (P95 per sti, under tre treff utelatt).
Konfigsjekken leser `settings`, ikke `os.environ` — det er settings viewene
kjører med — og reglene er prods: lokalt står DEBUG og HTTPS rødt med vilje.
Feilmeldinger går gjennom `_scrub_secrets()` før de sendes til klienten.

## Miljøvariabler

Settes i `.env` lokalt. Nøkler å kjenne til:

| Variabel | Formål |
|----------|--------|
| `SECRET_KEY` | Kryptografisk Django-nøkkel |
| `DEBUG` | `True` lokalt, `False` i prod |
| `RATELIMIT_ENABLE` | Nød-bryter for rate-limiting |
| `REDIS_URL` | Aktiverer Redis-cache (ellers LocMemCache) |
| `BACKUP_DIR` | Sti til backup-mappe (Railway: `/data/backups`) |
| `LOG_LEVEL` | Loggnivå for rot-loggeren (default `INFO`) |
| `ADMINS` | Mottakere av feilvarsel, format `Navn:epost`, komma-separert |
| `AHASEND_API_KEY` + `AHASEND_ACCOUNT_ID` | AHASends HTTP-API v2 (`core/mail_backends.py`). **Dette er transporten i prod** — Railway sperrer utgående SMTP på alle porter |
| `EMAIL_HOST` m.fl. | SMTP for feilvarsel. Brukes kun lokalt |
| `EMAIL_TIMEOUT` | Tidsgrense for utsending, default 10 s. Må aldri være `None` |
| `OFFSITE_S3_BUCKET`, `OFFSITE_S3_REGION`, `OFFSITE_S3_ENDPOINT`, `OFFSITE_S3_ACCESS_KEY`, `OFFSITE_S3_SECRET_KEY` | Scaleway Object Storage for offsite backup (`core/offsite.py`). Bare prod |
| `OFFSITE_BACKUP_KEY` | Krypteringsnøkkelen for offsite-backupene. Skal også ligge i en passordbehandler utenfor Railway |

## Deployment

Railway med PostgreSQL og persistent volume på `/data`. Auto-deploy fra GitHub `main`. Health-check: `GET /healthz/`.