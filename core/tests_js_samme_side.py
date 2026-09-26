"""Ingen toppnivåfunksjon definert to ganger på samme side (26. sep. 2026, G3).

Uten bundler deler filene på en side ett navnerom, og **den sist lastede
vinner i stillhet**. Pasientsiden hadde sin egen `updateClock` i
`patients-utils.js`; da `portal-clock.js` kom inn på siden, ville to like
navn stått der. Testen rendrer sidene og leser skriptene de *faktisk* laster.
"""
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser

SIDER = ('/pasienter/', '/portal-admin/server-status/')


def _skript(html):
    """Stiene til `static/js/*.js` siden laster, i rekkefølge (uten hash)."""
    ut = []
    for src in re.findall(r'<script src="([^"]+)"', html):
        m = re.search(r'/js/([\w-]+?)(?:\.[0-9a-f]{12})?\.js$', src)
        if m:
            ut.append(m.group(1) + '.js')
    return ut


@override_settings(SECURE_SSL_REDIRECT=False)
class IngenDobbeltePaaSammeSideTests(TestCase):

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        sett_aktiv_vakt(2026)
        self.c = Client()
        self.c.force_login(CustomUser.objects.create_user(
            username='sidetest', password='x', role='admin', must_change_password=False))

    def test_hver_side(self):
        for side in SIDER:
            with self.subTest(side):
                filer = _skript(self.c.get(side).content.decode())
                self.assertIn('portal-clock.js', filer, 'den felles klokka')
                sett: dict = {}
                dobbel = []
                for fil in filer:
                    kilde = open(finders.find('js/' + fil), encoding='utf-8').read()
                    for navn in re.findall(r'^(?:async )?function (\w+)\(', kilde, re.M):
                        if navn in sett:
                            dobbel.append(f'{navn}: {sett[navn]} og {fil}')
                        sett[navn] = fil
                self.assertEqual(dobbel, [])
                self.assertGreater(len(filer), 1, 'fant ingen skript — testen måler ingenting')
