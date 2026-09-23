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
        # Artistlista er tom etter `0021`; testene lager sin egen «Headliner».
        self.headliner = Konserttype.objects.create(navn='Headliner')
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

    def test_forslaget_til_kjennetegn_er_lagt_inn_og_typeforslagene_er_borte(self):
        """André: «vi kommer med et forslag som vi kan justere». Pyro først.
        Typeforslagene ble fjernet da typene ble artister (`0021`) — de er
        ikke artister, og sto ubrukt."""
        self.assertEqual(Kjennetegn.objects.order_by('rekkefolge').first().navn, 'Pyro')
        self.assertFalse(Konserttype.objects.filter(navn='Fast post (ikke konsert)').exists())

    def test_et_typeforslag_i_bruk_blir_staaende(self):
        """`0021` fjerner bare de ubrukte: en konsert som peker på «Pop» skal
        ikke miste typen sin."""
        import importlib

        from django.apps import apps
        m = importlib.import_module('ko.migrations.0021_artister_uten_typeforslag')
        pop = Konserttype.objects.create(navn='Pop')
        Konserttype.objects.create(navn='Rock / metal')
        egen = Konserttype.objects.create(navn='Kaizers')
        self._lagre(konserttype_id=pop.pk)
        m.fjern_ubrukte_typeforslag(apps, None)
        # «Headliner» (fra `setUp`) er ubrukt og går også.
        self.assertEqual(sorted(Konserttype.objects.values_list('navn', flat=True)), ['Kaizers', 'Pop'])
        self.assertTrue(Konserttype.objects.filter(pk=egen.pk).exists())

    def test_uten_navn_er_artisten_navnet_og_uten_begge_er_det_en_feil(self):
        post = self._lagre(navn='')
        self.assertEqual(post.navn, 'Headliner')
        with self.assertRaisesRegex(services.Ugyldig, 'artist eller et navn'):
            self._lagre(navn='  ', konserttype_id=None)


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
            'tomt navn uten artist': dict(navn='  ', konserttype_id=None),
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


class HistorikkenTests(_Program):
    """Steg 5: planen husker hva den var — og KO-loggen får en linje bare når
    endringen gjelder noe som pågår eller begynner innen to timer."""

    def _linjer(self):
        from ko.models import Logglinje
        from ko import systemlinjer
        return list(Logglinje.objects.filter(systemkode=systemlinjer.PROGRAM_ENDRET).order_by('id'))

    def test_opprettet_baerer_hele_bildet_og_endret_bare_det_som_endret_seg(self):
        from ko.models import Programendring
        post = self._lagre()
        forste = Programendring.objects.get()
        self.assertEqual(forste.hva, 'opprettet')
        self.assertEqual(forste.detaljer['behov'], f'2 {AMBULANSE}, 4 {LAG}')
        self.assertEqual(forste.detaljer['beredskap'], 'Oransje')
        self._lagre(post=post, beredskap='rod')
        endret = Programendring.objects.order_by('-id').first()
        self.assertEqual(endret.hva, 'endret')
        self.assertEqual(endret.detaljer, [{'felt': 'beredskap', 'fra': 'Oransje', 'til': 'Rød'}])
        self.assertEqual(endret.av_navn, 'kolederen')

    def test_en_lagring_uten_endring_er_ingen_rad(self):
        from ko.models import Programendring
        post = self._lagre()
        self._lagre(post=post)
        self.assertEqual(Programendring.objects.count(), 1)

    def test_flyttet_til_neste_doegn_paa_samme_klokkeslett_er_en_endring(self):
        from ko.models import Programendring
        post = self._lagre()
        self._lagre(post=post, fra=self.fra + timedelta(days=1), til=self.til + timedelta(days=1))
        self.assertEqual(Programendring.objects.order_by('-id').first().detaljer[0]['felt'], 'tid')

    def test_slettet_star_igjen_med_navnet(self):
        from ko.models import Programendring
        post = self._lagre()
        program.slett_post(post, bruker=self.leder)
        rader = list(Programendring.objects.order_by('id'))
        self.assertEqual([r.hva for r in rader], ['opprettet', 'slettet'])
        self.assertTrue(all(r.post_id is None for r in rader), 'posten er borte, historikken står')
        self.assertEqual(rader[1].post_navn, 'Headliner fredag')

    def test_planlegging_langt_fram_gir_ingen_linje_i_ko_loggen(self):
        langt = timezone.now() + timedelta(days=2)
        post = self._lagre(fra=langt, til=langt + timedelta(hours=2))
        self._lagre(post=post, fra=langt, til=langt + timedelta(hours=2), beredskap='rod')
        self.assertEqual(self._linjer(), [])

    def test_i_drift_gir_linje_i_ko_loggen_med_hva_som_endret_seg(self):
        from ko import systemlinjer
        naa = timezone.now()
        post = self._lagre(fra=naa + timedelta(minutes=90), til=naa + timedelta(hours=4))
        self._lagre(post=post, fra=naa + timedelta(minutes=120), til=naa + timedelta(hours=4), beredskap='rod')
        linjer = self._linjer()
        self.assertEqual(len(linjer), 2, 'lagt til og endret — begge innen to timer')
        tekst = systemlinjer.tegn(linjer[1].systemkode, linjer[1].systemdata)
        self.assertIn('Headliner fredag (Parkscene) endret', tekst)
        self.assertIn('beredskap Oransje → Rød', tekst)

    def test_grensen_er_to_timer_foer_start(self):
        naa = timezone.now()
        self.assertTrue(program.i_drift(naa + timedelta(hours=2), naa + timedelta(hours=3), naa))
        self.assertFalse(program.i_drift(naa + timedelta(hours=2, seconds=1), naa + timedelta(hours=3), naa))
        self.assertFalse(program.i_drift(naa - timedelta(hours=1), naa, naa), 'over er over')

    def test_en_konsert_i_drift_flyttet_langt_fram_loftes_likevel(self):
        """Å utsette noe som skulle begynt om en time, er nettopp det loggen skal si."""
        naa = timezone.now()
        post = self._lagre(fra=naa + timedelta(minutes=30), til=naa + timedelta(hours=2))
        self._lagre(post=post, fra=naa + timedelta(days=1), til=naa + timedelta(days=1, hours=2))
        self.assertEqual(len(self._linjer()), 2)

    def test_sletting_i_drift_loftes(self):
        naa = timezone.now()
        post = self._lagre(fra=naa + timedelta(minutes=30), til=naa + timedelta(hours=2))
        program.slett_post(post, bruker=self.leder)
        self.assertEqual(len(self._linjer()), 2)


