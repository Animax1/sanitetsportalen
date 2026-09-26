"""Knappen og døra bak den svarer likt på «kan lede» (26. sep. 2026, E4).

Knappen «Valglister» i sentralbordet sto på `er_global_admin or skriv_leder`,
endepunktene bak den på det samme **pluss** «ikke en enhetskonto» (M6). En
bilkonto med `skriv_leder` fikk knappen og så 403 — en knapp som fører til en
vegg. Nås gjennom `/ko/`, som bygger sentralbordet for alle med KO-tilgang.
Regelen står nå ett sted: `oppdrag.views_common.kan_lede`.
"""
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from oppdrag.models import Enhet
from oppdrag.views import sentralbordkontekst


def _bruker(navn, *, enhet=False, nivaa='skriv_leder'):
    u = CustomUser.objects.create_user(username=navn, password='x', role='bruker',
                                       must_change_password=False)
    ModulTilgang.objects.create(bruker=u, modul_slug='oppdrag', nivaa=nivaa)
    ModulTilgang.objects.create(bruker=u, modul_slug='ko', nivaa='les')
    if enhet:
        Enhet.objects.create(navn=f'Bil {navn}', user=u)
    return CustomUser.objects.get(pk=u.pk)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KanLedeTests(TestCase):

    def _knappen(self, bruker):
        req = RequestFactory().get('/ko/')
        req.user = bruker
        return sentralbordkontekst(req)['kan_lede']

    def _doera(self, bruker):
        self.client.force_login(bruker)
        return self.client.post('/oppdrag/api/lokasjoner/', {'navn': 'Scene nord'},
                                content_type='application/json').status_code

    def test_lederen_faar_knappen_og_kommer_inn(self):
        leder = _bruker('leder')
        self.assertTrue(self._knappen(leder))
        self.assertIn(self._doera(leder), (200, 201))

    def test_bilkontoen_faar_verken_knapp_eller_dor(self):
        bil = _bruker('bil', enhet=True)
        self.assertFalse(self._knappen(bil), 'knappen ville ført til en vegg')
        self.assertEqual(self._doera(bil), 403)

    def test_bemanneren_faar_ikke_knappen(self):
        """`skriv_full` bemanner; å sette opp verdimengdene er ett trinn over."""
        operator = _bruker('operator', nivaa='skriv_full')
        self.assertFalse(self._knappen(operator))
        self.assertEqual(self._doera(operator), 403)
