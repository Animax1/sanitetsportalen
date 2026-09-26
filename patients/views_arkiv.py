"""Vaktarkivet: arkivering, visning og sletting.

Skilt ut fra ``views.py`` i N13.3.
"""
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.arkiv import get_handler, logg_arkivhendelse, verifiser
from core.auth_decorators import er_global_admin, modul_kreves
from core.ratelimit import rate_limit

from .services import arkiver_aktiv_vakt, compute_arkiv_stats
from .views_common import _json_body

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# VAKTARKIV – database-basert arkiv av vakter
# ════════════════════════════════════════════════════════════════════════

@modul_kreves('patients', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='patients:arkiv', rate='10/m', method='POST')
def arkiv_lagre_view(request):
    """Lagre aktiv vakt som arkiv-snapshot. Kun admin.

    Body: {arrangement_navn: str, notat: str (valgfri)}
    Returnerer: {ok: true, id, tittel, antall_pasienter}
    """
    if not er_global_admin(request.user):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    arrangement_navn = (data.get('arrangement_navn') or '').strip()
    if not arrangement_navn:
        return JsonResponse({'error': 'arrangement_navn er påkrevd'}, status=400)

    notat = (data.get('notat') or '').strip()

    try:
        arkiv, antall = arkiver_aktiv_vakt(arrangement_navn, notat, request.user)
    except Exception:
        logger.exception('Feil ved arkivering av vakt')
        return JsonResponse({'error': 'Arkivering feilet. Se server-logg.'}, status=500)

    logg_arkivhendelse(type(arkiv), 'arkiv_lagret', f'arkiv_id={arkiv.pk}, tittel={arkiv.tittel}',
                       request=request, record_id=arkiv.pk)
    return JsonResponse({
        'ok': True,
        'id': arkiv.pk,
        'tittel': arkiv.tittel,
        'antall_pasienter': antall,
    }, status=201)


@modul_kreves('patients', 'les', svar='json')
@require_http_methods(['GET'])
def arkiv_liste_view(request):
    """Liste alle arkiver. Global admin.

    Returnerer: [{id, tittel, arrangement_navn, importert_at, antall_pasienter, importert_av}]
    """
    if not er_global_admin(request.user):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    from .models import VaktArkiv
    arkiver = VaktArkiv.objects.select_related('importert_av').all()
    data = [{
        'id': a.pk,
        'tittel': a.tittel,
        'arrangement_navn': a.arrangement_navn,
        'importert_at': a.importert_at.isoformat(),
        'antall_pasienter': a.antall_pasienter,
        'importert_av': a.importert_av_visning,
    } for a in arkiver]
    return JsonResponse(data, safe=False)


@modul_kreves('patients', 'les', svar='json')
@require_http_methods(['GET', 'DELETE'])
@rate_limit(group='patients:arkiv-slett', rate='10/m', method='DELETE')
def arkiv_detalj_view(request, pk):
    """Vis (GET) eller slett (DELETE) et arkiv.

    GET: Returnerer full statistikk + metadata + SHA-256-verifikasjon.
    DELETE: Krever admin og {confirm: true} i body.
    """
    from .models import VaktArkiv

    try:
        arkiv = VaktArkiv.objects.select_related('importert_av').get(pk=pk)
    except VaktArkiv.DoesNotExist:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)

    if request.method == 'GET':
        if not er_global_admin(request.user):
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        stats = compute_arkiv_stats(arkiv)

        # **`core.arkiv.verifiser`, som oppdrag bruker** (26. sep. 2026, E3).
        # Til da sto regelen skrevet ut her — radsignaturen, eller aggregatets
        # etter kollaps — og en endring i den ene ville gitt to svar på
        # «er arkivet tuklet med». Handleren henter radene med samme funksjon
        # som arkiveringen brukte.
        tamper_detected = verifiser(get_handler('patients'), arkiv)

        return JsonResponse({
            'id': arkiv.pk,
            'tittel': arkiv.tittel,
            'arrangement_navn': arkiv.arrangement_navn,
            'importert_at': arkiv.importert_at.isoformat(),
            'importert_av': arkiv.importert_av_visning,
            'antall_pasienter': arkiv.antall_pasienter,
            'year_snapshot': arkiv.year_snapshot,
            'notat': arkiv.notat,
            'sha256': arkiv.sha256,
            'tamper_detected': tamper_detected,
            # Grensesnittet må kunne skille et arkiv med pasientrader fra ett
            # som kun har frosne tall igjen — ellers ser de like ut, mens
            # integritetssjekken i praksis dekker to helt ulike ting.
            'kollapset': arkiv.er_kollapset,
            'kollapset_at': (
                arkiv.kollapset_at.isoformat() if arkiv.kollapset_at else None
            ),
            'stats': stats,
        })

    # DELETE
    if not er_global_admin(request.user):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    if not data.get('confirm'):
        return JsonResponse(
            {'error': 'Bekreftelse mangler. Send {\"confirm\": true} for å slette.'},
            status=400,
        )

    tittel = arkiv.tittel
    arkiv.delete()  # CASCADE sletter ArkivertPasient-rader
    logg_arkivhendelse(VaktArkiv, 'arkiv_slettet', f'arkiv_id={pk}, tittel={tittel}',
                       request=request, record_id=pk)
    return JsonResponse({'ok': True})
