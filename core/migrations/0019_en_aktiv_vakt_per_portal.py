"""Portalene, del 3 av 3: databasen håndhever én aktiv vakt per portal (17. okt. 2026).

Egen migrasjon etter dataene i 0018, så indeksen bygges over rader der regelen
alt holder, i en egen transaksjon.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_vaktportal_standard'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='vakt',
            constraint=models.UniqueConstraint(
                condition=models.Q(('er_aktiv', True)),
                fields=('portal',),
                name='en_aktiv_vakt_per_portal',
            ),
        ),
    ]
