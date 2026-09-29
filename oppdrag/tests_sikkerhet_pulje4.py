"""Sikkerhetsgjennomgangen 28. sep. 2026, pulje 4: bilkontoen og sentralbordet.

Regelen i modulen er «enhetskontoer 403 uansett nivå» på det sentralbordet gjør.
Den sto som en `if` i noen views og manglet i sju. Ingenting i tilgangsmatrisen
hindrer at en bilkonto får `skriv_full` ved en feil — og da kunne den ta andre
biler av vakt, sette dem passive, opprette oppdrag og redigere dem.
"""
from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver

from accounts.models import ModulTilgang
from oppdrag.models import Enhet, Oppdrag
from oppdrag.tests_views import OppdragBasis, _bruker, _klient


def _monstre(resolver, ut=None):
    ut = [] if ut is None else ut
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            _monstre(p, ut)
        elif isinstance(p, URLPattern):
            ut.append(p)
    return ut


class OppdragFullSperrerBilen(TestCase):
    """Strukturen: hvert `skriv_full`-view i oppdrag har `ikke_for_enhetskonto`."""

    def test_hvert_skriv_full_view_sperrer_enhetskontoen(self):
        from django.urls import get_resolver
        funnet, mangler = [], []
        for p in _monstre(get_resolver()):
            krav = getattr(p.callback, '_modul_kreves', None)
            if krav != ('oppdrag', 'skriv_full'):
                continue
            funnet.append(p.name)
            if not getattr(p.callback, '_ikke_for_enhetskonto', False):
                mangler.append(p.name)
        self.assertGreaterEqual(len(funnet), 8, 'fant for få views — leser testen riktig?')
        self.assertEqual(mangler, [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BilkontoMedSkrivFullTests(OppdragBasis):
    """Atferden, gjennom endepunktene: en bilkonto som ved en feil har `skriv_full`."""

    def setUp(self):
        super().setUp()
        self.bilbruker = _bruker('bil_p4', 'skriv_full', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=self.bilbruker)
        self.bil = _klient(self.bilbruker)
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(pa_vakt=True)

    def test_tar_ikke_en_annen_bil_av_vakt(self):
        res = self.bil.post(f'/oppdrag/api/enheter/{self.annen_enhet.pk}/vakt/',
                            data={'pa_vakt': False}, content_type='application/json')
        self.assertEqual(res.status_code, 403, res.content)
        self.annen_enhet.refresh_from_db()
        self.assertTrue(self.annen_enhet.pa_vakt)

    def test_oppretter_ikke_oppdrag(self):
        for_ = Oppdrag.objects.count()
        res = self.bil.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
            'lokasjon_id': self.lokasjon.pk})
        self.assertEqual(res.status_code, 403, res.content)
        self.assertEqual(Oppdrag.objects.count(), for_)

    def test_redigerer_ikke_sitt_eget_oppdrag(self):
        o = self._oppdrag(fritekst='original')
        res = self.bil.put(f'/oppdrag/api/oppdrag/{o.pk}/', content_type='application/json',
                           data={'fritekst': 'endret av bilen'})
        self.assertEqual(res.status_code, 403, res.content)
        o.refresh_from_db()
        self.assertEqual(o.fritekst, 'original')

    def test_sentralbordet_med_samme_nivaa_slipper_gjennom(self):
        """Motprøven: det er bilkontoen som stenges, ikke nivået."""
        sentral = _klient(_bruker('sentral_p4', 'skriv_full'))
        o = self._oppdrag(fritekst='original')
        res = sentral.put(f'/oppdrag/api/oppdrag/{o.pk}/', content_type='application/json',
                          data={'fritekst': 'endret av sentralbordet'})
        self.assertEqual(res.status_code, 200, res.content)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class StatistikkForBilkontoTests(OppdragBasis):
    """`oppdrag:les` er ikke nok for oppdragsfanen når kontoen er en bil."""

    def setUp(self):
        super().setUp()
        self.bilbruker = _bruker('bil_stat', 'les', delt=True)
        ModulTilgang.objects.create(bruker=self.bilbruker, modul_slug='statistikk', nivaa='les')
        Enhet.objects.filter(pk=self.enhet.pk).update(user=self.bilbruker)
        self.bilbruker.refresh_from_db()

    def test_fanen_er_ikke_hennes(self):
        from statistikk.views import lesbare_kilder
        self.assertNotIn('oppdrag', [h.slug for h in lesbare_kilder(self.bilbruker)])

    def test_endepunktet_svarer_ikke(self):
        res = _klient(self.bilbruker).get('/statistikk/api/kilde/oppdrag/full-stats/')
        self.assertIn(res.status_code, (403, 404), res.content[:200])

    def test_sentralbordet_ser_den(self):
        """Motprøven."""
        from statistikk.views import lesbare_kilder
        sentral = _bruker('sentral_stat', 'les')
        ModulTilgang.objects.create(bruker=sentral, modul_slug='statistikk', nivaa='les')
        self.assertIn('oppdrag', [h.slug for h in lesbare_kilder(sentral)])
