"""KO-tallene — hendelsesbildet og loggen — og handleren som melder dem inn i
statistikkregisteret (pulje 7a, 21. sep. 2026, `docs/FORSLAG_KO_STATISTIKK.md`).

**Retningen er `ko` → `oppdrag`**, som alt annet i modulen: oppdragene på en
hendelse leses gjennom `Hendelse.oppdrag`, og stemplingene gjennom
`Statusmelding.objects.gjeldende_bulk`. Oppdragsmodulen kjenner ikke fila.

**Tallene teller hendelser, ikke personer** (notatet §8): pasientregistreringen,
oppdragene og hendelsene er tre målinger av tre ting, og summeres aldri. Og de
teller ikke per operatør (André, 21. sep. 2026: «ansvarsområde er ikke viktig,
trenger ikke per person») — loggens tall går per time og per slag.

**Lag på hendelsen regnes av loggen, ikke av `HendelseLag`.** Raden slettes
når laget tas av; systemlinjene `hendelse_lag_paa`/`_av` (og laglista på
`hendelse_opprettet`) står i 730 dager. Det er «holdbart, men skjørt» — et
`til`-felt på raden ville vært renere, og er bevisst *ikke* tatt i denne
pulja: det rører hvordan tavla og skjemaet leser hvem som står på hendelsen.

Ingen arkiv: KO-loggen fryses aldri (se `ko/backup.py`), så
`arkiv_full_stats` svarer `None` som før fase 7 gjorde for oppdrag.
"""
from __future__ import annotations

import statistics as smod
from datetime import timedelta

from django.utils import timezone

from core.stats import BaseStatistikkHandler, register

from . import systemlinjer as sk
from .models import (HENDELSE_LUKKET, KILDE_OPERATOR, KILDE_SYSTEM, MELDER_VALG,
                     PRIORITET_DRIFT, PRIORITET_NAVN, PRIORITET_PLASSERING,
                     PRIORITET_RANG, PRIORITET_ROD, PRIORITET_VALG, PRIORITET_VIKTIG,
                     Hendelse, Logglinje)

#: Prioritetene som ikke «løses»: bestillinger, ikke hendelser (A5).
UTENFOR_LOSNING = frozenset({PRIORITET_DRIFT, PRIORITET_PLASSERING})
#: De som listes med navn når de ble lukket uten lag og uten oppdrag.
FLAGGES_UTEN_RESSURS = frozenset({PRIORITET_VIKTIG, PRIORITET_ROD})
#: Antall stillhetshull som vises. Tre er det man rekker å spørre om.
STILLHET_TOPP = 3
#: Prioritetsnavn → kode, for systemlinjene som fryser navnet.
_KODE_FOR_NAVN = {navn: kode for kode, navn in PRIORITET_VALG}


def _p90(verdier):
    import math
    sortert = sorted(verdier)
    return sortert[max(0, math.ceil(0.9 * len(sortert)) - 1)]


def _sd(verdier):
    """Samme form som oppdragsfanens `_sd` — skrevet her, ikke importert, av
    samme grunn som der: to moduler som deler en konstant er koblet."""
    if not verdier:
        return {'n': 0, 'mean': None, 'median': None, 'p90': None, 'min': None, 'max': None}
    return {
        'n': len(verdier),
        'mean': round(smod.mean(verdier), 1),
        'median': round(smod.median(verdier), 1),
        'p90': round(_p90(verdier), 1),
        'min': round(min(verdier), 1),
        'max': round(max(verdier), 1),
    }


def _min(fra, til):
    return (til - fra).total_seconds() / 60


def _time(t):
    return timezone.localtime(t).hour


# ── Grunnlaget ───────────────────────────────────────────────────────────────


