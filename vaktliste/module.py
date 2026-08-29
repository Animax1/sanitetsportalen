"""Modul-deklarasjon for vaktliste-appen.

Vaktlista: hvem som er på vakt, hvor, og når. Se
``docs/BESLUTNING_VAKTLISTE.md``.

Modulen sto med ``url=None`` og begge ``show_*``-flagg av gjennom fase 1 —
samme regel som oppdragsmodulen fulgte: et modulkort som fører til 404 er en
knapp som fører til en vegg. Fra fase 2 finnes siden, og flaggene er på.

``admin_only`` sto på gjennom fase 2 og er **av fra fase 3**: objektsjekkene
som gir nivåene mening — badgen og reservasjonen — håndheves nå på hvert
endepunkt (`services.kan_sette_vaktpost` m.fl.). Fram til de fantes, ville et
nivå som slapp inn gitt korps-brukeren tilgang til *alle* korps.

**`nivaa_navn` er ikke pynt.** `skriv_handling` betyr noe annet her enn i
oppdragsmodulen: der er det «navngitte stemplinger», her er det «fører sitt
eget korps» — redigering avgrenset av badgen `Mannskap.korps`, uten
innsjekk-stempling. Uten en egen etikett ville matrisen vist «Skrive:
handling» begge steder, og nivået blitt delt ut i god tro med feil
forventning. Se §4.5 i notatet.
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
    admin_only=False,       # åpnet i fase 3, se over
    is_core=False,
    order=115,              # mellom statistikk (110) og oppdrag (120)
    show_in_nav=True,
    show_in_dashboard=True,
    nivaaer=('les', 'skriv_handling', 'skriv_full'),
    nivaa_navn=(
        ('les', 'Lese — hele lista, alle korps'),
        ('skriv_handling', 'Skrive: eget korps'),
        ('skriv_full', 'Skrive: alle korps'),
    ),
)
