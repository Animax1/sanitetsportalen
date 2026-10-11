"""Miljømerket og admins statusmelding (11. okt. 2026).

`core/miljo.py` og `core/statusmelding.py`. Testene går gjennom de ekte sidene —
innloggingen, portalen, pasientsiden, lagsiden — og gjennom bjellas ekte
polling i node, fordi det er der merket enten står eller ikke står.
"""
import json
import logging
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core import miljo as miljomodul
from core.models import AppSetting
from core.statusmelding import NOKKEL, StatusmeldingInnstillinger, aktiv
from patients.js_test_utils import JS_DIR, node_available, read_js, run_node

ROT = Path(settings.BASE_DIR)

#: Sider med egen <head> som ikke er portalsider. Tom med vilje — en ny side
#: uten merket skal bli rød, ikke havne her uten at noen har tenkt seg om.
UTEN_MERKE = {
    'templates/vaktliste/fil.html': 'Vaktlista som fil på e-post — et dokument, ikke en portalside',
}


class MiljoetTests(SimpleTestCase):

    def test_den_lukkede_lista(self):
        for verdi, (type_, vis, gyldig) in {
            'drift': ('drift', False, True),
            'test': ('test', True, True),
            'utvikling': ('utvikling', True, True),
            ' test ': ('test', True, True),
            '': ('ukjent', True, False),
            'production': ('ukjent', True, False),
            'staging': ('ukjent', True, False),
            'Drift': ('ukjent', True, False),
            'prodution': ('ukjent', True, False),
        }.items():
            with self.subTest(verdi=verdi):
                m = miljomodul.miljo(verdi)
                self.assertEqual((m['type'], m['vis'], m['gyldig']), (type_, vis, gyldig))

    def test_drift_har_verken_merke_fane_eller_epost(self):
        m = miljomodul.miljo('drift')
        self.assertEqual((m['merke'], m['fane'], m['epost']), ('', '', ''))

    def test_advarselen_ved_oppstart(self):
        logger = logging.getLogger('test.miljo')
        with override_settings(PORTAL_MILJO='staging'), self.assertLogs(logger, 'WARNING') as logg:
            miljomodul.advar_ved_ukjent(logger)
        self.assertIn("'staging'", logg.output[0])
        with override_settings(PORTAL_MILJO='test'), self.assertNoLogs(logger, 'WARNING'):
            miljomodul.advar_ved_ukjent(logger)

    def test_serverstatus_er_rod_bare_for_ukjent(self):
        from core.admin_status import _miljorad
        for verdi, ok in (('drift', True), ('test', True), ('utvikling', True), ('', False), ('prod', False)):
            with self.subTest(verdi=verdi), override_settings(PORTAL_MILJO=verdi):
                self.assertEqual(_miljorad()['ok'], ok)

    def test_epostens_emne(self):
        from core.mail_backends import _med_miljo
        for verdi, ventet in (('drift', 'Feil'), ('test', '[test] Feil'), ('utvikling', '[utvikling] Feil'),
                              ('', '[ukjent miljø] Feil')):
            with self.subTest(verdi=verdi), override_settings(PORTAL_MILJO=verdi):
                self.assertEqual(_med_miljo('Feil'), ventet)
        with override_settings(PORTAL_MILJO='test'):
            self.assertEqual(_med_miljo('[test] Feil'), '[test] Feil', 'ikke to ganger')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SideneTests(TestCase):
    """Merket på de ekte sidene, i alle fire tilstandene."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='kari_m', password='x', must_change_password=False)
        gi_standardtilgang(self.bruker, 'skriver')
        self.inne = Client()
        self.inne.force_login(self.bruker)

    def _sider(self):
        return {'innlogging': Client().get('/accounts/login/'),
                'portalen': self.inne.get('/'),
                'pasientsiden': self.inne.get('/pasienter/'),
                'lagsiden': Client().get('/lag/r/')}

    def test_drift_viser_ingenting(self):
        with override_settings(PORTAL_MILJO='drift'):
            for navn, svar in self._sider().items():
                with self.subTest(navn):
                    html = svar.content.decode()
                    self.assertEqual(svar.status_code, 200)
                    self.assertNotIn('class="miljomerke', html)
                    self.assertNotRegex(html, r'<title>\[')

    def test_hver_type_viser_sitt_merke_og_sin_fane(self):
        for verdi, merke, fane in (('test', 'TESTMILJØ', '[TEST] '), ('utvikling', 'UTVIKLING', '[UTV] '),
                                   ('staging', 'UKJENT MILJØ', '[?] ')):
            with override_settings(PORTAL_MILJO=verdi):
                for navn, svar in self._sider().items():
                    with self.subTest(verdi=verdi, side=navn):
                        html = svar.content.decode()
                        self.assertIn(merke, html)
                        self.assertIn('<title>' + fane, html)

    def test_innloggingen_forklarer_hva_merket_betyr(self):
        with override_settings(PORTAL_MILJO='test'):
            self.assertContains(Client().get('/accounts/login/'), 'Ingenting du registrerer her er ekte')

    def test_js_faar_prefikset_til_titler_den_setter_selv(self):
        with override_settings(PORTAL_MILJO='test'):
            self.assertContains(self.inne.get('/'), 'window.PORTAL_FANEPREFIKS = "[TEST] ";')


class HverSideHarMerketTests(SimpleTestCase):
    """Som `_ikoner.html`: en ny side med egen <head> skal ikke kunne lages uten."""

    def _maler(self):
        for sti in sorted(ROT.glob('**/templates/**/*.html')):
            rel = sti.relative_to(ROT).as_posix()
            if '.venv' in sti.parts or 'site-packages' in sti.parts:
                continue
            tekst = sti.read_text(encoding='utf-8')
            if '<title>' in tekst:
                yield rel, tekst

    def test_tittel_og_merke(self):
        funn = []
        for rel, tekst in self._maler():
            if rel in UTEN_MERKE:
                continue
            if not re.search(r'<title>\{\{ miljo\.fane \}\}', tekst):
                funn.append(f'{rel}: <title> uten {{{{ miljo.fane }}}}')
            if 'partials/_statusmerke.html' not in tekst:
                funn.append(f'{rel}: tar ikke med partials/_statusmerke.html')
        self.assertEqual(funn, [])

    def test_unntakene_finnes(self):
        for rel in UTEN_MERKE:
            self.assertTrue((ROT / rel).exists(), rel)


class StatusmeldingenTests(TestCase):

    def _sett(self, **data):
        AppSetting.set(NOKKEL, json.dumps(data))

    def test_ingen_melding_uten_tekst_eller_med_ukjent_farge(self):
        self.assertIsNone(aktiv())
        for data in ({'tekst': '', 'farge': 'rod'}, {'tekst': 'Hei', 'farge': 'lilla'},
                     {'tekst': 'Hei'}):
            with self.subTest(data=data):
                self._sett(**data)
                self.assertIsNone(aktiv())
        AppSetting.set(NOKKEL, '{ikke json')
        self.assertIsNone(aktiv(), 'en verdi skrevet for hånd skal ikke ta ned toppmenyen')

    def test_vis_til(self):
        til = timezone.now() + timedelta(hours=1)
        self._sett(tekst='Vedlikehold', farge='oransje', til=til.isoformat())
        self.assertEqual(aktiv(), {'tekst': 'Vedlikehold', 'farge': 'oransje'})
        self.assertIsNone(aktiv(til), 'ved grensa er den borte')
        self.assertIsNotNone(aktiv(til - timedelta(seconds=1)))

    def test_valideringen(self):
        from django.core.exceptions import ValidationError
        h = StatusmeldingInnstillinger()
        self.assertEqual(h.valider({}), {}, 'fraværende er «behold»')
        self.assertEqual(h.valider({'statusmelding_tekst': '  '}), {'data': None}, 'tom er «ingen»')
        for post in ({'statusmelding_tekst': 'x' * 41, 'statusmelding_farge': 'rod'},
                     {'statusmelding_tekst': 'Hei', 'statusmelding_farge': 'lilla'},
                     {'statusmelding_tekst': 'Hei', 'statusmelding_farge': 'rod', 'statusmelding_til': 'i morgen'},
                     {'statusmelding_tekst': 'Hei', 'statusmelding_farge': 'rod',
                      'statusmelding_til': '2020-01-01T10:00'}):
            with self.subTest(post=post), self.assertRaises(ValidationError):
                h.valider(post)
        fram = (timezone.localtime() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        h.lagre(h.valider({'statusmelding_tekst': 'x' * 40, 'statusmelding_farge': 'gul',
                           'statusmelding_til': fram}))
        self.assertEqual(aktiv()['farge'], 'gul')
        h.lagre(h.valider({'statusmelding_tekst': ''}))
        self.assertIsNone(aktiv())

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_gjennom_siden_og_bjella_og_escapet(self):
        bruker = CustomUser.objects.create_user(username='ola_m', password='x', must_change_password=False)
        gi_standardtilgang(bruker, 'skriver')
        klient = Client()
        klient.force_login(bruker)
        html = klient.get('/').content.decode()
        self.assertRegex(html, r'id="portal-statusmelding"[^>]*hidden', 'elementet står, skjult, for bjella')
        self._sett(tekst='<b>Bruk papir</b>', farge='rod')
        html = klient.get('/').content.decode()
        self.assertIn('&lt;b&gt;Bruk papir&lt;/b&gt;', html)
        self.assertNotIn('<b>Bruk papir</b>', html)
        self.assertIn('statusmelding-rod', html)
        self.assertEqual(klient.get('/api/varsler/ulest-antall/').json()['statusmelding'],
                         {'tekst': '<b>Bruk papir</b>', 'farge': 'rod'})

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_admin_setter_den_paa_innstillingssiden(self):
        admin = CustomUser.objects.create_user(username='adm_m', password='x', role='admin',
                                               must_change_password=False)
        klient = Client()
        klient.force_login(admin)
        self.assertContains(klient.get('/portal-admin/innstillinger/'), 'name="statusmelding_tekst"')
        svar = klient.post('/portal-admin/innstillinger/', {
            'session_timeout_hours': '8', 'statusmelding_tekst': 'Vakt pågår',
            'statusmelding_farge': 'gronn', 'statusmelding_til': ''})
        self.assertEqual(svar.status_code, 302)
        self.assertEqual(aktiv(), {'tekst': 'Vakt pågår', 'farge': 'gronn'})


class BjellaTegnerMeldingenTests(SimpleTestCase):
    """Hele `notifications.js` i node: pollingen er den ekte inngangen."""

    OPPSETT = """
    const el = { hidden: true, textContent: '', title: '', className: 'statusmelding' };
    const badge = { textContent: '', style: {} };
    globalThis.document = { visibilityState: 'visible',
      getElementById: (id) => ({ 'portal-statusmelding': el, 'notification-badge': badge })[id] || null,
      querySelector: () => null, addEventListener() {} };
    globalThis.window = globalThis;
    let tikk = null; globalThis.setInterval = (fn) => { tikk = fn; return 1; };
    let svar = {};
    globalThis.fetch = async () => ({ ok: true, json: async () => svar });
    const vis = () => ({ hidden: el.hidden, tekst: el.textContent, klasse: el.className });
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_meldingen_kommer_endres_og_forsvinner(self):
        kode = """
          (async () => {
            const ut = [];
            svar = { unread: 0, statusmelding: { tekst: '<b>Papir</b>', farge: 'rod' } };
            await tikk(); ut.push(vis());
            svar = { unread: 0 };                       // eldre server: står urørt
            await tikk(); ut.push(vis());
            svar = { unread: 0, statusmelding: { tekst: 'Hei', farge: 'lilla' } };
            await tikk(); ut.push(vis());               // ukjent farge: ingen melding
            svar = { unread: 0, statusmelding: null };
            await tikk(); ut.push(vis());
            console.log(JSON.stringify(ut));
          })();
        """
        ut = run_node(read_js(JS_DIR / 'notifications.js'), kode, preamble=self.OPPSETT)
        (rader,) = [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']
        self.assertEqual(rader[0], {'hidden': False, 'tekst': '<b>Papir</b>',
                                    'klasse': 'statusmelding statusmelding-rod'})
        self.assertEqual(rader[1], rader[0])
        self.assertEqual(rader[2], {'hidden': True, 'tekst': '', 'klasse': 'statusmelding'})
        self.assertEqual(rader[3], {'hidden': True, 'tekst': '', 'klasse': 'statusmelding'})


class FanetittelenTests(SimpleTestCase):

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_prefikset_og_uten(self):
        from patients.js_test_utils import PORTAL_UTILS_JS, build_harness
        ut = run_node(build_harness(((PORTAL_UTILS_JS, ('fanetittel',)),)), """
            const uten = fanetittel('Logg · KO');
            globalThis.PORTAL_FANEPREFIKS = '[TEST] ';
            console.log(JSON.stringify([uten, fanetittel('Logg · KO')]));
        """)
        self.assertEqual(json.loads(ut.splitlines()[0]), ['Logg · KO', '[TEST] Logg · KO'])


class KoVinduetForSegTests(SimpleTestCase):
    """`koTegnEgetVindu()` i `ko-layout.js` setter fanetittelen selv — gjennom
    `fanetittel()`, ellers står «[TEST]» bare til første vindu åpnes."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_tittelen_baerer_miljoet(self):
        from patients.js_test_utils import KO_JS, PORTAL_UTILS_JS, build_harness
        harness = build_harness(((PORTAL_UTILS_JS, ('fanetittel',)), (KO_JS, ('koTegnEgetVindu',))))
        ut = run_node(harness, """
            globalThis.PORTAL_FANEPREFIKS = '[TEST] ';
            const node = () => ({ style: {}, classList: { add() {}, remove() {}, toggle() {} },
                                  insertBefore() {} });
            const rad = node(); const vindu = node();
            globalThis.KO_VINDUSNAVN = { logg: 'Logg' };
            globalThis.koVinduElement = () => vindu;
            globalThis.document = { title: '', body: node(),
              getElementById: (id) => (id === 'ko-rad-1' ? rad : null),
              querySelectorAll: () => [] };
            koTegnEgetVindu('logg');
            console.log(document.title);
        """)
        self.assertEqual(ut.splitlines()[0], '[TEST] Logg · KO')
