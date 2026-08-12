"""Opprett backup-konfigurasjon for arkiv-modulen (GDPR-tiltaksplan fase 3.2).

Scheduleren itererer ``ModuleBackupConfig``-rader med ``enabled=True`` og en
registrert handler. Uten en rad for ``arkiv`` ville handleren finnes, men aldri
bli kjørt automatisk.

Intervallet er satt til én gang i døgnet, ikke hver time som for pasientdata:
arkivet endres bare når en vakt arkiveres. Innholds-hashen gjør dessuten at
uendret arkiv ikke gir nye filer, så i praksis lages det én backup per
arkivert vakt.
"""
from django.db import migrations

ARKIV_SLUG = 'arkiv'
INTERVALL_DOGN = 1440
MAKS_BACKUPER = 20


def opprett_arkiv_config(apps, schema_editor):
    ModuleBackupConfig = apps.get_model('core', 'ModuleBackupConfig')
    ModuleBackupConfig.objects.get_or_create(
        module_slug=ARKIV_SLUG,
        defaults={
            'enabled': True,
            'interval_minutes': INTERVALL_DOGN,
            'max_backups': MAKS_BACKUPER,
        },
    )


def fjern_arkiv_config(apps, schema_editor):
    ModuleBackupConfig = apps.get_model('core', 'ModuleBackupConfig')
    ModuleBackupConfig.objects.filter(module_slug=ARKIV_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_notification_read_at'),
    ]

    operations = [
        migrations.RunPython(opprett_arkiv_config, fjern_arkiv_config),
    ]
