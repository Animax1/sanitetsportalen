"""Oppdragstallene, og handleren som melder dem inn i statistikkregisteret.

Fase 6 av oppdragsmodulen. Utregningen ligger i modulen som eier dataene —
statistikkappen henter, cacher og viser (se ``core/stats.py``).

**Én utregning, to kilder.** ``_stats_fra_rader()`` regner på nøytrale dicter,
og både den aktive vakta og et arkiv bygger slike dicter. Det er samme grep som
``_compute_full_stats_from_dicts`` i pasientmodulen, og grunnen er den samme:
en arkivert vakt skal vise de samme tallene som den viste live. To utregninger
ville drevet fra hverandre, og forskjellen ville dukket opp først når noen
sammenlignet i fjor med i år.

**Tre ting er verdt å kjenne før man rører fila:**

1. **Varigheter regnes fra gjeldende statusmeldinger**, ikke fra rådataene.
   En korreksjon er en ny rad som peker på den gamle, og regelen for hvilken
   som gjelder bor i ``StatusmeldingManager``. Statistikken bruker
   ``gjeldende_bulk()`` nettopp for å slippe å skrive den regelen på nytt.
2. **En varighet som slutter i en automatisk stempling telles ikke** (§12.2 i
   beslutningsnotatet, besluttet 29. aug. 2026). Trykker en enhet «Rykker ut»
   på et nytt oppdrag mens et annet pågår, lukkes det gamle med samme
   tidsstempel og merkes ``automatisk``. Sluttiden er da avledet, ikke målt —
   mannskapet kan ha vært ferdig et kvarter tidligere. Oppdraget telles i alle
   antall og fordelinger; det er bare varigheten som mangler måling som
   holdes utenfor. Andre varigheter på samme oppdrag (typisk responstiden
   fram til «Fremme») teller som vanlig.
3. **Negative varigheter telles ikke.** De kan ikke skje ved korreksjon —
   rekkefølgen håndheves der — men en enhet som stempler offline sender
   klienttid, og en klokke som går feil kan gi «Fremme» før «Rykker ut». Et
   umulig tall skal ikke dra medianen.

Begge utelatelsene rapporteres i ``summary['utelatt']``. Et tall som er
utelatt uten at noen får vite det, er verre enn et tall som mangler.

``sd()`` har samme form som pasientstatistikkens — grensesnittet renderer de
to med samme helper — men er skrevet her, ikke importert. Oppdragsmodulen
rører ikke ``patients``, og en delt konstant er nettopp det som ville koblet
to moduler som ellers ikke kjenner hverandre (samme begrunnelse som for
verdimengdene i ``choices.py``).
"""
from __future__ import annotations

import math
import statistics as smod
from datetime import datetime, timedelta

from django.db.models import Prefetch
from django.utils import timezone

from core.stats import BaseStatistikkHandler, register

from . import choices
from .models import Enhet, Enhetshendelse, Oppdrag, Oppdragsenhet, Statusmelding
from .services import utledet_av_statuser

#: Hendelsestypene som kan la et oppdrag stå uten ressurs (pulje 7b). «Tatt
#: av» er ikke med: den nekter å ta den siste, så noen står alltid igjen.
_AVGANGER = (Enhetshendelse.AVBRUTT, Enhetshendelse.RYKKET_VIDERE,
             Enhetshendelse.AVVENTER)

#: Rangen hastegrad og grovsortering deles om (C2): «bilen fant det mer
#: alvorlig» er en lavere rang enn meldt. Drift og Plassering har ingen
#: pasient og står utenfor tabellen.
_HASTEGRAD_RANG = {'Akutt': 0, 'Haster': 1, 'Vanlig': 2}
_GROV_RANG = {'rod': 0, 'gul': 1, 'gronn': 2}

#: Status → kolonnenavn på `ArkivertOppdrag`. Kartet er det ene stedet de to
#: er koblet: `ArkivOppdragsstatusKolonnerTests` går gjennom statusene og
#: krever et felt for hver, slik at en ny status ikke kan legges til uten at
#: arkivet følger med.
_STATUSFELT = {
    choices.RYKKER_UT: 'rykker_ut_at',
    choices.FREMME: 'fremme_at',
    choices.AVREIST: 'avreist_at',
    choices.LEVERER: 'leverer_at',
    choices.BEHANDLET: 'behandlet_at',
    choices.LEDIG: 'ledig_at',
}


