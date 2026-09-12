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

from .signals import SKJULT
from .test_helpers import LAG, gruppe
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


class VaktlinjaPaaTelefonTests(SimpleTestCase):
    """Del 3 (12. sep. 2026): «drift ikonet i vaktlister i planlegging delen
    går litt utenfor på iphone og alle korps nedtrekksfeltet blir flyttet på
    sær plass i horisontal visning på ios.» Statusmerket er `nowrap` på
    skjermer med plass; under 992 px får spennet bryte, formen står på én
    linje, og spaceren tar hele linja så knappene alltid står sist."""

    def _mobilblokk(self):
        css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'vaktliste.css').read_text(encoding='utf-8')
        start = css.index('@media (max-width: 991.98px) {')
        return css[start:css.index('\n}\n', start)]

    def test_statusmerket_faar_bryte_men_formen_staar_paa_en_linje(self):
        blokk = self._mobilblokk()
        m = re.search(r'\.vl-status \{([^}]*)\}', blokk)
        self.assertIsNotNone(m)
        self.assertIn('white-space: normal', m.group(1))
        self.assertIn('max-width: 100%', m.group(1))
        m = re.search(r'\.vl-status strong \{([^}]*)\}', blokk)
        self.assertIn('white-space: nowrap', m.group(1))

    def test_knappene_staar_sist_paa_egen_linje(self):
        blokk = self._mobilblokk()
        m = re.search(r'\.vl-vaktvelger \.flex-grow-1 \{([^}]*)\}', blokk)
        self.assertIsNotNone(m, 'spaceren foran knappene må ta hele linja')
        self.assertIn('flex-basis: 100%', m.group(1))
        m = re.search(r'\.vl-korpsvalg \{([^}]*)\}', blokk)
        self.assertIn('margin-left: 0', m.group(1))
        m = re.search(r'\.vl-vaktvelger #vaktliste-velger \{([^}]*)\}', blokk)
        self.assertIn('max-width: none', m.group(1))


