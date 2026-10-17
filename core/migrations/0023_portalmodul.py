"""Modulene i hver portal, og taket (17. okt. 2026, fase 5a). Skjemaet."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_vaktnavn_unikt_per_portal"),
    ]

    operations = [
        migrations.CreateModel(
            name="Portalmodul",
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
                ("modul_slug", models.CharField(max_length=64, verbose_name="Modul")),
                (
                    "tak",
                    models.CharField(
                        help_text="Det høyeste nivået moderator kan dele ut i portalen.",
                        max_length=32,
                        verbose_name="Tak",
                    ),
                ),
                (
                    "portal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="moduler",
                        to="core.vaktportal",
                        verbose_name="Portal",
                    ),
                ),
            ],
            options={
                "verbose_name": "Modul i portalen",
                "verbose_name_plural": "Moduler i portalen",
                "ordering": ["portal", "modul_slug"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("portal", "modul_slug"),
                        name="en_rad_per_modul_i_portalen",
                    )
                ],
            },
        ),
    ]
