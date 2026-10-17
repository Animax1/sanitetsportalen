"""Mannskapet per portal, del 1: skjemaet (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.5).

`portal` på `Mannskap` og `Kontokorps` (nullbar til 0033 har fylt den).
`user` går fra én-til-én til en vanlig peker med unikhet **per portal**: Kari
kan være mannskap og føre et korps i hver portal (beslutning 24). Navnet er
unikt per (portal, korps, navn) — to portaler kan begge ha «Ola Hansen» i HGSD.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_tilhorighet"),
        ("vaktliste", "0031_tilhorighet_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="mannskap",
            name="unikt_navn_per_korps",
        ),
        migrations.AddField(
            model_name="kontokorps",
            name="portal",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.vaktportal",
                verbose_name="Portal",
            ),
        ),
        migrations.AddField(
            model_name="mannskap",
            name="portal",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.vaktportal",
                verbose_name="Portal",
            ),
        ),
        migrations.AlterField(
            model_name="kontokorps",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="kontokorps",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Konto",
            ),
        ),
        migrations.AlterField(
            model_name="mannskap",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Valgfri kobling til en portalbruker. Fra fase 3 avgjør den hvilket korps kontoen kan redigere. Gir i seg selv ingen tilgang.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mannskap",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Koblet konto",
            ),
        ),
        migrations.AddConstraint(
            model_name="kontokorps",
            constraint=models.UniqueConstraint(
                fields=("portal", "user"), name="ett_kontokorps_per_konto_i_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="mannskap",
            constraint=models.UniqueConstraint(
                fields=("portal", "korps", "navn"), name="unikt_navn_per_korps_i_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="mannskap",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("portal", "user"),
                name="en_mannskapsrad_per_konto_i_portal",
            ),
        ),
    ]
