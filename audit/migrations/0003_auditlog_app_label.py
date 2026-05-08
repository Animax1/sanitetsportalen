"""Legg til app_label på AuditLog (Fase 3a).

Endringer:
1. Nytt felt ``app_label`` (CharField, indeksert).
2. Data-migrering som backfiller ``app_label`` for eksisterende rader basert
   på ``table_name``-prefikset:
   - ``patients_*``  → ``patients``
   - ``backup``      → ``patients``  (backup-funksjonen er en del av patients-modulen)
   - ``accounts_*``  → ``accounts``
   - ``audit_*``     → ``audit``
   - alt annet       → tom streng (vises som "Ukjent" i admin-filter)
3. Ny composite-index ``(app_label, created_at)`` for raske rapportspørringer.
"""
from django.db import migrations, models


# Eksplisitt mapping for table_names som ikke følger app_<modell>-mønsteret.
EKSPLISITT_MAPPING = {
    'backup': 'patients',
}


def _utled_app_label(table_name: str) -> str:
    """Utled app_label fra table_name. Holdes synkronisert med audit/signals.py."""
    if not table_name:
        return ''
    if table_name in EKSPLISITT_MAPPING:
        return EKSPLISITT_MAPPING[table_name]
    if '_' in table_name:
        return table_name.split('_', 1)[0]
    # Tabellnavn uten understrek: anta at hele navnet er app-label.
    return table_name


def backfill_app_label(apps, schema_editor):
    """Sett app_label på eksisterende rader basert på table_name."""
    AuditLog = apps.get_model('audit', 'AuditLog')

    # Iterer over distincte table_names og oppdater bulk per gruppe — billigere
    # enn å iterere rad-for-rad i prod (kan være titusener av rader).
    distinkt_tabeller = AuditLog.objects.values_list('table_name', flat=True).distinct()
    for tabell in distinkt_tabeller:
        label = _utled_app_label(tabell)
        AuditLog.objects.filter(table_name=tabell, app_label='').update(app_label=label)


def reverser_backfill(apps, schema_editor):
    """Reverser ved å sette app_label tilbake til tom streng."""
    AuditLog = apps.get_model('audit', 'AuditLog')
    AuditLog.objects.update(app_label='')


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0002_rename_audit_auditlog_table_rec_idx_audit_audit_table_n_dc0494_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='app_label',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text=(
                    'Django app-label modulen tilhører (eks. "patients", '
                    '"accounts"). Fylles automatisk fra table_name hvis ikke '
                    'satt eksplisitt.'
                ),
                max_length=64,
                verbose_name='App / modul',
            ),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(
                fields=['app_label', 'created_at'],
                name='audit_audit_app_lab_dbf1e6_idx',
            ),
        ),
        migrations.RunPython(backfill_app_label, reverse_code=reverser_backfill),
    ]
