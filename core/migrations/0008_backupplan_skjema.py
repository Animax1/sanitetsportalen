"""Backupplan, steg 1 av 3: skjemaet.

Delt i tre migrasjoner med vilje. `ModuleBackupConfig` skal bli `Backupplan`
med nye felter, de gamle skal fylle de nye, og så skal de gamle bort — altså
skjema, data, skjema. Gjøres det i én migrasjon, skriver vi rader og kjører
`ALTER TABLE` i samme transaksjon, og PostgreSQL avviser det med
«cannot ALTER TABLE … because it has pending trigger events». Det tok ned
release-fasen 30. august 2026 (`vaktliste.0007`), og CLAUDE.md gir tre lovlige
veier ut: tømme triggerkøen, `atomic = False`, eller dele opp. Her er
oppdelingen den enkleste — hver migrasjon gjør én slags ting, og da finnes
problemet ikke.

Ingen kolonner mister data: de tre gamle feltene som betyr noe videre
(`module_slug`, `max_backups`, `last_run_at`) gis nye navn framfor å bli
opprettet på nytt.
"""
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_offsitekopi'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ModuleBackupConfig',
            new_name='Backupplan',
        ),
        migrations.RenameField('backupplan', 'module_slug', 'slug'),
        migrations.RenameField('backupplan', 'max_backups', 'behold'),
        migrations.RenameField('backupplan', 'last_run_at', 'sist_fil_at'),
        migrations.AddField(
            model_name='backupplan',
            name='folger_standard',
            field=models.BooleanField(
                default=True,
                help_text='Av for å gi denne modulen egne innstillinger.',
                verbose_name='Følger standardplanen'),
        ),
        migrations.AddField(
            model_name='backupplan',
            name='modus',
            field=models.CharField(
                choices=[('av', 'Av'), ('ved_endring', 'Ved endring'),
                         ('alltid', 'Alltid')],
                default='ved_endring', max_length=16, verbose_name='Modus'),
        ),
        migrations.AddField(
            model_name='backupplan',
            name='intervall_verdi',
            field=models.PositiveIntegerField(
                default=1, validators=[MinValueValidator(1)],
                verbose_name='Intervall'),
        ),
        migrations.AddField(
            model_name='backupplan',
            name='intervall_enhet',
            field=models.CharField(
                choices=[('minutt', 'minutter'), ('time', 'timer'),
                         ('dogn', 'døgn')],
                default='time', max_length=8, verbose_name='Enhet'),
        ),
        migrations.AddField(
            model_name='backupplan',
            name='sist_sjekket_at',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Sist vurdert'),
        ),
        migrations.AddField(
            model_name='backupplan',
            name='sist_resultat',
            field=models.CharField(
                blank=True, default='', max_length=200,
                verbose_name='Siste resultat'),
        ),
        migrations.AlterField(
            model_name='backupplan',
            name='slug',
            field=models.CharField(
                help_text='Modul-slug, «full» for hele databasen, eller '
                          '«standard» for malen.',
                max_length=64, unique=True, verbose_name='Slug'),
        ),
        migrations.AlterField(
            model_name='backupplan',
            name='behold',
            field=models.PositiveIntegerField(
                default=50, validators=[MinValueValidator(1)],
                help_text='Eldste filer på Railway-volumet slettes når '
                          'antallet overstiges. Gjelder ikke kopiene hos '
                          'Scaleway — de styres av bucketens livssyklusregel. '
                          'Pre-restore-snapshots telles ikke.',
                verbose_name='Behold filer'),
        ),
        migrations.AlterField(
            model_name='backupplan',
            name='sist_fil_at',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Siste fil'),
        ),
        migrations.AlterModelOptions(
            name='backupplan',
            options={'ordering': ['slug'],
                     'verbose_name': 'Backupplan',
                     'verbose_name_plural': 'Backupplaner'},
        ),
    ]
