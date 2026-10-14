"""Personvernerklæringen, `/personvern/` (12. okt. 2026) — `core/personvern.py`.

Tre ting skal holde: siden svarer **uten innlogging**, tallene den oppgir er
**de koden håndhever**, og den er **lenket fra hver side** med egen `<head>`.
Den andre er den som ville forfalt i stillhet: en lagringstid skrevet av for
hånd står igjen på siden den dagen noen flytter den, og en erklæring som
oppgir feil frist er verre enn en som ikke oppgir noen.
"""
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.middleware import sesjonstid_timer
from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.management.commands.purge_old_logs import DEFAULT_LOG_DAYS, DEFAULT_NOTIFICATION_DAYS
from core import personvern
from core.kartkobling import DELT_VARIGHET_NOKKEL
from core.models import AppSetting
from core.offsite import FORVENTET_DAGER, PREFIKS, PREFIKS_FULL

ROT = Path(settings.BASE_DIR)
MAL = ROT / 'core/templates/core/personvern.html'

#: Sider med egen <head> uten lenken. Tom for portalsider med vilje — en ny
#: side uten lenken skal bli rød, ikke havne her uten at noen har tenkt seg om.
UTEN_LENKE = {
    'templates/vaktliste/fil.html': 'Vaktlista som fil på e-post — et dokument, ikke en portalside',
    'core/templates/core/personvern.html': 'Erklæringen selv',
}

#: Tall med enhet som kan stå i malen. Alt annet skal komme fra koden.
TILLATTE_TALL = {
    '24 timer': 'kartets frist, håndhevet av kart.sanitet.net og ikke av portalen (A.9)',
}


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SidenTests(TestCase):

    def test_svarer_uten_innlogging(self):
        svar = Client().get('/personvern/')
        self.assertEqual(svar.status_code, 200)
        self.assertContains(svar, 'personvern@sanitet.net')
        self.assertContains(svar, 'Kverneland Røde Kors')
        self.assertContains(svar, 'eies, driftes og utvikles av <strong>André Eritsland</strong>')
        self.assertContains(svar, '<code>sessionid</code>', html=False)

    def test_tar_ikke_imot_skriving(self):
        self.assertEqual(Client().post('/personvern/').status_code, 405)

    def test_passordbyttet_staar_ikke_i_veien(self):
        bruker = CustomUser.objects.create_user(username='ny_m', password='x', must_change_password=True)
        klient = Client()
        klient.force_login(bruker)
        self.assertEqual(klient.get('/personvern/').status_code, 200)
        self.assertRedirects(klient.get('/'), '/accounts/change-password/', fetch_redirect_response=False)

    def test_tallene_folger_innstillingene(self):
        AppSetting.set('session_timeout_hours', '12')
        AppSetting.set(DELT_VARIGHET_NOKKEL, '40')
        html = Client().get('/personvern/').content.decode()
        self.assertIn('12 timer etter siste bruk', html)
        self.assertIn('i 40 minutter', html)

    def test_tallene_folger_konstantene(self):
        # Kontrollverdier, ikke de ekte: 730 står flere steder på siden (lagene, offsite),
        # og et `assertIn('730 dager')` traff dem da loggfristen ble mutert til 365.
        class Arkiv:
            retention_dager = 365 * 7

        with mock.patch.object(personvern, 'DEFAULT_LOG_DAYS', 7311), \
                mock.patch.object(personvern, 'DEFAULT_NOTIFICATION_DAYS', 7322), \
                mock.patch.dict(personvern.FORVENTET_DAGER, {PREFIKS: 7333, PREFIKS_FULL: 7344}), \
                mock.patch.object(personvern, 'arkivhandler', return_value=Arkiv()), \
                override_settings(MFA_TRUST_DEVICE_DAYS=7355):
            html = ' '.join(Client().get('/personvern/').content.decode().split())
        for tekst, antall in (('<td>7311 dager</td>', 2), ('<td>7322 dager</td>', 1),
                              ('ligger 7333 dager hos Scaleway', 1), ('7344 dager. Noe som er slettet', 1),
                              ('<td>7355 dager</td>', 1), ('arkiveres opplysningene i 84 måneder', 1)):
            with self.subTest(tekst):
                self.assertEqual(html.count(tekst), antall)

    def test_konstantene_er_de_som_haandheves(self):
        k = personvern.personvern_kontekst()
        self.assertEqual((k['logg_dager'], k['varsel_dager']), (DEFAULT_LOG_DAYS, DEFAULT_NOTIFICATION_DAYS))
        self.assertEqual((k['offsite_dager'], k['offsite_full_dager']),
                         (FORVENTET_DAGER[PREFIKS], FORVENTET_DAGER[PREFIKS_FULL]))

    def test_modulenes_frister_kommer_fra_registrene(self):
        # Tester får importere moduler; produksjonskoden i core går gjennom registrene.
        from park.services import OPPBEVARING_DAGER as PARK
        from patients.arkiv import PasientArkivHandler
        from vaktliste.overnatting import OPPBEVARING_DAGER as OVERNATTING

        html = ' '.join(Client().get('/personvern/').content.decode().split())
        self.assertIn(f'Slettes {OVERNATTING} dager etter natten', html)
        self.assertIn(f'Registreringene slettes {PARK} dager etter', html)
        mnd = round(PasientArkivHandler.retention_dager / 365 * 12)
        self.assertIn(f'arkiveres opplysningene i {mnd} måneder', html)
        self.assertEqual(personvern.arkivmaaneder('finnes_ikke'), None)

    def test_en_feilende_handler_tar_ikke_ned_siden(self):
        class Feiler:
            slug = 'park'

            def frist_dager(self):
                raise RuntimeError('treg spørring')

        with mock.patch.object(personvern, 'all_handlers', return_value=[Feiler()]):
            self.assertEqual(personvern.modulfrister(), {})
            html = ' '.join(Client().get('/personvern/').content.decode().split())
        self.assertIn('Registreringene slettes etter en fast tid', html)


