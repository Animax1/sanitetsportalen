"""Fase 5a: portalene, modulene og taket (`core/portaladmin.py`, `core.models.Portalmodul`).

Tjenestelaget er det tunge laget her (CLAUDE.md, «Mutasjonstesting»): et tak
som ikke kapper, eller en modul som ikke forsvinner, legger seg i hva hver
konto i portalen får — og ses av ingen.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang, PortalRolle, Portaltilgang
from accounts.test_helpers import gi_modultilgang
from audit.models import AuditLog
from core import portaladmin
from core.auth_decorators import har_tilgang, nivaa_for, tom_tilgangscache
from core.models import Portalmodul, Tilhorighet, Vaktportal
from core.portal import eneste_portal


def _bruker(navn='kari', **kw):
    return CustomUser.objects.create_user(username=navn, password='x',
                                          must_change_password=False, **kw)


class ModuleneIPortalenTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()

    def test_standard_har_alle_modulene_etter_migrasjonen(self):
        """`post_migrate` legger modulene i portalene når `ModuleSettings` får
        radene sine — i en fersk base skjer det etter datamigrasjonen."""
        from core.modules import get_all_modules
        har = set(Portalmodul.objects.filter(portal=self.standard)
                  .values_list('modul_slug', flat=True))
        self.assertEqual(har, {m.slug for m in get_all_modules()})

    def test_en_ny_portal_faar_alle_med_modulens_eget_toppnivaa(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        tak = dict(Portalmodul.objects.filter(portal=brann).values_list('modul_slug', 'tak'))
        self.assertEqual(tak['statistikk'], 'les', 'statistikk har bare les')
        self.assertEqual(tak['vaktliste'], 'skriv_leder')
        self.assertEqual(tak['park'], 'skriv_leder')

    def test_en_ny_modul_kommer_inn_i_alle_portaler_en_gang(self):
        from core.models import ModuleSettings
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        Portalmodul.objects.filter(modul_slug='park').delete()
        ModuleSettings.objects.filter(slug='park').delete()
        ModuleSettings.ensure_defaults_exist(portalmodell=Portalmodul)
        self.assertEqual(Portalmodul.objects.filter(modul_slug='park').count(), 2)
        # Admin tar den ut av Brann; neste deploy setter den ikke inn igjen.
        Portalmodul.objects.filter(portal=brann, modul_slug='park').delete()
        ModuleSettings.ensure_defaults_exist(portalmodell=Portalmodul)
        self.assertFalse(Portalmodul.objects.filter(portal=brann, modul_slug='park').exists())


class TaketKapperTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.kari = _bruker()
        gi_modultilgang(bruker=self.kari, modul_slug='patients', nivaa='skriv_full')

    def _nivaa(self):
        tom_tilgangscache(self.kari)
        return nivaa_for(self.kari, 'patients')

    def test_taket_kapper_det_som_alt_er_delt_ut(self):
        self.assertEqual(self._nivaa(), 'skriv_full')
        Portalmodul.objects.filter(portal=self.standard, modul_slug='patients').update(tak='les')
        self.assertEqual(self._nivaa(), 'les')
        self.assertTrue(har_tilgang(self.kari, 'patients', 'les'))
        self.assertFalse(har_tilgang(self.kari, 'patients', 'skriv_full'))

    def test_et_tak_over_raden_gir_raden(self):
        Portalmodul.objects.filter(portal=self.standard, modul_slug='patients').update(
            tak='skriv_leder')
        self.assertEqual(self._nivaa(), 'skriv_full')

    def test_modul_uten_rad_finnes_ikke(self):
        Portalmodul.objects.filter(portal=self.standard, modul_slug='patients').delete()
        self.assertIsNone(self._nivaa())
        self.assertTrue(ModulTilgang.objects.filter(modul_slug='patients').exists(),
                        'tilgangen står; den gir bare ingenting')

    def test_ukjent_tak_stenger(self):
        Portalmodul.objects.filter(portal=self.standard, modul_slug='patients').update(tak='alt')
        self.assertIsNone(self._nivaa())

    def test_admin_er_uberoert(self):
        admin = _bruker('sjef', role='admin')
        Portalmodul.objects.filter(portal=self.standard, modul_slug='patients').delete()
        self.assertTrue(har_tilgang(admin, 'patients', 'skriv_full'))

    def test_matrisen_tilbyr_bare_portalens_moduler_og_opp_til_taket(self):
        from accounts.forms import ModulTilgangForm
        Portalmodul.objects.filter(portal=self.standard, modul_slug='oppdrag').update(
            tak='skriv_full')
        Portalmodul.objects.filter(portal=self.standard, modul_slug='park').delete()
        skjema = ModulTilgangForm(bruker=self.kari, portal=self.standard)
        self.assertNotIn('modul_park', skjema.fields)
        valg = [v for v, _ in skjema.fields['modul_oppdrag'].choices]
        self.assertIn('skriv_full', valg)
        self.assertNotIn('skriv_leder', valg)


class TjenestelagetTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()

    def test_slug_lages_av_navnet_med_aeoeaa(self):
        self.assertEqual(portaladmin.foreslaa_slug('Røros Ålesund Ærø 2026'),
                         'roros-alesund-aero-2026')
        portal = portaladmin.opprett_portal('Landsskytterstevnet 2026')
        self.assertEqual(portal.slug, 'landsskytterstevnet-2026')

    def test_opprett_avviser(self):
        portaladmin.opprett_portal('Brann')
        for navn, slug, melding in (('', '', 'navn'), ('brann', 'b2', 'finnes'),
                                    ('Annen', 'brann', 'tatt'), ('Annen', 'Store Bokstaver', 'små')):
            with self.subTest(navn=navn, slug=slug):
                with self.assertRaisesMessage(ValidationError, melding):
                    portaladmin.opprett_portal(navn, slug)

    def test_siste_aktive_portal_kan_ikke_deaktiveres(self):
        with self.assertRaisesMessage(ValidationError, 'eneste aktive'):
            portaladmin.sett_grunnlag(self.standard, navn='Standard', er_aktiv=False)
        self.standard.refresh_from_db()
        self.assertTrue(self.standard.er_aktiv)
        brann = portaladmin.opprett_portal('Brann')
        portaladmin.sett_grunnlag(self.standard, navn='Standard', er_aktiv=False)
        self.standard.refresh_from_db()
        self.assertFalse(self.standard.er_aktiv)
        with self.assertRaisesMessage(ValidationError, 'eneste aktive'):
            portaladmin.sett_grunnlag(brann, navn='Brann', er_aktiv=False)

    def test_navnet_kan_ikke_ta_en_annens(self):
        portaladmin.opprett_portal('Brann')
        with self.assertRaisesMessage(ValidationError, 'finnes'):
            portaladmin.sett_grunnlag(self.standard, navn='BRANN', er_aktiv=True)

    def test_moduler_med_tak_og_ut(self):
        endringer = portaladmin.sett_moduler(self.standard, {'park': None, 'oppdrag': 'skriv_full'})
        self.assertEqual(sorted(endringer), [('oppdrag', 'skriv_leder', 'skriv_full'),
                                             ('park', 'skriv_leder', None)])
        self.assertFalse(Portalmodul.objects.filter(portal=self.standard, modul_slug='park').exists())
        self.assertEqual(Portalmodul.objects.get(portal=self.standard, modul_slug='oppdrag').tak,
                         'skriv_full')
        portaladmin.sett_moduler(self.standard, {'park': 'les'})
        self.assertEqual(Portalmodul.objects.get(portal=self.standard, modul_slug='park').tak, 'les')

    def test_moduler_valideres_foer_noe_skrives(self):
        for onsket, melding in (({'oppdrag': 'skriv_full', 'park': 'skriv_full'}, 'har ikke nivået'),
                                ({'finnes_ikke': 'les'}, 'Ukjent modul'),
                                ({'core': 'les'}, 'Ukjent modul')):
            with self.subTest(onsket=onsket):
                with self.assertRaisesMessage(ValidationError, melding):
                    portaladmin.sett_moduler(self.standard, onsket)
        self.assertEqual(Portalmodul.objects.get(portal=self.standard, modul_slug='oppdrag').tak,
                         'skriv_leder', 'oppdrag ble ikke skrevet før park avviste')

    def test_tilhorighetene(self):
        hgsd = Tilhorighet.objects.create(navn='HGSD')
        portaladmin.sett_tilhorigheter(self.standard, [hgsd.pk])
        self.assertEqual(list(self.standard.tilhorigheter.all()), [hgsd])
        with self.assertRaisesMessage(ValidationError, 'ukjente'):
            portaladmin.sett_tilhorigheter(self.standard, [hgsd.pk, 987654])

    def test_moderator_og_tilbake(self):
        kari = _bruker()
        portaladmin.sett_moderator(self.standard, kari, True)
        self.assertEqual(Portaltilgang.objects.get(bruker=kari).rolle, PortalRolle.MODERATOR)
        portaladmin.sett_moderator(self.standard, kari, False)
        self.assertEqual(Portaltilgang.objects.get(bruker=kari).rolle, PortalRolle.MEDLEM,
                         'medlemskapet står')

    def test_admin_blir_ikke_moderator(self):
        with self.assertRaisesMessage(ValidationError, 'Global admin'):
            portaladmin.sett_moderator(self.standard, _bruker('sjef', role='admin'), True)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SideneTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.sjef = _bruker('sjef', role='admin')
        self.c = Client()
        self.c.force_login(self.sjef)

    def test_bare_admin(self):
        kari = _bruker()
        gi_modultilgang(bruker=kari, modul_slug='patients', nivaa='skriv_leder')
        portaladmin.sett_moderator(self.standard, kari, True)
        c = Client()
        c.force_login(kari)
        for sti in ('/admin/portaler/', f'/admin/portaler/{self.standard.pk}/'):
            with self.subTest(sti=sti):
                self.assertIn(c.get(sti).status_code, (302, 403))

    def test_ny_portal_fra_lista(self):
        svar = self.c.post('/admin/portaler/', {'navn': 'Brann'})
        brann = Vaktportal.objects.get(navn='Brann')
        self.assertRedirects(svar, f'/admin/portaler/{brann.pk}/', fetch_redirect_response=False)
        self.assertContains(self.c.get('/admin/portaler/'), 'brann')

    def test_modulene_fra_siden_og_auditen(self):
        svar = self.c.post(f'/admin/portaler/{self.standard.pk}/', {
            'handling': 'moduler', 'med_oppdrag': 'on', 'tak_oppdrag': 'skriv_full',
            'med_patients': 'on', 'tak_patients': 'les'})
        self.assertEqual(svar.status_code, 302)
        tak = dict(Portalmodul.objects.filter(portal=self.standard)
                   .values_list('modul_slug', 'tak'))
        self.assertEqual((tak['oppdrag'], tak['patients']), ('skriv_full', 'les'))
        self.assertNotIn('park', tak, 'ikke krysset av = ute av portalen')
        self.assertIn('core', tak, 'admin-modulene røres ikke fra siden')
        logget = AuditLog.objects.filter(table_name='core_portalmodul')
        self.assertTrue(logget.filter(action='UPDATE', field_name='tak', new_value='les').exists())
        self.assertTrue(logget.filter(action='DELETE').exists())

    def test_moderator_fra_siden_logges(self):
        kari = _bruker()
        self.c.post(f'/admin/portaler/{self.standard.pk}/',
                    {'handling': 'moderator', 'brukernavn': 'kari', 'er_moderator': '1'})
        self.assertEqual(Portaltilgang.objects.get(bruker=kari).rolle, PortalRolle.MODERATOR)
        self.assertTrue(AuditLog.objects.filter(table_name='accounts_portaltilgang',
                                                record_id=kari.pk).exists())
        self.assertContains(self.c.get(f'/admin/portaler/{self.standard.pk}/'), 'kari')

    def test_siden_viser_avvisningen(self):
        svar = self.c.post(f'/admin/portaler/{self.standard.pk}/',
                           {'handling': 'grunnlag', 'navn': 'Standard'}, follow=True)
        self.assertContains(svar, 'eneste aktive')
