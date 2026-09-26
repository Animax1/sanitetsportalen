"""Verdimengdene som administreres på sentralbordet: lokasjoner, enhetstyper
og problemstillinger (André, 12. sep. 2026: «Admin må kunne redigere listen
over problemstillinger blant annet hvor de skal stå i rekkefølgen i
nedtrekksvinduet. Samme gjelder med rekkefølge på lokasjoner og
grupperinger.»).

Tre tabeller, én fabrikk — og fabrikken er `core.verdilister` fra 26. sep.
2026 (E2), delt med KO. Her står bare *hva* tabellene er. De tre svarer likt: liste for `les`, opprett,
endre og omsortere for **`skriv_leder`** (oppdragsmodulens andre bruk av
trinnet — lokasjoner var `skriv_full` én dag, og André ville ha dem på
leder: den som setter opp verdimengdene endrer hva *alle* på vakta får velge
mellom), sletting for global admin med `{"confirm": true}` og PROTECT →
409 med råd om å deaktivere.

Rekkefølgen settes med hele lista (`PUT …/rekkefolge/` med `ider`), ikke
med «flytt opp» per rad: to opp-trykk som krysser hverandre i nettet ville
ellers gitt en rekkefølge ingen ba om. Klienten flytter i sin egen liste og
sender resultatet.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import er_global_admin, modul_kreves
from core.ratelimit import rate_limit
from core.verdilister import Verdiliste, lag_views

from . import choices, verdier
from .models import Enhetstype, Lokasjon, Lydvarsel, Problemstilling
from .views_common import kan_lede


class Verdimengde(Verdiliste):
    """Oppdragsmodulens verdimengder — beskrivelsen per tabell. Mekanikken
    (felter, 404, 409, rekkefølge, ETag) er `core.verdilister` sin (E2)."""

    #: Brukt i teksten ved 409 og i grensesnittet.
    entall = ''


class Lokasjoner(Verdimengde):
    model = Lokasjon
    entall = 'lokasjonen'

    def i_bruk(self, rad):
        return rad.oppdrag.count()

    def raad_ved_bruk(self, rad, brukt):
        return (f'«{rad.navn}» er brukt av {brukt} oppdrag og kan ikke slettes. '
                'Deaktiver den i stedet — da forsvinner den fra nedtrekket.')


class Enhetstyper(Verdimengde):
    model = Enhetstype
    entall = 'enhetstypen'
    # **De to flaggene settes her, ikke på den enkelte enheten** (16. sep.
    # 2026): «kan gå passiv vakt» og «kan avvente» er egenskaper ved *slaget*
    # ressurs — spesialressurser går bakvakt, ambulanser gjør det ikke. Sto de
    # på hver enhet, måtte de settes på nytt for hver bil, og en glemt
    # avkryssing ville sett ut som en bevisst beslutning.
    ekstra = {'kan_passiv_vakt': bool, 'kan_avvente': bool}

    def i_bruk(self, rad):
        return rad.enheter.count()

    def raad_ved_bruk(self, rad, brukt):
        return (f'«{rad.navn}» har {brukt} enheter og kan ikke slettes. '
                'Flytt enhetene til en annen type først, eller deaktiver typen.')


def _kategori(raa):
    verdi = str(raa or '').strip()
    if verdi not in dict(Problemstilling.KATEGORI):
        raise ValueError('Kategori må være medisinsk, drift eller begge.')
    return verdi


class Problemstillinger(Verdimengde):
    model = Problemstilling
    entall = 'problemstillingen'
    ekstra = {'kategori': _kategori, 'med_antall': bool}

    def rader(self):
        from . import verdier
        return verdier.problemstillinger(inkluder_inaktive=True)

    def i_bruk(self, rad):
        # Teksten på oppdraget er navnet; ingen FK å telle gjennom. Sletting
        # av en rad river ikke oppdrag med seg, så bruk sperrer ikke her.
        return 0

    def er_fast(self, rad):
        return rad.er_fast


VERDIMENGDER = {
    'lokasjoner': Lokasjoner(),
    'enhetstyper': Enhetstyper(),
    'problemstillinger': Problemstillinger(),
}


def _views(slug):
    return lag_views(modul='oppdrag', liste=VERDIMENGDER[slug], slug=slug, kan_lede=kan_lede,
                     nekt='Å sette opp verdimengdene er skriv_leder.',
                     gruppe='oppdrag:verdier:', skille=':')


lokasjoner_view, lokasjon_detalj_view, lokasjoner_rekkefolge_view = _views('lokasjoner')
enhetstyper_view, enhetstype_detalj_view, enhetstyper_rekkefolge_view = _views('enhetstyper')
(problemstillinger_view, problemstilling_detalj_view,
 problemstillinger_rekkefolge_view) = _views('problemstillinger')


# ── Bilinnstillingene (12. sep. 2026) ─────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'PUT'])
@rate_limit(group='oppdrag:bilinnstillinger', rate='30/m', method='PUT')
def bilinnstillinger_view(request):
    """Lydvarselets terskler per hastegrad, om lyden er på i det hele tatt,
    om nytt oppdrag skal pipe, og om grovsortering kreves før Avreist.

    GET for alle med `les` — bilen henter dem hvert femte minutt, så en
    endring når fram uten at siden lastes på nytt. PUT er **global admin**
    (André: «Admin kan justere»): tallene gjelder alle biler på alle vakter.
    """
    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'data': verdier.bilinnstillinger()})
    if not er_global_admin(request.user):
        return json_feil('Bilinnstillingene settes av global admin.', 403)
    data = json_body(request)
    terskler = data.get('terskler') or {}
    if not isinstance(terskler, dict):
        return json_feil('Send `terskler` som {hastegrad: [første, gjenta]}.')
    nye = {}
    for hastegrad, par in terskler.items():
        if hastegrad not in choices.HASTEGRAD:
            return json_feil(f'Ukjent hastegrad «{hastegrad}».')
        try:
            forste, gjenta = (int(par[0]), int(par[1]))
        except (TypeError, ValueError, IndexError, KeyError):
            return json_feil(f'{hastegrad}: send to hele tall i sekunder.')
        if forste < 0 or gjenta < 5 or forste > 86400 or gjenta > 86400:
            return json_feil(f'{hastegrad}: første varsel 0–86400 s, gjenta minst 5 s.')
        nye[hastegrad] = (forste, gjenta)
    for hastegrad, (forste, gjenta) in nye.items():
        Lydvarsel.objects.update_or_create(
            hastegrad=hastegrad, defaults={'forste_sekunder': forste, 'gjenta_sekunder': gjenta})
    aktive = data.get('aktive')
    if aktive is not None:
        if not isinstance(aktive, dict) or any(h not in choices.HASTEGRAD for h in aktive):
            return json_feil('Send `aktive` som {hastegrad: true/false}.')
        for hastegrad, paa in aktive.items():
            Lydvarsel.objects.update_or_create(hastegrad=hastegrad, defaults={'aktiv': bool(paa)})
    from core.models import AppSetting
    for felt, nokkel in (('nytt_oppdrag', verdier.LYD_NYTT_NOKKEL),
                         ('lyd_aktiv', verdier.LYD_AKTIV_NOKKEL),
                         ('krev_grov_avreist', verdier.KREV_GROV_AVREIST_NOKKEL)):
        if felt in data:
            AppSetting.set(nokkel, '1' if data[felt] else '0')
    return JsonResponse({'status': 'ok', 'data': verdier.bilinnstillinger()})
