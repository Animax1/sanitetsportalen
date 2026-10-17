"""KOs lister og ansvarsmerket per portal, del 2: alt til «Standard» (17. okt. 2026)."""
from django.db import migrations


def fyll(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    standard, _ = Vaktportal.objects.get_or_create(
        slug='standard', defaults={'navn': 'Standard'})
    for navn in ('Ansvarsomraade', 'Konserttype', 'Kjennetegn', 'Ansvarsmerke'):
        apps.get_model('ko', navn).objects.filter(portal__isnull=True).update(portal=standard)


class Migration(migrations.Migration):

    dependencies = [
        ('ko', '0025_ko_listene_per_portal'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
