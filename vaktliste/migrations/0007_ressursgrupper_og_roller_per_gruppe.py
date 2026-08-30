"""Ressurstypen blir en tabell, og rollen blir gruppas.

**Tre skritt i én migrasjon, fordi de henger sammen.** `Ressurs.type` var en
`choices`-streng; den blir `Ressurs.gruppe`, en FK. Rollene var globale; de blir
gruppas. Og begge deler har data i basen som må følge med — en tom
`RenameField` ville tømt vaktlistene for både gruppe og rolle.

**Rollene viftes ut, de flyttes ikke.** En global rolle er i dag tilgjengelig
overalt, og det er den oppførselen som skal bevares: hver eksisterende rolle
kopieres derfor til *hver* gruppe, og vaktpostene pekes på kopien som hører til
sin egen ressurs' gruppe. Alternativet — å gjette hvilken gruppe «Lagleder»
egentlig hørte til — ville tatt bort rollen fra rader som lovlig brukte den.
Prisen er noen ubrukte rader vaktlederen kan slette; det er den billige feilen.

Standardgruppene er hardkodet her og ikke lest fra `choices.py`. En migrasjon
skal gi samme resultat om fem år, og appkoden den leste da kan være borte.
"""
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.text


#: (verdien som sto i `Ressurs.type`, visningsnavn, ikon)
STANDARDGRUPPER = (
    ('samleplass', 'Samleplass', 'hospital'),
    ('mannskapsbil', 'Mannskapsbil', 'truck-front'),
    ('ambulanse', 'Ambulanse', 'truck'),
    ('lag', 'Lag', 'people'),
    ('ko', 'KO', 'broadcast-pin'),
    ('annet', 'Annet', 'box'),
)


def seed_og_flytt(apps, schema_editor):
    Ressursgruppe = apps.get_model('vaktliste', 'Ressursgruppe')
    Ressurs = apps.get_model('vaktliste', 'Ressurs')
    Ressursrolle = apps.get_model('vaktliste', 'Ressursrolle')
    Vaktpost = apps.get_model('vaktliste', 'Vaktpost')

    # Alle seks opprettes, også de ingen bruker: de er standardsettet en ny
    # installasjon skal ha, og migrasjonen er det eneste stedet som gir det.
    per_verdi = {}
    for i, (verdi, navn, ikon) in enumerate(STANDARDGRUPPER):
        per_verdi[verdi] = Ressursgruppe.objects.create(
            navn=navn, ikon=ikon, rekkefolge=(i + 1) * 10)
    reserve = per_verdi['annet']

    for ressurs in Ressurs.objects.all():
        ressurs.gruppe = per_verdi.get(ressurs.type, reserve)
        ressurs.save(update_fields=['gruppe'])

    # Rollene: én kopi per gruppe, og vaktpostene følger sin egen gruppe.
    gamle = list(Ressursrolle.objects.filter(gruppe__isnull=True))
    for gammel in gamle:
        kopi_per_gruppe = {}
        for gruppe in per_verdi.values():
            kopi_per_gruppe[gruppe.pk] = Ressursrolle.objects.create(
                gruppe=gruppe, navn=gammel.navn, er_aktiv=gammel.er_aktiv)
        for vp in Vaktpost.objects.filter(rolle=gammel).select_related('ressurs'):
            vp.rolle_id = kopi_per_gruppe[vp.ressurs.gruppe_id].pk
            vp.save(update_fields=['rolle'])
        gammel.delete()


def tilbake(apps, schema_editor):
    """Nok til at migrasjonen kan rulles tilbake uten å felle skranker.

    Den gjenoppretter ikke `type`-strengen — feltet er borte i denne
    retningen, og `RemoveField` legger det tilbake med standardverdien.
    Rollene slås sammen til én rad per navn, slik `unique=True` krever.
    """
    Ressursrolle = apps.get_model('vaktliste', 'Ressursrolle')
    Vaktpost = apps.get_model('vaktliste', 'Vaktpost')

    beholdt = {}
    for rolle in Ressursrolle.objects.order_by('pk'):
        if rolle.navn in beholdt:
            Vaktpost.objects.filter(rolle=rolle).update(rolle=beholdt[rolle.navn])
            rolle.delete()
        else:
            beholdt[rolle.navn] = rolle
            rolle.gruppe = None
            rolle.save(update_fields=['gruppe'])


