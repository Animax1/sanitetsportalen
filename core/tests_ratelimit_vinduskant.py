"""Vakt: en rate-limit-test må sende nok forsøk til å tåle vinduskanten.

Regelen står i `CLAUDE.md` («Rate-limit-tester må tåle vinduskanten») og i
docstringen til `nok_til_a_bryte()`: en test som krever 429 etter en serie
forsøk må sende ``2 × grense + 1``, ellers kan den jitrede vinduskanten dele
serien i to bøtter der ingen når grensa. Feilen viser seg omtrent én kjøring av
seksti, og på en annen maskin enn din.

**Prosaen holdt ikke.** Regelen var brutt fem ganger da vakten kom (27. sep.
2026: CI på `main` rød på `50bdcdf`, samme commit grønn på `staging`), og
kartleggingen 29. sep. fant tre til — 15 og 12 forsøk mot `10/5m` i
innloggingen, og to tester som skrev ``2 * 10 + 1`` av for hånd.

Vakten leser testfilene med AST. En test **krever struping** når den har en
positiv assertion som bærer 429 — direkte, eller gjennom et navn som er satt fra
et uttrykk med 429 eller et kall til en ``*block*``/``*blokk*``-hjelper — og
**sender en serie** når den har en løkke. Slike tester må hente antallet fra
`nok_til_a_bryte()`, i metoden eller i klassens egne attributter.

Hva den ikke fanger: at *argumentet* er riktig grense. ``nok_til_a_bryte(5)``
mot en grense på ti går gjennom her. Den grensen er bevisst — tallet i
dekoratøren og tallet i testen står i hver sin fil, og en vakt som prøvde å
koble dem ville vært skjør på nettopp den måten som får folk til å slå den av.
"""
import ast
import pathlib
import textwrap

from django.conf import settings
from django.test import SimpleTestCase


HJELPER = 'nok_til_a_bryte'

#: Tester som krever struping etter en løkke, men ikke skal bruke hjelperen.
#: Nøkkel: ``'<sti>::<Klasse>.<metode>'``. Begrunnelsen er påkrevd.
UNNTAK: dict[str, str] = {
    'park/tests_js.py::ParkReglerTests.test_tokenet_glemmes_naar_serveren_sier_nei': (
        'Kjører en JS-regel i node over en tabell med statuskoder; 429 er data '
        'i tabellen, ikke svaret fra en serie mot serveren.'),
}

_POSITIVE = {'assertIn', 'assertEqual', 'assertTrue', 'assertGreater',
             'assertGreaterEqual', 'assertCountEqual'}


def _har_429(node):
    return any(isinstance(n, ast.Constant) and n.value == 429
               for n in ast.walk(node))


