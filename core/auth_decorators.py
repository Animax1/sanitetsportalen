"""Felles tilgangskontroll for sanitetsportalen.

Inneholder modultilgangen og `admin_required`. Rollehierarkiet som lå her
falt med deploy 2, da `role` krympet til admin/bruker.

`accounts/decorators.py` re-eksporterer fortsatt `admin_required`, slik at
gammel import ikke brekker. Nye apps SKAL importere herfra direkte.

Tre kategorier (§3 i docs/BESLUTNING_ROLLEMODELLEN.md):
    global admin  – brukeradmin, backup, moduloppsett, audit, arkiv og alt
                    irreversibelt. Står utenfor modulaksen.
    modulbasert   – ModulTilgang(bruker, modul_slug, nivaa).
    globalt uten admin – innlogging, min profil, passordbytte, MFA.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


# ── Global admin ─────────────────────────────────────────────────────────────
#
# `ROLE_HIERARKI` og `has_role_at_least()` sto her fram til deploy 2. Hierarkiet
# var aldri et hierarki av rettigheter: `lead_view` lå over `read_write`, men
# hadde ikke skrivetilgang (§2.3). Det gikk godt så lenge helperen kun ble kalt
# med 'admin' — men den som skrev `has_role_at_least(user, 'read_write')` i
# neste modul ville gitt `lead_view` skrivetilgang uten å merke det.
#
# Med `role` krympet til admin/bruker er det ingenting å rangere. Bruk
# `er_global_admin()` for admin, og `har_tilgang()` for alt annet.


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
# Hvert trinn inneholder trinnene under seg — `har_tilgang(..., 'les')` er sant
# for alle fire. Et nytt trinn er derfor additivt for modulene som ikke
# deklarerer det: de tilbyr det ikke i matrisen, og ingen kan få det der.
NIVAA_HIERARKI = {
    'les': 0,
    'skriv_handling': 1,
    'skriv_full': 2,
    'skriv_leder': 3,
}

_TILGANG_CACHE = '_modultilgang_cache'
_MODUL_CACHE = '_aktive_moduler_cache'


def er_global_admin(user):
    """True for `role='admin'`. Global admin står utenfor modulaksen."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'role', None) == 'admin'


# ── Decorator ────────────────────────────────────────────────────────────────

def admin_required(view_func):
    """Krev global admin. Gir 403 ellers.

    Den eneste rollebaserte dekoratøren som står igjen. `write_required`,
    `stats_required` og `role_required` er borte: de tok en liste over de fem
    rolleverdiene, og de verdiene finnes ikke lenger. Ingen av dem sto på et
    view da de ble fjernet — modultilgang hadde overtatt hver enkelt.
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not er_global_admin(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


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
