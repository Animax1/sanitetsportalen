"""`core.vask.vask` — URL-legitimasjon og kjente hemmeligheter (26. sep. 2026, E6)."""
from django.test import SimpleTestCase

from core.vask import vask


class VaskTests(SimpleTestCase):

    def test_url_legitimasjon(self):
        self.assertEqual(vask('redis://default:pw@host:6379/0 nede'),
                         'redis://[scrubbed]@host:6379/0 nede')

    def test_kjente_hemmeligheter(self):
        self.assertEqual(vask('nøkkel ABC123 avvist', hemmeligheter=('ABC123', '', None)),
                         'nøkkel *** avvist')

    def test_kappes_etter_vasking(self):
        """Kappet først, ville en halv nøkkel stått igjen i teksten."""
        ut = vask('xx HEMMELIGNOKKEL', hemmeligheter=('HEMMELIGNOKKEL',), maks=8)
        self.assertEqual(ut, 'xx ***')

    def test_tom_inn_tom_ut(self):
        self.assertEqual(vask(''), '')
        self.assertIsNone(vask(None))
