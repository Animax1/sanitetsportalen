# Sanitetsportalen — Django

Portal for sanitetsvakt og beredskap. Fire brukervendte moduler i dag —
pasientregistrering, oppdrag, vaktliste og statistikk — på et felles rammeverk som er
bygget for å ta flere.

Django 5.2, Bootstrap 5, Chart.js og Tabulator. Drift på Railway med PostgreSQL; lokalt på
SQLite.

> **Sist gjennomgått 14. sep. 2026.** Fram til da beskrev denne fila en rollemodell med
> `read_only`/`read_write`/`lead_view`/`lead` og fem `kan_redigere_*`-flagg på
> `CustomUser`. **Ingen av delene finnes** — de ble slettet i deploy 2 og 3. En leser
> bygget altså feil mental modell av hele tilgangsstyringen. Se «Tilgangskontroll».

---

## Hvor ting står

| Jeg vil … | Les |
|---|---|
| sette opp portalen på Railway | [`docs/DEPLOY_GUIDE.md`](docs/DEPLOY_GUIDE.md) |
| drifte en vakt, eller rydde opp når noe knekker | [`docs/RUNBOOK_VAKT.md`](docs/RUNBOOK_VAKT.md) |
| forstå hvordan koden henger sammen | [`docs/TEKNISK_DOKUMENTASJON.md`](docs/TEKNISK_DOKUMENTASJON.md) |
| endre kode | [`CLAUDE.md`](CLAUDE.md) — reglene og hvorfor de finnes |
| endre kode i én modul | modulens egen `CLAUDE.md`: [`patients/`](patients/CLAUDE.md), [`oppdrag/`](oppdrag/CLAUDE.md), [`vaktliste/`](vaktliste/CLAUDE.md), [`statistikk/`](statistikk/CLAUDE.md). Rota gjelder der også |
| vite hva som skal gjøres | [`TODO.md`](TODO.md) |
| vite hva som *er* gjort | [`CHANGELOG.md`](CHANGELOG.md) |
| forstå personvernsiden | [`docs/PERSONVERN_DOKUMENTASJON.md`](docs/PERSONVERN_DOKUMENTASJON.md) |
| vite hvordan backup virker | [`docs/BACKUP.md`](docs/BACKUP.md) |

Beslutninger som formet portalen ligger i `docs/BESLUTNING_*.md`. De forklarer *hvorfor*,
og er ofte det man egentlig leter etter.

---

## Arkitektur

```
sanitetsportalen/
├── core/           – Rammeverket. Skal kunne kjøre uten en eneste modul
│   ├── modules.py      – Modulregisteret
│   ├── models.py       – Vakt, AppSetting, Backup, ModuleSettings, Backupplan
│   ├── vakt.py         – Portalens scope: hent_aktiv_vakt
│   ├── auth_decorators.py – admin_required, modul_kreves, har_tilgang
│   ├── backup/         – All backup-logikk. Ingen vei utenom
│   ├── arkiv/          – Frysing, signatur og kollaps
│   ├── stats.py        – Statistikkregisteret
│   ├── driftstatus.py  – Modulenes tall til server-status
│   ├── portalinnstillinger.py – Modulenes felter i portalinnstillingene
│   ├── kontokobling.py – Modulenes kort i brukeradmin
│   ├── middleware.py   – CSP, metrikker, backupklokka
│   └── signals.py      – Audit for AppSetting, ModuleSettings, Vakt
├── accounts/       – Kontoer, tilgangsnivåer, MFA, innlogging
├── audit/          – AuditLog og RequestAuditMiddleware
├── patients/       – Pasientregistrering
├── oppdrag/        – Oppdragshåndtering: sentralbord og enhetsskjerm
├── vaktliste/      – Vaktlister, mannskap, korps, ressurser
├── statistikk/     – /statistikk/ — henter fra modulene, eier ingen data
├── static/         – CSS og JavaScript (ingen bundler)
└── templates/      – HTML-maler
```

### Rammeverk og moduler — retningen er enveis

