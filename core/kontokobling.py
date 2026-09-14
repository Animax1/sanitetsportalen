"""Register for moduler som kobler en portalkonto til sine egne rader.

Brukersiden under `/portal-admin/brukere/<pk>/` har et kort «Pasientregistrering»
der admin velger om kontoen er førstehjelper, helsepersonell eller ingen av
delene. Fram til 14. sep. 2026 lå det i `accounts/forms.py`, som en direkte
import av `patients.models` — altså **kontoappen som kjente én modul ved navn**
(`docs/TEKNISK_GJELD.md` §3.1).

Retningen er den samme feilen som `core/driftstatus.py` og
`core/portalinnstillinger.py` løste, bare i en annen app: `accounts` eier
kontoen, modulen eier hva en konto *betyr* hos den.

**Koblingen er domenedata, ikke tilgang.** Det er den viktigste setningen i
denne fila. Radioen satte tidligere også `kan_redigere_pasienter`, og
sammenblandingen gjorde det umulig å være koblet som førstehjelper uten å ha
skrivetilgang — og omvendt. Tilgang settes i matrisen modul × nivå; dette sier
bare hvem personen er i felt. Vaktlistas `Mannskap.user` er samme slags peker.

Å legge til kobling fra en ny modul:

1. Lag en subklasse i ``<app>/kontokobling.py`` med ``handling``, ``mal`` og
   ``skjema()``
2. Registrer den fra ``apps.ready()``
3. Kortet dukker opp på brukersiden uten at `accounts` endres

Malbiten leser sitt eget skjema som ``kontokoblinger.<slug>`` — slugen er
modulens egen, og står som en literal i modulens egen mal.
"""
from __future__ import annotations

from typing import ClassVar


class BaseKontokoblingHandler:
    """Subklasses per modul som kobler kontoer til sine egne rader."""

    #: Modul-slug. Nøkkel i registeret, og navnet malbiten slår opp på.
    slug: ClassVar[str] = ''

    #: Rekkefølge på kortene. Lavest først.
    order: ClassVar[int] = 100

    #: Verdien i skjemaets skjulte `action`-felt. **Må være unik** — viewet
    #: finner handleren på den. To moduler med samme handling ville latt den
    #: ene lagre den andres skjema.
    handling: ClassVar[str] = ''

    #: Sti til malbiten, f.eks. ``'patients/kontokobling.html'``.
    mal: ClassVar[str] = ''

    #: Meldingen som vises når lagringen gikk.
    suksessmelding: ClassVar[str] = 'Koblingen er oppdatert.'

    def skjema(self, user, data=None):
        """Skjemaet for denne kontoen. ``data`` er `request.POST` ved lagring."""
        raise NotImplementedError

    def __str__(self) -> str:
        return f'<KontokoblingHandler slug={self.slug!r}>'


class _Registry:
    def __init__(self) -> None:
        self._handlers: dict[str, BaseKontokoblingHandler] = {}

    def register(self, handler: BaseKontokoblingHandler) -> None:
        if not handler.slug:
            raise ValueError(
                f'Handler {handler.__class__.__name__} mangler slug.')
        if not handler.handling:
            raise ValueError(
                f'Handler {handler.__class__.__name__} mangler handling.')
        for annen in self._handlers.values():
            if annen.handling == handler.handling and annen.slug != handler.slug:
                raise ValueError(
                    f'Handlingen {handler.handling!r} er alt tatt av '
                    f'{annen.slug!r} — to moduler kan ikke dele den, for da '
                    f'ville den ene lagret den andres skjema.')
        self._handlers[handler.slug] = handler

    def all(self) -> list[BaseKontokoblingHandler]:
        return sorted(self._handlers.values(), key=lambda h: (h.order, h.slug))

    def for_handling(self, handling: str) -> BaseKontokoblingHandler | None:
        for h in self._handlers.values():
            if h.handling == handling:
                return h
        return None

    def clear(self) -> None:
        self._handlers.clear()


_registry = _Registry()


def register(handler: BaseKontokoblingHandler) -> None:
    """Registrer en handler. Kalles fra `apps.ready()` i hver modul."""
    _registry.register(handler)


def all_handlers() -> list[BaseKontokoblingHandler]:
    """Alle registrerte handlere, sortert på (order, slug)."""
    return _registry.all()


def for_handling(handling: str) -> BaseKontokoblingHandler | None:
    """Handleren som eier dette `action`-navnet, eller None."""
    return _registry.for_handling(handling)


def clear_registry() -> None:
    """Bare ment for testbruk."""
    _registry.clear()
