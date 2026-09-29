"""Vaktarkivet for oppdrag: visning og sletting (fase 7).

Arkiveringen gjør «Avslutt vakt» (`oppdrag/vaktslutt.py`) siden 28. sep. 2026.

Egen fil, ikke flere hundre linjer til i `views.py`. Skillet følger
pasientmodulen, der arkivet ligger i `views_arkiv.py` av samme grunn.

**Alle endepunktene krever global admin**, ikke `skriv_full`. Arkivering
fryser en hel vakt og starter en 24-måneders klokke mot en irreversibel
kollaps; sletting fjerner arkivet for godt. §3.3 i beslutningsnotatet
reserverer det irreversible for admin — og det er samme gate som
pasientarkivet står bak.

Enhetskontoer får 403 uansett nivå, som ellers i modulen: bilen ser sine egne
oppdrag, ikke vaktas arkiv.
"""
from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body
from core.arkiv import verifiser
from core.auth_decorators import er_global_admin, modul_kreves
from core.ratelimit import rate_limit

from .arkiv import OppdragArkivHandler
from .models import OppdragArkiv
from .statistikk import arkiv_stats



def _antall_oppdrag(arkiv) -> int:
    if arkiv.er_kollapset:
        total = ((arkiv.aggregat or {}).get('full') or {}).get('summary', {}).get('total')
        return arkiv.antall_rader if total is None else total
    return arkiv.oppdrag.values('oppdragsnummer').distinct().count()


def _arkiv_til_dict(arkiv, *, med_stats=False):
    data = {
        'id': arkiv.pk,
        'tittel': arkiv.tittel,
        'vakt_navn': arkiv.vakt_navn,
        # Radene er én per oppdrag × enhet (11. sep. 2026); oppdragene
        # telles distinkt. Etter kollaps finnes bare aggregatet, og det bærer
        # tallet i `summary.total`.
        'antall_oppdrag': _antall_oppdrag(arkiv),
        'antall_enhetsrader': arkiv.antall_rader,
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
@require_http_methods(['GET'])
def arkiv_liste_view(request):
    """Arkivene. Global admin.

    POST — «arkiver den aktive vakta» — er slettet 28. sep. 2026: «Avslutt vakt»
    på `/portal-admin/vakt/` arkiverer oppdragene med resten
    (`oppdrag/vaktslutt.py`), med samme sperre mot oppdrag på tavla.
    """
    if not er_global_admin(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Ingen tilgang'}, status=403)
    return JsonResponse({'status': 'ok', 'data': [
        _arkiv_til_dict(a) for a in
        OppdragArkiv.objects.select_related('importert_av')
    ]})


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'DELETE'])
@rate_limit(group='oppdrag:arkiv-slett', rate='10/m', method='DELETE')
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

    # Gjennom `core.vaktsletting.slett_arkiv`, som tar en backup først og
    # skriver auditraden — samme vei som vakt-siden (28. sep. 2026).
    from core.vaktsletting import KanIkkeSlettes, slett_arkiv
    try:
        slett_arkiv('oppdrag', arkiv.pk, bruker=request.user, request=request)
    except KanIkkeSlettes as feil:
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=409)
    except ObjectDoesNotExist:
        # Slettet av en annen imens — `slett_arkiv` henter på nytt under sperren.
        return JsonResponse({'status': 'error', 'message': 'Arkivet er allerede slettet.'},
                            status=404)
    return JsonResponse({'status': 'ok'})