class Migration(migrations.Migration):

    dependencies = [
        ('vaktliste', '0006_gi_rollen_riktig_navn'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ressursgruppe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(
                    auto_now_add=True, help_text='Tidspunktet raden ble opprettet.',
                    verbose_name='Opprettet')),
                ('updated_at', models.DateTimeField(
                    auto_now=True, help_text='Tidspunktet raden sist ble endret.',
                    verbose_name='Sist oppdatert')),
                ('navn', models.CharField(max_length=60, unique=True, verbose_name='Navn')),
                ('ikon', models.CharField(
                    default='box',
                    help_text='Bootstrap-ikon uten «bi-»-prefiks, f.eks. «truck».',
                    max_length=40, verbose_name='Ikon')),
                ('rekkefolge', models.IntegerField(
                    default=100,
                    help_text='Styrer rekkefølgen på faner og bemanningskurver. '
                              'Settes automatisk til opprettelsesrekkefølgen.',
                    verbose_name='Rekkefølge')),
                ('er_aktiv', models.BooleanField(
                    default=True,
                    help_text='Inaktive grupper skjules i nedtrekk, men beholdes '
                              'på ressurser som allerede bruker dem.',
                    verbose_name='Aktiv')),
            ],
            options={
                'verbose_name': 'Ressursgruppe',
                'verbose_name_plural': 'Ressursgrupper',
                'ordering': ['rekkefolge', django.db.models.functions.text.Lower('navn')],
            },
        ),
        # Begge FK-ene legges nullbare, fylles av dataskrittet, og strammes
        # etterpå. Rekkefølgen er ikke valgfri: en NOT NULL-kolonne kan ikke
        # legges på en tabell som allerede har rader.
        migrations.AddField(
            model_name='ressurs',
            name='gruppe',
            field=models.ForeignKey(
                null=True,
                help_text='Hva slags ting ressursen er. Styrer ikon, fanerekkefølge, '
                          'hvilke roller som tilbys, og hvilken bemanningskurve den '
                          'telles i.',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='ressurser', to='vaktliste.ressursgruppe',
                verbose_name='Gruppe'),
        ),
        migrations.AddField(
            model_name='ressursrolle',
            name='gruppe',
            field=models.ForeignKey(
                null=True,
                help_text='Rollen tilbys på ressurser i denne gruppa.',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='roller', to='vaktliste.ressursgruppe',
                verbose_name='Ressursgruppe'),
        ),
        # Navnet må slippe den globale unikheten *før* kopiene lages.
        migrations.AlterField(
            model_name='ressursrolle',
            name='navn',
            field=models.CharField(max_length=120, verbose_name='Navn'),
        ),
        migrations.RunPython(seed_og_flytt, tilbake),
        migrations.RemoveField(model_name='ressurs', name='type'),
        migrations.AlterField(
            model_name='ressurs',
            name='gruppe',
            field=models.ForeignKey(
                help_text='Hva slags ting ressursen er. Styrer ikon, fanerekkefølge, '
                          'hvilke roller som tilbys, og hvilken bemanningskurve den '
                          'telles i.',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='ressurser', to='vaktliste.ressursgruppe',
                verbose_name='Gruppe'),
        ),
        migrations.AlterField(
            model_name='ressursrolle',
            name='gruppe',
            field=models.ForeignKey(
                help_text='Rollen tilbys på ressurser i denne gruppa.',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='roller', to='vaktliste.ressursgruppe',
                verbose_name='Ressursgruppe'),
        ),
        migrations.AlterModelOptions(
            name='ressursrolle',
            options={'ordering': ['gruppe__rekkefolge',
                                  django.db.models.functions.text.Lower('navn')],
                     'verbose_name': 'Ressursrolle',
                     'verbose_name_plural': 'Ressursroller'},
        ),
        migrations.AddConstraint(
            model_name='ressursrolle',
            constraint=models.UniqueConstraint(
                fields=('gruppe', 'navn'), name='unikt_rollenavn_per_gruppe'),
        ),
    ]
