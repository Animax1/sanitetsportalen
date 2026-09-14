"""Slett `patients.BackupConfig` — backupplanen bor i `core.Backupplan`.

Singletonen styrte den gamle `db_backup`-kommandoen: ett intervall, for én
modul, valgt fra fem faste verdier. Den ble erstattet av `core.Backupplan`
13. sep. 2026 (tre moduser, fritt intervall, per modul), og verdiene ble
kopiert over allerede da — `core/0002_modulebackupconfig` leser denne tabellen
og skriver planraden for «patients». Derfor er det ingen data å ta vare på her:
migrasjonen som trengte dem har alt kjørt.

**Avhengigheten på `core/0002` gjør rekkefølgen til en regel.** Den
migrasjonen gjør `apps.get_model('patients', 'BackupConfig')` i et
`RunPython`-steg, og kjøres slettingen først i en tom base, finnes modellen
ikke lenger i den historiske tilstanden — `LookupError` ved oppsett av en ny
base, mens prod, der 0002 har kjørt for lenge siden, går fint.

Prøvd uten avhengigheten 14. sep. 2026: Django la dem likevel i riktig
rekkefølge, fordi `core/0002` selv peker på `patients/0005`. Kanten er altså
ikke det som redder oss i dag — den gjør bare at rekkefølgen står skrevet i
stedet for å være et sammentreff i grafen. Det er nok grunn til å ha den:
det som holder tilfeldigvis, slutter å holde uten at noen endrer det.

Ren skjemaendring: ingen `RunPython`, ingen triggerkø, ikke noe behov for
`SET CONSTRAINTS ALL IMMEDIATE`.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0016_vakt_er_fasit'),
        ('core', '0002_modulebackupconfig'),
    ]

    operations = [
        migrations.DeleteModel(name='BackupConfig'),
    ]
