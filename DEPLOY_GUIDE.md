# Deploy-veiledning – Pasientregistreringssystem

Denne guiden tar deg gjennom alt du trenger for å kjøre systemet live på Railway.
Du trenger ikke være utvikler – følg stegene i rekkefølge.

---

## 1. Forutsetninger

Før du begynner, sørg for at du har:

- En **GitHub-konto** med prosjektets kode i et repository
- En **Railway-konto** (gratis å opprette på [railway.app](https://railway.app))

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
3. Klikk på PostgreSQL-tjenesten → **Variables**-fanen → kopier verdien for `DATABASE_URL`
   (du trenger den i neste steg)

### 2c. Sett miljøvariabler

Klikk på **web**-tjenesten din (GitHub-deployen) → **Variables**-fanen → **New Variable**
og legg til følgende én for én:

| Variabel               | Verdi                                        | Merknad                                      |
|------------------------|----------------------------------------------|----------------------------------------------|
| `SECRET_KEY`           | Minst 50 tilfeldige tegn                     | Bruk en passordgenerator eller kjør `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DATABASE_URL`         | Kopier fra PostgreSQL-tjenestens Variables   | Starter som regel med `postgresql://`        |
| `ALLOWED_HOSTS`        | `ditt-domene.up.railway.app`                 | Oppdater etter at du har generert domene     |
| `CSRF_TRUSTED_ORIGINS` | `https://ditt-domene.up.railway.app`         | Må matche `ALLOWED_HOSTS` med https://       |
| `DEBUG`                | `false`                                      | Alltid `false` i produksjon                  |
| `BACKUP_DIR`           | `/data/backups`                              | Må peke på Volume-stien (se steg 2d)         |
| `RATELIMIT_ENABLE`     | `true`                                       | Aktiverer innloggings-rate-limiting          |

### 2d. Opprette Volume for backup-lagring

Backupfiler må ligge på et persistert volum – ellers slettes de hver gang appen deployes på nytt.

1. Trykk **Ctrl+K** i Railway-nettleseren for å åpne kommandopaletten
2. Skriv **Create Volume** og velg det
3. Sett **Mount Path** til `/data`
4. Koble volumet til **web**-tjenesten din (velg den i dropdown)
5. Sett miljøvariabelen `BACKUP_DIR=/data/backups` i web-tjenestens Variables
   (dette oppretter undermappen automatisk ved første backup)

Volumet heter gjerne noe som `backup` – navnet er ikke viktig, mount path (`/data`) er det som teller.

---

## 3. Første deploy og verifisering

### Procfile

Sjekk at `Procfile` i rotkatalogen inneholder følgende:

```
release: python manage.py migrate && python manage.py collectstatic --noinput
web: gunicorn myproject.wsgi --workers 1 --threads 4
```

`release`-kommandoen kjører automatisk av Railway **før** appen starter.
Det betyr at migreringer og statiske filer alltid er oppdaterte etter en deploy.

### Generer domene

1. Klikk på web-tjenesten → **Settings** → **Networking** → **Generate Domain**
2. Kopier domenenavnet (f.eks. `pasient-reg-prod.up.railway.app`)
3. Oppdater miljøvariablene `ALLOWED_HOSTS` og `CSRF_TRUSTED_ORIGINS` med dette domenet

### Sjekk at appen kjører

Åpne domenet i nettleseren. Du skal se innloggingssiden.
Hvis du ser en Django-feilside, sjekk **Deployments**-loggen i Railway for detaljer.

---

## 4. Opprette admin-bruker

Du har to muligheter:

### Alternativ A – Railway Shell (anbefalt)

1. Klikk på web-tjenesten → **Shell**-fanen
2. Skriv:

```bash
python manage.py create_admin --username admin --password "velg-et-sikkert-passord"
```

### Alternativ B – Miljøvariabler (automatisk ved deploy)

Legg til disse to variablene i web-tjenestens Variables:

| Variabel                    | Verdi                  |
|-----------------------------|------------------------|
| `DJANGO_SUPERUSER_USERNAME` | `admin`                |
| `DJANGO_SUPERUSER_PASSWORD` | Ditt valgte passord    |

Da kjøres `createsuperuser --noinput` automatisk ved neste deploy.
Du kan fjerne variablene igjen etterpå.

---

## 5. Backup-verifisering

### Volumet persisterer filer mellom deploys

Backupfiler lagres på Railway Volume under `/data/backups`.
Filer på volumet overlever nye deploys og omstart av tjenesten.
Filer **utenfor** volumet (f.eks. i `/app/`) slettes ved deploy.

### Sjekk at backupfilen ikke inneholder passord-hasher

En backup skal kun inneholde pasientdata – aldri brukere, passord eller audit-logg.
Slik verifiserer du dette i PowerShell etter å ha lastet ned en backup-fil:

```powershell
# Pakk ut den gzip-komprimerte JSON-filen
Expand-Archive -Path backup.json.gz -DestinationPath .
# (eller bruk 7-Zip hvis Expand-Archive ikke støtter .gz)

# Søk etter passord-hasher
Select-String -Path backup.json -Pattern "pbkdf2_|argon2"
```

Hvis søket ikke gir treff – alt er som det skal.
Hvis du finner `pbkdf2_` eller `argon2` i filen, er noe feil med `BACKUP_APPS`-konfigurasjonen.

### In-process scheduler – ingen separat cron-service trengs

Automatisk backup kjøres **inne i web-prosessen** via `BackupSchedulerMiddleware`.
Middlewaren sjekker ved hver innkommende forespørsel (maks én gang per 60 sekunder)
om det er på tide med en ny backup basert på `BackupConfig.interval_minutes`.
Hvis ja, startes backupen i en bakgrunnstråd uten å forsinke forespørselen.

Du trenger **ikke** å opprette en egen cron-service eller planlagt jobb i Railway.

---

## 6. Nødbryter for rate-limiting

Hvis innloggings-rate-limiting ved en feil blokkerer legitime brukere
(f.eks. etter mange mislykkede forsøk fra samme kontor-IP), kan du skru den av midlertidig:

1. Gå til web-tjenestens **Variables** i Railway
2. Sett `RATELIMIT_ENABLE` til `false`
3. Railway redeployer automatisk
4. Løs den underliggende årsaken, og sett `RATELIMIT_ENABLE` tilbake til `true`

---

## 7. Oppdateringsflyt

Slik oppdaterer du appen etter kodeendringer:

```powershell
# 1. Gjør endringene dine lokalt og commit
git add .
git commit -m "Beskrivelse av endringen"

# 2. Push til GitHub
git push origin main
```

Railway oppdager pushet automatisk og starter en ny deploy.
Du kan følge prosessen under **Deployments**-fanen i Railway.

Når deployen er ferdig: trykk **Ctrl+F5** i nettleseren for å tvinge en full oppdatering
(dette tømmer nettleserens cache av statiske filer).

---

## Vanlige feil under deploy

### `DisallowedHost at /`
Oppdater `ALLOWED_HOSTS` med det genererte Railway-domenet.

### `CSRF verification failed`
Oppdater `CSRF_TRUSTED_ORIGINS` med `https://` + det genererte Railway-domenet.

### `Backup viser «Fil mangler på disk»`
`BACKUP_DIR` peker ikke til Volume-stien. Sjekk at:
- Volumet er koblet til web-tjenesten med mount path `/data`
- `BACKUP_DIR` er satt til `/data/backups`

### `Static files mangler (CSS/JS ikke lastet)`
Sjekk at `Procfile` inneholder `collectstatic --noinput` i `release`-steget.

### Migreringer kjøres ikke
Sjekk at `Procfile` inneholder `python manage.py migrate` i `release`-steget,
og se i **Deployments**-loggen om det er feilmeldinger fra migreringen.
