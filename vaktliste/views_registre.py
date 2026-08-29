"""Registersiden: mannskapet og de tre verdimengdene admin styrer.

**Hvorfor denne fila finnes.** Fase 1 la registrene i `vaktliste/admin.py` og
skrev at «Django-admin er uansett riktig hjem for `Korps`, `Kompetanse` og
`VaktRolle`». Det var feil: `/django-admin/` er kun rutet når `DEBUG` eller
`OFFLINE_MODE` er på (S1 — den er en parallell innloggingsflate som omgår
rate-limiting, kontosperre, MFA-tvang og `LoginEvent`). I produksjon fantes det
dermed ingen vei til å opprette et korps eller et mannskap, og
planleggingssiden hadde en nedtrekksliste som aldri kunne fylles.

`admin.py` blir stående som utviklerverktøy lokalt. Den er ikke flaten
portalen bruker.

**Egen side, ikke en fane på planleggingssiden.** Registrene er *globale* —
personellet organisasjonen har — mens fanene på `/vaktliste/` er ressursene i
*én* vakt. To ulike omfang i samme faneliste ville sagt at «Mannskap» er noe
som hører til oktobervakta.

**Mannskapslista er ikke et admin-skjermbilde, den er bestillingen.** Første
setning i det André ba om var «lister opp personell overordnet sortert etter
hvilket korps de tilhører, kompetanse, rolle under vakt». Derfor er lista
gruppert på korps og viser kompetansene, framfor å være en flat tabell med en
blyant på hver rad.

**Sletting er ikke veien ut av et register.** `Mannskap`, `Korps` og
`VaktRolle` er PROTECT-et fra rader som beskriver historikk, og `Kompetanse`
er blokkert her selv om M2M-en ikke ville protestert — å slette den ville
stilltiende strippet kompetansen fra alle som har den. Pensjonering
(`er_aktiv=False`) er den normale veien ut, som i pasientmodulens
navneregistre.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, modul_kreves
from core.ratelimit import rate_limit

from .models import Kompetanse, Korps, Mannskap, VaktRolle
from .views import _feil, _int, _json_body, _nektet


def _ider(raa):
    """Liste med klientverdier → liste med gyldige int-er.

    `.set()` med en ikke-numerisk verdi i lista kaster, og feilen kommer fra
    Django framfor fra oss. Silen her gjør at et rusket element blir ignorert
    i stedet for å ta ned hele lagringen.
    """
    if not isinstance(raa, (list, tuple)):
        return []
    return [i for i in (_int(v) for v in raa) if i is not None]


# ── Siden ────────────────────────────────────────────────────────────────────

@modul_kreves('vaktliste', 'les')
@require_http_methods(['GET'])
def registre_view(request):
    """Mannskaps- og registersiden.

    Admin-only i fase 2, som resten av modulen: `kan_redigere_mannskap()`
    finnes og er testet, men badgen den avgrenser på håndheves først i fase 3.
    """
    if not er_global_admin(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return render(request, 'vaktliste/registre.html')


# ── De tre verdimengdene ─────────────────────────────────────────────────────
#
# `Korps`, `Kompetanse` og `VaktRolle` har samme form — navn, er_aktiv,
# rekkefolge — og fire views hver ville vært ord for ord like bortsett fra
# modellnavnet. Samme grep som `patients/views_registre.py` (N13.2), og av
# samme grunn: tre kopier er tre steder en rettelse kan bli glemt.
#
# Korps har ett felt til (`kortnavn`), og fabrikken tar derfor en liste over
# valgfrie tekstfelter framfor å bli to fabrikker.

def _register_views(model, etikett, etikett_bestemt, *, ekstra_felt=()):
    """Bygg (liste-view, detalj-view) for en av verdimengdene.

    Args:
        model: Korps, Kompetanse eller VaktRolle
        etikett: ubestemt form til feilmeldinger («Korpset» → «Korps»)
        etikett_bestemt: bestemt form, til «… er i bruk»-meldingen
        ekstra_felt: valgfrie tekstfelter modellen har utover navn
    """

    def _til_dict(rad):
        ut = {
            'id': rad.pk,
            'navn': rad.navn,
            'er_aktiv': rad.er_aktiv,
            'rekkefolge': rad.rekkefolge,
            'i_bruk': _antall_bruk(model, rad),
        }
        for felt in ekstra_felt:
            ut[felt] = getattr(rad, felt)
        return ut

    @never_cache
    @modul_kreves('vaktliste', 'les', svar='json')
    @require_http_methods(['GET', 'POST'])
    @rate_limit(group=f'vaktliste:register:{model._meta.model_name}',
                rate='60/m', method='POST')
    def liste_view(request):
        if not er_global_admin(request.user):
            return _nektet()

        if request.method == 'GET':
            # Inaktive er med: de skal kunne aktiveres igjen, og en rad som
            # forsvinner helt ser ut som en sletting som ikke skjedde.
            return JsonResponse({'status': 'ok', 'data': [
                _til_dict(r) for r in model.objects.all()]})

        data = _json_body(request)
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil(f'{etikett} må ha et navn.')

        felter = {felt: (data.get(felt) or '').strip() for felt in ekstra_felt}
        try:
            with transaction.atomic():
                rad = model.objects.create(
                    navn=navn,
                    rekkefolge=_int(data.get('rekkefolge')) or 100,
                    **felter,
                )
        except IntegrityError:
            return _feil(f'«{navn}» finnes allerede.')
        return JsonResponse({'status': 'ok', 'data': _til_dict(rad)}, status=201)

    @modul_kreves('vaktliste', 'les', svar='json')
    @require_http_methods(['PUT', 'DELETE'])
    def detalj_view(request, pk):
        if not er_global_admin(request.user):
            return _nektet()

        try:
            rad = model.objects.get(pk=pk)
        except model.DoesNotExist:
            return _feil(f'{etikett} ikke funnet', status=404)

        if request.method == 'DELETE':
            # PROTECT dekker Korps og VaktRolle. Kompetanse er en M2M og ville
            # sluppet gjennom — og stilltiende strippet kompetansen fra alle
            # som har den. Telle-sjekken under gjelder derfor alle tre.
            if _antall_bruk(model, rad):
                return _feil(
                    f'{etikett_bestemt} er i bruk og kan ikke slettes. '
                    f'Sett den inaktiv i stedet — da skjules den i '
                    f'nedtrekkslistene, men beholdes der den alt er brukt.',
                    status=409)
            try:
                rad.delete()
            except ProtectedError:
                return _feil(
                    f'{etikett_bestemt} er i bruk og kan ikke slettes. '
                    f'Sett den inaktiv i stedet.', status=409)
            return JsonResponse({'status': 'ok'})

        data = _json_body(request)
        if 'navn' in data:
            navn = (data.get('navn') or '').strip()
            if not navn:
                return _feil(f'{etikett} må ha et navn.')
            rad.navn = navn
        for felt in ekstra_felt:
            if felt in data:
                setattr(rad, felt, (data.get(felt) or '').strip())
        if 'er_aktiv' in data:
            rad.er_aktiv = bool(data['er_aktiv'])
        if 'rekkefolge' in data:
            rad.rekkefolge = _int(data['rekkefolge']) or 100

        try:
            with transaction.atomic():
                rad.save()
        except IntegrityError:
            return _feil(f'«{rad.navn}» finnes allerede.')
        return JsonResponse({'status': 'ok', 'data': _til_dict(rad)})

    return liste_view, detalj_view


def _antall_bruk(model, rad):
    """Hvor mange rader som viser til denne — grunnlaget for «kan slettes».

    Tallet vises også i lista: en verdimengde man kan slette uten å vite hva
    som henger i den, sletter man for lett.
    """
    if model is Korps:
        return rad.mannskap.count() + rad.reserverte_ressurser.count()
    if model is Kompetanse:
        return rad.mannskap.count()
    return rad.vaktposter.count()          # VaktRolle


korps_view, korps_detalj_view = _register_views(
    Korps, 'Korpset', 'Korpset', ekstra_felt=('kortnavn',))
kompetanser_view, kompetanse_detalj_view = _register_views(
    Kompetanse, 'Kompetansen', 'Kompetansen')
roller_view, rolle_detalj_view = _register_views(
    VaktRolle, 'Rollen', 'Rollen')

# Navn for tracebacks og URL-reversering — uten dette heter alle seks
# `liste_view`/`detalj_view`. Samme grep som i pasientmodulen.
korps_view.__name__ = 'korps_view'
korps_detalj_view.__name__ = 'korps_detalj_view'
kompetanser_view.__name__ = 'kompetanser_view'
kompetanse_detalj_view.__name__ = 'kompetanse_detalj_view'
roller_view.__name__ = 'roller_view'
rolle_detalj_view.__name__ = 'rolle_detalj_view'


# ── Mannskapet ───────────────────────────────────────────────────────────────

def _mannskap_til_dict(m):
    return {
        'id': m.pk,
        'navn': m.navn,
        'korps_id': m.korps_id,
        'korps_navn': m.korps.navn,
        'korps_kort': m.korps.kortnavn or m.korps.navn,
        'kompetanser': [
            {'id': k.pk, 'navn': k.navn} for k in m.kompetanser.all()],
        'telefon': m.telefon,
        'user_id': m.user_id,
        'brukernavn': m.user.username if m.user else '',
        'er_aktiv': m.er_aktiv,
        'notat': m.notat,
        # Er personen satt opp noe sted, kan raden ikke slettes. Klienten
        # trenger å vite det før knappen trykkes, ikke etterpå.
        'i_bruk': m.vaktposter.count(),
    }


def _kontoer():
    """Kontoene, med hvilket mannskap hver er koblet til.

    `Mannskap.user` er en OneToOne, så en konto som alt er tatt kan ikke velges
    på nytt. Klienten trenger likevel å se den koblede kontoen når *den*
    personen redigeres — derfor sendes `mannskap_id` med, framfor at serveren
    filtrerer og etterlater et tomt nedtrekk på personen som faktisk har en
    konto.
    """
    from accounts.models import CustomUser
    return [
        {'id': u.pk, 'brukernavn': u.username,
         'mannskap_id': getattr(u, 'mannskap', None) and u.mannskap.pk}
        for u in (CustomUser.objects
                  .filter(is_active=True)
                  .select_related('mannskap')
                  .order_by('username'))
    ]


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='vaktliste:mannskap', rate='60/m', method='POST')
def mannskap_view(request):
    """Hele mannskapsregisteret (GET), eller legg til en person (POST).

    GET sender også de tre verdimengdene og de ledige kontoene: siden trenger
    alle fire for å tegne seg, og fire kall der ett holder er fire steder noe
    kan komme i utakt.
    """
    if not er_global_admin(request.user):
        return _nektet()

    if request.method == 'GET':
        folk = (Mannskap.objects
                .select_related('korps', 'user')
                .prefetch_related('kompetanser'))
        return JsonResponse({'status': 'ok', 'data': {
            'mannskap': [_mannskap_til_dict(m) for m in folk],
            'korps': [{'id': k.pk, 'navn': k.navn, 'kortnavn': k.kortnavn,
                       'er_aktiv': k.er_aktiv}
                      for k in Korps.objects.all()],
            'kompetanser': [{'id': k.pk, 'navn': k.navn, 'er_aktiv': k.er_aktiv}
                            for k in Kompetanse.objects.all()],
            'roller': [{'id': r.pk, 'navn': r.navn, 'er_aktiv': r.er_aktiv}
                       for r in VaktRolle.objects.all()],
            'kontoer': _kontoer(),
        }})

    data = _json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return _feil('Personen må ha et navn.')

    korps = Korps.objects.filter(pk=_int(data.get('korps_id'))).first()
    if korps is None:
        # Uten korps finnes ingen badge, og personen kan verken sorteres i
        # lista eller redigeres av en korps-bruker fra fase 3.
        return _feil('Velg hvilket korps personen hører til.')

    try:
        with transaction.atomic():
            person = Mannskap.objects.create(
                navn=navn,
                korps=korps,
                telefon=(data.get('telefon') or '').strip(),
                user_id=_int(data.get('user_id')),
                notat=(data.get('notat') or '').strip(),
            )
            person.kompetanser.set(_ider(data.get('kompetanse_ider')))
    except IntegrityError:
        return _feil(f'«{navn}» finnes allerede i {korps.navn}. '
                     f'To like navn i samme korps er umulige å skille i lista.')

    person = (Mannskap.objects.select_related('korps', 'user')
              .prefetch_related('kompetanser').get(pk=person.pk))
    return JsonResponse(
        {'status': 'ok', 'data': _mannskap_til_dict(person)}, status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def mannskap_detalj_view(request, pk):
    """Rediger en person, eller fjern en som aldri ble satt opp.

    Fra fase 3 gates dette på `services.kan_redigere_mannskap()` — regelen
    finnes og er testet, men badgen den avgrenser på håndheves ikke ennå.
    """
    if not er_global_admin(request.user):
        return _nektet()

    try:
        person = (Mannskap.objects.select_related('korps', 'user')
                  .prefetch_related('kompetanser').get(pk=pk))
    except Mannskap.DoesNotExist:
        return _feil('Personen finnes ikke', status=404)

    if request.method == 'DELETE':
        try:
            person.delete()
        except ProtectedError:
            return _feil(
                f'{person.navn} står på en vaktliste og kan ikke slettes. '
                f'Sett personen inaktiv i stedet — da skjules hun i '
                f'nedtrekkslistene, men blir stående der hun gikk vakt.',
                status=409)
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil('Personen må ha et navn.')
        person.navn = navn
    if 'korps_id' in data:
        korps = Korps.objects.filter(pk=_int(data['korps_id'])).first()
        if korps is None:
            return _feil('Velg hvilket korps personen hører til.')
        person.korps = korps
    if 'telefon' in data:
        person.telefon = (data.get('telefon') or '').strip()
    if 'notat' in data:
        person.notat = (data.get('notat') or '').strip()
    if 'er_aktiv' in data:
        person.er_aktiv = bool(data['er_aktiv'])
    if 'user_id' in data:
        person.user_id = _int(data['user_id'])

    try:
        with transaction.atomic():
            person.save()
            if 'kompetanse_ider' in data:
                person.kompetanser.set(_ider(data.get('kompetanse_ider')))
    except IntegrityError:
        return _feil(f'«{person.navn}» finnes allerede i {person.korps.navn}.')

    person = (Mannskap.objects.select_related('korps', 'user')
              .prefetch_related('kompetanser').get(pk=person.pk))
    return JsonResponse({'status': 'ok', 'data': _mannskap_til_dict(person)})
