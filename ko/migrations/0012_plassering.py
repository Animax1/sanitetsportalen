"""Prioriteten «Plassering» etter Drift (André, 19. sep. 2026). Feltet vides
fra 8 til 12 tegn for å romme verdien. Bare skjema.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ko", "0011_deling_av_linjer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="hendelse",
            name="prioritet",
            field=models.CharField(
                choices=[
                    ("viktig", "Viktig"),
                    ("rod", "Rød"),
                    ("gul", "Gul"),
                    ("gronn", "Grønn"),
                    ("drift", "Drift"),
                    ("plassering", "Plassering"),
                ],
                db_index=True,
                default="gronn",
                max_length=12,
                verbose_name="Prioritet",
            ),
        ),
    ]
