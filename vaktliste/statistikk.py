"""Bemanningstallene — belastning mot bemanning — og handleren som melder dem
inn i statistikkregisteret (pulje 7c, 21. sep. 2026,
`docs/FORSLAG_KO_STATISTIKK.md` §2 D og C7).

**Retningen er `vaktliste` → `oppdrag`**, den tillatte: enhetsutnyttelsen leser
oppdragenes koblingsrader gjennom `Ressurs.enhet`, og oppdragsmodulen kjenner
ikke fila. De to andre fanene henter tallene herfra som linjer over sine egne
grafer — gjennom statistikkappen, ikke ved import.

**Vaktlista for vakta, ikke lista i drift.** `vaktliste_i_bruk()` svarer på
«nå», og statistikk er per vakt: `Vaktliste.vakt` er en én-til-én.

**«På vakt» er vaktlistas eget begrep**, som i `ressurser_paa_vakt_naa`: et
skift med mannskap, ikke avmeldt, som dekker tidspunktet. Om personen har møtt
står ved siden av (`mott`), fordi «planlagt 12, møtt 9» er akkurat det tallet
gjennomgangen vil ha. Et lag er en ressurs uten oppdragsenhet — KOs
definisjon; en enhet er en ressurs med.

**Tallene teller personer og timer, aldri navn.** Kilden krever `les_alle`
i vaktlista — `les` er «sitt eget korps», og hele bemanningen er ikke det.
"""
from __future__ import annotations

import statistics as smod
from datetime import timedelta

from django.utils import timezone

from core.stats import BaseStatistikkHandler, register

from .models import Ressurs, Vaktliste, Vaktpost


def _min(fra, til):
    return (til - fra).total_seconds() / 60


def _timer(intervaller):
    return round(sum((til - fra).total_seconds() for fra, til in intervaller) / 3600, 2)


def union(intervaller):
    """Slå sammen overlappende `(fra, til)`. To skift som overlapper er én
    bemannet periode, ikke to — ellers ble bilen bemannet dobbelt."""
    ut = []
    for fra, til in sorted(i for i in intervaller if i[1] > i[0]):
        if ut and fra <= ut[-1][1]:
            ut[-1] = (ut[-1][0], max(ut[-1][1], til))
        else:
            ut.append((fra, til))
    return ut


def lengste_hull(bemannet, opptatt):
    """Lengste sammenhengende tid innenfor ``bemannet`` uten noe i ``opptatt``.

    Begge er lister av `(fra, til)`; `opptatt` trenger bare være sortert —
    overlapp håndteres av `pos`, som aldri går bakover. Svarer i minutter,
    `0.0` når det ikke finnes bemannet tid.
    """
    lengst = 0.0
    opptatt = sorted(opptatt)
    for b_fra, b_til in bemannet:
        pos = b_fra
        for o_fra, o_til in opptatt:
            if o_til <= pos or o_fra >= b_til:
                continue
            lengst = max(lengst, _min(pos, max(pos, o_fra)))
            pos = max(pos, o_til)
        lengst = max(lengst, _min(pos, max(pos, b_til)))
    return round(lengst, 1)


def _timebolker(intervaller, nokkel):
    """Per klokketime: hvor mange **distinkte** nøkler hadde et intervall som
    dekket noe av timen. Et skift 20:10–21:40 teller i 20 og 21."""
    per = {t: set() for t in range(24)}
    for fra, til, n in intervaller:
        if til <= fra:
            continue
        t = timezone.localtime(fra).replace(minute=0, second=0, microsecond=0)
        steg = 0
        while t < til and steg < 168:
            per[t.hour].add(nokkel(n))
            t += timedelta(hours=1)
            steg += 1
    return {t: len(s) for t, s in per.items()}


