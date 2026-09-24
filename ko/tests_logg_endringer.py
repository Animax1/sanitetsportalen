"""Endringsnummeret for loggen (24. sep. 2026), og det KO skriver på
oppdragene i sentralbordets liste.

`logg` er alt `logg_view` sender: linjene, festing og fjerning (som endrer en
rad uten ny id), delingene og hendelseslista. Loggen hentes nå når tallet er
nytt, hvert 2,5 sekund, i stedet for hvert 15. — to operatører fører samtidig.

Oppdragsmodulens eget område (`oppdrag`) prøves i `oppdrag/tests_endringer.py`.
Her står det KO eier og som står på oppdragsraden: prioriteten, lagene og de
delte linjene — og at en vanlig linje i strømmen **ikke** får sentralbordet
til å hente listene.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.test import SimpleTestCase, override_settings

from core import endringer
from core.test_helpers import koblet, skrivinger_utenom_signalene
from ko import services
from ko import signals as ko_signals
from ko.endringer import LOGG
from ko.models import Logglinje
from oppdrag.endringer import OPPDRAG

from .tests_tavle import PorteneTests, _Grunnlag


class _Teller(_Grunnlag):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.h = services.opprett_hendelse(self.vakt, 'Fall ved scenen', bruker=self.operator)

    def _endrer(self, fn, omrade):
        foer = endringer.versjon(omrade)
        with self.captureOnCommitCallbacks(execute=True):
            fn()
        return endringer.versjon(omrade) != foer


class LoggenTests(_Teller):

    def test_en_linje(self):
        self.assertTrue(self._endrer(lambda: services.skriv_linje(self.vakt, 'Radio 3 ok', bruker=self.operator),
                                     LOGG))

    def test_festing_endrer_en_rad_uten_ny_id(self):
        linje = services.skriv_linje(self.vakt, 'Viktig', bruker=self.operator)
        self.assertTrue(self._endrer(lambda: services.fest_linje(linje, bruker=self.operator), LOGG))

    def test_prioritet_og_bli_med_paa_hendelsen(self):
        self.assertTrue(self._endrer(lambda: services.sett_prioritet(self.h, 'rod', bruker=self.operator), LOGG))
        annen = self.operator.__class__.objects.create_user(username='ko2', password='x', role='bruker')
        self.assertTrue(self._endrer(lambda: services.bli_med(self.h, annen), LOGG))

    def test_ikke_under_loaddata(self):
        foer = endringer.versjon(LOGG)
        with self.captureOnCommitCallbacks(execute=True):
            ko_signals.loggen_endret(sender=Logglinje, instance=None, raw=True)
        self.assertEqual(endringer.versjon(LOGG), foer)


class OppdragslistaFraKoTests(_Teller):
    """Det KO eier og som står på oppdragsraden (`oppdrag_til_dict`)."""

    def test_prioriteten_og_lagene(self):
        self.assertTrue(self._endrer(lambda: services.sett_prioritet(self.h, 'viktig', bruker=self.operator),
                                     OPPDRAG))
        self.assertTrue(self._endrer(lambda: services.sett_lag(self.h, [self.lag1.pk], bruker=self.operator),
                                     OPPDRAG))

    def test_en_linje_i_hendelsen_og_delingen_av_den(self):
        linje = services.skriv_linje(self.vakt, 'Pasient våken', bruker=self.operator, hendelse=self.h)
        self.assertTrue(self._endrer(lambda: services.del_linje(linje, bruker=self.operator), OPPDRAG))

    def test_hodet_alene(self):
        """Redigering av hodet skriver ingen systemlinje (audit fører den) —
        så `Hendelse` må øke tallet selv, ikke via en linje i hendelsen."""
        self.h.refresh_from_db()
        self.assertTrue(self._endrer(lambda: services.rediger_hendelse(
            self.h, bruker=self.operator, versjon=self.h.versjon, tittel='Fall ved baren'), OPPDRAG))

    def test_deling_med_ett_oppdrag_alene(self):
        """«Del med <enhet>» lager bare en `Linjedeling` — linja røres ikke."""
        from oppdrag import services as oppdrag_services
        from oppdrag.models import Oppdrag
        o = Oppdrag.objects.create(vakt=self.vakt, enhet=self.enhet, hendelse=self.h, lokasjon=self.park,
                                   problemstilling='Pustevansker', hastegrad='Akutt',
                                   oppdragsnummer=oppdrag_services.neste_oppdragsnummer(self.vakt))
        linje = services.skriv_linje(self.vakt, 'Pasient våken', bruker=self.operator, hendelse=self.h)
        self.assertTrue(self._endrer(lambda: services.del_linje(linje, bruker=self.operator, oppdrag=o), OPPDRAG))

    def test_en_linje_i_stroemmen_henter_ikke_sentralbordets_lister(self):
        self.assertFalse(self._endrer(lambda: services.skriv_linje(self.vakt, 'Radio 3 ok', bruker=self.operator),
                                      OPPDRAG),
                         'hver linje i strømmen ville fått sentralbordet til å hente begge listene')


class LoggensModellerErKobletTests(SimpleTestCase):

    LOGG = ('ko.Logglinje', 'ko.Linjedeling', 'ko.Hendelse', 'ko.HendelseLag', 'ko.HendelseDeltaker',
            'oppdrag.Oppdrag')
    OPPDRAG = ('ko.Hendelse', 'ko.HendelseLag', 'ko.Linjedeling', 'ko.Logglinje')

    def test_logg(self):
        mangler = [f'{s} {m}' for m in self.LOGG for s, sig in (('post_save', post_save), ('post_delete', post_delete))
                   if not koblet(sig, m, ko_signals.loggen_endret)]
        self.assertEqual(mangler, [])

    def test_oppdragslista(self):
        mangler = [f'{s} {m}' for m in self.OPPDRAG for s, sig in (('post_save', post_save), ('post_delete', post_delete))
                   if not koblet(sig, m, ko_signals.oppdragslista_endret)]
        self.assertEqual(mangler, [])


class LoggEndringerFangesTests(SimpleTestCase):
    """`.update()` og `bulk_*` på loggens modeller sender ingen signaler. Hver
    av dem skal stå her med begrunnelse for at tallet likevel øker."""

    SPORET = {m.split('.')[1] for m in LoggensModellerErKobletTests.LOGG}

    VURDERT = {
        'ko/services.py: Linjedeling.bulk_create': 'korriger() er atomisk og lagrer den nye linja i samme '
                                                   'transaksjon; tallet øker ved commit, etter delingene',
    }

    def test_hver_skriving_utenom_signalene_er_vurdert(self):
        funn = skrivinger_utenom_signalene(self.SPORET)
        self.assertEqual(sorted(funn - set(self.VURDERT)), [],
                         'ny skriving utenom signalene — øker den loggens tall? Vurder og før den inn')
        self.assertEqual(sorted(set(self.VURDERT) - funn), [], 'står i VURDERT, men finnes ikke lenger')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortenTests(PorteneTests):

    def test_loggens_tall_krever_les_i_ko(self):
        url = '/api/endringer/?omrader=logg,oppdrag,tavle'
        svar = self._klient('les', vaktliste=None, oppdrag=None).get(url).json()
        self.assertEqual(sorted(svar), [LOGG], 'loggen uten vaktlista og oppdragene — og ingenting annet')
        self.assertNotIn(LOGG, self._klient(None).get(url).json())
