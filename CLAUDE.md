# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Arbeidsflyt ved commit/push

**Før enhver endring som skal commites og pushes: oppdater `CHANGELOG.md` og `TODO.md` i forkant.**
Legg endringen øverst i CHANGELOG (ny `## YYYY-MM-DD`-seksjon ved behov), og kryss av / flytt
relevante punkter i TODO. Dette skal gjøres som del av samme commit, ikke etterpå.

**Oppgi alltid commit-SHA-en ved push** (André, 14. sep. 2026): «når du pusher ting så vil
jeg ha bygg nr jeg kommer til å se på staging/prod». Sju tegn holder — `ce365b5` — og det
skal stå for *hver* gren som ble pushet, ikke bare den siste. Det er nummeret som står i
Railway-deployen, og uten det må den som verifiserer gjette om det hun ser på er det som
nettopp gikk ut.

**Et åpent punkt skal aldri stå som barn under et avkrysset punkt.** Krysses en forelder
av, løftes de uavkryssede barna ut til en synlig bolk først. To punkter havnet der 14. sep.
2026, og et punkt under noe ferdig er et punkt ingen leser igjen.

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

# Tester – hele suiten. **`myproject` skal med** (14. sep. 2026): den bærer 32
# tester på databasevalg, cache, `_env_bool`, statiske filer og migrasjoner —
# altså vaktene rundt «DATABASE_URL må være PostgreSQL på Railway» og den
# `_env_bool` som hadde rate-limitingen av i prod. Lista her utelot den, så den
# som fulgte dokumentasjonen kjørte dem aldri.
python manage.py test patients accounts audit core statistikk oppdrag vaktliste myproject -v 2

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

**CSP-ens `media-src` er `'self' blob:`** (14. sep. 2026). `_stilleLydbaerer()` i
`oppdrag-enhet.js` bygger en stum WAV som Blob — uten den demper iOS' ringebryter
lydvarselet, fordi Web Audio alene regnes som «ambient». `default-src 'self'` dekker ikke
`blob:`, så direktivet må stå eksplisitt; å slakke `default-src` i stedet ville sluppet
blob-er inn i alt som arver. Feilen var *stille der det telte*: siden virket, oppdraget
lastet, og bare konsollen sa fra — mens bilen ikke pep.

**Modaler slipper fokus før Bootstrap skjuler dem** — `slippFokusFoerSkjul()` i
`portal-utils.js`, én lytter på `hide.bs.modal` (den bobler) for hele portalen. Bootstrap
5.3 setter `aria-hidden` uten å flytte fokus ut, og da *nekter* nettleseren å sette
attributtet: modalen blir liggende eksponert for skjermlesere etter at den visuelt er
borte. `inert` måtte vært satt per vindu; dette er ett sted.

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

**Portalens egne tabeller logges av `core/signals.py`** (14. sep. 2026):
`AppSetting`, `ModuleSettings` og `Vakt`. De sto uten audit i det hele tatt fram til da —
å slå av en modul for *alle*, eller flytte sesjonstimeouten, etterlot ingenting, mens hvert
feltbytte på en pasient ble logget minutiøst. Feil vei rundt: jo mer inngripende
handlingen var, jo mindre spor satte den.

**`AppSetting` trenger en unntaksliste, og telleren er grunnen.** Tabellen er nøkkel/verdi
og blander to ting: innstillinger et *menneske* har bestemt, og tellere *maskinen* har
talt. `patients.services.next_patient_nr()` teller opp raden ved **hver
pasientregistrering** (og `oppdrag.services` per oppdrag) — uten unntaket får du én
auditrad per pasient, `next_patient_nr_vakt_7: 41 → 42`, blandet inn mellom de ekte
pasientradene på nøyaktig de vaktene der loggen betyr mest. `cron.*` er med i lista også,
men den er den *svake* grunnen: fem rader i måneden, og de vises bedre på
`/portal-admin/server-status/`.

