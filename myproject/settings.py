"""
Django-innstillinger for pasientregistreringssystemet.
"""
import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

# ── Grunnleggende ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent



def _env_bool(navn, default):
    """Boolsk miljøvariabel, uavhengig av store og små bokstaver.

    Fram til 13. sep. 2026 sto det `== 'True'` her — og Railway hadde
    `RATELIMIT_ENABLE=true`, slik dokumentasjonen sa. Da ble verdien False, og
    rate-limitingen var av i prod uten at noe meldte fra. Konfigsjekken på
    server-status fant det. Alt som ligner på ja er ja; alt annet er nei.
    """
    verdi = os.environ.get(navn)
    if verdi is None or verdi.strip() == '':
        return default
    return verdi.strip().lower() in ('1', 'true', 'yes', 'on', 'ja')


DEBUG = _env_bool('DEBUG', False)

# SECRET_KEY signerer sesjonscookies, CSRF-tokens og MFA trust-cookies. Kjører
# produksjon på en kjent nøkkel, kan sesjoner og MFA-cookies forfalskes.
# Tidligere hadde variabelen en hardkodet fallback som slo inn stilltiende hvis
# miljøvariabelen manglet. Nå feiler oppstarten i stedet — høylytt og med én
# gang — når DEBUG er av. Fallbacken beholdes kun for lokal utvikling.
_PLACEHOLDER_SECRET_KEYS = {
    'change-me-in-production',
    'dev-only-ikke-bruk-i-prod-changeme123!',
}

SECRET_KEY = os.environ.get('SECRET_KEY', '').strip()

if not DEBUG:
    if not SECRET_KEY:
        raise ImproperlyConfigured(
            'SECRET_KEY mangler. Sett miljøvariabelen SECRET_KEY til en lang '
            'tilfeldig streng (50+ tegn) før oppstart med DEBUG=False. '
            'På Railway settes den under Variables.'
        )
    if SECRET_KEY in _PLACEHOLDER_SECRET_KEYS:
        raise ImproperlyConfigured(
            'SECRET_KEY er satt til en kjent eksempelverdi. Bytt den til en '
            'lang tilfeldig streng før oppstart med DEBUG=False.'
        )
    if len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            f'SECRET_KEY er {len(SECRET_KEY)} tegn. Den skal være minst 50 — '
            'meldingen over har sagt det lenge, men sjekket det ikke (13. sep. 2026).'
        )
elif not SECRET_KEY:
    SECRET_KEY = 'dev-only-ikke-bruk-i-prod-changeme123!'

# Den gamle offline-modusen (`OFFLINE_MODE`: laptop uten TLS, egen SQLite,
# CSRF åpen for LAN) ble lagt ned 13. sep. 2026. Reserven er vaktlista som
# fil på e-post og offline drift i nettleseren — se TEKNISK_DOKUMENTASJON §11.

# Sikker default: tillat kun localhost hvis miljøvariabel mangler.
# I produksjon settes ALLOWED_HOSTS via Railway Variables.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '.localhost,127.0.0.1').split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS_RAW = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in CSRF_TRUSTED_ORIGINS_RAW.split(',') if o.strip()]

# ── Applikasjoner ────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',         # Sanitetsportal-fellesprimitiver (BaseTimeStampedModel, validatorer, RBAC)
    'accounts',
    'patients',
    'statistikk',
    'oppdrag',
    'vaktliste',
    'ko',
    'backlog',
    'audit',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
]

# ── Mellomvare ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.MemoryLoggingMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'audit.middleware.RequestAuditMiddleware',
    'accounts.middleware.MustChangePasswordMiddleware',
    'accounts.middleware.DynamicSessionTimeoutMiddleware',
    # **Etter autentiseringen, før arbeidet** (16. sep. 2026): den trenger
    # `request.user` og `request.session`, og den skal notere at noen var her
    # også når viewet under svarer med en feil.
    'core.middleware.BrukerAktivitetMiddleware',
    'core.middleware.BackupSchedulerMiddleware',
    # Intervallsending av vaktlista som fil (13. sep. 2026) — samme klokke
    # som backup-planleggeren: trafikken driver den.
    'vaktliste.middleware.FilutsendingMiddleware',
    'core.middleware.SecurityHeadersMiddleware',
    'core.middleware.RequestMetricsMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

# ── Maler ────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.portal_modules',
                'core.context_processors.notification_unread_count',
                'core.context_processors.csp_nonce',
                'core.context_processors.tilgang',
                'core.context_processors.versjon',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# ── Database ─────────────────────────────────────────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}

