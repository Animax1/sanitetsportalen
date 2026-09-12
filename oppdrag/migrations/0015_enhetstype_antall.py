from django.db import migrations, models


class Migration(migrations.Migration):
    """`Enhet.type` og `Oppdrag.antall` (André, 12. sep. 2026). Rene
    skjemaendringer: eksisterende enheter får «annet», og settes i
    enhetspanelet."""

    dependencies = [
        ("oppdrag", "0014_enhetshendelse"),
    ]

    operations = [
        migrations.AddField(
            model_name="enhet",
            name="type",
            field=models.CharField(
                choices=[("ambulanse", "Ambulanse"), ("mannskapsbil", "Mannskapsbil"),
                         ("lag", "Lag til fots"), ("annet", "Annet")],
                default="annet", max_length=16, verbose_name="Enhetstype"),
        ),
        migrations.AlterField(
            model_name="oppdrag",
            name="hastegrad",
            field=models.CharField(
                choices=[("Akutt", "Akutt"), ("Haster", "Haster"), ("Vanlig", "Vanlig"),
                         ("Teknisk", "Teknisk")],
                max_length=16, verbose_name="Hastegrad"),
        ),
        migrations.AddField(
            model_name="oppdrag",
            name="antall",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Antall"),
        ),
    ]
