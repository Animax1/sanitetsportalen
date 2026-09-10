"""Audit-logging for vaktlistemodulen — fase 1: `Mannskap`.

Samme mønster som ``oppdrag/signals.py``, med samme unntak av samme grunn:
`notat` er fritekst, og fritekst er der helseopplysninger havner når det ikke
finnes et felt for dem. Kostbehov og allergier skal ikke inn i portalen (§7 i
beslutningsnotatet) — men skriver noen det i notatfeltet likevel og retter
det, skal ikke begge versjonene ligge i en logg med 730 dagers lagring.
Raden sier at feltet ble endret, av hvem og når; hva som sto der sier den
ikke.

Regelen er bygget inn fra første lagring, ikke ettermontert — samme
rekkefølgekrav som fase 2 i oppdragsmodulen, og av samme grunn: rader som er
skrevet feil kan ikke fjernes i ettertid uten å røre auditsporet.

Registrene (`Korps`, `Kompetanse`, `Ressursrolle`) auditlogges ikke på feltnivå:
de er organisasjonsoppsett uten personopplysninger, og endres fra
Django-admin, som har sin egen historikk.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from audit.models import AuditLog
from audit.utils import get_current_request

from .models import Mannskap

TABELLNAVN = 'vaktliste_mannskap'

logger = logging.getLogger(__name__)

# Felter som ikke gir en auditrad i det hele tatt. Unntaksliste, ikke
# inkluderingsliste — glemsomhet skal gi for mye logging, ikke for lite.
FELT_UTEN_AUDIT = frozenset({
    'id',
    'created_at',
    'updated_at',   # auto_now — ville gitt en rad ved hver lagring
})

# Felter som gir en auditrad, men **uten verdier**.
FELT_UTEN_VERDILOGGING = frozenset({
    'notat',
})

#: Det som skrives i stedet for verdien. En tom streng ville vært tvetydig —
#: den betyr «feltet var ikke satt» ellers i loggen.
SKJULT = '(skjult)'


def _bruker_og_ip():
    request = get_current_request()
    bruker = None
    ip = None
    if request:
        bruker = getattr(request, 'user', None)
        if bruker and not bruker.is_authenticated:
            bruker = None
        ip = request.META.get('REMOTE_ADDR')
    return bruker, ip


def _felter():
    """Konkrete kolonner på modellen, minus unntakene.

    M2M (`kompetanser`) er ikke en kolonne og fanges ikke av pre_save —
    endringer der går gjennom egne rader den dagen noen trenger det.
    """
    return [
        f.name for f in Mannskap._meta.concrete_fields
        if f.name not in FELT_UTEN_AUDIT
    ]


def _verdi(obj, felt):
    """Lesbar verdi for audit — eller `(skjult)` for unntatte felter.

    Kun ``None`` blir tom streng. Å kollapse alle falsy verdier ville gjort
    ``False`` til ``''`` — den feilen kostet pasientmodulen at
    deaktiveringer aldri ble logget riktig.
    """
    if felt in FELT_UTEN_VERDILOGGING:
        return SKJULT
    verdi = getattr(obj, felt, None)
    return '' if verdi is None else str(verdi)


@receiver(pre_save, sender=Mannskap)
def mannskap_pre_save(sender, instance, **kwargs):
    """Logg feltendringer for eksisterende mannskap."""
    if not instance.pk:
        return

    try:
        gammel = Mannskap.objects.get(pk=instance.pk)
    except Mannskap.DoesNotExist:
        return

    bruker, ip = _bruker_og_ip()
    for felt in _felter():
        gammel_verdi = _verdi(gammel, felt)
        ny_verdi = _verdi(instance, felt)
        # For unntatte felter er begge `(skjult)` — sammenlign rå verdier,
        # ellers ville en faktisk endring aldri gitt noen rad.
        if felt in FELT_UTEN_VERDILOGGING:
            if getattr(gammel, felt, None) == getattr(instance, felt, None):
                continue
        elif gammel_verdi == ny_verdi:
            continue
        AuditLog.objects.create(
            table_name=TABELLNAVN,
            record_id=instance.pk,
            action='UPDATE',
            field_name=felt,
            old_value=gammel_verdi,
            new_value=ny_verdi,
            user=bruker,
            ip=ip,
        )


@receiver(post_save, sender=Mannskap)
def mannskap_post_save(sender, instance, created, **kwargs):
    """Logg opprettelse."""
    if not created:
        return
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=TABELLNAVN,
        record_id=instance.pk,
        action='CREATE',
        field_name='',
        old_value='',
        new_value=str(instance),
        user=bruker,
        ip=ip,
    )


@receiver(post_delete, sender=Mannskap)
def mannskap_post_delete(sender, instance, **kwargs):
    """Logg sletting. Pensjonering er den normale veien ut; en faktisk
    sletting er verdt et spor."""
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=TABELLNAVN,
        record_id=instance.pk or 0,
        action='DELETE',
        field_name='',
        old_value=str(instance),
        new_value='',
        user=bruker,
        ip=ip,
    )
