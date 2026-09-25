"""Overnattingens lagringstid, håndhevet av `purge_old_logs` (25. sep. 2026).

Se `core/opprydding.py` for registeret og `vaktliste/overnatting.py` for fristen.
Plasseringene slettes 30 dager etter natta; rommene står.
"""
from __future__ import annotations

from core.opprydding import BaseOppryddingHandler, register

from . import overnatting


class OvernattingOpprydding(BaseOppryddingHandler):
    slug = 'vaktliste'
    etikett = 'overnattingsplasseringer'

    def frist_dager(self) -> int:
        return overnatting.OPPBEVARING_DAGER

    def antall_utlopte(self, naa) -> int:
        # Samme spørring som slettingen — en tørrkjøring som regner fristen på
        # egen hånd lover før eller siden noe annet enn den skarpe gjør.
        return overnatting.utlopte(naa).count()

    def rydd(self, naa) -> int:
        return overnatting.slett_utlopte(naa)


def register_handlers() -> None:
    """Kalles fra `VaktlisteConfig.ready()`."""
    register(OvernattingOpprydding())
