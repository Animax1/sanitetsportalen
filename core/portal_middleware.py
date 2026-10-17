"""Hvilken portal forespørselen gjelder — portalregelen og fanevakten (17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.4. For hver innlogget forespørsel:

1. **Portalregelen.** Mulige portaler er de aktive kontoen har medlemskap i
   (global admin: alle aktive). Valget står i sesjonen og kontrolleres mot de
   mulige *hver gang* — er kontoen fjernet fra portalen, eller portalen
   deaktivert, gjelder valget ikke lenger. Én mulig velges av seg selv. Flere
   uten et gyldig valg stopper **både lesing og skriving**: sider sendes til
   portalvelgeren, API-kall får 409. Null er en foreldreløs konto.
2. **Fanevakten.** Siden vet hvilken portal den ble tegnet for, og sender den i
   `X-Portal` (eller `_portal` i et skjema). Stemmer den ikke med sesjonen —
   noen byttet portal i en annen fane — svarer vi 409 i stedet for å skrive i
   feil portal. Har kontoen flere portaler, **må** en skriving bære den: ellers
   er vakten valgfri, og den første glemte stien er hullet.
3. **Konteksten.** Portalen legges på `request.user` (der `har_tilgang` leser
   den) og i `core.portal.aktiver_portal()` (der `hent_aktiv_vakt` leser den),
   for hele forespørselen — også signaler og `on_commit` som kjører i den.

**Stiene som ikke gjelder én portal** slipper gjennom uten valg: innlogging,
passord og MFA, min profil, varslene, personvern, statiske filer, helse,
manifestet, velgeren selv og parks side uten innlogging (den får portalen fra
lenken).
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from core.portal import BRUKER_ATTR, SESJON_NOKKEL, aktiver_portal, mulige_portaler

#: Stier som ikke gjelder én portal. Prefikser, som `MustChangePasswordMiddleware`.
UTENFOR_PORTAL = (
    '/accounts/',
    '/static/',
    '/personvern/',
    '/healthz/',
    '/robots.txt',
    '/manifest.webmanifest',
    '/portal/',
    '/min-profil/',
    '/varsler/',
    '/api/varsler/',
    '/lag/r/',
    '/django-admin/',
)

SKRIVENDE = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def _json_feil(melding: str, status: int, **ekstra) -> JsonResponse:
    """Svaret begge klientfamiliene leser: `message` (`core.jsonkropp.json_feil`,
    oppdrag, KO, vaktlista) og `error` (pasientsiden). Med bare `error` viste
    tavla «Kunne ikke flytte.» og grunnen forsvant (17. okt. 2026)."""
    return JsonResponse({'status': 'error', 'message': melding, 'error': melding, **ekstra},
                        status=status)


def _vil_ha_json(request) -> bool:
    return ('/api/' in request.path
            or 'application/json' in request.headers.get('Accept', '')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest')


def _fanens_portal(request, flere: bool):
    """Portalen siden sier den ble tegnet for, eller ``None`` når den ikke sier noe.

    **Skjemafeltet leses bare når kontoen har flere portaler**, og da etter at
    kroppen er lest inn: `request.POST` tømmer datastrømmen, og et view som
    leser `request.body` etterpå ville krasjet (stemplingen i vaktlista gjorde
    det). Med én portal finnes ingen annen fane å ha byttet i.
    """
    verdi = request.headers.get('X-Portal')
    if verdi:
        return verdi
    if flere and request.method in SKRIVENDE and request.content_type in (
            'application/x-www-form-urlencoded', 'multipart/form-data'):
        request.body  # noqa: B018 — legger kroppen i minnet, så viewet kan lese den
        return request.POST.get('_portal') or None
    return None


def velg_portal(request, mulige):
    """Portalen etter regelen, og skriv valget i sesjonen. ``None`` når det ikke er entydig."""
    valgt_id = request.session.get(SESJON_NOKKEL)
    portal = next((p for p in mulige if p.pk == valgt_id), None)
    if portal is None and len(mulige) == 1:
        portal = mulige[0]
    if portal is None:
        request.session.pop(SESJON_NOKKEL, None)
    elif valgt_id != portal.pk:
        request.session[SESJON_NOKKEL] = portal.pk
    return portal


class PortalMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if not getattr(user, 'is_authenticated', False) or any(
                request.path.startswith(p) for p in UTENFOR_PORTAL):
            return self.get_response(request)

        mulige = list(mulige_portaler(user))
        portal = velg_portal(request, mulige)

        if portal is None:
            if not mulige:
                melding = ('Kontoen din er ikke med i noen portal. '
                           'Be en administrator eller moderator om tilgang.')
                if _vil_ha_json(request):
                    return _json_feil(melding, 403)
                return render(request, 'core/ingen_portal.html', {'melding': melding},
                              status=403)
            if _vil_ha_json(request):
                return _json_feil('Velg portal først.', 409, velg_portal=True)
            return redirect(reverse('core:portal_velg') + '?' + urlencode(
                {'neste': request.get_full_path()}))

        fanens = _fanens_portal(request, flere=len(mulige) > 1)
        if fanens is not None and fanens != portal.slug:
            return _json_feil(f'Du byttet til portalen «{portal.navn}» i en annen fane. '
                              f'Last siden på nytt før du fortsetter.', 409, portal_byttet=True)
        if fanens is None and request.method in SKRIVENDE and len(mulige) > 1:
            return _json_feil('Siden sa ikke hvilken portal den gjelder. Last den på nytt.', 409,
                              portal_byttet=True)

        setattr(user, BRUKER_ATTR, portal)
        request.portal = portal
        request.portal_antall = len(mulige)
        with aktiver_portal(portal):
            return self.get_response(request)
