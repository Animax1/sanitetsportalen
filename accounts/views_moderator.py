"""`/moderator/brukere/` — moderatorens brukere i sin portal (fase 5b, 17. okt. 2026).

Reglene står i `accounts/moderering.py`; her står skjemaene og meldingene.
Stiene ligger utenfor `/admin/`, fordi alt der er admin-only og håndheves slik.
Portalen er den kontoen står i — middlewaren har satt den, og fanevakten hindrer
at en innsending havner i en portal moderatoren byttet til i en annen fane.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import moderator_kreves, tom_tilgangscache
from core.models import Kontotilhorighet
from core.portal import gjeldende_portal
from core.ratelimit import rate_limit

from . import moderering
from .forms import ModeratorKontoForm, ModulTilgangForm
from .invitasjon import send_invitasjon
from .models import PortalRolle, Portaltilgang
from .passord import lag_midlertidig_passord
from .views import _log_user_admin_action


def _vis_feil(request, feil: ValidationError) -> None:
    messages.error(request, ' '.join(feil.messages))


def _logg_medlemskap(request, bruker, portal, fra, til):
    _log_user_admin_action(request, bruker, 'UPDATE', field_name=f'medlem i {portal.slug}',
                           old_value=fra, new_value=til, table_name='accounts_portaltilgang')


@never_cache
@moderator_kreves
@require_http_methods(['GET', 'POST'])
@rate_limit(group='moderator:brukere', rate='60/m', method='POST', on_limit='html')
def brukere_view(request):
    """Lista, gruppert på portalens tilhørigheter, og «Legg til valgte».

    **Flere om gangen** (André, 18. okt. 2026: «å legge til flere brukere samtidig må
    være enklere enn å trykke per bruker»). Alle eller ingen: en konto som ikke kan
    legges til, stopper innsendingen, så lista aldri står halvveis oppdatert.
    """
    portal = gjeldende_portal()
    if request.method == 'POST':
        ider = {int(v) for v in request.POST.getlist('bruker') if v.isdigit()}
        kontoer = list(moderering.synlige_kontoer(portal).filter(pk__in=ider))
        if not ider:
            messages.error(request, 'Kryss av for minst én konto.')
        elif len(kontoer) != len(ider):
            messages.error(request, 'Listen inneholder kontoer som ikke hører til portalen — '
                                    'last siden på nytt.')
        else:
            try:
                with transaction.atomic():
                    nye = [k for k in kontoer if moderering.legg_til(request.user, portal, k)]
            except ValidationError as feil:
                _vis_feil(request, feil)
            else:
                for konto in nye:
                    _logg_medlemskap(request, konto, portal, 'nei', 'ja')
                messages.success(request, f'{len(nye)} lagt til i {portal.navn}: '
                                          + ', '.join(k.username for k in nye) + '.')
        return redirect('accounts:moderator_brukere')

    return render(request, 'accounts/moderator_brukere.html', {
        'portal': portal,
        'grupper': moderering.grupper(portal),
        'MODERATOR': PortalRolle.MODERATOR,
    })


@never_cache
@moderator_kreves
@require_http_methods(['GET', 'POST'])
@rate_limit(group='moderator:bruker', rate='60/m', method='POST', on_limit='html')
def bruker_view(request, pk):
    """Én konto: modultilgangen i portalen, og «Fjern fra portalen»."""
    portal = gjeldende_portal()
    bruker = get_object_or_404(moderering.synlige_kontoer(portal), pk=pk)
    tilgang = Portaltilgang.objects.filter(bruker=bruker, portal=portal).first()
    sperre = None
    try:
        moderering.kan_styre(request.user, portal, bruker)
    except ValidationError as feil:
        sperre = ' '.join(feil.messages)

    matrise = ModulTilgangForm(bruker=bruker, portal=portal, utdeler=request.user)
    if request.method == 'POST':
        handling = request.POST.get('handling')
        try:
            if handling == 'fjern':
                if moderering.fjern(request.user, portal, bruker):
                    _logg_medlemskap(request, bruker, portal, 'ja', 'nei')
                messages.success(request, f'{bruker.username} er tatt ut av {portal.navn}. '
                                          'Kontoen står.')
                return redirect('accounts:moderator_brukere')
            if handling != 'moduler':
                raise ValidationError('Ukjent handling.')
            moderering.kan_styre(request.user, portal, bruker)
            if tilgang is None:
                raise ValidationError('Kontoen er ikke med i portalen — legg den til først.')
            matrise = ModulTilgangForm(request.POST, bruker=bruker, portal=portal,
                                       utdeler=request.user)
            if matrise.is_valid():
                for slug, fra, til in matrise.save():
                    _log_user_admin_action(request, bruker, 'UPDATE', field_name=slug,
                                           old_value=fra or 'ingen', new_value=til or 'ingen',
                                           table_name='accounts_modultilgang')
                messages.success(request, 'Tilgangen er lagret.')
                return redirect('accounts:moderator_bruker', pk=bruker.pk)
            messages.error(request, 'Et av nivåene kan ikke deles ut herfra.')
        except ValidationError as feil:
            _vis_feil(request, feil)
            return redirect('accounts:moderator_bruker', pk=bruker.pk)

    return render(request, 'accounts/moderator_bruker.html', {
        'portal': portal,
        'bruker': bruker,
        'tilgang': tilgang,
        'sperre': sperre,
        'matrise': matrise,
        'tilhorigheter': bruker.tilhorigheter.select_related('tilhorighet'),
    })


@never_cache
@moderator_kreves
@require_http_methods(['GET', 'POST'])
@rate_limit(group='moderator:ny', rate='20/m', method='POST', on_limit='html')
def ny_view(request):
    """Ny konto i portalen: en person, med tilgang satt i samme skjema.

    Invitasjon når e-posten finnes og kan brukes, ellers et engangspassord som
    vises én gang — samme to veier som admins skjema.
    """
    portal = gjeldende_portal()
    form = ModeratorKontoForm(portal=portal)
    # Tilgangen settes i samme skjema (André, 18. okt. 2026: «dårlig ux å opprette
    # bruker og så ikke kunne umiddelbart sette tilganger») — med samme grense som
    # på kontosiden: aldri over taket, aldri over hennes eget nivå.
    matrise = ModulTilgangForm(portal=portal, utdeler=request.user)
    if request.method == 'POST':
        form = ModeratorKontoForm(request.POST, portal=portal)
        matrise = ModulTilgangForm(request.POST, portal=portal, utdeler=request.user)
        if form.is_valid() and matrise.is_valid():
            vil_invitere = (request.POST.get('metode', 'invitasjon') == 'invitasjon'
                            and bool(form.cleaned_data.get('email')))
            midlertidig = None
            with transaction.atomic():
                bruker = form.save(commit=False)
                if vil_invitere:
                    bruker.set_unusable_password()
                    bruker.must_change_password = False
                else:
                    midlertidig = lag_midlertidig_passord()
                    bruker.set_password(midlertidig)
                    bruker.must_change_password = True
                bruker.save()
                if form.cleaned_data.get('tilhorighet'):
                    Kontotilhorighet.objects.create(
                        bruker=bruker, tilhorighet=form.cleaned_data['tilhorighet'])
                Portaltilgang.objects.create(bruker=bruker, portal=portal)
                endringer = matrise.save(bruker)
            tom_tilgangscache(bruker)
            _log_user_admin_action(request, bruker, 'CREATE', field_name='username',
                                   new_value=bruker.username)
            _logg_medlemskap(request, bruker, portal, 'nei', 'ja')
            for slug, fra, til in endringer:
                _log_user_admin_action(request, bruker, 'CREATE', field_name=slug,
                                       old_value=fra or 'ingen', new_value=til or 'ingen',
                                       table_name='accounts_modultilgang')

            if midlertidig is not None:
                return render(request, 'accounts/moderator_ny.html', {
                    'portal': portal, 'form': ModeratorKontoForm(portal=portal),
                    'matrise': ModulTilgangForm(portal=portal, utdeler=request.user),
                    'midlertidig': midlertidig, 'ny_bruker': bruker,
                })
            if send_invitasjon(bruker, request):
                messages.success(request, f'«{bruker.username}» er opprettet, og invitasjonen '
                                          f'er sendt til {bruker.email}.')
            else:
                messages.warning(request, f'«{bruker.username}» er opprettet, men invitasjonen '
                                          'kunne ikke sendes. Be en administrator sende den '
                                          'på nytt.')
            return redirect('accounts:moderator_bruker', pk=bruker.pk)

    return render(request, 'accounts/moderator_ny.html', {
        'portal': portal, 'form': form, 'matrise': matrise,
    })
