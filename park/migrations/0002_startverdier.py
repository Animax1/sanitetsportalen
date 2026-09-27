"""Startverdiene for de to verdimengdene (`docs/FORSLAG_PARK.md` §3.3).

**Problemstillingene er kopiert, ikke importert**, fra
`patients.choices.PROBLEMSTILLING` slik den sto 27. sep. 2026 (B6). En
migrasjon skal gi samme resultat om ett år; en import ville gitt det som står i
pasientmodulen *da*. Og fra første endring er lista parks egen.

**Utfallene** er Andrés (B7, 27. sep. 2026): «Behandlet på stedet» øverst.
"""
from django.db import migrations

PROBLEMSTILLINGER = (
    'Stor ytre blødning',
    'Bevisstløs',
    'Nedsatt bevissthet',
    'Pustevansker',
    'Brystsmerter',
    'Magesmerter',
    'Blodsukker forstyrrelse',
    'Kramper',
    'Temperatur forstyrrelse',
    'Brannskade',
    'Skade bein/fot',
    'Skade arm/håndledd',
    'Skade skulder/kragebein',
    'Skade overkropp',
    'Skade nakke',
    'Skade hode',
    'Skade øye/nese/øre/tann',
    'Psykiatri',
    'Annen sykdom',
    'Annen skade',
    'Mistanke overgrep',
)

UTFALL = (
    'Behandlet på stedet',
    'Gikk videre selv',
    'Fulgt til samleplass',
    'Tilkalt bil',
    'Avslo hjelp',
    'Overlatt til andre (vakt/politi)',
)


def fyll(apps, schema_editor):
    for modell, navnene in (('Problemstilling', PROBLEMSTILLINGER), ('Utfall', UTFALL)):
        Modell = apps.get_model('park', modell)
        for i, navn in enumerate(navnene):
            # `get_or_create`: en base der noen allerede har lagt inn raden
            # (en gjenoppretting før migrasjonen) skal ikke feile på unik.
            Modell.objects.get_or_create(navn=navn, defaults={'rekkefolge': (i + 1) * 10})


class Migration(migrations.Migration):

    dependencies = [('park', '0001_initial')]

    operations = [migrations.RunPython(fyll, migrations.RunPython.noop)]
