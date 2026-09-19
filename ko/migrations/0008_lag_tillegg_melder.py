"""Lag på hendelsen, beskrivelsen som tillegg, melder som avkryssing
(André, 19. sep. 2026). **Bare skjema** — dataskrittet står i `0009` og
fjerningen av de gamle feltene i `0010`, så ingen migrasjon skriver rader og
endrer skjema i samme transaksjon (CLAUDE.md, «Migrasjoner»)."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ko", "0007_ansvarsomraader"),
        ("vaktliste", "0020_vaktpost_sortering"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="logglinje",
            name="beskrivelse",
            field=models.BooleanField(default=False, verbose_name="Tillegg til beskrivelsen"),
        ),
        migrations.AddField(
            model_name="hendelse",
            name="melder_typer",
            field=models.JSONField(blank=True, default=list, verbose_name="Melder"),
        ),
        migrations.AlterField(
            model_name="hendelse",
            name="melder",
            field=models.CharField(
                blank=True, default="", max_length=120, verbose_name="Melder (andre)"
            ),
        ),
        migrations.CreateModel(
            name="HendelseLag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("ressurs_navn", models.CharField(max_length=120, verbose_name="Ressurs (navn)")),
                ("fra", models.DateTimeField(verbose_name="På hendelsen fra")),
                ("av_navn", models.CharField(blank=True, default="", max_length=150,
                                             verbose_name="Registrert av (navn)")),
                ("av", models.ForeignKey(blank=True, null=True,
                                         on_delete=django.db.models.deletion.SET_NULL,
                                         related_name="ko_lag_registrert",
                                         to=settings.AUTH_USER_MODEL,
                                         verbose_name="Registrert av")),
                ("hendelse", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name="lag", to="ko.hendelse",
                                               verbose_name="Hendelse")),
                ("ressurs", models.ForeignKey(blank=True, null=True,
                                              on_delete=django.db.models.deletion.SET_NULL,
                                              related_name="ko_hendelser",
                                              to="vaktliste.ressurs",
                                              verbose_name="Ressurs")),
            ],
            options={
                "verbose_name": "Lag på hendelse",
                "verbose_name_plural": "Lag på hendelser",
                "ordering": ["fra", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("hendelse", "ressurs"),
                                            name="et_lag_en_gang_per_hendelse"),
                ],
            },
        ),
    ]
