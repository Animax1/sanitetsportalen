# -*- coding: utf-8 -*-
"""Avtalte pauser i vaktlista (23. sep. 2026).

André: «vi har planer om å hente avtalte pauser fra /vaktliste». Svarene:
per lag/ressurs, teller i timene, lederens, synlig for mannskapet men admin
kan skjule, og en regel i planleggeren nå.
"""
from core.models import AppSetting

from . import fil, pauser, services
from .models import Pause, Vaktpost
from .tests_planlegger import kl
from .tests_tilgang import TilgangsBasis


class _Pauser(TilgangsBasis):

    def setUp(self):
        super().setUp()
        self.r = self.res_hgsd
        # To skift som møtes: 14–22 og 22–06. Pausen kan ligge over byttet.
        Vaktpost.objects.create(ressurs=self.r, fra_tid=kl(2, 14), til_tid=kl(2, 22))
        Vaktpost.objects.create(ressurs=self.r, fra_tid=kl(2, 22), til_tid=kl(3, 6))


class PausereglerTests(_Pauser):

    def test_innenfor_skiftene_ogsaa_over_et_skiftbytte(self):
        p = pauser.lagre(self.r, kl(2, 21, 45), kl(2, 22, 15))
        self.assertFalse(p.fra_regel)
        with self.assertRaisesRegex(pauser.Ugyldig, 'innenfor skiftene'):
            pauser.lagre(self.r, kl(2, 13, 45), kl(2, 14, 15))
        with self.assertRaisesRegex(pauser.Ugyldig, 'innenfor skiftene'):
            pauser.lagre(self.r, kl(3, 5, 45), kl(3, 6, 15))

    def test_grensene_er_skiftets_egne(self):
        pauser.lagre(self.r, kl(2, 14), kl(2, 14, 30))
        pauser.lagre(self.r, kl(3, 5, 30), kl(3, 6))

    def test_en_annen_ressurs_sine_skift_teller_ikke(self):
        Vaktpost.objects.create(ressurs=self.res_karmoy, fra_tid=kl(4, 14), til_tid=kl(4, 22))
        with self.assertRaises(pauser.Ugyldig):
            pauser.lagre(self.r, kl(4, 16), kl(4, 16, 30))

    def test_hoeyst_fire_timer_og_til_etter_fra(self):
        pauser.lagre(self.r, kl(2, 15), kl(2, 19))
        with self.assertRaisesRegex(pauser.Ugyldig, 'fire timer'):
            pauser.lagre(self.r, kl(2, 22), kl(3, 2, 5))
        with self.assertRaisesRegex(pauser.Ugyldig, '«Til»'):
            pauser.lagre(self.r, kl(2, 23), kl(2, 23))
        with self.assertRaisesRegex(pauser.Ugyldig, 'både fra og til'):
            pauser.lagre(self.r, None, kl(2, 23))

    def test_aldri_to_over_hverandre_men_inntil_gaar(self):
        p = pauser.lagre(self.r, kl(2, 18), kl(2, 18, 30))
        with self.assertRaisesRegex(pauser.Ugyldig, 'alt en pause 18:00–18:30'):
            pauser.lagre(self.r, kl(2, 18, 15), kl(2, 18, 45))
        pauser.lagre(self.r, kl(2, 18, 30), kl(2, 19))
        pauser.lagre(self.r, kl(2, 17, 30), kl(2, 18))   # inntil foran går også
        # En annen ressurs sin pause på samme tid sperrer ikke.
        Vaktpost.objects.create(ressurs=self.res_karmoy, fra_tid=kl(2, 14), til_tid=kl(2, 22))
        pauser.lagre(self.res_karmoy, kl(2, 18), kl(2, 18, 30))
        # Å flytte den ene overlapper ikke seg selv.
        pauser.lagre(self.r, kl(2, 18, 5), kl(2, 18, 25), pause=p)

    def test_en_regelpause_som_rettes_blir_lederens(self):
        p = Pause.objects.create(ressurs=self.r, fra=kl(2, 18), til=kl(2, 18, 30), fra_regel=True)
        pauser.lagre(self.r, kl(2, 19), kl(2, 19, 30), pause=p)
        p.refresh_from_db()
        self.assertFalse(p.fra_regel)
        self.assertEqual(p.fra, kl(2, 19))

    def test_pausen_teller_i_timene(self):
        """André: «ja» — ingen fratrekk. Belastningen er den samme før og etter."""
        foer = services.planleggingstall(self.vl)
        pauser.lagre(self.r, kl(2, 18), kl(2, 19))
        self.assertEqual(services.planleggingstall(self.vl), foer)


