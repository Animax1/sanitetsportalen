"""Oppdragsmodulens bidrag til driftsdashbordet (14. sep. 2026).

Lå i `core/admin_status.py` som en direkte import av `oppdrag.models` fram til
statusregisteret ble bygget. Se `core/driftstatus.py`.
"""
from __future__ import annotations

from django.utils import timezone

from core.driftstatus import BaseDriftstatusHandler, register


class OppdragDriftstatus(BaseDriftstatusHandler):
    slug = 'oppdrag'
    order = 20

    def vaktbilde(self, vakt) -> dict:
        """Tavla for den aktive vakta.

        `vakt` kan være `None` — da har portalen ingen aktiv vakt, og
        `vakt_id=None` gir null rader. Det er riktig svar: det er ingenting
        på tavla når det ikke finnes en tavle.
        """
        from oppdrag import choices
        from oppdrag.models import Oppdrag

        tavla = Oppdrag.objects.filter(
            vakt_id=(vakt.pk if vakt else None), historikk_fra__isnull=True)
        ventende = tavla.filter(status=choices.VENTER, trenger_ressurs=False)
        eldste = ventende.order_by('created_at').first()
        return {
            'oppdrag': {
                'paa_tavla': tavla.count(),
                'ventende': ventende.count(),
                'trenger_ressurs': tavla.filter(trenger_ressurs=True).count(),
                'eldste_ventende_minutter': (
                    int((timezone.now() - eldste.created_at).total_seconds() / 60)
                    if eldste else None),
            },
        }


def register_handlers() -> None:
    register(OppdragDriftstatus())
