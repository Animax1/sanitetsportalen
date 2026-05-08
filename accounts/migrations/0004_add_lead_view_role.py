"""Legg til lead_view-rolle i UserRole-choices.

Kun en AlterField for å oppdatere valgmulighetene. Ingen datamigrering.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_email_optional'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Administrator'),
                    ('lead', 'Leder'),
                    ('lead_view', 'Leder (kun lesing)'),
                    ('read_write', 'Les/skriv'),
                    ('read_only', 'Kun lesing'),
                ],
                default='read_only',
                max_length=20,
                verbose_name='Rolle',
            ),
        ),
    ]
