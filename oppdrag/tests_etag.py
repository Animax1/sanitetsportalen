"""ETag-en er hele svaret, ikke en feltliste (26. sep. 2026, A2).

De tre listene som polles — sentralbordets oppdrag, bilens oppdrag og
enhetslista — hadde hver sin håndskrevne liste over felt som skulle inn i
ETag-en. CHANGELOG har rettet den felt for felt i to uker («skal ikke drukne i
en 304»), og det manglet fortsatt hastegrad, problemstilling, lokasjon, antall,
grovsortering, fritekst og enhetslista. En endring rett i oppdragsvinduet
(23. sep.) ga derfor 304 hos de andre operatørene, og bilen sto med gammel
lokasjon til neste stempling.

**Nå hashes hele den serialiserte payloaden.** Det lukker feilklassen: et felt
noen legger til i svaret, er med i ETag-en uten at noen husker det. Prisen er
at svaret ikke får bære noe som regnes ut fra klokka — da ville hver polling
gitt en ny ETag og aldri 304. `test_uendret_gir_304` holder det.
"""
from __future__ import annotations

import json

from django.test import override_settings

from oppdrag import services
from oppdrag.models import Lokasjon

from .tests_flere_enheter import FlereEnheterBasis, _bruker, _klient


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EtagErHeleSvaretTests(FlereEnheterBasis):

    def setUp(self):
        super().setUp()
        self.ks = _klient(_bruker('sentral_etag', 'skriv_full'))
        bil = _bruker('bil_etag', 'skriv_handling')
        self.a.user = bil
        self.a.save(update_fields=['user'])
        self.kb = _klient(bil)
        self.o = self._oppdrag(self.a)
        services.sett_status(self.o, 'rykker_ut', enhet=self.a)

    LISTER = {
        'sentralbordet': ('ks', '/oppdrag/api/oppdrag/'),
        'bilen': ('kb', '/oppdrag/api/oppdrag/'),
        'enhetslista': ('ks', '/oppdrag/api/enheter/'),
    }

    def _etag(self, liste):
        klient, url = self.LISTER[liste]
        res = getattr(self, klient).get(url)
        self.assertEqual(res.status_code, 200, res.content)
        return res['ETag']

    def _put(self, **felt):
        res = self.ks.put(f'/oppdrag/api/oppdrag/{self.o.pk}/', data=json.dumps(felt),
                          content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)

    def test_uendret_gir_304(self):
        """**Vakta mot at svaret får et felt regnet ut fra «nå».** Da ville
        ETag-en endret seg ved hver polling, og trafikken økt i stedet for å
        synke — uten at noe annet ble rødt."""
        for liste, (klient, url) in self.LISTER.items():
            with self.subTest(liste=liste):
                etag = self._etag(liste)
                res = getattr(self, klient).get(url, HTTP_IF_NONE_MATCH=etag)
                self.assertEqual(res.status_code, 304)

    def test_en_verdi_endret_i_vinduet_synes_i_alle_tre(self):
        endringer = {
            'hastegrad': {'hastegrad': 'Haster'},
            'lokasjon': {'lokasjon_id': Lokasjon.objects.create(navn='Village').pk},
            'problemstilling': {'problemstilling': 'Brystsmerter'},
        }
        for navn, felt in endringer.items():
            foer = {liste: self._etag(liste) for liste in self.LISTER}
            self._put(**felt)
            for liste in self.LISTER:
                with self.subTest(endring=navn, liste=liste):
                    self.assertNotEqual(self._etag(liste), foer[liste])

    def test_notatet_synes_hos_sentralbordet_og_bilen(self):
        foer = {liste: self._etag(liste) for liste in ('sentralbordet', 'bilen')}
        self._put(fritekst='Pasienten sitter ved scenen')
        for liste, etag in foer.items():
            with self.subTest(liste=liste):
                self.assertNotEqual(self._etag(liste), etag)

    def test_en_bil_til_paa_et_oppdrag_i_gang_synes_hos_sentralbordet(self):
        foer = self._etag('sentralbordet')
        services.varsle_enhet(self.o, self.b)
        self.assertNotEqual(self._etag('sentralbordet'), foer)
