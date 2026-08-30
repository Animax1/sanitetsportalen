"""Vaktlistesiden og API-et — fase 2: planlegging.

Se ``docs/BESLUTNING_VAKTLISTE.md``. Tre ting å vite om denne fila:

**Fase 3 gater på nivå og objekt, ikke på admin.** `@modul_kreves(...,
'les')` slipper inn på lesing; skriving avgjøres inne i viewet, per objekt.
To terskler, og skillet mellom dem er *hva slags utsagn* nivået får avgi:

| Handling | Krav |
|---|---|
| Lese lista | `les` — hele lista, alle korps (§4.4) |
| Bemanne en ressurs | `services.kan_sette_vaktpost()` — badge **og** reservasjon |
| Dele ut ressurser, planlegge ny vakt | `services.kan_skrive_alt()` |
| Slette en vaktliste | global admin — irreversibelt |

**Reglene ligger i `services.py`**, ikke her. `kan_sette_vaktpost()` er
skrevet som én funksjon nettopp for at et endepunkt ikke skal kunne huske
badgen og glemme reservasjonen.

**Innsjekk finnes ikke ennå.** `mott_at`/`av_vakt_at` er felter på modellen,
men ingen sti setter dem før fase 4 — og da bak `skriv_full`.

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
from .models import Korps, Mannskap, Ressurs, VaktRolle, Vaktliste, Vaktpost


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
        'startet': vl.vakt.startet.isoformat() if vl.vakt.startet else None,
        'er_aktiv_vakt': vl.vakt.er_aktiv,
        'notat': vl.notat,
    }


def _ressurs_til_dict(r):
    return {
        'id': r.pk,
        'navn': r.navn,
        'type': r.type,
        'type_navn': choices.RESSURSTYPE_NAVN.get(r.type, r.type),
        'ikon': choices.RESSURSTYPE_IKON.get(r.type, 'box'),
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
    kompetanser = list(vp.mannskap.kompetanser.all())
    if foreldre is not None:
        kompetanser = services.synlige_kompetanser(kompetanser, foreldre)
    return {
        'id': vp.pk,
        'ressurs_id': vp.ressurs_id,
        'mannskap_id': vp.mannskap_id,
        'navn': vp.mannskap.navn,
        'korps_navn': vp.mannskap.korps.navn,
        'korps_kort': vp.mannskap.korps.kortnavn or vp.mannskap.korps.navn,
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
    return render(request, 'vaktliste/index.html', {
        'ressurstyper': [
            {'verdi': v, 'navn': n, 'ikon': choices.RESSURSTYPE_IKON.get(v, 'box')}
            for v, n in choices.RESSURSTYPE_VALG
        ],
        **_tilgangskontekst(request.user),
    })


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

    Å planlegge en vakt er `skriv_full`: det lager en rad i `core.Vakt`, som
    er portalens scope og ikke ett korps' bord.
    """
    if request.method == 'POST' and not services.kan_skrive_alt(request.user):
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
@require_http_methods(['GET', 'DELETE'])
def vaktliste_detalj_view(request, pk):
    """Hele oppsettet for én liste (GET), eller slett den (DELETE).

    GET er sidas hovedkall: ressurser, vaktposter og nedtrekksdataene i ett
    svar. Faner uten data er fortsatt faner, så alt hentes samlet framfor ett
    kall per ressurs.

    DELETE er **global admin**. Å slette en vaktliste river hele oppsettet og
    alle skiftene på det; det hører til samme kategori som resten av det
    irreversible i portalen, ikke til modulaksen.
    """
    if request.method == 'DELETE' and not er_global_admin(request.user):
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

    ressurser = list(vl.ressurser.select_related('korps', 'enhet'))
    poster = list(
        Vaktpost.objects
        .filter(ressurs__vaktliste=vl)
        .select_related('mannskap', 'mannskap__korps', 'rolle')
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
        'roller': [
            {'id': r.pk, 'navn': r.navn}
            for r in VaktRolle.objects.filter(er_aktiv=True)
        ],
        'mannskap': [
            {'id': m.pk, 'navn': m.navn, 'korps_id': m.korps_id,
             'korps_navn': m.korps.navn}
            for m in Mannskap.objects.filter(er_aktiv=True).select_related('korps')
        ],
        'enheter': _enheter(),
    }})


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

    Reservasjonen (`korps`) settes her, av den som **deler ut**: `skriv_full`
    eller admin. Korps-brukeren bemanner det som er reservert henne, men
    bestemmer ikke selv hva hun får — kunne hun det, ville reservasjonen ikke
    vært en tildeling.
    """
    if not services.kan_skrive_alt(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.get(pk=pk)
    except Vaktliste.DoesNotExist:
        return _feil('Vaktliste ikke funnet', status=404)

    data = _json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return _feil('Ressursen må ha et navn.')

    type_ = data.get('type') or choices.ANNET
    if type_ not in choices.RESSURSTYPE_NAVN:
        return _feil(f'Ukjent ressurstype: {type_!r}')

    try:
        with transaction.atomic():
            ressurs = Ressurs.objects.create(
                vaktliste=vl,
                navn=navn,
                type=type_,
                korps_id=_int(data.get('korps_id')),
                enhet_id=_int(data.get('enhet_id')),
                rekkefolge=(_int(data.get('rekkefolge'))
                            or services.neste_rekkefolge(vl)),
            )
    except IntegrityError:
        return _feil(f'«{navn}» finnes allerede på denne vaktlista.')

    ressurs = Ressurs.objects.select_related('korps', 'enhet').get(pk=ressurs.pk)
    return JsonResponse(
        {'status': 'ok', 'data': _ressurs_til_dict(ressurs)}, status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def ressurs_detalj_view(request, pk):
    """Rediger eller fjern en ressurs. `skriv_full`/admin — se `ressurser_view`."""
    if not services.kan_skrive_alt(request.user):
        return _nektet()

    try:
        ressurs = Ressurs.objects.select_related('korps', 'enhet').get(pk=pk)
    except Ressurs.DoesNotExist:
        return _feil('Ressurs ikke funnet', status=404)

    if request.method == 'DELETE':
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
    if 'type' in data:
        if data['type'] not in choices.RESSURSTYPE_NAVN:
            return _feil(f'Ukjent ressurstype: {data["type"]!r}')
        ressurs.type = data['type']
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
    reservasjonen på ressursen. Begge sjekkes av én funksjon i `services`.
    """
    try:
        ressurs = Ressurs.objects.select_related('korps').get(pk=pk)
    except Ressurs.DoesNotExist:
        return _feil('Ressurs ikke funnet', status=404)

    data = _json_body(request)
    try:
        mannskap = Mannskap.objects.select_related('korps').get(
            pk=_int(data.get('mannskap_id')))
    except (Mannskap.DoesNotExist, TypeError, ValueError):
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

    try:
        with transaction.atomic():
            vaktpost = Vaktpost.objects.create(
                ressurs=ressurs,
                mannskap=mannskap,
                rolle_id=_int(data.get('rolle_id')),
                fra_tid=fra_tid,
                til_tid=til_tid,
                merknad=(data.get('merknad') or '').strip(),
            )
    except IntegrityError:
        return _feil(
            f'{mannskap.navn} står allerede på «{ressurs.navn}» fra dette '
            f'tidspunktet.')

    vaktpost = (Vaktpost.objects
                .select_related('mannskap', 'mannskap__korps', 'rolle')
                .prefetch_related('mannskap__kompetanser')
                .get(pk=vaktpost.pk))
    return JsonResponse(
        {'status': 'ok',
         'data': _vaktpost_til_dict(vaktpost, services.foreldrekart())},
        status=201)


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

    if not services.kan_sette_vaktpost(
            request.user, vaktpost.ressurs, vaktpost.mannskap):
        return _nektet()

    if request.method == 'DELETE':
        vaktpost.delete()
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
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
