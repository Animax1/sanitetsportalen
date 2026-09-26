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

from core.jsdata import js_json
from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves
from core.idempotency import bygg_nokkel, forkast, fullfor, reserver
from core.ratelimit import rate_limit
from core.sortering import Norsk
from core.vakt import hent_aktiv_vakt

from . import choices, services, verdier
from .choices import validate_oppdrag_choice_fields
from .models import Enhet, Enhetstype, Lokasjon, Oppdrag, Oppdragsendring, Statusmelding
from .views_common import (
    bytte_til_dict, endring_til_dict, er_enhetskonto, etag_for_svar, hendelse_til_dict, json_body, melding_til_dict,
    oppdrag_til_dict, status_tidspunkt_for,
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
        # Bilen setter antall pasienter på problemstillingene som bærer et
        # (André, 12. sep. 2026) — hvilke det er, er data fra tabellen.
        med_antall = js_json(verdier.med_antall())
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
            'neste_kjede': js_json(neste),
            'status_navn': js_json(choices.STATUS_NAVN),
            # Stedene ved «Avreist» og grovsorteringens verdier — data
            # til knappene, som kjeden. Én kilde: `choices`.
            'avreist_til': js_json(list(choices.AVREIST_TIL)),
            'grovsortering': js_json(list(choices.GROVSORTERING)),
            'med_antall': med_antall,
            # Den andre knappen per status (12. sep. 2026), til projeksjonen
            # mens et trykk ligger usendt — samme grunn som kjeden.
            'alternativ': js_json({s: a[0] for s, a in services.ALTERNATIV.items()}),
            'alternativ_navn': js_json({a[0]: a[1] for a in services.ALTERNATIV.values()}),
            'avbryt_fra': js_json(sorted(services.AVBRYT_FRA)),
            # Lydvarselets terskler og om nytt oppdrag skal pipe (12. sep.
            # 2026) — data fra tabellen, hentet på nytt hvert femte minutt.
            'bilinnstillinger': js_json(verdier.bilinnstillinger()),
        })

    return render(request, 'oppdrag/sentral.html',
                  sentralbordkontekst(request))



def sentralbordkontekst(request) -> dict:
    """Alt sentralbordflata trenger — **én kilde, to sider**.

    `/oppdrag/` og `/ko/` viser samme sentralbord fra og med pulje 4, og
    konteksten skal ikke skrives to ganger: en verdimengde som kom til i den
    ene og ikke i den andre er et nedtrekk som er tomt på én av sidene, og det
    ser ut som en datafeil og ikke som en glemt linje.

    **Gatene er `oppdrag`-modulens, også når sida er KO** (André, 18. sep.
    2026). Det er komposisjonsregelen fra rollemodellen §5, samme som
    `kan_se_besetning` bruker for vaktlista: KO *viser* oppdragsmodulens data,
    og hvem som får se dem er oppdragsmodulens sak. Alternativet — egne
    KO-nivåer foran de samme endepunktene — ville lagt tilgangsmodellen to
    steder, og to steder glir fra hverandre.
    """
    return {
        'kan_skrive': har_tilgang(request.user, 'oppdrag', 'skriv_full'),
        # Verdimengdene — lokasjoner, enhetstyper, problemstillinger — settes
        # opp av `skriv_leder` (André, 12. sep. 2026). Knappen vises bare da.
        'kan_lede': (er_global_admin(request.user)
                     or har_tilgang(request.user, 'oppdrag', 'skriv_leder')),
        # **Besetningspanelet er vaktlistas data, lånt inn** (§6 i
        # vaktlistenotatet). Flagget er en *slug* gjennom `core`, ikke en
        # import: oppdragsmodulen skal ikke kjenne vaktlista i Python, og
        # `OppdragImportererIkkeVaktlista` håndhever det.
        #
        # Gaten er `les` i **vaktliste**, ikke i oppdrag — komposisjonsregelen
        # fra rollemodellen §5. Har ikke operatøren vaktlistetilgang, vises
        # panelet ikke i det hele tatt, framfor å gi avledet innsyn i hvem som
        # går vakt.
        'kan_se_besetning': har_tilgang(request.user, 'vaktliste', 'les'),
        # Hvilke problemstillinger som hører til hver hastegrad, og hvilke
        # som bærer et antall — skjemaet bygger nedtrekket om når hastegraden
        # endres (André, 12. sep. 2026). Én kilde: tabellene, gjennom
        # `verdier`. Klienten henter dem på nytt når noen redigerer dem.
        'problemstillinger_for': js_json(verdier.problemstillinger_per_hastegrad()),
        'med_antall': js_json(verdier.med_antall()),
        'enhetstyper': js_json([[t.pk, t.navn] for t in verdier.enhetstyper()]),
        # Sentralbordet uthever ventende oppdrag forbi første lydterskel
        # (André, 12. sep. 2026: «Det bør og komme en utheving hos operatør»).
        'lydvarsel': js_json(verdier.lydvarsel()),
        # Til «Før status» i detaljvisningen (§9): stedene ved «Avreist» og
        # statusnavnene. Samme kilde som enhetsskjermen: `choices`.
        'avreist_til': js_json(list(choices.AVREIST_TIL)),
        'status_navn': js_json(choices.STATUS_NAVN),
        # «Avbrutt» i sentralbordets statusnedtrekk (23. sep. 2026): samme
        # regel som bilens Avbryt-knapp, fra samme kilde.
        'avbryt_fra': js_json(sorted(services.AVBRYT_FRA)),
        'hastegrader': choices.HASTEGRAD,
    }

# ── Enheter ──────────────────────────────────────────────────────────────────

