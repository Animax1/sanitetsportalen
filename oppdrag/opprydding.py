"""Fristen på oppdragets frie tekst, håndhevet av `purge_old_logs`.

Se `oppdrag/fritekstfrist.py` for regelen og `core/opprydding.py` for
registeret. Jobben går natt til søndag; vis-regelen skjuler teksten straks
fristen er ute, så den sene feiingen viser aldri noe den ikke skulle.
"""
from __future__ import annotations

from core.opprydding import BaseOppryddingHandler, register

from . import fritekstfrist


class FritekstOpprydding(BaseOppryddingHandler):
    slug = 'oppdrag'
    etikett = 'oppdrag med fritekst eller «Annet sted»-tekst tømt'

    def frist_dager(self) -> int:
        return fritekstfrist.frist_dager()

    def antall_utlopte(self, naa) -> int:
        return fritekstfrist.antall_utlopte(naa)

    def rydd(self, naa) -> int:
        return fritekstfrist.tom_utlopte(naa)


def register_handlers() -> None:
    """Kalles fra `OppdragConfig.ready()`."""
    register(FritekstOpprydding())
