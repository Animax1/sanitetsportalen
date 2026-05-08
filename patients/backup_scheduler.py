"""In-process scheduler for automatisk backup.

Designvalg: I stedet for en egen cron-service (som krever delt volum med
web-servicen), kjører vi backup-sjekken inne i web-prosessen. En middleware
trigger en sjekk ved hver request, men med en in-memory throttle som sikrer
at selve sjekken ikke kjører oftere enn én gang per 60 sekund per prosess.

Selve backup-operasjonen kjøres i en bakgrunnstråd slik at request-latency
ikke påvirkes. Vi bruker en database-lås via select_for_update for å unngå
at to prosesser/tråder lager samme backup samtidig når Gunicorn kjører med
flere arbeidere.
"""
import logging
import threading
import time
from datetime import timedelta

from django.db import transaction, OperationalError
from django.utils import timezone

from .backup_service import create_backup, purge_old_backups
from .models import BackupConfig

logger = logging.getLogger(__name__)

# Minimum tid mellom throttle-sjekker (per prosess). Dette er IKKE
# backup-intervallet – det er hvor ofte vi i det hele tatt leser
# BackupConfig fra databasen.
_THROTTLE_SECONDS = 60

# Per-prosess state for throttle
_last_check_ts = 0.0
_check_lock = threading.Lock()

# Per-prosess lås for å unngå at samme prosess starter flere
# bakgrunnstråder samtidig
_running_lock = threading.Lock()
_is_running = False


def _should_run_now(cfg):
    """Avgjør om en automatisk backup skal kjøre nå basert på konfig."""
    if cfg.interval_minutes == 0:
        return False
    if cfg.last_run_at is None:
        return True
    elapsed = timezone.now() - cfg.last_run_at
    return elapsed >= timedelta(minutes=cfg.interval_minutes)


def _run_backup_with_db_lock():
    """Kjører backup-operasjonen med database-lås for å unngå duplikater
    på tvers av Gunicorn-arbeidere.

    Bruker select_for_update + dobbeltsjekk: vi tar raden med lås, sjekker
    om den fortsatt trenger backup, og oppdaterer last_run_at FØR selve
    backupen kjøres. Dermed vil andre arbeidere som kommer like etter se
    den oppdaterte last_run_at og hoppe over.
    """
    global _is_running
    try:
        with transaction.atomic():
            try:
                cfg = BackupConfig.objects.select_for_update(nowait=True).get(pk=1)
            except OperationalError:
                # En annen arbeider holder låsen akkurat nå – hopp over
                logger.debug('backup_scheduler: kunne ikke ta lås, hopper over')
                return

            if not _should_run_now(cfg):
                logger.debug('backup_scheduler: konfig sier at det ikke er tid ennå')
                return

            # Reserver slotten ved å oppdatere last_run_at først.
            # Hvis create_backup feiler rulles dette tilbake av transaction.atomic.
            cfg.last_run_at = timezone.now()
            cfg.save(update_fields=['last_run_at'])

            backup = create_backup(kind='auto', note='Automatisk (in-process)')
            purged = purge_old_backups()
            if backup is None:
                # #0: identisk innhold som forrige auto-backup — hoppet over.
                # last_run_at er allerede oppdatert ovenfor, slik at vi ikke
                # spammer dumpdata for hver request. Neste sjekk skjer etter
                # cfg.interval_minutes som vanlig.
                logger.info(
                    'backup_scheduler: auto-backup hoppet over (identisk innhold). '
                    'Slettet %d gamle.', purged,
                )
            else:
                logger.info(
                    'backup_scheduler: OK %s (%d bytes). Slettet %d gamle.',
                    backup.filename, backup.size_bytes, purged,
                )
    except Exception:
        logger.exception('backup_scheduler: feil under automatisk backup')
    finally:
        with _running_lock:
            _is_running = False


def maybe_run_backup():
    """Hoved-inngangspunkt. Kalt fra middleware ved hver request.

    Returner raskt uten å blokkere. Selve backupen kjøres i en bakgrunnstråd
    hvis det er tid for en ny backup.
    """
    global _last_check_ts, _is_running

    # Throttle: maks én sjekk per _THROTTLE_SECONDS per prosess
    now = time.monotonic()
    with _check_lock:
        if now - _last_check_ts < _THROTTLE_SECONDS:
            return
        _last_check_ts = now

    # Unngå flere samtidige bakgrunnstråder i samme prosess
    with _running_lock:
        if _is_running:
            return
        _is_running = True

    # Rask sjekk uten lås for å unngå unødvendig bakgrunnstråd
    try:
        cfg = BackupConfig.objects.get(pk=1)
    except BackupConfig.DoesNotExist:
        with _running_lock:
            _is_running = False
        return

    if not _should_run_now(cfg):
        with _running_lock:
            _is_running = False
        return

    # Kjør backup i bakgrunnstråd slik at request-latency ikke påvirkes
    t = threading.Thread(target=_run_backup_with_db_lock, daemon=True)
    t.start()