def _synlig_for_bilen(request, oppdrag):
    """Lista utelater oppdraget 30 minutter etter Ledig — «en bil som blir
    stående ulåst». Detalj-, stemplings-, grovsorterings- og antall-endepunktet
    må følge samme regel, ellers kan bilen hente og endre alt den har vært på
    i vakta (13. sep. 2026, M4)."""
    return oppdrag in services.synlige_for_enhet(request.user.enhet, oppdrag.vakt)


@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET'])
def enheter_view(request):
    """Enhetslista med **utledet** status.

    Enheten har ingen statuskolonne. `Ledig (2 venter)` regnes ut fra
    oppdragene hver gang — se `services.enhet_status` for hvorfor det ikke
    lagres.
    """
    # Bilen ser sine egne oppdrag, ikke flåtens (13. sep. 2026, M6):
    # enhetsskjermen bruker ikke dette endepunktet.
    if er_enhetskonto(request.user):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)
    vakt = hent_aktiv_vakt()

    # `?alle=1` tar med pensjonerte enheter. Ressursoversikten på tavla skal
    # ikke se dem — de er borte for godt — men enhetspanelet er stedet man
    # gjenoppretter dem fra, og da må de være synlige et sted.
    # Alfabetisk innenfor gruppa (André, 12. sep. 2026) — `Lower`, ellers er
    # «alfabetisk» databasens alfabet, og SQLite og PostgreSQL svarer ulikt.
    qs = Enhet.objects.select_related('user', 'enhetstype').order_by(Norsk('navn'))
    if request.GET.get('alle') != '1':
        qs = qs.filter(er_aktiv=True)
    enheter = list(qs)
    # **«Ledig siden» hentes i ett spørsmål for hele lista** — lista pollet
    # hvert tiende sekund, og ett oppslag per enhet ville vært N spørringer.
    ledig_siden = services.ledig_siden_bulk(enheter, vakt)

    # **Serialiseringen ligger i `services`, ikke her.** KOs ressursoversikt
    # tegner samme kort og leser samme funksjon; en kopi ville manglet neste
    # felt noen la til, uten at noe ble rødt. Se `services.enhetskort`.
    #
    # Det aktive oppdraget i ett blikk (prosjektleder, 11. sep. 2026): «det
    # handler om å kjapt skaffe oversikt» — nummer, hastegrad, problemstilling
    # og når statusen ble satt, uten å åpne oppdraget.
    data = [services.enhetskort(e, vakt, ledig_siden.get(e.pk)) for e in enheter]

    # Enheter som ikke er på vakt sendes med, de filtreres ikke bort.
    # Sentralbordet viser dem i en egen gruppe: en bil som forsvinner fra
    # tavla er en bil ingen husker å sette inn igjen.
    # Hele svaret, ikke en feltliste (A2) — se `etag_for_svar`.
    etag = etag_for_svar(data)
    if request.META.get('HTTP_IF_NONE_MATCH') == etag:
        svar = HttpResponseNotModified()
        svar['ETag'] = etag
        return svar

    svar = JsonResponse({'status': 'ok', 'data': data})
    svar['ETag'] = etag
    return svar


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['PUT'])
@rate_limit(group='oppdrag:enhet-skriv', rate='60/m', method='PUT')
def enhet_detalj_view(request, pk):
    """Enhetstypen (André, 12. sep. 2026). Navn og konto settes i
    brukeradministrasjonen, som før; typen er oppdragsmodulens egen, og
    settes i enhetspanelet av den som setter biler på og av vakt."""
    try:
        enhet = Enhet.objects.get(pk=pk)
    except Enhet.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Enhet ikke funnet'}, status=404)
    data = json_body(request)
    if 'type' in data:
        # ID-en til en aktiv type, eller tom. Typen er en tabell (12. sep.
        # 2026); en inaktiv type kan beholdes, men ikke velges på nytt.
        if data['type'] in (None, ''):
            enhet.enhetstype = None
        else:
            try:
                enhet.enhetstype = Enhetstype.objects.get(pk=int(data['type']), er_aktiv=True)
            except (Enhetstype.DoesNotExist, TypeError, ValueError):
                return JsonResponse(
                    {'status': 'error', 'message': 'Ukjent enhetstype.'}, status=400)
    enhet.save(update_fields=['enhetstype', 'updated_at'])
    return JsonResponse({'status': 'ok', 'data': {
        'id': enhet.pk, 'type': enhet.enhetstype_id,
        'type_navn': enhet.enhetstype.navn if enhet.enhetstype else ''}})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:vaktmodus', rate='60/m', method='POST')
def enhet_vaktmodus_view(request, pk):
    """Sett enheten i aktiv eller passiv vakt (André, 16. sep. 2026).

    **Passiv er ikke «av vakt».** Enheten har en 24/7-vakt gjennom
    arrangementet; passiv er bakvakt — hun sover, men kan varsles. Derfor et
    eget endepunkt ved siden av `enhet_vakt_view`, ikke en tredje verdi i det:
    «kan ikke få nye oppdrag» er noe helt annet enn «ligger og sover».

    Drift, ikke oppsett — samme terskel som å ta en bil av vakt.
    """
    try:
        enhet = Enhet.objects.select_related('enhetstype').get(pk=pk, er_aktiv=True)
    except Enhet.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Enhet ikke funnet'}, status=404)

    passiv = bool(json_body(request).get('passiv'))
    try:
        services.sett_vaktmodus(
            enhet, passiv=passiv, vakt=hent_aktiv_vakt(), bruker=request.user)
    except ValueError as feil:
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)
    return JsonResponse({'status': 'ok', 'data': {
        'id': enhet.pk, 'navn': enhet.navn, 'passiv_vakt': enhet.passiv_vakt}})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:avvent', rate='60/m', method='POST')
