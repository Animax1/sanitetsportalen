"""Ressursene (enhetene) og skiftene på dem, og besetningen `/oppdrag/` og `/ko/` leser.

Delt ut av `vaktliste/views.py` i G2 (14. okt. 2026) — tilgangstersklene og
kartet over filene står i docstringen der.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import har_tilgang, modul_kreves
from core.ratelimit import rate_limit

from . import services, vaktdrift
from .models import Mannskap, Ressurs, Ressursgruppe, Vaktliste, Vaktpost
from .views import _ukjent_peker, _nektet, _int, _tid, _ressurs_til_dict, _vaktpost_til_dict


# ── Ressurser ────────────────────────────────────────────────────────────────

@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:ressurser', rate='120/m', method='POST')
def ressurser_view(request, pk):
    """Legg en ressurs til vaktlista.

    Fanerekkefølgen settes automatisk til «sist» — den som bygger vakta legger
    inn ressursene i den rekkefølgen hun tenker på dem, og det er den fanene
    skal ha. Ingen skriver et tall.

    Reservasjonen (`korps`) settes her, av den som **deler ut**. Korps-brukeren
    bemanner det som er reservert henne, men bestemmer ikke selv hva hun får —
    kunne hun det, ville reservasjonen ikke vært en tildeling.

    **Å opprette en ressurs er `skriv_leder`**, ikke `skriv_full` (30. aug.
    2026). Bemanneren fyller plassene på ressursene som finnes; hva vakta
    består av er vaktlederens beslutning.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.i_portal().get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)

    data = json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return json_feil('Enheten må ha et navn.')

    gruppe_id = _int(data.get('gruppe_id'))
    gruppe = Ressursgruppe.objects.filter(pk=gruppe_id).first()
    if not gruppe:
        return json_feil('Enheten må høre til en ressurstype.')

    # **Noen grupper finnes i ett eksemplar.** Samleplassen og KO er
    # samlingspunkt for flere korps, ikke flåter — «Samleplass 2» er ikke en
    # ny samleplass, det er en delt vaktliste ingen leser riktig. Knappen er
    # borte i grensesnittet, men en regel som bare finnes der er ingen regel:
    # nedtrekket i «Ny ressurs» og et bart POST når begge hit.
    if not gruppe.flere_enheter and Ressurs.objects.filter(
            vaktliste=vl, gruppe=gruppe).exists():
        return json_feil(f'«{gruppe.navn}» finnes i ett eksemplar, og står '
                     f'allerede på denne vaktlisten.')

    ukjent = _ukjent_peker(Ressurs, korps=_int(data.get('korps_id')),
                           enhet=_int(data.get('enhet_id')))
    if ukjent:
        return json_feil(ukjent)
    try:
        with transaction.atomic():
            ressurs = Ressurs.objects.create(
                vaktliste=vl,
                navn=navn,
                gruppe=gruppe,
                korps_id=_int(data.get('korps_id')),
                enhet_id=_int(data.get('enhet_id')),
                rekkefolge=(_int(data.get('rekkefolge'))
                            or services.neste_rekkefolge(vl)),
            )
    except IntegrityError:
        return json_feil(f'«{navn}» finnes allerede på denne vaktlisten.')

    ressurs = (Ressurs.objects
               .select_related('korps', 'enhet', 'gruppe').get(pk=ressurs.pk))
    return JsonResponse(
        {'status': 'ok', 'data': _ressurs_til_dict(ressurs)}, status=201)


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET'])
def ressurser_uten_enhet_view(request):
    """Ressursene uten oppdragsenhet, for KOs tavle (pulje 6).

    Samme gate som `besetning_view` under, av samme grunn: svaret bærer navn
    på mannskap fra alle korps, og en `les`-bruker som bare ser sitt eget
    korps på `/vaktliste/` skal ikke få alle her. KO-operatøren har
    `oppdrag:les` (tavla krever det); den som ser alle korps har det fra før.
    """
    if not (services.ser_alle_korps(request.user)
            or har_tilgang(request.user, 'oppdrag', 'les')):
        return json_feil('Listen viser alle korps, og du ser bare ditt eget.', status=403)
    return JsonResponse({'status': 'ok', 'data': vaktdrift.ressurser_uten_enhet()})


