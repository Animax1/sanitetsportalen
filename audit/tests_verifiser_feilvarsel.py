"""Tester for «manage.py verifiser_feilvarsel».

Kommandoen finnes fordi varslingsstien er stille når den er ødelagt. Testene her
vokter nettopp den egenskapen: at kommandoen selv *ikke* er stille når noe er
galt. En verifiseringskommando som feiler stille er verre enn ingen kommando —
da har man et grønt svar på et spørsmål man aldri stilte.

Kjør med: python manage.py test audit.tests_verifiser_feilvarsel
"""
import logging
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'
KONSOLL = 'django.core.mail.backends.console.EmailBackend'


class OppsettskontrollTests(TestCase):
    """Steg 1: kommandoen skal nekte å gi grønt lys på et oppsett som ikke virker."""

    @override_settings(ADMINS=[], EMAIL_BACKEND=LOCMEM)
    def test_tom_admins_gir_feil_ikke_stillhet(self):
        """Tom ADMINS er den farligste tilstanden: null mottakere, null feilmelding."""
        with self.assertRaises(CommandError) as ctx:
            call_command('verifiser_feilvarsel', stdout=StringIO())
        self.assertIn('ADMINS', str(ctx.exception))

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')], EMAIL_BACKEND=KONSOLL)
    def test_konsollbackend_advarer(self):
        """Konsoll-backend betyr at ingenting sendes — det må sies tydelig."""
        ut = StringIO()
        call_command('verifiser_feilvarsel', '--dry-run', stdout=ut)
        self.assertIn('konsoll', ut.getvalue().lower())

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')], EMAIL_BACKEND=LOCMEM)
    def test_dry_run_sender_ingenting(self):
        mail.outbox = []
        call_command('verifiser_feilvarsel', '--dry-run', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0, 'Tørrkjøring sendte e-post')


class VarslingskjedeTests(TestCase):
    """Steg 3: en ekte exception skal gå hele veien til en e-post."""

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')], EMAIL_BACKEND=LOCMEM)
    def test_full_kjoring_sender_varsel_med_traceback(self):
        mail.outbox = []
        # Dempingsfilteret er per prosess og kan ha sett denne linja i en
        # tidligere test i samme kjøring.
        for handler in logging.getLogger('django.request').handlers:
            for f in handler.filters:
                if hasattr(f, '_sist_sendt'):
                    f._sist_sendt.clear()

        call_command('verifiser_feilvarsel', stdout=StringIO())

        self.assertEqual(len(mail.outbox), 1, 'Varselet kom ikke fram')
        kropp = mail.outbox[0].body
        self.assertIn('FeilvarselTest', kropp,
                      'Tracebacken mangler — da tester vi ikke exc_info-stien')
        self.assertIn('Traceback', kropp)

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')], EMAIL_BACKEND=LOCMEM)
    def test_varselet_er_merket_som_ikke_reell_feil(self):
        """Den som får mailen kl. 03 skal se med én gang at det er en test."""
        mail.outbox = []
        for handler in logging.getLogger('django.request').handlers:
            for f in handler.filters:
                if hasattr(f, '_sist_sendt'):
                    f._sist_sendt.clear()

        call_command('verifiser_feilvarsel', stdout=StringIO())
        self.assertTrue(mail.outbox, 'Ingen e-post å kontrollere')
        tekst = mail.outbox[0].subject + mail.outbox[0].body
        self.assertIn('ikke en reell feil', tekst.lower())


class TidsgrenseTests(TestCase):
    """En SMTP-vert som svelger pakkene skal gi rapport, ikke stillhet.

    Hendelsen 22. aug. 2026: Railway-containeren nådde ikke `send.ahasend.com`
    utgående, og kommandoen sto i `sock.connect()` til den ble avbrutt manuelt.
    Uten tidsgrense arver `smtplib` Pythons globale socket-timeout, som er None.
    """

    @override_settings(
        ADMINS=[('Drift', 'drift@example.invalid')],
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    )
    def test_tidsavbrudd_gir_forstaaelig_feilmelding(self):
        from unittest.mock import patch

        with patch('django.core.mail.backends.smtp.EmailBackend.open',
                   side_effect=TimeoutError('timed out')):
            with self.assertRaises(CommandError) as ctx:
                call_command('verifiser_feilvarsel', '--timeout', '1',
                             stdout=StringIO())

        melding = str(ctx.exception)
        self.assertIn('Tidsavbrudd', melding)
        # Den som leser feilen kl. 03 skal ledes mot brannmur, ikke passord.
        self.assertIn('droppet', melding)
        self.assertNotIn('EMAIL_HOST_PASSWORD', melding)

    @override_settings(
        ADMINS=[('Drift', 'drift@example.invalid')],
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    )
    def test_tidsgrensen_sendes_til_backenden(self):
        from unittest.mock import patch

        with patch('audit.management.commands.verifiser_feilvarsel.get_connection') as gc:
            gc.return_value.open.side_effect = TimeoutError()
            with self.assertRaises(CommandError):
                call_command('verifiser_feilvarsel', '--timeout', '7',
                             stdout=StringIO())
        self.assertEqual(gc.call_args.kwargs.get('timeout'), 7)


