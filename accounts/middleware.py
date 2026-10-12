"""Mellomvare for passordbytte-påbud og dynamisk sesjonsløpetid."""
from django.shortcuts import redirect
from django.urls import reverse


class MustChangePasswordMiddleware:
    """
    Tvinger brukere til å bytte passord hvis must_change_password er satt.
    Tillater kun passordbytte-URL, logg-ut og static-filer.
    """

    # NB: /django-admin/ sto her tidligere og gjorde passordbytte-påbudet
    # valgfritt for alle med is_staff. Flaten er nå av i produksjon (S1), og
    # unntaket er fjernet — også lokalt, hvor det bare skjulte problemet.
    ALLOWED_PATHS = (
        '/accounts/change-password/',
        '/accounts/logout/',
        '/accounts/login/',
        '/static/',
        # Lenket fra hver side, også passordbyttet: å lese erklæringen skal
        # ikke kreve at passordet er byttet først.
        '/personvern/',
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
            request.session.set_expiry(sesjonstid_timer() * 3600)
        return self.get_response(request)


def sesjonstid_timer() -> int:
    """Sesjonens løpetid i timer, klemt til 1–24. Kaster aldri.

    Egen funksjon fordi personvernsiden (`core/personvern.py`) oppgir den samme
    tiden til brukerne — og et tall skrevet av for hånd der ville stått igjen den
    dagen admin flyttet det.
    """
    try:
        from core.models import AppSetting
        hours = int(AppSetting.get('session_timeout_hours', 8))
    except Exception:
        # Ved import-feil eller manglende tabell (før migrering): standarden,
        # som er den samme som i settings.
        return 8
    return max(1, min(24, hours))
