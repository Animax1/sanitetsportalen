"""
Signals for pasient-app.
Loggfører CREATE, UPDATE og DELETE til AuditLog.
"""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import Patient
from audit.models import AuditLog
from audit.utils import get_current_request


def _get_user_and_ip():
    """Hent bruker og IP fra thread-local request."""
    request = get_current_request()
    user = None
    ip = None
    if request:
        user = getattr(request, 'user', None)
        if user and not user.is_authenticated:
            user = None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
    return user, ip


@receiver(pre_save, sender=Patient)
def patient_pre_save(sender, instance, **kwargs):
    """Logg feltendringer (UPDATE) for eksisterende pasienter."""
    if not instance.pk:
        return  # Ny pasient – håndteres av post_save

    try:
        old = Patient.objects.get(pk=instance.pk)
    except Patient.DoesNotExist:
        return

    user, ip = _get_user_and_ip()

    # Spor alle endrede felt (behandler_id logges automatisk som FK-endring)
    felt_to_track = [
        'problemstilling', 'arsak', 'transport', 'inntid', 'grovsortering',
        'pabegynt', 'plassering', 'behandler_id', 'helsepersonell', 'lege',
        'medisiner', 'inn_obspost', 'ut_obspost', 'utskrevet',
        'utskrevet_til', 'journal', 'year', 'is_active',
    ]

    for field in felt_to_track:
        old_val = str(getattr(old, field, '') or '')
        new_val = str(getattr(instance, field, '') or '')
        if old_val != new_val:
            action = 'DELETE' if field == 'is_active' and new_val == 'False' else 'UPDATE'
            AuditLog.objects.create(
                table_name='patients_patient',
                record_id=instance.pk,
                action=action,
                field_name=field,
                old_value=old_val,
                new_value=new_val,
                user=user,
                ip=ip,
            )


@receiver(post_save, sender=Patient)
def patient_post_save(sender, instance, created, **kwargs):
    """Logg opprettelse (CREATE) av ny pasient."""
    if not created:
        return

    user, ip = _get_user_and_ip()

    AuditLog.objects.create(
        table_name='patients_patient',
        record_id=instance.pk,
        action='CREATE',
        field_name=None,
        old_value=None,
        new_value=str(instance.pasientnummer),
        user=user,
        ip=ip,
    )


@receiver(post_delete, sender=Patient)
def patient_post_delete(sender, instance, **kwargs):
    """Logg hard-sletting av pasient (skal ikke skje normalt)."""
    user, ip = _get_user_and_ip()

    AuditLog.objects.create(
        table_name='patients_patient',
        record_id=instance.pk,
        action='DELETE',
        field_name=None,
        old_value=str(instance.pasientnummer),
        new_value=None,
        user=user,
        ip=ip,
    )
