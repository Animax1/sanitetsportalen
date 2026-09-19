"""19. sep. 2026 (André): `Oppdrag.enhet` nullbar — et oppdrag kan opprettes
uten ressurs og står som «Trenger ressurs»; hastegraden «Plassering» etter
Drift; grovsorteringen «Ikke aktuelt» (feltet vidåpnet til 16 tegn). Bare
skjema; ingen rader skrives.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("oppdrag", "0027_oppdrag_hendelse"),
    ]

    operations = [
        migrations.AlterField(
            model_name="oppdrag",
            name="enhet",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="oppdrag",
                to="oppdrag.enhet",
                verbose_name="Enhet",
            ),
        ),
        migrations.AlterField(
            model_name="oppdrag",
            name="grovsortering",
            field=models.CharField(
                blank=True,
                choices=[
                    ("rod", "Rød"),
                    ("gul", "Gul"),
                    ("gronn", "Grønn"),
                    ("ikke_aktuelt", "Ikke aktuelt"),
                ],
                default="",
                max_length=16,
                verbose_name="Grovsortering",
            ),
        ),
        migrations.AlterField(
            model_name="oppdrag",
            name="hastegrad",
            field=models.CharField(
                choices=[
                    ("Akutt", "Akutt"),
                    ("Haster", "Haster"),
                    ("Vanlig", "Vanlig"),
                    ("Drift", "Drift"),
                    ("Plassering", "Plassering"),
                ],
                max_length=16,
                verbose_name="Hastegrad",
            ),
        ),
    ]
