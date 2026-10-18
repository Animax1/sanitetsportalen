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


def csp_nonce(request):
    """Gjør request-ets CSP-nonce tilgjengelig som {{ csp_nonce }}.

    Settes av ``SecurityHeadersMiddleware``. Enhver inline <script> og <style>
    må ha ``nonce="{{ csp_nonce }}"`` — uten det kjører skriptet ikke og stilene
    brukes ikke (script-src fra F5, style-src-elem fra 14. okt. 2026).

    Faller tilbake til tom streng hvis middlewaren ikke har kjørt, slik at
    templates som rendres utenfor request/response-syklusen (feilsider,
    management-kommandoer) ikke kaster.
    """
    return {'csp_nonce': getattr(request, 'csp_nonce', '')}


def tilgang(request):
    """Legg til ``er_global_admin`` i template-context.

    Malene gatet tidligere på ``request.user.role == 'admin'`` direkte. Det
    virker fortsatt — ``admin`` overlevde krympingen av ``role`` i deploy 2 —
    men det er rollefeltet, og hele poenget med rollemodellen er at maler ikke
    skal spørre om rollen. Én kilde, og den heter det samme som helperen i
    ``core.auth_decorators``.
    """
    from core.auth_decorators import er_global_admin
    return {'er_global_admin': er_global_admin(getattr(request, 'user', None))}


def versjon(request):
    """Legg til ``versjon`` — bygg og dato — i template-context.

    Footeren i ``base_portal.html`` viser den. Regnes ut én gang per prosess
    i ``core.versjon.hent_versjon``; her kostes ingenting per request.
    """
    from core.versjon import hent_versjon
    return {'versjon': hent_versjon()}


def portal(request):
    """Legg til ``aktiv_portal`` og ``flere_portaler`` (17. okt. 2026).

    Middlewaren har lagt portalen på forespørselen. ``flere_portaler`` styrer
    merket i toppen: med én portal vises ingenting, så ingen ser en endring
    før portal nummer to finnes.
    """
    from core.auth_decorators import er_global_admin, er_moderator

    portal = getattr(request, 'portal', None)
    user = getattr(request, 'user', None)
    return {
        'aktiv_portal': portal,
        'flere_portaler': getattr(request, 'portal_antall', 0) > 1,
        # «Moderator»-gruppa i avatar-menyen (fase 5b). **Admin ser den også**
        # (André, 18. okt. 2026: «admin har ikke tilgang til moderator sine sider, de
        # må han») — sidene slapp ham inn, men lenkene sto bare for moderatoren.
        'vis_moderatormeny': (portal is not None
                              and (er_global_admin(user) or er_moderator(user, portal))),
    }


def statusmerke(request):
    """Legg til ``miljo`` og ``statusmelding`` — merket i toppmenyen.

    Miljøet er fast for prosessen (`core/miljo.py`); statusmeldingen er én
    `AppSetting` (`core/statusmelding.py`). **Kaster aldri**: et merke som ikke
    kan leses skal gi en side uten merke, ikke en side som feiler.
    """
    from core.miljo import miljo
    try:
        from core.statusmelding import aktiv
        melding = aktiv()
    except Exception:   # noqa: BLE001 — databasen kan være nede; siden skal stå
        melding = None
    # **Portalnavnet i fanen** når kontoen har flere portaler (fase 5c, §4.4):
    # to faner med «Vaktliste» i hver sin portal skal kunne skilles i fanelinja.
    # Det går inn i `fane`, ikke i en ny variabel — hver mal og `fanetittel()`
    # leser den alt (`core/tests_statusmerke.py`), og med én portal er den uendret.
    merke = dict(miljo())
    portal = getattr(request, 'portal', None)
    if portal is not None and getattr(request, 'portal_antall', 0) > 1:
        merke['fane'] = f'{merke["fane"]}{portal.navn} · '
    return {'miljo': merke, 'statusmelding': melding}
