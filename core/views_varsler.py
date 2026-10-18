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


def _flere_portaler(user) -> bool:
    """Bjella står utenfor portalene (`UTENFOR_PORTAL`), så varslene fra alle
    portalene kontoen er med i, står i samme liste — og må si hvor de hører til."""
    from core.portal import mulige_portaler
    return mulige_portaler(user).count() > 1

@login_required
@require_GET
def notification_unread_count_view(request):
    """JSON-endepunkt for bjelle-badge: { "unread": <int> }.

    Pollet av JS i base_portal.html hvert 30. sekund. Kun innloggede
    brukere, bruker en effektiv COUNT-query.

    **Bærer også admins statusmelding** (11. okt. 2026, `core/statusmelding.py`):
    bjella poller alt på hver innlogget side, så meldingen kommer fram uten
    sidelasting og uten en forespørsel til.
    """
    from django.http import JsonResponse
    from core.models import Notification
    from core.statusmelding import aktiv
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'unread': count, 'statusmelding': aktiv()})


@login_required
@require_GET
def notification_list_view(request):
    """Varselside: paginert liste over varsler for innlogget bruker.

    Default: nyeste først, paginert 50 per side. Klikk på et varsel
    går til /varsler/<id>/lest/ som markerer som lest og redirecter
    til varselets URL.
    """
    from core.models import Notification
    qs = (Notification.objects.filter(user=request.user).select_related('portal')
          .order_by('-created_at'))
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    unread_total = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'core/notification_list.html', {
        'page_obj': page_obj,
        'unread_total': unread_total,
        'vis_portal': _flere_portaler(request.user),
    })


def _bytt_til_varselets_portal(request, notif):
    """Stå i portalen varselet hører til før lenken åpnes (fase 5c, §4.4).

    Lenken i et varsel fra Brann er en sti som `/oppdrag/`, og den gjelder
    portalen sesjonen står i — uten byttet ville Kari sett Standards oppdrag
    under et varsel om Branns. Varselsidene står utenfor portalregelen, så
    byttet skjer her, før omdirigeringen. Er kontoen ikke lenger med i portalen,
    åpnes ingenting: svaret er lista, med grunnen.
    """
    from core.portal import SESJON_NOKKEL, mulige_portaler

    if not notif.portal_id or request.session.get(SESJON_NOKKEL) == notif.portal_id:
        return None
    mulige = list(mulige_portaler(request.user))
    if not any(p.pk == notif.portal_id for p in mulige):
        messages.warning(request, f'Varselet hører til «{notif.portal.navn}», som du ikke '
                                  'lenger er med i.')
        return redirect('core:notification_list')
    request.session[SESJON_NOKKEL] = notif.portal_id
    if len(mulige) > 1:
        messages.info(request, f'Du står nå i portalen «{notif.portal.navn}».')
    return None


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
    stopp = _bytt_til_varselets_portal(request, notif)
    if stopp is not None:
        return stopp
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
    qs = (Notification.objects.filter(user=request.user).select_related('portal')
          .order_by('-created_at')[:10])
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    flere = _flere_portaler(request.user)
    from core.portal import SESJON_NOKKEL
    her = request.session.get(SESJON_NOKKEL)
    return JsonResponse({
        'notifications': [
            {
                'id': n.pk,
                'title': n.title,
                'message': n.message,
                'url': n.url,
                'module_slug': n.module_slug,
                # Portalnavnet bare når kontoen har flere — med én er det støy.
                'portal': n.portal.navn if flere and n.portal else '',
                # Bjella navigerer da i stedet for å merke lest der man står:
                # lenken gjelder en annen portal (`_bytt_til_varselets_portal`).
                'annen_portal': bool(flere and n.portal_id and n.portal_id != her),
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
