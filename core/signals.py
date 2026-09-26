"""Audit-logging for portalens egne tabeller: `AppSetting`, `ModuleSettings`, `Vakt`.

**Hullet dette lukker** (14. sep. 2026, meldt av André ved staging-verifisering:
«logges ingenting fra core?»). Svaret var nesten nei, og det var ikke nytt av
flyttingen — det hadde stått slik hele tiden. Portalen logget hvert feltbytte
på en pasient minutiøst, mens «noen slo av pasientmodulen for alle» og «noen
flyttet sesjonstimeouten fra 8 til 720 timer» ikke etterlot noe. Det er feil
vei rundt: jo mer irreversibel handlingen er, jo mindre spor satte den.

Samme mønster som `vaktliste/signals.py` og `oppdrag/signals.py` — og de to
vaktene derfra gjelder her også:

- **`@ikke_under_loaddata`** på alt som lagrer. Django sender `raw=True` når
  `loaddata` skriver en rad, og portalfila er den *første* som lastes i en
  gjenoppretting. Uten vakten ville hver eneste gjenoppretting skrevet en
  auditrad per lastet innstilling, med gjenopprettingen selv som eneste
  forklaring.
- **Ingen `bulk_create`** på disse modellene — den hopper over signalene.

── Hvorfor `AppSetting` trenger en unntaksliste ──────────────────────────────

Tabellen er nøkkel/verdi, og den blander to helt ulike ting: innstillinger et
*menneske* har bestemt, og tellere *maskinen* har talt. Et signal som logger
alt ville logget begge.

Telleren er den som gjør det uholdbart, ikke cron-linjene:
`patients.services.next_patient_nr()` teller opp raden ved **hver
pasientregistrering**, og `oppdrag.services` gjør det samme per oppdrag. Uten
unntaket får du én ekstra auditrad per pasient — `next_patient_nr_vakt_7:
41 → 42` — blandet inn mellom de ekte pasientradene på nøyaktig de vaktene der
loggen betyr mest.

Regelen er derfor: **logg det et menneske har bestemt, ikke det maskinen har
talt.** Og den står som én navngitt liste, ikke som spredte `if`-er, slik at
det finnes ett sted å se etter.

**Lista er en unntaksliste, ikke en inkluderingsliste.** En ny nøkkel noen
legger til om et år blir logget som standard. Det er riktig vei å feile: en
teller for mye i loggen er støy, en innstilling for lite er et hull — og hullet
oppdages først den dagen noen spør hvem som endret noe.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from audit.models import AuditLog
from audit.utils import get_current_request, ikke_under_loaddata
from core.klientip import klient_ip

from .models import AppSetting, ModuleSettings, Vakt

logger = logging.getLogger(__name__)

APPSETTING_TABELL = 'patients_appsetting'      # db_table, se core/models.py
MODULESETTINGS_TABELL = 'core_modulesettings'
VAKT_TABELL = 'core_vakt'

#: Nøkkelprefikser som **ikke** gir en auditrad. Maskinskriving uten et
#: menneske bak — se modulens docstring for hvorfor telleren er det
#: avgjørende tilfellet og ikke cron-linjene.
#:
#: Prefiks og ikke eksakte navn, fordi begge tellerne bærer vakt-ID i
#: nøkkelen (`next_patient_nr_vakt_7`) — en eksakt liste ville sluppet
#: gjennom hver nye vakt.
NOKLER_UTEN_AUDIT = (
    'next_patient_nr_vakt_',    # teller, én skriving per pasient
    'next_oppdrag_nr_vakt_',    # teller, én skriving per oppdrag
    'next_hendelse_nr_vakt_',   # teller, én skriving per KO-hendelse
    'cron.',                    # jobbstatus; vises bedre på server-status
)


def nokkel_logges(key: str) -> bool:
    """Skal denne `AppSetting`-nøkkelen gi auditrader?

    Egen funksjon og ikke en `if` inne i mottakeren, av samme grunn som
    `klikkSkalKjore()` i frontend: en regel som ikke lar seg kalle, lar seg
    ikke prøve — og denne regelen er den eneste tingen som skiller en
    brukbar logg fra en full av tellerstøy.
    """
    return not any(key.startswith(p) for p in NOKLER_UTEN_AUDIT)


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


def _verdi(verdi):
    """Kun ``None`` blir tom streng.

    Å kollapse alle falsy verdier ville gjort ``False`` til ``''`` — den
    feilen kostet pasientmodulen at deaktiveringer aldri ble logget riktig.
    """
    return '' if verdi is None else str(verdi)


# ── AppSetting ───────────────────────────────────────────────────────────────
#
# `key` er tekst-primærnøkkel, mens `AuditLog.record_id` er `BigIntegerField`.
# Nøkkelen går derfor i `field_name` (`max_length=64`, nøyaktig som `key`) og
# `record_id` står 0. Det er også den *lesbare* formen: raden sier «hvilken
# innstilling», ikke «rad nummer hva».


@receiver(pre_save, sender=AppSetting)
@ikke_under_loaddata
def appsetting_pre_save(sender, instance, **kwargs):
    """Logg endring av en eksisterende innstilling.

    `AppSetting.set()` bruker `update_or_create`, så en endring kommer hit med
    `pk` satt *og* raden på plass i basen. En ny nøkkel har også `pk` satt
    (den er nøkkelen selv) — derfor spørres basen, ikke `instance.pk`, om
    dette er en opprettelse.
    """
    if not nokkel_logges(instance.key):
        return
    gammel = AppSetting.objects.filter(pk=instance.pk).first()
    if gammel is None:
        return                                  # opprettelse, tas i post_save
    if _verdi(gammel.value) == _verdi(instance.value):
        return
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=APPSETTING_TABELL,
        record_id=0,
        action='UPDATE',
        field_name=instance.key,
        old_value=_verdi(gammel.value),
        new_value=_verdi(instance.value),
        user=bruker,
        ip=ip,
    )


@receiver(post_save, sender=AppSetting)
@ikke_under_loaddata
def appsetting_post_save(sender, instance, created, **kwargs):
    if not created or not nokkel_logges(instance.key):
        return
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=APPSETTING_TABELL,
        record_id=0,
        action='CREATE',
        field_name=instance.key,
        old_value='',
        new_value=_verdi(instance.value),
        user=bruker,
        ip=ip,
    )


@receiver(post_delete, sender=AppSetting)
def appsetting_post_delete(sender, instance, **kwargs):
    """En slettet innstilling faller tilbake på koden sin standardverdi —
    altså en stille oppførselsendring. Verdt et spor."""
    if not nokkel_logges(instance.key):
        return
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=APPSETTING_TABELL,
        record_id=0,
        action='DELETE',
        field_name=instance.key,
        old_value=_verdi(instance.value),
        new_value='',
        user=bruker,
        ip=ip,
    )


# ── ModuleSettings ───────────────────────────────────────────────────────────
#
# Å slå av en modul tar den fra *alle* brukere på én gang, uten deploy og uten
# varsel. Det er blant de mest inngripende knappene i portalen, og den satte
# ingen spor.

MODULESETTINGS_FELTER = ('slug', 'enabled')


@receiver(pre_save, sender=ModuleSettings)
@ikke_under_loaddata
def modulesettings_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    gammel = ModuleSettings.objects.filter(pk=instance.pk).first()
    if gammel is None:
        return
    bruker, ip = _bruker_og_ip()
    for felt in MODULESETTINGS_FELTER:
        gammel_verdi = _verdi(getattr(gammel, felt, None))
        ny_verdi = _verdi(getattr(instance, felt, None))
        if gammel_verdi == ny_verdi:
            continue
        AuditLog.objects.create(
            table_name=MODULESETTINGS_TABELL,
            record_id=instance.pk,
            action='UPDATE',
            field_name=felt,
            old_value=gammel_verdi,
            new_value=ny_verdi,
            user=bruker,
            ip=ip,
        )


# ── Vakt ─────────────────────────────────────────────────────────────────────
#
# Vakta er scopet alt annet henger på. `avsluttet` stenger registreringen,
# `er_aktiv` og `navn` avgjør hvor nye rader havner. Ingen personopplysninger
# i modellen, så feltene logges med verdi.
#
# `ModuleSettings.ensure_defaults_exist()` kjører i `post_migrate` og
# oppretter rader — det skjer uten en innlogget bruker og gir rader med
# `user=None`. Det er riktig: de *ble* opprettet, og «av systemet» er et
# sannere svar enn ingen rad.

VAKT_FELTER = ('navn', 'er_aktiv', 'startet', 'avsluttet')


@receiver(pre_save, sender=Vakt)
@ikke_under_loaddata
def vakt_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    gammel = Vakt.objects.filter(pk=instance.pk).first()
    if gammel is None:
        return
    bruker, ip = _bruker_og_ip()
    for felt in VAKT_FELTER:
        gammel_verdi = _verdi(getattr(gammel, felt, None))
        ny_verdi = _verdi(getattr(instance, felt, None))
        if gammel_verdi == ny_verdi:
            continue
        AuditLog.objects.create(
            table_name=VAKT_TABELL,
            record_id=instance.pk,
            action='UPDATE',
            field_name=felt,
            old_value=gammel_verdi,
            new_value=ny_verdi,
            user=bruker,
            ip=ip,
        )


@receiver(post_save, sender=Vakt)
@ikke_under_loaddata
def vakt_post_save(sender, instance, created, **kwargs):
    if not created:
        return
    bruker, ip = _bruker_og_ip()
    AuditLog.objects.create(
        table_name=VAKT_TABELL,
        record_id=instance.pk,
        action='CREATE',
        field_name='',
        old_value='',
        new_value=str(instance),
        user=bruker,
        ip=ip,
    )
