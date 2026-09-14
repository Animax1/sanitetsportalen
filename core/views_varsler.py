"""Varsler: liste, lesemerking og JSON-API-et bjella bruker.

Delt ut av `core/views.py` 14. sep. 2026 (gjeldspunkt 3.7).
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.url_safety import safe_redirect_url


# ─────────────────────────────────────────────────────────────────────────────
# Fase 5: Varsler (notifications)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_GET
def notification_unread_count_view(request):
    """JSON-endepunkt for bjelle-badge: { "unread": <int> }.

    Pollet av JS i base_portal.html hvert 30. sekund. Kun innloggede
    brukere, bruker en effektiv COUNT-query.
    """
    from django.http import JsonResponse
    from core.models import Notification
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'unread': count})


@login_required
@require_GET
def notification_list_view(request):
    """Varselside: paginert liste over varsler for innlogget bruker.

    Default: nyeste først, paginert 50 per side. Klikk på et varsel
    går til /varsler/<id>/lest/ som markerer som lest og redirecter
    til varselets URL.
    """
    from core.models import Notification
    qs = Notification.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    unread_total = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'core/notification_list.html', {
        'page_obj': page_obj,
        'unread_total': unread_total,
    })


@login_required
@require_http_methods(['POST', 'GET'])
def notification_mark_read_view(request, pk: int):
    """Marker et varsel som lest, redirect til varselets URL.

    GET støttes så vanlige <a>-lenker fungerer. Det er trygt fordi
    handlingen kun påvirker brukerens egne varsler og er idempotent.
    POST anbefales for forms.
    """
    from core.models import Notification
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'read_at'])
    # S4: Notification.url er et CharField uten validator. I dag settes den kun
    # fra patients/signals.py med hardkodede relative stier, men notify() er
    # eksplisitt designet som et generisk API for framtidige moduler. Første
    # modul som lar brukerinput påvirke url-en ville gjort dette til en ekte
    # lagret open redirect — med en lenke som ser ut til å komme fra portalen.
    return redirect(safe_redirect_url(request, notif.url, '/varsler/'))


@login_required
@require_http_methods(['POST'])
def notification_mark_all_read_view(request):
    """Marker ALLE uleste varsler for brukeren som lest."""
    from core.models import Notification
    updated = Notification.objects.filter(
        user=request.user, is_read=False,
    ).update(is_read=True, read_at=timezone.now())
    if updated:
        messages.success(request, f'Markerte {updated} varsler som lest.')
    else:
        messages.info(request, 'Ingen uleste varsler å markere.')
    return redirect('core:notification_list')


# ── JSON API for dropdown-bjelle ──────────────────────────────────────────────

@login_required
@require_GET
def notification_api_list_view(request):
    """JSON: siste 10 varsler for innlogget bruker.

    Brukes av notifications.js for å populere dropdown-panelet.
    Returnerer { notifications: [...], unread_count: int }.
    """
    from django.http import JsonResponse
    from core.models import Notification
    qs = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({
        'notifications': [
            {
                'id': n.pk,
                'title': n.title,
                'message': n.message,
                'url': n.url,
                'module_slug': n.module_slug,
                'level': n.level,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in qs
        ],
        'unread_count': unread_count,
    })


@login_required
@require_POST
def notification_api_mark_read_view(request, pk: int):
    """JSON: marker ett varsel som lest. Brukes av dropdown inline.

    Returnerer { ok: true, unread_count: int } etter oppdatering.
    """
    from django.http import JsonResponse
    from core.models import Notification
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'read_at'])
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'ok': True, 'unread_count': unread_count})


@login_required
@require_POST
def notification_api_mark_all_read_view(request):
    """JSON: marker alle uleste varsler som lest.

    Returnerer { ok: true, updated: int }.
    """
    from django.http import JsonResponse
    from core.models import Notification
    updated = Notification.objects.filter(
        user=request.user, is_read=False,
    ).update(is_read=True, read_at=timezone.now())
    return JsonResponse({'ok': True, 'updated': updated})