class _Grunnlag:
    """Alt statistikken leser, hentet i fire spørringer og gruppert per
    hendelse. Hendelsene, alle logglinjene (også korrigerte og fjernede —
    rettingene *er* et tall), oppdragene på hendelsene og deres gjeldende
    stemplinger."""

    def __init__(self, vakt, naa=None):
        from oppdrag.models import Oppdrag, Statusmelding

        self.naa = naa or timezone.now()
        self.hendelser = list(Hendelse.objects.filter(vakt=vakt).order_by('hendelsesnummer'))
        self.linjer = list(Logglinje.objects.filter(vakt=vakt).order_by('tidspunkt', 'id'))
        oppdragene = list(Oppdrag.objects.filter(vakt=vakt, hendelse__isnull=False)
                          .order_by('created_at'))
        meldinger = Statusmelding.objects.gjeldende_bulk([o.pk for o in oppdragene])
        self.oppdrag_per_hendelse: dict[int, list] = {}
        for o in oppdragene:
            self.oppdrag_per_hendelse.setdefault(o.hendelse_id, []).append(
                (o, meldinger.get(o.pk, [])))
        self.linjer_per_hendelse: dict[int, list] = {}
        for linje in self.linjer:
            if linje.hendelse_id:
                self.linjer_per_hendelse.setdefault(linje.hendelse_id, []).append(linje)
        self.per_id = {h.pk: h for h in self.hendelser}

    def linjer_for(self, hendelse):
        return self.linjer_per_hendelse.get(hendelse.pk, [])

    def oppdrag_for(self, hendelse):
        return self.oppdrag_per_hendelse.get(hendelse.pk, [])

    def slutt(self, hendelse):
        return hendelse.lukket_at or self.naa


def lagperioder(hendelse, linjer, slutt):
    """``[(lagnavn, fra, til)]`` for lagene som har stått på hendelsen.

    Leses av systemlinjene: `hendelse_opprettet` bærer laglista ved start,
    `hendelse_lag_paa`/`_av` hver endring. Et lag som fortsatt står, står til
    ``slutt`` (lukkingen, eller nå). Samme lag på igjen etter av gir to
    perioder — det er to økter.
    """
    apne: dict[str, object] = {}
    perioder = []
    for linje in linjer:
        if linje.kilde != KILDE_SYSTEM:
            continue
        data = linje.systemdata or {}
        if linje.systemkode == sk.HENDELSE_OPPRETTET:
            for navn in data.get('lag') or []:
                apne.setdefault(navn, linje.tidspunkt)
        elif linje.systemkode == sk.HENDELSE_LAG_PAA and data.get('lag'):
            apne.setdefault(data['lag'], linje.tidspunkt)
        elif linje.systemkode == sk.HENDELSE_LAG_AV and data.get('lag') in apne:
            fra = apne.pop(data['lag'])
            perioder.append((data['lag'], fra, max(fra, linje.tidspunkt)))
    for navn, fra in apne.items():
        perioder.append((navn, fra, max(fra, slutt)))
    return perioder


# ── A. Hendelsesbildet ───────────────────────────────────────────────────────


def _hendelsesbildet(g):
    per_prioritet = {kode: 0 for kode, _ in PRIORITET_VALG}
    per_lokasjon: dict[str, int] = {}
    per_melder = {kode: 0 for kode, _ in MELDER_VALG}
    varighet_per_prioritet = {kode: [] for kode, _ in PRIORITET_VALG}
    varigheter = []
    apne = 0
    for h in g.hendelser:
        per_prioritet[h.prioritet] = per_prioritet.get(h.prioritet, 0) + 1
        navn = h.lokasjon_navn or '(ingen)'
        per_lokasjon[navn] = per_lokasjon.get(navn, 0) + 1
        for kode in h.melder_typer or []:
            per_melder[kode] = per_melder.get(kode, 0) + 1
        if h.lukket_at:
            m = _min(h.opprettet_at, h.lukket_at)
            if m >= 0:
                varigheter.append(m)
                varighet_per_prioritet.setdefault(h.prioritet, []).append(m)
        else:
            apne += 1
    return {
        'antall': len(g.hendelser),
        'apne': apne,
        'per_prioritet': per_prioritet,
        'per_lokasjon': dict(sorted(per_lokasjon.items(), key=lambda p: (-p[1], p[0]))),
        'per_melder': per_melder,
        'varighet': _sd(varigheter),
        'varighet_per_prioritet': {k: _sd(v) for k, v in varighet_per_prioritet.items()},
    }


def _forste_lag_tid(hendelse, linjer):
    perioder = lagperioder(hendelse, linjer, hendelse.opprettet_at)
    return min((fra for _, fra, _ in perioder), default=None)


