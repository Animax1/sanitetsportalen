"""Migrasjon: legg til Behandler-modell, year-felt på Patient,
konverter behandler-tekst til FK, og fjern notat-feltet.

Steg:
1. Rename Patient.behandler → Patient.behandler_old (CharField)
2. CreateModel Behandler
3. AddField Patient.behandler (FK, null=True)
4. AddField Patient.year (IntegerField, null=True midlertidig)
5. RunPython: konverter behandler-tekst til FK-referanser
6. RunPython: sett year på alle eksisterende pasienter
7. AlterField Patient.year → null=False, db_index=True
8. RemoveField Patient.behandler_old
9. RemoveField Patient.notat
"""
from datetime import datetime

import django.db.models.deletion
from django.db import migrations, models


# ── Datamigreringer ───────────────────────────────────────────────────────────

def migrate_behandler_strings_to_fk(apps, schema_editor):
    """Konverter eksisterende behandler-tekst til Behandler-FK.

    Plassholderne 'Behandler 1' … 'Behandler 10' fra det hardkodede
    HTML-skjemaet opprettes som INAKTIVE slik at de ikke vises i
    dropdown, men bevarer historikken på gamle pasienter.
    """
    Patient = apps.get_model('patients', 'Patient')
    Behandler = apps.get_model('patients', 'Behandler')

    # Opprett standard-plassholdere som inaktive
    standard_names = [f'Behandler {i}' for i in range(1, 11)]
    for name in standard_names:
        Behandler.objects.get_or_create(name=name, defaults={'is_active': False})

    # For hver unike behandler-streng i Patient: opprett Behandler hvis ikke finnes
    unique_names = (
        Patient.objects
        .exclude(behandler_old='')
        .values_list('behandler_old', flat=True)
        .distinct()
    )
    for name in unique_names:
        name = (name or '').strip()
        if not name:
            continue
        is_active = name not in standard_names
        Behandler.objects.get_or_create(name=name, defaults={'is_active': is_active})

    # Knytt hver Patient til riktig Behandler-rad
    for p in Patient.objects.all():
        old = (p.behandler_old or '').strip()
        if old:
            try:
                p.behandler = Behandler.objects.get(name=old)
                p.save(update_fields=['behandler'])
            except Behandler.DoesNotExist:
                pass


def reverse_behandler_fk(apps, schema_editor):
    """Reverse: kopier FK.name tilbake til behandler_old-tekstkolonnen."""
    Patient = apps.get_model('patients', 'Patient')
    for p in Patient.objects.all():
        if p.behandler_id:
            behandler = apps.get_model('patients', 'Behandler').objects.get(pk=p.behandler_id)
            p.behandler_old = behandler.name
            p.save(update_fields=['behandler_old'])


def backfill_year(apps, schema_editor):
    """Sett year til inneværende år for alle pasienter uten år."""
    Patient = apps.get_model('patients', 'Patient')
    current_year = datetime.now().year
    Patient.objects.filter(year__isnull=True).update(year=current_year)


def reverse_backfill_year(apps, schema_editor):
    """Reverse: ingen handling nødvendig."""
    pass


# ── Migrasjonsoperasjoner ─────────────────────────────────────────────────────

class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        # 1. Gi det gamle CharField-feltet et midlertidig navn
        migrations.RenameField(
            model_name='patient',
            old_name='behandler',
            new_name='behandler_old',
        ),

        # 2. Opprett Behandler-modellen
        migrations.CreateModel(
            name='Behandler',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True, verbose_name='Navn')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')),
            ],
            options={
                'verbose_name': 'Behandler',
                'verbose_name_plural': 'Behandlere',
                'ordering': ['-is_active', 'name'],
            },
        ),

        # 3. Legg til FK-feltet (null=True for å tillate migrering)
        migrations.AddField(
            model_name='patient',
            name='behandler',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='patients',
                to='patients.behandler',
                verbose_name='Behandler',
            ),
        ),

        # 4. Legg til year midlertidig som null=True
        migrations.AddField(
            model_name='patient',
            name='year',
            field=models.IntegerField(null=True, verbose_name='År'),
        ),

        # 5. Konverter behandler-tekst til FK-referanser
        migrations.RunPython(
            migrate_behandler_strings_to_fk,
            reverse_code=reverse_behandler_fk,
        ),

        # 6. Fyll inn year for alle eksisterende pasienter
        migrations.RunPython(
            backfill_year,
            reverse_code=reverse_backfill_year,
        ),

        # 7. Gjør year obligatorisk med db_index
        migrations.AlterField(
            model_name='patient',
            name='year',
            field=models.IntegerField(db_index=True, verbose_name='År'),
        ),

        # 8. Fjern det midlertidige behandler_old-feltet
        migrations.RemoveField(
            model_name='patient',
            name='behandler_old',
        ),

        # 9. Fjern notat-feltet (ingen prod-data ennå)
        migrations.RemoveField(
            model_name='patient',
            name='notat',
        ),
    ]
