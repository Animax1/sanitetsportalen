"""Backup-admin: én side for planer, filer, kjøring og gjenoppretting.

Delt ut av `core/views.py` 14. sep. 2026 (gjeldspunkt 3.7).

Selve logikken ligger i `core/backup/`; her er bare flaten. Gjenopprettingens
auditrad skrives av `restore_backup`, ikke her — se den funksjonens docstring:
katastrofeveien går gjennom kommandolinja, og skulle ikke vært den eneste uten
spor.
"""
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core.auth_decorators import admin_required
from core.ratelimit import rate_limit


# ─────────────────────────────────────────────────────────────────────────────
# Fase 4: Backup-admin
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
@require_GET
def backup_admin_view(request):
    """Hele backup-administrasjonen på én side.

    Erstattet oversikt + én side per modul + egen gjenopprettingsside
    (13. sep. 2026). Den gamle inndelingen kostet fire runder for å ta backup
    av alt og fem steg for å gjenopprette; nå står planene, filene og
    handlingene på samme side, og hver modul folder seg ut der den står.

    Gjenopprettingen har fortsatt sin egen side med bekreftelse. Den er ikke
    det som var tungvint — den er den ene handlingen her som sletter rader, og
    den skal koste et bevisst klikk.
    """
    from core.backup.oversikt import sideinnhold
    from core.forms import BackupplanForm

    return render(request, 'core/backup_admin.html', sideinnhold(BackupplanForm))


@admin_required
@require_http_methods(['POST'])
def backup_admin_plan_view(request, slug: str):
    """Lagre én plan — standardplanen eller en modul sin egen."""
    from core.forms import BackupplanForm
    from core.models import Backupplan

    from core.backup import get_handler

    if slug != Backupplan.STANDARD_SLUG and get_handler(slug) is None:
        messages.error(request, f'Ingen backup-handler for «{slug}».')
        return redirect('portaladmin:backup_admin')

    plan = Backupplan.hent(slug)
    form = BackupplanForm(request.POST, instance=plan, prefix=slug)
    if form.is_valid():
        form.save()
        messages.success(request, f'Backupplanen for «{slug}» er lagret.')
    else:
        # Feltfeilene går tapt i omdirigeringen, så de skrives ut her. Et
        # skjema som stille ikke lagret er verre enn en melding. Etiketten
        # brukes, ikke feltnavnet: «intervall_verdi» er kodens navn på
        # «Intervall», og det er ikke brukeren som valgte det.
        for felt, feil in form.errors.items():
            etikett = form.fields[felt].label if felt in form.fields else felt
            messages.error(request, f'{etikett}: {" ".join(feil)}')
    return redirect('portaladmin:backup_admin')


@admin_required
@require_http_methods(['POST'])
@rate_limit(group='backup:run', rate='6/m', method='POST', on_limit='html')
def backup_admin_run_view(request, slug: str = ''):
    """Ta backup nå — av én modul, eller av alle når slug er tom.

    «Alle» er den knappen som gjorde de fire rundene overflødige.
    """
    from core.backup import KIND_MANUAL, create_backup, enforce_cap, get_handler
    from core.backup.klokke import planer
    from core.models import Backupplan

    if slug:
        if get_handler(slug) is None:
            messages.error(request, f'Ingen backup-handler for «{slug}».')
            return redirect('portaladmin:backup_admin')
        slugger = [slug]
    else:
        slugger = [s for s, _ in planer()]

    laget, feilet = [], []
    for s in slugger:
        try:
            backup = create_backup(
                slug=s, kind=KIND_MANUAL, user=request.user,
                note=f'Manuelt startet av {request.user.username}',
            )
            enforce_cap(s, Backupplan.hent(s).behold_effektiv)
            if backup is not None:
                laget.append(s)
        except Exception as exc:   # noqa: BLE001 — vises i UI
            feilet.append(f'{s}: {exc}')

    if laget:
        messages.success(
            request,
            f'Backup laget for {", ".join(laget)}.' if len(laget) > 1
            else f'Backup laget for {laget[0]}.')
    if feilet:
        messages.error(request, 'Feilet: ' + ' · '.join(feilet))
    if not laget and not feilet:
        messages.info(request, 'Ingen nye filer — innholdet var uendret.')
    return redirect('portaladmin:backup_admin')


@admin_required
@require_http_methods(['GET', 'POST'])
@rate_limit(group='backup:restore', rate='6/m', method='POST', on_limit='html')
def backup_admin_restore_view(request, slug: str, pk: int):
    """Gjenopprett én backup, bak en bekreftelse som sier hva som skjer."""
    from core.backup import get_handler, restore_backup
    from core.forms import BackupRestoreConfirmForm
    from core.models import Backup

    handler = get_handler(slug)
    if handler is None:
        messages.error(request, f'Ingen backup-handler for «{slug}».')
        return redirect('portaladmin:backup_admin')

    backup = get_object_or_404(Backup, pk=pk, module_slug=slug)

    if request.method == 'POST':
        form = BackupRestoreConfirmForm(request.POST, expected_slug=slug)
        if form.is_valid():
            try:
                # Auditraden skrives av tjenesten, ikke her: gjenoppretting har
                # to innganger, og katastrofeveien går gjennom kommandolinja.
                restore_backup(backup, user=request.user,
                               kilde='grensesnittet')
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f'Gjenoppretting feilet: {exc}')
                return redirect('portaladmin:backup_admin')
            messages.success(
                request,
                f'Modul «{handler.display_name or slug}» gjenopprettet '
                f'fra {backup.filename}. Et pre-restore-snapshot ble laget '
                'først som sikkerhetsnett.',
            )
            return redirect('portaladmin:backup_admin')
    else:
        form = BackupRestoreConfirmForm(expected_slug=slug)

    berort = _berorte_rader(handler)
    return render(request, 'core/backup_admin_restore.html', {
        'slug': slug,
        'handler': handler,
        'backup': backup,
        'form': form,
        'berort': berort,
        'berort_sum': sum(b['antall'] for b in berort),
    })


def _berorte_rader(handler) -> list[dict]:
    """Hva gjenopprettingen faktisk sletter, tabell for tabell.

    Bekreftelsen ba tidligere om modul-slugen uten å si hva som sto på spill.
    «Slett og erstatt» er et annet svar når man ser at det gjelder 1 240 rader
    i ni tabeller.
    """
    from django.apps import apps as django_apps

    ut = []
    for etikett in handler.get_restore_models():
        try:
            app_label, modellnavn = etikett.split('.')
            modell = django_apps.get_model(app_label, modellnavn)
            ut.append({
                'navn': modell._meta.verbose_name_plural or etikett,
                'antall': modell.objects.count(),
            })
        except Exception:   # noqa: BLE001 — en rad mindre er bedre enn 500
            continue
    return ut


@admin_required
@require_http_methods(['POST'])
def backup_admin_delete_view(request, slug: str, pk: int):
    """Slett én enkelt backup-fil + DB-rad."""
    from core.backup import get_backup_dir
    from core.models import Backup

    backup = get_object_or_404(Backup, pk=pk, module_slug=slug)
    path = get_backup_dir() / backup.filename
    filename = backup.filename
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            messages.warning(
                request,
                f'Kunne ikke slette filen på disk ({exc}). DB-rad fjernes likevel.',
            )
    backup.delete()
    messages.success(request, f'Slettet backup «{filename}».')
    return redirect('portaladmin:backup_admin')
