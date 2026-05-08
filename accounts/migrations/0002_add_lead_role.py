"""Legg til 'lead' (Leder) som gyldig rolle.

Dette er en rent deklarativ endring – databasekolonnen er allerede en CharField,
så vi trenger kun å oppdatere choices slik at Django validerer korrekt og UI
viser den nye rollen.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Administrator'),
                    ('lead', 'Leder'),
                    ('read_write', 'Les/skriv'),
                    ('read_only', 'Kun lesing'),
                ],
                default='read_only',
                max_length=20,
                verbose_name='Rolle',
            ),
        ),
    ]
