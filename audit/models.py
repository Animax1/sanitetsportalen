"""Revisjonslogg-modell.

Fase 3a tilføyde feltet ``app_label`` slik at audit-loggen kan filtreres per
modul (pasienter, accounts, framtidige moduler) i Django-admin og rapporter.
Feltet fylles automatisk via et ``pre_save``-signal i ``audit.signals`` —
eksisterende kode som kaller ``AuditLog.objects.create(table_name=…)`` trenger
ikke endring.
"""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Logg over alle endringer i pasientdatabasen og andre auditerte tabeller."""

    ACTION_CHOICES = [
        ('CREATE', 'Opprettet'),
        ('UPDATE', 'Oppdatert'),
        ('DELETE', 'Slettet'),
    ]

    app_label = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        verbose_name='App / modul',
        help_text=(
            'Django app-label modulen tilhører (eks. "patients", "accounts"). '
            'Fylles automatisk fra table_name hvis ikke satt eksplisitt.'
        ),
    )
    table_name = models.CharField(max_length=64, verbose_name='Tabell')
    record_id = models.BigIntegerField(verbose_name='Post-ID')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name='Handling')
    field_name = models.CharField(max_length=64, null=True, blank=True, verbose_name='Felt')
    old_value = models.TextField(null=True, blank=True, verbose_name='Gammel verdi')
    new_value = models.TextField(null=True, blank=True, verbose_name='Ny verdi')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        verbose_name='Bruker',
    )
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP-adresse')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Tidspunkt')

    class Meta:
        verbose_name = 'Revisjonslogg'
        verbose_name_plural = 'Revisjonslogger'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['table_name', 'record_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['app_label', 'created_at']),
        ]

    def __str__(self):
        return f'{self.action} {self.table_name}#{self.record_id} @ {self.created_at}'
