"""KO-innstillingene: verdilistene og «Nullstill».

Delt ut av `ko/views.py` i G2 (13. okt. 2026). `kan_lede_ko` — døra for
listene — bor der, fordi `index_view` bruker den samme regelen for knappen.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, modul_kreves
from core.jsonkropp import json_body, json_feil
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt
from core.verdilister import Verdiliste, lag_views

from . import services
from .models import Ansvarsmerke, Ansvarsomraade, EksternRessurs, Kjennetegn, Konserttype
from .views import kan_lede_ko


# ── KO-innstillingene: ansvarsområdene (18. sep. 2026) ───────────────────────
#
# Samme fabrikk som `oppdrag/views_verdier.py` — `core.verdilister` fra
# 26. sep. 2026 (E2). Til da sto en egen kopi her, med unikt navn uten
# store/små, men uten sperre for `ProtectedError` og med HTML-404 — de to
# hadde glidd. Tabellene er KOs; `oppdrag` kjenner ikke `ko`, og `core` kjenner
# ingen av dem. Fabrikken bar også `Ressursbehov` fra 18. til
# 19. sep. 2026; lista ble erstattet av lagene fra vaktlista (`HendelseLag`).

VERDILISTER = {
    # I bruk = kontoer som bærer merket nå. Linjene teller ikke: de er tekst,
    # og et område som slettes skal ikke skrive om loggen.
    'ansvarsomraader': Verdiliste(
        Ansvarsomraade, i_bruk=lambda r: Ansvarsmerke.objects.i_portal().filter(omraade=r.navn).count()),
    # Programmet (tavleplanleggeren, steg 2). I bruk = konserter som peker
    # dit, i alle vakter: en type fjorårets program står med, slettes ikke.
    'konserttyper': Verdiliste(Konserttype, i_bruk=lambda r: r.poster.count()),
    'kjennetegn': Verdiliste(Kjennetegn, i_bruk=lambda r: r.poster.count()),
    # Eksterne ressurser (19. okt. 2026). I bruk = hendelser der den står som
    # varslet, i alle vakter — en rad fjorårets hendelser bærer, slettes ikke.
    'eksterne': Verdiliste(EksternRessurs, i_bruk=lambda r: r.varslinger.count()),
}


def _views(slug):
    return lag_views(modul='ko', liste=VERDILISTER[slug], slug=slug,
                     kan_lede=kan_lede_ko,
                     nekt='Å sette opp KO-innstillingene er skriv_leder i KO.',
                     gruppe='ko:', skille='_')


ansvarsomraader_view, ansvarsomraade_detalj_view, ansvarsomraader_rekkefolge_view = \
    _views('ansvarsomraader')
konserttyper_view, konserttype_detalj_view, konserttyper_rekkefolge_view = _views('konserttyper')
kjennetegn_view, kjennetegn_detalj_view, kjennetegn_rekkefolge_view = _views('kjennetegn')
eksterne_view, ekstern_detalj_view, eksterne_rekkefolge_view = _views('eksterne')


# ── Nullstilling (18. sep. 2026) ─────────────────────────────────────────────

#: Hva som kan nullstilles, og regelen som gjør det. Navngitt sti per ting.
def _nullstill_oppdrag(vakt):
    # `ko` → `oppdrag` er den tillatte retningen; lokal import som i
    # `index_view`, så modulene lastes i samme rekkefølge som ellers.
    from oppdrag.services import nullstill_vakt
    return nullstill_vakt(vakt)


NULLSTILL = {
    'oppdrag': ('oppdrag', _nullstill_oppdrag),
    'hendelser': ('hendelser', services.nullstill_hendelser),
    'logg': ('logglinjer', services.nullstill_logg),
}


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:nullstill', rate='10/m', method='POST')
def nullstill_view(request, hva):
    """Slett alt av én sort i **aktiv vakt** (André, 18. sep. 2026: «for test
    og utvikling. På prod så står admin ansvarlig for databehandlingen»).

    **Global admin, med `confirm`.** Dekoratøren gir KO-nivået fordi hvert
    view under en modul skal være dekorert; admin-sjekken er den ekte døra.
    Auditraden skrives her, som for sletteinngangen: dette er en navngitt
    handling, og «hvem tømte oppdragslista, og når» er nøyaktig det man leter
    etter i ettertid. Oppdragene nullstilles av oppdragsmodulens egen regel.
    """
    if hva not in NULLSTILL:
        return json_feil('Ukjent nullstilling.', 404)
    if not er_global_admin(request.user):
        return json_feil('Nullstilling er global admin.', 403)
    if not json_body(request).get('confirm'):
        return json_feil('Bekreftelse mangler.', status=400)
    vakt = hent_aktiv_vakt()
    etikett, regel = NULLSTILL[hva]
    antall = regel(vakt)

    from audit.models import AuditLog
    from core.klientip import klient_ip
    AuditLog.objects.create(
        table_name=f'ko_nullstill_{hva}',
        record_id=vakt.pk,
        action='DELETE',
        field_name='nullstilt',
        new_value=f'{antall} {etikett} slettet i vakt {vakt.navn}',
        user=request.user,
        ip=klient_ip(request),
    )
    return JsonResponse({'status': 'ok', 'antall': antall})