# **En manglende DATABASE_URL på Railway skal krasje, ikke falle tilbake.**
#
# `dj_database_url.config()` faller tilbake til `default` når variabelen ikke
# finnes, og den fallbacken er en SQLite-fil i containeren. Lokalt er det
# riktig. På Railway er containeren flyktig, så filen er tom og forsvinner
# igjen — og det er *stille*: appen starter, migrasjonene «kjører», og
# ingenting feiler.
#
# Det farligste tilfellet er ikke websiden, som ville vist en tom portal og
# blitt oppdaget samme minutt. Det er cron-jobbene. `purge_old_logs` ville
# talt null rader i en tom base, skrevet «Slettet 0 audit-logger», og
# avsluttet med kode 0. En grønn jobb som aldri håndhever lagringstidene i
# A.9 — en feil som først oppdages den dagen noen spør hvorfor det ligger
# fire år med logger i basen.
#
# Samme mønster som SECRET_KEY-sjekken over: en feilkonfigurasjon i prod skal
# stoppe oppstarten høylytt og med én gang. Sjekken henger på
# `RAILWAY_ENVIRONMENT` og ikke på `DEBUG` — utenfor Railway er SQLite lov.
#
# **Ett unntak, og det er navngitt:** `verifiser_backup` lager en engangsbase for
# å laste backupfilene inn i den og telle radene. Den kjører underprosesser med
# `PORTAL_ENGANGSBASE=1`, og en flyktig SQLite-fil er nettopp det den vil ha —
# den skal aldri bli portalens base, og slettes når kommandoen er ferdig.
# Flagget settes av den ene kommandoen og skal aldri stå på en tjeneste.
if (os.environ.get('RAILWAY_ENVIRONMENT')
        and not os.environ.get('PORTAL_ENGANGSBASE')
        and 'sqlite' in DATABASES['default'].get('ENGINE', '')):
    raise ImproperlyConfigured(
        'DATABASE_URL mangler eller er ugyldig — Django falt tilbake til '
        'SQLite i containeren. På Railway er den filen tom og flyktig, og '
        'en cron-jobb mot den ville rapportert suksess uten å gjøre noe. '
        'Sett DATABASE_URL på tjenesten, helst som referansen '
        '${{Postgres.DATABASE_URL}} og ikke som en kopiert verdi — en kopi '
        'blir stående igjen når passordet roteres.'
    )

