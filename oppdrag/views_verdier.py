"""Verdimengdene som administreres på sentralbordet: lokasjoner, enhetstyper
og problemstillinger (André, 12. sep. 2026: «Admin må kunne redigere listen
over problemstillinger blant annet hvor de skal stå i rekkefølgen i
nedtrekksvinduet. Samme gjelder med rekkefølge på lokasjoner og
grupperinger.»).

Tre tabeller, én fabrikk. De tre svarer likt: liste for `les`, opprett,
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

from django.db.models import ProtectedError
from django.http import HttpResponseNotModified, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves

from . import choices, verdier
from .models import Enhetstype, Lokasjon, Lydvarsel, Problemstilling
from .views_common import er_enhetskonto, etag_for, json_body


def _feil(melding, status=400):
    return JsonResponse({'status': 'error', 'message': melding}, status=status)


class Verdimengde:
    """Beskrivelsen av én tabell: hva som kan settes, hva som teller som
    «i bruk», og hvilke rader som er faste."""

    model = None
    entall = ''
    #: Felt utover navn/er_aktiv som PUT/POST får sette: {navn: normaliserer}.
    ekstra: dict = {}

    def til_dict(self, rad):
        d = {'id': rad.pk, 'navn': rad.navn, 'er_aktiv': rad.er_aktiv,
             'rekkefolge': rad.rekkefolge, 'i_bruk': self.i_bruk(rad),
             'fast': self.er_fast(rad)}
        for felt in self.ekstra:
            d[felt] = getattr(rad, felt)
        return d

    def rader(self):
        return list(self.model.objects.all())

    def i_bruk(self, rad) -> int:
        return 0

    def er_fast(self, rad) -> bool:
        return False

    def raad_ved_bruk(self, rad, brukt) -> str:
        return (f'«{rad.navn}» er i bruk ({brukt}) og kan ikke slettes. '
                'Deaktiver den i stedet — da forsvinner den fra nedtrekket.')


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


def _kan_lede(request):
    # Global admin står utenfor modulaksen og får `skriv_full` av
    # `nivaa_for` — leder-trinnet må nevnes eksplisitt, som `kan_lede` i
    # vaktlista gjør.
    # En enhetskonto setter ikke opp verdimengdene, uansett nivå (M6).
    if er_enhetskonto(request.user):
        return False
    return er_global_admin(request.user) or har_tilgang(request.user, 'oppdrag', 'skriv_leder')


def _sett_felter(vm, rad, data, *, ny=False):
    """Navn, aktiv, rekkefølge og ekstrafeltene fra kroppen. Returnerer
    feiltekst eller None."""
    if 'navn' in data or ny:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return 'Navn kan ikke være tomt.'
        if vm.er_fast(rad) and navn != rad.navn:
            return f'«{rad.navn}» er fast og kan ikke få nytt navn.'
        if vm.model.objects.filter(navn=navn).exclude(pk=rad.pk).exists():
            return f'«{navn}» finnes allerede.'
        rad.navn = navn
    if 'er_aktiv' in data:
        if vm.er_fast(rad) and not data['er_aktiv']:
            return f'«{rad.navn}» er fast og kan ikke deaktiveres.'
        rad.er_aktiv = bool(data['er_aktiv'])
    if 'rekkefolge' in data:
        try:
            rad.rekkefolge = int(data['rekkefolge'])
        except (TypeError, ValueError):
            return 'Rekkefølge må være et tall.'
    for felt, normaliser in vm.ekstra.items():
        if felt in data:
            if vm.er_fast(rad):
                return f'«{rad.navn}» er fast og kan ikke endres.'
            try:
                setattr(rad, felt, normaliser(data[felt]))
            except ValueError as feil:
                return str(feil)
    return None


def _liste_view(slug):
    vm = VERDIMENGDER[slug]

    @never_cache
    @modul_kreves('oppdrag', 'les', svar='json')
    @require_http_methods(['GET', 'POST'])
    def view(request):
        if request.method == 'GET':
            data = [vm.til_dict(r) for r in vm.rader()]
            etag = etag_for([tuple(sorted(d.items())) for d in data])
            if request.META.get('HTTP_IF_NONE_MATCH') == etag:
                svar = HttpResponseNotModified()
                svar['ETag'] = etag
                return svar
            svar = JsonResponse({'status': 'ok', 'data': data})
            svar['ETag'] = etag
            return svar

        if not _kan_lede(request):
            return _feil('Å sette opp verdimengdene er skriv_leder.', 403)
        data = json_body(request)
        rad = vm.model()
        # Sist i lista: den som legger til, flytter etterpå om hun vil.
        siste = vm.model.objects.order_by('-rekkefolge').values_list('rekkefolge', flat=True).first()
        rad.rekkefolge = (siste or 0) + 10
        feil = _sett_felter(vm, rad, data, ny=True)
        if feil:
            return _feil(feil)
        rad.save()
        return JsonResponse({'status': 'ok', 'data': vm.til_dict(rad)})

    view.__name__ = f'{slug}_view'
    return view


def _detalj_view(slug):
    vm = VERDIMENGDER[slug]

    @modul_kreves('oppdrag', 'les', svar='json')
    @require_http_methods(['PUT', 'DELETE'])
    def view(request, pk):
        if not _kan_lede(request):
            return _feil('Å sette opp verdimengdene er skriv_leder.', 403)
        try:
            rad = vm.model.objects.get(pk=pk)
        except vm.model.DoesNotExist:
            return _feil('Ikke funnet', 404)

        if request.method == 'DELETE':
            if not er_global_admin(request.user):
                return _feil('Sletting er global admin.', 403)
            if not json_body(request).get('confirm'):
                return _feil('Bekreftelse mangler. Send {"confirm": true}.')
            if vm.er_fast(rad):
                return _feil(f'«{rad.navn}» er fast og kan ikke slettes.')
            brukt = vm.i_bruk(rad)
            if brukt:
                return _feil(vm.raad_ved_bruk(rad, brukt), 409)
            try:
                rad.delete()
            except ProtectedError:
                return _feil(vm.raad_ved_bruk(rad, '?'), 409)
            return JsonResponse({'status': 'ok'})

        feil = _sett_felter(vm, rad, json_body(request))
        if feil:
            return _feil(feil)
        rad.save()
        return JsonResponse({'status': 'ok', 'data': vm.til_dict(rad)})

    view.__name__ = f'{slug}_detalj_view'
    return view


def _rekkefolge_view(slug):
    vm = VERDIMENGDER[slug]

    @modul_kreves('oppdrag', 'les', svar='json')
    @require_http_methods(['PUT'])
    def view(request):
        if not _kan_lede(request):
            return _feil('Å sette opp verdimengdene er skriv_leder.', 403)
        ider = json_body(request).get('ider')
        if not isinstance(ider, list) or not all(isinstance(i, int) for i in ider):
            return _feil('Send `ider` som en liste med tall.')
        rader = {r.pk: r for r in vm.model.objects.filter(pk__in=ider)}
        if len(rader) != len(set(ider)):
            return _feil('Lista inneholder ukjente rader — hent den på nytt.')
        for plass, pk in enumerate(ider):
            rad = rader[pk]
            ny = (plass + 1) * 10
            if rad.rekkefolge != ny:
                rad.rekkefolge = ny
                rad.save(update_fields=['rekkefolge', 'updated_at'])
        return JsonResponse({'status': 'ok', 'data': [vm.til_dict(r) for r in vm.rader()]})

    view.__name__ = f'{slug}_rekkefolge_view'
    return view


lokasjoner_view = _liste_view('lokasjoner')
lokasjon_detalj_view = _detalj_view('lokasjoner')
lokasjoner_rekkefolge_view = _rekkefolge_view('lokasjoner')
enhetstyper_view = _liste_view('enhetstyper')
enhetstype_detalj_view = _detalj_view('enhetstyper')
enhetstyper_rekkefolge_view = _rekkefolge_view('enhetstyper')
problemstillinger_view = _liste_view('problemstillinger')
problemstilling_detalj_view = _detalj_view('problemstillinger')
problemstillinger_rekkefolge_view = _rekkefolge_view('problemstillinger')


# ── Bilinnstillingene (12. sep. 2026) ─────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'PUT'])
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
        return _feil('Bilinnstillingene settes av global admin.', 403)
    data = json_body(request)
    terskler = data.get('terskler') or {}
    if not isinstance(terskler, dict):
        return _feil('Send `terskler` som {hastegrad: [første, gjenta]}.')
    nye = {}
    for hastegrad, par in terskler.items():
        if hastegrad not in choices.HASTEGRAD:
            return _feil(f'Ukjent hastegrad «{hastegrad}».')
        try:
            forste, gjenta = (int(par[0]), int(par[1]))
        except (TypeError, ValueError, IndexError, KeyError):
            return _feil(f'{hastegrad}: send to hele tall i sekunder.')
        if forste < 0 or gjenta < 5 or forste > 86400 or gjenta > 86400:
            return _feil(f'{hastegrad}: første varsel 0–86400 s, gjenta minst 5 s.')
        nye[hastegrad] = (forste, gjenta)
    for hastegrad, (forste, gjenta) in nye.items():
        Lydvarsel.objects.update_or_create(
            hastegrad=hastegrad, defaults={'forste_sekunder': forste, 'gjenta_sekunder': gjenta})
    aktive = data.get('aktive')
    if aktive is not None:
        if not isinstance(aktive, dict) or any(h not in choices.HASTEGRAD for h in aktive):
            return _feil('Send `aktive` som {hastegrad: true/false}.')
        for hastegrad, paa in aktive.items():
            Lydvarsel.objects.update_or_create(hastegrad=hastegrad, defaults={'aktiv': bool(paa)})
    from patients.models import AppSetting
    for felt, nokkel in (('nytt_oppdrag', verdier.LYD_NYTT_NOKKEL),
                         ('lyd_aktiv', verdier.LYD_AKTIV_NOKKEL),
                         ('krev_grov_avreist', verdier.KREV_GROV_AVREIST_NOKKEL)):
        if felt in data:
            AppSetting.set(nokkel, '1' if data[felt] else '0')
    return JsonResponse({'status': 'ok', 'data': verdier.bilinnstillinger()})