class PlanMotFaktiskTests(_Program):

    def setUp(self):
        super().setUp()
        self.naa = timezone.now()
        self.fra = self.naa - timedelta(hours=2)
        self.til = self.naa - timedelta(hours=1)

    def _sto(self, ressurs, fra_min, til_min, lokasjon=None, **kw):
        return Tavleplassering.objects.create(
            vakt=self.vakt, ressurs=ressurs, ressurs_navn=ressurs.navn, lokasjon=lokasjon or self.park,
            lokasjon_navn=(lokasjon or self.park).navn, fra=self.fra + timedelta(minutes=fra_min),
            til=self.fra + timedelta(minutes=til_min) if til_min is not None else None, **kw)

    def _rad(self, **kw):
        return next(r for r in program.plan_mot_faktisk(self.vakt, self.naa) if r['navn'] == kw.get('navn', 'Headliner fredag'))

    def test_snitt_og_minutter_under_behovet(self):
        self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 2}])
        self._sto(self.lag1, 0, 60)      # hele timen
        self._sto(self.lag2, 30, 60)     # andre halvtime
        self._sto(self.lag2, 0, 60, lokasjon=self.club)  # et annet sted teller ikke
        b = self._rad()['behov'][0]
        self.assertEqual(b['snitt'], 1.5)
        self.assertEqual(b['under_min'], 30)

    def test_bare_gruppa_teller_og_pause_teller_ikke(self):
        self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 1}, {'gruppe_id': self.bil.gruppe_id, 'antall': 1}])
        self._sto(self.bil, 0, 60)
        self._sto(self.lag1, 0, 60, pause=True)   # på stedet, men i pause
        rad = self._rad()
        lag = next(b for b in rad['behov'] if b['gruppe_navn'] == LAG)
        amb = next(b for b in rad['behov'] if b['gruppe_navn'] == self.bil.gruppe.navn)
        self.assertEqual((lag['snitt'], lag['under_min']), (0.0, 60))
        self.assertEqual((amb['snitt'], amb['under_min']), (1.0, 0))

    def test_en_aapen_plassering_teller_fram_til_naa_og_en_som_paagaar_regnes_til_naa(self):
        self.fra, self.til = self.naa - timedelta(hours=1), self.naa + timedelta(hours=1)
        self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 1}])
        self._sto(self.lag1, 30, None)
        b = self._rad()['behov'][0]
        self.assertEqual((b['snitt'], b['under_min']), (0.5, 30))

    def test_ikke_begynt_har_ikke_noe_faktisk(self):
        self.fra, self.til = self.naa + timedelta(hours=1), self.naa + timedelta(hours=2)
        self._lagre()
        rad = self._rad()
        self.assertFalse(rad['startet'])
        self.assertIsNone(rad['behov'][0]['snitt'])
        self.assertIsNone(rad['oppdrag'])

    def test_gruppa_matches_paa_navnet_naar_pekeren_er_borte(self):
        post = self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 1}])
        post.behov.update(gruppe=None)
        self._sto(self.lag1, 0, 60)
        self._sto(self.bil, 0, 60)
        self.assertEqual(self._rad()['behov'][0]['snitt'], 1.0, 'bare laget — aldri «alle»')

    def test_opprinnelig_behov_og_antall_endringer(self):
        post = self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 4}])
        self._lagre(post=post, behov=[{'gruppe_id': self.lag.pk, 'antall': 5}])
        self._lagre(post=post, behov=[{'gruppe_id': self.lag.pk, 'antall': 5}], beredskap='rod')
        rad = self._rad()
        self.assertEqual(rad['behov_opprinnelig'], f'4 {LAG}')
        self.assertEqual(rad['behov_naa'], f'5 {LAG}')
        self.assertEqual(rad['endringer'], 2)

    def test_oppdrag_paa_stedet_mens_konserten_paagikk(self):
        from oppdrag.models import Oppdrag
        from oppdrag.services import neste_oppdragsnummer
        self.fra, self.til = self.naa - timedelta(minutes=5), self.naa + timedelta(hours=1)
        self._lagre()
        for sted in (self.park, self.park, self.club):
            Oppdrag.objects.create(vakt=self.vakt, oppdragsnummer=neste_oppdragsnummer(self.vakt),
                                   problemstilling='Fall', hastegrad='Akutt', lokasjon=sted)
        self.assertEqual(self._rad()['oppdrag'], 2)

    def test_en_plassering_fra_foer_konserten_klippes_ved_start(self):
        self._lagre(behov=[{'gruppe_id': self.lag.pk, 'antall': 1}])
        self._sto(self.lag1, -30, 60)    # sto der en halvtime før konserten
        self.assertEqual(self._rad()['behov'][0]['snitt'], 1.0)

    def test_oppdrag_foer_konserten_teller_ikke(self):
        from oppdrag.models import Oppdrag
        from oppdrag.services import neste_oppdragsnummer
        self.fra, self.til = self.naa - timedelta(minutes=5), self.naa + timedelta(hours=1)
        self._lagre()
        for _ in range(2):
            o = Oppdrag.objects.create(vakt=self.vakt, oppdragsnummer=neste_oppdragsnummer(self.vakt),
                                       problemstilling='Fall', hastegrad='Akutt', lokasjon=self.park)
        Oppdrag.objects.filter(pk=o.pk).update(created_at=self.fra - timedelta(minutes=1))
        self.assertEqual(self._rad()['oppdrag'], 1)

    def test_arkivert_teller_per_oppdragsnummer_og_kollapset_er_ukjent(self):
        from oppdrag.models import ArkivertOppdrag, OppdragArkiv
        self._lagre()
        arkiv = OppdragArkiv.objects.create(tittel='A', vakt=self.vakt, vakt_navn='v', antall_rader=3)
        inne = self.fra + timedelta(minutes=10)
        # Én rad per oppdrag *og enhet* — oppdrag 1 hadde to biler.
        for nr, enhet, sted, t in ((1, 'A1', 'Parkscene', inne), (1, 'A2', 'Parkscene', inne),
                                   (2, 'A1', 'Parkscene', inne), (3, 'A1', 'Club', inne),
                                   (4, 'A1', 'Parkscene', self.fra - timedelta(minutes=1))):
            ArkivertOppdrag.objects.create(arkiv=arkiv, oppdragsnummer=nr, enhet_navn=enhet, lokasjon_navn=sted,
                                           opprettet_at=t)
        self.assertEqual(self.park.navn, 'Parkscene')
        self.assertEqual(self._rad()['oppdrag'], 2, 'oppdrag 1 to ganger er ett oppdrag')
        OppdragArkiv.objects.filter(pk=arkiv.pk).update(kollapset_at=self.naa)
        self.assertIsNone(self._rad()['oppdrag'], 'radene er borte — null ville vært en påstand')

    def test_dekket_helt_enkelt(self):
        t0 = self.naa
        t = lambda m: t0 + timedelta(minutes=m)
        self.assertEqual(program._dekket([], t(0), t(60), 1), (0.0, 60))
        self.assertEqual(program._dekket([(t(0), t(60)), (t(0), t(60))], t(0), t(60), 2), (2.0, 0))
        self.assertEqual(program._dekket([(t(0), t(30))], t(0), t(60), 0), (0.5, 0), 'null trengs er aldri under')
        self.assertEqual(program._dekket([], t(0), t(0), 1), (None, 0))


