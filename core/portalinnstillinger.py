"""Register for moduler som har innstillinger på portalinnstillingssiden.

`/portal-admin/innstillinger/` eier portalens egne felter — vaktas navn og
sesjonstimeouten. Vaktlista la til fire til (mottakere, «send ved drift»,
intervall, «bare hvis endret»), og fram til 14. sep. 2026 gjorde den det ved
at *viewet* importerte `vaktliste.fil`: validering, lagring og malmarkup for én
modul, midt i rammeverkets side.

Samme retningsproblem som driftsdashbordet hadde, og samme svar. Se
`core/driftstatus.py`.

Å legge til innstillinger fra en ny modul:

1. Lag en subklasse av ``BasePortalinnstillingHandler`` i
   ``<app>/portalinnstillinger.py`` med ``mal`` som peker på en malbit
2. Registrer den fra ``apps.ready()``
3. Feltene dukker opp på siden, valideres og lagres uten at `core` endres

**Alt valideres før noe lagres.** Det er ikke en detalj: navnet skrives på
`Vakt`, timeouten og modulenes verdier i `AppSetting`, og ingen transaksjon
binder dem. Rekkefølgen i viewet er det eneste som hindrer at en avvist
innsending lagrer halve skjemaet, og `valider()`/`lagre()` er delt i to
nettopp for at en handler ikke skal kunne skrive noe før de andre har sagt ja.
`core/tests_portal_settings.py` og `vaktliste/tests_fil.py` håndhever det fra
hver sin side.
"""
from __future__ import annotations

from typing import ClassVar


class BasePortalinnstillingHandler:
    """Subklasses per modul som har innstillinger på portalens side."""

    #: Modul-slug. Brukes som nøkkel og i feilmeldinger.
    slug: ClassVar[str] = ''

    #: Rekkefølge på kortene. Lavest først, etter portalens egne.
    order: ClassVar[int] = 100

    #: Sti til malbiten som tegner feltene, f.eks.
    #: ``'vaktliste/portalinnstillinger.html'``. Malbiten bor i **modulen**,
    #: ikke i `core`: markupen kjenner feltene, og feltene er modulens.
    mal: ClassVar[str] = ''

    def kontekst(self) -> dict:
        """Verdier malbiten trenger. Slås sammen inn i sidens kontekst."""
        return {}

    def valider(self, post) -> dict:
        """Les `request.POST` og returner verdiene som skal lagres.

        Kast ``django.core.exceptions.ValidationError`` ved feil. **Skriv
        ingenting her** — se modulens docstring.
        """
        return {}

    def lagre(self, verdier: dict) -> None:
        """Skriv verdiene `valider()` returnerte. Kalles først når *alle*
        handlere, og portalens egne felter, har validert."""

    def __str__(self) -> str:
        return f'<PortalinnstillingHandler slug={self.slug!r}>'


class _Registry:
    def __init__(self) -> None:
        self._handlers: dict[str, BasePortalinnstillingHandler] = {}

    def register(self, handler: BasePortalinnstillingHandler) -> None:
        if not handler.slug:
            raise ValueError(
                f'Handler {handler.__class__.__name__} mangler slug.')
        self._handlers[handler.slug] = handler

    def all(self) -> list[BasePortalinnstillingHandler]:
        return sorted(self._handlers.values(), key=lambda h: (h.order, h.slug))

    def clear(self) -> None:
        self._handlers.clear()


_registry = _Registry()


def register(handler: BasePortalinnstillingHandler) -> None:
    """Registrer en handler. Kalles fra `apps.ready()` i hver modul."""
    _registry.register(handler)


def all_handlers() -> list[BasePortalinnstillingHandler]:
    """Alle registrerte handlere, sortert på (order, slug)."""
    return _registry.all()


def clear_registry() -> None:
    """Bare ment for testbruk."""
    _registry.clear()
