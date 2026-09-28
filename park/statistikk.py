"""Fanen «Lag» i `/statistikk/` (pulje 3, B12) — og handleren som melder den inn.

**Tallene teller kontakter, ikke pasienter** (`FORSLAG_KO.md` §8). Én registrering
kan gjelde flere (`antall`, B9), så fanen skiller *registreringer* (trykk på
«Registrer») fra *kontakter* (summen av antall). Og en person laget hjalp kan
senere havne i `/pasienter/` og på et oppdrag — tre registre, tre målinger, som
aldri summeres.

**Slettede registreringer telles ikke** (B20), men antallet står i svaret, så
den som leser tallene ser at det er ryddet i dem.

**Gaten er `park: les`** (B17), ikke KO: ledelsen får fanen, operatørene ikke.
`statistikk/views.py` komponerer tilgangen; handleren sier bare hvilket nivå.

Ingen arkiv ennå — park følger arkiveringen når den flytter til `/portal-admin/`.
"""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Max, Sum
from django.utils import timezone

from core.sortering import norsk_nokkel
from core.stats import BaseStatistikkHandler, register

from .models import Registrering


def _fordeling(rader, felt) -> list[dict]:
    """``[{navn, registreringer, kontakter}]``, flest kontakter først.

    Likt antall sorteres på navn med norsk alfabet — ellers er rekkefølgen
    databasens, og den er ikke den samme på SQLite og PostgreSQL.
    """
    ut = [{'navn': r[felt], 'registreringer': r['n'], 'kontakter': r['k'] or 0}
          for r in rader.values(felt).annotate(n=Count('id'), k=Sum('antall'))]
    ut.sort(key=lambda d: (-d['kontakter'], norsk_nokkel(d['navn'])))
    return ut


def _per_time(rader) -> list[dict]:
    """Kontakter per time på døgnet, i norsk tid. Alle 24 timene, så et hull
    i aktiviteten synes som et hull og ikke forsvinner."""
    teller = defaultdict(int)
    for tid, antall in rader.values_list('registrert_at', 'antall'):
        teller[timezone.localtime(tid).hour] += antall
    return [{'time': t, 'kontakter': teller[t]} for t in range(24)]


def _kryss(rader, per_problemstilling, per_utfall) -> dict:
    """Problemstilling × utfall, i kontakter. Radene og kolonnene står i samme
    rekkefølge som fordelingene, så tabellen leses ovenfra og ned."""
    celler = defaultdict(int)
    for ps, utf, antall in rader.values_list('problemstilling', 'utfall', 'antall'):
        celler[(ps, utf)] += antall
    rekker = [p['navn'] for p in per_problemstilling]
    kolonner = [u['navn'] for u in per_utfall]
    return {'rader': rekker, 'kolonner': kolonner,
            'celler': [[celler[(r, k)] for k in kolonner] for r in rekker]}


def _per_lag(rader) -> list[dict]:
    ut = [{'navn': r['ressurs_navn'], 'registreringer': r['n'], 'kontakter': r['k'] or 0,
           'siste': r['siste'].isoformat() if r['siste'] else None}
          for r in rader.values('ressurs_navn').annotate(
              n=Count('id'), k=Sum('antall'), siste=Max('registrert_at'))]
    ut.sort(key=lambda d: (-d['kontakter'], norsk_nokkel(d['navn'])))
    return ut


def _forhandsvalg(rader) -> list[dict]:
    """Målingen (B21): hvor stedet i nedtrekket kom fra, og hvor ofte laget
    byttet det. Endrer lagene ofte et forhåndsvalg fra KO, er tavla for treg
    til å være en god kilde — og da bør regelen «nyeste vinner» vurderes."""
    navn = dict(Registrering.FORHANDSVALG)
    ut = []
    for kilde, _ in Registrering.FORHANDSVALG:
        utvalg = rader.filter(forhandsvalg_kilde=kilde)
        n = utvalg.count()
        if not n:
            continue
        endret = utvalg.filter(forhandsvalg_endret=True).count()
        ut.append({'kilde': kilde, 'navn': navn[kilde], 'registreringer': n,
                   'endret': endret, 'andel_endret': round(100 * endret / n)})
    return ut


def park_stats(vakt) -> dict:
    alle = Registrering.objects.filter(vakt=vakt)
    rader = alle.filter(slettet_at__isnull=True)
    per_problemstilling = _fordeling(rader, 'problemstilling')
    per_utfall = _fordeling(rader, 'utfall')
    return {
        'summary': {
            'registreringer': rader.count(),
            'kontakter': rader.aggregate(k=Sum('antall'))['k'] or 0,
            'lag': rader.values('ressurs_navn').distinct().count(),
            'steder': rader.values('lokasjon_navn').distinct().count(),
            'slettet': alle.filter(slettet_at__isnull=False).count(),
        },
        'per_problemstilling': per_problemstilling,
        'per_utfall': per_utfall,
        'per_sted': _fordeling(rader, 'lokasjon_navn'),
        'per_lag': _per_lag(rader),
        'per_time': _per_time(rader),
        'kryss': _kryss(rader, per_problemstilling, per_utfall),
        'forhandsvalg': _forhandsvalg(rader),
    }


class ParkStatistikkHandler(BaseStatistikkHandler):
    """Fanen «Lag». `slug` er modulens, så gaten blir `park: les` (B17)."""

    slug = 'park'
    display_name = 'Lag'
    order = 35              # etter KO (30), før bemanningen (40)
    nivaa = 'les'

    def full_stats(self, vakt):
        return park_stats(vakt)


def register_handlers() -> None:
    """Kalles fra `ParkConfig.ready()`."""
    register(ParkStatistikkHandler())
