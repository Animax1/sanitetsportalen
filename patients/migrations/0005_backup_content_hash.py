from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0004_backupconfig_backup'),
    ]

    operations = [
        migrations.AddField(
            model_name='backup',
            name='content_hash',
            field=models.CharField(
                blank=True,
                default='',
                help_text='SHA256 over ukomprimert JSON-innhold. Brukes til å hoppe over identiske auto-backups.',
                max_length=64,
            ),
        ),
        migrations.AddIndex(
            model_name='backup',
            index=models.Index(
                fields=['kind', '-created_at'],
                name='backup_kind_created_idx',
            ),
        ),
    ]