def _p90(verdier):
    """90-persentilen som nærmeste rang: verdien 90 % av målingene ligger
    under eller på. Ikke interpolert — «90 % av akutte hadde bil fremme innen
    7 min» skal peke på en måling som finnes."""
    sortert = sorted(verdier)
    return sortert[max(0, math.ceil(0.9 * len(sortert)) - 1)]


def _sd(verdier):
    """Sammendrag av en liste varigheter i minutter.

    `p90` fra pulje 7b (21. sep. 2026): snittet dras av ett utlegg, og
    medianen sier ingenting om halen. Pasientfanens `sd()` har ikke nøkkelen;
    `_sdRad()` i JS tåler at den mangler.
    """
    if not verdier:
        return {'n': 0, 'mean': None, 'median': None, 'p90': None,
                'min': None, 'max': None}
    return {
        'n': len(verdier),
        'mean': round(smod.mean(verdier), 1),
        'median': round(smod.median(verdier), 1),
        'p90': round(_p90(verdier), 1),
        'min': round(min(verdier), 1),
        'max': round(max(verdier), 1),
    }


def _i_hastegradrekkefolge(teller):
    """Dict i AMK-rekkefølge, alle fem hastegradene med — også de på null.

    C8 (André, 21. sep. 2026: «det mangler en hastegrad»). Sortert på antall
    byttet smultringen rekkefølge fra vakt til vakt, og en hastegrad uten
    oppdrag forsvant fra tegningen. Ukjente verdier — data fra før en
    hastegrad ble omdøpt — legges sist, synkende.
    """
    ut = {h: teller.get(h, 0) for h in choices.HASTEGRAD}
    for navn, antall in _sortert_synkende(
            {k: v for k, v in teller.items() if k not in ut}).items():
        ut[navn] = antall
    return ut


def _sortert_synkende(teller):
    """Dict sortert på antall, høyest først — så på navn ved likhet.

    Rekkefølgen er visningsrekkefølgen. Uten sorteringen ville stolpene
    flyttet på seg mellom to lastinger av samme side.
    """
    return dict(sorted(teller.items(), key=lambda p: (-p[1], p[0])))


class _Varigheter:
    """Samler varigheter og holder regnskap over det som ble utelatt.

    Egen klasse framfor løse lister fordi utelatelsene skal telles ett sted.
    Var tellingen spredt utover, ville en ny varighet lett blitt lagt til uten
    at den ble med i regnskapet — og da hadde tallet «utelatt: 0» løyet.
    """

    def __init__(self):
        self.automatisk = 0
        self.negativ = 0

    def minutter(self, start, slutt):
        """Minutter fra ``start`` til ``slutt``, eller ``None``.

        Begge er enten ``None``, et tidspunkt, eller en ``(tidspunkt,
        automatisk)``-tuppel. Det er *sluttstemplingen* som avgjør om
        varigheten er målt eller avledet — starten kan gjerne være avledet
        uten at sluttiden blir det.
        """
        if start is None or slutt is None:
            return None

        slutt_tid, slutt_automatisk = slutt
        if slutt_automatisk:
            self.automatisk += 1
            return None

        fra = start[0] if isinstance(start, tuple) else start
        minutter = (slutt_tid - fra).total_seconds() / 60
        if minutter < 0:
            self.negativ += 1
            return None
        return minutter

    def som_dict(self):
        return {'automatisk': self.automatisk, 'negativ': self.negativ}


