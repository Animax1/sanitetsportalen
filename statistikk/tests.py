"""Tester for statistikk-modulen.

Modulen ble skilt ut fra pasientmodulen august 2026. Testene her dekker det
utskillingen faktisk endret: hvor endepunktene ligger, hvem som slipper inn,
og at ingen fikk mer tilgang enn før flyttingen.
"""
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from core.auth_decorators import har_tilgang, nivaa_for
from core.models import ModuleSettings
from core.modules import get_module, get_visible_modules


ALLE_ROLLER = ('read_only', 'read_write', 'lead_view', 'lead', 'admin')

# Rollene som så statistikkfanen før utskillingen. Lista er med vilje skrevet
# ut i stedet for utledet: den er fasiten flyttingen skal måles mot, og en
# utledet liste ville fulgt med på et utilsiktet skift.
STATS_ROLLER = ('lead_view', 'lead', 'admin')
UTEN_STATS = ('read_only', 'read_write')


# Kartleggingen datamigrasjonen bruker (§8.1). Gjentatt her fordi testene må
# lage brukere som ligner på dem migrasjonen produserte — nye brukere får
# ingen rader av seg selv.
BACKFILL = {
    'read_only':  [('patients', 'les')],
    'read_write': [('patients', 'skriv_full')],
    'lead_view':  [('patients', 'les'),        ('statistikk', 'les')],
    'lead':       [('patients', 'skriv_full'), ('statistikk', 'les')],
    'admin':      [],
}


def _bruker(rolle, *, tilganger=None):
    """Bruker med rollen, og med radene backfillen ville gitt den.

    `tilganger` overstyrer for tester som trenger en annen kombinasjon enn
    den dagens roller kartlegges til.
    """
    bruker = CustomUser.objects.create_user(
        username=f'bruker_{rolle}', password='testpass123',
        role=rolle, must_change_password=False,
    )
    for slug, nivaa in (BACKFILL[rolle] if tilganger is None else tilganger):
        ModulTilgang.objects.create(bruker=bruker, modul_slug=slug, nivaa=nivaa)
    return bruker


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


class ModulTilgangSynlighetTests(TestCase):
    """Synlighet leser `ModulTilgang` — samme kilde som håndhevelsen.

    Erstatter `MinRolleTests`. Det midlertidige `Module.min_rolle`-feltet er
    borte; modulen gates av en rad, som alle andre.
    """

    def test_ingen_rad_er_ingen_tilgang(self):
        uten = _bruker('read_only', tilganger=[])
        self.assertIsNone(nivaa_for(uten, 'statistikk'))
        self.assertNotIn('statistikk', [m.slug for m in get_visible_modules(uten)])

    def test_rad_gir_tilgang(self):
        med = _bruker('read_only', tilganger=[('statistikk', 'les')])
        self.assertTrue(har_tilgang(med, 'statistikk', 'les'))

    def test_admin_ser_modulen_uten_rad(self):
        """Global admin står utenfor modulaksen og trenger ingen rader."""
        admin = _bruker('admin')
        self.assertEqual(ModulTilgang.objects.filter(bruker=admin).count(), 0)
        self.assertIn('statistikk', [m.slug for m in get_visible_modules(admin)])

    def test_deaktivert_modul_stenger_for_alle_andre_enn_admin(self):
        """Toggelen var en menybryter (§2.2). Nå er den en dør.

        `GET /pasienter/` ga 200 med modulen deaktivert. Verdt å vite *før*
        noen prøver å stenge en modul under en hendelse.
        """
        ModuleSettings.objects.update_or_create(
            slug='statistikk', defaults={'enabled': False},
        )
        lead = _bruker('lead')
        self.assertFalse(har_tilgang(lead, 'statistikk', 'les'))

        # Admin slipper fortsatt inn — ellers kan man deaktivere seg selv ut
        # av å kunne reaktivere.
        self.assertTrue(har_tilgang(_bruker('admin'), 'statistikk', 'les'))

    def test_anonym_bruker_har_ingenting(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(har_tilgang(AnonymousUser(), 'statistikk', 'les'))
        self.assertIsNone(nivaa_for(AnonymousUser(), 'statistikk'))
