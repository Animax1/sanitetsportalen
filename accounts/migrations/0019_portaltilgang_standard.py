"""Portaltilgangene, del 2 av 2: alle kontoer blir medlem av «Standard» (17. okt. 2026).

Alt som finnes hører til ett miljø, så hver konto som kan noe i dag får et
medlemskap der — ellers ville de vært foreldreløse etter deployen: innlogget,
men uten en portal å stå i.

- **Hver konto med modulrader** får medlemskap, og radene kobles til det.
  Det gjelder også en global admin som har rader: de må høre til noe.
- **Hver aktiv konto uten admin-rolle** får medlemskap, også uten rader — en
  bilkonto eller en ny konto som ennå ikke har fått tilgang skal stå i
  portalen, ikke utenfor den.
- **Ingen blir moderator.** Det deler admin ut.

Global admin uten rader trenger ingen medlemskap: hun ser alle portaler.
"""
from django.db import migrations


def fyll(apps, schema_editor):
    Vaktportal = apps.get_model('core', 'Vaktportal')
    Portaltilgang = apps.get_model('accounts', 'Portaltilgang')
    ModulTilgang = apps.get_model('accounts', 'ModulTilgang')
    CustomUser = apps.get_model('accounts', 'CustomUser')

    portal, _ = Vaktportal.objects.get_or_create(
        slug='standard', defaults={'navn': 'Standard'})

    med_rader = set(ModulTilgang.objects.values_list('bruker_id', flat=True))
    aktive = set(CustomUser.objects.filter(is_active=True).exclude(role='admin')
                 .values_list('pk', flat=True))
    for bruker_id in sorted(med_rader | aktive):
        tilgang, _ = Portaltilgang.objects.get_or_create(
            bruker_id=bruker_id, portal=portal, defaults={'rolle': 'medlem'})
        ModulTilgang.objects.filter(bruker_id=bruker_id, portaltilgang__isnull=True).update(
            portaltilgang=tilgang)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_portaltilgang'),
        ('core', '0018_vaktportal_standard'),
    ]

    operations = [
        migrations.RunPython(fyll, migrations.RunPython.noop),
    ]
