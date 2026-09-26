"""Verdilister: små tabeller en leder setter opp, med én fabrikk (26. sep. 2026, E2).

Lokasjonene, enhetstypene og problemstillingene i oppdrag, ansvarsområdene,
konserttypene og kjennetegnene i KO: liste for `les`, opprett/endre/omsortere
for den som leder, sletting for global admin med `confirm` og 409 når raden er
i bruk. **To fabrikker med rundt 130 like linjer** sto i `oppdrag/views_verdier.py`
og `ko/views.py`, og de hadde glidd:

| | oppdrag | KO | nå |
|---|---|---|---|
| Unikt navn | eksakt | uten store/små | **uten store/små** — «Scene» og «scene» i ett nedtrekk er en feil |
| Maks lengde | ingen sjekk (for langt navn: 500 på PostgreSQL) | sjekket | **sjekket**, lest av modellfeltet |
| `ProtectedError` ved sletting | 409 | 500 | **409** |
| Ukjent ID | JSON-404 | HTML-404 | **JSON-404** |
| ETag på lista | ja | nei | **ja** |

Fabrikken ligger i `core` fordi to moduler trenger den og `ko` ikke skal kjenne
`oppdrag`. Modulen melder inn tabellene (`Verdiliste`) og sin egen regel for
hvem som leder — tilgangen er modulens, mekanikken er felles.
"""
from __future__ import annotations

import hashlib
import json

from django.db.models.deletion import ProtectedError
from django.http import HttpResponseNotModified, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, modul_kreves
from core.jsonkropp import json_body, json_feil
from core.ratelimit import rate_limit


class Verdiliste:
    """Beskrivelsen av én tabell. Subklass, eller gi `i_bruk` som funksjon.

    Tabellen må ha `navn`, `er_aktiv` og `rekkefolge`.
    """

    model = None
    #: Felt utover navn/er_aktiv/rekkefolge som PUT/POST får sette: {navn: normaliserer}.
    ekstra: dict = {}

    def __init__(self, model=None, *, i_bruk=None):
        if model is not None:
            self.model = model
        if i_bruk is not None:
            self.i_bruk = i_bruk

    @property
    def maks(self) -> int | None:
        return self.model._meta.get_field('navn').max_length

    def rader(self):
        return list(self.model.objects.all())

    def i_bruk(self, rad) -> int:
        return 0

    def er_fast(self, rad) -> bool:
        return False

    def raad_ved_bruk(self, rad, brukt) -> str:
        return (f'«{rad.navn}» er i bruk ({brukt}) og kan ikke slettes. '
                'Deaktiver den i stedet — da forsvinner den fra nedtrekket.')

    def til_dict(self, rad) -> dict:
        d = {'id': rad.pk, 'navn': rad.navn, 'er_aktiv': rad.er_aktiv,
             'rekkefolge': rad.rekkefolge, 'i_bruk': self.i_bruk(rad),
             'fast': self.er_fast(rad)}
        for felt in self.ekstra:
            d[felt] = getattr(rad, felt)
        return d

    def valider_navn(self, navn, rad) -> str | None:
        if not navn:
            return 'Navn kan ikke være tomt.'
        if self.maks and len(navn) > self.maks:
            return f'Navnet er for langt (maks {self.maks} tegn).'
        if self.er_fast(rad) and navn != rad.navn:
            return f'«{rad.navn}» er fast og kan ikke få nytt navn.'
        if self.model.objects.filter(navn__iexact=navn).exclude(pk=rad.pk).exists():
            return f'«{navn}» finnes allerede.'
        return None

    def sett_felter(self, rad, data, *, ny=False) -> str | None:
        """Navn, aktiv, rekkefølge og ekstrafeltene fra kroppen. Returnerer
        feiltekst eller None. Rører ikke basen."""
        if 'navn' in data or ny:
            navn = (data.get('navn') or '').strip()
            feil = self.valider_navn(navn, rad)
            if feil:
                return feil
            rad.navn = navn
        if 'er_aktiv' in data:
            if self.er_fast(rad) and not data['er_aktiv']:
                return f'«{rad.navn}» er fast og kan ikke deaktiveres.'
            rad.er_aktiv = bool(data['er_aktiv'])
        if 'rekkefolge' in data:
            try:
                rad.rekkefolge = int(data['rekkefolge'])
            except (TypeError, ValueError):
                return 'Rekkefølge må være et tall.'
        for felt, normaliser in self.ekstra.items():
            if felt in data:
                if self.er_fast(rad):
                    return f'«{rad.navn}» er fast og kan ikke endres.'
                try:
                    setattr(rad, felt, normaliser(data[felt]))
                except ValueError as feil:
                    return str(feil)
        return None


