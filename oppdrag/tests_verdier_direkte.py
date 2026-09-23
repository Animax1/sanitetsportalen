"""Verdiene rett i oppdragsvinduet (backlog punkt 4 og 5, 23. sep. 2026).

André: «klikke på disse verdiene … gir en liten dropdown for de andre
valgene», og «rediger-knappen inne i oppdraget gjemmer redigerbar info».
Svarene han ga før koden:

- **Hastegraden alene:** problemstillingen beholdes om den passer, ellers
  blir den «Udefinert».
- **Tildelt ressurs** endres bare med null eller én enhet — ellers «Flytt».
- **Hver endring står i tidslinjen** (`Oppdragsendring`).
- **Lista venter** — dette gjelder inne i oppdraget.
"""
import json

from django.test import SimpleTestCase, override_settings

from oppdrag import choices
from oppdrag.models import Lokasjon, Oppdragsendring
from patients.js_test_utils import (OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)

from .tests_runde_d import _konst
from .tests_views import OppdragBasis, _bruker, _klient


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EndringeneLoggesTests(OppdragBasis):

    def setUp(self):
        super().setUp()
        self.sentral = _bruker('sentral_verdi', 'skriv_full')
        self.c = _klient(self.sentral)
        self.o = self._oppdrag()   # Akutt / Pustevansker / Hovedscene

    def _put(self, **felt):
        return self.c.put(f'/oppdrag/api/oppdrag/{self.o.pk}/', data=json.dumps(felt),
                          content_type='application/json')

    def _endringer(self):
        return [(e.felt, e.fra_verdi, e.til_verdi, e.automatisk, e.endret_av_navn)
                for e in Oppdragsendring.objects.filter(oppdrag=self.o)]

    def test_hastegrad_som_passer_beholder_problemstillingen(self):
        res = self._put(hastegrad='Haster')
        self.assertEqual(res.status_code, 200, res.content)
        self.o.refresh_from_db()
        self.assertEqual((self.o.hastegrad, self.o.problemstilling), ('Haster', 'Pustevansker'))
        self.assertEqual(self._endringer(), [('hastegrad', 'Akutt', 'Haster', False, 'sentral_verdi')])

    def test_hastegrad_som_ikke_passer_gir_udefinert_og_to_linjer(self):
        """André: «settes til udefinert om det skiftes til drift
        problemstillinger. Ellers så beholdes problemstillingen»."""
        res = self._put(hastegrad='Drift')
        self.assertEqual(res.status_code, 200, res.content)
        self.o.refresh_from_db()
        self.assertEqual((self.o.hastegrad, self.o.problemstilling), ('Drift', choices.UDEFINERT))
        self.assertEqual(self._endringer(), [
            ('hastegrad', 'Akutt', 'Drift', False, 'sentral_verdi'),
            ('problemstilling', 'Pustevansker', choices.UDEFINERT, True, 'sentral_verdi'),
        ])

    def test_lokasjonen_logges_med_navn(self):
        ny = Lokasjon.objects.create(navn='Village')
        self.assertEqual(self._put(lokasjon_id=ny.pk).status_code, 200)
        self.assertEqual(self._endringer(), [('lokasjon', 'Hovedscene', 'Village', False, 'sentral_verdi')])

    def test_notatet_logges_uten_verdier(self):
        """Samme regel som audit: at det ble endret, aldri hva det sto."""
        self.assertEqual(self._put(fritekst='Pasienten heter Kari').status_code, 200)
        self.assertEqual(self._endringer(), [('fritekst', '', '', False, 'sentral_verdi')])
        self.assertFalse(Oppdragsendring.objects.filter(til_verdi__icontains='Kari').exists())

    def test_uendret_gir_ingen_linje_og_avvist_gir_ingen_linje(self):
        self.assertEqual(self._put(hastegrad='Akutt').status_code, 200)
        self.assertEqual(self._put(problemstilling='Finnes ikke').status_code, 400)
        self.assertEqual(self._endringer(), [])

    def test_tidslinjen_faar_endringene(self):
        self._put(hastegrad='Drift')
        data = self.c.get(f'/oppdrag/api/oppdrag/{self.o.pk}/').json()['data']
        self.assertEqual([(e['felt_navn'], e['fra'], e['til'], e['automatisk'], e['av'])
                          for e in data['endringer']],
                         [('Hastegrad', 'Akutt', 'Drift', False, 'sentral_verdi'),
                          ('Problemstilling', 'Pustevansker', choices.UDEFINERT, True, 'sentral_verdi')])

    def test_les_kan_ikke_endre(self):
        leser = _klient(_bruker('leser_verdi', 'les'))
        res = leser.put(f'/oppdrag/api/oppdrag/{self.o.pk}/', data=json.dumps({'hastegrad': 'Drift'}),
                        content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self._endringer(), [])