Regelen står i `nokkel_logges()` — **logg det et menneske har bestemt, ikke det maskinen
har talt** — som egen funksjon og ikke en `if` inne i mottakeren, så den lar seg prøve.
`NOKLER_UTEN_AUDIT` er **prefikser**, fordi begge tellerne bærer vakt-ID i nøkkelen; en
eksakt liste ville virket i test og lekket ved neste vakt. Og den er en **unntaksliste**:
en ny nøkkel logges som standard, fordi en teller for mye er støy mens en innstilling for
lite er et hull man oppdager et år senere.

`AppSetting.key` er tekst-PK mens `AuditLog.record_id` er `BigIntegerField`, så nøkkelen
går i `field_name` (`max_length=64`, nøyaktig som `key`) og `record_id` står 0. Det er
også den lesbare formen. Her blir `EKSPLISITT_MAPPING` i `audit/signals.py` virksom for
første gang: tabellnavnet er fortsatt `patients_appsetting`, så uten den ville radene
stått som «patients».

**Vaktene mot `loaddata` finnes ved å lete, ikke ved å stå i en liste.**
`SignalerFyrerIkkeUnderLoaddataTests` scannet `('oppdrag', 'patients', 'vaktliste')`
skrevet for hånd, og ville ikke sett `core/signals.py` den dagen den kom. Den globber nå
`*/signals.py`; unntak står i `VAKTEN_UNNTATT` med begrunnelse.

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
| «Trenger ny ressurs» spør **to** ting: er noen på vei, *og* var noen framme | `services.trenger_ny_ressurs()` |
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

**«Avbrutt» og «trenger ny ressurs» er to ulike beskjeder** (15. sep. 2026). Regelen sto
som ett spørsmål — «finnes det andre enheter som ikke er ledige» — og den kan ikke skille en
bil som ble ledig fordi hun *ble ferdig* fra en som ble ledig fordi hun *avbrøt*: begge er
`Ledig` på koblingsraden. Behandlet Bil A på stedet og Bil B avbrøt, sto det «trenger ny
ressurs» på et ferdig oppdrag. `services.trenger_ny_ressurs()` spør nå begge, og
`LOSER_OPPDRAGET` er `(Behandlet, Leverer)` — **`Ledig` står bevisst ikke der**. Svaret
leses av **statusmeldingene, ikke koblingsradene**: `behandle_paa_sted` sender raden videre
til `Ledig`, så raden bærer ikke spor av at jobben ble gjort. Både `avbryt_oppdrag` og
`start_oppdrag` bruker funksjonen; feilen sto begge steder.

**Avbrytelsen vises som eget merke** (`avbrutt_av` i svaret, `services.avbrutt_av_bulk` for
lista — tavla polles hvert tiende sekund). Merket er **dempet, ikke alarmerende**: en
avbrytelse sier hva som skjedde, «trenger ny ressurs» krever handling nå, og samme farge
ville lært operatøren å overse den ene. Begge kan stå samtidig. **Merket er med i ETag-en** —
en bil som avbryter på et oppdrag noen alt har løst endrer verken status eller tidspunkt, og
det ville ellers druknet i en 304.

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
- **Utskriftslista grupperes på dag, så ressurs** (15. sep. 2026 — snudd fra
  ressurs-først). Den svarer nå på «hvem er på vakt i dag, og hvor», som er det den som
  møter om morgenen spør om; før svarte den på «hvem står på denne bilen, og når», med
  begrunnelsen at leseren sto ved bilen. Begge er gyldige — dette er et valg om hvem arket
  er for. Korpset er fortsatt en kolonne, og `_skiftrekkefolge()` har `til_tid` som andre
  ledd fordi skift som begynner samtidig ellers står i innsettingsrekkefølge, og et kort
  skift havner midt blant de lange.
- **`_dagnokkel()` er den ene regelen for hvilken dag et skift hører til: startdagen.**
  «fre. 20:00 – lør. 04:00» står under fredag — ikke under begge dager, ikke splittet
  (André, 15. sep. 2026). **Merk at rapportmodulen har landet motsatt for timer**
  (`FORSLAG_RAPPORTMODUL.md` §2.2, splitting ved midnatt): der er spørsmålet hvor mange
  timer, her er det hvem som er til stede. Forskjellen er bevisst og skal ikke «rettes».
  Nøkkelen er nullpolstret fordi den sorteres — `2026-9-15` < `2026-9-4` som tekst.
