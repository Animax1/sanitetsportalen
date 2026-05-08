"""Fase 4: Legg til ModuleBackupConfig + data-migrering fra patients.BackupConfig."""
from django.db import migrations, models


def migrate_backup_config_forward(apps, schema_editor):
    """Kopier eksisterende patients.BackupConfig (singleton) til ModuleBackupConfig.

    Singletonen i patients har pk=1 og inneholder interval_minutes + last_run_at.
    Vi oppretter en tilsvarende rad med module_slug='patients' i den nye tabellen.
    Idempotent: hvis raden allerede finnes, oppdateres ikke verdiene.
    """
    OldConfig = apps.get_model('patients', 'BackupConfig')
    NewConfig = apps.get_model('core', 'ModuleBackupConfig')

    try:
        old = OldConfig.objects.get(pk=1)
    except OldConfig.DoesNotExist:
        old = None

    defaults = {
        'enabled': True,
        'interval_minutes': old.interval_minutes if old else 60,
        'max_backups': 50,
        'last_run_at': old.last_run_at if old else None,
    }
    NewConfig.objects.get_or_create(module_slug='patients', defaults=defaults)


def migrate_backup_config_backward(apps, schema_editor):
    """Reversering: slett kun raden for 'patients' (de andre er nye)."""
    NewConfig = apps.get_model('core', 'ModuleBackupConfig')
    NewConfig.objects.filter(module_slug='patients').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_modulesettings'),
        # patients.BackupConfig må eksistere for data-migreringen.
        ('patients', '0005_backup_content_hash'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModuleBackupConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('module_slug', models.CharField(
                    help_text='Matcher slug på en registrert backup-handler.',
                    max_length=64, unique=True, verbose_name='Modul-slug')),
                ('enabled', models.BooleanField(
                    default=True,
                    help_text=(
                        'Hvis avkrysset kjøres automatisk backup på '
                        'intervallet under.'
                    ),
                    verbose_name='Backup aktivert')),
                ('interval_minutes', models.IntegerField(
                    choices=[
                        (0, 'Av'),
                        (5, 'Hvert 5. minutt'),
                        (15, 'Hvert 15. minutt'),
                        (30, 'Hvert 30. minutt'),
                        (60, 'Hver time'),
                        (360, 'Hver 6. time'),
                        (1440, 'Hver 24. time'),
                    ],
                    default=60,
                    help_text='Hvor ofte automatisk backup skal kjøres.',
                    verbose_name='Backup-intervall')),
                ('max_backups', models.IntegerField(
                    default=50,
                    help_text=(
                        'Eldste backuper slettes automatisk slik at totalt '
                        'antall ikke overstiger denne verdien. '
                        'Pre-restore-snapshots telles ikke.'
                    ),
                    verbose_name='Maks antall backuper')),
                ('last_run_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='Sist kjørt')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Modul-backup-konfigurasjon',
                'verbose_name_plural': 'Modul-backup-konfigurasjoner',
                'ordering': ['module_slug'],
            },
        ),
        migrations.RunPython(
            migrate_backup_config_forward,
            migrate_backup_config_backward,
        ),
    ]