def rader_for_vakt(vakt):
    """Nøytrale rader for oppdragene i én vakt.

    Én spørring for oppdragene og én for statusmeldingene. Antall oppdrag i
    en vakt er lite, men endepunktet caches i 60 sekunder og pollet fra en
    åpen fane — det er den samme regningen som gjorde pasientlista til appens
    dyreste sti før den fikk `select_related`.
    """
    from .arkiv import _per_enhet, avreist_sted, enhetshendelser_for

    oppdragene = list(
        Oppdrag.objects
        .filter(vakt=vakt)
        .select_related('enhet', 'lokasjon')
        .prefetch_related(
            Prefetch('enheter', Oppdragsenhet.objects.select_related('enhet')),
            Prefetch('enhetshendelser', Enhetshendelse.objects.select_related('enhet')))
        .order_by('oppdragsnummer')
    )
    meldinger = Statusmelding.objects.gjeldende_bulk([o.pk for o in oppdragene])

    # **Én rad per oppdrag × enhet** (§5 i notatet om flere enheter) — samme
    # form som arkivet fryser. Responstiden er bilens, ikke oppdragets;
    # antall oppdrag telles distinkt i `_stats_fra_rader`.
    rader = []
    for oppdrag in oppdragene:
        hendelser = enhetshendelser_for(oppdrag)
        for enhetsnavn, status, gjeldende, modus, varslet_at in _per_enhet(
                oppdrag, meldinger[oppdrag.pk]):
            sted, sted_tekst = avreist_sted(gjeldende)
            rader.append({
                'oppdragsnummer': oppdrag.oppdragsnummer,
                'hastegrad': oppdrag.hastegrad,
                'problemstilling': oppdrag.problemstilling,
                'enhet': enhetsnavn,
                # Modusen som ble frosset ved varsling — se `_per_enhet`.
                'varslet_modus': modus,
                'lokasjon': oppdrag.lokasjon.navn if oppdrag.lokasjon else '(ingen)',
                'status': status,
                'opprettet': oppdrag.created_at,
                # Gjeldende melding per status: en korreksjon overstyrer raden
                # den peker på, og regelen bor i manageren.
                'tider': {m.status: (m.tidspunkt, m.automatisk) for m in gjeldende},
                'forsinket': sum(1 for m in gjeldende if m.forsinket),
                # Pulje 7b. Radens: når *hun* ble varslet, og hvor hun dro.
                # Oppdragets, gjentatt per rad som hastegraden: bilens
                # grovsortering og enhetshendelsene.
                'varslet_at': varslet_at,
                'avreist_til': sted,
                # Bare live — fritekst fryses ikke i arkivet.
                'avreist_til_tekst': sted_tekst,
                'grovsortering': oppdrag.grovsortering or '',
                'enhetshendelser': hendelser,
            })
    return rader


def _fra_iso(verdi):
    return datetime.fromisoformat(verdi) if verdi else None


def rader_for_arkiv(arkiv):
    """Nøytrale rader fra et arkiv — samme form som `rader_for_vakt`."""
    rader = []
    for rad in arkiv.oppdrag.all():
        automatiske = set(rad.automatiske_statuser or [])
        tider = {}
        for status, felt in _STATUSFELT.items():
            tidspunkt = getattr(rad, felt)
            if tidspunkt is not None:
                tider[status] = (tidspunkt, status in automatiske)
        rader.append({
            'oppdragsnummer': rad.oppdragsnummer,
            'hastegrad': rad.hastegrad,
            'problemstilling': rad.problemstilling,
            'enhet': rad.enhet_navn,
            # Arkivraden bærer modusen, så «oppdrag i passiv tid» overlever
            # arkiveringen — ellers forsvant tallet nøyaktig når rapporten
            # skrives.
            'varslet_modus': rad.varslet_modus,
            'lokasjon': rad.lokasjon_navn or '(ingen)',
            'status': rad.sluttstatus,
            'opprettet': rad.opprettet_at,
            'tider': tider,
            'forsinket': rad.antall_forsinket,
            'varslet_at': rad.varslet_at,
            'avreist_til': rad.avreist_til or '',
            'avreist_til_tekst': '',
            'grovsortering': rad.grovsortering or '',
            'enhetshendelser': [
                {**h, 'tidspunkt': _fra_iso(h.get('tidspunkt')),
                 'varslet_at': _fra_iso(h.get('varslet_at'))}
                for h in (rad.enhetshendelser or [])
            ],
        })
    return rader


def oppdrag_stats(vakt, naa=None):
    """Full statistikk for oppdragene i én vakt.

    `naa` er der for testene: åpne intervaller (7b) løper til nå, og en test
    som lot «nå» være klokka på veggen ga et annet svar kl. 20 enn kl. 11 —
    timebolkene slår sammen dager, og et intervall som løp inn i neste døgn
    talte to ganger i samme time.
    """
    paa_vakt = Enhet.objects.filter(er_aktiv=True, pa_vakt=True)
    return _stats_fra_rader(
        rader_for_vakt(vakt),
        naa=naa,
        # Enhetene er ikke scopet på vakt — de er oppsett, ikke vaktdata.
        # Tallet beskriver beredskapen akkurat nå, og finnes derfor bare for
        # den aktive vakta.
        enheter_pa_vakt=paa_vakt.count(),
        # **Passiv teller med i beredskapen** (André, 16. sep. 2026): enheten
        # har en 24/7-vakt gjennom arrangementet. Men da betyr
        # `enheter_pa_vakt` «aktiv eller passiv», og et tall der de to ikke
        # lar seg skille dokumenterer ikke at noen sov. Derfor står passiv
        # som eget ledd ved siden av, ikke trukket fra.
        enheter_passiv=paa_vakt.filter(passiv_vakt=True).count(),
        passiv_timer=passiv_timer_for(vakt),
    )


