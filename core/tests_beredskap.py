"""Beredskapstrinnene og driftsmodusen på server-status (24. sep. 2026).

Tersklene sto skrevet to steder — runbook §2 og hurtigreferansen på
dashbordet — og begge regnet fra 1 worker, mens vakt-modus starter på 2
(André: «før vakten skal starte spinner vi opp redis og 2 workers og 4
tråder», og Railway Pro på vakt). I tillegg farget dashbordets egen regel
300–500 ms grønt, der runbooken sa gult. Nå er det én liste,
`BEREDSKAPSTRINN`, og runbooken holdes i takt av en test.

Tjenestelaget prøves tungt: et feil trinn er et feil tiltak midt i en vakt.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser

from .admin_status import (BEREDSKAPSTRINN, KRITISK, TRADER_VED_VENTING, TRAADREGEL, VAKTMODUS,
                           beredskapsnivaa, driftsmodus, metrikkilde)

RUNBOOK = Path(settings.BASE_DIR) / 'docs' / 'RUNBOOK_VAKT.md'


class BeredskapsnivaaTests(SimpleTestCase):

    def _nivaa(self, p95, feil=0):
        return beredskapsnivaa(p95, feil)['nivaa']

    def test_grensene_paa_p95(self):
        for p95, nivaa in ((0, 'gronn'), (299.9, 'gronn'), (300, 'gul'), (499.9, 'gul'), (500, 'oransje'),
                           (999.9, 'oransje'), (1000, 'rod'), (5000, 'rod')):
            with self.subTest(p95=p95):
                self.assertEqual(self._nivaa(p95), nivaa)

    def test_5xx_alene_gir_oransje_og_roedt(self):
        """«eller 1–2 5xx» / «eller ≥ 3 5xx» — en rask server som svarer
        500 er ikke grønn."""
        self.assertEqual([self._nivaa(10, n) for n in (0, 1, 2, 3, 40)],
                         ['gronn', 'oransje', 'oransje', 'rod', 'rod'])
        self.assertEqual(self._nivaa(1200, 1), 'rod', 'det høyeste av de to gjelder')

    def test_faa_maalinger_sies_men_5xx_er_5xx(self):
        """Tre forespørsler og én treg ga «Oransje» på dashbordet."""
        from .admin_status import FA_MAALINGER
        tynt = beredskapsnivaa(700, 0, 3)
        self.assertEqual((tynt['nivaa'], tynt['fa_maalinger']), ('oransje', True), 'trinnet står')
        self.assertFalse(beredskapsnivaa(700, 0, FA_MAALINGER)['fa_maalinger'])
        self.assertTrue(beredskapsnivaa(700, 0, FA_MAALINGER - 1)['fa_maalinger'])
        self.assertFalse(beredskapsnivaa(10, 1, 3)['fa_maalinger'], 'en 500 er ikke tynn')
        self.assertFalse(beredskapsnivaa(700, 0)['fa_maalinger'], 'ukjent antall er ikke få')

    def test_ingen_trafikk_er_groent(self):
        self.assertEqual(self._nivaa(None, None), 'gronn')

    def test_tiltakene_regnes_fra_vakt_modus(self):
        """Oransje og rødt skal øke **forbi** grunnlinja — et tiltak som alt
        er gjort, er ikke et tiltak."""
        workers = [t['workers'] for t in BEREDSKAPSTRINN if t['workers'] is not None]
        self.assertTrue(workers)
        self.assertTrue(all(w > VAKTMODUS['workers'] for w in workers), workers)
        self.assertEqual(workers, sorted(workers))
        self.assertEqual([t['p95_fra'] for t in BEREDSKAPSTRINN],
                         sorted(t['p95_fra'] for t in BEREDSKAPSTRINN))


class DriftsmodusTests(SimpleTestCase):

    REDIS_OK = {'backend': 'redis', 'healthy': True}

    def test_de_fire_tilstandene(self):
        self.assertEqual(driftsmodus({'workers': '2'}, self.REDIS_OK)['modus'], 'vakt')
        self.assertEqual(driftsmodus({'workers': '1 (default)'}, {'backend': 'locmem', 'healthy': True})['modus'],
                         'lavkostnad')
        self.assertEqual(driftsmodus({'workers': '1'}, self.REDIS_OK)['modus'], 'halvveis')
        feil = driftsmodus({'workers': '2'}, {'backend': 'locmem', 'healthy': True})
        self.assertEqual((feil['modus'], feil['ok']), ('feil', False))

    def test_redis_som_ikke_svarer_er_ikke_redis(self):
        self.assertEqual(driftsmodus({'workers': '3'}, {'backend': 'redis', 'healthy': False})['modus'], 'feil')

    def test_worker_tallet_leses_robust(self):
        self.assertEqual(driftsmodus({'workers': 'tull'}, {'backend': 'locmem', 'healthy': True})['modus'],
                         'lavkostnad')
        self.assertEqual(driftsmodus(None, None)['modus'], 'lavkostnad')


class MetrikkildeTests(SimpleTestCase):

    def test_samlet_i_redis_eller_bare_denne_workeren(self):
        self.assertEqual(metrikkilde({'source': 'redis', 'unique_workers': 2}, {'workers': '2'})['tekst'],
                         'Samlet fra 2 workers')
        lokal = metrikkilde({'source': 'local'}, {'workers': '2'})
        self.assertFalse(lokal['ok'], 'med to workers og lokale tall ser man halve appen')
        self.assertTrue(metrikkilde({'source': 'local'}, {'workers': '1'})['ok'])


class BeredskapstrinneneIRunbookenTests(SimpleTestCase):
    """Runbook §2 og dashbordets tabell er samme liste. Leter i §2-tabellen
    etter én rad per trinn, med trinnets terskel og — der tiltaket er flere
    workers — `WEB_WORKERS=N`."""

    def _seksjon2(self):
        tekst = RUNBOOK.read_text(encoding='utf-8')
        m = re.search(r'^## 2\. .*?(?=^## 3\. )', tekst, re.S | re.M)
        self.assertIsNotNone(m, 'fant ikke §2 i runbooken')
        return m.group(0)

    def test_hvert_trinn_har_sin_rad(self):
        rader = [linje for linje in self._seksjon2().splitlines() if linje.startswith('| **')]
        navn = [re.match(r'\| \*\*([^*]+)\*\*', r).group(1) for r in rader]
        self.assertEqual(navn, [t['navn'] for t in BEREDSKAPSTRINN] + [KRITISK['navn']])
        for trinn, rad in zip(BEREDSKAPSTRINN, rader):
            with self.subTest(trinn=trinn['navn']):
                self.assertIn(trinn['terskel'], rad)
                if trinn['workers'] is not None:
                    self.assertIn(f"`WEB_WORKERS={trinn['workers']}`", rad)

    def test_grunnlinja_staar_i_runbooken(self):
        tekst = RUNBOOK.read_text(encoding='utf-8')
        self.assertIn(f"**{VAKTMODUS['workers']} × {VAKTMODUS['threads']}**", tekst)
        self.assertIn(f"**{VAKTMODUS['plan']}**", tekst)


@override_settings(SECURE_SSL_REDIRECT=False)
class DashbordetTests(TestCase):

    def setUp(self):
        CustomUser.objects.create_user(username='admin1', password='testpass123', role='admin',
                                       must_change_password=False)
        self.client.login(username='admin1', password='testpass123')

    def test_svaret_baerer_trinnet_modusen_og_kilden(self):
        d = self.client.get(reverse('portaladmin:admin_server_status_json')).json()
        m5 = d['metrics_5min']
        self.assertEqual(d['beredskap'], beredskapsnivaa(m5['p95_ms'], m5['errors_5xx'], m5['count']))
        self.assertIn(d['driftsmodus']['modus'], ('vakt', 'lavkostnad', 'halvveis', 'feil'))
        self.assertIn('tekst', d['metrikkilde'])

    def test_tabellen_tegnes_fra_trinnene_og_belastning_staar_foerst(self):
        html = self.client.get(reverse('portaladmin:admin_server_status')).content.decode()
        for t in BEREDSKAPSTRINN:
            self.assertIn(f'id="trinn-{t["nivaa"]}"', html)
        self.assertLess(html.index('id="p95-5min"'), html.index('id="backup-age"'),
                        'belastning øverst, sjekk før vakt under')
        self.assertLess(html.index('id="tregeste"'), html.index('id="cron-rader"'))
        for id_ in ('beredskap-nivaa', 'beredskap-tiltak', 'metrikk-kilde', 'driftsmodus'):
            self.assertIn(f'id="{id_}"', html)

    def test_traadregelen_staar_ved_tabellen(self):
        """Regelen sto i runbook §5, men ikke der man ser under stress."""
        html = self.client.get(reverse('portaladmin:admin_server_status')).content.decode()
        self.assertIn('id="traadregel"', html)
        self.assertIn(f'WEB_THREADS={TRADER_VED_VENTING}', html)
        self.assertIn(f'WEB_THREADS={TRADER_VED_VENTING}', TRAADREGEL)


class BeredskapstrinnTilkoblingerTests(SimpleTestCase):
    """Høyeste trinn skal holde seg under Postgres-taket med margin
    (runbook §3c): workers × (tråder + 2), der de to er backupklokka og
    reservenettet i hver prosess."""

    POSTGRES_TAK = 100
    MARGIN = 20          # cron-jobbene, release-fasen, en psql-økt
    TRADER_I_PARAGRAF_5 = TRADER_VED_VENTING

    def test_hoeyeste_trinn_med_flest_traader_er_under_taket(self):
        workers = max(t['workers'] or VAKTMODUS['workers'] for t in BEREDSKAPSTRINN)
        tilkoblinger = workers * (self.TRADER_I_PARAGRAF_5 + 2)
        self.assertLessEqual(tilkoblinger, self.POSTGRES_TAK - self.MARGIN,
                             f'{workers} workers × {self.TRADER_I_PARAGRAF_5} tråder gir ~{tilkoblinger}')

    def test_runbooken_sier_seks_traader_i_paragraf_5(self):
        tekst = RUNBOOK.read_text(encoding='utf-8')
        m = re.search(r'^## 5\. .*?(?=^## 6\. )', tekst, re.S | re.M)
        self.assertIn(f'`WEB_THREADS` = `{self.TRADER_I_PARAGRAF_5}`', m.group(0))
