"""`VaktRolle` → `Ressursrolle`.

Navnet var misvisende: rollen gjelder ikke vakta, den gjelder plassen på
bilen eller laget. Samme person er sjåfør på mannskapsbilen lørdag og
lagleder på samleplassen søndag — og det er nettopp derfor rollen sitter på
`Vaktpost` og ikke på `Mannskap`.

`RenameModel` framfor slett-og-opprett: FK-en fra `Vaktpost.rolle` følger med,
og radene består. Modulen har aldri vært i prod, men migrasjonen skal uansett
være riktig for den som kjører den lokalt med data.
"""
from django.db import migrations
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ('vaktliste', '0005_ledige_plasser_og_vaktlengde'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='VaktRolle',
            new_name='Ressursrolle',
        ),
        migrations.AlterModelOptions(
            name='ressursrolle',
            options={
                'ordering': [Lower('navn')],
                'verbose_name': 'Ressursrolle',
                'verbose_name_plural': 'Ressursroller',
            },
        ),
    ]
