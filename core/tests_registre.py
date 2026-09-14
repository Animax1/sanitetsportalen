"""De to registrene som tok `core` ut av modulene (14. sep. 2026).

`core/driftstatus.py` og `core/portalinnstillinger.py` er nye mekanismer, og
begge har én egenskap som ikke vises i den glade stien:

- **Driftsdashbordet skal overleve at én modul feiler.** Et dashbord som selv
  gir 500 fordi vaktlista har en treg spørring, er borte akkurat når man
  trenger det — og da er det viktigere å se de andre kortene.
- **Portalinnstillingene skal ikke lagre halve skjemaet.** Navnet skrives på
  `Vakt`, resten i `AppSetting`, og ingen transaksjon binder dem. Todelingen
  `valider()`/`lagre()` er hele sperra.

Testene her bruker **oppdiktede handlere**, ikke de ekte. De ekte er dekket av
`core/tests_admin_status.py` og `vaktliste/tests_fil.py`; det som prøves her er
*registeret*, og da skal ikke en endring i vaktlista kunne gjøre testen grønn
eller rød av feil grunn.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase, override_settings

from core import driftstatus, kontokobling, portalinnstillinger


class _Sprekker(driftstatus.BaseDriftstatusHandler):
    slug = 'sprekker'
    order = 1

    def vaktbilde(self, vakt) -> dict:
        raise RuntimeError(
            'kunne ikke koble til redis://portal:hemmelig123@10.0.0.7:6379/0')


class _Virker(driftstatus.BaseDriftstatusHandler):
    slug = 'virker'
    order = 2

    def vaktbilde(self, vakt) -> dict:
        return {'mitt_tall': 42, 'fikk_vakt': vakt is not None}

    def epost(self) -> dict:
        return {'siste_ok_at': '2026-09-14T12:00:00'}


class DriftstatusregisteretTests(SimpleTestCase):

    def setUp(self) -> None:
        self._sikret = driftstatus.all_handlers()
        driftstatus.clear_registry()
        self.addCleanup(self._gjenopprett)

    def _gjenopprett(self) -> None:
        driftstatus.clear_registry()
        for h in self._sikret:
            driftstatus.register(h)

    def test_en_handler_som_sprekker_tar_ikke_med_seg_de_andre(self) -> None:
        driftstatus.register(_Sprekker())
        driftstatus.register(_Virker())

        verdier, feil = driftstatus.samle('vaktbilde', None)

        self.assertEqual(verdier['mitt_tall'], 42,
                         'den fungerende handleren skal levere som før')
        self.assertIn('sprekker', feil, 'feilen skal si hvilken modul det var')

    def test_feilmeldingen_vaskes_for_credentials(self) -> None:
        """Samme `_scrub_secrets` som resten av dashbordet.

        Svaret går til klienten, og havner i logger, skjermbilder og
        support-mailer. En feil fra en modul kan bære connection-strengen sin
        — det er nettopp den formen `_scrub_secrets` tar, og en handlerfeil
        skal gjennom den som alt annet.
        """
        driftstatus.register(_Sprekker())
        _, feil = driftstatus.samle('vaktbilde', None)
        self.assertNotIn('hemmelig123', feil)
        self.assertIn('[scrubbed]@', feil)

    def test_vakta_sendes_videre(self) -> None:
        driftstatus.register(_Virker())
        verdier, _ = driftstatus.samle('vaktbilde', object())
        self.assertTrue(verdier['fikk_vakt'])

    def test_uten_handlere_er_svaret_tomt_og_feilfritt(self) -> None:
        """Ingen registrerte moduler er ikke en feil — det er en portal uten
        moduler, og dashbordet skal fortsatt tegne seg."""
        verdier, feil = driftstatus.samle('vaktbilde', None)
        self.assertEqual((verdier, feil), ({}, ''))

    def test_handler_uten_slug_avvises(self) -> None:
        class UtenSlug(driftstatus.BaseDriftstatusHandler):
            pass

        with self.assertRaises(ValueError):
            driftstatus.register(UtenSlug())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class DashbordetTaalerEnDoedModulTests(TestCase):
    """Samme poeng, men gjennom det ekte endepunktet."""

    def setUp(self) -> None:
        from accounts.models import CustomUser
        from accounts.test_helpers import gi_standardtilgang

        admin = CustomUser.objects.create_user(
            username='driftadmin', password='pwd', role='admin',
            must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        self.client = Client()
        self.client.force_login(admin)

        self._sikret = driftstatus.all_handlers()
        driftstatus.register(_Sprekker())
        self.addCleanup(self._gjenopprett)

    def _gjenopprett(self) -> None:
        driftstatus.clear_registry()
        for h in self._sikret:
            driftstatus.register(h)

    def test_json_svarer_200_med_feilen_i_svaret(self) -> None:
        from django.urls import reverse

        resp = self.client.get(reverse('portaladmin:admin_server_status_json'))
        self.assertEqual(resp.status_code, 200)
        vaktbilde = resp.json()['vaktbilde']
        self.assertIn('sprekker', vaktbilde['error'])
        # Nøklene klienten leser skal finnes selv når en modul er død.
        for nokkel in ('vaktlister_i_drift', 'siste_utsending', 'oppdrag'):
            with self.subTest(nokkel=nokkel):
                self.assertIn(nokkel, vaktbilde)


class _NekterAlltid(portalinnstillinger.BasePortalinnstillingHandler):
    slug = 'nekter'
    order = 1

    def valider(self, post) -> dict:
        raise ValidationError('modulen sier nei')

    def lagre(self, verdier) -> None:      # pragma: no cover — skal aldri nås
        raise AssertionError('lagre() ble kalt etter at valider() nektet')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortalinnstillingerValidererForLagringTests(TestCase):
    """**Den egenskapen registeret finnes for.**

    En modul som nekter skal stoppe *hele* innsendingen — også portalens egne
    felter. Ellers ville vaktas navn blitt skrevet mens modulens verdier ikke
    ble det, og brukeren sett «lagret» over et halvt lagret skjema.
    """

    def setUp(self) -> None:
        from accounts.models import CustomUser
        from accounts.test_helpers import gi_standardtilgang
        from django.urls import reverse

        admin = CustomUser.objects.create_user(
            username='innstadmin', password='pwd', role='admin',
            must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        self.client = Client()
        self.client.force_login(admin)
        self.url = reverse('portaladmin:portal_settings')

        self._sikret = portalinnstillinger.all_handlers()
        self.addCleanup(self._gjenopprett)

    def _gjenopprett(self) -> None:
        portalinnstillinger.clear_registry()
        for h in self._sikret:
            portalinnstillinger.register(h)

    def test_en_modul_som_nekter_stopper_portalens_egne_felter(self) -> None:
        from core.vakt import hent_aktiv_vakt

        vakt = hent_aktiv_vakt()
        vakt.navn = 'Uendret'
        vakt.save(update_fields=['navn'])

        portalinnstillinger.register(_NekterAlltid())
        resp = self.client.post(self.url, {
            'event_name': 'Skulle ikke lagres', 'session_timeout_hours': '12'})

        self.assertEqual(resp.status_code, 200, 'skal vise skjemaet på nytt')
        self.assertEqual(hent_aktiv_vakt().navn, 'Uendret')
        self.assertContains(resp, 'modulen sier nei')

    def test_malbiten_til_en_registrert_modul_tegnes(self) -> None:
        """Uten dette ville feltene forsvunnet fra siden uten at noe feilet —
        skjemaet ville sett komplett ut og lagret standardverdier."""
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'vaktliste_fil_mottakere')
        self.assertIn('vaktliste/portalinnstillinger.html',
                      [t.name for t in resp.templates])


class _Kobler(kontokobling.BaseKontokoblingHandler):
    slug = 'kobler'
    handling = 'koble_noe'
    mal = ''

    def skjema(self, user, data=None):
        from django import forms

        class Skjema(forms.Form):
            felt = forms.CharField(required=False)

            def save(self):
                return None

        return Skjema(data) if data is not None else Skjema()


class KontokoblingsregisteretTests(SimpleTestCase):
    """Registeret som tok `accounts` ut av pasientmodulen (14. sep. 2026)."""

    def setUp(self) -> None:
        self.modul = kontokobling
        self._sikret = kontokobling.all_handlers()
        kontokobling.clear_registry()
        self.addCleanup(self._gjenopprett)

    def _gjenopprett(self) -> None:
        self.modul.clear_registry()
        for h in self._sikret:
            self.modul.register(h)

    def test_handlingsnavnet_peker_pa_handleren(self) -> None:
        self.modul.register(_Kobler())
        self.assertEqual(self.modul.for_handling('koble_noe').slug, 'kobler')
        self.assertIsNone(self.modul.for_handling('finnes-ikke'))

    def test_to_moduler_kan_ikke_dele_handlingsnavn(self) -> None:
        """**Den ene feilen registeret må stoppe.** Viewet finner handleren på
        `action`-navnet; delte to moduler det, ville den ene lagret den andres
        skjema — og brukeren sett «lagret» over noe helt annet."""
        class Tyv(_Kobler):
            slug = 'tyv'

        self.modul.register(_Kobler())
        with self.assertRaises(ValueError) as ctx:
            self.modul.register(Tyv())
        self.assertIn('koble_noe', str(ctx.exception))

    def test_handler_uten_handling_avvises(self) -> None:
        class UtenHandling(self.modul.BaseKontokoblingHandler):
            slug = 'x'

        with self.assertRaises(ValueError):
            self.modul.register(UtenHandling())
