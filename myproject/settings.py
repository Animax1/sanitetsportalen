"""
Django-innstillinger for pasientregistreringssystemet.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

# ── Grunnleggende ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-ikke-bruk-i-prod-changeme123!')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

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
    'audit',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
]

# ── Mellomvare ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internasjonalisering ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'nb'
TIME_ZONE = 'Europe/Oslo'
USE_I18N = True
USE_TZ = True

# ── Statiske filer ───────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

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
            #   - django-ratelimit failopener av seg selv ved cache-feil
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
        }
    }
    CACHE_BACKEND_NAME = 'locmem'

# ── Rate-limiting ────────────────────────────────────────────────────────────
# Bruk django-ratelimit med LocMemCache. Se accounts/views.py for grenser.
RATELIMIT_VIEW = 'accounts.views.ratelimited_view'
# Nød-bryter: sett RATELIMIT_ENABLE=False i miljøvariabler for å slå av rate-limiting
# uten å deploye (f.eks. ved event der mange kobler seg på samme wifi).
RATELIMIT_ENABLE = os.environ.get('RATELIMIT_ENABLE', 'True') == 'True'

# ── MFA-innstillinger ────────────────────────────────────────────────────────
# Antall dager en enhet kan stoles på uten ny TOTP-kode
MFA_TRUST_DEVICE_DAYS = 30
# Utsteder som vises i authenticator-appen
OTP_TOTP_ISSUER = 'Sanitetsportalen'

# ── Standard primærnøkkeltype ─────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
