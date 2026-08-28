"""Deploy 3 (§8): de fem ``kan_redigere_*``-flaggene fjernes.

Flaggene kom med Fase 3a og skulle styre hvilke moduler brukeren så i
dashboard og nav-meny. De gjorde det aldri på en måte som betydde noe: ingen
view leste dem (§2.1), og etter at ``Module.is_visible_for`` gikk over til
``ModulTilgang`` i deploy 1 gjorde de ingenting i det hele tatt.

**Hvorfor de fikk stå gjennom deploy 1 og 2.** En rollback av deploy 1 må
kunne bygge matrisen fra noe, og backfillen leser ``role``. Så lenge både
``role`` og flaggene sto urørt, fantes fasiten. Deploy 2 krympet ``role``, og
med det lukket vinduet uansett — derfor er det først nå kolonnene kan gå.

**Reverserbar, men tom.** Django gjenskaper feltene med ``default=False`` ved
en rollback. Verdiene som lå der er borte, og det er greit: de betydde
ingenting. Tilgangen ligger i ``ModulTilgang``, som denne migrasjonen ikke
rører.

Én bivirkning verdt å kjenne til: kortet «Modul-tilganger» på ``/min-profil/``
leste disse flaggene fram til nå, og viste «Nei» til brukere som faktisk hadde
tilgang — backfillen rørte flagget med vilje (§8.1). Kortet er skrevet om til å
lese ``ModulTilgang`` i samme deploy. Uten den endringen ville denne
migrasjonen tatt ned siden.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_krymp_role'),
    ]

    operations = [
        migrations.RemoveField(model_name='customuser', name='kan_redigere_pasienter'),
        migrations.RemoveField(model_name='customuser', name='kan_redigere_vakter'),
        migrations.RemoveField(model_name='customuser', name='kan_redigere_utstyr'),
        migrations.RemoveField(model_name='customuser', name='kan_se_rapport'),
        migrations.RemoveField(model_name='customuser', name='kan_redigere_beredskap'),
    ]