class SkiftOgStemplerIAuditloggenTests(TilgangsBasis):
    """«Ønsker dette for å få logget det meste» (André, 12. sep. 2026):
    skift, ressurser og — først og fremst — møtt/av vakt-stemplene."""

    def setUp(self):
        super().setUp()
        AuditLog.objects.all().delete()

    def _skift(self):
        from datetime import timedelta
        from .models import Vaktpost
        return Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))

    def _rader(self, tabell, **filter):
        return list(AuditLog.objects.filter(table_name=tabell, **filter).order_by('pk'))

    def test_stemplene_logges_med_hvem(self):
        self.c_vl.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/drift/start/')
        vp = self._skift()
        AuditLog.objects.all().delete()
        res = self.c_vl.post(f'/vaktliste/api/vaktposter/{vp.pk}/stempling/mott/')
        self.assertEqual(res.status_code, 200, res.content)
        rader = self._rader('vaktliste_vaktpost', record_id=vp.pk, action='UPDATE')
        self.assertEqual([r.field_name for r in rader], ['mott_at'])
        self.assertEqual(rader[0].old_value, '')
        self.assertTrue(rader[0].new_value)
        self.assertEqual(rader[0].user_id, self.vaktleder.pk, 'hvem stemplet')
        self.assertEqual(rader[0].app_label, 'vaktliste')
        self.c_vl.post(f'/vaktliste/api/vaktposter/{vp.pk}/stempling/av_vakt/')
        self.c_vl.post(f'/vaktliste/api/vaktposter/{vp.pk}/stempling/angre_av_vakt/')
        felter = [r.field_name for r in self._rader('vaktliste_vaktpost', record_id=vp.pk, action='UPDATE')]
        self.assertEqual(felter, ['mott_at', 'av_vakt_at', 'av_vakt_at'], 'angring er også en endring')

    def test_skift_opprettes_endres_og_slettes_med_spor(self):
        res = self.c_vl.post(
            f'/vaktliste/api/ressurser/{self.res_hgsd.pk}/vaktposter/',
            data={'mannskap_id': self.p_hgsd.pk, 'fra_tid': self._iso(0), 'til_tid': self._iso(8)},
            content_type='application/json')
        self.assertEqual(res.status_code, 201, res.content)
        pk = res.json()['data']['id']
        opprettet = self._rader('vaktliste_vaktpost', record_id=pk, action='CREATE')
        self.assertEqual(len(opprettet), 1)
        self.assertIn('Kari på Lag HGSD', opprettet[0].new_value)
        self.assertRegex(opprettet[0].new_value, r'\d\d\.\d\d \d\d:\d\d–\d\d\.\d\d \d\d:\d\d', 'tidene står i raden')

        res = self.c_vl.put(f'/vaktliste/api/vaktposter/{pk}/',
                            data={'til_tid': self._iso(12), 'merknad': 'syk, gikk hjem'},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        endret = {r.field_name: r for r in self._rader('vaktliste_vaktpost', record_id=pk, action='UPDATE')}
        self.assertIn('til_tid', endret)
        self.assertEqual((endret['merknad'].old_value, endret['merknad'].new_value), (SKJULT, SKJULT),
                         'merknaden er fritekst: logges som endret, uten verdier')

        res = self.c_vl.delete(f'/vaktliste/api/vaktposter/{pk}/', data='{"confirm": true}',
                               content_type='application/json')
        self.assertIn(res.status_code, (200, 204), res.content)
        slettet = self._rader('vaktliste_vaktpost', record_id=pk, action='DELETE')
        self.assertEqual(len(slettet), 1)
        self.assertIn('Kari på Lag HGSD', slettet[0].old_value)

    def test_ressurs_logges_og_sletting_tar_skiftene_med_spor(self):
        res = self.c_leder.post(
            f'/vaktliste/api/vaktlister/{self.vl.pk}/ressurser/',
            data={'navn': 'Bil 2', 'gruppe_id': gruppe(LAG).pk, 'korps_id': self.hgsd.pk},
            content_type='application/json')
        self.assertEqual(res.status_code, 201, res.content)
        pk = res.json()['data']['id']
        opprettet = self._rader('vaktliste_ressurs', record_id=pk, action='CREATE')
        self.assertEqual(len(opprettet), 1)
        self.assertIn('Bil 2', opprettet[0].new_value)

        res = self.c_leder.put(f'/vaktliste/api/ressurser/{pk}/', data={'korps_id': self.karmoy.pk},
                            content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        endret = {r.field_name: (r.old_value, r.new_value)
                  for r in self._rader('vaktliste_ressurs', record_id=pk, action='UPDATE')}
        self.assertEqual(endret.get('korps'), ('Haugesund', 'Karmøy'))

        vp = self._skift()
        AuditLog.objects.all().delete()
        res = self.c_leder.delete(f'/vaktliste/api/ressurser/{self.res_hgsd.pk}/', data='{"confirm": true}',
                                  content_type='application/json')
        self.assertIn(res.status_code, (200, 204), res.content)
        self.assertEqual(len(self._rader('vaktliste_ressurs', record_id=self.res_hgsd.pk, action='DELETE')), 1)
        skift = self._rader('vaktliste_vaktpost', record_id=vp.pk, action='DELETE')
        self.assertEqual(len(skift), 1, 'CASCADE-slettingen av skiftet har eget spor')
        self.assertEqual(skift[0].user_id, self.leder.pk)

    def test_kopiert_oppsett_logges(self):
        from . import services
        ny = services.opprett_planlagt_vakt('Neste')
        AuditLog.objects.all().delete()
        self.assertEqual(services.kopier_oppsett(self.vl, ny), 3)
        self.assertEqual(AuditLog.objects.filter(table_name='vaktliste_ressurs', action='CREATE').count(), 3)
