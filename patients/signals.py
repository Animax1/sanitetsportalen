"""
Signals for pasient-app.

- AuditLog: CREATE/UPDATE/DELETE logges for hver pasient-endring.
- Notification (Fase 5): når ``behandler`` eller ``helsepersonell_ref``
  tildeles eller flyttes mellom brukere, varsles berørte parter via
  core.notifications.notify(). Både ny mottaker og forrige eier varsles
  ved flytting, kun ny mottaker ved første tildeling.
"""
import logging

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import Patient, Behandler, Helsepersonell
from audit.models import AuditLog
from audit.utils import get_current_request
from core.notifications import notify

logger = logging.getLogger(__name__)


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
    """Logg feltendringer (UPDATE) for eksisterende pasienter.

    Lagrer også originale FK-ID-er som transient attributter på ``instance``
    (``_orig_behandler_id``, ``_orig_helsepersonell_ref_id``) slik at
    post_save kan oppdage flyttinger og sende varsler.
    """
    if not instance.pk:
        # Ny pasient – håndteres av post_save. Marker som ny slik at
        # tildelings-varsel sendes for behandler/helsepersonell som
        # settes ved opprettelsen.
        instance._orig_behandler_id = None
        instance._orig_helsepersonell_ref_id = None
        return

    try:
        old = Patient.objects.get(pk=instance.pk)
    except Patient.DoesNotExist:
        instance._orig_behandler_id = None
        instance._orig_helsepersonell_ref_id = None
        return

    # Lagre originalverdier for post_save (varsel-signal)
    instance._orig_behandler_id = old.behandler_id
    instance._orig_helsepersonell_ref_id = old.helsepersonell_ref_id

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
    """Logg opprettelse (CREATE) av ny pasient + send varsler."""
    if created:
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

    # ── Fase 5: varsel om tildeling/flytting ──
    _send_assignment_notifications(instance, created)


def _send_assignment_notifications(patient, created):
    """Send varsel når behandler eller helsepersonell_ref endret seg.

    Logikk:
    - Ved CREATE: varsle ny mottaker hvis FK er satt.
    - Ved UPDATE der FK endret seg:
        * Ny verdi != None  → varsle ny mottaker ('patient_assigned')
        * Gammel verdi != None → varsle forrige eier ('patient_transferred_away')
    - Hvis FK ikke endret seg: ingen varsel.

    Defensiv design: feiler aldri — logger evt. unntak og lar lagring
    fortsette uten varsel. Varsler skal aldri kunne hindre pasient-lagring.
    """
    try:
        # ── Behandler-FK ──
        orig_b_id = getattr(patient, '_orig_behandler_id', None) if not created else None
        new_b_id = patient.behandler_id
        if created:
            # Ved CREATE: kun varsle ny mottaker (ingen forrige)
            if new_b_id is not None:
                _notify_assignment(patient, patient.behandler, role='førstehjelper')
        elif orig_b_id != new_b_id:
            # FK endret seg
            if new_b_id is not None:
                _notify_assignment(patient, patient.behandler, role='førstehjelper')
            if orig_b_id is not None:
                try:
                    prev = Behandler.objects.get(pk=orig_b_id)
                except Behandler.DoesNotExist:
                    prev = None
                if prev is not None:
                    _notify_transfer(patient, prev, new_owner=patient.behandler,
                                     role='førstehjelper')

        # ── Helsepersonell-FK ──
        orig_h_id = getattr(patient, '_orig_helsepersonell_ref_id', None) if not created else None
        new_h_id = patient.helsepersonell_ref_id
        if created:
            if new_h_id is not None:
                _notify_assignment(patient, patient.helsepersonell_ref,
                                   role='oppfølgingsansvarlig')
        elif orig_h_id != new_h_id:
            if new_h_id is not None:
                _notify_assignment(patient, patient.helsepersonell_ref,
                                   role='oppfølgingsansvarlig')
            if orig_h_id is not None:
                try:
                    prev = Helsepersonell.objects.get(pk=orig_h_id)
                except Helsepersonell.DoesNotExist:
                    prev = None
                if prev is not None:
                    _notify_transfer(patient, prev,
                                     new_owner=patient.helsepersonell_ref,
                                     role='oppfølgingsansvarlig')
    except Exception:
        # Varsler skal ALDRI kunne føre til at pasient-lagring feiler.
        logger.exception('Feil ved opprettelse av tildelings-varsel for pasient pk=%s',
                         patient.pk)


def _notify_assignment(patient, role_obj, *, role):
    """Varsle ny mottaker om at de er tildelt en pasient."""
    if role_obj is None or role_obj.user is None:
        return
    notify(
        user=role_obj.user,
        module_slug='patients',
        kind='patient_assigned',
        title=f'Ny pasient tildelt',
        message=f'Du er satt som {role} for pasient #{patient.pasientnummer}.',
        url=f'/pasienter/?focus={patient.pasientnummer}',
    )


def _notify_transfer(patient, previous_obj, *, new_owner, role):
    """Varsle forrige eier om at pasienten er flyttet til en annen."""
    if previous_obj is None or previous_obj.user is None:
        return
    new_name = new_owner.name if new_owner is not None else 'ingen'
    notify(
        user=previous_obj.user,
        module_slug='patients',
        kind='patient_transferred_away',
        title='Pasient flyttet',
        message=(
            f'Pasient #{patient.pasientnummer} er flyttet fra deg som '
            f'{role} til {new_name}.'
        ),
        url=f'/pasienter/?focus={patient.pasientnummer}',
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
