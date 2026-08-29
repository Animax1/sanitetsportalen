"""Audit-logging for oppdragsmodulen.

Samme mønster som ``patients/signals.py``, med **én forskjell som er hele
poenget med fase 2 i beslutningsnotatet**: `fritekst` logges som *endret*, men
verdiene skrives ikke.

``AuditLog.old_value`` og ``new_value`` er ``TextField`` med 730 dagers
lagring, og feltlista utledes fra modellen — et nytt fritekstfelt havner der
av seg selv. Skriver en operatør noe sensitivt om en pasient og retter det,
ville begge versjonene ligget i loggen i to år. Sporet av *at* noen endret
feltet er det som trengs for etterprøvbarhet; innholdet er det ikke.

Regelen er bygget inn fra første lagring, ikke ettermontert. Var den kommet
senere, ville feltet vært i produksjon med verdilogging på i mellomtiden — og
de radene kan ikke fjernes uten å røre auditsporet.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from audit.models import AuditLog
from audit.utils import get_current_request

from .models import Oppdrag

TABELLNAVN = 'oppdrag_oppdrag'

logger = logging.getLogger(__name__)

# Felter som ikke gir en auditrad i det hele tatt. Unntaksliste, ikke
# inkluderingsliste — samme vending som i pasientmodulen: glemsomhet skal gi
# for mye logging, ikke for lite.
FELT_UTEN_AUDIT = frozenset({
    'id',
    'created_at',
    'updated_at',   # auto_now — ville gitt en rad ved hver lagring
})

# Felter som gir en auditrad, men **uten verdier**. Raden sier at feltet ble
# endret, av hvem og når; hva som sto der sier den ikke.
FELT_UTEN_VERDILOGGING = frozenset({
    'fritekst',
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
        videresendt = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = (videresendt.split(',')[0].strip() if videresendt
              else request.META.get('REMOTE_ADDR'))
    return bruker, ip


def felt_som_spores():
    """Feltnavnene som skal audit-logges, utledet fra modellen selv.

    Returnerer ``attname``: for en ForeignKey gir det ``enhet_id``, altså
    ID-en som faktisk lagres — og som ikke utløser en ekstra spørring når vi
    leser den av objektet.
    """
    return [
        f.attname
        for f in Oppdrag._meta.concrete_fields
        if f.name not in FELT_UTEN_AUDIT and f.attname not in FELT_UTEN_AUDIT
    ]


def _verdi(obj, felt):
    """Formater en feltverdi for loggen, eller skjul den.

    Kun ``None`` blir tom streng. Å kollapse alle falsy verdier ville gjort
    ``False`` til ``''`` — den feilen kostet pasientmodulen at deaktiveringer
    aldri ble logget riktig.
    """
    if felt in FELT_UTEN_VERDILOGGING:
        return SKJULT
    verdi = getattr(obj, felt, None)
    return '' if verdi is None else str(verdi)


@receiver(pre_save, sender=Oppdrag)
def oppdrag_pre_save(sender, instance, **kwargs):
    """Logg feltendringer for eksisterende oppdrag."""
    if not instance.pk:
        return

    try:
        forrige = Oppdrag.objects.get(pk=instance.pk)
    except Oppdrag.DoesNotExist:
        return

    bruker, ip = _bruker_og_ip()
    rader = []
    for felt in felt_som_spores():
        gammel = _verdi(forrige, felt)
        ny = _verdi(instance, felt)
        # Skjulte felt sammenlignes på råverdien; ellers ville `(skjult)` ==
        # `(skjult)` gjort enhver endring i fritekst usynlig.
        if felt in FELT_UTEN_VERDILOGGING:
            if getattr(forrige, felt, None) == getattr(instance, felt, None):
                continue
        elif gammel == ny:
            continue
        rader.append(AuditLog(
            table_name=TABELLNAVN,
            app_label='oppdrag',   # bulk_create kjører ikke pre_save-signalet
            record_id=instance.pk,
            action='UPDATE',
            field_name=felt,
            old_value=gammel,
            new_value=ny,
            user=bruker,
            ip=ip,
        ))

    if rader:
        AuditLog.objects.bulk_create(rader)


@receiver(post_save, sender=Oppdrag)
def oppdrag_post_save(sender, instance, created, **kwargs):
    if not created:
        return
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=TABELLNAVN,
        record_id=instance.pk,
        action='CREATE',
        user=bruker,
        ip=ip,
    )


@receiver(post_delete, sender=Oppdrag)
def oppdrag_post_delete(sender, instance, **kwargs):
    """Slettede oppdrag logges uten innhold.

    Bare ID-en lagres. Et oppdrag som slettes skal ikke etterlate
    problemstilling og fritekst i en tabell med to års lagring — det ville
    gjort sletting til en måte å bevare data på.
    """
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=TABELLNAVN,
        record_id=instance.pk,
        action='DELETE',
        user=bruker,
        ip=ip,
    )
