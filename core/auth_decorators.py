"""Felles tilgangskontroll for sanitetsportalen.

Inneholder rolle-hierarkiet, has_role_at_least() og dekorator-snarveier
som tidligere lå i accounts/decorators.py og patients/services.py.

Begge stedene re-eksporterer fortsatt de samme navnene, slik at ingen
eksisterende import brekker. Nye apps SKAL importere herfra direkte.

Rollehierarki:
    read_only   – kun lesing av pasientliste/tavle
    read_write  – kan lese/skrive pasienter (ingen statistikk-dashboard)
    lead_view   – kan lese pasienter og se statistikk, IKKE skrivetilgang
    lead        – kan lese/skrive pasienter og se full statistikk
    admin       – full tilgang (brukeradmin, audit, nullstill, arkiv)
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


# ── Rolle-hierarki ───────────────────────────────────────────────────────────

ROLE_HIERARKI = {
    'read_only': 0,
    'read_write': 1,
    'lead_view': 2,
    'lead': 3,
    'admin': 4,
}


def has_role_at_least(user, min_role):
    """Returner True hvis user har min_role eller høyere rolle.

    False hvis brukeren ikke er autentisert eller ikke har en kjent rolle.
    Trygg å kalle med AnonymousUser eller en bruker uten role-attributt.
    """
    if not user.is_authenticated:
        return False
    return (
        ROLE_HIERARKI.get(getattr(user, 'role', None), -1)
        >= ROLE_HIERARKI.get(min_role, 99)
    )


# ── Decorator ────────────────────────────────────────────────────────────────

def role_required(*roles):
    """Dekorator som krever at innlogget bruker har én av de angitte rollene.

    Gir 403 Forbudt hvis rollen mangler. Krever automatisk at brukeren
    er innlogget (login_required wrappes innenfor).
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ── Snarveier ────────────────────────────────────────────────────────────────

# Full administrativ tilgang (brukeradmin, audit, nullstill).
admin_required = role_required('admin')

# Skrivetilgang til pasienter: admin, lead, read_write (IKKE lead_view).
write_required = role_required('admin', 'lead', 'read_write')

# Statistikk-dashboard og full oversikt: admin, lead, lead_view.
stats_required = role_required('admin', 'lead', 'lead_view')

# Kan se andre år/datasett: admin, lead, lead_view.
dataset_scope_all = role_required('admin', 'lead', 'lead_view')
