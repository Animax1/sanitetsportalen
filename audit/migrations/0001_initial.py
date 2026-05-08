"""Innledende migrasjon for audit-appen."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('table_name', models.CharField(max_length=64, verbose_name='Tabell')),
                ('record_id', models.BigIntegerField(verbose_name='Post-ID')),
                ('action', models.CharField(
                    choices=[('CREATE', 'Opprettet'), ('UPDATE', 'Oppdatert'), ('DELETE', 'Slettet')],
                    max_length=10,
                    verbose_name='Handling',
                )),
                ('field_name', models.CharField(blank=True, max_length=64, null=True, verbose_name='Felt')),
                ('old_value', models.TextField(blank=True, null=True, verbose_name='Gammel verdi')),
                ('new_value', models.TextField(blank=True, null=True, verbose_name='Ny verdi')),
                ('ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP-adresse')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Tidspunkt')),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_logs',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Bruker',
                )),
            ],
            options={
                'verbose_name': 'Revisjonslogg',
                'verbose_name_plural': 'Revisjonslogger',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['table_name', 'record_id'], name='audit_auditlog_table_rec_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['created_at'], name='audit_auditlog_created_idx'),
        ),
    ]
