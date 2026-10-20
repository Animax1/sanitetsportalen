"""KO-siden og endepunktene — pulje 2: loggen.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Tersklene, som er modulens tre
nivåer:

| Handling | Krav |
|---|---|
| Se siden, lese loggen og hendelsene, polle | `les` |
| Skrive ut KO (`/ko/utskrift/`), alle vinduene | `les` — ressursene, oppdragene og tavla med sine modulers gater |
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
en vakt), loggen hentes uansett når endringsnummeret går opp (2,5 s, med 30 s
som sikkerhetsnett), og en poller til mot samme side ville vært en poller til. Skrivingen har navngitte stier.

**Flatene er kolonner, ikke faner** (17. sep. 2026). Se `ko/CLAUDE.md`: tre av
fire trengs for å fullføre én handling, og en skjult fane er en fane du ikke vet
har endret seg.

**Delt etter flate** (G2, 13. okt. 2026) — tabellen over gjelder alle filene:

| Fil | Flaten |
|---|---|
| `views.py` | Siden, loggen, ansvar, tilstede — og hjelperne de andre bruker |
| `views_hendelser.py` | Hendelsenes skrivestier og knyttingen av oppdrag |
| `views_innstillinger.py` | Verdilistene og «Nullstill» |
| `views_tavle.py` | Tavla |
| `views_program.py` | Programmet; bruker tavlas `_tavle_gate` og `_tavle_tid` |
| `views_utskrift.py` | Utskriften og service workeren |

Retningen er inn mot denne fila: den importerer ingen av de andre, og
`views_program` → `views_tavle` er den ene kanten mellom dem.

**Loggen er scopet til aktiv vakt**, og det er ikke bare et filter: `les`
betyr «denne vakta». Tidligere vakters logg er `skriv_leder` og har ennå ingen
flate — se `ko/module.py` og `TODO.md`.
"""
from __future__ import annotations


from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import (
    er_global_admin, er_moderator, har_tilgang, modul_kreves, nivaa_for,
)
from core.jsonkropp import json_body, json_feil
from core import kartkobling
from core.jsdata import js_json
from core.middleware import csp_med_skjemamaal
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt

from . import services, systemlinjer
from .models import MELDER_VALG, PRIORITET_VALG, EksternRessurs, Hendelse, Logglinje, Talegruppe
from .tilstede import tilstede
from .utskrift import KOPI_MINUTTER, kan_lagres_lokalt


# ── Hjelpere ─────────────────────────────────────────────────────────────────

def _tid(raa):
    """Et klokkeslett fra klienten, eller `None`.

    `None` betyr «bruk servertid», og det er den vanlige veien: operatøren
    trykker og linja får tida nå. En **ugyldig** streng blir også `None` og
    ikke en 400 — `services.vurder_tidspunkt` eier hva som er lov, og to
    steder som avviser tid ville før eller siden vært uenige.
    """
    return parse_datetime(raa) if isinstance(raa, str) and raa else None


