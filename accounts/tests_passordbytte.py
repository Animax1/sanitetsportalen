"""Admin krever passordbytte — én konto eller alle (22. okt. 2026).

`accounts/passordbytte.py`, knappene i `user_detail.html` og `user_list.html`. Testene går
gjennom viewene, og kallstedet prøves med en ekte innlogget sesjon: et flagg som ble satt
uten at sesjonen døde, ville sett riktig ut i basen og latt brukeren fortsette.
"""
from __future__ import annotations

from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog


def _bruker(navn, **kw):
    kw.setdefault('must_change_password', False)
    return CustomUser.objects.create_user(username=navn, password='GammeltPassord123!', **kw)


def _innlogget(bruker) -> Client:
    c = Client()
    c.force_login(bruker)
    return c


def _har_sesjon(bruker) -> bool:
    return any(str(s.get_decoded().get('_auth_user_id')) == str(bruker.pk)
               for s in Session.objects.all())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class _Grunnlag(TestCase):

    def setUp(self):
        self.admin = _bruker('pb_admin', role='admin')
        gi_standardtilgang(self.admin, 'admin')
        self.c = _innlogget(self.admin)


class EnKontoTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.offer = _bruker('pb_kari')
        gi_standardtilgang(self.offer, 'leser')
        self.url = f'/admin/brukere/{self.offer.pk}/'

    def test_flagget_settes_brukeren_logges_ut_og_handlingen_auditlogges(self):
        hennes = _innlogget(self.offer)
        self.assertTrue(_har_sesjon(self.offer))
        res = self.c.post(self.url, {'action': 'krev_passordbytte'})
        self.assertRedirects(res, self.url, fetch_redirect_response=False)
        self.offer.refresh_from_db()
        self.assertTrue(self.offer.must_change_password)
        self.assertFalse(_har_sesjon(self.offer))
        # Passordet er det samme — hun bytter det selv.
        self.assertTrue(self.offer.check_password('GammeltPassord123!'))
        # Og den gamle fanen kommer ingen vei.
        self.assertEqual(hennes.get('/admin/brukere/').status_code, 302)
        rad, = AuditLog.objects.filter(record_id=self.offer.pk, field_name='must_change_password')
        self.assertEqual((rad.old_value, rad.new_value), ('False', 'True'))

    def test_neste_innlogging_moter_passordskjemaet(self):
        self.c.post(self.url, {'action': 'krev_passordbytte'})
        res = _innlogget(self.offer).get('/patients/')
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res['Location'], reverse('accounts:change_password'))

    def test_konto_uten_passord_faar_ikke_flagget(self):
        self.offer.set_unusable_password()
        self.offer.save()
        res = self.c.post(self.url, {'action': 'krev_passordbytte'})
        self.assertEqual(res.status_code, 302)
        self.offer.refresh_from_db()
        self.assertFalse(self.offer.must_change_password)
        self.assertFalse(AuditLog.objects.filter(
            record_id=self.offer.pk, field_name='must_change_password').exists())

    def test_knappen_vises_bare_med_passord(self):
        self.assertContains(self.c.get(self.url), 'value="krev_passordbytte"')
        self.offer.set_unusable_password()
        self.offer.save()
        self.assertNotContains(self.c.get(self.url), 'value="krev_passordbytte"')

    def test_vanlig_bruker_kan_ikke(self):
        annen = _bruker('pb_annen')
        gi_standardtilgang(annen, 'leder')
        res = _innlogget(annen).post(self.url, {'action': 'krev_passordbytte'})
        self.assertEqual(res.status_code, 403)
        self.offer.refresh_from_db()
        self.assertFalse(self.offer.must_change_password)


class AlleTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.personlig = _bruker('pb_ola')
        self.admin2 = _bruker('pb_admin2', role='admin')
        self.delt = _bruker('pb_bil', er_delt_konto=True)
        self.frossen = _bruker('pb_frossen', is_active=False)
        self.invitert = _bruker('pb_invitert')
        self.invitert.set_unusable_password()
        self.invitert.save()

    def _krev_alle(self, klient=None):
        return (klient or self.c).post('/admin/brukere/', {'action': 'krev_passordbytte_alle'})

    def _flagg(self, bruker):
        bruker.refresh_from_db()
        return bruker.must_change_password

    def test_personlige_kontoer_med_passord_og_ingen_andre(self):
        _innlogget(self.personlig)
        _innlogget(self.delt)
        res = self._krev_alle()
        self.assertRedirects(res, '/admin/brukere/', fetch_redirect_response=False)
        self.assertTrue(self._flagg(self.personlig))
        self.assertTrue(self._flagg(self.admin2))
        self.assertFalse(_har_sesjon(self.personlig))
        for unntatt in (self.delt, self.frossen, self.invitert, self.admin):
            self.assertFalse(self._flagg(unntatt), unntatt.username)
        # Den som trykket, og bilen, er fortsatt innlogget.
        self.assertTrue(_har_sesjon(self.admin))
        self.assertTrue(_har_sesjon(self.delt))
        self.assertEqual(
            set(AuditLog.objects.filter(field_name='must_change_password',
                                        new_value='True (alle)').values_list('record_id', flat=True)),
            {self.personlig.pk, self.admin2.pk})

    def test_vanlig_bruker_kan_ikke(self):
        leder = _bruker('pb_leder')
        gi_standardtilgang(leder, 'leder')
        res = self._krev_alle(_innlogget(leder))
        self.assertEqual(res.status_code, 403)
        self.assertFalse(self._flagg(self.personlig))

    def test_get_endrer_ingenting(self):
        self.c.get('/admin/brukere/', {'action': 'krev_passordbytte_alle'})
        self.assertFalse(self._flagg(self.personlig))
