"""Oppdragsnummer og arkivflagg.

To ting i én migrasjon fordi de kom av samme behov: å finne tilbake til et
oppdrag etter at det er ryddet bort fra tavla.

**Nummeret backfilles før unikhetskravet settes.** Rekkefølgen er poenget:
legges kolonnen til som `NOT NULL` med en default, får alle eksisterende rader
samme nummer og `UniqueConstraint` feiler ved neste steg. Derfor tre steg —
nullbar kolonne, backfill, så stram inn.

Backfillen nummererer per år i `created_at`-rekkefølge, altså i den
rekkefølgen oppdragene faktisk kom inn, og setter `AppSetting`-telleren for
hvert år den fant. Uten det siste ville neste opprettelse startet på 1 og
kollidert.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_nummer(apps, schema_editor):
    Oppdrag = apps.get_model('oppdrag', 'Oppdrag')
    AppSetting = apps.get_model('patients', 'AppSetting')

    aar = Oppdrag.objects.values_list('year', flat=True).distinct()
    for year in aar:
        nr = 0
        rader = Oppdrag.objects.filter(year=year).order_by('created_at', 'pk')
        for nr, oppdrag in enumerate(rader, start=1):
            oppdrag.oppdragsnummer = nr
            oppdrag.save(update_fields=['oppdragsnummer'])
        # Telleren må stå der backfillen slapp. Starter den på 1, kolliderer
        # neste opprettelse med rad nummer 1 og feiler på unikhetskravet.
        AppSetting.objects.update_or_create(
            key=f'next_oppdrag_nr_{year}',
            defaults={'value': str(nr + 1)},
        )


def fjern_tellere(apps, schema_editor):
    """Reversering: ta bort tellerne backfillen laget.

    Kolonnene forsvinner av seg selv når operasjonene rulles tilbake, men
    `AppSetting`-radene er skrevet av denne funksjonen og må ryddes her.
    """
    AppSetting = apps.get_model('patients', 'AppSetting')
    AppSetting.objects.filter(key__startswith='next_oppdrag_nr_').delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('patients', '0001_initial'),
        ('oppdrag', '0002_enhet_pa_vakt'),
    ]

    operations = [
        # 1) Nullbar, slik at eksisterende rader kan legges til uten verdi.
        migrations.AddField(
            model_name='oppdrag',
            name='oppdragsnummer',
            field=models.IntegerField(null=True, verbose_name='Oppdragsnummer'),
        ),
        # 2) Fyll dem, per år, i den rekkefølgen oppdragene kom inn.
        migrations.RunPython(backfill_nummer, fjern_tellere),
        # 3) Først nå kan kolonnen kreve verdi, og nummeret være unikt.
        migrations.AlterField(
            model_name='oppdrag',
            name='oppdragsnummer',
            field=models.IntegerField(verbose_name='Oppdragsnummer'),
        ),
        migrations.AddConstraint(
            model_name='oppdrag',
            constraint=models.UniqueConstraint(
                fields=('year', 'oppdragsnummer'),
                name='unikt_oppdragsnummer_per_aar',
            ),
        ),
        migrations.AddField(
            model_name='oppdrag',
            name='arkivert_at',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True, verbose_name='Arkivert'),
        ),
        migrations.AddField(
            model_name='oppdrag',
            name='arkivert_av',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='arkiverte_oppdrag',
                to=settings.AUTH_USER_MODEL, verbose_name='Arkivert av'),
        ),
    ]
