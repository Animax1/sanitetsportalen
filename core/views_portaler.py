"""`/admin/portaler/` — portalene, satt opp av global admin (fase 5a, 17. okt. 2026).

Reglene står i `core/portaladmin.py`; her står bare skjemaene og meldingene.
Siden for én portal har fire skjemaer, hvert med sin `handling`, så en
innsending bare rører det den gjelder.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from audit.models import AuditLog
from core.auth_decorators import admin_required
from core.klientip import klient_ip
from core.models import Portalmodul, Tilhorighet, Vaktportal
from core.ratelimit import rate_limit

from accounts.moderering import kandidater_til_moderator

from . import portaladmin


def _vis_feil(request, feil: ValidationError) -> None:
    messages.error(request, ' '.join(feil.messages))


@admin_required
@require_http_methods(['GET', 'POST'])
@rate_limit(group='portaladmin:portaler', rate='20/m', method='POST', on_limit='html')
def portaler_view(request):
    """Lista over portalene, og «Ny portal»."""
    from accounts.models import PortalRolle, Portaltilgang

    if request.method == 'POST':
        try:
            portal = portaladmin.opprett_portal(request.POST.get('navn'),
                                                request.POST.get('slug'))
        except ValidationError as feil:
            _vis_feil(request, feil)
        else:
            messages.success(request, f'«{portal.navn}» er opprettet, med alle modulene. '
                                      'Velg tilhørigheter, moduler og moderatorer under.')
            return redirect('portaladmin:portal', pk=portal.pk)

    rader = []
    for portal in Vaktportal.objects.all():
        tilganger = Portaltilgang.objects.filter(portal=portal)
        rader.append({
            'portal': portal,
            'medlemmer': tilganger.count(),
            'moderatorer': [t.bruker.username for t in tilganger.filter(
                rolle=PortalRolle.MODERATOR).select_related('bruker')],
            'moduler': Portalmodul.objects.filter(portal=portal).count(),
        })
    return render(request, 'core/portaler.html', {'rader': rader})


@admin_required
@require_http_methods(['GET', 'POST'])
@rate_limit(group='portaladmin:portal', rate='60/m', method='POST', on_limit='html')
def portal_view(request, pk):
    """Én portal: navn og status, tilhørigheter, moduler med tak, moderatorer."""
    from accounts.models import CustomUser, PortalRolle, Portaltilgang
    from core.modules import get_all_modules

    portal = get_object_or_404(Vaktportal, pk=pk)
    if request.method == 'POST':
        handling = request.POST.get('handling')
        try:
            if handling == 'grunnlag':
                portaladmin.sett_grunnlag(portal, navn=request.POST.get('navn'),
                                          er_aktiv=request.POST.get('er_aktiv') == 'on')
                messages.success(request, 'Lagret.')
            elif handling == 'tilhorigheter':
                portaladmin.sett_tilhorigheter(portal, request.POST.getlist('tilhorighet'))
                messages.success(request, 'Tilhørighetene er lagret.')
            elif handling == 'moduler':
                onsket = {m.slug: (request.POST.get(f'tak_{m.slug}') or None)
                          if request.POST.get(f'med_{m.slug}') == 'on' else None
                          for m in get_all_modules() if not m.admin_only}
                endringer = portaladmin.sett_moduler(portal, onsket)
                messages.success(request, f'Modulene er lagret ({len(endringer)} endret).')
            elif handling == 'moderator':
                # Valgt i en liste, ikke skrevet inn (André, 18. okt. 2026: «fritekst
                # for å legge inn hvem som skal være moderator er dårlig arbeidsflyt»).
                pk = request.POST.get('bruker', '')
                bruker = CustomUser.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
                if bruker is None:
                    raise ValidationError('Velg en konto fra listen.')
                er = request.POST.get('er_moderator') == '1'
                portaladmin.sett_moderator(portal, bruker, er)
                AuditLog.objects.create(
                    table_name='accounts_portaltilgang', record_id=bruker.pk, action='UPDATE',
                    field_name=f'rolle i {portal.slug}',
                    new_value=PortalRolle.MODERATOR if er else PortalRolle.MEDLEM,
                    user=request.user, ip=klient_ip(request))
                messages.success(request, f'{bruker.username} er {"moderator" if er else "ikke lenger moderator"} '
                                          f'i {portal.navn}.')
            else:
                raise ValidationError('Ukjent handling.')
        except ValidationError as feil:
            _vis_feil(request, feil)
        return redirect('portaladmin:portal', pk=portal.pk)

    tak = dict(Portalmodul.objects.filter(portal=portal).values_list('modul_slug', 'tak'))
    moduler = [{
        'modul': m, 'med': m.slug in tak,
        'tak': tak.get(m.slug) if tak.get(m.slug) in m.nivaaer else Portalmodul.toppen_for(m.slug),
        'valg': [(v, m.etikett_for(v)) for v in m.nivaaer],
    } for m in get_all_modules() if not m.admin_only]
    valgt = set(portal.tilhorigheter.values_list('pk', flat=True))
    katalog = [{'t': t, 'valgt': t.pk in valgt} for t in Tilhorighet.objects.all()]
    return render(request, 'core/portal.html', {
        'portal': portal,
        'moduler': moduler,
        'katalog': katalog,
        'kandidater': kandidater_til_moderator(portal),
        'moderatorer': (Portaltilgang.objects
                        .filter(portal=portal, rolle=PortalRolle.MODERATOR)
                        .select_related('bruker').order_by('bruker__username')),
    })


@admin_required
@require_http_methods(['GET', 'POST'])
@rate_limit(group='portaladmin:tilhorigheter', rate='60/m', method='POST', on_limit='html')
def tilhorigheter_view(request):
    """Katalogen: korps og «annet» (som Leger), for alle portaler (18. okt. 2026).

    Var korpsregisteret inne i vaktlista. André: «korpsene bør settes opp av admin
    UTENFOR /vaktliste». Tre skjemaer med hver sin `handling`: ny, rediger, slett.
    """
    if request.method == 'POST':
        handling = request.POST.get('handling')
        try:
            if handling == 'ny':
                portaler = Vaktportal.objects.filter(
                    pk__in=[int(p) for p in request.POST.getlist('portal') if p.isdigit()])
                t = portaladmin.opprett_tilhorighet(
                    request.POST.get('navn'), request.POST.get('kortnavn'),
                    request.POST.get('type') or Tilhorighet.KORPS, portaler)
                messages.success(request, f'«{t.navn}» er lagt til i katalogen.')
            elif handling in ('rediger', 'slett'):
                pk = request.POST.get('pk', '')
                t = get_object_or_404(Tilhorighet, pk=int(pk) if pk.isdigit() else 0)
                if handling == 'slett':
                    portaladmin.slett_tilhorighet(t)
                    messages.success(request, f'«{t.navn}» er slettet.')
                else:
                    portaladmin.endre_tilhorighet(
                        t, navn=request.POST.get('navn'), kortnavn=request.POST.get('kortnavn'),
                        type_=request.POST.get('type'),
                        er_aktiv=request.POST.get('er_aktiv') == 'on')
                    messages.success(request, f'«{t.navn}» er lagret.')
            else:
                raise ValidationError('Ukjent handling.')
        except ValidationError as feil:
            _vis_feil(request, feil)
        return redirect('portaladmin:tilhorigheter')

    rader = [{'t': t, 'bruk': portaladmin.bruk_av(t),
              'portaler': [p.navn for p in t.portaler.all()]}
             for t in Tilhorighet.objects.prefetch_related('portaler')]
    return render(request, 'core/tilhorigheter.html', {
        'rader': rader,
        'typer': Tilhorighet.TYPE_VALG,
        'portaler': Vaktportal.objects.filter(er_aktiv=True),  # `Meta.ordering` er norsk
    })
