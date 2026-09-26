"""`scripts/sikkerhetsruter.json` er i takt med `urlpatterns` (26. sep. 2026, B5).

Se `core/sikkerhetsruter.py` for hvorfor lista ikke lenger skrives for hånd.
Her prøves tre ting: at fila er det kommandoen ville skrevet, at klassifiseringen
ikke peker på ruter som er borte, og — det scriptet gjør utenfra — at hver
stengt rute faktisk er stengt for en anonym bruker, med GET og med POST.
"""
from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from core import sikkerhetsruter


class FilaErITaktTests(TestCase):

    def test_fila_er_det_kommandoen_ville_skrevet(self):
        self.assertEqual(
            json.loads(sikkerhetsruter.FIL.read_text(encoding='utf-8')), sikkerhetsruter.bygg(),
            'Rutene har endret seg. Kjør: python manage.py sikkerhetsruter')

    def test_klassifiseringen_peker_ikke_paa_ruter_som_er_borte(self):
        """Samme feil som den håndskrevne lista hadde: en åpen rute som
        forsvant, ville stått her som «vurdert» uten å finnes."""
        monstre = set(sikkerhetsruter.alle_monstre())
        for navn, tabell in (('AAPNE', sikkerhetsruter.AAPNE),
                             ('OMDIRIGERER', sikkerhetsruter.OMDIRIGERER)):
            with self.subTest(tabell=navn):
                self.assertEqual(sorted(set(tabell) - monstre), [])

    def test_hver_aapning_er_begrunnet(self):
        for monster, grunn in {**sikkerhetsruter.AAPNE, **sikkerhetsruter.OMDIRIGERER}.items():
            with self.subTest(monster=monster):
                self.assertTrue(grunn.strip())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AnonymErStengtUteTests(TestCase):
    """Det scriptet gjør mot staging, gjort i suiten: aldri 200, aldri 500."""

    def _stengt(self, status, location):
        return status in (401, 403, 404, 405) or (
            status in (301, 302) and '/accounts/login/' in location)

    def test_get(self):
        c = Client()
        feil = []
        for sti in sikkerhetsruter.bygg()['stengt']:
            res = c.get(sti)
            if not self._stengt(res.status_code, res.get('Location', '')):
                feil.append(f'GET {sti} → {res.status_code} {res.get("Location", "")}')
        self.assertEqual(feil, [])

    def test_post_uten_csrf(self):
        c = Client(enforce_csrf_checks=True)
        feil = []
        for sti in sikkerhetsruter.bygg()['stengt']:
            res = c.post(sti, data='{}', content_type='application/json')
            if not self._stengt(res.status_code, res.get('Location', '')):
                feil.append(f'POST {sti} → {res.status_code}')
        self.assertEqual(feil, [])

    def test_omdirigeringene_gir_aldri_200(self):
        c = Client()
        for sti in sikkerhetsruter.bygg()['omdirigerer']:
            with self.subTest(sti=sti):
                self.assertIn(c.get(sti).status_code, (301, 302, 404))

    def test_de_aapne_svarer_uten_innlogging(self):
        """200, eller 400 for en lenke med ugyldig token — siden sier at lenken
        ikke virker. Aldri en omdirigering til innloggingen, aldri 500."""
        c = Client()
        for sti in sikkerhetsruter.bygg()['aapne']:
            with self.subTest(sti=sti):
                self.assertIn(c.get(sti).status_code, (200, 400))
