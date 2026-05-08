"""Gjør e-post valgfri (nullable) med betinget unique-constraint.

Endringer:
- `email`-kolonnen blir nullable (`NULL` tillatt) i stedet for unique på kolonnen.
- Konverterer eksisterende tomme strenger til NULL.
- Legger til en betinget UniqueConstraint slik at e-post kun må være unik
  når den faktisk er satt. Flere brukere kan ha NULL samtidig.
"""
from django.db import migrations, models


def blank_emails_to_null(apps, schema_editor):
    """Konverter tom streng til NULL før vi fjerner unique=True-indeksen."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(email='').update(email=None)


def noop_reverse(apps, schema_editor):
    """Reverse gjør ingenting – NULL kan trygt stå hvis vi ruller tilbake."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_add_lead_role'),
    ]

    operations = [
        # Steg 1: fjern unique=True fra kolonnen og gjør den nullable.
        migrations.AlterField(
            model_name='customuser',
            name='email',
            field=models.EmailField(
                max_length=120,
                null=True,
                blank=True,
                verbose_name='E-post',
                help_text='Valgfritt. Brukes kun som kontaktinformasjon for admin.',
            ),
        ),
        # Steg 2: normaliser eksisterende tomme strenger til NULL.
        migrations.RunPython(blank_emails_to_null, noop_reverse),
        # Steg 3: legg til betinget unique-constraint.
        migrations.AddConstraint(
            model_name='customuser',
            constraint=models.UniqueConstraint(
                fields=['email'],
                condition=models.Q(email__isnull=False),
                name='unique_email_if_set',
            ),
        ),
    ]
