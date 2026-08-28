"""Hjelpere for tester som trenger brukere med modultilgang.

Modulen heter bevisst *ikke* ``tests_*`` — den inneholder ingen tester selv, og
skal ikke plukkes opp av Djangos testoppdagelse.

Bakgrunn: etter at ``@modul_kreves`` ble håndhevet, er en bruker uten
``ModulTilgang``-rader stengt ute av modulen. I produksjon er det en
kanttilstand, ikke normalen: brukerne som fantes fikk rader av migrasjonen, og
nye får dem av matrisen på opprettingsskjemaet. En test som lager en bruker
uten rader modellerer altså noe som knapt finnes.

``gi_standardtilgang`` gir brukeren nøyaktig radene backfillen ville gitt den,
ut fra rollen. Kartleggingen er den samme som i
``accounts/migrations/0012_fyll_modultilgang.py`` — den er gjentatt her fordi
en test som importerer migrasjonen ville bundet seg til et filnavn som endrer
seg, men avviket er verdt å kjenne til: endres §8.1, må begge steder følge.
``BackfillTests`` leser migrasjonen direkte og er fasiten.
"""
from accounts.models import ModulTilgang

STANDARDTILGANG = {
    'read_only':  [('patients', 'les')],
    'read_write': [('patients', 'skriv_full')],
    'lead_view':  [('patients', 'les'),        ('statistikk', 'les')],
    'lead':       [('patients', 'skriv_full'), ('statistikk', 'les')],
    'admin':      [],   # global admin trenger ingen rader
}


def gi_standardtilgang(bruker):
    """Gi brukeren radene backfillen ville gitt den. Returnerer brukeren.

    Idempotent, så den kan kalles om igjen uten å duplisere.
    """
    for slug, nivaa in STANDARDTILGANG.get(getattr(bruker, 'role', ''), []):
        ModulTilgang.objects.update_or_create(
            bruker=bruker, modul_slug=slug, defaults={'nivaa': nivaa},
        )
    return bruker
