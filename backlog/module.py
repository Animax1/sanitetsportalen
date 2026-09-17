"""Modul-deklarasjon for backlog-modulen.

Endringsønsker og bugs, ett innspill per rad, med et løst-flagg. Formålet er å
samle det som ellers ligger spredt i chatter — og det er også grunnen til at
modulen er liten: en backlog ingen gidder å skrive i, er en tom backlog.

**Tre nivåer, og de er André sine egne** (17. sep. 2026): lese, lese/skrive, og
lese/skrive full. Stigen i portalen har fem navn, så de tre må oversettes — og
oversettelsen bevarer rekkefølgen hans:

| Hans | Portalens | Hva den får gjøre |
|---|---|---|
| les | `les` | Ser lista og filtrene |
| les/skriv | `skriv_full` | Melder inn, og redigerer sitt eget innen fristen |
| les/skriv full | `skriv_leder` | Setter løst, gjenåpner, styrer typene |

`skriv_handling` er hoppet over med vilje. Nivået er «navngitte overganger som
**ikke leser request-kroppen**», og å melde inn et innspill er nettopp å lese
kroppen. Å bruke det her ville vært å dele ut et nivå med feil betydning i
hodet — som er den ene feilen `nivaa_navn` finnes for å hindre.

**Og etikettene er modulens egne.** `skriv_leder` betyr «setter opp vakta» i
vaktlista og «setter opp verdimengdene» i oppdrag; her betyr det «leder
backloggen — avgjør hva som er løst». Samme trinn på stigen, tre ulike
fullmakter, og det er hele poenget med `nivaa_navn` — se §4.5 i
vaktlistenotatet.

`LedernivaaetsPlassIStigenTests.MED_LEDER` i `vaktliste/tests_tilgang.py` er
lista over moduler som *har* forklart nivået. En modul som tar det i bruk uten
å stå der, blir rød — og det er meningen: et toppnivå ingen har definert
betydningen av, deles ut i god tro med feil modul i hodet.
"""
from core.modules import Module


BacklogModule = Module(
    slug='backlog',
    name='Backlog',
    description=(
        'Endringsønsker og bugs, ett innspill om gangen. Filtrerbar på type '
        'og om saken er løst.'
    ),
    url='/backlog/',
    icon='list-check',
    admin_only=False,
    is_core=False,
    # Sist i menyen. Modulen er et verktøy for dem som utvikler portalen, ikke
    # en flate man er innom under en vakt.
    order=200,
    show_in_nav=True,
    show_in_dashboard=True,
    nivaaer=('les', 'skriv_full', 'skriv_leder'),
    nivaa_navn=(
        ('les', 'Lese: ser backloggen'),
        ('skriv_full', 'Skrive: melder inn, redigerer sitt eget'),
        ('skriv_leder', 'Skrive full: leder backloggen, setter løst'),
    ),
)
