"""KO fører «Avbrutt» for en enhet (bestilt 22. sep. 2026, levert 23. sep.).

André: bilen melder på samband at den avbryter. Før dette kunne KO bare
føre «Ledig» — da ble det ikke ført som avbrutt, og oppdraget ble ikke
flagget «trenger ny ressurs». `services.foer_avbrutt` er bilens
`avbryt_oppdrag` ført av sentralbordet: samme regel, operatøren som meldt av.
"""
import json
import unittest

from django.test import SimpleTestCase, override_settings

from oppdrag import choices, services
from oppdrag.models import Enhetshendelse, Statusmelding

from .tests_flere_enheter import SentralbordBasis, _bruker, _klient


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FoerAvbruttTests(SentralbordBasis):

    def _url(self, o, enhet):
        return f'/oppdrag/api/oppdrag/{o.pk}/enheter/{enhet.pk}/status/avbryt/'

    def _post(self, o, enhet, minutter=5, klient=None):
        kropp = {'tidspunkt': self._for(minutter).isoformat()} if minutter is not None else {}
        return (klient or self.ks).post(self._url(o, enhet), content_type='application/json', data=kropp)

    def test_avbrutt_er_ledig_ført_av_operatoren_og_oppdraget_trenger_ressurs(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(20), enhet=self.a)
        res = self._post(o, self.a)
        self.assertEqual(res.status_code, 200, res.content)
        o.refresh_from_db()
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.LEDIG)
        m = Statusmelding.objects.get(oppdrag=o, status=choices.LEDIG)
        self.assertTrue(m.manuell)
        self.assertEqual(m.meldt_av, self.sentral)
        self.assertTrue(o.trenger_ressurs, 'ingen andre på vei: oppdraget trenger ny ressurs')
        # Avbrytelsen er en enhetshendelse ved siden av Ledig — det er den som
        # skiller den fra et vanlig Ledig (`avbrutt_av`).
        h = Enhetshendelse.objects.get(oppdrag=o, type=Enhetshendelse.AVBRUTT)
        self.assertEqual(h.av, self.sentral)
        self.assertEqual(res.json()['data']['oppdrag']['avbrutt_av'], [self.a.navn])

    def test_bare_fra_rykker_ut_og_fremme(self):
        """Samme regel som bilens knapp: fra Avreist har hun en pasient."""
        o = self._gammelt(self.a)
        self.assertEqual(self._post(o, self.a).status_code, 400, 'Venter')
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(30), enhet=self.a)
        services.sett_status(o, choices.FREMME, tidspunkt=self._for(25), enhet=self.a)
        services.sett_status(o, choices.AVREIST, tidspunkt=self._for(20), enhet=self.a, sted='sykehus')
        self.assertEqual(self._post(o, self.a).status_code, 400, 'Avreist')
        self.assertFalse(Statusmelding.objects.filter(oppdrag=o, status=choices.LEDIG).exists())
        self.assertFalse(Enhetshendelse.objects.filter(oppdrag=o, type=Enhetshendelse.AVBRUTT).exists())

    def test_fra_fremme(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(30), enhet=self.a)
        services.sett_status(o, choices.FREMME, tidspunkt=self._for(25), enhet=self.a)
        self.assertEqual(self._post(o, self.a).status_code, 200)

    def test_tidspunktet_proves_som_en_ny_melding(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(20), enhet=self.a)
        self.assertEqual(self._post(o, self.a, minutter=None).status_code, 400, 'mangler')
        self.assertEqual(self._post(o, self.a, minutter=-30).status_code, 400, 'i framtida')
        self.assertEqual(self._post(o, self.a, minutter=40).status_code, 400, 'før Rykker ut')
        self.assertEqual(services.koblingsrad(o, self.a).status, choices.RYKKER_UT, 'ingenting skrevet')

    def test_krever_skriv_full_og_en_varslet_enhet(self):
        o = self._gammelt(self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(20), enhet=self.a)
        leser = _klient(_bruker('leser_avbrutt', 'les'))
        self.assertEqual(self._post(o, self.a, klient=leser).status_code, 403)
        self.assertEqual(self._post(o, self.b).status_code, 400, 'ikke varslet')
        self.assertEqual(self.ks.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.a.pk}/status/tull/',
                                      content_type='application/json', data={}).status_code, 404)

    def test_en_annen_bil_paa_vei_gir_ikke_flagget(self):
        o = self._gammelt(self.a, self.b)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(20), enhet=self.a)
        services.sett_status(o, choices.RYKKER_UT, tidspunkt=self._for(20), enhet=self.b)
        self.assertEqual(self._post(o, self.a).status_code, 200)
        o.refresh_from_db()
        self.assertFalse(o.trenger_ressurs, 'Bil B er fortsatt på vei')


class AvbruttINedtrekketTests(SimpleTestCase):
    """«Avbrutt» står i nedtrekket bare der bilen selv har knappen."""

    def setUp(self):
        from patients.js_test_utils import (OPPDRAG_SENTRAL_JS, build_harness,
                                            node_available)
        if not node_available():
            raise unittest.SkipTest('node er ikke tilgjengelig')
        from .tests_runde_d import _konst
        self.harness = _konst(OPPDRAG_SENTRAL_JS, 'STATUS_RANG') + build_harness((
            (OPPDRAG_SENTRAL_JS, ('_statusvalg',)),))

    def _foran(self, status, avbryt_fra):
        from patients.js_test_utils import run_node
        pre = f'globalThis.window = {{ OPPDRAG_AVBRYT_FRA: {json.dumps(avbryt_fra)} }};\n'
        ut = run_node(self.harness, f"console.log(JSON.stringify(_statusvalg('{status}').foran));",
                      preamble=pre)
        return json.loads(ut.splitlines()[0])

    def test_i_rykker_ut_og_fremme_sist_i_videre(self):
        fra = ['fremme', 'rykker_ut']
        self.assertEqual(self._foran('rykker_ut', fra)[-1], 'avbryt')
        self.assertEqual(self._foran('fremme', fra)[-1], 'avbryt')
        self.assertNotIn('avbryt', self._foran('avreist', fra))
        self.assertNotIn('avbryt', self._foran('venter', fra))

    def test_serveren_bestemmer_hvor(self):
        self.assertNotIn('avbryt', self._foran('fremme', []))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RegelenKommerFraServerenTests(SentralbordBasis):

    def test_begge_sidene_faar_avbryt_fra(self):
        """`/oppdrag/` og `/ko/` deler malbiten; lista er `services.AVBRYT_FRA`."""
        html = self.ks.get('/oppdrag/').content.decode()
        self.assertIn('window.OPPDRAG_AVBRYT_FRA = ["fremme", "rykker_ut"]', html)
