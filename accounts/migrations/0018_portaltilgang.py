"""Portaltilgangene, del 1 av 2: skjemaet (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.2).

`Portaltilgang(bruker, portal, rolle)`, og `ModulTilgang.portaltilgang` — nullbar
i basen bare til 0019 har fylt den. Unikheten flytter fra (bruker, modul) til
(medlemskap, modul): samme konto kan ha ulike nivåer i to portaler.

**Gammel kode i release-vinduet** lager modulrader uten medlemskap; de blir
usynlige for ny kode til de lagres på nytt. Vinduet er minutter, og matrisen
er det eneste som skriver.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_innloggingslogg_passord_ok"),
        ("core", "0019_en_aktiv_vakt_per_portal"),
    ]

    operations = [
        migrations.CreateModel(
            name="Portaltilgang",
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
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Tidspunktet raden ble opprettet.",
                        verbose_name="Opprettet",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Tidspunktet raden sist ble endret.",
                        verbose_name="Sist oppdatert",
                    ),
                ),
                (
                    "rolle",
                    models.CharField(
                        choices=[("moderator", "Moderator"), ("medlem", "Medlem")],
                        default="medlem",
                        max_length=16,
                        verbose_name="Rolle",
                    ),
                ),
            ],
            options={
                "verbose_name": "Portaltilgang",
                "verbose_name_plural": "Portaltilganger",
                "ordering": ["portal_id", "bruker__username"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="modultilgang",
            name="unik_modultilgang_per_bruker",
        ),
        migrations.AddField(
            model_name="portaltilgang",
            name="bruker",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="portaltilganger",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Bruker",
            ),
        ),
        migrations.AddField(
            model_name="portaltilgang",
            name="portal",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="portaltilganger",
                to="core.vaktportal",
                verbose_name="Portal",
            ),
        ),
        migrations.AddField(
            model_name="modultilgang",
            name="portaltilgang",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="modulrader",
                to="accounts.portaltilgang",
                verbose_name="Portaltilgang",
            ),
        ),
        migrations.AddConstraint(
            model_name="modultilgang",
            constraint=models.UniqueConstraint(
                fields=("portaltilgang", "modul_slug"),
                name="unik_modultilgang_per_portaltilgang",
            ),
        ),
        migrations.AddConstraint(
            model_name="portaltilgang",
            constraint=models.UniqueConstraint(
                fields=("bruker", "portal"),
                name="en_portaltilgang_per_bruker_og_portal",
            ),
        ),
    ]
