"""Vaktarkivet: arkivering, visning og sletting.

Skilt ut fra ``views.py`` i N13.3.
"""
import hashlib
import json as _jmod
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .services import (
    has_role_at_least, ARKIV_VIEW_MIN_ROLE, ARKIV_WRITE_ROLE,
    arkiver_aktiv_vakt, compute_arkiv_stats, compute_arkiv_full_stats,
)
from .views_common import _json_body

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# BACKUP / RESTORE
# ═══════════════════════════════════════════════════════════════════════

def _log_audit(request, action, detail):
    """Hjelpefunksjon for å logge backup-hendelser til AuditLog."""
    from audit.models import AuditLog
    AuditLog.objects.create(
        table_name='backup',
        record_id=0,
        action='CREATE',
        field_name=action,
        new_value=detail,
        user=request.user if request.user.is_authenticated else None,
        ip=request.META.get('REMOTE_ADDR'),
    )


# ════════════════════════════════════════════════════════════════════════
# VAKTARKIV – database-basert arkiv av vakter
# ════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(['POST'])
def arkiv_lagre_view(request):
    """Lagre aktiv vakt som arkiv-snapshot. Kun admin.

    Body: {arrangement_navn: str, notat: str (valgfri)}
    Returnerer: {ok: true, id, tittel, antall_pasienter}
    """
    if not has_role_at_least(request.user, ARKIV_WRITE_ROLE):
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

    _log_audit(request, 'arkiv_lagret', f'arkiv_id={arkiv.pk}, tittel={arkiv.tittel}')
    return JsonResponse({
        'ok': True,
        'id': arkiv.pk,
        'tittel': arkiv.tittel,
        'antall_pasienter': antall,
    }, status=201)


@login_required
@require_http_methods(['GET'])
def arkiv_liste_view(request):
    """Liste alle arkiver. Krever ARKIV_VIEW_MIN_ROLE (standard: admin).

    Returnerer: [{id, tittel, arrangement_navn, importert_at, antall_pasienter, importert_av}]
    """
    if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
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


@login_required
@require_http_methods(['GET', 'DELETE'])
def arkiv_detalj_view(request, pk):
    """Vis (GET) eller slett (DELETE) et arkiv.

    GET: Returnerer full statistikk + metadata + SHA-256-verifikasjon.
    DELETE: Krever admin og {confirm: true} i body.
    """
    from .models import VaktArkiv
    import hashlib
    import json as _jmod

    try:
        arkiv = VaktArkiv.objects.select_related('importert_av').get(pk=pk)
    except VaktArkiv.DoesNotExist:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)

    if request.method == 'GET':
        if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        stats = compute_arkiv_stats(arkiv)

        # SHA-256-verifikasjon. Kilden avhenger av om arkivet er kollapset:
        # etter kollaps finnes ikke pasientradene lenger, og `sha256` (som er
        # beregnet over dem) kan aldri verifiseres igjen. Da sjekkes det
        # frosne aggregatet i stedet.
        if arkiv.er_kollapset:
            from .services import _compute_sha256_for_aggregat
            sha_now = _compute_sha256_for_aggregat(arkiv, arkiv.aggregat or {})
            tamper_detected = bool(
                arkiv.aggregat_sha256 and sha_now != arkiv.aggregat_sha256
            )
        else:
            # Samme helper som arkiveringen brukte — verifikasjonen må lese
            # nøyaktig de feltene signaturen ble beregnet over.
            from .services import _compute_sha256_for_arkiv, _arkiv_pasienter_dicts
            sha_now = _compute_sha256_for_arkiv(arkiv, _arkiv_pasienter_dicts(arkiv))
            tamper_detected = bool(arkiv.sha256 and sha_now != arkiv.sha256)

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
    if not has_role_at_least(request.user, ARKIV_WRITE_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    if not data.get('confirm'):
        return JsonResponse(
            {'error': 'Bekreftelse mangler. Send {\"confirm\": true} for å slette.'},
            status=400,
        )

    tittel = arkiv.tittel
    arkiv.delete()  # CASCADE sletter ArkivertPasient-rader
    _log_audit(request, 'arkiv_slettet', f'arkiv_id={pk}, tittel={tittel}')
    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['GET'])
def arkiv_full_stats_view(request, pk):
    """Returner full statistikk for et arkivert vakt.

    Samme struktur som /api/full-stats/ (chi2, Kruskal-Wallis,
    krysstabeller, tids-statistikk pr. gruppe, ankomster, obs-stats).
    Tilgang: ARKIV_VIEW_MIN_ROLE (default admin).
    """
    from .models import VaktArkiv

    if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    try:
        arkiv = VaktArkiv.objects.get(pk=pk)
    except VaktArkiv.DoesNotExist:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)

    stats = compute_arkiv_full_stats(arkiv)
    return JsonResponse(stats)
