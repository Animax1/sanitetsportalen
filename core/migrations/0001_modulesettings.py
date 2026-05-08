"""Initial migrasjon for core-appen: oppretter ModuleSettings-tabellen.

Genererer raden for ``ModuleSettings`` som styrer hvilke moduler som er
aktive i sanitetsportalen. Kjøres som første migrasjon i ``core``.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ModuleSettings',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'slug',
                    models.CharField(
                        help_text='Matcher Module.slug i core.modules (ofte lik Django app-label).',
                        max_length=64,
                        unique=True,
                        verbose_name='Modul-slug',
                    ),
                ),
                (
                    'enabled',
                    models.BooleanField(
                        default=True,
                        help_text=(
                            'Hvis avkrysset vises modulen i dashboard og nav-meny for brukere '
                            'som har riktig permission-flagg. Kjernemoduler kan ikke deaktiveres.'
                        ),
                        verbose_name='Aktivert',
                    ),
                ),
                (
                    'backup_enabled',
                    models.BooleanField(
                        default=False,
                        help_text=(
                            'Reservert for fremtidig modul-styrt backup. Per Fase 3a har dette '
                            'feltet ingen effekt — backup styres fortsatt av BACKUP_APPS i kode. '
                            'Settes opp i en senere fase.'
                        ),
                        verbose_name='Inkluder i backup',
                    ),
                ),
                (
                    'note',
                    models.CharField(
                        blank=True,
                        default='',
                        help_text='Valgfri kommentar — f.eks. årsak til at modulen er deaktivert.',
                        max_length=255,
                        verbose_name='Admin-notat',
                    ),
                ),
                (
                    'updated_at',
                    models.DateTimeField(auto_now=True, verbose_name='Sist endret'),
                ),
                (
                    'updated_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name='+',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Sist endret av',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Modulinnstilling',
                'verbose_name_plural': 'Modulinnstillinger',
                'ordering': ['slug'],
            },
        ),
    ]