def passiv_timer_for(vakt) -> float:
    """Timer enheter har stått i passiv vakt i denne vakta.

    **Dette er hele grunnen til at `Vaktmodusperiode` finnes** (André, 16. sep.
    2026: «timer brukt i passiv tid når en helst skulle sovet»). Et boolsk
    felt på enheten sier hva som gjelder nå; vipper noen bryteren klokka 03,
    er gårsdagen borte uten tabellen.

    Åpne perioder telles fram til nå — vakta pågår, og timene er påløpt.
    """
    from .models import Vaktmodusperiode

    naa = timezone.now()
    sekunder = 0.0
    for rad in Vaktmodusperiode.objects.filter(
            vakt=vakt, modus=Vaktmodusperiode.PASSIV):
        slutt = rad.til or naa
        if slutt > rad.fra:
            sekunder += (slutt - rad.fra).total_seconds()
    return round(sekunder / 3600, 2)


def arkiv_stats(arkiv):
    """Full statistikk for et arkiv, regnet fra de frosne radene.

    Et oppdrag som fortsatt ventet da vakta ble arkivert, ventet fram til
    arkiveringen — ikke fram til nå, som kan være to år senere.
    """
    return _stats_fra_rader(rader_for_arkiv(arkiv), naa=arkiv.importert_at)


