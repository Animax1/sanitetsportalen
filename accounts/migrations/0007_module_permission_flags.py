"""Legger til 5 modul-permission-flagg på CustomUser (Fase 3a).

Pre-registrerer alle flagg som planen i SANITETSPORTAL_PLAN.md §3 spesifiserer,
i én migrasjon, slik at vi slipper fragmenterte migrasjoner når framtidige
moduler aktiveres.

Eksisterende brukere får alle flagg = False som default. For ``role='admin'``
brukere kjører vi en data-migrering som aktiverer alle flagg, slik at admins
ikke trenger å re-konfigurere seg selv etter migrasjon. (Admin har uansett
bypass i ``Module.is_visible_for``, men data-migreringen sikrer at admins
også fungerer riktig hvis bypass-logikken senere endres.)
"""
from django.db import migrations, models


def aktivere_alle_flagg_for_admins(apps, schema_editor):
    """Sett alle modul-flagg til True for eksisterende admin-brukere."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(role='admin').update(
        kan_redigere_pasienter=True,
        kan_redigere_vakter=True,
        kan_redigere_utstyr=True,
        kan_se_rapport=True,
        kan_redigere_beredskap=True,
    )


def reverser_admin_flagg(apps, schema_editor):
    """Rollback: sett alle flagg tilbake til False for admins."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(role='admin').update(
        kan_redigere_pasienter=False,
        kan_redigere_vakter=False,
        kan_redigere_utstyr=False,
        kan_se_rapport=False,
        kan_redigere_beredskap=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_customuser_groups_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='kan_redigere_pasienter',
            field=models.BooleanField(
                default=False,
                help_text='Gir tilgang til /pasienter/-modulen i dashboard og nav-meny.',
                verbose_name='Kan se pasientregistrering',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='kan_redigere_vakter',
            field=models.BooleanField(
                default=False,
                help_text='Reservert for fremtidig vakt-administrasjon (planlagt).',
                verbose_name='Kan se vakt-modulen',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='kan_redigere_utstyr',
            field=models.BooleanField(
                default=False,
                help_text='Reservert for fremtidig utstyrs-/lager-modul (planlagt).',
                verbose_name='Kan se utstyr-modulen',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='kan_se_rapport',
            field=models.BooleanField(
                default=False,
                help_text='Reservert for fremtidig rapport-/statistikk-modul (planlagt).',
                verbose_name='Kan se rapport-modulen',
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='kan_redigere_beredskap',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Reservert for fremtidig beredskap-/ambulanse-modul (planlagt). '
                    'Krever egen GDPR-vurdering før aktivering.'
                ),
                verbose_name='Kan se beredskap-modulen',
            ),
        ),
        migrations.RunPython(
            aktivere_alle_flagg_for_admins,
            reverse_code=reverser_admin_flagg,
        ),
    ]
