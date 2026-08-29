"""Deploy 2 av vakt-scopingen: vakta blir fasit, `year` forsvinner fra raden.

Skrevet for hånd, ikke av makemigrations — den interaktive «provide a
default»-dialogen gjelder ikke her: FK-en er allerede fylt av deploy 1 sin
backfill, verifisert i prod med `verifiser_vakt` («Ingen funn») 29. aug. 2026.
Sperresteget først i operasjonslista gjenkontrollerer det samme, med en
feilmelding som sier hva som skal gjøres, i stedet for en NOT NULL-eksplosjon
fra databasen.

**Enveis.** Etter denne finnes ikke `year` på radene, og koblingen kan ikke
gjenskapes fra data — flere vakter kan dele år. Rollback av deploy 2 er
gjenoppretting fra backup, ikke `migrate` bakover; RunPython-stegene sier det
høyt om noen prøver.

Datastegene:
- `event_name` → den aktive vaktas navn. Trygt akkurat her: verdien beskriver
  vakten som er aktiv nå. Historiske vakter beholder årstallsnavnet sitt.
- Telleren `next_patient_nr` → `next_patient_nr_vakt_<id>` for den aktive
  vakta. Skulle nøkkelen mangle, gjenskaper `next_patient_nr()` den fra
  radene — samme selvreparasjon som oppdragsnummeret har hatt fra start.
- `active_year` og `event_name` slettes fra AppSetting. `Vakt` bærer begge.
"""
from django.db import migrations, models
import django.db.models.deletion


def _stopp_reversering(apps, schema_editor):
    raise RuntimeError(
        'Deploy 2 kan ikke reverseres med migrate: year er borte fra radene '
        'og gjenskapes ikke. Rollback = gjenopprett fra backup.')


def sperre(apps, schema_editor):
    Patient = apps.get_model('patients', 'Patient')
    uten = Patient.objects.filter(vakt__isnull=True).count()
    if uten:
        raise RuntimeError(
            f'{uten} pasienter mangler vakt. Kjør «python manage.py '
            f'verifiser_vakt» og rett funnene før denne migrasjonen — '
            f'deploy 2 setter NOT NULL og har ingen year å falle tilbake på.')


def flytt_driftsverdier(apps, schema_editor):
    Vakt = apps.get_model('core', 'Vakt')
    AppSetting = apps.get_model('patients', 'AppSetting')

    peker = AppSetting.objects.filter(key='aktiv_vakt_id').first()
    aktiv = None
    if peker:
        try:
            aktiv = Vakt.objects.filter(pk=int(peker.value)).first()
        except (TypeError, ValueError):
            aktiv = None

    if aktiv is not None:
        navn = AppSetting.objects.filter(key='event_name').first()
        if navn and (navn.value or '').strip():
            nytt = navn.value.strip()
            # Unikhetskravet: kolliderer navnet med en annen vakt, beholder
            # den aktive årstallsnavnet sitt i stedet for å velte migrasjonen.
            if not Vakt.objects.filter(navn=nytt).exclude(pk=aktiv.pk).exists():
                aktiv.navn = nytt
                aktiv.save(update_fields=['navn'])

        teller = AppSetting.objects.filter(key='next_patient_nr').first()
        if teller:
            AppSetting.objects.update_or_create(
                key=f'next_patient_nr_vakt_{aktiv.pk}',
                defaults={'value': teller.value})

    AppSetting.objects.filter(
        key__in=('next_patient_nr', 'active_year', 'event_name')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_vakt'),
        ('patients', '0015_vakt_backfill'),
    ]

    operations = [
        migrations.RunPython(sperre, _stopp_reversering),
        migrations.AlterField(
            model_name='patient',
            name='vakt',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='pasienter', to='core.vakt', verbose_name='Vakt'),
        ),
        migrations.AlterField(
            model_name='patient',
            name='pasientnummer',
            field=models.IntegerField(verbose_name='Pasientnummer'),
        ),
        migrations.AddConstraint(
            model_name='patient',
            constraint=models.UniqueConstraint(
                fields=('vakt', 'pasientnummer'),
                name='unikt_pasientnummer_per_vakt'),
        ),
        migrations.RemoveField(model_name='patient', name='year'),
        migrations.RunPython(flytt_driftsverdier, _stopp_reversering),
    ]
