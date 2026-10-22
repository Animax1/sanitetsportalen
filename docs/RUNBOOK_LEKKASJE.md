# Runbook – Hemmelighetene kan være lekket

> Skrevet etter Railway-hendelsen 22. okt. 2026 («an unauthorized third party may have accessed
> encrypted environment variables and, for some of them, obtained the decrypted contents»).
> Det tok en hel dag fordi rekkefølgen, fallgruvene og kommandoene måtte finnes underveis.
> Her står de. Hendelsen selv er ført i [`docs/AVVIKSLOGG.md`](./AVVIKSLOGG.md).

**Gjelder når:** en leverandør (Railway, Scaleway, GitHub, AhaSend, MapTiler) melder at nøkler
eller miljøvariabler kan være kjent av andre, eller du selv mistenker det (en nøkkel i en commit,
en skjermdeling, en tapt PC).

**Forutsetter:** passordbehandleren, tilgang til Railway (begge prosjektene), Scaleway-konsollen,
AhaSend og MapTiler, og Python på din egen PC.

**Tidsbruk når alt går etter planen:** ca. 2–3 timer for alle fire miljøene.

---

## 0. De tre reglene som gjelder hele veien

1. **Ingen nøkkel limes inn i en chat, en e-post, en commit eller et skjermbilde.** Rett fra
   skriptet i §3 til passordbehandleren, og derfra til Railway. Trenger noen å sammenligne to
   verdier, bruk fingeravtrykket i §5.4.
2. **Gamle verdier slettes ikke fra passordbehandleren** — de merkes «utgått <dato>».
   `OFFSITE_BACKUP_KEY` *må* beholdes: den låser opp hver backup tatt før byttet (§5.7).
3. **Staging før prod, og ett trinn om gangen.** Et trinn er ferdig når `/healthz/` er grønn og
   viser forventet versjon — ikke når variabelen er lagret.

---

## 1. Første halvtime — før noe roteres

Dette kan gjøres med en gang, også om Railway har stanset deploy.

| # | Hva | Hvor | Hvorfor først |
|---|---|---|---|
| 1 | **Steng offentlig tilgang til Postgres** i alle fire miljøene (portal og kart, prod og staging) | Railway → Postgres-tjenesten → Settings → Networking → fjern TCP Proxy / public networking | Et lekket databasepassord åpner ingenting når basen bare nås over Railways interne nett. Det kjøper tid til §5.6 |
| 2 | **Trekk tilbake og lag ny S3-nøkkel** | Scaleway → IAM → Applications → `sanitetsportalen-backup` → API keys | Gjelder utenfor Railway. Sjekk samtidig **Policies**: bare `ObjectStorageBucketsRead`, `ObjectStorageObjectsRead`, `ObjectStorageObjectsWrite`. *Ikke* `ObjectStorageFullAccess` — den sto der 22. okt. uten at noen visste det |
| 3 | **Trekk tilbake og lag ny AhaSend-nøkkel** | AhaSend-dashbordet | Gjelder utenfor Railway |
| 4 | **Sjekk utgående trafikk** | Railway → hver tjeneste → Metrics → Network egress | En topp du ikke kan forklare er tegn på uttak |
| 5 | **Sikre loggene** | Scaleway Cockpit, §6 | Scaleway beholder bøtteloggene i **7 dager**. Ta skjermbilder før de forsvinner |
| 6 | **Åpne en rad i avviksloggen** | `docs/AVVIKSLOGG.md`, §7 | Tidspunktene er lettest å få riktig mens det skjer |

> Nye nøkler i punkt 2 og 3 virker først når portalen er deployet med dem. Er deploy stanset,
> feiler offsite-opplastingen og e-posten fram til da. **Det er riktig avveining:** en død
> lekket nøkkel er bedre enn en levende.

---

## 2. Hver hemmelighet — hvor den bor, hva den åpner, hva et bytte koster

### Sanitetsportalen (begge miljøer; web **og** cron-tjenestene)

