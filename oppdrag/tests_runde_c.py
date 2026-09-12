"""Andrés runde på staging 12. sep. 2026, del C — «trenger ny ressurs».

«Når enhet rykker ut på et oppdrag og får nytt oppdrag som de må rykke ut på
må det de var på først flyttes til et ventende på sentralbord og trenger ny
ressurs på seg.» Bilens rad lukkes som før (§4.3); oppdraget gjør det ikke.
"""
from django.test import SimpleTestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node)

from . import choices, services
from .models import Enhetshendelse
from .tests_flere_enheter import FlereEnheterBasis, _bruker, _klient


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TrengerRessursTests(FlereEnheterBasis):
    def _rykk_videre(self):
        forste = self._oppdrag(self.a)
        services.sett_status(forste, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(forste, choices.FREMME, enhet=self.a)
        andre = self._oppdrag(self.a)
        services.start_oppdrag(andre, enhet=self.a)
        forste.refresh_from_db()
        return forste, andre

    def test_det_forrige_blir_staaende_paa_tavla(self):
        forste, andre = self._rykk_videre()
        self.assertTrue(forste.trenger_ressurs)
        self.assertEqual(forste.status, choices.VENTER)
        self.assertIsNone(forste.historikk_fra)
        self.assertEqual(services.koblingsrad(forste, self.a).status, choices.LEDIG)
        lukking = services.koblingsrad(forste, self.a)
        self.assertTrue(lukking.er_avsluttet)

    def test_hendelsen_sier_hvor_hun_dro(self):
        forste, andre = self._rykk_videre()
        h = Enhetshendelse.objects.get(oppdrag=forste)
        self.assertEqual(h.type, Enhetshendelse.RYKKET_VIDERE)
        self.assertEqual(h.enhet, self.a)
        self.assertEqual(h.detalj, f'#{andre.oppdragsnummer}')
        c = _klient(_bruker('sentral_c', 'skriv_full'))
        d = c.get(f'/oppdrag/api/oppdrag/{forste.pk}/').json()['data']
        self.assertTrue(d['trenger_ressurs'])
        self.assertEqual(d['enhetshendelser'][0]['type'], 'rykket_videre')
        self.assertEqual(d['enhetshendelser'][0]['detalj'], f'#{andre.oppdragsnummer}')
        self.assertTrue(d['kan_slettes'], 'sentralbordet kan stryke et oppdrag som venter på ressurs')

    def test_en_ny_enhet_tar_over_og_flagget_nullstilles(self):
        forste, _ = self._rykk_videre()
        services.varsle_enhet(forste, self.b)
        forste.refresh_from_db()
        self.assertFalse(forste.trenger_ressurs)
        self.assertEqual(forste.status, choices.VENTER, 'B venter')
        services.sett_status(forste, choices.RYKKER_UT, enhet=self.b)
        forste.refresh_from_db()
        self.assertEqual(forste.status, choices.RYKKER_UT)
        services.sett_status(forste, choices.LEDIG, enhet=self.b)
        forste.refresh_from_db()
        self.assertEqual(forste.status, choices.LEDIG)
        self.assertIsNotNone(forste.historikk_fra, 'ferdig — nå ryddes det')

    def test_ingen_flagg_naar_en_annen_bil_fortsatt_er_paa(self):
        felles = self._to_enheter()
        services.sett_status(felles, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(felles, choices.RYKKER_UT, enhet=self.b)
        nytt = self._oppdrag(self.a)
        services.start_oppdrag(nytt, enhet=self.a)
        felles.refresh_from_db()
        self.assertFalse(felles.trenger_ressurs, 'B er der fortsatt')
        self.assertEqual(felles.status, choices.RYKKER_UT)
        self.assertEqual(Enhetshendelse.objects.filter(oppdrag=felles).count(), 1,
                         'men hendelsen står: A rykket videre')

    def test_lista_paa_sentralbordet_baerer_flagget(self):
        forste, _ = self._rykk_videre()
        c = _klient(_bruker('sentral_d', 'skriv_full'))
        rader = {r['id']: r for r in c.get('/oppdrag/api/oppdrag/').json()['data']}
        self.assertIn(forste.pk, rader)
        self.assertTrue(rader[forste.pk]['trenger_ressurs'])
        self.assertEqual(rader[forste.pk]['status'], choices.VENTER)


class TrengerRessursJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_SENTRAL_JS, ('_enhetsmatrise', 'tidslinjeHtml', 'tidSiden')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_merket_staar_forst_i_matrisen(self):
        ut = run_node(self.harness, """
            console.log(_enhetsmatrise({trenger_ressurs: true, enheter: [
              {enhet_id: 1, enhet_navn: 'HGSD 56', status: 'ledig', status_navn: 'Ledig', status_tidspunkt: null}]}));
            console.log('---');
            console.log(_enhetsmatrise({trenger_ressurs: false, enheter: [
              {enhet_id: 1, enhet_navn: 'HGSD 56', status: 'ledig', status_navn: 'Ledig', status_tidspunkt: null}]}));
        """)
        med, uten = ut.split('---')
        self.assertIn('Trenger ny ressurs', med)
        self.assertLess(med.index('Trenger ny ressurs'), med.index('HGSD 56'))
        self.assertNotIn('Trenger ny ressurs', uten)

    def test_tidslinjen_sier_rykket_videre_med_nummer(self):
        ut = run_node(self.harness, """
            globalThis.OPPDRAG_STATUS_NAVN = {};
            console.log(tidslinjeHtml({opprettet: '2026-08-29T20:00:00Z', enheter: [], historikk: [],
              enhetsbytter: [], enhetshendelser: [
                {type: 'rykket_videre', detalj: '#12', enhet_navn: '<b>HGSD 56</b>',
                 tidspunkt: '2026-08-29T20:10:00Z', av: 'bil'},
                {type: 'tatt_av', detalj: '', enhet_navn: 'KARM 12',
                 tidspunkt: '2026-08-29T20:05:00Z', av: 'ko'}]}));
        """)
        self.assertIn('Rykket videre til #12: &lt;b&gt;HGSD 56&lt;/b&gt;', ut)
        self.assertIn('Tatt av: KARM 12', ut)