def _etag(data) -> str:
    raa = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return '"vl:' + hashlib.sha256(raa.encode('utf-8')).hexdigest()[:16] + '"'


def lag_views(*, modul: str, liste: Verdiliste, slug: str, kan_lede, nekt: str,
              gruppe: str, skille: str = ':'):
    """(liste_view, detalj_view, rekkefolge_view) for én verdiliste.

    `kan_lede(user)` er modulens regel, `nekt` teksten ved 403. `gruppe` og
    `skille` gir rate-limit-gruppene — modulene beholder navnene de hadde, så
    ingen teller deles på tvers (`CLAUDE.md`, «Rate-limiting»).
    """

    @never_cache
    @modul_kreves(modul, 'les', svar='json')
    @require_http_methods(['GET', 'POST'])
    @rate_limit(group=f'{gruppe}{slug}', rate='60/m', method='POST')
    def liste_view(request):
        if request.method == 'GET':
            data = [liste.til_dict(r) for r in liste.rader()]
            etag = _etag(data)
            if request.META.get('HTTP_IF_NONE_MATCH') == etag:
                svar = HttpResponseNotModified()
            else:
                svar = JsonResponse({'status': 'ok', 'data': data})
            svar['ETag'] = etag
            return svar

        if not kan_lede(request.user):
            return json_feil(nekt, 403)
        rad = liste.model()
        # Sist i lista: den som legger til, flytter etterpå om hun vil.
        siste = (liste.model.objects.order_by('-rekkefolge')
                 .values_list('rekkefolge', flat=True).first())
        rad.rekkefolge = (siste or 0) + 10
        feil = liste.sett_felter(rad, json_body(request), ny=True)
        if feil:
            return json_feil(feil)
        rad.save()
        return JsonResponse({'status': 'ok', 'data': liste.til_dict(rad)})

    @modul_kreves(modul, 'les', svar='json')
    @require_http_methods(['PUT', 'DELETE'])
    @rate_limit(group=f'{gruppe}{slug}{skille}detalj', rate='60/m', method=['PUT', 'DELETE'])
    def detalj_view(request, pk):
        if not kan_lede(request.user):
            return json_feil(nekt, 403)
        rad = liste.model.objects.filter(pk=pk).first()
        if rad is None:
            return json_feil('Ikke funnet', 404)
        data = json_body(request)

        if request.method == 'DELETE':
            if not er_global_admin(request.user):
                return json_feil('Sletting er global admin.', 403)
            if not data.get('confirm'):
                return json_feil('Bekreftelse mangler. Send {"confirm": true}.')
            if liste.er_fast(rad):
                return json_feil(f'«{rad.navn}» er fast og kan ikke slettes.')
            brukt = liste.i_bruk(rad)
            if brukt:
                return json_feil(liste.raad_ved_bruk(rad, brukt), 409)
            try:
                rad.delete()
            except ProtectedError:
                return json_feil(liste.raad_ved_bruk(rad, '?'), 409)
            return JsonResponse({'status': 'ok'})

        feil = liste.sett_felter(rad, data)
        if feil:
            return json_feil(feil)
        rad.save()
        return JsonResponse({'status': 'ok', 'data': liste.til_dict(rad)})

    @modul_kreves(modul, 'les', svar='json')
    @require_http_methods(['PUT'])
    @rate_limit(group=f'{gruppe}{slug}{skille}rekkefolge', rate='30/m', method='PUT')
    def rekkefolge_view(request):
        """Hele lista, ikke «opp» per rad: to «opp» som krysser hverandre i
        nettet gir ellers en rekkefølge ingen ba om."""
        if not kan_lede(request.user):
            return json_feil(nekt, 403)
        ider = json_body(request).get('ider')
        if not isinstance(ider, list) or not all(isinstance(i, int) for i in ider):
            return json_feil('Send `ider` som en liste med tall.')
        rader = {r.pk: r for r in liste.model.objects.filter(pk__in=ider)}
        if len(rader) != len(set(ider)):
            return json_feil('Lista inneholder ukjente rader — hent den på nytt.')
        felter = ['rekkefolge'] + (
            ['updated_at'] if any(f.name == 'updated_at' for f in liste.model._meta.fields) else [])
        for plass, rad_pk in enumerate(ider):
            rad = rader[rad_pk]
            ny = (plass + 1) * 10
            if rad.rekkefolge != ny:
                rad.rekkefolge = ny
                rad.save(update_fields=felter)
        return JsonResponse({'status': 'ok', 'data': [liste.til_dict(r) for r in liste.rader()]})

    liste_view.__name__ = f'{slug}_view'
    detalj_view.__name__ = f'{slug}_detalj_view'
    rekkefolge_view.__name__ = f'{slug}_rekkefolge_view'
    return liste_view, detalj_view, rekkefolge_view
