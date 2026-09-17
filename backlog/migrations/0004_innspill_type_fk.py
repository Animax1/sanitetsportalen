"""Fjern den gamle kolonnen og gi FK-en navnet `type`.

**Ingen skriving her**, bare skjema — og det er hele grunnen til at
migrasjonen er delt fra `0003`. Se `CLAUDE.md`, Migrasjoner: de tre veiene ut
av «data før `ALTER` i samme transaksjon» er å tømme triggerkøen, sette
`atomic = False`, eller dele migrasjonen i to. Dette er den tredje.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [('backlog', '0003_innspill_type_ref')]

    operations = [
        migrations.RemoveField(model_name='innspill', name='type'),
        migrations.RenameField(model_name='innspill', old_name='type_ref',
                               new_name='type'),
        migrations.AlterField(
            model_name='innspill',
            name='type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='innspill',
                to='backlog.innspilltype',
                verbose_name='Type'),
        ),
    ]