- **Dagen er ytterste nivå på begge planleggingsflatene** (15. sep. 2026 — André: «i
  ressursgruppene må det være likt som oversikt, ressurser per dag»). `_grupperPaaDag()`
  brukes av «Oversikt» *og* av `_gruppedagbolker()` i gruppefanen; i begge er dagen en
  seksjonsoverskrift og ressurskortene står under den. `mkRessurs(r, apen, egne)` tegner
  derfor **de skiftene den får**, og bruker `_blokkrader` — en dagrad inni kortet ville
  gjentatt tittelen rett over. **`_blokkerMedDager()` er nå bare «Mitt korps»**, som har én
  tabell på tvers av ressursene og altså ingen seksjon å legge dagen i.
- **Utskriftsvelgeren avgrenser til en dag, ikke til en ressurs** (15. sep. 2026).
  `utskriftDag` er en `_dagnokkel()`-streng eller `null` for hele vakta. Ressursvalget ga
  mening da arket var gruppert på ressurs; etter snuingen ville «Ambulanse 1» vært et snitt
  på tvers av det arket er bygget rundt. **En endagsvakt får ingen velger i det hele tatt** —
  ett valg i et nedtrekk er en kontroll som ikke gjør noe; utskriftsknappen står igjen alene.
  Filtreringen skjer **før** tallene regnes, så arkhodet sier den valgte dagens timer og
  ikke hele vaktas.
- **En ressurs uten skift hører til ingen dag, og får bolken «Uten skift».** Uten den ville
  kortet med «Opprett vakt» ikke finnes noe sted, og ingen kunne satt opp den første vakta
  på en ny bil. Bolken vises bare når noen faktisk står uten skift.
- **Rekkefølgen i dagbolken er ressursenes, ikke skiftenes.** `_gruppedagbolker()` leser
  skiftene i serverens rekkefølge (`fra_tid`) og filtrerer så *ressurslista* — samles de per
  ressurs først, er rekkefølgen garantert av hvordan lista ble bygget og ikke av regelen,
  og en mutasjon som fjerner regelen går grønn. Det skjedde 15. sep. 2026.
- **Dagoverskriften vises alltid, også på en endagsvakt** (15. sep. 2026). Fram til da sto
  den bare når vakta spente over mer enn én dag; da måtte planleggeren vite at *fraværet*
  av en dagrad betydde noe, og tabellen skiftet form når vakta ble forlenget.
- **Ressurskortene i gruppefanen kan slås sammen**, og er det som standard når gruppa har
  mer enn én ressurs (André, 14.–15. sep. 2026). Tilstanden ligger i `ressursApen` i
  `vaktliste-kjerne.js`, **ikke i DOM-en** — `mkRessurs()` bygges på nytt ved hvert
  panelbytte, samme grunn til at `gateKnapper()` ikke kan gate den. **Map, ikke Set:**
  fraværende nøkkel betyr «som standarden», så et kort man åpnet ikke slår seg sammen igjen
  når noen legger til en bil i gruppa. Knappene blir stående i hodet på et sammenslått
  kort, og `apneVaktpost()` åpner kortet — ellers lagrer man et skift og ser ingenting
  skje. **Vippa sitter på ressursen, ikke på ressursen-den-dagen**: en bil som står i to
  dagbolker slås sammen begge steder, ellers hadde én ting hatt to tilstander.
  `map(mkRessurs)` sender indeksen som `apen` — den formen var harmløs til byggeren tok
  flere argumenter.
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
regner ut timer, skift, lengste skift, korteste hvile og **overlapp** per person;
`Belastningsgrenser` (én rad) bærer grensene varslene måles mot.

**Vaktas budsjett står øverst i «Planlegger»** (15. sep. 2026,
`docs/FORSLAG_PLANLEGGERFANE.md` steg 2–3): `services.planleggingstall()` gir
`satt_opp`, `bemannet` og `probono` **side om side**, fordi hvert av dem alene lyver litt
— ingen betaler for en tom plass, og «bemannet» står på null når lista er halvt satt opp.
Avstanden mellom de to første er arbeidslista. `Vaktliste.timetak` er **denne** vaktas
budsjett (`Belastningsgrenser` er organisasjonens og gjelder alle), `igjen` måles mot
**satt opp** og ikke mot bemannet, og `_dagbolker()` bryter ned per dag uten egne tak.

