"""Tøm «Annet sted»-tekstene i statistikk som alt er frosset (28. sep. 2026).

`OppdragStatistikkHandler.frys_stats` holder dem ute fra nå av; dette tar de
settene «Avslutt vakt» frøs på staging før det. Bare tekstene — tallene og
formen står, så visningen leser dem som før. Idempotent.

Logikken står her og ikke importert fra `oppdrag.statistikk`: en migrasjon
skal kjøre likt om fem år, uansett hva modulen heter eller gjør da.
"""
from django.db import migrations


def vask(apps, schema_editor):
    VaktStatistikk = apps.get_model('core', 'VaktStatistikk')
    for rad in VaktStatistikk.objects.filter(slug='oppdrag'):
        avreist = (rad.data or {}).get('avreist_til')
        if isinstance(avreist, dict) and avreist.get('annet_tekster'):
            avreist['annet_tekster'] = []
            rad.save(update_fields=['data'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_vaktstatistikk'),
        ('oppdrag', '0033_norsk_sortering'),
    ]

    operations = [
        migrations.RunPython(vask, migrations.RunPython.noop),
    ]
