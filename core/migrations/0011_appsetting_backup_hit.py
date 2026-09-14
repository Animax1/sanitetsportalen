"""`AppSetting` og `Backup` flytter fra `patients` til `core` — steg 1 av 2.

Ingen SQL. `SeparateDatabaseAndState` med tom `database_operations` sier til
Django: «modellen bor nå her», uten å røre databasen. Tabellene heter fortsatt
`patients_appsetting` og `patients_backup`, bundet med `db_table` i modellen —
se kommentaren der for hvorfor de ikke døpes om.

**Denne må kjøre før `patients/0018`**, som fjerner modellene fra pasientappens
tilstand. Motsatt rekkefølge ville latt Django se et øyeblikk der tabellen ikke
tilhører noen modell, og `Backup.created_by` ville mistet fremmednøkkelen sin
i tilstanden. Avhengigheten står i `patients/0018`, ikke her.

Ser du en `CreateModel` som lager tabeller i en base der de alt finnes, er det
verdt å lese `database_operations=[]` en gang til: den er tom, og det er hele
poenget.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_backupplan_rydd'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        # Tabellene er laget av pasientappen. Uten denne kan Django kjøre
        # tilstandsendringen før de finnes i grafen.
        ('patients', '0017_slett_backupconfig'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='AppSetting',
                    fields=[
                        ('key', models.CharField(max_length=64, primary_key=True,
                                                 serialize=False, verbose_name='Nøkkel')),
                        ('value', models.TextField(verbose_name='Verdi')),
                    ],
                    options={
                        'verbose_name': 'Appinnstilling',
                        'verbose_name_plural': 'Appinnstillinger',
                        'db_table': 'patients_appsetting',
                    },
                ),
                migrations.CreateModel(
                    name='Backup',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                                   serialize=False, verbose_name='ID')),
                        ('filename', models.CharField(max_length=255, unique=True)),
                        ('kind', models.CharField(choices=[
                            ('auto', 'Automatisk'), ('manual', 'Manuell'),
                            ('pre_restore', 'Før gjenoppretting'),
                            ('pre_reset', 'Før nullstilling av år')], max_length=20)),
                        ('size_bytes', models.BigIntegerField()),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('note', models.CharField(blank=True, default='', max_length=200)),
                        ('content_hash', models.CharField(
                            blank=True, default='',
                            help_text='SHA256 over ukomprimert JSON-innhold. '
                                      'Brukes til å hoppe over identiske auto-backups.',
                            max_length=64)),
                        ('module_slug', models.CharField(
                            db_index=True, default='patients',
                            help_text='Hvilken modul backupen tilhører. Brukes av '
                                      'core.backup for per-modul-cap og restore-rutting.',
                            max_length=64)),
                        ('created_by', models.ForeignKey(
                            blank=True, null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name='backups_created',
                            to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'ordering': ['-created_at'],
                        'db_table': 'patients_backup',
                        'indexes': [
                            models.Index(fields=['kind', '-created_at'],
                                         name='backup_kind_created_idx'),
                            models.Index(fields=['module_slug', '-created_at'],
                                         name='backup_module_created_idx'),
                        ],
                    },
                ),
            ],
        ),
    ]
