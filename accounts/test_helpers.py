"""Hjelpere for tester som trenger brukere med modultilgang.

Modulen heter bevisst *ikke* ``tests_*`` — den inneholder ingen tester selv, og
skal ikke plukkes opp av Djangos testoppdagelse.

Bakgrunn: etter at ``@modul_kreves`` ble håndhevet, er en bruker uten
``ModulTilgang``-rader stengt ute av modulen. I produksjon er det en
kanttilstand, ikke normalen: brukerne som fantes fikk rader av migrasjonen, og
nye får dem av matrisen på opprettingsskjemaet. En test som lager en bruker
uten rader modellerer altså noe som knapt finnes.

**Profilen oppgis eksplisitt.** Fram til deploy 2 leste hjelperen ``bruker.role``
og slo opp radene backfillen ville gitt. Det gikk så lenge rollen *var* en
tilgangsverdi. Nå er `role` krympet til ``admin``/``bruker``, og en oppslag på
rollen ville gitt alle testbrukere det samme — nemlig ingenting. Testene sier
derfor hva kontoen skal kunne, ikke hva den het:

    gi_standardtilgang(bruker, 'skriver')

Navnene beskriver tilgang, ikke de gamle rollene. `leder_les` er ikke «en
lead_view» — det er «leser pasienter, leser statistikk», som er den eneste
forskjellen den rollen noen gang gjorde.
"""
from accounts.models import ModulTilgang

#: Profil → radene profilen gir. Verdiene er de samme kombinasjonene
#: ``accounts/migrations/0012_fyll_modultilgang.py`` fylte tabellen med, slik at
#: testene fortsatt modellerer kontoer som faktisk finnes i prod.
PROFILER = {
    'leser':     [('patients', 'les')],
    'skriver':   [('patients', 'skriv_full')],
    'leder_les': [('patients', 'les'),        ('statistikk', 'les')],
    'leder':     [('patients', 'skriv_full'), ('statistikk', 'les')],
    'admin':     [],   # global admin trenger ingen rader
}


def gi_standardtilgang(bruker, profil):
    """Gi brukeren radene profilen beskriver. Returnerer brukeren.

    Idempotent, så den kan kalles om igjen uten å duplisere.

    Et ukjent profilnavn er en skrivefeil, ikke «ingen tilgang». Stille
    returnering hadde gjort testen grønn på feil grunnlag: brukeren ville
    manglet tilgang, endepunktet svart 403, og en test som *forventer* 403
    hadde bestått uten å teste noe.
    """
    if profil not in PROFILER:
        raise ValueError(
            f'Ukjent profil {profil!r}. Gyldige: {", ".join(sorted(PROFILER))}'
        )
    for slug, nivaa in PROFILER[profil]:
        ModulTilgang.objects.update_or_create(
            bruker=bruker, modul_slug=slug, defaults={'nivaa': nivaa},
        )
    return bruker
