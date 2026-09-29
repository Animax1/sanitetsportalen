"""Tøm tittel, siste logglinje og hvem som lukket i frosset KO-statistikk (28. sep. 2026).

`KoStatistikkHandler.frys_stats` holder dem ute fra nå av; dette tar de
settene «Avslutt vakt» frøs på staging før det. Formen står, så visningen
leser dem som før. Idempotent.

Logikken står her og ikke importert fra `ko.statistikk`: en migrasjon skal
kjøre likt om fem år, uansett hva modulen heter eller gjør da.
"""
from django.db import migrations


def vask(apps, schema_editor):
    VaktStatistikk = apps.get_model('core', 'VaktStatistikk')
    for rad in VaktStatistikk.objects.filter(slug='ko'):
        loste = (rad.data or {}).get('hvem_loste')
        liste = loste.get('verken_liste') if isinstance(loste, dict) else None
        if not isinstance(liste, list):
            continue
        endret = False
        for v in liste:
            if isinstance(v, dict) and any(v.get(k) for k in ('tittel', 'siste_linje', 'lukket_av')):
                v.update(tittel='', siste_linje='', lukket_av='')
                endret = True
        if endret:
            rad.save(update_fields=['data'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_vaktstatistikk'),
        ('ko', '0023_hendelselest'),
    ]

    operations = [
        migrations.RunPython(vask, migrations.RunPython.noop),
    ]
