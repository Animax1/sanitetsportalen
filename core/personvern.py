"""Personvernerklæringen — `/personvern/` (12. okt. 2026).

**Ingen innlogging.** Informasjonsplikten (GDPR art. 13) gjelder *før* noen gir
fra seg opplysninger: den som får en invitasjon, og lagene som registrerer på
`/lag/r/` uten konto. En erklæring bak innloggingen kan bare leses av dem som
allerede har gitt fra seg det den forteller om. Siden har ingen data og ingen
skjema, og lenkes fra hver side med egen `<head>` — `core/tests_personvern.py`
håndhever det.

**Den er erklæringen, ikke en kopi av den.** Del B i
`docs/PERSONVERN_DOKUMENTASJON.md` var den lettleste erklæringen, og hadde glidd:
den kjente bare én backupfrist (de nyeste 50 filene), ikke Scaleway, ikke
mannskapsregisteret, og ikke cookiene. To tekster om det samme er to kilder som glir fra
hverandre, og den som leser den ene vet ikke at den andre finnes. Del B peker nå
hit; **protokollen (del A) er fasit for hva som gjøres, malen for hva som sies.**

**Fristene som er kode, hentes fra koden.** Sesjonstiden og «delt posisjon» er
innstillinger admin kan flytte, og logg-, varsel- og offsitefristene står som
konstanter der de håndheves. Skrevet av for hånd ville de stått igjen på siden den
dagen noen endret dem — og en personvernerklæring som oppgir feil lagringstid er
verre enn en som ikke oppgir noen. Fristene en modul eier — lagregistreringene,
overnattingen — leses gjennom `core/opprydding.py`, samme register
`purge_old_logs` håndhever dem med: `core` får ikke importere en modul, og
registeret svarer med nøyaktig den fristen som faktisk slettes etter.
"""
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

from accounts.middleware import sesjonstid_timer
from audit.management.commands.purge_old_logs import (
    DEFAULT_LOG_DAYS,
    DEFAULT_NOTIFICATION_DAYS,
)
from core.arkiv import get_handler as arkivhandler
from core.kartkobling import delt_posisjon_min
from core.offsite import FORVENTET_DAGER, PREFIKS, PREFIKS_FULL
from core.opprydding import all_handlers

#: Kontaktadressen for personvern (André, 12. okt. 2026). Står også i
#: `docs/PERSONVERN_DOKUMENTASJON.md` A.1, A.14 og B.
KONTAKT = 'personvern@sanitet.net'
BEHANDLINGSANSVARLIG = 'Kverneland Røde Kors'


def modulfrister() -> dict[str, int]:
    """Slug → dager, fra oppryddingsregisteret. En handler som feiler utelates —
    siden sier da «en fast frist» i stedet for et tall, og tegnes likevel."""
    frister = {}
    for handler in all_handlers():
        try:
            frister[handler.slug] = int(handler.frist_dager())
        except Exception:
            continue
    return frister


def arkivmaaneder(slug: str) -> int | None:
    """Hvor lenge en moduls arkiverte rader står før de kollapser til
    statistikk, i hele måneder. `None` når modulen ikke arkiverer."""
    handler = arkivhandler(slug)
    if handler is None:
        return None
    return round(handler.retention_dager / 365 * 12)


def personvern_kontekst() -> dict:
    """Det siden oppgir som tall. Egen funksjon, så den lar seg prøve uten HTTP."""
    from django.conf import settings

    return {
        'kontakt': KONTAKT,
        'behandlingsansvarlig': BEHANDLINGSANSVARLIG,
        'sesjon_timer': sesjonstid_timer(),
        'logg_dager': DEFAULT_LOG_DAYS,
        'varsel_dager': DEFAULT_NOTIFICATION_DAYS,
        'offsite_dager': FORVENTET_DAGER[PREFIKS],
        'offsite_full_dager': FORVENTET_DAGER[PREFIKS_FULL],
        'mfa_dager': getattr(settings, 'MFA_TRUST_DEVICE_DAYS', 30),
        'delt_posisjon_min': delt_posisjon_min(),
        'frister': modulfrister(),
        'pasientarkiv_mnd': arkivmaaneder('patients'),
    }


@require_safe
@cache_control(no_cache=True)
def personvern_view(request):
    return render(request, 'core/personvern.html', personvern_kontekst())
