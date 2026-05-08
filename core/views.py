"""Views for core-appen (Sanitetsportal-skall).

Inneholder:
- Portal-dashboard på ``/`` (Fase 2)
- Legacy-redirects fra gamle root-URL-er (Fase 2)
- Admin-UI for moduler og auditlogg (Fase 3b)
- Min profil-side for vanlige brukere (Fase 3b)
"""
from __future__ import annotations

import csv
from datetime import timedelta
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.decorators import admin_required
from accounts.models import CustomUser, LoginEvent
from audit.models import AuditLog
from core.forms import ModuleSettingsForm
from core.models import ModuleSettings
from core.modules import get_all_modules, get_dashboard_modules, get_module


# ─────────────────────────────────────────────────────────────────────────────
# Portal-dashboard
# ─────────────────────────────────────────────────────────────────────────────


@login_required
@require_GET
def portal_dashboard_view(request):
    """Portal-forside med oversikt over moduler.

    Vises på `/`. Krever innlogging — uautentiserte brukere blir sendt til
    login-siden via `@login_required`. Etter innlogging redirecter Django
    automatisk tilbake hit (settings.LOGIN_REDIRECT_URL = '/').

    Modul-kortene leses fra ``core.modules``-registret og filtreres på:
    - ``ModuleSettings.enabled`` (admin kan toggle moduler i sanntid)
    - Brukerens ``permission_flag`` på CustomUser (admin ser alt)
    - ``Module.show_in_dashboard``
    """
    modules = get_dashboard_modules(request.user)
    return render(request, 'core/dashboard.html', {'modules': modules})


# ─────────────────────────────────────────────────────────────────────────────
# Min profil — for vanlige brukere
# ─────────────────────────────────────────────────────────────────────────────


