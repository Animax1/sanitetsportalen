# -*- coding: utf-8 -*-
"""Hjelpere for management-kommandoene som kjøres av Railway Cron.

**En død database skal gi én linje, ikke to hundre.**

Portalen har to cron-jobber — `purge_old_logs` og `kollaps_arkiv` — og de har
ingen bruker som ser på dem mens de kjører. Den eneste som noen gang leser
utskriften, er den som lurer på hvorfor jobben er rød. Hjelperen brukes også av
`backup_kjor`, som ikke er en cron-jobb, men som kjøres uten tilsyn på samme
måte når den startes med `railway ssh`. Et rått `OperationalError` gir da fire stablede tracebacks der den ene
setningen som betyr noe — «password authentication failed» — står omtrent på
linje 140, mellom to identiske kopier av seg selv.

`CommandError` skriver meldingen til stderr og avslutter med kode 1, så
jobben er fortsatt rød og Railway melder den fortsatt som feilet. Vi skjuler
ingenting: den underliggende teksten fra psycopg2 står i meldingen, med vert
og årsak.

**Hvorfor det er én funksjon og ikke én per jobb.** 30. aug. 2026 falt to av
jobbene på samme avviste passord i staging, og feilsøkingen begynte med å
lese to nesten identiske tracebacks for å finne ut at de sa det samme. Skrev
vi meldingen i hver kommando, ville den tredje før eller siden fått en annen
ordlyd — eller ingen.
"""
from __future__ import annotations

from contextlib import contextmanager

from django.core.management.base import CommandError
from django.db import OperationalError

#: Rådet som løser feilen i praksis. En kopiert `DATABASE_URL` ser riktig ut
#: helt til noen roterer databasepassordet, og da er det bare tjenestene med
#: en kopi som slutter å virke — mens websiden går videre som før, så
#: ingenting *ser* galt ut.
RAAD = (
    'Sjekk DATABASE_URL på tjenesten som kjører jobben. Er den en kopiert '
    'verdi framfor referansen ${{Postgres.DATABASE_URL}}, blir den stående '
    'igjen når databasepassordet roteres — og da feiler bare cron-jobbene, '
    'mens websiden går videre som før.'
)


def _forste_linje(feil):
    """Psycopg2 gjentar seg selv. Én gang holder."""
    tekst = str(feil).strip()
    return tekst.splitlines()[0] if tekst else feil.__class__.__name__


@contextmanager
def lesbar_dbfeil(jobb, navn=None):
    """Gjør en tilkoblingsfeil om til én lesbar linje i cron-loggen.

    Args:
        jobb: hva som ikke ble gjort, i klartekst — «ingen logger ble
            slettet». Meldingen skal si hva som *ikke skjedde*, ikke bare at
            noe feilet: en cron-jobb som feiler halvveis er noe annet enn en
            som aldri kom i gang.
        navn: jobbens navn for `registrer_kjoring` (13. sep. 2026) — siste
            kjøring, ok/feil, vises på /portal-admin/server-status/. Ingen
            har en bruker som ser cron-loggen, og en jobb som stille har
            sluttet å kjøre er den feilen man ellers oppdager for sent.
    """
    try:
        yield
    except OperationalError as feil:
        if navn:
            registrer_kjoring(navn, False, f'Databasen tok ikke imot tilkoblingen: {_forste_linje(feil)}')
        raise CommandError(
            f'Databasen tok ikke imot tilkoblingen, så {jobb}: '
            f'{_forste_linje(feil)}\n{RAAD}'
        ) from feil
    except Exception as feil:
        if navn:
            registrer_kjoring(navn, False, f'{feil.__class__.__name__}: {_forste_linje(feil)}')
        raise
    else:
        if navn:
            registrer_kjoring(navn, True, '')


#: Jobbene Railway Cron faktisk kjører. Dashbordet på
#: `/portal-admin/server-status/` viser «Aldri» for en jobb som står her uten
#: å være satt opp — og et varsel som alltid står rødt lærer deg å ikke se på
#: dashbordet.
#:
#: `db_backup` sto her fram til 13. sep. 2026 uten å være satt opp i Railway.
#: Den er ikke erstattet av `backup_kjor`: backup er ikke lenger en cron-jobb,
#: fordi Railway-volumet bare kan henge på én tjeneste og en cron-tjeneste uten
#: det ville skrevet filene til et flyktig containerfilsystem. Klokka er en
#: tråd i web-prosessen; se `core/backup/klokke.py`. Helsa til den vises som
#: sin egen linje på server-status, ikke som en cron-jobb.
CRON_JOBBER = ('purge_old_logs', 'kollaps_arkiv')


def registrer_kjoring(navn, ok, melding=''):
    """Skriv siste kjøring av en cron-jobb til `AppSetting` (`cron.<navn>`).
    Kaster aldri — en logg som tar ned jobben er verre enn ingen logg."""
    import json
    from django.utils import timezone
    try:
        from patients.models import AppSetting
        AppSetting.set(f'cron.{navn}', json.dumps(
            {'tid': timezone.now().isoformat(), 'ok': bool(ok), 'melding': (melding or '')[:300]}))
    except Exception:   # noqa: BLE001
        pass


def siste_kjoringer():
    """{navn: {tid, ok, melding} | None} for cron-jobbene."""
    import json
    from patients.models import AppSetting
    ut = {}
    for navn in CRON_JOBBER:
        raa = AppSetting.get(f'cron.{navn}', '')
        try:
            ut[navn] = json.loads(raa) if raa else None
        except (TypeError, ValueError):
            ut[navn] = None
    return ut
