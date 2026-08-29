"""Backfill: oppdragsradene pekt på vakta for året sitt.

Andre halvdel av deploy 1-backfillen — se `patients.0015` for hele
resonnementet, navnevalget og estimatene. Kjører etter den, slik at vaktene
for år med pasientdata allerede finnes; her lages kun vakter for år som bare
har oppdrag (i praksis: ingen, men backfillen skal ikke anta det).
"""
from datetime import datetime

from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    Vakt = apps.get_model('core', 'Vakt')
    Oppdrag = apps.get_model('oppdrag', 'Oppdrag')
    AppSetting = apps.get_model('patients', 'AppSetting')

    rad = AppSetting.objects.filter(key='active_year').first()
    try:
        aktivt = int(rad.value) if rad else None
    except (TypeError, ValueError):
        aktivt = None

    for year in Oppdrag.objects.values_list('year', flat=True).distinct():
        vakt = Vakt.objects.filter(year=year).first()
        if vakt is None:
            rader = Oppdrag.objects.filter(year=year).order_by('created_at')
            er_aktiv = (year == aktivt)
            vakt = Vakt.objects.create(
                navn=str(year),
                year=year,
                startet=(getattr(rader.first(), 'created_at', None)
                         or timezone.make_aware(datetime(year, 1, 1))),
                avsluttet=(None if er_aktiv
                           else getattr(rader.last(), 'created_at', None)),
                er_aktiv=er_aktiv,
            )
        Oppdrag.objects.filter(year=year).update(vakt=vakt)


def reverser(apps, schema_editor):
    """Null FK-ene, så `patients.0015` sin reversering kan slette vaktene."""
    Oppdrag = apps.get_model('oppdrag', 'Oppdrag')
    Oppdrag.objects.update(vakt=None)


class Migration(migrations.Migration):

    dependencies = [
        ('oppdrag', '0005_oppdrag_vakt'),
        ('patients', '0015_vakt_backfill'),
    ]

    operations = [
        migrations.RunPython(backfill, reverser),
    ]
