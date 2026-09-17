"""Koble hvert innspill til sin type. Dataskritt uten `ALTER` etterpå.

Feltet legges til som **nullbart**, fylles, og gjøres obligatorisk i `0004`.
Tre grunner til akkurat den formen:

1. `ALTER TABLE` etter en skriving i samme transaksjon avvises av PostgreSQL
   med «pending trigger events» (`CLAUDE.md`, Migrasjoner).
2. Et `NOT NULL`-felt lagt til på en tabell med rader trenger en default
   uansett, og en default på en FK er et vilkårlig valg vi ikke vil ha.
3. En rad med ukjent type skal ikke få en tilfeldig type tredd på seg —
   `_fyll` lager typen den fant i stedet, så ingenting går tapt.
"""
from django.db import migrations, models
import django.db.models.deletion


def fyll(apps, schema_editor):
    Innspill = apps.get_model('backlog', 'Innspill')
    Innspilltype = apps.get_model('backlog', 'Innspilltype')
    #: Kodeverdiene den gamle `TextChoices` brukte, til navnene tabellen har.
    GAMLE = {'bug': 'Bug', 'onske': 'Ønske'}
    for innspill in Innspill.objects.all():
        navn = GAMLE.get(innspill.type, innspill.type or 'Bug')
        # `get_or_create` og ikke `get`: står det en ukjent kodeverdi i basen,
        # skal raden beholde meningen sin framfor å tvinges inn i «Bug».
        type_, _ = Innspilltype.objects.get_or_create(navn=navn)
        innspill.type_ref = type_
        innspill.save(update_fields=['type_ref'])


def tom(apps, schema_editor):
    """Tilbakerullingen trenger ikke gjøre noe: `0004` har ikke kjørt, så den
    gamle kolonnen står der fortsatt med verdiene sine."""


class Migration(migrations.Migration):

    dependencies = [('backlog', '0002_innspilltype')]

    operations = [
        migrations.AddField(
            model_name='innspill',
            name='type_ref',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='innspill',
                to='backlog.innspilltype',
                verbose_name='Type'),
        ),
        migrations.RunPython(fyll, tom),
    ]
