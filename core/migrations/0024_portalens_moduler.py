"""Modulene i hver portal, del 2: hver portal får alle modulene med taket på toppen.

**Med én portal skal ingenting endres** — Standard hadde alle modulene før
`Portalmodul` fantes, og har dem etterpå. Modulene leses av `ModuleSettings`,
som har én rad per registrert modul (`ModuleSettings.ensure_defaults_exist`):
migrasjonen får ikke importere registeret i `core.modules`, som kan ha endret
seg siden den ble skrevet.
"""
from django.db import migrations

#: Toppen av stigen (`core.auth_decorators.NIVAA_HIERARKI`), skrevet ut: en
#: migrasjon skal ikke endre seg når koden gjør det.
TOPPEN = 'skriv_leder'


def fyll(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    ModuleSettings = apps.get_model('core', 'ModuleSettings')
    Portalmodul = apps.get_model('core', 'Portalmodul')
    slugger = list(ModuleSettings.objects.values_list('slug', flat=True))
    for portal in Vaktportal.objects.all():
        for slug in slugger:
            Portalmodul.objects.get_or_create(portal=portal, modul_slug=slug,
                                              defaults={'tak': TOPPEN})


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_portalmodul'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
