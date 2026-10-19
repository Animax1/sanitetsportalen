"""Kontoens signaler: KO-tilgang som forsvinner, logger ut av kartet (19. okt. 2026).

«Åpne kartet» i KO gir en økt i kart.sanitet.net (`docs/PLAN_FELLES_INNLOGGING.md`). Mister
brukeren KO, eller får et lavere nivå, skal den økten ikke leve videre med det gamle. Frysing,
sletting og de andre sikkerhetsoperasjonene går gjennom `accounts.sesjoner.avslutt_alle_sesjoner`;
dette er det som ikke gjør det.

**Signaler, ikke kallsteder.** Radene endres fra matrisen, fra moderatorflaten, når et
medlemskap fjernes (CASCADE) og når kontoen slettes — en liste over kallsteder ville vernet
dem som finnes i dag. **Kartet kjenner bare «kan tegne» (`skriv_full` og opp) eller ikke**, så
bare en endring over den grensa nedover logger ut. Et høyere nivå gjelder fra neste trykk på
knappen; å kaste noen ut av kartet for å gi dem mer ville vært en straff.
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from audit.utils import ikke_under_loaddata

from .models import ModulTilgang

KO = 'ko'


@receiver(pre_save, sender=ModulTilgang)
@ikke_under_loaddata
def husk_forrige_nivaa(sender, instance, **kwargs):
    instance._forrige_nivaa = None
    if instance.pk and instance.modul_slug == KO:
        instance._forrige_nivaa = (
            ModulTilgang.objects.filter(pk=instance.pk).values_list('nivaa', flat=True).first())


@receiver(post_save, sender=ModulTilgang)
@ikke_under_loaddata
def ko_senket(sender, instance, **kwargs):
    from core.auth_decorators import NIVAA_HIERARKI
    from core.kartkobling import logg_ut_i_kartet

    # `husk_forrige_nivaa` setter nivået bare for en eksisterende KO-rad. Ellers er det None, og
    # None er «tegnet ikke» — derfor logger verken en ny rad eller en annen modul ut.
    forrige = getattr(instance, '_forrige_nivaa', None)
    tegnet = NIVAA_HIERARKI.get(forrige, -1) >= NIVAA_HIERARKI['skriv_full']
    tegner = NIVAA_HIERARKI.get(instance.nivaa, -1) >= NIVAA_HIERARKI['skriv_full']
    if tegnet and not tegner:
        logg_ut_i_kartet(instance.bruker_id)


@receiver(post_delete, sender=ModulTilgang)
def ko_fjernet(sender, instance, **kwargs):
    from core.kartkobling import logg_ut_i_kartet

    if instance.modul_slug == KO:
        logg_ut_i_kartet(instance.bruker_id)
