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

# Samme suite, men delt. **190 s → ~106 s** (målt 16. sep. 2026, fire kjerner).
# `core` må stå for seg: `core/tests_backup.py` skriver ekte backupfiler til én
# mappe og rører det globale handlerregisteret, så fire arbeidere kolliderer —
# feilen kommer ut som «cannot pickle 'traceback' object», som ikke ligner det
# den er. Alt annet tåler `--parallel` fint.
python manage.py test patients accounts audit statistikk oppdrag vaktliste myproject -v 1 --parallel 4
python manage.py test core -v 1

# Én enkelt test
python manage.py test patients.tests.PatientAPITest.test_create_patient -v 2

# Migrasjoner
python manage.py makemigrations
python manage.py migrate
```

## Mutasjonstesting

**Den gjøres for hånd:** gjør koden feil med vilje, kjør testene, krev at de blir røde.
Det finnes ingen mutasjonsverktøy i kjøringen, og poenget er ikke en prosentsats — det er
å svare på ett spørsmål om gangen: *hadde noen merket det om denne regelen forsvant?*
Antall mutanter og hva som overlevde føres i CHANGELOG sammen med endringen.

**Kjør de testene som dekker mutanten, ikke hele appen.** Målt 16. sep. 2026:
`manage.py test oppdrag` er 38 sekunder, `oppdrag.tests_passiv_avvente` er 5. Med 21
mutanter blir det tretten minutter mot to, for nøyaktig samme svar — og over en økt med
hundre mutanter er forskjellen en klokketime. Fristelsen er å kjøre alt som en forsikring
mot at «mutanten traff et annet sted enn du tror», men den fella løses ved å **lese diffen
til mutanten**, ikke ved å kjøre 560 urelaterte tester. Hele suiten kjøres én gang, på
slutten.

**Innsatsen skal stå i forhold til hva en overlevende mutant koster**, ikke til hvor mye
kode som ble rørt. En feil i `services` legger seg i data og oppdages av ingen; en feil i
markupen ser den som åpner siden.

| Lag | Hvor tungt | Hva som prøves |
|---|---|---|
| Tjenestelaget og rammeverket — tilgang, arkiv, backup, offsite, migrasjoner | **Tungt.** Hver gren, hver grense, hver sperre. En mutant som overlever er et hull som tettes før det pushes | Vilkår snudd, `and` → `or`, grense av med én, sperre fjernet, `transaction.atomic()` fjernet, scope fjernet fra et filter |
| Views og endepunkter | **Middels.** Portene, ikke feltene | Tilgangsdekoratøren fjernet, 409-sjekken fjernet, `confirm`-kravet fjernet, nivået senket ett trinn |
| JS-funksjoner som **avgjør** noe — `avgjor()`, `kanBemannePlass()`, `lydSkalSpille()`, `klikkSkalKjore()`, `_dagnokkel()` | **Middels.** De er regler som tilfeldigvis kjører i en nettleser, og de er grunnen til at slike regler skilles ut som egne funksjoner | Regelen invertert, ett ledd i `&&` fjernet, kallstedet fjernet |
| JS-byggere og tegning (`mk*`, `tegn*`) | **Lett.** Bare der markupen bærer en regel: escaping, og knapper som skal være borte for et nivå | Escaping byttet mot rå interpolasjon, gaten i byggeren fjernet |
| CSS, maler og tekster | **Ingen.** Her er øyet raskere enn en mutant | |

Tretten mutanter på et tidsfelt og to på en tilgangsport er feil vei rundt. Er du i tvil om
et lag, spør hva brukeren ville sett: ser hun feilen med det samme, holder det å prøve den
ene regelen som avgjør; ser hun den aldri, hører innsatsen hjemme der.

**Tre måter en mutant lyver på.** Alle tre er sett i dette prosjektet, og alle tre gir et
falskt «OK» — som er verre enn ingen mutasjon, fordi det *bekrefter* en dekning som ikke
finnes:

1. **Den traff et annet sted enn du tror.** Et søk-og-erstatt med `, 1` tok det første
   treffet, og den samme tilgangssjekken sto i et view til. Kontrollér diffen til mutanten,
   ikke bare at den kjørte.
2. **Den var en no-op.** `start = start + steg if False else slutt` er identisk med
   `start = slutt`. At den overlevde betyr ingenting.
3. **Testen kaller hjelperen selv, så kallstedet kan fjernes.** Testene kalte
   `planleggerSikreLinjer()` direkte, og da kunne `tegnPanel()` slutte å kalle den uten at
   noe ble rødt — nøyaktig feilen regelen fantes for. **Muter kallstedet, ikke bare
   funksjonen**, og la minst én test gå gjennom den ekte inngangen.

**Og en fjerde som ikke er mutantens feil: fikstureringen bar ikke prod-formen.**
`_dagbolker()` lot seg mutere fra lokal tid til `.date()` rett på tidspunktet, fordi
testskiftene var skrevet i norsk tid. ORM-en gir UTC. Bærer ikke testdataene den formen
prod har, går mutanten grønn og regelen står udekket.

## Arkitektur

### Hvor dokumentasjonen bor

**Rota beskriver rammeverket, hver modul beskriver seg selv.** Fila var 1 433 linjer
15. sep. 2026, og 651 av dem — nær halvparten — gjaldt én modul om gangen; mest
vaktlista, som alene var 489 linjer. Regelen for hva som står hvor følger koden: **ligger den i `core/`
eller gjelder den alle, står den her; ligger den i en app, står den i appens egen fil.**

| Fil | Lastes når du arbeider i | Innhold |
|---|---|---|
| `CLAUDE.md` (denne) | overalt | Arbeidsflyt, mutasjonstesting, modulregistry, tilgangsmodell, rate-limiting, audit, backup, arkiv, avhengighetsretning, frontend, migrasjoner, drift |
| `patients/CLAUDE.md` | `patients/` | API-mønsteret og viewdelingen |
| `oppdrag/CLAUDE.md` | `oppdrag/` | Statusmaskinen, verdimengdene, bilens utganger, historikk mot arkiv |
| `vaktliste/CLAUDE.md` | `vaktliste/` | Korps og reservasjoner, skift, drift, planleggeren, offline |
| `statistikk/CLAUDE.md` | `statistikk/` | Kilderegisteret og de to gatene |

**Modulfilene lastes ikke alltid, og det er hele poenget — men det koster noe.** Rota leses
hver gang; en modulfil når noen faktisk arbeider i mappa. Derfor står **det som må vites før
man rører en modul** her: avhengighetsretningen, tilgangsnivåene, at hvert view under en
modul må være dekorert, at data inn i et `<script>` går gjennom `js_json()`. *Hvordan
modulen virker innvendig* står hos modulen. **En regel som gjelder to moduler hører hjemme i
rota**, ikke i begge — to kopier er to kilder som glir fra hverandre, og den som leser den
ene vet ikke at den andre finnes.

`core/tests_claude_md.py` håndhever tre ting delingen gjør mulig å bryte: at hver modulfil
er med i dokumentråte-testens liste (ellers slutter stiene og symbolene i den stille å bli
kontrollert), at tabellen over peker på filer som finnes og ingen fil mangler fra den, og
at et modulavsnitt ikke vokser tilbake i rota.

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

**`is_superuser` og `is_staff` er Djangos, ikke portalens** (15. sep. 2026). De gater
bare `/django-admin/`, som er rutet av i produksjon (S1), og settes **kun** av
`manage.py create_admin`. Å gjøre noen til administrator i brukeradministrasjonen setter
dem *ikke*, og skal ikke gjøre det — portaltilgang er `role == 'admin'` og `ModulTilgang`.

Det gjør superbrukerkontoen til noe annet enn «en administrator til»: den er den ene man
kommer tilbake inn med. **Flagget er eksklusivt til bootstrap-kontoen** (André, 15. sep.
2026), og det holdes av fire ting som hver dekker sin vei:

| Hvor | Hva den stopper |
|---|---|
| `AdminUserEditForm` låser `role` med `disabled` | Nedtrekket tegnes grått, **og** Django forkaster innsendt verdi. Et valg som gir feilmelding er en kontroll som fører til en vegg |
| `_kan_degraderes()` og `_kan_slettes()` | Andre lag. Forsvinner låsen i skjemaet, skal noe fortsatt stoppe det |
| `create_admin` avviser superbruker nummer to | Kommandoen er idempotent på *brukernavn*, så den laget én til for hvert nye navn — og da er bootstrap-kontoen en kategori, ikke en konto |
| `RollenSettesBareGjennomSkjemaeneTests` | Ingen kode skriver `.role` direkte. Et nytt endepunkt som gjør det, går utenom alle lagene over uten at noe blir rødt |

Den siste er den som holder de tre andre i live: sperrene verner nøyaktig de veiene som
finnes i dag, og en ny vei er usynlig for dem. **«Siste admin»-sperra dekker den ikke** — er det tre
administratorer, kan superbrukeren degraderes uten at noe protesterer, og da er nødutgangen
borte mens portalen ser helt normal ut. **Frysing står igjen med vilje:** grensen går ved om
handlingen lar seg reversere, og «Tø konto» står ved siden av.

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
kaster aldri og cacher i fem minutter. **Prefikset leses av `_prefiks()`, som kjenner tre
former** (15. sep. 2026): `Filter.Prefix`, `Filter.And.Prefix` — den S3 bruker når regelen
kombinerer prefiks med en tag eller en størrelsesgrense — og det gamle `Prefix` på toppnivå.
Vi leste to av dem, og meldte «filene blir liggende for alltid» om en regel som sto helt
riktig. Det er den verste sorten feilmelding: den peker på en ekte fare på et tidspunkt der
faren ikke finnes, og lærer den som leser den å overse kortet. Feilteksten bærer nå også
**koden Scaleway faktisk svarte** — sto det «mangler ObjectStorageBucketsRead» uansett, var
en riktig satt nøkkel og en feil i vår egen kode umulig å skille fra hverandre. `hent_offsite --list`
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

**Modul til modul går bare én vei, og den veien er navngitt.** Sentralbordet i `oppdrag`
viser besetningen fra vaktlista, og retningen er `vaktliste` → `oppdrag`: oppdragsmodulen
importerer **ikke** vaktlista, gaten settes med en slug gjennom `core`, og
`OppdragImportererIkkeVaktlista` leser importene med AST og håndhever det. Statistikkappen
navngir ingen kildemodul i det hele tatt (`StatistikkappenNavngirIngenKilde`). Hvordan de
to er koblet står hos modulene selv.

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

**Og leser du kilden, strip kommentarene først.** En test som krevde
`-webkit-text-fill-color` i en CSS-regel gikk grønn etter at deklarasjonen var fjernet —
strengen sto også i kommentaren som forklarte hvorfor den trengtes (16. sep. 2026, funnet
ved mutasjonstesting). En regel som leser sin egen prosa måler at noen har skrevet om
begrunnelsen, ikke at koden gjør det den sier.

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