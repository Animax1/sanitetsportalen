"""Ankomster per time: én kjerne, samme svar i begge statistikkene (26. sep. 2026, E1).

Grunnstatistikken regnet per døgn og time, full statistikk per klokketime. På
en vakt over flere døgn slo den ene sammen kl. 14 fredag og kl. 14 lørdag, og
sidene viste ulike tall for samme vakt. André valgte døgn og time («E1 a»).

Testene går gjennom `basic_stats` og `full_stats`, ikke gjennom hjelperen —
det var nettopp to kallsteder som gikk hver sin vei.
"""
from django.test import TestCase

from patients.models import Patient
from patients.services import basic_stats, full_stats
from patients.test_helpers import sett_aktiv_vakt

#: Tvers over et månedsskifte, to ankomster samme klokketime på ulike døgn,
#: og én i ISO-formatet eldre importer har.
INNTIDER = ['30.09.2098 22:10', '30.09.2098 22:40', '01.10.2098 08:05',
            '01.10.2098 22:15', '2098-10-02T00:30', '']


class AnkomsterPerTimeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.vakt = sett_aktiv_vakt(2098)
        for nr, tid in enumerate(INNTIDER, start=1):
            Patient.objects.create(pasientnummer=nr, vakt=cls.vakt, inntid=tid)

    def test_begge_statistikkene_gir_samme_svar(self):
        self.assertEqual(basic_stats(self.vakt)['arrivals_by_hour'],
                         full_stats(self.vakt)['arrivals'])

    def test_per_doegn_og_time_i_kronologisk_rekkefoelge(self):
        self.assertEqual(list(full_stats(self.vakt)['arrivals'].items()), [
            ('30.09 22:00', 2),
            ('01.10 08:00', 1),
            ('01.10 22:00', 1),   # ikke slått sammen med 30.09 22:00
            ('02.10 00:00', 1),   # etter midnatt, og etter oktober-timene over
        ])
