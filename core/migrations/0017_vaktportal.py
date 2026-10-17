"""Portalene, del 1 av 3: skjemaet (17. okt. 2026, `docs/BESLUTNING_PORTALER.md`).

`Vaktportal`, og `Vakt.portal` som **nullbar** — backupfiler fra før portalene
har ikke feltet, og ligger 730 dager offsite. `er_aktiv` får standard `False`;
det er en Python-standard og rører ikke databasen.

Delt i tre med vilje: data og skjema i samme migrasjon er nettopp det
`DataOgSkjemaISammeTransaksjonTests` vokter mot (PostgreSQL avviser `ALTER
TABLE` med utsatte triggere i kø). 0018 fyller data, 0019 legger indeksen.

**Gammel kode i release-vinduet** lager vakter uten portal. Indeksen i 0019
gjelder bare rader med portal (NULL-er er ulike i en unik indeks), så den
kan ikke stoppe en gammel `opprett_vakt`.
"""

import core.sortering
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_delt_posisjon_varighet"),
    ]

    operations = [
        migrations.CreateModel(
            name="Vaktportal",
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
                    "navn",
                    models.CharField(max_length=120, unique=True, verbose_name="Navn"),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="Sendes til kartet og står i offline-nøklene. Endres ikke etter at portalen er tatt i bruk.",
                        max_length=64,
                        unique=True,
                        verbose_name="Kortnavn",
                    ),
                ),
                (
                    "er_aktiv",
                    models.BooleanField(
                        default=True,
                        help_text="En deaktivert portal kan ikke velges, men alt i den står.",
                        verbose_name="Aktiv",
                    ),
                ),
                (
                    "opprettet_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Opprettet"),
                ),
            ],
            options={
                "verbose_name": "Portal",
                "verbose_name_plural": "Portaler",
                "ordering": [core.sortering.Norsk("navn")],
            },
        ),
        migrations.AlterField(
            model_name="vakt",
            name="er_aktiv",
            field=models.BooleanField(default=False, verbose_name="Aktiv"),
        ),
        migrations.AddField(
            model_name="vakt",
            name="portal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vakter",
                to="core.vaktportal",
                verbose_name="Portal",
            ),
        ),
    ]
