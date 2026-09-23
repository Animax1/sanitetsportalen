"""KO-siden og endepunktene — pulje 2: loggen.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Tersklene, som er modulens tre
nivåer:

| Handling | Krav |
|---|---|
| Se siden, lese loggen og hendelsene, polle | `les` |
| Skrive en linje, rette en linje, feste og løsne en linje | `skriv_full` |
| Opprette, redigere, prioritere, lukke og gjenåpne en hendelse, bli med | `skriv_full` |
| Knytte et oppdrag til en hendelse | `skriv_full` i **både** `ko` og `oppdrag` — det skriver på oppdraget |
| Fjerne innholdet i en linje (§4.4) | `skriv_leder` |
| Sette opp ansvarsområdene (KO-innstillinger) | `skriv_leder`, eller global admin |

**Retting og fjerning er to navngitte stier**, ikke ett endepunkt som leser en
`slett`-verdi ut av kroppen. Samme grep som `backlog` sine `lost`/`gjenapne`:
et fritt ledd i kroppen er et sted å ta feil, og en navngitt sti kan leses i en
logg uten å slå opp hva som sto i den. Her betyr det dessuten at de to
tilgangsnivåene ligger på hver sin dekoratør, i stedet for i en `if` inne i et
delt view.

**Hendelsene (pulje 5) følger med logg-pollen**, ikke et eget endepunkt:
`logg_view` svarer med `hendelser` hver gang. Lista er kort (tallet hendelser i
en vakt), tavla trenger den hvert 15. sekund uansett, og en poller til mot
samme side ville vært en poller til. Skrivingen har navngitte stier.

**Flatene er kolonner, ikke faner** (17. sep. 2026). Se `ko/CLAUDE.md`: tre av
fire trengs for å fullføre én handling, og en skjult fane er en fane du ikke vet
har endret seg.

**Loggen er scopet til aktiv vakt**, og det er ikke bare et filter: `les`
betyr «denne vakta». Tidligere vakters logg er `skriv_leder` og har ennå ingen
flate — se `ko/module.py` og `TODO.md`.
"""
from __future__ import annotations

import json

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import (
    er_global_admin, har_tilgang, modul_kreves, nivaa_for,
)
from core.jsdata import js_json
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt

from . import services, systemlinjer
from .models import (MELDER_VALG, PRIORITET_VALG, Ansvarsmerke, Ansvarsomraade, Hendelse,
                     Kjennetegn, Konserttype, Logglinje)
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
        # Hendelsen linja hører til (§4.1) — id til filteret, nummeret til
        # merket «H12». Tittelen står i `hendelser` i samme svar.
        'hendelse_id': linje.hendelse_id,
        'hendelse_nummer': (linje.hendelse.hendelsesnummer
                            if linje.hendelse_id else None),
        'uformell': linje.uformell,
        # Festet (18. sep. 2026): tidspunktet sorterer de festede, navnet
        # sier hvem. Tom/`''` når linja ikke er festet.
        'festet_at': linje.festet_at.isoformat() if linje.festet_at else '',
        'festet_av': linje.festet_av_navn,
        # Deling med enhetene (19. sep. 2026): `delt_at` når linja er delt
        # med alle oppdrag i hendelsen, `delt_med` oppdragene den er delt
        # med enkeltvis. Tilstanden sendes hel i `delte` på hver poll; her
        # står den for at en nyskrevet eller rettet linje kommer riktig.
        'delt_at': linje.delt_at.isoformat() if linje.delt_at else None,
        'delt_av': linje.delt_av_navn,
        'delt_med': sorted(d.oppdrag_id for d in linje.delinger.all()),
    }


def _hendelse_til_dict(h):
    """Én hendelse, slik tavla trenger den. `apne_oppdrag`/`antall_oppdrag`
    settes av `services.hendelser_for` i én spørring; mangler de (en hendelse
    hentet alene), telles de her."""
    apne = getattr(h, 'apne_oppdrag', None)
    return {
        'id': h.pk,
        'nummer': h.hendelsesnummer,
        'kode': services.hendelsesnr(h.hendelsesnummer),
        'tittel': h.tittel,
        'lokasjon_id': h.lokasjon_id,
        'lokasjon_navn': h.lokasjon_navn,
        'status': h.status,
        'versjon': h.versjon,
        'opprettet_at': h.opprettet_at.isoformat(),
        'opprettet_av': h.opprettet_av_navn,
        'fra_linje': h.opprettet_fra_linje_id,
        'lukket_at': h.lukket_at.isoformat() if h.lukket_at else '',
        'lukket_av': h.lukket_av_navn,
        'apne_oppdrag': apne if apne is not None else services.apne_oppdrag_i(h),
        'antall_oppdrag': getattr(h, 'antall_oppdrag', None)
                          if getattr(h, 'antall_oppdrag', None) is not None
                          else h.oppdrag.count(),
        # Hodet (18. sep. 2026): prioritet, melder og hvem som er på
        # hendelsen. Alt følger med hver poll — lista er kort, og en hendelse
        # som byttet prioritet har ingen ny id.
        'prioritet': h.prioritet,
        'melder_typer': list(h.melder_typer or []),
        'melder': h.melder,
        'melder_tekst': services.melder_tekst(h),
        # Lagene på hendelsen (19. sep. 2026).
        'lag': [{'id': l.pk, 'ressurs_id': l.ressurs_id, 'navn': l.ressurs_navn,
                 'fra': l.fra.isoformat(), 'av': l.av_navn} for l in h.lag.all()],
        'deltakere': [d.brukernavn for d in h.deltakere.all()],
    }


