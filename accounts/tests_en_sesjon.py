"""Én innlogging per konto (André, 12. sep. 2026: «ikke tillate flere
brukere samtidig»).

Policyen har stått siden N10: logger kontoen inn et nytt sted, ryker den
forrige økta. Testene her låser den fra utsiden — to nettlesere, samme
konto — så en omskriving av innloggingsstien ikke kan miste den i stillhet.
"""
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EnInnloggingPerKontoTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='bil7', password='TestPassord123!', role='bruker',
            must_change_password=False, er_delt_konto=True)
        gi_standardtilgang(self.user, 'skriver')

    def _logg_inn(self):
        c = Client()
        res = c.post('/accounts/login/', {'username': 'bil7', 'password': 'TestPassord123!'})
        self.assertEqual(res.status_code, 302, res.content)
        self.assertEqual(c.get('/').status_code, 200, 'innlogget')
        return c

    def test_ny_innlogging_kaster_den_forrige_ut(self):
        forste = self._logg_inn()
        andre = self._logg_inn()
        res = forste.get('/')
        self.assertEqual(res.status_code, 302, 'den første økta er borte')
        self.assertTrue(res['Location'].startswith('/accounts/login/'))
        self.assertEqual(andre.get('/').status_code, 200, 'den nye står')

    def test_ogsaa_naar_kontoen_mangler_nokkel_fra_for(self):
        # Sesjoner fra før feltet fantes (13. aug. 2026) — den grundige veien.
        forste = self._logg_inn()
        CustomUser.objects.filter(pk=self.user.pk).update(current_session_key='')
        self._logg_inn()
        self.assertEqual(forste.get('/').status_code, 302)
