"""Hver `{% url %}` i hver mal skal la seg slå opp.

**Hullet denne lukker.** Django feiler på en ukjent rute først når malen
faktisk *rendres*. En `{% url %}` inne i en `{% if %}` som bare vises for én
rolle, eller bare når en liste er tom, kan derfor være død i måneder med
suiten grønn — og gi 500 på en side som virket i går, hos den ene brukeren som
treffer den grenen.

Testen ble skrevet 14. sep. 2026, da adminflaten fikk ett navnerom
(`portaladmin`, gjeldspunkt 3.2) og 131 referanser skiftet prefiks. Den runden
gikk gjennom fordi *viewtestene* rendret sidene — men det var flaks, ikke
dekning: ingenting krevde at hver gren i hver mal ble rendret.

Den leser `{% url %}`-taggene med regex og ikke ved å rendre, fordi poenget er
å slippe å rendre: det er nettopp grenene ingen rendrer som er i fare.
Dynamiske navn (`{% url navn %}` uten hermetegn) hoppes over — de kan ikke
avgjøres uten å kjøre malen.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

#: `{% url 'navn' ... %}` og `{% url "navn" ... %}`.
URL_TAG = re.compile(r"""\{%\s*url\s+(['"])([^'"]+)\1""")


def _malfiler() -> list[Path]:
    rot = Path(settings.BASE_DIR)
    ut = []
    for mappe in sorted(rot.rglob('templates')):
        if '.venv' in mappe.parts or 'site-packages' in mappe.parts:
            continue
        ut += sorted(mappe.rglob('*.html'))
    return ut


class MalenesUrlerLarSegSlaOppTests(SimpleTestCase):

    def test_alle_navngitte_url_tagger_finnes(self) -> None:
        rot = Path(settings.BASE_DIR)
        funn = []
        sett = 0
        for mal in _malfiler():
            tekst = mal.read_text(encoding='utf-8')
            for _, navn in URL_TAG.findall(tekst):
                sett += 1
                try:
                    reverse(navn)
                except NoReverseMatch as feil:
                    # En rute med argumenter kan ikke reverses uten dem, men
                    # feilmeldingen skiller: «not a valid view function or
                    # pattern name» betyr at navnet er ukjent, mens en
                    # argumentfeil nevner argumentene.
                    if 'not a valid view function or pattern name' in str(feil):
                        funn.append(f'{mal.relative_to(rot)}: {navn}')

        self.assertGreater(sett, 50, 'fant nesten ingen url-tagger — leser testen malene?')
        self.assertEqual(funn, [], (
            'Disse malene peker på ruter som ikke finnes. Siden gir 500 når '
            'grenen rendres:\n  ' + '\n  '.join(funn)))

    def test_ingen_mal_bruker_de_gamle_adminnavnene(self) -> None:
        """Speilet: navnene finnes ikke lenger, så en gjenglemt referanse ville
        blitt fanget av testen over — men bare hvis den *ikke* tilfeldigvis
        kolliderer med et navn i et annet navnerom. Denne sier det rett ut."""
        rot = Path(settings.BASE_DIR)
        gamle = re.compile(r"\b(?:accounts|core):(user_list|user_create|user_detail|"
                           r"user_delete|login_event_list|portal_settings|"
                           r"module_admin_\w+|audit_log_\w+|backup_admin\w*)\b")
        funn = []
        for mal in _malfiler():
            for treff in gamle.findall(mal.read_text(encoding='utf-8')):
                funn.append(f'{mal.relative_to(rot)}: {treff}')
        self.assertEqual(funn, [], (
            'Adminflaten har navnerommet `portaladmin` siden 14. sep. 2026:\n  '
            + '\n  '.join(funn)))