# ── Autentisering ─────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.CustomUser'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Brukernavn slås opp uten hensyn til store bokstaver. Mobiltastatur setter
# automatisk stor forbokstav i tekstfelt, så en konto som heter
# `kari.nordmann` blir `Kari.nordmann` ved innlogging — og Postgres skiller
# på det. Se accounts/backends.py for hvordan tvetydighet håndteres.
AUTHENTICATION_BACKENDS = [
    'accounts.backends.CaseInsensitiveModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Passord-hashing under testkjøring ────────────────────────────────────────
# Produksjon bruker Djangos standard (PBKDF2 med 1 000 000 iterasjoner). Det er
# riktig for drift, men koster ~600 ms per hashing — og testsuiten oppretter
# brukere og logger inn hundrevis av ganger. Det alene stod for mesteparten av
# kjøretiden.
#
# Under `manage.py test` byttes hasheren til MD5. Den er kryptografisk verdiløs
# og skal ALDRI brukes utenfor tester; derfor den snevre betingelsen under.
# Produksjonsstien er urørt — hverken Gunicorn eller `runserver` har `test`
# som første argument.
_RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == 'test'

if _RUNNING_TESTS:
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

    # Backup-planleggeren ut av middleware-stacken under test.
    #
    # `_should_run_now()` returnerer True når `last_run_at` er null, og i en
    # fersk testdatabase er den alltid det. Første request i enhver test som
    # går gjennom stacken utløste derfor en ekte backup — som skriver filer og
    # rader, og på SQLite låser tabellen av og til. Resultatet var en
    # testsuite som feilet tilfeldig, med feilmeldinger som pekte på
    # backup_scheduler i tester som ikke har noe med backup å gjøre.
    #
    # En flaky suite er verre enn ingen suite: den lærer deg å kjøre om igjen
    # i stedet for å lese. Planleggeren testes direkte i patients-testene, så
    # ingenting mistes ved å ta den ut her.
    # Intervallsendingen av vaktlista ut av samme grunn: en bakgrunnstråd som
    # sender e-post midt i en test som ikke handler om det. Den testes direkte
    # i vaktliste/tests_fil.py.
    #: Lista slik den er i drift, før de to tas ut. Finnes fordi testene skal
    #: kunne spørre «står middlewaren registrert?» uten å lese denne fila som
    #: tekst — en `assertIn` mot kildekoden går i stykker av et linjeskift, og
    #: sier ingenting om hva Django faktisk kjører med. (14. sep. 2026, 3.8.)
    MIDDLEWARE_I_DRIFT = list(MIDDLEWARE)
    MIDDLEWARE = [m for m in MIDDLEWARE
                  if m not in ('core.middleware.BackupSchedulerMiddleware',
                               'vaktliste.middleware.FilutsendingMiddleware')]

# ── Internasjonalisering ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'nb'
TIME_ZONE = 'Europe/Oslo'
USE_I18N = True
USE_TZ = True

# ── Statiske filer ───────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# STORAGES, ikke STATICFILES_STORAGE. Den gamle innstillingen ble FJERNET i
# Django 5.1, og prosjektet kjører 5.2 — den sto igjen som død konfigurasjon og
# ble ignorert uten et eneste varsel. Følgene var reelle:
#
#   - Ingen hashing av filnavn, altså ingen cache-busting
#   - WhiteNoise serverte `/static/css/portal.css` med `max-age=14400`
#   - Enhver CSS- eller JS-endring var dermed usynlig for en bruker som hadde
#     besøkt siden, i inntil fire timer etter deploy
#
# Oppdaget 23. aug. 2026 etter to runder med «fargen har ikke endret seg» —
# der begge fiksene faktisk lå ute i prod. `collectstatic` avslørte det i
# loggen: «138 static files copied» uten det etterfølgende «post-processed»,
# som er manifest-steget som ikke kjørte.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# ── Sikkerhet ────────────────────────────────────────────────────────────────
# HTTPS er kun aktuelt i produksjon (Railway). Under utvikling med DEBUG=True
# er det HTTP, og cookies/redirects maa tilpasses.
_HTTPS_ENABLED = not DEBUG

# Cookies
SESSION_COOKIE_SECURE = _HTTPS_ENABLED
CSRF_COOKIE_SECURE = _HTTPS_ENABLED
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Proxy (Railway terminerer TLS foran appen)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HTTPS-tvang (kun produksjon, aldri offline-modus)
SECURE_SSL_REDIRECT = _HTTPS_ENABLED

# Health-endepunktet må svare 200 også på ren HTTP fra Railways interne
# healthcheck (som ikke går via proxy og derfor mangler X-Forwarded-Proto).
# Resten av appen redirectes fortsatt til HTTPS, og HSTS holder nettlesere på HTTPS.
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']

# HSTS (kun produksjon – unngå å låse seg ute lokalt eller offline)
if _HTTPS_ENABLED:
    SECURE_HSTS_SECONDS = 31536000  # 1 år
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Diverse headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Sesjonsvarighet – kan justeres av admin via AppSetting (se accounts/middleware.py)
# Default-verdi brukes hvis AppSetting ikke er satt.
SESSION_COOKIE_AGE = 8 * 60 * 60  # 8 timer i sekunder
SESSION_SAVE_EVERY_REQUEST = True  # resett timer ved hver request
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ── Cache (brukes av django-ratelimit, stats-cache, RequestMetrics) ─────────
# To backends støttes:
#   1) Redis (prod med flere workers): aktiveres når REDIS_URL er satt.
#      Delt cache mellom workers gir korrekt rate-limiting (telleren deles)
#      og delt stats-cache (færre DB-spørringer).
#   2) LocMemCache (lokal/single-worker): per-prosess, ingen ekstern
#      avhengighet. Tellere nullstilles ved restart, men det er akseptabelt.
#
# Bytte mellom backends gjøres kun ved å sette/fjerne REDIS_URL på Railway —
# ingen kodeendring kreves. Tester kjører alltid på LocMemCache (REDIS_URL
# ikke satt i test-miljø).
REDIS_URL = os.environ.get('REDIS_URL', '').strip()

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': 'pasientregistrering',  # isolerer nøkler hvis Redis deles
            'TIMEOUT': 300,  # 5 min default TTL (overstyres per-key der det trengs)
            # Merk: Django's innebygde RedisCache (django>=4.0) har INGEN innebygd
            # 'IGNORE_EXCEPTIONS'-option slik tredjepartspakken django-redis har.
            # Failsafe ved Redis-utfall er håndtert i koden:
            #   - patients/stats_cache.py: try/except rundt cache.get/set/delete
            #   - django-ratelimit: se core/ratelimit.py. Pakken faller IKKE
            #     åpen av seg selv — cache.add() mot en død Redis kaster
            #     ConnectionError, og RATELIMIT_FAIL_OPEN er False som default.
            #     Begge er håndtert: flagget settes True nedenfor, og
            #     core.ratelimit.er_rate_limited fanger exceptions
            #   - patients/admin_status.py _get_cache_health: try/except rundt probe
        }
    }
    # Sentinel for diagnostikk (vises i admin/server-status)
    CACHE_BACKEND_NAME = 'redis'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'pasientregistrering-ratelimit',
            'OPTIONS': {
                # 200 delte rate-limit-tellere med idempotens- og
                # statistikknøkler, og 200 ulike brukernavn mot innlogging
                # kunne kaste ut tellerne (13. sep. 2026, M15).
                'MAX_ENTRIES': 5000,
                'CULL_FREQUENCY': 4,
            },
        }
    }
    CACHE_BACKEND_NAME = 'locmem'

