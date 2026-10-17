"""KOs lister og ansvarsmerket per portal, del 1: skjemaet (17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.12: ansvarsområdene, artistene og kjennetegnene er
satt opp per arrangement, og navnet blir unikt per portal. `Ansvarsmerke.bruker`
går fra én-til-én til unik per (portal, konto) (beslutning 24).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_tilhorighet"),
        ("ko", "0024_frosset_statistikk_uten_fritekst"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ansvarsmerke",
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
            model_name="ansvarsomraade",
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
            model_name="kjennetegn",
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
            model_name="konserttype",
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
            model_name="ansvarsmerke",
            name="bruker",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ko_ansvar",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Bruker",
            ),
        ),
        migrations.AlterField(
            model_name="ansvarsomraade",
            name="navn",
            field=models.CharField(max_length=40, verbose_name="Ansvarsområde"),
        ),
        migrations.AlterField(
            model_name="kjennetegn",
            name="navn",
            field=models.CharField(max_length=60, verbose_name="Kjennetegn"),
        ),
        migrations.AlterField(
            model_name="konserttype",
            name="navn",
            field=models.CharField(max_length=60, verbose_name="Artist"),
        ),
        migrations.AddConstraint(
            model_name="ansvarsmerke",
            constraint=models.UniqueConstraint(
                fields=("portal", "bruker"), name="ko_ansvarsmerke_per_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="ansvarsomraade",
            constraint=models.UniqueConstraint(
                fields=("portal", "navn"), name="ko_ansvarsomraade_navn_per_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="kjennetegn",
            constraint=models.UniqueConstraint(
                fields=("portal", "navn"), name="ko_kjennetegn_navn_per_portal"
            ),
        ),
        migrations.AddConstraint(
            model_name="konserttype",
            constraint=models.UniqueConstraint(
                fields=("portal", "navn"), name="ko_konserttype_navn_per_portal"
            ),
        ),
    ]
