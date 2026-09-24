"""Endringsnummeret (`core/endringer.py`, 24. sep. 2026).

Rammeverket prøves tungt: et tall som ikke øker, er et bilde som står feil på
tavla til sikkerhetsnettet slår inn — og et tall som sendes ut uten tilgang,
sier at noe har skjedd der brukeren ikke får se.
"""
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser

from . import endringer


class _Rent:
    def setUp(self):
        super().setUp()
        self._forrige = dict(endringer._OMRADER)
        endringer._OMRADER.clear()
        cache.clear()

    def tearDown(self):
        endringer._OMRADER.clear()
        endringer._OMRADER.update(self._forrige)
        super().tearDown()


class RegisteretTests(_Rent, SimpleTestCase):

    def test_samme_navn_to_ganger_er_en_feil(self):
        gate = lambda r: True   # noqa: E731
        endringer.registrer('a', gate)
        endringer.registrer('a', gate)   # samme gate: idempotent
        with self.assertRaises(ValueError):
            endringer.registrer('a', lambda r: True)
        with self.assertRaises(ValueError):
            endringer.registrer('', gate)

    def test_bare_omraadene_med_tilgang_og_ingen_ukjente(self):
        endringer.registrer('aapen', lambda r: True)
        endringer.registrer('stengt', lambda r: False)

        def feiler(r):
            raise RuntimeError('gate nede')
        endringer.registrer('feiler', feiler)
        ut = endringer.versjoner(None, ['aapen', 'stengt', 'feiler', 'ukjent'])
        self.assertEqual(list(ut), ['aapen'], 'en gate som feiler, stenger')


class TalletTests(_Rent, TestCase):

    def test_oeker_foerst_etter_commit(self):
        foer = endringer.versjon('a')
        with self.captureOnCommitCallbacks(execute=False) as kall:
            endringer.endret('a')
        self.assertEqual(endringer.versjon('a'), foer, 'ikke før raden er synlig')
        for k in kall:
            k()
        self.assertNotEqual(endringer.versjon('a'), foer)

    def test_hver_endring_gir_et_nytt_tall(self):
        sett = {endringer.versjon('a')}
        for _ in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                endringer.endret('a')
            sett.add(endringer.versjon('a'))
        self.assertEqual(len(sett), 4)

    def test_toemt_cache_gir_et_tall_ingen_fane_har_sett(self):
        """Likhet, ikke størrelse — og ikke 1 igjen."""
        with mock.patch.object(endringer, '_ny_start', return_value=1_000_000):
            foer = endringer.versjon('a')
        cache.clear()
        with mock.patch.object(endringer, '_ny_start', return_value=2_000_000):
            self.assertNotEqual(endringer.versjon('a'), foer)
            cache.clear()
            with self.captureOnCommitCallbacks(execute=True):
                endringer.endret('a')   # uten nøkkel: kaster ikke
            self.assertEqual(endringer.versjon('a'), '2000000', 'neste lesing starter på nytt')

    def test_en_cache_som_er_nede_kaster_ikke(self):
        with mock.patch.object(endringer.cache, 'get', side_effect=ConnectionError('nede')), \
                mock.patch.object(endringer.cache, 'incr', side_effect=ConnectionError('nede')):
            self.assertEqual(endringer.versjon('a'), '')
            with self.captureOnCommitCallbacks(execute=True):
                endringer.endret('a')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EndepunktetTests(_Rent, TestCase):

    def setUp(self):
        super().setUp()
        CustomUser.objects.create_user(username='u', password='x', must_change_password=False)
        endringer.registrer('aapen', lambda r: True)
        endringer.registrer('stengt', lambda r: False)

    def test_krever_innlogging_og_svarer_bare_om_det_man_faar_se(self):
        url = reverse('core:endringer')
        self.assertEqual(self.client.get(url, {'omrader': 'aapen'}).status_code, 302)
        self.client.login(username='u', password='x')
        d = self.client.get(url, {'omrader': 'aapen,stengt,ukjent'}).json()
        self.assertEqual(list(d), ['aapen'])
        self.assertEqual(self.client.get(url).json(), {})

    def test_holdes_utenfor_p95(self):
        from .middleware import metrics_store
        metrics_store.reset()
        self.client.login(username='u', password='x')
        for _ in range(5):
            self.client.get(reverse('core:endringer'), {'omrader': 'aapen'})
        self.assertEqual(metrics_store.snapshot(300)['count'], 0,
                         'fire raske svar i sekundet ville trukket P95 ned')
