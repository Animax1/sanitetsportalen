"""Legg til CustomUser.current_session_key (N10).

**IKKE DØP OM DENNE FILA.** Navnet må være nøyaktig
``0008_customuser_current_session_key_and_more``, fordi det er navnet som står
registrert i ``django_migrations`` i produksjon. Django matcher migrasjoner på
app + navn, ikke på innhold: endrer man filnavnet, ser Django en ukjent
migrasjon, prøver å kjøre den på nytt, og feiler med
``DuplicateColumn: column "current_session_key" already exists``. Det skjedde
13. august 2026 og tok ned produksjon — se hendelsesnotatet i CHANGELOG.

Navnet stammer fra en generert versjon som også inneholdt en ``AlterField`` på
``is_superuser``. Det var kosmetisk opprydding av et avvik mellom Djangos
modellstatus og migrasjonshistorikken, og er fjernet fra innholdet her — men
navnet må bli stående. At fila heter «and_more» uten å inneholde «more» er
prisen for det.

Innholdet legger til én nullbar kolonne. Ingen indekser, ingen tabellås av
betydning, ingen omskriving av eksisterende rader.

Bakgrunnen for at kosmetikken er fjernet: en tilsvarende uetterspurt
oppryddingsmigrasjon (``audit/0004``, en indeks-omdøping) viste seg umulig å
kjøre mot den faktiske databasen og crash-loopet release-fasen samme dag. En
migrasjon skal gjøre én ting man faktisk trenger.
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
