"""Vaktlistesiden og API-et — planlegging og drift.

Se ``docs/BESLUTNING_VAKTLISTE.md``. Tre ting å vite om denne fila:

**Delt etter flate** (G2, 14. okt. 2026) — tilgangstabellen under gjelder alle filene:

| Fil | Flaten |
|---|---|
| `views.py` | Siden, veiledningen, vaktlistene — og hjelperne de andre bruker |
| `views_ressurser.py` | Ressursene, skiftene på dem, og besetningen `/oppdrag/` og `/ko/` leser |
| `views_grupper.py` | Ressursgruppene og rekkefølgen på rollene |
| `views_planlegger.py` | Planleggeren, «Del ut», belastningen og grensene, pausene |
| `views_drift.py` | Drift inn og ut, stemplingene, fila på e-post, service workeren |
| `views_overnatting.py` | Overnattingen |
| `views_registre.py` | Mannskap, korps, kompetanser, roller (fabrikken) |

Retningen er inn mot denne fila: den importerer ingen av de andre.

**Fase 3 gater på nivå og objekt, ikke på admin.** `@modul_kreves(...,
'les')` slipper inn på lesing; skriving avgjøres inne i viewet, per objekt.
To terskler, og skillet mellom dem er *hva slags utsagn* nivået får avgi:

| Handling | Krav |
|---|---|
| Lese lista | `les` — sitt eget korps; `les_alle` og oppover — alle. Fasit: `services.ser_alle_korps()` |
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

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import er_global_admin, modul_kreves
from core.ratelimit import rate_limit

from . import choices, fil, overnatting, pauser, services, vaktdrift
from .models import Korps, Pause, Ressursgruppe, Ressursrolle, Vaktliste, Vaktpost


# ── Hjelpere ─────────────────────────────────────────────────────────────────

#: Navnet brukeren ser når en peker ikke finnes. Nøkkelen er feltnavnet.
_PEKERNAVN = {'korps': 'korps', 'rolle': 'rolle', 'enhet': 'enhet', 'gruppe': 'gruppe'}


def _ukjent_peker(modell, **pekere):
    """Feilmeldingen for første peker som ikke finnes, ellers ``None``.

    **Slås opp før skrivingen** (26. sep. 2026, A7). Fremmednøklene er utsatt
    til commit, så en ukjent ID ble først en `IntegrityError` da
    `transaction.atomic()` lukket seg — og der sto en `except` skrevet for
    unik-skranken, som svarte «finnes allerede» om noe som ikke fantes, eller
    500 der meldingen leste `mannskap.navn` på en ledig plass. Et nedtrekk
    tegnet før noen slettet rollen, sender en slik ID.

    `None` er «ingen peker» og er lov. Målmodellen leses av feltet, så
    vaktlista trenger ikke importere `oppdrag` for å sjekke en enhet.
    """
    for felt, pk in pekere.items():
        if pk is None:
            continue
        mal = modell._meta.get_field(felt).related_model
        if not mal.objects.filter(pk=pk).exists():
            return f'Ukjent {_PEKERNAVN.get(felt, felt)}.'
    return None


def _nektet(melding='Ingen tilgang'):
    """403 med samme form som resten av API-et.

    Meldingen er generisk som standard: et svar som forteller *hvorfor* en
    ressurs er stengt, forteller også at den finnes.
    """
    return json_feil(melding, status=403)


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
        # Korpsfilteret (11. sep. 2026): sida sier fra når den viser bare
        # ett korps, og når den viser ingenting fordi kontoen mangler badge.
        # En tom liste uten forklaring ser ut som en vakt ingen har satt opp.
        'ser_alle_korps': services.ser_alle_korps(user),
        'mitt_korps_navn': korps.navn if korps else '',
        # Korps-føreren ser alle korps, men fører bare sitt eget — og uten
        # badge fører hun ingen. Da må sida si det (André, 13. sep. 2026:
        # «nå kan jeg ikke redigere noen av mine mannskaper»). Admin og
        # `skriv_full`+ står utenfor badgen.
        'mangler_badge': (korps is None and not services.kan_skrive_alt(user)
                          and nivaa_for(user, 'vaktliste') == 'skriv_handling'),
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


def _vaktliste_til_dict(vl, user):
    """`user` avgjør om feilteksten fra siste utsending sendes (B7). Påkrevd,
    ikke valgfri: et nytt endepunkt skal ikke kunne glemme den."""
    vis_feil = services.kan_skrive_alt(user)
    autodrift = vaktdrift.autodrift_tidspunkt(vl)
    return {
        'id': vl.pk,
        'vakt_navn': vl.vakt.navn,
        'vakt_id': vl.vakt_id,
        'status': vl.status,
        'status_navn': choices.STATUS_NAVN.get(vl.status, vl.status),
        'i_drift': vl.i_drift,
        'satt_i_drift_at': (vl.satt_i_drift_at.isoformat()
                            if vl.satt_i_drift_at else None),
        'drift_automatisk': vl.drift_automatisk,
        # Når klokka vil sette lista i drift — for teksten ved knappen.
        'autodrift_at': autodrift.isoformat() if autodrift else None,
        'startet': vl.vakt.startet.isoformat() if vl.vakt.startet else None,
        'planlagt_slutt': (vl.planlagt_slutt.isoformat()
                           if vl.planlagt_slutt else None),
        'timetak': vl.timetak,
        'er_aktiv_vakt': vl.vakt.er_aktiv,
        'notat': vl.notat,
        'arkivert_at': vl.arkivert_at.isoformat() if vl.arkivert_at else None,
        # Reserven (12. sep. 2026): siste utsending av vaktlista som fil, og
        # om det finnes mottakere å sende til — knappen skal si det før man
        # trykker, ikke etter.
        'siste_utsending': fil.utsending_til_dict(vl.utsendinger.first(), vis_feil=vis_feil),
        'fil_mottakere': len(fil.mottakere()),
        'fil_ved_drift': fil.sendes_ved_drift(),
        'fil_intervall_min': fil.intervall_minutter(),
        'fil_bare_endret': fil.bare_ved_endring(),
        # Står pausene på utskriften? Admin kan skjule dem der (André, 23.
        # sep. 2026); på skjermen står de uansett for den som planlegger.
        'pauser_paa_utskrift': pauser.vises_for_mannskapet(),
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
        # Planleggerens pauseregel, så oppsettet kan leses tilbake.
        'pause_etter_min': r.pause_etter_min,
        'pause_min': r.pause_min,
        'pause_forskyv': r.pause_forskyv,
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
        # Personens korps som ID, for korpsvelgeren (11. sep. 2026): den
        # filtrerer i nettleseren med samme regel som serveren bruker for
        # korps-brukeren, og en regel på navn ville brutt ved omdøping.
        'korps_id': person.korps_id if person else None,
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
        'probono': vp.probono,
        'alle_korps': vp.alle_korps,
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


def _veiledningsrolle(user):
    """Hvilken del av veiledningen som er brukerens. Visning, ikke tilgang."""
    from core.auth_decorators import nivaa_for
    if er_global_admin(user):
        return 'admin'
    return {'skriv_leder': 'leder', 'skriv_full': 'vaktleder',
            'skriv_handling': 'korpsforer'}.get(nivaa_for(user, 'vaktliste'), 'leser')


@modul_kreves('vaktliste', 'les')
@require_http_methods(['GET'])
def veiledning_view(request):
    """Brukerveiledningen (pulje 5, 1. okt. 2026). Én side for alle roller, med
    brukerens egen del pekt ut — en korps-fører skal kunne se hva vaktlederen
    gjør, men begynne med sitt eget."""
    return render(request, 'vaktliste/veiledning.html',
                  {'din_rolle': _veiledningsrolle(request.user)})


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
        # Klokka først, så «— i drift» i velgeren stemmer fra første lasting
        # etter start (30. sep. 2026, `vaktdrift.sett_forfalte_i_drift`).
        vaktdrift.sett_forfalte_i_drift()
        # Arkiverte lister er ute av velgeren. `?arkiverte=1` gir dem, og
        # bare til global admin — det er hun som henter tilbake.
        if request.GET.get('arkiverte'):
            if not er_global_admin(request.user):
                return _nektet()
            qs = (Vaktliste.objects.select_related('vakt')
                  .filter(arkivert_at__isnull=False).order_by('-arkivert_at'))
        else:
            qs = Vaktliste.objects.select_related('vakt').filter(arkivert_at__isnull=True)
        return JsonResponse({'status': 'ok', 'data': [
            _vaktliste_til_dict(vl, request.user) for vl in qs]})

    data = json_body(request)
    # **Vakta og kopien i én transaksjon** (26. sep. 2026). Kopieringen sto
    # etter, og feilet den, ble en tom vaktliste stående — med navnet tatt,
    # så et nytt forsøk fikk «finnes allerede».
    try:
        with transaction.atomic():
            ny = services.opprett_planlagt_vakt(
                data.get('navn'),
                startet=_tid(data.get('startet')),
                planlagt_slutt=_tid(data.get('planlagt_slutt')))
            kopiert = 0
            kopier_fra = _int(data.get('kopier_fra'))
            if kopier_fra:
                kilde = Vaktliste.objects.i_portal().filter(pk=kopier_fra).first()
                if kilde is not None:
                    kopiert = services.kopier_oppsett(kilde, ny)
    except ValueError as feil:
        return json_feil(str(feil))

    svar = _vaktliste_til_dict(ny, request.user)
    svar['kopierte_ressurser'] = kopiert
    return JsonResponse({'status': 'ok', 'data': svar}, status=201)


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:arkiver', rate='30/m', method='POST')
def vaktliste_arkiver_view(request, pk, retning):
    """Arkiver (`arkiver`) eller hent tilbake (`gjenopprett`) en vaktliste.

    Global admin, som sletting — det er den samme handlingen sett fra
    velgeren, bare reversibel. Retningen står i URL-en, ikke i kroppen,
    av samme grunn som driftporten: et veksle-endepunkt gir et kappløp.
    """
    if not er_global_admin(request.user):
        return _nektet()
    if retning not in ('arkiver', 'gjenopprett'):
        return json_feil('Ukjent retning.', status=404)
    try:
        vl = Vaktliste.objects.i_portal().select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)
    if retning == 'arkiver':
        # **En liste i drift arkiveres ikke** (26. sep. 2026, A6). Den ville
        # forsvunnet fra velgeren og fortsatt styrt sentralbordet, KO og
        # e-postutsendingen. Ta den ut av drift først — det er en dør, ikke en
        # sletting, og rører ingen stempler.
        if vl.i_drift:
            return json_feil('Listen står i drift. Ta den ut av drift før den arkiveres.',
                         status=409)
        if vl.arkivert_at is None:
            vl.arkivert_at = timezone.now()
            vl.save(update_fields=['arkivert_at', 'updated_at'])
    else:
        vl.arkivert_at = None
        vl.save(update_fields=['arkivert_at', 'updated_at'])
    return JsonResponse({'status': 'ok', 'data': _vaktliste_til_dict(vl, request.user)})


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'PUT', 'DELETE'])
@rate_limit(group='vaktliste:vaktliste-skriv', rate='60/m', method=['PUT', 'DELETE'])
def vaktliste_detalj_view(request, pk):
    """Hele oppsettet for én liste (GET), eller slett den (DELETE).

    GET er sidas hovedkall: ressurser, vaktposter og nedtrekksdataene i ett
    svar. Faner uten data er fortsatt faner, så alt hentes samlet framfor ett
    kall per ressurs.

    PUT endrer vaktas rammer — start, planlagt slutt og timetaket. Det er
    `skriv_leder`: de gjelder hele vakta, ikke ett korps' del av den, spennet
    er grunnlaget bemanningskurven tegnes over, og et skift som faller
    utenfor et flyttet spenn er ikke noe bemanneren kan se komme.

    **Timetaket er `skriv_leder` av samme grunn**, ikke `skriv_full` som
    planleggernotatets §4 først skisserte (15. sep. 2026). Det er et tall
    *alle* varsler på lista måles mot, det hører til samme feltfamilie som
    spennet, og det settes i samme PUT — én forespørsel med to ulike
    tilgangsnivåer inni er en regel ingen klarer å lese riktig. Samme
    plassering som `Belastningsgrenser`, som også er `skriv_leder`;
    forskjellen mellom dem er rekkevidden, ikke hvem som bestemmer.

    DELETE er **global admin**. Å slette en vaktliste river hele oppsettet og
    alle skiftene på det; det hører til samme kategori som resten av det
    irreversible i portalen, ikke til modulaksen.
    """
    if request.method == 'DELETE' and not er_global_admin(request.user):
        return _nektet()
    if request.method == 'PUT' and not services.kan_lede(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.i_portal().select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)

    # **Klokka går også her**, ikke bare i middlewaren (30. sep. 2026): den
    # sjekker høyst hvert minutt, og innsjekken skal være åpen i det første
    # trykket etter start.
    if request.method == 'GET' and vaktdrift.sett_i_drift_ved_start(vl):
        vl.refresh_from_db()

    if request.method == 'DELETE':
        if not json_body(request).get('confirm'):
            return json_feil('Bekreftelse mangler. Send {"confirm": true}.')
        # Vakta blir stående: den kan ha pasienter og oppdrag på seg, og en
        # vaktliste er uansett bare ett av flere blikk på den.
        vl.delete()
        return JsonResponse({'status': 'ok'})

    if request.method == 'PUT':
        data = json_body(request)
        start = (_tid(data.get('startet')) if 'startet' in data
                 else vl.vakt.startet)
        slutt = (_tid(data.get('planlagt_slutt')) if 'planlagt_slutt' in data
                 else vl.planlagt_slutt)
        if 'startet' in data and start is None:
            return json_feil('Vakten må ha et starttidspunkt.')
        if start and slutt and slutt <= start:
            # Samme regel som på et skift, og av samme grunn: et negativt
            # spenn ville gitt en kurve som ikke kan tegnes.
            return json_feil('Vakten må slutte etter at den begynner.')

        # **Tomt felt betyr «ingen tak», ikke null.** Et nedtrekk eller et
        # tallfelt som tømmes sender `''` eller `null`, og begge skal fjerne
        # taket. Null timer ville derimot vært et budsjett som er brukt opp
        # før noen er satt opp, og lista hadde stått gul fra første skift.
        timetak = vl.timetak
        if 'timetak' in data:
            raa = data.get('timetak')
            if raa in (None, ''):
                timetak = None
            else:
                try:
                    timetak = int(raa)
                except (TypeError, ValueError):
                    return json_feil('Timetaket må være et helt antall timer.')
                if timetak < 0:
                    return json_feil('Timetaket kan ikke være negativt.')

        # Brannrutinen (25. sep. 2026) står øverst på brannlista. Lederens,
        # som resten av det som gjelder hele vakta.
        if 'brannrutine' in data:
            brannrutine = str(data.get('brannrutine') or '').strip()
            if len(brannrutine) > overnatting.MAKS_BRANNRUTINE:
                return json_feil(f'Brannrutinen kan være høyst '
                             f'{overnatting.MAKS_BRANNRUTINE} tegn.')

        with transaction.atomic():
            if 'startet' in data:
                vl.vakt.startet = start
                # Året følger starten — vakta kan flyttes over et årsskifte
                # mens den planlegges, og `year` er portalens scope-nøkkel.
                vl.vakt.year = timezone.localtime(start).year
                vl.vakt.save(update_fields=['startet', 'year'])
            felter = []
            if 'planlagt_slutt' in data:
                vl.planlagt_slutt = slutt
                felter.append('planlagt_slutt')
            if 'timetak' in data:
                vl.timetak = timetak
                felter.append('timetak')
            if 'brannrutine' in data:
                vl.brannrutine = brannrutine
                felter.append('brannrutine')
            if felter:
                vl.save(update_fields=felter)

        vl.refresh_from_db()
        return JsonResponse({'status': 'ok', 'data': _vaktliste_til_dict(vl, request.user)})

    ressurser = list(vl.ressurser.select_related('korps', 'enhet', 'gruppe'))
    # **Skiftene filtreres her, i svaret sida bygges av.** Da gjelder
    # korpsfilteret alle fanene på én gang — oversikt, ressursfaner,
    # tilstede og kurver — i stedet for i hver bygger i nettleseren.
    # Ressursene er infrastruktur og sendes alle: en bil reservert et
    # annet korps står der med tom tabell, og merkelappen sier hvorfor.
    poster = list(services.synlige_vaktposter(
        Vaktpost.objects
        .filter(ressurs__vaktliste=vl)
        .select_related('mannskap', 'mannskap__korps', 'rolle', 'ressurs')
        .prefetch_related('mannskap__kompetanser'),
        request.user,
    ))
    foreldre = services.foreldrekart()
    return JsonResponse({'status': 'ok', 'data': {
        'vaktliste': _vaktliste_til_dict(vl, request.user),
        'ressurser': [_ressurs_til_dict(r) for r in ressurser],
        'vaktposter': [_vaktpost_til_dict(vp, foreldre) for vp in poster],
        # **Pausene sendes alle, uten korpsfilter** — de hører til ressursen,
        # og ressursene er infrastruktur som sendes alle.
        'pauser': [pauser.til_dict(p) for p in
                   Pause.objects.filter(ressurs__vaktliste=vl).order_by('fra', 'id')],
        # **Overnattingen sendes alle, uten korpsfilter** (André, 25. sep.
        # 2026): brannlista er hele lista, ellers stemmer ikke opptellingen.
        # Telefonen følger korpsfilteret — se `overnatting.vis_telefon`. Står
        # i hovedsvaret så den følger med i offline-kopien.
        'overnatting': overnatting.data_for(vl, request.user),
        'korps': [
            {'id': k.pk, 'navn': k.navn, 'kortnavn': k.kortnavn}
            for k in services.korps_i_portal().filter(er_aktiv=True)
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
        # **Nedtrekkene tilbyr bare dem brukeren får sette inn** (André,
        # 12. sep. 2026: «kan bytte til hvem som helst mannskap uavhengig av
        # korps» — serveren avviste det, men lista lot som). Korps-føreren
        # får eget korps; den som skriver alt får alle.
        'mannskap': [
            {'id': m.pk, 'navn': m.navn, 'korps_id': m.korps_id,
             'korps_navn': m.korps.navn}
            for m in services.mannskap_brukeren_kan_sette(request.user)
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
        'registrerer_i_park': g.registrerer_i_park,
        'i_bruk': g.ressurser.count(),
    }


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
