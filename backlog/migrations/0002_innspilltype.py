"""Innspilltype blir en tabell, og de to standardtypene seedes.

**Skjema først, data etter.** Rekkefølgen er ikke tilfeldig: den motsatte —
skrive rader og *deretter* endre skjema i samme transaksjon — er fella som tok
ned deployen 30. aug. 2026, fordi PostgreSQLs utsatte triggere ikke er tømt
når `ALTER TABLE` kommer. Her er det ingen `ALTER` etter skrivingen, så
migrasjonen er trygg som den står. Koblingen gjøres i `0003`, og den gamle
kolonnen fjernes i `0004` — tre migrasjoner nettopp for å holde hvert dataskritt
unna en skjemaendring.
"""
from django.db import migrations, models
import django.db.models.functions.text


def seed(apps, schema_editor):
    """De to typene bestillingen navnga. Resten legger admin inn selv."""
    Innspilltype = apps.get_model('backlog', 'Innspilltype')
    for rekkefolge, navn in ((10, 'Bug'), (20, 'Ønske')):
        Innspilltype.objects.get_or_create(
            navn=navn, defaults={'rekkefolge': rekkefolge})


def fjern_seed(apps, schema_editor):
    """Reverserbar, men **bare når ingen bruker dem** — `Innspill.type` er
    `PROTECT`, så en tilbakerulling med innspill på radene stopper her og ikke
    halvveis inne i en sletting."""
    Innspilltype = apps.get_model('backlog', 'Innspilltype')
    Innspilltype.objects.filter(navn__in=('Bug', 'Ønske')).delete()


class Migration(migrations.Migration):

    dependencies = [('backlog', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='Innspilltype',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('navn', models.CharField(max_length=40, unique=True,
                                          verbose_name='Navn')),
                ('er_aktiv', models.BooleanField(
                    default=True,
                    help_text='Inaktive typer kan ikke velges på nye innspill, '
                              'men blir stående på dem som alt har den.',
                    verbose_name='Aktiv')),
                ('rekkefolge', models.IntegerField(
                    default=100,
                    help_text='Styrer rekkefølgen i nedtrekket. Settes '
                              'automatisk til opprettelsesrekkefølgen.',
                    verbose_name='Rekkefølge')),
            ],
            options={
                'verbose_name': 'Innspilltype',
                'verbose_name_plural': 'Innspilltyper',
                'ordering': ['rekkefolge',
                             django.db.models.functions.text.Lower('navn')],
            },
        ),
        migrations.RunPython(seed, fjern_seed),
    ]
