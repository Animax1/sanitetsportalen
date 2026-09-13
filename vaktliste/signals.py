"""Audit-logging for vaktlistemodulen: `Mannskap`, `Vaktpost`, `Ressurs` og `Vaktliste`.

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

from core.klientip import klient_ip

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from audit.models import AuditLog
from audit.utils import get_current_request, ikke_under_loaddata

from .models import Mannskap, Ressurs, Utsending, Vaktliste, Vaktpost

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
        ip = klient_ip(request)
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
@ikke_under_loaddata
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
@ikke_under_loaddata
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


# ── Vaktlista: drift inn og ut ────────────────────────────────────────────────
#
# «Driftmodus og planleggingsmodus må logges i auditlog» (André, 12. sep.
# 2026). Statusen er den ene døra til innsjekken, og hvem som åpnet og
# stengte den er det man leter etter når stemplene ikke stemmer. Feltnivå,
# som mannskapet — men bare feltene som beskriver formen og spennet, ikke
# navnet på vakta (det bor på `core.Vakt`).

VAKTLISTE_TABELLNAVN = 'vaktliste_vaktliste'
VAKTLISTE_FELTER = ('status', 'satt_i_drift_at', 'satt_i_drift_av', 'planlagt_slutt', 'arkivert_at')


@receiver(pre_save, sender=Vaktliste)
@ikke_under_loaddata
def vaktliste_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        gammel = Vaktliste.objects.get(pk=instance.pk)
    except Vaktliste.DoesNotExist:
        return
    bruker, ip = _bruker_og_ip()
    for felt in VAKTLISTE_FELTER:
        gammel_verdi = _verdi(gammel, felt)
        ny_verdi = _verdi(instance, felt)
        if gammel_verdi == ny_verdi:
            continue
        AuditLog.objects.create(
            table_name=VAKTLISTE_TABELLNAVN,
            record_id=instance.pk,
            action='UPDATE',
            field_name=felt,
            old_value=gammel_verdi,
            new_value=ny_verdi,
            user=bruker,
            ip=ip,
        )


# ── Skift og ressurser ────────────────────────────────────────────────────────
#
# «Ønsker dette for å få logget det meste» (André, 12. sep. 2026): skiftene
# (opprett, endre, slett), ressursene, og først og fremst stemplene — møtt og
# av vakt er det som telles ved brann, og hvem som satte dem og når er det
# man leter etter når tallet ikke stemmer. Samme feltnivå som mannskapet.
#
# `merknad` på skiftet er fritekst, og unntas verdilogging av samme grunn som
# `Mannskap.notat`: «gikk hjem, syk» er en helseopplysning som ikke skal ligge
# i 730 dager. Raden sier at feltet ble endret, ikke hva som sto der.
#
# Sletting av en ressurs CASCADE-r skiftene, og Django sender `post_delete`
# for hver rad som ryker — de blir logget som slettet hver for seg, med den
# som slettet ressursen som bruker.

VAKTPOST_TABELLNAVN = 'vaktliste_vaktpost'
RESSURS_TABELLNAVN = 'vaktliste_ressurs'

VAKTPOST_FELT_UTEN_VERDILOGGING = frozenset({'merknad'})


def _felter_for(modell):
    return [f.name for f in modell._meta.concrete_fields if f.name not in FELT_UTEN_AUDIT]


def _verdi_for(obj, felt, uten_verdi):
    if felt in uten_verdi:
        return SKJULT
    verdi = getattr(obj, felt, None)
    return '' if verdi is None else str(verdi)


def _beskriv_vaktpost(vp) -> str:
    """Hvem, hvor og når — det en CREATE/DELETE-rad må bære for å kunne
    leses uten skiftet, som er borte etter sletting."""
    fra = timezone.localtime(vp.fra_tid).strftime('%d.%m %H:%M') if vp.fra_tid else '?'
    til = timezone.localtime(vp.til_tid).strftime('%d.%m %H:%M') if vp.til_tid else '?'
    return f'{vp} {fra}–{til}'


def _logg_endringer(modell, instance, tabell, uten_verdi=frozenset()):
    if not instance.pk:
        return
    try:
        gammel = modell.objects.get(pk=instance.pk)
    except modell.DoesNotExist:
        return
    bruker, ip = _bruker_og_ip()
    for felt in _felter_for(modell):
        if felt in uten_verdi:
            if getattr(gammel, felt, None) == getattr(instance, felt, None):
                continue
        elif _verdi_for(gammel, felt, uten_verdi) == _verdi_for(instance, felt, uten_verdi):
            continue
        AuditLog.objects.create(
            table_name=tabell, record_id=instance.pk, action='UPDATE', field_name=felt,
            old_value=_verdi_for(gammel, felt, uten_verdi),
            new_value=_verdi_for(instance, felt, uten_verdi),
            user=bruker, ip=ip)


def _logg_opprettet(instance, tabell, beskrivelse):
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=tabell, record_id=instance.pk, action='CREATE', field_name='',
        old_value='', new_value=beskrivelse, user=bruker, ip=ip)


def _logg_slettet(instance, tabell, beskrivelse):
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=tabell, record_id=instance.pk or 0, action='DELETE', field_name='',
        old_value=beskrivelse, new_value='', user=bruker, ip=ip)


@receiver(pre_save, sender=Vaktpost)
@ikke_under_loaddata
def vaktpost_pre_save(sender, instance, **kwargs):
    _logg_endringer(Vaktpost, instance, VAKTPOST_TABELLNAVN, VAKTPOST_FELT_UTEN_VERDILOGGING)


@receiver(post_save, sender=Vaktpost)
@ikke_under_loaddata
def vaktpost_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, VAKTPOST_TABELLNAVN, _beskriv_vaktpost(instance))


@receiver(post_delete, sender=Vaktpost)
def vaktpost_post_delete(sender, instance, **kwargs):
    _logg_slettet(instance, VAKTPOST_TABELLNAVN, _beskriv_vaktpost(instance))


@receiver(pre_save, sender=Ressurs)
@ikke_under_loaddata
def ressurs_pre_save(sender, instance, **kwargs):
    _logg_endringer(Ressurs, instance, RESSURS_TABELLNAVN)


@receiver(post_save, sender=Ressurs)
@ikke_under_loaddata
def ressurs_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, RESSURS_TABELLNAVN, f'{instance} ({instance.gruppe})')


@receiver(post_delete, sender=Ressurs)
def ressurs_post_delete(sender, instance, **kwargs):
    _logg_slettet(instance, RESSURS_TABELLNAVN, f'{instance} ({instance.gruppe})')


# ── Utsendinger av vaktlista som fil ─────────────────────────────────────────
#
# Raden er sporet, men den skal også stå i auditloggen der resten av vaktlista
# står: «hvem sendte fila hvor» er et spørsmål om utlevering av
# personopplysninger, og det svares under audit, ikke i en modultabell.

UTSENDING_TABELLNAVN = 'vaktliste_utsending'


@receiver(post_save, sender=Utsending)
@ikke_under_loaddata
def utsending_post_save(sender, instance, created, **kwargs):
    if created:
        status = 'sendt' if not instance.feil else f'feilet: {instance.feil[:120]}'
        _logg_opprettet(
            instance, UTSENDING_TABELLNAVN,
            f'Vaktlista «{instance.vaktliste.vakt.navn}» {status} — '
            f'{instance.get_utloest_display().lower()}, {instance.antall_rader} skift, '
            f'til: {instance.mottakere or "(ingen)"}')
