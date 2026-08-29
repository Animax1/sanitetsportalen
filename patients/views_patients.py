"""Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD og vaktavslutning.

Skilt ut fra ``views.py`` i N13.3.
"""
import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import (
    admin_required, er_global_admin, har_tilgang, modul_kreves, nivaa_for,
)
from core.idempotency import bygg_nokkel, forkast, fullfor, reserver
from core.ratelimit import rate_limit

from .choices import validate_patient_choice_fields
from .models import Patient, AppSetting, Forstehjelper, Helsepersonell
from .services import (
    kan_slette_selv, slettbare_pasient_ider,
    next_patient_nr,
    apply_list_filter, stamp_pabegynt_if_needed,
    hent_aktiv_vakt, vakt_for_year,
    stamp_obs_times_if_needed, stamp_utskrevet_if_needed,
    validate_patient_time_fields, validate_plassering_unique,
    SHARED_PLASSERINGER, now_local_str,
    recycle_patient_nr_if_last,
)
from .views_common import (
    _json_body, _ensure_pabegynt_not_before_inntid,
    _patient_to_dict,
)


# ── Hoved-side ────────────────────────────────────────────────────────────────

@modul_kreves('patients', 'les')
def index_view(request):
    """Render hoved-siden.

    Arrangementsnavnet sendes med i konteksten slik at headeren er riktig
    allerede i første render. Templaten hadde tidligere `LS26` hardkodet som
    innhold, og `loadSettings()` byttet det ut — men først etter tre awaitede
    fetch-er, så et gammelt arrangementsnavn sto synlig i mellomtiden.
    """
    return render(request, 'patients/index.html', {
        # Arrangementsnavnet ER vaktnavnet siden deploy 2 — én kilde.
        # Nøkkelen heter fortsatt event_name utad; malen og loadSettings()
        # leser den, og de skal ikke bry seg om hvor verdien bor.
        'event_name': hent_aktiv_vakt().navn,
        # §7.4: grensesnittet må gate på det samme som endepunktene gjør.
        # Gjorde det ikke det, viste vi «Ny pasient» til en bruker med bare
        # `les` — hen fikk opp skjemaet, fylte det ut, og møtte 403 på lagre.
        # En knapp som fører til en vegg er verre enn ingen knapp.
        'modul_nivaa': nivaa_for(request.user, 'patients') or '',
        'kan_skrive': har_tilgang(request.user, 'patients', 'skriv_full'),
        # `er_global_admin` kommer fra context processoren, ikke herfra: den
        # trengs i base_portal.html og profilsiden også.
    })


# ── Innstillinger ─────────────────────────────────────────────────────────────

#: Nøkler `GET /api/settings/` returnerer.
#:
#: `AppSetting` er en generisk nøkkel/verdi-tabell. Uten denne lista havnet
#: enhver ny driftsverdi automatisk i responsen til *alle* innloggede, også
#: rene lesere — inkludert verdier som ikke er ment for klienten. PUT har
#: alltid hatt en whitelist; at GET ikke hadde det var en asymmetri som
#: ville blitt et problem lenge etter at den ble innført (N12).
#:
#: Skal en ny nøkkel ut til frontend, legg den til her bevisst.
SETTINGS_READ_WHITELIST = frozenset({
    # `event_name` og `active_year` sto her fram til deploy 2. Begge bor på
    # vakta nå, og svaret bygges i viewet — lista står igjen for neste
    # driftsverdi som faktisk skal ut til klienten.
})


@modul_kreves('patients', 'les', svar='json')
@require_http_methods(['GET'])
def settings_view(request):
    """Les appinnstillingene pasientsiden trenger.

    **Kun GET.** Skrivingen flyttet til `/portal-admin/innstillinger/` (§4.1):
    `event_name` er en portalinnstilling, ikke en pasientinnstilling, og et
    endepunkt under `/pasienter/` som krever global admin sier at
    modulgrensen ikke betyr noe.

    Lesingen blir igjen fordi headeren og årsfiltreringen trenger verdiene, og
    fordi de er ufarlige for alle som allerede kan lese modulen.
    """
    vakt = hent_aktiv_vakt()
    svar = {
        s.key: s.value
        for s in AppSetting.objects.filter(key__in=SETTINGS_READ_WHITELIST)
    }
    # Nøklene beholder de gamle navnene utad: loadSettings() leser
    # `event_name`, og klienten skal ikke vite at kilden byttet.
    svar['event_name'] = vakt.navn
    svar['active_year'] = str(vakt.year)
    return JsonResponse(svar)

