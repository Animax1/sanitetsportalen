"""Planen på alle rader, «Flytt nå», rullingen og dekningen over et vindu
(23. sep. 2026, runde 2).

André: «trenger planlegg knapp på alle lokasjonene for å kunne sette
ressurser», «KO skal trykke flytt nå», «la admin og ko-leder kunne justere på
rulling», og at planleggeren skal følge tavlas tidslinje.

Tyngden ligger i `tavle.planlegg_pause`/`start_pause` — en feil der flytter et
lag til feil sted, eller lar en plan for i morgen avvises fordi laget ikke er
på vakt *nå*. Prøvene går gjennom endepunktene der porten er poenget.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from core.models import AppSetting
from ko import program, services, tavle
from ko.models import PlanlagtPause, Tavleplassering
from vaktliste.models import Pause

from .tests_hendelseslogg import skift
from .tests_tavle import PorteneTests, _Grunnlag


class _Plan(_Grunnlag):

    def _plan(self, ressurs=None, fra_min=10, lengde_min=30, **kw):
        naa = kw.pop('naa', None) or timezone.now()
        return tavle.planlegg_pause(self.vakt, ressurs or self.lag1, bruker=self.operator,
                                    fra=naa + timedelta(minutes=fra_min),
                                    til=naa + timedelta(minutes=fra_min + lengde_min), naa=naa, **kw)


class PlanPaaEtStedTests(_Plan):

    def test_planen_staar_paa_stedet_og_flytter_ingen(self):
        p = self._plasser(self.lag1, self.club)
        q = self._plan(lokasjon=self.park)
        self.assertEqual((q.pause, q.lokasjon, q.lokasjon_navn), (False, self.park, 'Parkscene'))
        self.assertEqual(tavle.aapen(self.lag1), p, 'planen flytter ingen')
        (d,) = tavle.effektive_pauser(self.vakt)
        self.assertEqual((d['pause'], d['lokasjon_id'], d['lokasjon_navn']), (False, self.park.pk, 'Parkscene'))
        self.assertTrue(self._plan(ressurs=self.lag2).pause, 'uten sted er det Pause-raden')

    def test_flytt_naa_plasserer_paa_stedet_med_planens_slutt(self):
        naa = timezone.now()
        self._plasser(self.lag1, self.club, naa=naa - timedelta(minutes=30))
        q = self._plan(lokasjon=self.park, fra_min=-5, lengde_min=65, naa=naa)
        p = tavle.start_pause(q, bruker=self.operator, naa=naa)
        q.refresh_from_db()
        self.assertEqual((p.lokasjon, p.pause, q.startet), (self.park, False, p))
        self.assertEqual(p.planlagt_til, q.til, 'planens slutt blir plasseringens')
        self.assertEqual(Tavleplassering.objects.filter(ressurs=self.lag1, til__isnull=True).count(), 1)

    def test_star_laget_alt_paa_stedet_knyttes_planen_dit(self):
        p = self._plasser(self.lag1, self.park)
        q = self._plan(lokasjon=self.park, fra_min=-5)
        self.assertEqual(tavle.start_pause(q, bruker=self.operator), p)
        # Men et lag i *pause* står ikke på stedet — der flyttes det.
        self._plasser(self.lag2, pause=True)
        q2 = self._plan(ressurs=self.lag2, lokasjon=self.park, fra_min=-5)
        self.assertEqual(tavle.start_pause(q2, bruker=self.operator).lokasjon, self.park)

    def test_en_pause_knyttes_ikke_til_et_sted_laget_staar_paa(self):
        self._plasser(self.lag1, self.park)
        q = self._plan(fra_min=-5)
        self.assertTrue(tavle.start_pause(q, bruker=self.operator).pause)

    def test_planlagt_slutt_settes_ikke_over_en_som_alt_finnes(self):
        naa = timezone.now()
        p = self._plasser(self.lag1, self.park, naa=naa - timedelta(minutes=5))
        tavle.sett_planlagt_slutt(p, naa + timedelta(hours=3), naa=naa)
        q = self._plan(lokasjon=self.park, fra_min=-5, lengde_min=30, naa=naa)
        tavle.start_pause(q, bruker=self.operator, naa=naa)
        p.refresh_from_db()
        self.assertEqual(p.planlagt_til, naa + timedelta(hours=3), 'KOs egen slutt vinner')

    def test_et_sted_kan_planlegges_et_doegn_en_pause_fire_timer(self):
        self._plan(lokasjon=self.park, lengde_min=5 * 60)
        with self.assertRaises(services.Ugyldig):
            self._plan(ressurs=self.lag2, lengde_min=5 * 60)
        with self.assertRaises(services.Ugyldig):
            self._plan(ressurs=self.lag2, lokasjon=self.park, lengde_min=24 * 60 + 1)

    def test_en_endret_stedsplan_beholder_doegnet(self):
        q = self._plan(lokasjon=self.park, lengde_min=60)
        naa = timezone.now()
        tavle.planlegg_pause(self.vakt, self.lag1, bruker=self.operator, pause=q,
                             fra=naa + timedelta(minutes=10), til=naa + timedelta(hours=6))
        q.refresh_from_db()
        self.assertEqual((q.pause, q.lokasjon), (False, self.park))

    def test_to_planer_over_hverandre_avvises_ogsaa_paa_tvers_av_rader(self):
        self._plan(lokasjon=self.park)
        with self.assertRaises(services.Ugyldig):
            self._plan(fra_min=20)
        with self.assertRaises(services.Ugyldig):
            self._plan(lokasjon=self.club, fra_min=20)

    def test_inaktivt_sted_avvises_og_slettet_sted_stopper_flytt_naa(self):
        from oppdrag.models import Lokasjon
        Lokasjon.objects.filter(pk=self.club.pk).update(er_aktiv=False)
        self.club.refresh_from_db()
        with self.assertRaises(services.Ugyldig):
            self._plan(lokasjon=self.club)
        q = self._plan(lokasjon=self.park, fra_min=-5)
        self.park.delete()
        q.refresh_from_db()
        with self.assertRaises(services.Ugyldig) as feil:
            tavle.start_pause(q, bruker=self.operator)
        self.assertIn('Parkscene', str(feil.exception), 'navnet er frosset')
        self.assertIsNone(tavle.aapen(self.lag1))

    def test_en_stedsplan_skjuler_ikke_vaktlistas_pause(self):
        naa = timezone.now()
        Pause.objects.create(ressurs=self.lag1, fra=naa + timedelta(minutes=5), til=naa + timedelta(minutes=35))
        # Over samme tid: en plan på et sted er ingen pause, og tar ikke dens plass.
        self._plan(lokasjon=self.park, fra_min=10, lengde_min=60)
        self.assertEqual(sorted(d['kilde'] for d in tavle.effektive_pauser(self.vakt)), ['ko', 'vaktliste'])
        # En KO-pause over den samme tida tar dens plass.
        PlanlagtPause.objects.create(vakt=self.vakt, ressurs=self.lag1, ressurs_navn='Lag 1',
                                     fra=naa + timedelta(minutes=80), til=naa + timedelta(minutes=90))
        self.assertIn('vaktliste', [d['kilde'] for d in tavle.effektive_pauser(self.vakt)],
                      'en KO-pause som ikke overlapper, lar den stå')
        PlanlagtPause.objects.filter(fra=naa + timedelta(minutes=80)).update(
            fra=naa + timedelta(minutes=20), til=naa + timedelta(minutes=30))
        self.assertNotIn('vaktliste', [d['kilde'] for d in tavle.effektive_pauser(self.vakt)])


class PaaVaktVedTests(_Plan):
    """En plan for i morgen gjelder laget som går vakt i morgen."""

    def test_laget_uten_skift_naa_kan_planlegges_der_det_har_skift(self):
        naa = timezone.now()
        skift(self.av_vakt, fra=10, til=14)
        with self.assertRaises(services.Ugyldig) as feil:
            self._plan(ressurs=self.av_vakt, fra_min=60, naa=naa)
        self.assertIn('har ikke skift', str(feil.exception))
        q = self._plan(ressurs=self.av_vakt, fra_min=11 * 60, lokasjon=self.park, naa=naa)
        self.assertEqual(q.ressurs, self.av_vakt)

    def test_paa_tavla_naa_holder_og_uten_vaktliste_holder_ingenting_annet(self):
        naa = timezone.now()
        self.assertTrue(tavle.paa_vakt_ved(self.lag1, naa + timedelta(hours=30), naa))
        self.assertFalse(tavle.paa_vakt_ved(self.av_vakt, naa + timedelta(hours=1), naa))
        skift(self.av_vakt, fra=2, til=4)
        self.assertTrue(tavle.paa_vakt_ved(self.av_vakt, naa + timedelta(hours=3), naa))
        self.assertFalse(tavle.paa_vakt_ved(self.av_vakt, naa + timedelta(hours=5), naa))

    def test_alle_ressurser_er_listas_ikke_tavlas(self):
        d = tavle.tavle_data(self.vakt)
        navn = [r['navn'] for r in d['alle_ressurser']]
        self.assertIn('Lag 9', navn, 'uten skift nå kan det likevel ha et i morgen')
        self.assertEqual([r['bil'] for r in d['alle_ressurser'] if r['navn'] == 'Ambulanse 1'], [True])
        self.assertNotIn('Ambulanse 1', [r['navn'] for r in tavle.tavle_data(self.vakt, med_biler=False)
                                         ['alle_ressurser']])


class RullingenTests(_Plan):

    def test_standard_klemmes_ved_lesing(self):
        self.assertEqual(tavle.rulling(), {'timer': 12, 'andel_bak': 25, 'steg_min': 120,
                                           'dognstart': '06:00'})
        AppSetting.set(tavle.ANDEL_BAK_NOKKEL, '80')
        AppSetting.set(tavle.STEG_NOKKEL, '1')
        self.assertEqual((tavle.andel_bak(), tavle.steg_min()), (50, 15))
        AppSetting.set(tavle.ANDEL_BAK_NOKKEL, 'x')
        self.assertEqual(tavle.andel_bak(), 25)

    def test_lagring_avviser_utenfor_grensene_i_stedet_for_aa_klemme(self):
        tavle.lagre_rulling(andel=0, steg=720)
        self.assertEqual((tavle.andel_bak(), tavle.steg_min()), (0, 720))
        tavle.lagre_rulling(andel=50, steg=15)
        for andel, steg in ((-1, 60), (51, 60), (25, 14), (25, 721), ('x', 60)):
            with self.subTest(andel=andel, steg=steg), self.assertRaises(services.Ugyldig):
                tavle.lagre_rulling(andel=andel, steg=steg)
        self.assertEqual((tavle.andel_bak(), tavle.steg_min()), (50, 15), 'et avslag lagrer ingenting')

    def test_tavla_og_programmet_baerer_den(self):
        tavle.lagre_rulling(andel=10, steg=60)
        d = tavle.tavle_data(self.vakt)
        self.assertEqual((d['andel_bak'], d['steg_min']), (10, 60))
        self.assertEqual(program.program_data(self.vakt)['rulling']['andel_bak'], 10)


class PlanPortene(PorteneTests):

    def test_alle_som_forer_tavla_planlegger_paa_et_sted(self):
        naa = timezone.now()
        kropp = {'ressurs_id': self.lag1.pk, 'lokasjon_id': self.park.pk,
                 'fra': (naa + timedelta(minutes=10)).isoformat(),
                 'til': (naa + timedelta(hours=5)).isoformat()}
        url = '/ko/api/tavle/pauser/'
        self.assertEqual(self._klient('les').post(url, kropp, content_type='application/json').status_code, 403)
        r = self._klient('skriv_full').post(url, kropp, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(PlanlagtPause.objects.get(pk=r.json()['data']['id']).lokasjon, self.park)
        ukjent = dict(kropp, lokasjon_id=99999)
        self.assertEqual(self._klient('skriv_full').post(url, ukjent, content_type='application/json')
                         .status_code, 404)

    def test_rullingen_endres_bare_av_lederen_og_i_samme_dor_som_oppsettet(self):
        url = '/ko/api/tavle/oppsett/'
        kropp = {'skjulte': [], 'fulgte': [], 'andel_bak': 10, 'steg_min': 60}
        self.assertEqual(self._klient('skriv_full').put(url, kropp, content_type='application/json')
                         .status_code, 403)
        self.assertEqual(tavle.andel_bak(), 25)
        r = self._klient('skriv_leder').put(url, kropp, content_type='application/json')
        self.assertEqual((r.json()['data']['andel_bak'], r.json()['data']['steg_min']), (10, 60))
        # Et avslag på rullingen lagrer heller ikke oppsettet.
        feil = {'skjulte': [self.club.pk], 'fulgte': [], 'andel_bak': 99}
        self.assertEqual(self._klient('skriv_leder').put(url, feil, content_type='application/json')
                         .status_code, 400)
        self.assertEqual(tavle.skjulte(), [])
        # Uten feltene røres ikke rullingen — heller ikke skrives: hver
        # lagring av avkryssingene ville ellers lagt to auditrader for
        # verdier ingen endret.
        AppSetting.objects.filter(key__in=[tavle.ANDEL_BAK_NOKKEL, tavle.STEG_NOKKEL]).delete()
        self._klient('skriv_leder').put(url, {'skjulte': [], 'fulgte': []}, content_type='application/json')
        self.assertFalse(AppSetting.objects.filter(key__in=[tavle.ANDEL_BAK_NOKKEL, tavle.STEG_NOKKEL]).exists())

    def test_dekningen_over_et_vindu(self):
        naa = timezone.now()
        start = naa.replace(minute=0, second=0, microsecond=0)
        c = self._klient('les')
        r = c.get('/ko/api/program/dekning/', {'fra': start.isoformat(), 'timer': 6})
        self.assertEqual(r.status_code, 200, r.content)
        timer = r.json()['data']['timer']
        self.assertEqual(len(timer), 6)
        self.assertEqual(timer[0]['grupper'].get(str(self.lag1.gruppe_id)), 2)
        for feil in ({'fra': start.isoformat(), 'timer': 0}, {'fra': start.isoformat(), 'timer': 49},
                     {'fra': 'i går', 'timer': 6}, {}):
            with self.subTest(feil=feil):
                self.assertEqual(c.get('/ko/api/program/dekning/', feil).status_code, 400)
        self.assertEqual(len(c.get('/ko/api/program/dekning/', {'fra': start.isoformat()})
                             .json()['data']['timer']), 24, 'standard er et døgn')


@override_settings(SECURE_SSL_REDIRECT=False)
class DekningenTellerBarePauserTests(_Plan):

    def test_en_stedsplan_trekker_ikke_fra(self):
        naa = timezone.now()
        start = naa.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        midt = start + program.MIDT_I_TIMEN
        PlanlagtPause.objects.create(vakt=self.vakt, ressurs=self.lag1, ressurs_navn='Lag 1',
                                     fra=midt - timedelta(minutes=5), til=midt + timedelta(minutes=5),
                                     pause=False, lokasjon=self.park, lokasjon_navn='Parkscene')
        self.assertEqual(program.paa_vakt_per_time(start, self.vakt, 1)[0]['pause'], {})
        PlanlagtPause.objects.filter(ressurs=self.lag1).update(pause=True, lokasjon=None)
        self.assertEqual(program.paa_vakt_per_time(start, self.vakt, 1)[0]['pause'],
                         {str(self.lag1.gruppe_id): 1})

    def test_antallet_timer_klemmes(self):
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        self.assertEqual(len(program.paa_vakt_per_time(start, None, 0)), 1)
        self.assertEqual(len(program.paa_vakt_per_time(start, None, 99)), program.MAKS_DEKNINGSTIMER)
