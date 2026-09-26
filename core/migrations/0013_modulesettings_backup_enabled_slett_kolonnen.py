"""Kolonnen `core_modulesettings.backup_enabled` slettes (26. sep. 2026, D4 deploy 2).

Steg 2 av to — se `0012`. Django glemte feltet der, og kolonnen fikk en
standardverdi i basen, så koden som kom med `0012` aldri nevner den. Denne
kan derfor bare gå ut etter at `0012` har kjørt i prod: i vinduet mellom
`migrate` og containerbyttet er det *forrige* deploys kode som svarer, og
den må ikke kjenne kolonnen.

Ren skjemaendring, ingen data: ingen `state_operations` (Django kjenner ikke
feltet), og ingen triggerkø å tømme. `reverse_sql` legger kolonnen tilbake med
samme standard som `0012` ga den, så en tilbakerulling til `0012` virker.
Gamle backupfiler bærer feltet; `core.backup.UTGAATTE_FELT` tar det ut.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_modulesettings_backup_enabled_ut_av_modellen'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE core_modulesettings DROP COLUMN backup_enabled',
            reverse_sql=('ALTER TABLE core_modulesettings '
                         'ADD COLUMN backup_enabled boolean NOT NULL DEFAULT false'),
        ),
    ]
