"""Førstehjelperne og helsepersonellet per portal, del 1: skjemaet (17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.12: personnavn er per portal. Navnet blir
unikt per portal, og `user` går fra én-til-én til unik per (portal, konto)
(beslutning 24) — «mine pasienter» følger kontoen i portalen den står i.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_tilhorighet"),
        ("patients", "0019_norsk_sortering"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="forstehjelper",
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
            model_name="helsepersonell",
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
            model_name="forstehjelper",
            name="name",
            field=models.CharField(max_length=120, verbose_name="Navn"),
        ),
        migrations.AlterField(
            model_name="forstehjelper",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Valgfri kobling til en portalbruker. Hvis satt, kan brukeren filtrere egne pasienter og får varsel ved tildeling.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="forstehjelper_profil",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Koblet bruker",
            ),
        ),
        migrations.AlterField(
            model_name="helsepersonell",
            name="name",
            field=models.CharField(max_length=120, verbose_name="Navn"),
        ),
        migrations.AlterField(
            model_name="helsepersonell",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Valgfri kobling til en portalbruker. Hvis satt, kan brukeren filtrere egne pasienter og får varsel ved tildeling.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="helsepersonell_profil",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Koblet bruker",
            ),
        ),
        migrations.AddConstraint(
            model_name="forstehjelper",
            constraint=models.UniqueConstraint(
                fields=("portal", "name"), name="forstehjelper_unik_i_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="forstehjelper",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("portal", "user"),
                name="forstehjelper_en_per_konto_i_portal",
            ),
        ),
        migrations.AddConstraint(
            model_name="helsepersonell",
            constraint=models.UniqueConstraint(
                fields=("portal", "name"), name="helsepersonell_unik_i_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="helsepersonell",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("portal", "user"),
                name="helsepersonell_en_per_konto_i_portal",
            ),
        ),
    ]
