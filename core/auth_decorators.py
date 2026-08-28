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
from django.http import JsonResponse


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

# `dataset_scope_all` sto her fram til 28. aug. 2026. Den var definert,
# re-eksportert i shimen og testet — men sto aldri på et view. Fjernet
# sammen med resten av §9-oppryddingen.


# ═════════════════════════════════════════════════════════════════════════════
# MODULTILGANG
#
# Erstatter de fem `kan_redigere_*`-flaggene. Flaggene var ikke
# tilgangskontroll: de leses kun av `Module.is_visible_for()`, altså dashboard
# og nav-meny, og en `read_write`-bruker uten `kan_redigere_pasienter` fikk
# **201 på POST /api/patients/**. Se docs/BESLUTNING_ROLLEMODELLEN.md §2.1.
#
# Tre kategorier, ikke to (§3):
#   1. Global admin   — brukeradmin, backup, moduloppsett, audit, arkiv og alt
#                       irreversibelt. Ett flagg, ingen modulakse.
#   2. Modulbasert    — denne tabellen.
#   3. Globalt uten admin — innlogging, min profil, passordbytte, MFA.
# ═════════════════════════════════════════════════════════════════════════════

# Ordnet stige. `ingen` finnes ikke som verdi — fravær av rad er ingen tilgang.
NIVAA_HIERARKI = {
    'les': 0,
    'skriv_handling': 1,
    'skriv_full': 2,
}

_TILGANG_CACHE = '_modultilgang_cache'
_MODUL_CACHE = '_aktive_moduler_cache'


def er_global_admin(user):
    """True for `role='admin'`. Global admin står utenfor modulaksen."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'role', None) == 'admin'


def tom_tilgangscache(user):
    """Glem det som er cachet på brukerobjektet.

    Cachen lever så lenge brukerobjektet gjør, altså normalt én request. Den
    må likevel kunne tømmes eksplisitt: admin som endrer en matrise og deretter
    leser tilgangen i samme request ville ellers fått det gamle svaret.
    """
    for navn in (_TILGANG_CACHE, _MODUL_CACHE):
        if hasattr(user, navn):
            delattr(user, navn)


def _tilganger(user):
    """{modul_slug: nivaa} for brukeren, hentet én gang per brukerobjekt.

    Nav-menyen kaller `is_visible_for` én gang per registrert modul. Uten
    cachen ville hver sidevisning gjort én spørring per modul.
    """
    cache = getattr(user, _TILGANG_CACHE, None)
    if cache is None:
        from accounts.models import ModulTilgang  # noqa: WPS433
        cache = dict(
            ModulTilgang.objects
            .filter(bruker=user)
            .values_list('modul_slug', 'nivaa')
        )
        setattr(user, _TILGANG_CACHE, cache)
    return cache


def _modul_er_aktiv(user, modul_slug):
    """False hvis modulen er slått av i ModuleSettings.

    Toggelen var tidligere en ren menybryter — `GET /pasienter/` ga 200 med
    modulen deaktivert (§2.2). Nå stenger den URL-en. Kjernemoduler kan ikke
    deaktiveres, og global admin slipper alltid inn: ellers kunne man
    deaktivere seg selv ut av å kunne reaktivere.
    """
    cache = getattr(user, _MODUL_CACHE, None)
    if cache is None:
        from core.models import ModuleSettings  # noqa: WPS433
        from core.modules import get_module  # noqa: WPS433
        cache = (ModuleSettings.get_enabled_slugs(), get_module)
        setattr(user, _MODUL_CACHE, cache)
    aktive, get_module = cache

    modul = get_module(modul_slug)
    if modul is not None and modul.is_core:
        return True
    return modul_slug in aktive


def nivaa_for(user, modul_slug):
    """Brukerens nivå på modulen, eller `None` for ingen tilgang.

    Global admin får høyeste nivå på alt. En deaktivert modul gir `None` for
    alle andre.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    if er_global_admin(user):
        return 'skriv_full'
    if not _modul_er_aktiv(user, modul_slug):
        return None
    return _tilganger(user).get(modul_slug)


def har_tilgang(user, modul_slug, nivaa='les'):
    """True hvis brukeren har `nivaa` eller høyere på modulen.

    Ukjent nivånavn gir False, ikke True — en skrivefeil i en dekoratør skal
    stenge døra, ikke åpne den.
    """
    kravet = NIVAA_HIERARKI.get(nivaa)
    if kravet is None:
        return False
    har = nivaa_for(user, modul_slug)
    if har is None:
        return False
    return NIVAA_HIERARKI.get(har, -1) >= kravet


def modul_kreves(modul_slug, nivaa='les', *, svar='html'):
    """Krev `nivaa` på `modul_slug`. Gir 403 ellers.

    Eksplisitt dekoratør framfor middleware på URL-prefiks: middleware er ett
    sted å glemme, men også ett sted å ta feil av `/pasienter/api/...`, og
    dekoratør matcher husets stil. Risikoen — en glemt dekoratør på et nytt
    endepunkt — lukkes av `ModulDekoratorTests`, som går gjennom
    `urlpatterns` og krever at hvert view er dekorert.

    `svar='json'` gir `{'error': ...}` med 403 i stedet for 403-siden, slik at
    et API-kall får en kropp klienten kan lese.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not har_tilgang(request.user, modul_slug, nivaa):
                if svar == 'json':
                    return JsonResponse({'error': 'Ingen tilgang'}, status=403)
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        # Leses av URL-gjennomgangstesten. Uten markøren måtte testen gjette
        # på om et view er dekorert, og en gjetning som tar feil den ene veien
        # slipper et udekorert endepunkt gjennom.
        wrapper._modul_kreves = (modul_slug, nivaa)
        return wrapper
    return decorator
