"""Tilhørighetene, del 1: `vaktliste.Korps` blir `core.Tilhorighet` (17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.3. Samme grep som `core/0011` brukte for
`AppSetting`: **modellen flytter, tabellen blir stående.** `CreateModel` under
står i `SeparateDatabaseAndState` med tom `database_operations` — den sier til
Django «modellen bor nå her», og rører ikke `vaktliste_korps`. Ser du en
`CreateModel` mot en tabell som alt finnes, er det verdt å lese den linja en
gang til.

Det som **er** SQL:

- `type` på tabellen, med `db_default='korps'`: gammel kode i release-vinduet
  lager korps uten feltet, og hver rad som finnes er et korps.
- `Vaktportal.tilhorigheter` (M2M) og `Kontotilhorighet` — nye tabeller.

`vaktliste/0030` fjerner modellen fra vaktlistas tilstand og peker de fire
fremmednøklene hit; `vaktliste/0031` fyller dataene. Rekkefølgen er en regel:
uten denne først ville tilstanden et øyeblikk hatt fremmednøkler til en modell
ingen eier.
"""
import core.sortering
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_en_aktiv_vakt_per_portal'),
        ('vaktliste', '0029_kontokorps'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='Tilhorighet',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                                   serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(
                            auto_now_add=True, help_text='Tidspunktet raden ble opprettet.',
                            verbose_name='Opprettet')),
                        ('updated_at', models.DateTimeField(
                            auto_now=True, help_text='Tidspunktet raden sist ble endret.',
                            verbose_name='Sist oppdatert')),
                        ('navn', models.CharField(max_length=120, unique=True, verbose_name='Navn')),
                        ('kortnavn', models.CharField(
                            blank=True, default='',
                            help_text='Vises i trange kolonner, f.eks. «HGSD». Valgfritt.',
                            max_length=20, verbose_name='Kortnavn')),
                        ('er_aktiv', models.BooleanField(
                            default=True,
                            help_text='Inaktive korps skjules i nedtrekkslister, men beholdes '
                                      'på mannskapet som allerede tilhører dem.',
                            verbose_name='Aktiv')),
                    ],
                    options={
                        'verbose_name': 'Tilhørighet',
                        'verbose_name_plural': 'Tilhørigheter',
                        'db_table': 'vaktliste_korps',
                        'ordering': [core.sortering.Norsk('navn')],
                    },
                ),
            ],
        ),
        migrations.AddField(
            model_name='tilhorighet',
            name='type',
            field=models.CharField(
                choices=[('korps', 'Korps'), ('annet', 'Annet')], db_default='korps',
                default='korps',
                help_text='«Korps» står i vaktlista; «Annet» — som «Leger» — bare i brukerlistene.',
                max_length=16, verbose_name='Type'),
        ),
        migrations.AddField(
            model_name='vaktportal',
            name='tilhorigheter',
            field=models.ManyToManyField(blank=True, related_name='portaler',
                                         to='core.tilhorighet', verbose_name='Tilhørigheter'),
        ),
        migrations.CreateModel(
            name='Kontotilhorighet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('bruker', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='tilhorigheter',
                    to=settings.AUTH_USER_MODEL, verbose_name='Bruker')),
                ('tilhorighet', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name='kontoer_med',
                    to='core.tilhorighet', verbose_name='Tilhørighet')),
            ],
            options={
                'verbose_name': 'Kontoens tilhørighet',
                'verbose_name_plural': 'Kontoenes tilhørigheter',
                'constraints': [models.UniqueConstraint(fields=('bruker', 'tilhorighet'),
                                                        name='en_kontotilhorighet_per_par')],
            },
        ),
    ]
