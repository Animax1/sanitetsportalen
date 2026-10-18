"""Fyll `Vaktmannskap` så ingen forsvinner fra registeret ved deploy (18. okt. 2026).

Registeret på `/vaktliste/` viser fra nå bare vaktas folk. Uten denne ville det
stått tomt i portalen som er i gang. To kilder:

1. **Hver vakt som ikke er avsluttet** (den aktive og de planlagte) får hele
   portalens register — slik det så ut i går.
2. **Hver tidligere vakt** får dem som sto på et skift der — så «Hent inn fra
   tidligere» har noe å vise fra før i dag.

Bare innsetting, ingen skjemaendring etter, så triggerkøen er ingen sak her.
"""
from django.db import migrations


def fyll(apps, schema_editor):
    Mannskap = apps.get_model('vaktliste', 'Mannskap')
    Vaktpost = apps.get_model('vaktliste', 'Vaktpost')
    Vaktmannskap = apps.get_model('vaktliste', 'Vaktmannskap')
    Vakt = apps.get_model('core', 'Vakt')

    par = set()
    for vakt_id, portal_id in Vakt.objects.filter(avsluttet__isnull=True).values_list(
            'pk', 'portal_id'):
        if portal_id is None:
            continue
        for m_id in Mannskap.objects.filter(portal_id=portal_id).values_list('pk', flat=True):
            par.add((vakt_id, m_id))
    par |= set(Vaktpost.objects.filter(mannskap__isnull=False)
               .values_list('ressurs__vaktliste__vakt_id', 'mannskap_id'))
    Vaktmannskap.objects.bulk_create(
        [Vaktmannskap(vakt_id=v, mannskap_id=m) for v, m in sorted(par)],
        ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('vaktliste', '0034_vaktmannskap'),
        ('core', '0024_portalens_moduler'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
