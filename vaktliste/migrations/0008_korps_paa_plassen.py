"""`Vaktpost.korps` — reservasjonen ned på den enkelte plassen.

Rent additivt: en nullbar kolonne, ingen dataskritt, ingen triggerkø å tømme
(se `DataOgSkjemaISammeTransaksjonTests`). Eksisterende plasser får NULL og
arver ressursens reservasjon som før — oppførselen er uendret til noen
faktisk setter et korps på en plass.

Hvorfor: en samleplass bemannes av flere korps. `Ressurs.korps` reserverer
hele ressursen til ett, og da måtte samleplassen deles i én ressurs per korps
— og da er den ikke lenger én samleplass.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vaktliste", "0007_ressursgrupper_og_roller_per_gruppe"),
    ]

    operations = [
        migrations.AddField(
            model_name="vaktpost",
            name="korps",
            field=models.ForeignKey(
                blank=True,
                help_text="Korpset plassen er satt av til. Tom = arver ressursens reservasjon.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reserverte_vaktposter",
                to="vaktliste.korps",
                verbose_name="Reservert korps",
            ),
        ),
    ]
