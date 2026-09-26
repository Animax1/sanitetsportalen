"""Tidsintervaller slått sammen — ett sted (26. sep. 2026, E5).

Løkka sto tre ganger i vaktlista: `statistikk.union` (bemannet tid per
ressurs), `pauser._slaa_sammen` (lagets skiftspenn) og inne i
`services._overlappstimer` (sum minus union). De to første var like; den
tredje var skrevet om med `start`/`slutt` og egne kommentarer om hvilke
mutanter som var ekvivalente. Tre kopier av samme regel er tre steder en
retting kan glemmes.

**Intervaller som møtes, slås sammen.** Et lag med skift 14–22 og 22–06 er
på vakt 14–06, ikke to ganger. **Tomme og baklengse intervaller** (`til <=
fra`) forkastes her, slik at kallstedet ikke må huske det.
"""
from __future__ import annotations


def slaa_sammen(intervaller):
    """`(fra, til)`-par sortert og slått sammen der de overlapper eller møtes."""
    ut = []
    for fra, til in sorted(i for i in intervaller if i[1] > i[0]):
        if ut and fra <= ut[-1][1]:
            ut[-1] = (ut[-1][0], max(ut[-1][1], til))
        else:
            ut.append((fra, til))
    return ut


def sekunder(intervaller) -> float:
    """Samlet lengde, i sekunder."""
    return sum((til - fra).total_seconds() for fra, til in intervaller)
