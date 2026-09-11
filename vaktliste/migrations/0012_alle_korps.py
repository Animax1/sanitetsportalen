"""`Vaktpost.alle_korps` — plassen er tildelt alle korps (11. sep. 2026).

Ett `AddField` med `False` som standard: ingen eksisterende plass blir
universal ved oppgraderingen — det ville delt ut det ingen har delt ut.
Intet dataskritt, ingen prøve.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vaktliste", "0011_probono"),
    ]

    operations = [
        migrations.AddField(
            model_name="vaktpost",
            name="alle_korps",
            field=models.BooleanField(default=False, verbose_name="Tildelt alle korps"),
        ),
    ]
