"""Backup-handler for backlog-modulen.

Registreres fra `apps.ready()`, i **samme commit som modellen**. Vaktlistemodulen
sto uten backup i det hele tatt fra den gikk i prod til 13. sep. 2026 — det ble
oppdaget ved en gjennomgang, ikke av noe rødt.

Én enhet, ikke to: backloggen har ikke noe arkiv som fryser. `lost` er et flagg
på raden, og raden hører til samme datasett som resten.

**Ingen `vakt`-peker**, så modulen er selvbærende og har ingen plass i
gjenopprettingsrekkefølgen — den kan lastes når som helst. Det er den ene
fordelen ved å stå utenfor vaktscopet, og den er verdt å notere: hver annen
modulfil forutsetter at portalfila er lastet først.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class BacklogBackupHandler(BaseBackupHandler):
    """Backup av backlog-modulen.

    Slettelista før `loaddata` utledes av `apps` (barn før foreldre), så en
    modell som legges til senere blir dekket uten at noen må huske en liste.
    """

    slug = 'backlog'
    display_name = 'Backlog'

    apps = ['backlog']
    exclude = []

    #: **Begge brukerpekerne strippes, og navnene er grunnen til at det er
    #: gratis.** Serialiseringen kjører med `natural_foreign`, så en FK til en
    #: konto lagres som brukernavnet — er kontoen slettet i mellomtiden, feiler
    #: **hele** gjenopprettingen med DeserializationError, altså akkurat når man
    #: trenger backupen.
    #:
    #: `opprettet_av_navn` og `lost_av_navn` står frosset på raden og bærer
    #: opplysningen: hvem som meldte inn, og hvem som løste. FK-ene bærer bare
    #: «er dette meg?», som angrefristen bruker — og et innspill gjenopprettet
    #: fra en backup er uansett eldre enn den timen.
    strip_fields = {
        'backlog.Innspill': ['opprettet_av', 'lost_av'],
    }


def register_handlers() -> None:
    """Kalles fra `BacklogConfig.ready()`."""
    register(BacklogBackupHandler())
