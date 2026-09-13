"""Hel databasebackup — katastrofekopien (13. sep. 2026).

Modulfilene dekker hver sin modul og har 730 dagers oppbevaring, fordi
kollapsen etter 24 måneder er irreversibel og krever at slettingen er
gjenopprettbar. Denne fila dekker **alt**, og har 90 dager, fordi den bærer
legitimasjon og logg. Se `docs/BACKUP.md` §1 for hvorfor fristen følger
innholdet og ikke omvendt.

## Hvorfor den finnes nå, når den ble valgt bort før

Begrunnelsen mot var at en backupfil på volumet med passordhasher og
TOTP-hemmeligheter er en legitimasjonsdump. Den var riktig for en ukryptert
fil. Med AES-256-GCM før opplasting, og en nøkkel Scaleway ikke har, er
innholdet ikke lesbart for noen uten `OFFSITE_BACKUP_KEY`. Prisen for å *ikke*
ha den var at gjenoppretting i tom base begynte med `create_admin` og kontoer
for hånd — og ingen hadde skrevet ned den prosedyren.

## Hva som er utelatt, og hvorfor

| Utelatt | Grunn |
|---|---|
| `sessions.Session` | Innlogginger som uansett er utløpt, og som ville gitt gamle økter tilbake |
| `contenttypes.ContentType`, `auth.Permission` | Gjenskapes av `migrate`. Lastes de på nytt, kolliderer primærnøklene — og `natural_foreign` gjør at alt som peker på dem finner fram uansett |
| `admin.LogEntry` | Django-admin er av i prod (S1) |
| `patients.Backup`, `core.OffsiteKopi`, `core.Backupplan` | Metadata *om* backupfiler. Å laste dem tilbake ville gjenopplive rader for filer som ikke finnes |

**Appene listes ikke opp for hånd.** `collect_apps()` regner dem ut fra
app-registeret ved hvert kall, så en ny modul er med fra den dagen den finnes.
En hardkodet liste ville vært en ny sjanse til å glemme noe — og en
katastrofekopi som stille mangler en app er verre enn ingen, fordi man tror man
har den.
"""
from __future__ import annotations

from .handlers import BaseBackupHandler, register

#: Apper som aldri skal med. `staticfiles` og `messages` har ingen modeller,
#: men står her så lista leses som «alt unntatt dette».
UTELATTE_APPER = {'sessions', 'contenttypes', 'staticfiles', 'messages'}

#: Enkeltmodeller som skal ut, selv om appen deres er med.
UTELATTE_MODELLER = [
    'auth.Permission',
    'admin.LogEntry',
    'patients.Backup',
    'patients.BackupConfig',
    'core.OffsiteKopi',
    'core.Backupplan',
]


class FullBackupHandler(BaseBackupHandler):
    """Alt i databasen, i én fil.

    Gjenopprettingen går gjennom den samme `restore_backup` som modulene:
    tøm i barn-først-rekkefølge, så `loaddata`. Rekkefølgen utledes over
    *hele* settet, så en fremmednøkkel på tvers av apper teller like mye som
    en innenfor.
    """

    slug = 'full'
    display_name = 'Hele databasen'

    exclude = list(UTELATTE_MODELLER)

    #: FK-er til brukere strippes **ikke** her, i motsetning til modulfilene:
    #: brukerne er med i denne fila, så det er ingen risiko for at en natural
    #: key peker på en konto som ikke finnes. Det er nettopp poenget med en hel
    #: backup — den er selvbærende.
    strip_fields = {}

    def collect_apps(self) -> list[str]:
        """Alle installerte apper med modeller, unntatt `UTELATTE_APPER`.

        Regnes ut ved hvert kall framfor å stå i en liste: en ny app skal være
        med fra dagen den finnes, ikke fra dagen noen husker å føre den opp.
        """
        from django.apps import apps as django_apps

        return sorted(
            konfig.label for konfig in django_apps.get_app_configs()
            if konfig.label not in UTELATTE_APPER and list(konfig.get_models())
        )


def register_handlers() -> None:
    """Kalles fra `CoreConfig.ready()`."""
    register(FullBackupHandler())
