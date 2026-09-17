"""KO-siden og endepunktene — pulje 2: loggen.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Tersklene, som er modulens tre
nivåer:

| Handling | Krav |
|---|---|
| Se siden, lese loggen, polle | `les` |
| Skrive en linje, rette en linje | `skriv_full` |
| Fjerne innholdet i en linje (§4.4) | `skriv_leder` |

**Retting og fjerning er to navngitte stier**, ikke ett endepunkt som leser en
`slett`-verdi ut av kroppen. Samme grep som `backlog` sine `lost`/`gjenapne`:
et fritt ledd i kroppen er et sted å ta feil, og en navngitt sti kan leses i en
logg uten å slå opp hva som sto i den. Her betyr det dessuten at de to
tilgangsnivåene ligger på hver sin dekoratør, i stedet for i en `if` inne i et
delt view.

**De gjenstående flatene er tomme, og de sier det selv.** Et «Oppdrag»-kort
som bare er blankt ser ødelagt ut — særlig mens sentralbordet fortsatt står på
`/oppdrag/` og flyttes først i pulje 5. Hver tom flate bærer derfor én linje om
hva som kommer og hvor tingen bor i dag.

**Flatene er kolonner, ikke faner** (17. sep. 2026). Se `ko/CLAUDE.md`: tre av
fire trengs for å fullføre én handling, og en skjult fane er en fane du ikke vet
har endret seg.

**Loggen er scopet til aktiv vakt**, og det er ikke bare et filter: `les`
betyr «denne vakta». Tidligere vakters logg er `skriv_leder` og får sin egen
flate i pulje 3 — se `ko/module.py`.
"""
from __future__ import annotations

import json

from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, modul_kreves, nivaa_for
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt

from . import services, systemlinjer
from .models import Logglinje
from .tilstede import tilstede


# ── Hjelpere ─────────────────────────────────────────────────────────────────

