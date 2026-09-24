"""KOs områder i endringsnummeret (`core/endringer.py`, 24. sep. 2026).

**`tavle`** er det første. Gaten er tavlas egen: `les` i KO (`tavle_view`)
og `les` i vaktlista (`_tavle_gate`) — et tall man ikke får se bildet bak,
skal man heller ikke få, for det sier at noe har skjedd.

Hva som øker tallet, står i `ko/signals.py`: signaler på modellene tavla
leser, i KO, vaktlista, oppdragsmodulen og innstillingene. Retningen er
`ko` → de andre, som ellers.
"""
from core import endringer
from core.auth_decorators import har_tilgang

TAVLE = 'tavle'


def tavle_gate(request) -> bool:
    return har_tilgang(request.user, 'ko', 'les') and har_tilgang(request.user, 'vaktliste', 'les')


def register_handlers() -> None:
    endringer.registrer(TAVLE, tavle_gate)


def tavla_endret() -> None:
    endringer.endret(TAVLE)
