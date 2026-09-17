"""Backlog-siden og API-et.

Se `backlog/CLAUDE.md`. Tre terskler, og de er modulens tre nivåer:

| Handling | Krav |
|---|---|
| Se lista og filtrene | `les` |
| Melde inn | `skriv_full` |
| Rette/slette sitt eget | `skriv_full` **og** `services.kan_endres()` |
| Sette løst / gjenåpne | `skriv_leder` |

**Løst og gjenåpnet er to navngitte stier**, ikke ett endepunkt som leser en
`lost`-verdi ut av kroppen. Samme grep som vaktlistas `arkiver`/`gjenopprett`:
et fritt ledd i kroppen er et sted å ta feil, og en navngitt sti kan leses i en
logg uten å slå opp hva som sto i den.
"""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves, nivaa_for
from core.jsdata import js_json
from core.ratelimit import rate_limit

from . import services
from .models import Innspill, Innspilltype


# ── Hjelpere ─────────────────────────────────────────────────────────────────

def _json_body(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _feil(melding, status=400):
    return JsonResponse({'status': 'error', 'message': melding}, status=status)


def _nektet():
    return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)


def _til_dict(innspill, bruker, naa):
    """Én rad, med `kan_endres` regnet ut på **serveren**.

    Klienten skal ikke regne fristen selv: en klokke som står feil ville gitt
    en knapp som fører til 403, og en som står andre veien ville skjult en
    knapp brukeren har lov til å trykke på. Serveren eier tida.
    """
    return {
        'id': innspill.pk,
        'type': innspill.type,
        'type_navn': innspill.get_type_display(),
        'tittel': innspill.tittel,
        'beskrivelse': innspill.beskrivelse,
        'modul_slug': innspill.modul_slug,
        'opprettet_av': innspill.opprettet_av_navn,
        'opprettet_at': innspill.opprettet_at.isoformat() if innspill.opprettet_at else '',
        'lost': innspill.lost,
        'lost_av': innspill.lost_av_navn,
        'lost_at': innspill.lost_at.isoformat() if innspill.lost_at else '',
        'kan_endres': services.kan_endres(innspill, bruker, naa),
    }


# ── Siden ────────────────────────────────────────────────────────────────────

