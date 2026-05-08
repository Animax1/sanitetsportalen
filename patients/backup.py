"""Backup-handler for patients-modulen.

Registrerer en BaseBackupHandler-subklasse i core.backup-registry
slik at sentral backup/restore-tjeneste kan håndtere patients-data.

Bevarer dagens sikkerhetsregel: KUN pasientrelaterte data inkluderes.
Brukere, MFA-hemmeligheter og audit-spor er bevisst utelatt.
"""
from __future__ import annotations

from core.backup import BaseBackupHandler, register


class PatientsBackupHandler(BaseBackupHandler):
    """Backup-handler for pasientregistrerings-modulen.

    SIKKERHET:
    - ``apps`` inkluderer kun ``patients``-modeller — accounts, audit
      og sessions røres aldri.
    - ``exclude`` fjerner Backup og BackupConfig fra dump for å unngå
      selvreferanse (backupen som lages skal ikke være med i innholdet).
    - ``restore_models`` lister opp modellene som skal slettes før
      ``loaddata`` kjøres, i FK-trygg rekkefølge (barn først).
    """
    slug = 'patients'
    display_name = 'Pasientregistrering'

    apps = ['patients']
    exclude = [
        # Backup og BackupConfig skal ikke være med i sin egen dump.
        'patients.Backup',
        'patients.BackupConfig',
        # VaktArkiv er bevisst utelatt: arkivet er låst og skal aldri
        # endres ved restore. Det forblir uavhengig av pasient-restore.
        'patients.VaktArkiv',
    ]
    restore_models = [
        # Slett-rekkefølge: barn -> foreldre. Patient har FK til Behandler
        # og Helsepersonell, så Patient må slettes først.
        # VaktArkiv er IKKE her — den røres aldri av restore (se exclude).
        'patients.Patient',
        'patients.Behandler',
        'patients.Helsepersonell',
        'patients.AppSetting',
    ]


def register_handlers() -> None:
    """Kalles fra patients.apps.PatientsConfig.ready().

    Idempotent: klargjør for at apps.ready() kan kalles flere ganger
    ved testkjøring uten å lage duplikater.
    """
    register(PatientsBackupHandler())
