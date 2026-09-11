"""To felt fra prosjektleders runde 11. sep. 2026.

`Statusmelding.sted` — hvor bilen dro ved «Avreist». `Oppdrag.grovsortering`
— bilens Rød/Gul/Grønn, ved siden av KO/AMKs hastegrad. Begge er tomme
strenger som standard; ingen rad endres, og ingen data skrives, så
migrasjonen har intet dataskritt og trenger ingen prøve.

Arkivets payload (`oppdrag/arkiv.py`) tar ikke feltene med — signaturene på
eksisterende arkiver i prod skal verifisere som før.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("oppdrag", "0008_arkiv"),
    ]

    operations = [
        migrations.AddField(
            model_name="oppdrag",
            name="grovsortering",
            field=models.CharField(
                blank=True,
                choices=[("rod", "Rød"), ("gul", "Gul"), ("gronn", "Grønn")],
                default="",
                max_length=8,
                verbose_name="Grovsortering",
            ),
        ),
        migrations.AddField(
            model_name="statusmelding",
            name="sted",
            field=models.CharField(
                blank=True,
                choices=[
                    ("samleplass", "Samleplass"),
                    ("skadepol", "Skadepol"),
                    ("legevakt", "Legevakt"),
                    ("sykehus", "Sykehus"),
                    ("annen_ambulanse", "Annen ambulanse"),
                    ("annet", "Annet sted"),
                ],
                default="",
                max_length=20,
                verbose_name="Avreist til",
            ),
        ),
    ]
