"""«Vi finner ikke fram» ble «Send posisjon», for bil og lag (André, 7. okt. 2026).

Varigheten flytter fra parks `park_hjelp_varighet_min` til kartkoblingens
`kart_delt_posisjon_min` — én felles innstilling i kortet «Kartet». Har admin satt en verdi på
staging, følger den med; den gamle raden slettes. Bare data, ingen skjemaendring, så
triggerkøen i PostgreSQL er ikke et tema (CLAUDE.md, «Migrasjoner»).
"""
from django.db import migrations

GAMMEL = 'park_hjelp_varighet_min'
NY = 'kart_delt_posisjon_min'


def flytt(apps, schema_editor):
    AppSetting = apps.get_model('core', 'AppSetting')
    gammel = AppSetting.objects.filter(key=GAMMEL).first()
    if gammel is None:
        return
    if not AppSetting.objects.filter(key=NY).exists():
        AppSetting.objects.create(key=NY, value=gammel.value)
    gammel.delete()


def tilbake(apps, schema_editor):
    AppSetting = apps.get_model('core', 'AppSetting')
    ny = AppSetting.objects.filter(key=NY).first()
    if ny is not None and not AppSetting.objects.filter(key=GAMMEL).exists():
        AppSetting.objects.create(key=GAMMEL, value=ny.value)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_backup_pre_slett'),
    ]

    operations = [
        migrations.RunPython(flytt, tilbake),
    ]
