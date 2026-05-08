"""Revisjonslogg-modell."""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Logg over alle endringer i pasientdatabasen."""

    ACTION_CHOICES = [
        ('CREATE', 'Opprettet'),
        ('UPDATE', 'Oppdatert'),
        ('DELETE', 'Slettet'),
    ]

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
        ]

    def __str__(self):
        return f'{self.action} {self.table_name}#{self.record_id} @ {self.created_at}'
