"""Tilhørighetene, del 3: «Standard» tar med alle korps, og kontoene får sitt (17. okt. 2026).

- **Hvert korps som finnes, er med i «Standard».** Ellers ville vaktlista stått
  uten korps etter deployen — den viser bare portalens.
- **Kontoene får tilhørigheten de allerede har**: korpset de fører
  (`Kontokorps`), og korpset til mannskapsraden de er koblet til
  (`Mannskap.user`). Moderatorens brukerliste bygger på dette.

Ligger i vaktlista og ikke i `core`: det er vaktlistas data som leses, og
`core` skal ikke kjenne en modul — heller ikke i en migrasjon.
"""
from django.db import migrations


def fyll(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    Tilhorighet = apps.get_model('core', 'Tilhorighet')
    Kontotilhorighet = apps.get_model('core', 'Kontotilhorighet')
    Kontokorps = apps.get_model('vaktliste', 'Kontokorps')
    Mannskap = apps.get_model('vaktliste', 'Mannskap')

    standard, _ = Vaktportal.objects.get_or_create(
        slug='standard', defaults={'navn': 'Standard'})
    standard.tilhorigheter.add(*Tilhorighet.objects.filter(type='korps'))

    par = set(Kontokorps.objects.values_list('user_id', 'korps_id'))
    par |= set(Mannskap.objects.filter(user__isnull=False).values_list('user_id', 'korps_id'))
    for bruker_id, korps_id in sorted(par):
        Kontotilhorighet.objects.get_or_create(bruker_id=bruker_id, tilhorighet_id=korps_id)


class Migration(migrations.Migration):

    dependencies = [
        ('vaktliste', '0030_korps_er_tilhorighet'),
        ('core', '0020_tilhorighet'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
