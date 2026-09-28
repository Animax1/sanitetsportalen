"""Backup-handler for park-modulen.

Registrert i **samme commit som modellen** (se `backlog/backup.py` for hvorfor).
En backup, ikke et arkiv: park følger arkiveringen når den flytter til
`/portal-admin/` (`TODO.md`), som KO.

**Rekkefølgen:** `Registrering.vakt` peker på `core.Vakt` med et heltall, så
portalfila må være lastet først. Pekerne til vaktlistas ressurs og
oppdragsmodulens lokasjon strippes — navnene er frosset ved siden av — så park
binder ikke til noen annen modulfil og står sist i
`core.backup.GJENOPPRETTINGSREKKEFOLGE`.

**Lenkene er med, og det er trygt:** raden bærer hashen av tokenet, ikke
tokenet. En gjenopprettet lenke virker igjen for den som har den i
tiltakskortet, innenfor oppetiden — og kan fjernes som før.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class ParkBackupHandler(BaseBackupHandler):
    slug = 'park'
    display_name = 'Park'

    apps = ['park']
    exclude = []

    #: Alle brukerpekerne strippes; navnene står frosset på radene. Én slettet
    #: konto ville ellers tatt hele gjenopprettingen med seg. `ressurs` og
    #: `lokasjon` strippes av samme grunn som i KO: kantene ut av modulen ville
    #: bundet park til `vaktliste` og `oppdrag` i gjenopprettingen, og navnet
    #: er det statistikken teller.
    strip_fields = {
        'park.Parklenke': ['opprettet_av', 'fjernet_av'],
        'park.Registrering': ['ressurs', 'lokasjon', 'slettet_av'],
        # `lokasjon` beholdes med vilje: uten den er raden meningsløs. Det
        # binder park til oppdragsfila i gjenopprettingen, og park står alt
        # etter `oppdrag` i rekkefølgen. Brukerpekeren strippes som de andre.
        'park.SkjultSted': ['skjult_av'],
    }


def register_handlers() -> None:
    """Kalles fra `ParkConfig.ready()`."""
    register(ParkBackupHandler())
