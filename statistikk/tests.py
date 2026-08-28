"""Tester for statistikk-modulen.

Modulen ble skilt ut fra pasientmodulen august 2026. Testene her dekker det
utskillingen faktisk endret: hvor endepunktene ligger, hvem som slipper inn,
og at ingen fikk mer tilgang enn før flyttingen.
"""
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from core.modules import Module, get_module, get_visible_modules


ALLE_ROLLER = ('read_only', 'read_write', 'lead_view', 'lead', 'admin')

# Rollene som så statistikkfanen før utskillingen. Lista er med vilje skrevet
# ut i stedet for utledet: den er fasiten flyttingen skal måles mot, og en
# utledet liste ville fulgt med på et utilsiktet skift.
STATS_ROLLER = ('lead_view', 'lead', 'admin')
UTEN_STATS = ('read_only', 'read_write')


def _bruker(rolle):
    return CustomUser.objects.create_user(
        username=f'bruker_{rolle}', password='testpass123',
        role=rolle, must_change_password=False,
    )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class StatistikkTilgangTests(TestCase):
    """Samme roller slipper inn etter flyttingen som før den.

    Dette er hele akseptansekriteriet for utskillingen: den skulle flytte
    kode, ikke åpne eller lukke noe. Testene sammenligner derfor mot
    STATS_ROLLER, som er rollene `stats_required` slapp inn i pasientmodulen.
    """

    def _hent(self, rolle, sti):
        c = Client()
        c.force_login(_bruker(rolle))
        return c.get(sti)

    def test_siden_krever_statistikktilgang(self):
        for rolle in UTEN_STATS:
            with self.subTest(rolle=rolle):
                self.assertEqual(self._hent(rolle, '/statistikk/').status_code, 403)

    def test_siden_er_apen_for_stats_roller(self):
        for rolle in STATS_ROLLER:
            with self.subTest(rolle=rolle):
                self.assertEqual(self._hent(rolle, '/statistikk/').status_code, 200)

    def test_full_stats_krever_statistikktilgang(self):
        for rolle in UTEN_STATS:
            with self.subTest(rolle=rolle):
                resp = self._hent(rolle, '/statistikk/api/full-stats/')
                self.assertEqual(resp.status_code, 403)

    def test_full_stats_er_apen_for_stats_roller(self):
        for rolle in STATS_ROLLER:
            with self.subTest(rolle=rolle):
                resp = self._hent(rolle, '/statistikk/api/full-stats/')
                self.assertEqual(resp.status_code, 200)

    def test_uautentisert_far_redirect_ikke_403(self):
        """En utlogget bruker skal til innlogging, ikke møte en vegg."""
        resp = Client().get('/statistikk/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FlyttedeEndepunkterTests(TestCase):
    """De gamle stiene videresender.

    Uten videresendingen slutter statistikken å oppdatere seg for alle som
    har pasientsiden åpen når deployen treffer — og den feiler stille:
    `loadStats()` logger en advarsel og lar forrige visning bli stående, så
    brukeren ser gamle tall uten å få vite det.
    """

    def setUp(self):
        self.client.force_login(_bruker('admin'))

    def test_gammel_full_stats_url_videresender(self):
        resp = self.client.get('/pasienter/api/full-stats/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/statistikk/api/full-stats/')

    def test_gammel_arkiv_full_stats_url_videresender(self):
        resp = self.client.get('/pasienter/api/innstillinger/arkiv/7/full-stats/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/statistikk/api/arkiv/7/full-stats/')

    def test_videresendingen_er_midlertidig_ikke_permanent(self):
        """302, ikke 301.

        En 301 caches av nettleseren for godt. Stien bør kunne tas i bruk
        igjen uten at gamle klienter sitter fast på videresendingen.
        """
        resp = self.client.get('/pasienter/api/full-stats/')
        self.assertEqual(resp.status_code, 302)

    def test_basic_stats_ble_ikke_flyttet(self):
        """`/pasienter/api/stats/` står igjen, og er fortsatt åpen for alle.

        Testen låser dagens tilstand, ikke en anbefaling. Endepunktet har
        ingen kjent konsument — header-chipsene regnes ut i nettleseren fra
        pasientlista, ikke herfra — og om det skal gates på pasientmodulen
        eller slettes, avgjøres i rollemodell-arbeidet. Da skal denne testen
        endres bevisst, ikke oppdages.
        """
        c = Client()
        c.force_login(_bruker('read_only'))
        self.assertEqual(c.get('/pasienter/api/stats/').status_code, 200)


class StatistikkModulRegistreringTests(TestCase):
    """Modulen er registrert, og synligheten følger rollen."""

    def test_modulen_finnes_i_registeret(self):
        modul = get_module('statistikk')
        self.assertIsNotNone(modul, 'statistikk mangler i core.modules')
        self.assertEqual(modul.url, '/statistikk/')

    def test_synlig_for_stats_roller(self):
        for rolle in STATS_ROLLER:
            with self.subTest(rolle=rolle):
                slugs = [m.slug for m in get_visible_modules(_bruker(rolle))]
                self.assertIn('statistikk', slugs)

    def test_usynlig_for_lavere_roller(self):
        for rolle in UTEN_STATS:
            with self.subTest(rolle=rolle):
                slugs = [m.slug for m in get_visible_modules(_bruker(rolle))]
                self.assertNotIn('statistikk', slugs)


class MinRolleTests(TestCase):
    """`Module.min_rolle` — midlertidig felt, men det må virke mens det finnes.

    Feltet erstattes av ModulTilgang. Fram til da er det den eneste gaten på
    modulsynligheten for statistikk, så oppførselen låses her.
    """

    def _modul(self, **kwargs):
        grunn = dict(slug='t', name='T', description='', url='/t/', icon='x')
        return Module(**{**grunn, **kwargs})

    def test_uten_min_rolle_ser_alle_innloggede_modulen(self):
        modul = self._modul()
        self.assertTrue(modul.is_visible_for(_bruker('read_only')))

    def test_min_rolle_stenger_lavere_roller(self):
        modul = self._modul(min_rolle='lead_view')
        self.assertFalse(modul.is_visible_for(_bruker('read_write')))
        self.assertTrue(modul.is_visible_for(_bruker('lead_view')))

    def test_admin_ser_modulen_uansett(self):
        """Admin har bypass før både flagg og rollekrav sjekkes."""
        modul = self._modul(min_rolle='lead')
        self.assertTrue(modul.is_visible_for(_bruker('admin')))

    def test_min_rolle_og_permission_flag_kombineres_med_and(self):
        """Begge må være oppfylt — ikke én av dem.

        Kombineres de med OR, ville et rollekrav åpnet en modul som
        flagget stenger, og omvendt. Ingen modul bruker begge i dag; testen
        låser semantikken før noen gjør det.
        """
        modul = self._modul(min_rolle='lead_view',
                            permission_flag='kan_redigere_pasienter')
        lead_view = _bruker('lead_view')
        self.assertFalse(modul.is_visible_for(lead_view),
                         'rollen holder, men flagget er False')

        lead_view.kan_redigere_pasienter = True
        lead_view.save(update_fields=['kan_redigere_pasienter'])
        self.assertTrue(modul.is_visible_for(lead_view))

    def test_anonym_bruker_ser_ingenting(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self._modul(min_rolle='read_only')
                         .is_visible_for(AnonymousUser()))
