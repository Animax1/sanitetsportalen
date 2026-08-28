"""Grensesnittet må gate på det samme som endepunktene gjør (§7.4).

Meldt fra staging: en konto med `skriv_full` ble satt ned til `les`, og
«Ny pasient» ble stående. Brukeren fikk opp registreringsskjemaet, fylte det
ut, og møtte 403 på lagre. Serveren var riktig hele tiden — `applyRoleVisibility`
gatet på `window.USER_ROLE`, altså rollen, som ikke lenger sier noe om hva du
får gjøre i modulen.

En knapp som fører til en vegg er verre enn ingen knapp: brukeren rekker å
gjøre arbeidet før hen får vite at det ikke gikk.
"""
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang


def _bruker(navn, nivaa):
    bruker = CustomUser.objects.create_user(
        username=navn, password='x', role='bruker', must_change_password=False,
    )
    if nivaa:
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa=nivaa)
    return bruker


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ModulTilgangIMalenTests(TestCase):
    """Malen må sende nivået, ikke rollen."""

    def _hent(self, navn, nivaa):
        c = Client()
        c.force_login(_bruker(navn, nivaa))
        resp = c.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode('utf-8')

    def test_nivaaet_sendes_til_klienten(self):
        self.assertIn('patients: "les"', self._hent('m_les', 'les'))
        self.assertIn('patients: "skriv_full"', self._hent('m_skriv', 'skriv_full'))

    def test_rollen_sendes_ikke_lenger(self):
        """`window.USER_ROLE` var kilden som gatet feil. Den skal være borte."""
        self.assertNotIn('USER_ROLE', self._hent('m_rolle', 'les'))

    def test_global_admin_merkes_eget(self):
        """Admin står utenfor modulaksen og trenger et eget felt."""
        admin = CustomUser.objects.create_user(
            username='m_admin', password='x', role='admin',
            must_change_password=False)
        c = Client()
        c.force_login(admin)
        html = c.get('/pasienter/').content.decode('utf-8')
        self.assertIn('admin: true', html)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ServerSideSynlighetTests(TestCase):
    """Markupen rendres ikke i det hele tatt for den som ikke skal ha den.

    Erstatter `ApplyRoleVisibilityTests`, som kjørte `applyRoleVisibility()` i
    node. Den funksjonen skjulte `.write-only`, `.admin-only` og `.list-only`
    med `display:none` — markupen lå i HTML-en uansett, inkludert URL-ene til
    admin-sidene. Endepunktene var gatet, så det var ingen tilgangsgrense, men
    det er ingen grunn til å sende noe vi vet mottakeren ikke skal ha.

    Testene her er derfor strengere enn de gamle: de krever **fravær fra
    HTML-en**, ikke at noe er skjult.
    """

    def _html(self, navn, nivaa, rolle='bruker'):
        bruker = CustomUser.objects.create_user(
            username=navn, password='x', role=rolle, must_change_password=False)
        if nivaa:
            ModulTilgang.objects.create(
                bruker=bruker, modul_slug='patients', nivaa=nivaa)
        c = Client()
        c.force_login(bruker)
        resp = c.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode('utf-8')

    def test_les_far_ingen_skriveknapper(self):
        """Selve feilen fra staging, nå på riktig lag."""
        html = self._html('ss_les', 'les')
        self.assertNotIn('openNewModal', html)
        self.assertNotIn('id="btn-save-edit"', html)

    def test_skriv_full_far_dem(self):
        """Vern mot at testen over passerer fordi alt er borte for alle."""
        html = self._html('ss_skriv', 'skriv_full')
        self.assertIn('openNewModal', html)
        self.assertIn('id="btn-save-edit"', html)

    def test_ikke_admin_far_ingen_adminkort(self):
        html = self._html('ss_ikke_admin', 'skriv_full')
        for markor in ('doResetActiveYear', 'lagreVaktSomArkiv',
                       'addForstehjelper', '/portal-admin/innstillinger/'):
            with self.subTest(markor=markor):
                self.assertNotIn(markor, html)

    def test_admin_far_adminkortene(self):
        html = self._html('ss_admin', None, rolle='admin')
        for markor in ('doResetActiveYear', 'lagreVaktSomArkiv',
                       'addForstehjelper', '/portal-admin/innstillinger/'):
            with self.subTest(markor=markor):
                self.assertIn(markor, html)

    def test_admin_url_er_ikke_i_html_for_ikke_admin(self):
        """Poenget med flyttingen: URL-strukturen røpes ikke lenger.

        `.admin-only` skjulte kortene, men lenkene lå der for enhver med
        utviklerverktøy.
        """
        html = self._html('ss_url', 'skriv_full')
        self.assertNotIn('/portal-admin/', html)
