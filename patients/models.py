"""Modeller for pasientregistrering."""
from datetime import datetime

from django.conf import settings
from django.db import models, transaction


class AppSetting(models.Model):
    """Applikasjonsinnstillinger (nøkkel-verdi-par)."""

    key = models.CharField(max_length=64, primary_key=True, verbose_name='Nøkkel')
    value = models.TextField(verbose_name='Verdi')

    class Meta:
        verbose_name = 'Appinnstilling'
        verbose_name_plural = 'Appinnstillinger'

    def __str__(self):
        return f'{self.key} = {self.value}'

    @classmethod
    def get(cls, key, default=None):
        """Hent verdi for nøkkel, eller standard-verdi."""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key, value):
        """Sett verdi for nøkkel (opprett eller oppdater)."""
        obj, _ = cls.objects.update_or_create(
            key=key,
            defaults={'value': str(value)},
        )
        return obj


class Behandler(models.Model):
    """Behandler som kan knyttes til pasienter.

    Inaktive behandlere vises ikke i dropdown, men beholdes som FK
    på historiske pasienter for å bevare referanseintegriteten.
    """

    name = models.CharField(max_length=120, unique=True, verbose_name='Navn')
    is_active = models.BooleanField(default=True, verbose_name='Aktiv')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')

    class Meta:
        verbose_name = 'Behandler'
        verbose_name_plural = 'Behandlere'
        ordering = ['-is_active', 'name']

    def __str__(self):
        suffix = '' if self.is_active else ' (inaktiv)'
        return f'{self.name}{suffix}'


class Helsepersonell(models.Model):
    """Helsepersonell som kan knyttes til pasienter.

    Samme mønster som Behandler – inaktive vises ikke i dropdown, men
    beholdes som FK på historiske pasienter for referanseintegritet.
    """

    name = models.CharField(max_length=120, unique=True, verbose_name='Navn')
    is_active = models.BooleanField(default=True, verbose_name='Aktiv')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')

    class Meta:
        verbose_name = 'Helsepersonell'
        verbose_name_plural = 'Helsepersonell'
        ordering = ['-is_active', 'name']

    def __str__(self):
        suffix = '' if self.is_active else ' (inaktiv)'
        return f'{self.name}{suffix}'


class Patient(models.Model):
    """Pasientmodell med alle kliniske feltnavn fra Flask-appen."""

    # Pasientnummer (separat fra intern PK)
    pasientnummer = models.IntegerField(unique=True, verbose_name='Pasientnummer')

    # År pasienten tilhører (indeksert for filtrering)
    year = models.IntegerField(db_index=True, verbose_name='År')

    # Kliniske felt (alle som tekst, matcher Flask-appen nøyaktig)
    problemstilling = models.CharField(max_length=255, default='', blank=True, verbose_name='Problemstilling')
    arsak = models.CharField(max_length=255, default='', blank=True, verbose_name='Årsak')
    transport = models.CharField(max_length=255, default='', blank=True, verbose_name='Transport')
    inntid = models.TextField(default='', blank=True, verbose_name='Inntid')
    grovsortering = models.CharField(max_length=50, default='', blank=True, verbose_name='Grovsortering')
    pabegynt = models.TextField(default='', blank=True, verbose_name='Påbegynt')
    plassering = models.CharField(max_length=255, default='', blank=True, verbose_name='Plassering')
    behandler = models.ForeignKey(
        Behandler,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='patients',
        verbose_name='Behandler',
    )
    # Gammelt tekstfelt – beholdes for historiske pasienter, brukes ikke ved nye registreringer
    helsepersonell = models.CharField(max_length=50, default='', blank=True, verbose_name='Helsepersonell (tekst, utgående)')
    helsepersonell_ref = models.ForeignKey(
        Helsepersonell,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='patients',
        verbose_name='Helsepersonell',
    )
    lege = models.CharField(max_length=50, default='', blank=True, verbose_name='Lege')
    medisiner = models.CharField(max_length=50, default='', blank=True, verbose_name='Medisiner')
    inn_obspost = models.TextField(default='', blank=True, verbose_name='Inn obspost')
    ut_obspost = models.TextField(default='', blank=True, verbose_name='UT obspost')
    utskrevet = models.TextField(default='', blank=True, verbose_name='Utskrevet')
    utskrevet_til = models.CharField(max_length=255, default='', blank=True, verbose_name='Utskrevet til')
    journal = models.CharField(max_length=50, default='', blank=True, verbose_name='Journal')

    # Systemfelter
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Oppdatert')
    is_active = models.BooleanField(default=True, verbose_name='Aktiv')

    class Meta:
        verbose_name = 'Pasient'
        verbose_name_plural = 'Pasienter'
        ordering = ['pasientnummer']

    def __str__(self):
        return f'Pasient #{self.pasientnummer} – {self.problemstilling or "ukjent"}'

    def save(self, *args, **kwargs):
        """Sett year automatisk til inneværende år hvis det ikke er satt."""
        if self.year is None:
            self.year = datetime.now().year
        super().save(*args, **kwargs)


