"""Døp om arkivfeltene til historikk.

Ren omdøping — ingen data endres, ingen kolonne legges til eller fjernes.

**Grunnen er navnekollisjon, ikke smak.** `core.arkiv` fryser, signerer og
kollapser hele vakter, og oppdragsmodulen får sin egen `BaseArkivHandler` i
fase 7. Feltene her gjør noe helt annet: de flytter ett oppdrag ut av den
aktive tavla. Hadde begge hett «arkiv», ville de stått med samme navn i samme
app og betydd hver sin ting — og den som leste `arkiver_view` ville trodd raden
ble fryst.

`RenameField` beholder innholdet; radene som allerede er flyttet ut av tavla på
staging beholder tidspunktet sitt.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('oppdrag', '0003_oppdragsnummer_og_arkivering'),
    ]

    operations = [
        migrations.RenameField(
            model_name='oppdrag',
            old_name='arkivert_at',
            new_name='historikk_fra',
        ),
        migrations.RenameField(
            model_name='oppdrag',
            old_name='arkivert_av',
            new_name='historikk_av',
        ),
        # Etikettene og related_name følger med navnet. `related_name` er den
        # som betyr noe i kode: `bruker.arkiverte_oppdrag` ville fortsatt lovet
        # arkivering.
        migrations.AlterField(
            model_name='oppdrag',
            name='historikk_fra',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True,
                verbose_name='I historikk fra'),
        ),
        migrations.AlterField(
            model_name='oppdrag',
            name='historikk_av',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='oppdrag_lagt_i_historikk',
                to=settings.AUTH_USER_MODEL, verbose_name='Flyttet av'),
        ),
    ]
