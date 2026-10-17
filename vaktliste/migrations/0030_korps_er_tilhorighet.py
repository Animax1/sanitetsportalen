"""Tilhørighetene, del 2: korpset forlater vaktlistas tilstand (17. okt. 2026).

**Ingen SQL.** Fremmednøklene peker allerede på `vaktliste_korps`, og den
tabellen eier `core.Tilhorighet` nå (`core/0020`). Her flyttes bare Djangos
bilde av dem. **`DeleteModel` står i `state_operations` med vilje** — som en
vanlig operasjon ville den slettet tabellen med alle korpsene.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_tilhorighet'),
        ('vaktliste', '0029_kontokorps'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='kontokorps',
                    name='korps',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            related_name='kontoer', to='core.tilhorighet',
                                            verbose_name='Korps'),
                ),
                migrations.AlterField(
                    model_name='vaktpost',
                    name='korps',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='Korpset plassen er satt av til. Tom = arver ressursens '
                                  'reservasjon.',
                        null=True, on_delete=django.db.models.deletion.PROTECT,
                        related_name='reserverte_vaktposter', to='core.tilhorighet',
                        verbose_name='Reservert korps'),
                ),
                migrations.AlterField(
                    model_name='mannskap',
                    name='korps',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                            related_name='mannskap', to='core.tilhorighet',
                                            verbose_name='Korps'),
                ),
                migrations.AlterField(
                    model_name='ressurs',
                    name='korps',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='Korpset som har fått ressursen. Tom = ureservert, og '
                                  'bemannes da av vaktleder.',
                        null=True, on_delete=django.db.models.deletion.PROTECT,
                        related_name='reserverte_ressurser', to='core.tilhorighet',
                        verbose_name='Reservert korps'),
                ),
                migrations.DeleteModel(name='Korps'),
            ],
        ),
    ]
