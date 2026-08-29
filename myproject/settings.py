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

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# SECRET_KEY signerer sesjonscookies, CSRF-tokens og MFA trust-cookies. Kjører
# produksjon på en kjent nøkkel, kan sesjoner og MFA-cookies forfalskes.
# Tidligere hadde variabelen en hardkodet fallback som slo inn stilltiende hvis
# miljøvariabelen manglet. Nå feiler oppstarten i stedet — høylytt og med én
# gang — når DEBUG er av. Fallbacken beholdes kun for lokal utvikling.
#
# Merk at offline-modus også kjører DEBUG=False; .env.offline.example setter
# derfor en egen nøkkel som skal byttes ved hvert event.
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
elif not SECRET_KEY:
    SECRET_KEY = 'dev-only-ikke-bruk-i-prod-changeme123!'

# Offline-modus: kjoeres paa event-laptop uten TLS-terminerende proxy.
# Skrur av HTTPS-tvang og HSTS, men beholder DEBUG=False slik at stack-traces
# og statiske filer fortsatt er produksjonsklare. Sett OFFLINE_MODE=True i
# .env.offline.example for offline-bruk.
OFFLINE_MODE = os.environ.get('OFFLINE_MODE', 'False') == 'True'

# Ekstra paranoia: OFFLINE_MODE skal ALDRI kunne aktiveres i prod-miljøet på
# Railway. Hvis variabelen ved et uhell settes der, krasjer appen ved oppstart
# i stedet for å kjøre uten HTTPS-tvang og HSTS.
if OFFLINE_MODE and os.environ.get('RAILWAY_ENVIRONMENT'):
    raise ImproperlyConfigured(
        "OFFLINE_MODE kan ikke brukes på Railway. "
        "Fjern OFFLINE_MODE-variabelen fra Railway Variables."
    )

# Sikker default: tillat kun localhost hvis miljøvariabel mangler.
# I produksjon settes ALLOWED_HOSTS via Railway Variables.
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '.localhost,127.0.0.1').split(',')

CSRF_TRUSTED_ORIGINS_RAW = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in CSRF_TRUSTED_ORIGINS_RAW.split(',') if o.strip()]

# I offline-modus kjører vi DEBUG=False uten HTTPS, men trenger fortsatt at
# Django godtar POST-requests fra localhost og hele LAN-rangen til lead-PC-en.
# Detekterer LAN-IP automatisk og legger til typiske private subnets samt
# alle hosts i ALLOWED_HOSTS som http-origins.
if OFFLINE_MODE:
    import socket
    _offline_origins = {'http://127.0.0.1:8000', 'http://localhost:8000'}
    # Auto-detekter primær LAN-IP
    try:
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(('10.255.255.255', 1))
        _lan_ip = _s.getsockname()[0]
        _s.close()
        _offline_origins.add(f'http://{_lan_ip}:8000')
    except Exception:
        pass
    # Legg til alle ALLOWED_HOSTS-oppføringer som http-origins
    for _host in ALLOWED_HOSTS:
        _host = _host.strip().lstrip('.')
        if _host and _host not in ('localhost', '127.0.0.1'):
            _offline_origins.add(f'http://{_host}:8000')
    # Wildcard-pattern for hele 192.168.x.x og 10.x.x.x i offline-modus
    # (Django støtter wildcard i CSRF_TRUSTED_ORIGINS fra 4.0+)
    _offline_origins.add('http://192.168.*.*:8000')
    _offline_origins.add('http://10.*.*.*:8000')
    CSRF_TRUSTED_ORIGINS = list(set(CSRF_TRUSTED_ORIGINS) | _offline_origins)
    # Tillat også alle hosts i offline (LAN er klientens nett, ingen DNS-rebinding-risiko)
    if '*' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS = ALLOWED_HOSTS + ['*']

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
    'patients.middleware.BackupSchedulerMiddleware',
    'patients.middleware.SecurityHeadersMiddleware',
    'patients.middleware.RequestMetricsMiddleware',
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
    MIDDLEWARE = [m for m in MIDDLEWARE
                  if m != 'patients.middleware.BackupSchedulerMiddleware']

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
# HTTPS er kun aktuelt i produksjon (Railway). I offline-modus eller under
# utvikling med DEBUG=True er det HTTP, og cookies/redirects maa tilpasses.
_HTTPS_ENABLED = (not DEBUG) and (not OFFLINE_MODE)

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
                'MAX_ENTRIES': 200,
                'CULL_FREQUENCY': 4,
            },
        }
    }
    CACHE_BACKEND_NAME = 'locmem'

# ── Rate-limiting ────────────────────────────────────────────────────────────
# Bruk django-ratelimit. Grensene ligger to steder: innlogging og MFA i
# accounts/views.py (N4), alle andre endepunkter i core/ratelimit.py (S3).
RATELIMIT_VIEW = 'accounts.views.ratelimited_view'
# Nød-bryter: sett RATELIMIT_ENABLE=False i miljøvariabler for å slå av rate-limiting
# uten å deploye (f.eks. ved event der mange kobler seg på samme wifi).
RATELIMIT_ENABLE = os.environ.get('RATELIMIT_ENABLE', 'True') == 'True'

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
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'

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
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'filters': ['error_throttle'],
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
        # Uhåndterte exceptions i views. Django logger disse på ERROR.
        'django.request': {
            'handlers': ['console', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
