"""Vaktlistesiden og API-et — planlegging og drift.

Se ``docs/BESLUTNING_VAKTLISTE.md``. Tre ting å vite om denne fila:

**Fase 3 gater på nivå og objekt, ikke på admin.** `@modul_kreves(...,
'les')` slipper inn på lesing; skriving avgjøres inne i viewet, per objekt.
To terskler, og skillet mellom dem er *hva slags utsagn* nivået får avgi:

| Handling | Krav |
|---|---|
| Lese lista | `les` — hele lista, alle korps (§4.4) |
| Bemanne en ressurs | `services.kan_sette_vaktpost()` — badge **og** reservasjon |
| Dele ut en ressurs, sette opp ledige plasser | `services.kan_skrive_alt()` |
| Opprette/fjerne ressurser og vaktlister, vaktas lengde, roller, grupper | `services.kan_lede()` |
| Sette i/ut av drift, stemple møtt og av vakt | `services.kan_stemple()` |
| Slette en vaktliste | global admin — irreversibelt |

**De to skrivenivåene skilles på hva en feil koster** (30. aug. 2026).
`kan_skrive_alt` bemanner: setter feil person på feil plass, og retter det
tilbake. `kan_lede` setter opp: fjerner en ressurs, og bemanningen forsvinner
med den. Derfor er «hvem som er på bilen» og «finnes bilen» to spørsmål.

**Reglene ligger i `services.py`**, ikke her. `kan_sette_vaktpost()` er
skrevet som én funksjon nettopp for at et endepunkt ikke skal kunne huske
badgen og glemme reservasjonen.

**Innsjekk kom i fase 4** (30. aug. 2026). `mott_at`/`av_vakt_at` settes av
`stempling_view`, som er ett navngitt endepunkt per overgang og ikke leser
kroppen — samme grep som oppdragsmodulens stemplinger. Reglene selv ligger som
data i `services.STEMPLINGER`.

**Innsjekk er stengt utenfor drift.** Et møtt-stempel før vakta finnes ikke, og
`drift_view` er den ene døra inn. Den er reversibel og rører ingen stempler.
Korps-føreren stempler *ikke* (avklaring 11.3) — se `services.kan_stemple`.

**Hver skriving som kan bryte en unik-skranke står i `transaction.atomic()`.**
Databasen er fasit for duplikater — en `exists()`-sjekk foran skrivingen er et
kappløp, ikke en skranke — men en `IntegrityError` som fanges *uten* et
savepoint rundt seg etterlater transaksjonen ubrukelig. Da feiler neste
spørring i samme forespørsel, typisk sesjonslagringen, og brukeren får en naken
400-side i stedet for feilmeldingen vi nettopp formulerte.
"""
from __future__ import annotations

import json

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, modul_kreves
from core.ratelimit import rate_limit

from . import choices, services
from .models import (Belastningsgrenser, Korps, Mannskap, Ressurs,
                     Ressursgruppe, Ressursrolle, Vaktliste, Vaktpost)


# ── Hjelpere ─────────────────────────────────────────────────────────────────

