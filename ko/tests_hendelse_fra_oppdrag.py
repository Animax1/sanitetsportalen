"""«Ny hendelse fra oppdraget» (20. okt. 2026).

André: «Det skjer at vi lager et oppdrag som man tror er et enkelt oppdrag, men så ser man
etterhvert at dette oppdraget må være en hendelse. Da er det fint at man på oppdraget kan ha en
shortcut for opprett hendelse, og da knyttes så klart dette oppdraget automatisk til hendelsen.
Men så bør det gjerne ikke være mulig å lage hendelse fra et oppdrag dersom oppdraget allerede
tilhører en annen hendelse.»

Tjenesten prøves gjennom endepunktet der porten står (`skriv_full` i begge modulene), og knyttingen
leses tilbake fra oppdraget og loggen — ikke fra returverdien.
"""
from __future__ import annotations

import json

from django.test import Client, SimpleTestCase, override_settings

from ko import services, systemlinjer
from ko.models import Hendelse, Logglinje
from patients.js_test_utils import JS_DIR, KO_JS, PORTAL_UTILS_JS, build_harness, run_node

from .tests_hendelser import _Grunnlag, _bruker, _gi

URL = '/ko/api/hendelser/ny/'


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HendelseFraOppdragTests(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.kari = _bruker('kari_fra')
        _gi(self.kari, 'ko', 'skriv_full')
        _gi(self.kari, 'oppdrag', 'skriv_full')
        self.klient = Client()
        self.klient.force_login(self.kari)
        self.oppdrag = self._oppdrag()

    def _ny(self, klient=None, **kropp):
        return (klient or self.klient).post(URL, json.dumps(
            {'tittel': 'Slagsmål', 'prioritet': 'rod', 'fra_oppdrag': self.oppdrag.pk} | kropp),
            content_type='application/json')

    def test_hendelsen_lages_og_oppdraget_knyttes(self):
        r = self._ny()
        self.assertEqual(r.status_code, 201, r.content)
        h = Hendelse.objects.get(pk=r.json()['data']['id'])
        self.oppdrag.refresh_from_db()
        self.assertEqual(self.oppdrag.hendelse_id, h.pk)
        self.assertTrue(Logglinje.objects.filter(
            hendelse=h, systemkode=systemlinjer.OPPDRAG_KNYTTET).exists(),
            'knyttingen står i hendelsens logg, som ved en vanlig knytting')
        self.assertEqual(r.json()['data']['antall_oppdrag'], 1)

    def test_oppdrag_i_en_hendelse_gir_ingen_ny_og_ikke_noe_nummer(self):
        """Valideringen kommer før nummeret trekkes: en avvist innsending skal ikke etterlate et
        hull i H-serien."""
        forrige = self._hendelse()
        services.knytt_oppdrag(self.oppdrag, forrige, bruker=self.kari)
        antall = Hendelse.objects.count()
        r = self._ny()
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn(services.hendelsesnr(forrige.hendelsesnummer), r.json()['message'])
        self.assertEqual(Hendelse.objects.count(), antall)
        self.oppdrag.refresh_from_db()
        self.assertEqual(self.oppdrag.hendelse_id, forrige.pk, 'står der det sto')
        neste = self._hendelse('Neste')
        self.assertEqual(neste.hendelsesnummer, forrige.hendelsesnummer + 1)

    def test_oppdrag_i_en_lukket_hendelse_gir_heller_ingen_ny(self):
        forrige = self._hendelse()
        services.knytt_oppdrag(self.oppdrag, forrige, bruker=self.kari)
        services.lukk_hendelse(forrige, bruker=self.kari, confirm=True)
        self.assertEqual(self._ny().status_code, 400)

    def test_uten_skrivetilgang_i_oppdrag_ingen_hendelse(self):
        bare_ko = _bruker('bare_ko')
        _gi(bare_ko, 'ko', 'skriv_full')
        _gi(bare_ko, 'oppdrag', 'les')
        k = Client()
        k.force_login(bare_ko)
        antall = Hendelse.objects.count()
        self.assertEqual(self._ny(klient=k).status_code, 403)
        self.assertEqual(Hendelse.objects.count(), antall)
        self.oppdrag.refresh_from_db()
        self.assertIsNone(self.oppdrag.hendelse_id)

    def test_uten_fra_oppdrag_kreves_ikke_oppdragstilgang(self):
        """Porten gjelder bare når et oppdrag skal røres — «Ny hendelse» ellers er KOs alene."""
        bare_ko = _bruker('bare_ko2')
        _gi(bare_ko, 'ko', 'skriv_full')
        k = Client()
        k.force_login(bare_ko)
        self.assertEqual(self._ny(klient=k, fra_oppdrag=None).status_code, 201)

    def test_tjenesten_avviser_oppdrag_i_en_annen_vakt(self):
        """Andre lag: viewet slipper ikke slike gjennom, men tjenesten er døra også for kode som
        kaller den direkte."""
        from core.models import Vakt
        from django.utils import timezone
        annen = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        type(self.oppdrag).objects.filter(pk=self.oppdrag.pk).update(vakt=annen)
        self.oppdrag.refresh_from_db()
        antall = Hendelse.objects.count()
        with self.assertRaises(services.Ugyldig):
            services.opprett_hendelse(self.vakt, 'X', bruker=self.kari, fra_oppdrag=self.oppdrag)
        self.assertEqual(Hendelse.objects.count(), antall, 'transaksjonen rullet hendelsen tilbake')

    def test_oppdrag_i_en_annen_vakt_er_404(self):
        from core.models import Vakt
        from django.utils import timezone
        annen = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        Oppdrag = type(self.oppdrag)
        Oppdrag.objects.filter(pk=self.oppdrag.pk).update(vakt=annen)
        self.assertEqual(self._ny().status_code, 404)


# ── Skjermen ─────────────────────────────────────────────────────────────────

OPPDRAG = {'id': 7, 'nummer': 45, 'hendelse_id': None, 'hendelse_nummer': None,
           'problemstilling': 'Fallskade', 'lokasjon_id': 3, 'lokasjon_navn': 'Hovedscene',
           'hastegrad': 'Akutt'}


class KnappenOgForslageneJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koKanSkrive', 'koHendelseValg', 'koApneHendelser', 'koTittelForOppdrag')),
            (JS_DIR / 'oppdrag-kort.js', ('hendelsesnr',)),
        ))

    def _kjor(self, kode, ko='skriv_full', oppdrag_skriv=True):
        pre = (f'const window = {{MODUL_TILGANG: {{ko: "{ko}"}}, '
               f'OPPDRAG_TILGANG: {{kanSkrive: {str(oppdrag_skriv).lower()}}}}};\n'
               'globalThis.koSorterHendelser = (l) => l; globalThis.koHendelser = new Map();\n')
        return run_node(self.harness, kode, preamble=pre).splitlines()[0]

    def test_knappen_bare_uten_hendelse_og_med_tilgang(self):
        ut = json.loads(self._kjor(f"""
            const o = {json.dumps(OPPDRAG)};
            console.log(JSON.stringify([
              koHendelseValg(o),
              koHendelseValg(Object.assign({{}}, o, {{hendelse_id: 2, hendelse_nummer: 14}})),
            ]));"""))
        uten, med = ut
        self.assertIn('data-action="koHendelseFraOppdrag" data-id="7"', uten)
        self.assertNotIn('koHendelseFraOppdrag', med, 'et oppdrag i en hendelse får ikke en til')
        for ko, oppdrag_skriv in (('les', True), ('skriv_full', False)):
            with self.subTest(ko=ko, oppdrag_skriv=oppdrag_skriv):
                self.assertNotIn('koHendelseFraOppdrag', self._kjor(
                    f'console.log(koHendelseValg({json.dumps(OPPDRAG)}));', ko=ko, oppdrag_skriv=oppdrag_skriv))

    def test_tittelforslaget(self):
        ut = json.loads(self._kjor(f"""
            const o = {json.dumps(OPPDRAG)};
            const m = (x) => Object.assign({{}}, o, x);
            console.log(JSON.stringify([
              koTittelForOppdrag(o), koTittelForOppdrag(m({{problemstilling: 'Udefinert'}})),
              koTittelForOppdrag(m({{lokasjon_navn: ''}})),
            ]));"""))
        self.assertEqual(ut, ['Fallskade — Hovedscene', 'Hovedscene', 'Fallskade'])


