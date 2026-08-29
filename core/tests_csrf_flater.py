"""En side hvis JS skriver, må gi JS en CSRF-token.

Bakgrunnen er en feil som sto i produksjonskoden gjennom hele fase 3 uten at
én eneste test så den: oppdragssiden hadde ingen ``{% csrf_token %}``, så hver
POST, PUT og DELETE derfra ble avvist med en HTML-403. `res.json()` kastet på
`<!DOCTYPE`, og feilmeldingsboksen ble aldri fylt — brukeren så at ingenting
skjedde.

**Djangos testklient hopper over CSRF-sjekken.** `Client()` settes opp med
``enforce_csrf_checks=False``, så 37 view-tester bekreftet at API-et virket
mens hver eneste skriving fra nettleseren var brutt. Det er en hel feilklasse
som er usynlig for vanlige view-tester, og den må derfor testes eksplisitt.

To vern her:

**Cookie-veien er død på dette nettstedet.** ``CSRF_COOKIE_HTTPONLY = True``
gjør at JS aldri får se ``csrftoken``. Tokenet kommer fra
``<meta name="csrf-token">``, som ``base_portal.html`` legger på hver side som
arver den — men som ``getCsrfToken()`` ikke leste før 29. aug. 2026. Fiksen var
å lese den, ikke å legge en holder i hver mal: da ville neste modul gjort
samme feil.

Tre vern her:

1. **Hjelperen** leser meta-taggen (node-test).
2. **Strukturelt**: enhver mal som laster skrivende JS må gi tokenet på en
   form hjelperen faktisk leser.
3. **Oppførsel** per skrivende flate, med ``enforce_csrf_checks=True``.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from oppdrag.models import Enhet, Lokasjon
from patients.models import AppSetting


def _maler():
    rot = Path(settings.BASE_DIR)
    ut = list((rot / 'templates').rglob('*.html'))
    for app in rot.iterdir():
        app_maler = app / 'templates'
        if app_maler.is_dir():
            ut.extend(app_maler.rglob('*.html'))
    return ut


def _js_filer_i(mal_tekst):
    """JS-filene malen laster, som stier under static/js/."""
    ut = []
    for tag in re.findall(r'<script\b[^>]*>', mal_tekst):
        m = re.search(r"js/([A-Za-z0-9_.-]+\.js)", tag)
        if m:
            ut.append(Path(settings.BASE_DIR) / 'static' / 'js' / m.group(1))
    return ut


def _arvekjede(sti: Path):
    """Malen selv, pluss alt den arver fra.

    Uten dette ville testen krevd en token i hver enkelt mal, selv om den lå i
    basemalen. Samme grep som `MorkTekstPaaMorkBakgrunnTests` bruker for
    stilark.
    """
    kjede, sett = [], set()
    kø = [sti]
    rot = Path(settings.BASE_DIR)
    while kø:
        naa = kø.pop()
        if naa in sett or not naa.is_file():
            continue
        sett.add(naa)
        kjede.append(naa)
        tekst = naa.read_text(encoding='utf-8')
        for forelder in re.findall(r'{%\s*extends\s+["\']([^"\']+)["\']', tekst):
            for kandidat in (rot / 'templates' / forelder,
                             *(m / 'templates' / forelder for m in rot.iterdir()
                               if (m / 'templates').is_dir())):
                if kandidat.is_file():
                    kø.append(kandidat)
                    break
    return kjede


#: Kall som sender en skrivemetode gjennom `apiFetch`.
SKRIVEMETODE = re.compile(r"method:\s*'(POST|PUT|PATCH|DELETE)'")

#: Formene `getCsrfToken()` faktisk kan lese. Cookien står ikke her: den er
#: `HttpOnly`, altså usynlig for JS.
LESBARE_KILDER = ('name="csrf-token"', 'csrf-token-holder')


class CsrfPaaSkrivendeFlaterTests(SimpleTestCase):
    """Strukturelt vern: laster malen JS som skriver, må den gi en token."""

    def _skrivende_maler(self):
        funn = []
        for mal in _maler():
            tekst = mal.read_text(encoding='utf-8')
            for js in _js_filer_i(tekst):
                if js.is_file() and SKRIVEMETODE.search(js.read_text(encoding='utf-8')):
                    funn.append((mal, js))
                    break
        return funn

    def test_testen_finner_faktisk_skrivende_flater(self):
        """Vern mot at testen blir tom og dermed alltid grønn."""
        self.assertGreaterEqual(len(self._skrivende_maler()), 2)

    def test_skrivende_flater_gir_js_en_lesbar_token(self):
        """Ikke «finnes et token», men «finnes det på en form JS kan lese».

        Første utgave av denne testen lette etter `csrf_token` hvor som helst i
        arvekjeden. Den var grønn mens feilen sto i koden, fordi
        `base_portal.html` har en utloggingsknapp med `{% csrf_token %}` inne i
        et skjema — tokenet var på sida, men ikke et sted `getCsrfToken()` så
        etter.
        """
        mangler = []
        for mal, js in self._skrivende_maler():
            samlet = '\n'.join(
                p.read_text(encoding='utf-8') for p in _arvekjede(mal))
            if not any(kilde in samlet for kilde in LESBARE_KILDER):
                mangler.append(f'{mal.name} (laster {js.name})')

        self.assertEqual(mangler, [], (
            'Maler som laster skrivende JS uten en CSRF-token JS kan lese:\n  '
            + '\n  '.join(mangler)
            + '\n\nCookien er HttpOnly, så getCsrfToken() leser '
              '<meta name="csrf-token"> eller #csrf-token-holder. Uten en av '
              'dem avvises hver skriving med en HTML-403 som res.json() kaster '
              'på. Djangos testklient hopper over CSRF, så vanlige view-tester '
              'ser det ikke.'
        ))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class OppdragCsrfOppforselTests(TestCase):
    """Oppførselsvern med CSRF slått på, slik nettleseren har det."""

    def setUp(self):
        AppSetting.objects.update_or_create(
            key='active_year', defaults={'value': '2098'})
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.enhet = Enhet.objects.create(navn='Haugesund 56')
        self.bruker = CustomUser.objects.create_user(
            username='sentralen', password='x', role='bruker',
            must_change_password=False)
        ModulTilgang.objects.create(
            bruker=self.bruker, modul_slug='oppdrag', nivaa='skriv_full')

    def _last(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.bruker)
        return c

    def _token_slik_js_leser_den(self, html):
        """Hent tokenet fra meta-taggen — den ene kilden JS faktisk bruker."""
        m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        return m.group(1) if m else None

    def test_sida_gir_js_en_lesbar_token(self):
        html = self._last().get('/oppdrag/').content.decode()
        self.assertIsNotNone(
            self._token_slik_js_leser_den(html),
            'sida mangler <meta name="csrf-token"> — JS får ingen token')

    def test_oppretting_virker_med_token_fra_sida(self):
        """Nøyaktig det nettleseren gjør: les token fra sida, send den med."""
        c = self._last()
        html = c.get('/oppdrag/').content.decode()
        token = self._token_slik_js_leser_den(html)

        resp = c.post(
            '/oppdrag/api/oppdrag/', content_type='application/json',
            data={'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
                  'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt'},
            HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 200)

    def test_uten_token_avvises(self):
        """Vern mot at testen over passerer fordi CSRF ikke håndheves."""
        resp = self._last().post(
            '/oppdrag/api/oppdrag/', content_type='application/json',
            data={'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
                  'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt'})
        self.assertEqual(resp.status_code, 403)


class GetCsrfTokenTests(SimpleTestCase):
    """Hjelperen selv, kjørt i node mot en stubbet DOM.

    Låser mekanismen: fjerner noen meta-grenen, feiler denne — og da er hver
    modulside uten `#csrf-token-holder` brutt igjen.
    """

    def setUp(self):
        from patients.js_test_utils import (
            PORTAL_UTILS_JS, build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness([(PORTAL_UTILS_JS, ('getCsrfToken',))])

    def _kjor(self, snippet):
        from patients.js_test_utils import run_node
        return run_node(self.harness, snippet)

    def test_leser_meta_taggen(self):
        ut = self._kjor('''
            globalThis.document = {
              cookie: '',
              querySelector: (s) => s === 'meta[name="csrf-token"]'
                ? { content: 'token-fra-meta' } : null,
              getElementById: () => null,
            };
            console.log(getCsrfToken());
        ''')
        self.assertIn('token-fra-meta', ut)

    def test_holder_virker_fortsatt(self):
        """Pasientsiden bruker holderen. Meta-grenen skal ikke ta den fra den."""
        ut = self._kjor('''
            globalThis.document = {
              cookie: '',
              querySelector: () => null,
              getElementById: (id) => id === 'csrf-token-holder'
                ? { querySelector: () => ({ value: 'token-fra-holder' }) } : null,
            };
            console.log(getCsrfToken());
        ''')
        self.assertIn('token-fra-holder', ut)

    def test_tom_streng_naar_ingenting_finnes(self):
        """Vern mot at hjelperen alltid returnerer noe."""
        ut = self._kjor('''
            globalThis.document = {
              cookie: '', querySelector: () => null, getElementById: () => null,
            };
            console.log(JSON.stringify(getCsrfToken()));
        ''')
        self.assertIn('""', ut)
