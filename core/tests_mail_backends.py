"""Tester for AHASend-backenden som sender e-post over HTTPS.

Backenden finnes fordi Railway sperrer utgående SMTP. Den ligger i varslings-
stien, altså den stien som skal virke når alt annet feiler — derfor er det
feiloppførselen som er tyngst testet her, ikke lykketilfellet.

Kjør med: python manage.py test core.tests_mail_backends
"""
import json
from unittest.mock import MagicMock, patch
from urllib import error

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from core.mail_backends import AhaSendApiBackend, AhaSendIkkeKonfigurert

KONFIG = dict(
    AHASEND_API_KEY='aha-sk-testnokkel',
    AHASEND_ACCOUNT_ID='konto-123',
    EMAIL_TIMEOUT=10,
    DEFAULT_FROM_EMAIL='Sanitetsportalen <noreply@mail.sanitet.net>',
)


def _svar(status=202):
    s = MagicMock()
    s.status = status
    s.__enter__ = lambda self: self
    s.__exit__ = lambda self, *a: False
    return s


@override_settings(**KONFIG)
class KroppTests(SimpleTestCase):
    """Det som faktisk sendes til API-et."""

    def _send_og_fang(self, melding):
        with patch('core.mail_backends.request.urlopen',
                   return_value=_svar()) as urlopen:
            AhaSendApiBackend().send_messages([melding])
        req = urlopen.call_args.args[0]
        return req, json.loads(req.data.decode('utf-8'))

    def test_avsender_med_visningsnavn_splittes(self):
        m = EmailMessage('Emne', 'Tekst',
                         'Sanitetsportalen <noreply@mail.sanitet.net>',
                         ['drift@example.invalid'])
        _, kropp = self._send_og_fang(m)
        self.assertEqual(kropp['from'],
                         {'email': 'noreply@mail.sanitet.net',
                          'name': 'Sanitetsportalen'})

    def test_mottakere_og_emne(self):
        m = EmailMessage('Feil i prod', 'Tekst', 'a@b.no',
                         ['en@example.invalid', 'to@example.invalid'])
        _, kropp = self._send_og_fang(m)
        self.assertEqual(kropp['subject'], 'Feil i prod')
        self.assertEqual([r['email'] for r in kropp['recipients']],
                         ['en@example.invalid', 'to@example.invalid'])

    def test_tekstinnhold(self):
        m = EmailMessage('E', 'Selve tracebacken', 'a@b.no', ['c@d.no'])
        _, kropp = self._send_og_fang(m)
        self.assertEqual(kropp['text_content'], 'Selve tracebacken')
        self.assertNotIn('html_content', kropp)

    def test_html_alternativ_blir_eget_felt(self):
        m = EmailMultiAlternatives('E', 'ren tekst', 'a@b.no', ['c@d.no'])
        m.attach_alternative('<p>html</p>', 'text/html')
        _, kropp = self._send_og_fang(m)
        self.assertEqual(kropp['text_content'], 'ren tekst')
        self.assertEqual(kropp['html_content'], '<p>html</p>')

    def test_headere_og_endepunkt(self):
        m = EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])
        req, _ = self._send_og_fang(m)
        self.assertEqual(
            req.full_url,
            'https://api.ahasend.com/v2/accounts/konto-123/messages')
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.get_header('Authorization'),
                         'Bearer aha-sk-testnokkel')
        self.assertTrue(req.get_header('Idempotency-key'),
                        'Idempotency-Key mangler — duplikater kan ikke lukes bort')

    def test_idempotensnokkel_er_unik_per_melding(self):
        nokler = []
        with patch('core.mail_backends.request.urlopen', return_value=_svar()) as u:
            AhaSendApiBackend().send_messages([
                EmailMessage('A', 'T', 'a@b.no', ['c@d.no']),
                EmailMessage('B', 'T', 'a@b.no', ['c@d.no']),
            ])
        for kall in u.call_args_list:
            nokler.append(kall.args[0].get_header('Idempotency-key'))
        self.assertEqual(len(set(nokler)), 2)


