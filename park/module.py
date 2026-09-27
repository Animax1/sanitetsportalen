"""Modul-deklarasjon for park-modulen — lagets utfallsregistrering.

Se `docs/FORSLAG_PARK.md`. Lagene registrerer **uten konto**, gjennom én lenke
i et tiltakskort (B3); nivåene under gjelder bare de innloggede flatene.

**To nivåer, og det er alt modulen trenger** (André, 27. sep. 2026, B2):

| Nivå | Hva det gir |
|---|---|
| `les` | Fanen «Lag» i `/statistikk/` (pulje 3). Ingen egen side |
| `skriv_leder` | Setter opp lenkene og problemstillingene, sletter feilregistreringer |

Global admin har i tillegg utfallene (B7) og bryterne i portalinnstillingene.
`skriv_handling` og `skriv_full` er hoppet over: registreringen skjer uten
konto, så det finnes ingen innlogget skriving mellom å lese og å sette opp.
"""
from core.modules import Module


ParkModule = Module(
    slug='park',
    name='Park',
    description=(
        'Lagenes registrering av hva de har gjort ute: problemstilling, '
        'sted og utfall — uten innlogging, via lenke i tiltakskortet.'
    ),
    url='/park/',
    icon='tree',
    admin_only=False,
    is_core=False,
    order=130,              # etter KO (125): lagene ute, etter kommandoplassen
    show_in_nav=True,
    show_in_dashboard=True,
    nivaaer=('les', 'skriv_leder'),
    nivaa_navn=(
        ('les', 'Lese: ser tallene i statistikken'),
        ('skriv_leder', 'Leder: setter opp lenker og lister, sletter feilregistreringer'),
    ),
)
