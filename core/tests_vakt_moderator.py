"""Fase 5c: «Avslutt vakt» til moderator, i egen portal (`docs/BESLUTNING_PORTALER.md` §4.8).

`/moderator/vakt/` har samme kropp som `/admin/vakt/` (`core/views_vakt.py`). Her står
det som skiller: moderatoren når bare sin portal, og gjenåpning, sletting og arkivene —
det irreversible og det som går på tvers — står hos admin.
"""
from __future__ import annotations

from unittest import mock

from django.db import transaction
from django.test import Client
from django.utils import timezone

from accounts.models import CustomUser, PortalRolle, Portaltilgang
from core.models import Vakt, Vaktportal
from core.tests_vakt_side import VaktsideBasis, _meldinger
from core.vakt import gjor_aktiv, hent_aktiv_vakt, opprett_vakt

SIDE = '/moderator/vakt/'
AVSLUTT = '/moderator/vakt/avslutt/'
NAVN = '/moderator/vakt/navn/'


class ModeratorensVaktTests(VaktsideBasis):

    def setUp(self):
        super().setUp()
        self.portal = self.vakt.portal
        self.mona = CustomUser.objects.create_user(username='mona', password='x',
                                                   must_change_password=False)
        Portaltilgang.objects.create(bruker=self.mona, portal=self.portal,
                                     rolle=PortalRolle.MODERATOR)
        self.m = Client()
        self.m.force_login(self.mona)
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        with transaction.atomic():
            self.kamp = gjor_aktiv(opprett_vakt('Kamp 1', year=2026, startet=timezone.now(),
                                                portal=self.brann))

    def test_moderatoren_ser_sin_vakt_uten_det_som_er_admins(self):
        tidligere = opprett_vakt('Gammel', year=2025, startet=timezone.now(), portal=self.portal)
        svar = self.m.get(SIDE)
        self.assertEqual(svar.status_code, 200)
        html = svar.content.decode()
        self.assertIn(self.vakt.navn, html)
        self.assertIn('Gammel', html)
        self.assertIn(f'action="{AVSLUTT}"', html)
        self.assertIn(f'action="{NAVN}"', html)
        for admins in ('/gjenaapne/', '/slett/', 'Arkiver', '/admin/'):
            self.assertNotIn(admins, html.split('<div class="portal-content">', 1)[1], admins)
        self.assertNotIn('Kamp 1', html, 'en annen portals vakt')
        self.assertTrue(tidligere.pk)

    def test_vakter_uten_portal_og_arkivene_er_admins(self):
        """Arkivene går på tvers av portalene, og en vakt uten portal (fra en backup før
        portalene) er admins å ta inn — moderatoren får ingen av dem, heller ikke i
        konteksten malen skjuler dem fra."""
        Vakt.objects.create(navn='Fra backupen', year=2024, startet=timezone.now())
        et_arkiv = [{'vakt_id': None, 'slug': 'patients', 'pk': 1, 'tittel': 'Brann 2025'}]
        with mock.patch('core.views_vakt._arkiver', return_value=et_arkiv):
            svar = self.m.get(SIDE)
        self.assertEqual(svar.context['arkiver'], [])
        self.assertNotIn('Fra backupen', [t['vakt'].navn for t in svar.context['tidligere']])
        sesjon = self.c.session
        sesjon['portal_id'] = self.portal.pk
        sesjon.save()
        admin = self.c.get('/admin/vakt/')
        self.assertIn('Fra backupen', [t['vakt'].navn for t in admin.context['tidligere']])

    def test_admin_ser_fortsatt_alt(self):
        opprett_vakt('Gammel', year=2025, startet=timezone.now(), portal=self.portal)
        # To portaler: admin velger, ellers sendes hun til velgeren.
        sesjon = self.c.session
        sesjon['portal_id'] = self.portal.pk
        sesjon.save()
        html = self.c.get('/admin/vakt/').content.decode()
        self.assertIn('/gjenaapne/', html)
        self.assertIn('/slett/', html)
        self.assertIn('action="/admin/vakt/avslutt/"', html)

    def test_moderatoren_avslutter_sin_portals_vakt_og_ikke_en_annens(self):
        svar = self.m.post(AVSLUTT, {'ny_vakt_navn': 'Neste', 'bekreft': 'ja'}, follow=True)
        self.assertRedirects(svar, SIDE)
        self.assertTrue(any('«Neste» er aktiv' in m for m in _meldinger(svar)), _meldinger(svar))
        self.assertEqual(hent_aktiv_vakt(self.portal).navn, 'Neste')
        self.assertFalse(Vakt.objects.get(pk=self.vakt.pk).er_aktiv)
        self.assertEqual(hent_aktiv_vakt(self.brann).pk, self.kamp.pk, 'Brann er urørt')

    def test_avslutningen_krever_avkrysning_ogsaa_for_moderator(self):
        self.m.post(AVSLUTT, {'ny_vakt_navn': 'Neste'})
        self.assertEqual(hent_aktiv_vakt(self.portal).pk, self.vakt.pk)

    def test_moderatoren_gir_vakta_navn(self):
        svar = self.m.post(NAVN, {'navn': 'Kamp mot Viking'})
        self.assertRedirects(svar, SIDE, fetch_redirect_response=False)
        self.assertEqual(Vakt.objects.get(pk=self.vakt.pk).navn, 'Kamp mot Viking')
        self.assertEqual(Vakt.objects.get(pk=self.kamp.pk).navn, 'Kamp 1')

    def test_admins_vaktruter_er_fortsatt_stengt_for_moderator(self):
        gammel = opprett_vakt('Gammel', year=2025, startet=timezone.now(), portal=self.portal)
        self.assertEqual(self.m.get('/admin/vakt/').status_code, 403)
        self.assertEqual(self.m.post('/admin/vakt/avslutt/',
                                     {'ny_vakt_navn': 'X', 'bekreft': 'ja'}).status_code, 403)
        self.assertEqual(self.m.post(f'/admin/vakt/{gammel.pk}/gjenaapne/').status_code, 403)
        self.assertEqual(self.m.get(f'/admin/vakt/{gammel.pk}/slett/').status_code, 403)

    def test_et_medlem_som_ikke_er_moderator_slipper_ikke_inn(self):
        Portaltilgang.objects.filter(bruker=self.mona).update(rolle=PortalRolle.MEDLEM)
        self.assertEqual(self.m.get(SIDE).status_code, 403)
        self.assertEqual(self.m.post(AVSLUTT, {'ny_vakt_navn': 'X', 'bekreft': 'ja'}).status_code,
                         403)
        self.assertEqual(self.m.post(NAVN, {'navn': 'X'}).status_code, 403)
        self.assertEqual(hent_aktiv_vakt(self.portal).pk, self.vakt.pk)

    def test_menyen_har_vakta_for_moderatoren(self):
        self.assertIn(f'href="{SIDE}"', self.m.get('/').content.decode())
