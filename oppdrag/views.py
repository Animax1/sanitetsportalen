"""Sentralbordet, enhetsskjermen og oppdrags-API-et.

Fase 3 og 4 av `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Stemplingsendepunktet er
det første som faktisk bruker `skriv_handling` — se §3.2 i rollemodellnotatet.

**Hvert view er dekorert.** `patients/tests_modul_dekorator.py` går gjennom
`urlpatterns` og håndhever det — risikoen ved dekoratør framfor middleware er
en glemt dekoratør, og en manuell gjennomgang holder bare til neste endepunkt.
"""
from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves
from core.idempotency import bygg_nokkel, forkast, fullfor, reserver
from core.ratelimit import rate_limit
from patients.services import get_active_year, hent_aktiv_vakt

from . import choices, services
from .choices import validate_oppdrag_choice_fields
from .models import Enhet, Lokasjon, Oppdrag, Statusmelding
from .views_common import (
    bytte_til_dict, er_enhetskonto, etag_for, json_body, melding_til_dict,
    oppdrag_til_dict,
)


# ── Siden ────────────────────────────────────────────────────────────────────

@modul_kreves('oppdrag', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Én URL, to grensesnitt.

    **Skjermen velges av om kontoen er knyttet til en `Enhet`, ikke av
    nivået.** Se `views_common.er_enhetskonto` for hvorfor. Sentralbordet
    ville vist enheten alle oppdrag i vakta — nettopp det den ikke skal se.
    """
    if er_enhetskonto(request.user):
        # Kjeden sendes med som data. Skjermen bruker den **kun** til å regne
        # ut hva neste knapp skal hete mens en stempling ligger usendt i køen
        # — uten den ville knappen dødd ved første trykk uten dekning, og hele
        # offline-køen vært halvveis. Når nettet er der, er det fortsatt
        # serverens `neste_overgang` per rad som gjelder; §4.2-invarianten om
        # at *serveren* ikke utleder handlingen av tilstanden er urørt.
        neste = {
            status: services.neste_i_kjeden(status)
            for status in choices.STATUS_NAVN
        }
        return render(request, 'oppdrag/enhet.html', {
            'enhet': request.user.enhet,
            'neste_kjede': json.dumps(neste),
            'status_navn': json.dumps(choices.STATUS_NAVN),
        })

    return render(request, 'oppdrag/sentral.html', {
        'kan_skrive': har_tilgang(request.user, 'oppdrag', 'skriv_full'),
        'problemstillinger': choices.PROBLEMSTILLING,
        'hastegrader': choices.HASTEGRAD,
    })


# ── Enheter ──────────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET'])
def enheter_view(request):
    """Enhetslista med **utledet** status.

    Enheten har ingen statuskolonne. `Ledig (2 venter)` regnes ut fra
    oppdragene hver gang — se `services.enhet_status` for hvorfor det ikke
    lagres.
    """
    year = get_active_year()

    # `?alle=1` tar med pensjonerte enheter. Ressursoversikten på tavla skal
    # ikke se dem — de er borte for godt — men enhetspanelet er stedet man
    # gjenoppretter dem fra, og da må de være synlige et sted.
    qs = Enhet.objects.select_related('user').order_by('navn')
    if request.GET.get('alle') != '1':
        qs = qs.filter(er_aktiv=True)
    enheter = list(qs)

    data = [
        {
            'id': e.pk,
            'navn': e.navn,
            'pa_vakt': e.pa_vakt,
            'er_aktiv': e.er_aktiv,
            'username': getattr(e.user, 'username', '') or '',
            'status': info['status'],
            'status_navn': info['status_navn'],
            'antall_ventende': info['antall_ventende'],
            'aktivt_oppdrag_id': (
                info['aktivt_oppdrag'].pk if info['aktivt_oppdrag'] else None),
        }
        for e, info in ((e, services.enhet_status(e, year)) for e in enheter)
    ]

    # Enheter som ikke er på vakt sendes med, de filtreres ikke bort.
    # Sentralbordet viser dem i en egen gruppe: en bil som forsvinner fra
    # tavla er en bil ingen husker å sette inn igjen.
    etag = etag_for([
        (r['id'], r['status'], r['antall_ventende'], r['aktivt_oppdrag_id'],
         r['pa_vakt'], r['er_aktiv'])
        for r in data
    ])
    if request.META.get('HTTP_IF_NONE_MATCH') == etag:
        svar = HttpResponseNotModified()
        svar['ETag'] = etag
        return svar

    svar = JsonResponse({'status': 'ok', 'data': data})
    svar['ETag'] = etag
    return svar


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:vakt', rate='60/m', method='POST')
def enhet_vakt_view(request, pk):
    """Ta en enhet på eller av vakt. Ressursoversikt, ikke oppsett.

    Skilt fra `enhet_detalj_view`, som er admin-flaten for navn, aktiv og
    kontokobling. Dette er drift: 113 tar biler på og av gjennom vakta, og
    skal ikke måtte være global admin for det.

    **En enhet med et påbegynt oppdrag kan ikke tas av vakt.** Den er ute
    akkurat nå; å fjerne den fra tavla ville skjult et pågående oppdrag for
    den som har ansvaret for det. Avslutt oppdraget først.
    """
    try:
        enhet = Enhet.objects.get(pk=pk, er_aktiv=True)
    except Enhet.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Enhet ikke funnet'}, status=404)

    pa_vakt = bool(json_body(request).get('pa_vakt'))

    if not pa_vakt:
        aktivt = services.aktivt_oppdrag(enhet, get_active_year())
        if aktivt is not None:
            return JsonResponse({
                'status': 'error',
                'message': (
                    f'«{enhet.navn}» har et pågående oppdrag '
                    f'({aktivt.get_status_display()}). Avslutt det først.'),
            }, status=400)

    enhet.pa_vakt = pa_vakt
    enhet.save(update_fields=['pa_vakt', 'updated_at'])
    return JsonResponse({'status': 'ok', 'data': {
        'id': enhet.pk, 'navn': enhet.navn, 'pa_vakt': enhet.pa_vakt}})


# ── Lokasjoner ───────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
def lokasjoner_view(request):
    """Liste (alle med `les`), eller opprett (kun global admin).

    Lokasjonene er arrangementsdata og hører til modulen, på samme måte som
    navneregistrene hører til pasientmodulen. Admin-gaten ligger inne i viewet
    fordi lesing og skriving har ulike krav — modulgaten dekker begge.
    """
    if request.method == 'GET':
        rader = list(Lokasjon.objects.all())
        data = [
            {'id': r.pk, 'navn': r.navn, 'er_aktiv': r.er_aktiv,
             'rekkefolge': r.rekkefolge}
            for r in rader
        ]
        etag = etag_for([(r['id'], r['navn'], r['er_aktiv'], r['rekkefolge'])
                         for r in data])
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            svar = HttpResponseNotModified()
            svar['ETag'] = etag
            return svar
        svar = JsonResponse({'status': 'ok', 'data': data})
        svar['ETag'] = etag
        return svar

    if not er_global_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    navn = (json_body(request).get('navn') or '').strip()
    if not navn:
        return JsonResponse(
            {'status': 'error', 'message': 'Navn kan ikke være tomt.'}, status=400)
    if Lokasjon.objects.filter(navn=navn).exists():
        return JsonResponse(
            {'status': 'error', 'message': f'«{navn}» finnes allerede.'}, status=400)

    lok = Lokasjon.objects.create(navn=navn)
    return JsonResponse({'status': 'ok', 'data': {
        'id': lok.pk, 'navn': lok.navn, 'er_aktiv': lok.er_aktiv,
        'rekkefolge': lok.rekkefolge}})


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def lokasjon_detalj_view(request, pk):
    """Endre navn/aktiv (PUT) eller deaktiver (DELETE). Kun global admin.

    **DELETE deaktiverer, den sletter ikke.** FK-en fra `Oppdrag` er `PROTECT`,
    så en lokasjon i bruk kan ikke forsvinne uten å ta historikken med seg.
    Å la knappen hete «slett» og gjøre noe annet ville vært verre enn å la
    være — den heter «deaktiver» i grensesnittet.
    """
    if not er_global_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    try:
        lok = Lokasjon.objects.get(pk=pk)
    except Lokasjon.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Lokasjon ikke funnet'}, status=404)

    if request.method == 'DELETE':
        lok.er_aktiv = False
        lok.save(update_fields=['er_aktiv', 'updated_at'])
        return JsonResponse({'status': 'ok'})

    data = json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return JsonResponse(
                {'status': 'error', 'message': 'Navn kan ikke være tomt.'}, status=400)
        if Lokasjon.objects.filter(navn=navn).exclude(pk=lok.pk).exists():
            return JsonResponse(
                {'status': 'error', 'message': f'«{navn}» finnes allerede.'}, status=400)
        lok.navn = navn
    if 'er_aktiv' in data:
        lok.er_aktiv = bool(data['er_aktiv'])
    if 'rekkefolge' in data:
        try:
            lok.rekkefolge = int(data['rekkefolge'])
        except (TypeError, ValueError):
            return JsonResponse(
                {'status': 'error', 'message': 'Rekkefølge må være et tall.'}, status=400)
    lok.save()
    return JsonResponse({'status': 'ok', 'data': {
        'id': lok.pk, 'navn': lok.navn, 'er_aktiv': lok.er_aktiv,
        'rekkefolge': lok.rekkefolge}})


# ── Oppdrag ──────────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='oppdrag:create', rate='60/m', method='POST')
def oppdrag_liste_view(request):
    """Liste oppdrag i aktiv vakt (GET), eller opprett (POST).

    **Enhetskontoer får kun egne rader.** Modulgaten sier at kontoen kan lese
    modulen; hvilke *rader* den kan lese er en objektsjekk dekoratoren ikke
    gjør, og den ligger her.
    """
    year = get_active_year()

    if request.method == 'GET':
        if er_enhetskonto(request.user):
            # Statusmeldingene følger med: skjermen viser tidslinjen på det
            # aktive oppdraget («Fremme 21:20») og automatisk-markøren på de
            # avsluttede, uten et kall per rad. Få rader — egne, i vakta,
            # innenfor 30-minuttersvinduet — så N+1 her er N liten.
            data = []
            for o in services.synlige_for_enhet(request.user.enhet, year):
                rad = oppdrag_til_dict(o, for_enhet=True)
                rad['statusmeldinger'] = [
                    melding_til_dict(m)
                    for m in Statusmelding.objects.gjeldende(o)
                ]
                data.append(rad)
            # Meldings-ID-ene må inn i ETag-en: en korreksjon endrer tidslinjen
            # uten å røre oppdragets status, og skal ikke drukne i en 304.
            etag_rader = [
                (r['id'], r['status'], r['enhet_id'],
                 tuple(m['id'] for m in r['statusmeldinger']))
                for r in data
            ]
        else:
            # Ferdigstilte er ute av den aktive lista. De er ikke borte —
            # de ligger i `historikk_liste_view`, søkbare på nummer.
            qs = (Oppdrag.objects.filter(year=year, historikk_fra__isnull=True)
                  .select_related('enhet', 'lokasjon').order_by('-created_at'))
            data = [oppdrag_til_dict(o) for o in qs]
            etag_rader = [(r['id'], r['status'], r['enhet_id']) for r in data]

        etag = etag_for(etag_rader)
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            svar = HttpResponseNotModified()
            svar['ETag'] = etag
            return svar
        svar = JsonResponse({'status': 'ok', 'data': data})
        svar['ETag'] = etag
        return svar

    # POST — kun sentralbordet oppretter oppdrag.
    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    data = json_body(request)
    try:
        validate_oppdrag_choice_fields(data)
    except ValidationError as feil:
        return JsonResponse(
            {'status': 'error', 'message': '; '.join(feil.messages)}, status=400)

    try:
        enhet = Enhet.objects.get(
            pk=data.get('enhet_id'), er_aktiv=True, pa_vakt=True)
    except (Enhet.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error',
             'message': 'Ukjent enhet, eller enheten er ikke på vakt.'}, status=400)
    try:
        lokasjon = Lokasjon.objects.get(pk=data.get('lokasjon_id'), er_aktiv=True)
    except (Lokasjon.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Ukjent eller inaktiv lokasjon.'}, status=400)

    # Nummeret tildeles inne i transaksjonen: feiler opprettelsen, rulles
    # også telleren tilbake, og nummeret brennes ikke.
    with transaction.atomic():
        oppdrag = Oppdrag.objects.create(
            year=year,
            # Deploy 1 av vakt-scopingen: FK-en skrives, `year` leses.
            vakt=hent_aktiv_vakt(),
            oppdragsnummer=services.neste_oppdragsnummer(year),
            enhet=enhet,
            problemstilling=data['problemstilling'],
            hastegrad=data['hastegrad'],
            lokasjon=lokasjon,
            fritekst=(data.get('fritekst') or '').strip(),
            opprettet_av=request.user,
        )
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'PUT'])
@rate_limit(group='oppdrag:detalj-skriv', rate='120/m', method='PUT')
def oppdrag_detalj_view(request, pk):
    """Hent ett oppdrag med tidslinje (GET), eller rediger felt (PUT).

    Tidslinjen er unionen av statusmeldinger og enhetsbytter. De to er skilt i
    databasen fordi et bytte ikke er en status og statistikken måler statusene;
    å slå dem sammen her er en visningsjobb.

    Statusmeldingene er de **gjeldende** — en korreksjon overstyrer raden den
    peker på. Den fulle historikken sendes med som `historikk`, slik at
    tidslinjen kan vise rettingen uten at klienten må regne den ut.
    """
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, year=get_active_year()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    if er_enhetskonto(request.user) and oppdrag.enhet_id != request.user.enhet.pk:
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    if request.method == 'GET':
        gjeldende = Statusmelding.objects.gjeldende(oppdrag)
        alle = Statusmelding.objects.filter(oppdrag=oppdrag).order_by('created_at')
        return JsonResponse({'status': 'ok', 'data': {
            **oppdrag_til_dict(oppdrag, for_enhet=er_enhetskonto(request.user)),
            'statusmeldinger': [melding_til_dict(m) for m in gjeldende],
            'historikk': [melding_til_dict(m) for m in alle],
            'enhetsbytter': [bytte_til_dict(b) for b in oppdrag.enhetsbytter.all()],
        }})

    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    data = json_body(request)
    try:
        validate_oppdrag_choice_fields(data)
    except ValidationError as feil:
        return JsonResponse(
            {'status': 'error', 'message': '; '.join(feil.messages)}, status=400)

    if 'problemstilling' in data:
        oppdrag.problemstilling = data['problemstilling']
    if 'hastegrad' in data:
        oppdrag.hastegrad = data['hastegrad']
    if 'fritekst' in data:
        oppdrag.fritekst = (data.get('fritekst') or '').strip()
    if 'lokasjon_id' in data:
        try:
            oppdrag.lokasjon = Lokasjon.objects.get(pk=data['lokasjon_id'])
        except (Lokasjon.DoesNotExist, ValueError, TypeError):
            return JsonResponse(
                {'status': 'error', 'message': 'Ukjent lokasjon.'}, status=400)
    oppdrag.save()
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:flytt', rate='60/m', method='POST')
def flytt_view(request, pk):
    """Flytt oppdraget til en annen enhet, og skriv det i oppdragets logg.

    Statusen står. Meldingene den første enheten rakk å sende blir stående med
    `meldt_av` intakt: de skjedde.
    """
    try:
        oppdrag = Oppdrag.objects.get(pk=pk, year=get_active_year())
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    try:
        ny_enhet = Enhet.objects.get(
            pk=json_body(request).get('enhet_id'), er_aktiv=True, pa_vakt=True)
    except (Enhet.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error',
             'message': 'Ukjent enhet, eller enheten er ikke på vakt.'}, status=400)

    bytte = services.flytt_til_enhet(oppdrag, ny_enhet, bruker=request.user)
    if bytte is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget står allerede på denne enheten.'},
            status=400)
    return JsonResponse({'status': 'ok', 'data': bytte_til_dict(bytte)})


# ── Stempling ────────────────────────────────────────────────────────────────

#: Det lukkede kroppsskjemaet fra §5.1. To nøkler, og settet er hele
#: kontrakten: en test kan uttømme det ved å sende en nøkkel til og kreve 400.
#: En feltwhitelist inne i en generell PUT kan ikke testes slik — settet av
#: felter der vokser med modellen.
STEMPLING_TILLATTE_NOKLER = frozenset({'klienttid', 'idempotency_key'})


def _stempling_kropp(request):
    """Parse stemplingskroppen mot det lukkede skjemaet.

    Returnerer ``(data, feilmelding)``. Tom kropp er gyldig — en stempling
    trenger strengt tatt ingenting; klienttid finnes for offline-køen. Alt som
    ikke står i skjemaet gir feil, også gyldig JSON: her skal ingen domenefelt
    noensinne kunne komme inn.
    """
    if not request.body:
        return {}, None
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None, 'Ugyldig JSON i kroppen.'
    if not isinstance(data, dict):
        return None, 'Kroppen må være et JSON-objekt.'
    ukjente = set(data) - STEMPLING_TILLATTE_NOKLER
    if ukjente:
        return None, (
            'Ukjente felt i stemplingen: ' + ', '.join(sorted(ukjente))
            + '. Tillatt: ' + ', '.join(sorted(STEMPLING_TILLATTE_NOKLER)) + '.')
    return data, None


@modul_kreves('oppdrag', 'skriv_handling', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:stempling', rate='60/m', method='POST')
def stempling_view(request, pk, overgang):
    """Ett navngitt endepunkt per overgang — bilens eneste skriveflate.

    Første faktiske bruk av `skriv_handling` (§3.2 i rollemodellnotatet): en
    innskrenket aktør får et smalt endepunkt, ikke en feltwhitelist inne i en
    generell PUT. Serveren utleder ingenting av gjeldende tilstand — knappen
    vet hvilken overgang den utfører og poster til den. `POST .../neste/`
    ville gitt kappløpet §4.2 beskriver når to trykk kommer tett.

    To porter: modulgaten over, og objektsjekken her — enheten må eie
    oppdraget. Sentralbordet stempler ikke; det korrigerer (fase 4b), og en
    konto uten enhet får 403 uansett nivå.

    **`idempotency_key` kobles til `core.idempotency` (fase 5).** Uten den ville
    en offline-kø som spilles av på nytt fått 409 på andre forsøk — teknisk
    ufarlig, siden statusmaskinen avviser overgangen og ingen rad oppstår, men
    ubrukelig for køen: den kan ikke skille «allerede levert» fra «avvist fordi
    skjermen har sakket akterut», og ville enten hengt fast eller kastet en
    stempling som faktisk kom fram. Med nøkkelen svarer en avspilling `ok` med
    den opprinnelige meldingen, og køen kan trygt stryke raden.
    """
    if overgang not in services.STEMPLBARE:
        return JsonResponse(
            {'status': 'error', 'message': f'Ukjent overgang «{overgang}».'},
            status=404)

    if not er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Bare enhetskontoer stempler.'},
            status=403)

    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, year=get_active_year()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    if oppdrag.enhet_id != request.user.enhet.pk:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget tilhører en annen enhet.'},
            status=403)

    data, feil = _stempling_kropp(request)
    if feil:
        return JsonResponse({'status': 'error', 'message': feil}, status=400)

    klienttid = None
    if data.get('klienttid') is not None:
        klienttid = parse_datetime(str(data['klienttid']))
        if klienttid is None:
            # Uleselig klienttid er en klientfeil, ikke et gammelt stempel —
            # den skal feile høyt, ikke stille bli servertid.
            return JsonResponse(
                {'status': 'error', 'message': 'Ugyldig klienttid.'}, status=400)
        if timezone.is_naive(klienttid):
            klienttid = timezone.make_aware(klienttid)

    tidspunkt, forsinket = services.vurder_klienttid(klienttid, oppdrag)

    # Reserveres her — etter all validering, rett før noe skrives. Reserverte
    # vi tidligere, ville en avvist stempling brent nøkkelen, og køen som
    # rettet seg og prøvde igjen fått «allerede levert» på et forsøk som
    # aldri kom fram.
    idem = bygg_nokkel('oppdrag_stempling', request.user.pk,
                       data.get('idempotency_key'))
    if idem:
        idem_status, verdi = reserver(idem)
        if idem_status == 'ferdig':
            # Køen spiller av et trykk som allerede kom fram. Svar med
            # meldingen den gang laget, ikke med 409: køen skal kunne stryke
            # raden, og den kan ikke skille en avvist overgang fra en levert.
            try:
                tidligere = Statusmelding.objects.get(pk=verdi)
                return JsonResponse({'status': 'ok', 'data': {
                    'oppdrag': oppdrag_til_dict(oppdrag, for_enhet=True),
                    'melding': melding_til_dict(tidligere),
                    'avspilling': True,
                }})
            except Statusmelding.DoesNotExist:
                # Meldingen er borte (korrigert bort, eller basen nullstilt).
                # Nøkkelen beskytter ikke lenger noe — la stemplingen gå.
                forkast(idem)
        elif idem_status == 'pagar':
            # Samme trykk sendt to ganger mens det første fortsatt kjører.
            return JsonResponse({
                'status': 'error',
                'message': 'Stemplingen er allerede sendt.',
                'duplikat': True,
            }, status=409)

    try:
        if overgang == choices.RYKKER_UT:
            # Lukker et eventuelt pågående oppdrag automatisk (§4.3).
            melding = services.start_oppdrag(
                oppdrag, bruker=request.user,
                tidspunkt=tidspunkt, forsinket=forsinket)
        else:
            melding = services.sett_status(
                oppdrag, overgang, bruker=request.user,
                tidspunkt=tidspunkt, forsinket=forsinket)
    except services.UlovligOvergang:
        # Typisk et dobbelttrykk der det første vant, eller en skjerm som har
        # sakket akterut. 409, ikke 400: forespørselen var velformet, det er
        # tilstanden som har flyttet seg. Klienten svarer med å hente på nytt.
        if idem:
            # Ingenting ble skrevet, så nøkkelen skal ikke stå som brukt.
            forkast(idem)
        return JsonResponse({
            'status': 'error',
            'message': (
                f'Oppdraget står i {oppdrag.get_status_display()} — '
                'skjermen er oppdatert.'),
        }, status=409)

    if idem:
        fullfor(idem, melding.pk)

    return JsonResponse({'status': 'ok', 'data': {
        'oppdrag': oppdrag_til_dict(oppdrag, for_enhet=True),
        'melding': melding_til_dict(melding),
    }})


# ── Historikk (rydding av tavla) ─────────────────────────────────────────────
#
# **Ikke vaktarkivet.** `core.arkiv` fryser, signerer og kollapser hele vakter,
# og denne appen får sin egen `BaseArkivHandler` i fase 7. Her flyttes ett
# ferdigstilt oppdrag ut av den aktive lista og inn i en søkbar historikk.
# Raden er urørt og handlingen reversibel — derfor `skriv_full` og ikke admin:
# §3.3 reserverer admin for det irreversible.

@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST', 'DELETE'])
@rate_limit(group='oppdrag:historikk', rate='60/m', method='POST')
def historikk_view(request, pk):
    """Flytt et ferdigstilt oppdrag til historikken (POST), eller hent det
    tilbake til tavla (DELETE).

    Enhetskontoer stenges ute selv om de skulle ha `skriv_full`: rydding av
    tavla er sentralbordets jobb, og bilen ser uansett bare sine egne rader.
    Samme objektsjekk-mønster som stemplingen, motsatt vei.
    """
    if er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Enheter rydder ikke tavla.'},
            status=403)

    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, year=get_active_year()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    if request.method == 'DELETE':
        services.hent_tilbake(oppdrag)
        return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})

    try:
        services.flytt_til_historikk(oppdrag, bruker=request.user)
    except services.KanIkkeFlyttes as feil:
        # Å rydde bort et pågående oppdrag ville skjult noe som fortsatt
        # skjer. 400: forespørselen er velformet, men tilstanden tillater den
        # ikke — og meldingen sier hvilken status som står i veien.
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)

    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET'])
def historikk_liste_view(request):
    """Historikken for aktiv vakt — de ferdigstilte oppdragene, nyest først.

    `?sok=` filtrerer. Nummer er hovedveien inn — det er det man har notert
    eller hørt på samband — så et rent tall treffer nummeret eksakt i stedet
    for som delstreng: søker man «1», skal man ikke få 1, 10, 11 og 21.
    Tekstsøk mot problemstilling, lokasjon og enhet er tilleggsveien for den
    som husker hva oppdraget gjaldt, men ikke nummeret.

    Enhetskontoer får 403: historikken er sentralbordets oversikt over hele
    vakta, og bilen skal se sine egne oppdrag, ikke andres.
    """
    if er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    qs = (Oppdrag.objects
          .filter(year=get_active_year(), historikk_fra__isnull=False)
          .select_related('enhet', 'lokasjon')
          .order_by('-historikk_fra'))

    sok = (request.GET.get('sok') or '').strip()
    if sok:
        if sok.lstrip('#').isdigit():
            qs = qs.filter(oppdragsnummer=int(sok.lstrip('#')))
        else:
            qs = qs.filter(
                Q(problemstilling__icontains=sok)
                | Q(lokasjon__navn__icontains=sok)
                | Q(enhet__navn__icontains=sok))

    return JsonResponse({'status': 'ok', 'data': [
        oppdrag_til_dict(o) for o in qs]})


# ── Korreksjoner ─────────────────────────────────────────────────────────────

@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:korriger', rate='60/m', method='POST')
def korriger_view(request, pk):
    """Rett tidspunktet på en statusmelding — som en **ny rad**, ikke en endring.

    **Dette er ikke et handling-endepunkt.** Det tar et tidspunkt, altså en
    feltverdi, og ligger derfor på `skriv_full` med vanlig kroppsvalidering.
    Å presse det inn under `skriv_handling` ville uthult det lukkede skjemaet
    i §5.1 med én gang — da hadde stemplingskroppen fått et domenefelt.

    Enhetskontoer stenges ute uansett nivå: en enhet stempler, den retter
    ikke. Rettingen er sentralbordets korrigering av det bilen meldte, og en
    bil som kunne rette sine egne tidspunkter ville gjort stemplingen til en
    påstand i stedet for en måling.
    """
    if er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Enheter retter ikke tidspunkt.'},
            status=403)

    try:
        melding = (Statusmelding.objects
                   .select_related('oppdrag', 'oppdrag__enhet', 'oppdrag__lokasjon')
                   .get(pk=pk, oppdrag__year=get_active_year()))
    except Statusmelding.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Statusmelding ikke funnet'}, status=404)

    raa = json_body(request).get('tidspunkt')
    if not raa:
        return JsonResponse(
            {'status': 'error', 'message': 'Mangler tidspunkt.'}, status=400)

    nytt = parse_datetime(str(raa))
    if nytt is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Ugyldig tidspunkt.'}, status=400)
    if timezone.is_naive(nytt):
        nytt = timezone.make_aware(nytt)

    try:
        services.valider_korreksjon(melding, nytt)
    except services.KorreksjonUgyldig as feil:
        # 400 og ikke 409: forespørselen er velformet, men verdien er ikke
        # lovlig — og meldingen sier hvilken regel som stanset den, slik at
        # operatøren vet om hun skal rette en annen rad først.
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)

    ny_melding = services.korriger_tidspunkt(melding, nytt, bruker=request.user)
    return JsonResponse({'status': 'ok', 'data': melding_til_dict(ny_melding)})