# ── Pasienter ─────────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('patients', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
# S3: kun POST telles — GET er pollet hvert 30. sekund av hver klient og
# svarer 304 uten kropp når ingenting er endret. 60/min er langt over det
# et menneske rekker, og godt under det en løpsk klient produserer.
@rate_limit(group='patients:create', rate='60/m', method='POST')
def patients_list_view(request):
    """Liste pasienter for aktivt år, eller opprett ny.

    Query-parametre:
      ?filter=<name>        – Filtrer på status (rod/gul/gronn/rodgul/aktive/utskrevet/alle)
      ?include_archived=1   – Inkluder inaktive pasienter
    """
    if request.method == 'GET':
        vakt = hent_aktiv_vakt()

        filter_name = request.GET.get('filter', 'alle')
        include_archived = request.GET.get('include_archived') == '1'
        # Fase 5: "mine"-filter — default AV, slås på via ?mine=1.
        # Filtrerer på Behandler.user ELLER Helsepersonell.user lik innlogget bruker.
        # Tilgjengelig for alle med lesetilgang til modulen.
        mine_only = request.GET.get('mine') == '1'

        # select_related: `_patient_to_dict()` leser navnet på både
        # forstehjelper og helsepersonell. Uten dette ble det én ekstra
        # spørring per pasient per felt — målt til 515 spørringer ved 1000
        # pasienter, mot 8 med. Endepunktet pollet hvert 30. sekund av hver
        # klient, så det var den dyreste stien i appen.
        # select_related('vakt'): serialiseringen leser vakt.year per rad.
        qs = (Patient.objects
              .select_related('forstehjelper', 'helsepersonell_ref', 'vakt')
              .order_by('pasientnummer'))
        if not include_archived:
            qs = qs.filter(is_active=True)

        if mine_only and request.user.is_authenticated:
            qs = qs.filter(
                Q(forstehjelper__user=request.user)
                | Q(helsepersonell_ref__user=request.user)
            )

        qs = apply_list_filter(qs, filter_name=filter_name, vakt=vakt)

        # ETag/304 — samme mønster som navneregistrene.
        #
        # Kroppen serialiseres én gang og hashes, i stedet for å hashe
        # feltverdier separat: da kan ETag-en per definisjon ikke komme i
        # utakt med det som faktisk sendes. Det dekker samtidig at svaret
        # varierer med ?filter, ?mine og ?include_archived — ulike parametre
        # gir ulik kropp og dermed ulik ETag, uten at de må hashes eksplisitt.
        #
        # Merk hva dette sparer: båndbredden (454 kB per kall ved 1000
        # pasienter), ikke databasearbeidet. Spørringen og serialiseringen
        # kjører uansett for å regne ut hashen.
        slettbare = slettbare_pasient_ider(request.user)
        kropp = json.dumps([_patient_to_dict(p, slettbare) for p in qs],
                           default=str)
        etag_value = ('"v1:'
                      + hashlib.sha256(kropp.encode('utf-8')).hexdigest()[:16]
                      + '"')

        if request.META.get('HTTP_IF_NONE_MATCH') == etag_value:
            return HttpResponseNotModified()

        response = HttpResponse(kropp, content_type='application/json')
        response['ETag'] = etag_value
        response['Cache-Control'] = 'private, must-revalidate'
        return response

    # POST – opprett ny pasient i aktivt år (krever skrivetilgang)
    if not har_tilgang(request.user, 'patients', 'skriv_full'):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)

    # Valider tidsfelter – kun format dd.mm.åååå tt:mm godtas
    try:
        validate_patient_time_fields(data)
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

    # Valider kliniske felt mot fast verdimengde. Uten dette kan en klient som
    # går utenom grensesnittet lagre vilkårlig fritekst i feltene.
    try:
        validate_patient_choice_fields(data)
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

    vakt = hent_aktiv_vakt()

    # FORBEDRINGER #19: Valider plassering FØR nummer-tildeling
    # – hindrer hopp i pasientnummer hvis valideringen feiler.
    try:
        validate_plassering_unique(data.get('plassering', ''), vakt)
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

    # Én felles tidsstempel for hele requesten:
    # – inntid og pabegynt skal aldri kunne gå i utakt på grunn av mikro-drift
    # – alltid Europe/Oslo, uavhengig av container-TZ (UTC på Railway)
    now_str = now_local_str()
    data['_now_str'] = now_str  # leses av stamp_*_if_needed

    # Konverter forstehjelper-ID til Forstehjelper-objekt
    forstehjelper_obj = None
    forstehjelper_id = data.get('forstehjelper')
    if forstehjelper_id:
        try:
            forstehjelper_obj = Forstehjelper.objects.get(pk=int(forstehjelper_id))
        except (Forstehjelper.DoesNotExist, ValueError, TypeError):
            pass

    # Konverter helsepersonell_ref-ID til Helsepersonell-objekt
    helsepersonell_obj = None
    helsepersonell_id = data.get('helsepersonell_ref')
    if helsepersonell_id:
        try:
            helsepersonell_obj = Helsepersonell.objects.get(pk=int(helsepersonell_id))
        except (Helsepersonell.DoesNotExist, ValueError, TypeError):
            pass

    # Bruk server-tid hvis frontend sendte blank/manglende inntid.
    # Tidligere: data.get('inntid', now) – returnerte '' hvis nøkkelen fantes med tom verdi.
    inntid_value = (data.get('inntid') or '').strip() or now_str

    # F3: idempotens. Reserveres FØRST her — etter all validering, rett før
    # noe opprettes. Reserverte vi tidligere, ville en avvist innsending brent
    # nøkkelen, og brukeren som rettet feilen fått «allerede sendt inn» på det
    # korrigerte forsøket.
    idem = bygg_nokkel('patient_create', request.user.pk,
                       data.get('idempotency_key'))
    if idem:
        status, verdi = reserver(idem)
        if status == 'ferdig':
            # Retry etter at den første forespørselen var ferdig: svar med
            # pasienten den opprettet, og 200 i stedet for 201 — ingenting ble
            # opprettet nå.
            try:
                return JsonResponse(
                    _patient_to_dict(Patient.objects.get(pk=verdi),
                                     slettbare_pasient_ider(request.user)),
                )
            except Patient.DoesNotExist:
                # Pasienten er slettet i mellomtiden. Nøkkelen beskytter ikke
                # lenger noe, så la forespørselen gå videre og opprette.
                forkast(idem)
        elif status == 'pagar':
            # Dobbeltinnsending mens den første fortsatt kjører. Raden er på
            # vei; klienten skal laste lista på nytt, ikke sende igjen.
            return JsonResponse(
                {'error': 'Registreringen er allerede sendt inn.',
                 'duplikat': True},
                status=409,
            )

    # FORBEDRINGER #19: Atomisk transaksjon – alt eller ingenting.
    # next_patient_nr() kalles inne i blokken slik at en eventuell IntegrityError
    # ved save() ruller tilbake nummer-allokeringen.
    with transaction.atomic():
        nr = next_patient_nr(vakt)
        patient = Patient(
            pasientnummer=nr,
            vakt=vakt,   # alltid i aktiv vakt
            problemstilling=data.get('problemstilling', ''),
            arsak=data.get('arsak', ''),
            transport=data.get('transport', ''),
            inntid=inntid_value,
            grovsortering=data.get('grovsortering', ''),
            pabegynt=data.get('pabegynt', ''),
            plassering=data.get('plassering', ''),
            forstehjelper=forstehjelper_obj,
            helsepersonell_ref=helsepersonell_obj,
            lege=data.get('lege', ''),
            medisiner=data.get('medisiner', ''),
            inn_obspost=data.get('inn_obspost', ''),
            ut_obspost=data.get('ut_obspost', ''),
            utskrevet=data.get('utskrevet', ''),
            utskrevet_til=data.get('utskrevet_til', ''),
            journal=data.get('journal', ''),
        )
        # Rekkefølge: påbegynt → obs-stempling → utskrevet-stempling
        # Alle stamp_*-funksjoner leser data['_now_str'] for konsistent tidsstempel.
        stamp_pabegynt_if_needed(patient, data)
        stamp_obs_times_if_needed(patient, '', data)
        stamp_utskrevet_if_needed(patient, data)

        # Sikkerhetsnett: pabegynt skal aldri kunne være før inntid på nyopprettet pasient.
        # Hvis det skjer (f.eks. brukeren skrev inn inntid manuelt frem i tid),
        # justeres pabegynt opp til inntid.
        _ensure_pabegynt_not_before_inntid(patient)

        try:
            patient.save()
        except Exception:
            # Frigi nøkkelen, ellers står brukeren igjen med en reservasjon
            # for en pasient som aldri ble opprettet, og kan ikke prøve igjen.
            if idem:
                forkast(idem)
            raise

    if idem:
        fullfor(idem, patient.pk)
    return JsonResponse(
        _patient_to_dict(patient, slettbare_pasient_ider(request.user)),
        status=201)