def _stats_fra_rader(rader, *, enheter_pa_vakt=None, enheter_passiv=None,
                     passiv_timer=None, naa=None):
    """Tallene, regnet på nøytrale rader fra vakta eller fra et arkiv.

    **En rad er én enhets innsats på ett oppdrag** (11. sep. 2026). Det som
    er *bilens* — responstid, ventetid, utrykning, tid på stedet, oppdragstid
    og `per_enhet` — telles per rad. Det som er *oppdragets* — antall,
    hastegrad, problemstilling, lokasjon, status nå og ankomsttime — telles
    én gang per `oppdragsnummer`, med statusen utledet av radene som på tavla.
    Et arkiv med én rad per oppdrag gir nøyaktig de gamle tallene; ikke
    «rett» tellingen til å gå per rad — det står i notatets §5.
    """
    var = _Varigheter()

    responstider, ventetider, utrykningstider = [], [], []
    tid_pa_stedet, oppdragstider = [], []
    per_hastegrad, per_problemstilling = {}, {}
    per_lokasjon, per_enhet = {}, {}
    resp_per_hastegrad, resp_per_enhet = {}, {}
    oppdragstid_per_problem = {}
    status_naa = {status: 0 for status, _ in choices.STATUS_VALG}
    ankomster = {time: 0 for time in range(24)}
    forsinket_meldt = 0
    per_oppdrag = {}

    for rad in rader:
        tider = rad['tider']
        forsinket_meldt += rad['forsinket']

        opprettet = rad['opprettet']
        rykker_ut = tider.get(choices.RYKKER_UT)
        fremme = tider.get(choices.FREMME)
        # Tida på stedet slutter når bilen drar — eller når pasienten er
        # behandlet på sted (12. sep. 2026), som er den andre veien ut.
        avreist = tider.get(choices.AVREIST) or tider.get(choices.BEHANDLET)
        ledig = tider.get(choices.LEDIG)

        respons = var.minutter(opprettet, fremme)
        vente = var.minutter(opprettet, rykker_ut)
        utrykning = var.minutter(rykker_ut, fremme)
        paa_stedet = var.minutter(fremme, avreist)
        oppdragstid = var.minutter(opprettet, ledig)

        for verdi, samling in (
            (respons, responstider),
            (vente, ventetider),
            (utrykning, utrykningstider),
            (paa_stedet, tid_pa_stedet),
            (oppdragstid, oppdragstider),
        ):
            if verdi is not None:
                samling.append(verdi)

        enhetsnavn = rad['enhet']
        hastegrad = rad['hastegrad']
        problemstilling = rad['problemstilling']

        per_enhet[enhetsnavn] = per_enhet.get(enhetsnavn, 0) + 1
        if respons is not None:
            resp_per_hastegrad.setdefault(hastegrad, []).append(respons)
            resp_per_enhet.setdefault(enhetsnavn, []).append(respons)
        if oppdragstid is not None:
            oppdragstid_per_problem.setdefault(
                problemstilling, []).append(oppdragstid)

        gruppe = per_oppdrag.setdefault(
            rad['oppdragsnummer'], {'rad': rad, 'statuser': [], 'rader': []})
        gruppe['statuser'].append(rad['status'])
        gruppe['rader'].append(rad)

    # Oppdragets egne tall — én gang per nummer, uansett hvor mange biler.
    for gruppe in per_oppdrag.values():
        rad = gruppe['rad']
        per_hastegrad[rad['hastegrad']] = per_hastegrad.get(rad['hastegrad'], 0) + 1
        per_problemstilling[rad['problemstilling']] = (
            per_problemstilling.get(rad['problemstilling'], 0) + 1)
        per_lokasjon[rad['lokasjon']] = per_lokasjon.get(rad['lokasjon'], 0) + 1
        status = utledet_av_statuser(gruppe['statuser'])
        status_naa[status] = status_naa.get(status, 0) + 1
        ankomster[timezone.localtime(rad['opprettet']).hour] += 1

    fullforte = status_naa.get(choices.TERMINAL, 0)
    total = len(per_oppdrag)

    # Pulje 7b (21. sep. 2026). Hver del er en egen funksjon med egne tester
    # — de er regler, og en `if` inne i løkka over lar seg ikke prøve alene.
    naa = naa or timezone.now()
    vente = _ventetid_og_koe(per_oppdrag, var, naa)

    return {
        'summary': {
            'total': total,
            'aktive': total - fullforte,
            'fullforte': fullforte,
            # Radene: én per oppdrag × enhet. Lik `total` når hvert oppdrag
            # hadde én bil, og det er slik en leser ser at tallene skiller.
            'enhetsinnsatser': len(rader),
            # `None` for et arkiv: beredskapen «akkurat nå» finnes ikke for en
            # vakt som er over, og et tall der ville vært oppdiktet.
            'enheter_pa_vakt': enheter_pa_vakt,
            # Passiv er *en del av* tallet over, ikke ved siden av det.
            # `None` for et arkiv, av samme grunn.
            'enheter_passiv': enheter_passiv,
            'passiv_timer': passiv_timer,
            # **Oppdrag som kom i passiv tid** — regnet av modusen som ble
            # frosset på koblingsraden ved varsling, ikke av enhetens
            # tilstand nå. Tallet gjelder også for et arkiv: det ligger i
            # radene, ikke i nåtiden.
            'oppdrag_i_passiv': sum(
                1 for r in rader if r.get('varslet_modus') == 'passiv'),
            'responstid': _sd(responstider),
            'ventetid': _sd(ventetider),
            'utrykningstid': _sd(utrykningstider),
            'tid_pa_stedet': _sd(tid_pa_stedet),
            'oppdragstid': _sd(oppdragstider),
            'forsinket_meldt': forsinket_meldt,
            'utelatt': var.som_dict(),
        },
        'status_naa': [
            {'status': status, 'navn': navn, 'antall': status_naa.get(status, 0)}
            for status, navn in choices.STATUS_VALG
        ],
        'per_hastegrad': _i_hastegradrekkefolge(per_hastegrad),
        'per_problemstilling': _sortert_synkende(per_problemstilling),
        'per_lokasjon': _sortert_synkende(per_lokasjon),
        'per_enhet': _sortert_synkende(per_enhet),
        'responstid_per_hastegrad': {
            navn: _sd(resp_per_hastegrad.get(navn, []))
            for navn in _i_hastegradrekkefolge(
                {k: len(v) for k, v in resp_per_hastegrad.items()})},
        'responstid_per_enhet': {
            navn: _sd(verdier) for navn, verdier in resp_per_enhet.items()},
        'oppdragstid_per_problemstilling': {
            navn: _sd(verdier)
            for navn, verdier in sorted(oppdragstid_per_problem.items())},
        'ankomster': [
            {'time': time, 'antall': ankomster[time]} for time in range(24)],
        # ── Pulje 7b ──
        **vente,
        'konkordans': _konkordans(per_oppdrag),
        'avreist_til': _avreist_til(rader),
        'utfall_per_problemstilling': _utfall_per_problemstilling(per_oppdrag),
        'enhetshendelser': _enhetshendelser(per_oppdrag),
    }


# ── Pulje 7b: ventetida i to, køen, hvem løste hva ─────────────────────────


def _minutter(fra, til):
    return (til - fra).total_seconds() / 60


def _tid(verdi):
    """Tidspunktet i en `(tidspunkt, automatisk)`-tuppel, eller verdien selv."""
    return verdi[0] if isinstance(verdi, tuple) else verdi


