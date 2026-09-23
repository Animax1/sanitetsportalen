"""Vaktlistas pauser på KO-tavla (23. sep. 2026).

André: «vaktlistas pause er utgangspunktet og står i Pause-raden av seg selv;
KO kan endre den i drift, og da gjelder KOs versjon resten av vakta, merket
«endret i drift» — vaktlista overstyrer den ikke lenger. KO kan fortsatt
planlegge for lag vaktlista ikke har gitt pause.»

Tyngden er i `tavle.effektive_pauser` og overtakelsen i viewene: en feil der
gir en pause som står dobbelt, eller en KO-endring som stille blir rullet
tilbake av vaktlista — og det ser ingen før laget står i pause midt i
headlineren.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from ko import program, tavle
from ko.models import PlanlagtPause
from vaktliste.models import Pause

from .tests_tavle import PorteneTests, _Grunnlag


class _Vaktlistepauser(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.naa = timezone.now()
        self.vp = Pause.objects.create(ressurs=self.lag1, fra=self.naa + timedelta(minutes=5),
                                       til=self.naa + timedelta(minutes=35))

    def _pauser(self):
        return tavle.effektive_pauser(self.vakt)

    def _ko(self, ressurs, fra_min, til_min, **kw):
        return PlanlagtPause.objects.create(
            vakt=self.vakt, ressurs=ressurs, ressurs_navn=ressurs.navn,
            fra=self.naa + timedelta(minutes=fra_min), til=self.naa + timedelta(minutes=til_min), **kw)


class EffektivePauserTests(_Vaktlistepauser):

    def test_vaktlistas_pause_staar_av_seg_selv_uten_kopi(self):
        (q,) = self._pauser()
        self.assertEqual((q['id'], q['kilde'], q['ressurs_navn'], q['startet']),
                         (f'v{self.vp.pk}', 'vaktliste', 'Lag 1', False))
        self.assertFalse(PlanlagtPause.objects.exists(), 'ingen kopi før KO rører den')

    def test_overtatt_vises_som_kos_og_vaktlista_overstyrer_ikke_lenger(self):
        q = tavle.overta_pause(self.vakt, self.vp, bruker=self.operator)
        self.assertEqual([(p['id'], p['kilde']) for p in self._pauser()], [(q.pk, 'vaktliste')])
        tavle.planlegg_pause(self.vakt, self.lag1, pause=q, bruker=self.operator,
                             fra=self.naa + timedelta(minutes=45), til=self.naa + timedelta(minutes=75))
        # Vaktlista flytter sin — KOs versjon står.
        Pause.objects.filter(pk=self.vp.pk).update(fra=self.naa + timedelta(minutes=90),
                                                   til=self.naa + timedelta(minutes=120))
        (p,) = self._pauser()
        self.assertEqual((p['id'], p['kilde'], p['fra']), (q.pk, 'endret', self.naa + timedelta(minutes=45)))

    def test_kos_egen_pause_over_vaktlistas_vinner_men_ikke_for_et_annet_lag(self):
        egen = self._ko(self.lag1, 20, 50)
        annen = self._ko(self.lag2, 5, 35)
        self.assertEqual({p['id'] for p in self._pauser()}, {egen.pk, annen.pk})
        PlanlagtPause.objects.filter(pk=egen.pk).update(fra=self.naa + timedelta(minutes=35),
                                                        til=self.naa + timedelta(minutes=50))
        self.assertIn(f'v{self.vp.pk}', {p['id'] for p in self._pauser()}, 'inntil er ikke over')

    def test_avlyst_skjuler_vaktlistas_og_er_selv_borte(self):
        q = tavle.overta_pause(self.vakt, self.vp, bruker=self.operator)
        tavle.slett_pause(q)
        q.refresh_from_db()
        self.assertTrue(q.avlyst, 'raden står — ellers kom vaktlistas tilbake')
        self.assertEqual(self._pauser(), [])

    def test_en_avlyst_sperrer_ikke_for_en_ny_kos_pause(self):
        tavle.slett_pause(tavle.overta_pause(self.vakt, self.vp, bruker=self.operator))
        tavle.planlegg_pause(self.vakt, self.lag1, bruker=self.operator,
                             fra=self.naa + timedelta(minutes=10), til=self.naa + timedelta(minutes=20))

    def test_en_kos_egen_slettes_fortsatt(self):
        egen = self._ko(self.lag2, 5, 35)
        tavle.slett_pause(egen)
        self.assertFalse(PlanlagtPause.objects.filter(pk=egen.pk).exists())

    def test_overtakelsen_er_idempotent(self):
        a = tavle.overta_pause(self.vakt, self.vp, bruker=self.operator)
        b = tavle.overta_pause(self.vakt, self.vp, bruker=self.operator)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual((a.fra, a.til, a.av_navn), (self.vp.fra, self.vp.til, 'ko1'))

    def test_bare_lista_i_bruk_og_sortert_paa_tid(self):
        from vaktliste.models import Vaktliste
        from vaktliste.test_helpers import LAG, gruppe, lag_ressurs
        from core.models import Vakt
        annen = Vaktliste.objects.create(vakt=Vakt.objects.create(navn='annen', year=2025,
                                                                  startet=self.naa))
        fremmed = lag_ressurs(vaktliste=annen, navn='Lag X', gruppe=gruppe(LAG))
        Pause.objects.create(ressurs=fremmed, fra=self.naa, til=self.naa + timedelta(minutes=30))
        tidlig = self._ko(self.lag2, -30, -10)
        sen = self._ko(self.lag2, 60, 90)
        self.assertEqual([p['id'] for p in self._pauser()], [tidlig.pk, f'v{self.vp.pk}', sen.pk],
                         'på tid, ikke KOs først og vaktlistas etter')

    def test_tavlesvaret_baerer_dem_med_kilden(self):
        d = tavle.tavle_data(self.vakt)
        self.assertEqual([(p['id'], p['kilde']) for p in d['pauser']], [(f'v{self.vp.pk}', 'vaktliste')])
        self.assertEqual(d['pauser'][0]['fra'], self.vp.fra.isoformat())


class VaktlistepauseneGjennomEndepunkteneTests(PorteneTests):

    def setUp(self):
        super().setUp()
        self.naa = timezone.now()
        self.vp = Pause.objects.create(ressurs=self.lag1, fra=self.naa - timedelta(minutes=1),
                                       til=self.naa + timedelta(minutes=29))
        self.url = f'/ko/api/tavle/pauser/v{self.vp.pk}/'

    def _kropp(self, fra_min, til_min):
        return {'fra': (self.naa + timedelta(minutes=fra_min)).isoformat(),
                'til': (self.naa + timedelta(minutes=til_min)).isoformat()}

    def test_endre_gjoer_den_til_kos_merket_endret(self):
        self.assertEqual(self._klient('les').put(self.url, self._kropp(10, 40),
                                                 content_type='application/json').status_code, 403)
        self.assertFalse(PlanlagtPause.objects.exists())
        r = self._klient('skriv_full').put(self.url, self._kropp(10, 40), content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        q = PlanlagtPause.objects.get()
        self.assertEqual((q.fra_vaktliste_id, q.endret, q.fra), (self.vp.pk, True, self.naa + timedelta(minutes=10)))

    def test_en_avvist_endring_etterlater_ingen_overtakelse(self):
        r = self._klient('skriv_full').put(self.url, self._kropp(10, 10), content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(PlanlagtPause.objects.exists(), 'transaksjonen skal rulle overtakelsen tilbake')

    def test_pause_naa_paa_vaktlistas(self):
        r = self._klient('skriv_full').post(self.url + 'start/', {}, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        q = PlanlagtPause.objects.get()
        self.assertIsNotNone(q.startet_id)
        self.assertFalse(q.endret, '«Pause nå» er ikke en endring')
        self.assertTrue(tavle.aapen(self.lag1).pause)

    def test_fjern_avlyser_og_andre_gang_er_den_borte(self):
        c = self._klient('skriv_full')
        self.assertEqual(c.delete(self.url, {}, content_type='application/json').status_code, 200)
        self.assertTrue(PlanlagtPause.objects.get().avlyst)
        self.assertEqual(c.delete(self.url, {}, content_type='application/json').status_code, 404)
        q = PlanlagtPause.objects.get()
        self.assertEqual(c.put(f'/ko/api/tavle/pauser/{q.pk}/', self._kropp(10, 40),
                               content_type='application/json').status_code, 404)

    def test_ukjente_og_fremmede_referanser_er_404(self):
        from vaktliste.models import Vaktliste
        from vaktliste.test_helpers import LAG, gruppe, lag_ressurs
        from core.models import Vakt
        annen = Vaktliste.objects.create(vakt=Vakt.objects.create(navn='annen', year=2025, startet=self.naa))
        fremmed = Pause.objects.create(ressurs=lag_ressurs(vaktliste=annen, navn='Lag X', gruppe=gruppe(LAG)),
                                       fra=self.naa, til=self.naa + timedelta(minutes=30))
        c = self._klient('skriv_full')
        for ref in (f'v{fremmed.pk}', 'v99999', 'vx', 'tull', '0'):
            with self.subTest(ref=ref):
                self.assertEqual(c.put(f'/ko/api/tavle/pauser/{ref}/', self._kropp(10, 40),
                                       content_type='application/json').status_code, 404)
        self.assertFalse(PlanlagtPause.objects.exists())

    def test_bilens_pause_uten_oppdragstilgang_er_404(self):
        from vaktliste.models import Vaktpost
        Vaktpost.objects.create(ressurs=self.bil, fra_tid=self.naa - timedelta(hours=1),
                                til_tid=self.naa + timedelta(hours=5))
        bp = Pause.objects.create(ressurs=self.bil, fra=self.naa, til=self.naa + timedelta(minutes=30))
        url = f'/ko/api/tavle/pauser/v{bp.pk}/'
        self.assertEqual(self._klient('skriv_full', oppdrag=None).delete(
            url, {}, content_type='application/json').status_code, 404)
        self.assertFalse(PlanlagtPause.objects.exists(), 'en bil man ikke får se, overtas ikke')
        self.assertEqual(self._klient('skriv_full').delete(
            url, {}, content_type='application/json').status_code, 200)


class DekningenTrekkerFraPausenTests(_Vaktlistepauser):

    def test_et_lag_i_pause_midt_i_timen_er_ikke_paa_vakt_den_timen(self):
        start = self.naa.replace(minute=0, second=0, microsecond=0)
        midt = start + program.MIDT_I_TIMEN
        Pause.objects.filter(pk=self.vp.pk).update(fra=midt - timedelta(minutes=10),
                                                   til=midt + timedelta(minutes=10))
        (time,) = program.paa_vakt_per_time(start, self.vakt)[:1]
        g = str(self.lag1.gruppe_id)
        self.assertEqual((time['grupper'].get(g), time['pause'].get(g)), (1, 1))
        # Uten vakt (planleggeren uten KO-kontekst) trekkes ingenting fra.
        self.assertEqual(program.paa_vakt_per_time(start)[0]['grupper'].get(g), 2)

    def test_pausen_maa_dekke_midten_akkurat(self):
        start = self.naa.replace(minute=0, second=0, microsecond=0)
        midt = start + program.MIDT_I_TIMEN
        g = str(self.lag1.gruppe_id)
        for fra, til, i_pause in ((midt, midt + timedelta(minutes=5), 1),
                                  (midt - timedelta(minutes=5), midt, 0)):
            with self.subTest(fra=fra):
                Pause.objects.filter(pk=self.vp.pk).update(fra=fra, til=til)
                self.assertEqual(program.paa_vakt_per_time(start, self.vakt)[0]['pause'].get(g, 0), i_pause)

    def test_kos_endring_gjelder_ogsaa_i_stripa(self):
        start = self.naa.replace(minute=0, second=0, microsecond=0)
        midt = start + program.MIDT_I_TIMEN
        Pause.objects.filter(pk=self.vp.pk).update(fra=midt - timedelta(minutes=10),
                                                   til=midt + timedelta(minutes=10))
        self.vp.refresh_from_db()
        tavle.slett_pause(tavle.overta_pause(self.vakt, self.vp, bruker=self.operator))
        self.assertEqual(program.paa_vakt_per_time(start, self.vakt)[0]['pause'], {})


class DekningsendepunktetTests(PorteneTests):

    def test_endepunktet_trekker_fra_pausene_i_aktiv_vakt(self):
        naa = timezone.now()
        start = timezone.localtime(naa).replace(hour=0, minute=0, second=0, microsecond=0)
        timen = int((naa - start).total_seconds() // 3600)
        midt = start + timedelta(hours=timen) + program.MIDT_I_TIMEN
        Pause.objects.create(ressurs=self.lag1, fra=midt - timedelta(minutes=5), til=midt + timedelta(minutes=5))
        # Døgnet timen hører til: før døgnstarten er det gårsdagens.
        from ko.tavle import dognstart
        dogn = start if timezone.localtime(naa).hour >= int(dognstart()[:2]) else start - timedelta(days=1)
        r = self._klient('les').get('/ko/api/program/dekning/', {'dogn': dogn.date().isoformat()})
        self.assertEqual(r.status_code, 200, r.content)
        g = str(self.lag1.gruppe_id)
        i_pause = [t['pause'].get(g, 0) for t in r.json()['data']['timer']]
        self.assertEqual(sum(i_pause), 1, i_pause)
