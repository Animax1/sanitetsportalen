"""Programmet — konsertene, beredskapsnivå og behov (tavleplanleggeren, steg 2,
23. sep. 2026).

Tyngden ligger i tjenestelaget (`ko/program.py`): en feil der legger seg i
programmet og gir planleggeren og tavla feil tall, og det ser ingen før
konserten er i gang. Portene prøves gjennom endepunktene.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import Client
from django.utils import timezone

from ko import program, services, tavle
from ko.models import Kjennetegn, Konserttype, Programbehov, Programpost, Tavleplassering
from oppdrag.models import Lokasjon
from vaktliste.models import Ressursgruppe
from vaktliste.test_helpers import AMBULANSE, LAG, gruppe

from .tests_hendelseslogg import _bruker, _gi
from .tests_tavle import _Grunnlag


class _Program(_Grunnlag):

    def setUp(self):
        super().setUp()
        self.leder = _bruker('kolederen')
        self.lag = gruppe(LAG)
        self.amb = gruppe(AMBULANSE)
        self.headliner = Konserttype.objects.get(navn='Headliner')
        self.pyro = Kjennetegn.objects.get(navn='Pyro')
        naa = timezone.now()
        self.fra = naa + timedelta(hours=1)
        self.til = naa + timedelta(hours=3)

    def _data(self, **kw):
        data = {'lokasjon_id': self.park.pk, 'navn': 'Headliner fredag',
                'konserttype_id': self.headliner.pk, 'beredskap': 'oransje', 'publikum': 12000,
                'kjennetegn': [self.pyro.pk],
                'behov': [{'gruppe_id': self.lag.pk, 'antall': 4}, {'gruppe_id': self.amb.pk, 'antall': 2}]}
        data.update(kw)
        return data

    def _lagre(self, post=None, fra=None, til=None, **kw):
        return program.lagre_post(self.vakt, self._data(**kw), fra=fra or self.fra, til=til or self.til,
                                  bruker=self.leder, post=post)


class ForslagetTests(_Program):

    def test_forslaget_til_typer_og_kjennetegn_er_lagt_inn(self):
        """André: «vi kommer med et forslag som vi kan justere». Pyro først."""
        self.assertEqual(Kjennetegn.objects.order_by('rekkefolge').first().navn, 'Pyro')
        self.assertTrue(Konserttype.objects.filter(navn='Fast post (ikke konsert)').exists())


class LagrePostTests(_Program):

    def test_ny_konsert_med_behov_kjennetegn_og_frosne_navn(self):
        post = self._lagre()
        self.assertEqual(post.lokasjon_navn, 'Parkscene')
        self.assertEqual(post.konserttype_navn, 'Headliner')
        self.assertEqual(post.beredskap, 'oransje')
        self.assertEqual(post.publikum, 12000)
        self.assertEqual(list(post.kjennetegn.values_list('navn', flat=True)), ['Pyro'])
        self.assertEqual(sorted(post.behov.values_list('gruppe_navn', 'antall')),
                         sorted([(LAG, 4), (AMBULANSE, 2)]))
        self.assertEqual(post.endret_av_navn, 'kolederen')

    def test_typen_setter_ingen_ressurser(self):
        """André: «Konserttyper skal ikke automatisk sette ressurser.»"""
        post = self._lagre(behov=[])
        self.assertEqual(post.behov.count(), 0)

    def test_endring_bytter_ut_behovet_i_sin_helhet(self):
        post = self._lagre()
        self._lagre(post=post, behov=[{'gruppe_id': self.lag.pk, 'antall': 5}], kjennetegn=[])
        post.refresh_from_db()
        self.assertEqual(list(post.behov.values_list('gruppe_navn', 'antall')), [(LAG, 5)])
        self.assertEqual(post.kjennetegn.count(), 0)
        self.assertEqual(Programpost.objects.count(), 1, 'en endring, ikke en ny')

    def test_null_er_ingen_og_tas_ut(self):
        post = self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 0}])
        self.assertEqual(post.behov.count(), 0)

    def test_ugyldige_verdier_avvises_og_ingenting_lagres(self):
        ugyldige = {
            'tomt navn': dict(navn='  '),
            'for langt navn': dict(navn='x' * 121),
            'ukjent sted': dict(lokasjon_id=99999),
            'sted som ikke er et tall': dict(lokasjon_id='tull'),
            'ukjent type': dict(konserttype_id=99999),
            'ukjent beredskap': dict(beredskap='lilla'),
            'negativt publikum': dict(publikum=-1),
            'publikum som ikke er et tall': dict(publikum='mange'),
            'samme gruppe to ganger': dict(behov=[{'gruppe_id': self.lag.pk, 'antall': 1},
                                                  {'gruppe_id': self.lag.pk, 'antall': 2}]),
            'for mange': dict(behov=[{'gruppe_id': self.lag.pk, 'antall': 100}]),
            'ukjent gruppe': dict(behov=[{'gruppe_id': 99999, 'antall': 1}]),
            'behov som ikke er en liste': dict(behov='fire lag'),
            'antall som ikke er et tall': dict(behov=[{'gruppe_id': self.lag.pk, 'antall': 'fire'}]),
            'ukjent kjennetegn': dict(kjennetegn=[99999]),
            'kjennetegn som ikke er tall': dict(kjennetegn=['Pyro']),
        }
        for hva, kw in ugyldige.items():
            with self.subTest(hva), self.assertRaises(services.Ugyldig):
                self._lagre(**kw)
        self.assertEqual(Programpost.objects.count(), 0)
        self.assertEqual(Programbehov.objects.count(), 0)

    def test_99_er_lov_og_100_er_ikke(self):
        self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 99}])
        with self.assertRaises(services.Ugyldig):
            self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 100}])

    def test_tidene(self):
        with self.assertRaises(services.Ugyldig):
            self._lagre(til=self.fra)
        with self.assertRaises(services.Ugyldig):
            self._lagre(til=self.fra + timedelta(hours=24, minutes=1))
        self._lagre(til=self.fra + timedelta(hours=24))

    def test_et_ugyldig_behov_rulles_tilbake_ogsaa_paa_en_endring(self):
        post = self._lagre()
        with self.assertRaises(services.Ugyldig):
            self._lagre(post=post, navn='Nytt navn', behov=[{'gruppe_id': 99999, 'antall': 1}])
        post.refresh_from_db()
        self.assertEqual(post.navn, 'Headliner fredag')
        self.assertEqual(post.behov.count(), 2)

    def test_inaktivt_sted_alene_avvises_paa_en_ny(self):
        """For seg selv — i testen under er typen inaktiv samtidig, og da
        kunne feilen like gjerne kommet derfra (funnet ved mutasjon)."""
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False)
        with self.assertRaises(services.Ugyldig):
            self._lagre()
        self.assertEqual(Programpost.objects.count(), 0)

    def test_feiler_skrivingen_halvveis_blir_ingenting_staaende(self):
        """Valideringen skjer før all skriving, så bare en feil *i*
        skrivingen viser om transaksjonen er der: konserten skal ikke stå igjen
        uten behovet sitt."""
        from unittest import mock
        from django.db import DatabaseError
        post = self._lagre()
        ekte = Programbehov.objects.create
        kall = []

        def feil_paa_andre(**kw):
            kall.append(kw)
            if len(kall) == 2:
                raise DatabaseError('borte')
            return ekte(**kw)

        with mock.patch.object(Programbehov.objects, 'create', side_effect=feil_paa_andre), \
                self.assertRaises(DatabaseError):
            self._lagre(post=post, navn='Halvveis')
        post.refresh_from_db()
        self.assertEqual(post.navn, 'Headliner fredag')
        self.assertEqual(post.behov.count(), 2, 'det gamle behovet står, ikke halve det nye')

    def test_inaktivt_sted_type_og_gruppe_avvises_paa_ny_men_beholdes_paa_endring(self):
        post = self._lagre()
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False)
        Konserttype.objects.filter(pk=self.headliner.pk).update(er_aktiv=False)
        self._lagre(post=post, navn='Beholder sted og type')
        post.refresh_from_db()
        self.assertEqual(post.navn, 'Beholder sted og type')
        with self.assertRaises(services.Ugyldig):
            self._lagre()
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=True)
        with self.assertRaises(services.Ugyldig):
            self._lagre()
        Ressursgruppe.objects.filter(pk=self.amb.pk).update(er_aktiv=False)
        with self.assertRaises(services.Ugyldig):
            self._lagre(konserttype_id=None)

    def test_tomt_beredskapsnivaa_er_lov_for_et_fast_behov(self):
        post = self._lagre(beredskap='', konserttype_id=None, publikum=None)
        self.assertEqual(post.beredskap, '')
        self.assertIsNone(post.publikum)


class FolgerKonsertenTests(_Program):

    def test_folger_konsertens_slutt_og_flytter_seg_med_den(self):
        post = self._lagre(fra=timezone.now() - timedelta(minutes=30))
        p = self._plasser(self.lag1, self.park)
        program.folg(p, post, naa=timezone.now())
        data = tavle.tavle_data(self.vakt)
        rad = next(x for x in data['plasseringer'] if x['id'] == p.pk)
        self.assertEqual(rad['folger_id'], post.pk)
        self.assertEqual(rad['planlagt_til'], post.til.isoformat())
        ny_til = post.til + timedelta(minutes=30)
        self._lagre(post=post, fra=post.fra, til=ny_til)
        data = tavle.tavle_data(self.vakt)
        self.assertEqual(next(x for x in data['plasseringer'] if x['id'] == p.pk)['planlagt_til'],
                         ny_til.isoformat(), 'konserten ble forsinket, og slutten fulgte med')

    def test_bare_paa_stedet_det_staar_og_ikke_naar_konserten_er_over(self):
        post = self._lagre(fra=timezone.now() - timedelta(minutes=30))
        paa_club = self._plasser(self.lag1, self.club)
        with self.assertRaises(services.Ugyldig):
            program.folg(paa_club, post, naa=timezone.now())
        p = self._plasser(self.lag2, self.park)
        with self.assertRaises(services.Ugyldig):
            program.folg(p, post, naa=post.til)
        program.folg(p, post, naa=post.til - timedelta(seconds=1))

    def test_en_lukket_plassering_foelger_ingenting(self):
        post = self._lagre(fra=timezone.now() - timedelta(minutes=30))
        p = self._plasser(self.lag1, self.park, naa=timezone.now() - timedelta(minutes=10))
        self._plasser(self.lag1, self.club)
        p.refresh_from_db()
        with self.assertRaises(services.Ugyldig):
            program.folg(p, post, naa=timezone.now())

    def test_egen_tid_tar_plassen_til_konserten_og_omvendt(self):
        post = self._lagre(fra=timezone.now() - timedelta(minutes=30))
        p = self._plasser(self.lag1, self.park)
        tavle.sett_planlagt_slutt(p, timezone.now() + timedelta(hours=5))
        program.folg(p, post, naa=timezone.now())
        p.refresh_from_db()
        self.assertEqual(p.folger_id, post.pk)
        self.assertIsNone(p.planlagt_til, 'aldri begge')
        tavle.sett_planlagt_slutt(p, None)
        p.refresh_from_db()
        self.assertIsNone(p.folger_id, 'ingen plan er ingen plan — heller ikke konsertens')

    def test_en_slettet_konsert_tar_slutten_med_seg(self):
        post = self._lagre(fra=timezone.now() - timedelta(minutes=30))
        p = self._plasser(self.lag1, self.park)
        program.folg(p, post, naa=timezone.now())
        program.slett_post(post)
        p.refresh_from_db()
        self.assertIsNone(p.folger_id)
        self.assertTrue(Tavleplassering.objects.filter(pk=p.pk, til__isnull=True).exists(),
                        'laget står der fortsatt')


class ProgrammetPaaTavlaTests(_Program):

    def test_tavla_baerer_programmet(self):
        post = self._lagre()
        data = tavle.tavle_data(self.vakt)
        self.assertEqual([p['id'] for p in data['program']], [post.pk])
        self.assertEqual(data['program'][0]['beredskap_navn'], 'Oransje')
        self.assertEqual(len(data['program'][0]['behov']), 2)

    def test_en_annen_vakts_program_er_ikke_med(self):
        from core.models import Vakt
        gammel = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        program.lagre_post(gammel, self._data(), fra=self.fra, til=self.til, bruker=self.leder)
        self.assertEqual(tavle.tavle_data(self.vakt)['program'], [])


class PorteneTests(_Program):

    def _klient(self, ko):
        self._nr = getattr(self, '_nr', 0) + 1
        b = _bruker(f'p{self._nr}_{ko}')
        if ko:
            _gi(b, 'ko', ko)
        _gi(b, 'vaktliste', 'les')
        _gi(b, 'oppdrag', 'les')
        c = Client()
        c.force_login(b)
        return c

    def _kropp(self, **kw):
        d = self._data(**kw)
        d['fra'], d['til'] = self.fra.isoformat(), self.til.isoformat()
        return d

    def test_les_ser_programmet_og_valgene(self):
        self._lagre()
        r = self._klient('les').get('/ko/api/program/')
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        self.assertEqual(len(data['poster']), 1)
        self.assertIn('Pyro', [k['navn'] for k in data['kjennetegn']])
        self.assertIn(LAG, [g['navn'] for g in data['grupper']])
        self.assertIn('Parkscene', [s['navn'] for s in data['steder']])
        self.assertEqual([b['verdi'] for b in data['beredskap']], ['gronn', 'gul', 'oransje', 'rod'])
        self.assertEqual(self._klient(None).get('/ko/api/program/').status_code, 403)

    def test_bare_ko_leder_skriver(self):
        for niva in ('les', 'skriv_full'):
            with self.subTest(niva):
                self.assertEqual(self._klient(niva).post('/ko/api/program/', self._kropp(),
                                                         content_type='application/json').status_code, 403)
        c = self._klient('skriv_leder')
        r = c.post('/ko/api/program/', self._kropp(), content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        pk = r.json()['data']['id']
        url = f'/ko/api/program/{pk}/'
        self.assertEqual(self._klient('skriv_full').put(url, self._kropp(navn='x'),
                                                        content_type='application/json').status_code, 403)
        self.assertEqual(self._klient('skriv_full').delete(url).status_code, 403)
        self.assertEqual(c.put(url, self._kropp(navn='Endret'), content_type='application/json').status_code, 200)
        self.assertEqual(Programpost.objects.get(pk=pk).navn, 'Endret')
        self.assertEqual(c.delete(url).status_code, 200)
        self.assertFalse(Programpost.objects.filter(pk=pk).exists())

    def test_ugyldig_er_400_og_en_annen_vakts_konsert_finnes_ikke(self):
        from core.models import Vakt
        c = self._klient('skriv_leder')
        self.assertEqual(c.post('/ko/api/program/', self._kropp(beredskap='lilla'),
                                content_type='application/json').status_code, 400)
        kropp = self._kropp()
        kropp['fra'] = 'i kveld'
        self.assertEqual(c.post('/ko/api/program/', kropp, content_type='application/json').status_code, 400)
        gammel = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        post = program.lagre_post(gammel, self._data(), fra=self.fra, til=self.til, bruker=self.leder)
        self.assertEqual(c.put(f'/ko/api/program/{post.pk}/', self._kropp(),
                               content_type='application/json').status_code, 404)

    def test_folg_konserten_gjennom_plasseringen(self):
        post = self._lagre(fra=timezone.now() - timedelta(minutes=30))
        p = self._plasser(self.lag1, self.park)
        url = f'/ko/api/tavle/plasseringer/{p.pk}/'
        c = self._klient('skriv_full')
        self.assertEqual(c.put(url, {'folger_id': 99999}, content_type='application/json').status_code, 400)
        r = c.put(url, {'folger_id': post.pk, 'planlagt_til': None}, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertEqual(p.folger_id, post.pk, 'følger går foran en tom egen tid')
        self.assertEqual(c.put(url, {'folger_id': None, 'planlagt_til': None},
                               content_type='application/json').status_code, 200)
        p.refresh_from_db()
        self.assertIsNone(p.folger_id)

    def test_listene_leses_av_les_og_settes_opp_av_lederen(self):
        for slug in ('konserttyper', 'kjennetegn'):
            with self.subTest(slug):
                url = f'/ko/api/{slug}/'
                self.assertEqual(self._klient('les').get(url).status_code, 200)
                self.assertEqual(self._klient('skriv_full').post(url, {'navn': 'Ny'},
                                                                 content_type='application/json').status_code, 403)
                self.assertEqual(self._klient('skriv_leder').post(url, {'navn': 'Ny'},
                                                                  content_type='application/json').status_code, 200)

    def test_en_type_i_bruk_slettes_ikke(self):
        self._lagre()
        admin = _bruker('admin_p', role='admin')
        c = Client()
        c.force_login(admin)
        r = c.delete(f'/ko/api/konserttyper/{self.headliner.pk}/', {'confirm': True},
                     content_type='application/json')
        self.assertEqual(r.status_code, 409, 'fjorårets program står med typen')

    def test_fanene_paa_sida_for_lederen(self):
        c = self._klient('skriv_leder')
        side = c.get('/ko/').content.decode()
        self.assertIn('/ko/api/konserttyper/', side)
        self.assertIn('/ko/api/kjennetegn/', side)
        self.assertIn('data-vindu="plan"', side)
        self.assertIn('data-action="koPlanNy"', side)
        les = self._klient('les').get('/ko/').content.decode()
        self.assertIn('data-vindu="plan"', les, 'alle med les ser planleggeren')
        self.assertNotIn('data-action="koPlanNy"', les, 'men bare lederen får «+ Konsert»')


class DekningTests(_Program):
    """Steg 4: vaktlistas tall per time, per gruppe — **samme regel som resten
    av portalen** for hvem som er på vakt (`ressurser_med_skift`)."""

    def setUp(self):
        super().setUp()
        from datetime import datetime, time
        from vaktliste.models import Korps, Mannskap, Vaktpost
        self.Vaktpost = Vaktpost
        self.korps, _ = Korps.objects.get_or_create(navn='Testkorps')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        tz = timezone.get_current_timezone()
        self.dogn = '2026-10-02'
        self.start = timezone.make_aware(datetime(2026, 10, 2, 6, 0), tz)
        # Lag 1 og Lag 2 har skift fra _Grunnlag som dekker nå — fjern dem, så
        # tellingen i oktober bare ser det testen setter opp.
        Vaktpost.objects.all().delete()

    def _skift(self, ressurs, fra_t, til_t, **kw):
        return self.Vaktpost.objects.create(
            ressurs=ressurs, mannskap=kw.pop('mannskap', self.person),
            fra_tid=self.start + timedelta(hours=fra_t), til_tid=self.start + timedelta(hours=til_t), **kw)

    def test_doegnet_begynner_ved_doegnstarten_i_portalens_tidssone(self):
        self.assertEqual(program.dogn_start(self.dogn), self.start)
        self.assertIsNone(program.dogn_start('i morgen'))

    def test_midt_i_timen_teller_og_bilen_er_med(self):
        self._skift(self.lag1, 16, 16.25)     # 22:00–22:15 → ikke i 22-timen
        self._skift(self.lag2, 16.25, 18)     # 22:15–24:00 → i 22- og 23-timen
        self._skift(self.bil, 15, 17)         # 21–23, bilen med
        timer = program.paa_vakt_per_time(self.start)
        self.assertEqual(len(timer), 24)
        lag, amb = str(self.lag.pk), str(self.bil.gruppe_id)
        self.assertEqual(timer[16]['grupper'].get(lag), 1, '22-timen: bare Lag 2')
        self.assertEqual(timer[16]['grupper'].get(amb), 1, 'bilen teller, ut fra skiftet')
        self.assertEqual(timer[17]['grupper'].get(lag), 1)
        self.assertIsNone(timer[17]['grupper'].get(amb), 'bilen gikk av 23:00')
        self.assertEqual(timer[0]['fra'], self.start.isoformat())

    def test_ledig_plass_og_avmeldt_teller_ikke(self):
        self._skift(self.lag1, 16, 18, mannskap=None)
        self._skift(self.lag2, 16, 18, avmeldt_at=timezone.now())
        self.assertEqual(program.paa_vakt_per_time(self.start)[16]['grupper'], {})

    def test_samme_regel_som_vaktlista_og_lagene_er_fortsatt_uten_biler(self):
        from vaktliste.services import ressurser_med_skift, ressurser_paa_vakt_naa
        self._skift(self.lag1, 16, 18)
        self._skift(self.bil, 16, 18)
        t = self.start + timedelta(hours=17)
        self.assertEqual({r.pk for r in ressurser_med_skift(self.vl, t)}, {self.lag1.pk, self.bil.pk})
        self.assertEqual({r.pk for r in ressurser_paa_vakt_naa(self.vl, t)}, {self.lag1.pk},
                         'ressursoversiktens lag har fortsatt ingen biler')

    def test_porten_er_vaktlistas_og_doegnet_maa_vaere_en_dato(self):
        url = '/ko/api/program/dekning/'
        uten = _bruker('uten_vl')
        _gi(uten, 'ko', 'les')
        c = Client()
        c.force_login(uten)
        self.assertEqual(c.get(url, {'dogn': self.dogn}).status_code, 403)
        _gi(uten, 'vaktliste', 'les')
        self.assertEqual(c.get(url, {'dogn': 'fredag'}).status_code, 400)
        r = c.get(url, {'dogn': self.dogn})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['data']['timer']), 24)
