"""Registersiden: mannskapet og de tre verdimengdene admin styrer.

**Verdimengdene sorteres alfabetisk.** `rekkefolge` ble fjernet 30. aug. 2026:
alle radene sto på standardverdien, så `ordering` falt uansett tilbake på
navnet — det var alfabetisk i praksis, med et tallfelt i skjemaet som pris.

**Hvorfor denne fila finnes.** Fase 1 la registrene i `vaktliste/admin.py` og
skrev at «Django-admin er uansett riktig hjem for `Korps`, `Kompetanse` og
`Ressursrolle`». Det var feil: `/django-admin/` er kun rutet når `DEBUG` eller
`OFFLINE_MODE` er på (S1 — den er en parallell innloggingsflate som omgår
rate-limiting, kontosperre, MFA-tvang og `LoginEvent`). I produksjon fantes det
dermed ingen vei til å opprette et korps eller et mannskap, og
planleggingssiden hadde en nedtrekksliste som aldri kunne fylles.

`admin.py` blir stående som utviklerverktøy lokalt. Den er ikke flaten
portalen bruker.

**Egen side, ikke en fane på planleggingssiden.** Registrene er *globale* —
personellet organisasjonen har — mens fanene på `/vaktliste/` er ressursene i
*én* vakt. To ulike omfang i samme faneliste ville sagt at «Mannskap» er noe
som hører til oktobervakta.

**Mannskapslista er ikke et admin-skjermbilde, den er bestillingen.** Første
setning i det André ba om var «lister opp personell overordnet sortert etter
hvilket korps de tilhører, kompetanse, rolle under vakt». Derfor er lista
gruppert på korps og viser kompetansene, framfor å være en flat tabell med en
blyant på hver rad.

**Sletting er ikke veien ut av et register.** `Mannskap`, `Korps` og
`Ressursrolle` er PROTECT-et fra rader som beskriver historikk, og `Kompetanse`
er blokkert her selv om M2M-en ikke ville protestert — å slette den ville
stilltiende strippet kompetansen fra alle som har den. Pensjonering
(`er_aktiv=False`) er den normale veien ut, som i pasientmodulens
navneregistre.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit

from .models import (Kompetanse, Korps, Mannskap, Ressursgruppe,
                     Ressursrolle)
from . import services
from .views import _feil, _int, _json_body, _nektet, _tilgangskontekst


def _ider(raa):
    """Liste med klientverdier → liste med gyldige int-er.

    `.set()` med en ikke-numerisk verdi i lista kaster, og feilen kommer fra
    Django framfor fra oss. Silen her gjør at et rusket element blir ignorert
    i stedet for å ta ned hele lagringen.
    """
    if not isinstance(raa, (list, tuple)):
        return []
    return [i for i in (_int(v) for v in raa) if i is not None]


# ── Siden ────────────────────────────────────────────────────────────────────

@modul_kreves('vaktliste', 'les')
@require_http_methods(['GET'])
def registre_view(request):
    """Mannskaps- og registersiden.

    `les` slipper inn — hele registeret, alle korps. Hva kontoen får *endre*
    avgjøres per rad, både her og på serveren.
    """
    return render(request, 'vaktliste/registre.html',
                  _tilgangskontekst(request.user))


# ── De tre verdimengdene ─────────────────────────────────────────────────────
#
# `Korps`, `Kompetanse` og `Ressursrolle` har samme form — navn og er_aktiv —
# og fire views hver ville vært ord for ord like bortsett fra modellnavnet.
# Samme grep som `patients/views_registre.py` (N13.2), og av samme grunn: tre
# kopier er tre steder en rettelse kan bli glemt.
#
# Korps har ett felt til (`kortnavn`), og fabrikken tar derfor en liste over
# valgfrie tekstfelter framfor å bli to fabrikker.

def verdi_til_dict(model, rad, *, ekstra_felt=(), stige=False, gruppe=False):
    """Én rad fra en verdimengde som JSON.

    **Modulnivå, ikke inne i fabrikken.** Mannskapsendepunktet sender de tre
    verdimengdene med i sitt eget svar (siden trenger alle fire for å tegne
    seg), og de radene skal ha nøyaktig samme form som `/api/korps/` og
    vennene gir. Var de to formene skrevet hver for seg, ville de gli fra
    hverandre — og det gjorde de: registerfanene viste «ubrukt» på et korps
    med mannskap, fordi den lette nedtrekkslista manglet `i_bruk`. En
    Django-test som spurte `/api/korps/` direkte så det ikke, for det er ikke
    den veien siden går.
    """
    ut = {
        'id': rad.pk,
        'navn': rad.navn,
        'er_aktiv': rad.er_aktiv,
        'i_bruk': _antall_bruk(model, rad),
    }
    for felt in ekstra_felt:
        ut[felt] = getattr(rad, felt)
    if stige:
        ut['bygger_paa_id'] = rad.bygger_paa_id
        ut['bygger_paa_navn'] = rad.bygger_paa.navn if rad.bygger_paa else ''
    if gruppe:
        # Rollen hører til en gruppe, og nedtrekket i ressurstabellen filtrerer
        # på den. Uten IDen i svaret måtte klienten gjette ut fra navnet.
        ut['gruppe_id'] = rad.gruppe_id
        ut['gruppe_navn'] = rad.gruppe.navn
    return ut


#: Hvordan hver verdimengde serialiseres. Ett sted, brukt av både fabrikken og
#: mannskapsendepunktet — se `verdi_til_dict`.
VERDIMENGDER = {
    'korps': (Korps, {'ekstra_felt': ('kortnavn',)}),
    'kompetanser': (Kompetanse, {'stige': True}),
    'roller': (Ressursrolle, {'gruppe': True}),
}


def _register_views(model, etikett, etikett_bestemt, *, ekstra_felt=(),
                    stige=False, gruppe=False, krav='skriv_alt'):
    """Bygg (liste-view, detalj-view) for en av verdimengdene.

    Args:
        model: Korps, Kompetanse eller Ressursrolle
        etikett: ubestemt form til feilmeldinger («Korpset» → «Korps»)
        etikett_bestemt: bestemt form, til «… er i bruk»-meldingen
        ekstra_felt: valgfrie tekstfelter modellen har utover navn
        stige: modellen har `bygger_paa` (bare `Kompetanse`). Feltet er en FK
            til seg selv og må sykkelsjekkes, så det kan ikke behandles som
            de valgfrie tekstfeltene.
        gruppe: modellen henger under en `Ressursgruppe` (bare `Ressursrolle`).
            Feltet er påkrevd ved opprettelse — en rolle uten gruppe ville
            ikke dukket opp i noe nedtrekk, altså en rad man lager og aldri
            finner igjen.
        krav: hvilken terskel skriving krever. `'skriv_alt'` for
            organisasjonsdataene (korps, kompetanser), `'lede'` for rollene:
            en rolle er del av vaktoppsettet, og `skriv_full` bemanner det
            oppsettet uten å bestemme det.
    """
    _slipper_inn = (services.kan_lede if krav == 'lede'
                    else services.kan_skrive_alt)

    def _til_dict(rad):
        return verdi_til_dict(model, rad, ekstra_felt=ekstra_felt,
                              stige=stige, gruppe=gruppe)

    @never_cache
    @modul_kreves('vaktliste', 'les', svar='json')
    @require_http_methods(['GET', 'POST'])
    @rate_limit(group=f'vaktliste:register:{model._meta.model_name}',
                rate='60/m', method='POST')
    def liste_view(request):
        # Verdimengdene er organisasjonens oppsett, ikke ett korps' bord:
        # kunne korps-brukeren opprette korps, kunne hun lage seg et nytt å
        # føre. `les` ser dem — nedtrekkslistene trenger dem.
        if request.method == 'POST' and not _slipper_inn(request.user):
            return _nektet()

        if request.method == 'GET':
            # Inaktive er med: de skal kunne aktiveres igjen, og en rad som
            # forsvinner helt ser ut som en sletting som ikke skjedde.
            qs = model.objects.all()
            if gruppe:
                qs = qs.select_related('gruppe')
            return JsonResponse({'status': 'ok', 'data': [
                _til_dict(r) for r in qs]})

        data = _json_body(request)
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil(f'{etikett} må ha et navn.')

        felter = {felt: (data.get(felt) or '').strip() for felt in ekstra_felt}
        if stige:
            felter['bygger_paa_id'] = _int(data.get('bygger_paa_id'))
        if gruppe:
            gruppe_id = _int(data.get('gruppe_id'))
            if not gruppe_id or not Ressursgruppe.objects.filter(
                    pk=gruppe_id).exists():
                return _feil(f'{etikett} må høre til en ressursgruppe.')
            felter['gruppe_id'] = gruppe_id
        try:
            with transaction.atomic():
                rad = model.objects.create(
                    navn=navn,
                    **felter,
                )
        except IntegrityError:
            return _feil(f'«{navn}» finnes allerede.')
        return JsonResponse({'status': 'ok', 'data': _til_dict(rad)}, status=201)

    @modul_kreves('vaktliste', 'les', svar='json')
    @require_http_methods(['PUT', 'DELETE'])
    def detalj_view(request, pk):
        if not _slipper_inn(request.user):
            return _nektet()

        try:
            rad = (model.objects.select_related('gruppe').get(pk=pk) if gruppe
                   else model.objects.get(pk=pk))
        except model.DoesNotExist:
            return _feil(f'{etikett} ikke funnet', status=404)

        if request.method == 'DELETE':
            # PROTECT dekker Korps og Ressursrolle. Kompetanse er en M2M og ville
            # sluppet gjennom — og stilltiende strippet kompetansen fra alle
            # som har den. Telle-sjekken under gjelder derfor alle tre.
            if _antall_bruk(model, rad):
                return _feil(
                    f'{etikett_bestemt} er i bruk og kan ikke slettes. '
                    f'Sett den inaktiv i stedet — da skjules den i '
                    f'nedtrekkslistene, men beholdes der den alt er brukt.',
                    status=409)
            try:
                rad.delete()
            except ProtectedError:
                return _feil(
                    f'{etikett_bestemt} er i bruk og kan ikke slettes. '
                    f'Sett den inaktiv i stedet.', status=409)
            return JsonResponse({'status': 'ok'})

        data = _json_body(request)
        if 'navn' in data:
            navn = (data.get('navn') or '').strip()
            if not navn:
                return _feil(f'{etikett} må ha et navn.')
            rad.navn = navn
        for felt in ekstra_felt:
            if felt in data:
                setattr(rad, felt, (data.get(felt) or '').strip())
        if stige and 'bygger_paa_id' in data:
            forelder = _int(data['bygger_paa_id'])
            # «A bygger på B, B bygger på A» har ikke noe svar på hvilken som
            # er øverst. Stoppes ved skriving, ikke ved lesing.
            if services.lager_sykel(rad.pk, forelder):
                return _feil(
                    'Det ville laget en ring i stigen: kompetansen kan ikke '
                    'bygge på noe som allerede bygger på den.')
            rad.bygger_paa_id = forelder
        if 'er_aktiv' in data:
            rad.er_aktiv = bool(data['er_aktiv'])

        try:
            with transaction.atomic():
                rad.save()
        except IntegrityError:
            return _feil(f'«{rad.navn}» finnes allerede.')
        return JsonResponse({'status': 'ok', 'data': _til_dict(rad)})

    return liste_view, detalj_view


def _antall_bruk(model, rad):
    """Hvor mange rader som viser til denne — grunnlaget for «kan slettes».

    Tallet vises også i lista: en verdimengde man kan slette uten å vite hva
    som henger i den, sletter man for lett.
    """
    if model is Korps:
        return rad.mannskap.count() + rad.reserverte_ressurser.count()
    if model is Kompetanse:
        return rad.mannskap.count()
    return rad.vaktposter.count()          # Ressursrolle


korps_view, korps_detalj_view = _register_views(
    Korps, 'Korpset', 'Korpset', ekstra_felt=('kortnavn',))
kompetanser_view, kompetanse_detalj_view = _register_views(
    Kompetanse, 'Kompetansen', 'Kompetansen', stige=True)
roller_view, rolle_detalj_view = _register_views(
    Ressursrolle, 'Rollen', 'Rollen', gruppe=True, krav='lede')

# Navn for tracebacks og URL-reversering — uten dette heter alle seks
# `liste_view`/`detalj_view`. Samme grep som i pasientmodulen.
korps_view.__name__ = 'korps_view'
korps_detalj_view.__name__ = 'korps_detalj_view'
kompetanser_view.__name__ = 'kompetanser_view'
kompetanse_detalj_view.__name__ = 'kompetanse_detalj_view'
roller_view.__name__ = 'roller_view'
rolle_detalj_view.__name__ = 'rolle_detalj_view'


# ── Mannskapet ───────────────────────────────────────────────────────────────

def _mannskap_til_dict(m, foreldre=None):
    """Én person som JSON.

    `kompetanser` er de **synlige** — har hun AFØR, er VFØR implisert og
    utelates (§ kompetansestigen i `services.py`). `alle_kompetanser` er hele
    settet, fordi redigeringsskjemaet må vise det som faktisk er krysset av,
    og fordi «har hun egentlig VFØR?» skal kunne besvares uten å åpne skjemaet.

    `foreldre` slås opp én gang av kalleren; uten det ville hver rad kostet en
    spørring.
    """
    alle = list(m.kompetanser.all())
    synlige = (services.synlige_kompetanser(alle, foreldre)
               if foreldre is not None else alle)
    return {
        'id': m.pk,
        'navn': m.navn,
        'korps_id': m.korps_id,
        'korps_navn': m.korps.navn,
        'korps_kort': m.korps.kortnavn or m.korps.navn,
        'kompetanser': [{'id': k.pk, 'navn': k.navn} for k in synlige],
        'alle_kompetanser': [{'id': k.pk, 'navn': k.navn} for k in alle],
        'telefon': m.telefon,
        'user_id': m.user_id,
        'brukernavn': m.user.username if m.user else '',
        'er_aktiv': m.er_aktiv,
        'notat': m.notat,
        # Er personen satt opp noe sted, kan raden ikke slettes. Klienten
        # trenger å vite det før knappen trykkes, ikke etterpå.
        'i_bruk': m.vaktposter.count(),
    }


def _kontoer():
    """Kontoene, med hvilket mannskap hver er koblet til.

    `Mannskap.user` er en OneToOne, så en konto som alt er tatt kan ikke velges
    på nytt. Klienten trenger likevel å se den koblede kontoen når *den*
    personen redigeres — derfor sendes `mannskap_id` med, framfor at serveren
    filtrerer og etterlater et tomt nedtrekk på personen som faktisk har en
    konto.
    """
    from accounts.models import CustomUser
    return [
        {'id': u.pk, 'brukernavn': u.username,
         'mannskap_id': getattr(u, 'mannskap', None) and u.mannskap.pk}
        for u in (CustomUser.objects
                  .filter(is_active=True)
                  .select_related('mannskap')
                  .order_by('username'))
    ]


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='vaktliste:mannskap', rate='60/m', method='POST')
def mannskap_view(request):
    """Hele mannskapsregisteret (GET), eller legg til en person (POST).

    GET sender også de tre verdimengdene og de ledige kontoene: siden trenger
    alle fire for å tegne seg, og fire kall der ett holder er fire steder noe
    kan komme i utakt.

    POST er `kan_fore_korps` på **målkorpset**: korps-brukeren legger til sine
    egne folk, ikke andres.
    """
    if request.method == 'GET':
        folk = (Mannskap.objects
                .select_related('korps', 'user')
                .prefetch_related('kompetanser'))
        foreldre = services.foreldrekart()
        return JsonResponse({'status': 'ok', 'data': {
            'mannskap': [_mannskap_til_dict(m, foreldre) for m in folk],
            **{
                nokkel: [verdi_til_dict(modell, r, **kw)
                         for r in modell.objects.all()]
                for nokkel, (modell, kw) in VERDIMENGDER.items()
            },
            # Kontolista er bare med for den som kan bruke den. `user_id`
            # er `skriv_full`-felt (se under), og en liste over portalens
            # brukernavn er ikke noe en korps-fører trenger for å føre lista
            # si.
            'kontoer': _kontoer() if services.kan_skrive_alt(request.user) else [],
        }})

    data = _json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return _feil('Personen må ha et navn.')

    korps = Korps.objects.filter(pk=_int(data.get('korps_id'))).first()
    if korps is None:
        # Uten korps finnes ingen badge, og personen kan verken sorteres i
        # lista eller redigeres av en korps-bruker.
        return _feil('Velg hvilket korps personen hører til.')

    if not services.kan_fore_korps(request.user, korps.pk):
        return _nektet()

    # `user`-koblingen flytter en badge: kontoen den peker på arver korpset,
    # og dermed hva den kontoen får redigere. Den er derfor `skriv_full`, selv
    # om resten av raden er korps-førerens bord.
    full = services.kan_skrive_alt(request.user)
    if data.get('user_id') and not full:
        return _nektet('Kontokobling krever full skrivetilgang.')

    try:
        with transaction.atomic():
            person = Mannskap.objects.create(
                navn=navn,
                korps=korps,
                telefon=(data.get('telefon') or '').strip(),
                user_id=_int(data.get('user_id')) if full else None,
                notat=(data.get('notat') or '').strip(),
            )
            person.kompetanser.set(_ider(data.get('kompetanse_ider')))
    except IntegrityError:
        return _feil(f'«{navn}» finnes allerede i {korps.navn}. '
                     f'To like navn i samme korps er umulige å skille i lista.')

    person = (Mannskap.objects.select_related('korps', 'user')
              .prefetch_related('kompetanser').get(pk=person.pk))
    return JsonResponse(
        {'status': 'ok', 'data': _mannskap_til_dict(person, services.foreldrekart())},
        status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def mannskap_detalj_view(request, pk):
    """Rediger en person, eller fjern en som aldri ble satt opp.

    Gates på `services.kan_redigere_mannskap()` — badgen. To felter er likevel
    unntatt og krever `skriv_full`, fordi de ikke handler om *personen* men om
    hvem som rår over henne:

    - **`korps_id`** flytter raden ut av korps-førerens rekkevidde, eller
      henter en inn i den. Begge korps må derfor være hennes, som i praksis
      betyr at hun ikke flytter noen. Se `services.kan_flytte_mannskap`.
    - **`user_id`** flytter en badge: kontoen den peker på arver korpset.

    Sletting følger badgen, som tillegging: det er speilbildet av å legge
    inn, og PROTECT stopper det uansett i det personen har gått en vakt.
    """
    try:
        person = (Mannskap.objects.select_related('korps', 'user')
                  .prefetch_related('kompetanser').get(pk=pk))
    except Mannskap.DoesNotExist:
        return _feil('Personen finnes ikke', status=404)

    if not services.kan_redigere_mannskap(request.user, person):
        return _nektet()
    full = services.kan_skrive_alt(request.user)

    if request.method == 'DELETE':
        try:
            person.delete()
        except ProtectedError:
            return _feil(
                f'{person.navn} står på en vaktliste og kan ikke slettes. '
                f'Sett personen inaktiv i stedet — da skjules hun i '
                f'nedtrekkslistene, men blir stående der hun gikk vakt.',
                status=409)
        return JsonResponse({'status': 'ok'})

    data = _json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return _feil('Personen må ha et navn.')
        person.navn = navn
    if 'korps_id' in data:
        korps = Korps.objects.filter(pk=_int(data['korps_id'])).first()
        if korps is None:
            return _feil('Velg hvilket korps personen hører til.')
        if not services.kan_flytte_mannskap(request.user, person, korps.pk):
            return _nektet('Flytting mellom korps krever full skrivetilgang.')
        person.korps = korps
    if 'telefon' in data:
        person.telefon = (data.get('telefon') or '').strip()
    if 'notat' in data:
        person.notat = (data.get('notat') or '').strip()
    if 'er_aktiv' in data:
        person.er_aktiv = bool(data['er_aktiv'])
    if 'user_id' in data:
        if not full:
            return _nektet('Kontokobling krever full skrivetilgang.')
        person.user_id = _int(data['user_id'])

    try:
        with transaction.atomic():
            person.save()
            if 'kompetanse_ider' in data:
                person.kompetanser.set(_ider(data.get('kompetanse_ider')))
    except IntegrityError:
        return _feil(f'«{person.navn}» finnes allerede i {person.korps.navn}.')

    person = (Mannskap.objects.select_related('korps', 'user')
              .prefetch_related('kompetanser').get(pk=person.pk))
    return JsonResponse(
        {'status': 'ok', 'data': _mannskap_til_dict(person, services.foreldrekart())})
