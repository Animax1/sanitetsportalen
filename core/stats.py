"""Register for moduler som leverer statistikk.

Statistikkmodulen samler tall fra portalens moduler. Fram til fase 6 av
oppdragsmodulen importerte den ``patients.services`` direkte — det virket så
lenge det fantes én kilde, men var også hele grunnen til at en kilde nummer to
ikke kunne legges til uten å endre statistikkappen. Registeret her er samme
idiom som ``core.backup`` og ``core.arkiv``: modulen som eier dataene eier
også utregningen, og statistikkappen henter, cacher og viser.

Å legge til statistikk fra en ny modul:

1. Lag en subklasse av ``BaseStatistikkHandler`` i ``<app>/statistikk.py``
2. Registrer den fra ``apps.ready()`` med ``register(MinHandler())``
3. Bygg fanen i grensesnittet — endepunktet finnes fra og med registreringen

**Registeret kjenner ikke tilgangskontroll**, like lite som backup-registeret
gjør det. Hvilke kilder en bruker får se avgjøres av statistikkappen (§5:
modulen komponerer tilgang, den eier den ikke) — den spør ``har_tilgang`` for
hver registrerte slug. Ville registeret filtrert selv, måtte det kjent
brukeren, og da ville en ny kaller lett fått med seg kilder den ikke skulle.

**Formen på payloaden er handlerens, ikke registerets.** Pasienttallene har
`summary`/`crosstab_*`/`kw_*`, oppdragstallene har `per_hastegrad` og
responstider — de to skal ikke presses inn i samme skjema for å se like ut.
Grensesnittet har uansett én fane per kilde. Samme arbeidsdeling som i
``core.arkiv``, der handleren eier payloadens form.
"""
from __future__ import annotations

from typing import ClassVar


class BaseStatistikkHandler:
    """Subklasses per modul som skal levere tall til statistikksiden.

    Subklassen MÅ sette ``slug`` og implementere ``full_stats()``.
    """

    #: Modul-slug. MÅ matche modulregistryets slug — den brukes både som
    #: nøkkel her og som modulen tilgangen sjekkes mot. Er de to ulike, ville
    #: statistikkappen sjekket tilgang mot en modul som ikke finnes, og
    #: `har_tilgang` svarer False på ukjent slug: kilden ville vært usynlig
    #: for alle uten at noe feilet.
    slug: ClassVar[str] = ''

    #: Fanenavn i grensesnittet.
    display_name: ClassVar[str] = ''

    #: Rekkefølge på fanene. Lavest først.
    order: ClassVar[int] = 100

    def full_stats(self, vakt) -> dict:
        """Tallene for én vakt. Returner en JSON-serialiserbar dict."""
        raise NotImplementedError

    def arkiv_full_stats(self, pk):
        """Tallene for ett arkiv, eller ``None`` hvis det ikke finnes.

        ``None`` dekker begge de to måtene et arkiv kan mangle på: modulen
        arkiverer ikke ennå (oppdrag, fram til fase 7), eller pk-en peker på
        noe som ikke finnes. Klienten skal se det samme i begge tilfeller —
        «det er ikke noe arkiv der» — så de deler svar med vilje.
        """
        return None

    def __str__(self) -> str:
        return f'<StatistikkHandler slug={self.slug!r}>'


class _Registry:
    """Intern registry — bruk register()/get_handler()/all_handlers()."""

    def __init__(self) -> None:
        self._handlers: dict[str, BaseStatistikkHandler] = {}

    def register(self, handler: BaseStatistikkHandler) -> None:
        if not handler.slug:
            raise ValueError(
                f'Handler {handler.__class__.__name__} mangler slug.'
            )
        self._handlers[handler.slug] = handler

    def get(self, slug: str) -> BaseStatistikkHandler | None:
        return self._handlers.get(slug)

    def all(self) -> list[BaseStatistikkHandler]:
        # Sortert, ikke innsettingsrekkefølge: rekkefølgen her blir
        # fanerekkefølgen, og innsettingen følger INSTALLED_APPS. Da ville et
        # bytte i settings flyttet på fanene uten at noen mente det.
        return sorted(self._handlers.values(), key=lambda h: (h.order, h.slug))

    def clear(self) -> None:
        """Bare for tester."""
        self._handlers.clear()


_registry = _Registry()


def register(handler: BaseStatistikkHandler) -> None:
    """Registrer en handler. Kalles fra app.ready() i hver modul."""
    _registry.register(handler)


def get_handler(slug: str) -> BaseStatistikkHandler | None:
    """Hent handler for gitt modul-slug, eller None."""
    return _registry.get(slug)


def all_handlers() -> list[BaseStatistikkHandler]:
    """Alle registrerte handlere, sortert på (order, slug)."""
    return _registry.all()


def clear_registry() -> None:
    """Bare ment for testbruk — nullstill registry."""
    _registry.clear()
