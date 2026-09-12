"""Skjema, del 3 av 3 (12. sep. 2026): `Enhet.type` er oversatt til FK-en i
`0020` og fjernes. Egen migrasjon, så skjemaendringen ikke står i samme
transaksjon som dataskrittet."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('oppdrag', '0020_seed_enhetstyper_problemstillinger'),
    ]

    operations = [
        migrations.RemoveField(model_name='enhet', name='type'),
    ]
