"""Modul-registry for Sanitetsportalen.

Definerer ``Module``-baseklassen som hver app deklarerer i sin egen
``module.py``, og et globalt registry der alle moduler er listet eksplisitt.

Designvalg (Fase 3a, Beslutning 1B):
- ``Module``-konfigurasjon lever per app (``patients/module.py``,
  ``accounts/module.py`` osv.) for å holde app-spesifikk kode lokalt.
- Den eksplisitte registreringen gjøres sentralt i ``core/modules.py`` slik at
  hele portalens omfang er synlig på ett sted.

Hvordan legge til en ny modul:
1. Lag ``<app>/module.py`` med en klasse som arver fra ``Module``.
2. Importer klassen i ``_REGISTERED_MODULES`` nederst i denne fila.
3. Hvis modulen krever et nytt permission-flagg på ``CustomUser``, legg til
   feltet via migrasjon i ``accounts``.

Modulen vises på dashboardet og i nav-menyen kun hvis:
- modulen er ``enabled=True`` i ``ModuleSettings``, og
- brukeren har permission-flagget angitt av ``permission_flag`` (eller flagget
  er ``None`` for moduler som er åpne for alle innloggede brukere).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class Module:
    """Konfigurasjon for én portal-modul.

    Frosset dataklasse gjør instansene uforanderlige og hashable. Alle felter
    er deklarative — ingen logikk i klassen selv.

    Args:
        slug: Unik nøkkel som matcher Django-app-label (``'patients'``,
            ``'accounts'`` osv.). Brukes i ``ModuleSettings.slug`` og i
            ``AuditLog.app_label``.
        name: Visningsnavn på dashboardet (norsk, brukes også i navigasjon).
        description: Kort beskrivelse til modulkortet.
        url: URL-prefiks som modulen lever på (eks. ``'/pasienter/'``).
            Kan være ``None`` for moduler uten egen forside (f.eks. interne
            tjenester som logger til AuditLog uten UI).
        icon: Bootstrap-ikon-klasse uten ``bi-``-prefiks
            (f.eks. ``'clipboard-pulse'``).
        permission_flag: Navnet på BooleanField på ``CustomUser`` som styrer
            om brukeren ser modulen. ``None`` = synlig for alle innloggede.
            Hvis flagget ikke finnes på modellen behandles modulen som
            usynlig for alle (defensivt).
        admin_only: Hvis ``True`` vises modulen kun for brukere med
            ``role='admin'``. Permission-flagget ignoreres da.
        is_core: Kjernemodul som ikke kan deaktiveres via UI. Dashboard-toggle
            i ``ModuleSettings``-admin er disabled for slike moduler.
        order: Sorteringsnøkkel — lavere kommer først i meny og dashboard.
        show_in_nav: Hvis ``False`` vises modulen kun på dashboardet, ikke i
            den øverste nav-baren. Nyttig for sjeldent brukte moduler.
        show_in_dashboard: Hvis ``False`` vises modulen kun i nav-baren.
            Nyttig for tjenester uten egen landingsside (f.eks. innstillinger).
    """

    slug: str
    name: str
    description: str
    url: Optional[str]
    icon: str
    permission_flag: Optional[str] = None
    admin_only: bool = False
    is_core: bool = False
    order: int = 100
    show_in_nav: bool = True
    show_in_dashboard: bool = True

    def is_visible_for(self, user) -> bool:
        """Avgjør om modulen skal vises for gitt bruker.

        Tar IKKE hensyn til ``ModuleSettings.enabled`` — det sjekkes separat i
        ``get_visible_modules`` slik at admin alltid kan se hvilke moduler som
        er deaktivert (f.eks. som overvåkings-info i ``ModuleSettings``-admin).
        """
        if user is None or not getattr(user, 'is_authenticated', False):
            return False

        # Admin ser alltid alt — uavhengig av flagg.
        if getattr(user, 'role', None) == 'admin':
            return True

        if self.admin_only:
            return False

        if self.permission_flag is None:
            return True

        # Defensivt: hvis flagget ikke er definert på brukermodellen,
        # behandler vi modulen som usynlig i stedet for å feile.
        return bool(getattr(user, self.permission_flag, False))


# ─────────────────────────────────────────────────────────────────────────────
# Eksplisitt modul-registrering
#
# Hver modul importeres fra sin egen app sin module.py. Rekkefølgen her
# bestemmer ikke visningsrekkefølge (det styres av Module.order), men holder
# importene samlet for oversikt.
# ─────────────────────────────────────────────────────────────────────────────


def _build_registry() -> tuple[Module, ...]:
    """Bygg det globale modul-registeret.

    Importene skjer inne i funksjonen for å unngå sirkulære imports under
    Django-oppstart (apps må være ferdig lastet før modeller refereres).
    """
    from accounts.module import AccountsModule  # noqa: WPS433
    from core.module import CoreModule  # noqa: WPS433
    from patients.module import PatientsModule  # noqa: WPS433

    return (
        CoreModule,
        AccountsModule,
        PatientsModule,
    )


_REGISTRY_CACHE: Optional[tuple[Module, ...]] = None


def get_all_modules() -> tuple[Module, ...]:
    """Returner alle registrerte moduler i sortert rekkefølge.

    Cacher resultatet etter første kall siden registret er statisk gjennom
    prosessens levetid.
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        modules = _build_registry()
        _REGISTRY_CACHE = tuple(sorted(modules, key=lambda m: (m.order, m.slug)))
    return _REGISTRY_CACHE


def reset_registry_cache() -> None:
    """Tøm cache — kun for test-bruk."""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = None


def get_module(slug: str) -> Optional[Module]:
    """Slå opp én modul på slug, eller ``None`` hvis ukjent."""
    for module in get_all_modules():
        if module.slug == slug:
            return module
    return None


def get_visible_modules(user, *, only_enabled: bool = True) -> list[Module]:
    """Returner moduler som skal vises for gitt bruker.

    Args:
        user: Innlogget bruker (``CustomUser``-instans). Kan være anonym —
            da returneres tom liste.
        only_enabled: Hvis ``True`` (default) filtreres moduler som er
            deaktivert i ``ModuleSettings`` bort. Sett ``False`` for å få
            alle synlige moduler uavhengig av enabled-status (brukes f.eks.
            i admin-UI for å vise hele listen med togglestatus).

    Returnerer modulene i sortert rekkefølge (``order``, deretter ``slug``).
    """
    visible = [m for m in get_all_modules() if m.is_visible_for(user)]

    if not only_enabled:
        return visible

    # Lazy import for å unngå at modules.py drar inn modeller før Django er klar.
    from core.models import ModuleSettings  # noqa: WPS433

    enabled_slugs = ModuleSettings.get_enabled_slugs()
    return [m for m in visible if m.is_core or m.slug in enabled_slugs]


def get_dashboard_modules(user) -> list[Module]:
    """Moduler som skal vises som kort på dashboardet."""
    return [m for m in get_visible_modules(user) if m.show_in_dashboard]


def get_nav_modules(user) -> list[Module]:
    """Moduler som skal vises i nav-baren (alle sider som extender base_portal)."""
    return [m for m in get_visible_modules(user) if m.show_in_nav]
