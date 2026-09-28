"""Lagregistreringenes lagringstid, håndhevet av `purge_old_logs` (28. sep. 2026).

Se `core/opprydding.py` for registeret og `park/services.py` for fristen.
Registreringene slettes `OPPBEVARING_DAGER` etter at de kom inn; lenkene,
verdimengdene og de skjulte stedene står.
"""
from __future__ import annotations

from core.opprydding import BaseOppryddingHandler, register

from . import services


class RegistreringOpprydding(BaseOppryddingHandler):
    slug = 'park'
    etikett = 'lagregistreringer'

    def frist_dager(self) -> int:
        return services.OPPBEVARING_DAGER

    def antall_utlopte(self, naa) -> int:
        # Samme spørring som slettingen — en tørrkjøring som regner fristen på
        # egen hånd lover før eller siden noe annet enn den skarpe gjør.
        return services.utlopte(naa).count()

    def rydd(self, naa) -> int:
        return services.slett_utlopte(naa)


def register_handlers() -> None:
    """Kalles fra `ParkConfig.ready()`."""
    register(RegistreringOpprydding())
