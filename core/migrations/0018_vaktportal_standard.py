"""Portalene, del 2 av 3: «Standard», og `er_aktiv` blir fasit (17. okt. 2026).

Alle vakter går til portalen «Standard» — alt som finnes i dag hører til ett
miljø. Den lages også i en tom base, så testbasen og en fersk installasjon har
den.

**`er_aktiv` rettes etter pekeren.** Fram til nå var `AppSetting['aktiv_vakt_id']`
fasit og `er_aktiv` en kopi som kunne komme i utakt (`core/views_vakt.py` sa
det selv). Nøyaktig én vakt — den pekeren viser til — får `er_aktiv=True`; alle
andre `False`. Uten peker, eller med en som peker på noe som ikke finnes,
beholdes den nyeste som alt var merket aktiv. Uten noen av delene blir ingen
aktiv, og `hent_aktiv_vakt()` gjør vakta for året aktiv ved første oppslag,
som den alltid har gjort.

`avsluttet` røres ikke: en vakt som feilaktig sto som aktiv uten å være det,
var heller ikke den portalen viste, og når den ble lukket vet vi ikke.

**Pekeren slettes ikke.** Ruller noen tilbake til kode som leser den, peker
den fortsatt riktig — så lenge ingen har byttet vakt i mellomtiden. Den ryddes
i en senere migrasjon.
"""
from django.db import migrations


def standard_og_aktiv(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    Vakt = apps.get_model('core', 'Vakt')
    AppSetting = apps.get_model('core', 'AppSetting')

    portal, _ = Vaktportal.objects.get_or_create(
        slug='standard', defaults={'navn': 'Standard'})
    Vakt.objects.filter(portal__isnull=True).update(portal=portal)

    aktiv = None
    raa = AppSetting.objects.filter(key='aktiv_vakt_id').values_list('value', flat=True).first()
    try:
        aktiv = Vakt.objects.filter(pk=int(raa)).first() if raa is not None else None
    except (TypeError, ValueError):
        aktiv = None
    if aktiv is None:
        aktiv = Vakt.objects.filter(er_aktiv=True).order_by('-startet', '-pk').first()

    Vakt.objects.exclude(pk=getattr(aktiv, 'pk', None)).update(er_aktiv=False)
    if aktiv is not None:
        Vakt.objects.filter(pk=aktiv.pk).update(er_aktiv=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_vaktportal'),
    ]

    operations = [
        # Bakover: ingenting å gjøre. 0017 bakover fjerner kolonnen og tabellen,
        # og `er_aktiv`-rettingen er riktig også for koden før portalene.
        migrations.RunPython(standard_og_aktiv, migrations.RunPython.noop),
    ]
