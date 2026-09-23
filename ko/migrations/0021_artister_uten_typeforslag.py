"""Konserttypene er blitt artister (André, 23. sep. 2026: «Endre navnet
konserttyper til Artist»).

Forslaget `0017` la inn — «Headliner», «Pop», «Fast post (ikke konsert)» — er
typer, ikke artister, og ville stått i artistlista som om noen hadde lagt dem
inn. **Bare de som ikke er i bruk fjernes**: en type en konsert alt peker på,
står, og KO-leder kan gi den et nytt navn. Egen migrasjon, bare data, så den
ikke deler transaksjon med skjemaendringen i `0020`.

Baklengs gjør ingenting: forslaget var bare et forslag.
"""
from django.db import migrations

FORSLAG = ('Headliner', 'Hiphop / rap', 'Rock / metal', 'Pop', 'Elektronisk / DJ',
           'Akustisk / lokal', 'Fast post (ikke konsert)')


def fjern_ubrukte_typeforslag(apps, schema_editor):
    Konserttype = apps.get_model('ko', 'Konserttype')
    Konserttype.objects.filter(navn__in=FORSLAG, poster__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [('ko', '0020_planlagt_plassering_og_artist')]

    operations = [migrations.RunPython(fjern_ubrukte_typeforslag, migrations.RunPython.noop)]
