"""KOs områder i endringsnummeret (`core/endringer.py`, 24. sep. 2026).

**`tavle`** er det første. Gaten er tavlas egen: `les` i KO (`tavle_view`)
og `les` i vaktlista (`_tavle_gate`) — et tall man ikke får se bildet bak,
skal man heller ikke få, for det sier at noe har skjedd.

Hva som øker tallet, står i `ko/signals.py`: signaler på modellene tavla
leser, i KO, vaktlista, oppdragsmodulen og innstillingene. Retningen er
`ko` → de andre, som ellers.

**`logg`** (24. sep. 2026) er loggstrømmen og hendelsene — alt `logg_view`
sender: linjene, fjernede og festede, delingene og hendelseslista med lag,
deltakere og antallet åpne oppdrag. Gaten er `logg_view`s: `les` i KO.

Oppdragslista i KO er **ikke** et KO-område: den er sentralbordets, og følger
`oppdrag`, som oppdragsmodulen melder inn (`oppdrag/endringer.py`). KO øker
det tallet for det KO skriver på oppdragene i lista — prioriteten, lagene og
delte linjer (`ko/signals.py`).
"""
from core import endringer
from core.auth_decorators import har_tilgang

TAVLE = 'tavle'
LOGG = 'logg'


def tavle_gate(request) -> bool:
    return har_tilgang(request.user, 'ko', 'les') and har_tilgang(request.user, 'vaktliste', 'les')


def logg_gate(request) -> bool:
    return har_tilgang(request.user, 'ko', 'les')


def register_handlers() -> None:
    endringer.registrer(TAVLE, tavle_gate)
    endringer.registrer(LOGG, logg_gate)


def tavla_endret() -> None:
    endringer.endret(TAVLE)


def loggen_endret() -> None:
    endringer.endret(LOGG)
