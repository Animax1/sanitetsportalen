"""Samleplass og KO finnes i ett eksemplar.

`flere_enheter` er på for alle grupper, og settes av for de to som er én ting:
samleplassen og KO er samlingspunkt for flere korps, ikke flåter. Uten flagget
sto det en «Ny samleplass»-knapp som inviterte til å lage noe som ikke finnes.

**Dataskrittet står sist**, etter `AddField`. Da er det ingen skjemaendring
igjen som kan bli avvist av triggerkøen — se
`DataOgSkjemaISammeTransaksjonTests` og `vaktliste/0007`, som måtte tømme køen
fordi rekkefølgen der er motsatt.
"""
from django.db import migrations, models

#: Gruppene som finnes i ett eksemplar. Navnene er de migrasjon 0007 seedet;
#: har noen døpt dem om, gjør skrittet ingenting for dem — og det er riktig,
#: for da har vaktlederen alt tatt et valg vi ikke skal overstyre.
ENKELTGRUPPER = ('Samleplass', 'KO')


def sett_enkeltgrupper(apps, schema_editor):
    Ressursgruppe = apps.get_model('vaktliste', 'Ressursgruppe')
    Ressursgruppe.objects.filter(navn__in=ENKELTGRUPPER).update(
        flere_enheter=False)


def tilbake(apps, schema_editor):
    """Alt tilbake til «flere enheter» — feltets standardverdi."""
    Ressursgruppe = apps.get_model('vaktliste', 'Ressursgruppe')
    Ressursgruppe.objects.filter(navn__in=ENKELTGRUPPER).update(
        flere_enheter=True)


class Migration(migrations.Migration):

    dependencies = [
        ('vaktliste', '0008_korps_paa_plassen'),
    ]

    operations = [
        migrations.AddField(
            model_name='ressursgruppe',
            name='flere_enheter',
            field=models.BooleanField(
                default=True,
                help_text='Av for grupper som er én ting: samleplassen og KO '
                          'finnes i ett eksemplar. På for flåter — ambulanser, '
                          'biler, lag.',
                verbose_name='Flere enheter',
            ),
        ),
        migrations.RunPython(sett_enkeltgrupper, tilbake),
    ]