class PauseportTests(_Pauser):

    def _post(self, c, fra=None, til=None):
        return c.post(f'/vaktliste/api/ressurser/{self.r.pk}/pauser/',
                      {'fra': (fra or kl(2, 18)).isoformat(), 'til': (til or kl(2, 18, 30)).isoformat()},
                      content_type='application/json')

    def test_lederen_legger_inn_og_andre_faar_403(self):
        for navn, c in (('les', self.c_leser), ('skriv_handling', self.c_kb), ('skriv_full', self.c_vl)):
            with self.subTest(konto=navn):
                self.assertEqual(self._post(c).status_code, 403)
        self.assertFalse(Pause.objects.exists())
        r = self._post(self.c_leder)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['data']['ressurs_id'], self.r.pk)
        self.assertEqual(self._post(self.c_adm, kl(2, 19), kl(2, 19, 30)).status_code, 201)

    def test_feil_er_400_med_meldingen_og_ukjent_er_404(self):
        r = self._post(self.c_leder, kl(2, 12), kl(2, 12, 30))
        self.assertEqual(r.status_code, 400)
        self.assertIn('innenfor skiftene', r.json()['message'])
        self.assertEqual(self.c_leder.post('/vaktliste/api/ressurser/99999/pauser/', {},
                                           content_type='application/json').status_code, 404)

    def test_flytt_og_fjern_er_lederens(self):
        p = pauser.lagre(self.r, kl(2, 18), kl(2, 18, 30))
        url = f'/vaktliste/api/pauser/{p.pk}/'
        kropp = {'fra': kl(2, 19).isoformat(), 'til': kl(2, 19, 30).isoformat()}
        self.assertEqual(self.c_vl.put(url, kropp, content_type='application/json').status_code, 403)
        self.assertEqual(self.c_vl.delete(url).status_code, 403)
        self.assertEqual(self.c_leder.put(url, kropp, content_type='application/json').status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.fra, kl(2, 19))
        self.assertEqual(self.c_leder.delete(url).status_code, 200)
        self.assertFalse(Pause.objects.exists())
        self.assertEqual(self.c_leder.delete(url).status_code, 404)

    def test_lista_sender_pausene_til_alle_som_ser_den(self):
        pauser.lagre(self.r, kl(2, 18), kl(2, 18, 30))
        data = self.c_leser.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/').json()['data']
        self.assertEqual([p['ressurs_id'] for p in data['pauser']], [self.r.pk])
        self.assertTrue(data['vaktliste']['pauser_paa_utskrift'])

    def test_pausene_auditlogges(self):
        from audit.models import AuditLog
        p = pauser.lagre(self.r, kl(2, 18), kl(2, 18, 30))
        pauser.lagre(self.r, kl(2, 19), kl(2, 19, 30), pause=p)
        pauser.slett(p)
        self.assertEqual(
            list(AuditLog.objects.filter(table_name='vaktliste_pause').values_list('action', flat=True)
                 .order_by('id')),
            ['CREATE', 'UPDATE', 'UPDATE', 'DELETE'])


