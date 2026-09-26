"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — oppdragsmodulen.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
from datetime import timedelta

from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from oppdrag import choices
from oppdrag.models import Oppdrag, Problemstilling, Statusmelding
from oppdrag.tests import _enhet, _oppdrag
from oppdrag.tests_views import _bruker, _klient
from core.jsonkropp import json_body


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class Basis(TestCase):
    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.vakt = sett_aktiv_vakt(2098)
        self.bilbruker = _bruker('bil_s', 'skriv_full')
        self.enhet = _enhet('Bil 1', self.bilbruker)
        self.bil = _klient(self.bilbruker)
        self.sentral = _klient(_bruker('sentral_s', 'skriv_full'))

    def _ledig_for(self, oppdrag, minutter):
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.LEDIG,
            tidspunkt=timezone.now() - timedelta(minutes=minutter))
        oppdrag.enheter.update(status=choices.LEDIG)
        Oppdrag.objects.filter(pk=oppdrag.pk).update(status=choices.LEDIG)


class BilenSerBareDetListaViserTests(Basis):
    """M4: 30-minuttersvinduet gjelder detalj, grovsortering og antall også."""

    def test_nylig_avsluttet_kan_hentes(self):
        o = _oppdrag(self.enhet)
        self._ledig_for(o, 10)
        self.assertEqual(self.bil.get(f'/oppdrag/api/oppdrag/{o.pk}/').status_code, 200)

    def test_gammelt_er_borte_for_bilen(self):
        o = _oppdrag(self.enhet)
        self._ledig_for(o, 45)
        self.assertEqual(self.bil.get(f'/oppdrag/api/oppdrag/{o.pk}/').status_code, 404)
        self.assertEqual(self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/grovsortering/Rød/').status_code, 404)
        self.assertEqual(self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/antall/2/').status_code, 404)
        # Sentralbordet ser det fortsatt — vinduet er bilens.
        self.assertEqual(self.sentral.get(f'/oppdrag/api/oppdrag/{o.pk}/').status_code, 200)


class EnhetskontoSerIkkeFlaatenTests(Basis):
    """M6: bilen ser sine egne oppdrag, ikke flåtens, og setter ikke opp."""

    def test_enhetslista_er_stengt(self):
        self.assertEqual(self.bil.get('/oppdrag/api/enheter/').status_code, 403)
        self.assertEqual(self.sentral.get('/oppdrag/api/enheter/').status_code, 200)

    def test_flytting_er_stengt(self):
        o = _oppdrag(self.enhet)
        annen = _enhet('Bil 2')
        res = self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/flytt/', content_type='application/json',
                            data={'enhet_id': annen.pk})
        self.assertEqual(res.status_code, 403)

    def test_verdimengdene_er_stengt_selv_med_skriv_leder(self):
        from accounts.models import ModulTilgang
        ModulTilgang.objects.filter(bruker=self.bilbruker).update(nivaa='skriv_leder')
        for slug in ('lokasjoner', 'enhetstyper', 'problemstillinger'):
            res = self.bil.post(f'/oppdrag/api/{slug}/', content_type='application/json',
                                data={'navn': 'Fra bilen'})
            self.assertEqual(res.status_code, 403, slug)


class ScriptInjeksjonTests(Basis):
    """H1: et problemstillingsnavn kan ikke lukke skriptet på /oppdrag/."""

    def test_navnet_er_escapet_i_begge_skjermene(self):
        Problemstilling.objects.create(navn='</script><script>alert(1)</script>', kategori='begge')
        for klient in (self.sentral, self.bil):
            html = klient.get('/oppdrag/').content.decode()
            self.assertNotIn('</script><script>alert(1)', html)
            if klient is self.sentral:
                self.assertIn('\\u003c/script\\u003e\\u003cscript\\u003ealert(1)', html)


class JsonKroppTests(TestCase):
    """M8: gyldig JSON som ikke er et objekt gir tom dict, ikke 500."""

    def test_liste_streng_og_null(self):
        for kropp in (b'[]', b'"x"', b'null', b'1', b'[{"a": 1}]'):
            req = RequestFactory().post('/', data=kropp, content_type='application/json')
            self.assertEqual(json_body(req), {}, kropp)
        req = RequestFactory().post('/', data=b'{"a": 1}', content_type='application/json')
        self.assertEqual(json_body(req), {'a': 1})
