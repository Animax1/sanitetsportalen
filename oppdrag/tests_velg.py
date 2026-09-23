"""«Velg…» øverst i nedtrekkene, og ledig i enhetsvalget (23. sep. 2026).

André: «Ledetekst "Velg..." … på alle dropdown som ikke har lagret verdi …
Hvis man har valgt og lagret en verdi så må jo den så klart være selected …
Hvis obligatorisk felt så feilmelding om man lagrer med "Velg..." selected.»
Og: «Ledig i nedtrekkslista — når du skal velge enhet når du oppretter
oppdrag så kan du se hvem som er ledig.»

Reglene kjøres i node gjennom de ekte inngangene: `fyllProblemstillinger`,
`_varsleValg`/`varsleEnhet`, `_flyttValg`/`flyttOppdrag` og `mkEnhetsvalg`.
"""
import json

from django.test import SimpleTestCase

from patients.js_test_utils import (OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)


def _harness(*navn):
    return build_harness((
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (OPPDRAG_SENTRAL_JS, navn),
    ))


class VelgValgTests(SimpleTestCase):
    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_velg_er_valgt_bare_uten_lagret_verdi(self):
        ut = run_node(_harness(), "console.log(velgValg('')); console.log(velgValg('Fall'));").splitlines()
        self.assertEqual(ut[0], '<option value="" selected>Velg…</option>')
        self.assertEqual(ut[1], '<option value="">Velg…</option>')


class ProblemstillingEtterByttetTests(SimpleTestCase):
    """Nytt oppdrag: ingenting valgt gir «Velg…». *Var* det valgt noe, gjelder
    samme regel som i oppdragsvinduet — beholdes om den kan, ellers
    «Udefinert» (`services.problemstilling_etter_hastegrad`)."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = _harness('fyllProblemstillinger', 'problemstillingEtterBytte',
                                'problemstillingerFor')

    def _valgt(self, hastegrad, valgt):
        ut = run_node(self.harness, f"""
            globalThis.window = {{ OPPDRAG_PROBLEMSTILLINGER_FOR: {{
              Akutt: ['Udefinert', 'Fall', 'Transport'], Drift: ['Udefinert', 'Strøm', 'Transport'] }} }};
            const sel = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => sel }};
            fyllProblemstillinger('nytt', {json.dumps(hastegrad)}, {json.dumps(valgt)});
            const m = sel.innerHTML.match(/value="([^"]*)" selected/g);
            console.log(JSON.stringify([m, sel.innerHTML.startsWith('<option value=""')]));
        """).splitlines()[0]
        return json.loads(ut)

    def test_ingenting_valgt_gir_velg(self):
        self.assertEqual(self._valgt('Akutt', ''), [['value="" selected'], True])

    def test_valget_beholdes_naar_det_finnes(self):
        self.assertEqual(self._valgt('Drift', 'Transport'), [['value="Transport" selected'], True])

    def test_valget_som_ikke_finnes_blir_udefinert(self):
        self.assertEqual(self._valgt('Drift', 'Fall'), [['value="Udefinert" selected'], True])


class VarsleOgFlyttTests(SimpleTestCase):
    """Legg til og Flytt: «Velg…» først, og et klikk uten valg sier fra i
    stedet for å sende `enheter/0/`."""

    PRE = """
        globalThis.enheter = [{id: 10, navn: 'Amb 1', pa_vakt: true}, {id: 11, navn: 'Amb 2', pa_vakt: true},
                              {id: 12, navn: 'Amb 3', pa_vakt: true}];
        let kall = [];
        globalThis.apiFetch = async (url) => { kall.push(url); return { ok: true, json: async () => ({ status: 'ok' }) }; };
        globalThis.lastAlt = async () => {}; globalThis.visOppdrag = async () => {};
        globalThis.apentOppdragId = null;
        globalThis.bootstrap = { Modal: { getInstance: () => null } };
        const feilEl = (id) => ({ id, textContent: '', skjult: true,
          classList: { remove(k) { if (k === 'd-none') this.eier.skjult = false; }, add() {} } });
        const felter = {};
        for (const id of ['enheter-feil', 'flytt-feil']) { felter[id] = feilEl(id); felter[id].classList.eier = felter[id]; }
        globalThis.document = { getElementById: (id) => felter[id] || null };
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = _harness('_varsleValg', 'varsleEnhet', '_visEnhetsfeil', '_enhetshandling',
                                '_flyttValg', 'flyttFraEnheter', 'flyttOppdrag')

    def test_valgene_starter_paa_velg(self):
        ut = run_node(self.harness, self.PRE + """
            const o = { id: 7, enheter: [{enhet_id: 10, enhet_navn: 'Amb 1', status: 'fremme'},
                                         {enhet_id: 11, enhet_navn: 'Amb 2', status: 'fremme'}] };
            const v = _varsleValg(o), f = _flyttValg(o);
            console.log(v.match(/<select id="varsle-enhet"[^>]*>(<option[^>]*>[^<]*<\\/option>)/)[1]);
            console.log(f.match(/<select id="flytt-fra"[^>]*>(<option[^>]*>[^<]*<\\/option>)/)[1]);
            console.log(f.match(/<select id="flytt-enhet"[^>]*>(<option[^>]*>[^<]*<\\/option>)/)[1]);
        """).splitlines()
        self.assertEqual(ut[:3], ['<option value="" selected>Velg…</option>'] * 3)

    def test_legg_til_uten_valg_sier_fra_og_sender_ingenting(self):
        ut = run_node(self.harness, self.PRE + """
            felter['varsle-enhet'] = { value: '' };
            await varsleEnhet(7);
            console.log(JSON.stringify([felter['enheter-feil'].textContent, felter['enheter-feil'].skjult, kall]));
            felter['varsle-enhet'].value = '12';
            await varsleEnhet(7);
            console.log(JSON.stringify(kall));
        """).splitlines()
        self.assertEqual(json.loads(ut[0]), ['Velg en enhet å legge til.', False, []])
        self.assertEqual(json.loads(ut[1]), ['/oppdrag/api/oppdrag/7/enheter/12/'])

    def test_flytt_uten_fra_eller_til_sier_fra_og_sender_ingenting(self):
        ut = run_node(self.harness, self.PRE + """
            felter['flytt-fra'] = { value: '' }; felter['flytt-enhet'] = { value: '12' };
            await flyttOppdrag(7);
            console.log(JSON.stringify([felter['flytt-feil'].textContent, felter['flytt-feil'].skjult, kall]));
            felter['flytt-fra'].value = '10'; felter['flytt-enhet'].value = '';
            await flyttOppdrag(7);
            console.log(JSON.stringify([felter['flytt-feil'].textContent, kall]));
            delete felter['flytt-fra']; felter['flytt-enhet'].value = '';
            await flyttOppdrag(7);
            console.log(JSON.stringify([felter['flytt-feil'].textContent, kall]));
            felter['flytt-enhet'].value = '12';
            await flyttOppdrag(7);
            console.log(JSON.stringify(kall));
        """).splitlines()
        self.assertEqual(json.loads(ut[0]), ['Velg hvilken enhet oppdraget flyttes fra.', False, []])
        self.assertEqual(json.loads(ut[1]), ['Velg enheten oppdraget flyttes til.', []])
        self.assertEqual(json.loads(ut[2]), ['Velg enheten oppdraget flyttes til.', []],
                         'med én enhet på oppdraget finnes ingen fra-nedtrekk')
        self.assertEqual(json.loads(ut[3]), ['/oppdrag/api/oppdrag/7/flytt/'])