def _andre_aktive(hendelse, rader):
    """Var en *annen* enhet på oppdraget da hendelsen skjedde?

    Samme spørsmål som `services.trenger_ny_ressurs` stiller live, stilt i
    ettertid på radene: varslet før, og ikke ledig ennå. En bil som selv
    avventet er ikke på vei, som der.
    """
    t = hendelse['tidspunkt']
    for rad in rader:
        if rad['enhet'] == hendelse['enhet'] or not rad['varslet_at']:
            continue
        if rad['varslet_at'] > t:
            continue
        ledig = _tid(rad['tider'].get(choices.LEDIG))
        if ledig is not None and ledig <= t:
            continue
        return True
    return False


def _uten_ressurs_intervaller(gruppe):
    """``[(fra, til)]`` der oppdraget sto uten noen som tok det.

    Starter ved opprettelsen og ved hver avgang som etterlot oppdraget alene;
    slutter ved neste varsling **eller** neste «Rykker ut» — den som avventet
    kan ombestemme seg uten at noen ny varsles. ``til`` er ``None`` mens det
    fortsatt står.
    """
    rad = gruppe['rad']
    rader = gruppe['rader']
    starter = [rad['opprettet']]
    for h in rad['enhetshendelser']:
        if h['type'] in _AVGANGER and not _andre_aktive(h, rader):
            starter.append(h['tidspunkt'])
    slutter = sorted(
        [r['varslet_at'] for r in rader if r['varslet_at']]
        + [_tid(r['tider'][choices.RYKKER_UT]) for r in rader
           if choices.RYKKER_UT in r['tider']])
    ut = []
    for fra in sorted(starter):
        # `>=`, ikke `>`: opprettet *med* enhet har varslingen i samme
        # øyeblikk, og da er KO-ventetida null — ikke tida til Rykker ut.
        til = next((t for t in slutter if t >= fra), None)
        ut.append((fra, til))
    return ut


def _tildelt_venter_intervaller(gruppe):
    """``[(fra, til, enhet)]`` der en enhet var varslet og ennå ikke rykket ut."""
    ut = []
    for r in gruppe['rader']:
        if not r['varslet_at']:
            continue
        slutt = _tid(r['tider'].get(choices.RYKKER_UT)) or _tid(r['tider'].get(choices.LEDIG))
        ut.append((r['varslet_at'], slutt, r['enhet']))
    for h in gruppe['rad']['enhetshendelser']:
        # Raden er slettet; hendelsen bærer varslingstida (0030).
        if h['type'] == Enhetshendelse.TATT_AV and h['varslet_at']:
            ut.append((h['varslet_at'], h['tidspunkt'], h['enhet']))
    return ut


def _timebolker(intervaller, naa):
    """Per klokketime: hvor mange intervaller var åpne, og lengste ventetid.

    Lengste er hvor lenge den som hadde ventet lengst hadde ventet ved
    timens slutt (eller ved sitt eget slutt). Et åpent intervall løper til
    ``naa``. Kappes ved 168 timer — en rad med et umulig tidspunkt skal ikke
    låse endepunktet.
    """
    antall = {t: 0 for t in range(24)}
    lengste = {t: 0.0 for t in range(24)}
    for fra, til, *_ in intervaller:
        til = til or naa
        if til <= fra:
            continue
        t = timezone.localtime(fra).replace(minute=0, second=0, microsecond=0)
        steg = 0
        while t < til and steg < 168:
            neste = t + timedelta(hours=1)
            antall[t.hour] += 1
            lengste[t.hour] = max(lengste[t.hour], _minutter(fra, min(til, neste)))
            t = neste
            steg += 1
    return antall, lengste


