# -*- coding: utf-8 -*-
"""Hjelpere for management-kommandoene som kjøres av Railway Cron.

**En død database skal gi én linje, ikke to hundre.**

Portalen har tre cron-jobber — `purge_old_logs`, `kollaps_arkiv` og
`db_backup` — og de har ingen bruker som ser på dem mens de kjører. Den
eneste som noen gang leser utskriften, er den som lurer på hvorfor jobben er
rød. Et rått `OperationalError` gir da fire stablede tracebacks der den ene
setningen som betyr noe — «password authentication failed» — står omtrent på
linje 140, mellom to identiske kopier av seg selv.

`CommandError` skriver meldingen til stderr og avslutter med kode 1, så
jobben er fortsatt rød og Railway melder den fortsatt som feilet. Vi skjuler
ingenting: den underliggende teksten fra psycopg2 står i meldingen, med vert
og årsak.

**Hvorfor det er én funksjon og ikke tre.** 30. aug. 2026 falt to av de tre
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
def lesbar_dbfeil(jobb):
    """Gjør en tilkoblingsfeil om til én lesbar linje i cron-loggen.

    Args:
        jobb: hva som ikke ble gjort, i klartekst — «ingen logger ble
            slettet». Meldingen skal si hva som *ikke skjedde*, ikke bare at
            noe feilet: en cron-jobb som feiler halvveis er noe annet enn en
            som aldri kom i gang.
    """
    try:
        yield
    except OperationalError as feil:
        raise CommandError(
            f'Databasen tok ikke imot tilkoblingen, så {jobb}: '
            f'{_forste_linje(feil)}\n{RAAD}'
        ) from feil
