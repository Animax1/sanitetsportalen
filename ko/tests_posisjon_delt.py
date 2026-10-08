"""«OBS: Lag 3 delte posisjon» i KO-loggen (André, 8. okt. 2026).

Linja skrives når kartet **tok imot** en delt posisjon (`core.kartkobling.posisjon_delt`),
står i loggstrømmen — og i hendelsen når laget eller bilen står på en åpen — og bærer aldri
koordinatene. Prøvd gjennom den ekte inngangen, `kartkobling.send_delt_posisjon` med `urlopen`
mocket, så et signal som slutter å sendes blir rødt.
"""
from __future__ import annotations

import json
import unittest
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from core import kartkobling
from core.models import ModuleSettings
from ko import services, systemlinjer
from ko.models import KILDE_SYSTEM, Logglinje
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Oppdrag
from patients.js_test_utils import KO_JS, build_harness, node_available, run_node

from .tests_tavle import _Grunnlag

KOBLET = {'KART_URL': 'https://kart.example.no', 'KART_HMAC_NOKKEL': 'k' * 64}


class _Svar:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@override_settings(**KOBLET)
class DeltPosisjonILoggenTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.delete(kartkobling.PAUSE_NOKKEL)
        patcher = mock.patch('core.kartkobling.request.urlopen', return_value=_Svar())
        self.urlopen = patcher.start()
        self.addCleanup(patcher.stop)

    def _del(self, type_='lag', navn='Lag 1', kilde_id=None, minutter=15):
        naa = timezone.now()
        return kartkobling.send_delt_posisjon(
            type_, navn, 59.41, 5.27, naa, naa + timedelta(minutes=minutter),
            kilde_id=self.lag1.pk if kilde_id is None and type_ == 'lag' else kilde_id)

    def _linjer(self):
        return list(Logglinje.objects.filter(kilde=KILDE_SYSTEM,
                                             systemkode=systemlinjer.POSISJON_DELT).order_by('id'))

    def test_lag_uten_hendelse_gir_en_linje_i_stroemmen_uten_koordinater(self):
        self.assertTrue(self._del())
        (linje,) = self._linjer()
        self.assertIsNone(linje.hendelse_id)
        self.assertEqual(set(linje.systemdata), {'type', 'navn', 'til'},
                         'aldri koordinatene — loggen står i 730 dager')
        self.assertNotIn('59.41', json.dumps(linje.systemdata))
        tekst = systemlinjer.tegn(linje.systemkode, linje.systemdata)
        self.assertTrue(tekst.startswith('OBS: Lag 1 delte posisjon · vises i kartet til '), tekst)

    def test_lag_paa_en_aapen_hendelse_faar_linja_i_hendelsen(self):
        h = services.opprett_hendelse(self.vakt, 'Besvimt', bruker=self.operator, lokasjon=self.park)
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        self._del()
        self.assertEqual(self._linjer()[0].hendelse_id, h.pk)

    def test_lag_paa_en_lukket_hendelse_faar_den_ikke(self):
        h = services.opprett_hendelse(self.vakt, 'Besvimt', bruker=self.operator, lokasjon=self.park)
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator)
        self._del()
        self.assertIsNone(self._linjer()[0].hendelse_id)

    def test_bil_paa_et_oppdrag_i_en_hendelse_faar_linja_i_hendelsen(self):
        h = services.opprett_hendelse(self.vakt, 'Fall', bruker=self.operator, lokasjon=self.park)
        o = Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet, lokasjon=self.park, problemstilling='Fall',
            hastegrad=choices.HASTEGRAD[0])
        oservices.sett_status(o, choices.RYKKER_UT, enhet=self.enhet)
        services.knytt_oppdrag(o, h, bruker=self.operator)
        self._del('enhet', 'HGSD 56', kilde_id=self.enhet.pk)
        (linje,) = self._linjer()
        self.assertEqual(linje.hendelse_id, h.pk)
        self.assertEqual(systemlinjer.tegn(linje.systemkode, linje.systemdata).split(' · ')[0],
                         'OBS: HGSD 56 delte posisjon')

    def test_bil_uten_oppdrag_staar_bare_i_stroemmen(self):
        self._del('enhet', 'HGSD 56', kilde_id=self.enhet.pk)
        self.assertIsNone(self._linjer()[0].hendelse_id)

    def test_flere_trykk_paa_kort_tid_er_en_linje_men_ikke_for_andre(self):
        self._del()
        self._del()
        self._del('lag', 'Lag 2', kilde_id=self.lag2.pk)
        self._del('enhet', 'Lag 1', kilde_id=self.enhet.pk)
        self.assertEqual([(l.systemdata['type'], l.systemdata['navn']) for l in self._linjer()],
                         [('lag', 'Lag 1'), ('lag', 'Lag 2'), ('enhet', 'Lag 1')])

    def test_etter_samlevinduet_blir_det_en_ny_linje(self):
        self._del()
        Logglinje.objects.filter(systemkode=systemlinjer.POSISJON_DELT).update(
            tidspunkt=timezone.now() - timedelta(minutes=3))
        self._del()
        self.assertEqual(len(self._linjer()), 2)

    def test_kartet_som_ikke_tok_imot_gir_ingen_linje(self):
        from urllib import error
        self.urlopen.side_effect = error.HTTPError('u', 404, 'x', {}, None)
        with self.assertLogs('core.kartkobling', 'WARNING'):
            self.assertFalse(self._del())
        self.assertEqual(self._linjer(), [])

    def test_ko_slaatt_av_gir_ingen_linje(self):
        ModuleSettings.objects.filter(slug='ko').update(enabled=False)
        self.assertTrue(self._del())
        self.assertEqual(self._linjer(), [])

    def test_en_feil_i_ko_tar_ikke_ned_delingen(self):
        with mock.patch('ko.signals.systemlinje', side_effect=RuntimeError('nede')), \
                self.assertLogs('ko.signals', 'WARNING'):
            self.assertTrue(self._del())


# ── Klienten: strømmen og merket ─────────────────────────────────────────────

@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class DeltPosisjonIStroemmenTests(SimpleTestCase):

    def _kjor(self, uttrykk):
        harness = build_harness(((KO_JS, ('koLinjeMerke', 'koIStrommen')),))
        return json.loads(run_node(harness, f'console.log(JSON.stringify({uttrykk}));').splitlines()[0])

    def test_staar_i_stroemmen_med_og_uten_hendelse_og_er_oransje(self):
        for hendelse_id in (None, 5):
            linje = json.dumps({'kilde': 'system', 'systemkode': 'posisjon_delt',
                                'hendelse_id': hendelse_id})
            with self.subTest(hendelse_id=hendelse_id):
                self.assertTrue(self._kjor(f'koIStrommen({linje})'))
                self.assertEqual(self._kjor(f'koLinjeMerke({linje})'), 'posisjon')