class LedigIEnhetsvalgetTests(SimpleTestCase):
    """«Når du skal velge enhet når du oppretter oppdrag så kan du se hvem
    som er ledig.» Statusen står ved navnet, og ledig er framhevet."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = _harness('mkEnhetsvalg', '_grupperEnheter', '_typeRekkefolge')

    def test_statusen_staar_ved_navnet_og_ledig_er_merket(self):
        html = run_node(self.harness, """
            globalThis.enheter = [
              {id: 1, navn: 'Amb 1', type: 1, pa_vakt: true, status: 'ledig', status_navn: 'Ledig'},
              {id: 2, navn: 'Amb 2', type: 1, pa_vakt: true, status: 'fremme', status_navn: 'Fremme'}];
            console.log(mkEnhetsvalg());
        """)
        rad1, rad2 = html.split('</label>')[:2]
        self.assertIn('nytt-enhet-status er-ledig', rad1)
        self.assertIn('>Ledig</span>', rad1)
        self.assertNotIn('er-ledig', rad2)
        self.assertIn('status-fremme', rad2)
        self.assertIn('>Fremme</span>', rad2)

    def test_statusen_escapes(self):
        html = run_node(self.harness, """
            globalThis.enheter = [{id: 1, navn: 'A', type: 1, pa_vakt: true,
                                   status: '"><img src=x>', status_navn: '<img src=y>'}];
            console.log(mkEnhetsvalg());
        """)
        self.assertNotIn('<img', html)
