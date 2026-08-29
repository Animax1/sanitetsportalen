"""Tester for statistikk-modulen.

Modulen ble skilt ut fra pasientmodulen august 2026. Testene her dekker det
utskillingen faktisk endret: hvor endepunktene ligger, hvem som slipper inn,
og at ingen fikk mer tilgang enn før flyttingen.
"""
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from accounts.test_helpers import PROFILER
from core.auth_decorators import har_tilgang, nivaa_for
from core.models import ModuleSettings
from core.modules import get_module, get_visible_modules


ALLE_PROFILER = ('leser', 'skriver', 'leder_les', 'leder', 'admin')

#: Stien til pasienttallene etter fase 6. Kilden står i stien, og hvilke
#: slugs som svarer avgjøres av `core.stats`-registeret.
PASIENTKILDEN = '/statistikk/api/kilde/patients/full-stats/'

# Profilene som så statistikkfanen før utskillingen. Lista er med vilje
# skrevet ut i stedet for utledet: den er fasiten flyttingen skal måles mot,
# og en utledet liste ville fulgt med på et utilsiktet skift.
#
# Navnene var rollenavn fram til deploy 2 — `lead_view`, `read_write` og
# resten. Da `role` krympet til admin/bruker, ble de erstattet av profilene i
# `accounts.test_helpers`, som beskriver tilgang i stedet for tittel. Det er
# de samme kombinasjonene: `leder_les` er «leser pasienter, leser statistikk».
STATS_PROFILER = ('leder_les', 'leder', 'admin')
UTEN_STATS = ('leser', 'skriver')


