"""«Nytt siden sist du åpnet hendelsen» (27. sep. 2026).

André: varselmerke i hendelsesloggen og sidebaren ved noe nytt, «nytt siden
sist du åpnet hendelsen … i henhold til best practice». Reglene står i
`services.nye_for` og `services.merk_lest`; tjenestelaget prøves tungt, porten
som port, og tellingen gjennom den ekte pollen.
"""
from django.test import Client, TestCase, override_settings

from ko import services
from ko.models import HendelseLest

from .tests_hendelseslogg import _bruker, _gi, _Grunnlag


class NyeForTests(_Grunnlag):

    def _skriv(self, h, tekst, bruker):
        return services.skriv_linje(self.vakt, tekst, bruker=bruker, hendelse=h)

    def test_andres_linjer_er_nye_egne_er_ikke(self):
        h = self._hendelse()
        self._skriv(h, 'Fra den andre', self.andre)
        self._skriv(h, 'Fra meg', self.operator)
        # Opprettelsen og min egen linje er mine; én linje er fra den andre.
        self.assertEqual(services.nye_for(self.operator, self.vakt), {h.pk: 1})

    def test_lesemerket_nullstiller_og_nye_linjer_teller_igjen(self):
        h = self._hendelse()
        l1 = self._skriv(h, 'En', self.andre)
        services.merk_lest(self.operator, h, l1.pk)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {})
        self._skriv(h, 'To', self.andre)
        self._skriv(h, 'Tre', self.andre)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {h.pk: 2})

    def test_grensen_er_eksakt(self):
        """Linja merket er sett; den neste er ny. Av med én i begge retninger."""
        h = self._hendelse()
        l1 = self._skriv(h, 'En', self.andre)
        l2 = self._skriv(h, 'To', self.andre)
        services.merk_lest(self.operator, h, l1.pk)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {h.pk: 1})
        services.merk_lest(self.operator, h, l2.pk)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {})

    def test_systemlinjer_fra_andre_teller(self):
        """«H14 satt til Viktig av Kari» er det man skal legge merke til."""
        h = self._hendelse()
        services.merk_lest(self.operator, h, 10 ** 9)
        services.sett_prioritet(h, 'viktig', bruker=self.andre)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {h.pk: 1})

    def test_hver_bruker_har_sitt_eget_merke(self):
        h = self._hendelse()
        l1 = self._skriv(h, 'En', self.andre)
        tredje = _bruker('ko3')
        services.merk_lest(self.operator, h, l1.pk)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {})
        self.assertEqual(services.nye_for(tredje, self.vakt)[h.pk], 2)

    def test_hendelsene_telles_hver_for_seg(self):
        a, b = self._hendelse('A'), self._hendelse('B')
        self._skriv(a, 'x', self.andre)
        self._skriv(b, 'y', self.andre)
        self._skriv(b, 'z', self.andre)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {a.pk: 1, b.pk: 2})

    def test_linjer_uten_hendelse_teller_ikke(self):
        services.skriv_linje(self.vakt, 'I strømmen', bruker=self.andre)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {})

    def test_fjernet_linje_er_ikke_nytt(self):
        h = self._hendelse()
        l1 = self._skriv(h, 'Feil', self.andre)
        services.fjern(l1, bruker=self.andre)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {})

    def test_merket_gaar_bare_framover(self):
        """To faner eller skjerm 2 kan melde i ulik rekkefølge."""
        h = self._hendelse()
        l1 = self._skriv(h, 'En', self.andre)
        l2 = self._skriv(h, 'To', self.andre)
        self.assertEqual(services.merk_lest(self.operator, h, l2.pk), l2.pk)
        self.assertEqual(services.merk_lest(self.operator, h, l1.pk), l2.pk)
        self.assertEqual(HendelseLest.objects.get().til_linje, l2.pk)

    def test_merket_gaar_aldri_forbi_siste_linje(self):
        """Ellers ville linjer som ennå ikke er skrevet stått som lest."""
        h = self._hendelse()
        l1 = self._skriv(h, 'En', self.andre)
        self.assertEqual(services.merk_lest(self.operator, h, l1.pk + 1000), l1.pk)
        self._skriv(h, 'To', self.andre)
        self.assertEqual(services.nye_for(self.operator, self.vakt), {h.pk: 1})

    def test_andre_vakter_er_utenfor(self):
        from core.vakt import vakt_for_year
        h = self._hendelse()
        self._skriv(h, 'x', self.andre)
        self.assertEqual(services.nye_for(self.operator, vakt_for_year(2091)), {})


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LestPortenOgPollenTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        _gi(self.operator, 'ko', 'les')
        self.c = Client()
        self.c.force_login(self.operator)

    def test_pollen_bærer_tellingen_for_den_som_spør(self):
        h = self._hendelse()
        services.skriv_linje(self.vakt, 'x', bruker=self.andre, hendelse=h)
        svar = self.c.get('/ko/api/logg/').json()
        self.assertEqual(svar['nye'], {str(h.pk): 1})

    def test_lest_med_les_nivaa_og_pollen_blir_tom(self):
        h = self._hendelse()
        linje = services.skriv_linje(self.vakt, 'x', bruker=self.andre, hendelse=h)
        svar = self.c.post(f'/ko/api/hendelser/{h.pk}/lest/', {'til': linje.pk},
                           content_type='application/json')
        self.assertEqual((svar.status_code, svar.json()['til']), (200, linje.pk))
        self.assertEqual(self.c.get('/ko/api/logg/').json()['nye'], {})

    def test_uten_ko_tilgang_er_403(self):
        h = self._hendelse()
        c = Client()
        c.force_login(_bruker('utenfor'))
        self.assertEqual(c.post(f'/ko/api/hendelser/{h.pk}/lest/', {'til': 1},
                                content_type='application/json').status_code, 403)

    def test_ugyldig_til_er_400(self):
        h = self._hendelse()
        for kropp in ({}, {'til': 'x'}):
            with self.subTest(kropp=kropp):
                self.assertEqual(self.c.post(f'/ko/api/hendelser/{h.pk}/lest/', kropp,
                                             content_type='application/json').status_code, 400)


