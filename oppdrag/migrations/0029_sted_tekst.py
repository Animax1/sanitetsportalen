"""«Annet sted» ved Avreist får et fritekstfelt (André, 19. sep. 2026):
`Statusmelding.sted_tekst`. Bare skjema.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("oppdrag", "0028_uten_enhet_plassering_ikke_aktuelt"),
    ]

    operations = [
        migrations.AddField(
            model_name="statusmelding",
            name="sted_tekst",
            field=models.CharField(
                blank=True, default="", max_length=120, verbose_name="Annet sted"
            ),
        ),
    ]