**`core` er rammeverket og skal kunne kjøre uten en eneste modul.** `accounts` og `audit`
regnes som rammeverk de også. Retningen håndheves av
`core/tests_avhengighetsretning.py`, som leser importene med AST.

Fram til 14. sep. 2026 sto retningen snudd: `core.backup`, `core.arkiv` og `core.offsite`
importerte alle `patients.models`, fordi `AppSetting` og `Backup` bodde der. Ingenting
gikk i stykker av det — derfor sto det i et år, og derfor holdes det nå av en test og ikke
av en intensjon.

**En modul melder seg inn i et register; rammeverket spør aldri etter en modul ved navn.**
Fem registre i dag, alle etter samme idiom — modulen registrerer fra `apps.ready()`:

| Register | Modulen melder inn | Fra |
|---|---|---|
| `core/modules.py` | Selve modulen, og hvilke nivåer den bruker | `<app>/module.py` |
| `core/backup/` | Hva som skal med i backupfila | `<app>/backup.py` |
| `core/arkiv/` | Hva som går inn i arkivets signatur | `<app>/arkiv.py` |
| `core/stats.py` | Tall til `/statistikk/` | `<app>/statistikk.py` |
| `core/driftstatus.py` | Tall til server-status | `<app>/driftstatus.py` |
| `core/portalinnstillinger.py` | Felter i portalinnstillingene | `<app>/portalinnstillinger.py` |
| `core/kontokobling.py` | Kort i brukeradmin | `<app>/kontokobling.py` |

En modul vises bare hvis `ModuleSettings.enabled=True` **og** brukeren har en
`ModulTilgang`-rad på den.

### Datamodeller — de viktigste

**core**
- **Vakt** — scopet alt annet henger på. Pasienter og oppdrag hører til én vakt.
  Én aktiv om gangen, pekt på av `AppSetting['aktiv_vakt_id']`
- **AppSetting** — nøkkel/verdi for det portalvide. `db_table = 'patients_appsetting'`,
  beholdt med vilje da modellen flyttet (se «Migrasjoner» i `CLAUDE.md`)
- **Backup** — metadata om backupfiler. `db_table = 'patients_backup'`, samme grunn
- **Backupplan** — én rad per modul: modus (`av`/`ved_endring`/`alltid`), intervall, cap
- **ModuleSettings** — én rad per modul, admin kan slå av og på uten deploy

**accounts**
- **CustomUser** — `role` er **kontotype** (`admin` eller `bruker`), ikke tilgangsnivå
- **ModulTilgang** — `(bruker, modul_slug, nivaa)`. Dette *er* tilgangsstyringen
- **LoginEvent** — inn-/utlogging, MFA, passordbytte

**patients** — `Patient`, `Forstehjelper`, `Helsepersonell`, `VaktArkiv`, `ArkivertPasient`
**oppdrag** — `Oppdrag`, `Statusmelding`, `Enhet`, `Lokasjon`, `Problemstilling`, `OppdragArkiv`
**vaktliste** — `Korps`, `Mannskap`, `Ressurs`, `Vaktpost`, `Vaktliste`, `Kompetanse`
**audit** — `AuditLog`, feltnivå

---

## Tilgangskontroll

**Tre kategorier, ikke én.** Se [`docs/BESLUTNING_ROLLEMODELLEN.md`](docs/BESLUTNING_ROLLEMODELLEN.md).

1. **Global admin** (`role == 'admin'`) — brukeradmin, backup, moduloppsett, audit, arkiv
   og alt irreversibelt. Står utenfor modulaksen og trenger ingen rader
2. **Modulbasert** — `ModulTilgang(bruker, modul_slug, nivaa)`
3. **Globalt uten admin** — innlogging, min profil, passordbytte, MFA

Nivåene er en ordnet stige, og **fravær av rad er ingen tilgang** — det finnes ingen
`'ingen'`-verdi å lagre:

| Nivå | Betyr |
|---|---|
| `les` | Kan se modulens data — i vaktlista: sitt eget korps |
| `les_alle` | Vaktlista: ser alle korps. Deklareres kun der |
| `skriv_handling` | Navngitte overganger (stemplinger), leser ikke request-kroppen |
| `skriv_full` | Kan redigere felter |
| `skriv_leder` | Kan sette opp — oppretter og fjerner det de andre redigerer |

