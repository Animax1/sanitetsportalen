"""Belastningsvarselet (18. okt. 2026, `core/belastning.py`).

De to rene funksjonene — `vurder()` (hva er over) og `neste()` (når sendes det) — er reglene,
og prøves direkte. Resten går gjennom `vurder_og_varsle()` med Djangos e-postboks, og
klokketråden prøves på kallstedet.
"""
from __future__ import annotations

from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings

from core import belastning
from core.belastning import Maaling, neste, vurder

T = {'p95_ms': 2000, 'feil_5xx': 5, 'minne_pst': 85, 'varighet': 5}


class VurderTests(SimpleTestCase):

    def test_normalt_gir_ingenting(self):
        self.assertEqual(vurder(Maaling(antall=100, p95_ms=300, feil_5xx=0, minne_pst=40), T), [])

    def test_hvert_signal_for_seg(self):
        self.assertEqual(len(vurder(Maaling(p95_ms=2001), T)), 1)
        self.assertEqual(vurder(Maaling(p95_ms=2000), T), [], 'over, ikke lik')
        self.assertEqual(len(vurder(Maaling(feil_5xx=5), T)), 1)
        self.assertEqual(vurder(Maaling(feil_5xx=4), T), [])
        self.assertEqual(len(vurder(Maaling(minne_pst=85, minne_mb=400), T)), 1)
        self.assertEqual(vurder(Maaling(minne_pst=84.9, minne_mb=400), T), [])
        self.assertEqual(len(vurder(Maaling(db_ok=False), T)), 1)

    def test_ukjent_minne_og_p95_teller_ikke(self):
        self.assertEqual(vurder(Maaling(p95_ms=None, minne_pst=None), T), [])

    def test_p95_teller_bare_med_nok_forespoersler(self):
        snapshot = {'count': belastning.MIN_FORESPORSLER - 1, 'p95_ms': 9000, 'errors_5xx': 0}
        with mock.patch('core.middleware.metrics_store.snapshot', return_value=snapshot), \
                mock.patch('core.middleware.metrics_store.tregeste_stier', return_value=[]):
            self.assertIsNone(belastning.maal().p95_ms)
            snapshot['count'] = belastning.MIN_FORESPORSLER
            self.assertEqual(belastning.maal().p95_ms, 9000)


class NesteTests(SimpleTestCase):

    def test_maa_vare_foer_det_sendes_og_sendes_en_gang(self):
        over = ['P95']
        t, h = neste({}, over, 1000, 5)
        self.assertIsNone(h)
        t, h = neste(t, over, 1000 + 299, 5)
        self.assertIsNone(h)
        t, h = neste(t, over, 1000 + 300, 5)
        self.assertEqual(h, 'start')
        t, h = neste(t, over, 1000 + 900, 5)
        self.assertIsNone(h, 'ikke én e-post per minutt')
        t, h = neste(t, [], 1000 + 960, 5)
        self.assertEqual((t, h), ({}, 'slutt'))

    def test_en_topp_som_gikk_over_gir_ingenting(self):
        t, _ = neste({}, ['P95'], 1000, 5)
        self.assertEqual(neste(t, [], 1100, 5), ({}, None))


@override_settings(ADMINS=[('Drift', 'drift@example.org')], PORTAL_MILJO='test',
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                                       'LOCATION': 'belastning-test'}})
class VarselTests(TestCase):

    def setUp(self):
        cache.clear()

    def _tikk(self, naa, maaling):
        with mock.patch('core.belastning.maal', return_value=maaling):
            return belastning.vurder_og_varsle(naa=naa)

    def test_start_og_slutt_som_to_e_poster_til_admins(self):
        tung = Maaling(antall=200, p95_ms=4500, feil_5xx=0,
                       tregeste=[{'path': '/statistikk/api/', 'p95_ms': 6000, 'count': 12}])
        self.assertIsNone(self._tikk(0, tung))
        self.assertEqual(self._tikk(301, tung), 'start')
        self.assertIsNone(self._tikk(361, tung))
        self.assertEqual(len(mail.outbox), 1)
        start = mail.outbox[0]
        self.assertEqual(start.to, ['drift@example.org'])
        self.assertIn('[test] Høy belastning', start.subject)
        self.assertIn('4500 ms', start.body)
        self.assertIn('/statistikk/api/', start.body)

        self.assertEqual(self._tikk(600, Maaling(antall=200, p95_ms=300)), 'slutt')
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('normal igjen', mail.outbox[1].subject)

    def test_avslaatt_sender_ingenting(self):
        from core.models import AppSetting
        AppSetting.set(belastning.AKTIV_NOKKEL, '0')
        tung = Maaling(db_ok=False)
        self._tikk(0, tung)
        self.assertIsNone(self._tikk(10_000, tung))
        self.assertEqual(mail.outbox, [])

    def test_tersklene_leses_fra_innstillingene_og_klemmes(self):
        from core.models import AppSetting
        AppSetting.set('belastning_p95_ms', '500')
        AppSetting.set('belastning_varighet_min', '0')
        AppSetting.set('belastning_feil_5xx', 'tull')
        t = belastning.terskler()
        self.assertEqual((t['p95_ms'], t['varighet'], t['feil_5xx']), (500, 1, 5))

    def test_en_feil_i_maalingen_tar_ikke_ned_klokka(self):
        with mock.patch('core.belastning.maal', side_effect=RuntimeError('x')):
            self.assertIsNone(belastning.vurder_og_varsle(naa=0))


class KlokkaKallerVarseletTests(SimpleTestCase):
    """Kallstedet, ikke bare funksjonen (CLAUDE.md, «Mutasjonstesting»)."""

    def test_hvert_tikk_vurderer_belastningen(self):
        from core.backup import klokke

        class _Stopp(Exception):
            pass

        with mock.patch.object(klokke, 'rydd_foreldrelose'), \
                mock.patch.object(klokke, 'kjor_forfalte'), \
                mock.patch('core.belastning.vurder_og_varsle') as varsle, \
                mock.patch.object(klokke.time, 'sleep', side_effect=[None, _Stopp()]):
            with self.assertRaises(_Stopp):
                klokke._lokke()
        varsle.assert_called_once()


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InnstillingerTests(TestCase):

    def setUp(self):
        from accounts.models import CustomUser
        self.admin = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                                    must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)

    def test_kortet_lagrer_tersklene_og_bryteren(self):
        from core.models import AppSetting
        self.assertContains(self.c.get('/admin/innstillinger/'), 'Belastningsvarsel')
        self.c.post('/admin/innstillinger/', {
            'session_timeout_hours': '8',
            'belastning_sendt': '1', 'belastning_p95_ms': '3000', 'belastning_feil_5xx': '10',
            'belastning_minne_pst': '90', 'belastning_varighet': '10'})
        t = belastning.terskler()
        self.assertEqual((t['p95_ms'], t['feil_5xx'], t['minne_pst'], t['varighet']),
                         (3000, 10, 90, 10))
        self.assertEqual(AppSetting.get(belastning.AKTIV_NOKKEL), '0', 'boksen var ikke krysset')

    def test_utenfor_grensene_lagres_ikke(self):
        svar = self.c.post('/admin/innstillinger/', {'session_timeout_hours': '8',
                                                     'belastning_p95_ms': '10'}, follow=True)
        self.assertContains(svar, 'Svartid P95 må være mellom')
        self.assertEqual(belastning.terskler()['p95_ms'], 2000)
