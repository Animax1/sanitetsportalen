"""Statistikk-endepunktene og statistikksiden.

Skilt ut fra pasientmodulen august 2026. Bakgrunnen står i CHANGELOG:
statistikk skulle uansett bli sin egen modul, og rollemodellen kunne ikke
utformes før den var det — så lenge «ser statistikk» og «kan skrive» var to
akser i samme modul, trengte tilgangsnivået fire trinn i stedet for tre.

**Appen kjenner ingen kildemodul ved navn.** Fram til fase 6 av
oppdragsmodulen importerte den ``patients.services`` direkte; nå spør den
``core.stats``-registeret, og hver modul melder inn sin egen handler fra
``apps.ready()``. Det var den importen som gjorde at kilde nummer to ikke
kunne legges til uten å endre denne fila.

Avhengighetsretningen er fortsatt statistikk → moduler, aldri motsatt.
Presentasjonen kjenner domenet; domenet kjenner ikke presentasjonen.

``/pasienter/api/stats/`` ble ikke flyttet hit — det ble slettet 28. aug. 2026.
Det matet aldri header-chipsene; de regnes ut i nettleseren fra pasientlista.
Endepunktet var en rest fra Flask-porten uten kjent konsument.
"""
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves
from core.ratelimit import rate_limit
from core.stats import all_handlers, get_handler
from core.stats_cache import cached_stats_response

# Den ene importen fra en modul som står igjen — og den handler ikke om tall.
# `hent_aktiv_vakt` er portalens scope, delt av alle moduler: `Vakt` bor i
# `core`, men funksjonen ble liggende i pasientmodulen fordi `AppSetting`
# (pekeren `aktiv_vakt_id`) gjør det. Oppdragsmodulen importerer den fra samme
# sted. Å flytte den hører til den ryddejobben, ikke til statistikkregisteret.
from patients.services import hent_aktiv_vakt


# §5: **modulen komponerer tilgang, den eier den ikke.** Den viser kun kilder
# brukeren har minst `les` på i kildemodulen. Uten den regelen er statistikk en
# bakvei rundt modultilgangen: en person uten oppdragstilgang ville fått
# avledet innsyn i oppdragsdata gjennom aggregatene.
#
# Med to kilder ble regelen «vis det du har tilgang til», ikke «alt eller
# ingenting». Det siste var det samme så lenge det bare fantes én kilde, men
# ville tatt statistikken fra alle som leser pasienter uten å ha oppdrag i det
# øyeblikket oppdragsmodulen meldte seg inn i registeret.
def lesbare_kilder(user):
    """Handlerne brukeren har lesetilgang til kildemodulen for.

    ``har_tilgang`` svarer også nei for en modul som er slått av i
    ``ModuleSettings`` — en deaktivert modul skal ikke lyse gjennom
    statistikken.
    """
    return [h for h in all_handlers() if har_tilgang(user, h.slug, 'les')]


def _kilde_for(user, slug):
    """Handleren for slug-en, hvis den finnes og brukeren får se den."""
    handler = get_handler(slug)
    if handler is None:
        return None
    if not har_tilgang(user, handler.slug, 'les'):
        return None
    return handler


@modul_kreves('statistikk', 'les')
@require_http_methods(['GET'])
def statistikk_view(request):
    """Statistikksiden. Fanene er kildene brukeren faktisk kan se.

    Ingen lesbare kilder gir 403: en statistikkside uten tall er en side som
    later som den virker. Det er samme svar som før fase 6 — den gangen fordi
    `patients` var eneste kilde og manglet, nå fordi ingen av kildene slapp
    gjennom.
    """
    kilder = lesbare_kilder(request.user)
    if not kilder:
        raise PermissionDenied
    slugs = {h.slug for h in kilder}
    return render(request, 'statistikk/index.html', {
        'kilder': [
            {'slug': h.slug, 'navn': h.display_name} for h in kilder
        ],
        # Panelene rendres server-side, som resten av synligheten i portalen
        # (`.admin-only` ble fjernet fra JS i august). Et skjult panel i
        # HTML-en er fortsatt sendt: en konto uten pasienttilgang skal ikke
        # ha pasientmarkupen liggende i kilden.
        'har_patients': 'patients' in slugs,
        'har_oppdrag': 'oppdrag' in slugs,
    })


@modul_kreves('statistikk', 'les', svar='json')
@require_http_methods(['GET'])
# S3: appens dyreste spørring. Cachen tar 60 sekunder av gangen, men
# cache-miss-stien var helt ubeskyttet — og det er nettopp den en klient
# i løkke treffer gang på gang. Statistikksiden lastes ved åpning og ved
# auto-refresh hvert 30. sekund, altså rundt 2/min per kilde i normal bruk.
#
# Gruppenavnet beholdt prefikset `patients:` ved flyttingen. Det er
# cache-nøkkelen for tellerne, og å bytte den ville nullstilt bøtta for alle
# som var midt i et vindu i det deployen traff. Alle kilder deler teller med
# vilje: bremsen skal måle hvor mye en klient ber om, ikke hvor mange faner
# den fordeler forespørslene på.
@rate_limit(group='patients:full-stats', rate='30/m', method='GET')
def kilde_full_stats_view(request, slug):
    """Full statistikk fra én kilde, for aktiv vakt.

    Cachet 60s med ETag/304. Dyre aggregater regnes kun én gang per minutt
    per kilde per vakt.

    Ett endepunkt per kilde, ikke ett samlet: fanen som ikke er åpnet skal
    ikke koste noe, og to kilder som deler cache-nøkkel ville regnet ut begge
    hver gang én av dem utløp.
    """
    handler = _kilde_for(request.user, slug)
    if handler is None:
        return JsonResponse(
            {'error': f'Ukjent eller utilgjengelig statistikkilde: «{slug}»'},
            status=403,
        )

    vakt = hent_aktiv_vakt()

    # Vakt-ID i nøkkelen, ikke år: to vakter samme år skal ikke dele cache.
    # Slug-en må stå der av samme grunn — uten den ville kilde nummer to
    # servert kilde nummer éns tall i 60 sekunder.
    @cached_stats_response(cache_key=f'full:{handler.slug}:vakt:{vakt.pk}', ttl=60)
    def _inner(req):
        return handler.full_stats(vakt)

    return _inner(request)


@modul_kreves('statistikk', 'les', svar='json')
@require_http_methods(['GET'])
def kilde_arkiv_full_stats_view(request, slug, pk):
    """Full statistikk for ett arkiv fra én kilde.

    **To gates, ikke én.** Visningen flyttet hit sammen med resten av
    statistikkrenderingen, men tilgangen fulgte ikke med: arkivet er
    strengere beskyttet enn live-statistikken: det er global admin. Hadde
    endepunktet arvet statistikkmodulens gate ved flyttingen, ville enhver med
    statistikktilgang fått innsyn i arkiverte vakter uten at noen bestemte
    det.

    Oppslaget gjør handleren, ikke denne fila — arkivmodellen tilhører
    kildemodulen. Svarer den ``None``, finnes det ikke noe arkiv å vise:
    enten fordi pk-en er ukjent, eller fordi modulen ikke arkiverer ennå.
    Klienten skal se det samme i begge tilfeller.
    """
    if not er_global_admin(request.user):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    handler = _kilde_for(request.user, slug)
    if handler is None:
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = handler.arkiv_full_stats(pk)
    if data is None:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)
    return JsonResponse(data)