@login_required
@require_GET
def profile_view(request):
    """Min profil-side med permissions, moduler og aktivitetslogg.

    Viser:
    - Brukerens rolle og 5 modul-permissions
    - Modulene brukeren har tilgang til
    - Siste 10 innloggingshendelser (LoginEvent)
    - Sikkerhetsstatus (MFA, sist endret passord)

    Tilgjengelig for alle innloggede brukere.
    """
    user = request.user

    # Hent permissions som liste av (label, value) for visning
    permissions = [
        ('Pasientregistrering', getattr(user, 'kan_redigere_pasienter', False)),
        ('Vakter', getattr(user, 'kan_redigere_vakter', False)),
        ('Utstyr', getattr(user, 'kan_redigere_utstyr', False)),
        ('Rapport', getattr(user, 'kan_se_rapport', False)),
        ('Beredskap', getattr(user, 'kan_redigere_beredskap', False)),
    ]

    # Moduler brukeren har tilgang til (skjul kjernemoduler uten dashboard)
    visible_modules = get_dashboard_modules(user)

    # Aktivitetslogg: siste 10 innlogginger (alle event-typer)
    recent_events = (
        LoginEvent.objects
        .filter(user=user)
        .order_by('-created_at')[:10]
    )

    # Antall vellykkede innlogginger siste 7 dager
    one_week_ago = timezone.now() - timedelta(days=7)
    weekly_login_count = LoginEvent.objects.filter(
        user=user,
        success=True,
        event_type=LoginEvent.EVENT_LOGIN,
        created_at__gte=one_week_ago,
    ).count()

    return render(request, 'core/profile.html', {
        'permissions': permissions,
        'visible_modules': visible_modules,
        'recent_events': recent_events,
        'weekly_login_count': weekly_login_count,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Admin: modul-administrasjon
# ─────────────────────────────────────────────────────────────────────────────


@admin_required
@require_GET
def module_admin_list_view(request):
    """Liste over alle moduler med toggle-status.

    Bygger listen fra ``core.modules``-registret slik at admin alltid ser
    alle registrerte moduler — ikke bare de som har en
    ``ModuleSettings``-rad. ``ensure_defaults_exist()`` skal i praksis ha
    sikret at alle har en rad, men vi viser ``None`` defensivt for å
    unngå feil på en delvis migrert DB.
    """
    settings_by_slug = {
        s.slug: s for s in ModuleSettings.objects.all()
    }
    rows = []
    for modul in get_all_modules():
        rows.append({
            'module': modul,
            'settings': settings_by_slug.get(modul.slug),
        })
    return render(request, 'core/module_admin_list.html', {'rows': rows})


@admin_required
@require_http_methods(['GET', 'POST'])
def module_admin_edit_view(request, slug: str):
    """Rediger én ``ModuleSettings``-rad.

    Henter raden via ``slug`` (URL-parameter), validerer mot ``ModuleSettingsForm``
    og lagrer med ``updated_by=request.user``. Ved POST-suksess redirecter til
    listevisningen med en messages.success-melding.
    """
    settings_obj = get_object_or_404(ModuleSettings, slug=slug)
    modul = get_module(slug)  # kan være None hvis modul fjernet fra kode

    if request.method == 'POST':
        form = ModuleSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(
                request,
                f'Innstillingene for «{modul.name if modul else slug}» er oppdatert.',
            )
            return redirect('core:module_admin_list')
    else:
        form = ModuleSettingsForm(instance=settings_obj)

    return render(request, 'core/module_admin_edit.html', {
        'form': form,
        'settings_obj': settings_obj,
        'module': modul,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Admin: auditlogg-visning
# ─────────────────────────────────────────────────────────────────────────────


def _filter_audit_queryset(request) -> tuple:
    """Bygg filtrert AuditLog-queryset fra GET-parametre.

    Returnerer ``(queryset, filters_dict)`` slik at template kan
    re-rendre filter-skjemaet med eksisterende verdier.
    """
    qs = AuditLog.objects.select_related('user').all()

    app_label = (request.GET.get('app_label') or '').strip()
    action = (request.GET.get('action') or '').strip()
    user_id = (request.GET.get('user') or '').strip()
    date_from = (request.GET.get('date_from') or '').strip()
    date_to = (request.GET.get('date_to') or '').strip()
    search = (request.GET.get('q') or '').strip()

    if app_label:
        qs = qs.filter(app_label=app_label)
    if action:
        qs = qs.filter(action=action)
    if user_id:
        try:
            qs = qs.filter(user_id=int(user_id))
        except (TypeError, ValueError):
            pass
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if search:
        qs = qs.filter(
            Q(table_name__icontains=search)
            | Q(field_name__icontains=search)
            | Q(old_value__icontains=search)
            | Q(new_value__icontains=search),
        )

    filters = {
        'app_label': app_label,
        'action': action,
        'user': user_id,
        'date_from': date_from,
        'date_to': date_to,
        'q': search,
    }
    return qs, filters


@admin_required
@require_GET
def audit_log_list_view(request):
    """Paginert visning av AuditLog med filter.

    Filtre (alle som GET-parametre):
    - ``app_label``: matcher AuditLog.app_label eksakt
    - ``action``: CREATE / UPDATE / DELETE
    - ``user``: bruker-ID
    - ``date_from`` / ``date_to``: ISO-dato (YYYY-MM-DD)
    - ``q``: fritekstsøk i table_name, field_name, old_value, new_value
    """
    qs, filters = _filter_audit_queryset(request)
    qs = qs.order_by('-created_at')

    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Distinkte app_labels for filter-dropdown
    distinct_app_labels = (
        AuditLog.objects
        .exclude(app_label='')
        .values_list('app_label', flat=True)
        .distinct()
        .order_by('app_label')
    )

    return render(request, 'core/audit_log_list.html', {
        'page_obj': page_obj,
        'filters': filters,
        'distinct_app_labels': distinct_app_labels,
        'all_users': CustomUser.objects.order_by('username'),
        'action_choices': AuditLog.ACTION_CHOICES,
        'total_count': paginator.count,
    })


@admin_required
@require_GET
def audit_log_csv_export_view(request):
    """CSV-eksport av filtrert AuditLog.

    Bruker samme filter som listen, men har en hard grense på 5000 rader for
    å hindre at admin tilfeldigvis dumper hele tabellen (kan ha millioner
    av rader). Hvis treffmengden er større blir det en feilmelding og
    redirect tilbake til listen med oppfordring om å snevre inn filteret.
    """
    qs, _filters = _filter_audit_queryset(request)
    total = qs.count()
    MAX_ROWS = 5000

    if total > MAX_ROWS:
        messages.error(
            request,
            f'CSV-eksport er begrenset til {MAX_ROWS:,} rader. '
            f'Filteret ditt matcher {total:,} rader — snevre inn dato eller app.',
        )
        # Bevar GET-parametre i redirect
        qs_string = request.GET.urlencode()
        url = '/portal-admin/auditlog/'
        if qs_string:
            url = f'{url}?{qs_string}'
        return redirect(url)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = (
        f'attachment; filename="auditlog_{timestamp}.csv"'
    )

    # UTF-8 BOM så Excel åpner med riktig tegnsett
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Tidspunkt', 'App', 'Tabell', 'Post-ID', 'Handling',
        'Felt', 'Gammel verdi', 'Ny verdi', 'Bruker', 'IP',
    ])

    # Iterator + select_related for å unngå minnesprett
    for row in qs.order_by('-created_at').iterator(chunk_size=500):
        writer.writerow([
            row.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            row.app_label or '',
            row.table_name,
            row.record_id,
            row.action,
            row.field_name or '',
            row.old_value or '',
            row.new_value or '',
            row.user.username if row.user else '',
            row.ip or '',
        ])

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Legacy-redirects (Fase 2 — uendret)
# ─────────────────────────────────────────────────────────────────────────────


def legacy_root_redirect(request, subpath: str = '') -> HttpResponse:
    """Redirect en gammel root-URL til den nye `/pasienter/`-versjonen.

    Args:
        subpath: Den delen av URL-en som kommer ETTER prefikset som ble
                 fjernet. F.eks. for `/api/patients/` er subpath = "patients/".

    Returnerer 301 Moved Permanently og bevarer query string.
    """
    new_path = '/pasienter' + request.path
    if request.META.get('QUERY_STRING'):
        new_path = f"{new_path}?{request.META['QUERY_STRING']}"
    return HttpResponsePermanentRedirect(new_path)


# ─────────────────────────────────────────────────────────────────────────────
# Fase 4: Backup-admin
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
@require_GET
def backup_admin_overview_view(request):
    """Oversikt: alle moduler med backup-handler + status.

    Viser én rad per modul: konfig (intervall, enabled, max_backups),
    siste-kjørt-tid og antall backuper på disk.
    """
    from core.backup import all_handlers
    from core.models import ModuleBackupConfig
    from patients.models import Backup

    handlers = all_handlers()
    # Sørg for at det finnes en konfig per registrert modul.
    for h in handlers:
        ModuleBackupConfig.get_or_default(h.slug)

    rows = []
    for h in handlers:
        cfg = ModuleBackupConfig.objects.get(module_slug=h.slug)
        backup_count = Backup.objects.filter(module_slug=h.slug).count()
        rows.append({
            'slug': h.slug,
            'display_name': h.display_name or h.slug,
            'config': cfg,
            'backup_count': backup_count,
        })

    return render(request, 'core/backup_admin_overview.html', {
        'rows': rows,
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def backup_admin_module_view(request, slug: str):
    """Per-modul backup-side: rediger konfig + se backup-liste."""
    from core.backup import all_handlers, get_handler
    from core.forms import ModuleBackupConfigForm
    from core.models import ModuleBackupConfig
    from patients.models import Backup

    handler = get_handler(slug)
    if handler is None:
        messages.error(request, f'Ingen backup-handler registrert for «{slug}».')
        return redirect('core:backup_admin_overview')

    cfg = ModuleBackupConfig.get_or_default(slug)

    if request.method == 'POST':
        form = ModuleBackupConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Backup-innstillinger for «{handler.display_name or slug}» lagret.',
            )
            return redirect('core:backup_admin_module', slug=slug)
    else:
        form = ModuleBackupConfigForm(instance=cfg)

    backups = (
        Backup.objects
        .filter(module_slug=slug)
        .order_by('-created_at')[:200]
    )

    return render(request, 'core/backup_admin_module.html', {
        'slug': slug,
        'handler': handler,
        'config': cfg,
        'form': form,
        'backups': backups,
        'backup_count': Backup.objects.filter(module_slug=slug).count(),
        'all_handlers': all_handlers(),
    })


@admin_required
@require_http_methods(['POST'])
def backup_admin_run_view(request, slug: str):
    """Trigger en manuell backup for modulen NÅ."""
    from core.backup import KIND_MANUAL, create_backup, enforce_cap, get_handler
    from core.models import ModuleBackupConfig

    handler = get_handler(slug)
    if handler is None:
        messages.error(request, f'Ingen backup-handler for «{slug}».')
        return redirect('core:backup_admin_overview')

    try:
        backup = create_backup(
            slug=slug, kind=KIND_MANUAL, user=request.user,
            note=f'Manuelt startet av {request.user.username}',
        )
        cfg = ModuleBackupConfig.get_or_default(slug)
        purged = enforce_cap(slug, cfg.max_backups)
        if backup is None:
            # Burde aldri skje for manual, men vi er defensive.
            messages.info(request, 'Ingen ny backup ble lagret.')
        else:
            msg = f'Backup laget: {backup.filename}'
            if purged:
                msg += f' (slettet {purged} eldre).'
            messages.success(request, msg)
    except Exception as exc:  # noqa: BLE001 — vises i UI
        messages.error(request, f'Backup feilet: {exc}')

    return redirect('core:backup_admin_module', slug=slug)


@admin_required
@require_http_methods(['GET', 'POST'])
def backup_admin_restore_view(request, slug: str, pk: int):
    """Restore-flyt med slug-bekreftelse + audit-log-oppføring."""
    from core.backup import get_handler, restore_backup
    from core.forms import BackupRestoreConfirmForm
    from patients.models import Backup
    from audit.models import AuditLog

    handler = get_handler(slug)
    if handler is None:
        messages.error(request, f'Ingen backup-handler for «{slug}».')
        return redirect('core:backup_admin_overview')

    backup = get_object_or_404(Backup, pk=pk, module_slug=slug)

    if request.method == 'POST':
        form = BackupRestoreConfirmForm(request.POST, expected_slug=slug)
        if form.is_valid():
            try:
                restore_backup(backup, user=request.user)
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f'Restore feilet: {exc}')
                return redirect('core:backup_admin_module', slug=slug)

            # Logg restore-handlingen i audit-log.
            AuditLog.objects.create(
                table_name=f'{slug}_backup_restore',
                record_id=backup.pk,
                action='UPDATE',
                user=request.user,
                app_label='core',
                field_name='restore',
                old_value='',
                new_value=backup.filename,
            )
            messages.success(
                request,
                f'Modul «{handler.display_name or slug}» gjenopprettet '
                f'fra {backup.filename}. Et pre-restore-snapshot ble laget '
                'først som sikkerhetsnett.',
            )
            return redirect('core:backup_admin_module', slug=slug)
    else:
        form = BackupRestoreConfirmForm(expected_slug=slug)

    return render(request, 'core/backup_admin_restore.html', {
        'slug': slug,
        'handler': handler,
        'backup': backup,
        'form': form,
    })


@admin_required
@require_GET
def backup_admin_download_view(request, slug: str, pk: int):
    """Last ned en backup-fil som application/gzip."""
    from core.backup import get_backup_dir
    from patients.models import Backup

    backup = get_object_or_404(Backup, pk=pk, module_slug=slug)
    path = get_backup_dir() / backup.filename
    if not path.exists():
        messages.error(request, f'Filen «{backup.filename}» mangler på disk.')
        return redirect('core:backup_admin_module', slug=slug)

    # Streamer ikke — backups er typisk små (< 50 MB), og enklere å lese
    # hele i minne enn å håndtere chunked transfer + close-callbacks.
    response = HttpResponse(
        path.read_bytes(),
        content_type='application/gzip',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="{backup.filename}"'
    )
    return response


@admin_required
@require_http_methods(['POST'])
def backup_admin_delete_view(request, slug: str, pk: int):
    """Slett én enkelt backup-fil + DB-rad."""
    from core.backup import get_backup_dir
    from patients.models import Backup

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
    return redirect('core:backup_admin_module', slug=slug)