def avvent_view(request, pk, enhet_pk):
    """Operatøren setter enheten til «avventer» på oppdraget.

    Hun blir stående varslet — «Rykk ut» er fortsatt tilgjengelig, og begge
    deler står i loggen. Se `services.avvent_oppdrag`.
    """
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    try:
        enhet = Enhet.objects.select_related('enhetstype').get(pk=enhet_pk)
    except Enhet.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Enhet ikke funnet'}, status=404)
    try:
        services.avvent_oppdrag(oppdrag, enhet, bruker=request.user)
    except ValueError as feil:
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)
    except services.UlovligOvergang as feil:
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=409)
    oppdrag.refresh_from_db()
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:kvitter', rate='60/m', method='POST')
def kvitter_avbrutt_view(request, pk):
    """Operatøren kvitterer ut avbrytelsene på oppdraget.

    Den andre veien — å sende en ny enhet — kvitterer av seg selv i
    `services.varsle_enhet`. Denne finnes for tilfellet der ingen skal
    sendes: merket skal ikke bli stående for alltid på et oppdrag noen har
    tatt stilling til.
    """
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    services.kvitter_avbrutt(oppdrag, bruker=request.user)
    oppdrag.refresh_from_db()
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


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
        aktivt = services.aktivt_oppdrag(enhet, hent_aktiv_vakt())
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
    vakt = hent_aktiv_vakt()

    if request.method == 'GET':
        if er_enhetskonto(request.user):
            # Statusmeldingene følger med: skjermen viser tidslinjen på det
            # aktive oppdraget («Fremme 21:20») og automatisk-markøren på de
            # avsluttede, uten et kall per rad. Få rader — egne, i vakta,
            # innenfor 30-minuttersvinduet — så N+1 her er N liten.
            data = []
            egne = list(services.synlige_for_enhet(request.user.enhet, vakt))
            for o in egne:
                # Bilens egen rad: statusen, kjeden og tidslinjen er hennes.
                kobling = services.koblingsrad(o, request.user.enhet)
                gjeldende = Statusmelding.objects.gjeldende(o)
                egne_meldinger = [m for m in gjeldende if m.oppdragsenhet_id == kobling.pk]
                siste = [m for m in egne_meldinger if m.status == kobling.status]
                rad = oppdrag_til_dict(
                    o, for_enhet=True, koblingsrad=kobling,
                    status_tidspunkt=siste[-1].tidspunkt.isoformat() if siste else None)
                rad['statusmeldinger'] = [melding_til_dict(m) for m in egne_meldinger]
                # De andre bilenes stempler, med navn (André, 12. sep. 2026:
                # «nyttig for de å vite historikken der»). Egen kjede og
                # knapper hviler fortsatt bare på `statusmeldinger`.
                rad['andre_meldinger'] = [melding_til_dict(m) for m in gjeldende
                                          if m.oppdragsenhet_id != kobling.pk]
                data.append(rad)
        else:
            # Ferdigstilte er ute av den aktive lista. De er ikke borte —
            # de ligger i `historikk_liste_view`, søkbare på nummer.
            qs = list(Oppdrag.objects.filter(vakt=vakt, historikk_fra__isnull=True)
                      .select_related('enhet', 'lokasjon', 'hendelse')
                      .prefetch_related('enheter__enhet').order_by('-created_at'))
            gjeldende = Statusmelding.objects.gjeldende_bulk([o.pk for o in qs])
            status_tid = status_tidspunkt_for(qs, gjeldende)
            avbrutt = services.avbrutt_av_bulk([o.pk for o in qs])
            avventer = services.avventer_av_bulk([o.pk for o in qs])
            data = [oppdrag_til_dict(o, status_tidspunkt=status_tid.get(o.pk),
                                     meldinger=gjeldende[o.pk],
                                     avbrutt_av=avbrutt.get(o.pk, []),
                                     avventer_av=avventer.get(o.pk, []))
                    for o in qs]
            # **Ferdige oppdrag i historikken telles med** (André, 21. sep.
            # 2026: «ferdige oppdrag som vises i historikk vises ikke som
            # ferdig i tallstatistikken»). Et ferdig oppdrag går til
            # historikken av seg selv, så lista over inneholder nesten aldri
            # et ferdig — tallet i hodet sto på null. Antallet følger med,
            # og er med i ETag-en: et oppdrag som ryddes bort endrer ikke
            # radene som står igjen.
            i_historikk = Oppdrag.objects.filter(vakt=vakt, historikk_fra__isnull=False).count()

        # **Hele svaret, ikke en feltliste** (26. sep. 2026, A2). Lista over
        # felt ble rettet felt for felt i to uker — meldings-ID-ene, «Rett tid»,
        # avbrytelsene, avventingen, hendelsen, lagene, de delte linjene — og
        # manglet fortsatt hastegrad, lokasjon, antall og notatet. Se
        # `etag_for_svar`. Antallet i historikken står ved siden av.
        etag = etag_for_svar(data, ekstra=None if er_enhetskonto(request.user) else i_historikk)
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            svar = HttpResponseNotModified()
            svar['ETag'] = etag
            return svar
        svar = JsonResponse({'status': 'ok', 'data': data,
                             'antall_i_historikk': (0 if er_enhetskonto(request.user)
                                                    else i_historikk)})
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
    feil = (verdier.valider_problemstilling(data)
            or _valider_problemstilling_og_antall(data, data.get('hastegrad'), data.get('problemstilling')))
    if feil:
        return JsonResponse({'status': 'error', 'message': feil}, status=400)

    # `enhet_ider` (flere enheter, §4) — den første er primær. `enhet_id`
    # godtas fortsatt og betyr én: gamle klienter og tester skal ikke brekke.
    enheter, feil = _enheter_fra_kroppen(data)
    if feil:
        return JsonResponse({'status': 'error', 'message': feil}, status=400)
    try:
        lokasjon = Lokasjon.objects.get(pk=data.get('lokasjon_id'), er_aktiv=True)
    except (Lokasjon.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Ukjent eller inaktiv lokasjon.'}, status=400)

    # Nummeret tildeles inne i transaksjonen: feiler opprettelsen, rulles
    # også telleren tilbake, og nummeret brennes ikke.
    # **Uten enhet** (André, 19. sep. 2026: «å opprette oppdrag behøver ikke
    # en ressurs»): oppdraget står som «Trenger ressurs» fra første sekund,
    # med samme opptrapping på tavla som når en bil rykket videre. Ingen lyd
    # — lyd går bare til enhetene, og ingen er varslet.
    naa = timezone.now()
    with transaction.atomic():
        # **Alle enhetene varsles gjennom `varsle_enhet`, også den første**
        # (26. sep. 2026, A1). Oppdraget ble opprettet med `enhet=enheter[0]`,
        # og da laget broen i `Oppdrag.save()` den første koblingsraden — uten
        # bjella. Det vanligste tilfellet, én bil, fikk ingen rad. `varsle_enhet`
        # gjør den første til primær og fryser modusen, som broen gjorde.
        oppdrag = Oppdrag.objects.create(
            vakt=vakt,
            oppdragsnummer=services.neste_oppdragsnummer(vakt),
            enhet=None,
            problemstilling=data['problemstilling'],
            hastegrad=data['hastegrad'],
            antall=data.get('antall'),
            lokasjon=lokasjon,
            fritekst=(data.get('fritekst') or '').strip(),
            opprettet_av=request.user,
            trenger_ressurs=not enheter,
            trenger_ressurs_siden=None if enheter else naa,
        )
        for enhet in enheter:
            services.varsle_enhet(oppdrag, enhet, bruker=request.user)
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


def _valider_problemstilling_og_antall(data, hastegrad, problemstilling, *, gjeldende=None):
    """Problemstillingen må høre til hastegraden, og `antall` er et heltall
    som bare finnes for problemstillinger som bærer et. Muterer ``data`` —
    `antall` normaliseres til int eller None. Returnerer feiltekst eller None.

    Ved redigering sendes bare feltene som endres, så kalleren gir de
    *gjeldende* verdiene for det som mangler i kroppen."""
    if hastegrad is not None and problemstilling is not None:
        if not verdier.problemstilling_passer(hastegrad, problemstilling, gjeldende=gjeldende):
            return (f'«{problemstilling}» er ikke en problemstilling for '
                    f'hastegrad {hastegrad}.')
    if not verdier.baerer_antall(problemstilling or ''):
        # Ingen antall å bære: feltet tømmes uansett hva klienten sendte.
        if 'antall' in data or problemstilling is not None:
            data['antall'] = None
        return None
    raa = data.get('antall')
    if raa in (None, ''):
        data['antall'] = None
        return None
    try:
        antall = int(raa)
    except (TypeError, ValueError):
        return 'Antall må være et helt tall.'
    if antall < 0 or antall > 32000:
        return 'Antall må være et helt tall mellom 0 og 32000.'
    data['antall'] = antall
    return None


def _enheter_fra_kroppen(data):
    """``(enheter, feil)`` fra `enhet_ider` eller `enhet_id`, i oppgitt rekkefølge.

    Dubletter strykes (samme bil to ganger er én bil), og alle må være
    aktive og på vakt — én ukjent avviser hele opprettelsen, ikke bare den
    ene: operatøren mente å sende flere, og skal ikke få ett oppdrag med
    færre enn hun krysset av.

    **Tom liste er lov** (19. sep. 2026): oppdraget opprettes uten enhet.
    `enhet_ider` må da være oppgitt som `[]` — en kropp helt uten enhetsfelt
    er fortsatt en feil, så en gammel klient som glemte feltet ikke stille
    får et oppdrag uten bil.
    """
    ukjent = 'Ukjent enhet, eller enheten er ikke på vakt.'
    raa = data.get('enhet_ider')
    if raa is None:
        if data.get('enhet_id') is None:
            return None, 'Oppgi enhetene (tom liste for ingen).'
        raa = [data.get('enhet_id')]
    if not isinstance(raa, list):
        return None, 'Oppgi minst én enhet.'
    if not raa:
        return [], None
    ider = []
    for verdi in raa:
        try:
            pk = int(verdi)
        except (TypeError, ValueError):
            return None, ukjent
        if pk not in ider:
            ider.append(pk)
    funnet = {e.pk: e for e in Enhet.objects.filter(pk__in=ider, er_aktiv=True, pa_vakt=True)}
    if len(funnet) != len(ider):
        return None, ukjent
    return [funnet[pk] for pk in ider], None


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'PUT', 'DELETE'])
@rate_limit(group='oppdrag:detalj-skriv', rate='120/m', method=['PUT', 'DELETE'])
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
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    kobling = None
    if er_enhetskonto(request.user):
        kobling = services.koblingsrad(oppdrag, request.user.enhet)
        if kobling is None:
            return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)
        if not _synlig_for_bilen(request, oppdrag):
            return JsonResponse({'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    if request.method == 'GET':
        andre = []
        if kobling is not None:
            # Bilen får sin egen kjede i `statusmeldinger` — det er den
            # knappene bygger på. De andre bilenes gjeldende stempler følger
            # med i `andre_meldinger` (§7.3, snudd 12. sep. 2026): historikken
            # på oppdraget er nyttig i bilen, og navnet står på hver rad.
            alle_gjeldende = Statusmelding.objects.gjeldende(oppdrag)
            gjeldende = [m for m in alle_gjeldende if m.oppdragsenhet_id == kobling.pk]
            andre = [m for m in alle_gjeldende if m.oppdragsenhet_id != kobling.pk]
            alle = (Statusmelding.objects.filter(oppdragsenhet=kobling)
                    .select_related('oppdragsenhet__enhet', 'meldt_av', 'trukket_tilbake_av')
                    .order_by('created_at'))
        else:
            gjeldende = Statusmelding.objects.gjeldende(oppdrag)
            alle = (Statusmelding.objects.filter(oppdrag=oppdrag)
                    .select_related('oppdragsenhet__enhet', 'meldt_av', 'trukket_tilbake_av')
                    .order_by('created_at'))
        return JsonResponse({'status': 'ok', 'data': {
            **oppdrag_til_dict(oppdrag, for_enhet=er_enhetskonto(request.user),
                               koblingsrad=kobling),
            'statusmeldinger': [melding_til_dict(m) for m in gjeldende],
            'andre_meldinger': [melding_til_dict(m) for m in andre],
            'historikk': [melding_til_dict(m) for m in alle],
            'enhetsbytter': [bytte_til_dict(b) for b in oppdrag.enhetsbytter.all()],
            'enhetshendelser': [hendelse_til_dict(h) for h in
                                oppdrag.enhetshendelser.select_related('enhet', 'av')],
            # Endringene i verdiene (23. sep. 2026) — til tidslinjen.
            'endringer': [endring_til_dict(e) for e in oppdrag.endringer.all()],
            # Knappen skal bare finnes når den kan brukes.
            'kan_slettes': (not er_enhetskonto(request.user)
                            and services.kan_slettes(oppdrag, request.user)),
        }})

    if request.method == 'DELETE':
        # Sletting (André, 12. sep. 2026): sentralbordet mens alle venter,
        # global admin i historikken. `{"confirm": true}` i kroppen stopper et
        # kall som treffer URL-en uten å mene det — dialogen stopper feilklikket.
        if er_enhetskonto(request.user) or not services.kan_slettes(oppdrag, request.user):
            return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)
        if not json_body(request).get('confirm'):
            return JsonResponse(
                {'status': 'error', 'message': 'Bekreftelse mangler. Send {"confirm": true}.'},
                status=400)
        services.slett_oppdrag(oppdrag)
        return JsonResponse({'status': 'ok'})

    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    data = json_body(request)
    try:
        validate_oppdrag_choice_fields(data)
    except ValidationError as feil:
        return JsonResponse(
            {'status': 'error', 'message': '; '.join(feil.messages)}, status=400)

    # **Hastegraden alene** (23. sep. 2026, rett i vinduet): problemstillingen
    # beholdes om den passer, ellers blir den «Udefinert» — ikke en 400.
    # Sendes begge, er det operatørens valg, og da gjelder valideringen under.
    automatisk = set()
    if 'hastegrad' in data and 'problemstilling' not in data:
        ny = services.problemstilling_etter_hastegrad(data['hastegrad'], oppdrag.problemstilling)
        if ny != oppdrag.problemstilling:
            data['problemstilling'] = ny
            automatisk.add(Oppdragsendring.PROBLEMSTILLING)

    feil = (verdier.valider_problemstilling(data, gjeldende=oppdrag.problemstilling)
            or _valider_problemstilling_og_antall(
                data, data.get('hastegrad', oppdrag.hastegrad),
                data.get('problemstilling', oppdrag.problemstilling),
                gjeldende=oppdrag.problemstilling))
    if feil:
        return JsonResponse({'status': 'error', 'message': feil}, status=400)
    # **Bare feltene som endres, skrives** (26. sep. 2026, A5). Objektet ble
    # lest før valideringen; en `save()` uten `update_fields` skrev derfor
    # tilbake status, `trenger_ressurs`, `historikk_fra` og `enhet` slik de
    # sto da — og en stempling fra bilen i mellomtiden forsvant.
    endret = []
    if 'problemstilling' in data:
        oppdrag.problemstilling = data['problemstilling']
        endret.append('problemstilling')
    if 'hastegrad' in data:
        oppdrag.hastegrad = data['hastegrad']
        endret.append('hastegrad')
    if 'antall' in data:
        oppdrag.antall = data['antall']
        endret.append('antall')
    if 'fritekst' in data:
        oppdrag.fritekst = (data.get('fritekst') or '').strip()
        endret.append('fritekst')
    if 'lokasjon_id' in data:
        try:
            oppdrag.lokasjon = Lokasjon.objects.get(pk=data['lokasjon_id'])
        except (Lokasjon.DoesNotExist, ValueError, TypeError):
            return JsonResponse(
                {'status': 'error', 'message': 'Ukjent lokasjon.'}, status=400)
        endret.append('lokasjon')
    # Verdiene før endringen, lest av raden som står i basen — ikke av
    # objektet over, som alt er endret.
    foer = services.felt_i_tidslinjen(Oppdrag.objects.select_related('lokasjon').get(pk=oppdrag.pk))
    with transaction.atomic():
        if endret:
            oppdrag.save(update_fields=endret + ['updated_at'])
        services.logg_endringer(oppdrag, foer, bruker=request.user, automatisk=automatisk)
    # Svaret leses på nytt: objektet over bærer status fra før lagringen.
    oppdrag.refresh_from_db()
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:flytt', rate='60/m', method='POST')
def flytt_view(request, pk):
    """Flytt oppdraget til en annen enhet, og skriv det i oppdragets logg.

    Statusen står. Meldingene den første enheten rakk å sende blir stående med
    `meldt_av` intakt: de skjedde.
    """
    if er_enhetskonto(request.user):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)
    try:
        oppdrag = Oppdrag.objects.get(pk=pk, vakt=hent_aktiv_vakt())
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    kropp = json_body(request)
    try:
        ny_enhet = Enhet.objects.get(
            pk=kropp.get('enhet_id'), er_aktiv=True, pa_vakt=True)
    except (Enhet.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error',
             'message': 'Ukjent enhet, eller enheten er ikke på vakt.'}, status=400)
    # Med flere enheter er «flytt» flytt av *én* rad. Uten `fra_enhet_id` er
    # det den primære — slik det alltid har vært.
    fra_enhet = None
    if kropp.get('fra_enhet_id') is not None:
        try:
            fra_enhet = Enhet.objects.get(pk=kropp['fra_enhet_id'])
        except (Enhet.DoesNotExist, ValueError, TypeError):
            return JsonResponse(
                {'status': 'error', 'message': 'Ukjent enhet å flytte fra.'}, status=400)

    try:
        bytte = services.flytt_til_enhet(
            oppdrag, ny_enhet, bruker=request.user, fra_enhet=fra_enhet)
    except ValueError as feil:
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)
    if bytte is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget står allerede på denne enheten.'},
            status=400)
    return JsonResponse({'status': 'ok', 'data': bytte_til_dict(bytte)})


