"""Parklenken bærer portalen, del 2: alle lenker til «Standard» (17. okt. 2026)."""
from django.db import migrations


def fyll(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    standard, _ = Vaktportal.objects.get_or_create(
        slug='standard', defaults={'navn': 'Standard'})
    apps.get_model('park', 'Parklenke').objects.filter(portal__isnull=True).update(
        portal=standard)


class Migration(migrations.Migration):

    dependencies = [
        ('park', '0005_parklenke_portal'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