@modul_kreves('backlog', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Backlog-siden.

    Konteksten bærer nivået fordi **grensesnittet gater på
    `window.MODUL_TILGANG`, ikke på rollen** (`CLAUDE.md`) — «Sett løst» skal
    ikke stå der for den som får 403 på den.

    Modulvalgene går gjennom `js_json()` og aldri `json.dumps` + `|safe`:
    modulnavnene er ikke brukerdata i dag, men regelen er at data inn i et
    `<script>` går den veien, og et unntak «fordi akkurat denne er trygg» er
    hvordan den neste blir det ikke.
    """
    return render(request, 'backlog/index.html', {
        'modul_nivaa': nivaa_for(request.user, 'backlog') or '',
        'er_global_admin': er_global_admin(request.user),
        'moduler_json': js_json(
            [{'slug': s, 'navn': n} for s, n in services.valgbare_moduler()]),
        'typer_json': js_json(
            [{'verdi': v, 'navn': n} for v, n in Innspilltype.choices]),
    })


# ── Lista og innmelding ──────────────────────────────────────────────────────

@never_cache
@modul_kreves('backlog', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='backlog:innspill', rate='30/m', method='POST')
def innspill_view(request):
    """GET: lista, filtrert. POST: nytt innspill.

    **Filteret er serverens.** `?type=bug&lost=0&modul=vaktliste` — og et ukjent
    filternavn ignoreres i stedet for å gi 400: en lenke fra en gammel fane skal
    vise lista, ikke en feilmelding.

    **Men et *ugyldig* filter på et kjent felt tier ikke.** `?lost=kanskje`
    ville ellers vist alt, og den som filtrerte ville lest det som at det ikke
    finnes noen uløste. Et filter som stille viser feil mengde er verre enn
    ingen filter — samme grunn som at et filter aldri skal skjule noe stille.
    """
    if request.method == 'POST':
        return _opprett(request)

    qs = Innspill.objects.select_related('opprettet_av', 'lost_av')

    type_ = request.GET.get('type')
    if type_:
        if type_ not in Innspilltype.values:
            return _feil(f'Ukjent type: {type_}')
        qs = qs.filter(type=type_)

    lost = request.GET.get('lost')
    if lost is not None and lost != '':
        if lost not in ('0', '1'):
            return _feil('Filteret «lost» må være 0 eller 1')
        qs = qs.filter(lost=(lost == '1'))

    modul = request.GET.get('modul')
    if modul:
        if not services.gyldig_modul_slug(modul):
            return _feil(f'Ukjent modul: {modul}')
        qs = qs.filter(modul_slug=modul)

    naa = timezone.now()
    rader = [_til_dict(i, request.user, naa) for i in qs]
    return JsonResponse({'status': 'ok', 'data': rader, 'antall': len(rader)})


def _opprett(request):
    if not har_tilgang(request.user, 'backlog', 'skriv_full'):
        return _nektet()

    data = _json_body(request)
    tittel = (data.get('tittel') or '').strip()
    if not tittel:
        return _feil('Tittel må fylles ut')

    type_ = (data.get('type') or '').strip()
    if type_ not in Innspilltype.values:
        return _feil('Velg om det er en bug eller et ønske')

    modul_slug = (data.get('modul_slug') or '').strip()
    if not services.gyldig_modul_slug(modul_slug):
        return _feil(f'Ukjent modul: {modul_slug}')

    innspill = Innspill.objects.create(
        type=type_,
        tittel=tittel[:200],
        beskrivelse=(data.get('beskrivelse') or '').strip(),
        modul_slug=modul_slug,
        opprettet_av=request.user,
        opprettet_av_navn=request.user.username,
    )
    return JsonResponse(
        {'status': 'ok', 'data': _til_dict(innspill, request.user, timezone.now())},
        status=201)


# ── Ett innspill ─────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('backlog', 'skriv_full', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def innspill_detalj_view(request, pk):
    """Rett eller slett sitt eget, innen fristen.

    Gaten er `services.kan_endres()` og ikke en `if` her, fordi den bærer tre
    vilkår som må sjekkes samlet — forfatteren, fristen og at saken ikke er
    løst. Et endepunkt som husket to av dem ville sett ut som om det virket.

    **403 og ikke 404 når fristen er ute.** Raden finnes, og brukeren ser den i
    lista; et 404 ville sagt at den var borte.
    """
    innspill = Innspill.objects.filter(pk=pk).first()
    if innspill is None:
        return _feil('Innspillet finnes ikke', status=404)
    if not services.kan_endres(innspill, request.user):
        return _nektet()

    if request.method == 'DELETE':
        innspill.delete()
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
    if 'tittel' in data:
        tittel = (data.get('tittel') or '').strip()
        if not tittel:
            return _feil('Tittel må fylles ut')
        innspill.tittel = tittel[:200]
    if 'beskrivelse' in data:
        innspill.beskrivelse = (data.get('beskrivelse') or '').strip()
    if 'type' in data:
        type_ = (data.get('type') or '').strip()
        if type_ not in Innspilltype.values:
            return _feil('Velg om det er en bug eller et ønske')
        innspill.type = type_
    if 'modul_slug' in data:
        modul_slug = (data.get('modul_slug') or '').strip()
        if not services.gyldig_modul_slug(modul_slug):
            return _feil(f'Ukjent modul: {modul_slug}')
        innspill.modul_slug = modul_slug

    innspill.save()
    return JsonResponse(
        {'status': 'ok', 'data': _til_dict(innspill, request.user, timezone.now())})


@never_cache
@modul_kreves('backlog', 'skriv_leder', svar='json')
@require_http_methods(['POST'])
def lost_view(request, pk, *, lost):
    """Sett løst, eller gjenåpne. To navngitte stier, én funksjon.

    **`lost` kommer fra URL-en, ikke fra kroppen** — se `urls.py`. Den som
    leser en logg skal kunne se hva som skjedde uten å slå opp kroppen, og et
    fritt ledd er et sted å ta feil.

    Hvem som løste fryses på raden, som ved innmelding: `lost_av_navn` er det
    som står igjen når kontoen en dag er borte.
    """
    innspill = Innspill.objects.filter(pk=pk).first()
    if innspill is None:
        return _feil('Innspillet finnes ikke', status=404)

    innspill.lost = lost
    if lost:
        innspill.lost_av = request.user
        innspill.lost_av_navn = request.user.username
        innspill.lost_at = timezone.now()
    else:
        # **Gjenåpning tømmer sporet med vilje.** Et `lost_av` som ble stående
        # på en åpen sak ville lest som «denne er løst av Kari» ved siden av et
        # merke som sier at den ikke er det.
        innspill.lost_av = None
        innspill.lost_av_navn = ''
        innspill.lost_at = None
    innspill.save()
    return JsonResponse(
        {'status': 'ok', 'data': _til_dict(innspill, request.user, timezone.now())})