class RegelpauseTests(TilgangsBasis):
    """`pauser.regelpause` og `les_regel`: regelen alene."""

    def test_etter_og_lengde_og_forskyvningen(self):
        self.assertEqual(pauser.regelpause(kl(2, 14), kl(2, 22), etter_min=240, lengde_min=30),
                         (kl(2, 18), kl(2, 18, 30)))
        self.assertEqual(pauser.regelpause(kl(2, 14), kl(2, 22), etter_min=240, lengde_min=30, indeks=2),
                         (kl(2, 19), kl(2, 19, 30)))

    def test_for_kort_skift_faar_ingen_pause_men_akkurat_nok_faar(self):
        self.assertIsNone(pauser.regelpause(kl(2, 14), kl(2, 18, 29), etter_min=240, lengde_min=30))
        self.assertEqual(pauser.regelpause(kl(2, 14), kl(2, 18, 30), etter_min=240, lengde_min=30),
                         (kl(2, 18), kl(2, 18, 30)))

    def test_forskjoevet_ut_av_skiftet_er_en_feil_ikke_en_utelatelse(self):
        pauser.regelpause(kl(2, 14), kl(2, 22), etter_min=240, lengde_min=60, indeks=3)
        with self.assertRaisesRegex(services.Planleggerfeil, 'får ikke plass'):
            pauser.regelpause(kl(2, 14), kl(2, 22), etter_min=240, lengde_min=60, indeks=4)

    def test_les_regel(self):
        self.assertIsNone(pauser.les_regel({}))
        self.assertIsNone(pauser.les_regel({'pause_min': '', 'pause_etter_min': ''}))
        self.assertEqual(pauser.les_regel({'pause_min': '30', 'pause_etter_min': 240}), (240, 30, True))
        self.assertEqual(pauser.les_regel({'pause_min': 30, 'pause_etter_min': 0, 'pause_forskyv': False}),
                         (0, 30, False))
        for halv in ({'pause_min': 30}, {'pause_etter_min': 240}, {'pause_min': 30, 'pause_etter_min': ''}):
            with self.subTest(halv=halv), self.assertRaisesRegex(services.Planleggerfeil, 'både lengde'):
                pauser.les_regel(halv)
        for feil in ({'pause_min': 30}, {'pause_etter_min': 240}, {'pause_min': 'x', 'pause_etter_min': 1},
                     {'pause_min': 4, 'pause_etter_min': 1}, {'pause_min': 241, 'pause_etter_min': 1},
                     {'pause_min': 30, 'pause_etter_min': -1}, {'pause_min': 30, 'pause_etter_min': 24 * 60 + 1}):
            with self.subTest(feil=feil), self.assertRaises(services.Planleggerfeil):
                pauser.les_regel(feil)
        self.assertEqual(pauser.les_regel({'pause_min': 5, 'pause_etter_min': 24 * 60})[:2], (24 * 60, 5))
        self.assertEqual(pauser.les_regel({'pause_min': 240, 'pause_etter_min': 0})[1], 240)


