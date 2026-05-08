"""Fase 4: Legg til module_slug på Backup + tilhørende indeks."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0006_vaktarkiv'),
    ]

    operations = [
        migrations.AddField(
            model_name='backup',
            name='module_slug',
            field=models.CharField(
                db_index=True,
                default='patients',
                help_text=(
                    'Hvilken modul backupen tilhører. Brukes av core.backup '
                    'for per-modul-cap og restore-rutting.'
                ),
                max_length=64,
            ),
        ),
        migrations.AddIndex(
            model_name='backup',
            index=models.Index(
                fields=['module_slug', '-created_at'],
                name='backup_module_created_idx',
            ),
        ),
    ]
