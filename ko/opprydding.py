"""KO-loggens lagringstid, håndhevet av `purge_old_logs`.

Se `core/opprydding.py` for registeret og `ko/services.py` for hvor fristen
bor. Kort: **730 dager som standard, styrt av en `AppSetting`** og ikke av en
Railway-variabel — en variabel har ingen auditspor, må settes likt på både web-
og cron-tjenesten, og er usynlig i portalen.
"""
from __future__ import annotations

from core.opprydding import BaseOppryddingHandler, register

from . import services
from .models import Logglinje


class KoLoggOpprydding(BaseOppryddingHandler):
    slug = 'ko'
    etikett = 'KO-logglinjer'

    def frist_dager(self) -> int:
        return services.oppbevaringsdager()

    def antall_utlopte(self, naa) -> int:
        return self._utlopte(naa).count()

    def rydd(self, naa) -> int:
        return services.slett_utlopte(naa)

    def _utlopte(self, naa):
        """Samme grense som `services.slett_utlopte`, uten slettingen.

        Grensen regnes ut **ett sted** — i `services` — og hentes hit. To
        utregninger av samme frist ville før eller siden gitt en tørrkjøring
        som lovte noe annet enn den skarpe kjøringen gjorde, og da er
        tørrkjøringen verre enn ingen.
        """
        from datetime import timedelta

        grense = naa - timedelta(days=services.oppbevaringsdager())
        return Logglinje.objects.filter(registrert_at__lt=grense)


def register_handlers() -> None:
    """Kalles fra `KoConfig.ready()`."""
    register(KoLoggOpprydding())