def _tid_til_forste_ressurs(g):
    """A3. Klokka starter når KO hørte om hendelsen — ikke når oppdraget ble
    laget. Et oppdrag knyttet til fra før hendelsen fantes teller som null."""
    from oppdrag import choices

    per_prioritet = {kode: {'oppdrag': [], 'rykker_ut': [], 'lag': [], 'ressurs': []}
                     for kode, _ in PRIORITET_VALG}
    # «alle» regnes av hendelsene, ikke av medianene per prioritet — medianen
    # av medianer er ikke en median.
    alle = {'oppdrag': [], 'rykker_ut': [], 'lag': [], 'ressurs': []}
    for h in g.hendelser:
        samling = per_prioritet.setdefault(
            h.prioritet, {'oppdrag': [], 'rykker_ut': [], 'lag': [], 'ressurs': []})
        kandidater = []
        oppdragene = g.oppdrag_for(h)
        if oppdragene:
            forste = min(o.created_at for o, _ in oppdragene)
            samling['oppdrag'].append(max(0.0, _min(h.opprettet_at, forste)))
            kandidater.append(samling['oppdrag'][-1])
            rykk = [m.tidspunkt for _, meldinger in oppdragene for m in meldinger
                    if m.status == choices.RYKKER_UT]
            if rykk:
                samling['rykker_ut'].append(max(0.0, _min(h.opprettet_at, min(rykk))))
                kandidater.append(samling['rykker_ut'][-1])
        lag_tid = _forste_lag_tid(h, g.linjer_for(h))
        if lag_tid is not None:
            samling['lag'].append(max(0.0, _min(h.opprettet_at, lag_tid)))
            kandidater.append(samling['lag'][-1])
        if kandidater:
            samling['ressurs'].append(min(kandidater))
    for samling in per_prioritet.values():
        for ledd, verdier in samling.items():
            alle[ledd].extend(verdier)
    ut = {kode: {ledd: _sd(verdier) for ledd, verdier in samling.items()}
          for kode, samling in per_prioritet.items()}
    ut['alle'] = {ledd: _sd(verdier) for ledd, verdier in alle.items()}
    return ut


def _siste_operatorlinje(linjer):
    for linje in reversed(linjer):
        # `fjern()` tømmer teksten, så `tekst` alene holder fjernede utenfor.
        if linje.kilde == KILDE_OPERATOR and linje.tekst:
            return linje.tekst[:160]
    return ''


def _hvem_loste(g):
    """A5. Lukkede hendelser utenom Drift og Plassering, i fire ruter: lag og
    oppdrag, bare lag, bare oppdrag, verken. En Rød eller Viktig i «verken»
    listes med navn — enten var prioriteten for høy, eller så gjorde noen
    andre jobben, og begge deler hører hjemme i gjennomgangen."""
    ruter = ('lag_og_oppdrag', 'bare_lag', 'bare_oppdrag', 'verken')
    per_prioritet = {kode: {r: 0 for r in ruter}
                     for kode, _ in PRIORITET_VALG if kode not in UTENFOR_LOSNING}
    verken_liste = []
    lag_til_oppdrag = []
    for h in g.hendelser:
        if not h.lukket_at or h.prioritet in UTENFOR_LOSNING:
            continue
        linjer = g.linjer_for(h)
        oppdragene = g.oppdrag_for(h)
        lag_tid = _forste_lag_tid(h, linjer)
        hadde_lag = lag_tid is not None
        hadde_oppdrag = bool(oppdragene)
        if hadde_lag and hadde_oppdrag:
            rute = 'lag_og_oppdrag'
            forste_oppdrag = min(o.created_at for o, _ in oppdragene)
            if forste_oppdrag >= lag_tid:
                lag_til_oppdrag.append(_min(lag_tid, forste_oppdrag))
        elif hadde_lag:
            rute = 'bare_lag'
        elif hadde_oppdrag:
            rute = 'bare_oppdrag'
        else:
            rute = 'verken'
            if h.prioritet in FLAGGES_UTEN_RESSURS:
                verken_liste.append({
                    'hendelsesnummer': h.hendelsesnummer,
                    'tittel': h.tittel,
                    'prioritet': h.prioritet,
                    'opprettet': h.opprettet_at.isoformat(),
                    'lukket': h.lukket_at.isoformat(),
                    'minutter': round(_min(h.opprettet_at, h.lukket_at), 1),
                    'lukket_av': h.lukket_av_navn,
                    'siste_linje': _siste_operatorlinje(linjer),
                })
        per_prioritet.setdefault(h.prioritet, {r: 0 for r in ruter})[rute] += 1
    return {
        'ruter': list(ruter),
        'per_prioritet': per_prioritet,
        'sum': {r: sum(p[r] for p in per_prioritet.values()) for r in ruter},
        'lag_til_oppdrag': _sd(lag_til_oppdrag),
        'verken_liste': sorted(verken_liste, key=lambda v: v['hendelsesnummer']),
    }