| Variabel | Lages med | Åpner | Når den byttes |
|---|---|---|---|
| `SECRET_KEY` | `token_urlsafe(64)` — minst 50 tegn, ellers starter ikke portalen | Forfalskede sesjoner, invitasjons- og nullstillingslenker (`accounts/signert_lenke.py`), «husk MFA»-informasjonskapsler | **Alle logges ut.** Utestående invitasjoner og lenker for nytt passord slutter å virke — send dem på nytt |
| `DATABASE_URL` | — | Hele databasen | Skal være referansen `${{Postgres.DATABASE_URL}}`; selve passordet byttes på Postgres-tjenesten (§5.6) |
| `KART_HMAC_NOKKEL` | `token_hex(32)` | Sende posisjoner til kartet i portalens navn | **Par** med kartets `PORTAL_HMAC_NOKKEL` i *samme* miljø (§5.5) |
| `KART_INNLOGGING_NOKKEL` | `token_hex(32)` | Lage innloggingsbilletter til kartet — logge inn som hvem som helst med KO | **Par** med kartets `PORTAL_INNLOGGING_NOKKEL` (§5.5). Må være ulik `KART_HMAC_NOKKEL` |
| `OFFSITE_BACKUP_KEY` | `token_urlsafe(48)` — minst 32 tegn | Dekryptere backupfilene, *om* man også har filene | **Bare prod.** Gammel nøkkel beholdes (§5.7) |
| `OFFSITE_S3_ACCESS_KEY`, `OFFSITE_S3_SECRET_KEY` | Scaleway (§1 punkt 2) | Backupbøtta | Bare prod |
| `AHASEND_API_KEY` | AhaSend (§1 punkt 3) | Sende e-post i portalens navn | `AHASEND_ACCOUNT_ID` er ikke hemmelig |
| `REDIS_URL` | — | Cachen (bare på under vakt) | Referanse til Redis-tjenesten, som byttes der |
| `EMAIL_HOST_PASSWORD` | — | SMTP | Brukes bare lokalt |

Ikke hemmelige, røres ikke: `OFFSITE_S3_BUCKET`, `_REGION`, `_ENDPOINT`, `KART_URL`, `PORTAL_MILJO`,
`AHASEND_ACCOUNT_ID`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.

### Kartet — kart.sanitet.net og testkart.sanitet.net

| Variabel | Lages med | Åpner | Når den byttes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | `token_urlsafe(64)` | Sesjoner, aktiveringslenker, «husk denne enheten» | Alle logges ut av kartet |
| `DATABASE_URL` | — | Kartets database | Referanse, som i portalen (§5.6) |
| `PORTAL_HMAC_NOKKEL` | = portalens `KART_HMAC_NOKKEL` | Se portalen | `PORTAL_HMAC_NOKKEL_FORRIGE` tar imot den gamle mens portalen byttes (§5.5) |
| `PORTAL_INNLOGGING_NOKKEL` | = portalens `KART_INNLOGGING_NOKKEL` | Se portalen | `PORTAL_INNLOGGING_NOKKEL_FORRIGE`, som over |
| `MAPTILER_NOKKEL` | MapTiler-kontoen | Kartfliser på vår kvote | Én nøkkel for begge miljøene, låst til `*.sanitet.net`. Sendes uansett til nettleseren, så den er den minst verdifulle |

### Kontoer utenfor Railway

GitHub (Railway logger inn med den: bytt passord, se over 2FA og *Settings → Applications*),
Scaleway-konsollen, AhaSend, MapTiler, passordbehandleren selv.

---

## 3. Lag alle nøklene på én gang

Kjør på **din egen PC**. Lagre som `nye_nokler.py`, kjør `python nye_nokler.py`, og kopier
utskriften rett inn i passordbehandleren som én post, «Nøkler etter <hendelse> <dato>».
Bare standardbiblioteket.