def _kaller_sperrehjelper(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            navn = getattr(n.func, 'attr', None) or getattr(n.func, 'id', '')
            if 'block' in navn.lower() or 'blokk' in navn.lower():
                return True
    return False


def _sperrenavn(funksjon):
    """Navn i funksjonen som er satt fra et uttrykk som sier «strupet»."""
    navn = set()
    for n in ast.walk(funksjon):
        if isinstance(n, ast.Assign) and (_har_429(n.value) or _kaller_sperrehjelper(n.value)):
            navn |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return navn


def krever_struping(funksjon) -> bool:
    sperrenavn = _sperrenavn(funksjon)
    for n in ast.walk(funksjon):
        if not (isinstance(n, ast.Call) and getattr(n.func, 'attr', None) in _POSITIVE):
            continue
        if any(_har_429(a) for a in n.args):
            return True
        if any(isinstance(m, ast.Name) and m.id in sperrenavn
               for a in n.args for m in ast.walk(a)):
            return True
    return False


def _har_lokke(node) -> bool:
    return any(isinstance(n, (ast.For, ast.While, ast.comprehension))
               for n in ast.walk(node))


def seriehjelpere(tre) -> set[str]:
    """Funksjoner på modulnivå som selv går i løkke — `_statuser(kall, antall)`.

    Uten dem ser vakten bare løkker skrevet rett i testen, og de tre
    endepunkttestene i `core/tests_ratelimit.py` sto utenfor: en ny
    ``_statuser(..., 12)`` ville gått rett gjennom.
    """
    return {n.name for n in tre.body
            if isinstance(n, ast.FunctionDef) and _har_lokke(n)}


def sender_serie(funksjon, hjelpere=frozenset()) -> bool:
    if _har_lokke(funksjon):
        return True
    return any(isinstance(n, ast.Call) and getattr(n.func, 'id', None) in hjelpere
               for n in ast.walk(funksjon))


def _bruker_hjelperen(node) -> bool:
    return any(isinstance(n, ast.Call) and getattr(n.func, 'id', None) == HJELPER
               for n in ast.walk(node))


def brudd_i_kilde(kilde: str, sti: str = '<kilde>'):
    """Returner ``(nøkkel, linje)`` for hver test som bryter regelen."""
    tre = ast.parse(kilde)
    hjelpere = seriehjelpere(tre)
    funn = []
    for klasse in [n for n in ast.walk(tre) if isinstance(n, ast.ClassDef)]:
        klasseattributter = [s for s in klasse.body
                             if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
        klassen_har_hjelperen = any(_bruker_hjelperen(s) for s in klasseattributter)
        for metode in klasse.body:
            if not (isinstance(metode, ast.FunctionDef) and metode.name.startswith('test')):
                continue
            if not (krever_struping(metode) and sender_serie(metode, hjelpere)):
                continue
            if _bruker_hjelperen(metode) or klassen_har_hjelperen:
                continue
            funn.append((f'{sti}::{klasse.name}.{metode.name}', metode.lineno))
    return funn


def testfilene():
    rot = pathlib.Path(settings.BASE_DIR)
    return sorted(p for p in rot.rglob('tests*.py')
                  if not {'.venv', 'venv', 'node_modules', 'staticfiles'} & set(p.parts))


def ratelimittester_i_kilde(kilde: str, sti: str = '<kilde>'):
    """Alle tester vakten regner som rate-limit-tester, med eller uten brudd."""
    tre = ast.parse(kilde)
    hjelpere = seriehjelpere(tre)
    return {f'{sti}::{k.name}.{m.name}'
            for k in ast.walk(tre) if isinstance(k, ast.ClassDef)
            for m in k.body
            if isinstance(m, ast.FunctionDef) and m.name.startswith('test')
            and krever_struping(m) and sender_serie(m, hjelpere)}


class RateLimitTesterTaalerVinduskantenTests(SimpleTestCase):

    def test_ingen_rate_limit_test_teller_forsokene_for_haand(self):
        rot = pathlib.Path(settings.BASE_DIR)
        brudd = []
        for fil in testfilene():
            sti = fil.relative_to(rot).as_posix()
            for nokkel, linje in brudd_i_kilde(fil.read_text(encoding='utf-8'), sti):
                if nokkel not in UNNTAK:
                    brudd.append(f'{sti}:{linje}  {nokkel.split("::")[1]}')
        self.assertEqual(brudd, [], (
            'Disse testene krever 429 etter en serie forsøk, men antallet kommer '
            f'ikke fra `{HJELPER}()` i core/tests_ratelimit.py. Den jitrede '
            'vinduskanten kan dele serien i to bøtter der ingen når grensa. '
            'Bruk `range(nok_til_a_bryte(<grense>))`, eller før testen i UNNTAK '
            'med begrunnelse.'))

    def test_unntakene_finnes_og_er_begrunnet(self):
        rot = pathlib.Path(settings.BASE_DIR)
        alle = set()
        for fil in testfilene():
            sti = fil.relative_to(rot).as_posix()
            alle |= {n for n, _ in brudd_i_kilde(fil.read_text(encoding='utf-8'), sti)}
        for nokkel, grunn in UNNTAK.items():
            self.assertIn(nokkel, alle, f'{nokkel} står i UNNTAK, men bryter ikke regelen lenger')
            self.assertTrue(grunn.strip(), f'{nokkel} mangler begrunnelse')

    def test_vakten_ser_de_kjente_rate_limit_testene(self):
        """Uten denne kunne klassifiseringen stille falle til null funn og vakten
        stått grønn om ingenting — en vakt som melder grønt om en dekning den
        ikke har, er verre enn ingen vakt."""
        rot = pathlib.Path(settings.BASE_DIR)
        sett = set()
        for fil in testfilene():
            sti = fil.relative_to(rot).as_posix()
            sett |= ratelimittester_i_kilde(fil.read_text(encoding='utf-8'), sti)
        for kjent in (
            # assertIn(429, …) over en listeforståelse
            'core/tests_ratelimit.py::RateLimitEndepunktTests.test_passordbytte_strupes_og_svarer_html',
            # antallet i et klasseattributt
            'accounts/tests_sikkerhet_runde2.py::RateLimitPaaBrukeradminTests.test_sletting_strupes',
            # «blokkert» satt fra en hjelper, ikke fra 429
            'accounts/tests.py::RateLimitTests.test_per_username_limit_blocks_after_10',
            # «blokkert» satt fra `status_code in (403, 429)`
            'accounts/tests.py::RateLimitTests.test_per_ip_limit_protects_against_username_spraying',
            'accounts/tests_brukernavn.py::RateLimitNokkelTests.test_store_bokstaver_deler_botte_med_smaa',
            'accounts/tests_innlogging_herding.py::MfaRateLimitTests.test_egen_bruker_blir_ratelimited',
            'park/tests.py::GrenseneTests.test_taket_per_lenke',
            # serien sendes av `_statuser(kall, antall)`, ikke i testen selv
            'core/tests_ratelimit.py::RateLimitEndepunktTests.test_opprett_pasient_strupes',
        ):
            self.assertIn(kjent, sett)
        self.assertGreaterEqual(len(sett), 16)


class KlassifiseringenTests(SimpleTestCase):
    """Vakten prøvd mot oppdiktede tester, så den ikke måler noe annet enn den later som."""

    def _brudd(self, metode, klassebody=''):
        kilde = textwrap.dedent('''
            class T(TestCase):
            {klassebody}
                def test_x(self):
            {metode}
        ''').format(klassebody=textwrap.indent(textwrap.dedent(klassebody), '    '),
                    metode=textwrap.indent(textwrap.dedent(metode), '        '))
        return brudd_i_kilde(kilde)

    def test_haandtelt_serie_mot_429_er_brudd(self):
        self.assertTrue(self._brudd('''
            s = [c.post('/x/').status_code for _ in range(12)]
            self.assertIn(429, s)
        '''))

    def test_haandtelt_2x_pluss_1_er_ogsaa_brudd(self):
        """Riktig tall i dag, men ikke koblet til regelen."""
        self.assertTrue(self._brudd('''
            s = [c.post('/x/').status_code for _ in range(2 * 10 + 1)]
            self.assertIn(429, s)
        '''))

    def test_hjelperen_i_metoden_er_ok(self):
        self.assertFalse(self._brudd('''
            s = [c.post('/x/').status_code for _ in range(nok_til_a_bryte(10))]
            self.assertIn(429, s)
        '''))

    def test_hjelperen_i_et_klasseattributt_er_ok(self):
        self.assertFalse(self._brudd('''
            s = [c.post('/x/').status_code for _ in range(self.FORSOK)]
            self.assertIn(429, s)
        ''', klassebody='FORSOK = nok_til_a_bryte(10)'))

    def test_blokkert_fra_hjelper_er_brudd(self):
        self.assertTrue(self._brudd('''
            blokkert = False
            for _ in range(11):
                blokkert = blokkert or self._is_blocked(c.post('/x/'))
            self.assertTrue(blokkert)
        '''))

    def test_serie_gjennom_en_hjelper_er_brudd(self):
        kilde = textwrap.dedent('''
            def _statuser(kall, antall):
                return [kall().status_code for _ in range(antall)]

            class T(TestCase):
                def test_x(self):
                    self.assertIn(429, _statuser(lambda: c.post('/x/'), 12))
        ''')
        self.assertTrue(brudd_i_kilde(kilde))
        self.assertFalse(brudd_i_kilde(kilde.replace('12)', 'nok_til_a_bryte(10))')))

    def test_negativ_test_er_ikke_brudd(self):
        """Tester som krever at noe *ikke* strupes, skal ikke tvinges til hjelperen."""
        self.assertFalse(self._brudd('''
            for _ in range(70):
                self.assertNotEqual(c.get('/x/').status_code, 429)
            s = [c.get('/x/').status_code for _ in range(70)]
            self.assertNotIn(429, s)
        '''))

    def test_enkeltkall_uten_serie_er_ikke_brudd(self):
        """Et kall med strupingen mocket er ikke utsatt for vinduskanten."""
        self.assertFalse(self._brudd('''
            svar = c.post('/x/')
            self.assertEqual(svar.status_code, 429)
        '''))