# ── Enhetene på oppdraget (flere enheter, §4 og §9) ─────────────────────────

def _oppdrag_og_enhet(request, pk, enhet_pk):
    """``(oppdrag, enhet, feilsvar)`` for endepunktene under.

    Enhetskontoer stenges ute uansett nivå, som i `korriger_view`: dette er
    sentralbordets føring av hva bilene gjør, ikke bilens stempling.
    """
    if er_enhetskonto(request.user):
        return None, None, JsonResponse(
            {'status': 'error', 'message': 'Enheter fører ikke for hverandre.'},
            status=403)
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return None, None, JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    try:
        enhet = Enhet.objects.get(pk=enhet_pk)
    except Enhet.DoesNotExist:
        return None, None, JsonResponse(
            {'status': 'error', 'message': 'Ukjent enhet.'}, status=404)
    return oppdrag, enhet, None


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST', 'DELETE'])
@rate_limit(group='oppdrag:oppdragsenhet', rate='60/m', method=['POST', 'DELETE'])
def oppdragsenhet_view(request, pk, enhet_pk):
    """Varsle en enhet til (POST), eller ta henne av (DELETE).

    Å ta av går bare mens hun venter, og aldri den siste — har bilen rykket
    ut, er det en hendelse, og svaret er «Ledig» fra bilen eller en føring
    (`foering_view`), ikke å late som hun aldri var der.
    """
    oppdrag, enhet, feil = _oppdrag_og_enhet(request, pk, enhet_pk)
    if feil:
        return feil
    try:
        if request.method == 'POST':
            if not (enhet.er_aktiv and enhet.pa_vakt):
                return JsonResponse(
                    {'status': 'error',
                     'message': 'Ukjent enhet, eller enheten er ikke på vakt.'},
                    status=400)
            services.varsle_enhet(oppdrag, enhet, bruker=request.user)
        else:
            services.ta_av_enhet(oppdrag, enhet, bruker=request.user)
    except ValueError as feil:
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)
    oppdrag.refresh_from_db()
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:foering', rate='60/m', method='POST')
def foering_view(request, pk, enhet_pk, overgang, sted=None):
    """Sentralbordet setter en enhets status (§9) — hvilken som helst av dem.

    **Leser kroppen** — `tidspunkt` er påkrevd for en ny melding, for hele
    poenget er å føre bakover i tid. Det er derfor `skriv_full` og ikke
    `skriv_handling`: bilens stemplingsendepunkt leser ingen domenefelt, og
    dette er en annen aktør med et annet endepunkt.

    Fra 22. sep. 2026 går det også bakover, og da trekkes meldingene etter
    målet tilbake i stedet for å slettes (`services.foer_status`). `venter`
    er derfor et gyldig mål her, selv om ingen stempler den.
    """
    if overgang not in services.FOERBARE and overgang != choices.AVBRYT:
        return JsonResponse(
            {'status': 'error', 'message': f'Ukjent overgang «{overgang}».'}, status=404)
    if sted and (overgang != choices.AVREIST or sted not in choices.AVREIST_TIL_NAVN):
        return JsonResponse(
            {'status': 'error', 'message': f'Ukjent sted «{sted}» for «{overgang}».'},
            status=404)
    oppdrag, enhet, feil = _oppdrag_og_enhet(request, pk, enhet_pk)
    if feil:
        return feil

    # Tom tidspunkt er lov: et steg tilbake skriver ingen ny melding, og da
    # trengs det ingen tid. Tjenesten krever den der den trengs.
    raa = json_body(request).get('tidspunkt')
    tidspunkt = None
    if raa:
        tidspunkt = parse_datetime(str(raa))
        if tidspunkt is None:
            return JsonResponse(
                {'status': 'error', 'message': 'Ugyldig tidspunkt.'}, status=400)
        if timezone.is_naive(tidspunkt):
            tidspunkt = timezone.make_aware(tidspunkt)

    try:
        if overgang == choices.AVBRYT:
            # «Avbrutt» (23. sep. 2026): ikke en status i kjeden, men bilens
            # Avbryt-knapp ført av sentralbordet — se `services.foer_avbrutt`.
            melding = services.foer_avbrutt(oppdrag, enhet, tidspunkt=tidspunkt,
                                            bruker=request.user)
        else:
            melding = services.foer_status(
                oppdrag, enhet, overgang, tidspunkt=tidspunkt, bruker=request.user,
                sted=sted or '', sted_tekst=_sted_tekst(json_body(request), sted))
    except (services.UlovligOvergang, services.KorreksjonUgyldig) as feil:
        # 400, ikke 409: operatøren sitter ved et skjema, og meldingen sier
        # hvilket ledd som mangler eller hvilken nabo som er i veien.
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)
    oppdrag.refresh_from_db()
    return JsonResponse({'status': 'ok', 'data': {
        'oppdrag': oppdrag_til_dict(oppdrag),
        # Meldingen bak statusen enheten står i nå — `None` for Venter.
        'melding': melding_til_dict(melding) if melding else None,
    }})


