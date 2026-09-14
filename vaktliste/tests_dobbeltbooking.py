"""Nedtrekket tilbyr ikke en person som alt står på plassen (14. sep. 2026).

**Buggen André meldte fra staging:**

    PUT /vaktliste/api/vaktposter/88/  →  400 (Bad Request)
    endreVaktpost @ vaktliste-offline.js

Årsaken: `_fyllValgFor()` listet **alle** i mannskapsregisteret i nedtrekket for
en ledig plass. Databasen har en unik-skranke på `(ressurs, mannskap, fra_tid)`,
så valgte man en som alt sto på samme ressurs til samme starttid, svarte
serveren 400 «Personen står allerede på denne ressursen fra dette tidspunktet».

Serveren gjorde altså riktig. Feilen var at grensesnittet **tilbød et valg som
ikke kunne gjennomføres** — stikk i strid med portalens egen regel: «en knapp
som fører til en vegg er verre enn ingen knapp».

Regelen ligger i `opptattPaaPlassen()` og ikke som en `filter` inne i byggeren,
av samme grunn som `klikkSkalKjore()`: en regel som ikke lar seg kalle, lar seg
ikke prøve.
"""
import json

from django.test import SimpleTestCase

from patients.js_test_utils import (
    VAKTLISTE_JS, build_harness, node_available, run_node,
)


