"""Deling av logglinjer med enhetene (19. sep. 2026).

`Logglinje.beskrivelse` er borte: beskrivelsen fra «Ny hendelse» er nå bare
den første linja i loggen. I stedet kommer `delt_at`/`delt_av` på linja — delt
med *alle* oppdrag fra hendelsen, nå og senere — og `Linjedeling` for deling
med ett oppdrag. Bare skjema; ingen rader skrives.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ko", "0010_fjern_ressursbehov"),
        ("oppdrag", "0027_oppdrag_hendelse"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="logglinje",
            name="beskrivelse",
        ),
        migrations.AddField(
            model_name="logglinje",
            name="delt_at",
            field=models.DateTimeField(
                blank=True, db_index=True, null=True, verbose_name="Delt"
            ),
        ),
        migrations.AddField(
            model_name="logglinje",
            name="delt_av",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ko_delte_logglinjer",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Delt av",
            ),
        ),
        migrations.AddField(
            model_name="logglinje",
            name="delt_av_navn",
            field=models.CharField(
                blank=True, default="", max_length=150, verbose_name="Delt av (navn)"
            ),
        ),
        migrations.CreateModel(
            name="Linjedeling",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "delt_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Delt"
                    ),
                ),
                (
                    "delt_av_navn",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=150,
                        verbose_name="Delt av (navn)",
                    ),
                ),
                (
                    "delt_av",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ko_linjedelinger",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Delt av",
                    ),
                ),
                (
                    "linje",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delinger",
                        to="ko.logglinje",
                        verbose_name="Linje",
                    ),
                ),
                (
                    "oppdrag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ko_delinger",
                        to="oppdrag.oppdrag",
                        verbose_name="Oppdrag",
                    ),
                ),
            ],
            options={
                "verbose_name": "Linjedeling",
                "verbose_name_plural": "Linjedelinger",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("linje", "oppdrag"), name="en_deling_per_oppdrag"
                    )
                ],
            },
        ),
    ]
