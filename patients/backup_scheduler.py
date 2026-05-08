"""In-process scheduler for automatisk backup — per modul (Fase 4).

Designvalg: I stedet for en egen cron-service (som krever delt volum med
web-servicen), kjører vi backup-sjekken inne i web-prosessen. En middleware
trigger en sjekk ved hver request, men med en in-memory throttle som sikrer
at selve sjekken ikke kjører oftere enn én gang per 60 sekund per prosess.

Selve backup-operasjonen kjøres i en bakgrunnstråd slik at request-latency
ikke påvirkes. Vi bruker en database-lås via select_for_update for å unngå
at to prosesser/tråder lager samme backup samtidig når Gunicorn kjører med
flere arbeidere.

**Per-modul (Fase 4):** Tidligere var det én singleton ``BackupConfig`` for
patients. Nå itererer vi alle ``ModuleBackupConfig``-rader hvor
``enabled=True`` og en backup-handler er registrert, og kjører backup
uavhengig per modul (med eget intervall + cap).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from django.db import transaction, OperationalError
from django.utils import timezone

logger = logging.getLogger(__name__)

# Minimum tid mellom throttle-sjekker (per prosess). Dette er IKKE
# backup-intervallet — det er hvor ofte vi i det hele tatt leser
# ModuleBackupConfig fra databasen.
_THROTTLE_SECONDS = 60

# Per-prosess state for throttle.
_last_check_ts = 0.0
_check_lock = threading.Lock()

# Per-prosess lås for å unngå at samme prosess starter flere
# bakgrunnstråder samtidig.
_running_lock = threading.Lock()
_is_running = False


def _should_run_now(cfg) -> bool:
    """Avgjør om en automatisk backup skal kjøre nå basert på konfig."""
    if not cfg.enabled:
        return False
    if cfg.interval_minutes == 0:
        return False
    if cfg.last_run_at is None:
        return True
    elapsed = timezone.now() - cfg.last_run_at
    return elapsed >= timedelta(minutes=cfg.interval_minutes)


def _run_backup_for_module(slug: str) -> None:
    """Kjør backup for én modul med database-lås for å unngå duplikater
    på tvers av Gunicorn-arbeidere.

    Bruker select_for_update + dobbeltsjekk: vi tar raden med lås, sjekker
    om den fortsatt trenger backup, og oppdaterer last_run_at FØR selve
    backupen kjøres. Dermed vil andre arbeidere som kommer like etter se
    den oppdaterte last_run_at og hoppe over.
    """
    # Lazy-import for å unngå sirkulære avhengigheter ved app-loading.
    from core.backup import (
        KIND_AUTO,
        create_backup,
        enforce_cap,
        get_handler,
    )
    from core.models import ModuleBackupConfig

    if get_handler(slug) is None:
        logger.debug('backup_scheduler: ingen handler for %s, hopper over', slug)
        return

    try:
        with transaction.atomic():
            try:
                cfg = (
                    ModuleBackupConfig.objects
                    .select_for_update(nowait=True)
                    .get(module_slug=slug)
                )
            except OperationalError:
                logger.debug(
                    'backup_scheduler: kunne ikke ta l\xe5s for %s, hopper over', slug,
                )
                return
            except ModuleBackupConfig.DoesNotExist:
                return

            if not _should_run_now(cfg):
                return

            # Reserver slot ved \xe5 oppdatere last_run_at f\xf8rst.
            cfg.last_run_at = timezone.now()
            cfg.save(update_fields=['last_run_at'])

            backup = create_backup(
                slug=slug, kind=KIND_AUTO,
                note='Automatisk (in-process)',
            )
            purged = enforce_cap(slug, cfg.max_backups)
            if backup is None:
                logger.info(
                    'backup_scheduler[%s]: hoppet over (identisk innhold). '
                    'Slettet %d gamle.', slug, purged,
                )
            else:
                logger.info(
                    'backup_scheduler[%s]: OK %s (%d bytes). Slettet %d gamle.',
                    slug, backup.filename, backup.size_bytes, purged,
                )
    except Exception:
        logger.exception('backup_scheduler[%s]: feil under automatisk backup', slug)


def _run_all_modules() -> None:
    """Iterer alle aktive ModuleBackupConfig og kj\xf8r backup der det trengs.

    Kalt fra bakgrunnstr\xe5d i ``maybe_run_backup``.
    """
    global _is_running
    try:
        from core.backup import get_handler
        from core.models import ModuleBackupConfig

        active_configs = ModuleBackupConfig.objects.filter(enabled=True)
        for cfg in active_configs:
            if get_handler(cfg.module_slug) is None:
                continue
            if not _should_run_now(cfg):
                continue
            _run_backup_for_module(cfg.module_slug)
    finally:
        with _running_lock:
            _is_running = False


def maybe_run_backup() -> None:
    """Hoved-inngangspunkt. Kalt fra middleware ved hver request.

    Returnerer raskt uten \xe5 blokkere. Selve backupen kj\xf8res i en
    bakgrunnstr\xe5d hvis det er tid for en eller flere moduler.
    """
    global _last_check_ts, _is_running

    # Throttle: maks \xe9n sjekk per _THROTTLE_SECONDS per prosess.
    now = time.monotonic()
    with _check_lock:
        if now - _last_check_ts < _THROTTLE_SECONDS:
            return
        _last_check_ts = now

    # Unng\xe5 flere samtidige bakgrunnstr\xe5der i samme prosess.
    with _running_lock:
        if _is_running:
            return
        _is_running = True

    # Rask sjekk om det finnes minst \xe9n aktiv konfig som faktisk trenger backup.
    # (Sparer oss for en bakgrunnstr\xe5d hvis ingenting er due.)
    try:
        from core.backup import get_handler
        from core.models import ModuleBackupConfig

        any_due = False
        for cfg in ModuleBackupConfig.objects.filter(enabled=True):
            if get_handler(cfg.module_slug) is None:
                continue
            if _should_run_now(cfg):
                any_due = True
                break

        if not any_due:
            with _running_lock:
                _is_running = False
            return
    except Exception:
        # Hvis vi ikke kan sp\xf8rre DB (f.eks. under migrate), gi opp stille.
        with _running_lock:
            _is_running = False
        return

    # Kj\xf8r backup i bakgrunnstr\xe5d slik at request-latency ikke p\xe5virkes.
    t = threading.Thread(target=_run_all_modules, daemon=True)
    t.start()
