from django.db import migrations, models


class Migration(migrations.Migration):
    """«Trenger ny ressurs» (André, 12. sep. 2026): `Oppdrag.trenger_ressurs`
    og `Enhetshendelse.detalj` med typen «rykket videre». Rene skjemaendringer."""

    dependencies = [
        ("oppdrag", "0015_enhetstype_antall"),
    ]

    operations = [
        migrations.AddField(
            model_name="oppdrag",
            name="trenger_ressurs",
            field=models.BooleanField(default=False, verbose_name="Trenger ny ressurs"),
        ),
        migrations.AddField(
            model_name="enhetshendelse",
            name="detalj",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Detalj"),
        ),
        migrations.AlterField(
            model_name="enhetshendelse",
            name="type",
            field=models.CharField(
                choices=[("tatt_av", "Tatt av oppdraget"),
                         ("rykket_videre", "Rykket ut på et annet oppdrag")],
                max_length=16, verbose_name="Hendelse"),
        ),
    ]