def _ventetid_og_koe(per_oppdrag, var, naa):
    """C4, C4b og C4c — ventetida delt i to, køen per time, og de som aldri
    rykket ut. Se `docs/FORSLAG_KO_STATISTIKK.md`."""
    ko_vente, ko_per_hastegrad = [], {}
    reaksjon, reaksjon_passiv = [], []
    reaksjon_per_hastegrad, reaksjon_per_enhet = {}, {}
    uten, tildelt = [], []
    aldri_rykket = []
    etter_avgang = 0
    lengste_uten = None

    for nummer, gruppe in per_oppdrag.items():
        rad = gruppe['rad']
        hastegrad = rad['hastegrad']

        intervaller = _uten_ressurs_intervaller(gruppe)
        if len(intervaller) > 1:
            etter_avgang += 1
        for fra, til in intervaller:
            uten.append((fra, til))
            minutter = _minutter(fra, til or naa)
            if til is not None:
                ko_vente.append(minutter)
                ko_per_hastegrad.setdefault(hastegrad, []).append(minutter)
            if minutter > 0 and (lengste_uten is None or minutter > lengste_uten['minutter']):
                lengste_uten = {
                    'minutter': round(minutter, 1), 'oppdragsnummer': nummer,
                    'hastegrad': hastegrad, 'fra': fra.isoformat(),
                    'paagaar': til is None,
                }

        tildelt.extend(_tildelt_venter_intervaller(gruppe))

        for r in gruppe['rader']:
            if not r['varslet_at']:
                continue
            rykker_ut = r['tider'].get(choices.RYKKER_UT)
            if rykker_ut is None:
                if choices.LEDIG in r['tider']:
                    aldri_rykket.append({
                        'oppdragsnummer': nummer, 'hastegrad': hastegrad,
                        'problemstilling': r['problemstilling'], 'enhet': r['enhet'],
                        'sto_i': round(_minutter(r['varslet_at'],
                                                 _tid(r['tider'][choices.LEDIG])), 1),
                        'endte': 'Meldt ledig uten å rykke ut',
                    })
                continue
            minutter = var.minutter(r['varslet_at'], rykker_ut)
            if minutter is None:
                continue
            if r.get('varslet_modus') == 'passiv':
                reaksjon_passiv.append(minutter)
                continue
            reaksjon.append(minutter)
            reaksjon_per_hastegrad.setdefault(hastegrad, []).append(minutter)
            reaksjon_per_enhet.setdefault(r['enhet'], []).append(minutter)

        for h in rad['enhetshendelser']:
            if h['type'] == Enhetshendelse.TATT_AV:
                aldri_rykket.append({
                    'oppdragsnummer': nummer, 'hastegrad': hastegrad,
                    'problemstilling': rad['problemstilling'], 'enhet': h['enhet'],
                    'sto_i': (round(_minutter(h['varslet_at'], h['tidspunkt']), 1)
                              if h['varslet_at'] else None),
                    'endte': 'Tatt av',
                })

    uten_antall, uten_lengste = _timebolker(uten, naa)
    tildelt_antall, tildelt_lengste = _timebolker(tildelt, naa)
    koe = [
        {'time': t, 'uten_ressurs': uten_antall[t], 'tildelt_venter': tildelt_antall[t],
         'lengste': round(max(uten_lengste[t], tildelt_lengste[t]), 1)}
        for t in range(24)
    ]
    topp = max(koe, key=lambda k: (k['uten_ressurs'] + k['tildelt_venter'], -k['time']))
    flest = (None if not (topp['uten_ressurs'] + topp['tildelt_venter'])
             else {'antall': topp['uten_ressurs'] + topp['tildelt_venter'], 'time': topp['time']})

    hastegrader = _i_hastegradrekkefolge(
        {k: len(v) for k, v in {**ko_per_hastegrad, **reaksjon_per_hastegrad}.items()})
    return {
        'ventetid_delt': {
            'ko_ventetid': _sd(ko_vente),
            'reaksjonstid': _sd(reaksjon),
            'reaksjonstid_passiv': _sd(reaksjon_passiv),
            'per_hastegrad': {
                navn: {'ko_ventetid': _sd(ko_per_hastegrad.get(navn, [])),
                       'reaksjonstid': _sd(reaksjon_per_hastegrad.get(navn, []))}
                for navn in hastegrader},
            'reaksjonstid_per_enhet': {
                navn: _sd(verdier) for navn, verdier in sorted(reaksjon_per_enhet.items())},
            'uten_ressurs_etter_avgang': etter_avgang,
        },
        'koe': koe,
        'lengste_uten_ressurs': lengste_uten,
        'flest_i_koe': flest,
        'aldri_rykket_ut': sorted(aldri_rykket, key=lambda r: (r['oppdragsnummer'], r['enhet'])),
    }


def _konkordans(per_oppdrag):
    """C2: meldt hastegrad (KO) × bilens grovsortering, én gang per oppdrag.

    Drift og Plassering står utenfor — ingen pasient å sortere. `enige`,
    `bilen_hoyere` og `bilen_lavere` teller bare de tre fargene; «ikke
    aktuelt» og «ikke vurdert» er verken enighet eller avvik.
    """
    kolonner = [k for k, _ in choices.GROVSORTERING] + ['']
    antall = {h: {k: 0 for k in kolonner} for h in _HASTEGRAD_RANG}
    enige = hoyere = lavere = vurderte = 0
    for gruppe in per_oppdrag.values():
        rad = gruppe['rad']
        hastegrad, grov = rad['hastegrad'], rad.get('grovsortering', '')
        if hastegrad not in antall:
            continue
        antall[hastegrad][grov if grov in antall[hastegrad] else ''] += 1
        if grov in _GROV_RANG:
            vurderte += 1
            diff = _GROV_RANG[grov] - _HASTEGRAD_RANG[hastegrad]
            if diff == 0:
                enige += 1
            elif diff < 0:
                hoyere += 1
            else:
                lavere += 1
    return {
        'rader': list(_HASTEGRAD_RANG),
        'kolonner': [[k, n] for k, n in choices.GROVSORTERING] + [['', 'Ikke vurdert']],
        'antall': antall,
        'vurderte': vurderte, 'enige': enige,
        'bilen_hoyere': hoyere, 'bilen_lavere': lavere,
    }


