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

urlpatterns = [
    # Health-endepunkt (forbedring #2) — INGEN auth, brukes av Railway
    # og eksterne monitorer. Plassert på root for at Railway sin
    # "Health Check Path"-konfigurasjon skal kunne peke direkte hit.
    path('healthz/', healthz, name='healthz'),

    # Django Admin – kun for superbrukere
    path('django-admin/', admin.site.urls),

    # Brukerkontoer (innlogging, passord, admin-panel brukere)
    path('accounts/', include('accounts.urls')),

    # Pasientregistrering (fra Fase 2 mountet under /pasienter/)
    # OBS: må stå FØR core fordi core inneholder legacy-redirects som ellers
    # ville fanget /api/... og /admin/server-status/... under root.
    path('pasienter/', include('patients.urls')),

    # Sanitetsportal-skall (dashboard + legacy-redirects)
    # Mountet på '' så portal-dashboardet ligger på /.
    path('', include('core.urls')),
]
