"""Parklenken bærer portalen, del 1: skjemaet (17. okt. 2026, §4.13).

`/lag/r/` har ingen innlogging, så lenken er det eneste som kan si hvilken
portal en registrering hører til.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_tilhorighet"),
        ("park", "0004_ko_tavlen"),
    ]

    operations = [
        migrations.AddField(
            model_name="parklenke",
            name="portal",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.vaktportal",
                verbose_name="Portal",
            ),
        ),
    ]