class EmailTimeoutInnstillingTests(TestCase):
    """EMAIL_TIMEOUT verner driften, ikke bare denne kommandoen.

    AdminEmailHandler sender synkront i requestens egen tråd. Uten tidsgrense
    ville en hengende SMTP-vert låst tråden for godt — og med fire tråder per
    worker skal det ikke mange feil til før appen slutter å svare for alle.
    """

    def test_email_timeout_er_satt(self):
        from django.conf import settings as s
        self.assertIsNotNone(
            getattr(s, 'EMAIL_TIMEOUT', None),
            'EMAIL_TIMEOUT mangler — da arver smtplib en uendelig timeout',
        )

    def test_email_timeout_er_kort_nok_til_aa_verne_traaden(self):
        from django.conf import settings as s
        self.assertLessEqual(
            s.EMAIL_TIMEOUT, 30,
            'En request-tråd skal ikke blokkeres i mer enn 30 sekunder på e-post',
        )


AHASEND = 'core.mail_backends.AhaSendApiBackend'


class TransportvalgTests(TestCase):
    """Steg 2 må prøve den transporten som faktisk er i bruk.

    HTTP-backenden arver `open()` fra BaseEmailBackend, som er en no-op. Kalte
    kommandoen den, ville den meldt «Åpnet og autentisert» uten å ha kontaktet
    noe — falsk grønt på nøyaktig det spørsmålet kommandoen finnes for.
    """

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')],
                       EMAIL_BACKEND=LOCMEM)
    def test_backend_uten_transport_hopper_over_steg_2(self):
        ut = StringIO()
        call_command('verifiser_feilvarsel', stdout=ut)
        tekst = ut.getvalue()
        self.assertIn('Hoppet over', tekst)
        # Skal ikke love en testmelding den ikke sendte.
        self.assertNotIn('Verifisering av e-postoppsettet', tekst)

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')],
                       EMAIL_BACKEND=AHASEND,
                       AHASEND_API_KEY='aha-sk-test',
                       AHASEND_ACCOUNT_ID='konto-1')
    def test_http_backend_sender_ekte_melding(self):
        from unittest.mock import MagicMock, patch
        svar = MagicMock()
        svar.status = 202
        svar.__enter__ = lambda s: s
        svar.__exit__ = lambda s, *a: False

        ut = StringIO()
        with patch('core.mail_backends.request.urlopen', return_value=svar) as u:
            call_command('verifiser_feilvarsel', stdout=ut)

        self.assertIn('Sendt og godtatt', ut.getvalue())
        self.assertTrue(u.called, 'Ingen HTTP-kall — steg 2 prøvde ingenting')

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')],
                       EMAIL_BACKEND=AHASEND,
                       AHASEND_API_KEY='aha-sk-test',
                       AHASEND_ACCOUNT_ID='konto-1')
    def test_http_feil_gir_handlingsrettet_melding(self):
        from unittest.mock import patch
        with patch('core.mail_backends.request.urlopen',
                   side_effect=TimeoutError('tidsavbrudd')):
            with self.assertRaises(CommandError) as ctx:
                call_command('verifiser_feilvarsel', stdout=StringIO())
        melding = str(ctx.exception)
        self.assertIn('Utsending feilet', melding)
        # Skal lede mot de faktiske årsakene, ikke bare si «feil».
        self.assertIn('scope', melding)
        self.assertIn('AHASEND_ACCOUNT_ID', melding)


class KontekstTests(TestCase):
    """Kommandoen må si hvor den kjører — svaret gjelder bare der.

    22. aug. 2026 så e-postoppsettet grønt ut både lokalt og via `railway run`,
    mens containeren ikke fikk pakkene ut i det hele tatt. Tre ganger samme dag
    traff en test eller en variabel feil miljø. Utskriften skal gjøre det
    umulig å lese et lokalt svar som om det gjaldt produksjon.
    """

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')],
                       EMAIL_BACKEND=LOCMEM)
    def test_lokal_kjoring_advarer(self):
        import os
        from unittest.mock import patch
        ut = StringIO()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RAILWAY_ENVIRONMENT_NAME', None)
            call_command('verifiser_feilvarsel', stdout=ut)
        tekst = ut.getvalue()
        self.assertIn('lokalt', tekst.lower())
        self.assertIn('IKKE produksjon', tekst)

    @override_settings(ADMINS=[('Drift', 'drift@example.invalid')],
                       EMAIL_BACKEND=LOCMEM)
    def test_container_viser_miljonavn(self):
        import os
        from unittest.mock import patch
        ut = StringIO()
        with patch.dict(os.environ, {'RAILWAY_ENVIRONMENT_NAME': 'staging',
                                     'RAILWAY_SERVICE_NAME': 'web'}):
            call_command('verifiser_feilvarsel', stdout=ut)
        tekst = ut.getvalue()
        self.assertIn('staging', tekst)
        # Navnene er invertert — utskriften må si det, ellers feilleses den.
        self.assertIn('production', tekst)
