"""Backup-handler for det portalvide — vakta og moduloppsettet (13. sep. 2026).

**Uten denne kan ingen av de andre filene gjenopprettes i en tom base.**
`core.Vakt` er scopet alt henger på: pasienter, oppdrag og vaktlister peker på
den med fremmednøkkel, og `Vakt` har ingen natural key, så pekeren lagres som
et heltall. Er raden ikke der når modulfila lastes, feiler hele
gjenopprettingen — og en tom base er nettopp det offsite-kopien finnes for.
Hullet sto åpent fram til nå; se `docs/TEKNISK_GJELD.md` §4.

Derfor er portalfila **først** i gjenopprettingsrekkefølgen:
portal → patients → arkiv → oppdrag → oppdrag_arkiv → vaktliste.

## Hva som ikke er med, og hvorfor

- **`Backupplan` og `OffsiteKopi`** er metadata *om* backup. Å laste dem
  tilbake fra en backup ville gjenopplive rader for filer som ikke finnes, og
  sette klokka tilbake til tilstanden den hadde da fila ble tatt.
  `Backupplan.hent()` lager planene på nytt med fornuftige verdier.
- **`Notification`** er varsler med en påkrevd FK til en bruker. Den kan ikke
  strippes (feltet må ha en verdi), og med `natural_foreign` ville en slettet
  konto tatt hele gjenopprettingen med seg. Varslene er dessuten transiente —
  `purge_old_logs` sletter dem etter 30 dager.

`AppSetting` hører hjemme her, men bor fortsatt i pasientmodulen og dekkes av
pasientfila. Den flytter hit sammen med resten av det portalvide
(`docs/TEKNISK_GJELD.md` §2), og da utvides `apps` under.
"""
from __future__ import annotations

from .handlers import BaseBackupHandler, register


class PortalBackupHandler(BaseBackupHandler):
    """Vakta og moduloppsettet — grunnlaget de andre filene hviler på."""

    slug = 'portal'
    display_name = 'Portal (vakter og moduloppsett)'

    #: `AppSetting` kom hit 14. sep. 2026, i **samme** deploy som modellen
    #: flyttet fra `patients` — ikke en fase senere, som planen først sa.
    #: Pasientfila dumpet `apps = ['patients']` og fikk innstillingene med på
    #: kjøpet; portalfila lister modellene sine ved navn. Ventet vi, ville
    #: portalinnstillingene — aktiv vakt, lydvarslene, e-postmottakerne — ligget
    #: utenfor **alle** backupfiler i mellomtiden, uten at noe sa fra.
    apps = ['core.Vakt', 'core.ModuleSettings', 'core.AppSetting']
    exclude = []

    #: `ModuleSettings.updated_by` er sporet av hvem som slo modulen av eller
    #: på. Med `natural_foreign` lagres den som brukernavnet, og en slettet
    #: konto ville da tatt hele gjenopprettingen med seg. Hvem som gjorde det
    #: står i audit-loggen; hva som er på og av, er det denne fila skal bære.
    strip_fields = {'core.ModuleSettings': ['updated_by']}


def register_handlers() -> None:
    """Kalles fra `CoreConfig.ready()`."""
    register(PortalBackupHandler())
