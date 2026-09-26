"""Audit-logging for vaktlistemodulen: `Mannskap`, `Vaktpost`, `Ressurs`, `Vaktliste`,
`Pause` og overnattingen.

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

**Registrene og grensene logges også** (26. sep. 2026, B3). Her sto det at
`Korps`, `Kompetanse` og `Ressursrolle` ikke ble logget fordi de «endres fra
Django-admin, som har sin egen historikk». Det har ikke vært sant siden
registrene flyttet inn på `/vaktliste/` (30. aug. 2026), og Django-admin er
ikke rutet i prod. Å slette en `Ressursgruppe` tar rollene med seg, og
`Belastningsgrenser` endrer varslene for alle lister — det er oppsett, men
inngripende oppsett. `tests_audit_registre.HverModellHarSporTests` krever nå
mottakere for hver modell i appen, eller et begrunnet unntak.
"""
from __future__ import annotations

from core.klientip import klient_ip

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from audit.models import AuditLog
from audit.utils import get_current_request, ikke_under_loaddata

from .models import (Belastningsgrenser, Kompetanse, Korps, Mannskap, Overnatting,
                     Overnattingsrom, Pause, Ressurs, Ressursgruppe, Ressursrolle, Utsending,
                     Vaktliste, Vaktpost)

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
# **Alle kolonnene, ikke en liste** (26. sep. 2026, B3). Lista sto skrevet for
# hånd og manglet `timetak` — vaktas budsjett. `brannrutine` (25. sep. 2026) er
# stedets rutine og logges med verdi: «hvem flyttet samleplassen» er et
# spørsmål man stiller. `notat` er fritekst og logges uten verdi, som
# `Mannskap.notat`.
VAKTLISTE_FELT_UTEN_VERDILOGGING = frozenset({'notat'})


def _beskriv_vaktliste(vl) -> str:
    return f'Vaktliste for {vl.vakt.navn}' if vl.vakt_id else f'Vaktliste {vl.pk}'


@receiver(pre_save, sender=Vaktliste)
@ikke_under_loaddata
def vaktliste_pre_save(sender, instance, **kwargs):
    _logg_endringer(Vaktliste, instance, VAKTLISTE_TABELLNAVN, VAKTLISTE_FELT_UTEN_VERDILOGGING)


@receiver(post_save, sender=Vaktliste)
@ikke_under_loaddata
def vaktliste_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, VAKTLISTE_TABELLNAVN, _beskriv_vaktliste(instance))


@receiver(post_delete, sender=Vaktliste)
def vaktliste_post_delete(sender, instance, **kwargs):
    # `vakt` kan være borte når CASCADE går fra vakta — da står bare pk igjen.
    try:
        beskrivelse = _beskriv_vaktliste(instance)
    except Exception:   # noqa: BLE001 — sletteraden skal skrives uansett
        beskrivelse = f'Vaktliste {instance.pk}'
    _logg_slettet(instance, VAKTLISTE_TABELLNAVN, beskrivelse)


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


# ── Pausene (23. sep. 2026) ──────────────────────────────────────────────────
#
# Oppsett som skiftene: hvem la inn, flyttet og fjernet en pause. En regel i
# planleggeren som lager tjue pauser gir tjue rader — det er det som skjedde.

PAUSE_TABELLNAVN = 'vaktliste_pause'


def _beskriv_pause(p) -> str:
    fra = timezone.localtime(p.fra).strftime('%d.%m %H:%M') if p.fra else '?'
    til = timezone.localtime(p.til).strftime('%H:%M') if p.til else '?'
    kilde = ' (regel)' if p.fra_regel else ''
    return f'{p} {fra}–{til}{kilde}'


@receiver(pre_save, sender=Pause)
@ikke_under_loaddata
def pause_pre_save(sender, instance, **kwargs):
    _logg_endringer(Pause, instance, PAUSE_TABELLNAVN)


@receiver(post_save, sender=Pause)
@ikke_under_loaddata
def pause_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, PAUSE_TABELLNAVN, _beskriv_pause(instance))


@receiver(post_delete, sender=Pause)
def pause_post_delete(sender, instance, **kwargs):
    _logg_slettet(instance, PAUSE_TABELLNAVN, _beskriv_pause(instance))