```python
"""Nye hemmeligheter etter en mulig lekkasje.

Kjør lokalt. Lim aldri resultatet inn i en chat, en e-post eller en commit:
rett i passordbehandleren, og derfra i Railway.

Tegnene er A–Z, a–z, 0–9, «-» og «_» (eller hex): ingen «$», «{» eller
anførselstegn, som Railway eller et skall kan tolke, og ingen tegn som må
kodes i en URL — databasepassordet settes inn i DATABASE_URL.
"""
import secrets


def django_secret_key() -> str:
    # Portalen krever minst 50 tegn; 64 byte gir 86 tegn.
    return secrets.token_urlsafe(64)


def backupnokkel() -> str:
    # core/offsite.py krever minst 32 tegn; 48 byte gir 64 tegn.
    return secrets.token_urlsafe(48)


def hmac_nokkel() -> str:
    # 32 tilfeldige byte som hex (64 tegn).
    return secrets.token_hex(32)


def databasepassord() -> str:
    # 32 byte gir 43 tegn. Lengden brukes som kontroll i runbookens §5.6.
    return secrets.token_urlsafe(32)


for miljo in ('PROD (main)', 'STAGING'):
    innlogging = hmac_nokkel()
    posisjon = hmac_nokkel()
    print(f'\n========== {miljo} ==========')
    print('\n-- Portalen (sanitetsportalen) --')
    print(f'SECRET_KEY={django_secret_key()}')
    print(f'KART_INNLOGGING_NOKKEL={innlogging}')
    print(f'KART_HMAC_NOKKEL={posisjon}')
    if miljo.startswith('PROD'):
        # Bare prod har offsite-backup.
        print(f'OFFSITE_BACKUP_KEY={backupnokkel()}')
    print(f'POSTGRES_PASSWORD (portalens Postgres-tjeneste)={databasepassord()}')
    print('\n-- Kartet (kart-sanitet) — SAMME verdier som portalen der det står --')
    print(f'DJANGO_SECRET_KEY={django_secret_key()}')
    print(f'PORTAL_INNLOGGING_NOKKEL={innlogging}   # = KART_INNLOGGING_NOKKEL over')
    print(f'PORTAL_HMAC_NOKKEL={posisjon}   # = KART_HMAC_NOKKEL over')
    print(f'POSTGRES_PASSWORD (kartets Postgres-tjeneste)={databasepassord()}')

print('\nIkke laget her (lages hos leverandøren): OFFSITE_S3_ACCESS_KEY/SECRET_KEY')
print('(Scaleway), AHASEND_API_KEY (AhaSend), MAPTILER_NOKKEL (MapTiler).')
```

Hver nøkkel er unik per miljø. **Samme verdi to steder er bare riktig for parene** mellom
portalen og kartet i *samme* miljø, og skriptet skriver dem ut slik.

---

## 4. Før du endrer noe i Railway — fire kontroller

1. **Virker deploy?** Gjør en ufarlig variabelendring på portalens staging (f.eks. legg til
   `ROTASJON_TEST=1`) og se at det kommer en ny deployment som blir grønn. Under hendelsen 22. okt.
   var bygg stanset i timevis: en variabel som lagres i den tilstanden, gjelder ikke før neste
   vellykkede deploy, og alt ser riktig ut i dashbordet mens appen kjører på de gamle verdiene.
2. **Er `DATABASE_URL` en referanse overalt?** Raw Editor på web-tjenesten — og i portalen også
   på **cron-tjenestene** — skal vise `DATABASE_URL="${{Postgres.DATABASE_URL}}"`. En innlimt kopi
   blir stående igjen med det gamle passordet, og cron-jobbene feiler i stillhet.
3. **Leser tjenesten oppsettet du tror?** Kartet: `railway.json` gjelder bare der tjenesten har
   tatt den i bruk — testkart hadde aldri gjort det (22. okt.), og Railway slutter å lese fila
   01.12.2026 (kartets `TODO.md`). Se at Settings har bygge-, start- og pre-deploy-kommando.
4. **Restart eller Redeploy?** **Restart** bruker variablene deployment-en ble laget med.
   **Redeploy** henter de nye. I denne runbooken står det alltid Redeploy.

---

## 5. Rotasjonen, trinn for trinn

Rekkefølgen er med vilje: det som ikke tar ned noe først, databasen sent, backupnøkkelen sist
(den skal verifiseres etterpå).

### 5.1 Portal staging og kart staging, så prod

Hele §5.2–5.6 gjøres først for staging (testportal + testkart), og verifiseres med §8. Så prod.

### 5.2 AhaSend og S3 inn i portalen (prod)

Lim inn de nye verdiene fra §1 i `AHASEND_API_KEY`, `OFFSITE_S3_ACCESS_KEY` og
`OFFSITE_S3_SECRET_KEY` → Redeploy web. Kontroll: `/admin/backup/` → kortet «Offsite-kopi
(Scaleway)» skal si «Aktiv»; ta en manuell backup av én modul og se «1 fil lastet opp».

### 5.3 `SECRET_KEY` (portalen) og `DJANGO_SECRET_KEY` (kartet)

Ny verdi → Redeploy (portalen: web og cron). **Alle logges ut**, og «Session data corrupted» i
loggen etterpå er gamle informasjonskapsler som avvises — ufarlig. Send utestående invitasjoner
på nytt fra `/admin/brukere/<id>/` («Send invitasjon på nytt»).

