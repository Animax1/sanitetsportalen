"""Portaltilgangene, portalregelen og fanevakten (17. okt. 2026, fase 2).

`docs/BESLUTNING_PORTALER.md` §4.2 og §4.4. **Testene går gjennom den ekte
middlewaren** med testklienten, ikke rett på hjelperne: en test som kalte
`velg_portal()` selv ville stått grønn den dagen middlewaren sluttet å kalle den.

Det som avgjør om noen ser eller skriver i feil portal:

- En konto med to portaler og intet valg kommer **ikke** inn — verken på sider
  eller API.
- Modulradene gjelder **bare** portalen kontoen står i.
- En fane som står i en annen portal enn sesjonen får **409**, ikke en skriving.
"""
from __future__ import annotations

import json

from django.test import Client, TestCase, override_settings

from accounts.forms import ModulTilgangForm
from accounts.models import CustomUser, ModulTilgang, Portaltilgang
from accounts.test_helpers import gi_modultilgang, medlemskap
from core.auth_decorators import har_tilgang, tom_tilgangscache
from core.models import Vaktportal
from core.portal import SESJON_NOKKEL, aktiver_portal, brukerens_portal, eneste_portal
from patients.js_test_utils import (
    PORTAL_UTILS_JS, build_harness, node_available, run_node,
)


