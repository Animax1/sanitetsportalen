"""Tilgangskontroll-dekoratorer basert på brukerrolle."""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def role_required(*roles):
    """
    Dekorator som krever at innlogget bruker har én av de angitte rollene.
    Gir 403 Forbudt hvis rollen mangler.
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


# Snarveier
# Rollehierarki:
#   admin       – full tilgang (brukeradmin, audit, nullstill)
#   lead        – kan lese/skrive pasienter og se full statistikk
#   lead_view   – kan lese pasienter og se statistikk, IKKE skrivetilgang
#   read_write  – kan lese/skrive pasienter (ingen statistikk-dashboard)
#   read_only   – kun lesing av pasientliste/tavle
admin_required = role_required('admin')

# Skrivetilgang: admin, lead, read_write (IKKE lead_view)
write_required = role_required('admin', 'lead', 'read_write')

# Statistikk/full oversikt: admin, lead, lead_view
stats_required = role_required('admin', 'lead', 'lead_view')

# Kan se andre år/datasett: admin, lead, lead_view
dataset_scope_all = role_required('admin', 'lead', 'lead_view')
