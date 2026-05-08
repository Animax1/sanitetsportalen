"""Innledende migrasjon for patients-appen."""
from django.db import migrations, models


def seed_app_settings(apps, schema_editor):
    """Legger til startverdier i AppSetting. Idempotent (bruker get_or_create).

    Database-agnostisk — fungerer med både SQLite og Postgres.
    """
    AppSetting = apps.get_model('patients', 'AppSetting')
    defaults = [
        ('next_patient_nr', '1'),
        ('event_name', 'LS26'),
    ]
    for key, value in defaults:
        AppSetting.objects.get_or_create(key=key, defaults={'value': value})


def unseed_app_settings(apps, schema_editor):
    AppSetting = apps.get_model('patients', 'AppSetting')
    AppSetting.objects.filter(key__in=['next_patient_nr', 'event_name']).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AppSetting',
            fields=[
                ('key', models.CharField(max_length=64, primary_key=True, serialize=False, verbose_name='Nøkkel')),
                ('value', models.TextField(verbose_name='Verdi')),
            ],
            options={
                'verbose_name': 'Appinnstilling',
                'verbose_name_plural': 'Appinnstillinger',
            },
        ),
        migrations.CreateModel(
            name='Patient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pasientnummer', models.IntegerField(unique=True, verbose_name='Pasientnummer')),
                ('problemstilling', models.CharField(blank=True, default='', max_length=255, verbose_name='Problemstilling')),
                ('arsak', models.CharField(blank=True, default='', max_length=255, verbose_name='Årsak')),
                ('transport', models.CharField(blank=True, default='', max_length=255, verbose_name='Transport')),
                ('inntid', models.TextField(blank=True, default='', verbose_name='Inntid')),
                ('grovsortering', models.CharField(blank=True, default='', max_length=50, verbose_name='Grovsortering')),
                ('pabegynt', models.TextField(blank=True, default='', verbose_name='Påbegynt')),
                ('plassering', models.CharField(blank=True, default='', max_length=255, verbose_name='Plassering')),
                ('behandler', models.CharField(blank=True, default='', max_length=255, verbose_name='Behandler')),
                ('helsepersonell', models.CharField(blank=True, default='', max_length=50, verbose_name='Helsepersonell')),
                ('lege', models.CharField(blank=True, default='', max_length=50, verbose_name='Lege')),
                ('medisiner', models.CharField(blank=True, default='', max_length=50, verbose_name='Medisiner')),
                ('inn_obspost', models.TextField(blank=True, default='', verbose_name='Inn obspost')),
                ('ut_obspost', models.TextField(blank=True, default='', verbose_name='UT obspost')),
                ('utskrevet', models.TextField(blank=True, default='', verbose_name='Utskrevet')),
                ('utskrevet_til', models.CharField(blank=True, default='', max_length=255, verbose_name='Utskrevet til')),
                ('journal', models.CharField(blank=True, default='', max_length=50, verbose_name='Journal')),
                ('notat', models.TextField(blank=True, default='', verbose_name='Notat')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Oppdatert')),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
            ],
            options={
                'verbose_name': 'Pasient',
                'verbose_name_plural': 'Pasienter',
                'ordering': ['pasientnummer'],
            },
        ),
        # Legg til startverdier (database-agnostisk)
        migrations.RunPython(seed_app_settings, reverse_code=unseed_app_settings),
    ]
