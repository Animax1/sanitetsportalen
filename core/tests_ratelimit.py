"""Tester for rate-limiting utover innlogging (S3).

To lag:

* ``RateLimitKjerneTests`` kjører dekoratøren mot et syntetisk view, og dekker
  de egenskapene som er lette å miste ved en refaktorering: at hver gruppe har
  sin egen bøtte, at nøkkelen er per bruker, at nød-bryteren virker, og at en
  død cache slipper trafikken gjennom i stedet for å stanse den.
* ``RateLimitEndepunktTests`` går gjennom de faktiske URL-ene. Uten dem ville
  en dekoratør som falt av et view under en flytting passert usett.

Mønsteret med å telle ``grense + margin`` forsøk og lete etter 429 blant
statusene er arvet fra N4-testene. Vinduet i django-ratelimit er justert mot
veggklokka, så en test som krever at nøyaktig forsøk nummer N+1 feiler ville
vært flakete på et minuttskifte.
"""
import json
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.test import Client, RequestFactory, TestCase, override_settings

from accounts.models import CustomUser
from core.ratelimit import er_rate_limited, rate_limit
from patients.models import AppSetting


NY_PASIENT = {
    'problemstilling': 'Pustevansker',
    'inntid': '19.04.2026 14:30',
}


def _statuser(kall, antall):
    """Kjør ``kall()`` ``antall`` ganger og returner statuskodene."""
    return [kall().status_code for _ in range(antall)]


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class RateLimitKjerneTests(TestCase):
    """Egenskapene ved selve dekoratøren, uten en ekte URL i veien."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.en = CustomUser.objects.create_user(
            username='rl-en', password='pass', role='read_write',
            must_change_password=False,
        )
        self.to = CustomUser.objects.create_user(
            username='rl-to', password='pass', role='read_write',
            must_change_password=False,
        )

    def _view(self, **kwargs):
        @rate_limit(**kwargs)
        def _v(request):
            return JsonResponse({'ok': True})
        return _v

    def _post(self, user):
        req = self.factory.post('/syntetisk/')
        req.user = user
        return req

    def test_grensen_gir_429_med_json(self):
        view = self._view(group='test:a', rate='3/m')
        statuser = [view(self._post(self.en)).status_code for _ in range(8)]
        self.assertEqual(statuser[0], 200)
        self.assertIn(429, statuser)

        siste = view(self._post(self.en))
        self.assertEqual(siste['Content-Type'], 'application/json')
        self.assertIn('error', json.loads(siste.content))

    def test_hver_gruppe_har_egen_botte(self):
        """Kjernen i S3, og lærdommen fra N4.

        To endepunkter skal aldri dele teller. Ble gruppen utledet av
        funksjonsnavnet i stedet for oppgitt eksplisitt, kunne en flytting
        mellom moduler stille slått to bøtter sammen.
        """
        a = self._view(group='test:a', rate='3/m')
        b = self._view(group='test:b', rate='3/m')

        for _ in range(8):
            a(self._post(self.en))

        self.assertEqual(b(self._post(self.en)).status_code, 200)

    def test_botta_er_per_bruker(self):
        view = self._view(group='test:a', rate='3/m')
        for _ in range(8):
            view(self._post(self.en))

        self.assertEqual(view(self._post(self.to)).status_code, 200)

    def test_annen_metode_telles_ikke(self):
        """``method='POST'`` skal la GET gå urørt — også i telleren."""
        view = self._view(group='test:a', rate='3/m', method='POST')

        for _ in range(20):
            req = self.factory.get('/syntetisk/')
            req.user = self.en
            self.assertEqual(view(req).status_code, 200)

        self.assertEqual(view(self._post(self.en)).status_code, 200)

    @override_settings(RATELIMIT_ENABLE=False)
    def test_nodbryteren_slar_av_alt(self):
        view = self._view(group='test:a', rate='3/m')
        statuser = [view(self._post(self.en)).status_code for _ in range(20)]
        self.assertEqual(set(statuser), {200})

    def test_cachefeil_faller_apent(self):
        """En død cache skal ikke stanse pasientregistrering.

        Pakken fanger ikke ``ConnectionError`` fra ``cache.add()``, så uten
        try/except i ``er_rate_limited`` ville en Redis-utkobling gitt 500 på
        hvert skriveendepunkt i appen.
        """
        with self.assertLogs('core.ratelimit', level='WARNING'):
            with patch('core.ratelimit.is_ratelimited',
                       side_effect=ConnectionError('Redis er nede')):
                self.assertFalse(er_rate_limited(
                    self._post(self.en),
                    group='test:a', key='user', rate='1/m',
                ))

    def test_fail_open_flagget_star_pa(self):
        """Regresjonsvern for beslutningen i settings.py.

        Pakkens default er False, som betyr 429 på alt når cachen svarer uten
        verdi. Faller flagget tilbake til default, forsvinner halve
        fail-open-garantien uten at noen annen test merker det.
        """
        self.assertTrue(settings.RATELIMIT_FAIL_OPEN)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class RateLimitEndepunktTests(TestCase):
    """De fire endepunktene S3 pekte ut, pluss pasient-redigering."""

    def setUp(self):
        cache.clear()
        AppSetting.objects.update_or_create(
            key='active_year', defaults={'value': '2026'},
        )
        self.admin = CustomUser.objects.create_user(
            username='rl-admin', password='pass', role='admin',
            must_change_password=False,
        )
        self.skriver = CustomUser.objects.create_user(
            username='rl-skriver', password='pass', role='read_write',
            must_change_password=False,
        )

    def _klient(self, user):
        c = Client()
        c.force_login(user)
        return c

    def _opprett(self, klient):
        return klient.post(
            '/pasienter/api/patients/',
            data=json.dumps(NY_PASIENT),
            content_type='application/json',
        )

    def test_opprett_pasient_strupes(self):
        c = self._klient(self.skriver)
        statuser = _statuser(lambda: self._opprett(c), 65)
        self.assertEqual(statuser[0], 201)
        self.assertIn(429, statuser)

    def test_lesing_av_pasientlista_strupes_ikke(self):
        """GET pollet hvert 30. sekund av hver klient må gå fritt.

        Traff den samme bøtta som POST, ville en travel vakt strupt seg selv
        på ren lesing.
        """
        c = self._klient(self.skriver)
        statuser = _statuser(lambda: c.get('/pasienter/api/patients/'), 70)
        self.assertNotIn(429, statuser)
        self.assertEqual(self._opprett(c).status_code, 201)

    def test_full_stats_strupes(self):
        c = self._klient(self.admin)
        statuser = _statuser(lambda: c.get('/statistikk/api/full-stats/'), 35)
        self.assertEqual(statuser[0], 200)
        self.assertIn(429, statuser)

    def test_passordbytte_strupes_og_svarer_html(self):
        """Feilede gjett på nåværende passord skal fortsatt strupes."""
        c = self._klient(self.admin)

        svar = [
            c.post('/accounts/change-password/', {
                'old_password': 'feil-passord',
                'new_password1': 'NyttPassord123!',
                'new_password2': 'NyttPassord123!',
            })
            for _ in range(15)
        ]
        self.assertIn(429, [s.status_code for s in svar])

        strupt = next(s for s in svar if s.status_code == 429)
        self.assertIn('text/html', strupt['Content-Type'])

    def test_tvungent_passordbytte_strupes_aldri(self):
        """En ny bruker skal ikke kunne låse seg ute av portalen.

        `MustChangePasswordMiddleware` sperrer hver URL unntatt denne, så en
        429 her stenger brukeren ute av *hele* portalen. Og det er ikke noe
        å beskytte: `old_password` sjekkes ikke i denne stien, så det finnes
        ikke noe gammelt passord å gjette.

        Scenariet er en frivillig som fomler med passordreglene ved
        vaktstart — for kort, for likt brukernavnet, bekreftelsen skrevet
        feil.
        """
        ny = CustomUser.objects.create_user(
            username='rl-ny', password='MidlertidigPass1!', role='read_write',
            must_change_password=True,
        )
        c = self._klient(ny)

        statuser = _statuser(lambda: c.post('/accounts/change-password/', {
            'old_password': '',
            'new_password1': 'kort',
            'new_password2': 'kort',
        }), 25)
        self.assertNotIn(429, statuser)

        # ...og et gyldig forsøk skal fortsatt gå gjennom etterpå.
        ok = c.post('/accounts/change-password/', {
            'old_password': '',
            'new_password1': 'EndeligEtGodtPass1!',
            'new_password2': 'EndeligEtGodtPass1!',
        })
        self.assertEqual(ok.status_code, 302)
        ny.refresh_from_db()
        self.assertFalse(ny.must_change_password)

    def test_ugyldig_skjema_koster_ikke_kvote(self):
        """Bøtta teller gjett, ikke innsendinger.

        Uten dette skillet kunne en bruker som skrev bekreftelsen feil noen
        ganger, bruke opp kvoten sin uten å ha gjettet på passordet én gang.
        """
        c = self._klient(self.admin)

        avvist = _statuser(lambda: c.post('/accounts/change-password/', {
            'old_password': 'feil-passord',
            'new_password1': 'NyttPassord123!',
            'new_password2': 'StemmerIkke456!',
        }), 25)
        self.assertNotIn(429, avvist)

        # Kvoten skal være urørt: første ekte gjett gir «feil passord», ikke 429.
        gjett = c.post('/accounts/change-password/', {
            'old_password': 'feil-passord',
            'new_password1': 'NyttPassord123!',
            'new_password2': 'NyttPassord123!',
        })
        self.assertEqual(gjett.status_code, 200)

    def test_auditlog_eksport_strupes(self):
        c = self._klient(self.admin)
        statuser = _statuser(
            lambda: c.get('/portal-admin/auditlog/eksport.csv'), 15,
        )
        self.assertEqual(statuser[0], 200)
        self.assertIn(429, statuser)

    def test_statistikk_og_pasientoppretting_deler_ikke_botte(self):
        """Ende-til-ende-utgaven av ``test_hver_gruppe_har_egen_botte``."""
        c = self._klient(self.admin)
        _statuser(lambda: c.get('/statistikk/api/full-stats/'), 35)
        self.assertEqual(self._opprett(c).status_code, 201)
