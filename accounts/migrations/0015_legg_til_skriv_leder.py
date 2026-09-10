"""`skriv_leder` inn i `ModulTilgang.nivaa`.

Rent additivt: ingen eksisterende rad endres, og `choices` håndheves ikke av
databasen — migrasjonen finnes fordi Django ellers melder feltet som uskrevet
ved hver `makemigrations --check`.

Nivået deklareres bare av vaktlistemodulen (`vaktliste/module.py`). Matrisen
tilbyr det derfor ikke på de andre, og ingen kan få det der.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_fjern_modulflagg"),
    ]

    operations = [
        migrations.AlterField(
            model_name="modultilgang",
            name="nivaa",
            field=models.CharField(
                choices=[
                    ("les", "Lese"),
                    ("skriv_handling", "Skrive: handling"),
                    ("skriv_full", "Skrive: full"),
                    ("skriv_leder", "Skrive: leder"),
                ],
                max_length=20,
                verbose_name="Nivå",
            ),
        ),
    ]
