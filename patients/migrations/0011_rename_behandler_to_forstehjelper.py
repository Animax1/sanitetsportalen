import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0010_remove_patient_helsepersonell'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Behandler',
            new_name='Forstehjelper',
        ),
        migrations.RenameField(
            model_name='patient',
            old_name='behandler',
            new_name='forstehjelper',
        ),
        migrations.RenameField(
            model_name='arkivertpasient',
            old_name='behandler_navn',
            new_name='forstehjelper_navn',
        ),
        migrations.AlterField(
            model_name='forstehjelper',
            name='user',
            field=models.OneToOneField(
                blank=True,
                help_text='Valgfri kobling til en portalbruker. Hvis satt, kan brukeren filtrere egne pasienter og får varsel ved tildeling.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='forstehjelper_profil',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Koblet bruker',
            ),
        ),
        migrations.AlterModelOptions(
            name='forstehjelper',
            options={
                'ordering': ['-is_active', 'name'],
                'verbose_name': 'Førstehjelper',
                'verbose_name_plural': 'Forstehjelpere',
            },
        ),
        migrations.AlterField(
            model_name='patient',
            name='forstehjelper',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='patients',
                to='patients.forstehjelper',
                verbose_name='Førstehjelper',
            ),
        ),
        migrations.AlterField(
            model_name='arkivertpasient',
            name='forstehjelper_navn',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                verbose_name='Førstehjelper (navn)',
            ),
        ),
    ]