class KopierProgrammetTests(_Program):

    def setUp(self):
        super().setUp()
        from datetime import date
        from core.models import Vakt
        self.i_fjor = Vakt.objects.create(navn='Vakt 2025', year=2025, startet=timezone.now() - timedelta(days=365))
        tz = timezone.get_current_timezone()
        from datetime import datetime
        self.fredag = timezone.make_aware(datetime(2025, 9, 26, 22, 0), tz)
        program.lagre_post(self.i_fjor, self._data(), fra=self.fredag, til=self.fredag + timedelta(hours=2),
                           bruker=self.leder)
        program.lagre_post(self.i_fjor, self._data(navn='Natt', lokasjon_id=self.club.pk),
                           fra=self.fredag + timedelta(hours=4), til=self.fredag + timedelta(hours=5), bruker=self.leder)
        self.maal = date(2026, 9, 25)

    def test_flyttet_i_hele_doegn_og_klokkeslettene_staar(self):
        svar = program.kopier_program(self.i_fjor, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        self.assertEqual((svar['kopiert'], svar['hoppet_over']), (2, []))
        poster = list(Programpost.objects.filter(vakt=self.vakt).order_by('fra'))
        self.assertEqual([timezone.localtime(p.fra).strftime('%d.%m %H:%M') for p in poster],
                         ['25.09 22:00', '26.09 02:00'], 'natta etter følger med')
        self.assertEqual(sorted(poster[0].behov.values_list('gruppe_navn', 'antall')),
                         sorted([(LAG, 4), (AMBULANSE, 2)]))
        self.assertEqual(poster[0].beredskap, 'oransje')
        self.assertEqual(list(poster[0].kjennetegn.values_list('navn', flat=True)), ['Pyro'])

    def test_stedet_finnes_paa_navnet_og_et_borte_sted_nevnes(self):
        from ko.models import Programpost as PP
        PP.objects.filter(vakt=self.i_fjor, navn='Natt').update(lokasjon=None)
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False)
        ny = Lokasjon.objects.create(navn='Parkscene 2026')
        PP.objects.filter(vakt=self.i_fjor, navn='Headliner fredag').update(lokasjon=None, lokasjon_navn='Parkscene 2026')
        svar = program.kopier_program(self.i_fjor, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        self.assertEqual(svar['kopiert'], 2)
        self.assertEqual(Programpost.objects.get(vakt=self.vakt, navn='Headliner fredag').lokasjon, ny)
        Lokasjon.objects.filter(pk=ny.pk).update(er_aktiv=False)
        svar = program.kopier_program(self.i_fjor, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        self.assertEqual(svar['kopiert'], 1)
        self.assertIn('Headliner fredag', svar['hoppet_over'][0])

    def test_natta_etter_hoerer_til_doegnet_foer(self):
        """Første konsert kl. 05:30 hører til døgnet før (døgnstart 06:00) — den
        skal lande natt til dagen etter `forste_dogn`, ikke på selve datoen.
        05:30 og ikke 01:30: 01:30 er 23:30 UTC dagen før, og da ville en
        `.date()` på tidspunktet tilfeldigvis truffet riktig døgn."""
        from core.models import Vakt
        from datetime import datetime
        natt = timezone.make_aware(datetime(2025, 9, 27, 5, 30), timezone.get_current_timezone())
        v = Vakt.objects.create(navn='Natt 2025', year=2025, startet=natt)
        program.lagre_post(v, self._data(navn='Nattkonsert'), fra=natt, til=natt + timedelta(hours=1), bruker=self.leder)
        program.kopier_program(v, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        post = Programpost.objects.get(vakt=self.vakt, navn='Nattkonsert')
        self.assertEqual(timezone.localtime(post.fra).strftime('%d.%m %H:%M'), '26.09 05:30')

    def test_et_inaktivt_sted_paa_id_viker_for_et_aktivt_med_samme_navn(self):
        Lokasjon.objects.filter(pk=self.park.pk).update(er_aktiv=False, navn='Parkscene (gammel)')
        ny = Lokasjon.objects.create(navn=self.park.navn)
        svar = program.kopier_program(self.i_fjor, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        self.assertEqual(svar['hoppet_over'], [])
        self.assertEqual(Programpost.objects.get(vakt=self.vakt, navn='Headliner fredag').lokasjon, ny)

    def test_en_gruppe_som_er_borte_nevnes_og_resten_av_behovet_kommer_med(self):
        from vaktliste.models import Ressursgruppe
        Ressursgruppe.objects.filter(pk=self.amb.pk).update(er_aktiv=False)
        svar = program.kopier_program(self.i_fjor, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        self.assertEqual(svar['kopiert'], 2)
        self.assertEqual([h for h in svar['hoppet_over'] if AMBULANSE in h],
                         [f'{n} — behovet for «{AMBULANSE}» er ikke med, gruppa finnes ikke'
                          for n in ('Headliner fredag', 'Natt')])
        post = Programpost.objects.get(vakt=self.vakt, navn='Headliner fredag')
        self.assertEqual(list(post.behov.values_list('gruppe_navn', flat=True)), [LAG])

    def test_tomt_program_er_en_feil_og_kopien_har_historikk(self):
        from core.models import Vakt
        from ko.models import Programendring
        tom = Vakt.objects.create(navn='Tom', year=2024, startet=timezone.now())
        with self.assertRaises(services.Ugyldig):
            program.kopier_program(tom, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        program.kopier_program(self.i_fjor, self.vakt, forste_dogn=self.maal, bruker=self.leder)
        self.assertEqual(Programendring.objects.filter(vakt=self.vakt, hva='opprettet').count(), 2)


class Steg5PorteneTests(PorteneTests):

    def test_etterpaa_aktiv_for_les_tidligere_for_lederen(self):
        from core.models import Vakt
        self._lagre()
        r = self._klient('les').get('/ko/api/program/etterpaa/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['data']['poster']), 1)
        self.assertEqual(r.json()['data']['vakter'], [], 'vaktvelgeren er lederens')
        gammel = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now() - timedelta(days=365))
        self.assertEqual(self._klient('skriv_full').get('/ko/api/program/etterpaa/', {'vakt': gammel.pk}).status_code, 403)
        leder = self._klient('skriv_leder')
        self.assertEqual(leder.get('/ko/api/program/etterpaa/', {'vakt': gammel.pk}).status_code, 200)
        self.assertEqual(leder.get('/ko/api/program/etterpaa/', {'vakt': 99999}).status_code, 404)

    def test_kopier_er_lederens_og_spor_foer_den_legger_til(self):
        from core.models import Vakt
        gammel = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now() - timedelta(days=365))
        program.lagre_post(gammel, self._data(), fra=self.fra, til=self.til, bruker=self.leder)
        url = '/ko/api/program/kopier/'
        kropp = {'fra_vakt_id': gammel.pk, 'forste_dogn': '2026-09-25'}
        self.assertEqual(self._klient('skriv_full').post(url, kropp, content_type='application/json').status_code, 403)
        c = self._klient('skriv_leder')
        self.assertEqual(c.post(url, dict(kropp, forste_dogn='fredag'), content_type='application/json').status_code, 400)
        self.assertEqual(c.post(url, dict(kropp, fra_vakt_id=self.vakt.pk),
                                content_type='application/json').status_code, 400, 'ikke fra seg selv')
        self.assertEqual(c.post(url, kropp, content_type='application/json').status_code, 200)
        r = c.post(url, kropp, content_type='application/json')
        self.assertEqual(r.status_code, 409, 'vakta har alt et program')
        self.assertEqual(r.json()['antall'], 1)
        self.assertEqual(c.post(url, dict(kropp, confirm=True), content_type='application/json').status_code, 200)
        self.assertEqual(Programpost.objects.filter(vakt=self.vakt).count(), 2)
        self.assertEqual(c.post(url, dict(kropp, fra_vakt_id=self.vakt.pk, confirm=True),
                                content_type='application/json').status_code, 400,
                         'ikke fra seg selv — også når vakta har et program å kopiere')
        self.assertEqual(Programpost.objects.filter(vakt=self.vakt).count(), 2)
