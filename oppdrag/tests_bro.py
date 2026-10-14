"""Broene telles (14. okt. 2026, G6b-forarbeidet) — `oppdrag/bro.py`.

Reglene som prøves, hver gjennom den ekte inngangen (`save()`, server-status):

- Under test **kaster** en bro; i drift **telles** den, og kaster aldri.
- Telleren overlever en feil uten å ødelegge transaksjonen rundt (savepointet).
- Telleren auditlogges ikke — det er maskinen som teller.
- Server-status bærer svaret, og «Aldri brukt» er det dashbordet sier når
  ingen er brukt.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.db import connection, transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog
from core.models import AppSetting
from patients.js_test_utils import JS_DIR, build_harness, node_available, run_node

from . import bro, choices, services
from .models import Enhet, Lokasjon, Oppdrag, Statusmelding
from .test_helpers import lag_oppdrag

AAR = 2031


class _Basis(TestCase):
    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.vakt = sett_aktiv_vakt(AAR)
        self.a = Enhet.objects.create(navn='Haugesund 56')
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')

    def _felter(self):
        return dict(vakt=self.vakt, oppdragsnummer=services.neste_oppdragsnummer(self.vakt),
                    problemstilling='Pustevansker', hastegrad='Akutt', lokasjon=self.lokasjon)

    def _via_broen(self):
        return Oppdrag.objects.create(enhet=self.a, **self._felter())


class UnderTestKasterBroeneTests(_Basis):

    def test_oppdrag_med_enhet_kaster(self):
        with self.assertRaises(bro.BroBrukt):
            self._via_broen()

    def test_melding_uten_koblingsrad_kaster(self):
        o = lag_oppdrag(enhet=self.a, **self._felter())
        with self.assertRaises(bro.BroBrukt):
            Statusmelding.objects.create(oppdrag=o, status=choices.RYKKER_UT,
                                         tidspunkt=timezone.now())

    def test_melding_med_bare_koblingsrad_kaster(self):
        o = lag_oppdrag(enhet=self.a, **self._felter())
        with self.assertRaises(bro.BroBrukt):
            Statusmelding.objects.create(oppdragsenhet=o.primaer, status=choices.RYKKER_UT,
                                         tidspunkt=timezone.now())

    def test_drift_sin_vei_kaster_ikke(self):
        """`varsle_enhet` og en melding med koblingsraden — slik drift gjør."""
        o = Oppdrag.objects.create(enhet=None, **self._felter())
        services.varsle_enhet(o, self.a)
        Statusmelding.objects.create(oppdrag=o, oppdragsenhet=o.primaer,
                                     status=choices.RYKKER_UT, tidspunkt=timezone.now())
        self.assertEqual(bro.status(), {n: None for n in bro.BROER})


@override_settings(OPPDRAG_BRO_KASTER=False)
class IDriftTellesBroeneTests(_Basis):

    def test_hver_bro_telles_for_seg(self):
        with self.assertLogs('oppdrag.bro', 'WARNING') as logg:
            o = self._via_broen()
            o2 = self._via_broen()
            Statusmelding.objects.create(oppdrag=o, status=choices.RYKKER_UT,
                                         tidspunkt=timezone.now())
        status = bro.status()
        self.assertEqual(status['oppdrag']['antall'], 2)
        self.assertEqual(status['oppdrag']['oppdrag'], o2.pk)
        self.assertEqual(status['statusmelding']['antall'], 1)
        self.assertIsNone(status['statusmelding_oppdrag'])
        self.assertEqual(len(logg.records), 3)
        self.assertIn('oppdrag', logg.output[0])

    def test_forste_gang_staar_siste_flytter_seg(self):
        with mock.patch('oppdrag.bro.timezone.now') as naa:
            naa.return_value = datetime(2031, 6, 1, 20, 0, tzinfo=dt_timezone.utc)
            self._via_broen()
            naa.return_value = datetime(2031, 6, 1, 21, 30, tzinfo=dt_timezone.utc)
            self._via_broen()
        rad = bro.status()['oppdrag']
        self.assertTrue(rad['forste'].startswith('2031-06-01T20:00'))
        self.assertTrue(rad['siste'].startswith('2031-06-01T21:30'))

    def test_telleren_auditlogges_ikke(self):
        self._via_broen()
        self.assertFalse(AuditLog.objects.filter(field_name__startswith=bro.PREFIKS).exists())

    def test_en_feilet_telling_tar_ikke_ned_lagringen_eller_transaksjonen(self):
        """**Savepointet.** En ekte databasefeil inne i tellingen: uten
        `atomic()` rundt ville transaksjonen vært ødelagt, og neste spørring —
        her `count()` — kastet `TransactionManagementError`."""
        def feil(*a, **k):
            with connection.cursor() as c:
                c.execute('SELECT * FROM finnes_ikke_g6b')

        with mock.patch('oppdrag.bro._tell', side_effect=feil), \
                self.assertLogs('oppdrag.bro', 'ERROR'):
            with transaction.atomic():
                o = self._via_broen()
                self.assertEqual(o.enheter.count(), 1)
        self.assertTrue(Oppdrag.objects.filter(pk=o.pk).exists())

    def test_server_status_viser_broene(self):
        admin = CustomUser.objects.create_user(username='g6b_adm', password='x', role='admin',
                                               must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        c = Client()
        c.force_login(admin)

        def broer():
            res = c.get('/portal-admin/server-status/json/', secure=True)
            self.assertEqual(res.status_code, 200)
            return res.json()['vaktbilde']['oppdrag']['broer']

        self.assertEqual(broer(), {n: None for n in bro.BROER})
        self._via_broen()
        self.assertEqual(broer()['oppdrag']['antall'], 1)

    def test_en_odelagt_verdi_gir_aldri_et_unntak(self):
        AppSetting.objects.create(key=bro.PREFIKS + 'oppdrag', value='{ikke json')
        self.assertIsNone(bro.status()['oppdrag'])
        self._via_broen()
        self.assertEqual(bro.status()['oppdrag']['antall'], 1)


@unittest.skipUnless(node_available(), 'node mangler')
class BroTekstJsTests(SimpleTestCase):
    """`broTekst()` i `portal-status.js` avgjør hva dashbordet påstår."""

    def test_tekstene(self):
        harness = build_harness(((JS_DIR / 'portal-status.js', ('datoKlokke', 'broTekst')),))
        ut = run_node(harness, """
const brukt = {antall: 2, forste: '2031-06-01T18:00:00Z', siste: '2031-06-01T19:00:00Z', oppdrag: 4};
console.log(JSON.stringify([
  broTekst(null),
  broTekst({oppdrag: null, statusmelding: null}),
  broTekst({oppdrag: brukt, statusmelding: {...brukt, antall: 1, siste: '2031-06-01T20:00:00Z'}}),
]));""")
        ingen, aldri, brukt = json.loads(ut.splitlines()[0])
        self.assertEqual(ingen, {'tekst': '–', 'klasse': ''})
        self.assertEqual(aldri, {'tekst': 'Aldri brukt', 'klasse': 'status-ok'})
        self.assertEqual(brukt['klasse'], 'status-warn')
        self.assertTrue(brukt['tekst'].startswith('Brukt 3 g. (oppdrag, statusmelding), sist '),
                        brukt['tekst'])
