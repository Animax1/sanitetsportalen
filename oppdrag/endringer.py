"""Oppdragsmodulens område i endringsnummeret (`core/endringer.py`, 24. sep. 2026).

**`oppdrag`** er sentralbordets to lister: enhetene og oppdragene. Samme lister
i `/oppdrag/` og i KO, og derfor meldt inn **her** og ikke av KO — oppdrags-
modulen får ikke kjenne KO, og sentralbordet på `/oppdrag/` skal være like
raskt uten den.

Hva som øker tallet, står i `oppdrag/signals.py` (modulens egne modeller) og i
`ko/signals.py` (hendelsens prioritet, lagene og delte linjer, som står på
oppdraget i lista). Retningen er `ko` → `oppdrag`, som ellers: KO kaller
`oppdrag_endret()`, oppdragsmodulen vet ikke at KO finnes.

Gaten er listenes egen: `les` i oppdragsmodulen. Bilens skjerm har samme nivå,
men følger ikke tallet — den leser bare egne oppdrag og har sin egen polling.
"""
from core import endringer
from core.auth_decorators import har_tilgang

OPPDRAG = 'oppdrag'


def oppdrag_gate(request) -> bool:
    return har_tilgang(request.user, 'oppdrag', 'les')


def register_handlers() -> None:
    endringer.registrer(OPPDRAG, oppdrag_gate)


def oppdrag_endret() -> None:
    endringer.endret(OPPDRAG)
