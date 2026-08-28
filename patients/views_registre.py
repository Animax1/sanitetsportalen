"""Navneregistrene: Forstehjelper og Helsepersonell.

Skilt ut fra ``views.py`` i N13.3. Begge registrene bygges av samme fabrikk —
se N13.2.
"""
import hashlib

from django.http import JsonResponse, HttpResponseNotModified
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import modul_kreves

from .models import Forstehjelper, Helsepersonell
from .views_common import _json_body


# ── Navneregistre: Forstehjelper og Helsepersonell ────────────────────────────
#
# De to modellene har identisk form — `name`, `user`, `is_active` — og hadde
# fire views som var ord for ord like bortsett fra modellnavnet og ordlyden i
# feilmeldingene, inkludert ETag-blokken og ProtectedError-håndteringen (N13).
#
# Fabrikken under bygger begge par. Oppførselen er uendret; feilmeldingene er
# bevart ordrett, siden de vises direkte i grensesnittet.


def _navneliste_views(model, etikett, etikett_bestemt):
    """Bygg (liste-view, detalj-view) for et navneregister.

    Args:
        model: Forstehjelper eller Helsepersonell
        etikett: ubestemt form til feilmeldinger («Førstehjelper»)
        etikett_bestemt: bestemt form («Førstehjelperen»)
    """

    @never_cache
    @modul_kreves('patients', 'les', svar='json')
    @require_http_methods(['GET', 'POST'])
    def liste_view(request):
        """Liste alle (GET), eller opprett ny (POST, kun admin).

        GET returnerer alle rader (inkl. inaktive) sortert etter is_active desc,
        name. Støtter ETag/304-mønsteret:
          - Beregner ETag basert på innholdet. Hvis klienten sender
            If-None-Match med samme ETag, returneres 304 uten kropp.
          - never_cache og ETag er kompatible: never_cache sier «bekreft med
            server» og ETag sier «hvis samme, send 304».
        """
        if request.method == 'GET':
            rader = list(model.objects.all().order_by('-is_active', 'name'))
            data = [{'id': r.id, 'name': r.name, 'is_active': r.is_active} for r in rader]

            # ETag som SHA-256-hash av (id, name, is_active)-tupler. sha256
            # brukes kun for identitet (ikke sikkerhet), og kortes til 16 tegn
            # for å holde header-verdien kompakt.
            hash_input = str(sorted([(r.id, r.name, r.is_active) for r in rader]))
            etag_value = '"v1:' + hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:16] + '"'

            if request.META.get('HTTP_IF_NONE_MATCH') == etag_value:
                return HttpResponseNotModified()

            response = JsonResponse(data, safe=False)
            response['ETag'] = etag_value
            response['Cache-Control'] = 'private, must-revalidate'
            return response

        # POST – kun admin
        if request.user.role != 'admin':
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        data = _json_body(request)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Navn er påkrevd'}, status=400)

        if model.objects.filter(name=name).exists():
            return JsonResponse(
                {'error': f'{etikett} "{name}" finnes allerede'}, status=400)

        rad = model.objects.create(name=name, is_active=True)
        return JsonResponse(
            {'id': rad.id, 'name': rad.name, 'is_active': rad.is_active}, status=201)

    @modul_kreves('patients', 'les', svar='json')
    @require_http_methods(['PUT', 'DELETE'])
    def detalj_view(request, pk):
        """Oppdater (PUT) eller slett (DELETE). Kun admin."""
        if request.user.role != 'admin':
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        try:
            rad = model.objects.get(pk=pk)
        except model.DoesNotExist:
            return JsonResponse({'error': f'{etikett} ikke funnet'}, status=404)

        if request.method == 'PUT':
            data = _json_body(request)
            if 'name' in data:
                name = (data['name'] or '').strip()
                if not name:
                    return JsonResponse({'error': 'Navn kan ikke være tomt'}, status=400)
                rad.name = name
            if 'is_active' in data:
                rad.is_active = bool(data['is_active'])
            rad.save()
            return JsonResponse(
                {'id': rad.id, 'name': rad.name, 'is_active': rad.is_active})

        # DELETE – blokkert hvis raden er i bruk (PROTECT gir ProtectedError)
        from django.db.models.deletion import ProtectedError
        try:
            rad.delete()
            return JsonResponse({'ok': True})
        except ProtectedError:
            return JsonResponse(
                {'error': f'{etikett_bestemt} er knyttet til pasienter og kan '
                          f'ikke slettes. Deaktiver i stedet.'},
                status=409,
            )

    return liste_view, detalj_view


forstehjelpere_view, forstehjelper_detail_view = _navneliste_views(
    Forstehjelper, 'Førstehjelper', 'Førstehjelperen')
helsepersonell_view, helsepersonell_detail_view = _navneliste_views(
    Helsepersonell, 'Helsepersonell', 'Helsepersonellet')

# Navn for feilsøking og Djangos URL-reversering — uten dette heter alle fire
# `liste_view`/`detalj_view` i tracebacks.
forstehjelpere_view.__name__ = 'forstehjelpere_view'
forstehjelper_detail_view.__name__ = 'forstehjelper_detail_view'
helsepersonell_view.__name__ = 'helsepersonell_view'
helsepersonell_detail_view.__name__ = 'helsepersonell_detail_view'


