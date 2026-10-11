"""Hvilket miljø portalen kjører i — og merket som sier det (11. okt. 2026).

Utløst 29. aug. 2026: en arbeidsøkt gikk med til å feilsøke en innlogging som
feilet fordi forsøkene gikk mot prod mens kontoen lå på staging. Under en vakt er
innsatsen høyere: forskjellen er om en pasient registreres i den ekte basen
eller i en testbase.

**`PORTAL_MILJO` er en lukket liste, og den er ikke Railways miljønavn**
(André, 11. okt. 2026). Kjører en dag flere korps hver sin instans, kan prod for
ett av dem hete noe helt annet enn `production` i Railway — navnet på miljøet og
*hva slags* miljø det er, er to ting. Typen settes eksplisitt per tjeneste.

| Verdi | Merke | Fanen |
|---|---|---|
| `drift` | ingen — prod er den nøytrale tilstanden | som før |
| `test` | TESTMILJØ, lilla striper | `[TEST] …` |
| `utvikling` | UTVIKLING, turkis striper | `[UTV] …` |
| mangler eller ugyldig | UKJENT MILJØ, grå striper | `[?] …` |

**Ingen alias** (`production`, `staging`): hver ekstra stavemåte er en ny vei til
feil tolkning, og en skrivefeil skal gi et synlig merke. **Ingen stopp ved
oppstart** heller, slik `DATABASE_URL` har: en skrivefeil skal ikke ta ned prod
midt i en vakt. Merket, en rød rad på server-status og en advarsel i loggen er
nok til at den blir sett.

Utenfor Railway er standarden `utvikling` (`settings.PORTAL_MILJO`); på Railway
uten variabelen er det ukjent. Fargene overlapper ikke admins statusmelding
(grønn, gul, oransje, rød — `core/statusmelding.py`), så et miljømerke kan aldri
forveksles med en melding.
"""
from __future__ import annotations

from django.conf import settings

#: Typene, med det merket og fanen viser. **Rekkefølgen er ikke viktig; settet er
#: det.** En ny type legges til her og ingen andre steder.
TYPER = {
    'drift': {'merke': '', 'kort': '', 'fane': '', 'epost': '', 'klasse': ''},
    'test': {'merke': 'TESTMILJØ', 'kort': 'TEST', 'fane': '[TEST] ', 'epost': '[test] ',
             'klasse': 'miljomerke-test',
             'forklaring': 'Dette er testmiljøet. Ingenting du registrerer her er ekte.'},
    'utvikling': {'merke': 'UTVIKLING', 'kort': 'UTV', 'fane': '[UTV] ', 'epost': '[utvikling] ',
                  'klasse': 'miljomerke-utvikling',
                  'forklaring': 'Utviklingsmiljø. Ingenting du registrerer her er ekte.'},
}
UKJENT = {'merke': 'UKJENT MILJØ', 'kort': 'UKJENT', 'fane': '[?] ', 'epost': '[ukjent miljø] ',
          'klasse': 'miljomerke-ukjent',
          'forklaring': 'Portalen vet ikke hvilket miljø den kjører i (PORTAL_MILJO). '
                        'Sjekk adressen før du registrerer noe.'}


def miljo(raa: str | None = None) -> dict:
    """Miljøet portalen kjører i, med det merket trenger.

    ``type`` er en av `TYPER`, eller ``'ukjent'``. ``vis`` sier om merket skal
    stå — alt utenom `drift`. ``gyldig`` er usann for en verdi som ikke står i
    lista, og server-status farger den rød.
    """
    verdi = (settings.PORTAL_MILJO if raa is None else raa) or ''
    verdi = str(verdi).strip()
    if verdi in TYPER:
        return {'type': verdi, 'verdi': verdi, 'gyldig': True, 'vis': verdi != 'drift',
                **TYPER[verdi]}
    return {'type': 'ukjent', 'verdi': verdi, 'gyldig': False, 'vis': True, **UKJENT}


def advar_ved_ukjent(logger) -> None:
    """Én linje i loggen ved oppstart når verdien ikke står i lista."""
    m = miljo()
    if not m['gyldig']:
        logger.warning(
            'PORTAL_MILJO er %r — ikke en av %s. Portalen viser «UKJENT MILJØ» til den er satt.',
            m['verdi'], ', '.join(sorted(TYPER)))