def _eskaleringer(g):
    """A6. Fra → til, opp og ned, og hvor lenge etter opprettelsen."""
    koder = [kode for kode, _ in PRIORITET_VALG]
    matrise = {fra: {til: 0 for til in koder} for fra in koder}
    opp = ned = 0
    etter = []
    for linje in g.linjer:
        if linje.systemkode != sk.HENDELSE_PRIORITET:
            continue
        data = linje.systemdata or {}
        fra = _KODE_FOR_NAVN.get(data.get('fra_prioritet'))
        til = _KODE_FOR_NAVN.get(data.get('prioritet'))
        if fra is None or til is None or fra == til:
            continue
        matrise[fra][til] += 1
        if PRIORITET_RANG[til] < PRIORITET_RANG[fra]:
            opp += 1
        else:
            ned += 1
        h = g.per_id.get(linje.hendelse_id)
        if h is not None:
            etter.append(max(0.0, _min(h.opprettet_at, linje.tidspunkt)))
    return {'koder': koder, 'matrise': matrise, 'opp': opp, 'ned': ned,
            'etter_opprettelse': _sd(etter)}


def _timebolker_hendelser(g):
    """A8. Åpne hendelser per klokketime, med den høyeste prioriteten som sto
    åpen i timen (laveste rang). Kappes ved 168 timer per hendelse."""
    antall = {t: 0 for t in range(24)}
    hoyeste = {t: None for t in range(24)}
    for h in g.hendelser:
        fra, til = h.opprettet_at, g.slutt(h)
        if til < fra:
            continue
        t = timezone.localtime(fra).replace(minute=0, second=0, microsecond=0)
        steg = 0
        # `<`, ikke `<=`: lukket nøyaktig 22:00 sto ikke åpen i time 22.
        while t < til and steg < 168:
            antall[t.hour] += 1
            gjeldende = hoyeste[t.hour]
            if gjeldende is None or PRIORITET_RANG[h.prioritet] < PRIORITET_RANG[gjeldende]:
                hoyeste[t.hour] = h.prioritet
            t += timedelta(hours=1)
            steg += 1
    return [{'time': t, 'apne': antall[t], 'hoyeste': hoyeste[t]} for t in range(24)]


def _ressursbruk(g):
    """A4. Oppdrag per hendelse, og lagtimer — summen av hver lagøkt."""
    oppdrag_per = []
    lag_timer = 0.0
    per_lag: dict[str, dict] = {}
    for h in g.hendelser:
        oppdrag_per.append(len(g.oppdrag_for(h)))
        sett = set()
        for navn, fra, til in lagperioder(h, g.linjer_for(h), g.slutt(h)):
            timer = (til - fra).total_seconds() / 3600
            lag_timer += timer
            rad = per_lag.setdefault(navn, {'hendelser': 0, 'timer': 0.0})
            rad['timer'] += timer
            if navn not in sett:
                rad['hendelser'] += 1
                sett.add(navn)
    return {
        'oppdrag_per_hendelse': _sd(oppdrag_per),
        'hendelser_med_oppdrag': sum(1 for n in oppdrag_per if n),
        'lagtimer': round(lag_timer, 1),
        'per_lag': {navn: {'hendelser': r['hendelser'], 'timer': round(r['timer'], 1)}
                    for navn, r in sorted(per_lag.items())},
    }


# ── B. Loggen ────────────────────────────────────────────────────────────────