**Hver modul deklarerer hvilke nivåer som betyr noe for den**, og gir dem sin egen
etikett: `skriv_handling` er «stempling» i oppdrag og «fører sitt eget korps» i vaktlista.
Uten etiketten deles nivået ut i god tro med feil modul i hodet.

```python
from core.auth_decorators import admin_required, har_tilgang, modul_kreves

@modul_kreves('patients', 'skriv_full', svar='json')
```

**Ordet «bruker» i grensesnittet betyr ikke «vanlig tilgang».** En konto ser ingenting før
den har en `ModulTilgang`-rad.

---

## Lokalt på Windows (PowerShell)

```powershell
# 1. Hent prosjektet
git clone <repo-url>
cd sanitetsportalen

# 2. Virtuelt miljø
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# Hvis scripts er blokkert:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3. Avhengigheter (låst med hasher)
pip install -r requirements.txt

# 4. Miljøvariabler
Copy-Item .env.example .env
# Rediger .env og sett SECRET_KEY til en lang tilfeldig streng

# 5. Database og admin
python manage.py migrate
python manage.py create_admin --username admin --password "bytt-meg"

# 6. Start
python manage.py runserver        # http://127.0.0.1:8000/
```

### Avhengigheter er låst med hasher

`requirements.txt` redigeres ikke for hånd. `requirements.in` er ønskene:

```powershell
# Ny eller endret pakke:
#  1. legg den i requirements.in
#  2. kjør:
pip-compile --generate-hashes --strip-extras
#  3. commit begge filene
```

Uten hasher kan en kompromittert pakke på PyPI bytte innhold under samme versjonsnummer.

---

## Tester

```powershell
# Hele suiten
python manage.py test patients accounts audit core statistikk oppdrag vaktliste myproject -v 2

# Én enkelt test
python manage.py test patients.tests.PatientAPITest.test_create_patient -v 2
```

**`myproject` skal med.** Den bærer testene på databasevalg, cache, `_env_bool`, statiske
filer og migrasjoner — altså vaktene rundt «`DATABASE_URL` må peke på PostgreSQL på
Railway» og rundt den `_env_bool` som hadde rate-limitingen av i prod til 13. sep. 2026.
Kommandoen utelot den i lang tid, og `core/tests_testkommandoen.py` håndhever nå at hver
pakke med tester står i den.

Et antall her ville råtnet fra dagen det ble skrevet — kjør kommandoen.

**JS testes ved å kjøre funksjonene i node**, ikke ved å grep-e etter kodelinjer; se
`patients/js_test_utils.py`. Skillet går på hva assertionen påstår: å lese kilden for å
*finne* en funksjon er greit, å påstå at en literal kodelinje står der er det ikke — den
går i stykker av en omskriving som gjør det samme, og går grønn når noen skriver det
samme feil et annet sted.

**Migrasjonsprøver mot ekte PostgreSQL** kjøres før en migrasjon som rører data pushes:

```powershell
$env:MIGRASJONSPROVE_DATABASE_URL = "postgres://postgres:PASSORD@localhost:5432/postgres"
python manage.py verifiser_migrasjoner
```

Å kjøre suiten mot PostgreSQL er ikke det samme og holder ikke: Djangos testbase lages ved
å kjøre migrasjonene mot en *tom* base, så et dataskritt uten data skriver ingenting og
feilen viser seg aldri.

---

## Sikkerhet

### Autentisering

- PBKDF2-HMAC-SHA256, 1 000 000 iterasjoner
- Brute-force-lås: 5 feil → 15 minutter utestengt
- Dobbel rate-limit på innlogging: per brukernavn og per IP
- TOTP MFA med engangskoder og backup-koder
- MFA trust-cookie, signert og enhets-bundet
- Sesjonsinvalidering ved passord- og MFA-bytte

**Nødbryter:** `RATELIMIT_ENABLE=false`. Verdien leses uavhengig av store og små
bokstaver — fram til 13. sep. 2026 ble den sammenlignet med `== 'True'`, og da sto
rate-limitingen av i prod uten at noen visste det.

