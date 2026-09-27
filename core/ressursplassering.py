"""Register for moduler som vet hvor en ressurs står nå.

`/park/` forhåndsvelger stedet et lag registrerer fra (`docs/FORSLAG_PARK.md`
§5.1, B19): det nyeste av KOs plassering på tavla og lagets siste
registrering. Park kan ikke importere `ko` — KO står øverst — og KO skal ikke
kjenne park (B15). Samme idiom som `core/kontokobling.py` og
`core/driftstatus.py`: modulen som *vet* melder seg inn, modulen som *spør*
spør registeret, og ingen av dem kjenner den andre.

Å melde inn en kilde:

1. Lag en subklasse i ``<app>/ressursplassering.py`` med ``slug`` og
   ``aapen_plassering()``
2. Registrer den fra ``apps.ready()``

**En modul som er slått av i `ModuleSettings` spørres ikke.** En avslått KO
skal ikke lyse gjennom parksiden, like lite som gjennom statistikken.

**Og en feilende kilde gir `None`, ikke 500** — forhåndsvalget er et
hjelpemiddel; siden laget registrerer fra skal virke uten det.
"""
from __future__ import annotations

import logging
from typing import ClassVar

logger = logging.getLogger(__name__)


class BaseRessursplasseringHandler:
    """Subklasses per modul som plasserer ressurser på steder."""

    #: Modul-slug. Nøkkel i registeret, og modulen som må være slått på.
    slug: ClassVar[str] = ''

    def aapen_plassering(self, ressurs_id: int) -> dict | None:
        """``{'lokasjon_id', 'lokasjon_navn', 'fra'}`` der ressursen står nå.

        ``None`` når ressursen ikke står på et sted — ikke plassert, på pause,
        eller opptatt av noe som ikke er et sted.
        """
        raise NotImplementedError

    def __str__(self) -> str:
        return f'<RessursplasseringHandler slug={self.slug!r}>'


_handlers: dict[str, BaseRessursplasseringHandler] = {}


def register(handler: BaseRessursplasseringHandler) -> None:
    """Registrer en handler. Kalles fra `apps.ready()` i hver modul."""
    if not handler.slug:
        raise ValueError(f'Handler {handler.__class__.__name__} mangler slug.')
    _handlers[handler.slug] = handler


def aapen_plassering(ressurs_id: int) -> dict | None:
    """Første kilde som vet hvor ressursen står, blant modulene som er på."""
    from core.models import ModuleSettings

    aktive = ModuleSettings.get_enabled_slugs()
    for slug in sorted(_handlers):
        if slug not in aktive:
            continue
        try:
            svar = _handlers[slug].aapen_plassering(ressurs_id)
        except Exception:
            logger.warning('Ressursplassering fra %r feilet — forhåndsvalget '
                           'går videre uten den.', slug, exc_info=True)
            continue
        if svar is not None:
            return svar
    return None


def all_handlers() -> list[BaseRessursplasseringHandler]:
    return [_handlers[s] for s in sorted(_handlers)]


def clear_registry() -> None:
    """Bare ment for testbruk."""
    _handlers.clear()
