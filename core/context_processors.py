"""Context processors for core-appen.

Eksponerer modul-registret til alle templates som bruker base_portal.html
(pasienter, framtidige moduler) slik at nav-baren rendres dynamisk uten at
hver view trenger å sende modules manuelt.
"""
from __future__ import annotations

from core.modules import get_nav_modules


def notification_unread_count(request):
    """Eksponer ``notification_unread_count`` til alle templates.

    Brukes av bjelle-badge i ``base_portal.html``. Returnerer 0 for
    uautentiserte requests slik at templates kan rendre uten try/except.
    Bruker en effektiv COUNT-query (en heltallsverdi, ingen join).
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'notification_unread_count': 0}
    # Lokal import for å unngå cirkulær import (core.models -> apps boot)
    from core.models import Notification
    try:
        count = Notification.objects.filter(user=user, is_read=False).count()
    except Exception:
        # Defensiv: hvis migrasjoner ikke er kjørt ennå, ikke kræsj nav-baren
        count = 0
    return {'notification_unread_count': count}


def portal_modules(request):
    """Legg til ``nav_modules`` i template-context.

    Returnerer en tom liste for uautentiserte requests slik at templates kan
    iterere uten å sjekke ``request.user.is_authenticated`` først.
    Lazy-evalueres — hvis ingen template bruker ``nav_modules`` koster det
    ingenting.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'nav_modules': []}
    return {'nav_modules': get_nav_modules(user)}
