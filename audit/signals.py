"""Pre-save-signal som automatisk fyller AuditLog.app_label.

Designvalg (Fase 3a):
- Vi løser app_label-fylling med et signal i stedet for å overstyre ``save()``,
  slik at logikken også gjelder ``AuditLog.objects.create(...)`` og bulk-create
  (sistnevnte kun hvis Django utvides senere — bulk_create kjører ikke
  pre_save i dag, men det er ingen bulk_create-bruk i kodebasen).
- Logikken må holdes synkronisert med ``audit/migrations/0002_auditlog_app_label.py``
  (samme mapping). Endrer du denne, oppdater også migrasjonen for konsistens
  ved fremtidig restore fra backup.
"""
from __future__ import annotations

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import AuditLog


# Eksplisitt mapping for table_names som ikke følger app_<modell>-mønsteret.
# Hvis du legger til nye logiske kategorier (f.eks. 'cron', 'system'), tilordne
# dem her slik at admin kan filtrere på modul.
EKSPLISITT_MAPPING: dict[str, str] = {
    'backup': 'patients',
}


def utled_app_label(table_name: str) -> str:
    """Utled Django app_label fra et AuditLog.table_name.

    Args:
        table_name: F.eks. ``'patients_patient'``, ``'backup'``, ``'accounts_customuser'``.

    Returnerer Django app-label (f.eks. ``'patients'``) eller tom streng hvis
    ikke utledelig — da vises raden som "Ukjent" i admin-filteret.
    """
    if not table_name:
        return ''
    if table_name in EKSPLISITT_MAPPING:
        return EKSPLISITT_MAPPING[table_name]
    if '_' in table_name:
        return table_name.split('_', 1)[0]
    return table_name


@receiver(pre_save, sender=AuditLog)
def fyll_app_label(sender, instance: AuditLog, **kwargs):
    """Sett ``instance.app_label`` automatisk hvis det er tomt."""
    # Hvis caller eksplisitt har satt app_label, behold det.
    if instance.app_label:
        return
    instance.app_label = utled_app_label(instance.table_name)
