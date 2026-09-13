"""Backupplan, steg 3 av 3: de gamle feltene ut.

`enabled` og `interval_minutes` er lest av `0009` og har ingen lesere igjen.
Se docstringen i `0008` for hvorfor dette ikke står i samme migrasjon som
skrivingen.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_backupplan_data'),
    ]

    operations = [
        migrations.RemoveField(model_name='backupplan', name='enabled'),
        migrations.RemoveField(model_name='backupplan', name='interval_minutes'),
    ]
