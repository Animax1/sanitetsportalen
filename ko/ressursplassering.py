"""KOs plassering av lagene, meldt inn i `core/ressursplassering.py`.

`/park/` forhåndsvelger stedet et lag registrerer fra, og KOs tavle er den ene
kilden (`docs/FORSLAG_PARK.md` §5.1). KO kjenner ikke park (B15) — den svarer
bare registeret på hvor en ressurs står.

**Bare en åpen plassering på et sted teller.** Pause er ikke et sted, og et lag
på en hendelse har ingen åpen plassering (`tavle.avslutt_for_hendelse`).
"""
from __future__ import annotations

from core.ressursplassering import BaseRessursplasseringHandler, register


class KoRessursplassering(BaseRessursplasseringHandler):
    slug = 'ko'

    def aapen_plassering(self, ressurs_id: int) -> dict | None:
        from .models import Tavleplassering

        rad = (Tavleplassering.objects
               .filter(ressurs_id=ressurs_id, til__isnull=True, pause=False,
                       lokasjon__isnull=False)
               .only('lokasjon_id', 'lokasjon_navn', 'fra')
               .first())
        if rad is None:
            return None
        return {'lokasjon_id': rad.lokasjon_id, 'lokasjon_navn': rad.lokasjon_navn,
                'fra': rad.fra}


def register_handlers() -> None:
    register(KoRessursplassering())