def _loggen(g):
    per_time = [{'time': t, 'operator': 0, 'system': 0} for t in range(24)]
    rettinger, tid_til_retting = 0, []
    fjerninger = 0
    hendelseslinjer = delte = 0
    tid_til_deling = []
    per_id = {linje.pk: linje for linje in g.linjer}
    for linje in g.linjer:
        per_time[_time(linje.tidspunkt)]['operator' if linje.kilde == KILDE_OPERATOR else 'system'] += 1
        if linje.korrigerer_id:
            rettinger += 1
            original = per_id.get(linje.korrigerer_id)
            if original is not None:
                tid_til_retting.append(max(0.0, _min(original.registrert_at, linje.registrert_at)))
        if linje.fjernet_at:
            fjerninger += 1
        if linje.kilde == KILDE_OPERATOR and linje.hendelse_id and not linje.korrigerer_id:
            hendelseslinjer += 1
            if linje.delt_at:
                delte += 1
                tid_til_deling.append(max(0.0, _min(linje.registrert_at, linje.delt_at)))
    return {
        'per_time': per_time,
        'operatorlinjer': sum(r['operator'] for r in per_time),
        'systemlinjer': sum(r['system'] for r in per_time),
        'rettinger': rettinger,
        'tid_til_retting': _sd(tid_til_retting),
        'fjerninger': fjerninger,
        'hendelseslinjer': hendelseslinjer,
        'delte': delte,
        'tid_til_deling': _sd(tid_til_deling),
    }


def _apne_ved(g, t):
    """Hendelsene som sto åpne ved tidspunktet — antall og høyeste prioritet."""
    apne = [h for h in g.hendelser if h.opprettet_at <= t < g.slutt(h)]
    if not apne:
        return 0, None
    return len(apne), min(apne, key=lambda h: PRIORITET_RANG[h.prioritet]).prioritet


def _stillhet(g):
    """B4. De lengste hullene uten operatørlinje mens minst én hendelse sto
    åpen. Hullet måles fra en linje til den neste, og fra den siste til nå
    når noe fortsatt står åpent — det hullet er det som pågår."""
    tider = [linje.tidspunkt for linje in g.linjer if linje.kilde == KILDE_OPERATOR]
    hull = []
    par = list(zip(tider, tider[1:]))
    if tider and tider[-1] < g.naa:
        par.append((tider[-1], g.naa))
    for fra, til in par:
        if _min(fra, til) < 1:
            continue   # linjer skrevet i samme minutt er ikke et hull
        antall, hoyeste = _apne_ved(g, fra)
        if not antall:
            continue
        hull.append({'fra': fra.isoformat(), 'til': til.isoformat(),
                     'minutter': round(_min(fra, til), 1),
                     'apne': antall, 'hoyeste': hoyeste, 'paagaar': til == g.naa})
    hull.sort(key=lambda h: -h['minutter'])
    return hull[:STILLHET_TOPP]


def _stemplinger(vakt):
    """B5. Datakvaliteten på responstidene: hvor mange stemplinger ble ført av
    KO i etterkant, og hvor mange kom forsinket fra en bil uten dekning."""
    from oppdrag.models import Statusmelding

    alle = Statusmelding.objects.filter(oppdrag__vakt=vakt)
    return {
        'antall': alle.count(),
        'ko_forte': alle.filter(manuell=True).count(),
        'forsinkede': alle.filter(forsinket=True).count(),
    }


# ── Handleren ────────────────────────────────────────────────────────────────


def ko_stats(vakt, naa=None):
    g = _Grunnlag(vakt, naa)
    return {
        'hendelser': _hendelsesbildet(g),
        'tid_til_forste_ressurs': _tid_til_forste_ressurs(g),
        'hvem_loste': _hvem_loste(g),
        'eskaleringer': _eskaleringer(g),
        'gjenapninger': sum(1 for l in g.linjer if l.systemkode == sk.HENDELSE_GJENAPNET),
        'samtidighet': _timebolker_hendelser(g),
        'ressursbruk': _ressursbruk(g),
        'logg': _loggen(g),
        'stillhet': _stillhet(g),
        'stemplinger': _stemplinger(vakt),
        'prioriteter': [[kode, navn] for kode, navn in PRIORITET_VALG],
        'meldere': [[kode, navn] for kode, navn in MELDER_VALG],
    }


class KoStatistikkHandler(BaseStatistikkHandler):
    """Hendelsesbildet og loggen. Ingen arkiv — loggen fryses aldri."""

    slug = 'ko'
    display_name = 'KO'
    order = 30

    def full_stats(self, vakt):
        return ko_stats(vakt)


def register_handlers() -> None:
    """Kalles fra ``ko.apps.KoConfig.ready()``."""
    register(KoStatistikkHandler())