### 5.4 Fingeravtrykk — sammenligne uten å vise

Når du må vite om to steder har samme verdi, sammenlign de åtte første tegnene av SHA-256:

```sh
# I en Railway-konsoll (Linux):
printf '%s' "$NAVN_PAA_VARIABELEN" | sha256sum | cut -c1-8
```

```powershell
# Lokalt i PowerShell, for verdien i passordbehandleren (lim inn mellom anførselstegnene):
$v = "VERDIEN"; (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($v))) -Algorithm SHA256).Hash.Substring(0,8).ToLower(); Remove-Variable v
```

Åtte tegn av en hash avslører ikke en tilfeldig nøkkel, og kan trygt limes inn i en chat.

### 5.5 Nøkkelparene mellom portalen og kartet (per miljø)

Kartet godtar en forrige nøkkel mens portalen byttes, så ingenting faller ut i mellomtiden.

1. **Kartet:** flytt dagens verdier til `PORTAL_HMAC_NOKKEL_FORRIGE` og
   `PORTAL_INNLOGGING_NOKKEL_FORRIGE`, sett de nye i `PORTAL_HMAC_NOKKEL` og
   `PORTAL_INNLOGGING_NOKKEL` → Redeploy.
2. **Portalen:** sett de samme nye verdiene i `KART_HMAC_NOKKEL` og `KART_INNLOGGING_NOKKEL` →
   Redeploy.
3. **Prøv:** «Åpne kartet» fra KO, og «Send posisjon» fra en bil eller et lag (§8).
4. **Kartet:** tøm begge `_FORRIGE` → Redeploy. *Ved en lekkasje gjøres dette samme dag* — den
   gamle nøkkelen er nettopp den som kan være kjent. (Ved en rutinerotasjon kan den stå et døgn.)

### 5.6 Databasepassordet (gjentas for hvert av de fire miljøene)

**Det viktigste vi lærte 22. okt.:** passordet bor på tre steder, og hvert av dem oppdateres for
seg. Kartet var nede i nesten åtte timer fordi de tre ikke stemte.

| Hvor | Får ny verdi når |
|---|---|
| Variabelen `POSTGRES_PASSWORD` på Postgres-tjenesten | Du lagrer den |
| Postgres-*containeren* (det konsollet ser) | Postgres-tjenesten redeployes |
| Databasen selv | Du kjører `ALTER USER` |

Appen får variabelen gjennom `${{Postgres.DATABASE_URL}}` først når **appen** redeployes.

**Endre `POSTGRES_PASSWORD` alene endrer ikke passordet i databasen** — variabelen leses bare når
basen opprettes.

Gjør dette, i denne rekkefølgen, uten pause mellom trinn 5 og 6 (portal prod: utenom vakt, og
ta en backup først med `python manage.py backup_kjor --alle`):

1. **Nytt passord** fra skriptet i §3 (43 tegn) — eller alene:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. **Postgres-tjenesten → Variables → Raw Editor:** bytt verdien i `POSTGRES_PASSWORD="…"`.
   Ingen mellomrom eller linjeskift innenfor anførselstegnene. Lagre, og ta i bruk endringen hvis
   Railway spør. Se samtidig at `DATABASE_URL` der er bygget av `${{POSTGRES_PASSWORD}}`:
   `postgresql://${{PGUSER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{PGDATABASE}}`.
3. **Redeploy Postgres-tjenesten** og vent til den er grønn. Dataene står på volumet. Appen
   har et kort avbrudd mens basen starter.
4. **Åpne et *nytt* konsoll** på Postgres-tjenesten (et gammelt har gamle variabler):
   ```sh
   printf '%s' "$POSTGRES_PASSWORD" | wc -c
   ```
   Skal gi **43**. Noe annet: containeren har ikke fått verdien — **stopp**, og gjør trinn 3 igjen.
5. **Sett passordet i basen** — én linje fra `root@…#`-prompten, *ikke* inne i psql:
   ```sh
   printf '%s\n' "SET log_statement = 'none';" '\getenv pw POSTGRES_PASSWORD' "ALTER USER postgres WITH PASSWORD :'pw';" | psql -h /var/run/postgresql -U postgres
   ```
   Forventet: `SET` og `ALTER ROLE`. Linja henter passordet fra miljøvariabelen, så det limes
   aldri inn og havner verken i psql-historikken eller i Postgres-loggen. Bekreft over nettverket,
   slik appen kobler til:
   ```sh
   psql -c "select 1;"
   ```
   Forventet: en tabell med `1`.