def _json_body(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def _feil(melding, status=400):
    return JsonResponse({'status': 'error', 'message': melding}, status=status)


def _nektet(melding='Ingen tilgang'):
    """403 med samme form som resten av API-et.

    Meldingen er generisk som standard: et svar som forteller *hvorfor* en
    ressurs er stengt, forteller også at den finnes.
    """
    return _feil(melding, status=403)


def _tilgangskontekst(user):
    """Nivået, admin-flagget og badgen — det grensesnittet trenger for å gate.

    Sendes til begge sidene i modulen. **Dette er visning, ikke håndhevelse:**
    hver av verdiene speiler en regel serveren håndhever uansett, og en klient
    som lyver om dem får fortsatt 403. Poenget er at en knapp som fører til en
    vegg er verre enn ingen knapp.

    `mitt_korps_id` er badgen, og den er *ikke* tilgang i seg selv — den lar
    bare nettleseren regne ut det samme som `kan_bemanne_ressurs()` gjør, slik
    at korps-brukeren ser «Sett på vakt» på sine egne ressurser og ikke på
    andres.
    """
    from core.auth_decorators import nivaa_for
    korps = services.brukerens_korps(user)
    return {
        'modul_nivaa': nivaa_for(user, 'vaktliste') or '',
        'er_global_admin': er_global_admin(user),
        'mitt_korps_id': korps.pk if korps else None,
    }


def _int(raa):
    """Klientverdi → int, eller ``None`` hvis den ikke er et tall.

    Tom streng er det vanlige tilfellet: et HTML-nedtrekk med «Ingen valgt»
    sender ``''``, ikke ``null``. Sendes den rett inn i et FK-filter, kaster
    Django `ValueError` og brukeren får en 500 der hun skulle fått «velg
    korps». `or None` alene dekker ikke søsteren — en ikke-numerisk streng —
    så begge fanges her, ett sted.
    """
    if raa in (None, '', False):
        return None
    try:
        return int(raa)
    except (TypeError, ValueError):
        return None


def _tid(raa):
    """ISO-streng → aware datetime, eller ``None`` hvis den ikke lar seg lese."""
    if not raa:
        return None
    verdi = parse_datetime(str(raa))
    if verdi is None:
        return None
    if timezone.is_naive(verdi):
        verdi = timezone.make_aware(verdi)
    return verdi


def _vaktliste_til_dict(vl):
    return {
        'id': vl.pk,
        'vakt_navn': vl.vakt.navn,
        'vakt_id': vl.vakt_id,
        'status': vl.status,
        'status_navn': choices.STATUS_NAVN.get(vl.status, vl.status),
        'i_drift': vl.i_drift,
        'satt_i_drift_at': (vl.satt_i_drift_at.isoformat()
                            if vl.satt_i_drift_at else None),
        'startet': vl.vakt.startet.isoformat() if vl.vakt.startet else None,
        'planlagt_slutt': (vl.planlagt_slutt.isoformat()
                           if vl.planlagt_slutt else None),
        'er_aktiv_vakt': vl.vakt.er_aktiv,
        'notat': vl.notat,
    }


def _ressurs_til_dict(r):
    return {
        'id': r.pk,
        'navn': r.navn,
        'gruppe_id': r.gruppe_id,
        'gruppe_navn': r.gruppe.navn,
        'ikon': r.gruppe.ikon,
        'korps_id': r.korps_id,
        'korps_navn': r.korps.navn if r.korps else '',
        'enhet_id': r.enhet_id,
        'enhet_navn': r.enhet.navn if r.enhet else '',
        'rekkefolge': r.rekkefolge,
    }


def _vaktpost_til_dict(vp, foreldre=None):
    """Ett skift som JSON.

    `kompetanser` er personens **synlige** kompetanser (stigen skjuler de
    impliserte, se `services.synlige_kompetanser`). De er med fordi
    ressurstabellen skal kunne vurdere sammensetningen av et lag uten å bla
    til mannskapsregisteret — det var bestillingen bak kompetansekolonnen.

    `rolle_id` følger `rolle` fordi rollen redigeres i raden: en nedtrekksliste
    trenger IDen for å vite hva som er valgt.
    """
    person = vp.mannskap
    kompetanser = list(person.kompetanser.all()) if person else []
    if foreldre is not None:
        kompetanser = services.synlige_kompetanser(kompetanser, foreldre)
    return {
        'id': vp.pk,
        'ressurs_id': vp.ressurs_id,
        'mannskap_id': vp.mannskap_id,
        # Tom person = ledig plass. Klienten trenger flagget eksplisitt
        # framfor å utlede det av et tomt navn: et tomt navn kan også bety
        # «noe gikk galt», og de to skal ikke se like ut.
        'ledig': person is None,
        'navn': person.navn if person else '',
        'korps_navn': person.korps.navn if person else '',
        'korps_kort': (person.korps.kortnavn or person.korps.navn) if person else '',
        # **Reservasjonen på plassen.** `korps_navn` over er personens korps —
        # et annet spørsmål. En ledig plass har ingen person, men kan være satt
        # av til et korps, og det er det denne bærer. `reservert_korps_id`
        # arver ressursens når plassen ikke har sin egen, slik at grensesnittet
        # viser det samme som serveren håndhever.
        'plass_korps_id': vp.korps_id,
        'reservert_korps_id': services.reservert_korps(vaktpost=vp),
        'kompetanser': [k.navn for k in kompetanser],
        'rolle_id': vp.rolle_id,
        'rolle': vp.rolle.navn if vp.rolle else '',
        'fra_tid': vp.fra_tid.isoformat(),
        'til_tid': vp.til_tid.isoformat(),
        'mott_at': vp.mott_at.isoformat() if vp.mott_at else None,
        'av_vakt_at': vp.av_vakt_at.isoformat() if vp.av_vakt_at else None,
        'avmeldt_at': vp.avmeldt_at.isoformat() if vp.avmeldt_at else None,
        'tilstede': vp.er_tilstede,
        'merknad': vp.merknad,
    }


# ── Siden ────────────────────────────────────────────────────────────────────

@modul_kreves('vaktliste', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Planleggingssiden.

    Fanene bygges av ressursene i nettleseren — de er data, ikke kode, og
    tilpasser seg vaktas art av seg selv.

    Konteksten bærer nivået og badgen fordi **grensesnittet gater på
    `window.MODUL_TILGANG`, ikke på rollen** (CLAUDE.md). Uten badgen kunne
    ikke nettleseren skille en ressurs korps-brukeren får bemanne fra en hun
    ikke får — og en «Sett på vakt»-knapp som gir 403 er verre enn ingen knapp.
    """
    return render(request, 'vaktliste/index.html',
                  _tilgangskontekst(request.user))


# ── Vaktlister ───────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='vaktliste:vaktlister', rate='60/m', method='POST')
def vaktlister_view(request):
    """Liste vaktlistene (GET), eller planlegg en ny vakt (POST).

    POST lager **både** `core.Vakt` og vaktlista, og rører ikke portalens
    aktive vakt — se `services.opprett_planlagt_vakt`. Er `kopier_fra` satt,
    kopieres ressursoppsettet fra en tidligere liste; aldri personene.

    Å planlegge en vakt er `skriv_leder`: det lager en rad i `core.Vakt`, som
    er portalens scope og ikke ett korps' bord — og en vaktliste til er ikke
    noe den som bemanner trenger for å bemanne.
    """
    if request.method == 'POST' and not services.kan_lede(request.user):
        return _nektet()

    if request.method == 'GET':
        qs = Vaktliste.objects.select_related('vakt').all()
        return JsonResponse({'status': 'ok', 'data': [
            _vaktliste_til_dict(vl) for vl in qs]})

    data = _json_body(request)
    try:
        ny = services.opprett_planlagt_vakt(
            data.get('navn'), startet=_tid(data.get('startet')))
    except ValueError as feil:
        return _feil(str(feil))

    kopiert = 0
    kopier_fra = _int(data.get('kopier_fra'))
    if kopier_fra:
        kilde = Vaktliste.objects.filter(pk=kopier_fra).first()
        if kilde is not None:
            kopiert = services.kopier_oppsett(kilde, ny)

    svar = _vaktliste_til_dict(ny)
    svar['kopierte_ressurser'] = kopiert
    return JsonResponse({'status': 'ok', 'data': svar}, status=201)


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'PUT', 'DELETE'])
def vaktliste_detalj_view(request, pk):
    """Hele oppsettet for én liste (GET), eller slett den (DELETE).

    GET er sidas hovedkall: ressurser, vaktposter og nedtrekksdataene i ett
    svar. Faner uten data er fortsatt faner, så alt hentes samlet framfor ett
    kall per ressurs.

    PUT endrer vaktas lengde — start og planlagt slutt. Det er `skriv_leder`:
    spennet gjelder hele vakta, ikke ett korps' del av den, det er grunnlaget
    bemanningskurven tegnes over, og et skift som faller utenfor et flyttet
    spenn er ikke noe bemanneren kan se komme.

    DELETE er **global admin**. Å slette en vaktliste river hele oppsettet og
    alle skiftene på det; det hører til samme kategori som resten av det
    irreversible i portalen, ikke til modulaksen.
    """
    if request.method == 'DELETE' and not er_global_admin(request.user):
        return _nektet()
    if request.method == 'PUT' and not services.kan_lede(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return _feil('Vaktliste ikke funnet', status=404)

    if request.method == 'DELETE':
        if not _json_body(request).get('confirm'):
            return _feil('Bekreftelse mangler. Send {"confirm": true}.')
        # Vakta blir stående: den kan ha pasienter og oppdrag på seg, og en
        # vaktliste er uansett bare ett av flere blikk på den.
        vl.delete()
        return JsonResponse({'status': 'ok'})

    if request.method == 'PUT':
        data = _json_body(request)
        start = (_tid(data.get('startet')) if 'startet' in data
                 else vl.vakt.startet)
        slutt = (_tid(data.get('planlagt_slutt')) if 'planlagt_slutt' in data
                 else vl.planlagt_slutt)
        if 'startet' in data and start is None:
            return _feil('Vakta må ha et starttidspunkt.')
        if start and slutt and slutt <= start:
            # Samme regel som på et skift, og av samme grunn: et negativt
            # spenn ville gitt en kurve som ikke kan tegnes.
            return _feil('Vakta må slutte etter at den begynner.')

        with transaction.atomic():
            if 'startet' in data:
                vl.vakt.startet = start
                # Året følger starten — vakta kan flyttes over et årsskifte
                # mens den planlegges, og `year` er portalens scope-nøkkel.
                vl.vakt.year = timezone.localtime(start).year
                vl.vakt.save(update_fields=['startet', 'year'])
            if 'planlagt_slutt' in data:
                vl.planlagt_slutt = slutt
                vl.save(update_fields=['planlagt_slutt'])

        vl.refresh_from_db()
        return JsonResponse({'status': 'ok', 'data': _vaktliste_til_dict(vl)})

    ressurser = list(vl.ressurser.select_related('korps', 'enhet', 'gruppe'))
    poster = list(
        Vaktpost.objects
        .filter(ressurs__vaktliste=vl)
        .select_related('mannskap', 'mannskap__korps', 'rolle', 'ressurs')
        .prefetch_related('mannskap__kompetanser')
    )
    foreldre = services.foreldrekart()
    return JsonResponse({'status': 'ok', 'data': {
        'vaktliste': _vaktliste_til_dict(vl),
        'ressurser': [_ressurs_til_dict(r) for r in ressurser],
        'vaktposter': [_vaktpost_til_dict(vp, foreldre) for vp in poster],
        'korps': [
            {'id': k.pk, 'navn': k.navn, 'kortnavn': k.kortnavn}
            for k in Korps.objects.filter(er_aktiv=True)
        ],
        # Samme form som `/api/roller/` gir — rollene administreres fra denne
        # sida nå, og manageren trenger `i_bruk`. Skrev vi formen på nytt her,
        # ville den glidd fra registerendepunktets, akkurat som `i_bruk` gjorde
        # på registersiden. Alle rollene sendes; nedtrekket filtrerer på
        # gruppa og på `er_aktiv` i nettleseren.
        'roller': [_rolle_til_dict(r)
                   for r in Ressursrolle.objects.select_related('gruppe')],
        # Gruppene: nedtrekket i «Ny ressurs», ikonet på fanen, og rekkefølgen
        # bemanningskurvene tegnes i. Alle sendes, også de inaktive — en
        # ressurs kan stå på en gruppe som er tatt ut av bruk, og fanen dens
        # skal fortsatt ha et navn.
        'grupper': [_gruppe_til_dict(g) for g in Ressursgruppe.objects.all()],
        'mannskap': [
            {'id': m.pk, 'navn': m.navn, 'korps_id': m.korps_id,
             'korps_navn': m.korps.navn}
            for m in Mannskap.objects.filter(er_aktiv=True).select_related('korps')
        ],
        'enheter': _enheter(),
    }})


def _rolle_til_dict(rolle):
    """Én rolle, i **samme form** som `/api/roller/` gir.

    Importen er lokal fordi `views_registre` importerer hjelpere herfra —
    en ring på modulnivå ellers. Samme grep som `_enheter()`.

    Grunnen til å dele formen: rollene administreres fra planleggingssiden nå,
    og manageren trenger `i_bruk`. Skrev vi formen på nytt her, ville den
    glidd fra registerendepunktets — akkurat slik `i_bruk` gjorde på
    registersiden, der fanene viste «ubrukt» på et korps som var i bruk.
    """
    from .views_registre import verdi_til_dict
    from .models import Ressursrolle as _Rolle
    return verdi_til_dict(_Rolle, rolle, gruppe=True)


def _gruppe_til_dict(g):
    """Én ressursgruppe som JSON.

    `i_bruk` er antall ressurser som står på gruppa — samme grunn som på
    rollene: en gruppe man kan slette uten å vite hvor mange ressurser som
    peker på den, sletter man for lett.
    """
    return {
        'id': g.pk,
        'navn': g.navn,
        'ikon': g.ikon,
        'rekkefolge': g.rekkefolge,
        'flere_enheter': g.flere_enheter,
        'er_aktiv': g.er_aktiv,
        'i_bruk': g.ressurser.count(),
    }


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='vaktliste:grupper', rate='60/m', method='POST')
def grupper_view(request):
    """Ressursgruppene: liste (GET) eller opprett (POST).

    **Å opprette en gruppe er `skriv_leder`.** Gruppa bestemmer hvilke roller
    en ressurs kan få og hvilken bemanningskurve den telles i; den er en del
    av oppsettet, ikke av bemanningen.

    Rekkefølgen settes automatisk til «sist», som på ressursene: den som
    legger til «Førstehjelpstelt» skal ikke måtte finne på et tall.
    """
    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'data': [
            _gruppe_til_dict(g) for g in Ressursgruppe.objects.all()]})

    if not services.kan_lede(request.user):
        return _nektet()

    data = _json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return _feil('Gruppa må ha et navn.')
    ikon = (data.get('ikon') or '').strip() or 'box'

    try:
        with transaction.atomic():
            gruppe = Ressursgruppe.objects.create(
                navn=navn, ikon=ikon,
                # Standard er en flåte. En gruppe som finnes i ett eksemplar
                # er unntaket, og skal oppgis eksplisitt.
                flere_enheter=bool(data.get('flere_enheter', True)),
                rekkefolge=(_int(data.get('rekkefolge'))
                            or services.neste_grupperekkefolge()))
    except IntegrityError:
        return _feil(f'«{navn}» finnes allerede.')

    return JsonResponse(
        {'status': 'ok', 'data': _gruppe_til_dict(gruppe)}, status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def gruppe_detalj_view(request, pk):
    """Rediger eller fjern en ressursgruppe. `skriv_leder`/admin.

    Sletting stoppes av `PROTECT` på `Ressurs.gruppe` når noen ressurs står på
    gruppa. Det er med vilje: en gruppe i bruk deaktiveres, den fjernes ikke —
    ellers ville en vaktliste mistet fanen sin fordi noen ryddet i et register.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    try:
        gruppe = Ressursgruppe.objects.get(pk=pk)
    except Ressursgruppe.DoesNotExist:
        return _feil('Ressursgruppe ikke funnet', status=404)

    if request.method == 'DELETE':
        if gruppe.ressurser.exists():
            return _feil('Gruppa er i bruk. Deaktiver den i stedet.')
        gruppe.delete()
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil('Gruppa må ha et navn.')
        gruppe.navn = navn
    if 'ikon' in data:
        gruppe.ikon = (data.get('ikon') or '').strip() or 'box'
    if 'flere_enheter' in data:
        gruppe.flere_enheter = bool(data['flere_enheter'])
    if 'er_aktiv' in data:
        gruppe.er_aktiv = bool(data['er_aktiv'])
    if 'rekkefolge' in data:
        gruppe.rekkefolge = _int(data['rekkefolge']) or 100

    try:
        with transaction.atomic():
            gruppe.save()
    except IntegrityError:
        return _feil(f'«{gruppe.navn}» finnes allerede.')

    return JsonResponse({'status': 'ok', 'data': _gruppe_til_dict(gruppe)})


def _enheter():
    """Enhetene fra oppdragsmodulen, for kobling av biler og ambulanser.

    Avhengigheten går én vei — `vaktliste` → `oppdrag` (§6) — og importen
    ligger inne i funksjonen slik at modulen kan leses uten den.
    """
    from oppdrag.models import Enhet
    return [
        {'id': e.pk, 'navn': e.navn}
        for e in Enhet.objects.filter(er_aktiv=True)
    ]


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
        vl = Vaktliste.objects.get(pk=pk)
    except Vaktliste.DoesNotExist:
        return _feil('Vaktliste ikke funnet', status=404)

    data = _json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return _feil('Ressursen må ha et navn.')

    gruppe_id = _int(data.get('gruppe_id'))
    gruppe = Ressursgruppe.objects.filter(pk=gruppe_id).first()
    if not gruppe:
        return _feil('Ressursen må høre til en gruppe.')

    # **Noen grupper finnes i ett eksemplar.** Samleplassen og KO er
    # samlingspunkt for flere korps, ikke flåter — «Samleplass 2» er ikke en
    # ny samleplass, det er en delt vaktliste ingen leser riktig. Knappen er
    # borte i grensesnittet, men en regel som bare finnes der er ingen regel:
    # nedtrekket i «Ny ressurs» og et bart POST når begge hit.
    if not gruppe.flere_enheter and Ressurs.objects.filter(
            vaktliste=vl, gruppe=gruppe).exists():
        return _feil(f'«{gruppe.navn}» finnes i ett eksemplar, og står '
                     f'allerede på denne vaktlista.')

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
        return _feil(f'«{navn}» finnes allerede på denne vaktlista.')

    ressurs = (Ressurs.objects
               .select_related('korps', 'enhet', 'gruppe').get(pk=ressurs.pk))
    return JsonResponse(
        {'status': 'ok', 'data': _ressurs_til_dict(ressurs)}, status=201)


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
    data = services.besetning(pk)
    if data is None:
        return _feil('Enheten er ikke koblet til en ressurs i denne vakta.',
                     status=404)
    return JsonResponse({'status': 'ok', 'data': data})


# ── Planleggingstall (fase 5) ────────────────────────────────────────────────

@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET'])
def belastning_view(request, pk):
    """Timer, skift og hvile per person — belastningen før vakta.

    **`les` ser tallene.** De er lista, regnet sammen: hvem som står oppført
    hvor mange timer er ikke en annen opplysning enn selve vaktlista, og en
    korps-fører som planlegger sine egne folk trenger nettopp dette for å se
    at hun er i ferd med å slite dem ut.

    **Regnestykket ligger i `services`,** ikke her — det er ikke et view som
    skal kunne svare på hva «korteste hvile» betyr.
    """
    try:
        vl = Vaktliste.objects.select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return _feil('Vaktliste ikke funnet', status=404)

    grenser = Belastningsgrenser.hent()
    rader = services.belastning_per_person(vl, grenser)
    return JsonResponse({'status': 'ok', 'data': {
        'personer': rader,
        'sammendrag': services.belastning_sammendrag(vl, rader),
        'grenser': {
            'maks_skift_timer': grenser.maks_skift_timer,
            'min_hvile_timer': grenser.min_hvile_timer,
        },
    }})


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT'])
@rate_limit(group='vaktliste:grenser', rate='30/m', method='PUT')
def grenser_view(request):
    """Sett grensene varslene måler mot. `skriv_leder`.

    **Organisasjonens regler, ikke portalens** (§8b) — derfor er de data og
    ikke tall i en `if`. Og derfor er de `skriv_leder`: å flytte grensa
    endrer hva *alle* vaktlister varsler om, og det er en beslutning om
    hvordan organisasjonen bemanner, ikke om hvem som står på bilen i kveld.

    Grensene sperrer ingenting. Settes de urimelig høyt, forsvinner varslene —
    og det er en beslutning noen har tatt, ikke en feil portalen skal hindre.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    data = _json_body(request)
    grenser = Belastningsgrenser.hent()
    for felt in ('maks_skift_timer', 'min_hvile_timer'):
        if felt not in data:
            continue
        verdi = _int(data[felt])
        if verdi is None or not 1 <= verdi <= 168:
            return _feil('Grensene oppgis i hele timer, mellom 1 og 168 '
                         '(en uke).')
        setattr(grenser, felt, verdi)
    grenser.save()

    return JsonResponse({'status': 'ok', 'data': {
        'maks_skift_timer': grenser.maks_skift_timer,
        'min_hvile_timer': grenser.min_hvile_timer,
    }})


# ── Drift (fase 4) ───────────────────────────────────────────────────────────

@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:drift', rate='30/m', method='POST')
def drift_view(request, pk, tilstand):
    """Åpne eller stenge innsjekken. Ett navngitt endepunkt per retning.

    **Drift betyr én ting: innsjekk er åpen** (§5). Ikke en livssyklus, ikke
    en låsing — lista kan fortsatt endres, for folk uteblir og bytter, og en
    liste som låser seg idet vakta starter er en liste som forlates til
    fordel for et ark.

    **Retningen står i URL-en, ikke i kroppen.** Samme grep som
    `oppdrag.views.stempling_view`: `POST .../veksle/` ville gitt et kappløp
    når to trykk kommer tett, og den som trykket sist ville ikke visst hva
    hun endte på.

    `skriv_full`, ikke `skriv_leder`: å åpne innsjekken er en driftshandling
    under vakta, ikke en del av oppsettet. Og ikke `skriv_handling` — se
    `services.kan_stemple`.

    Ut av drift er reversibel og **rører ingen stempler**. Det er en dør, ikke
    en sletting.
    """
    if tilstand not in ('start', 'stopp'):
        return _feil(f'Ukjent tilstand «{tilstand}».', status=404)
    if not services.kan_skrive_alt(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return _feil('Vaktliste ikke funnet', status=404)

    if tilstand == 'start':
        vl.status = choices.DRIFT
        # Tidspunktet settes kun ved åpning, og beholdes ved en senere
        # stenging: «i drift siden 08:04» skal fortsatt kunne leses etterpå.
        vl.satt_i_drift_at = timezone.now()
        vl.satt_i_drift_av = request.user
        vl.save(update_fields=['status', 'satt_i_drift_at', 'satt_i_drift_av',
                               'updated_at'])
    else:
        vl.status = choices.PLANLEGGING
        vl.save(update_fields=['status', 'updated_at'])

    return JsonResponse({'status': 'ok', 'data': _vaktliste_til_dict(vl)})


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:stempling', rate='120/m', method='POST')
def stempling_view(request, pk, handling):
    """Møtt, av vakt, og angring av begge. Ett endepunkt per navngitt overgang.

    **Kroppen leses ikke.** Knappen vet hvilken overgang den utfører, og
    serveren utleder ingenting av gjeldende tilstand — nøyaktig som
    `oppdrag.views.stempling_view`. Reglene selv ligger som data i
    `services.STEMPLINGER`.

    Tre porter, og de svarer på hver sin ting:

    1. **Hvem:** `services.kan_stemple` — ikke korps-føreren (avklaring 11.3).
    2. **Når:** lista må være i drift. Et møtt-stempel før vakta finnes ikke,
       og et stempel etter at innsjekken er stengt er en rad ingen har tatt
       ansvar for.
    3. **Hva:** overgangens egne forutsetninger — «av vakt» krever «møtt».

    Rekkefølgen er med vilje: en korps-fører som trykker skal få vite at hun
    ikke har lov, ikke at lista ikke er i drift.
    """
    if handling not in services.STEMPLINGER:
        return _feil(f'Ukjent stempling «{handling}».', status=404)
    if not services.kan_stemple(request.user):
        return _nektet()

    try:
        vp = (Vaktpost.objects
              .select_related('ressurs__vaktliste', 'mannskap__korps', 'rolle')
              .get(pk=pk))
    except Vaktpost.DoesNotExist:
        return _feil('Skiftet finnes ikke', status=404)

    if not vp.ressurs.vaktliste.i_drift:
        return _feil(
            'Innsjekken er stengt. Sett vaktlista i drift først — da åpnes '
            'møtt og av vakt.', status=409)

    ok, melding = services.stemple(vp, handling)
    if not ok:
        return _feil(melding)
    vp.save(update_fields=['mott_at', 'av_vakt_at', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'data': _vaktpost_til_dict(vp, services.foreldrekart()),
    })


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def ressurs_detalj_view(request, pk):
    """Rediger eller fjern en ressurs. `skriv_leder`/admin — se `ressurser_view`.

    **DELETE krever `{"confirm": true}`**, som sletting av en vaktliste. Det er
    ikke en bekreftelsesdialog flyttet til serveren — dialogen står i
    grensesnittet — men et krav om at klienten sier hva den mener. En
    slette-URL som virker på et bart kall er en URL noe annet kan treffe ved
    et uhell, og CASCADE tar alle skiftene med seg.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    try:
        ressurs = (Ressurs.objects
                   .select_related('korps', 'enhet', 'gruppe').get(pk=pk))
    except Ressurs.DoesNotExist:
        return _feil('Ressurs ikke funnet', status=404)

    if request.method == 'DELETE':
        if not _json_body(request).get('confirm'):
            return _feil('Bekreftelse mangler. Send {"confirm": true}.')
        # CASCADE tar vaktpostene. Det er riktig her: fjernes bilen fra
        # vakta, finnes ikke skiftene på den heller.
        ressurs.delete()
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil('Ressursen må ha et navn.')
        ressurs.navn = navn
    if 'gruppe_id' in data:
        gruppe_id = _int(data['gruppe_id'])
        if not gruppe_id or not Ressursgruppe.objects.filter(pk=gruppe_id).exists():
            return _feil('Ressursen må høre til en gruppe.')
        ressurs.gruppe_id = gruppe_id
    if 'korps_id' in data:
        ressurs.korps_id = _int(data['korps_id'])
    if 'enhet_id' in data:
        ressurs.enhet_id = _int(data['enhet_id'])
    if 'rekkefolge' in data:
        ressurs.rekkefolge = _int(data['rekkefolge']) or 100

    try:
        with transaction.atomic():
            ressurs.save()
    except IntegrityError:
        return _feil(f'«{ressurs.navn}» finnes allerede på denne vaktlista.')

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
        ressurs = Ressurs.objects.select_related('korps').get(pk=pk)
    except Ressurs.DoesNotExist:
        return _feil('Ressurs ikke funnet', status=404)

    data = _json_body(request)

    # **Ingen `mannskap_id` = ledig plass.** Det er slik planlegging faktisk
    # begynner: behovet settes opp først («Lag 1 trenger fire»), personene
    # fylles inn etter hvert. `antall` lager flere like plasser i én
    # forespørsel — fire tomme rader er fire klikk uten den.
    mannskap = None
    if data.get('mannskap_id') not in (None, ''):
        try:
            mannskap = Mannskap.objects.select_related('korps').get(
                pk=_int(data.get('mannskap_id')))
        except Mannskap.DoesNotExist:
            return _feil('Ukjent mannskap.')

    # Regelen står i services, som én funksjon — se modul-docstringen.
    if not services.kan_sette_vaktpost(request.user, ressurs, mannskap):
        return _nektet()

    fra_tid = _tid(data.get('fra_tid'))
    til_tid = _tid(data.get('til_tid'))
    if fra_tid is None or til_tid is None:
        return _feil('Skiftet må ha både fra- og til-tidspunkt.')
    if til_tid <= fra_tid:
        # Et skift som slutter før det begynner ville gitt negativ
        # skiftlengde i planleggingstallene (§8b) — stopp det her, der
        # brukeren kan rette det, framfor å regne på det senere.
        return _feil('Skiftet må slutte etter at det begynner.')

    # Flere like plasser i ett kall. Kun for ledige: to identiske rader med
    # samme person ville uansett brutt unik-skranken.
    # `or 1` ville gjort et eksplisitt `antall: 0` om til én plass i stillhet.
    # Utelatt felt betyr «én»; en oppgitt verdi tas på ordet og valideres.
    antall = _int(data['antall']) if 'antall' in data else 1
    if mannskap is not None:
        antall = 1
    if antall is None or not 1 <= antall <= 50:
        return _feil('Antall plasser må være mellom 1 og 50.')

    # **Reservasjonen på plassen.** Oppgis den ikke, arver plassen ressursens
    # — `NULL` betyr «som ressursen», ikke «ingen». Å sette den er å dele ut,
    # og krever `skriv_full` som all annen utdeling.
    korps_id = _int(data.get('korps_id')) if 'korps_id' in data else None
    if korps_id is not None and not services.kan_skrive_alt(request.user):
        return _nektet('Reservasjonen settes av den som deler ut.')

    felter = dict(
        ressurs=ressurs,
        mannskap=mannskap,
        korps_id=korps_id,
        rolle_id=_int(data.get('rolle_id')),
        fra_tid=fra_tid,
        til_tid=til_tid,
        merknad=(data.get('merknad') or '').strip(),
    )
    try:
        with transaction.atomic():
            lagde = [Vaktpost.objects.create(**felter) for _ in range(antall)]
    except IntegrityError:
        return _feil(
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
def vaktpost_detalj_view(request, pk):
    """Rediger tider, rolle og merknad — eller fjern skiftet.

    Samme doble regel som ved opprettelsen, og lest fra raden som *finnes*:
    hadde vi lest den fra request-kroppen, kunne en korps-bruker rørt et skift
    på en annen ressurs ved å oppgi sin egen.
    """
    try:
        vaktpost = Vaktpost.objects.select_related(
            'ressurs', 'ressurs__korps', 'mannskap', 'mannskap__korps', 'rolle'
        ).get(pk=pk)
    except Vaktpost.DoesNotExist:
        return _feil('Vaktpost ikke funnet', status=404)

    # Inngangsporten er «får du ta i denne raden», ikke «får du opprette
    # dette paret» — en ledig plass på egen ressurs er nettopp den man skal
    # fylle. Se `services.kan_rore_vaktpost`.
    if not services.kan_rore_vaktpost(request.user, vaktpost):
        return _nektet()

    if request.method == 'DELETE':
        # Å fjerne en **ledig** plass er å fjerne et behov vaktleder satte
        # opp. Korps-brukeren fyller plasser, hun avlyser dem ikke — kunne
        # hun det, ville et hull i bemanningen kunne skjules ved å slette
        # raden som viste det.
        if vaktpost.mannskap_id is None and not services.kan_skrive_alt(request.user):
            return _nektet('Ledige plasser fjernes av den som satte dem opp.')
        vaktpost.delete()
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)

    # **Å fylle en ledig plass er den ene skrivingen som endrer hvem regelen
    # gjelder for.** Sjekken over gjaldt raden slik den står nå; her sjekkes
    # den på nytt mot personen som skal inn. Uten det kunne en korps-bruker
    # fylt en ledig plass på sin egen ressurs med en fra et annet korps.
    if 'mannskap_id' in data:
        ny_id = _int(data['mannskap_id'])
        ny_person = None
        if ny_id is not None:
            ny_person = (Mannskap.objects.select_related('korps')
                         .filter(pk=ny_id).first())
            if ny_person is None:
                return _feil('Ukjent mannskap.')
        if not services.kan_sette_vaktpost(
                request.user, vaktpost.ressurs, ny_person, vaktpost=vaktpost):
            return _nektet()
        vaktpost.mannskap = ny_person

    if 'korps_id' in data:
        # Å endre hvem plassen er satt av til, er å dele ut på nytt — samme
        # terskel som å reservere hele ressursen. Kunne korps-brukeren gjøre
        # det, kunne hun tildelt seg selv en plass på samleplassen.
        if not services.kan_skrive_alt(request.user):
            return _nektet('Reservasjonen settes av den som deler ut.')
        vaktpost.korps_id = _int(data['korps_id'])
    if 'rolle_id' in data:
        vaktpost.rolle_id = _int(data['rolle_id'])
    if 'merknad' in data:
        vaktpost.merknad = (data.get('merknad') or '').strip()

    fra_tid = _tid(data.get('fra_tid')) if 'fra_tid' in data else vaktpost.fra_tid
    til_tid = _tid(data.get('til_tid')) if 'til_tid' in data else vaktpost.til_tid
    if fra_tid is None or til_tid is None:
        return _feil('Skiftet må ha både fra- og til-tidspunkt.')
    if til_tid <= fra_tid:
        return _feil('Skiftet må slutte etter at det begynner.')
    vaktpost.fra_tid = fra_tid
    vaktpost.til_tid = til_tid

    try:
        with transaction.atomic():
            vaktpost.save()
    except IntegrityError:
        return _feil('Personen står allerede på denne ressursen fra dette '
                     'tidspunktet.')

    vaktpost.refresh_from_db()
    return JsonResponse(
        {'status': 'ok',
         'data': _vaktpost_til_dict(vaktpost, services.foreldrekart())})
