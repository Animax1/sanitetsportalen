# Deploy-veiledning – Sanitetsportalen

Denne guiden tar deg gjennom alt du trenger for å kjøre portalen live på Railway.
Du trenger ikke være utvikler – følg stegene i rekkefølge.

> **Sist gjennomgått 14. sep. 2026**, som del av dokumentrunden etter at det portalvide
> flyttet til `core` og backupen ble lagt om. Kapittel 5 sa fram til da at «en backup skal
> kun inneholde pasientdata – aldri brukere, passord eller audit-logg», og forklarte
> hvordan du laster ned fila for å kontrollere det. Begge deler er nå feil: den hele
> databasebackupen inneholder brukere, MFA-hemmeligheter og logg **med vilje**, og
> backupfiler skal ikke lastes ned i det hele tatt. Se kapittel 5.

---

## 1. Forutsetninger

Før du begynner, sørg for at du har:

- En **GitHub-konto** med portalens kode i et repository
- En **Railway-konto** (gratis å opprette på [railway.app](https://railway.app))
- En **Scaleway-konto** hvis du vil ha offsite-backup (kapittel 6). Portalen kjører fint
  uten, men da ligger alle backupene på ett sted

---

## 2. Oppsett i Railway

### 2a. Nytt prosjekt fra GitHub

1. Logg inn på [railway.app](https://railway.app)
2. Klikk **New Project** → **Deploy from GitHub repo**
3. Velg ditt repository fra listen
4. Railway oppdager Django automatisk og starter en første deploy
   (den vil feile inntil miljøvariabler og database er satt opp – det er normalt)

### 2b. Legg til PostgreSQL

1. I prosjektet, klikk **+ New** → **Database** → **Add PostgreSQL**
2. Railway oppretter en PostgreSQL-tjeneste automatisk

**Sett `DATABASE_URL` som referansen `${{Postgres.DATABASE_URL}}`, ikke som en kopiert
verdi.** En kopi blir stående igjen når passordet roteres, og da feiler bare cron-jobbene
mens websiden går videre som før – altså en stille feil du oppdager når du trenger jobben.

Portalen **nekter å starte** på Railway hvis `DATABASE_URL` ikke peker på PostgreSQL.
Sjekken står i `settings.py` og henger på `RAILWAY_ENVIRONMENT`. Uten den ville
`dj_database_url` falt stille tilbake til en SQLite-fil i den flyktige containeren, og da
hadde `purge_old_logs` talt null rader, skrevet «Slettet 0 audit-logger» og avsluttet med
kode 0 – en grønn jobb som aldri håndhever sletteplikten.

### 2c. Sett miljøvariabler

Klikk på **web**-tjenesten din → **Variables**-fanen → **New Variable**.

**Må settes:**

| Variabel | Verdi | Merknad |
|---|---|---|
| `SECRET_KEY` | Minst 50 tilfeldige tegn | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Referanse, ikke kopi – se 2b |
| `ALLOWED_HOSTS` | `ditt-domene.up.railway.app` | Oppdater etter at domenet er generert |
| `CSRF_TRUSTED_ORIGINS` | `https://ditt-domene.up.railway.app` | Må matche `ALLOWED_HOSTS`, med `https://` |
| `DEBUG` | `false` | Alltid `false` i produksjon |
| `BACKUP_DIR` | `/data/backups` | Må peke på Volume-stien, se 2d |
| `RATELIMIT_ENABLE` | `true` | Nødbryter, se kapittel 8 |

**E-post – kreves for feilvarsel og for vaktlista på e-post:**

| Variabel | Verdi | Merknad |
|---|---|---|
| `ADMINS` | `Navn:epost@eksempel.no` | Komma-separert for flere. Mottakere av feilvarsel |
| `DEFAULT_FROM_EMAIL` | `noreply@ditt-domene.no` | Avsender |
| `AHASEND_API_KEY` | Fra AHASend | |
| `AHASEND_ACCOUNT_ID` | Fra AHASend | |

> **Railway sperrer utgående SMTP på alle porter.** Målt fra containeren 22. aug. 2026:
> 587, 2525, 465 og 25 er stengt, 443 er åpen. Derfor går e-post gjennom AHASends
> HTTP-API (`core/mail_backends.py`), ikke SMTP. Å bytte SMTP-leverandør treffer samme
> vegg – det er en plattformpolicy, ikke noe ved AHASend. `EMAIL_HOST` og de andre
> SMTP-variablene leses fortsatt, men brukes bare lokalt.

**Valgfritt:**

| Variabel | Standard | Formål |
|---|---|---|
| `REDIS_URL` | *(tom)* | Aktiverer Redis-cache. Uten den brukes LocMemCache |
| `LOG_LEVEL` | `INFO` | Loggnivå for rot-loggeren |
| `EMAIL_TIMEOUT` | `10` | Tidsgrense for utsending i sekunder. **Må aldri være `None`** |
| `WEB_WORKERS` | `1` | Gunicorn-prosesser. Se `docs/RUNBOOK_VAKT.md` §4 før du øker |
| `WEB_THREADS` | `4` | Tråder per prosess |
| `WEB_MAX_REQUESTS` | `1000` | Prosessen resirkuleres etter så mange forespørsler |

Offsite-variablene står i kapittel 6.

### 2d. Opprette Volume for backup-lagring

Backupfiler må ligge på et persistert volum – ellers slettes de hver gang appen deployes.

1. Trykk **Ctrl+K** i Railway for å åpne kommandopaletten
2. Skriv **Create Volume** og velg det
3. Sett **Mount Path** til `/data`
4. Koble volumet til **web**-tjenesten
5. Sett `BACKUP_DIR=/data/backups` (undermappen opprettes ved første backup)

Volumets navn er likegyldig; mount path (`/data`) er det som teller.

> **Et Railway-volum kan bare henge på én tjeneste**, og det er web-tjenesten. Det er
> grunnen til at backup-klokka er en tråd i web-prosessen og ikke en cron-tjeneste – se
> kapittel 5.

---

## 3. Første deploy og verifisering

### Procfile

Sjekk at `Procfile` i rotkatalogen inneholder:

```
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: gunicorn myproject.wsgi --workers ${WEB_WORKERS:-1} --threads ${WEB_THREADS:-4} --max-requests ${WEB_MAX_REQUESTS:-1000} --max-requests-jitter 50 --bind 0.0.0.0:$PORT --timeout 60
```

`release` kjører **før** Railway bytter container. Det betyr at det finnes et vindu der
gammel kode serverer mot nytt skjema – se kapittel 9 om hva det betyr for migrasjoner.

`nixpacks.toml` legger til ett byggsteg: `python core/skriv_bygg.py` stempler bygget med
commit-SHA og klokkeslett, slik at footeren kan si hvilket bygg som kjører.

### Generer domene

1. Web-tjenesten → **Settings** → **Networking** → **Generate Domain**
2. Oppdater `ALLOWED_HOSTS` og `CSRF_TRUSTED_ORIGINS` med domenet

### Sjekk at portalen kjører

- Åpne domenet: du skal se innloggingssiden
- `GET /healthz/` skal svare – det er også Railways health-check
- **Nederst på hver portalside står byggnummeret**: commit-SHA og dato. Det er svaret på
  «er dette den nye koden, eller er det cachen?»

---

## 4. Opprette admin-bruker

Railway-shellen har ingen terminal, så kommandoen kjøres direkte:

```bash
python manage.py create_admin --username admin --password "velg-et-sikkert-passord"
```

Kontoen må bytte passord ved første innlogging.

---

## 5. Backup

### To lag, og de svarer på hvert sitt spørsmål

| Lag | Hva | Hvor |
|---|---|---|
| **Modulfiler** | Åtte handlere: `portal`, `patients`, `arkiv`, `oppdrag`, `oppdrag_arkiv`, `vaktliste`, `ko`, `backlog` – én per modul | Volumet, og offsite under `backups/` |
| **Hel database** | `full` – alt unntatt sesjoner, contenttypes, permissions og backup-metadata | Volumet, og offsite under `full/` |

**Den hele fila inneholder brukere, passordhasher, MFA-hemmeligheter og audit-logg, med
vilje.** Den er selvbærende, og det er poenget: den kan gjenopprettes i en tom base der
det ikke finnes noen å logge inn som.

### Backupfilene skal ikke finnes andre steder enn hos Scaleway eller på Railway

**Det finnes ingen nedlastingsknapp, og det er en beslutning – ikke en mangel.** En
`.json.gz` med hele pasientregisteret i nedlastingsmappa er en helseopplysningsdump
utenfor portalens kontroll, og den hele fila bærer i tillegg passordhasher og
TOTP-hemmeligheter. Gjelder også modulfilene.

Vil du kontrollere *innholdet* i backupene, bruk kommandoen som gjør det uten å flytte
fila noe sted:

```bash
python manage.py verifiser_backup
```

Den laster filene fra volumet inn i en engangsbase og sammenligner radene mot det filene
inneholder. Testsuiten svarer på om koden virker; denne på om innholdet gjør det.

### Klokka er en tråd, ikke en cron-jobb

Automatisk backup styres av `core.Backupplan` – tre moduser (`av`, `ved_endring`,
`alltid`) og fritt intervall, satt per modul på `/portal-admin/backup/`.

Klokka (`core/backup/klokke.py`) er en **tråd i web-prosessen**, fordi volumet bare kan
henge på web-tjenesten. En cron-tjeneste som tok backup ville skrevet fila til sitt eget
flyktige containerfilsystem, opprettet databaseraden, og forsvunnet med fila – og
kollapssperra foran arkivsletting spør bare etter raden. Da ville den åpnet seg på
spøkelsesbackuper.

`BackupSchedulerMiddleware` står igjen som reservenett gjennom samme `kjor_forfalte()`,
og er det eneste stedet som varsler om at tråden har stoppet.

**Du trenger ikke opprette en cron-tjeneste for backup.** Manuell kjøring:
`python manage.py backup_kjor`.

---

## 6. Offsite-backup til Scaleway (valgfritt, men anbefalt)

Uten dette ligger alle backupene på ett sted, og et tapt Railway-prosjekt tar dem med seg.

| Variabel | Merknad |
|---|---|
| `OFFSITE_S3_BUCKET` | Bucketnavn |
| `OFFSITE_S3_REGION` | Standard `nl-ams` |
| `OFFSITE_S3_ENDPOINT` | Standard `https://s3.nl-ams.scw.cloud` |
| `OFFSITE_S3_ACCESS_KEY` | |
| `OFFSITE_S3_SECRET_KEY` | |
| `OFFSITE_BACKUP_KEY` | Krypteringsnøkkelen |

**`OFFSITE_BACKUP_KEY` skal også ligge i en passordbehandler utenfor Railway.** Uten den
er bucketen uleselig – og det er meningen. Mister du både Railway og nøkkelen, har du
kryptert søppel.

Uten variablene er modulen **inert**: ingen feil, ingen forsøk. Staging og lokal utvikling
har ingen offsite-backup, med vilje. Hvilke variabler som mangler står på
`/portal-admin/backup/`.

### Oppbevaringstider håndheves av Scaleway, ikke av portalen

Nøkkelen har ikke sletterett. Sett to livssyklusregler i bucketen, på **nøyaktig** disse
prefiksene:

| Prefiks | Oppbevaring |
|---|---|
| `backups/` | 730 dager (modulfilene) |
| `full/` | 90 dager (hele databasen) |

Portalen leser reglene *tilbake* fra bucketen og viser avvik på `/portal-admin/backup/`.
`/full` er ikke `full/`, og en regel som treffer ingenting er en oppbevaringstid som
stille ble uendelig.

Filene komprimeres først og krypteres så – AES-256-GCM. Rekkefølgen er ikke vilkårlig:
chiffertekst lar seg ikke komprimere, mens gzip på dumpdata-JSON gir 5–15 % av rå
størrelse.

---

## 7. Cron-jobbene

**To** jobber skal settes opp som egne Railway-tjenester fra samme repo, med
`restartPolicy: NEVER`:

| Tjeneste | Start Command | Plan |
|---|---|---|
| `purge_old_logs` | `python manage.py purge_old_logs` | `0 0 * * SUN` |
| `kollaps_arkiv` | `python manage.py kollaps_arkiv` | `0 4 1 * *` |

**`startCommand` må settes eksplisitt.** Uten den arver tjenesten `Procfile`-ens
`web:`-linje og starter gunicorn i stedet for kommandoen – jobben gjør da ingenting og
feiler ikke. Begge manglet den i første oppsett.

Begge rører bare databasen og trenger derfor ikke volumet. Siste kjøring vises på
`/portal-admin/server-status/`, og «Aldri» betyr at jobben ikke har kjørt én eneste gang.

Tørrkjør før første skarpe kjøring: `python manage.py kollaps_arkiv --dry-run`.

---

## 8. Nødbryter for rate-limiting

Blokkerer rate-limitingen legitime brukere (mange mislykkede forsøk fra samme kontor-IP):

1. Web-tjenestens **Variables** → sett `RATELIMIT_ENABLE` til `false`
2. Railway redeployer automatisk
3. Løs den underliggende årsaken, og sett den tilbake til `true`

Verdien leses uavhengig av store og små bokstaver. Fram til 13. sep. 2026 ble den
sammenlignet med `== 'True'`, og da sto rate-limitingen av i prod uten at noen visste det.

---

## 9. Oppdateringsflyt

Portalen har **to miljøer**:

| Gren | Miljø |
|---|---|
| `staging` | Staging – testes her først. Het `rollemodell` til 25. sep. 2026 |
| `main` | Produksjon |

```bash
git push origin HEAD:staging         # staging
# verifiser på staging-domenet
git push origin HEAD:main            # prod
```

Railway auto-deployer fra begge. Følg prosessen under **Deployments**, og sammenlign
**byggnummeret i footeren** med commit-en du pushet – de skal stemme.

### Migrasjoner og release-vinduet

`release` kjører før containerbyttet, så mellom `migrate` og byttet står **gammel kode og
serverer mot nytt skjema**. Det har to konsekvenser å kjenne:

- **Ikke døp om tabeller som gammel kode leser.** `core.AppSetting` og `core.Backup`
  beholdt derfor `patients_appsetting` og `patients_backup` da modellene flyttet – en
  omdøping ville gitt 500 på tilnærmet hver forespørsel i vinduet, fordi tabellen bærer
  pekeren til aktiv vakt.
- **En migrasjon som først skriver rader og deretter endrer skjema må tømme PostgreSQLs
  triggerkø imellom.** Ellers avvises `ALTER TABLE` og release-fasen crash-looper
  containeren. SQLite har ingen utsatte triggere, så testsuiten er grønn uansett – det tok
  ned deployen 30. aug. 2026. Se `CLAUDE.md`, «Migrasjoner».

---

## 10. Hvis deployen knekker

Railway deployer automatisk ved push, og en dårlig commit er i prod på noen minutter.

### Raskest: rull tilbake i Railway

1. Web-tjenesten → **Deployments**
2. Finn siste deploy som virket
3. **⋮** → **Redeploy**

Dette bygger den commit-en på nytt. Ingen kode trengs, og det er raskeste vei tilbake.

> **Men det ruller ikke tilbake databasen.** Kjørte den nye deployen en migrasjon som
> endret skjemaet, står basen igjen i den nye formen mens koden er den gamle. Les
> avsnittet under før du redeployer.

### Har det kjørt en migrasjon?

Se i **Deployments**-loggen fra release-fasen. Tre tilfeller:

| Migrasjonen | Rollback |
|---|---|
| Ingen migrasjon kjørte | Redeploy er nok |
| Ren tilstandsmigrasjon (`database_operations=[]`) | Redeploy er nok – ingen SQL kjørte |
| Endret skjemaet | Redeploy alene er **ikke** nok |

I det tredje tilfellet: rull migrasjonen tilbake *før* du redeployer, hvis den er
reversibel:

```bash
python manage.py migrate <app> <forrige_migrasjonsnavn>
```

Er den ikke reversibel, er backupen veien tilbake – se `docs/RUNBOOK_VAKT.md` §8b.

### Rett vei framover er som regel bedre enn bakover

En ny commit som retter feilen er ofte tryggere enn et tilbakerull, særlig hvis
migrasjonen har skrevet data. Rull tilbake når portalen er **nede**; rett framover når den
virker med en feil.

### Under vakt

Ikke deploy under vakt. Går det galt likevel: `docs/RUNBOOK_VAKT.md` har terskler,
nedbremsing og nødbrytere.

---

## 11. Avhengigheter

`requirements.txt` er **låst med hasher** og er den Railway installerer. Den redigeres
ikke for hånd.

```bash
# Ny eller oppdatert pakke:
#  1. legg den i requirements.in
#  2. kjør:
pip-compile --generate-hashes --strip-extras
#  3. commit begge filene
```

`requirements.in` er ønskene, `requirements.txt` er det `pip-compile` løste dem til. Uten
hasher kan en kompromittert pakke på PyPI bytte innhold under samme versjonsnummer.

---

## 12. Vanlige feil under deploy

### `DisallowedHost at /`
Oppdater `ALLOWED_HOSTS` med det genererte Railway-domenet.

### `CSRF verification failed`
Oppdater `CSRF_TRUSTED_ORIGINS` med `https://` + domenet.

### `ImproperlyConfigured: DATABASE_URL må peke på PostgreSQL`
`DATABASE_URL` mangler eller peker feil. Sett den som referansen
`${{Postgres.DATABASE_URL}}`. Sjekken er med vilje – se 2b.

### `Backup viser «Fil mangler på disk»`
`BACKUP_DIR` peker ikke til volumstien. Sjekk at volumet er koblet til web-tjenesten med
mount path `/data`, og at `BACKUP_DIR=/data/backups`.

### Offsite-backup skjer ikke
`/portal-admin/backup/` lister hvilke `OFFSITE_*`-variabler som mangler. Er ingen satt, er
modulen inert med vilje – det er normalt på staging.

### `Static files mangler (CSS/JS ikke lastet)`
Sjekk at `Procfile` har `collectstatic --noinput` i `release`. WhiteNoise hasher
filnavnene, så en gammel cache er aldri feil versjon – men trykk gjerne **Ctrl+F5**.

### Migreringer kjøres ikke
Sjekk `Procfile` og se etter feilmeldinger fra release-fasen i **Deployments**-loggen.

### Cron-jobben gjør ingenting og feiler ikke
`startCommand` mangler på tjenesten, så den kjører gunicorn i stedet. Se kapittel 7.
