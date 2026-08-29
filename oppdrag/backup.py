"""Backup-handlere for oppdragsmodulen.

To enheter, av samme grunn som i pasientmodulen: den aktive vaktdataen endrer
seg hele tiden og trenger hyppig backup, mens arkivet endres én gang per
arrangement og aldri skal berøres av en restore av den andre.

**Arkivbackupen er ikke valgfri.** `core.arkiv.kollaps()` sletter radnivået
permanent, og sperren foran den krever en backup med slugen
`oppdrag_arkiv` tatt etter at arkivet ble opprettet. Uten denne handleren
ville sperren aldri kunne åpnes, og kollapsen måtte tvinges — altså gjøres
uten nett.

Brukere, MFA-hemmeligheter og audit-spor er bevisst utelatt fra begge, som i
`patients/backup.py`.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class OppdragBackupHandler(BaseBackupHandler):
    """Backup av den aktive oppdragsdataen.

    Modulen hadde ingen backup fram til fase 7 — arkivet gjorde mangelen
    synlig, men den gjaldt hele modulen: en vakts oppdrag, statusmeldinger og
    enhetsbytter lå utenfor all dekning.

    `Enhet` og `Lokasjon` er med. De er oppsett, ikke vaktdata, men et
    oppdrag uten sin enhet lar seg ikke gjenopprette (PROTECT), og en dump
    som ikke kan lastes tilbake er ingen backup.
    """

    slug = 'oppdrag'
    display_name = 'Oppdrag'

    apps = ['oppdrag']
    exclude = [
        # Arkivet håndteres av OppdragArkivBackupHandler og skal aldri endres
        # av en restore av den aktive dataen. Begge modellene må ekskluderes:
        # barna uten forelderen ville feilet på fremmednøkkel og rullet hele
        # gjenopprettingen tilbake — samme felle som i pasientmodulen.
        'oppdrag.OppdragArkiv',
        'oppdrag.ArkivertOppdrag',
    ]
    restore_models = [
        # Barn først. Statusmelding og Enhetsbytte peker på Oppdrag, Oppdrag
        # peker på Enhet og Lokasjon.
        'oppdrag.Statusmelding',
        'oppdrag.Enhetsbytte',
        'oppdrag.Oppdrag',
        'oppdrag.Lokasjon',
        'oppdrag.Enhet',
    ]
    # FK-er ut av modulens eget datasett. Med `natural_foreign` lagres de som
    # brukernavn, og er kontoen slettet feiler HELE gjenopprettingen med
    # DeserializationError — altså akkurat når man trenger backupen. Ingen av
    # dem er nødvendig for å forstå dataene: hvem som meldte en status er
    # interessant i tidslinjen, ikke i en gjenoppretting av den.
    strip_fields = {
        'oppdrag.Oppdrag': ['opprettet_av', 'historikk_av'],
        'oppdrag.Statusmelding': ['meldt_av'],
        'oppdrag.Enhetsbytte': ['byttet_av'],
        'oppdrag.Enhet': ['user'],
    }


class OppdragArkivBackupHandler(BaseBackupHandler):
    """Backup av oppdragsarkivet.

    Forelder og barn hører sammen i samme dump — et arkiv uten sine rader,
    eller rader uten sitt arkiv, er ikke gjenopprettbart.
    """

    slug = 'oppdrag_arkiv'
    display_name = 'Oppdragsarkiv'

    apps = ['oppdrag.OppdragArkiv', 'oppdrag.ArkivertOppdrag']
    exclude = []
    restore_models = [
        'oppdrag.ArkivertOppdrag',
        'oppdrag.OppdragArkiv',
    ]
    # Brukernavnet ligger frosset i `importert_av_navn`, så FK-en utelates —
    # se ArkivBackupHandler i patients/backup.py.
    strip_fields = {'oppdrag.OppdragArkiv': ['importert_av']}


def register_handlers() -> None:
    """Kalles fra ``oppdrag.apps.OppdragConfig.ready()``."""
    register(OppdragBackupHandler())
    register(OppdragArkivBackupHandler())
