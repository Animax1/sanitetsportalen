"""Legg til CustomUser.current_session_key (N10).

Håndskrevet, ikke generert. `makemigrations` ville tatt med en `AlterField` på
`is_superuser` i samme slengen — et rent kosmetisk avvik mellom Djangos
modellstatus og migrasjonshistorikken, som stammer fra en Django-oppgradering.

Den er utelatt med vilje. En deploy 13. august 2026 tok ned produksjon fordi en
tilsvarende, uetterspurt oppryddingsmigrasjon (`audit/0004`, en indeks-omdøping)
viste seg umulig å kjøre mot den faktiske databasen — se hendelsesnotatet i
CHANGELOG. Lærdommen er å la en migrasjon gjøre én ting man faktisk trenger.

Denne legger til én nullbar kolonne. Ingen indekser, ingen tabellås av betydning,
ingen omskriving av eksisterende rader.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_module_permission_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='current_session_key',
            field=models.CharField(
                blank=True,
                max_length=40,
                null=True,
                verbose_name='Aktiv sesjonsnøkkel',
            ),
        ),
    ]