6. **Redeploy appen med en gang** — fra trinn 5 avvises appens *nye* tilkoblinger (portalen
   holder eksisterende i opptil 10 minutter). Portalen: web **og** cron-tjenestene. Kartet: web.
7. **Kontroll:** §8.

**Når det går galt:**

| Du ser | Betyr | Gjør |
|---|---|---|
| `password authentication failed for user "postgres"` i appens logg | Appen og basen har ulikt passord | Trinn 4 i et nytt konsoll. 43: gjør trinn 5–6 igjen. Annet tall: tilbake til trinn 3 |
| `railway-#` som prompt | Du står inne i psql midt i en setning | Ctrl+C, `\q`, kjør linja fra `root@…#` |
| `\getenv: extra argument "ALTER" ignored` | Konsollet slo sammen flere innlimte linjer til én | Bruk `printf`-linja i trinn 5, som er én linje |
| `q: command not found` | `\q` skrevet i skallet, ikke i psql | Ufarlig |
| `invalid command \getenv` | psql eldre enn 15 | Stopp og finn en annen vei — ikke lim inn passordet i `\password`; det bommet 22. okt. |
| `psql -U postgres` avvises med passordfeil | `PGHOST` peker på nettverket | `psql -h /var/run/postgresql -U postgres` (socketen slipper inn uten passord) |

### 5.7 `OFFSITE_BACKUP_KEY` (bare portal prod)

1. **Merk den gamle nøkkelen** i passordbehandleren med datoen den sluttet å gjelde. Den trengs
   for å lese hver backup tatt før byttet, i inntil 730 dager.
2. Ny verdi → Redeploy web.
3. `python manage.py backup_kjor --alle`, så `python manage.py verifiser_backup`.
   `/admin/backup/` skal vise en ny opplasting med tidspunkt.
4. **En backup fra før byttet** krever den gamle nøkkelen: sett `OFFSITE_BACKUP_KEY` midlertidig
   tilbake mens du kjører `python manage.py gjenopprett`, og sett den nye tilbake etterpå. Portalen
   kjenner bare én nøkkel om gangen (eget punkt i `TODO.md`).

### 5.8 MapTiler

Ny nøkkel i MapTiler-kontoen, med «Allowed HTTP origins» `*.sanitet.net` → `MAPTILER_NOKKEL` på
kartet i begge miljøer → Redeploy → trekk tilbake den gamle. Kontroll: bakgrunnskartet «Flyfoto og
satellitt» vises.

### 5.9 Til slutt: brukernes passord

Når `SECRET_KEY` er byttet: `/admin/brukere/` → **«Krev passordbytte for alle»**. Alle personlige
kontoer med passord logges ut og må velge nytt ved neste innlogging. Delte kontoer (biler), frosne
kontoer, kontoer uten passord og din egen er ikke med — bytt ditt under «Min profil», og bilenes
for hånd. Én bruker: brukersiden → «Krev passordbytte (logg ut nå)». Kartets egne kontoer har ingen
slik knapp ennå (`TODO.md`).

---

## 6. Loggene — hvem har vært inne?

### Scaleway (backupbøtta)

Første gang tar dette tid; gjør det før loggene er eldre enn 7 dager.

1. **Rettigheter:** konsollen → organisasjonen øverst til høyre → IAM → Users. «Owner» holder.
   Ellers trengs `ObservabilityReadOnly`.
2. **Grafana mangler ofte datakilden for `nl-ams`** («No data» med røde trekanter). Rettes med
   Scaleways CLI, fra github.com/scaleway/scaleway-cli → Releases (`…_windows_amd64.exe`; sjekk
   `Get-FileHash` mot verdien på siden før du kjører den):
   1. IAM → API keys → **Generate API key** for deg selv, utløp **1 dag**.
   2. I PowerShell — variablene i stedet for `scw init`, som avviste innliming i det skjulte feltet:
      ```powershell
      $env:SCW_SECRET_KEY = "secret key (fem grupper med bindestrek)"
      $env:SCW_ACCESS_KEY = "access key (begynner med SCW)"
      $env:SCW_DEFAULT_PROJECT_ID = "prosjekt-id fra Project settings"
      $env:SCW_DEFAULT_REGION = "nl-ams"
      .\scw.exe cockpit grafana sync-data-sources project-id=$env:SCW_DEFAULT_PROJECT_ID
      ```
   3. **Rydd etterpå:** slett API-nøkkelen i IAM, og
      `Remove-Item (Get-PSReadLineOption).HistorySavePath`.
