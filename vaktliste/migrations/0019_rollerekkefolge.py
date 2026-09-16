"""Rollene får en rekkefølge (André, 16. sep. 2026, pulje 3 punkt 6).

**Skjema først, data etterpå — og det er den trygge retningen.** Regelen i
`CLAUDE.md` gjelder migrasjoner som *skriver rader og deretter endrer skjema*:
PostgreSQLs utsatte fremmednøkler legger en hendelse i kø ved hver skriving, og
`ALTER TABLE` på en tabell med hendelser i køen avvises. Her kommer `AddField`
først og skrivingen sist, så køen tømmes av committen og det finnes ingen
`ALTER TABLE` etter den. Derfor trengs verken `SET CONSTRAINTS ALL IMMEDIATE`
eller `atomic = False`.

Dataskrittet gir hver rolle et distinkt tall i sin gruppes rekkefølge, spredt
med ti. Uten det står alle på 100, og den første omsorteringen ville måttet
finne på verdier for hele lista. Utgangspunktet er dagens rekkefølge —
alfabetisk — så ingenting *flytter* seg av migrasjonen; den gjør bare
rekkefølgen til noe som kan endres.
"""

import django.db.models.functions.text
from django.db import migrations, models


def spre_rekkefolgen(apps, schema_editor):
    Ressursrolle = apps.get_model("vaktliste", "Ressursrolle")
    per_gruppe = {}
    # Sortert som i dag: gruppe, så navn. `order_by` her og ikke Meta —
    # historiske modeller bærer ikke `Lower`, og små/store bokstaver skal
    # ikke avgjøre hvem som får 10 og hvem som får 20.
    for rolle in Ressursrolle.objects.order_by("gruppe_id", "navn"):
        n = per_gruppe.get(rolle.gruppe_id, 0) + 1
        per_gruppe[rolle.gruppe_id] = n
        rolle.rekkefolge = n * 10
        rolle.save(update_fields=["rekkefolge"])


def tilbake(apps, schema_editor):
    """Ingenting å gjøre — feltet fjernes av `AddField` sin reverse."""


class Migration(migrations.Migration):

    dependencies = [
        ("vaktliste", "0018_vaktliste_timetak"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="ressursrolle",
            options={
                "ordering": [
                    "gruppe__rekkefolge",
                    "rekkefolge",
                    django.db.models.functions.text.Lower("navn"),
                ],
                "verbose_name": "Ressursrolle",
                "verbose_name_plural": "Ressursroller",
            },
        ),
        migrations.AddField(
            model_name="ressursrolle",
            name="rekkefolge",
            field=models.IntegerField(
                default=100,
                help_text="Styrer rekkefølgen i nedtrekket. Settes automatisk til opprettelsesrekkefølgen.",
                verbose_name="Rekkefølge",
            ),
        ),
        migrations.RunPython(spre_rekkefolgen, tilbake),
    ]