def _avreist_til(rader):
    """C1: hvor bilene dro, per sted og sted × hastegrad. Per rad — det er
    bilens tur. «Annet sted»-tekstene bare live; arkivet fryser dem ikke."""
    navn_for = dict(choices.AVREIST_TIL)
    per_sted = {navn: 0 for navn in navn_for.values()}
    per_sted_hastegrad = {}
    annet = []
    for rad in rader:
        if choices.AVREIST not in rad['tider']:
            continue
        sted = rad.get('avreist_til', '')
        navn = navn_for.get(sted, '(ikke oppgitt)')
        per_sted[navn] = per_sted.get(navn, 0) + 1
        per_sted_hastegrad.setdefault(navn, {})
        per_sted_hastegrad[navn][rad['hastegrad']] = (
            per_sted_hastegrad[navn].get(rad['hastegrad'], 0) + 1)
        if sted == 'annet' and rad.get('avreist_til_tekst'):
            annet.append({'oppdragsnummer': rad['oppdragsnummer'],
                          'enhet': rad['enhet'], 'tekst': rad['avreist_til_tekst']})
    return {
        'per_sted': per_sted,
        'per_sted_hastegrad': per_sted_hastegrad,
        'annet_tekster': sorted(annet, key=lambda a: a['oppdragsnummer']),
    }


def _utfall_per_problemstilling(per_oppdrag):
    """C3: per problemstilling — behandlet på sted (utført for drift),
    transportert, eller ingen av delene. Én gang per oppdrag: er én bil
    avreist, er pasienten transportert uansett hva de andre stemplet."""
    ut = {}
    for gruppe in per_oppdrag.values():
        problem = gruppe['rad']['problemstilling']
        rad = ut.setdefault(problem, {'behandlet': 0, 'transportert': 0, 'uten': 0})
        tider = [r['tider'] for r in gruppe['rader']]
        if any(choices.AVREIST in t or choices.LEVERER in t for t in tider):
            rad['transportert'] += 1
        elif any(choices.BEHANDLET in t for t in tider):
            rad['behandlet'] += 1
        else:
            rad['uten'] += 1
    return dict(sorted(ut.items(), key=lambda p: (-sum(p[1].values()), p[0])))


def _enhetshendelser(per_oppdrag):
    """C5: avbrytelser, avventinger, rykket videre og tatt av — totalt og
    per enhet."""
    typer = [t for t, _ in Enhetshendelse.TYPER]
    per_type = {t: 0 for t in typer}
    per_enhet = {}
    for gruppe in per_oppdrag.values():
        for h in gruppe['rad']['enhetshendelser']:
            if h['type'] not in per_type:
                continue
            per_type[h['type']] += 1
            per_enhet.setdefault(h['enhet'], {t: 0 for t in typer})[h['type']] += 1
    return {
        'typer': [[t, navn] for t, navn in Enhetshendelse.TYPER],
        'per_type': per_type,
        'per_enhet': dict(sorted(per_enhet.items())),
    }


class OppdragStatistikkHandler(BaseStatistikkHandler):
    """Oppdragstallene: responstider, fordelinger og status akkurat nå."""

    slug = 'oppdrag'
    display_name = 'Oppdrag'
    order = 20

    def full_stats(self, vakt):
        return oppdrag_stats(vakt)

    def arkiv_full_stats(self, pk):
        """Tallene for ett oppdragsarkiv, eller ``None`` (fase 7).

        Kollapset arkiv leverer det frosne aggregatet: radene finnes ikke
        lenger, og å regne på ingenting ville gitt nuller som så ut som
        målinger.
        """
        from .models import OppdragArkiv

        try:
            arkiv = OppdragArkiv.objects.get(pk=pk)
        except OppdragArkiv.DoesNotExist:
            return None
        if arkiv.er_kollapset:
            return (arkiv.aggregat or {}).get('full')
        return arkiv_stats(arkiv)


def register_handlers() -> None:
    """Kalles fra ``oppdrag.apps.OppdragConfig.ready()``."""
    register(OppdragStatistikkHandler())