class FlytenJsTests(SimpleTestCase):
    """Gjennom `koHendelseFraOppdrag()`: detaljvinduet lukkes før skjemaet åpnes, skjemaet bærer
    oppdraget, og et oppdrag i en hendelse åpner ingenting."""

    def test_flyten(self):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koHendelseFraOppdrag', 'koTittelForOppdrag')),
            (JS_DIR / 'oppdrag-kort.js', ('oppdragsnr',)),
        ))
        kode = f"""
            const el = {{}};
            const felt = (id) => (el[id] ||= {{ value: '', innerHTML: '' }});
            const lyttere = {{}};
            const detalj = {{ classList: {{ contains: (k) => k === 'show' }},
                             addEventListener: (n, fn) => {{ lyttere[n] = fn; }} }};
            globalThis.document = {{ getElementById: (id) => (id === 'oppdragDetaljModal' ? detalj : felt(id)) }};
            const hendelser = [];
            globalThis.bootstrap = {{ Modal: {{ getOrCreateInstance: () => ({{ hide: () => hendelser.push('skjul detalj') }}) }} }};
            globalThis._koFyllSkjema = (h, linje, tittel) => {{ felt('ko-h-tittel').value = tittel; felt('ko-h-fra-oppdrag').value = ''; }};
            globalThis.koFyllLokasjoner = (id) => {{ felt('ko-h-lokasjon').value = String(id); }};
            globalThis.koVelgPrioritet = (p) => {{ felt('prio').value = p; }};
            globalThis.koHendelseModal = () => ({{ show: () => hendelser.push('vis skjema') }});
            globalThis.apentOppdrag = {json.dumps(OPPDRAG)};
            koHendelseFraOppdrag(7);
            const foer = hendelser.slice();
            lyttere['hidden.bs.modal']();
            const r = {{ foer, etter: hendelser.slice(), tittel: felt('ko-h-tittel').value,
                        fra: felt('ko-h-fra-oppdrag').value, lok: felt('ko-h-lokasjon').value,
                        prio: felt('prio').value, hode: felt('ko-hendelse-modal-tittel').innerHTML }};
            hendelser.length = 0;
            globalThis.apentOppdrag = Object.assign({{}}, apentOppdrag, {{ hendelse_id: 2 }});
            koHendelseFraOppdrag(7);
            r.iHendelse = hendelser.slice();
            console.log(JSON.stringify(r));
        """
        r = json.loads(run_node(harness, kode).splitlines()[0])
        self.assertEqual(r['foer'], ['skjul detalj'], 'skjemaet venter til detaljvinduet er lukket')
        self.assertEqual(r['etter'], ['skjul detalj', 'vis skjema'])
        self.assertEqual((r['tittel'], r['fra'], r['lok']), ('Fallskade — Hovedscene', '7', '3'))
        self.assertEqual(r['prio'], '', '«ingen er valgt på forhånd»: prioriteten foreslås ikke')
        self.assertIn('O45', r['hode'])
        self.assertEqual(r['iHendelse'], [], 'et oppdrag i en hendelse åpner ingenting')


