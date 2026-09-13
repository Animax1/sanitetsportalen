"""Backupplan, steg 2 av 3: de gamle feltene fyller de nye.

Ingen skjemaendring her — se docstringen i `0008` for hvorfor de tre stegene
er delt.

**Eksisterende rader beholder oppførselen sin, og settes derfor til «egen
plan».** Alternativet var å la dem arve standardplanen med det samme, og det
ville vært å endre hvor ofte prod tar backup uten at noen ba om det. Arven er
en forenkling man skal velge, ikke en man våkner opp til. Nye rader som
opprettes etter denne migrasjonen følger standarden.

Oversettelsen av det gamle paret `enabled` + `interval_minutes`:

| Gammelt | Nytt |
|---|---|
| `enabled=False`, eller `interval_minutes=0` | modus `av` |
| ellers | modus `ved_endring` |

`ved_endring` er ikke et valg, det er en beskrivelse: den gamle scheduleren
hoppet over skrivingen når innholdet var identisk med forrige fil. Modusen
`alltid` fantes ikke, så ingen rad kan ha ment den.
"""
from django.db import migrations


def _verdi_og_enhet(minutter: int) -> tuple[int, str]:
    """Finn den groveste enheten som gjengir minuttallet nøyaktig.

    60 → (1, time), ikke (60, minutt). Enheten er det brukeren skal lese
    tilbake, og «hver time» er lettere å forstå enn «hvert 60. minutt».
    """
    if minutter <= 0:
        return 1, 'time'
    if minutter % 1440 == 0:
        return minutter // 1440, 'dogn'
    if minutter % 60 == 0:
        return minutter // 60, 'time'
    return minutter, 'minutt'


def fyll_fra_gamle_felter(apps, schema_editor):
    Backupplan = apps.get_model('core', 'Backupplan')

    for plan in Backupplan.objects.all():
        minutter = plan.interval_minutes or 0
        if not plan.enabled or minutter == 0:
            plan.modus = 'av'
            # Et intervall må stå der selv når modusen er av, ellers har
            # feltet ingen verdi å vise den dagen noen skrur den på igjen.
            verdi, enhet = _verdi_og_enhet(minutter or 60)
        else:
            plan.modus = 'ved_endring'
            verdi, enhet = _verdi_og_enhet(minutter)
        plan.intervall_verdi = verdi
        plan.intervall_enhet = enhet
        plan.folger_standard = False
        plan.save(update_fields=['modus', 'intervall_verdi', 'intervall_enhet',
                                 'folger_standard'])

    # Standardplanen må finnes før noen rad kan arve den. Verdiene er de samme
    # som `Backupplan.OPPSTARTSVERDIER`; står de to i utakt, er det denne som
    # gjelder for eksisterende baser, og koden som gjelder for nye.
    Backupplan.objects.get_or_create(slug='standard', defaults={
        'modus': 'ved_endring',
        'intervall_verdi': 10,
        'intervall_enhet': 'minutt',
        'behold': 50,
        'folger_standard': False,
    })


def tilbake(apps, schema_editor):
    """Skriv modusen tilbake til `enabled`, så en nedgradering ikke slår på
    backup for moduler som sto av."""
    Backupplan = apps.get_model('core', 'Backupplan')
    for plan in Backupplan.objects.exclude(slug='standard'):
        plan.enabled = plan.modus != 'av'
        plan.interval_minutes = plan.intervall_verdi * {
            'minutt': 1, 'time': 60, 'dogn': 1440}.get(plan.intervall_enhet, 1)
        plan.save(update_fields=['enabled', 'interval_minutes'])
    Backupplan.objects.filter(slug='standard').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_backupplan_skjema'),
    ]

    operations = [
        migrations.RunPython(fyll_fra_gamle_felter, tilbake),
    ]