def bemanning_stats(vakt, naa=None):
    from oppdrag import choices
    from oppdrag.models import Oppdrag, Oppdragsenhet, Statusmelding

    naa = naa or timezone.now()
    vaktliste = Vaktliste.objects.filter(vakt=vakt).first()
    poster = list(
        Vaktpost.objects
        .filter(ressurs__vaktliste=vaktliste, mannskap__isnull=False, avmeldt_at__isnull=True)
        .select_related('ressurs')
    ) if vaktliste else []
    ressurser = {r.pk: r for r in Ressurs.objects.filter(vaktliste=vaktliste)} if vaktliste else {}

    # ── Per klokketime. Personer, ikke skift: én på to overlappende skift
    # er én person i timen. Møtt telles fra møtt-tidspunktet.
    personer = _timebolker([(p.fra_tid, p.til_tid, p.mannskap_id) for p in poster], lambda m: m)
    mott = _timebolker([(max(p.fra_tid, p.mott_at), p.til_tid, p.mannskap_id)
                        for p in poster if p.mott_at], lambda m: m)
    lag = _timebolker([(p.fra_tid, p.til_tid, p.ressurs_id) for p in poster
                       if p.ressurs.enhet_id is None], lambda r: r)
    enheter = _timebolker([(p.fra_tid, p.til_tid, p.ressurs.enhet_id) for p in poster
                           if p.ressurs.enhet_id is not None], lambda e: e)
    per_time = [{'time': t, 'personer': personer[t], 'mott': mott[t],
                 'lag': lag[t], 'enheter': enheter[t]} for t in range(24)]

    # ── Bemannet tid per ressurs (union av skiftene) ──
    skift_per_ressurs: dict[int, list] = {}
    for p in poster:
        skift_per_ressurs.setdefault(p.ressurs_id, []).append((p.fra_tid, p.til_tid))
    bemannet_per_ressurs = {rid: union(s) for rid, s in skift_per_ressurs.items()}
    enhetstimer = round(sum(_timer(b) for rid, b in bemannet_per_ressurs.items()
                            if ressurser[rid].enhet_id is not None), 2)
    lagtimer = round(sum(_timer(b) for rid, b in bemannet_per_ressurs.items()
                         if ressurser[rid].enhet_id is None), 2)
    persontimer = round(sum((p.til_tid - p.fra_tid).total_seconds() for p in poster) / 3600, 2)

    # ── Oppdrag mot bemanningen ──
    antall_oppdrag = Oppdrag.objects.filter(vakt=vakt).count()
    oppdrag_per_enhetstime = round(antall_oppdrag / enhetstimer, 2) if enhetstimer else None

    # ── Enhetsutnyttelse: oppdragstid som andel av bemannet tid, per enhet ──
    rader = list(Oppdragsenhet.objects.filter(oppdrag__vakt=vakt).select_related('enhet', 'oppdrag'))
    meldinger = Statusmelding.objects.gjeldende_bulk(list({r.oppdrag_id for r in rader}))
    opptatt_per_enhet: dict[int, list] = {}
    navn_per_enhet: dict[int, str] = {}
    for rad in rader:
        navn_per_enhet[rad.enhet_id] = rad.enhet.navn
        ledig = next((m.tidspunkt for m in meldinger.get(rad.oppdrag_id, [])
                      if m.oppdragsenhet_id == rad.pk and m.status == choices.LEDIG), None)
        opptatt_per_enhet.setdefault(rad.enhet_id, []).append((rad.varslet_at, ledig or naa))
    bemannet_per_enhet: dict[int, list] = {}
    for rid, b in bemannet_per_ressurs.items():
        r = ressurser[rid]
        if r.enhet_id is not None:
            bemannet_per_enhet.setdefault(r.enhet_id, []).extend(b)
            navn_per_enhet.setdefault(r.enhet_id, r.navn)
    utnyttelse = {}
    for enhet_id, navn in sorted(navn_per_enhet.items(), key=lambda p: p[1]):
        bemannet = union(bemannet_per_enhet.get(enhet_id, []))
        opptatt = union(opptatt_per_enhet.get(enhet_id, []))
        bem_t = _timer(bemannet) if bemannet else None
        opp_t = _timer(opptatt)
        utnyttelse[navn] = {
            'bemannet_timer': bem_t,
            'oppdrag_timer': opp_t,
            # `None`, ikke 0, når bilen ikke er koblet til vaktlista: «ukjent»
            # skal stå der, ikke et tall som ser ut som en måling.
            'andel': round(min(opp_t / bem_t, 1.0) * 100) if bem_t else None,
            'lengste_ledig': lengste_hull(bemannet, opptatt) if bemannet else None,
            'oppdrag': len(opptatt_per_enhet.get(enhet_id, [])),
        }

    andeler = [u['andel'] for u in utnyttelse.values() if u['andel'] is not None]
    return {
        'har_vaktliste': vaktliste is not None,
        'per_time': per_time,
        'summary': {
            'personer': len({p.mannskap_id for p in poster}),
            'skift': len(poster),
            'mott': sum(1 for p in poster if p.mott_at),
            'persontimer': persontimer,
            'enhetstimer': enhetstimer,
            'lagtimer': lagtimer,
            'antall_oppdrag': antall_oppdrag,
            'oppdrag_per_enhetstime': oppdrag_per_enhetstime,
            'utnyttelse_median': round(smod.median(andeler)) if andeler else None,
        },
        'utnyttelse': utnyttelse,
    }


class BemanningStatistikkHandler(BaseStatistikkHandler):
    """Belastning mot bemanning. Krever `les_alle`: `les` er ett korps."""

    slug = 'vaktliste'
    display_name = 'Bemanning'
    order = 40
    nivaa = 'les_alle'

    def full_stats(self, vakt):
        return bemanning_stats(vakt)


def register_handlers() -> None:
    """Kalles fra ``vaktliste.apps.VaktlisteConfig.ready()``."""
    register(BemanningStatistikkHandler())
