from django.db import migrations, models


def teknisk_blir_drift(apps, schema_editor):
    """Hastegraden het «Teknisk» i noen timer 12. sep. 2026 før den ble
    «Drift». Rader fra staging rettes; prod har ingen. Skjemaendringen over
    er bare Python-valg og sender ingen SQL, så triggerkøen er tom."""
    Oppdrag = apps.get_model('oppdrag', 'Oppdrag')
    Oppdrag.objects.filter(hastegrad='Teknisk').update(hastegrad='Drift')
    Oppdrag.objects.filter(problemstilling='Annet teknisk').update(problemstilling='Annet')
    ArkivertOppdrag = apps.get_model('oppdrag', 'ArkivertOppdrag')
    ArkivertOppdrag.objects.filter(hastegrad='Teknisk').update(hastegrad='Drift')


class Migration(migrations.Migration):
    dependencies = [
        ("oppdrag", "0016_trenger_ressurs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="oppdrag",
            name="hastegrad",
            field=models.CharField(
                choices=[("Akutt", "Akutt"), ("Haster", "Haster"), ("Vanlig", "Vanlig"),
                         ("Drift", "Drift")],
                max_length=16, verbose_name="Hastegrad"),
        ),
        migrations.RunPython(teknisk_blir_drift, migrations.RunPython.noop),
    ]
