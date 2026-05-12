"""Auto-generert migrasjon for Django 5-oppgradering (omdøping av indeks-navn).

Denne ligger i GitHub-repoet og deployeres derfra — den følger IKKE med i
Fase 3-zip-en, men eksisterer i workspace slik at lokal test-suite kjører.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0001_initial'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='auditlog',
            new_name='audit_audit_table_n_dc0494_idx',
            old_name='audit_auditlog_table_rec_idx',
        ),
        migrations.RenameIndex(
            model_name='auditlog',
            new_name='audit_audit_created_a3c1b8_idx',
            old_name='audit_auditlog_created_idx',
        ),
    ]
