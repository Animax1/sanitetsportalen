"""Vaktarkivet for oppdrag: arkivering, visning og sletting (fase 7).

Egen fil, ikke flere hundre linjer til i `views.py`. Skillet følger
pasientmodulen, der arkivet ligger i `views_arkiv.py` av samme grunn.

**Alle fire endepunktene krever global admin**, ikke `skriv_full`. Arkivering
fryser en hel vakt og starter en 24-måneders klokke mot en irreversibel
kollaps; sletting fjerner arkivet for godt. §3.3 i beslutningsnotatet
reserverer det irreversible for admin — og det er samme gate som
pasientarkivet står bak.

Enhetskontoer får 403 uansett nivå, som ellers i modulen: bilen ser sine egne
oppdrag, ikke vaktas arkiv.
"""
from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.arkiv import verifiser
from core.auth_decorators import er_global_admin, modul_kreves
from patients.services import hent_aktiv_vakt

from .arkiv import OppdragArkivHandler, arkiver_vakt
from .models import OppdragArkiv
from .statistikk import arkiv_stats
from .views_common import json_body

logger = logging.getLogger(__name__)


def _logg_audit(request, handling, detalj):
    """Arkivhendelser i auditsporet.

    Signalet i `oppdrag/signals.py` logger feltendringer på oppdrag, ikke
    handlinger på et arkiv — og «hvem arkiverte vakta, og når» er nettopp det
    man leter etter i ettertid.
    """
    from audit.models import AuditLog
    AuditLog.objects.create(
        table_name='oppdrag_oppdragarkiv',
        record_id=0,
        action='CREATE',
        field_name=handling,
        new_value=detalj,
        user=request.user if request.user.is_authenticated else None,
        ip=request.META.get('REMOTE_ADDR'),
    )


def _arkiv_til_dict(arkiv, *, med_stats=False):
    data = {
        'id': arkiv.pk,
        'tittel': arkiv.tittel,
        'vakt_navn': arkiv.vakt_navn,
        'antall_oppdrag': arkiv.antall_rader,
        'importert_at': arkiv.importert_at.isoformat(),
        'importert_av': arkiv.importert_av_visning,
        'notat': arkiv.notat,
        'sha256': arkiv.sha256,
        # Grensesnittet må kunne skille et arkiv med rader fra ett som bare
        # har frosne tall igjen — ellers ser de like ut, mens
        # integritetssjekken dekker to helt ulike ting.
        'kollapset': arkiv.er_kollapset,
        'kollapset_at': (
            arkiv.kollapset_at.isoformat() if arkiv.kollapset_at else None),
    }
    if med_stats:
        data['tamper_detected'] = verifiser(OppdragArkivHandler(), arkiv)
        data['stats'] = (
            (arkiv.aggregat or {}).get('full') if arkiv.er_kollapset
            else arkiv_stats(arkiv)
        )
    return data


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
def arkiv_liste_view(request):
    """Liste arkivene (GET), eller arkiver den aktive vakta (POST)."""
    if not er_global_admin(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'data': [
            _arkiv_til_dict(a) for a in
            OppdragArkiv.objects.select_related('importert_av')
        ]})

    vakt = hent_aktiv_vakt()
    notat = (json_body(request).get('notat') or '').strip()
    try:
        arkiv, antall = arkiver_vakt(vakt, notat, request.user)
    except Exception:
        # Samme svar som pasientarkivet: en halvferdig arkivering er rullet
        # tilbake av transaksjonen, og detaljene hører hjemme i logg, ikke i
        # et API-svar.
        logger.exception('Feil ved arkivering av oppdrag for vakt %s', vakt.pk)
        return JsonResponse(
            {'status': 'error', 'message': 'Arkivering feilet. Se server-logg.'},
            status=500)

    _logg_audit(request, 'arkiv_lagret',
                f'arkiv_id={arkiv.pk}, vakt={vakt.navn}, antall={antall}')
    return JsonResponse(
        {'status': 'ok', 'data': _arkiv_til_dict(arkiv)}, status=201)


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'DELETE'])
def arkiv_detalj_view(request, pk):
    """Vis ett arkiv med tall og integritetssjekk (GET), eller slett det.

    Sletting krever ``{"confirm": true}``. Arkivet er det eneste som står
    igjen etter at vakta er avsluttet og oppdragene slettet, så et feilklikk
    her koster mer enn de fleste andre steder i portalen.
    """
    if not er_global_admin(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    try:
        arkiv = OppdragArkiv.objects.select_related('importert_av').get(pk=pk)
    except OppdragArkiv.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Arkiv ikke funnet'}, status=404)

    if request.method == 'GET':
        return JsonResponse(
            {'status': 'ok', 'data': _arkiv_til_dict(arkiv, med_stats=True)})

    if not json_body(request).get('confirm'):
        return JsonResponse(
            {'status': 'error',
             'message': 'Bekreftelse mangler. Send {"confirm": true} for å slette.'},
            status=400)

    tittel = arkiv.tittel
    arkiv.delete()   # CASCADE tar de arkiverte oppdragene
    _logg_audit(request, 'arkiv_slettet', f'arkiv_id={pk}, tittel={tittel}')
    return JsonResponse({'status': 'ok'})
