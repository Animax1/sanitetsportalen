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


class ModuleBackupConfig(models.Model):
    """Per-modul backup-konfigurasjon.

    Erstatter den gamle singleton-modellen ``patients.BackupConfig``.
    Hver registrerte modul kan ha sin egen backup-konfigurasjon med
    eget intervall, max-antall og av/på-bryter. Configs uten matchende
    backup-handler ignoreres av scheduleren.

    Data-migrering: ved oppgradering kopieres den eksisterende
    ``patients.BackupConfig.interval_minutes``-verdien til en ny rad
    med ``module_slug='patients'``.
    """
    INTERVAL_CHOICES = [
        (0,    'Av'),
        (5,    'Hvert 5. minutt'),
        (15,   'Hvert 15. minutt'),
        (30,   'Hvert 30. minutt'),
        (60,   'Hver time'),
        (360,  'Hver 6. time'),
        (1440, 'Hver 24. time'),
    ]

    module_slug = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Modul-slug',
        help_text='Matcher slug på en registrert backup-handler.',
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name='Backup aktivert',
        help_text='Hvis avkrysset kjøres automatisk backup på intervallet under.',
    )
    interval_minutes = models.IntegerField(
        choices=INTERVAL_CHOICES,
        default=60,
        verbose_name='Backup-intervall',
        help_text='Hvor ofte automatisk backup skal kjøres.',
    )
    max_backups = models.IntegerField(
        default=50,
        verbose_name='Maks antall backuper',
        help_text=(
            'Eldste backuper slettes automatisk slik at totalt antall ikke '
            'overstiger denne verdien. Pre-restore-snapshots telles ikke.'
        ),
    )
    last_run_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Sist kjørt',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Modul-backup-konfigurasjon'
        verbose_name_plural = 'Modul-backup-konfigurasjoner'
        ordering = ['module_slug']

    def __str__(self) -> str:
        return f'{self.module_slug} ({"av" if not self.enabled else self.get_interval_minutes_display()})'

    @classmethod
    def get_or_default(cls, slug: str):
        """Hent config for slug, eller opprett med defaults.

        Brukt av admin-UI og scheduler. Idempotent.
        """
        obj, _ = cls.objects.get_or_create(module_slug=slug)
        return obj


class Notification(models.Model):
    """Generisk varsel som vises i bjella i topp-nav.

    Fase 5: Første bruksområde er pasient-tildeling (modul ``patients``),
    men modellen er designet generisk slik at framtidige moduler (vakter,
    utstyr, beredskap) kan opprette varsler uten endring i denne fila.

    Bruks-API: ``core.notifications.notify(user, module_slug, kind, ...)``.

    Felt-beskrivelse:
        user         — mottaker (FK til CustomUser)
        module_slug  — hvilken modul som lagde varselet ('patients', 'vakter', ...)
        kind         — fri streng som identifiserer varseltypen for filter
                       og dedup ('patient_assigned', 'patient_transferred_away',
                       'shift_assigned', osv.)
        level        — alvorlighetsgrad. ``info`` (default) er grønn,
                       ``warning`` gul, ``critical`` rød. Brukes som hook
                       for fremtidige UI-features (badge-farge, lyd, push).
                       Per Fase 5 vises alle varsler likt i bjella.
        title        — kort overskrift (vises fett i liste)
        message      — detaljtekst (under tittel)
        url          — hvor brukeren skal sendes ved klikk (relativ URL)
        is_read      — om mottakeren har åpnet eller markert som lest
        created_at   — når varselet ble opprettet
    """

    LEVEL_INFO = 'info'
    LEVEL_WARNING = 'warning'
    LEVEL_CRITICAL = 'critical'
    LEVEL_CHOICES = [
        (LEVEL_INFO, 'Info'),
        (LEVEL_WARNING, 'Advarsel'),
        (LEVEL_CRITICAL, 'Kritisk'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Mottaker',
    )
    module_slug = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name='Modul',
        help_text='Slug for modulen som lagde varselet.',
    )
    kind = models.CharField(
        max_length=64,
        verbose_name='Varseltype',
        help_text='Maskinell identifikator for varseltypen (brukes til filter og dedup).',
    )
    level = models.CharField(
        max_length=16,
        choices=LEVEL_CHOICES,
        default=LEVEL_INFO,
        verbose_name='Nivå',
        help_text=(
            'Alvorlighetsgrad. Reservert for fremtidige UI-features '
            '(badge-farge, lyd, push). Per Fase 5 vises alle likt.'
        ),
    )
    title = models.CharField(
        max_length=200,
        verbose_name='Tittel',
    )
    message = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Melding',
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Lenke',
        help_text='Relativ URL som brukeren sendes til ved klikk.',
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Lest',
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Lest tidspunkt',
        help_text='Settes til timezone.now() når brukeren markerer varselet som lest.',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Opprettet',
    )

    class Meta:
        verbose_name = 'Varsel'
        verbose_name_plural = 'Varsler'
        ordering = ['-created_at']
        indexes = [
            # Bjelle-count: hent ulest pr. bruker, ferskeste først
            models.Index(
                fields=['user', 'is_read', '-created_at'],
                name='core_notif_user_read_idx',
            ),
            # Filter pr. modul: framtidig moduldropdown i varselliste
            models.Index(
                fields=['user', 'module_slug', '-created_at'],
                name='core_notif_user_module_idx',
            ),
        ]

    def __str__(self) -> str:
        status = 'lest' if self.is_read else 'ulest'
        return f'[{self.module_slug}] {self.title} ({status})'
