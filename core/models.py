"""Felles modeller for sanitetsportalen.

Inneholder:
- ``BaseTimeStampedModel``: abstrakt mixin med created_at/updated_at.
- ``ModuleSettings``: konfigurasjon per modul (enabled-toggle, backup-flagg).
"""
from __future__ import annotations

from django.conf import settings
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


class ModuleSettings(models.Model):
    """Database-styrt konfigurasjon per modul.

    Hver rad tilsvarer én modul i ``core.modules.get_all_modules()``. Admin
    kan toggle ``enabled`` på/av i sanntid uten deploy. Kjernemoduler
    (``Module.is_core=True``) kan ikke deaktiveres — det håndheves i admin
    via ``ModuleSettingsAdmin``.

    Backup-flagget er reservert for fremtidig bruk: ``BackupSchedulerMiddleware``
    leser i dag fra ``BACKUP_APPS`` i ``patients/backup_service.py``. Når Fase 3b
    eller senere fase implementerer modul-styrt backup, vil den lese fra
    ``ModuleSettings.backup_enabled`` i stedet. Frem til da har feltet ingen
    effekt utover dokumentasjon i admin.
    """

    slug = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Modul-slug',
        help_text='Matcher Module.slug i core.modules (ofte lik Django app-label).',
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name='Aktivert',
        help_text=(
            'Hvis avkrysset vises modulen i dashboard og nav-meny for brukere '
            'som har riktig permission-flagg. Kjernemoduler kan ikke deaktiveres.'
        ),
    )
    backup_enabled = models.BooleanField(
        default=False,
        verbose_name='Inkluder i backup',
        help_text=(
            'Reservert for fremtidig modul-styrt backup. Per Fase 3a har dette '
            'feltet ingen effekt — backup styres fortsatt av BACKUP_APPS i kode. '
            'Settes opp i en senere fase.'
        ),
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Admin-notat',
        help_text='Valgfri kommentar — f.eks. årsak til at modulen er deaktivert.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Sist endret',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name='Sist endret av',
    )

    class Meta:
        verbose_name = 'Modulinnstilling'
        verbose_name_plural = 'Modulinnstillinger'
        ordering = ['slug']

    def __str__(self) -> str:
        status = 'aktiv' if self.enabled else 'deaktivert'
        return f'{self.slug} ({status})'

    @classmethod
    def get_enabled_slugs(cls) -> set[str]:
        """Returner sett med slugs for moduler som er ``enabled=True``.

        Moduler som ikke har en rad i tabellen behandles som **deaktivert**.
        ``ensure_defaults_exist()`` sørger for at en rad finnes for hver
        registrert modul, og kalles fra core.apps.CoreConfig.ready().
        """
        return set(cls.objects.filter(enabled=True).values_list('slug', flat=True))

    @classmethod
    def ensure_defaults_exist(cls) -> None:
        """Sørg for at hver registrert modul har en rad i tabellen.

        Idempotent: kjører ``get_or_create`` for hver modul. Kalles fra
        ``CoreConfig.ready()`` etter at app-registret er ferdig lastet.

        Kjernemoduler får ``enabled=True`` per default og kan ikke deaktiveres.
        Andre moduler får ``enabled=True`` ved første registrering — admin må
        eksplisitt skru av.
        """
        # Lazy import: modules.py importerer fra denne fila, så vi kan ikke
        # importere på toppnivå.
        from core.modules import get_all_modules  # noqa: WPS433

        for module in get_all_modules():
            cls.objects.get_or_create(
                slug=module.slug,
                defaults={'enabled': True},
            )
