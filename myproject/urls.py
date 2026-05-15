"""
Hoved-URL-konfigurasjon for Sanitetsportalen.

Struktur (fra Fase 2):
- /                  → core (portal-dashboard + legacy-redirects)
- /pasienter/        → patients-appen (alle gamle /api/... og /admin/server-status/...)
- /accounts/         → innlogging, passord, brukeradministrasjon
- /healthz/          → health-check (ingen auth, brukes av Railway)
- /django-admin/     → Django sin innebygde admin (kun superbrukere)
"""
from django.contrib import admin
from django.urls import path, include

from patients.health import healthz
from patients import admin_status as _admin_status

urlpatterns = [
    # Health-endepunkt (forbedring #2) — INGEN auth, brukes av Railway
    # og eksterne monitorer. Plassert på root for at Railway sin
    # "Health Check Path"-konfigurasjon skal kunne peke direkte hit.
    path('healthz/', healthz, name='healthz'),

    # Django Admin – kun for superbrukere
    path('django-admin/', admin.site.urls),

    # Brukerkontoer (innlogging, passord, admin-panel brukere)
    path('accounts/', include('accounts.urls')),

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
