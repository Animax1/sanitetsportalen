"""Vaktlistas bidrag til driftsdashbordet (14. sep. 2026).

Lå i `core/admin_status.py` som en direkte import av `vaktliste.models` fram
til statusregisteret ble bygget. Se `core/driftstatus.py`.
"""
from __future__ import annotations

from django.utils import timezone

from core.driftstatus import BaseDriftstatusHandler, register


class VaktlisteDriftstatus(BaseDriftstatusHandler):
    slug = 'vaktliste'
    order = 10

    def vaktbilde(self, vakt) -> dict:
        from vaktliste import choices
        from vaktliste.models import Utsending, Vaktliste

        drift = [
            {'id': v.pk, 'vakt': v.vakt.navn,
             'siden': v.satt_i_drift_at.isoformat() if v.satt_i_drift_at else None}
            for v in (Vaktliste.objects.filter(status=choices.DRIFT)
                      .select_related('vakt'))
        ]
        u = Utsending.objects.order_by('-created_at').first()
        return {
            'vaktlister_i_drift': drift,
            'siste_utsending': None if u is None else {
                'tid': u.created_at.isoformat(),
                'minutter_siden': int(
                    (timezone.now() - u.created_at).total_seconds() / 60),
                'utloest': u.utloest,
                'antall_mottakere': len([
                    m for m in (u.mottakere or '').replace(';', ',').split(',')
                    if m.strip()]),
                'ok': not u.feil,
                'feil': (u.feil or '')[:200],
            },
        }

    def epost(self) -> dict:
        """Vaktlistefila er den e-posten portalen sender som betyr noe.

        Feilvarsel til `ADMINS` er portalens egen og går ikke gjennom
        `Utsending` — den vises ikke her, og skal ikke: et statuskort som
        sier «siste e-post gikk fint» om en feilmelding er villedende.
        """
        from vaktliste.models import Utsending

        siste_ok = Utsending.objects.filter(feil='').order_by('-created_at').first()
        siste = Utsending.objects.order_by('-created_at').first()
        return {
            'siste_ok_at': siste_ok.created_at.isoformat() if siste_ok else None,
            'siste_feil': (siste.feil[:200] if siste and siste.feil else None),
            'siste_feil_at': (siste.created_at.isoformat()
                              if siste and siste.feil else None),
        }


def register_handlers() -> None:
    register(VaktlisteDriftstatus())
