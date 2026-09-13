"""Prodtestfunnene 13. sep. 2026, vaktlista (punkt 4.1).

Korps-føreren hvis egen mannskapsrad ble koblet fra så «Mannskapsregisteret
er tomt» og kunne ikke redigere noen. To ting, hver med sin test:

- Sida sa feil: meldingen leste lista over dem hun får *sette* (tom uten
  badge), ikke registeret hun *ser* (alle korps). Og ingen sa hvorfor hun
  ikke fikk redigere — varselet om manglende badge fantes bare for `les`.
- Og koblingen på e-post var `skriv_full`+ (M5). André: «Fiks alt inkludert
  kobling» — bare leder og global admin flytter en badge.
"""
import json

from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from patients.js_test_utils import VAKTLISTE_JS, build_harness, node_available, run_node
from vaktliste.models import Korps, Mannskap
from vaktliste.tests_tilgang import _bruker, _klient


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KorpsforerUtenBadgeTests(TestCase):
    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        Mannskap.objects.create(navn='Ola', korps=self.korps)

    def test_sida_sier_hvorfor_hun_ikke_faar_redigere(self):
        res = _klient(_bruker('kf_uten', 'skriv_handling')).get('/vaktliste/')
        self.assertContains(res, 'id="vl-korpsfilter"')
        self.assertContains(res, 'ikke knyttet')
        self.assertContains(res, 'Du ser alle korps')

    def test_med_badge_ingen_merknad(self):
        kf = _bruker('kf_med', 'skriv_handling')
        Mannskap.objects.create(navn='Fører', korps=self.korps, user=kf)
        self.assertNotContains(_klient(kf).get('/vaktliste/'), 'vl-korpsfilter')

    def test_de_som_staar_utenfor_badgen_faar_ingen_merknad(self):
        for navn, nivaa, admin in (('vl', 'skriv_full', False), ('led', 'skriv_leder', False),
                                   ('adm', None, True), ('sam', 'les_alle', False)):
            with self.subTest(konto=navn):
                res = _klient(_bruker(navn, nivaa, admin=admin)).get('/vaktliste/')
                self.assertNotContains(res, 'Du ser alle korps')

    def test_registeret_hun_ser_er_ikke_tomt(self):
        """Registeret (`synlig_mannskap`) har alle korps for `skriv_handling`,
        også uten badge — det er lista hun får sette som er tom."""
        res = _klient(_bruker('kf_reg', 'skriv_handling')).get('/vaktliste/api/mannskap/')
        self.assertEqual([m['navn'] for m in res.json()['data']['mannskap']], ['Ola'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KoblingBareForLederTests(TestCase):
    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.kari = CustomUser.objects.create_user(
            username='kari', password='x', email='kari@example.org', must_change_password=False)

    def _opprett(self, klient):
        return klient.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Kari', 'korps_id': self.korps.pk, 'epost': 'kari@example.org'})

    def test_skriv_full_lagrer_eposten_uten_aa_koble(self):
        d = self._opprett(_klient(_bruker('vl', 'skriv_full'))).json()['data']
        self.assertEqual(d['epost'], 'kari@example.org')
        self.assertIsNone(d['user_id'])
        self.assertTrue(d['konto_finnes'], 'merket sier at kontoen finnes — lederen kobler')

    def test_leder_og_admin_kobler(self):
        for navn, nivaa, admin in (('led', 'skriv_leder', False), ('adm', None, True)):
            with self.subTest(konto=navn):
                Mannskap.objects.all().delete()
                d = self._opprett(_klient(_bruker(navn, nivaa, admin=admin))).json()['data']
                self.assertEqual(d['user_id'], self.kari.pk)

    def test_redigering_med_skriv_full_kobler_heller_ikke(self):
        person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        res = _klient(_bruker('vl2', 'skriv_full')).put(
            f'/vaktliste/api/mannskap/{person.pk}/', content_type='application/json',
            data={'epost': 'kari@example.org'})
        self.assertEqual(res.status_code, 200, res.content)
        person.refresh_from_db()
        self.assertIsNone(person.user_id)


class RegisteretErTomtJsTests(SimpleTestCase):
    """Meldingen leser registeret, og ingenting før det er hentet."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(((VAKTLISTE_JS, ('registeretErTomt',)),))

    def test_regelen(self):
        ut = run_node(self.harness, '''
            console.log(JSON.stringify([
              registeretErTomt(null),
              registeretErTomt({}),
              registeretErTomt({ mannskap: [] }),
              registeretErTomt({ mannskap: [{ navn: 'Ola' }] }),
              // Korpsfilteret tømmer `mannskap`, men `alle_mannskap` står.
              registeretErTomt({ mannskap: [], alle_mannskap: [{ navn: 'Ola' }] }),
            ]));
        ''')
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [False, False, True, False, False])