# ── Stempling ────────────────────────────────────────────────────────────────

#: Det lukkede kroppsskjemaet fra §5.1. Tre nøkler, og settet er hele
#: kontrakten: en test kan uttømme det ved å sende en nøkkel til og kreve 400.
#: En feltwhitelist inne i en generell PUT kan ikke testes slik — settet av
#: felter der vokser med modellen. `sted_tekst` (19. sep. 2026) er det ene
#: domenefeltet, og det leses bare ved «Annet sted» — se `_sted_tekst`.
STEMPLING_TILLATTE_NOKLER = frozenset({'klienttid', 'idempotency_key', 'sted_tekst'})


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
@rate_limit(group='oppdrag:grovsortering', rate='60/m', method='POST')
def grovsortering_view(request, pk, verdi):
    """Bilen setter Rød/Gul/Grønn på sitt eget oppdrag.

    Samme form som stemplingene: verdien i URL-en, ikke i kroppen, og bare
    enhetskontoen som eier oppdraget. Det er ikke en statusovergang — bilen
    kan endre vurderingen underveis — så den går ikke gjennom
    `sett_status`, og den er ikke idempotent-nøklet: å sette «Rød» to ganger
    er «Rød».
    """
    if verdi not in choices.GROVSORTERING_NAVN:
        return JsonResponse(
            {'status': 'error', 'message': f'Ukjent grovsortering «{verdi}».'},
            status=404)
    if not er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Bare enhetskontoer grovsorterer.'},
            status=403)
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    rad = services.koblingsrad(oppdrag, request.user.enhet)
    if rad is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget tilhører en annen enhet.'},
            status=403)
    if not _synlig_for_bilen(request, oppdrag):
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    oppdrag.grovsortering = verdi
    oppdrag.save(update_fields=['grovsortering', 'updated_at'])
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(
        oppdrag, for_enhet=True, koblingsrad=rad)})


