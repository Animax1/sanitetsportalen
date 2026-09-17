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

from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves, nivaa_for
from core.jsdata import js_json
from core.ratelimit import rate_limit

from . import services
from . import varsler
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


def _int(verdi):
    """ID fra klienten. Et nedtrekk med «Ingen valgt» sender `''`, ikke `null`,
    og den strengen i et FK-filter gir `ValueError` — altså 500 der brukeren
    skulle fått «velg en type». Samme grep som `vaktliste.views._int()`."""
    try:
        return int(verdi)
    except (TypeError, ValueError):
        return None


def _hent_aktiv_type(verdi):
    """Typen, hvis den finnes **og** er aktiv. `None` ellers.

    En deaktivert type kan ikke velges på et nytt innspill — det er hele
    poenget med `er_aktiv`. Den blir stående på dem som alt har den, så lista
    beholder meningen sin.
    """
    pk = _int(verdi)
    if pk is None:
        return None
    return Innspilltype.objects.filter(pk=pk, er_aktiv=True).first()


def _til_dict(innspill, bruker, naa):
    """Én rad, med `kan_endres` regnet ut på **serveren**.

    Klienten skal ikke regne fristen selv: en klokke som står feil ville gitt
    en knapp som fører til 403, og en som står andre veien ville skjult en
    knapp brukeren har lov til å trykke på. Serveren eier tida.
    """
    return {
        'id': innspill.pk,
        'type': innspill.type_id,
        'type_navn': innspill.type.navn,
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


def _typeliste(bare_aktive=False):
    """Typene, som klienten trenger dem. `i_bruk` er antallet innspill, og det
    er tallet 409-svaret ved sletting peker på."""
    qs = Innspilltype.objects.all()
    if bare_aktive:
        qs = qs.filter(er_aktiv=True)
    return [{'id': t.pk, 'navn': t.navn, 'er_aktiv': t.er_aktiv,
             'rekkefolge': t.rekkefolge, 'i_bruk': t.innspill.count()}
            for t in qs]


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
        'typer_json': js_json(_typeliste()),
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

    qs = Innspill.objects.select_related('type', 'opprettet_av', 'lost_av')

    type_ = request.GET.get('type')
    if type_:
        type_id = _int(type_)
        if type_id is None or not Innspilltype.objects.filter(pk=type_id).exists():
            return _feil(f'Ukjent type: {type_}')
        qs = qs.filter(type_id=type_id)

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

    type_ = _hent_aktiv_type(data.get('type'))
    if type_ is None:
        return _feil('Velg en type')

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
    # **Varselet er en sideeffekt, ikke en del av innmeldingen.** `meld_nytt_innspill`
    # kaster aldri — et innspill skal ikke gå tapt fordi bjella feilet.
    varsler.meld_nytt_innspill(innspill)
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
        type_ = _hent_aktiv_type(data.get('type'))
        if type_ is None:
            return _feil('Velg en type')
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


# ── Backloginnstillinger: typene ─────────────────────────────────────────────
#
# Samme mønster som oppdragsmodulens verdimengder (`oppdrag/views_verdier.py`):
# lista for `les`, opprett og endre for `skriv_leder`, sletting for global admin
# med `{"confirm": true}` — og **`PROTECT` → 409 med rådet om å deaktivere**.
#
# Rådet er det som gjør sperren nyttig. «Kan ikke slettes» alene etterlater
# brukeren uten en vei videre, og da er neste trekk å slette innspillene i
# stedet — altså å miste det sperren fantes for å verne.

@never_cache
@modul_kreves('backlog', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='backlog:typer', rate='30/m', method='POST')
def typer_view(request):
    """GET: alle typene. POST: ny type."""
    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'data': _typeliste()})

    if not har_tilgang(request.user, 'backlog', 'skriv_leder'):
        return _nektet()

    navn = (_json_body(request).get('navn') or '').strip()
    if not navn:
        return _feil('Navn må fylles ut')
    if Innspilltype.objects.filter(navn__iexact=navn).exists():
        # `iexact`: «Bug» og «bug» er samme type for et menneske, og to rader
        # som ser like ut i et nedtrekk er verre enn en feilmelding.
        return _feil(f'«{navn}» finnes allerede')

    type_ = Innspilltype.objects.create(navn=navn[:40])
    return JsonResponse({'status': 'ok', 'data': {
        'id': type_.pk, 'navn': type_.navn, 'er_aktiv': type_.er_aktiv,
        'rekkefolge': type_.rekkefolge, 'i_bruk': 0}}, status=201)


@never_cache
@modul_kreves('backlog', 'skriv_leder', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def type_detalj_view(request, pk):
    """PUT: navn og `er_aktiv`. DELETE: bare når ingen bruker typen.

    **Slettingen krever global admin og `confirm`.** To sperrer, og de stopper
    hver sin ting: nivået stopper den som ikke skal slette noe, `confirm`
    stopper et kall som treffer URL-en uten å mene det. De er ikke samme sperre.
    """
    type_ = Innspilltype.objects.filter(pk=pk).first()
    if type_ is None:
        return _feil('Typen finnes ikke', status=404)

    if request.method == 'DELETE':
        if not er_global_admin(request.user):
            return _nektet()
        if not _json_body(request).get('confirm'):
            return _feil('Sletting må bekreftes')
        try:
            type_.delete()
        except ProtectedError:
            brukt = type_.innspill.count()
            return JsonResponse({'status': 'error', 'message': (
                f'«{type_.navn}» er i bruk på {brukt} innspill og kan ikke '
                f'slettes. Deaktiver den i stedet — da forsvinner den fra '
                f'nedtrekket, men blir stående på dem som alt har den.'
            )}, status=409)
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil('Navn må fylles ut')
        if Innspilltype.objects.filter(navn__iexact=navn).exclude(pk=pk).exists():
            return _feil(f'«{navn}» finnes allerede')
        type_.navn = navn[:40]
    if 'er_aktiv' in data:
        type_.er_aktiv = bool(data.get('er_aktiv'))
    type_.save()
    return JsonResponse({'status': 'ok', 'data': {
        'id': type_.pk, 'navn': type_.navn, 'er_aktiv': type_.er_aktiv,
        'rekkefolge': type_.rekkefolge, 'i_bruk': type_.innspill.count()}})
