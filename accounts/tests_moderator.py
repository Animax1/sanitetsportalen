"""Fase 5b: moderatorens brukere (`accounts/moderering.py`, `/moderator/brukere/`).

Tjenestelaget og portene er de tunge lagene her: en moderator som ser utenfor
portalen, rører en annen moderator eller deler ut over seg selv, er nøyaktig
det §4.2 i `docs/BESLUTNING_PORTALER.md` sier aldri skal skje — og ingen ser
det på skjermen.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import get_resolver
from django.utils import timezone

from accounts import moderering
from accounts.forms import ModulTilgangForm
from accounts.models import CustomUser, ModulTilgang, PortalRolle, Portaltilgang
from accounts.test_helpers import gi_modultilgang
from audit.models import AuditLog
from core.auth_decorators import er_moderator, tom_tilgangscache
from core.models import Kontotilhorighet, Portalmodul, Tilhorighet, Vaktportal
from core.portal import eneste_portal


def _bruker(navn, **kw):
    return CustomUser.objects.create_user(username=navn, password='x',
                                          must_change_password=False, **kw)


class _Oppsett(TestCase):
    """Standard med HGSD og Leger; «Annet» står i katalogen, men ikke i portalen."""

    def setUp(self):
        self.portal = eneste_portal()
        self.hgsd = Tilhorighet.objects.create(navn='HGSD')
        self.leger = Tilhorighet.objects.create(navn='Leger', type=Tilhorighet.ANNET)
        self.annet = Tilhorighet.objects.create(navn='Annet korps')
        self.portal.tilhorigheter.set([self.hgsd, self.leger])

        self.mona = _bruker('mona', fullt_navn='Mona Moderator')
        Portaltilgang.objects.create(bruker=self.mona, portal=self.portal,
                                     rolle=PortalRolle.MODERATOR)
        gi_modultilgang(bruker=self.mona, modul_slug='vaktliste', nivaa='skriv_full')
        gi_modultilgang(bruker=self.mona, modul_slug='patients', nivaa='les')

        self.kari = self._med('kari', self.hgsd)                       # ikke medlem
        self.ola = self._med('ola', self.hgsd, medlem=True)
        gi_modultilgang(bruker=self.ola, modul_slug='vaktliste', nivaa='les')
        self.lege = self._med('lege02', self.leger, medlem=True)
        self.fremmed = self._med('fremmed', self.annet)                 # utenfor
        self.bil = _bruker('bil56', er_delt_konto=True)
        Portaltilgang.objects.create(bruker=self.bil, portal=self.portal)
        self.kollega = self._med('kollega', self.hgsd)
        Portaltilgang.objects.create(bruker=self.kollega, portal=self.portal,
                                     rolle=PortalRolle.MODERATOR)
        self.admin = _bruker('sjef', role='admin')
        Kontotilhorighet.objects.create(bruker=self.admin, tilhorighet=self.hgsd)

    def _med(self, navn, tilh, medlem=False):
        b = _bruker(navn)
        Kontotilhorighet.objects.create(bruker=b, tilhorighet=tilh)
        if medlem:
            Portaltilgang.objects.create(bruker=b, portal=self.portal)
        return b


class SynligeKontoerTests(_Oppsett):

    def test_moderatoren_ser_portalens_tilhorigheter_og_medlemmer(self):
        synlige = set(moderering.synlige_kontoer(self.portal).values_list('username', flat=True))
        self.assertEqual(synlige, {'mona', 'kari', 'ola', 'lege02', 'bil56', 'kollega'})

    def test_en_konto_med_en_annen_portals_tilhorighet_er_usynlig(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        brann.tilhorigheter.set([self.annet])
        self.assertNotIn(self.fremmed, moderering.synlige_kontoer(self.portal))
        self.assertIn(self.fremmed, moderering.synlige_kontoer(brann))
        self.assertNotIn(self.ola, moderering.synlige_kontoer(brann))

    def test_gruppene_folger_tilhorigheten_og_medlemmer_uten_staar_sist(self):
        Kontotilhorighet.objects.create(bruker=self.lege, tilhorighet=self.hgsd)
        grupper = moderering.grupper(self.portal)
        self.assertEqual([t.navn if t else None for t, _ in grupper], ['HGSD', 'Leger', None])
        hgsd = [k.username for k, _ in grupper[0][1]]
        self.assertIn('lege02', hgsd, 'to tilhørigheter: under begge')
        self.assertIn('lege02', [k.username for k, _ in grupper[1][1]])
        self.assertEqual([k.username for k, _ in grupper[2][1]], ['bil56', 'mona'])
        roller = dict((k.username, r) for k, r in grupper[0][1])
        self.assertIsNone(roller['kari'])
        self.assertEqual(roller['ola'], PortalRolle.MEDLEM)
        self.assertEqual(roller['kollega'], PortalRolle.MODERATOR)


class StyreTests(_Oppsett):

    def test_legg_til_gjor_kontoen_til_medlem(self):
        self.assertTrue(moderering.legg_til(self.mona, self.portal, self.kari))
        self.assertTrue(Portaltilgang.objects.filter(bruker=self.kari, portal=self.portal,
                                                     rolle=PortalRolle.MEDLEM).exists())
        self.assertFalse(moderering.legg_til(self.mona, self.portal, self.kari))

    def test_en_konto_utenfor_kan_ikke_legges_til(self):
        with self.assertRaises(ValidationError):
            moderering.legg_til(self.mona, self.portal, self.fremmed)
        self.assertFalse(Portaltilgang.objects.filter(bruker=self.fremmed).exists())

    def test_admin_styres_ikke_herfra(self):
        with self.assertRaises(ValidationError):
            moderering.legg_til(self.mona, self.portal, self.admin)
        with self.assertRaises(ValidationError):
            moderering.legg_til(self.admin, self.portal, self.admin)

    def test_fjern_tar_medlemskapet_og_modulradene_men_ikke_kontoen(self):
        self.assertTrue(moderering.fjern(self.mona, self.portal, self.ola))
        self.assertFalse(Portaltilgang.objects.filter(bruker=self.ola).exists())
        self.assertFalse(ModulTilgang.objects.filter(bruker=self.ola).exists())
        self.assertTrue(CustomUser.objects.filter(pk=self.ola.pk, is_active=True).exists())

    def test_fjern_rorer_ikke_medlemskap_i_en_annen_portal(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        Portaltilgang.objects.create(bruker=self.ola, portal=brann)
        moderering.fjern(self.mona, self.portal, self.ola)
        self.assertTrue(Portaltilgang.objects.filter(bruker=self.ola, portal=brann).exists())

    def test_en_moderator_rorer_ikke_en_annen_moderator(self):
        for handling in (moderering.fjern, moderering.legg_til):
            with self.assertRaises(ValidationError):
                handling(self.mona, self.portal, self.kollega)
        self.assertTrue(Portaltilgang.objects.filter(bruker=self.kollega).exists())

    def test_en_moderator_rorer_ikke_seg_selv(self):
        with self.assertRaises(ValidationError):
            moderering.fjern(self.mona, self.portal, self.mona)
        self.assertTrue(Portaltilgang.objects.filter(bruker=self.mona).exists())

    def test_admin_kan_ta_ut_en_moderator(self):
        self.assertTrue(moderering.fjern(self.admin, self.portal, self.kollega))


class UtdelbartTests(_Oppsett):

    def test_grensen_er_eget_nivaa_under_taket(self):
        self.assertEqual(moderering.utdelbart(self.mona, self.portal),
                         {'vaktliste': 'skriv_full', 'patients': 'les'})

    def test_taket_kapper_under_eget_nivaa(self):
        Portalmodul.objects.filter(portal=self.portal, modul_slug='vaktliste').update(tak='les')
        tom_tilgangscache(self.mona)
        self.assertEqual(moderering.utdelbart(self.mona, self.portal)['vaktliste'], 'les')

    def test_admin_faar_taket(self):
        ut = moderering.utdelbart(self.admin, self.portal)
        self.assertEqual(ut['vaktliste'], 'skriv_leder')
        self.assertEqual(ut['statistikk'], 'les')

    def test_et_ukjent_tak_gir_ingenting_aa_dele_ut(self):
        Portalmodul.objects.filter(portal=self.portal, modul_slug='vaktliste').update(tak='tull')
        tom_tilgangscache(self.mona)
        self.assertNotIn('vaktliste', moderering.utdelbart(self.mona, self.portal))
        self.assertNotIn('vaktliste', moderering.utdelbart(self.admin, self.portal))

    def test_matrisen_tilbyr_ikke_over_eget_nivaa_og_avviser_det(self):
        form = ModulTilgangForm(bruker=self.ola, portal=self.portal, utdeler=self.mona)
        self.assertEqual(set(form.fields), {'modul_vaktliste', 'modul_patients'})
        valg = [v for v, _ in form.fields['modul_vaktliste'].choices]
        self.assertIn('skriv_full', valg)
        self.assertNotIn('skriv_leder', valg)
        post = ModulTilgangForm({'modul_vaktliste': 'skriv_leder'}, bruker=self.ola,
                                portal=self.portal, utdeler=self.mona)
        self.assertFalse(post.is_valid())

    def test_uten_utdeler_er_matrisen_som_for(self):
        form = ModulTilgangForm(bruker=self.ola, portal=self.portal)
        self.assertIn('modul_ko', form.fields)
        self.assertIn('skriv_leder', [v for v, _ in form.fields['modul_vaktliste'].choices])


def _moderatorruter():
    ut = []

    def gaa(resolver, prefiks=''):
        for p in resolver.url_patterns:
            full = prefiks + str(p.pattern)
            if hasattr(p, 'url_patterns'):
                gaa(p, full)
            elif full.startswith('moderator/'):
                ut.append((full, p.callback))
    gaa(get_resolver())
    return ut


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(_Oppsett):

    def _klient(self, bruker):
        c = Client()
        c.force_login(bruker)
        return c

    def _sti(self, monster):
        return '/' + monster.replace('<int:pk>', str(self.ola.pk))

    def test_hver_moderatorrute_er_merket_og_stengt_for_andre(self):
        ruter = _moderatorruter()
        self.assertGreaterEqual(len(ruter), 6, 'brukerne (5b) og vakta (5c)')
        anonym = Client()
        medlem = self._klient(self.ola)
        for monster, cb in ruter:
            self.assertTrue(getattr(cb, '_moderator_kreves', False), monster)
            res = anonym.get(self._sti(monster))
            self.assertEqual(res.status_code, 302, monster)
            self.assertIn('/accounts/login/', res['Location'])
            # Porten før metoden: et medlem får 403 også på en POST-rute.
            self.assertEqual(medlem.get(self._sti(monster)).status_code, 403, monster)
            self.assertEqual(medlem.post(self._sti(monster)).status_code, 403, monster)
            # 405 er en rute som bare tar POST — porten slapp gjennom.
            for slipper in (self.mona, self.admin):
                self.assertIn(self._klient(slipper).get(self._sti(monster)).status_code,
                              (200, 405), monster)

    def test_moderator_i_en_annen_portal_er_ikke_moderator_her(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        Portaltilgang.objects.create(bruker=self.ola, portal=brann, rolle=PortalRolle.MODERATOR)
        self.assertTrue(er_moderator(self.ola, brann))
        self.assertFalse(er_moderator(self.ola, self.portal))

    def test_en_konto_utenfor_portalen_gir_404(self):
        c = self._klient(self.mona)
        self.assertEqual(c.get(f'/moderator/brukere/{self.fremmed.pk}/').status_code, 404)
        self.assertEqual(c.get(f'/moderator/brukere/{self.admin.pk}/').status_code, 404)
        # En konto utenfor i utvalget stopper hele innsendingen — kari kommer ikke inn heller.
        c.post('/moderator/brukere/', {'bruker': [self.kari.pk, self.fremmed.pk]})
        self.assertFalse(Portaltilgang.objects.filter(bruker__in=[self.kari, self.fremmed])
                         .exists())
        c.post('/moderator/brukere/', {'bruker': 'x'})
        self.assertFalse(Portaltilgang.objects.filter(bruker=self.fremmed).exists())

    def test_legg_til_og_ta_ut_fra_siden_med_audit(self):
        c = self._klient(self.mona)
        res = c.post('/moderator/brukere/', {'bruker': self.kari.pk})
        self.assertRedirects(res, '/moderator/brukere/')
        self.assertTrue(Portaltilgang.objects.filter(bruker=self.kari).exists())
        c.post(f'/moderator/brukere/{self.kari.pk}/', {'handling': 'fjern'})
        self.assertFalse(Portaltilgang.objects.filter(bruker=self.kari).exists())
        logget = list(AuditLog.objects.filter(table_name='accounts_portaltilgang',
                                              record_id=self.kari.pk)
                      .values_list('new_value', flat=True))
        self.assertEqual(sorted(logget), ['ja', 'nei'])

    def test_flere_legges_til_i_ett_trykk(self):
        """André, 18. okt. 2026: «å legge til flere brukere samtidig må være enklere
        enn å trykke per bruker»."""
        andre = _bruker('andre')
        Kontotilhorighet.objects.create(bruker=andre, tilhorighet=self.leger)
        svar = self._klient(self.mona).post('/moderator/brukere/',
                                            {'bruker': [self.kari.pk, andre.pk]}, follow=True)
        self.assertEqual(set(Portaltilgang.objects.filter(portal=self.portal,
                                                          bruker__in=[self.kari, andre])
                             .values_list('bruker__username', flat=True)), {'kari', 'andre'})
        self.assertContains(svar, '2 lagt til')
        self.assertEqual(AuditLog.objects.filter(table_name='accounts_portaltilgang',
                                                 new_value='ja').count(), 2)

    def test_en_kollega_i_utvalget_stopper_alle(self):
        Portaltilgang.objects.filter(bruker=self.kollega).delete()
        Portaltilgang.objects.create(bruker=self.kollega, portal=self.portal,
                                     rolle=PortalRolle.MODERATOR)
        self._klient(self.mona).post('/moderator/brukere/',
                                     {'bruker': [self.kari.pk, self.kollega.pk]})
        self.assertFalse(Portaltilgang.objects.filter(bruker=self.kari).exists())

    def test_lista_har_avkrysning_for_dem_utenfor_og_rediger_tilgang_for_medlemmene(self):
        html = self._klient(self.mona).get('/moderator/brukere/').content.decode()
        self.assertIn(f'name="bruker" value="{self.kari.pk}"', html)
        self.assertNotIn(f'name="bruker" value="{self.ola.pk}"', html)
        self.assertIn(f'href="/moderator/brukere/{self.ola.pk}/"', html)
        self.assertIn('Rediger tilgang', html)

    def test_moderatoren_kan_ikke_ta_ut_en_kollega_fra_siden(self):
        self._klient(self.mona).post(f'/moderator/brukere/{self.kollega.pk}/',
                                     {'handling': 'fjern'})
        self.assertTrue(Portaltilgang.objects.filter(bruker=self.kollega).exists())

    def test_tilgang_lagres_innenfor_og_avvises_over(self):
        c = self._klient(self.mona)
        c.post(f'/moderator/brukere/{self.ola.pk}/',
               {'handling': 'moduler', 'modul_vaktliste': 'skriv_full', 'modul_patients': 'les'})
        tom_tilgangscache(self.ola)
        rader = dict(ModulTilgang.objects.filter(bruker=self.ola)
                     .values_list('modul_slug', 'nivaa'))
        self.assertEqual(rader, {'vaktliste': 'skriv_full', 'patients': 'les'})
        self.assertTrue(AuditLog.objects.filter(table_name='accounts_modultilgang',
                                                record_id=self.ola.pk,
                                                new_value='skriv_full').exists())
        c.post(f'/moderator/brukere/{self.ola.pk}/',
               {'handling': 'moduler', 'modul_vaktliste': 'skriv_leder'})
        self.assertEqual(ModulTilgang.objects.get(bruker=self.ola, modul_slug='vaktliste').nivaa,
                         'skriv_full')
        c.post(f'/moderator/brukere/{self.ola.pk}/', {'handling': 'moduler', 'modul_ko': 'les'})
        self.assertFalse(ModulTilgang.objects.filter(bruker=self.ola, modul_slug='ko').exists())

    def test_tilgang_gis_ikke_til_en_som_ikke_er_medlem(self):
        self._klient(self.mona).post(f'/moderator/brukere/{self.kari.pk}/',
                                     {'handling': 'moduler', 'modul_patients': 'les'})
        self.assertFalse(Portaltilgang.objects.filter(bruker=self.kari).exists())
        self.assertFalse(ModulTilgang.objects.filter(bruker=self.kari).exists())

    def test_tilgang_til_seg_selv_eller_en_kollega_avvises(self):
        c = self._klient(self.mona)
        for konto in (self.mona, self.kollega):
            c.post(f'/moderator/brukere/{konto.pk}/',
                   {'handling': 'moduler', 'modul_vaktliste': 'les'})
        self.assertEqual(ModulTilgang.objects.get(bruker=self.mona, modul_slug='vaktliste').nivaa,
                         'skriv_full')
        self.assertFalse(ModulTilgang.objects.filter(bruker=self.kollega).exists())

    def test_menyen_viser_lenkene_for_moderatoren_og_admin(self):
        """Admin ser dem også (André, 18. okt. 2026)."""
        for bruker, ser in ((self.mona, True), (self.ola, False), (self.admin, True)):
            html = self._klient(bruker).get('/').content.decode()
            self.assertEqual('/moderator/brukere/' in html, ser, bruker.username)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NyKontoTests(_Oppsett):

    def _post(self, **data):
        c = Client()
        c.force_login(self.mona)
        return c.post('/moderator/brukere/ny/', data)

    def test_ny_konto_med_engangspassord(self):
        res = self._post(username='Nina.Ny', fullt_navn='Nina Ny', tilhorighet=self.hgsd.pk,
                         metode='passord', role='admin', er_delt_konto='on')
        self.assertEqual(res.status_code, 200)
        nina = CustomUser.objects.get(username='nina.ny')
        self.assertEqual(nina.role, 'bruker', 'rollen settes aldri herfra')
        self.assertFalse(nina.er_delt_konto)
        self.assertTrue(nina.must_change_password)
        self.assertTrue(nina.has_usable_password())
        self.assertContains(res, 'Engangspassordet')
        self.assertTrue(Portaltilgang.objects.filter(bruker=nina, portal=self.portal,
                                                     rolle=PortalRolle.MEDLEM).exists())
        self.assertTrue(Kontotilhorighet.objects.filter(bruker=nina, tilhorighet=self.hgsd)
                        .exists())
        self.assertTrue(AuditLog.objects.filter(record_id=nina.pk, action='CREATE').exists())

    def test_ny_konto_med_invitasjon(self):
        res = self._post(username='nils', email='nils@example.org', tilhorighet=self.leger.pk,
                         metode='invitasjon')
        nils = CustomUser.objects.get(username='nils')
        self.assertRedirects(res, f'/moderator/brukere/{nils.pk}/', fetch_redirect_response=False)
        self.assertFalse(nils.has_usable_password())

    def test_tilhorigheten_maa_vaere_portalens(self):
        res = self._post(username='nora', tilhorighet=self.annet.pk, metode='passord')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='nora').exists())

    def test_med_epost_kreves_tilhorighet(self):
        self._post(username='nora', email='nora@example.org', metode='passord')
        self.assertFalse(CustomUser.objects.filter(username='nora').exists())

    def test_uten_epost_trengs_ingen_tilhorighet(self):
        """André, 18. okt. 2026: «kontoer uten epost trenger ikke tilhørighet»."""
        self._post(username='nora', metode='passord')
        nora = CustomUser.objects.get(username='nora')
        self.assertFalse(Kontotilhorighet.objects.filter(bruker=nora).exists())
        self.assertTrue(Portaltilgang.objects.filter(bruker=nora, portal=self.portal).exists())

    def test_tilgangen_settes_i_samme_skjema_og_innenfor_grensen(self):
        """André, 18. okt. 2026: «dårlig ux å opprette bruker og så ikke kunne
        umiddelbart sette tilganger»."""
        self.assertContains(self._klient_get(), 'name="modul_vaktliste"')
        self._post(username='nora', metode='passord', modul_vaktliste='skriv_full',
                   modul_patients='les')
        nora = CustomUser.objects.get(username='nora')
        self.assertEqual(dict(ModulTilgang.objects.filter(bruker=nora)
                              .values_list('modul_slug', 'nivaa')),
                         {'vaktliste': 'skriv_full', 'patients': 'les'})
        self.assertTrue(AuditLog.objects.filter(table_name='accounts_modultilgang',
                                                record_id=nora.pk).exists())

    def test_over_eget_nivaa_gir_ingen_konto(self):
        self._post(username='nora', metode='passord', modul_vaktliste='skriv_leder')
        self.assertFalse(CustomUser.objects.filter(username='nora').exists())

    def _klient_get(self):
        c = Client()
        c.force_login(self.mona)
        return c.get('/moderator/brukere/ny/')

    def test_en_epost_som_finnes_gir_ingen_konto_nummer_to(self):
        self.ola.email = 'ola@example.org'
        self.ola.save()
        self._post(username='ola2', email='OLA@example.org', tilhorighet=self.hgsd.pk,
                   metode='passord')
        self.assertFalse(CustomUser.objects.filter(username='ola2').exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AdminlistaFiltreneTests(_Oppsett):

    def _navn(self, filter_):
        c = Client()
        c.force_login(self.admin)
        res = c.get('/admin/brukere/', {'filter': filter_})
        return {u.username for u in res.context['users']}

    def test_uten_portal(self):
        self.assertEqual(self._navn('uten_portal'), {'kari', 'fremmed'})

    def test_ikke_innlogget_paa_12_mnd(self):
        naa = timezone.now()
        CustomUser.objects.update(last_login_at=naa)
        CustomUser.objects.filter(pk=self.kari.pk).update(last_login_at=naa - timedelta(days=366))
        CustomUser.objects.filter(pk=self.ola.pk).update(last_login_at=naa - timedelta(days=364))
        CustomUser.objects.filter(pk=self.lege.pk).update(last_login_at=None)
        self.assertEqual(self._navn('inaktiv'), {'kari', 'lege02'})

    def test_ukjent_filter_er_alle(self):
        self.assertEqual(len(self._navn('tull')), CustomUser.objects.count())
