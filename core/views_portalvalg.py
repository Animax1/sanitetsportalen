"""Portalvelgeren (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.4).

Viser portalene kontoen kan stå i, og skriver valget i sesjonen. Middlewaren
sender hit når valget ikke er entydig, med `?neste=` tilbake dit brukeren
skulle. Med én mulig portal velges den uten at denne siden vises.

**Valget kontrolleres mot de mulige ved innsending**, ikke bare ved visning:
en portal kontoen ikke er med i, eller som er deaktivert, kan ikke velges ved
å sende ID-en for hånd.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from core.portal import SESJON_NOKKEL, mulige_portaler


def _trygg_neste(request, neste):
    if neste and url_has_allowed_host_and_scheme(
            neste, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return neste
    return '/'


@login_required
@require_http_methods(['GET', 'POST'])
def velg_view(request):
    mulige = list(mulige_portaler(request.user))
    neste = request.POST.get('neste') or request.GET.get('neste') or ''
    feil = None
    if request.method == 'POST':
        valgt = next((p for p in mulige if p.slug == request.POST.get('portal')), None)
        if valgt is not None:
            request.session[SESJON_NOKKEL] = valgt.pk
            return redirect(_trygg_neste(request, neste))
        feil = 'Den portalen kan du ikke velge.'
    return render(request, 'core/velg_portal.html', {
        'mulige': mulige,
        'valgt_id': request.session.get(SESJON_NOKKEL),
        'neste': neste,
        'feil': feil,
    }, status=400 if feil else 200)