# ── Koblingen til /oppdrag (fase 6) ──────────────────────────────────────────

@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET'])
def besetning_view(request, pk):
    """Besetningen på én enhet — sentralbordets vindu inn i vaktlista.

    **Avhengighetsretningen går én vei: `vaktliste` → `oppdrag`** (§6).
    Oppdragsmodulen importerer ikke vaktlista; sentralbordet henter dette
    endepunktet og rendrer svaret. Koblingen ligger dermed i nettleseren, ikke
    i Python — samme grep som lot statistikkappen slutte å importere
    pasientmodulen.

    **Gaten er `les` i vaktliste, ikke i oppdrag.** Har ikke operatøren
    vaktlistetilgang, får hun 403 og panelet vises ikke i det hele tatt. Det
    er komposisjonsregelen fra rollemodellen §5: en modul viser bare kilder
    brukeren har tilgang til, framfor å gi avledet innsyn i data hun ikke
    skulle sett.

    404 betyr «enheten er ikke koblet til en ressurs i denne vakta» — noe
    annet enn «ingen på vakt», og de to skal ikke se like ut for operatøren.
    """
    # Svaret bærer telefon og ISSI for alle på bilen, uansett korps. En
    # `les`-bruker som på `/vaktliste/` bare ser sitt eget korps skal ikke
    # kunne iterere `<pk>` her og få alle (13. sep. 2026, M3). Sentralbordet
    # har `oppdrag:les`; den som ser alle korps har det fra før.
    if not (services.ser_alle_korps(request.user)
            or har_tilgang(request.user, 'oppdrag', 'les')):
        return json_feil('Besetningen viser alle korps, og du ser bare ditt eget.', status=403)
    data = vaktdrift.besetning(pk)
    if data is not None:
        return JsonResponse({'status': 'ok', 'data': data})

    # **Meldingen skal si sannheten, ikke bare nei.** «Ikke koblet» leses som
    # «koblingen din er ødelagt» — og den vanligste grunnen til at man ikke
    # finner besetningen er at bilen er koblet i en vakt man har *planlagt*,
    # mens sentralbordet står i den aktive. Da er ikke oppsettet feil; det er
    # feil vakt som er aktiv, og det er noe helt annet å rette.
    annen = vaktdrift.koblet_i_annen_vakt(pk)
    if annen:
        return json_feil(
            f'Enheten er koblet i vaktlisten for «{annen}», som verken er i '
            f'drift eller hører til den aktive vakten. Sett den listen i drift, '
            f'eller koble enheten i vaktlisten for vakten som går nå.', status=404)
    return json_feil('Enheten er ikke koblet til noen vaktliste.',
                 status=404)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='vaktliste:ressurs-skriv', rate='120/m', method=['PUT', 'DELETE'])
