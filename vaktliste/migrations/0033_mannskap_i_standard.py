"""Mannskapet per portal, del 2: alt som finnes, hører til «Standard» (17. okt. 2026)."""
from django.db import migrations


def fyll(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    standard, _ = Vaktportal.objects.get_or_create(
        slug='standard', defaults={'navn': 'Standard'})
    for navn in ('Mannskap', 'Kontokorps'):
        apps.get_model('vaktliste', navn).objects.filter(portal__isnull=True).update(
            portal=standard)


class Migration(migrations.Migration):

    dependencies = [
        ('vaktliste', '0032_mannskap_per_portal'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
