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

import statistics as smod

from django.db.models import Prefetch
from django.utils import timezone

from core.stats import BaseStatistikkHandler, register

from . import choices
from .models import Enhet, Oppdrag, Oppdragsenhet, Statusmelding
from .services import utledet_av_statuser

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


def _sd(verdier):
    """Sammendrag av en liste varigheter i minutter."""
    if not verdier:
        return {'n': 0, 'mean': None, 'median': None, 'min': None, 'max': None}
    return {
        'n': len(verdier),
        'mean': round(smod.mean(verdier), 1),
        'median': round(smod.median(verdier), 1),
        'min': round(min(verdier), 1),
        'max': round(max(verdier), 1),
    }


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
    from .arkiv import _per_enhet

    oppdragene = list(
        Oppdrag.objects
        .filter(vakt=vakt)
        .select_related('enhet', 'lokasjon')
        .prefetch_related(Prefetch('enheter', Oppdragsenhet.objects.select_related('enhet')))
        .order_by('oppdragsnummer')
    )
    meldinger = Statusmelding.objects.gjeldende_bulk([o.pk for o in oppdragene])

    # **Én rad per oppdrag × enhet** (§5 i notatet om flere enheter) — samme
    # form som arkivet fryser. Responstiden er bilens, ikke oppdragets;
    # antall oppdrag telles distinkt i `_stats_fra_rader`.
    rader = []
    for oppdrag in oppdragene:
        for enhetsnavn, status, gjeldende, modus in _per_enhet(oppdrag, meldinger[oppdrag.pk]):
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
            })
    return rader


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
        })
    return rader


def oppdrag_stats(vakt):
    """Full statistikk for oppdragene i én vakt."""
    paa_vakt = Enhet.objects.filter(er_aktiv=True, pa_vakt=True)
    return _stats_fra_rader(
        rader_for_vakt(vakt),
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
    """Full statistikk for et arkiv, regnet fra de frosne radene."""
    return _stats_fra_rader(rader_for_arkiv(arkiv))


def _stats_fra_rader(rader, *, enheter_pa_vakt=None, enheter_passiv=None,
                     passiv_timer=None):
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

        gruppe = per_oppdrag.setdefault(rad['oppdragsnummer'], {'rad': rad, 'statuser': []})
        gruppe['statuser'].append(rad['status'])

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
        'per_hastegrad': _sortert_synkende(per_hastegrad),
        'per_problemstilling': _sortert_synkende(per_problemstilling),
        'per_lokasjon': _sortert_synkende(per_lokasjon),
        'per_enhet': _sortert_synkende(per_enhet),
        'responstid_per_hastegrad': {
            navn: _sd(verdier) for navn, verdier in resp_per_hastegrad.items()},
        'responstid_per_enhet': {
            navn: _sd(verdier) for navn, verdier in resp_per_enhet.items()},
        'oppdragstid_per_problemstilling': {
            navn: _sd(verdier)
            for navn, verdier in sorted(oppdragstid_per_problem.items())},
        'ankomster': [
            {'time': time, 'antall': ankomster[time]} for time in range(24)],
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
