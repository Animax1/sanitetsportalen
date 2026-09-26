"""Ingen produksjonskode leser `Oppdrag.enhet` lenger (26. sep. 2026, G6a).

Kolonnen er arven fra én bil per oppdrag, og fjernes i deploy 2. Før den kan
fjernes, må ingen lese den. En statisk regel ville bommet — `enhet` er navnet
på fire andre felt — så denne prøver **atferden**: hent svarene, sett
kolonnen til en *feil* bil på hvert oppdrag, og krev at ingenting endret seg.
Leser noe kolonnen, viser den feil bil, og testen blir rød.
"""
from django.utils import timezone

from . import services
from .models import Enhet, Oppdrag
from .statistikk import oppdrag_stats, rader_for_vakt
from .tests_views import OppdragBasis, _bruker, _klient


class IngenLeserDenGamleKolonnenTests(OppdragBasis):

    def setUp(self):
        super().setUp()
        self.c = _klient(_bruker('g6_sentral', 'skriv_full'))
        self.op = _bruker('g6_op', 'skriv_full')
        self.lokkedue = Enhet.objects.create(navn='Lokkedue 99')
        # Ett oppdrag med to biler (den andre ute), ett ferdig i historikken,
        # ett som bare venter.
        o1 = self._oppdrag()
        services.varsle_enhet(o1, self.annen_enhet, bruker=self.op)
        services.start_oppdrag(o1, bruker=self.op, enhet=self.annen_enhet)
        o2 = self._oppdrag(enhet=self.annen_enhet)
        services.start_oppdrag(o2, bruker=self.op, enhet=self.annen_enhet)
        services.sett_status(o2, 'fremme', bruker=self.op, enhet=self.annen_enhet)
        services.behandle_paa_sted(o2, bruker=self.op, enhet=self.annen_enhet)
        self._oppdrag()
        self.oppdragene = list(Oppdrag.objects.all())

    def _svarene(self):
        c = self.c
        naa = timezone.now()
        return {
            'lista': c.get('/oppdrag/api/oppdrag/').json(),
            'historikken': c.get('/oppdrag/api/historikk/').json(),
            'historikksøk': c.get('/oppdrag/api/historikk/?sok=Karm').json(),
            'enhetene': c.get('/oppdrag/api/enheter/').json(),
            'detaljene': [c.get(f'/oppdrag/api/oppdrag/{o.pk}/').json() for o in self.oppdragene],
            'statistikken': oppdrag_stats(self.vakt, naa=naa),
            'arkivradene': rader_for_vakt(self.vakt),
        }

    def test_en_feil_verdi_i_kolonnen_endrer_ingenting(self):
        foer = self._svarene()
        self.assertTrue(foer['lista']['data'], 'scenarioet ga en tom liste')
        Oppdrag.objects.update(enhet=self.lokkedue)
        etter = self._svarene()
        for navn in foer:
            with self.subTest(navn):
                self.assertEqual(etter[navn], foer[navn])
        # Lokkeduen er en ekte enhet og står i enhetslista — men ikke på noe oppdrag.
        self.assertNotIn('Lokkedue', str({k: v for k, v in etter.items() if k != 'enhetene'}))
