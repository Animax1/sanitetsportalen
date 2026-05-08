"""
Hoved-URL-konfigurasjon for pasientregistreringssystemet.
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

    # Pasientregistrering (hoved-app)
    path('', include('patients.urls')),
]
