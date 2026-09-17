"""Register for moduler som har data med en lagringstid å håndheve.

`purge_old_logs` kjøres av Railway Cron og rydder rammeverkets egne tabeller —
`AuditLog`, `LoginEvent` og `core.Notification`. Fra 17. sep. 2026 har også en
**modul** data med en frist: KO-loggen.

**Jobben kan ikke bare importere `ko`.** `audit/` er rammeverk
(`TEKNISK_GJELD.md` §1) og måles med samme målestokk som `core` i
`core/tests_avhengighetsretning.py` — retningen går én vei, og en cron-jobb er
ingen unntaksgrunn. Det er samme retningsproblem driftsdashbordet og
portalinnstillingene hadde, og svaret er det samme: et register modulen melder
seg inn i.

Å legge til en ny:

1. Lag en subklasse av ``BaseOppryddingHandler`` i ``<app>/opprydding.py``
2. Registrer den fra ``apps.ready()``
3. `purge_old_logs` rydder den, uten at `audit` eller `core` endres

**Fristen eies av modulen, ikke av jobben.** Jobben spør «hva har løpt ut?» og
teller svaret; *hvor lenge* er modulens sak, fordi det er modulen som vet hva
dataene er. `--days` på kommandoen gjelder derfor rammeverkets egne tabeller og
rører ikke handlerne — ellers ville ett flagg stilt på to helt ulike
lagringstider samtidig.
"""
from __future__ import annotations

from typing import ClassVar


class BaseOppryddingHandler:
    """Subklasses per modul som har data med en lagringstid."""

    #: Modul-slug. Brukes i utskriften og i feilmeldinger.
    slug: ClassVar[str] = ''

    #: Hva som ryddes, i flertall og klartekst: «KO-logglinjer». Står i
    #: cron-loggen, som er det eneste stedet noen noen gang leser dette.
    etikett: ClassVar[str] = ''

    def frist_dager(self) -> int:
        """Lagringstiden modulen håndhever nå. Bare til utskriften."""
        raise NotImplementedError

    def antall_utlopte(self, naa) -> int:
        """Hvor mange rader som *ville* blitt slettet. Brukes av `--dry-run`."""
        raise NotImplementedError

    def rydd(self, naa) -> int:
        """Slett det som har løpt ut. Returnerer antallet."""
        raise NotImplementedError


_REGISTER: dict[str, BaseOppryddingHandler] = {}


def register(handler: BaseOppryddingHandler) -> None:
    """Registrer en handler. Kalles fra ``apps.ready()``.

    Idempotent på slug: `ready()` kan kjøre flere ganger i en testkjøring, og
    to registreringer av samme modul ville talt slettingen dobbelt i
    utskriften.
    """
    if not handler.slug:
        raise ValueError('Oppryddingshandler uten slug.')
    _REGISTER[handler.slug] = handler


def all_handlers() -> list[BaseOppryddingHandler]:
    """Handlerne, sortert på slug — så cron-loggen ser lik ut hver uke."""
    return [_REGISTER[s] for s in sorted(_REGISTER)]


def clear_registry() -> None:
    """Bare for tester."""
    _REGISTER.clear()