def _bruker(profil, *, tilganger=None):
    """Bruker med radene profilen beskriver.

    `tilganger` overstyrer for tester som trenger en annen kombinasjon enn
    profilene dekker.
    """
    bruker = CustomUser.objects.create_user(
        username=f'bruker_{profil}', password='testpass123',
        role='admin' if profil == 'admin' else 'bruker',
        must_change_password=False,
    )
    for slug, nivaa in (PROFILER[profil] if tilganger is None else tilganger):
        ModulTilgang.objects.create(bruker=bruker, modul_slug=slug, nivaa=nivaa)
    return bruker


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class StatistikkTilgangTests(TestCase):
    """Samme kontoer slipper inn etter flyttingen som før den.

    Dette er hele akseptansekriteriet for utskillingen: den skulle flytte
    kode, ikke åpne eller lukke noe. Testene sammenligner derfor mot
    STATS_PROFILER, som er kontoene `stats_required` slapp inn i pasientmodulen.
    """

    def _hent(self, profil, sti):
        c = Client()
        c.force_login(_bruker(profil))
        return c.get(sti)

    def test_siden_krever_statistikktilgang(self):
        for profil in UTEN_STATS:
            with self.subTest(profil=profil):
                self.assertEqual(self._hent(profil, '/statistikk/').status_code, 403)

    def test_siden_er_apen_for_stats_profiler(self):
        for profil in STATS_PROFILER:
            with self.subTest(profil=profil):
                self.assertEqual(self._hent(profil, '/statistikk/').status_code, 200)

    def test_full_stats_krever_statistikktilgang(self):
        for profil in UTEN_STATS:
            with self.subTest(profil=profil):
                resp = self._hent(profil, PASIENTKILDEN)
                self.assertEqual(resp.status_code, 403)

    def test_full_stats_er_apen_for_stats_profiler(self):
        for profil in STATS_PROFILER:
            with self.subTest(profil=profil):
                resp = self._hent(profil, PASIENTKILDEN)
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
        self.assertEqual(resp['Location'], PASIENTKILDEN)

    def test_gammel_arkiv_full_stats_url_videresender(self):
        resp = self.client.get('/pasienter/api/innstillinger/arkiv/7/full-stats/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp['Location'],
            '/statistikk/api/kilde/patients/arkiv/7/full-stats/')

    def test_en_kilde_stiene_videresender_ogsaa(self):
        """Fase 6 flyttet stiene en gang til — samme grunn, samme svar.

        En fane som sto åpen da deployen traff har den gamle JS-fila i minnet
        og spør fortsatt etter `/statistikk/api/full-stats/`.
        """
        resp = self.client.get('/statistikk/api/full-stats/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], PASIENTKILDEN)

        resp = self.client.get('/statistikk/api/arkiv/7/full-stats/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp['Location'],
            '/statistikk/api/kilde/patients/arkiv/7/full-stats/')

    def test_videresendingen_er_midlertidig_ikke_permanent(self):
        """302, ikke 301.

        En 301 caches av nettleseren for godt. Stien bør kunne tas i bruk
        igjen uten at gamle klienter sitter fast på videresendingen.
        """
        resp = self.client.get('/pasienter/api/full-stats/')
        self.assertEqual(resp.status_code, 302)

    def test_basic_stats_er_slettet(self):
        """`/pasienter/api/stats/` finnes ikke lenger.

        Testen låste tidligere at endepunktet *sto igjen*, med et notat om at
        den skulle endres bevisst når rollemodell-arbeidet avgjorde om det
        skulle gates eller slettes. Avgjørelsen ble sletting: det var en rest
        fra Flask-porten, header-chipsene regnes ut i nettleseren fra
        pasientlista, og ingen JS-fil i repoet kalte det.

        Den står igjen snudd, ikke slettet — 404 her betyr «bevisst borte», og
        neste som lurer på hvor endepunktet ble av finner svaret i en test i
        stedet for i git-historikken.
        """
        c = Client()
        c.force_login(_bruker('leser'))
        self.assertEqual(c.get('/pasienter/api/stats/').status_code, 404)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KildekomposisjonTests(TestCase):
    """§5: modulen komponerer tilgang, den eier den ikke.

    Med kilde nummer to ble regelen «vis det du har tilgang til», ikke «alt
    eller ingenting». Det siste var det samme så lenge det fantes én kilde,
    men ville tatt statistikken fra alle som leser pasienter uten å ha
    oppdrag, i det øyeblikket oppdragsmodulen meldte seg inn i registeret.
    """

    OPPDRAGSKILDEN = '/statistikk/api/kilde/oppdrag/full-stats/'

    def _med(self, navn, tilganger):
        c = Client()
        c.force_login(_bruker(navn, tilganger=tilganger))
        return c

    def test_uten_oppdragstilgang_ingen_oppdragsfane(self):
        c = self._med('kun_pasient', [('statistikk', 'les'), ('patients', 'les')])
        html = c.get('/statistikk/').content.decode('utf-8')
        self.assertIn('kilde-patients', html)
        self.assertNotIn('kilde-oppdrag', html)

    def test_uten_oppdragstilgang_stenges_oppdragstallene(self):
        """Ellers er statistikk en bakvei rundt modultilgangen."""
        c = self._med('kun_pasient2', [('statistikk', 'les'), ('patients', 'les')])
        self.assertEqual(c.get(self.OPPDRAGSKILDEN).status_code, 403)

    def test_med_oppdragstilgang_kommer_bade_fane_og_tall(self):
        c = self._med('begge', [('statistikk', 'les'), ('patients', 'les'),
                                ('oppdrag', 'les')])
        html = c.get('/statistikk/').content.decode('utf-8')
        self.assertIn('kilde-patients', html)
        self.assertIn('kilde-oppdrag', html)
        self.assertEqual(c.get(self.OPPDRAGSKILDEN).status_code, 200)

    def test_uten_pasienttilgang_faar_man_fortsatt_oppdragstallene(self):
        """Selve endringen: én manglende kilde stenger ikke hele siden."""
        c = self._med('kun_oppdrag', [('statistikk', 'les'), ('oppdrag', 'les')])
        resp = c.get('/statistikk/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('kilde-oppdrag', html)
        self.assertNotIn('kilde-patients', html)
        self.assertEqual(c.get(PASIENTKILDEN).status_code, 403)
        self.assertEqual(c.get(self.OPPDRAGSKILDEN).status_code, 200)

    def test_ingen_kilder_gir_403_paa_siden(self):
        """En statistikkside uten tall er en side som later som den virker."""
        c = self._med('ingen_kilder', [('statistikk', 'les')])
        self.assertEqual(c.get('/statistikk/').status_code, 403)

    def test_ukjent_kilde_gir_403_ikke_500(self):
        c = self._med('ukjent', [('statistikk', 'les'), ('patients', 'les')])
        self.assertEqual(
            c.get('/statistikk/api/kilde/finnesikke/full-stats/').status_code, 403)

    def test_kildene_deler_ikke_cache(self):
        """Slug-en må stå i cache-nøkkelen — ellers server kilde to kilde éns
        tall i 60 sekunder."""
        from django.core.cache import cache
        cache.clear()
        c = self._med('cachetest', [('statistikk', 'les'), ('patients', 'les'),
                                    ('oppdrag', 'les')])
        pasient = c.get(PASIENTKILDEN).json()
        oppdrag = c.get(self.OPPDRAGSKILDEN).json()
        self.assertIn('crosstab_prob_triage', pasient)
        self.assertIn('per_hastegrad', oppdrag)

    def test_fanerad_skjules_ved_en_kilde(self):
        """En fanerad med ett valg er en knapp som ikke gjør noe."""
        c = self._med('en_kilde', [('statistikk', 'les'), ('patients', 'les')])
        self.assertNotIn('id="kilde-nav"',
                         c.get('/statistikk/').content.decode('utf-8'))

    def test_deaktivert_kildemodul_forsvinner_fra_fanene(self):
        """En modul som er slått av skal ikke lyse gjennom statistikken."""
        ModuleSettings.objects.update_or_create(
            slug='oppdrag', defaults={'enabled': False})
        c = self._med('deaktivert', [('statistikk', 'les'), ('patients', 'les'),
                                     ('oppdrag', 'les')])
        html = c.get('/statistikk/').content.decode('utf-8')
        self.assertNotIn('kilde-oppdrag', html)
        self.assertEqual(c.get(self.OPPDRAGSKILDEN).status_code, 403)

    def test_arkivstatistikk_finnes_ikke_for_oppdrag_enda(self):
        """Oppdrag arkiveres i fase 7. Fram til da: 404, ikke et tomt svar."""
        c = Client()
        c.force_login(_bruker('admin'))
        resp = c.get('/statistikk/api/kilde/oppdrag/arkiv/1/full-stats/')
        self.assertEqual(resp.status_code, 404)


class StatistikkModulRegistreringTests(TestCase):
    """Modulen er registrert, og synligheten følger modultilgangen."""

    def test_modulen_finnes_i_registeret(self):
        modul = get_module('statistikk')
        self.assertIsNotNone(modul, 'statistikk mangler i core.modules')
        self.assertEqual(modul.url, '/statistikk/')

    def test_synlig_for_stats_profiler(self):
        for profil in STATS_PROFILER:
            with self.subTest(profil=profil):
                slugs = [m.slug for m in get_visible_modules(_bruker(profil))]
                self.assertIn('statistikk', slugs)

    def test_usynlig_uten_statistikktilgang(self):
        for profil in UTEN_STATS:
            with self.subTest(profil=profil):
                slugs = [m.slug for m in get_visible_modules(_bruker(profil))]
                self.assertNotIn('statistikk', slugs)


class ModulTilgangSynlighetTests(TestCase):
    """Synlighet leser `ModulTilgang` — samme kilde som håndhevelsen.

    Erstatter `MinRolleTests`. Det midlertidige `Module.min_rolle`-feltet er
    borte; modulen gates av en rad, som alle andre.
    """

    def test_ingen_rad_er_ingen_tilgang(self):
        uten = _bruker('leser', tilganger=[])
        self.assertIsNone(nivaa_for(uten, 'statistikk'))
        self.assertNotIn('statistikk', [m.slug for m in get_visible_modules(uten)])

    def test_rad_gir_tilgang(self):
        med = _bruker('leser', tilganger=[('statistikk', 'les')])
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
        lead = _bruker('leder')
        self.assertFalse(har_tilgang(lead, 'statistikk', 'les'))

        # Admin slipper fortsatt inn — ellers kan man deaktivere seg selv ut
        # av å kunne reaktivere.
        self.assertTrue(har_tilgang(_bruker('admin'), 'statistikk', 'les'))

    def test_anonym_bruker_har_ingenting(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(har_tilgang(AnonymousUser(), 'statistikk', 'les'))
        self.assertIsNone(nivaa_for(AnonymousUser(), 'statistikk'))
