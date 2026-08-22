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
