"""Legg til mfa_required-felt på CustomUser og event_type på LoginEvent.

Data-migrasjon: Sett mfa_required=True for admin og lead-brukere.
"""
from django.db import migrations, models


def set_mfa_required_for_privileged_roles(apps, schema_editor):
    """Sett mfa_required=True for alle brukere med admin- eller lead-rolle."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(role__in=('admin', 'lead')).update(mfa_required=True)


def reverse_mfa_required(apps, schema_editor):
    """Nullstill mfa_required til False for alle brukere (reversibel migrasjon)."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(mfa_required=True).update(mfa_required=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_add_lead_view_role'),
    ]

    operations = [
        # Legg til mfa_required på CustomUser
        migrations.AddField(
            model_name='customuser',
            name='mfa_required',
            field=models.BooleanField(
                default=False,
                verbose_name='Krev MFA',
                help_text='Krev to-faktor-autentisering ved pålogging',
            ),
        ),
        # Legg til event_type på LoginEvent
        migrations.AddField(
            model_name='loginevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('login', 'Innlogging'),
                    ('mfa_setup_completed', 'MFA-oppsett fullført'),
                    ('mfa_verify_success', 'MFA-verifisering vellykket'),
                    ('mfa_verify_failed', 'MFA-verifisering feilet'),
                    ('mfa_backup_used', 'MFA backup-kode brukt'),
                    ('mfa_trust_cookie_used', 'MFA trust-cookie brukt'),
                    ('mfa_reset_by_admin', 'MFA nullstilt av admin'),
                ],
                default='login',
                max_length=30,
                verbose_name='Hendelsestype',
            ),
        ),
        # Data-migrasjon: sett mfa_required for privilegerte roller
        migrations.RunPython(
            set_mfa_required_for_privileged_roles,
            reverse_code=reverse_mfa_required,
        ),
    ]