@modul_kreves('oppdrag', 'skriv_handling', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:antall', rate='60/m', method='POST')
def antall_view(request, pk, antall):
    """Bilen setter antall pasienter på sitt eget oppdrag (André, 12. sep.
    2026: «bilen må sette antall pasienter ikke operatøren»).

    Samme form som grovsorteringen: tallet i URL-en, bare enhetskontoen som
    er på oppdraget, ikke idempotent-nøklet — «3» to ganger er «3». Bare for
    problemstillinger som bærer et antall; ellers 400. Tomt felt vises som
    «1 pasient», så det laveste tallet som kan settes er 1.
    """
    if not er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Bare enhetskontoer setter antall.'},
            status=403)
    if antall < 1 or antall > 999:
        return JsonResponse(
            {'status': 'error', 'message': 'Antall må være mellom 1 og 999.'}, status=400)
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    rad = services.koblingsrad(oppdrag, request.user.enhet)
    if rad is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget tilhører en annen enhet.'},
            status=403)
    if not _synlig_for_bilen(request, oppdrag):
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    if not verdier.baerer_antall(oppdrag.problemstilling):
        return JsonResponse(
            {'status': 'error', 'message': f'«{oppdrag.problemstilling}» bærer ikke et antall.'},
            status=400)
    oppdrag.antall = antall
    oppdrag.save(update_fields=['antall', 'updated_at'])
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(
        oppdrag, for_enhet=True, koblingsrad=rad)})


