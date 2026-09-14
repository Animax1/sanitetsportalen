"""`AppSetting` og `Backup` flytter til `core` — steg 2 av 2.

Ingen SQL. Modellene fjernes fra pasientappens tilstand; tabellene blir stående
og eies nå av `core` (se `core/0011`).

**Avhengigheten på `core/0011` er det som gjør rekkefølgen til en regel.**
Kjørte denne først, ville tilstanden hatt et øyeblikk uten modell for
tabellene, og `Backup.created_by` ville mistet fremmednøkkelen sin — Django
ville da villet lage den på nytt i en senere migrasjon, altså ekte SQL mot en
kolonne som alt er riktig.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0017_slett_backupconfig'),
        ('core', '0011_appsetting_backup_hit'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='AppSetting'),
                migrations.DeleteModel(name='Backup'),
            ],
        ),
    ]