@modul_kreves('ko', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Situasjonsbildet: loggen, ressursoversikten og oppdragslista.

    Konteksten bærer nivået fordi **grensesnittet gater på
    `window.MODUL_TILGANG`, ikke på rollen** (`CLAUDE.md`): «Fjern» skal ikke
    tegnes for en som får 403 av den, og en knapp som fører til en vegg er
    verre enn ingen knapp.

    **`med_antall` er ordforrådet det delte enhetskortet leser.**
    `oppdrag-kort.js` tegnes av begge sidene, og `_problemMedAntall()` slår opp
    her for å vite om problemstillingen bærer et pasientantall. Uten den står
    «Transport» der det skulle stått «Transport · 3 pasienter» — kortet ser
    riktig ut og er fattigere, som er den stille varianten av å mangle feature
    parity.
    """
    from oppdrag.views import sentralbordkontekst

    # **Sentralbordets kontekst i sin helhet** (pulje 4). Ikke et utvalg: en
    # verdimengde som kom til i `/oppdrag/` og ikke her ville gitt et tomt
    # nedtrekk på KO-sida, og det ser ut som en datafeil og ikke som en glemt
    # linje. Gatene i den er **oppdragsmodulens**, også her — se funksjonens
    # egen docstring.
    kontekst = sentralbordkontekst(request)
    verdifaner_ekstra = [
        {'slug': 'ansvarsomraader', 'navn': 'Ansvarsområder', 'ny': 'Nytt ansvarsområde',
         'url': '/ko/api/ansvarsomraader/'},
        # Tavla (22. sep. 2026): «På tavla» og «Følg besøk ★» per lokasjon,
        # tegnet av `koTegnTavleOppsett()` i ko-tavle.js gjennom kroken `tegn`.
        {'slug': 'tavla', 'navn': 'Tavla', 'tegn': 'koTegnTavleOppsett'},
        # Programmet (23. sep. 2026): listene konsertene velger fra. Samme
        # fabrikk som ansvarsområdene.
        {'slug': 'konserttyper', 'navn': 'Konserttyper', 'ny': 'Ny konserttype',
         'url': '/ko/api/konserttyper/'},
        {'slug': 'kjennetegn', 'navn': 'Kjennetegn', 'ny': 'Nytt kjennetegn',
         'url': '/ko/api/kjennetegn/'},
    ] if _kan_lede_ko(request) else []
    if er_global_admin(request.user):
        # «Nullstill» (André, 18. sep. 2026) — for test og utvikling; i prod
        # står admin ansvarlig. Ingen liste: fanen tegnes av
        # `koTegnNullstill()` i ko-hendelser.js, gjennom den generelle kroken
        # `tegn`, så oppdragsmodulens admin-JS fortsatt ikke kjenner KO.
        verdifaner_ekstra.append({'slug': 'nullstill', 'navn': 'Nullstill',
                                  'tegn': 'koTegnNullstill'})
    kontekst.update({
        'modul_nivaa': nivaa_for(request.user, 'ko') or '',
        'er_global_admin': er_global_admin(request.user),
        'ko_maks_tekst': services.MAKS_TEKST,
        # **Har operatøren oppdragstilgang i det hele tatt?** Uten den tegnes
        # ikke oppdragsflata — verken lista, verktøylinja eller modalene — og
        # KO står som logg og ingenting mer. Serveren nekter uansett; dette
        # avgjør om knappene finnes.
        'kan_se_oppdrag': har_tilgang(request.user, 'oppdrag', 'les'),
        # Vaktlistas ressurser uten oppdragsenhet (pulje 6) er vaktlistas
        # data, lånt inn — gaten er `les` i **vaktliste**, som besetningen.
        'kan_se_vaktliste': har_tilgang(request.user, 'vaktliste', 'les'),
        # Chat (§4.5): bryteren avgjør om avkryssingen finnes i skjemaet.
        'chat_tillatt': services.chat_tillatt(),
        # Ansvarsmerket (§5.1): nedtrekket i toppen, og hva som står nå.
        'ansvarsomraader': services.ansvarsomraader_aktive(),
        'mitt_ansvar': services.ansvar_for(request.user),
        'vakt_navn': hent_aktiv_vakt().navn,
        'kan_skrive_ko': har_tilgang(request.user, 'ko', 'skriv_full'),
        # Hendelsesskjemaet (18. sep. 2026): prioritetene, og melderne
        # (19. sep. 2026) — fast liste i kode. Lagene fylles av klienten fra
        # vaktlistas ressurser uten enhet, som alt polles.
        'prioriteter': PRIORITET_VALG,
        'prioriteter_json': js_json([list(p) for p in PRIORITET_VALG]),
        'melder_valg': MELDER_VALG,
        'melder_valg_json': js_json([list(m) for m in MELDER_VALG]),
        # KO-innstillingene — ansvarsområdene — settes opp av KOs
        # `skriv_leder` eller global admin. Sentralbordets valglister har
        # sin egen gate (`kan_lede`, oppdragsmodulens); de to vises i samme
        # vindu, men hver fane har sin egen dør.
        'kan_lede_ko': _kan_lede_ko(request),
        # Fanen legges til i sentralbordets valgliste-modal gjennom en
        # generell krok (`verdifaner_ekstra`), så `oppdrag/` ikke kjenner KO.
        'verdifaner_ekstra': verdifaner_ekstra,
        'verdifaner_ekstra_json': js_json(verdifaner_ekstra),
    })
    return render(request, 'ko/index.html', kontekst)


def _kan_lede_ko(request) -> bool:
    return (er_global_admin(request.user)
            or har_tilgang(request.user, 'ko', 'skriv_leder'))


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:ansvar', rate='60/m', method='POST')
def ansvar_view(request):
    """Sett eget ansvarsmerke (§5.1). `les` holder: merket styrer ingenting,
    og den som bare leser kan likevel ha ansvar for samband."""
    try:
        omraade = services.sett_ansvar(request.user, _json_body(request).get('omraade'))
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'omraade': omraade})


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
    # **De festede sendes hele hver gang, som `fjernede`** (18. sep. 2026):
    # festing og løsning endrer en rad uten ny id, og ville aldri kommet
    # gjennom `?siden=`. Lista er kort — en håndfull beskjeder — og klienten
    # setter merket på de id-ene som står her og tar det av resten.
    festede = [
        {'id': pk, 'festet_at': tid.isoformat(), 'festet_av': navn}
        for pk, tid, navn in Logglinje.objects
        .filter(vakt=vakt, festet_at__isnull=False)
        .values_list('pk', 'festet_at', 'festet_av_navn')
    ]
    return JsonResponse({
        'status': 'ok',
        'data': linjer,
        'fjernede': fjernede,
        'festede': festede,
        'vakt': vakt.navn,
        # Hele lista hver gang, som `fjernede`: en hendelse som lukkes eller
        # omdøpes får ingen ny id, og ville aldri kommet gjennom `?siden=`.
        'hendelser': [_hendelse_til_dict(h) for h in services.hendelser_for(vakt)],
        # Delingstilstanden, hel hver gang (19. sep. 2026) — en angret deling
        # er fravær, og fravær kommer aldri gjennom `?siden=`.
        'delte': services.delte_for_vakt(vakt),
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
    vakt = hent_aktiv_vakt()
    # `hendelse_id` gjør linja til en kommentar i hendelsen. 404 utenfor
    # vakta, som alle andre hendelsesstier.
    hendelse = None
    if data.get('hendelse_id') is not None:
        hendelse = get_object_or_404(Hendelse, pk=data['hendelse_id'], vakt=vakt)
    try:
        linje = services.skriv_linje(
            vakt,
            data.get('tekst'),
            bruker=request.user,
            tidspunkt=_tid(data.get('tidspunkt')),
            # `None` = «stemple fra merket mitt»; oppgitt verdi vinner.
            ansvarsomraade=data.get('ansvarsomraade'),
            uformell=bool(data.get('uformell')),
            hendelse=hendelse,
        )
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)}, status=201)


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_fest', rate='60/m', method='POST')
def logg_fest_view(request, pk):
    """Fest linja øverst i loggstrømmen (18. sep. 2026). `skriv_full`, som
    å skrive den — det er en beskjed på en felles tavle."""
    linje = get_object_or_404(Logglinje, pk=pk, vakt=hent_aktiv_vakt())
    try:
        services.fest_linje(linje, bruker=request.user)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_losne', rate='60/m', method='POST')
def logg_losne_view(request, pk):
    linje = get_object_or_404(Logglinje, pk=pk, vakt=hent_aktiv_vakt())
    services.losne_linje(linje, bruker=request.user)
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)})


def _oppdrag_for_deling(data, vakt):
    """`oppdrag_id` i kroppen gjør delingen individuell. 404 utenfor vakta,
    som hendelsesstiene; `None` når kroppen ikke oppgir noe."""
    if data.get('oppdrag_id') is None:
        return None
    from oppdrag.models import Oppdrag
    return get_object_or_404(Oppdrag, pk=data['oppdrag_id'], vakt=vakt)


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_del', rate='60/m', method='POST')
def logg_del_view(request, pk):
    """Del linja med enhetene (19. sep. 2026). Uten `oppdrag_id` i kroppen:
    med alle oppdrag fra hendelsen, nå og senere. `skriv_full`, som å skrive
    den — det er det samme nivået som fører loggen."""
    vakt = hent_aktiv_vakt()
    linje = get_object_or_404(Logglinje, pk=pk, vakt=vakt)
    try:
        services.del_linje(linje, bruker=request.user,
                           oppdrag=_oppdrag_for_deling(_json_body(request), vakt))
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_angre_deling', rate='60/m', method='POST')
def logg_angre_deling_view(request, pk):
    vakt = hent_aktiv_vakt()
    linje = get_object_or_404(Logglinje, pk=pk, vakt=vakt)
    try:
        services.angre_deling(linje, bruker=request.user,
                              oppdrag=_oppdrag_for_deling(_json_body(request), vakt))
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)})


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


# ── Hendelsene (pulje 5) ─────────────────────────────────────────────────────
#
# Navngitte stier, som loggen: `ny`, `rediger`, `lukk`, `gjenapne`, og
# oppdragets `hendelse`. Hver av dem er én regel i `services`, og viewet eier
# bare HTTP-en: 400 for det som ikke lar seg gjøre, 409 for en konflikt om en
# tilstand, 404 for noe utenfor vakta.

def _hendelse(pk):
    return get_object_or_404(Hendelse, pk=pk, vakt=hent_aktiv_vakt())


def _lokasjon_fra(data):
    """`(lokasjon, feil)`. `lokasjon_id` som tall gir raden, `None`/tom gir
    ingen; et ukjent tall er 400 og ikke stille `None` — en lokasjon som
    forsvinner uten å si fra er en feil man finner i loggen et døgn senere."""
    from oppdrag.models import Lokasjon

    raa = data.get('lokasjon_id')
    if raa in (None, '', 0):
        return None, None
    try:
        return Lokasjon.objects.get(pk=int(raa)), None
    except (Lokasjon.DoesNotExist, ValueError, TypeError):
        return None, 'Ukjent lokasjon.'


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_ny', rate='60/m', method='POST')
def hendelse_ny_view(request):
    """Ny hendelse — fra en logglinje (`fra_linje`) eller fra ingenting."""
    data = _json_body(request)
    vakt = hent_aktiv_vakt()
    lokasjon, feil = _lokasjon_fra(data)
    if feil:
        return _feil(feil)
    fra_linje = None
    if data.get('fra_linje'):
        fra_linje = get_object_or_404(Logglinje, pk=data['fra_linje'], vakt=vakt)
    try:
        hendelse = services.opprett_hendelse(
            vakt, data.get('tittel'), bruker=request.user,
            lokasjon=lokasjon, fra_linje=fra_linje,
            prioritet=data.get('prioritet'),
            beskrivelse=data.get('beskrivelse'),
            melder_typer=data.get('melder_typer'),
            melder=data.get('melder'),
            lag=data.get('lag'))
    except services.Ugyldig as feil:
        return _feil(str(feil))
    hendelse = services.hendelse_med_telling(hendelse)
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)},
                        status=201)


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_rediger', rate='60/m', method='POST')
def hendelse_rediger_view(request, pk):
    """Tittel og lokasjon, med `versjon` — 409 når noen andre rakk det først
    (§7.1). `lokasjon_id` sendt som `null` tømmer; utelatt rører ikke."""
    hendelse = _hendelse(pk)
    data = _json_body(request)
    lokasjon, feil = _lokasjon_fra(data)
    if feil:
        return _feil(feil)
    try:
        services.rediger_hendelse(
            hendelse, bruker=request.user, versjon=data.get('versjon'),
            tittel=data.get('tittel'),
            lokasjon=lokasjon, sett_lokasjon='lokasjon_id' in data,
            melder_typer=data.get('melder_typer'),
            melder=data.get('melder'),
            lag=data.get('lag'))
    except services.Konflikt as feil:
        return _feil(str(feil), status=409)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_prioritet', rate='60/m', method='POST')
def hendelse_prioritet_view(request, pk):
    """Prioriteten — logget som egen linje (18. sep. 2026)."""
    hendelse = _hendelse(pk)
    try:
        services.sett_prioritet(hendelse, _json_body(request).get('prioritet'),
                                bruker=request.user)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_bli_med', rate='60/m', method='POST')
def hendelse_bli_med_view(request, pk):
    """«Bli med» (18. sep. 2026). Idempotent; svarer med lista."""
    hendelse = _hendelse(pk)
    services.bli_med(hendelse, request.user)
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_lag', rate='60/m', method='POST')
def hendelse_lag_view(request, pk):
    """Lagene på hendelsen (19. sep. 2026): hele lista med ressurs-id-er,
    og tjenestelaget regner differansen og logger hvert lag som kom til
    eller gikk. Lukket hendelse tar ikke imot."""
    hendelse = _hendelse(pk)
    try:
        services.sett_lag(hendelse, _json_body(request).get('lag'), bruker=request.user)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    hendelse = services.hendelse_med_telling(hendelse)
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_lukk', rate='60/m', method='POST')
def hendelse_lukk_view(request, pk):
    """Lukk. **409 med antallet** når hendelsen har åpne oppdrag, og gjennom
    med `{"confirm": true}` (§4.6). Operatøren skal aldri møte en vegg, bare
    en dør hun må åpne bevisst."""
    hendelse = _hendelse(pk)
    try:
        services.lukk_hendelse(
            hendelse, bruker=request.user,
            confirm=bool(_json_body(request).get('confirm')))
    except services.HarApneOppdrag as feil:
        return JsonResponse({'status': 'error', 'message': str(feil),
                             'apne_oppdrag': feil.antall}, status=409)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_gjenapne', rate='60/m', method='POST')
def hendelse_gjenapne_view(request, pk):
    """Åpne igjen — logget som egen linje (André, 18. sep. 2026)."""
    hendelse = _hendelse(pk)
    try:
        services.gjenapne_hendelse(hendelse, bruker=request.user)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:oppdrag_hendelse', rate='60/m', method='POST')
def oppdrag_hendelse_view(request, pk):
    """Knytt oppdraget til en hendelse (`hendelse_id`), eller løsne det
    (`null`).

    **Krever `skriv_full` i oppdragsmodulen også**, sjekket her og ikke bare
    i dekoratøren: kallet skriver på en oppdragsrad, og hvem som får skrive på
    oppdrag er oppdragsmodulens sak (komposisjonsregelen, rollemodellen §5).
    Dekoratøren gir KO-nivået; denne linja gir det andre.
    """
    from oppdrag.models import Oppdrag

    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return _feil('Krever skrivetilgang i oppdragsmodulen.', status=403)
    vakt = hent_aktiv_vakt()
    oppdrag = get_object_or_404(Oppdrag, pk=pk, vakt=vakt)
    data = _json_body(request)
    hendelse = None
    if data.get('hendelse_id') is not None:
        hendelse = get_object_or_404(Hendelse, pk=data['hendelse_id'], vakt=vakt)
    try:
        services.knytt_oppdrag(oppdrag, hendelse, bruker=request.user)
    except services.Ugyldig as feil:
        return _feil(str(feil))
    return JsonResponse({'status': 'ok', 'hendelse_id': oppdrag.hendelse_id})


# ── KO-innstillingene: ansvarsområdene (18. sep. 2026) ───────────────────────
#
# Samme form som `oppdrag/views_verdier.py`: liste for `les`, opprett/endre/
# omsortere for leder (KO-leder eller global admin), sletting for global admin
# med `confirm` og 409 når raden er i bruk. Én fabrikk — skrevet her og ikke
# som rader i oppdragsmodulens `VERDIMENGDER`, fordi tabellen er KOs og
# `oppdrag` ikke kjenner `ko`. Fabrikken bar også `Ressursbehov` fra 18. til
# 19. sep. 2026; lista ble erstattet av lagene fra vaktlista (`HendelseLag`).

class _Verdiliste:
    """Én tabell: modellen, slugen og hva som teller som «i bruk»."""

    def __init__(self, model, slug, maks, i_bruk):
        self.model, self.slug, self.maks, self.i_bruk = model, slug, maks, i_bruk

    def til_dict(self, rad):
        return {'id': rad.pk, 'navn': rad.navn, 'er_aktiv': rad.er_aktiv,
                'rekkefolge': rad.rekkefolge, 'i_bruk': self.i_bruk(rad)}

    def valider_navn(self, navn, *, unntatt_pk=None):
        if not navn:
            return 'Navn kan ikke være tomt.'
        if len(navn) > self.maks:
            return f'Navnet er for langt (maks {self.maks} tegn).'
        if self.model.objects.filter(navn__iexact=navn).exclude(pk=unntatt_pk).exists():
            return f'«{navn}» finnes allerede.'
        return None


VERDILISTER = {
    # I bruk = kontoer som bærer merket nå. Linjene teller ikke: de er tekst,
    # og et område som slettes skal ikke skrive om loggen.
    'ansvarsomraader': _Verdiliste(Ansvarsomraade, 'ansvarsomraader', 40,
                                   lambda r: Ansvarsmerke.objects.filter(omraade=r.navn).count()),
    # Programmet (tavleplanleggeren, steg 2). I bruk = konserter som peker
    # dit, i alle vakter: en type fjorårets program står med, slettes ikke.
    'konserttyper': _Verdiliste(Konserttype, 'konserttyper', 60, lambda r: r.poster.count()),
    'kjennetegn': _Verdiliste(Kjennetegn, 'kjennetegn', 60, lambda r: r.poster.count()),
}


def _liste_view(slug):
    vl = VERDILISTER[slug]

    @never_cache
    @modul_kreves('ko', 'les', svar='json')
    @require_http_methods(['GET', 'POST'])
    @rate_limit(group=f'ko:{slug}', rate='60/m', method='POST')
    def view(request):
        if request.method == 'GET':
            return JsonResponse({'status': 'ok', 'data': [
                vl.til_dict(r) for r in vl.model.objects.all()]})
        if not _kan_lede_ko(request):
            return _feil('Å sette opp KO-innstillingene er skriv_leder i KO.', 403)
        navn = (_json_body(request).get('navn') or '').strip()
        feil = vl.valider_navn(navn)
        if feil:
            return _feil(feil)
        siste = (vl.model.objects.order_by('-rekkefolge')
                 .values_list('rekkefolge', flat=True).first())
        rad = vl.model.objects.create(navn=navn, rekkefolge=(siste or 0) + 10)
        return JsonResponse({'status': 'ok', 'data': vl.til_dict(rad)})

    view.__name__ = f'{slug}_view'
    return view


def _detalj_view(slug):
    vl = VERDILISTER[slug]

    @modul_kreves('ko', 'les', svar='json')
    @require_http_methods(['PUT', 'DELETE'])
    @rate_limit(group=f'ko:{slug}_detalj', rate='60/m', method=['PUT', 'DELETE'])
    def view(request, pk):
        if not _kan_lede_ko(request):
            return _feil('Å sette opp KO-innstillingene er skriv_leder i KO.', 403)
        rad = get_object_or_404(vl.model, pk=pk)
        data = _json_body(request)
        if request.method == 'DELETE':
            if not er_global_admin(request.user):
                return _feil('Sletting er global admin.', 403)
            if not data.get('confirm'):
                return _feil('Bekreftelse mangler. Send {"confirm": true}.')
            brukt = vl.i_bruk(rad)
            if brukt:
                return _feil(f'«{rad.navn}» er i bruk ({brukt}) og kan ikke slettes. '
                             'Deaktiver den i stedet.', 409)
            rad.delete()
            return JsonResponse({'status': 'ok'})
        if 'navn' in data:
            navn = (data.get('navn') or '').strip()
            feil = vl.valider_navn(navn, unntatt_pk=rad.pk)
            if feil:
                return _feil(feil)
            rad.navn = navn
        if 'er_aktiv' in data:
            rad.er_aktiv = bool(data['er_aktiv'])
        rad.save()
        return JsonResponse({'status': 'ok', 'data': vl.til_dict(rad)})

    view.__name__ = f'{slug}_detalj_view'
    return view


def _rekkefolge_view(slug):
    vl = VERDILISTER[slug]

    @modul_kreves('ko', 'les', svar='json')
    @require_http_methods(['PUT'])
    @rate_limit(group=f'ko:{slug}_rekkefolge', rate='30/m', method='PUT')
    def view(request):
        """Hele lista, som i oppdragsmodulen: to «opp» som krysser hverandre
        i nettet gir ellers en rekkefølge ingen ba om."""
        if not _kan_lede_ko(request):
            return _feil('Å sette opp KO-innstillingene er skriv_leder i KO.', 403)
        ider = _json_body(request).get('ider')
        if not isinstance(ider, list) or not all(isinstance(i, int) for i in ider):
            return _feil('Send `ider` som en liste med tall.')
        rader = {r.pk: r for r in vl.model.objects.filter(pk__in=ider)}
        if len(rader) != len(set(ider)):
            return _feil('Lista inneholder ukjente rader — hent den på nytt.')
        for plass, rad_pk in enumerate(ider):
            rad = rader[rad_pk]
            ny = (plass + 1) * 10
            if rad.rekkefolge != ny:
                rad.rekkefolge = ny
                rad.save(update_fields=['rekkefolge'])
        return JsonResponse({'status': 'ok', 'data': [
            vl.til_dict(r) for r in vl.model.objects.all()]})

    view.__name__ = f'{slug}_rekkefolge_view'
    return view


ansvarsomraader_view = _liste_view('ansvarsomraader')
ansvarsomraade_detalj_view = _detalj_view('ansvarsomraader')
ansvarsomraader_rekkefolge_view = _rekkefolge_view('ansvarsomraader')
konserttyper_view = _liste_view('konserttyper')
konserttype_detalj_view = _detalj_view('konserttyper')
konserttyper_rekkefolge_view = _rekkefolge_view('konserttyper')
kjennetegn_view = _liste_view('kjennetegn')
kjennetegn_detalj_view = _detalj_view('kjennetegn')
kjennetegn_rekkefolge_view = _rekkefolge_view('kjennetegn')


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
        return _feil('Ukjent nullstilling.', 404)
    if not er_global_admin(request.user):
        return _feil('Nullstilling er global admin.', 403)
    if not _json_body(request).get('confirm'):
        return _feil('Bekreftelse mangler.', status=400)
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


# ── Tavla (22. sep. 2026) ─────────────────────────────────────────────────────
#
# **Tavla viser vaktlistas ressurser, så gaten er vaktlistas også** — `les` i
# vaktlista, som ressursoversikten og besetningen. Bilene og oppdragene på dem
# tas med bare for den som ser oppdragene: KO *viser* modulenes data, og hvem
# som får se dem er modulens sak (komposisjonsregelen, rollemodellen §5).

def _tavle_gate(request):
    if not har_tilgang(request.user, 'vaktliste', 'les'):
        return _feil('Tavla viser vaktlistas ressurser, og krever lesetilgang i vaktlista.', 403)
    return None


def _tavle_ressurs(request, data):
    """Ressursen i kroppen — og **en bil bare med lesetilgang i
    oppdragsmodulen**, samme regel som `tavle_view` bruker for å vise den. En
    bil man ikke får se, finnes ikke: 404, ikke 403."""
    from vaktliste.models import Ressurs
    try:
        ressurs = Ressurs.objects.get(pk=int(data.get('ressurs_id')))
    except (Ressurs.DoesNotExist, TypeError, ValueError):
        return None
    if ressurs.enhet_id is not None and not har_tilgang(request.user, 'oppdrag', 'les'):
        return None
    return ressurs


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:tavle', rate='240/m', method='GET')
def tavle_view(request):
    """Alt tavla trenger, i ett svar. Polles som loggen."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = tavle.tavle_data(hent_aktiv_vakt(),
                            med_biler=har_tilgang(request.user, 'oppdrag', 'les'))
    return JsonResponse({'status': 'ok', 'data': data})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_plasser', rate='120/m', method='POST')
