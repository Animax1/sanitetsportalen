"""En ukjent førstehjelper eller helsepersonell gir 400, ikke en stille `None` (26. sep. 2026, B8).

POST og PUT slo opp ID-en og svelget `DoesNotExist` med `pass`: svaret var
201/200, pasienten sto **uten** behandler, og tildelingsvarselet ble aldri
sendt. Operatøren så «lagret» og hadde ingen grunn til å sjekke. Det skjer
uten at noen gjør noe galt — et nedtrekk tegnet før noen fjernet personen
fra registeret, sender en ID som var gyldig da.
"""
from __future__ import annotations

import json

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from patients.models import Forstehjelper, Helsepersonell, Patient

UKJENT = 987654


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UkjentBehandlerTests(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        bruker = CustomUser.objects.create_user(
            username='skriver_b8', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(bruker, 'skriver')
        self.c = Client()
        self.c.force_login(bruker)

    def _post(self, **data):
        data = {'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00', **data}
        return self.c.post('/pasienter/api/patients/', data=json.dumps(data),
                           content_type='application/json')

    def _put(self, pk, **data):
        return self.c.put(f'/pasienter/api/patients/{pk}/', data=json.dumps(data),
                          content_type='application/json')

    def test_ny_pasient_med_ukjent_forstehjelper(self):
        res = self._post(forstehjelper=UKJENT)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('førstehjelper', res.json()['error'])
        self.assertFalse(Patient.objects.exists())

    def test_ny_pasient_med_ukjent_helsepersonell(self):
        res = self._post(helsepersonell_ref='ikke-et-tall')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('helsepersonell', res.json()['error'])

    def test_endring_til_ukjent_forstehjelper_rorer_ingenting(self):
        ola = Forstehjelper.objects.create(name='Ola')
        pk = self._post(forstehjelper=ola.pk, plassering='Akutt 1').json()['id']
        res = self._put(pk, forstehjelper=UKJENT, plassering='Akutt 2')
        self.assertEqual(res.status_code, 400, res.content)
        p = Patient.objects.get(pk=pk)
        self.assertEqual((p.forstehjelper_id, p.plassering), (ola.pk, 'Akutt 1'),
                         'En avvist endring skal ikke lagre halvparten')

    def test_endring_til_ukjent_helsepersonell(self):
        pk = self._post().json()['id']
        res = self._put(pk, helsepersonell_ref=UKJENT)
        self.assertEqual(res.status_code, 400, res.content)

    def test_tom_verdi_fjerner_fortsatt(self):
        """«Ingen valgt» er ikke en ukjent person."""
        hp = Helsepersonell.objects.create(name='Lege')
        pk = self._post(helsepersonell_ref=hp.pk).json()['id']
        self.assertEqual(self._put(pk, helsepersonell_ref='').status_code, 200)
        self.assertIsNone(Patient.objects.get(pk=pk).helsepersonell_ref_id)

    def test_avvist_innsending_brenner_ikke_idempotensnokkelen(self):
        """Reserver etter all validering, aldri før (`CLAUDE.md`, idempotens)."""
        self.assertEqual(self._post(forstehjelper=UKJENT, idempotency_key='k-b8').status_code, 400)
        self.assertEqual(self._post(idempotency_key='k-b8').status_code, 201)
