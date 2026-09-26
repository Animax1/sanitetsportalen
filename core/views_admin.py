"""Adminsidene: portalinnstillinger, moduloppsett og auditlogg.

Delt ut av `core/views.py` 14. sep. 2026 (gjeldspunkt 3.7). Backup-admin og
varsler ligger i `views_backup.py` og `views_varsler.py`.

Legacy-redirectene står her fordi de peker på adminstier.
"""
from __future__ import annotations

import csv
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from accounts.models import CustomUser
from audit.models import AuditLog
from core.auth_decorators import admin_required
from core.forms import ModuleSettingsForm
from core.models import ModuleSettings, Vakt
from core.modules import get_all_modules, get_module
from core.ratelimit import rate_limit
from core.validators import les_iso_dato


# ─────────────────────────────────────────────────────────────────────────────
# Admin: portalinnstillinger (§4.1)
# ─────────────────────────────────────────────────────────────────────────────


@admin_required
@require_http_methods(['GET', 'POST'])
def portal_settings_view(request):
    """Arrangementsnavn og sesjonstimeout.

    Begge lå under ``/pasienter/`` fordi pasientmodulen var den eneste som
    fantes. Ingen av dem hører til der: arrangementsnavnet gjelder vakten, som
    med flere moduler dekker mer enn pasientregistreringen, og
    sesjonstimeouten gjelder innloggingen.

    Flyttingen ble gjort sammen med rollemodellen fordi tilgangssjekkene deres
    uansett skulle skrives om — og fordi «admin-only-endepunkt inne i en
    modul» er nettopp den sammenblandingen ``ModulTilgang`` skal fjerne. Et
    endepunkt under ``/pasienter/`` som krever global admin sier at
    modulgrensen ikke betyr noe.

    ``AppSetting`` er en generisk nøkkel/verdi-tabell uten validering, så den
    ligger her: en timeout på 0 timer ville logget ut alle umiddelbart.
    """
    from core.models import AppSetting
    from core.portalinnstillinger import all_handlers
    from core.vakt import hent_aktiv_vakt

    # **Modulenes felter kommer gjennom registeret**, ikke gjennom en import
    # av modulen (14. sep. 2026). Fram til da sto `from vaktliste import fil`
    # her, med modulens validering og lagring midt i rammeverkets view. Se
    # `core/portalinnstillinger.py`.
    handlere = all_handlers()

    if request.method == 'POST':
        feil = False

        # ── Alt valideres, ingenting lagres ──────────────────────────────
        # Navnet skrives på `Vakt` og resten i `AppSetting`; ingen transaksjon
        # binder dem, så denne todelingen er det eneste som hindrer at en
        # avvist innsending lagrer halve skjemaet. Hver handler får si sitt
        # før noen skriver.
        try:
            timer = int((request.POST.get('session_timeout_hours') or '').strip())
        except (TypeError, ValueError):
            messages.error(request, 'Sesjonstimeout må være et helt tall.')
            feil = True
        else:
            if not 1 <= timer <= 24:
                messages.error(
                    request, 'Sesjonstimeout må være mellom 1 og 24 timer.')
                feil = True

        # Arrangementsnavnet ER den aktive vaktas navn siden deploy 2 — én
        # kilde.
        vakt = hent_aktiv_vakt()
        nytt_navn = (request.POST.get('event_name') or '').strip()
        if not nytt_navn:
            messages.error(request, 'Vakta må ha et navn.')
            feil = True
        elif Vakt.objects.filter(navn=nytt_navn).exclude(pk=vakt.pk).exists():
            messages.error(
                request,
                f'En annen vakt heter allerede «{nytt_navn}». '
                f'Legg på en dato eller velg et annet navn.')
            feil = True

        modulverdier = {}
        for handler in handlere:
            try:
                modulverdier[handler.slug] = handler.valider(request.POST)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                feil = True

        # ── Så lagres alt ────────────────────────────────────────────────
        if not feil:
            vakt.navn = nytt_navn
            vakt.save(update_fields=['navn'])
            AppSetting.set('session_timeout_hours', timer)
            for handler in handlere:
                handler.lagre(modulverdier[handler.slug])
            messages.success(request, 'Portalinnstillingene er lagret.')
            return redirect('portaladmin:portal_settings')

    try:
        timer = int(AppSetting.get('session_timeout_hours', 8))
    except (TypeError, ValueError):
        timer = 8

    kontekst = {
        'event_name': hent_aktiv_vakt().navn,
        'session_timeout_hours': timer,
        'innstillingsfragmenter': [h.mal for h in handlere if h.mal],
    }
    for handler in handlere:
        kontekst.update(handler.kontekst())
    return render(request, 'core/portal_settings.html', kontekst)


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
            return redirect('portaladmin:module_admin_list')
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
    # Et ugyldig datofilter ignoreres og vises tomt (B6) — ellers 500.
    fra_dato = les_iso_dato(request.GET.get('date_from'))
    til_dato = les_iso_dato(request.GET.get('date_to'))
    date_from = fra_dato.isoformat() if fra_dato else ''
    date_to = til_dato.isoformat() if til_dato else ''
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
    if fra_dato:
        qs = qs.filter(created_at__date__gte=fra_dato)
    if til_dato:
        qs = qs.filter(created_at__date__lte=til_dato)
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


def _csv_trygg(verdi):
    """Excel tolker celler som begynner med `=`, `+`, `-`, `@`, tab eller CR
    som formler — og verdiene her er brukerinnskrevne (13. sep. 2026, M9).
    Et innledende apostrof gjør cella til tekst."""
    verdi = verdi or ''
    return "'" + verdi if verdi[:1] in ('=', '+', '-', '@', '\t', '\r') else verdi


@admin_required
@require_GET
# S3: 5000 rader per kall, uten grense på antall kall. En admin som
# eksporterer manuelt trenger noen få i minuttet; alt over det er en
# klient i løkke som drar hele auditloggen ut av databasen.
@rate_limit(group='audit:csv-export', rate='10/m', method='GET',
            on_limit='html')
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
            _csv_trygg(row.old_value),
            _csv_trygg(row.new_value),
            row.user.username if row.user else '',
            row.ip or '',
        ])

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Gamle /api/-adresser (26. sep. 2026, D4)
# ─────────────────────────────────────────────────────────────────────────────

_flyttet_logg = logging.getLogger('core.api_flyttet')


def api_flyttet(request) -> HttpResponse:
    """410 for `/api/…`-adressene som flyttet til `/pasienter/api/` i fase 2.

    **Var en 301 til og med 26. sep. 2026.** En 301 gjør en POST om til en GET
    i nettleseren, så en gammel klient som lagret noe fikk et svar uten at
    noe ble lagret — stille. Ingen JS i portalen bruker adressene, og det som
    likevel treffer, skal feile synlig. **Hvert treff logges som advarsel**:
    `path=`-linjene i loggen tar bare trege forespørsler, så uten denne ville et
    gammelt kall vært usynlig i Railway.

    `/api/varsler/` og `/api/endringer/` har egne ruter foran denne.
    """
    _flyttet_logg.warning('Gammel /api/-adresse: %s %s', request.method, request.path)
    return JsonResponse({
        'error': 'Adressen er flyttet. Pasientmodulens API ligger under /pasienter/api/.',
    }, status=410)