class VaktArkiv(models.Model):
    """Låst arkiv-snapshot av en vakt. Read-only kun for admin (standard)."""

    tittel = models.CharField(max_length=255, verbose_name='Tittel')
    arrangement_navn = models.CharField(max_length=255, verbose_name='Arrangementsnavn')
    importert_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Importert')
    importert_av = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='vaktarkiver',
        verbose_name='Importert av',
    )
    antall_pasienter = models.IntegerField(verbose_name='Antall pasienter')
    year_snapshot = models.IntegerField(verbose_name='År (snapshot)')
    notat = models.TextField(blank=True, verbose_name='Notat')
    sha256 = models.CharField(max_length=64, blank=True, verbose_name='SHA-256')

    class Meta:
        verbose_name = 'Vaktarkiv'
        verbose_name_plural = 'Vaktarkiver'
        ordering = ['-importert_at']

    def __str__(self):
        return self.tittel


class ArkivertPasient(models.Model):
    """Statistikk-relevante felt fra en arkivert pasient. Read-only via design."""

    arkiv = models.ForeignKey(
        VaktArkiv,
        on_delete=models.CASCADE,
        related_name='pasienter',
        verbose_name='Arkiv',
    )
    pasientnummer = models.IntegerField(verbose_name='Pasientnummer')
    problemstilling = models.CharField(max_length=255, blank=True, default='', verbose_name='Problemstilling')
    arsak = models.CharField(max_length=255, blank=True, default='', verbose_name='Årsak')
    transport = models.CharField(max_length=255, blank=True, default='', verbose_name='Transport')
    grovsortering = models.CharField(max_length=50, blank=True, default='', verbose_name='Grovsortering')
    plassering = models.CharField(max_length=255, blank=True, default='', verbose_name='Plassering')
    inntid = models.TextField(blank=True, default='', verbose_name='Inntid')
    pabegynt = models.TextField(blank=True, default='', verbose_name='Påbegynt')
    inn_obspost = models.TextField(blank=True, default='', verbose_name='Inn obspost')
    ut_obspost = models.TextField(blank=True, default='', verbose_name='Ut obspost')
    utskrevet = models.TextField(blank=True, default='', verbose_name='Utskrevet')
    utskrevet_til = models.CharField(max_length=255, blank=True, default='', verbose_name='Utskrevet til')
    behandler_navn = models.CharField(max_length=255, blank=True, default='', verbose_name='Behandler (navn)')
    helsepersonell_navn = models.CharField(max_length=255, blank=True, default='', verbose_name='Helsepersonell (navn)')
    lege = models.CharField(max_length=50, blank=True, default='', verbose_name='Lege')
    medisiner = models.CharField(max_length=50, blank=True, default='', verbose_name='Medisiner')
    journal = models.CharField(max_length=50, blank=True, default='', verbose_name='Journal')

    class Meta:
        unique_together = [['arkiv', 'pasientnummer']]
        ordering = ['pasientnummer']
        verbose_name = 'Arkivert pasient'
        verbose_name_plural = 'Arkiverte pasienter'

    def __str__(self):
        return f'Pasient #{self.pasientnummer} (arkiv: {self.arkiv_id})'


class BackupConfig(models.Model):
    """Singleton-modell med backup-innstillinger (én rad)."""
    INTERVAL_CHOICES = [
        (0,    'Av'),
        (30,   'Hver 30. min'),
        (60,   'Hver time'),
        (360,  'Hver 6. time'),
        (1440, 'Hver 24. time'),
    ]
    interval_minutes = models.IntegerField(choices=INTERVAL_CHOICES, default=60)
    last_run_at      = models.DateTimeField(null=True, blank=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Backup-konfigurasjon'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Backup(models.Model):
    """Metadata om en backup-fil. Selve filen ligger på disk/volume."""
    KIND_CHOICES = [
        ('auto',        'Automatisk'),
        ('manual',      'Manuell'),
        ('pre_restore', 'Før gjenoppretting'),
        ('pre_reset',   'Før nullstilling av år'),
    ]
    filename    = models.CharField(max_length=255, unique=True)
    kind        = models.CharField(max_length=20, choices=KIND_CHOICES)
    size_bytes  = models.BigIntegerField()
    created_at  = models.DateTimeField(auto_now_add=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='backups_created',
    )
    note        = models.CharField(max_length=200, blank=True, default='')
    content_hash = models.CharField(
        max_length=64, blank=True, default='',
        help_text='SHA256 over ukomprimert JSON-innhold. '
                  'Brukes til å hoppe over identiske auto-backups.',
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', '-created_at'], name='backup_kind_created_idx'),
        ]

    def __str__(self):
        return f'{self.filename} ({self.get_kind_display()})'
