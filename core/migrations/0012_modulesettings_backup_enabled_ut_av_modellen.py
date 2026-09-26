"""`ModuleSettings.backup_enabled` ut av modellen, **ikke** ut av basen (26. sep. 2026, D4).

Feltet hadde ingen virkning. Å slette kolonnen i samme deploy ville gitt 500
i vinduet der Railway har kjørt `migrate`, men ennå ikke byttet container:
den gamle koden velger kolonnen i hver spørring mot moduloppsettet, som leses
på hver side. Derfor to steg:

1. **Denne:** Django glemmer feltet (`state_operations`), og kolonnen får en
   standardverdi *i basen* (`db_default`), så den nye koden kan lage rader uten
   å nevne den. Den gamle koden, som fortsatt nevner den, virker som før.
2. **Neste deploy:** kolonnen slettes. Da nevner ingen kode den lenger. Står i
   `TODO.md`.

Gamle backupfiler bærer feltet; `core.backup.UTGAATTE_FELT` tar det ut ved
innlasting.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_appsetting_backup_hit'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterField(
                    model_name='modulesettings',
                    name='backup_enabled',
                    field=models.BooleanField(default=False, db_default=False),
                ),
            ],
            state_operations=[
                migrations.RemoveField(model_name='modulesettings', name='backup_enabled'),
            ],
        ),
    ]