### HTTP-sikkerhet

Aktivt når `DEBUG=False`: HTTPS-tvang, HSTS ett år med subdomener og preload, sikre
cookies, `X-Frame-Options: DENY`, nosniff, `Referrer-Policy: same-origin`,
`Permissions-Policy` uten kamera, mikrofon og posisjon.

**CSP har ingen verter i `script-src`** — `'self'` + nonce. Bootstrap, ikonene, Tabulator
og Chart.js ligger under `static/vendor/`, ikke på CDN: med `cdn.jsdelivr.net` i lista
kunne én HTML-injeksjon lastet en hvilken som helst npm-pakke, nonce eller ei.
`media-src` er `'self' blob:` for den stille lydbæreren i bilens skjerm.

**Data inn i et `<script>`-element går gjennom `js_json()`**, aldri `json.dumps` + `|safe`:
`json.dumps` escaper ikke `<`, og et navn med `</script>` lukker skriptet.

**Klient-IP leses ett sted**, `core/klientip.py`: siste ledd i `X-Forwarded-For` — det
Railway la til. Første ledd er klientens påstand.

### Audit

- Pasienter, oppdrag, mannskap, skift og ressurser logges på feltnivå
- Portalens egne tabeller også (`core/signals.py`, 14. sep. 2026): `AppSetting`,
  `ModuleSettings` og `Vakt`. Å slå av en modul for alle satte tidligere ingen spor
- Tellere og cron-status logges **ikke** — `next_patient_nr` skrives per pasient, og
  loggen skal si hva et menneske bestemte, ikke hva maskinen talte
- Fritekstfelter logges som endret, men uten verdier
- Inn-/utlogging, MFA og passordbytte som `LoginEvent`

### Backup

**To lag.** Sju handlere: seks modulfiler (`portal`, `patients`, `arkiv`, `oppdrag`,
`oppdrag_arkiv`, `vaktliste`) og én hel databasebackup.

**Den hele fila inneholder brukere, passordhasher, MFA-hemmeligheter og audit-logg, med
vilje** — den skal kunne gjenopprettes i en tom base der det ikke finnes noen å logge inn
som. Modulfilene inneholder bare modulens egne data.

**Backupfilene skal ikke finnes andre steder enn hos Scaleway eller på Railway. Det
finnes ingen nedlastingsknapp**, heller ikke for modulfilene: en `.json.gz` med hele
pasientregisteret i nedlastingsmappa er en helseopplysningsdump utenfor portalens
kontroll.

Offsite komprimeres først og krypteres så (AES-256-GCM) — chiffertekst lar seg ikke
komprimere. To prefikser med hver sin oppbevaringstid, håndhevet av Scaleways
livssyklusregler: `backups/` 730 dager, `full/` 90 dager. Portalens nøkkel har ikke
sletterett.

`python manage.py verifiser_backup` laster filene inn i en engangsbase og sammenligner
radene. Suiten svarer på om koden virker; denne på om innholdet gjør det.

---

## Vanlige feil

### `Activate.ps1 kan ikke lastes inn`
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### `python åpner Microsoft Store`
Windows' app-alias. Slå av under **Innstillinger → Apper → Avanserte appinnstillinger →
Appkjøringsaliaser**, eller bruk `py` i stedet for `python`.

### `psycopg2-binary feiler ved installasjon`
Lokalt trengs den ikke — SQLite er standard. Kommenter den ut i `requirements.txt` hvis
installasjonen stopper der, men **ikke commit** den endringen: Railway trenger den.

### `Static files mangler (CSS/JS ikke lastet)`
```powershell
python manage.py collectstatic --noinput
```
WhiteNoise hasher filnavnene, så en gammel kopi er aldri feil versjon.

### Feil i prod
Se [`docs/DEPLOY_GUIDE.md`](docs/DEPLOY_GUIDE.md) §12, og
[`docs/RUNBOOK_VAKT.md`](docs/RUNBOOK_VAKT.md) §8c hvis en deploy knakk.
