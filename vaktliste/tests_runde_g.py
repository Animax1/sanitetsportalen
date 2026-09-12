"""Andrés forbedringsliste 12. sep. 2026, vaktlistedelen.

«Flytt sett i drift inn under innstillinger. Ha noe visuelt som viser at
vaktlisten er i planlegging eller i drift. Kunne redigere mannskaper selv om
vi er i drift modus. Driftmodus og planleggingsmodus må logges i auditlog.»
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from audit.models import AuditLog
from patients.js_test_utils import (
    PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available, run_node)

from .tests_tilgang import TilgangsBasis


class DriftIAuditloggenTests(TilgangsBasis):
    def test_inn_og_ut_av_drift_gir_rader_med_hvem(self):
        AuditLog.objects.all().delete()
        res = self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        self.assertEqual(res.status_code, 200, res.content)
        rader = list(AuditLog.objects.filter(table_name='vaktliste_vaktliste', record_id=self.vl.pk)
                     .order_by('field_name'))
        felter = {r.field_name: (r.old_value, r.new_value, r.user_id) for r in rader}
        self.assertEqual(felter['status'][:2], ('planlegging', 'drift'))
        self.assertEqual(felter['status'][2], self.vaktleder.pk, 'hvem åpnet innsjekken')
        self.assertIn('satt_i_drift_at', felter)
        self.assertIn('satt_i_drift_av', felter)
        AuditLog.objects.all().delete()
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/stopp/')
        rad = AuditLog.objects.get(table_name='vaktliste_vaktliste', field_name='status')
        self.assertEqual((rad.old_value, rad.new_value), ('drift', 'planlegging'))


class DriftknappenBorIInnstillingerTests(SimpleTestCase):
    def test_knappen_staar_i_vinduet_ikke_i_vaktlinja(self):
        html = (Path(settings.BASE_DIR) / 'templates/vaktliste/index.html').read_text(encoding='utf-8')
        velger = html[html.index('class="vl-vaktvelger'):html.index('id="vaktliste-status"')]
        self.assertNotIn('id="vl-drift"', velger)
        modal = html[html.index('id="vaktModal"'):]
        for_lista = modal[modal.index('id="vakt-for-lista"'):modal.index('id="vakt-arkiv-bolk"')]
        self.assertIn('id="vl-drift"', for_lista, 'inne i bolken som gjelder én liste')


class StatusmerkeJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnStatus', 'tegnDriftknapp', 'iDrift', '_dag', '_kl', '_d')),
    )
    STUBB = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = self.STUBB + build_harness(self.HARNESS)

    def _kjor(self, i_drift, kan_skrive='true'):
        return run_node(self.harness, f"""
            const status = {{ innerHTML: '', className: '' }};
            const drift = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: (id) => ({{ 'vaktliste-status': status, 'vl-drift': drift }})[id] }};
            globalThis.kanSkriveAlt = () => {kan_skrive};
            globalThis.aktivListe = {{ vaktliste: {{ i_drift: {i_drift}, status_navn: {'"I drift"' if i_drift == 'true' else '"Planlegging"'},
              startet: '2026-09-12T08:00:00Z', planlagt_slutt: '2026-09-12T20:00:00Z' }} }};
            tegnStatus();
            console.log(status.className); console.log(status.innerHTML); console.log('---'); console.log(drift.innerHTML);
        """)

    def test_merket_sier_formen_med_ikon_og_fet(self):
        ut = self._kjor('true')
        klasse, merke = ut.split('\n')[:2]
        self.assertEqual(klasse, 'vl-status vl-drift')
        self.assertIn('<strong>I drift</strong>', merke)
        self.assertIn('bi-play-circle-fill', merke)
        ut = self._kjor('false')
        klasse, merke = ut.split('\n')[:2]
        self.assertEqual(klasse, 'vl-status vl-planlegging')
        self.assertIn('<strong>Planlegging</strong>', merke)

    def test_driftknappen_tegnes_med_forklaring_og_bare_for_den_som_kan(self):
        _, knapp = self._kjor('false').split('---')
        self.assertIn('data-arg="start"', knapp)
        self.assertIn('Sett i drift', knapp)
        self.assertIn('åpner innsjekken', knapp)
        _, knapp = self._kjor('true').split('---')
        self.assertIn('data-arg="stopp"', knapp)
        _, knapp = self._kjor('true', 'false').split('---')
        self.assertNotIn('data-action', knapp, 'uten skriv_full: ingen knapp')


class KnappefargerTests(SimpleTestCase):
    def test_outline_secondary_er_lys_paa_portalsidene(self):
        css = (Path(settings.BASE_DIR) / 'static/css/portal.css').read_text(encoding='utf-8')
        m = re.search(r'\.btn-outline-secondary\s*\{([^}]*)\}', css)
        self.assertIsNotNone(m)
        self.assertIn('var(--portal-text)', m.group(1))
        self.assertIn('var(--portal-border)', m.group(1))