def _bruker(navn, role='bruker'):
    return CustomUser.objects.create_user(
        username=navn, password='TestPassord123!', role=role, must_change_password=False)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortalBasis(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')

    def _klient(self, bruker):
        c = Client()
        c.force_login(bruker)
        return c


class PortalregelenTests(PortalBasis):

    def test_en_mulig_portal_velges_av_seg_selv(self):
        """Én portal å stå i: inn uten velger, og valget skrives i sesjonen —
        selv om installasjonen har to portaler."""
        b = _bruker('kari')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='skriv_full', portal=self.brann)
        c = self._klient(b)
        self.assertEqual(c.get('/oppdrag/').status_code, 200)
        self.assertEqual(c.session[SESJON_NOKKEL], self.brann.pk)

    def test_to_portaler_uten_valg_stopper_siden(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        svar = self._klient(b).get('/oppdrag/')
        self.assertEqual(svar.status_code, 302)
        self.assertTrue(svar['Location'].startswith('/portal/?neste='))

    def test_to_portaler_uten_valg_stopper_api(self):
        """Lesing stoppes like mye som skriving — ellers finnes ikke noe riktig svar."""
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        svar = self._klient(b).get('/oppdrag/api/oppdrag/')
        self.assertEqual(svar.status_code, 409)
        self.assertTrue(svar.json()['velg_portal'])
        # Begge nøklene: KO og oppdrag leser `message`, pasientsiden `error`.
        self.assertEqual(svar.json()['message'], svar.json()['error'])

    def test_valget_gjelder_og_kan_byttes(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        medlemskap(b, self.standard)   # med i Standard, men uten oppdrag der
        c = self._klient(b)
        svar = c.post('/portal/', {'portal': 'brann', 'neste': '/oppdrag/'})
        self.assertEqual(svar.status_code, 302)
        self.assertEqual(svar['Location'], '/oppdrag/')
        self.assertEqual(c.get('/oppdrag/').status_code, 200)
        c.post('/portal/', {'portal': 'standard'})
        self.assertEqual(c.get('/oppdrag/').status_code, 403,
                         'radene i Brann skal ikke gjelde i Standard')

    def test_en_portal_man_ikke_er_med_i_kan_ikke_velges(self):
        b = _bruker('ola')
        medlemskap(b, self.standard)
        svar = self._klient(b).post('/portal/', {'portal': 'brann'})
        self.assertEqual(svar.status_code, 400)

    def test_en_deaktivert_portal_kan_ikke_velges(self):
        b = _bruker('ola')
        medlemskap(b, self.standard)
        medlemskap(b, self.brann)
        Vaktportal.objects.filter(pk=self.brann.pk).update(er_aktiv=False)
        svar = self._klient(b).post('/portal/', {'portal': 'brann'})
        self.assertEqual(svar.status_code, 400)

    def test_valget_kontrolleres_ved_hver_forespoersel(self):
        """Fjernet fra portalen midt i sesjonen: valget gjelder ikke lenger."""
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        c = self._klient(b)
        c.post('/portal/', {'portal': 'brann'})
        self.assertEqual(c.get('/oppdrag/').status_code, 200)
        Portaltilgang.objects.filter(bruker=b, portal=self.brann).delete()
        # Én mulig igjen: den velges, og Brann-radene er borte med medlemskapet.
        self.assertEqual(c.get('/oppdrag/').status_code, 200)
        self.assertEqual(c.session[SESJON_NOKKEL], self.standard.pk)

    def test_foreldreloes_konto_faar_en_side_som_sier_det(self):
        b = _bruker('ingen')
        svar = self._klient(b).get('/oppdrag/')
        self.assertEqual(svar.status_code, 403)
        self.assertContains(svar, 'ikke med i noen portal', status_code=403)
        api = self._klient(b).get('/oppdrag/api/oppdrag/')
        self.assertEqual(api.status_code, 403)
        self.assertIn('ikke med i noen portal', api.json()['message'])

    def test_stier_utenfor_portalen_virker_uten_valg(self):
        b = _bruker('ola')
        medlemskap(b, self.standard)
        medlemskap(b, self.brann)
        c = self._klient(b)
        self.assertEqual(c.get('/min-profil/').status_code, 200)
        self.assertEqual(c.get('/portal/').status_code, 200)

    def test_global_admin_med_to_portaler_maa_velge(self):
        admin = _bruker('sjef', role='admin')
        svar = self._klient(admin).get('/oppdrag/')
        self.assertEqual(svar.status_code, 302)

    def test_global_admin_med_en_portal_gaar_rett_inn(self):
        Vaktportal.objects.filter(pk=self.brann.pk).update(er_aktiv=False)
        admin = _bruker('sjef', role='admin')
        self.assertEqual(self._klient(admin).get('/oppdrag/').status_code, 200)

    def test_neste_peker_ikke_ut_av_portalen(self):
        b = _bruker('ola')
        medlemskap(b, self.brann)
        svar = self._klient(b).post('/portal/', {'portal': 'brann',
                                                 'neste': 'https://ond.example/'})
        self.assertEqual(svar['Location'], '/')


class KontekstenTests(PortalBasis):
    """Portalen forespørselen står i, er den aktiv vakt slås opp i."""

    def test_pasienten_havner_i_portalens_vakt(self):
        from patients.models import Patient
        from core.vakt import hent_aktiv_vakt
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='patients', nivaa='skriv_full', portal=self.brann)
        svar = self._klient(b).post('/pasienter/api/patients/', content_type='application/json',
                                    data={'problemstilling': 'Pustevansker'})
        self.assertEqual(svar.status_code, 201)
        self.assertEqual(Patient.objects.get().vakt, hent_aktiv_vakt(self.brann))
        self.assertEqual(Patient.objects.get().vakt.portal, self.brann)


class FanevaktenTests(PortalBasis):

    def setUp(self):
        super().setUp()
        self.b = _bruker('ola')
        gi_modultilgang(bruker=self.b, modul_slug='patients', nivaa='skriv_full',
                        portal=self.brann)
        gi_modultilgang(bruker=self.b, modul_slug='patients', nivaa='skriv_full',
                        portal=self.standard)
        self.c = self._klient(self.b)
        self.c.post('/portal/', {'portal': 'brann'})

    def _ny_pasient(self, **headers):
        return self.c.post('/pasienter/api/patients/', content_type='application/json',
                           data={'problemstilling': 'Pustevansker'}, headers=headers)

    def test_feil_portal_i_hodet_gir_409(self):
        from patients.models import Patient
        svar = self._ny_pasient(**{'X-Portal': 'standard'})
        self.assertEqual(svar.status_code, 409)
        self.assertTrue(svar.json()['portal_byttet'])
        self.assertIn('Last siden på nytt', svar.json()['message'])
        self.assertFalse(Patient.objects.exists())

    def test_riktig_portal_i_hodet_skriver(self):
        self.assertEqual(self._ny_pasient(**{'X-Portal': 'brann'}).status_code, 201)

    def test_skriving_uten_portal_avvises_naar_kontoen_har_flere(self):
        self.assertEqual(self._ny_pasient().status_code, 409)

    def test_lesing_med_feil_portal_gir_409(self):
        svar = self.c.get('/pasienter/api/patients/', headers={'X-Portal': 'standard'})
        self.assertEqual(svar.status_code, 409)

    def test_skjemafeltet_teller_som_hodet(self):
        """Begge veier: feil portal i skjemaet stopper, riktig slipper gjennom.

        Bare den første ble prøvd først — og den ga 409 også når feltet ikke ble
        lest, fordi en skriving uten portal avvises uansett (mutant 5)."""
        admin = _bruker('sjef', role='admin')
        c = self._klient(admin)
        c.post('/portal/', {'portal': 'brann'})
        feil = c.post('/portal-admin/vakt/navn/', {'navn': 'Kamp 7', '_portal': 'standard'})
        self.assertEqual(feil.status_code, 409)
        riktig = c.post('/portal-admin/vakt/navn/', {'navn': 'Kamp 7', '_portal': 'brann'})
        self.assertEqual(riktig.status_code, 302)
        from core.vakt import hent_aktiv_vakt
        self.assertEqual(hent_aktiv_vakt(self.brann).navn, 'Kamp 7')

    def test_en_portal_trenger_ikke_hodet(self):
        """Med én portal finnes ingen annen fane å bytte i — eksisterende flyt står."""
        b = _bruker('kari')
        gi_modultilgang(bruker=b, modul_slug='patients', nivaa='skriv_full', portal=self.brann)
        svar = self._klient(b).post('/pasienter/api/patients/', content_type='application/json',
                                    data={'problemstilling': 'Pustevansker'})
        self.assertEqual(svar.status_code, 201)


class ModulraderPerPortalTests(PortalBasis):

    def test_radene_gjelder_bare_portalen_man_staar_i(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='skriv_full', portal=self.brann)
        medlemskap(b, self.standard)
        setattr(b, '_aktiv_portal', self.standard)
        self.assertFalse(har_tilgang(b, 'oppdrag', 'les'))
        tom_tilgangscache(b)
        setattr(b, '_aktiv_portal', self.brann)
        self.assertTrue(har_tilgang(b, 'oppdrag', 'skriv_full'))

    def test_uten_portal_er_svaret_ingen_tilgang(self):
        """Aldri «Standard», og aldri summen av portalene."""
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        self.assertIsNone(brukerens_portal(b))
        self.assertFalse(har_tilgang(b, 'oppdrag', 'les'))

    def test_brukerens_portal_er_brukerens_ikke_installasjonens(self):
        b = _bruker('kari')
        medlemskap(b, self.brann)
        self.assertEqual(brukerens_portal(b), self.brann)

    def test_modulraden_krever_medlemskap(self):
        b = _bruker('ola')
        with self.assertRaises(ValueError):
            ModulTilgang.objects.create(bruker=b, modul_slug='oppdrag', nivaa='les')

    def test_modulraden_kan_ikke_si_en_annen_bruker(self):
        a, b = _bruker('a'), _bruker('b')
        with self.assertRaises(ValueError):
            ModulTilgang.objects.create(bruker=a, portaltilgang=medlemskap(b, self.brann),
                                        modul_slug='oppdrag', nivaa='les')

    def test_fjernet_fra_portalen_tar_radene_med(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        Portaltilgang.objects.filter(bruker=b, portal=self.brann).delete()
        self.assertFalse(ModulTilgang.objects.filter(bruker=b).exists())

    def test_samme_modul_i_to_portaler(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='skriv_full', portal=self.standard)
        self.assertEqual(ModulTilgang.objects.filter(bruker=b).count(), 2)


class MatrisenPerPortalTests(PortalBasis):

    def test_matrisen_skriver_i_portalen_og_lar_den_andre_staa(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        with aktiver_portal(self.brann):
            skjema = ModulTilgangForm({'modul_oppdrag': 'skriv_full'}, bruker=b)
            self.assertTrue(skjema.is_valid(), skjema.errors)
            skjema.save(b)
        rader = {(r.portaltilgang.portal.slug, r.nivaa)
                 for r in ModulTilgang.objects.filter(bruker=b, modul_slug='oppdrag')}
        self.assertEqual(rader, {('standard', 'les'), ('brann', 'skriv_full')})

    def test_ingen_tilgang_i_en_portal_lar_den_andre_staa(self):
        """Matrisen leser og sletter bare i sin egen portal (mutant 15 og 16).

        Leste den alle portalene, ville «Ingen tilgang» i Brann meldt en endring
        fra Standards «les» — en auditrad om noe som ikke skjedde. Slettet den i
        alle, ville raden i Standard forsvunnet."""
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        medlemskap(b, self.brann)
        with aktiver_portal(self.brann):
            skjema = ModulTilgangForm({'modul_oppdrag': ''}, bruker=b)
            self.assertTrue(skjema.is_valid(), skjema.errors)
            self.assertEqual(skjema.save(b), [])
        self.assertTrue(ModulTilgang.objects.filter(
            bruker=b, modul_slug='oppdrag', portaltilgang__portal=self.standard).exists())

    def test_ingen_tilgang_sletter_i_portalen(self):
        b = _bruker('ola')
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=b, modul_slug='oppdrag', nivaa='les', portal=self.standard)
        with aktiver_portal(self.brann):
            skjema = ModulTilgangForm({'modul_oppdrag': ''}, bruker=b)
            self.assertTrue(skjema.is_valid())
            self.assertEqual(skjema.save(b), [('oppdrag', 'les', '')])
        self.assertEqual(
            list(ModulTilgang.objects.filter(bruker=b).values_list(
                'portaltilgang__portal__slug', flat=True)), ['standard'])

    def test_en_ny_konto_uten_moduler_staar_i_portalen(self):
        b = _bruker('ny')
        with aktiver_portal(self.brann):
            skjema = ModulTilgangForm({}, bruker=b)
            self.assertTrue(skjema.is_valid())
            skjema.save(b)
        self.assertTrue(Portaltilgang.objects.filter(bruker=b, portal=self.brann).exists())


class KoSidebarenTests(PortalBasis):
    """«Hvem har KO oppe» gjelder portalen sidebaren vises i (mutant 20)."""

    def test_ko_i_en_annen_portal_teller_ikke(self):
        from ko.tilstede import _har_ko_tilgang_ider
        her = _bruker('her')
        der = _bruker('der')
        gi_modultilgang(bruker=her, modul_slug='ko', nivaa='les', portal=self.brann)
        gi_modultilgang(bruker=der, modul_slug='ko', nivaa='les', portal=self.standard)
        with aktiver_portal(self.brann):
            self.assertEqual(_har_ko_tilgang_ider([her.pk, der.pk]), {her.pk})


class KlientenTests(TestCase):
    """`portal-utils.js`: nøkkelen og skjemafeltet."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def _kjor(self, kode, portal):
        harness = build_harness([(PORTAL_UTILS_JS, ('sidensPortal', 'brukerNokkel',
                                                    'leggPortalPaaSkjema'))])
        forspill = f"""
            const felt = [];
            globalThis.document = {{
              querySelector: (s) => s === 'meta[name="portal"]'
                ? {{ getAttribute: () => {json.dumps(portal)} }} : null,
              createElement: () => ({{}}),
            }};
            globalThis.PORTAL_BRUKER_ID = 7;
        """
        # `run_node` skriver «OK» til slutt; svaret er første linje.
        return run_node(harness, kode, preamble=forspill).strip().splitlines()[0]

    def test_standard_beholder_den_gamle_noekkelen(self):
        """Køer skrevet før portalene fantes hører til Standard, og skal sendes."""
        self.assertEqual(self._kjor("console.log(brukerNokkel('vl'))", 'standard'), 'vl:u7')

    def test_en_annen_portal_faar_egen_noekkel(self):
        self.assertEqual(self._kjor("console.log(brukerNokkel('vl'))", 'brann'), 'vl:u7:pbrann')

    def test_skjemaet_faar_portalen(self):
        ut = self._kjor("""
            const lagt = [];
            const skjema = { method: 'post', querySelector: () => null,
                             appendChild: (e) => lagt.push(e) };
            leggPortalPaaSkjema(skjema);
            console.log(JSON.stringify(lagt.map(e => [e.name, e.value])));
        """, 'brann')
        self.assertEqual(json.loads(ut), [['_portal', 'brann']])

    def test_apifetch_sender_portalen(self):
        """Fanevakten virker bare hvis klienten faktisk sender hodet (mutant 22)."""
        harness = build_harness([(PORTAL_UTILS_JS, (
            'sidensPortal', 'sekunderSidenInteraksjon', 'getCsrfToken', 'apiFetch'))])
        forspill = """
            globalThis.document = {
              querySelector: (s) => s === 'meta[name="portal"]'
                ? { getAttribute: () => 'brann' } : null,
              getElementById: () => null,
              cookie: '',
            };
            let sisteInteraksjon = Date.now();   // toppnivå-tilstand i fila, ikke en funksjon
            let sendt = null;
            globalThis.fetch = async (url, opts) => { sendt = opts.headers; return {}; };
        """
        ut = run_node(harness, """
            (async () => {
              await apiFetch('/x/', { method: 'POST', body: '{}' });
              console.log(sendt['X-Portal']);
            })();
        """, preamble=forspill).strip().splitlines()
        # Den asynkrone utskriften kommer etter harnessens «OK».
        self.assertEqual([linje for linje in ut if linje != 'OK'], ['brann'])

    def test_get_skjema_faar_ikke_feltet(self):
        ut = self._kjor("""
            const lagt = [];
            leggPortalPaaSkjema({ method: 'get', querySelector: () => null,
                                  appendChild: (e) => lagt.push(e) });
            console.log(lagt.length);
        """, 'brann')
        self.assertEqual(ut, '0')