def tavle_plasser_view(request):
    """Sett en ledig ressurs på en lokasjon, eller i pause, fra nå."""
    from oppdrag.models import Lokasjon

    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = _json_body(request)
    ressurs = _tavle_ressurs(request, data)
    if ressurs is None:
        return _feil('Ukjent ressurs.', 404)
    lokasjon = None
    if not data.get('pause'):
        try:
            lokasjon = Lokasjon.objects.get(pk=int(data.get('lokasjon_id')))
        except (Lokasjon.DoesNotExist, TypeError, ValueError):
            return _feil('Ukjent lokasjon.', 404)
    try:
        p = tavle.plasser(hent_aktiv_vakt(), ressurs, bruker=request.user,
                          lokasjon=lokasjon, pause=bool(data.get('pause')))
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok', 'data': {'id': p.pk}})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_uten_plass', rate='120/m', method='POST')
def tavle_uten_plass_view(request):
    """Ta ressursen av tavla — dit man drar den når den ikke står noe sted."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    ressurs = _tavle_ressurs(request, _json_body(request))
    if ressurs is None:
        return _feil('Ukjent ressurs.', 404)
    try:
        tavle.avslutt(hent_aktiv_vakt(), ressurs, bruker=request.user)
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok'})


# ── Tavla, steg 2: retting, pauser, oppsett ──────────────────────────────────

def _tavle_tid(raa, hva):
    """Et tidspunkt fra tavlas skjemaer. **Ugyldig er en 400 her**, ikke «nå»
    som i loggen: en retting som stille ble til nå, har skrevet om historikken
    til noe ingen ba om."""
    t = parse_datetime(raa) if isinstance(raa, str) and raa else None
    if t is None or timezone.is_naive(t):
        raise services.Ugyldig(f'«{hva}» mangler eller er ikke et tidspunkt.')
    return t


def _bil_skjult(request, ressurs_id) -> bool:
    """En bil man ikke får se uten oppdragstilgang (som `_tavle_ressurs`)."""
    from vaktliste.models import Ressurs
    if ressurs_id is None or har_tilgang(request.user, 'oppdrag', 'les'):
        return False
    return Ressurs.objects.filter(pk=ressurs_id, enhet__isnull=False).exists()


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='ko:tavle_rett', rate='60/m', method=['PUT', 'DELETE'])
def tavle_plassering_view(request, pk):
    """Rett tidene på en plassering, sett den planlagte slutten, eller fjern
    den (skisse 3; planlagt slutt 23. sep. 2026)."""
    from . import tavle
    from .models import Tavleplassering

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    p = Tavleplassering.objects.filter(pk=pk, vakt=hent_aktiv_vakt()).first()
    if p is None or _bil_skjult(request, p.ressurs_id):
        return _feil('Ukjent plassering.', 404)
    data = _json_body(request)
    try:
        if request.method == 'DELETE':
            tavle.fjern(p, bruker=request.user)
            return JsonResponse({'status': 'ok'})
        if 'fra' not in data and 'planlagt_til' not in data and 'folger_id' not in data:
            raise services.Ugyldig('Ingenting å endre.')
        # Tidene og den planlagte slutten i ett: feiler den ene, er heller
        # ikke den andre lagret — skjemaet sendte dem som én ting.
        with transaction.atomic():
            if 'fra' in data:
                fra = _tavle_tid(data.get('fra'), 'Fra')
                til = _tavle_tid(data.get('til'), 'Til') if p.til is not None else None
                tavle.rett(p, fra=fra, til=til, bruker=request.user)
            if data.get('folger_id'):
                # «Følger konserten» (steg 2) går foran en egen tid.
                from . import program
                from .models import Programpost
                post = Programpost.objects.filter(pk=_heltall_eller_none(data.get('folger_id'))).first()
                if post is None:
                    raise services.Ugyldig('Ukjent konsert.')
                program.folg(p, post, naa=timezone.now())
            elif 'planlagt_til' in data or 'folger_id' in data:
                # Tomt er «ingen plan»; noe annet enn et tidspunkt er en feil.
                raa = data.get('planlagt_til')
                slutt = _tavle_tid(raa, 'Planlagt slutt') if raa else None
                tavle.sett_planlagt_slutt(p, slutt)
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok'})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_pauser', rate='60/m', method='POST')
def tavle_pauser_view(request):
    """Planlegg en pause for et lag (skisse 2, «+ Planlegg»)."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = _json_body(request)
    ressurs = _tavle_ressurs(request, data)
    if ressurs is None:
        return _feil('Ukjent ressurs.', 404)
    try:
        q = tavle.planlegg_pause(hent_aktiv_vakt(), ressurs, bruker=request.user,
                                 fra=_tavle_tid(data.get('fra'), 'Fra'),
                                 til=_tavle_tid(data.get('til'), 'Til'))
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok', 'data': {'id': q.pk}})


