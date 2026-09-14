"""Register for moduler som bidrar med tall til driftsdashbordet.

`/portal-admin/server-status/` viser to ting som ikke er portalens egne:
hvilke vaktlister som er i drift og når fila sist gikk ut (vaktlista), og hvor
mange oppdrag som står på tavla (oppdrag). Fram til 14. sep. 2026 hentet
`core/admin_status.py` dem ved å importere modulene direkte.

Det virket. Problemet var retningen: **rammeverket kjente modulene ved navn.**
Så lenge filene lå i `patients` leste koblingen som «modul → modul» og var
usynlig; da server-status flyttet til `core`, ble den «rammeverk → modul».
Samme sted `core/stats.py` sto for et år siden, med samme svar.

Å legge til tall fra en ny modul:

1. Lag en subklasse av ``BaseDriftstatusHandler`` i ``<app>/driftstatus.py``
2. Registrer den fra ``apps.ready()`` med ``register(MinHandler())``
3. Ferdig — dashbordet henter den uten å vite at modulen finnes

**Nøklene handleren returnerer er handlerens, ikke registerets.** Vaktlista
leverer `vaktlister_i_drift` og `siste_utsending`, oppdrag leverer `oppdrag`;
de skal ikke presses inn i samme skjema for å se like ut. Samme arbeidsdeling
som i `core.arkiv` og `core.stats`, der handleren eier payloadens form.

**Hver handler fanges hver for seg.** Et dashbord som selv gir 500 fordi én
modul har en treg spørring, er borte akkurat når man trenger det — og da er
det viktigere å se de andre kortene enn å vite at ett mangler. Feilen havner i
`error` i svaret, som før.
"""
from __future__ import annotations

from typing import ClassVar


class BaseDriftstatusHandler:
    """Subklasses per modul som skal levere tall til driftsdashbordet."""

    #: Modul-slug. Brukes som nøkkel i registeret og i feilmeldinger.
    slug: ClassVar[str] = ''

    #: Rekkefølge nøklene slås sammen i. Lavest først. Betyr lite i praksis —
    #: nøklene er disjunkte — men gjør utfallet forutsigbart hvis to handlere
    #: en dag skulle levere samme nøkkel.
    order: ClassVar[int] = 100

    def vaktbilde(self, vakt) -> dict:
        """Tall om den aktive vakta. ``vakt`` kan være ``None``.

        Returner en dict som slås sammen inn i `vaktbilde`-delen av svaret.
        """
        return {}

    def epost(self) -> dict:
        """Siste e-post modulen sendte, hvis den sender noen.

        Slås sammen inn i `epost`-delen. Portalen sender ikke e-post selv
        utenom feilvarsel, så dette er modulenes å svare på.
        """
        return {}

    def __str__(self) -> str:
        return f'<DriftstatusHandler slug={self.slug!r}>'


class _Registry:
    def __init__(self) -> None:
        self._handlers: dict[str, BaseDriftstatusHandler] = {}

    def register(self, handler: BaseDriftstatusHandler) -> None:
        if not handler.slug:
            raise ValueError(
                f'Handler {handler.__class__.__name__} mangler slug.')
        self._handlers[handler.slug] = handler

    def all(self) -> list[BaseDriftstatusHandler]:
        return sorted(self._handlers.values(), key=lambda h: (h.order, h.slug))

    def clear(self) -> None:
        self._handlers.clear()


_registry = _Registry()


def register(handler: BaseDriftstatusHandler) -> None:
    """Registrer en handler. Kalles fra `apps.ready()` i hver modul."""
    _registry.register(handler)


def all_handlers() -> list[BaseDriftstatusHandler]:
    """Alle registrerte handlere, sortert på (order, slug)."""
    return _registry.all()


def clear_registry() -> None:
    """Bare ment for testbruk."""
    _registry.clear()


def samle(metode: str, *args) -> tuple[dict, str]:
    """Kall ``metode`` på hver handler og slå sammen svarene.

    Returnerer ``(verdier, feil)``. Feilen er tom når alt gikk bra; ellers er
    den den *siste* feilen, i samme form som `admin_status` skrev den før —
    dashbordet har ett `error`-felt, og et kort som viser fire feilmeldinger
    samtidig er ikke mer lesbart enn ett som viser den siste.
    """
    from core.admin_status import _scrub_secrets

    ut: dict = {}
    feil = ''
    for handler in all_handlers():
        try:
            ut.update(getattr(handler, metode)(*args) or {})
        except Exception as exc:   # noqa: BLE001 — se modulens docstring
            feil = _scrub_secrets(f'{handler.slug}: {exc}')[:200]
    return ut, feil