class PlanleggerensPauseregelTests(TilgangsBasis):
    """Regelen gjennom `generer_grunnlag` — den ekte inngangen."""

    def setUp(self):
        super().setUp()
        self.vl2 = services.opprett_planlagt_vakt('Vakt 2')
        from .test_helpers import gruppe
        from .test_helpers import LAG
        self.lag = gruppe(LAG)

    def _linje(self, **kw):
        linje = {'gruppe_id': self.lag.pk, 'antall': 3,
                 'vinduer': [{'fra': kl(2, 14), 'til': kl(2, 22), 'plasser': 4}],
                 'pause_min': 30, 'pause_etter_min': 240}
        linje.update(kw)
        return linje

    def _pauser(self):
        return {r.navn: [(p.fra, p.til, p.fra_regel) for p in r.pauser.all()]
                for r in self.vl2.ressurser.order_by('navn')}

    def test_tre_lag_tar_pause_etter_hverandre(self):
        svar = services.generer_grunnlag(self.vl2, [self._linje()])
        self.assertEqual(svar['pauser'], 3)
        self.assertEqual(self._pauser(), {
            'Lag 1': [(kl(2, 18), kl(2, 18, 30), True)],
            'Lag 2': [(kl(2, 18, 30), kl(2, 19), True)],
            'Lag 3': [(kl(2, 19), kl(2, 19, 30), True)],
        })
        r = self.vl2.ressurser.get(navn='Lag 2')
        self.assertEqual((r.pause_etter_min, r.pause_min, r.pause_forskyv), (240, 30, True))

    def test_samtidig_naar_forskyvningen_er_av(self):
        services.generer_grunnlag(self.vl2, [self._linje(pause_forskyv=False)])
        self.assertEqual({v[0][0] for v in self._pauser().values()}, {kl(2, 18)})
        self.assertEqual(set(self.vl2.ressurser.values_list('pause_forskyv', flat=True)), {False})

    def test_et_forskjoevet_lag_legger_seg_etter_dem_paa_samtidig(self):
        """To lag på «samtidig» tar 18:00; det forskjøvne tar neste ledige."""
        services.generer_grunnlag(self.vl2, [self._linje(antall=2, pause_forskyv=False),
                                             self._linje(antall=1)])
        self.assertEqual(sorted(v[0][0] for v in self._pauser().values()),
                         [kl(2, 18), kl(2, 18), kl(2, 19)])

    def test_forskyvningen_telles_paa_tvers_av_linjene_saa_tilbakelesingen_holder(self):
        """Leses oppsettet tilbake, er hvert lag sin egen linje. Da skal lag to
        fortsatt ta pause etter lag én, ikke samtidig."""
        services.generer_grunnlag(self.vl2, [self._linje()])
        linjer = [{'ressurs_id': r.pk, 'vinduer': [{'fra': kl(2, 14), 'til': kl(2, 22), 'plasser': 4}],
                   'pause_min': 30, 'pause_etter_min': 240}
                  for r in self.vl2.ressurser.order_by('rekkefolge')]
        foer = self._pauser()
        services.generer_grunnlag(self.vl2, linjer)
        self.assertEqual(self._pauser(), foer)

    def test_en_annen_gruppe_og_en_annen_skiftstart_forskyves_ikke_sammen(self):
        from .test_helpers import AMBULANSE
        from .test_helpers import gruppe
        services.generer_grunnlag(self.vl2, [
            self._linje(antall=1),
            self._linje(antall=1, gruppe_id=gruppe(AMBULANSE).pk),
            self._linje(antall=1, vinduer=[{'fra': kl(2, 15), 'til': kl(2, 23), 'plasser': 2}]),
        ])
        starter = sorted(v[0][0] for v in self._pauser().values())
        self.assertEqual(starter, [kl(2, 18), kl(2, 18), kl(2, 19)])

    def test_regenerering_lager_regelpausene_paa_nytt_og_lar_lederens_staa(self):
        services.generer_grunnlag(self.vl2, [self._linje(antall=1)])
        r = self.vl2.ressurser.get()
        egen = pauser.lagre(r, kl(2, 20), kl(2, 20, 30))
        linje = {'ressurs_id': r.pk, 'vinduer': [{'fra': kl(2, 14), 'til': kl(2, 22), 'plasser': 4}],
                 'pause_min': 30, 'pause_etter_min': 300}
        services.generer_grunnlag(self.vl2, [linje])
        self.assertEqual(self._pauser()['Lag 1'],
                         [(kl(2, 19), kl(2, 19, 30), True), (kl(2, 20), kl(2, 20, 30), False)])
        self.assertTrue(Pause.objects.filter(pk=egen.pk).exists())
        # Regelen tatt bort: regelpausene går, lederens står.
        services.generer_grunnlag(self.vl2, [dict(linje, pause_min='', pause_etter_min='')])
        self.assertEqual(self._pauser()['Lag 1'], [(kl(2, 20), kl(2, 20, 30), False)])
        r.refresh_from_db()
        self.assertIsNone(r.pause_min)

    def test_en_regelpause_oppaa_lederens_hoppes_over(self):
        services.generer_grunnlag(self.vl2, [self._linje(antall=1)])
        r = self.vl2.ressurser.get()
        Pause.objects.filter(ressurs=r).delete()
        pauser.lagre(r, kl(2, 18, 15), kl(2, 18, 45))
        linje = {'ressurs_id': r.pk, 'vinduer': [{'fra': kl(2, 14), 'til': kl(2, 22), 'plasser': 4}],
                 'pause_min': 30, 'pause_etter_min': 240}
        self.assertEqual(services.forhaandsvis_grunnlag(self.vl2, [linje])['pauser'], 0)
        services.generer_grunnlag(self.vl2, [linje])
        self.assertEqual(self._pauser()['Lag 1'], [(kl(2, 18, 15), kl(2, 18, 45), False)])

    def test_forhaandsvisningen_skriver_ingenting(self):
        svar = services.forhaandsvis_grunnlag(self.vl2, [self._linje()])
        self.assertEqual((svar['pauser'], [ln['pauser'] for ln in svar['linjer']]), (3, [1, 1, 1]))
        self.assertFalse(Pause.objects.exists())

    def test_ugyldig_regel_gjennom_viewet_er_400_og_skriver_ingenting(self):
        r = self.c_leder.post(f'/vaktliste/api/vaktlister/{self.vl2.pk}/generer/', {'linjer': [
            {'gruppe_id': self.lag.pk, 'vinduer': [{'fra': kl(2, 14).isoformat(), 'til': kl(2, 22).isoformat()}],
             'pause_min': 30}]}, content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.vl2.ressurser.exists())

    def test_viewet_sender_regelen_videre(self):
        r = self.c_leder.post(f'/vaktliste/api/vaktlister/{self.vl2.pk}/generer/', {'linjer': [
            {'gruppe_id': self.lag.pk, 'antall': 2,
             'vinduer': [{'fra': kl(2, 14).isoformat(), 'til': kl(2, 22).isoformat(), 'plasser': 1}],
             'pause_min': 30, 'pause_etter_min': 240, 'pause_forskyv': False}]}, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({v[0][0] for v in self._pauser().values()}, {kl(2, 18)})


class PausenePaaEpostTests(_Pauser):

    def test_fila_viser_pausene_til_admin_skjuler_dem(self):
        pauser.lagre(self.r, kl(2, 18), kl(2, 18, 30))
        Vaktpost.objects.create(ressurs=self.res_karmoy, fra_tid=kl(2, 14), til_tid=kl(2, 22))
        ressurser = {r['navn']: r for g in fil.rader_for(self.vl) for r in g['ressurser']}
        self.assertEqual(ressurser['Lag HGSD']['pauser'], ['02.10 18:00–18:30'])
        self.assertEqual(ressurser['Lag Karmøy']['pauser'], [])
        self.assertIn('Pause: 02.10 18:00–18:30', fil.bygg_fil(self.vl))
        AppSetting.set(pauser.VIS_NOKKEL, '0')
        self.assertNotIn('Pause:', fil.bygg_fil(self.vl))
        self.assertFalse(self.c_leser.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/')
                         .json()['data']['vaktliste']['pauser_paa_utskrift'])

    def test_en_annen_vaktlistes_pauser_er_ikke_med(self):
        annen = services.opprett_planlagt_vakt('Annen')
        from .test_helpers import lag_ressurs
        r = lag_ressurs(vaktliste=annen, navn='Lag HGSD')
        Pause.objects.create(ressurs=r, fra=kl(2, 18), til=kl(2, 18, 30))
        ressurser = {x['navn']: x for g in fil.rader_for(self.vl) for x in g['ressurser']}
        self.assertEqual(ressurser['Lag HGSD']['pauser'], [])

    def test_innstillingen_lagres_fra_portalinnstillingene(self):
        from .portalinnstillinger import VaktlistefilInnstillinger
        h = VaktlistefilInnstillinger()
        self.assertTrue(h.kontekst()['vaktliste_vis_pauser'])
        h.lagre(h.valider({}))
        self.assertFalse(pauser.vises_for_mannskapet())
        h.lagre(h.valider({'vaktliste_vis_pauser': '1'}))
        self.assertTrue(pauser.vises_for_mannskapet())

    def test_en_pause_endrer_signaturen_saa_fila_sendes_paa_nytt(self):
        foer = fil.signatur(fil.rader_for(self.vl))
        pauser.lagre(self.r, kl(2, 18), kl(2, 18, 30))
        self.assertNotEqual(fil.signatur(fil.rader_for(self.vl)), foer)

    def test_timeoversikten_er_uendret(self):
        rader = services.belastning_per_person(self.vl)
        pauser.lagre(self.r, kl(2, 18), kl(2, 19))
        self.assertEqual(services.belastning_per_person(self.vl), rader)

