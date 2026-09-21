"""Statistikk pulje 7b (21. sep. 2026). Bare skjema.

`Enhetshendelse.varslet_at`: hendelsen bærer hvor lenge enheten hadde vært
på oppdraget — koblingsraden slettes ved «tatt av», og tallet gikk med den.

`ArkivertOppdrag`: `varslet_at`, `grovsortering`, `avreist_til` og
`enhetshendelser`, så en arkivert vakt viser de samme nye tallene som den
viste live. Alle i SHA-payloaden bare når satt; eldre arkiv verifiserer
uendret.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("oppdrag", "0029_sted_tekst"),
    ]

    operations = [
        migrations.AddField(
            model_name="enhetshendelse",
            name="varslet_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Varslet på oppdraget"
            ),
        ),
        migrations.AddField(
            model_name="arkivertoppdrag",
            name="varslet_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Når enheten ble varslet på oppdraget. Bærer reaksjonstida.",
                null=True,
                verbose_name="Varslet",
            ),
        ),
        migrations.AddField(
            model_name="arkivertoppdrag",
            name="grovsortering",
            field=models.CharField(
                blank=True, default="", max_length=16, verbose_name="Grovsortering"
            ),
        ),
        migrations.AddField(
            model_name="arkivertoppdrag",
            name="avreist_til",
            field=models.CharField(
                blank=True, default="", max_length=20, verbose_name="Avreist til"
            ),
        ),
        migrations.AddField(
            model_name="arkivertoppdrag",
            name="enhetshendelser",
            field=models.JSONField(
                blank=True, default=list, verbose_name="Enhetshendelser"
            ),
        ),
    ]