# Brukt av tavla og programmet, som ligger i hver sin fil fra G2 (13. okt. 2026).
def _heltall_eller_none(raa):
    try:
        return int(raa)
    except (TypeError, ValueError):
        return None


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
        # Beskrivelsen i hodet (19. okt. 2026): roten i kjeden. Klienten har
        # alle linjene nøklet på rot (`koLinjer`), så gjeldende versjon er et
        # oppslag der og ikke en spørring per hendelse her.
        'beskrivelse_rot': h.beskrivelse_linje_id,
        # Talegruppa i Nødnett, og om bilene ser den (19. okt. 2026).
        'talegruppe': h.talegruppe,
        'talegruppe_delt': h.talegruppe_delt,
        # De eksterne ressursene som er varslet (19. okt. 2026).
        'varslinger': [{'ressurs_id': v.ressurs_id, 'navn': v.navn,
                        'tid': v.varslet_at.isoformat(), 'av': v.av_navn}
                       for v in h.varslinger.all()],
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
    lagret = services.lagret_oppsett(request.user)
    verdifaner_ekstra = [
        {'slug': 'ansvarsomraader', 'navn': 'Ansvarsområder', 'ny': 'Nytt ansvarsområde',
         'url': '/ko/api/ansvarsomraader/'},
        # Tavla (22. sep. 2026): «På tavla» og «Følg besøk ★» per lokasjon,
        # tegnet av `koTegnTavleOppsett()` i ko-tavle.js gjennom kroken `tegn`.
        {'slug': 'tavla', 'navn': 'Tavla', 'tegn': 'koTegnTavleOppsett'},
        # Programmet (23. sep. 2026): listene konsertene velger fra. Samme
        # fabrikk som ansvarsområdene.
        # «Konserttyper» ble «Artister» 23. sep. 2026 (André); URL-en står.
        {'slug': 'konserttyper', 'navn': 'Artister', 'ny': 'Ny artist',
         'url': '/ko/api/konserttyper/'},
        {'slug': 'kjennetegn', 'navn': 'Kjennetegn', 'ny': 'Nytt kjennetegn',
         'url': '/ko/api/kjennetegn/'},
        # Eksterne ressurser (19. okt. 2026): hvem hendelsen kan krysse av
        # som varslet.
        {'slug': 'eksterne', 'navn': 'Eksterne ressurser', 'ny': 'Ny ekstern aktør',
         'url': '/ko/api/eksterne/'},
    ] if _kan_lede_ko(request) else []
    # Talegruppene (19. okt. 2026) har sin egen dør: KO-leder, moderator i
    # portalen eller admin. En moderator uten `skriv_leder` i KO ser bare denne
    # fanen — ikke resten av KO-innstillingene.
    if kan_sette_opp_talegrupper(request.user):
        verdifaner_ekstra.append({'slug': 'talegrupper', 'navn': 'Talegrupper (TG)',
                                  'ny': 'Ny talegruppe', 'url': '/ko/api/talegrupper/'})
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
        # Utskriften uten nett (13. okt. 2026): KO-siden henter den i
        # bakgrunnen bare for personlige kontoer — se `ko/utskrift.py`.
        'ko_kopi': kan_lagres_lokalt(request.user),
        'ko_kopi_minutter': KOPI_MINUTTER,
        'kan_skrive_ko': har_tilgang(request.user, 'ko', 'skriv_full'),
        # Hendelsesskjemaet (18. sep. 2026): prioritetene, og melderne
        # (19. sep. 2026) — fast liste i kode. Lagene fylles av klienten fra
        # vaktlistas ressurser uten enhet, som alt polles.
        'prioriteter': PRIORITET_VALG,
        'prioriteter_json': js_json([list(p) for p in PRIORITET_VALG]),
        'melder_valg': MELDER_VALG,
        'melder_valg_json': js_json([list(m) for m in MELDER_VALG]),
        # Eksterne ressurser (19. okt. 2026): de aktive, til avkryssingen i
        # hodet. Lest ved sidelasting, som ansvarsområdene — en ny rad under
        # KO-innstillinger vises etter neste lasting. Varslinger som alt står
        # på en hendelse, vises uansett: de bærer navnet selv.
        'eksterne_json': js_json([{'id': r.pk, 'navn': r.navn}
                                  for r in EksternRessurs.objects.i_portal().filter(er_aktiv=True)]),
        # Talegruppene (19. okt. 2026): navnene til nedtrekket i hodet.
        'talegrupper_json': js_json(list(Talegruppe.objects.i_portal().filter(er_aktiv=True)
                                         .values_list('navn', flat=True))),
        # KO-innstillingene — ansvarsområdene — settes opp av KOs
        # `skriv_leder` eller global admin. Sentralbordets valglister har
        # sin egen gate (`kan_lede`, oppdragsmodulens); de to vises i samme
        # vindu, men hver fane har sin egen dør.
        'kan_lede_ko': _kan_lede_ko(request),
        # Fanen legges til i sentralbordets valgliste-modal gjennom en
        # generell krok (`verdifaner_ekstra`), så `oppdrag/` ikke kjenner KO.
        'verdifaner_ekstra': verdifaner_ekstra,
        'verdifaner_ekstra_json': js_json(verdifaner_ekstra),
        # «Åpne kartet» (19. okt. 2026): bare når miljøet har nøkkelen og admin har slått
        # den på. Gaten står også i `kart_view`, så knappen er ikke den eneste døra.
        'kart_innlogging': kartkobling.innlogging_paa(),
        # «Lagre oppsettet» (20. okt. 2026): det kontoen har lagret, til når nettleserens kopi er
        # tom — etter «Logg ut», eller på en annen PC. `js_json`, som alt inn i et skript.
        'lagret_oppsett_json': js_json(lagret.oppsett if lagret else None),
        'lagret_oppsett_tid': lagret.lagret_at if lagret else None,
    })
    return render(request, 'ko/index.html', kontekst)


