"""`les_alle` inn i `ModulTilgang.nivaa`.

Rent additivt, som 0015: ingen eksisterende rad endres, og `choices`
håndheves ikke av databasen — migrasjonen finnes fordi Django ellers melder
feltet som uskrevet ved `makemigrations --check`.

Nivået deklareres bare av vaktlistemodulen. **Eksisterende `les`-rader blir
smalere**, ikke videre: `les` betyr «eget korps» fra nå, og den som skal se
alle korps må få `les_alle` i matrisen. Det er den trygge retningen.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_legg_til_skriv_leder"),
    ]

    operations = [
        migrations.AlterField(
            model_name="modultilgang",
            name="nivaa",
            field=models.CharField(
                choices=[
                    ("les", "Lese"),
                    ("les_alle", "Lese: alt"),
                    ("skriv_handling", "Skrive: handling"),
                    ("skriv_full", "Skrive: full"),
                    ("skriv_leder", "Skrive: leder"),
                ],
                max_length=20,
                verbose_name="Nivå",
            ),
        ),
    ]
