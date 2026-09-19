"""Dataskrittet mellom `0008` og `0010`: det som sto i `Hendelse.beskrivelse`
blir det første tillegget i hendelsen, ført av den som opprettet den, på
opprettelsestidspunktet — og et `melder`-navn blir «Andre» med teksten.

**Bare data.** Skjemaet før står i `0008`, skjemaet etter i `0010`. Hadde
skrivingen og `RemoveField` stått i samme fil, ville PostgreSQL avvist
`ALTER TABLE` med «pending trigger events» (CLAUDE.md, «Migrasjoner»).

`lagsressurser` (fritekst, 18. sep.) migreres ikke: feltet levde ett døgn på
staging, og en tekst som «Lag 1, Lag 3» lar seg ikke slå opp mot en ressurs
med sikkerhet. Det som sto der er borte etter denne; det står i CHANGELOG.
"""

from django.db import migrations


def framover(apps, schema_editor):
    Hendelse = apps.get_model('ko', 'Hendelse')
    Logglinje = apps.get_model('ko', 'Logglinje')
    for h in Hendelse.objects.exclude(beskrivelse='').iterator():
        Logglinje.objects.create(
            vakt_id=h.vakt_id,
            kilde='operator',
            tidspunkt=h.opprettet_at,
            tekst=h.beskrivelse,
            forfatter_id=h.opprettet_av_id,
            forfatter_navn=h.opprettet_av_navn,
            hendelse=h,
            beskrivelse=True,
        )
    for h in Hendelse.objects.exclude(melder='').iterator():
        if not h.melder_typer:
            h.melder_typer = ['andre']
            h.save(update_fields=['melder_typer'])


def bakover(apps, schema_editor):
    Hendelse = apps.get_model('ko', 'Hendelse')
    Logglinje = apps.get_model('ko', 'Logglinje')
    for linje in (Logglinje.objects.filter(beskrivelse=True, hendelse__isnull=False)
                  .order_by('id').iterator()):
        h = Hendelse.objects.get(pk=linje.hendelse_id)
        h.beskrivelse = (h.beskrivelse + '\n' + linje.tekst).strip()
        h.save(update_fields=['beskrivelse'])


class Migration(migrations.Migration):

    dependencies = [
        ("ko", "0008_lag_tillegg_melder"),
    ]

    operations = [
        migrations.RunPython(framover, bakover),
    ]
