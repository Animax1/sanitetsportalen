"""Base-klasse og register for backup-handlere per modul.

Hver modul som ønsker per-modul-backup registrerer en subklasse av
``BaseBackupHandler``. Handler-en svarer på:

- hva som skal serialiseres (apps + ekskluderte modeller)
- hvordan en backup gjenopprettes (hvilke modeller skal slettes først,
  i hvilken rekkefølge)

Dette lar core.backup.service være helt modul-agnostisk og hindrer at
hver ny app må reimplementere serialisering.
"""
from __future__ import annotations

from typing import ClassVar


class BaseBackupHandler:
    """Subklasses for hver modul som skal backupes.

    Subklassen MÅ sette ``slug`` (matcher ModuleSettings.slug) og bør
    overstyre ``apps`` og/eller ``exclude``. ``restore_models`` brukes
    av default-restore for å slette i riktig rekkefølge før loaddata.
    """
    #: Modul-slug. MÅ være unik på tvers av handlers og matche
    #: ModuleSettings.slug for riktig kobling i admin-UI.
    slug: ClassVar[str] = ''

    #: Menneskelig navn (vises i admin-UI). Settes av subklasse.
    display_name: ClassVar[str] = ''

    #: Liste over Django-app-labels som skal inkluderes i dumpdata.
    apps: ClassVar[list[str]] = []

    #: Modeller som skal ekskluderes (format: 'app_label.ModelName').
    #: Brukes for å unngå selvreferanse (f.eks. backup-tabellen).
    exclude: ClassVar[list[str]] = []

    #: Modeller som default-restore skal slette før loaddata,
    #: i FK-trygg rekkefølge (barn først, foreldre sist).
    #: Format: 'app_label.ModelName'. Hvis tom liste, slettes ingen
    #: modeller — restore kjører kun loaddata.
    restore_models: ClassVar[list[str]] = []

    def collect_apps(self) -> list[str]:
        """Returner apps til dumpdata. Default: self.apps."""
        if not self.apps:
            raise NotImplementedError(
                f'{self.__class__.__name__} må sette `apps` eller '
                f'overstyre collect_apps().'
            )
        return list(self.apps)

    def collect_exclude(self) -> list[str]:
        """Returner ekskluderte modeller. Default: self.exclude."""
        return list(self.exclude)

    def get_restore_models(self) -> list[str]:
        """Returner modeller som skal slettes før loaddata. Default: self.restore_models."""
        return list(self.restore_models)

    def __str__(self) -> str:
        return f'<BackupHandler slug={self.slug!r}>'


class _Registry:
    """Intern registry — bruk register()/get_handler()/all_handlers().

    Holdes separat fra modul-globale variabler for å gjøre testing enklere.
    """
    def __init__(self) -> None:
        self._handlers: dict[str, BaseBackupHandler] = {}

    def register(self, handler: BaseBackupHandler) -> None:
        if not handler.slug:
            raise ValueError(
                f'Handler {handler.__class__.__name__} mangler slug.'
            )
        self._handlers[handler.slug] = handler

    def get(self, slug: str) -> BaseBackupHandler | None:
        return self._handlers.get(slug)

    def all(self) -> list[BaseBackupHandler]:
        return list(self._handlers.values())

    def clear(self) -> None:
        """Bare for tester."""
        self._handlers.clear()


_registry = _Registry()


def register(handler: BaseBackupHandler) -> None:
    """Registrer en handler. Kalles fra app.ready() i hver modul."""
    _registry.register(handler)


def get_handler(slug: str) -> BaseBackupHandler | None:
    """Hent handler for gitt modul-slug, eller None."""
    return _registry.get(slug)


def all_handlers() -> list[BaseBackupHandler]:
    """Liste over alle registrerte handlers."""
    return _registry.all()


def clear_registry() -> None:
    """Bare ment for testbruk — nullstill registry."""
    _registry.clear()