def _tavle_pause(request, pk):
    from .models import PlanlagtPause
    q = PlanlagtPause.objects.filter(pk=pk, vakt=hent_aktiv_vakt()).first()
    if q is None or _bil_skjult(request, q.ressurs_id):
        return None
    return q


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='ko:tavle_pause', rate='60/m', method=['PUT', 'DELETE'])
def tavle_pause_view(request, pk):
    """Endre eller fjern en planlagt pause."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    q = _tavle_pause(request, pk)
    if q is None:
        return _feil('Ukjent pause.', 404)
    data = _json_body(request)
    try:
        if request.method == 'DELETE':
            tavle.slett_pause(q)
            return JsonResponse({'status': 'ok'})
        tavle.planlegg_pause(q.vakt, q.ressurs, pause=q, bruker=request.user,
                             fra=_tavle_tid(data.get('fra'), 'Fra'),
                             til=_tavle_tid(data.get('til'), 'Til'))
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok'})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_pause_start', rate='60/m', method='POST')
def tavle_pause_start_view(request, pk):
    """«Pause nå»: KO starter den; tavla flytter ingen av seg selv."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    q = _tavle_pause(request, pk)
    if q is None:
        return _feil('Ukjent pause.', 404)
    try:
        tavle.start_pause(q, bruker=request.user)
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok'})


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET', 'PUT'])
@rate_limit(group='ko:tavle_oppsett', rate='30/m', method='PUT')
def tavle_oppsett_view(request):
    """KO-innstillinger, fanen «Tavla»: per lokasjon «På tavla» og «Følg
    besøk ★». Å lese er `les`; å endre er KO-lederens (`skriv_leder`), som
    resten av KO-innstillingene."""
    from oppdrag.models import Lokasjon

    from . import tavle

    if request.method == 'PUT':
        if not _kan_lede_ko(request):
            return _feil('Å sette opp tavla er skriv_leder i KO.', 403)
        data = _json_body(request)
        try:
            tavle.lagre_oppsett(skjulte_ider=data.get('skjulte'), fulgte_ider=data.get('fulgte'))
        except services.Ugyldig as e:
            return _feil(str(e))
    ute, fulgt = set(tavle.skjulte()), set(tavle.fulgte())
    return JsonResponse({'status': 'ok', 'data': [{
        'id': l.pk, 'navn': l.navn, 'paa_tavla': l.pk not in ute, 'fulgt': l.pk in fulgt,
    } for l in Lokasjon.objects.filter(er_aktiv=True).order_by('rekkefolge', 'navn')]})