# ── Nettleseren ─────────────────────────────────────────────────────────────

import json  # noqa: E402
import unittest  # noqa: E402

from django.test import SimpleTestCase  # noqa: E402

from oppdrag.tests_runde_d import _konst  # noqa: E402
from patients.js_test_utils import KO_JS, build_harness, node_available, run_node  # noqa: E402

from . import tests_js  # noqa: E402
from .tests_js import PRIORITET_PREAMBLE, VINDU_DOM, VINDU_HARNESS  # noqa: E402

# Fiksturene lånes gjennom modulen, ikke ved å importere klassen: et
# testklassenavn i dette navnerommet ville fått Django til å kjøre alle
# testene i den én gang til herfra.
_H5, _H6, _H7 = (getattr(tests_js.HendelsenIHendelsesvinduetTests, n) for n in ('H5', 'H6', 'H7'))

HARNESS = VINDU_HARNESS + ((KO_JS, ('koTaImotHendelser', 'koHentLogg')),)

FORSPILL = """
    const merker = []; let svar = { ok: true };
    globalThis.apiFetch = (url, opts) => { merker.push([url, JSON.parse(opts.body).til]); return Promise.resolve(svar); };
    function koFyllHendelsevalg() {}
    function koTegnLogg() {} function koTaImotDelte() {} let koSisteId = 0;
    const tikk = () => new Promise((r) => setTimeout(r, 0));
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class MerketINettleserenTests(SimpleTestCase):
    """Tallet i tabellen og sidebaren, og lesemerket som sendes."""

    def _kjor(self, script):
        preamble = PRIORITET_PREAMBLE + _konst(KO_JS[0], 'KO_VINDUER')
        ut = run_node(build_harness(HARNESS), VINDU_DOM + FORSPILL
                      + 'koHendelser = new Map('
                      + json.dumps([[5, _H5], [6, _H6], [7, _H7]]) + ');\n'
                      + "koLinjer = new Map([[2, {id: 2, rot: 2, kilde: 'operator', hendelse_id: 5, systemkode: ''}]]);\n"
                      + '(async () => {\n' + script + '\n})();', preamble=preamble).splitlines()
        return [json.loads(l) for l in ut if l != 'OK']

    def test_merket_sier_antall_og_ordet(self):
        (ut,) = self._kjor('console.log(JSON.stringify([koNyeMerke(0), koNyeMerke(1), koNyeMerke(3), koNyeMerke(150)]));')
        self.assertEqual(ut[0], '')
        self.assertIn('>1<span class="visually-hidden"> ny</span>', ut[1])
        self.assertIn('>3<span class="visually-hidden"> nye</span>', ut[2])
        self.assertIn('title="3 nye siden du sist åpnet hendelsen"', ut[2])
        self.assertIn('>99+<', ut[3])

    def test_tabellen_og_sidebaren_viser_tallet(self):
        (ut,) = self._kjor("""
            koTaImotHendelser(Array.from(koHendelser.values()), { '6': 3 });
            const tabell = el('ko-hendelser-liste').innerHTML;
            koVelgHendelse(5);
            const side = el('ko-hendelse-sidebar').innerHTML;
            console.log(JSON.stringify({ tabell, side }));
        """)
        rad6 = ut['tabell'].split('data-id="6"')[1].split('</tr>')[0]
        self.assertIn('ko-nye', rad6)
        self.assertIn('class="h-rad h-rod h-ny"', ut['tabell'])
        self.assertNotIn('ko-nye', ut['tabell'].split('data-id="5"')[1].split('</tr>')[0])
        side6 = ut['side'].split('data-id="6"')[1].split('</button>')[0]
        self.assertIn('ko-nye', side6)
        self.assertIn(' ny"', ut['side'].split('data-id="6"')[0].rsplit('<button', 1)[1])

    def test_den_aapne_hendelsen_har_intet_merke(self):
        (ut,) = self._kjor("""
            koTaImotHendelser(Array.from(koHendelser.values()), { '5': 2 });
            koVelgHendelse(5);
            console.log(JSON.stringify(el('ko-hendelse-sidebar').innerHTML));
        """)
        self.assertNotIn('ko-nye', ut)

    def test_det_skjerm_2_viser_har_intet_merke(self):
        (ut,) = self._kjor("""
            koTaImotHendelser(Array.from(koHendelser.values()), { '6': 2 });
            koFolgerSett = Date.now(); koFolgerViser = 6;
            koTegnHendelser();
            console.log(JSON.stringify(el('ko-hendelser-liste').innerHTML));
        """)
        self.assertNotIn('ko-nye', ut)

    def test_aapning_sender_lesemerket_en_gang_og_igjen_ved_nytt(self):
        (ut,) = self._kjor("""
            koVelgHendelse(5); await tikk();
            koTegnHendelser(); await tikk();
            koLinjer.set(9, {id: 9, rot: 9, kilde: 'operator', hendelse_id: 5, systemkode: ''});
            koTegnHendelser(); await tikk();
            console.log(JSON.stringify(merker));
        """)
        self.assertEqual(ut, [['/ko/api/hendelser/5/lest/', 2], ['/ko/api/hendelser/5/lest/', 9]])

    def test_en_skjult_fane_leser_ingenting(self):
        (ut,) = self._kjor("""
            document.visibilityState = 'hidden';
            koVelgHendelse(5); await tikk();
            console.log(JSON.stringify(merker));
        """)
        self.assertEqual(ut, [])

    def test_avvist_merke_proves_igjen(self):
        (ut,) = self._kjor("""
            svar = { ok: false };
            koVelgHendelse(5); await tikk();
            svar = { ok: true };
            koTegnHendelser(); await tikk();
            koTegnHendelser(); await tikk();
            console.log(JSON.stringify(merker.length));
        """)
        self.assertEqual(ut, 2)

    def test_pollen_gir_tallene_videre(self):
        """Gjennom den ekte `koHentLogg` — kallstedet er regelen."""
        (ut,) = self._kjor("""
            const liste = Array.from(koHendelser.values());
            globalThis.apiFetch = async () => ({ json: async () => ({ data: [], hendelser: liste, nye: { '6': 4 } }) });
            await koHentLogg();
            console.log(JSON.stringify(koNyeTall));
        """)
        self.assertEqual(ut, {'6': 4})


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class FanenKommerFramTests(SimpleTestCase):

    def test_kroken_starter_lytteren(self):
        """Den ekte `DOMContentLoaded`-kroken, med hvert navn byttet mot en
        opptaker — som `test_ko_js_starter_den_etter_oppsettet`."""
        from patients.js_test_utils import read_js
        kilde = read_js(KO_JS)
        start = kilde.index("document.addEventListener('DOMContentLoaded', ")
        krok = kilde[start + len("document.addEventListener('DOMContentLoaded', "):kilde.rindex(');')]
        ut = run_node('', 'const kall = [];\n'
                      'const stub = new Proxy({}, { has: (t, k) => k !== "kall",'
                      ' get: (t, k) => k === "document" ? { getElementById: () => null }'
                      ' : (...a) => { kall.push(String(k)); return null; } });\n'
                      'new Function("stub", "with (stub) { (" + ' + json.dumps(krok) + ' + ")(); }")(stub);\n'
                      'console.log(JSON.stringify(kall));').splitlines()
        self.assertIn('koLestStart', json.loads(ut[0]))

    def test_synlig_fane_tegner_paa_nytt_skjult_gjor_ikke(self):
        ut = run_node(build_harness(((KO_JS, ('koLestStart',)),)), """
            let lytter = null; let tegnet = 0;
            globalThis.document = { visibilityState: 'hidden',
                                    addEventListener: (navn, f) => { if (navn === 'visibilitychange') lytter = f; } };
            function koTegnHendelser() { tegnet += 1; }
            koLestStart();
            lytter();
            document.visibilityState = 'visible';
            lytter();
            console.log(tegnet);
        """).splitlines()
        self.assertEqual(ut[0], '1')