def _json_body(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _feil(melding, status=400):
    return JsonResponse({'status': 'error', 'message': melding}, status=status)


def _tid(raa):
    """Et klokkeslett fra klienten, eller `None`.

    `None` betyr «bruk servertid», og det er den vanlige veien: operatøren
    trykker og linja får tida nå. En **ugyldig** streng blir også `None` og
    ikke en 400 — `services.vurder_tidspunkt` eier hva som er lov, og to
    steder som avviser tid ville før eller siden vært uenige.
    """
    return parse_datetime(raa) if isinstance(raa, str) and raa else None


def _til_dict(linje):
    """Én linje, slik klienten trenger den.

    **Teksten regnes ut på serveren for begge sorter linje.** En systemlinje
    lagres som kode + data (`ko/systemlinjer.py`) nettopp for at ordlyden skal
    kunne rettes uten at historikken skrives om — men *tegningen* hører hjemme
    her og ikke i nettleseren: gjorde klienten det, ville malen for hver
    setning ligget to steder, og utskriften av loggen fått en annen ordlyd enn
    skjermen.
    """
    er_system = linje.er_systemlinje
    return {
        'id': linje.pk,
        'rot': (linje.rot_id or linje.pk),
        'kilde': linje.kilde,
        'tidspunkt': linje.tidspunkt.isoformat(),
        'registrert_at': linje.registrert_at.isoformat(),
        'tekst': (systemlinjer.tegn(linje.systemkode, linje.systemdata)
                  if er_system else linje.tekst),
        'systemkode': linje.systemkode,
        'forfatter': linje.forfatter_navn,
        'delt_konto': linje.forfatter_delt_konto,
        'ansvarsomraade': linje.ansvarsomraade,
        'korrigerer': linje.korrigerer_id,
        'fjernet': linje.er_fjernet,
        'fjernet_av': linje.fjernet_av_navn,
        'fjernet_at': linje.fjernet_at.isoformat() if linje.fjernet_at else '',
    }


@modul_kreves('ko', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Situasjonsbildet. Fire flater og en sidebar; loggen er fylt fra pulje 2.

    Konteksten bærer nivået fordi **grensesnittet gater på
    `window.MODUL_TILGANG`, ikke på rollen** (`CLAUDE.md`): «Fjern» skal ikke
    tegnes for en som får 403 av den, og en knapp som fører til en vegg er
    verre enn ingen knapp.
    """
    return render(request, 'ko/index.html', {
        'modul_nivaa': nivaa_for(request.user, 'ko') or '',
        'er_global_admin': er_global_admin(request.user),
        'ko_maks_tekst': services.MAKS_TEKST,
    })


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:tilstede', rate='120/m', method='GET')
def tilstede_view(request):
    """Hvem har KO oppe (§5.3).

    `never_cache`: en liste over hvem som sitter der nå, servert fra en cache,
    er en liste som lyver om nøyaktig det den finnes for.

    Bremsen er satt over pollingintervallet med god margin — sida henter hvert
    30. sekund, altså to i minuttet per fane. `120/m` treffer først den som
    poller i en løkke, og det er den vi vil bremse. Gruppen oppgis eksplisitt,
    som alle andre steder: den er cache-nøkkelen, og to endepunkter skal aldri
    dele teller.
    """
    return JsonResponse({'status': 'ok', 'data': tilstede()})


# ── Loggen ───────────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:logg', rate='240/m', method='GET')
def logg_view(request):
    """Loggen for aktiv vakt. `?siden=<id>` gir bare det som er nytt.

    **Pollingen er den ene spørringen som går hele vakta**, fra hver operatør,
    hvert 15. sekund. Derfor `?siden=` og ikke en full henting: en logg på
    fire hundre linjer sendt fire ganger i minuttet til seks skjermer er en
    kostnad uten en gevinst.

    **`fjernede` sendes hver gang, og det er ikke sløsing.** Sletteinngangen
    *endrer* en rad i stedet for å legge til en ny, så den har ingen ny `id`
    og ville aldri kommet med i et `?siden=`-svar — linja ville blitt stående
    med teksten sin på hver annen operatørs skjerm til hun lastet siden på
    nytt. Lista er liten (fjerning er sjelden og logget) og idempotent:
    klienten blanker de id-ene den ikke alt har blanket.

    **WebSockets er bevisst ikke tatt i bruk** (§7.1): arbeidet her er
    påføringer, og polling skalerer fint så lenge nesten alt er nye rader.
    """
    vakt = hent_aktiv_vakt()
    qs = Logglinje.objects.gjeldende(vakt)

    siden = request.GET.get('siden')
    if siden:
        try:
            qs = qs.filter(pk__gt=int(siden))
        except (TypeError, ValueError):
            return _feil('«siden» må være et tall.')

    linjer = [_til_dict(l) for l in qs]
    fjernede = list(
        Logglinje.objects
        .filter(vakt=vakt, fjernet_at__isnull=False)
        .values_list('pk', flat=True)
    )
    return JsonResponse({
        'status': 'ok',
        'data': linjer,
        'fjernede': fjernede,
        'vakt': vakt.navn,
    })


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_skriv', rate='120/m', method='POST')
def logg_skriv_view(request):
    """Skriv en linje. Den vanlige veien inn i loggen.

    Bremsen er satt høyt med vilje: under en hendelse skriver flere operatører
    samtidig og fort, og en logg som avviser linjer fordi det går unna er en
    logg som mangler nettopp de linjene man leter etter etterpå. `120/m` per
    bruker treffer en løkke, ikke et menneske.
    """
    data = _json_body(request)
    try:
        linje = services.skriv_linje(
            hent_aktiv_vakt(),
            data.get('tekst'),
            bruker=request.user,
            tidspunkt=_tid(data.get('tidspunkt')),
            ansvarsomraade=data.get('ansvarsomraade') or '',
        )
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)}, status=201)


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_rett', rate='60/m', method='POST')
def logg_rett_view(request, pk):
    """Rett en linje — som en **ny rad som peker på den gamle** (§4.3).

    409 og ikke 400 når noen andre rakk det først: det er en konflikt om en
    tilstand, ikke en feil i det som ble sendt, og operatøren skal se at hun
    må lese den nye versjonen før hun retter videre.
    """
    linje = get_object_or_404(Logglinje, pk=pk, vakt=hent_aktiv_vakt())
    data = _json_body(request)
    try:
        ny = services.korriger(
            linje,
            bruker=request.user,
            tekst=data.get('tekst'),
            tidspunkt=_tid(data.get('tidspunkt')),
        )
    except services.AlleredeKorrigert as feil:
        return _feil(str(feil), status=409)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    except IntegrityError:
        # Unikhetskravet på `korrigerer` er sperren som holder når to
        # operatører trykker i samme sekund; sjekken i `korriger()` er for
        # feilmeldingens skyld. Uten denne grenen blir kappløpet en 500.
        return _feil('Linja er allerede rettet av noen andre.', status=409)
    return JsonResponse({'status': 'ok', 'data': _til_dict(ny)}, status=201)


@modul_kreves('ko', 'skriv_leder', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_fjern', rate='30/m', method='POST')
def logg_fjern_view(request, pk):
    """Sletteinngangen (§4.4). `skriv_leder`, og `confirm` kreves.

    **`confirm` er ikke pynt.** Operasjonen er den ene i modulen som ikke lar
    seg angre — teksten finnes etterpå bare i en backupfil ingen har en knapp
    til. Kravet ligger server-side og ikke bare som et vindu i nettleseren, av
    samme grunn som ellers i portalen: en klient som går utenom grensesnittet
    skal møte den samme døra.

    Auditraden skrives **her og ikke av et signal**, med samme begrunnelse som
    `restore_backup`: dette er en navngitt handling, ikke en feltendring, og
    «hvem fjernet en logglinje, og når» er nøyaktig det man leter etter i
    ettertid. **Teksten som ble fjernet står ikke i raden** — lå den der, ville
    den ligget i auditloggen i 730 dager, og inngangen vært et skuespill. Samme
    valg som `FELT_UTEN_VERDILOGGING` tar for `notat` i vaktlista.
    """
    if not _json_body(request).get('confirm'):
        return _feil('Bekreftelse mangler.', status=400)

    linje = get_object_or_404(Logglinje, pk=pk, vakt=hent_aktiv_vakt())
    try:
        antall = services.fjern(linje, bruker=request.user)
    except services.Ugyldig as feil:
        return _feil(str(feil))

    from audit.models import AuditLog
    from core.klientip import klient_ip
    AuditLog.objects.create(
        table_name='ko_logglinje',
        record_id=linje.pk,
        action='UPDATE',
        field_name='fjernet',
        new_value=f'{antall} rad(er) tømt',
        user=request.user if request.user.is_authenticated else None,
        ip=klient_ip(request),
    )
    return JsonResponse({'status': 'ok', 'antall': antall})
