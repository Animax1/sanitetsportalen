"""Brukerdetaljenes handlinger som tabell (G2, 13. okt. 2026).

`user_detail_view` var åtte `elif`-grener på `action`; nå slår den opp i
`accounts.views._BRUKERHANDLINGER`. Testene her vokter det delingen gjorde mulig
å bryte, og det som sto udekket før den:

- **Tabellen går foran modulenes kontokoblinger.** Før sto `edit` først og
  koblingene som nummer to — tok en kobling navnet `freeze`, ville den vunnet.
  Nå ville den aldri blitt kalt. Ingen av dem gjør det, og testen sørger for at
  det forblir slik; da er rekkefølgen uten betydning.
- **Hver knapp på siden har en handler, og hver handler en knapp.** En
  skrivefeil i `value` ga før, som nå, en side som bare ble tegnet på nytt.
- **«Opphev frysing»** («Tø konto» til 22. okt. 2026) hadde ingen test.
- **De to handlingene som tegner siden i stedet for å sende videre** — et
  ugyldig skjema og et midlertidig passord — er de eneste som skriver i `side`.
"""
from __future__ import annotations

import re

from django.template.loader import get_template
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from accounts.views import _BRUKERHANDLINGER
from audit.models import AuditLog
from core.kontokobling import all_handlers


def _kilde(mal: str) -> str:
    # Malsøkeren, ikke en sti: koblingsmalene ligger i appenes egne mapper.
    return get_template(mal).template.source


def _handlingsknapper(kilde: str) -> set[str]:
    return set(re.findall(r'name="action" value="([a-z_]+)"', kilde))


class TabellenOgKnappeneTests(TestCase):

    def test_ingen_kontokobling_tar_et_navn_fra_tabellen(self):
        koblinger = {h.handling for h in all_handlers()}
        self.assertTrue(koblinger, 'Ingen kontokoblinger registrert — testen ville vært tom.')
        self.assertEqual(koblinger & set(_BRUKERHANDLINGER), set(), (
            'Tabellen går foran koblingene i `user_detail_view`; en kobling med '
            'samme navn ville aldri blitt kalt.'))

    def test_hver_knapp_har_en_handler_og_hver_handler_en_knapp(self):
        knapper = _handlingsknapper(_kilde('accounts/user_detail.html'))
        self.assertEqual(knapper, set(_BRUKERHANDLINGER))
        for h in all_handlers():
            if h.mal:
                self.assertEqual(_handlingsknapper(_kilde(h.mal)), {h.handling}, h.mal)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HandlingeneGjennomViewetTests(TestCase):

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='adm_g2', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.offer = CustomUser.objects.create_user(
            username='kari_g2', password='GammeltPassord123!', must_change_password=False,
            email='kari@example.com', fullt_navn='Kari Nordmann')
        self.c = Client()
        self.c.force_login(self.admin)
        self.url = f'/admin/brukere/{self.offer.pk}/'

    def test_to_konto(self):
        self.offer.is_active = False
        self.offer.save(update_fields=['is_active'])
        res = self.c.post(self.url, {'action': 'thaw'})
        self.assertRedirects(res, self.url, fetch_redirect_response=False)
        self.offer.refresh_from_db()
        self.assertTrue(self.offer.is_active)
        rad, = AuditLog.objects.filter(record_id=self.offer.pk, field_name='is_active')
        self.assertEqual((rad.old_value, rad.new_value), ('False', 'True'))

    def test_ugyldig_redigering_tegner_siden_med_feilene(self):
        res = self.c.post(self.url, {'action': 'edit', 'email': 'ikke-en-epost',
                                     'role': 'bruker', 'fullt_navn': 'Kari'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context['form'].is_bound)
        self.assertIn('email', res.context['form'].errors)
        self.assertTrue(res.context['tilgang_form'].is_bound)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.email, 'kari@example.com')

    def test_ukjent_handling_tegner_siden_og_rorer_ingenting(self):
        res = self.c.post(self.url, {'action': 'finnes_ikke'})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.context['form'].is_bound)
        self.assertIsNone(res.context['temp_password'])
        self.assertFalse(AuditLog.objects.filter(record_id=self.offer.pk).exists())

    def test_get_tegner_siden_med_alle_nokler(self):
        res = self.c.get(self.url)
        self.assertEqual(res.status_code, 200)
        for nokkel in ('target_user', 'form', 'tilgang_form', 'kontokoblinger',
                       'kontokoblingsfragmenter', 'temp_password', 'recent_events',
                       'has_totp_device', 'kan_slettes', 'slette_sperre'):
            self.assertIn(nokkel, res.context, nokkel)