@override_settings(**KONFIG)
class TidsgrenseTests(SimpleTestCase):
    """AdminEmailHandler sender synkront i requestens tråd."""

    def test_timeout_sendes_til_urlopen(self):
        with patch('core.mail_backends.request.urlopen',
                   return_value=_svar()) as u:
            AhaSendApiBackend().send_messages(
                [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])
        self.assertEqual(u.call_args.kwargs['timeout'], 10)

    @override_settings(EMAIL_TIMEOUT=None)
    def test_faller_tilbake_til_en_grense_naar_innstillingen_mangler(self):
        """Aldri None — det ville arvet Pythons uendelige socket-timeout."""
        self.assertTrue(AhaSendApiBackend().timeout)


@override_settings(**KONFIG)
class FeilhaandteringTests(SimpleTestCase):
    """Stien som skal virke når alt annet feiler, må feile forutsigbart."""

    def _feilende(self, exc):
        return patch('core.mail_backends.request.urlopen', side_effect=exc)

    def test_fail_silently_kaster_ikke(self):
        """AdminEmailHandler kaller alltid med fail_silently=True."""
        with self._feilende(TimeoutError('tidsavbrudd')):
            sendt = AhaSendApiBackend(fail_silently=True).send_messages(
                [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])
        self.assertEqual(sendt, 0)

    def test_uten_fail_silently_kaster(self):
        with self._feilende(TimeoutError('tidsavbrudd')):
            with self.assertRaises(TimeoutError):
                AhaSendApiBackend(fail_silently=False).send_messages(
                    [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])

    def test_feilen_logges_selv_naar_den_svelges(self):
        """En stille feil uten loggspor er umulig å feilsøke."""
        with self._feilende(TimeoutError('tidsavbrudd')):
            with self.assertLogs('core.mail_backends', level='ERROR') as logg:
                AhaSendApiBackend(fail_silently=True).send_messages(
                    [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])
        self.assertIn('tidsavbrudd', '\n'.join(logg.output))

    def test_http_feilkropp_tas_med_i_meldingen(self):
        """API-et forklarer *hvorfor* — ugyldig domene, manglende scope."""
        feil = error.HTTPError(
            'url', 403, 'Forbidden', {},
            __import__('io').BytesIO(b'{"message":"domain not verified"}'))
        with self._feilende(feil):
            with self.assertRaises(RuntimeError) as ctx:
                AhaSendApiBackend(fail_silently=False).send_messages(
                    [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])
        self.assertIn('403', str(ctx.exception))
        self.assertIn('domain not verified', str(ctx.exception))

    def test_svar_utenfor_2xx_teller_ikke_som_sendt(self):
        with patch('core.mail_backends.request.urlopen', return_value=_svar(500)):
            sendt = AhaSendApiBackend(fail_silently=True).send_messages(
                [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])
        self.assertEqual(sendt, 0)

    def test_for_mange_mottakere_avvises(self):
        m = EmailMessage('E', 'T', 'a@b.no',
                         [f'n{i}@example.invalid' for i in range(101)])
        with self.assertRaises(ValueError):
            AhaSendApiBackend(fail_silently=False).send_messages([m])

    def test_melding_uten_mottakere_sendes_ikke(self):
        with patch('core.mail_backends.request.urlopen') as u:
            sendt = AhaSendApiBackend().send_messages(
                [EmailMessage('E', 'T', 'a@b.no', [])])
        self.assertEqual(sendt, 0)
        u.assert_not_called()


class KonfigurasjonTests(SimpleTestCase):

    @override_settings(AHASEND_API_KEY='', AHASEND_ACCOUNT_ID='')
    def test_manglende_nokkel_gir_null_uten_aa_kaste(self):
        sendt = AhaSendApiBackend(fail_silently=True).send_messages(
            [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])
        self.assertEqual(sendt, 0)

    @override_settings(AHASEND_API_KEY='', AHASEND_ACCOUNT_ID='')
    def test_manglende_nokkel_kaster_naar_den_skal(self):
        with self.assertRaises(AhaSendIkkeKonfigurert):
            AhaSendApiBackend(fail_silently=False).send_messages(
                [EmailMessage('E', 'T', 'a@b.no', ['c@d.no'])])

    def test_tom_liste_gjor_ingenting(self):
        self.assertEqual(AhaSendApiBackend().send_messages([]), 0)
