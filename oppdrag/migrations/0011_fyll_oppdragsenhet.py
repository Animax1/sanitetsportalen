"""Én koblingsrad per oppdrag, fra `Oppdrag.enhet` — og meldingene pekes på den.

Deploy 1 av flere enheter på ett oppdrag (`docs/BESLUTNING_FLERE_ENHETER_
PER_OPPDRAG.md` §6). **Bare data, ingen skjemaendring** — derfor ingen
`SET CONSTRAINTS ALL IMMEDIATE`: triggerkøen fylles, men ingen `ALTER TABLE`
følger etter i samme transaksjon. Skjemaet står i `0010`; `Oppdrag.enhet` og
nullbarheten på `Statusmelding.oppdragsenhet` strammes i deploy 2.

Prøven i `core/migrasjonsprover.py` kjører denne mot PostgreSQL med rader i
den historiske formen og sjekker at hvert oppdrag fikk nøyaktig én
koblingsrad med oppdragets status, og at ingen melding står uten.
"""

from django.db import migrations


def fyll(apps, schema_editor):
    Oppdrag = apps.get_model('oppdrag', 'Oppdrag')
    Oppdragsenhet = apps.get_model('oppdrag', 'Oppdragsenhet')
    Statusmelding = apps.get_model('oppdrag', 'Statusmelding')

    for oppdrag in Oppdrag.objects.filter(enheter__isnull=True).iterator():
        rad = Oppdragsenhet.objects.create(
            oppdrag=oppdrag,
            enhet_id=oppdrag.enhet_id,
            status=oppdrag.status,
            varslet_at=oppdrag.created_at,
            varslet_av_id=oppdrag.opprettet_av_id,
            rekkefolge=0,
        )
        Statusmelding.objects.filter(
            oppdrag=oppdrag, oppdragsenhet__isnull=True).update(oppdragsenhet=rad)


def tom(apps, schema_editor):
    # Baklengs: koblingsradene bort, meldingene tilbake til bare oppdrag.
    # `Oppdrag.enhet` står urørt i deploy 1, så ingenting går tapt.
    Statusmelding = apps.get_model('oppdrag', 'Statusmelding')
    Oppdragsenhet = apps.get_model('oppdrag', 'Oppdragsenhet')
    Statusmelding.objects.update(oppdragsenhet=None)
    Oppdragsenhet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("oppdrag", "0010_flere_enheter"),
    ]

    operations = [
        migrations.RunPython(fyll, tom),
    ]