# ── Programmet (tavleplanleggeren, steg 2 — 23. sep. 2026) ───────────────────
#
# **Å lese er `les` i KO, å skrive er KO-lederens** (André: «KO-leder»), både
# før og under vakta. Behovet peker på vaktlistas ressursgrupper, men bærer
# bare navnene deres — ingen vaktlistedata om personer — så gaten er KOs egen.

def _heltall_eller_none(raa):
    try:
        return int(raa)
    except (TypeError, ValueError):
        return None


def _program_tider(data):
    return _tavle_tid(data.get('fra'), 'Fra'), _tavle_tid(data.get('til'), 'Til')


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='ko:program', rate='60/m', method='POST')
def program_view(request):
    """Programmet for aktiv vakt, og valgene skjemaet trenger. POST lager en
    ny konsert."""
    from . import program

    vakt = hent_aktiv_vakt()
    if request.method == 'POST':
        if not _kan_lede_ko(request):
            return _feil('Å legge programmet er KO-lederens (skriv_leder i KO).', 403)
        data = _json_body(request)
        try:
            fra, til = _program_tider(data)
            post = program.lagre_post(vakt, data, fra=fra, til=til, bruker=request.user)
        except services.Ugyldig as e:
            return _feil(str(e))
        return JsonResponse({'status': 'ok', 'data': program.til_dict(post)})
    return JsonResponse({'status': 'ok', 'data': program.program_data(vakt)})


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='ko:program_post', rate='60/m', method=['PUT', 'DELETE'])
def program_post_view(request, pk):
    """Endre eller slett en konsert i aktiv vakt."""
    from . import program
    from .models import Programpost

    if not _kan_lede_ko(request):
        return _feil('Å legge programmet er KO-lederens (skriv_leder i KO).', 403)
    post = Programpost.objects.filter(pk=pk, vakt=hent_aktiv_vakt()).first()
    if post is None:
        return _feil('Ukjent konsert.', 404)
    if request.method == 'DELETE':
        program.slett_post(post, bruker=request.user)
        return JsonResponse({'status': 'ok'})
    data = _json_body(request)
    try:
        fra, til = _program_tider(data)
        post = program.lagre_post(post.vakt, data, fra=fra, til=til, bruker=request.user, post=post)
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok', 'data': program.til_dict(post)})


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:program_dekning', rate='60/m', method='GET')
def program_dekning_view(request):
    """Dekningsstripa i planleggeren (steg 4): på vakt per ressursgruppe, time
    for time, i døgnet `?dogn=YYYY-MM-DD`. **Tallene er vaktlistas**, så
    gaten er vaktlistas også — som tavla."""
    from . import program

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    start = program.dogn_start(request.GET.get('dogn', ''))
    if start is None:
        return _feil('Oppgi døgnet som ?dogn=ÅÅÅÅ-MM-DD.')
    return JsonResponse({'status': 'ok', 'data': {'timer': program.paa_vakt_per_time(start)}})


