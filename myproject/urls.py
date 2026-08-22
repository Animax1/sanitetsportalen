"""
Hoved-URL-konfigurasjon for Sanitetsportalen.

Struktur (fra Fase 2):
- /                  → core (portal-dashboard + legacy-redirects)
- /pasienter/        → patients-appen (alle gamle /api/... og /admin/server-status/...)
- /accounts/         → innlogging og passordbytte
- /portal-admin/     → all administrasjon (brukere, moduler, logger, backup, status)
- /healthz/          → health-check (ingen auth, brukes av Railway)
- /robots.txt        → crawler-sperre (ingen auth)
- /django-admin/     → kun i DEBUG/offline, se under
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include

from core.robots import robots_txt
from patients.health import healthz
from patients import admin_status as _admin_status

urlpatterns = [
    # Health-endepunkt (forbedring #2) — INGEN auth, brukes av Railway
    # og eksterne monitorer. Plassert på root for at Railway sin
    # "Health Check Path"-konfigurasjon skal kunne peke direkte hit.
    path('healthz/', healthz, name='healthz'),

    # robots.txt — INGEN auth (må være lesbar for å ha effekt). Holder
    # portalen ute av søkemotorer og AI-crawlere. Se core/robots.py for
    # hvorfor denne og X-Robots-Tag-headeren begge trengs.
    path('robots.txt', robots_txt, name='robots_txt'),

    # Kontoer og administrasjon. Modulen mountes på root fordi den betjener
    # både /accounts/ (innlogging) og /portal-admin/ (brukeradmin) — se
    # docstringen i accounts/urls.py.
    path('', include('accounts.urls')),

    # Server-status admin (global URL, ingen namespace)
    path('portal-admin/server-status/',                    _admin_status.admin_status_view,      name='admin_server_status'),
    path('portal-admin/server-status/json/',               _admin_status.admin_status_json,      name='admin_server_status_json'),
    path('portal-admin/server-status/flag/',               _admin_status.admin_set_flag,         name='admin_set_flag'),
    path('portal-admin/server-status/sessions/',           _admin_status.admin_sessions_list,    name='admin_sessions_list'),
    path('portal-admin/server-status/sessions/kill/',      _admin_status.admin_session_kill,     name='admin_session_kill'),
    path('portal-admin/server-status/sessions/kill-all/',  _admin_status.admin_session_kill_all, name='admin_session_kill_all'),

    # Pasientregistrering (fra Fase 2 mountet under /pasienter/)
    # OBS: må stå FØR core fordi core inneholder legacy-redirects som ellers
    # ville fanget /api/... og /admin/server-status/... under root.
    path('pasienter/', include('patients.urls')),

    # Sanitetsportal-skall (dashboard + legacy-redirects)
    # Mountet på '' så portal-dashboardet ligger på /.
    path('', include('core.urls')),
]

# ── Django admin: kun lokalt og i offline-modus (S1) ─────────────────────────
#
# Django sin innebygde admin er en parallell innloggingsflate som omgår alt
# appen ellers gjør ved innlogging: rate-limiting per brukernavn og IP,
# kontosperre etter 5 feilede forsøk, MFA-tvang for brukere med mfa_required,
# tvungent passordbytte og LoginEvent-logging. Alt dette sitter på
# accounts.views.login_view. django_otp sin OTPMiddleware håndhever ingenting —
# den setter kun request.user.otp_device.
#
# I produksjon finnes det derfor kun én vei inn, og den er sikret. Portalen
# dekker det admin faktisk trenger:
#   /portal-admin/brukere/           brukeradministrasjon
#   /portal-admin/innloggingslogg/   LoginEvent
#   /portal-admin/auditlog/          AuditLog
#   /portal-admin/moduler/           ModuleSettings
#   /portal-admin/backup/            Backup
#   /portal-admin/server-status/     drift
# AppSetting redigeres med `python manage.py appsetting` (nødoperasjon).
#
# Lokalt (DEBUG) og i offline-modus beholdes flaten som utviklerverktøy. Begge
# er miljøer uten reell eksponering: offline-modus har hard sperre mot å kjøre
# på Railway (settings.py).
if settings.DEBUG or getattr(settings, 'OFFLINE_MODE', False):
    urlpatterns.insert(1, path('django-admin/', admin.site.urls))
