"""Fase 5c: portalnavnet i fanetittelen når kontoen har flere portaler (§4.4).

Går gjennom `miljo.fane`, som hver mal og `fanetittel()` leser alt — med én
portal er tittelen som før.
"""
from __future__ import annotations

import re

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, Portaltilgang
from core.models import Vaktportal
from core.portal import SESJON_NOKKEL, eneste_portal


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False, PORTAL_MILJO='test')
class PortalnavnetIFanenTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.kari = CustomUser.objects.create_user(username='kari', password='x',
                                                   must_change_password=False)
        Portaltilgang.objects.create(bruker=self.kari, portal=self.standard)
        self.c = Client()
        self.c.force_login(self.kari)

    def _tittel_og_prefiks(self):
        html = self.c.get('/').content.decode()
        tittel = re.search(r'<title>(.*?)</title>', html, re.S).group(1).strip()
        prefiks = re.search(r'PORTAL_FANEPREFIKS = "(.*?)"', html).group(1)
        return tittel, prefiks

    def test_med_en_portal_er_tittelen_som_for(self):
        tittel, prefiks = self._tittel_og_prefiks()
        self.assertTrue(tittel.startswith('[TEST] '), tittel)
        self.assertNotIn('Standard', tittel)
        self.assertEqual(prefiks, '[TEST] ')

    def test_med_flere_portaler_staar_navnet_i_fanen(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        Portaltilgang.objects.create(bruker=self.kari, portal=brann)
        sesjon = self.c.session
        sesjon[SESJON_NOKKEL] = brann.pk
        sesjon.save()
        tittel, prefiks = self._tittel_og_prefiks()
        self.assertTrue(tittel.startswith('[TEST] Brann · '), tittel)
        self.assertEqual(prefiks, '[TEST] Brann · ')
