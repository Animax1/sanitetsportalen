"""Endringsnummeret for sentralbordet (24. sep. 2026): området `oppdrag`.

Enhets- og oppdragslista hentes når tallet er nytt — hvert 2,5 sekund i
stedet for hvert 30. Et tall som ikke øker, er en bil som har stemplet uten at
sentralbordet ser det før sikkerhetsnettet slår inn. Derfor prøves hver kilde,
hver mottaker og hver skriving som går utenom signalene.

Det KO skriver på oppdragene i lista (prioritet, lag, delte linjer), prøves i
`ko/tests_logg_endringer.py` — oppdragsmodulen kjenner ikke KO.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.test import SimpleTestCase, TestCase, override_settings

from core import endringer
from core.test_helpers import koblet, skrivinger_utenom_signalene
from oppdrag import choices, services
from oppdrag import signals as oppdrag_signals
from oppdrag.endringer import OPPDRAG
from oppdrag.models import Enhet, Oppdrag

from .tests_flere_enheter import FlereEnheterBasis, _bruker, _klient


class HvaSomOekerTalletTests(FlereEnheterBasis):

    def setUp(self):
        super().setUp()
        cache.clear()

    def _endrer(self, fn):
        foer = endringer.versjon(OPPDRAG)
        with self.captureOnCommitCallbacks(execute=True):
            fn()
        return endringer.versjon(OPPDRAG) != foer

    def test_nytt_oppdrag(self):
        self.assertTrue(self._endrer(lambda: self._oppdrag(self.a)))

    def test_en_bil_som_stempler(self):
        o = self._oppdrag(self.a)
        self.assertTrue(self._endrer(lambda: services.sett_status(o, choices.RYKKER_UT)))

    def test_en_bil_som_tas_av_vakt(self):
        self.assertTrue(self._endrer(lambda: Enhet.objects.filter(pk=self.a.pk).first().save()))

    def test_et_oppdrag_som_slettes(self):
        o = self._oppdrag(self.a)
        self.assertTrue(self._endrer(o.delete))

    def test_ikke_foer_commit(self):
        """Øker tallet før raden er synlig, henter fanen det gamle bildet, ser
        det nye tallet, og henter ikke igjen — `transaction.on_commit`."""
        foer = endringer.versjon(OPPDRAG)
        with self.captureOnCommitCallbacks(execute=False):
            self._oppdrag(self.a)
            self.assertEqual(endringer.versjon(OPPDRAG), foer)

    def test_ikke_under_loaddata(self):
        foer = endringer.versjon(OPPDRAG)
        with self.captureOnCommitCallbacks(execute=True):
            oppdrag_signals.oppdrag_endret(sender=Oppdrag, instance=None, raw=True)
        self.assertEqual(endringer.versjon(OPPDRAG), foer)


class ListenesModellerErKobletTests(SimpleTestCase):
    """Hver modell sentralbordets lister leser, skal øke tallet ved lagring —
    og ved sletting der raden kan forsvinne i drift. Fjernes en mottaker,
    blir dette rødt."""

    LAGRING = ('oppdrag.Oppdrag', 'oppdrag.Oppdragsenhet', 'oppdrag.Statusmelding',
               'oppdrag.Enhetshendelse', 'oppdrag.Enhetsbytte', 'oppdrag.Enhet',
               'oppdrag.Enhetstype', 'oppdrag.Lokasjon')
    #: Enhet, enhetstype og lokasjon slettes ikke i drift — de deaktiveres.
    SLETTING = tuple(m for m in LAGRING if m not in ('oppdrag.Enhet', 'oppdrag.Enhetstype', 'oppdrag.Lokasjon'))

    def test_lagring_og_sletting(self):
        mangler = [f'post_save {m}' for m in self.LAGRING
                   if not koblet(post_save, m, oppdrag_signals.oppdrag_endret)]
        mangler += [f'post_delete {m}' for m in self.SLETTING
                    if not koblet(post_delete, m, oppdrag_signals.oppdrag_endret)]
        self.assertEqual(mangler, [])


class OppdragEndringerFangesTests(SimpleTestCase):
    """**`.update()` og `bulk_*` sender ingen signaler.** Hver slik skriving på
    en modell listene leser, skal stå her med begrunnelse for at tallet likevel
    øker — ellers står sentralbordet feil til sikkerhetsnettet slår inn."""

    SPORET = {m.split('.')[1] for m in ListenesModellerErKobletTests.LAGRING}

    VURDERT = {
        'oppdrag/services.py: Statusmelding.update': '_slett_meldinger kobler fra korrigerer rett før '
                                                     'meldingene og oppdraget slettes (post_delete)',
    }

    def test_hver_skriving_utenom_signalene_er_vurdert(self):
        funn = skrivinger_utenom_signalene(self.SPORET)
        self.assertEqual(sorted(funn - set(self.VURDERT)), [],
                         'ny skriving utenom signalene — øker den sentralbordets tall? Vurder og før den inn')
        self.assertEqual(sorted(set(self.VURDERT) - funn), [], 'står i VURDERT, men finnes ikke lenger')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortenTests(TestCase):
    """Tallet sier at noe har skjedd — det får bare den som får se listene."""

    def test_oppdragstallet_krever_les_i_oppdrag(self):
        url = '/api/endringer/?omrader=oppdrag'
        self.assertIn(OPPDRAG, _klient(_bruker('les', 'les')).get(url).json())
        self.assertNotIn(OPPDRAG, _klient(_bruker('ingen')).get(url).json())

