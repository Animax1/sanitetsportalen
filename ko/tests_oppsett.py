"""KO-verktøylinja (20. okt. 2026): «Lagre oppsettet» på kontoen, KO-innstillinger som meny
med Vaktarkiv, og Pålogget/Oppsett som ikonknapper.

André: «oppsett knappen har ingen måte å lagre oppsett på». Oppsettet sto bare i
`localStorage`, og «Logg ut» tømmer den (`Clear-Site-Data`, H4).
"""
from __future__ import annotations

import json

from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_modultilgang_oppdater
from ko.models import KoOppsett
from patients.js_test_utils import KO_JS, KO_LAYOUT_JS, PORTAL_UTILS_JS, build_harness, run_node

OPPSETT = {'rader': [['logg', 'hendelser'], ['ressurser', 'oppdrag']],
           'bredde': [40, 60], 'hoyde': 50, 'skjult': []}
URL = '/ko/api/oppsett/'


def _bruker(navn, **kw):
    return CustomUser.objects.create_user(username=navn, password='x',
                                          must_change_password=False, **kw)


def _gi(bruker, modul, nivaa):
    gi_modultilgang_oppdater(bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LagreOppsettetTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.kari = _bruker('kari')
        _gi(self.kari, 'ko', 'les')
        self.client.force_login(self.kari)

    def _post(self, data):
        return self.client.post(URL, json.dumps(data), content_type='application/json')

    def test_les_kan_lagre_sitt_eget(self):
        svar = self._post({'oppsett': OPPSETT})
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(KoOppsett.objects.get(bruker=self.kari).oppsett, OPPSETT)

    def test_lagre_igjen_overskriver_en_rad(self):
        self._post({'oppsett': OPPSETT})
        self._post({'oppsett': OPPSETT | {'hoyde': 70}})
        self.assertEqual(KoOppsett.objects.filter(bruker=self.kari).count(), 1)
        self.assertEqual(KoOppsett.objects.get(bruker=self.kari).oppsett['hoyde'], 70)

    def test_kroppen_kan_ikke_velge_en_annen_konto(self):
        per = _bruker('per')
        self._post({'oppsett': OPPSETT, 'bruker': per.pk})
        self.assertFalse(KoOppsett.objects.filter(bruker=per).exists())
        self.assertTrue(KoOppsett.objects.filter(bruker=self.kari).exists())

    def test_feil_form_avvises(self):
        for feil in (None, [], 'x', {'rader': []}, OPPSETT | {'ekstra': 1},
                     {k: v for k, v in OPPSETT.items() if k != 'skjult'}):
            with self.subTest(feil=feil):
                self.assertEqual(self._post({'oppsett': feil}).status_code, 400)
        self.assertFalse(KoOppsett.objects.exists())

    def test_for_stort_avvises(self):
        stort = OPPSETT | {'skjult': ['x' * 50] * 50}
        self.assertEqual(self._post({'oppsett': stort}).status_code, 400)
        self.assertFalse(KoOppsett.objects.exists())

    def test_uten_ko_ingen_lagring(self):
        uten = _bruker('uten')
        self.client.force_login(uten)
        self.assertEqual(self._post({'oppsett': OPPSETT}).status_code, 403)
        self.assertFalse(KoOppsett.objects.exists())

    def test_get_er_ikke_lov(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_siden_baerer_det_lagrede(self):
        self.assertIn('window.KO_LAGRET_OPPSETT = null;', self.client.get('/ko/').content.decode())
        self._post({'oppsett': OPPSETT})
        side = self.client.get('/ko/').content.decode()
        self.assertIn('"rader": [["logg", "hendelser"]', side)
        self.assertIn('Lagret på kontoen din', side)

    def test_siden_viser_bare_eget_oppsett(self):
        per = _bruker('per')
        KoOppsett.objects.create(bruker=per, oppsett=OPPSETT)
        self.assertIn('window.KO_LAGRET_OPPSETT = null;', self.client.get('/ko/').content.decode())


class OppsettetErPerPortalTests(TestCase):
    """Per (portal, konto), som ansvarsmerket: samme person kan ha ett oppsett i Brann og et
    annet i Standard, og det ene skal aldri lekke inn i det andre."""

    def setUp(self):
        from core.models import Vaktportal
        from core.portal import eneste_portal
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.kari = _bruker('kari')

    def test_lagret_i_en_portal_finnes_ikke_i_den_andre(self):
        from core.portal import aktiver_portal
        from ko import services
        with aktiver_portal(self.brann):
            services.lagre_oppsett(self.kari, OPPSETT)
        with aktiver_portal(self.standard):
            self.assertIsNone(services.lagret_oppsett(self.kari))
            services.lagre_oppsett(self.kari, OPPSETT | {'hoyde': 70})
        with aktiver_portal(self.brann):
            self.assertEqual(services.lagret_oppsett(self.kari).oppsett['hoyde'], 50)
        self.assertEqual(KoOppsett.objects.filter(bruker=self.kari).count(), 2)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VerktoylinjaTests(TestCase):
    """KO-innstillinger er en meny, og hvert valg har sin egen gate."""

    def setUp(self):
        self.client = Client()

    def _verktoy(self, bruker):
        self.client.force_login(bruker)
        side = self.client.get('/ko/').content.decode()
        return side[side.index('id="ko-verktoy"'):side.index('id="ko-konsoll"')]

    def test_arkivet_uten_innstillingene(self):
        """Den som har arkivet, men ikke innstillingene, skal ikke miste det i menyen."""
        b = _bruker('fører')
        _gi(b, 'ko', 'skriv_full')
        _gi(b, 'oppdrag', 'skriv_full')
        verktoy = self._verktoy(b)
        self.assertIn('data-bs-target="#arkivModal"', verktoy)
        self.assertNotIn('data-bs-target="#valglisterModal"', verktoy)
        self.assertIn('id="ko-innstillinger-knapp"', verktoy)

    def test_innstillingene_uten_arkivet(self):
        b = _bruker('koleder')
        _gi(b, 'ko', 'skriv_leder')
        verktoy = self._verktoy(b)
        self.assertIn('data-bs-target="#valglisterModal"', verktoy)
        self.assertNotIn('data-bs-target="#arkivModal"', verktoy)

    def test_ingen_av_dem_gir_ingen_meny(self):
        b = _bruker('leser')
        _gi(b, 'ko', 'les')
        self.assertNotIn('id="ko-innstillinger-knapp"', self._verktoy(b))

    def test_arkivet_staar_bare_i_menyen(self):
        b = _bruker('sjef', role='admin')
        verktoy = self._verktoy(b)
        meny = verktoy[verktoy.index('id="ko-innstillinger-knapp"'):]
        meny = meny[:meny.index('</div>\n        </div>')]
        self.assertEqual(verktoy.count('data-bs-target="#arkivModal"'), 1)
        self.assertIn('data-bs-target="#arkivModal"', meny)

    def test_oppsett_og_paalogget_er_ikoner_med_navn(self):
        b = _bruker('ikon')
        _gi(b, 'ko', 'les')
        verktoy = self._verktoy(b)
        for navn, knapp in (('Pålogget', 'ko-sidebar-knapp'), ('Oppsett', 'ko-oppsett-knapp')):
            with self.subTest(navn=navn):
                start = verktoy.index(f'id="{knapp}"')
                tagg = verktoy[start:verktoy.index('</button>', start)]
                self.assertIn(f'aria-label="{navn}"', tagg)
                self.assertNotIn(f'>{navn}', tagg.replace('\n', '').replace(' ', ''))
        self.assertIn('data-action="koLagreOppsettPaaKontoen"', verktoy)


class LesOppsettetJsTests(SimpleTestCase):
    """Rekkefølgen i `koLesOppsett()`: nettleserens kopi, så kontoens, så standarden."""

    def setUp(self):
        from oppdrag.tests_runde_d import _konst
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koGyldigOppsett', 'koStandardOppsett', 'koKlemProsent', 'koGyldigSkjult',
                     'koGyldigePlasser', 'koIRutenettet', 'koLesOppsett',
                     'koLagreOppsettPaaKontoen')),
        ))
        self.pre = ''.join(_konst(KO_LAYOUT_JS, n) for n in (
            'KO_VINDUER', 'KO_PLASSER', 'KO_PAR', 'KO_OPPSETT_STANDARD',
            'KO_VINDUSNAVN', 'KO_MIN_PROSENT', 'KO_OPPSETT_NOKKEL')) + 'let koOppsett = null;\n'

    def _les(self, lokal, konto):
        kode = (
            'const lager = {};\n'
            + (f"lager['ko.oppsett'] = {json.dumps(json.dumps(lokal))};\n" if lokal is not None else '')
            + 'globalThis.localStorage = { getItem: (k) => lager[k] ?? null };\n'
            + f'globalThis.KO_LAGRET_OPPSETT = {json.dumps(konto)};\n'
            + 'console.log(JSON.stringify(koLesOppsett().rader));'
        )
        return json.loads(run_node(self.harness, kode, preamble=self.pre).splitlines()[0])

    def test_tom_nettleser_gir_kontoens(self):
        """Det er hele feilen: etter «Logg ut» er nettleseren tom."""
        self.assertEqual(self._les(None, OPPSETT), OPPSETT['rader'])

    def test_nettleserens_kopi_vinner(self):
        lokal = OPPSETT | {'rader': [['hendelser', 'logg'], ['oppdrag', 'ressurser']]}
        self.assertEqual(self._les(lokal, OPPSETT), lokal['rader'])

    def test_ugyldig_kontokopi_gir_standarden(self):
        self.assertEqual(self._les(None, {'rader': 'tull'}),
                         [['hendelser', 'logg'], ['ressurser', 'oppdrag']])

    def test_lagre_sender_det_som_staar_og_sier_fra(self):
        kode = (
            "globalThis.localStorage = { getItem: () => null };\n"
            "koOppsett = " + json.dumps(OPPSETT) + ";\n"
            "const status = { textContent: '' };\n"
            "globalThis.document = { getElementById: () => status };\n"
            "let sendt = null;\n"
            "globalThis.apiFetch = async (url, o) => { sendt = [url, o.method, JSON.parse(o.body)];"
            " return { ok: true, json: async () => ({}) }; };\n"
            "await koLagreOppsettPaaKontoen();\n"
            "console.log(JSON.stringify([sendt, status.textContent,"
            " globalThis.KO_LAGRET_OPPSETT.hoyde]));"
        )
        sendt, tekst, hoyde = json.loads(run_node(self.harness, kode, preamble=self.pre).splitlines()[0])
        self.assertEqual(sendt, ['/ko/api/oppsett/', 'POST', {'oppsett': OPPSETT}])
        self.assertIn('Lagret', tekst)
        self.assertEqual(hoyde, 50)

    def test_feil_fra_serveren_vises_og_kontokopien_staar(self):
        kode = (
            "globalThis.localStorage = { getItem: () => null };\n"
            "globalThis.KO_LAGRET_OPPSETT = null;\n"
            "const status = { textContent: '' };\n"
            "globalThis.document = { getElementById: () => status };\n"
            "globalThis.apiFetch = async () => ({ ok: false, json: async () => ({ message: 'For stort.' }) });\n"
            "await koLagreOppsettPaaKontoen();\n"
            "console.log(JSON.stringify([status.textContent, globalThis.KO_LAGRET_OPPSETT]));"
        )
        self.assertEqual(json.loads(run_node(self.harness, kode, preamble=self.pre).splitlines()[0]),
                         ['For stort.', None])
