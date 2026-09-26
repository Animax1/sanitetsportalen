"""Rutene `scripts/sikkerhetssjekk.py` prøver, utledet av `urlpatterns`.

**Lista sto skrevet for hånd, og forfalt** (26. sep. 2026, B5). Den var fra
13. sep.: 111 av 186 ruter manglet — hele KO, backlog og deler av alt annet —
og tre av stiene den prøvde fantes ikke lenger. De ga 404, og 404 telte som
«stengt», så scriptet meldte grønt om ruter som ikke var der. En skanner som
melder grønt om en dekning den ikke har, er verre enn ingen skanner.

Scriptet kjører utenfra og bruker bare standardbiblioteket, så det kan ikke
lese rutene selv. Derfor genereres `scripts/sikkerhetsruter.json` her
(`python manage.py sikkerhetsruter`), og `core/tests_sikkerhetsruter.py`
krever at fila er i takt med `urlpatterns`. Hver rute prøves anonymt med
**både GET og POST** — da trenger ingen å vite hvilke metoder et view tar: en
rute som bare tar POST svarer 405 på GET, og det er «stengt».

Alt er stengt med mindre det står i `AAPNE` eller `OMDIRIGERER`, med grunn.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings
from django.urls import get_resolver

FIL = Path(settings.BASE_DIR) / 'scripts' / 'sikkerhetsruter.json'

#: Rute (mønsteret, som `urlpatterns` skriver det) → hvorfor den svarer uten innlogging.
AAPNE = {
    'healthz/': 'Railways helsesjekk',
    'robots.txt': 'søkemotorer',
    'manifest.webmanifest': 'ikonene, før innlogging — se core/manifest.py',
    'accounts/login/': 'innloggingen',
    'accounts/glemt-passord/': 'glemt passord, før innlogging',
    'accounts/reset/<str:token>/': 'lenken fra glemt passord — tokenet er tilgangen',
    'accounts/invitasjon/<str:token>/': 'invitasjonslenken — tokenet er tilgangen',
    'vaktliste/sw.js': 'service workeren; kan ikke kreve innlogging før den er installert',
}

#: Gamle adresser som sender videre. Skal aldri svare 200 — men 301 til en
#: annen side enn innloggingen er riktig her.
OMDIRIGERER = {
    '^admin/server-status/(?P<rest>.*)$': 'gammel server-status-adresse',
    'pasienter/^admin/server-status/(?P<rest>.*)$': 'gammel server-status-adresse',
    'accounts/users/': 'brukeradmin flyttet til /portal-admin/brukere/',
    'accounts/users/ny/': 'brukeradmin flyttet til /portal-admin/brukere/',
    'accounts/users/<int:pk>/': 'brukeradmin flyttet til /portal-admin/brukere/',
    'pasienter/api/full-stats/': 'statistikken flyttet til /statistikk/ (fase 6)',
    'pasienter/api/innstillinger/arkiv/<int:pk>/full-stats/': 'statistikken flyttet til /statistikk/',
    'statistikk/api/full-stats/': 'til kilderegisteret, /statistikk/api/kilde/<slug>/',
    'statistikk/api/arkiv/<int:pk>/full-stats/': 'til kilderegisteret, /statistikk/api/kilde/<slug>/',
}

#: Ikke med: finnes ikke i prod, og står i scriptets `FINNES_IKKE`.
UTENFOR = ('django-admin/', 'static/')

_PARAMETER = re.compile(r'<(?:(\w+):)?(\w+)>')


def _eksempel(monster: str) -> str:
    """Et mønster som en sti: `<int:pk>` → `1`, alt annet → `x`, og regexen
    i de gamle adressene lest som den enkleste strengen den treffer."""
    # Regexgruppene først: `(?P<rest>.*)` ser ellers ut som en `<parameter>`.
    sti = re.sub(r'\(\?P<\w+>\.\*\)', '', monster).replace('.*', 'x')
    sti = _PARAMETER.sub(lambda m: '1' if m.group(1) == 'int' else 'x', sti)
    sti = sti.replace('^', '').replace('$', '')
    return '/' + sti


def alle_monstre() -> list[str]:
    def gaa(resolver, prefiks=''):
        for p in resolver.url_patterns:
            if hasattr(p, 'url_patterns'):
                yield from gaa(p, prefiks + str(p.pattern))
            else:
                yield prefiks + str(p.pattern)
    return sorted({m for m in gaa(get_resolver()) if not m.startswith(UTENFOR)})


def bygg() -> dict:
    stengt, aapne, videre = [], [], []
    for m in alle_monstre():
        (aapne if m in AAPNE else videre if m in OMDIRIGERER else stengt).append(_eksempel(m))
    return {
        '_generert_av': 'python manage.py sikkerhetsruter — rediger ikke for hånd',
        'stengt': stengt,
        'aapne': aapne,
        'omdirigerer': videre,
    }


def som_tekst(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + '\n'