def ressurs_detalj_view(request, pk):
    """Rediger eller fjern en ressurs.

    **Tre terskler i ett endepunkt**: navnet krever `kan_gi_nytt_navn`,
    reservasjonen er utdeling og krever `kan_sette_opp_skift` (30. sep. 2026),
    og gruppe, enhetskobling, rekkefølge og sletting krever `kan_lede`.

    **DELETE krever `{"confirm": true}`**, som sletting av en vaktliste. Det er
    ikke en bekreftelsesdialog flyttet til serveren — dialogen står i
    grensesnittet — men et krav om at klienten sier hva den mener. En
    slette-URL som virker på et bart kall er en URL noe annet kan treffe ved
    et uhell, og CASCADE tar alle skiftene med seg.
    """
    try:
        ressurs = (Ressurs.objects.i_portal()
                   .select_related('korps', 'enhet', 'gruppe').get(pk=pk))
    except Ressurs.DoesNotExist:
        return json_feil('Enhet ikke funnet', status=404)

    # **Inngangsporten er navneretten, ikke `kan_lede`** (André, 15. sep.
    # 2026: «redigere ressursens navn, men ikke gruppe, reservering, enhet i
    # oppdragsmodulen og sletting»). Navnet er det ene korps-føreren skal kunne
    # rette — bilen heter «Sola 56», ikke «Ambulanse 2» — og det er en
    # retting hun ser konsekvensen av med én gang. Alt annet på ressursen er
    # oppsett, og står i `RESSURS_OPPSETTFELTER`.
    #
    # Porten sto på `kan_bemanne_ressurs` ett døgn, og var i praksis stengt:
    # en ny ressurs er ureservert, så regelen slapp bare gjennom de bilene
    # lederen alt hadde delt ut. Se `services.kan_gi_nytt_navn`.
    if not services.kan_gi_nytt_navn(request.user, ressurs):
        return _nektet()

    if request.method == 'DELETE':
        # CASCADE tar skiftene, og det er ikke en handling man angrer.
        if not services.kan_lede(request.user):
            return _nektet('Enheter fjernes av den som satte dem opp.')
        if not json_body(request).get('confirm'):
            return json_feil('Bekreftelse mangler. Send {"confirm": true}.')
        # CASCADE tar vaktpostene. Det er riktig her: fjernes bilen fra
        # vakta, finnes ikke skiftene på den heller.
        ressurs.delete()
        return JsonResponse({'status': 'ok'})

    data = json_body(request)

    sperret = services.oppsettfelter(data, services.RESSURS_OPPSETTFELTER)
    if sperret and not services.kan_lede(request.user):
        return _nektet('Ressurstype og kobling til delt konto settes av den '
                       'som setter opp vakten: ' + ', '.join(sperret))
    sperret = services.oppsettfelter(data, services.RESSURS_UTDELINGSFELTER)
    if sperret and not services.kan_sette_opp_skift(request.user):
        return _nektet('Enheten deles ut av den som setter opp skiftene.')

    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return json_feil('Enheten må ha et navn.')
        ressurs.navn = navn
    if 'gruppe_id' in data:
        gruppe_id = _int(data['gruppe_id'])
        if not gruppe_id or not Ressursgruppe.objects.filter(pk=gruppe_id).exists():
            return json_feil('Enheten må høre til en ressurstype.')
        ressurs.gruppe_id = gruppe_id
    if 'korps_id' in data:
        ressurs.korps_id = _int(data['korps_id'])
    if 'enhet_id' in data:
        ressurs.enhet_id = _int(data['enhet_id'])
    if 'rekkefolge' in data:
        ressurs.rekkefolge = _int(data['rekkefolge']) or 100

    ukjent = _ukjent_peker(Ressurs, korps=ressurs.korps_id, enhet=ressurs.enhet_id)
    if ukjent:
        return json_feil(ukjent)
    # **Tømmes reservasjonen, blir plassene som arvet den åpne for alle** —
    # ellers ble de kladd igjen. Se `services.frigi_arvede_plasser`. Samme
    # transaksjon: frigjort uten at reservasjonen ble tømt er et halvt svar.
    tommes = 'korps_id' in data and ressurs.korps_id is None
    try:
        with transaction.atomic():
            if tommes:
                services.frigi_arvede_plasser(Ressurs.objects.get(pk=ressurs.pk))
            ressurs.save()
    except IntegrityError:
        return json_feil(f'«{ressurs.navn}» finnes allerede på denne vaktlisten.')

    ressurs.refresh_from_db()
    return JsonResponse({'status': 'ok', 'data': _ressurs_til_dict(ressurs)})


# ── Vaktposter ───────────────────────────────────────────────────────────────

