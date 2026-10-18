"""Fase 5c: innstillingene delt i portalens og systemets (`docs/BESLUTNING_PORTALER.md` §4.7).

Sperra er at moderatorens innsending siles til handlernes `portalfelt`, og at et
fraværende felt er «behold» i hver handler. Testene prøver den med et systemfelt
moderatoren sender likevel — knappen hun ikke ser, er ikke en sperre.
"""
from __future__ import annotations

import re

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, PortalRolle, Portaltilgang
from core.models import AppSetting, Vaktportal
from core.portal import eneste_portal
from core.portalinnstillinger import all_handlers

SIDE = '/moderator/innstillinger/'
ADMIN = '/admin/innstillinger/'


def _navn(html):
    """`name="…"` i skjemaet, uten CSRF-feltet. En radiogruppe er ett felt."""
    skjema = html.split('<form method="post"', 1)[1]
    ut, radio = [], set()
    for tagg in re.findall(r'<(?:input|select|textarea)\b[^>]*>', skjema):
        navn = re.search(r'name="([^"]+)"', tagg)
        if not navn or navn.group(1) == 'csrfmiddlewaretoken':
            continue
        if 'type="radio"' in tagg:
            if navn.group(1) in radio:
                continue
            radio.add(navn.group(1))
        ut.append(navn.group(1))
    return ut


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InnstillingeneDeltTests(TestCase):

    def setUp(self):
        self.portal = eneste_portal()
        self.mona = CustomUser.objects.create_user(username='mona', password='x',
                                                   must_change_password=False)
        Portaltilgang.objects.create(bruker=self.mona, portal=self.portal,
                                     rolle=PortalRolle.MODERATOR)
        self.m = Client()
        self.m.force_login(self.mona)
        self.admin = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                                    must_change_password=False)
        self.a = Client()
        self.a.force_login(self.admin)

    def _portalfelt(self):
        return frozenset().union(*(h.portalfelt for h in all_handlers()))

    def test_moderatoren_ser_bare_portalens_felter(self):
        felt = set(_navn(self.m.get(SIDE).content.decode()))
        self.assertEqual(felt, set(self._portalfelt()))
        for system in ('session_timeout_hours', 'ko_logg_dager', 'park_angrefrist',
                       'oppdrag_fritekst_dager'):
            self.assertNotIn(system, felt)

    def test_admin_ser_hvert_felt_en_gang(self):
        """En blandet malbit tegnes i begge seksjonene; hver halvdel skal stå én gang.
        Glemmer en ny blandet malbit flaggene, står feltene dobbelt — og den siste
        verdien i POST vinner i stillhet."""
        felt = _navn(self.a.get(ADMIN).content.decode())
        doble = sorted({n for n in felt if felt.count(n) > 1})
        self.assertEqual(doble, [])
        self.assertTrue(set(self._portalfelt()) <= set(felt))
        self.assertIn('session_timeout_hours', felt)
        self.assertIn('ko_logg_dager', felt)

    def test_portalfeltene_finnes_i_malbitene(self):
        """En skrivefeil i `portalfelt` ville silt bort et felt moderatoren ser —
        og lagret det som «av» der en avkryssing har et følgefelt."""
        felt = set(_navn(self.m.get(SIDE).content.decode()))
        for h in all_handlers():
            self.assertTrue(h.portalfelt <= felt, (h.slug, h.portalfelt - felt))

    def test_systemfelt_fra_moderatoren_lagres_ikke(self):
        AppSetting.set('session_timeout_hours', 8)
        svar = self.m.post(SIDE, {
            'session_timeout_hours': '1', 'ko_logg_dager': '1', 'park_angrefrist': '1',
            'ko_tavle_timer': '12', 'ko_chat_sendt': '1',
        })
        self.assertRedirects(svar, SIDE, fetch_redirect_response=False)
        self.assertEqual(str(AppSetting.get('session_timeout_hours')), '8')
        self.assertIsNone(AppSetting.get('ko.logg_dager'))
        self.assertIsNone(AppSetting.get('park_angrefrist_min'))
        from ko import tavle
        self.assertEqual(str(AppSetting.get_i_portal(tavle.TIMER_NOKKEL)), '12')

    def test_portalverdien_er_portalens(self):
        from ko import tavle
        self.m.post(SIDE, {'ko_tavle_timer': '12'})
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.assertEqual(str(AppSetting.get_i_portal(tavle.TIMER_NOKKEL, portal=self.portal)),
                         '12')
        self.assertNotEqual(str(AppSetting.get_i_portal(tavle.TIMER_NOKKEL, portal=brann)),
                            '12')

    def test_en_feil_i_portalfeltet_stopper_innsendingen(self):
        from ko import tavle
        self.m.post(SIDE, {'ko_tavle_timer': 'x', 'vaktliste_fil_intervall_min': '5'})
        self.assertIsNone(AppSetting.get_i_portal(tavle.TIMER_NOKKEL))

    def test_admin_lagrer_fortsatt_systemet(self):
        self.a.post(ADMIN, {'session_timeout_hours': '6'})
        self.assertEqual(str(AppSetting.get('session_timeout_hours')), '6')

    def test_porten(self):
        Portaltilgang.objects.filter(bruker=self.mona).update(rolle=PortalRolle.MEDLEM)
        self.assertEqual(self.m.get(SIDE).status_code, 403)
        self.assertEqual(self.m.post(SIDE, {'ko_tavle_timer': '12'}).status_code, 403)
        self.assertEqual(self.m.get(ADMIN).status_code, 403)

    def test_en_systemhandler_kjores_ikke_for_moderatoren(self):
        """Silen alene holder ikke: en handler som skriver også når feltet mangler —
        en avkryssing uten følgefelt — ville nullstilt systemets verdi hver gang
        moderatoren lagret. Derfor kjøres bare handlerne med `portalfelt`."""
        from core import portalinnstillinger

        class _SkriverAlltid(portalinnstillinger.BasePortalinnstillingHandler):
            slug = 'test_skriver_alltid'

            def valider(self, post):
                return {'av': post.get('test_bryter') is None}

            def lagre(self, verdier):
                AppSetting.set('test.skriver_alltid', 'av' if verdier['av'] else 'paa')

        sikret = portalinnstillinger.all_handlers()
        self.addCleanup(lambda: [portalinnstillinger.clear_registry()]
                        + [portalinnstillinger.register(h) for h in sikret])
        portalinnstillinger.register(_SkriverAlltid())
        AppSetting.set('test.skriver_alltid', 'paa')
        self.m.post(SIDE, {'ko_tavle_timer': '12'})
        self.assertEqual(AppSetting.get('test.skriver_alltid'), 'paa')

    def test_standarden_er_systemet(self):
        from core.portalinnstillinger import BasePortalinnstillingHandler
        self.assertEqual(BasePortalinnstillingHandler.portalfelt, frozenset())
        self.assertFalse(BasePortalinnstillingHandler.bare_portal)