class OpptattPaaPlassenTests(SimpleTestCase):

    HARNESS = ((VAKTLISTE_JS, ('opptattPaaPlassen',)),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    #: Fire rader på to ressurser. Kari står på ressurs 1 kl. 20:00.
    FORSPILL = '''
    const poster = [
      { id: 1, ressurs_id: 1, mannskap_id: 10, fra_tid: '2026-09-18T20:00:00+02:00' },
      { id: 2, ressurs_id: 1, mannskap_id: null, fra_tid: '2026-09-18T20:00:00+02:00' },
      { id: 3, ressurs_id: 2, mannskap_id: 11, fra_tid: '2026-09-18T20:00:00+02:00' },
      { id: 4, ressurs_id: 1, mannskap_id: 12, fra_tid: '2026-09-19T08:00:00+02:00' },
    ];
    const plassen = { id: 2, ressurs_id: 1, fra_tid: '2026-09-18T20:00:00+02:00' };
    const ut = (s) => console.log(JSON.stringify([...s].sort()));
    '''

    def _kjor(self, snippet):
        return json.loads(
            run_node(self.harness, self.FORSPILL + snippet).strip().splitlines()[0])

    def test_den_som_alt_staar_paa_ressursen_er_opptatt(self):
        """Kjernen: Kari (10) står på ressurs 1 kl. 20:00 og skal ikke tilbys
        på en annen ledig plass på samme bil til samme tid."""
        self.assertEqual(self._kjor('ut(opptattPaaPlassen(plassen, poster));'), [10])

    def test_annen_ressurs_sperrer_ikke(self):
        """Skranken er per ressurs. Å stå på KO kl. 20:00 hindrer ikke en plass
        på bilen — det er overlapp, og det er en annen sak (se TODO)."""
        self.assertNotIn(11, self._kjor('ut(opptattPaaPlassen(plassen, poster));'))

    def test_annen_starttid_sperrer_ikke(self):
        """Skranken er per starttid. Samme bil dagen etter er en annen rad."""
        self.assertNotIn(12, self._kjor('ut(opptattPaaPlassen(plassen, poster));'))

    def test_ledige_plasser_sperrer_ingen(self):
        """En rad uten person bærer ingen `mannskap_id`, og `null` i settet
        ville filtrert bort alt — nedtrekket hadde blitt tomt."""
        self.assertEqual(
            self._kjor('ut(opptattPaaPlassen(plassen, poster));'), [10],
            'kun Kari skal være opptatt; `null` skal ikke med')

    def test_raden_selv_teller_ikke(self):
        """Ser man på raden Kari alt står på, skal hun ikke være «opptatt» av
        seg selv — ellers forsvinner hun fra sitt eget nedtrekk."""
        self.assertEqual(
            self._kjor('''
              const egen = { id: 1, ressurs_id: 1, fra_tid: '2026-09-18T20:00:00+02:00' };
              ut(opptattPaaPlassen(egen, poster));
            '''), [])

    def test_tom_liste_gir_tomt_sett(self):
        """Første plass på en ny ressurs: ingen er opptatt, og funksjonen skal
        ikke kaste på `undefined`."""
        self.assertEqual(self._kjor('ut(opptattPaaPlassen(plassen, []));'), [])
        self.assertEqual(self._kjor('ut(opptattPaaPlassen(plassen, undefined));'), [])


class FeilbanneretSesTests(SimpleTestCase):
    """**Andre halvdel av samme melding:** «Jeg fikk feilen i konsoll på f12,
    så ingenting i nettleseren ellers.»

    `endreVaktpost()` kalte `visPanelfeil()` som den skulle, og `#vl-feil` sto
    i malen. Men banneret ligger rett over `#vl-panel`, altså øverst på sida,
    mens nedtrekket som ble avvist kan stå tretti rader ned i et regneark som
    ruller. Meldingen ble skrevet — bare utenfor skjermen.

    En feilmelding ingen ser er verre enn ingen feilmelding: brukeren tror
    lagringen gikk igjennom, og raden ruller tilbake uten forklaring.
    """

    HARNESS = ((VAKTLISTE_JS, ('visPanelfeil', 'rullTilFeil')),)

    #: Minimalt DOM: ett element som teller kall og husker klassene sine.
    PREAMBLE = '''
    const kall = [];
    const banner = {
      textContent: '',
      classList: {
        satt: new Set(['d-none']),
        remove(k) { this.satt.delete(k); },
        add(k) { this.satt.add(k); },
      },
      scrollIntoView(opts) { kall.push(opts); },
    };
    globalThis.banner = banner;
    globalThis.kall = kall;
    globalThis.finnes = true;
    globalThis.document = { getElementById: (id) => (finnes && id === 'vl-feil' ? banner : null) };
    '''

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, snippet):
        return run_node(self.harness, snippet, preamble=self.PREAMBLE)

    def test_meldingen_rulles_inn_i_bildet(self):
        """Kjernen: å vise banneret skal også bringe det fram."""
        self._kjor('''
          visPanelfeil('Personen står allerede på denne ressursen.');
          assert(banner.textContent.includes('allerede'), 'meldingen skrives');
          assert(!banner.classList.satt.has('d-none'), 'banneret vises');
          assert(kall.length === 1, 'rullingen skjedde: ' + kall.length);
        ''')

    def test_ruller_minst_mulig(self):
        """`block: 'nearest'` er valgt med vilje: står banneret alt i bildet,
        skal sida ikke hoppe. `'start'` ville rykket til toppen hver gang."""
        self._kjor('''
          visPanelfeil('nei');
          assert(kall[0] && kall[0].block === 'nearest', 'block: ' + JSON.stringify(kall[0]));
        ''')

    def test_uten_scrollIntoView_kastes_det_ikke(self):
        """En nettleser uten metoden skal fortsatt få meldingen — rullingen er
        en forbedring, ikke en forutsetning."""
        self._kjor('''
          delete banner.scrollIntoView;
          visPanelfeil('nei');
          assert(banner.textContent === 'nei', 'meldingen skrives likevel');
          assert(rullTilFeil(banner) === false, 'rullingen melder fra at den ikke gikk');
        ''')

    def test_uten_banner_i_malen_kastes_det_ikke(self):
        """Malene uten `#vl-feil` (utskriftsarket) skal ikke dø på en feil."""
        self._kjor('''
          finnes = false;
          visPanelfeil('nei');
          assert(kall.length === 0, 'ingen rulling uten element');
        ''')
