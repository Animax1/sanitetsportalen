"""Brukerveiledningen på `/vaktliste/veiledning/` (pulje 5, 1. okt. 2026).

**En veiledning som nevner en knapp som ikke finnes, er verre enn ingen** — den
sender folk på leting etter noe skjermen aldri viser. Ordene på skjermen ble byttet
30. sep. (pulje 3), og en tekst skrevet før det ville stått med de gamle. Derfor
leser testen hvert «…»-sitat i veiledningen og krever at det står i malen eller i
JS-en til vaktlisten. Det som ikke er et skjermnavn — et eksempel, en beskjed —
står i `IKKE_SKJERMNAVN` med grunnen.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .tests_tilgang import TilgangsBasis, _bruker, _klient

ROT = Path(settings.BASE_DIR)
MAL = ROT / 'templates/vaktliste/veiledning.html'

#: Sitater som ikke er navn på noe på skjermen.
IKKE_SKJERMNAVN = {
    'tre firemannslag 14–22': 'eksempel på et oppsett',
    'kommer 17:30': 'eksempel på en merknad',
    '4 plasser ikke delt ut': 'merket med et tall i; regelen står i `utdelingsmerke()`',
    'alle korps': 'nivået «Lese: alle korps» i tilgangsmatrisen, forkortet',
}


def _skjermkilde():
    deler = [(ROT / 'templates/vaktliste/index.html').read_text(encoding='utf-8')]
    deler += [p.read_text(encoding='utf-8')
              for p in sorted((ROT / 'static/js').glob('vaktliste-*.js'))]
    return '\n'.join(deler)


def sitater():
    tekst = re.sub(r'{%\s*comment\s*%}.*?{%\s*endcomment\s*%}', '',
                   MAL.read_text(encoding='utf-8'), flags=re.S)
    return {re.sub(r'\s+', ' ', s).strip() for s in re.findall(r'«([^»]+)»', tekst)}


def mangler(navn, kilde):
    return sorted(s for s in navn - set(IKKE_SKJERMNAVN) if s.rstrip(' …') not in kilde)


class SitateneFinnesPaaSkjermenTests(SimpleTestCase):

    def test_hvert_skjermnavn_finnes(self):
        funn = mangler(sitater(), _skjermkilde())
        self.assertEqual(funn, [], 'Veiledningen nevner noe skjermen ikke har:\n'
                         + '\n'.join(funn))

    def test_leseren_finner_sitatene(self):
        """Finner den ingen, er det regexen som har sluttet å lese."""
        funn = sitater()
        for navn in ('Del ut …', 'Koble til delt konto', 'Mitt korps', 'Tilstede nå',
                     'Innstillinger', 'Rediger enhet', 'Lag grunnlaget', 'Planlegger'):
            self.assertIn(navn, funn)

    def test_et_feil_navn_blir_fanget(self):
        self.assertEqual(mangler({'Del ut …', 'Knappen som ikke finnes'}, _skjermkilde()),
                         ['Knappen som ikke finnes'])


class SidenTests(TilgangsBasis):

    URL = '/vaktliste/veiledning/'

    def test_alle_med_les_naar_den(self):
        for navn, klient in (('les', self.c_leser), ('skriv_handling', self.c_kb),
                             ('skriv_full', self.c_vl), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                self.assertEqual(klient.get(self.URL).status_code, 200)

    def test_uten_modultilgang_er_den_stengt(self):
        self.assertIn(_klient(_bruker('utenfor')).get(self.URL).status_code, (302, 403))

    def test_brukerens_del_pekes_ut(self):
        for klient, rolle, tekst in ((self.c_leser, 'leser', 'Du kan <strong>se</strong>'),
                                     (self.c_kb, 'korpsforer', 'korps-fører'),
                                     (self.c_vl, 'vaktleder', 'vaktleder'),
                                     (self.c_leder, 'leder', 'leder'),
                                     (self.c_adm, 'admin', 'administrator')):
            with self.subTest(rolle=rolle):
                svar = klient.get(self.URL)
                self.assertEqual(svar.context['din_rolle'], rolle)
                self.assertIn(f'<section id="{rolle}" class="vl-veil-din">',
                              svar.content.decode())
                self.assertIn(tekst, svar.content.decode())

    def test_vaktlisten_lenker_til_den(self):
        self.assertIn('href="/vaktliste/veiledning/"',
                      self.c_leser.get('/vaktliste/').content.decode())