# ── Rate-limiting ────────────────────────────────────────────────────────────
# Bruk django-ratelimit. Grensene ligger to steder: innlogging og MFA i
# accounts/views.py (N4), alle andre endepunkter i core/ratelimit.py (S3).
RATELIMIT_VIEW = 'accounts.views.ratelimited_view'
# Nød-bryter: sett RATELIMIT_ENABLE=false i miljøvariabler for å slå av rate-limiting
# uten å deploye (f.eks. ved event der mange kobler seg på samme wifi).
RATELIMIT_ENABLE = _env_bool('RATELIMIT_ENABLE', True)

# Fall åpent hvis cachen ikke svarer. Pakkens default er å svare 429 på alt i
# den situasjonen; her ville det stanset pasientregistrering under vakt fordi
# en cache er nede. Bremsen er et vern mot løpske klienter, ikke systemets
# eneste forsvar — innlogging har i tillegg kontolåsing i databasen (5 feilede
# forsøk = 15 min), som er uavhengig av cachen.
#
# Merk at flagget alene ikke er nok: det dekker bare stien der cachen svarer
# uten verdi. Kaster den, må kallstedet fange det — se core/ratelimit.py.
RATELIMIT_FAIL_OPEN = True

# ── MFA-innstillinger ────────────────────────────────────────────────────────
# Antall dager en enhet kan stoles på uten ny TOTP-kode
MFA_TRUST_DEVICE_DAYS = 30
# Utsteder som vises i authenticator-appen
OTP_TOTP_ISSUER = 'Sanitetsportalen'

# ── Standard primærnøkkeltype ─────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── E-postvarsel ved kritiske feil (F1) ──────────────────────────────────────
#
# Sentry er bevisst fjernet fra prosjektet. I stedet bruker vi Djangos
# innebygde AdminEmailHandler, som sender stacktrace på e-post ved uhåndterte
# exceptions. Uten SMTP-variabler er alt dette inert: EMAIL_BACKEND faller
# tilbake til konsoll, og handleren logger i stedet for å sende.
ADMINS_RAW = os.environ.get('ADMINS', '')
ADMINS = [
    (n.strip(), e.strip())
    for n, _, e in (p.partition(':') for p in ADMINS_RAW.split(',') if p.strip())
    if e.strip()
]
MANAGERS = ADMINS

EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', True)

# Uten denne arver smtplib Pythons globale socket-timeout, som er None —
# altså uendelig. AdminEmailHandler sender *synkront, i requestens egen tråd*.
# En SMTP-vert som svelger pakkene i stedet for å avvise dem, ville dermed låst
# tråden for godt: en feil som skulle gitt én e-post, tar i stedet ned appen for
# alle. Gunicorn kjører med 4 tråder per worker, så det skal ikke mange til.
#
# Oppdaget 22. aug. 2026: Railway-containeren når ikke send.ahasend.com:587
# utgående, og `verifiser_feilvarsel` hang i connect() til den ble avbrutt.
# Dempingsfilteret begrenser skaden — maks én e-post per feiltype per 15 min —
# men det er timeouten som gjør varslingen ufarlig for driften.
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', 'sanitetsportalen@example.invalid',
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# AHASends HTTP-API, brukt i stedet for SMTP fordi Railway sperrer utgående
# SMTP. Målt fra containeren 22. aug. 2026: portene 587, 2525, 465 og 25 er alle
# stengt, mens 443 mot samme vert er åpen. Se core/mail_backends.py.
AHASEND_API_KEY = os.environ.get('AHASEND_API_KEY', '')
AHASEND_ACCOUNT_ID = os.environ.get('AHASEND_ACCOUNT_ID', '')