@modul_kreves('patients', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
# S3: redigering skjer oftere enn opprettelse — obs-tider stemples, sonen
# endres, pasienten skrives ut — så bøtta er romsligere enn ved
# opprettelse. Den stopper en løpsk klient, ikke en travel sykestue.
@rate_limit(group='patients:detail-write', rate='120/m',
            method=['PUT', 'DELETE'])
def patient_detail_view(request, pk):
    """Oppdater eller slett en pasient.

    **DELETE er en hard-delete**, ikke en soft-delete som docstringen tidligere
    påsto. Raden fjernes fra databasen og pasientnummeret resirkuleres hvis den
    var den siste. Eneste vei tilbake er en backup tatt før slettingen.

    `Patient.is_active` finnes på modellen og leses av `?include_archived`, men
    ingen produksjonskode setter den til False — feltet kan bare endres via
    Django-admin. Det er derfor ikke slettemekanismen appen faktisk bruker.
    """
    try:
        patient = Patient.objects.get(pk=pk)
    except Patient.DoesNotExist:
        return JsonResponse({'error': 'Pasient ikke funnet'}, status=404)

    if request.method == 'PUT':
        if not har_tilgang(request.user, 'patients', 'skriv_full'):
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        data = _json_body(request)

        # Valider tidsfelter – kun format dd.mm.åååå tt:mm godtas
        try:
            validate_patient_time_fields(data)
        except ValidationError as exc:
            return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

        # Valider kliniske felt mot fast verdimengde (samme regel som ved opprettelse)
        try:
            validate_patient_choice_fields(data)
        except ValidationError as exc:
            return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

        # Valider plassering-unikhet hvis plassering er i payload
        if 'plassering' in data:
            try:
                validate_plassering_unique(
                    data.get('plassering', ''),
                    patient.vakt,
                    exclude_pk=patient.pk,
                )
            except ValidationError as exc:
                return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

        allowed_text_fields = {
            'problemstilling', 'arsak', 'transport', 'inntid', 'grovsortering',
            'pabegynt', 'plassering', 'lege',
            'medisiner', 'inn_obspost', 'ut_obspost', 'utskrevet',
            'utskrevet_til', 'journal',
        }

        # Lagre gammel plassering FØR mutasjon for obs-stempling
        old_plassering = patient.plassering or ''

        for field, value in data.items():
            if field in allowed_text_fields:
                setattr(patient, field, value)

        # Forstehjelper: konverter ID til objekt
        if 'forstehjelper' in data:
            forstehjelper_id = data['forstehjelper']
            if forstehjelper_id:
                try:
                    patient.forstehjelper = Forstehjelper.objects.get(pk=int(forstehjelper_id))
                except (Forstehjelper.DoesNotExist, ValueError, TypeError):
                    pass
            else:
                patient.forstehjelper = None

        # Helsepersonell_ref: konverter ID til objekt
        if 'helsepersonell_ref' in data:
            hp_id = data['helsepersonell_ref']
            if hp_id:
                try:
                    patient.helsepersonell_ref = Helsepersonell.objects.get(pk=int(hp_id))
                except (Helsepersonell.DoesNotExist, ValueError, TypeError):
                    pass
            else:
                patient.helsepersonell_ref = None

        # Én felles tidsstempel for hele requesten (Europe/Oslo, uavh. av container-TZ).
        data['_now_str'] = now_local_str()

        # Rekkefølge: påbegynt → obs-stempling → utskrevet-stempling
        stamp_pabegynt_if_needed(patient, data)
        stamp_obs_times_if_needed(patient, old_plassering, data)
        stamp_utskrevet_if_needed(patient, data)

        # Sikkerhetsnett: pabegynt < inntid skal ikke kunne forekomme.
        _ensure_pabegynt_not_before_inntid(patient)

        patient.save()
        return JsonResponse(
            _patient_to_dict(patient, slettbare_pasient_ider(request.user)))

    # DELETE – hard-delete med recycle av pasientnummer.
    #
    # §4.2: `skriv_full` kan slette **egne** pasienter de siste 30 minuttene.
    # Eldre sletting, og andres, forblir global admin. Vinduet treffer
    # feilregistrering — en duplikat eller et feiltrykk som blokkerer et
    # pasientnummer — uten å gjøre sletting til et hverdagsverktøy.
    #
    # Merk at dette er en **hard-delete som resirkulerer pasientnummeret**.
    # Det er nettopp derfor vinduet er smalt: raden finnes ikke i noen backup
    # tatt etterpå.
    if not (er_global_admin(request.user)
            or kan_slette_selv(request.user, patient)):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    pasientnummer = patient.pasientnummer
    vakt = patient.vakt
    with transaction.atomic():
        patient.delete()
        recycled = recycle_patient_nr_if_last(vakt, pasientnummer)
    return JsonResponse({'ok': True, 'recycled_nr': recycled})


# ── Reset testdata ─────────────────────────────────────────────────────────────

@modul_kreves('patients', 'les', svar='json')
@admin_required
@require_http_methods(['POST'])
def avslutt_vakt_view(request):
    """Avslutt aktiv vakt og start en ny. Kun admin.

    Operasjonen er nullstillingens arvtaker (§3.4 i vakt-notatet): backup,
    slett vaktas pasienter, merk vakta avsluttet — men den gjelder ÉN vakt,
    og navnet sier det. «Nullstill år» ville slettet for mye den dagen et år
    rommer flere vakter.

    Den nye vakta opprettes i samme flyt, slik at portalen aldri står tømt
    uten aktiv vakt. Navnet er påkrevd og fritekst — det var beslutningen —
    og unikt: to vakter med samme navn lar seg ikke skille i statistikken.

    Oppdragene til den avsluttede vakta røres ikke. De er scopet bort fra
    alle visninger i samme øyeblikk som pekeren flytter, og livssyklusen
    deres (arkivering, kollaps) er fase 7 sitt ansvar.

    Krever {"confirm": true} for å unngå feilklikk. Pasientslettingen kan
    ikke angres uten backupen — gjenåpning av vakta (egen knapp) setter den
    aktiv igjen, men henter ikke rader tilbake.
    """
    from core.models import Vakt

    data = _json_body(request)
    if not data.get('confirm'):
        return JsonResponse(
            {'error': 'Bekreftelse mangler. Send {"confirm": true} for å slette.'},
            status=400,
        )
    nytt_navn = (data.get('ny_vakt_navn') or '').strip()
    if not nytt_navn:
        return JsonResponse(
            {'error': 'Den nye vakta må ha et navn — det settes ved vaktstart.'},
            status=400,
        )
    if Vakt.objects.filter(navn=nytt_navn).exists():
        return JsonResponse(
            {'error': f'En vakt med navnet «{nytt_navn}» finnes allerede. '
                      f'Legg på en dato eller velg et annet navn.'},
            status=400,
        )

    vakt = hent_aktiv_vakt()
    # Lag pre-reset backup før sletting
    from .backup_service import create_backup
    create_backup(kind='pre_reset', user=request.user,
                  note=f'Før avslutning av vakta «{vakt.navn}»')

    with transaction.atomic():
        deleted, _ = Patient.objects.filter(vakt=vakt).delete()
        vakt.er_aktiv = False
        vakt.avsluttet = timezone.now()
        vakt.save(update_fields=['er_aktiv', 'avsluttet'])

        from core.validators import current_local_year
        ny = Vakt.objects.create(
            navn=nytt_navn, year=current_local_year(), startet=timezone.now())
        AppSetting.set('aktiv_vakt_id', ny.pk)
        # Ny vakt har ingen tellernøkkel — next_patient_nr starter på 1 av
        # seg selv. Den gamle vaktas nøkkel blir liggende: gjenåpnes vakta,
        # fortsetter serien der den slapp.

    return JsonResponse({
        'ok': True,
        'avsluttet_vakt': vakt.navn,
        'ny_vakt': ny.navn,
        'antall_slettet': deleted,
        'melding': f'{deleted} pasienter slettet. Vakta «{vakt.navn}» er '
                   f'avsluttet, og «{ny.navn}» er aktiv.',
    })


@modul_kreves('patients', 'les', svar='json')
@admin_required
@require_http_methods(['GET'])
def vakter_view(request):
    """Vaktene, nyest først — grunnlaget for «Tidligere vakter»-lista.

    Kun admin: lista finnes for gjenåpning, som er en admin-handling, og
    vaktnavn fra tidligere arrangementer er ikke noe enhver leser trenger.
    `kollapset` sendes med slik at grensesnittet kan la være å tilby en
    gjenåpning serveren uansett ville avvist.
    """
    from core.models import Vakt

    return JsonResponse({'vakter': [
        {
            'id': v.pk,
            'navn': v.navn,
            'year': v.year,
            'er_aktiv': v.er_aktiv,
            'startet': v.startet.isoformat(),
            'avsluttet': v.avsluttet.isoformat() if v.avsluttet else None,
            'kollapset': v.vaktarkiver.filter(
                kollapset_at__isnull=False).exists(),
        }
        for v in Vakt.objects.order_by('-startet')
    ]})


@modul_kreves('patients', 'les', svar='json')
@admin_required
@require_http_methods(['POST'])
def gjenaapne_vakt_view(request):
    """Gjenåpne en avsluttet vakt. Kun admin.

    En feilklikk-avslutning midt i en vakt skal ikke være en katastrofe uten
    vei tilbake — det var beslutningen (§7.2). Gjenåpningen bytter aktiv
    vakt; den henter IKKE slettede pasientrader tilbake. De ligger i
    pre-reset-backupen, og gjenoppretting derfra er en egen, bevisst handling
    i backup-panelet.

    Døra er låst når vaktas arkiv er kollapset: da finnes ikke radnivået
    lenger, og en «aktiv» vakt uten mulighet for rådata ville løyet.
    """
    from core.models import Vakt

    data = _json_body(request)
    try:
        vakt = Vakt.objects.get(pk=int(data.get('vakt_id')))
    except (Vakt.DoesNotExist, TypeError, ValueError):
        return JsonResponse({'error': 'Ukjent vakt.'}, status=400)

    if vakt.vaktarkiver.filter(kollapset_at__isnull=False).exists():
        return JsonResponse(
            {'error': f'Arkivet for «{vakt.navn}» er kollapset — radnivået '
                      f'finnes ikke lenger, og vakta kan ikke gjenåpnes.'},
            status=400,
        )

    forrige = hent_aktiv_vakt()
    with transaction.atomic():
        if forrige.pk != vakt.pk:
            forrige.er_aktiv = False
            forrige.avsluttet = timezone.now()
            forrige.save(update_fields=['er_aktiv', 'avsluttet'])
        vakt.er_aktiv = True
        vakt.avsluttet = None
        vakt.save(update_fields=['er_aktiv', 'avsluttet'])
        AppSetting.set('aktiv_vakt_id', vakt.pk)

    return JsonResponse({
        'ok': True,
        'aktiv_vakt': vakt.navn,
        'melding': f'Vakta «{vakt.navn}» er aktiv igjen.',
    })


