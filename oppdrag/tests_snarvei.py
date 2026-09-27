"""`/oppdrag/` i menyen og på dashbordet bare for bilene og admin (27. sep. 2026).

André: «Sentralbordet jobber fra /ko/, så skjul det for dem også, de skal ikke
sperres. skriv_handling er bilene og de skal bare være i /oppdrag.»

**Snarvei, ikke tilgang**: alle som har tilgang kommer fortsatt inn på adressen.
Testene går gjennom den ekte menyen og det ekte dashbordet, ikke bare
`har_snarvei_for`, så et kallsted som slutter å spørre blir rødt.
"""
from django.test import TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from core.models import ModuleSettings


def _bruker(navn, nivaa=None, *, admin=False):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role='admin' if admin else 'bruker',
        must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='oppdrag', nivaa=nivaa)
    return b


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SnarveienTests(TestCase):

    def setUp(self):
        ModuleSettings.ensure_defaults_exist()
        ModuleSettings.objects.filter(slug='oppdrag').update(enabled=True)

    def _ser(self, bruker):
        """(i menyen, på dashbordet, på Min profil, kommer inn på adressen)"""
        self.client.force_login(bruker)
        forside = self.client.get('/').content.decode()
        profil = self.client.get('/min-profil/').content.decode()
        return ('href="/oppdrag/"' in forside and 'nav' in forside,
                'aria-label="Åpne Oppdrag"' in forside,
                'href="/oppdrag/"' in profil,
                self.client.get('/oppdrag/').status_code == 200)

    def test_bilen_har_snarveien(self):
        self.assertEqual(self._ser(_bruker('bil', 'skriv_handling')), (True, True, True, True))

    def test_admin_har_snarveien(self):
        self.assertEqual(self._ser(_bruker('sjef', admin=True)), (True, True, True, True))

    def test_sentralbordet_har_den_ikke_men_kommer_inn(self):
        for nivaa in ('skriv_full', 'skriv_leder', 'les'):
            with self.subTest(nivaa=nivaa):
                self.assertEqual(self._ser(_bruker(f'sentral_{nivaa}', nivaa)),
                                 (False, False, False, True))

    def test_uten_tilgang_er_det_som_foer(self):
        self.client.force_login(_bruker('utenfor'))
        self.assertNotIn('href="/oppdrag/"', self.client.get('/').content.decode())
        self.assertEqual(self.client.get('/oppdrag/').status_code, 403)

    def test_andre_moduler_er_uberort(self):
        """Tomt felt betyr alle med tilgang — som før."""
        from core.modules import get_module
        self.assertEqual(get_module('ko').snarvei_for_nivaaer, ())
        b = _bruker('koleser')
        ModulTilgang.objects.create(bruker=b, modul_slug='ko', nivaa='les')
        self.assertTrue(get_module('ko').har_snarvei_for(b))
