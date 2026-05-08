"""Felles abstrakte modeller for sanitetsportalen.

Disse modellene er abstrakte (Meta.abstract = True) og lager INGEN tabell
i seg selv. De brukes som mixin/baseklasse av konkrete modeller i andre apps.

Eksisterende modeller i `patients` og `accounts` definerer i dag sine egne
created_at/updated_at-felter. Vi rører ikke dem i fase 1 — denne filen er
ment som fundament for nye apps (vakter, oppdragsregistrering, utstyr osv.).
"""
from django.db import models


class BaseTimeStampedModel(models.Model):
    """Abstrakt baseklasse som gir created_at + updated_at automatisk.

    Bruk:
        class MinModell(BaseTimeStampedModel):
            navn = models.CharField(...)

    Feltene oppdateres automatisk av Django og skal ikke settes manuelt.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Opprettet',
        help_text='Tidspunktet raden ble opprettet.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Sist oppdatert',
        help_text='Tidspunktet raden sist ble endret.',
    )

    class Meta:
        abstract = True
