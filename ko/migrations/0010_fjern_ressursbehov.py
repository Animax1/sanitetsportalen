"""Skjemaet etter `0009`: de tre feltene som ble til tillegg og lag er
borte, og `Ressursbehov` med dem. Bare skjema — se `0008`."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ko", "0009_beskrivelse_til_tillegg"),
    ]

    operations = [
        migrations.RemoveField(model_name="hendelse", name="ressursbehov"),
        migrations.RemoveField(model_name="hendelse", name="beskrivelse"),
        migrations.RemoveField(model_name="hendelse", name="lagsressurser"),
        migrations.DeleteModel(name="Ressursbehov"),
    ]