class SkjemaetJsTests(SimpleTestCase):
    """`koLagreHendelse()` sender oppdraget, og `_koFyllSkjema()` tømmer det: uten tømmingen ville
    neste «Ny hendelse» — fra en linje eller fra ingenting — stille knyttet det forrige oppdraget."""

    def test_sendes_og_toemmes(self):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('_koFyllSkjema', 'koLagreHendelse', '_koSkjemaverdier')),
        ))
        kode = """
            const el = {};
            const nytt = () => ({ value: '', innerHTML: '', textContent: '', dataset: {}, checked: false,
              classList: { add() {}, remove() {}, toggle() {} }, closest() { return nytt(); } });
            globalThis.document = { getElementById: (id) => (el[id] ||= nytt()), querySelectorAll: () => [] };
            for (const f of ['koBeskrivelse', 'koFyllLagvalg', 'koFyllLokasjoner', 'koVelgPrioritet',
                             'koMelderAndreEndret', 'koHentLogg', 'koHentOppdragPaaNytt'])
              globalThis[f] = () => null;
            globalThis.koKlokke = () => ''; globalThis.koMittBrukernavn = () => 'kari';
            globalThis.koPrioritetValgt = () => true;
            globalThis.koHendelseModal = () => ({ hide() {} });
            globalThis.withSubmitGuard = async (id, fn) => fn();
            const sendt = [];
            globalThis._koHendelsehandling = async (sti, kropp) => { sendt.push(kropp);
              return { res: { ok: true, status: 201 }, data: { data: { id: 9 } } }; };
            _koFyllSkjema(null, null, 'Fallskade');
            el['ko-h-fra-oppdrag'].value = '7';
            await koLagreHendelse();
            _koFyllSkjema(null, null, '');
            await koLagreHendelse();
            console.log(JSON.stringify([sendt[0].fra_oppdrag, 'fra_oppdrag' in sendt[1]]));
        """
        ut = json.loads(run_node(harness, kode, preamble="let koValgtPrioritet = 'rod';\nlet koApenHendelseId = null;\n")
                        .splitlines()[0])
        self.assertEqual(ut, [7, False])
