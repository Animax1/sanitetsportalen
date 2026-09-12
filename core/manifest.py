"""Web-app-manifestet og ikonene — «legg til på hjem-skjermen».

Manifestet er en view og ikke en statisk fil fordi ikonstiene går gjennom
`{% static %}`: WhiteNoise hasher filnavnene i prod, og en JSON-fil med
`/static/img/logo-192.png` skrevet inn ville pekt på et navn som ikke
finnes etter `collectstatic`.

**Ingen innlogging.** Nettleseren henter manifestet uten cookies, og et
manifest bak innloggingen er et manifest som ikke finnes. Det inneholder
bare navn, farger og ikonstier.

Merket (`static/img/logo.svg`) er et skjold med en person i — vern om
folk. Bevisst uten kors: et rødt kors på hvitt er Røde Kors-emblemet og
beskyttet, og et hvitt kors på farget flate leser som apotek eller
førstehjelpsskilt. Første utkast var en ring med pulslinje; André leste
den som EKG og ville ha noe subtilt (12. sep. 2026).
"""
from django.http import JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

# Samme blå som portalens header (`--portal-header-bg`) og bakgrunn
# (`--portal-bg`) i base_portal.html — appen skal se ut som seg selv i
# oppgavebytteren og bak splash-skjermen.
TEMAFARGE = '#0f3460'
BAKGRUNN = '#0f172a'

# (sti under static/, sizes, type, purpose). Kildenavnene — `static()` gir
# de hashede.
IKONER = (
    ('img/logo.svg', 'any', 'image/svg+xml', None),
    ('img/logo-192.png', '192x192', 'image/png', None),
    ('img/logo-512.png', '512x512', 'image/png', None),
    ('img/logo-maskable-512.png', '512x512', 'image/png', 'maskable'),
)


def _ikon(sti, sizes, type_, purpose):
    ikon = {'src': static(sti), 'sizes': sizes, 'type': type_}
    if purpose:
        ikon['purpose'] = purpose
    return ikon


def manifest_data() -> dict:
    return {
        'name': 'Sanitetsportalen',
        # Samme navn begge steder (André, 12. sep. 2026). Kortnavnet er det
        # som står under ikonet på hjem-skjermen.
        'short_name': 'Sanitetsportalen',
        'description': 'Pasientregistrering, oppdrag, vaktliste og statistikk for sanitetsvakten.',
        'lang': 'no',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'any',
        'theme_color': TEMAFARGE,
        'background_color': BAKGRUNN,
        'icons': [_ikon(*i) for i in IKONER],
    }


@require_safe
@cache_control(max_age=86400)
def manifest_view(request):
    return JsonResponse(manifest_data(), content_type='application/manifest+json')