@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:vaktposter', rate='120/m', method='POST')
def vaktposter_view(request, pk):
    """Sett en person på en ressurs, med rolle og skifttider.

    Her lever den doble regelen (§4.2): badgen på personen **og**
    reservasjonen. Begge sjekkes av én funksjon i `services`.

    **Reservasjonen leses fra plassen når den har sin egen** (30. aug. 2026):
    en samleplass kan ha to plasser satt av til Haugesund og to til Karmøy.
    `services.reservert_korps()` slår de to nivåene sammen.
    """
    try:
        ressurs = Ressurs.objects.i_portal().select_related('korps').get(pk=pk)
    except Ressurs.DoesNotExist:
        return json_feil('Enhet ikke funnet', status=404)

    data = json_body(request)

    # **Ingen `mannskap_id` = ledig plass.** Det er slik planlegging faktisk
    # begynner: behovet settes opp først («Lag 1 trenger fire»), personene
    # fylles inn etter hvert. `antall` lager flere like plasser i én
    # forespørsel — fire tomme rader er fire klikk uten den.
    mannskap = None
    if data.get('mannskap_id') not in (None, ''):
        try:
            mannskap = Mannskap.objects.i_portal().select_related('korps').get(
                pk=_int(data.get('mannskap_id')))
        except Mannskap.DoesNotExist:
            return json_feil('Ukjent mannskap.')

    # **Å opprette et skift er å sette opp vakta, ikke å bemanne den**
    # (André, 15. sep. 2026). Porten sto på `kan_sette_vaktpost` — altså
    # badgen — og da kunne korps-føreren lage skift med frie tidspunkt, og
    # femti tomme plasser med `antall`, på sin egen ressurs. Å *fylle* en
    # plass er et annet spørsmål, og det stilles i `vaktpost_detalj_view`.
    if not services.kan_sette_opp_skift(request.user):
        return _nektet('Skift settes opp av den som setter opp vakten.')
    # Badgen sjekkes fortsatt på paret: den doble regelen gjelder også når
    # den som setter opp er lederen selv, og det er her den leses.
    if not services.kan_sette_vaktpost(request.user, ressurs, mannskap):
        return _nektet()

    fra_tid = _tid(data.get('fra_tid'))
    til_tid = _tid(data.get('til_tid'))
    if fra_tid is None or til_tid is None:
        return json_feil('Skiftet må ha både fra- og til-tidspunkt.')
    if til_tid <= fra_tid:
        # Et skift som slutter før det begynner ville gitt negativ
        # skiftlengde i planleggingstallene (§8b) — stopp det her, der
        # brukeren kan rette det, framfor å regne på det senere.
        return json_feil('Skiftet må slutte etter at det begynner.')

    # Flere like plasser i ett kall. Kun for ledige: to identiske rader med
    # samme person ville uansett brutt unik-skranken.
    # `or 1` ville gjort et eksplisitt `antall: 0` om til én plass i stillhet.
    # Utelatt felt betyr «én»; en oppgitt verdi tas på ordet og valideres.
    antall = _int(data['antall']) if 'antall' in data else 1
    if mannskap is not None:
        antall = 1
    if antall is None or not 1 <= antall <= 50:
        return json_feil('Antall plasser må være mellom 1 og 50.')

    # **Reservasjonen på plassen.** Oppgis den ikke, arver plassen ressursens
    # — `NULL` betyr «som ressursen», ikke «ingen». Å sette den er å dele ut,
    # og krever `skriv_full` som all annen utdeling.
    # Utdelingen er dekket av porten øverst — `korps_id` og `alle_korps` står
    # i `SKIFT_OPPSETTFELTER`, og den som kommer hit har `skriv_full`.
    korps_id = _int(data.get('korps_id')) if 'korps_id' in data else None
    # Tildelt alle korps vinner over korps_id.
    alle_korps = bool(data.get('alle_korps'))
    if alle_korps:
        korps_id = None

    felter = dict(
        ressurs=ressurs,
        mannskap=mannskap,
        korps_id=korps_id,
        rolle_id=_int(data.get('rolle_id')),
        fra_tid=fra_tid,
        til_tid=til_tid,
        merknad=(data.get('merknad') or '').strip(),
        probono=bool(data.get('probono')),
        alle_korps=alle_korps,
    )
    ukjent = _ukjent_peker(Vaktpost, korps=felter['korps_id'], rolle=felter['rolle_id'])
    if ukjent:
        return json_feil(ukjent)
    try:
        with transaction.atomic():
            lagde = [Vaktpost.objects.create(**felter) for _ in range(antall)]
    except IntegrityError:
        # Unik-skranken gjelder bare en person — en ledig plass har ingen
        # `mannskap`, og meldingen under leste `mannskap.navn` (A7).
        if mannskap is None:
            return json_feil('Plassen kunne ikke lagres.')
        return json_feil(
            f'{mannskap.navn} står allerede på «{ressurs.navn}» fra dette '
            f'tidspunktet.')

    vaktpost = (Vaktpost.objects
                .select_related('mannskap', 'mannskap__korps', 'rolle',
                                'ressurs')
                .prefetch_related('mannskap__kompetanser')
                .get(pk=lagde[0].pk))
    svar = _vaktpost_til_dict(vaktpost, services.foreldrekart())
    svar['antall_opprettet'] = len(lagde)
    return JsonResponse({'status': 'ok', 'data': svar}, status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='vaktliste:vaktpost-skriv', rate='120/m', method=['PUT', 'DELETE'])
