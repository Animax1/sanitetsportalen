"""Modul-deklarasjon for vaktliste-appen.

Vaktlista: hvem som er på vakt, hvor, og når. Se
``docs/BESLUTNING_VAKTLISTE.md``.

Modulen sto med ``url=None`` og begge ``show_*``-flagg av gjennom fase 1 —
samme regel som oppdragsmodulen fulgte: et modulkort som fører til 404 er en
knapp som fører til en vegg. Fra fase 2 finnes siden, og flaggene er på.

``admin_only=True`` gjennom fase 2: nivåene er deklarert, men objektsjekkene
som gir dem mening — badgen og reservasjonen — kommer i fase 3. Å slippe inn
`skriv_handling` før korps-regelen finnes, ville gitt korps-brukeren tilgang
til *alle* korps. Fail-closed er riktigere enn halvt håndhevet, og flagget
slås av når fase 3 håndhever reglene.

Nivåene deklareres allerede nå fordi de er en del av beslutningen (§4 i
notatet), men merk at de betyr noe annet her enn i oppdragsmodulen:
`skriv_handling` er «fører sitt eget korps» — redigering avgrenset av badgen
`Mannskap.korps`, uten innsjekk-stempling. Objektsjekkene som håndhever det
kommer i fase 3; fram til da finnes ingen endepunkter å håndheve dem på.
"""
from core.modules import Module


VaktlisteModule = Module(
    slug='vaktliste',
    name='Vaktliste',
    description=(
        'Personell og bemanning: mannskapsregister, vaktoppsett per ressurs, '
        'innsjekk og tilstedeoversikt.'
    ),
    url='/vaktliste/',
    icon='people',
    admin_only=True,        # til fase 3, se over
    is_core=False,
    order=115,              # mellom statistikk (110) og oppdrag (120)
    show_in_nav=True,
    show_in_dashboard=True,
    nivaaer=('les', 'skriv_handling', 'skriv_full'),
)
