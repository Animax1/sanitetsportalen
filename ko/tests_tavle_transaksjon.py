"""Tavlas skrivinger må ha sin egen transaksjon (20. okt. 2026).

André: «Jeg har et lag jeg ikke får flytte og får feilmelding kan ikke flytte» —
`TransactionManagementError: select_for_update cannot be used outside of a transaction`
fra `POST /ko/api/tavle/plasser/`. `@transaction.atomic` sto over `plasser()` til a3e70e6
la `paa_pause()` inn mellom dekoratøren og funksjonen, og da satt den på feil funksjon.

**`TestCase` kunne ikke se det:** hver test går inne i en transaksjon, så `select_for_update`
klager aldri. Denne klassen er en `TransactionTestCase` — forespørselen kjører i autocommit,
som i drift. `serialized_rollback`, fordi migrasjonene sår rader (portalen, gruppene) som
resten av suiten trenger etter at tabellene er tømt.
"""
from __future__ import annotations

from django.test import Client, TransactionTestCase, override_settings

from core.vakt import hent_aktiv_vakt
from ko import tavle
from ko.models import Tavleplassering
from oppdrag.models import Lokasjon
from vaktliste.models import Vaktliste
from vaktliste.test_helpers import LAG, gruppe, lag_ressurs

from .tests_hendelseslogg import _bruker, _gi, skift


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PlasserUtenforTransaksjonTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.operator = _bruker('ko_tx')
        for modul in ('ko', 'vaktliste', 'oppdrag'):
            _gi(self.operator, modul, 'skriv_full')
        self.park = Lokasjon.objects.create(navn='Parkscene')
        self.club = Lokasjon.objects.create(navn='Club Venue')
        vl = Vaktliste.objects.create(vakt=self.vakt)
        self.lag = lag_ressurs(vaktliste=vl, navn='Lag 1', gruppe=gruppe(LAG))
        skift(self.lag)
        self.client = Client()
        self.client.force_login(self.operator)

    def _post(self, **kropp):
        return self.client.post('/ko/api/tavle/plasser/', {'ressurs_id': self.lag.pk} | kropp,
                                content_type='application/json')

    def test_flytt_gjennom_endepunktet(self):
        """Den ekte inngangen: plasser, flytt, og pause — alle tre låser forrige plassering."""
        for kropp in ({'lokasjon_id': self.park.pk}, {'lokasjon_id': self.club.pk}, {'pause': True}):
            with self.subTest(kropp=kropp):
                r = self._post(**kropp)
                self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Tavleplassering.objects.filter(ressurs=self.lag).count(), 3)
        self.assertEqual(Tavleplassering.objects.filter(ressurs=self.lag, til__isnull=True).count(), 1)

    def test_tjenesten_direkte(self):
        tavle.plasser(self.vakt, self.lag, bruker=self.operator, lokasjon=self.park)
        tavle.plasser(self.vakt, self.lag, bruker=self.operator, lokasjon=self.club)
        self.assertEqual(Tavleplassering.objects.get(ressurs=self.lag, til__isnull=True).lokasjon,
                         self.club)