def vaktpost_detalj_view(request, pk):
    """Rediger tider, rolle og merknad — eller fjern skiftet.

    Samme doble regel som ved opprettelsen, og lest fra raden som *finnes*:
    hadde vi lest den fra request-kroppen, kunne en korps-bruker rørt et skift
    på en annen ressurs ved å oppgi sin egen.
    """
    try:
        vaktpost = Vaktpost.objects.i_portal().select_related(
            'ressurs', 'ressurs__korps', 'mannskap', 'mannskap__korps', 'rolle'
        ).get(pk=pk)
    except Vaktpost.DoesNotExist:
        return json_feil('Vaktpost ikke funnet', status=404)

    # Inngangsporten er «får du ta i denne raden», ikke «får du opprette
    # dette paret» — en ledig plass på egen ressurs er nettopp den man skal
    # fylle. Se `services.kan_rore_vaktpost`.
    if not services.kan_rore_vaktpost(request.user, vaktpost):
        return _nektet()

    if request.method == 'DELETE':
        # **Å fjerne et skift er å fjerne et behov vaktleder satte opp** — og
        # fra 15. sep. 2026 gjelder det raden uansett om den er fylt. Sperren
        # sto bare på de ledige, med den begrunnelsen at et hull i bemanningen
        # ikke skal kunne skjules ved å slette raden som viste det. Nøyaktig
        # samme argument gjelder en fylt rad: sletter korps-føreren skiftet i
        # stedet for å melde forfall, forsvinner plassen og ikke bare personen.
        # Hun tømmer raden i stedet (`mannskap_id: null`), og da står behovet.
        if not services.kan_sette_opp_skift(request.user):
            return _nektet('Skift fjernes av den som satte dem opp.')
        vaktpost.delete()
        return JsonResponse({'status': 'ok'})

    data = json_body(request)

    # **Tidene, utdelingen, probono og merknaden er oppsett, ikke bemanning.**
    # Én port for hele lista, framfor én `if` per felt: de to som sto her
    # dekket `korps_id` og `alle_korps`, mens `fra_tid`/`til_tid` gikk rett
    # gjennom — og det var hullet André meldte. Se `services.oppsettfelter`.
    sperret = services.oppsettfelter(data, services.SKIFT_OPPSETTFELTER)
    if sperret and not services.kan_sette_opp_skift(request.user):
        return _nektet('Tider og utdeling settes av den som setter opp vakten: '
                       + ', '.join(sperret))

    # **Å fylle en ledig plass er den ene skrivingen som endrer hvem regelen
    # gjelder for.** Sjekken over gjaldt raden slik den står nå; her sjekkes
    # den på nytt mot personen som skal inn. Uten det kunne en korps-bruker
    # fylt en ledig plass på sin egen ressurs med en fra et annet korps.
    if 'mannskap_id' in data:
        ny_id = _int(data['mannskap_id'])
        ny_person = None
        if ny_id is not None:
            ny_person = (Mannskap.objects.i_portal().select_related('korps')
                         .filter(pk=ny_id).first())
            if ny_person is None:
                return json_feil('Ukjent mannskap.')
        # **Porten gjelder overgangen, ikke innsendingen** (16. sep. 2026,
        # meldt fra staging: «de med les alle / skriv eget korps kan ikke
        # skrive merknad hvis det står ledig plass»).
        #
        # Vinduet sender hele skjemaet, så `mannskap_id` står i kroppen også
        # når ingen har rørt nedtrekket. På en ledig plass betyr det `null`
        # over `null` — og `kan_sette_vaktpost(..., mannskap=None)` er
        # `skriv_full`, fordi *å la en plass stå tom* er å sette opp et behov.
        # Regelen er riktig; den fyrte bare på en endring som ikke skjedde.
        # Korps-føreren fikk 403 på å skrive «mangler sjåfør» i en plass hun
        # har lov til å fylle.
        #
        # **En skriving som ikke endrer noe, trenger ingen tillatelse til å
        # endre det.** Sammenligningen går på ID og ikke på objektet: den
        # slipper å laste `vaktpost.mannskap`, og `_int('')` gir `None`, som
        # er nøyaktig det et tomt nedtrekk sender.
        if ny_id != vaktpost.mannskap_id:
            if not services.kan_sette_vaktpost(
                    request.user, vaktpost.ressurs, ny_person, vaktpost=vaktpost):
                return _nektet()
        vaktpost.mannskap = ny_person

    var_planlagt = services.er_planlagt(vaktpost)
    if 'korps_id' in data:
        # Å endre hvem plassen er satt av til, er å dele ut på nytt. Dekket av
        # porten over — `korps_id` står i `SKIFT_OPPSETTFELTER`.
        vaktpost.korps_id = _int(data['korps_id'])
    if 'rolle_id' in data:
        vaktpost.rolle_id = _int(data['rolle_id'])
    if 'merknad' in data:
        vaktpost.merknad = (data.get('merknad') or '').strip()
    # Probono settes av alle som kan redigere raden — samme port som
    # merknaden. Det er ikke å dele ut noe; det er å si hva skiftet er.
    if 'probono' in data:
        vaktpost.probono = bool(data.get('probono'))
    if 'alle_korps' in data:
        # Å tildele alle er å dele ut — dekket av porten over.
        vaktpost.alle_korps = bool(data.get('alle_korps'))
        if vaktpost.alle_korps:
            vaktpost.korps_id = None
    # **Planlagt går én vei** (André, 12. sep. 2026): en plass som er delt
    # ut — til et korps eller til alle — kan ikke tas tilbake til kladden.
    if services.er_planlagt(vaktpost) and not var_planlagt:
        return json_feil('En plass som er delt ut kan ikke settes tilbake til planlagt.')

    fra_tid = _tid(data.get('fra_tid')) if 'fra_tid' in data else vaktpost.fra_tid
    til_tid = _tid(data.get('til_tid')) if 'til_tid' in data else vaktpost.til_tid
    if fra_tid is None or til_tid is None:
        return json_feil('Skiftet må ha både fra- og til-tidspunkt.')
    if til_tid <= fra_tid:
        return json_feil('Skiftet må slutte etter at det begynner.')
    vaktpost.fra_tid = fra_tid
    vaktpost.til_tid = til_tid

    ukjent = _ukjent_peker(Vaktpost, korps=vaktpost.korps_id, rolle=vaktpost.rolle_id)
    if ukjent:
        return json_feil(ukjent)
    try:
        with transaction.atomic():
            vaktpost.save()
    except IntegrityError:
        return json_feil('Personen står allerede på denne enheten fra dette '
                     'tidspunktet.')

    vaktpost.refresh_from_db()
    return JsonResponse(
        {'status': 'ok',
         'data': _vaktpost_til_dict(vaktpost, services.foreldrekart())})
