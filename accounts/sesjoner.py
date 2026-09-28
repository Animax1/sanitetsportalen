"""Kontoens side av sesjonene: én aktiv per bruker, og alle ut ved et bytte.

Sto i `accounts/views.py` til 28. sep. 2026. Flyttet fordi to kommandoer
trenger dem — `sett_passord` satte passord uten å avslutte noe, og
`nullstill_mfa` må gjøre nøyaktig det knappen gjør. Primitivet som leser
sesjonstabellen er `core.sesjoner`; dette er det kontoen gjør med det.
"""
from django.contrib.sessions.models import Session

from core.sesjoner import slett_brukerens_sesjoner


def registrer_aktiv_sesjon(user, session_key):
    """Avslutt brukerens forrige sesjon og registrer den nye (N10).

    Portalen har én-sesjon-per-bruker som policy: logger du inn på en ny enhet,
    ryker den gamle. Det var tidligere implementert ved å iterere **alle**
    ikke-utløpte sesjoner og kalle ``get_decoded()`` på hver — signaturverifisering
    og JSON-parsing per rad. Django har ingen indeks fra bruker til sesjon, så
    mønsteret er i og for seg det vanlige; problemet var hvor det ble kalt.
    Kostnaden traff innloggingsstien, altså de ti minuttene ved vaktstart der
    alle logger på samtidig.

    Nå lagrer vi sesjonsnøkkelen på brukeren, og invalidering blir ett indeksert
    oppslag. Feltet er en cache av policyen, ikke fasit for hvilke sesjoner som
    finnes. Derfor beholder de sikkerhetskritiske stiene — passordbytte,
    admin-reset, frys og sletting — den grundige gjennomgangen.

    **Tom `current_session_key` betyr ikke «ingen sesjoner».** Den betyr at vi
    ikke *vet* om det finnes noen: brukeren kan ha en sesjon opprettet før feltet
    ble innført. Skjedde i produksjon 13. august 2026 — en bruker som allerede var
    innlogget på én enhet forble innlogget der etter å ha logget inn på en annen,
    fordi det ikke sto noen nøkkel å slette. Derfor faller vi tilbake til den
    grundige gjennomgangen når feltet er tomt. Det koster ett fullt gjennomløp
    per bruker, første gang de logger inn etter at feltet ble innført; deretter
    gjelder den raske stien.
    """
    forrige = user.current_session_key

    if not forrige:
        avslutt_andre_sesjoner(user, session_key)
        return

    if forrige != session_key:
        Session.objects.filter(session_key=forrige).delete()
        user.current_session_key = session_key
        user.save(update_fields=['current_session_key'])


def avslutt_andre_sesjoner(user, current_session_key):
    """Slett alle aktive sesjoner for brukeren, unntatt nåværende sesjon.

    Grundig variant: itererer og dekoder alle ikke-utløpte sesjoner. Brukes ved
    passordbytte, der det å garantere at ingen annen sesjon overlever er selve
    poenget — og hvor kostnaden er irrelevant fordi operasjonen er sjelden.
    Innloggingsstien bruker ``registrer_aktiv_sesjon()`` i stedet.
    """
    slett_brukerens_sesjoner(user, unntatt=current_session_key)

    if user.current_session_key != current_session_key:
        user.current_session_key = current_session_key
        user.save(update_fields=['current_session_key'])


def avslutt_alle_sesjoner(user):
    """Slett alle aktive sesjoner for brukeren (admin-reset, frys, sletting).

    Grundig av samme grunn som over: brukes kun i sikkerhetsoperasjoner der en
    overlevende sesjon er hele feilmodusen man vil unngå.
    """
    slett_brukerens_sesjoner(user)

    if user.current_session_key:
        user.current_session_key = None
        user.save(update_fields=['current_session_key'])
