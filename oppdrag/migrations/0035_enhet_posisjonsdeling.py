"""Hvem deler posisjon (André, 4. okt. 2026): tilstanden bilskjermen melder,
som nåtilstand på enheten. Bare skjema — ingen dataskritt, så triggerkøen i
PostgreSQL er ikke i spill (se «Migrasjoner» i rota).

Standardverdien `ukjent` er riktig for alle eksisterende rader: ingen bil har
meldt noe ennå, og kortet skal si nettopp det.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('oppdrag', '0034_frosset_statistikk_uten_fritekst'),
    ]

    operations = [
        migrations.AddField(
            model_name='enhet',
            name='posisjonsdeling',
            field=models.CharField(
                choices=[('ukjent', 'Ikke hørt fra bilskjermen'), ('deler', 'Deler posisjon'),
                         ('av', 'Slått av på bilskjermen'), ('nektet', 'Nettleseren har nektet'),
                         ('utilgjengelig', 'Ingen GPS på enheten')],
                default='ukjent', max_length=16, verbose_name='Deler posisjon'),
        ),
        migrations.AddField(
            model_name='enhet',
            name='posisjonsdeling_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Posisjonsdeling sist endret'),
        ),
    ]