class VerdiReglerJsTests(SimpleTestCase):
    """Reglene i vinduet, kjørt i node."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = (_konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE')
                        + _konst(OPPDRAG_SENTRAL_JS, 'VERDIFELT')
                        + _konst(OPPDRAG_SENTRAL_JS, 'VERDIFELT_NAVN')
                        + build_harness((
                            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
                            (OPPDRAG_SENTRAL_JS, (
                                '_verdiKanEndres', '_verdiValg', '_verdiForesporsel', '_verdiTekst',
                                '_verdiBrikke', '_verdiVelgerHtml', '_verdierHtml', '_notatHtml',
                                'endringTekst', 'hastegradKlasse', 'tidslinjeHtml',
                                'enhetshendelseTekst')),
                        )))

    PRE = """
        globalThis.lokasjoner = [{id: 1, navn: 'Hovedscene', er_aktiv: true},
                                 {id: 2, navn: 'Gammel', er_aktiv: false}];
        globalThis.enheter = [{id: 10, navn: 'Amb 1', pa_vakt: true}, {id: 11, navn: 'Amb 2', pa_vakt: true},
                              {id: 12, navn: 'Av vakt', pa_vakt: false}];
        globalThis.problemstillingerFor = (h) => (h === 'Drift' ? ['Udefinert', 'Matutlevering']
                                                                : ['Udefinert', 'Pustevansker']);
        const O = (n) => ({ id: 7, hastegrad: 'Akutt', problemstilling: 'Pustevansker', lokasjon_id: 1,
                            lokasjon_navn: 'Hovedscene', status_navn: 'Venter', fritekst: '',
                            enheter: [{enhet_id: 10, enhet_navn: 'Amb 1'}, {enhet_id: 11, enhet_navn: 'Amb 2'}].slice(0, n) });
    """

    def _json(self, uttrykk):
        ut = run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));', preamble=self.PRE)
        return json.loads(ut.splitlines()[0])

    def test_ressursen_bare_med_null_eller_en_enhet_og_ingenting_uten_skriv(self):
        self.assertEqual(self._json("[0, 1, 2].map((n) => _verdiKanEndres(O(n), 'ressurs', true))"),
                         [True, True, False])
        self.assertEqual(self._json("['hastegrad', 'problemstilling', 'lokasjon'].map((f) => _verdiKanEndres(O(1), f, false))"),
                         [False, False, False])

    def test_valget_blir_riktig_foresporsel(self):
        ut = self._json("""[
            _verdiForesporsel(O(1), 'hastegrad', 'Drift'),
            _verdiForesporsel(O(1), 'lokasjon', '1'),
            _verdiForesporsel(O(0), 'ressurs', '11'),
            _verdiForesporsel(O(1), 'ressurs', '11'),
            _verdiForesporsel(O(2), 'ressurs', '11'),
            _verdiForesporsel(O(0), 'ressurs', ''),
        ]""")
        self.assertEqual(ut[0], {'url': '/oppdrag/api/oppdrag/7/', 'method': 'PUT', 'body': {'hastegrad': 'Drift'}})
        self.assertEqual(ut[1]['body'], {'lokasjon_id': 1})
        self.assertEqual(ut[2], {'url': '/oppdrag/api/oppdrag/7/enheter/11/', 'method': 'POST', 'body': {}},
                         'uten enhet: den valgte legges til')
        self.assertEqual(ut[3], {'url': '/oppdrag/api/oppdrag/7/flytt/', 'method': 'POST', 'body': {'enhet_id': 11}},
                         'med én: oppdraget flyttes')
        self.assertIsNone(ut[4], 'med flere: ingenting — det er «Flytt»')
        self.assertIsNone(ut[5])

    def test_valgene_har_den_gjeldende_valgt(self):
        ut = self._json("""[
            _verdiValg(O(1), 'problemstilling').filter((v) => v.valgt).map((v) => v.verdi),
            _verdiValg({...O(1), problemstilling: 'Deaktivert'}, 'problemstilling').map((v) => v.verdi),
            _verdiValg(O(1), 'lokasjon').map((v) => v.tekst),
            _verdiValg(O(0), 'ressurs').map((v) => v.tekst),
        ]""")
        self.assertEqual(ut[0], ['Pustevansker'])
        self.assertEqual(ut[1][0], 'Deaktivert', 'en deaktivert gjeldende verdi står med')
        self.assertEqual(ut[2], ['Hovedscene'], 'inaktive lokasjoner tilbys ikke')
        self.assertEqual(ut[3], ['Velg enhet', 'Amb 1', 'Amb 2'], 'bare de på vakt')

    def test_endringsteksten(self):
        ut = self._json("""[
            endringTekst({felt: 'hastegrad', felt_navn: 'Hastegrad', fra: 'Akutt', til: 'Drift', automatisk: false}),
            endringTekst({felt: 'problemstilling', felt_navn: 'Problemstilling', fra: 'Pustevansker', til: 'Udefinert', automatisk: true}),
            endringTekst({felt: 'fritekst', felt_navn: 'Oppdragsnotat', fra: 'x', til: 'y', automatisk: false}),
        ]""")
        self.assertEqual(ut[0], 'Hastegrad: Akutt → Drift')
        self.assertEqual(ut[1], 'Problemstilling: Pustevansker → Udefinert (passet ikke den nye hastegraden)')
        self.assertEqual(ut[2], 'Oppdragsnotat endret', 'notatet uten verdier, selv om de skulle komme')

    def test_uten_skrivetilgang_ingen_knapper(self):
        """En knapp som fører til en vegg er verre enn ingen knapp."""
        ut = self._json("[_verdierHtml(O(1), null, false), _notatHtml({...O(1), fritekst: 'hei'}, false, false)]")
        self.assertNotIn('data-action', ut[0])
        self.assertNotIn('data-action', ut[1])
        self.assertIn('hei', ut[1])
        self.assertIn('data-action="visVerdivalg"', self._json("_verdierHtml(O(1), null, true)"))

    def test_escaping_i_brikkene_nedtrekket_notatet_og_tidslinjen(self):
        ut = run_node(self.harness, """
            const ondt = '<img src=x onerror=alert(1)>';
            const o = {...O(1), problemstilling: ondt, lokasjon_navn: ondt, status_navn: ondt, fritekst: ondt,
                       enheter: [{enhet_id: 10, enhet_navn: ondt}]};
            lokasjoner.push({id: 3, navn: ondt, er_aktiv: true});
            const html = _verdierHtml(o, null, true) + _verdierHtml(o, 'lokasjon', true)
              + _verdierHtml(o, 'problemstilling', true) + _notatHtml(o, false, true) + _notatHtml(o, true, true)
              + tidslinjeHtml({endringer: [{felt: 'lokasjon', felt_navn: 'Lokasjon', fra: ondt, til: ondt,
                                            automatisk: false, tidspunkt: '2026-09-23T10:00:00Z', av: ondt}]});
            assert(!html.includes('<img'), 'rå markup: ' + html);
            assert(html.includes('&lt;img'), 'escapet bort i stedet for å vises');
        """, preamble=self.PRE)
        self.assertIn('OK', ut)

    def test_tidslinjen_tegner_endringene(self):
        """Kallstedet, ikke bare `endringTekst`: uten løkka i `tidslinjeHtml`
        ville endringene vært lagret og aldri vist."""
        ut = self._json("""tidslinjeHtml({endringer: [{felt: 'hastegrad', felt_navn: 'Hastegrad', fra: 'Akutt',
            til: 'Drift', automatisk: false, tidspunkt: '2026-09-23T10:00:00Z', av: 'andre'}]})""")
        self.assertIn('Hastegrad: Akutt → Drift', ut)
        self.assertIn('andre', ut)
