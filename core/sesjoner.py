"""Hvem er pålogget nå — ett sted, to lesere (17. sep. 2026).

Loopen som dekoder Djangos sesjonstabell sto i `core/admin_status.py`, som
private navn i adminflaten. KO trenger den samme loopen til sidebaren sin
(`docs/FORSLAG_KO.md` §5.3), og en modul skal ikke plukke i en annen flates
private navn — så primitivet står her, i rammeverket, og **projeksjonen** er
hver leser sin egen.

Det skillet er hele poenget med fila. Adminlista bærer `session_key`, som er
håndtaket `admin_session_kill` avslutter en sesjon med; KO-sidebaren skal
**ikke** bære det. Hadde KO gjenbrukt adminradene som de er, ville hver
operatør fått et håndtak modulen ikke gir henne lov til å bruke — og den slags
oppdages først den dagen noen finner ut hva feltet er.

**«Pålogget» er ikke «til stede»** (André, 16. sep. 2026). `inaktiv_s` er
sekunder siden fana sist ble rørt, ikke siden sesjonen sist ble fornyet:
portalen poller seg selv hvert 5.–30. sekund, så `expire_date` er ikke et
dårlig mål på tilstedeværelse — det er ikke et mål på det i det hele tatt. Se
`BrukerAktivitetMiddleware` i `core/middleware.py`.
"""
from __future__ import annotations

from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone

from core.middleware import SISTE_INTERAKSJON


def inaktiv_sekunder(data, naa):
    """Sekunder siden brukeren sist rørte siden — `None` om vi ikke vet.

    **`None` og ikke 0.** En sesjon fra før `BrukerAktivitetMiddleware` fantes,
    eller en klient som aldri har kalt `apiFetch`, har ingen verdi — og «vet
    ikke» må kunne skilles fra «aktiv nå». Skrev vi 0, ville hver gammel sesjon
    sett ut som om noen satt der.
    """
    raa = data.get(SISTE_INTERAKSJON)
    if not raa:
        return None
    try:
        sist = datetime.fromisoformat(raa)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(sist):
        return None
    return max(0, int((naa - sist).total_seconds()))


def aktive_sesjoner():
    """[(bruker, rad)] for hver ikke-utløpt sesjon som hører til en bruker.

    Rada er råstoffet — `session_key`, `expire_date` og `inaktiv_s` — og
    brukerobjektet står ved siden av, slik at hver leser velger selv hva som
    slippes ut. Anonyme sesjoner og sesjoner med slettet bruker hoppes over.

    Brukerne hentes i **én** spørring, ikke én per sesjon: lista leses av et
    dashbord som polles hvert tiende sekund, og en N+1 der er en N+1 som
    kjører hele vakta.
    """
    User = get_user_model()
    naa = timezone.now()

    dekodet = []
    bruker_ider = []
    for sesjon in Session.objects.filter(expire_date__gt=naa):
        try:
            data = sesjon.get_decoded()
        except Exception:
            # En sesjon vi ikke får dekodet er ikke en sesjon vi kan si noe om.
            # Den skal ikke ta ned lista for de andre.
            continue
        raa_id = data.get('_auth_user_id')
        if not raa_id:
            continue
        try:
            bruker_id = int(raa_id)
        except (TypeError, ValueError):
            continue
        bruker_ider.append(bruker_id)
        dekodet.append((sesjon, bruker_id, data))

    brukere = {u.id: u for u in User.objects.filter(id__in=bruker_ider)}

    ut = []
    for sesjon, bruker_id, data in dekodet:
        bruker = brukere.get(bruker_id)
        if bruker is None:
            continue
        ut.append((bruker, {
            'session_key': sesjon.session_key,
            'expire_date': sesjon.expire_date.isoformat(),
            'inaktiv_s': inaktiv_sekunder(data, naa),
        }))
    return ut
