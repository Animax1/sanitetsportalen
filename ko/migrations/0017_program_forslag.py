"""Forslaget til konserttyper og kjennetegn (André, 23. sep. 2026: «vi kommer
med et forslag som vi kan justere»). Egen migrasjon, ikke i `0016`: data og
skjema i samme transaksjon er fella `DataOgSkjemaISammeTransaksjonTests`
holder vakt mot.

`get_or_create`, så en base som alt har en rad med samme navn ikke feiler.
Baklengs gjør ingenting: radene er KO-lederens fra første stund, og kan være
tatt i bruk eller omdøpt.
"""
from django.db import migrations

KONSERTTYPER = ('Headliner', 'Hiphop / rap', 'Rock / metal', 'Pop', 'Elektronisk / DJ',
                'Akustisk / lokal', 'Fast post (ikke konsert)')
KJENNETEGN = ('Pyro', 'Sittende publikum', 'Moshing ventet', 'Mye barn', 'Alkoholservering')


def legg_inn_forslag(apps, schema_editor):
    for modell, navnene in (('Konserttype', KONSERTTYPER), ('Kjennetegn', KJENNETEGN)):
        m = apps.get_model('ko', modell)
        for i, navn in enumerate(navnene):
            m.objects.get_or_create(navn=navn, defaults={'rekkefolge': (i + 1) * 10})


class Migration(migrations.Migration):

    dependencies = [('ko', '0016_program')]

    operations = [migrations.RunPython(legg_inn_forslag, migrations.RunPython.noop)]
