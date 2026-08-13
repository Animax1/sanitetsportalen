"""Tester for drift-puljen: logging (N3) og e-postvarsel ved kritiske feil (F1).

Kjør med: python manage.py test core.tests_drift
"""
import logging

from django.core import mail
from django.test import TestCase, override_settings

from core.log_filters import ThrottleByMessageFilter


class LoggingKonfigurasjonTests(TestCase):
    """N3: rot-loggeren skal faktisk ha en handler.

    Uten den propagerte alt til Pythons lastResort, som skriver fra WARNING —
    all INFO-logging var i praksis slått av i produksjon.
    """

    def test_rotlogger_har_handler(self):
        rot = logging.getLogger()
        self.assertTrue(rot.handlers, 'Rot-loggeren har ingen handler')

    def test_app_logger_naar_fram_paa_info(self):
        for navn in ['patients', 'core', 'accounts']:
            with self.subTest(logger=navn):
                logger = logging.getLogger(navn)
                self.assertTrue(
                    logger.isEnabledFor(logging.INFO),
                    f'INFO er ikke aktivert for {navn}',
                )

    def test_handler_har_formatter_med_tidsstempel(self):
        rot = logging.getLogger()
        formatter = rot.handlers[0].formatter
        self.assertIsNotNone(formatter, 'Handleren mangler formatter')
        self.assertIn('asctime', formatter._fmt)
        self.assertIn('levelname', formatter._fmt)


class ErrorEpostTests(TestCase):
    """F1: uhåndterte feil skal gi e-post, men ikke i en endeløs strøm."""

    @override_settings(
        ADMINS=[('Drift', 'drift@example.invalid')],
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_error_i_django_request_sender_epost(self):
        mail.outbox = []
        logger = logging.getLogger('django.request')
        logger.error('Testfeil i request', exc_info=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Testfeil', mail.outbox[0].subject + mail.outbox[0].body)

    @override_settings(
        ADMINS=[('Drift', 'drift@example.invalid')],
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_gjentatt_feil_gir_kun_en_epost(self):
        """Uten demping kan én feil i en travel sti gi hundrevis av mailer."""
        mail.outbox = []
        logger = logging.getLogger('django.request')
        for _ in range(20):
            logger.error('Samme feil om og om igjen')
        self.assertEqual(len(mail.outbox), 1)


class ThrottleFilterTests(TestCase):
    """Selve dempingsfilteret, uavhengig av e-postoppsettet."""

    def _record(self, melding, linje=10, navn='test'):
        return logging.LogRecord(
            name=navn, level=logging.ERROR, pathname='/app/x.py',
            lineno=linje, msg=melding, args=(), exc_info=None,
        )

    def test_forste_slipper_gjennom(self):
        f = ThrottleByMessageFilter(window_seconds=900)
        self.assertTrue(f.filter(self._record('feil')))

    def test_gjentakelse_dempes(self):
        f = ThrottleByMessageFilter(window_seconds=900)
        f.filter(self._record('feil'))
        self.assertFalse(f.filter(self._record('feil')))

    def test_ulike_steder_dempes_ikke_av_hverandre(self):
        """To ulike feil skal ikke skjule hverandre."""
        f = ThrottleByMessageFilter(window_seconds=900)
        self.assertTrue(f.filter(self._record('feil', linje=10)))
        self.assertTrue(f.filter(self._record('feil', linje=99)))

    def test_samme_sted_ulik_tekst_dempes(self):
        """Samme kodefeil gir ofte varierende tekst (ulike ID-er, verdier).

        Nøkkelen er derfor sted, ikke tekst — ellers slipper hver variant
        gjennom som om den var en ny feil.
        """
        f = ThrottleByMessageFilter(window_seconds=900)
        self.assertTrue(f.filter(self._record('feil for pasient 41')))
        self.assertFalse(f.filter(self._record('feil for pasient 42')))

    def test_vinduet_utloper(self):
        f = ThrottleByMessageFilter(window_seconds=0)
        self.assertTrue(f.filter(self._record('feil')))
        self.assertTrue(f.filter(self._record('feil')))
