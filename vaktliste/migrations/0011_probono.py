"""`Vaktpost.probono` — skiftet telles ikke i timene (11. sep. 2026).

Ett `AddField` med `False` som standard. Ingen rad endres, ingen data
skrives; intet dataskritt, ingen prøve.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vaktliste", "0010_belastningsgrenser"),
    ]

    operations = [
        migrations.AddField(
            model_name="vaktpost",
            name="probono",
            field=models.BooleanField(default=False, verbose_name="Probono"),
        ),
    ]
