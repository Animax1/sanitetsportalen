"""Lokasjonene per portal, del 1: skjemaet (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.12).

Branns «Hovedpost» og Landsskytters er ikke samme sted. Navnet blir unikt per portal.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_tilhorighet"),
        ("oppdrag", "0035_enhet_posisjonsdeling"),
    ]

    operations = [
        migrations.AddField(
            model_name="lokasjon",
            name="portal",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.vaktportal",
                verbose_name="Portal",
            ),
        ),
        migrations.AlterField(
            model_name="lokasjon",
            name="navn",
            field=models.CharField(max_length=120, verbose_name="Lokasjon"),
        ),
        migrations.AddConstraint(
            model_name="lokasjon",
            constraint=models.UniqueConstraint(
                fields=("portal", "navn"), name="lokasjon_unik_i_portal"
            ),
        ),
    ]
