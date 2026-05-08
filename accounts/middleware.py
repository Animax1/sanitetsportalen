"""Mellomvare for passordbytte-påbud og dynamisk sesjonsløpetid."""
from django.shortcuts import redirect
from django.urls import reverse


class MustChangePasswordMiddleware:
    """
    Tvinger brukere til å bytte passord hvis must_change_password er satt.
    Tillater kun passordbytte-URL, logg-ut og static-filer.
    """

    ALLOWED_PATHS = (
        '/accounts/change-password/',
        '/accounts/logout/',
        '/accounts/login/',
        '/static/',
        '/django-admin/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, 'must_change_password', False)
            and not any(request.path.startswith(p) for p in self.ALLOWED_PATHS)
        ):
            return redirect('accounts:change_password')
        return self.get_response(request)


class DynamicSessionTimeoutMiddleware:
    """Setter sesjonens utløp dynamisk basert på AppSetting.session_timeout_hours.

    Default 8 timer. Verdien kan endres av admin via UI. Leses per request
    siden SESSION_SAVE_EVERY_REQUEST=True uansett skriver sesjonen ved hvert
    kall – kostnaden er minimal.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                from patients.models import AppSetting
                hours = int(AppSetting.get('session_timeout_hours', 8))
                hours = max(1, min(24, hours))
                request.session.set_expiry(hours * 3600)
            except Exception:
                # Ved import-feil eller manglende tabell (før migrering)
                # fall tilbake til default i settings
                pass
        return self.get_response(request)
