"""Base-klasse og register for arkiv-handlere per modul.

Arkivmønsteret ble innført for pasientmodulen (GDPR-tiltaksplan fase 3.1–3.2)
og består av fire deler som gjentar seg for hver modul som skal arkivere data:

1. **Frysing** — et snapshot låses, med brukernavnet på den som arkiverte
   frosset i et tekstfelt slik at kontoen kan slettes etterpå (art. 17).
2. **Integritet** — SHA-256 over kanonisk JSON, verifisert ved hver visning.
3. **Kollaps** — etter N måneder slettes radnivået permanent og erstattes av
   frosset aggregat, fordi art. 5(1)(e) ikke tillater helseopplysninger på
   radnivå på ubestemt tid.
4. **Sperre** — kollaps nektes med mindre en backup finnes fra etter at
   arkivet ble opprettet, slik at slettingen er gjenopprettbar.

Park- og oppdragsmodulen trenger samme livsløp. Mønsteret ligger derfor her i
stedet for å kopieres per app.

**Arbeidsdelingen er bevisst:** core eier kanonisering, hashing og
orkestrering av kollaps. Handleren eier *hva* som går inn i payloaden. Det er
det som gjør at pasientmodulens signaturer er bit-identiske etter flyttingen —
payloaden bygges fortsatt av pasientkode, med `'pasienter'` som nøkkel og
sortering på `pasientnummer`. Hadde core bestemt payload-formen, ville hvert
eksisterende arkiv i produksjon meldt tukling.

Å legge til arkivering i en ny modul:

1. Lag en subklasse av ``BaseArkivHandler`` i ``<app>/arkiv.py``
2. Registrer den fra ``apps.ready()`` med ``register(MinHandler())``
3. Bruk ``core.arkiv.kollaps()`` og ``core.arkiv.verifiser()`` i modulens
   views og management-kommandoer
"""
from __future__ import annotations

from typing import ClassVar


class BaseArkivHandler:
    """Subklasses per modul som skal arkivere data.

    Subklassen MÅ sette ``slug`` og implementere ``sha_payload()``,
    ``aggregat_sha_payload()``, ``bygg_aggregat()`` og ``slett_rader()``.
    """

    #: Unik nøkkel for modulen. Brukes i registryet og i logging.
    slug: ClassVar[str] = ''

    #: Menneskelig navn til logg og admin-visning.
    display_name: ClassVar[str] = ''

    #: Slug til `core.backup`-handleren som dekker arkivet. Kollaps nektes
    #: med mindre det finnes en backup med denne slugen tatt etter at
    #: arkivet ble opprettet.
    backup_slug: ClassVar[str] = ''

    #: Antall dager før radnivået kollapser til aggregat. 730 = 24 måneder,
    #: som dekker to hele sesonger slik at årets vakt kan sammenlignes med
    #: fjorårets under planleggingen.
    retention_dager: ClassVar[int] = 730

    def sha_payload(self, arkiv, rader: list[dict]) -> dict:
        """Bygg dicten som hashes for radnivå-signaturen.

        **Endres denne, kan ingen eksisterende arkiv verifiseres igjen.**
        Nøkkelnavn, feltutvalg og sortering er alle del av signaturen.
        """
        raise NotImplementedError

    def aggregat_sha_payload(self, arkiv, aggregat: dict) -> dict:
        """Bygg dicten som hashes for aggregat-signaturen.

        Overtar integritetssjekken etter kollaps, siden radnivå-signaturen er
        beregnet over rader som ikke lenger finnes.
        """
        raise NotImplementedError

    def rad_dicts(self, arkiv) -> list[dict]:
        """Hent radene som inngår i signaturen, som dicts."""
        raise NotImplementedError

    def bygg_aggregat(self, arkiv) -> dict:
        """Beregn statistikken som skal fryses. Skal ikke slette noe."""
        raise NotImplementedError

    def slett_rader(self, arkiv) -> int:
        """Slett radnivået permanent. Returner antall slettede rader.

        Kalles kun fra ``core.arkiv.kollaps()``, inne i en transaksjon.
        """
        raise NotImplementedError

    def __str__(self) -> str:
        return f'<ArkivHandler slug={self.slug!r}>'


class _Registry:
    """Intern registry. Bruk register()/get_handler()/all_handlers()."""

    def __init__(self) -> None:
        self._handlers: dict[str, BaseArkivHandler] = {}

    def register(self, handler: BaseArkivHandler) -> None:
        if not handler.slug:
            raise ValueError(
                f'{handler.__class__.__name__} mangler slug — '
                'arkiv-handlere må ha en unik slug.'
            )
        # Idempotent: apps.ready() kan kjøre flere ganger under testing.
        self._handlers[handler.slug] = handler

    def get(self, slug: str) -> BaseArkivHandler | None:
        return self._handlers.get(slug)

    def all(self) -> list[BaseArkivHandler]:
        return list(self._handlers.values())


_registry = _Registry()


def register(handler: BaseArkivHandler) -> None:
    """Registrer en arkiv-handler. Kalles fra ``apps.ready()``."""
    _registry.register(handler)


def get_handler(slug: str) -> BaseArkivHandler | None:
    """Hent handler for en modul, eller None hvis den ikke er registrert."""
    return _registry.get(slug)


def all_handlers() -> list[BaseArkivHandler]:
    """Alle registrerte handlere."""
    return _registry.all()