**Linja sto først i «Planlegging», og ble flyttet samme dag.** Jeg leste «en planlegger»
som «planleggingstall» og la budsjettet i belastningsfanen; André: «Jeg ba om en
planlegger … Den skal bare admin og leder ha tilgang til. For den genererer grunnlaget på
alt.» Det er to ulike ting: **«Planlegging» er lista regnet sammen** (`les`, hva den
koster dem som står der), **«Planlegger» er stedet grunnlaget lages** (`kan_lede`).

- **Taket settes i `vaktliste_detalj_view`s PUT, sammen med start og planlagt slutt, og
  er derfor `skriv_leder`** — ikke `skriv_full`. Rekkevidden er den samme (hele vakta,
  ikke ett korps' del), og én forespørsel kan ikke ha to tilgangsnivåer inni seg.
- **Budsjettallene sendes bare til den som `ser_alle_korps`.** De filtreres aldri på
  korps — taket gjelder lista — så for en `les` med badge ville de vært et aggregat over
  skift hun ikke får se. `belastning_view` sender `planlegging: null`, og klienten tegner
  ingenting; en tom ramme ville sagt «her er noe du ikke får se».
- **`kanSetteTak()` leser serverens `kan_sette_tak`**, ikke `MODUL_TILGANG`. Regnes den
  ut i klienten, kan knappen og endepunktet komme i utakt.

- **Grensene er organisasjonens**, ikke portalens — derfor data og ikke tall i
  en `if`. `skriv_leder` flytter dem: det endrer hva *alle* vaktlister varsler
  om.
- **Ingenting avvises.** Noen ganger må noen ta et langt skift, og da skal
  lista si det høyt. Fargen er gul (`--vl-varsel`), ikke rød.
- **Overlappende skift gir hvile 0**, ikke et negativt tall — et negativt tall
  i en «korteste hvile»-kolonne ser ut som en regnefeil. **Null der betyr to ulike ting**
  (skift som henger sammen, og skift som overlapper), og det er derfor
  `_overlappstimer()` finnes ved siden av: sum minus union, så
  `timer - overlapp` er faktisk tilstedeværelse. **Summen korrigeres ikke, den
  navngis** — et tall som stille retter seg selv ville skjult dobbeltbookingen.
  Probono teller med her selv om den ikke teller i `timer`: kroppen skiller ikke på lønn.
  Overlappet har **ingen grense å måle mot**, med vilje — én person kan ikke stå to
  steder uansett hva `Belastningsgrenser` sier.
- **Faktisk tid regnes bare av ferdige skift** (både `mott_at` og
  `av_vakt_at`). Et pågående skift ville gitt et tall som endrer seg mens man
  ser på det.
- `_hviletider()` **sorterer selv**, selv om `Vaktpost.Meta.ordering` gjør det
  også: en hjelper skal ikke hvile på at den som kaller den har sortert. Uten
  den egne sorteringen målte testene modellens ordering. **`_dagbolker()` er skilt ut av
  `planleggingstall()` av nøyaktig samme grunn** (15. sep. 2026, funnet på nytt ved
  mutasjonstesting) — og den regner dagen i **lokal tid**: et skift som begynner 00:30
  norsk tid er 22:30 UTC dagen før, så `.date()` rett på tidspunktet legger hver eneste
  nattevakt på feil dag. En test med falske skift må derfor bære **UTC**, som ORM-en
  gjør; bærer den norsk tid, går mutanten grønn.

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

**Planleggeren lager grunnlaget for vaktlista** (15. sep. 2026, `services.generer_grunnlag`,
`POST api/vaktlister/<pk>/generer/`, `kan_lede`). Du sier «tre firemannslag 14–22, én
ambulanse 15–03, én på åttetimers rotasjon», og etterpå finnes ressursene og de tomme
plassene — klare til å fordeles og spisses i fanene som alt virker.

| Regel | Hvorfor |
|---|---|
| **Ressursen er subjektet, skiftvinduene hører til den** | Sola 56 har to adskilte 12-timersvakter (fre./lør. 15–03). Var linja vinduet, hadde hun blitt to ulike biler |
| **Ett skiftvindu er ett skift** | `skiftlengde`, som delte vinduet i bolker, er fjernet 15. sep. 2026 (André: «har vi noe behov for skiftlengde?»). En rotasjon settes opp som de skiftene den er; «Nytt skiftvindu» begynner der det forrige sluttet |
| **Plassene hører til vinduet, ikke til ressursen** | André: «noen ganger ønsker man å ha mindre og mer plasser på enkelte skift visse deler av døgnet.» Samleplassen kan ha seks 14–22 og to 22–06 — én ressurs med to vinduer. Det var også grunnen til at `skiftlengde` måtte gå: den ga alle sine genererte skift samme antall |
| **«Antall» finnes ikke for grupper i ett eksemplar** | Samleplass og KO (`flere_enheter=False`). Det kan bare være én, serveren avviser alt annet, og en kontroll som ikke gjør noe er en kontroll man lurer på |
| **Plassene fødes som planlagt kladd** | `er_planlagt()` — usynlig for korpsene til lederen deler dem ut. Samme grunn som at `kopier_oppsett` aldri tar personene |
| **`erstatt_kladd` rører bare kladden** | Korpsreserverte, `alle_korps` og **alle** bemannede står. Reservasjonen leses av `reservert_korps()`, ikke av feltet — ellers slettes en hel bils plasser fordi ressursen bærer korpset |
| **Ingen `bulk_create`, alt i én `transaction.atomic()`** | Signalene, og: `erstatt_kladd` sletter før den skriver, så en feil halvveis ville etterlatt lista tommere enn før man trykket |
| **`?forhaandsvis` regnes av samme kode** | Samme endepunkt, `_planlegg` + `_sammendrag`. En forhåndsvisning som regner på egen hånd viser før eller siden noe annet enn det som skjer |

**Feltet heter «plasser per skift», ikke «antall folk».** André beskriver Haugesund 56 som
«4 stk fordelt på 2 lag»; bilen har to seter, og de fire er bemanningspoolen. Regnestykket
står under raden — «6 skift × 1 ressurs = 12 plasser, 96 t» — nettopp for at den
oversettelsen skal være synlig før man trykker. Plassene står ikke som et ledd der, fordi
de kan være ulike fra vindu til vindu: hvert vindu viser sitt eget tall, raden summen.

**Parsingen av `plasser` står i `services._linjens_skift()`, ikke i viewet.** Viewet gjorde
`_int(...) or 1`, og da ble et eksplisitt `0` stille til 1 — en regel som later som den
avviser noe.

**Klientens tall er et anslag, serverens er fasit.** `_planleggerVindutall()` speiler
`_linjens_skift()` for å tegne regnestykket mens man skriver; `apneGenerer()` henter
serverens forhåndsvisning før bekreftelsen. `PlanleggerfanenTests` måler at de to sier det
samme på Andrés egne eksempler.

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

23 filer i `static/js/` (ingen bundler), fordelt på fem sider — pasientsiden,
`/statistikk/`, `/vaktliste/` og de to grensesnittene under `/oppdrag/`.

**To av sidene er delt i flere filer** (14. sep. 2026, gjeldspunkt 3.6): `vaktliste.js`
var 3 801 linjer og `oppdrag-sentral.js` 1 991. **Delingen har en nedre grense som
håndheves:** `test_hver_del_er_mindre_enn_den_var` krever at hver del er under 1 800
linjer, ellers kunne én fil vokst tilbake til 3 800 mens de andre sto tomme og alle de
andre reglene fortsatt vært grønne. Den sa fra 15. sep. 2026, og `vaktliste-oversikt.js`
ble skilt ut av tegningsfila. Uten bundler deler filene **ett globalt
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
| `vaktliste-*.js` (seks: kjerne, tegning, oversikt, handlinger, offline, register) | **kun** `/vaktliste/` | Hele vaktlistesiden: **én fane per ressursgruppe**, hver ressurs er et regneark med redigering i raden, «Oversikt» er utskriftslista, «Mannskap» er personellregisteret, og roller, grupper, korps og kompetanser administreres i modaler på siden. **Skjøten mellom `tegning` og `oversikt` går mellom regnearket og oppsummeringene** (15. sep. 2026): fanene, ressurskortene og radene man redigerer i ligger i den første; bemanningskurvene, utskriftslista, belastningen, «Tilstede nå» og «Mitt korps» leser de samme skiftene og svarer på noe annet |

**`data-action` + `data-hendelse` er to lyttere, og bare én skal fyre.** Klikk­delegeringen
i `portal-utils.js` treffer *alle* `[data-action]`. Et element som melder sin egen hendelse
— `<select data-action="…" data-hendelse="change">` i vaktlistas ressurstabell — ble derfor
kalt både på klikk og på endring: klikket som åpnet nedtrekket kalte handlingen uten felt og
verdi, sendte en tom PUT, og tegnet panelet på nytt, så lista forsvant idet den kom.
`klikkSkalKjore()` er regelen, og den ligger som en egen funksjon nettopp fordi en anonym
`if` inne i en lytter ikke lar seg kjøre i en test.

**Og delegeringen sender `(id, felt, verdi)` bare til elementer med `data-felt`** —
`hendelseArgumenter()`. Alt annet får **ett** argument. Planleggerfeltene ble skrevet med
`data-arg="0:1:fra"` og handlere som tok `(arg, verdi)`; `verdi` var alltid `undefined`,
hvert tastetrykk skrev `undefined` inn i tilstanden, og feltet ble blankt ved neste
tegning (meldt fra staging 15. sep. 2026 — «jeg får ikke fylt feltene»). Regelen sto
allerede her; koden ble skrevet som om den ikke gjorde det.

**En test som bare leser markupen ser ikke dette.** `PlanleggerfanenTests._skriv()` plukker
attributtene ut av den ekte markupen og sender dem gjennom `hendelseArgumenter()`, så
argumentene bygges nøyaktig som i nettleseren. Det er den formen en test av et
redigeringsfelt må ha.

**Adressen i `data-id` skal være en stabil ID, ikke en indeks.** `splice()` flytter ellers
adressen til hver rad under den man fjernet, og neste tastetrykk skriver i feil rad.
Planleggerens linjer og vinduer får derfor en klient-ID fra `planleggerNesteId`.

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

**Tall i dokumentene håndheves av `core/tallfasit.py`** (14. sep. 2026). Antall ruter,
backup-handlere, moduler og JS-filer regnes ut fra koden, og
`TallpaastanderTests` krever at dokumentene stemmer. Kjør `python manage.py tallfasit` for
å se de riktige tallene.

Påstandene **registreres eksplisitt** i `PAASTANDER`, ikke gjettes ut av prosaen: et
mønster som lette etter «\<tall\> endepunkter» hvor som helst ville truffet setninger som
ikke er påstander om totalen, og en test med falske funn blir slått av. Hver rad er et
bevisst valg om at akkurat det tallet skal holdes i live. Regexen må treffe **nøyaktig
ett** sted — flere treff er enten duplisert påstand eller et for løst mønster, og testen
sier fra om begge.

Regelen fanger **tall, ikke mening**: at kapittel 5 dokumenterte 16 av 123 endepunkter
fanges, at de 16 hadde feil tilgangskrav gjør det ikke. Den grensen er skrevet i
`core/tests_dokumentråte.py`, sammen med den andre kjente luken — et avsnitt som erklærer
seg historisk tier hele regelen til neste kapittel.

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
faller: duebolprinsippet, ikke flaks.

**Regelen er en funksjon, `nok_til_a_bryte(grense)` i `core/tests_ratelimit.py`**, og ikke
et tall man skriver av. Den ble brutt tre steder samtidig etter at jeg trodde jeg hadde
rettet den: `test_opprett_pasient_strupes` (65 mot 60/m), `test_full_stats_strupes` (35 mot
30) og `test_auditlog_eksport_strupes` (15 mot 10). Den første var «den uforklarte
enkeltfeilen» som gikk igjen i suiten i flere dager — den ble først fanget da en full
kjøring ble tatt vare på med `tee` i stedet for å bli grep-et bort. **Behold loggen fra
hver full kjøring.**

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