"""`sett_status` er én transaksjon (26. sep. 2026).

Dekoratøren sto over en lesefunksjon fra 19. sep. — enhetskortet ble limt inn
mellom den og `sett_status`. Stemplingsviewet kaller `sett_status` direkte, og
`ATOMIC_REQUESTS` er av, så en feil etter at meldingen var skrevet lot en
statusmelding stå som koblingsraden og oppdraget ikke visste om.
"""
from unittest.mock import patch

from .models import Oppdragsenhet, Statusmelding
from .tests_views import StemplingBasis


class SettStatusErAtomiskTests(StemplingBasis):

    def test_feil_etter_meldingen_ruller_alt_tilbake(self):
        o = self._oppdrag()
        self.assertEqual(self._stemple(o, 'rykker_ut').status_code, 200)
        foer = Statusmelding.objects.filter(oppdrag=o).count()
        # Gjennom den ekte inngangen: bilens stempling går rett på `sett_status`.
        with patch('oppdrag.services.utledet_status', side_effect=RuntimeError('midt i')):
            with self.assertRaises(RuntimeError):
                self._stemple(o, 'fremme')
        self.assertEqual(Statusmelding.objects.filter(oppdrag=o).count(), foer,
                         'meldingen skal rulles tilbake med resten')
        self.assertEqual(Oppdragsenhet.objects.get(oppdrag=o, enhet=self.enhet).status, 'rykker_ut')