@modul_kreves('ko', 'les')
@require_http_methods(['POST'])
@rate_limit(group='ko:kart', rate='30/m', method='POST', on_limit='html')
def kart_view(request):
    """«Åpne kartet»: lag en billett og post den videre til kartet (`docs/PLAN_FELLES_INNLOGGING.md`).

    **KO `les` er nok** — den som ser situasjonsbildet, ser kartet. `skriv_full` gir et kart man
    kan tegne i; nivået står i billetten, og kartet håndhever det.

    **POST, ikke en lenke.** Billetten skal ikke stå i en URL, der den havner i historikk, logger
    og `Referer`. Svaret er en side som poster videre med det samme, og CSP-ens `form-action`
    får kartets vert på akkurat dette svaret, ikke på resten av portalen.

    **Portalen er den brukeren står i nå**, og slugen går inne i den signerte billetten: sto den
    ved siden av, kunne den som har KO i én portal bedt om en annens biler og lag.
    """
    from core.portal import gjeldende_portal

    if not kartkobling.innlogging_paa():
        return render(request, '403.html', {
            'tittel': 'Kartet er ikke slått på',
            'melding': 'Innlogging i kartet fra KO er slått av eller ikke satt opp i dette miljøet.',
        }, status=403)
    bruker = request.user
    billett = kartkobling.lag_billett(
        bruker_id=bruker.pk,
        navn=(bruker.fullt_navn or bruker.username).strip(),
        portal=gjeldende_portal().slug,
        skriv=har_tilgang(bruker, 'ko', 'skriv_full'),
    )
    svar = render(request, 'ko/kart_videre.html',
                  {'kart_url': kartkobling.innlogging_url(), 'billett': billett})
    svar['Content-Security-Policy'] = csp_med_skjemamaal(
        request, kartkobling.kart_opprinnelse())
    return svar


def kan_lede_ko(user) -> bool:
    """Setter opp KO-innstillingene. Én regel for knappen og for endepunktene
    i verdilistefabrikken. Global admin trenger ingen egen `or`: `nivaa_for`
    gir toppen av stigen."""
    return har_tilgang(user, 'ko', 'skriv_leder')


def kan_sette_opp_talegrupper(user) -> bool:
    """Talegruppelista: KO-leder, moderator i portalen, eller global admin
    (André, 19. okt. 2026). Admin er med gjennom `kan_lede_ko` (`nivaa_for`)."""
    return kan_lede_ko(user) or er_moderator(user)


