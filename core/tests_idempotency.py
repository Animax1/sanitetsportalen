"""Tester for idempotens ved pasientopprettelse (F3).

Hendelsen som utløste mekanismen: 30. april 2026 ble en pasient registrert
dobbelt på Grønn sone i prod. Testene under er skrevet rundt de tre stiene som
kan gjenskape den — dobbeltinnsending mens den første kjører, retry etter at
den er ferdig, og en cache som ikke svarer.
"""
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from core.idempotency import bygg_nokkel, forkast, fullfor, reserver
from patients.models import AppSetting, Patient
from accounts.test_helpers import gi_standardtilgang


NY_PASIENT = {
    'problemstilling': 'Pustevansker',
    'inntid': '19.04.2026 14:30',
}


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class IdempotensKjerneTests(TestCase):
    """Modulen for seg, uten et endepunkt i veien."""

    def setUp(self):
        cache.clear()

    def test_nokkel_avvises_naar_klienten_ikke_sendte_noe_brukbart(self):
        """None betyr «ingen idempotens» — kallstedet oppfører seg som før F3."""
        for ubrukelig in (None, '', 'kort', 'x' * 65, 'har mellomrom',
                          'ugyldig/tegn'):
            self.assertIsNone(
                bygg_nokkel('patient_create', 1, ubrukelig),
                f'{ubrukelig!r} skulle vært avvist',
            )

    def test_nokkelen_er_navnerommet_per_bruker(self):
        """To brukere med samme tilfeldige verdi skal ikke kollidere."""
        a = bygg_nokkel('patient_create', 1, 'a1b2c3d4-e5f6-0000-1111-222233334444')
        b = bygg_nokkel('patient_create', 2, 'a1b2c3d4-e5f6-0000-1111-222233334444')
        self.assertIsNotNone(a)
        self.assertNotEqual(a, b)

    def test_livslopet_ny_pagar_ferdig(self):
        n = bygg_nokkel('patient_create', 1, 'aaaabbbbccccdddd')

        self.assertEqual(reserver(n), ('ny', None))
        self.assertEqual(reserver(n), ('pagar', None))

        fullfor(n, 42)
        self.assertEqual(reserver(n), ('ferdig', 42))

    def test_forkast_frigir_nokkelen(self):
        """Feiler opprettelsen, skal brukeren kunne prøve igjen med samme nøkkel."""
        n = bygg_nokkel('patient_create', 1, 'aaaabbbbccccdddd')
        reserver(n)
        forkast(n)
        self.assertEqual(reserver(n), ('ny', None))

    def test_cachefeil_gir_opprett_uansett(self):
        """Bedre dobbel registrering enn ingen registrering.

        En død cache skal ikke kunne stanse pasientregistrering under vakt.
        """
        n = bygg_nokkel('patient_create', 1, 'aaaabbbbccccdddd')
        with self.assertLogs('core.idempotency', level='WARNING'):
            with patch('core.idempotency.cache.add',
                       side_effect=ConnectionError('Redis er nede')):
                self.assertEqual(reserver(n), ('ny', None))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class IdempotensEndepunktTests(TestCase):
    """`POST /pasienter/api/patients/` med og uten nøkkel."""

    NOKKEL = 'a1b2c3d4-e5f6-0000-1111-222233334444'

    def setUp(self):
        cache.clear()
        AppSetting.objects.update_or_create(
            key='active_year', defaults={'value': '2026'},
        )
        self.user = CustomUser.objects.create_user(
            username='idem-skriver', password='pass', role='read_write',
            must_change_password=False,
        )
        gi_standardtilgang(self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def _post(self, **ekstra):
        kropp = dict(NY_PASIENT)
        kropp.update(ekstra)
        return self.client.post(
            '/pasienter/api/patients/',
            data=json.dumps(kropp),
            content_type='application/json',
        )

    def test_uten_nokkel_oppfores_som_for(self):
        """Eldre klienter og API-integrasjoner skal ikke brekke."""
        self.assertEqual(self._post().status_code, 201)
        self.assertEqual(self._post().status_code, 201)
        self.assertEqual(Patient.objects.count(), 2)

    def test_to_raske_poster_med_samme_nokkel_gir_en_pasient(self):
        """Akseptansekriteriet i F3, og selve hendelsen fra 30. april."""
        forste = self._post(idempotency_key=self.NOKKEL)
        self.assertEqual(forste.status_code, 201)

        # Den andre kommer mens den første fortsatt regnes som «pågår» —
        # `fullfor` har ikke rukket å kjøre i et ekte race.
        cache.set(bygg_nokkel('patient_create', self.user.pk, self.NOKKEL),
                  '__pagar__', 300)
        andre = self._post(idempotency_key=self.NOKKEL)

        self.assertEqual(andre.status_code, 409)
        self.assertTrue(andre.json()['duplikat'])
        self.assertEqual(Patient.objects.count(), 1)

    def test_retry_etter_fullfort_gir_samme_pasient_med_200(self):
        """En nettverks-retry skal få svaret, ikke en ny rad.

        200 og ikke 201: ingenting ble opprettet av *denne* forespørselen.
        """
        forste = self._post(idempotency_key=self.NOKKEL)
        self.assertEqual(forste.status_code, 201)

        andre = self._post(idempotency_key=self.NOKKEL)
        self.assertEqual(andre.status_code, 200)
        self.assertEqual(andre.json()['id'], forste.json()['id'])
        self.assertEqual(Patient.objects.count(), 1)

    def test_ulike_nokler_gir_to_pasienter(self):
        """To faner er to reelle registreringer, ikke en dublett."""
        self.assertEqual(self._post(idempotency_key=self.NOKKEL).status_code, 201)
        self.assertEqual(
            self._post(idempotency_key='99998888-7777-6666-5555-444433332222')
            .status_code, 201,
        )
        self.assertEqual(Patient.objects.count(), 2)

    def test_avvist_innsending_brenner_ikke_nokkelen(self):
        """Grunnen til at reservasjonen skjer etter all validering.

        Reserverte vi før, ville brukeren som rettet en feil i skjemaet fått
        «allerede sendt inn» på det korrigerte forsøket — og ikke kommet
        videre uten å lukke og åpne skjemaet på nytt.
        """
        avvist = self._post(idempotency_key=self.NOKKEL, inntid='19/04/2026 14:30')
        self.assertEqual(avvist.status_code, 400)
        self.assertEqual(Patient.objects.count(), 0)

        rettet = self._post(idempotency_key=self.NOKKEL)
        self.assertEqual(rettet.status_code, 201)
        self.assertEqual(Patient.objects.count(), 1)

    def test_slettet_pasient_blokkerer_ikke_ny_registrering(self):
        """Nøkkelen peker på en rad som ikke finnes lenger.

        DELETE er en hard-delete, så dette er en reell tilstand. Nøkkelen
        beskytter da ingenting, og forespørselen skal gå videre og opprette.
        """
        forste = self._post(idempotency_key=self.NOKKEL)
        Patient.objects.get(pk=forste.json()['id']).delete()

        paa_nytt = self._post(idempotency_key=self.NOKKEL)
        self.assertEqual(paa_nytt.status_code, 201)
        self.assertEqual(Patient.objects.count(), 1)

    def test_nokkelen_gjelder_kun_egen_bruker(self):
        """To personer som tilfeldigvis sender samme nøkkel skal ikke blokkere hverandre."""
        self.assertEqual(self._post(idempotency_key=self.NOKKEL).status_code, 201)

        annen = CustomUser.objects.create_user(
            username='idem-annen', password='pass', role='read_write',
            must_change_password=False,
        )
        gi_standardtilgang(annen)
        c = Client()
        c.force_login(annen)
        svar = c.post(
            '/pasienter/api/patients/',
            data=json.dumps({**NY_PASIENT, 'idempotency_key': self.NOKKEL}),
            content_type='application/json',
        )
        self.assertEqual(svar.status_code, 201)
        self.assertEqual(Patient.objects.count(), 2)
