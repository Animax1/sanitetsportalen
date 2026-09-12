"""Data, del 2 av 3 (12. sep. 2026): seed enhetstypene og problemstillingene
fra listene i `choices.py`, og oversett `Enhet.type` (slug) til FK-en.

Bare skriving — ingen skjemaendring etter dataskrittet, så PostgreSQLs
triggerkø er ikke et problem her. Feltet `type` fjernes i `0021`.
"""
from django.db import migrations

# Kopi av seed-listene slik de var da migrasjonen ble skrevet. Migrasjoner
# skal ikke lese `choices` — endres lista senere, skal ikke en gammel
# migrasjon seede noe annet enn den gjorde i prod.
ENHETSTYPER = (
    ('ambulanse', 'Ambulanse'),
    ('mannskapsbil', 'Mannskapsbil'),
    ('lag', 'Lag til fots'),
    ('annet', 'Annet'),
)
MEDISINSK = (
    'Udefinert', 'Stor ytre blødning', 'Bevisstløs', 'Nedsatt bevissthet',
    'Pustevansker', 'Brystsmerter', 'Magesmerter', 'Blodsukker forstyrrelse',
    'Kramper', 'Temperatur forstyrrelse', 'Brannskade', 'Skade bein/fot',
    'Skade arm/håndledd', 'Skade skulder/kragebein', 'Skade overkropp',
    'Skade nakke', 'Skade hode', 'Skade øye/nese/øre/tann', 'Psykiatri',
    'Annen sykdom', 'Annen skade', 'Mistanke overgrep', 'Transport',
)
DRIFT = ('Udefinert', 'Matutlevering', 'Transport', 'Utstyr', 'Forsyning', 'Annet')
MED_ANTALL = ('Transport',)


def seed(apps, schema_editor):
    Enhetstype = apps.get_model('oppdrag', 'Enhetstype')
    Problemstilling = apps.get_model('oppdrag', 'Problemstilling')
    Enhet = apps.get_model('oppdrag', 'Enhet')

    typer = {}
    for i, (slug, navn) in enumerate(ENHETSTYPER):
        typer[slug], _ = Enhetstype.objects.get_or_create(
            navn=navn, defaults={'rekkefolge': (i + 1) * 10})
    for enhet in Enhet.objects.all():
        enhet.enhetstype = typer.get(enhet.type)
        enhet.save(update_fields=['enhetstype'])

    rekkefolge = 0
    for navn in MEDISINSK + tuple(p for p in DRIFT if p not in MEDISINSK):
        rekkefolge += 10
        i_medisinsk, i_drift = navn in MEDISINSK, navn in DRIFT
        kategori = 'begge' if (i_medisinsk and i_drift) else ('drift' if i_drift else 'medisinsk')
        Problemstilling.objects.get_or_create(navn=navn, defaults={
            'kategori': kategori, 'med_antall': navn in MED_ANTALL,
            'rekkefolge': 0 if navn == 'Udefinert' else rekkefolge})


def tilbake(apps, schema_editor):
    Enhet = apps.get_model('oppdrag', 'Enhet')
    for enhet in Enhet.objects.select_related('enhetstype'):
        navn = enhet.enhetstype.navn if enhet.enhetstype else ''
        enhet.type = next((slug for slug, n in ENHETSTYPER if n == navn), 'annet')
        enhet.save(update_fields=['type'])


class Migration(migrations.Migration):

    dependencies = [
        ('oppdrag', '0019_enhetstype_problemstilling_tabeller'),
    ]

    operations = [
        migrations.RunPython(seed, tilbake),
    ]