3. **Spørringen:** Cockpit → «Access Grafana» → ☰ → Explore → datakilden med «Logs» og
   `nl-ams` → **Code** → `{resource_type="object_storage_bucket"}` → **Last 7 days** → Run query.
4. **Les:**
   - `ListObjects` fra en IP som ikke er din eller Railways er det du leter etter. **`403` er
     avvist.** Den lekkede nøkkelen hadde listerett, så et avvist forsøk brukte ikke den.
   - **Operasjoner på enkeltfiler logges ikke** (`GetObject` på en testfil dukket aldri opp
     22. okt.). Uten en vellykket listing er filnavnene — tidsstemplet til sekundet — ikke til
     å gjette.
5. **Skjermbilde** av spørring, tidsrom og resultat til avviksloggen.

### Railway og appene

- **Network egress** per tjeneste (§1 punkt 4).
- Portalens egne spor ligger i databasen: `/admin/auditlog/` og innloggingsloggen.
- En nettside som får tusenvis av `404` på `/.env`, `/.git/config` og `wp-login.php` er vanlig
  skanning av hele internett, ikke et angrep på oss. Det som teller er `2xx` på noe som krever
  innlogging, og **`POST`** mot innlogging.

---

## 7. Avvik og varsling

**Kverneland Røde Kors er behandlingsansvarlig; systemansvarlig er databehandler.** Plikten er
å **varsle korpset uten ugrunnet opphold** (GDPR art. 33(2)). Korpset vurderer og eventuelt melder
til Datatilsynet innen 72 timer fra korpset ble kjent med det.

1. Ny seksjon i `docs/AVVIKSLOGG.md` etter mønsteret fra 22. okt. 2026: hva skjedde, hva var
   eksponert, hvilke personopplysninger, undersøkelser, tiltak gjort, tiltak som gjenstår,
   vurdering (som *anbefaling*), lærdom.
2. Varsle korpset, og før dato og hvem i avviksloggen.
3. Før korpsets beslutning om Datatilsynet i samme seksjon.

---

## 8. Kontroll — alle fire miljøene

| Hva | Forventet |
|---|---|
| `https://portal.sanitet.net/healthz/` og `https://testportal.sanitet.net/healthz/` | `"db": {"ok": true}` og versjonen du deployet |
| `https://kart.sanitet.net/healthz` og `https://testkart.sanitet.net/healthz` | `ok` |
| `/konto/logg-inn/` og `/personvern/` på begge kartene | 200 — ikke 500. Healthz tegner ingen side; «Missing staticfiles manifest entry» viser seg bare her |
| `/admin/server-status/` (portalen) | Cron-jobbene ok etter neste kjøring |
| `/admin/backup/` (portal prod) | Offsite «Aktiv», ny opplasting, oppbevaringsreglene 730/90 dager |
| «Åpne kartet» fra KO, og «Send posisjon» | Du kommer inn i kartet; posisjonen vises der |
| E-post (send en invitasjon til deg selv) | Kommer fram — AhaSend-nøkkelen virker |
| Bakgrunnskartet «Flyfoto og satellitt» | Vises — MapTiler-nøkkelen virker |

---

## 9. Fallgruvene fra 22. okt. 2026 — kort

- **Deploy var stanset.** Alt så riktig ut i dashbordet, ingenting gjaldt. §4 punkt 1.
- **`POSTGRES_PASSWORD` endrer ikke databasen**, og konsollet viser ikke nødvendigvis det appen
  får. §5.6 med lengdesjekken.
- **Restart henter ikke nye variabler.** Redeploy gjør det.
- **Innliming bommer** — i `\password`, og i `scw init`s skjulte felt. Hent verdien fra en
  miljøvariabel (`\getenv`) eller lim inn der du ser den.
- **Konsollet slår sammen innlimte linjer.** Kommandoene her er laget som én linje der det betyr
  noe.
- **Testkart leste ikke `railway.json`**, og ga 500 på alle sider uten statiske filer mens
  healthz var grønn. §4 punkt 3 og §8.
- **CI kan bli rød av noe nytt i verden** — pip-audit fant 24 sårbarheter i pillow samme dag.
  Det er ikke rotasjonens feil, men det stopper deployen til det er rettet.