def _sted_tekst(data, sted) -> str:
    """Friteksten ved «Annet sted» (19. sep. 2026) — bare da, ellers tom. Det
    ene domenefeltet bilens endepunkt leser fra kroppen, og det er bevisst
    smalt: en streng, kappet til 120 tegn, uten betydning for overgangen."""
    if sted != 'annet':
        return ''
    return str(data.get('sted_tekst') or '').strip()[:120]


@modul_kreves('oppdrag', 'skriv_handling', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:stempling', rate='60/m', method='POST')
def stempling_view(request, pk, overgang, sted=None):
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
    # «Avbryt» (12. sep. 2026) er en handling, ikke en status, men går
    # samme vei som en stempling: navngitt i URL-en, køet i bilen, nøklet.
    if overgang not in services.STEMPLBARE and overgang != choices.AVBRYT:
        return JsonResponse(
            {'status': 'error', 'message': f'Ukjent overgang «{overgang}».'},
            status=404)
    # Stedet finnes bare for «Avreist», og bare fra lista. 404, som for en
    # ukjent overgang: en URL som ikke finnes, ikke en kropp som er feil.
    if sted is not None and (overgang != choices.AVREIST
                             or sted not in choices.AVREIST_TIL_NAVN):
        return JsonResponse(
            {'status': 'error', 'message': f'Ukjent sted «{sted}» for «{overgang}».'},
            status=404)

    if not er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Bare enhetskontoer stempler.'},
            status=403)

    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    rad = services.koblingsrad(oppdrag, request.user.enhet)
    if rad is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget tilhører en annen enhet.'},
            status=403)
    if not _synlig_for_bilen(request, oppdrag):
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)
    # **Bilen melder Ledig bare fra Leverer og Behandlet** (André, 12. sep.
    # 2026: «Etter avreist kan du ikke slå deg ledig før du har levert»). I
    # Rykker ut og Fremme heter utgangen Avbryt, i Fremme også Behandlet på
    # sted (22. sep. 2026). Sentralen
    # kan fortsatt føre Ledig fra alt — det går gjennom `foering_view`.
    if overgang == choices.LEDIG and rad.status not in services.BILEN_KAN_LEDIG_FRA:
        return JsonResponse({'status': 'error', 'message': (
            'Ledig meldes etter Leverer eller Behandlet på sted. '
            'Skal oppdraget avbrytes, meld det til KO.')}, status=400)
    # **Grovsorteringen må stå** før Behandlet på sted og før Ledig fra
    # Leverer — og før Avreist når innstillingen sier det (André, 12. sep.
    # 2026). Ellers ender pasienter i statistikken uten sortering.
    if (not oppdrag.grovsortering and services.kan_gaa_til(rad.status, overgang)
            and verdier.grov_kreves_for(oppdrag, overgang, rad.status)):
        return JsonResponse({'status': 'error', 'message': (
            'Sett grovsortering (Rød, Gul eller Grønn) først.')}, status=400)

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
                    'oppdrag': oppdrag_til_dict(
                        oppdrag, for_enhet=True, koblingsrad=rad),
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
                oppdrag, bruker=request.user, enhet=request.user.enhet,
                tidspunkt=tidspunkt, forsinket=forsinket)
        elif overgang == choices.AVBRYT:
            melding = services.avbryt_oppdrag(
                oppdrag, bruker=request.user, enhet=request.user.enhet,
                tidspunkt=tidspunkt, forsinket=forsinket)
        elif overgang == choices.BEHANDLET:
            # Ett trykk: Behandlet og Ledig (André, 12. sep. 2026).
            melding = services.behandle_paa_sted(
                oppdrag, bruker=request.user, enhet=request.user.enhet,
                tidspunkt=tidspunkt, forsinket=forsinket)
        else:
            melding = services.sett_status(
                oppdrag, overgang, bruker=request.user, enhet=request.user.enhet,
                tidspunkt=tidspunkt, forsinket=forsinket, sted=sted or '',
                sted_tekst=_sted_tekst(data, sted))
    except services.ProblemstillingUdefinert as feil:
        # Ikke en utdatert skjerm — et oppdrag som mangler noe. Meldingen er
        # bilens å lese, og 400 får køen til å slippe raden og vise den.
        if idem:
            forkast(idem)
        return JsonResponse({'status': 'error', 'message': str(feil)}, status=400)
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

    # Raden leses på nytt: `sett_status` skrev på sitt eget eksemplar av den,
    # og bilen skal se statusen den nettopp stemplet, ikke den før.
    return JsonResponse({'status': 'ok', 'data': {
        'oppdrag': oppdrag_til_dict(
            oppdrag, for_enhet=True,
            koblingsrad=services.koblingsrad(oppdrag, request.user.enhet)),
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
@rate_limit(group='oppdrag:historikk', rate='60/m', method=['POST', 'DELETE'])
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
                   .get(pk=pk, vakt=hent_aktiv_vakt()))
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
@require_http_methods(['GET', 'DELETE'])
@rate_limit(group='oppdrag:historikk-liste', rate='60/m', method=['GET', 'DELETE'])
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
    if request.method == 'DELETE':
        # Global admin tømmer historikken for vakta (André, 12. sep. 2026:
        # «individuelt og alle»). Bekreftelse i kroppen, som enkeltsletting.
        if not er_global_admin(request.user):
            return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)
        if not json_body(request).get('confirm'):
            return JsonResponse(
                {'status': 'error', 'message': 'Bekreftelse mangler. Send {"confirm": true}.'},
                status=400)
        antall = 0
        for o in Oppdrag.objects.filter(vakt=hent_aktiv_vakt(), historikk_fra__isnull=False):
            services.slett_oppdrag(o)
            antall += 1
        return JsonResponse({'status': 'ok', 'data': {'slettet': antall}})

    if er_enhetskonto(request.user):
        return JsonResponse(
            {'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    qs = (Oppdrag.objects
          .filter(vakt=hent_aktiv_vakt(), historikk_fra__isnull=False)
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

    # Bulk her også: historikken kan være hele vakta, og `oppdrag_til_dict`
    # slår ellers opp avbrytelsene én gang per rad.
    rader = list(qs)
    avbrutt = services.avbrutt_av_bulk([o.pk for o in rader])
    avventer = services.avventer_av_bulk([o.pk for o in rader])
    return JsonResponse({'status': 'ok', 'data': [
        oppdrag_til_dict(o, avbrutt_av=avbrutt.get(o.pk, []),
                         avventer_av=avventer.get(o.pk, [])) for o in rader]})


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
                   .get(pk=pk, oppdrag__vakt=hent_aktiv_vakt()))
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