# ── Overnattingen (25. sep. 2026) ────────────────────────────────────────────
#
# Brannlista er det man teller hoder etter, og «hvem flyttet Per ut av 2B»
# er det man leter etter når tallet ikke stemmer — samme grunn som stemplene.
# Rommets `merknad` handler om rommet (nødutgang), ikke om en person, og
# logges med verdi. Sletting av et rom CASCADE-r plasseringene, og hver av dem
# får sin egen rad, som skiftene under en ressurs.

OVERNATTINGSROM_TABELLNAVN = 'vaktliste_overnattingsrom'
OVERNATTING_TABELLNAVN = 'vaktliste_overnatting'


def _beskriv_overnatting(o) -> str:
    return f'{o.mannskap.navn} i {o.rom.navn} natt fra {o.natt:%d.%m.%Y}'


@receiver(pre_save, sender=Overnattingsrom)
@ikke_under_loaddata
def overnattingsrom_pre_save(sender, instance, **kwargs):
    _logg_endringer(Overnattingsrom, instance, OVERNATTINGSROM_TABELLNAVN)


@receiver(post_save, sender=Overnattingsrom)
@ikke_under_loaddata
def overnattingsrom_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, OVERNATTINGSROM_TABELLNAVN, instance.navn)


@receiver(post_delete, sender=Overnattingsrom)
def overnattingsrom_post_delete(sender, instance, **kwargs):
    _logg_slettet(instance, OVERNATTINGSROM_TABELLNAVN, instance.navn)


@receiver(pre_save, sender=Overnatting)
@ikke_under_loaddata
def overnatting_pre_save(sender, instance, **kwargs):
    _logg_endringer(Overnatting, instance, OVERNATTING_TABELLNAVN)


@receiver(post_save, sender=Overnatting)
@ikke_under_loaddata
def overnatting_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, OVERNATTING_TABELLNAVN, _beskriv_overnatting(instance))


@receiver(post_delete, sender=Overnatting)
def overnatting_post_delete(sender, instance, **kwargs):
    # Lagringstiden som løper ut er ikke en handling noen gjorde, og en rad per
    # sletting ville skrevet navn, rom og natt inn i en logg med 730 dagers
    # lagringstid — altså bevart det ryddingen skal fjerne. Se
    # `overnatting.slett_utlopte()`.
    from .overnatting import rydder_naa
    if rydder_naa():
        return
    _logg_slettet(instance, OVERNATTING_TABELLNAVN, _beskriv_overnatting(instance))


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


# ── Registrene og grensene (26. sep. 2026, B3) ───────────────────────────────
#
# Organisasjonsoppsett uten personopplysninger, så verdiene logges. **Stablet og
# eksplisitt**, som tavla i `ko/signals.py`, ikke en løkke med `.connect()`:
# `SignalerFyrerIkkeUnderLoaddataTests` leser `@receiver(...)` med en regex, og
# en løkke ville gått rett forbi den. Tabellnavnet slås opp på `sender`, så en
# modell som legges til står to steder — her og i `REGISTRE` — og
# `HverModellHarSporTests` sier fra om den ene mangler.

REGISTRE = {
    Korps: 'vaktliste_korps',
    Kompetanse: 'vaktliste_kompetanse',
    Ressursgruppe: 'vaktliste_ressursgruppe',
    Ressursrolle: 'vaktliste_ressursrolle',
    Belastningsgrenser: 'vaktliste_belastningsgrenser',
}


@receiver(pre_save, sender=Korps)
@receiver(pre_save, sender=Kompetanse)
@receiver(pre_save, sender=Ressursgruppe)
@receiver(pre_save, sender=Ressursrolle)
@receiver(pre_save, sender=Belastningsgrenser)
@ikke_under_loaddata
def register_pre_save(sender, instance, **kwargs):
    _logg_endringer(sender, instance, REGISTRE[sender])


@receiver(post_save, sender=Korps)
@receiver(post_save, sender=Kompetanse)
@receiver(post_save, sender=Ressursgruppe)
@receiver(post_save, sender=Ressursrolle)
@receiver(post_save, sender=Belastningsgrenser)
@ikke_under_loaddata
def register_post_save(sender, instance, created, **kwargs):
    if created:
        _logg_opprettet(instance, REGISTRE[sender], str(instance))


@receiver(post_delete, sender=Korps)
@receiver(post_delete, sender=Kompetanse)
@receiver(post_delete, sender=Ressursgruppe)
@receiver(post_delete, sender=Ressursrolle)
@receiver(post_delete, sender=Belastningsgrenser)
def register_post_delete(sender, instance, **kwargs):
    _logg_slettet(instance, REGISTRE[sender], str(instance))
