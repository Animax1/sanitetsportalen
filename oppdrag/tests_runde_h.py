"""Andrés forbedringsliste 12. sep. 2026, statusene i bilen.

«Behandlet på sted så ledig», «når du trykker rykker ut så skal det der
ledig nå står erstattes med avbryt», og «etter avreist kan du ikke slå deg
ledig før du har levert. Sentralen kan selvsagt redigere.»
"""
import json

from django.test import SimpleTestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node)

from . import choices, services
from .arkiv import OppdragArkivHandler, arkiver_vakt
from .models import ArkivertOppdrag, OppdragArkiv
from .statistikk import _STATUSFELT
from .tests_flere_enheter import FlereEnheterBasis


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BehandletIStatistikkOgArkivTests(FlereEnheterBasis):
    def _behandlet(self):
        o = self._oppdrag(self.a)
        for st in (choices.RYKKER_UT, choices.FREMME, choices.BEHANDLET, choices.LEDIG):
            services.sett_status(o, st, enhet=self.a)
        return o

    def test_utledet_status_regner_behandlet_som_ferdig_paa_stedet(self):
        self.assertEqual(services.utledet_av_statuser([choices.BEHANDLET, choices.VENTER]), choices.BEHANDLET)
        self.assertEqual(services.utledet_av_statuser([choices.BEHANDLET, choices.LEVERER]), choices.LEVERER)
        self.assertEqual(services.utledet_av_statuser([choices.BEHANDLET, choices.LEDIG]), choices.BEHANDLET)

    def test_tid_paa_stedet_slutter_ved_behandlet(self):
        from .statistikk import oppdrag_stats
        self._behandlet()
        stats = oppdrag_stats(self.vakt)
        self.assertEqual(stats['summary']['tid_pa_stedet']['n'], 1)

    def test_arkivet_har_kolonnen_og_signaturen_utelater_den_naar_tom(self):
        self.assertEqual(_STATUSFELT[choices.BEHANDLET], 'behandlet_at')
        o = self._behandlet()
        u = self._oppdrag(self.b)
        services.sett_status(u, choices.RYKKER_UT, enhet=self.b)
        services.sett_status(u, choices.LEDIG, enhet=self.b, manuell=True)
        arkiv, _ = arkiver_vakt(self.vakt, 'test', None)
        rader = {r['enhet_navn']: r for r in OppdragArkivHandler().rad_dicts(arkiv)}
        self.assertIn('behandlet_at', rader[self.a.navn], 'satt: står i payloaden')
        self.assertNotIn('behandlet_at', rader[self.b.navn], 'tom: utelatt, så eldre signaturer holder')
        self.assertIsNotNone(ArkivertOppdrag.objects.get(arkiv=arkiv, enhet_navn=self.a.navn).behandlet_at)


class BilensKnapperJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_ENHET_JS, ('renderAktivt', 'delteLinjerBlokk', 'erNyDelt', 'hendelsesnr', 'oppdragsnr', 'hastegradKlasse', '_udefinertVarsel', '_antallRad', '_medAntall',
                            '_problemMedAntall', 'tidslinjeEnhetHtml', '_stedvalg',
                            '_grovsorteringsrad', '_kanGrovsortere', '_varsledeRad', 'projiser')),
    )
    STUBB = ("globalThis.velgerStedFor = null; globalThis.AVREIST_TIL = []; globalThis.GROVSORTERING = [];\n"
             "const el = { innerHTML: '' }; globalThis.document = { getElementById: () => el };\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kort(self, status, neste, alt, kan_avbryte=False):
        return run_node(self.harness, self.STUBB + f"""
            globalThis.mineOppdrag = [{{ id: 1, status: '{status}', status_navn: 'x', problemstilling: 'Fall',
              hastegrad: 'Akutt', lokasjon_navn: 'Scene', opprettet: '2026-09-12T10:00:00Z', fritekst: '',
              neste_overgang: {json.dumps(neste)}, neste_navn: {json.dumps(neste)},
              alternativ_overgang: {json.dumps(alt)}, alternativ_navn: {json.dumps(alt)},
              kan_avbryte: {json.dumps(kan_avbryte)},
              statusmeldinger: [], varslede: [] }}];
            renderAktivt();
            console.log(el.innerHTML);
        """)

    def test_ingen_egen_ledig_knapp_og_den_andre_knappen_folger_statusen(self):
        ut = self._kort('rykker_ut', 'fremme', None, kan_avbryte=True)
        self.assertNotIn('stempleLedig', ut)
        self.assertNotIn('stempleAlternativ', ut)
        self.assertIn('data-action="stempleAvbryt"', ut)
        # Fremme har begge (22. sep. 2026): Behandlet på sted og Avbryt.
        ut = self._kort('fremme', 'avreist', 'behandlet', kan_avbryte=True)
        self.assertIn('stempleAlternativ', ut)
        self.assertIn('data-action="stempleAvbryt"', ut)
        self.assertEqual(ut.count('stor-knapp'), 3)
        ut = self._kort('avreist', 'leverer', None)
        self.assertNotIn('stempleAlternativ', ut, 'mellom Avreist og Leverer: bare neste')
        self.assertNotIn('stempleAvbryt', ut, 'ikke fra Avreist av')
        self.assertEqual(ut.count('stor-knapp'), 1)

    def test_projeksjonen_sier_utfort_uten_pasient(self):
        """Den andre knappen mens «Fremme» ligger usendt: «Utført» på Drift og
        Plassering, «Behandlet på sted» ellers (19. sep. 2026)."""
        ut = run_node(self.harness, """
            globalThis.OPPDRAG_NESTE = { rykker_ut: 'fremme', fremme: 'avreist' };
            globalThis.OPPDRAG_STATUSNAVN = { fremme: 'Fremme' };
            globalThis.OPPDRAG_ALTERNATIV = { fremme: 'behandlet' };
            globalThis.OPPDRAG_ALTERNATIV_NAVN = { behandlet: 'Behandlet på sted' };
            const k = [{ oppdragId: 7, overgang: 'fremme' }];
            console.log(JSON.stringify(['Drift', 'Plassering', 'Akutt'].map((h) => projiser([{ id: 7, status: 'rykker_ut', hastegrad: h }], k)[0].alternativ_navn)));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), ['Utført', 'Utført', 'Behandlet på sted'])

    def test_projeksjonen_kjenner_avbryt(self):
        ut = run_node(self.harness, """
            globalThis.OPPDRAG_NESTE = { rykker_ut: 'fremme', fremme: 'avreist', behandlet: 'ledig' };
            globalThis.OPPDRAG_STATUSNAVN = { ledig: 'Ledig', behandlet: 'Behandlet på sted' };
            globalThis.OPPDRAG_ALTERNATIV = { fremme: 'behandlet' };
            globalThis.OPPDRAG_ALTERNATIV_NAVN = { behandlet: 'Behandlet på sted' };
            globalThis.OPPDRAG_AVBRYT_FRA = ['fremme', 'rykker_ut'];
            const r = projiser([{ id: 7, status: 'rykker_ut' }], [{ oppdragId: 7, overgang: 'avbryt' }]);
            console.log(JSON.stringify([r[0].status, r[0].neste_overgang, r[0].alternativ_overgang, r[0].kan_avbryte]));
            const f = projiser([{ id: 7, status: 'rykker_ut' }], [{ oppdragId: 7, overgang: 'fremme' }]);
            console.log(JSON.stringify([f[0].status, f[0].alternativ_overgang, f[0].kan_avbryte]));
            const b = projiser([{ id: 7, status: 'fremme' }], [{ oppdragId: 7, overgang: 'behandlet' }]);
            console.log(JSON.stringify([b[0].status, b[0].neste_overgang, b[0].neste_navn, b[0].alternativ_overgang]));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), ['ledig', None, None, False])
        # Fremme usendt: begge knappene står, også uten dekning.
        self.assertEqual(json.loads(l[1]), ['fremme', 'behandlet', True])
        # Behandlet lukker med Ledig i samme trykk (12. sep. 2026): projeksjonen
        # viser Ledig, ikke et mellomsteg bilen aldri får se.
        self.assertEqual(json.loads(l[2]), ['ledig', None, None, None])

    def test_drift_og_plassering_har_ingen_grovsorteringsrad(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify([_kanGrovsortere({status: 'fremme', hastegrad: 'Akutt'}),
                                        _kanGrovsortere({status: 'fremme', hastegrad: 'Drift'}),
                                        _kanGrovsortere({status: 'leverer', hastegrad: 'Drift'}),
                                        _kanGrovsortere({status: 'fremme', hastegrad: 'Plassering'})]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [True, False, False, False])
