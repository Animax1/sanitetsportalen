"""Deploy 2 for oppdragene: vakta blir fasit også her.

Se `patients.0016` for hele resonnementet — sperren, enveisheten og
selvreparasjonen for tellere er de samme. Tellerne
`next_oppdrag_nr_<år>` flyttes til `next_oppdrag_nr_vakt_<id>` via vakta for
året; skulle en mangle, gjenskaper `neste_oppdragsnummer()` den fra radene.
"""
from django.db import migrations, models
import django.db.models.deletion


def _stopp_reversering(apps, schema_editor):
    raise RuntimeError(
        'Deploy 2 kan ikke reverseres med migrate: year er borte fra radene '
        'og gjenskapes ikke. Rollback = gjenopprett fra backup.')


def sperre(apps, schema_editor):
    Oppdrag = apps.get_model('oppdrag', 'Oppdrag')
    uten = Oppdrag.objects.filter(vakt__isnull=True).count()
    if uten:
        raise RuntimeError(
            f'{uten} oppdrag mangler vakt. Kjør «python manage.py '
            f'verifiser_vakt» og rett funnene før denne migrasjonen.')


def flytt_tellere(apps, schema_editor):
    Vakt = apps.get_model('core', 'Vakt')
    AppSetting = apps.get_model('patients', 'AppSetting')

    for rad in AppSetting.objects.filter(key__startswith='next_oppdrag_nr_'):
        hale = rad.key.rsplit('_', 1)[-1]
        if not hale.isdigit() or rad.key.startswith('next_oppdrag_nr_vakt_'):
            continue
        vakt = Vakt.objects.filter(year=int(hale)).order_by('-startet').first()
        if vakt is not None:
            AppSetting.objects.update_or_create(
                key=f'next_oppdrag_nr_vakt_{vakt.pk}',
                defaults={'value': rad.value})
        rad.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('oppdrag', '0006_vakt_backfill'),
        ('patients', '0016_vakt_er_fasit'),
    ]

    operations = [
        migrations.RunPython(sperre, _stopp_reversering),
        migrations.AlterField(
            model_name='oppdrag',
            name='vakt',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='oppdrag', to='core.vakt', verbose_name='Vakt'),
        ),
        migrations.RemoveConstraint(
            model_name='oppdrag', name='unikt_oppdragsnummer_per_aar'),
        migrations.AddConstraint(
            model_name='oppdrag',
            constraint=models.UniqueConstraint(
                fields=('vakt', 'oppdragsnummer'),
                name='unikt_oppdragsnummer_per_vakt'),
        ),
        migrations.RemoveIndex(model_name='oppdrag', name='oppdrag_aar_status_idx'),
        migrations.AddIndex(
            model_name='oppdrag',
            index=models.Index(fields=['vakt', 'status'],
                               name='oppdrag_vakt_status_idx'),
        ),
        migrations.RemoveField(model_name='oppdrag', name='year'),
        migrations.RunPython(flytt_tellere, _stopp_reversering),
    ]
