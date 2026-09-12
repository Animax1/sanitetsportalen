"""Data (12. sep. 2026): seed lydvarselets terskler med tallene fra første
utgave. Bare skriving — egen migrasjon, så den ikke deler transaksjon med en
skjemaendring (PostgreSQLs triggerkø, se CLAUDE.md «Migrasjoner»)."""
from django.db import migrations

TERSKLER = {'Akutt': (60, 10), 'Haster': (300, 60), 'Vanlig': (900, 60), 'Drift': (900, 60)}


def seed(apps, schema_editor):
    Lydvarsel = apps.get_model('oppdrag', 'Lydvarsel')
    for hastegrad, (forste, gjenta) in TERSKLER.items():
        Lydvarsel.objects.get_or_create(
            hastegrad=hastegrad, defaults={'forste_sekunder': forste, 'gjenta_sekunder': gjenta})


class Migration(migrations.Migration):

    dependencies = [
        ('oppdrag', '0023_lydvarsel'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