# ── Plan mot faktisk og kopiering (steg 5) ──────────────────────────────────
#
# **Aktiv vakt er `les`; tidligere vakter er KO-lederens** — samme skille som
# loggen (dataminimering). Programmet selv bærer ingen personopplysninger,
# men tabellen ved siden av teller oppdrag, og regelen skal være én.

def _program_vakt(request):
    from core.models import Vakt
    aktiv = hent_aktiv_vakt()
    raa = request.GET.get('vakt')
    if not raa:
        return aktiv, None
    vakt = Vakt.objects.filter(pk=_heltall_eller_none(raa)).first()
    if vakt is None:
        return None, _feil('Ukjent vakt.', 404)
    if vakt.pk != aktiv.pk and not _kan_lede_ko(request):
        return None, _feil('Tidligere vakter er KO-lederens (skriv_leder i KO).', 403)
    return vakt, None


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:program_etterpaa', rate='60/m', method='GET')
def program_etterpaa_view(request):
    """Plan mot faktisk per konsert, og historikken, for en vakt."""
    from core.models import Vakt

    from . import program
    from .models import Programpost

    vakt, feil = _program_vakt(request)
    if feil:
        return feil
    data = {'vakt': {'id': vakt.pk, 'navn': vakt.navn},
            'poster': program.plan_mot_faktisk(vakt),
            'endringer': program.endringer(vakt),
            'vakter': []}
    if _kan_lede_ko(request):
        med_program = set(Programpost.objects.values_list('vakt_id', flat=True).distinct())
        data['vakter'] = [{'id': v.pk, 'navn': v.navn, 'aar': v.year}
                          for v in Vakt.objects.filter(pk__in=med_program | {vakt.pk}).order_by('-startet')]
    return JsonResponse({'status': 'ok', 'data': data})


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:program_kopier', rate='10/m', method='POST')
def program_kopier_view(request):
    """«Kopier programmet» fra en tidligere vakt inn i aktiv vakt.

    **Har aktiv vakt alt et program, er det en 409 med antallet** — kopien
    legges til, den erstatter ingenting, og to programmer oppå hverandre er
    ikke noe man skal få ved et feilklikk. `{"confirm": true}` går gjennom.
    """
    from datetime import date

    from core.models import Vakt

    from . import program
    from .models import Programpost

    if not _kan_lede_ko(request):
        return _feil('Å legge programmet er KO-lederens (skriv_leder i KO).', 403)
    data = _json_body(request)
    aktiv = hent_aktiv_vakt()
    kilde = Vakt.objects.filter(pk=_heltall_eller_none(data.get('fra_vakt_id'))).first()
    if kilde is None or kilde.pk == aktiv.pk:
        return _feil('Velg en annen vakt å kopiere fra.')
    try:
        forste = date.fromisoformat(str(data.get('forste_dogn') or ''))
    except ValueError:
        return _feil('Oppgi første konsertdøgn som ÅÅÅÅ-MM-DD.')
    har = Programpost.objects.filter(vakt=aktiv).count()
    if har and not data.get('confirm'):
        return JsonResponse({'status': 'error', 'message':
                             f'Aktiv vakt har alt {har} i programmet. Kopien legges til ved siden av, ingenting erstattes. Fortsette?',
                             'antall': har}, status=409)
    try:
        svar = program.kopier_program(kilde, aktiv, forste_dogn=forste, bruker=request.user)
    except services.Ugyldig as e:
        return _feil(str(e))
    return JsonResponse({'status': 'ok', 'data': svar})
