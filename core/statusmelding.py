"""Admins statusmelding i toppmenyen (André, 11. okt. 2026).

«Jeg ser litt mer bruksområde enn bare å si hvilket miljø vi har.» Global admin
skriver en kort tekst og velger farge — *Vakt pågår*, *Vedlikehold i kveld 22–23*,
*Ustabil — bruk papirskjema* — og den står i toppmenyen på hver side, også i
prod, også på bilskjermen.

**Den er noe annet enn miljømerket** (`core/miljo.py`), og ser derfor annerledes
ut: miljømerket er et *vern* som ikke kan redigeres bort, og har striper i farger
denne aldri tilbys; meldingen er en *beskjed*, ensfarget, som skrives og fjernes
fritt.

| Farge | Betyr |
|---|---|
| grønn | til informasjon |
| gul | husk dette |
| oransje | noe skjer snart |
| rød | handle nå — sparsomt, ellers slutter den å bety noe |

**Lagret som én `AppSetting`** (JSON), så siden leser den med én spørring og
endringen står i revisjonsloggen med hvem og når (`core/signals.py`). **«Vis
til»** gjør at en melding om vedlikehold ikke blir stående i flere uker fordi
noen glemte den. **Den kommer fram uten sidelasting**: bjella poller hvert 30.
sekund på hver innlogget side, og svaret bærer meldingen (`views_varsler`).
"""
from __future__ import annotations

import json
from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.portalinnstillinger import BasePortalinnstillingHandler, register

NOKKEL = 'statusmelding'
MAKS_TEGN = 40
#: Fargene admin kan velge. Navnet er det som lagres og blir CSS-klassen —
#: derfor ASCII, og derfor en lukket liste.
FARGER = {'gronn': 'Grønn', 'gul': 'Gul', 'oransje': 'Oransje', 'rod': 'Rød'}


def _les() -> dict:
    from core.models import AppSetting

    try:
        data = json.loads(AppSetting.get(NOKKEL, '') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def aktiv(naa=None) -> dict | None:
    """Meldingen som skal vises nå, eller ``None``.

    **Leser forsvarlig**: en ukjent farge, en tom tekst eller et «til» som ikke
    lar seg lese gir ingen melding i stedet for en side som feiler — en verdi
    skrevet for hånd i shellet skal ikke ta ned toppmenyen.
    """
    data = _les()
    tekst = str(data.get('tekst') or '').strip()[:MAKS_TEGN]
    farge = data.get('farge')
    if not tekst or farge not in FARGER:
        return None
    til = data.get('til')
    if til:
        try:
            slutt = datetime.fromisoformat(til)
        except (TypeError, ValueError):
            return None
        if (naa or timezone.now()) >= slutt:
            return None
    return {'tekst': tekst, 'farge': farge}


class StatusmeldingInnstillinger(BasePortalinnstillingHandler):
    """Kortet «Statusmelding i toppmenyen» på `/portal-admin/innstillinger/`."""

    slug = 'statusmelding'
    order = 1   # først: den gjelder hele portalen
    mal = 'core/portalinnstillinger_statusmelding.html'

    def kontekst(self) -> dict:
        data = _les()
        til = data.get('til')
        try:
            til_lokal = (timezone.localtime(datetime.fromisoformat(til)).strftime('%Y-%m-%dT%H:%M')
                         if til else '')
        except (TypeError, ValueError):
            til_lokal = ''
        return {
            'statusmelding_tekst': data.get('tekst', ''),
            'statusmelding_farge': data.get('farge') or 'gronn',
            'statusmelding_til': til_lokal,
            'statusmelding_farger': list(FARGER.items()),
            'statusmelding_maks': MAKS_TEGN,
            'statusmelding_aktiv': aktiv(),
        }

    def valider(self, post) -> dict:
        """Les og prøv. **Skriv ingenting her.** Fraværende felt er «behold»;
        tom tekst er «ingen melding»."""
        if post.get('statusmelding_tekst') is None:
            return {}
        tekst = str(post.get('statusmelding_tekst')).strip()
        if not tekst:
            return {'data': None}
        if len(tekst) > MAKS_TEGN:
            raise ValidationError(f'Statusmeldingen kan være høyst {MAKS_TEGN} tegn.')
        farge = post.get('statusmelding_farge')
        if farge not in FARGER:
            raise ValidationError('Velg en farge for statusmeldingen.')
        raa_til = str(post.get('statusmelding_til') or '').strip()
        til = None
        if raa_til:
            try:
                til = datetime.fromisoformat(raa_til)
            except ValueError:
                raise ValidationError('«Vis til» må være et tidspunkt.') from None
            if timezone.is_naive(til):
                til = timezone.make_aware(til, timezone.get_current_timezone())
            if til <= timezone.now():
                raise ValidationError('«Vis til» er alt passert — meldingen ville aldri vist seg.')
        return {'data': {'tekst': tekst, 'farge': farge, 'til': til.isoformat() if til else None}}

    def lagre(self, verdier: dict) -> None:
        from core.models import AppSetting

        if 'data' in verdier:
            AppSetting.set(NOKKEL, json.dumps(verdier['data'], ensure_ascii=False)
                           if verdier['data'] else '')


def register_handlers() -> None:
    register(StatusmeldingInnstillinger())
