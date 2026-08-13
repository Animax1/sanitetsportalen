"""
Signals for pasient-app.

- AuditLog: CREATE/UPDATE/DELETE logges for hver pasient-endring.
- Notification (Fase 5): når ``forstehjelper`` eller ``helsepersonell_ref``
  tildeles eller flyttes mellom brukere, varsles berørte parter via
  core.notifications.notify(). Både ny mottaker og forrige eier varsles
  ved flytting, kun ny mottaker ved første tildeling.
"""
import logging

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .models import Patient, Forstehjelper, Helsepersonell
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


# Felter som bevisst ikke audit-logges (N2).
#
# Lista er over *unntakene*, ikke over det som spores. Det er en bevisst
# vending: tidligere sto den håndholdte lista over sporede felt her, og
# `helsepersonell_ref_id` hadde falt ut av den uten at noe fanget det opp.
# Endring av oppfølgingsansvarlig etterlot dermed ingen spor — samtidig som
# PERSONVERN_DOKUMENTASJON A.10 lovet at alle pasientendringer logges på
# feltnivå. Med unntakslista må et nytt felt aktivt legges til her for å slippe
# unna loggen; glemsomhet gir nå for mye logging, ikke for lite.
FELT_UTEN_AUDIT = frozenset({
    'id',             # intern PK, endres aldri
    'pasientnummer',  # settes ved opprettelse, endres aldri
    'created_at',     # auto_now_add
    'updated_at',     # auto_now — ville gitt en audit-rad ved hver lagring
})


def felt_som_spores():
    """Utled hvilke feltnavn som skal audit-logges, fra modellen selv.

    Returnerer ``attname``, ikke ``name``: for en ForeignKey gir det
    ``forstehjelper_id`` og ``helsepersonell_ref_id``, altså ID-en som faktisk
    lagres — som er det vi vil ha i loggen, og som ikke utløser en ekstra
    spørring når vi leser den av objektet.
    """
    return [
        f.attname
        for f in Patient._meta.concrete_fields
        if f.name not in FELT_UTEN_AUDIT and f.attname not in FELT_UTEN_AUDIT
    ]


def _audit_verdi(obj, felt):
    """Formater en feltverdi for audit-loggen.

    Tidligere sto det ``str(getattr(obj, felt, '') or '')``. Den varianten
    kollapser alle falsy verdier til tom streng — også ``False``. Konsekvensen
    var at deaktivering av en pasient ble logget med ``new_value=''`` i stedet
    for ``'False'``, og at DELETE-grenen under (som sammenlikner mot
    ``'False'``) aldri kunne slå til. Deaktiveringer har derfor alltid stått
    som UPDATE i loggen.

    Kun ``None`` blir tom streng nå — det er den verdien som faktisk betyr
    «ikke satt», typisk en FK uten referanse.
    """
    verdi = getattr(obj, felt, None)
    return '' if verdi is None else str(verdi)


@receiver(pre_save, sender=Patient)
def patient_pre_save(sender, instance, **kwargs):
    """Logg feltendringer (UPDATE) for eksisterende pasienter.

    Lagrer også originale FK-ID-er som transient attributter på ``instance``
    (``_orig_forstehjelper_id``, ``_orig_helsepersonell_ref_id``) slik at
    post_save kan oppdage flyttinger og sende varsler.
    """
    if not instance.pk:
        # Ny pasient – håndteres av post_save. Marker som ny slik at
        # tildelings-varsel sendes for forstehjelper/helsepersonell som
        # settes ved opprettelsen.
        instance._orig_forstehjelper_id = None
        instance._orig_helsepersonell_ref_id = None
        return

    try:
        old = Patient.objects.get(pk=instance.pk)
    except Patient.DoesNotExist:
        instance._orig_forstehjelper_id = None
        instance._orig_helsepersonell_ref_id = None
        return

    # Lagre originalverdier for post_save (varsel-signal)
    instance._orig_forstehjelper_id = old.forstehjelper_id
    instance._orig_helsepersonell_ref_id = old.helsepersonell_ref_id

    user, ip = _get_user_and_ip()

    for field in felt_som_spores():
        old_val = _audit_verdi(old, field)
        new_val = _audit_verdi(instance, field)
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
        # ── Førstehjelper-FK ──
        orig_b_id = getattr(patient, '_orig_forstehjelper_id', None) if not created else None
        new_b_id = patient.forstehjelper_id
        if created:
            # Ved CREATE: kun varsle ny mottaker (ingen forrige)
            if new_b_id is not None:
                _notify_assignment(patient, patient.forstehjelper, role='førstehjelper')
        elif orig_b_id != new_b_id:
            # FK endret seg
            if new_b_id is not None:
                _notify_assignment(patient, patient.forstehjelper, role='førstehjelper')
            if orig_b_id is not None:
                try:
                    prev = Forstehjelper.objects.get(pk=orig_b_id)
                except Forstehjelper.DoesNotExist:
                    prev = None
                if prev is not None:
                    _notify_transfer(patient, prev, new_owner=patient.forstehjelper,
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