class SesjonstidenTests(TestCase):
    """Samme tall som middlewaren setter — siden og sesjonen leser én funksjon."""

    def test_klemt_og_med_standard(self):
        self.assertEqual(sesjonstid_timer(), 8)
        for lagret, ventet in (('0', 1), ('99', 24), ('5', 5), ('tull', 8)):
            with self.subTest(lagret=lagret):
                AppSetting.set('session_timeout_hours', lagret)
                self.assertEqual(sesjonstid_timer(), ventet)

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_middlewaren_bruker_den(self):
        AppSetting.set('session_timeout_hours', '3')
        bruker = CustomUser.objects.create_user(username='kari_p', password='x', must_change_password=False)
        klient = Client()
        klient.force_login(bruker)
        klient.get('/personvern/')
        self.assertEqual(klient.session.get_expiry_age(), 3 * 3600)


class IngenFristForHaandTests(SimpleTestCase):

    def test_malen_skriver_ingen_frist_selv(self):
        tekst = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', MAL.read_text(encoding='utf-8'), flags=re.S)
        tekst = re.sub(r'\{#.*?#\}', '', tekst)
        tekst = re.sub(r'\{\{.*?\}\}', '', tekst)
        funn = [m.group(0) for m in re.finditer(r'\b\d+\s+(?:dager|døgn|timer|minutter|måneder|uker|år)\b', tekst)
                if m.group(0) not in TILLATTE_TALL]
        self.assertEqual(funn, [], (
            'En frist er skrevet inn for hånd i personvernerklæringen. Hent den fra koden '
            '(core/personvern.py), ellers står den igjen den dagen noen flytter den.'))


class HverSideLenkerTilErklaeringenTests(SimpleTestCase):

    def _maler(self):
        for sti in sorted(ROT.glob('**/templates/**/*.html')):
            if '.venv' in sti.parts or 'site-packages' in sti.parts:
                continue
            tekst = sti.read_text(encoding='utf-8')
            if '<title>' in tekst:
                yield sti.relative_to(ROT).as_posix(), tekst

    def test_hver_side_med_egen_head(self):
        funn = [rel for rel, tekst in self._maler()
                if rel not in UTEN_LENKE
                and "{% url 'personvern' %}" not in tekst
                and 'partials/_personvernlenke.html' not in tekst]
        self.assertEqual(funn, [], 'Sider uten lenke til /personvern/ — ta med partials/_personvernlenke.html')

    def test_unntakene_finnes(self):
        for rel in UTEN_LENKE:
            self.assertTrue((ROT / rel).exists(), rel)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LenkenPaaDeEkteSideneTests(TestCase):
    """Malskanningen ser at lenken står i fila; denne at den kommer ut i svaret."""

    def test_innlogget_og_uten(self):
        bruker = CustomUser.objects.create_user(username='ola_p', password='x', must_change_password=False)
        gi_standardtilgang(bruker, 'skriver')
        inne = Client()
        inne.force_login(bruker)
        for navn, svar in {'innlogging': Client().get('/accounts/login/'),
                           'lagsiden': Client().get('/lag/r/'),
                           'portalen': inne.get('/'),
                           'pasientsiden': inne.get('/pasienter/')}.items():
            with self.subTest(navn):
                self.assertEqual(svar.status_code, 200)
                self.assertContains(svar, 'href="/personvern/"')
