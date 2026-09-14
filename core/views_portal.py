"""Portalens egne sider: dashbordet og «Min profil».

Delt ut av `core/views.py` 14. sep. 2026 (gjeldspunkt 3.7). Fila var 830 linjer
og 24 views om alt fra backup til varsler — samme grep som `patients/views.py`
fikk i N13.3.

Her ligger det **alle innloggede** ser, uansett tilgang.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from datetime import timedelta

from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.models import LoginEvent
from core.models import ModuleSettings
from core.modules import get_dashboard_modules


# ─────────────────────────────────────────────────────────────────────────────
# Portal-dashboard
# ─────────────────────────────────────────────────────────────────────────────


@login_required
@require_GET
def portal_dashboard_view(request):
    """Portal-forside med oversikt over moduler.

    Vises på `/`. Krever innlogging — uautentiserte brukere blir sendt til
    login-siden via `@login_required`. Etter innlogging redirecter Django
    automatisk tilbake hit (settings.LOGIN_REDIRECT_URL = '/').

    Modul-kortene leses fra ``core.modules``-registret og filtreres på:
    - ``ModuleSettings.enabled`` (admin kan toggle moduler i sanntid)
    - Brukerens ``ModulTilgang``-rad på modulen (global admin ser alt)
    - ``Module.show_in_dashboard``
    """
    modules = get_dashboard_modules(request.user)
    return render(request, 'core/dashboard.html', {'modules': modules})


# ─────────────────────────────────────────────────────────────────────────────
# Min profil — for vanlige brukere
# ─────────────────────────────────────────────────────────────────────────────


def modultilganger_for_visning(user):
    """Radene «Modul-tilganger» på min profil, med nivå og status.

    **Kortet leste tidligere de fem ``kan_redigere_*``-flaggene**, og de var
    ikke bare døde — de var feil. Backfillen i deploy 1 utledet fra ``role``
    og rørte flagget med vilje (§8.1), så en konto med
    ``patients: skriv_full`` fikk «Nei» på pasientregistrering. Under sto det
    «Ta kontakt om du trenger flere tilganger», så siden ba brukeren melde fra
    om noe hen allerede hadde. En flate som viser noe annet enn den som
    håndhever, er den samme fella som §2.1.

    Modullista er den ``ModulTilgangForm`` bygger matrisen av, slik at det
    admin setter er det brukeren ser. ``admin_only``-moduler er utelatt: de
    gates av global admin og bruker ikke ``ModulTilgang``.

    **Nivået og «modulen er av» holdes fra hverandre**, og det er grunnen til at
    radene leses fra ``_tilganger`` og ikke fra ``nivaa_for``. Sistnevnte
    svarer på «hva slipper du inn på nå», og gir derfor ``None`` for en
    deaktivert modul. Kortet svarer på «hva har du fått», og hadde det vist en
    avslått modul som «ingen tilgang», ville brukeren lest et driftsvalg som et
    tilgangsvalg — og bedt om noe hen allerede har fått.
    """
    from accounts.forms import ModulTilgangForm
    # `_tilganger` framfor `nivaa_for`: se avsnittet over. Samme private
    # helper som `Module.is_visible_for` bruker.
    from core.auth_decorators import _tilganger, er_global_admin

    aktive = ModuleSettings.get_enabled_slugs()
    admin = er_global_admin(user)
    tilganger = {} if admin else _tilganger(user)

    rader = []
    for modul in ModulTilgangForm.moduler():
        nivaa = 'skriv_full' if admin else tilganger.get(modul.slug)
        rader.append({
            'navn': modul.name,
            # Modulens egen etikett når den har en — kortet skal si det
            # samme som matrisen der tilgangen ble delt ut.
            'nivaa': modul.etikett_for(nivaa) if nivaa else None,
            'deaktivert': not (modul.is_core or modul.slug in aktive),
        })
    return rader


@login_required
@require_GET
def profile_view(request):
    """Min profil-side med permissions, moduler og aktivitetslogg.

    Viser:
    - Brukerens modultilganger, med nivå
    - Modulene brukeren har tilgang til
    - Siste 10 innloggingshendelser (LoginEvent)
    - Sikkerhetsstatus (MFA, sist endret passord)

    Tilgjengelig for alle innloggede brukere.
    """
    user = request.user

    permissions = modultilganger_for_visning(user)

    # Moduler brukeren har tilgang til (skjul kjernemoduler uten dashboard)
    visible_modules = get_dashboard_modules(user)

    # Aktivitetslogg: siste 10 innlogginger (alle event-typer)
    recent_events = (
        LoginEvent.objects
        .filter(user=user)
        .order_by('-created_at')[:10]
    )

    # Antall vellykkede innlogginger siste 7 dager
    one_week_ago = timezone.now() - timedelta(days=7)
    weekly_login_count = LoginEvent.objects.filter(
        user=user,
        success=True,
        event_type=LoginEvent.EVENT_LOGIN,
        created_at__gte=one_week_ago,
    ).count()

    return render(request, 'core/profile.html', {
        'permissions': permissions,
        'visible_modules': visible_modules,
        'recent_events': recent_events,
        'weekly_login_count': weekly_login_count,
    })
