"""Standardgruppa «Lag» registrerer i `/park/` fra start (27. sep. 2026).

Lagene er nettopp dem parksiden er for (`docs/FORSLAG_PARK.md` §3.4). Uten
dette er lagnedtrekket tomt til noen finner knappen i gruppeoppsettet — og en
tom side er en side som later som den virker. Andre grupper står av; knappen
«Park» i gruppeoppsettet snur det.

Egen migrasjon etter feltet, ikke i samme: en dataendring i samme transaksjon
som en skjemaendring er det `DataOgSkjemaISammeTransaksjonTests` vokter mot.
"""
from django.db import migrations


def paa(apps, schema_editor):
    Ressursgruppe = apps.get_model('vaktliste', 'Ressursgruppe')
    Ressursgruppe.objects.filter(navn='Lag').update(registrerer_i_park=True)


class Migration(migrations.Migration):

    dependencies = [('vaktliste', '0024_ressursgruppe_registrerer_i_park')]

    operations = [migrations.RunPython(paa, migrations.RunPython.noop)]