def _kan_lede_ko(request) -> bool:
    return kan_lede_ko(request.user)


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:ansvar', rate='60/m', method='POST')
def ansvar_view(request):
    """Sett eget ansvarsmerke (§5.1). `les` holder: merket styrer ingenting,
    og den som bare leser kan likevel ha ansvar for samband."""
    try:
        omraade = services.sett_ansvar(request.user, json_body(request).get('omraade'))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'omraade': omraade})


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:oppsett', rate='30/m', method='POST')
def oppsett_view(request):
    """«Lagre oppsettet» (20. okt. 2026): vinduenes oppsett på kontoen, i portalen man står i.

    `les` holder: oppsettet er ens eget og styrer ingen andre. Raden er alltid den innloggedes —
    kroppen bærer ingen bruker å velge, så ingen kan lagre på en annens konto.
    """
    try:
        rad = services.lagre_oppsett(request.user, json_body(request).get('oppsett'))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'lagret': rad.lagret_at.isoformat()})


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

    **Pollingen er den ene spørringen som går hele vakta**, fra hver operatør —
    hver gang endringsnummeret går opp (spurt hvert 2,5 s), og ellers hvert
    30. s. Derfor `?siden=` og ikke en full henting: en logg på fire hundre
    linjer sendt for hver endring til seks skjermer er en kostnad uten en gevinst.

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
            return json_feil('«siden» må være et tall.')

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
        # Nytt siden *denne brukeren* sist hadde hendelsen framme (27. sep.
        # 2026). For seg og ikke i hver hendelse: hendelsene er like for alle,
        # dette er per konto.
        'nye': {str(k): v for k, v in services.nye_for(request.user, vakt).items()},
        # Delingstilstanden, hel hver gang (19. sep. 2026) — en angret deling
        # er fravær, og fravær kommer aldri gjennom `?siden=`.
        'delte': services.delte_for_vakt(vakt),
        # Hvem står på pause nå (20. okt. 2026), hel hver gang: en pause som slutter, er fravær.
        'pauser': _pauser_for(request.user, vakt),
    })


def _pauser_for(bruker, vakt) -> list[dict]:
    """Pausene fra tavla, **med hver kildes gate** (rollemodellen §5): et lag er vaktlistas, og
    vises med `les` der; en bil vises med `les` i oppdrag, som bilkortet selv. Uten noen av dem
    er lista tom — KO `les` alene gir ingen innsyn i ressursene."""
    from . import tavle

    lag = har_tilgang(bruker, 'vaktliste', 'les')
    biler = har_tilgang(bruker, 'oppdrag', 'les')
    return [p for p in tavle.paa_pause(vakt) if (biler if p['enhet_id'] else lag)]


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
    data = json_body(request)
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
        return json_feil(str(feil))
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
        return json_feil(str(feil))
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
                           oppdrag=_oppdrag_for_deling(json_body(request), vakt))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _til_dict(linje)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:logg_angre_deling', rate='60/m', method='POST')
def logg_angre_deling_view(request, pk):
    vakt = hent_aktiv_vakt()
    linje = get_object_or_404(Logglinje, pk=pk, vakt=vakt)
    try:
        services.angre_deling(linje, bruker=request.user,
                              oppdrag=_oppdrag_for_deling(json_body(request), vakt))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
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
    data = json_body(request)
    try:
        ny = services.korriger(
            linje,
            bruker=request.user,
            tekst=data.get('tekst'),
            tidspunkt=_tid(data.get('tidspunkt')),
        )
    except services.AlleredeKorrigert as feil:
        return json_feil(str(feil), status=409)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    except IntegrityError:
        # Unikhetskravet på `korrigerer` er sperren som holder når to
        # operatører trykker i samme sekund; sjekken i `korriger()` er for
        # feilmeldingens skyld. Uten denne grenen blir kappløpet en 500.
        return json_feil('Linja er allerede rettet av noen andre.', status=409)
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
    if not json_body(request).get('confirm'):
        return json_feil('Bekreftelse mangler.', status=400)

    linje = get_object_or_404(Logglinje, pk=pk, vakt=hent_aktiv_vakt())
    try:
        antall = services.fjern(linje, bruker=request.user)
    except services.Ugyldig as feil:
        return json_feil(str(feil))

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