# ── Offsite backup til Scaleway Object Storage (13. sep. 2026) ───────────────
# Inert uten bucket, nøkler og OFFSITE_BACKUP_KEY — bare prod har dem. Se
# core/offsite.py. OFFSITE_BACKUP_KEY må også ligge i en passordbehandler:
# uten den er bucketen uleselig, og det er meningen.
OFFSITE_S3_BUCKET = os.environ.get('OFFSITE_S3_BUCKET', '')
OFFSITE_S3_REGION = os.environ.get('OFFSITE_S3_REGION', 'nl-ams')
OFFSITE_S3_ENDPOINT = os.environ.get('OFFSITE_S3_ENDPOINT', 'https://s3.nl-ams.scw.cloud')
OFFSITE_S3_ACCESS_KEY = os.environ.get('OFFSITE_S3_ACCESS_KEY', '')
OFFSITE_S3_SECRET_KEY = os.environ.get('OFFSITE_S3_SECRET_KEY', '')
OFFSITE_BACKUP_KEY = os.environ.get('OFFSITE_BACKUP_KEY', '')

# Rekkefølgen er en prioritering, ikke en tilfeldighet: HTTP-API-et først fordi
# det er det eneste som faktisk kommer ut av containeren. SMTP beholdes fordi
# det virker i offline-modus og lokalt, der ingen brannmur står i veien.
if AHASEND_API_KEY and AHASEND_ACCOUNT_ID:
    EMAIL_BACKEND = 'core.mail_backends.AhaSendApiBackend'
elif EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    # Ingen transport konfigurert: skriv e-posten til stdout i stedet for å feile.
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Cookies (sessionid) ut av Djangos reserve-feilrapport (13. sep. 2026, L1).
DEFAULT_EXCEPTION_REPORTER_FILTER = 'core.error_reporting.SlankReporterFilter'

# ── Logging (N3) ─────────────────────────────────────────────────────────────
#
# Tidligere fantes kun én logger ('memory') og ingen rot-logger. Alt `patients`,
# `core` og `accounts` logget propagerte opp til en rot uten handler, og havnet
# i Pythons lastResort-handler — som skriver til stderr først fra WARNING.
# INFO-logging var dermed i praksis slått av i produksjon, inkludert linjene
# RUNBOOK-en ber deg lete etter for å verifisere at backup kjører.
#
# LOG_LEVEL som miljøvariabel gjør at man kan skru til DEBUG under feilsøking
# på Railway uten å deploye.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s: %(message)s',
        },
    },
    'filters': {
        # Demper e-post-stormer: maks én mail per feiltype per 15 min.
        'error_throttle': {
            '()': 'core.log_filters.ThrottleByMessageFilter',
            'window_seconds': 15 * 60,
        },
        'require_debug_false': {'()': 'django.utils.log.RequireDebugFalse'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['require_debug_false', 'error_throttle'],
            # include_html=False er et sikkerhetsvalg, ikke en formateringssak.
            # HTML-malen (technical_500.html) tar med *lokale variabler* for hver
            # stackramme. En feil i en pasientvisning ville da sendt kliniske
            # opplysninger ut av systemet på e-post. Tekstmalen har dem ikke.
            # Skal denne noen gang settes til True, må personvernkonsekvensen
            # vurderes på nytt først.
            'include_html': False,
            # Slank rapport: traceback og forespørselskontekst, ikke hele
            # Settings- og META-dumpen Django ellers legger ved. Se
            # core/error_reporting.py for hva som er utelatt og hvorfor.
            # Settes kun her, så feilsiden i DEBUG beholder full detalj.
            'reporter_class': 'core.error_reporting.SlankExceptionReporter',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'memory': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # **`django`-loggeren må stå her, ellers bruker den Djangos egen
        # e-posthandler** (12. sep. 2026). Django konfigurerer DEFAULT_LOGGING
        # før vår LOGGING, og en logger vi ikke nevner beholder handlerne
        # derfra: `django` fikk da en AdminEmailHandler *uten* demping og
        # *uten* den slanke rapportøren. Alt som logges under `django.*` utenom
        # `django.request` — `django.security.*` først og fremst — gikk den
        # veien, og sendte hele Settings- og META-dumpen på e-post. En
        # portskanner mot staging ga hundre slike på fem minutter.
        'django': {
            'handlers': ['console', 'mail_admins'],
            'level': 'INFO',
            'propagate': False,
        },
        # Uhåndterte exceptions i views. Django logger disse på ERROR.
        'django.request': {
            'handlers': ['console', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        # Feil Host-header er ikke en feil hos oss: det er skannere som
        # prøver domener på måfå, og svaret er 400 uansett. Konsollen får
        # linja, ingen får e-post — Djangos egen anbefaling for denne loggeren.
        'django.security.DisallowedHost': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
