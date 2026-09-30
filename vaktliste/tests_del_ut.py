"""«Del ut» som navngitt handling (pulje 4, 30. sep. 2026).

Utdelingen fantes — å sette reservasjonen *er* å dele ut — men sto ikke på
skjermen, og den hadde to terskler: `skriv_leder` for enheten, `skriv_full` for
plassen. André: «de kan begge ha likt». Og et hull: tømte lederen enhetens
reservasjon, ble plassene som arvet den kladd igjen og forsvant fra korpset.
André: «er det ikke greit å ha ledig for alle slik at en ser hva som noen korps
ikke kunne ta og dermed kan noen andre sikre seg det?»
"""
from __future__ import annotations

import json
from datetime import timedelta

from audit.models import AuditLog

from . import services
from .models import Ressurs, Vaktpost
from .test_helpers import LAG, gruppe, lag_ressurs
from .tests_tilgang import TilgangsBasis


class Basis(TilgangsBasis):

    def setUp(self):
        super().setUp()
        self.til = self.na + timedelta(hours=8)
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Karmøy 51', gruppe=gruppe(LAG))
        self.kladd = [self._plass() for _ in range(3)]
        self.til_hgsd = self._plass(korps=self.hgsd)
        self.aapen = self._plass(alle_korps=True)
        self.bemannet = self._plass(mannskap=self.p_karmoy)

    def _plass(self, ressurs=None, **felt):
        return Vaktpost.objects.create(ressurs=ressurs or self.bil, fra_tid=self.na,
                                       til_tid=self.til, **felt)

    def _del_ut(self, klient, *rader):
        return klient.post(f'/vaktliste/api/vaktlister/{self.vl.pk}/del-ut/',
                           data=json.dumps({'fordeling': list(rader)}),
                           content_type='application/json')

    def _kladd(self, ressurs=None):
        return services.ikke_delt_ut(ressurs or self.bil).count()


class DelUtTests(Basis):

    def test_til_et_korps_blir_kladden_korpsets(self):
        res = self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'korps_id': self.karmoy.pk})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['delt_ut'], 3)
        self.assertEqual(self._kladd(), 0)
        for vp in self.kladd:
            vp.refresh_from_db()
            self.assertEqual(services.reservert_korps(vaktpost=vp), self.karmoy.pk)

    def test_det_som_er_delt_ut_eller_bemannet_star(self):
        self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'korps_id': self.karmoy.pk})
        self.til_hgsd.refresh_from_db()
        self.aapen.refresh_from_db()
        self.assertEqual(services.reservert_korps(vaktpost=self.til_hgsd), self.hgsd.pk)
        self.assertTrue(self.aapen.alle_korps)

    def test_til_alle_aapner_hver_plass(self):
        res = self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'alle': True})
        self.assertEqual(res.json()['data']['delt_ut'], 3)
        self.bil.refresh_from_db()
        self.assertIsNone(self.bil.korps_id, 'enheten har ikke noe «alle»-felt')
        for vp in self.kladd:
            vp.refresh_from_db()
            self.assertTrue(vp.alle_korps)
        self.til_hgsd.refresh_from_db()
        self.assertFalse(self.til_hgsd.alle_korps, 'korpsets plass står')

    def test_korpset_ser_plassene_etterpaa(self):
        url = f'/vaktliste/api/vaktlister/{self.vl.pk}/'
        ser = lambda: {vp['id'] for vp in self.c_kb.get(url).json()['data']['vaktposter']}
        self.assertFalse({vp.pk for vp in self.kladd} & ser())
        self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'korps_id': self.hgsd.pk})
        self.assertTrue({vp.pk for vp in self.kladd} <= ser())

    def test_skriv_full_deler_ut_skriv_handling_gjor_ikke(self):
        res = self._del_ut(self.c_kb, {'ressurs_id': self.bil.pk, 'korps_id': self.hgsd.pk})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self._kladd(), 3)

    def test_alt_eller_ingenting(self):
        """En ukjent rad stopper hele fordelingen før noe er skrevet."""
        andre = lag_ressurs(vaktliste=self.vl, navn='Sola 56', gruppe=gruppe(LAG))
        self._plass(ressurs=andre)
        for feil in ({'ressurs_id': andre.pk},
                     {'ressurs_id': andre.pk, 'korps_id': 99999},
                     {'ressurs_id': 99999, 'korps_id': self.hgsd.pk}):
            with self.subTest(feil=feil):
                res = self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk,
                                               'korps_id': self.hgsd.pk}, feil)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertEqual(self._kladd(), 3)
                self.assertEqual(self._kladd(andre), 1)

    def test_en_feil_midt_i_skrivingen_ruller_tilbake_alt(self):
        """Valideringen stopper det meste før noe skrives; transaksjonen er
        for resten. Feiler den andre enheten, skal den første ikke stå delt ut."""
        from unittest import mock
        andre = lag_ressurs(vaktliste=self.vl, navn='Sola 56', gruppe=gruppe(LAG))
        self._plass(ressurs=andre)
        ekte = services.del_ut

        def feiler_paa_den_andre(ressurs, **kw):
            if ressurs.pk == andre.pk:
                raise RuntimeError('databasen falt')
            return ekte(ressurs, **kw)

        with mock.patch.object(services, 'del_ut', side_effect=feiler_paa_den_andre):
            with self.assertRaises(RuntimeError):
                self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'alle': True},
                             {'ressurs_id': andre.pk, 'alle': True})
        self.assertEqual(self._kladd(), 3)

    def test_en_enhet_paa_en_annen_vaktliste_avvises(self):
        annen = services.opprett_planlagt_vakt('Annen')
        fremmed = lag_ressurs(vaktliste=annen, navn='Fremmed', gruppe=gruppe(LAG))
        self._plass(ressurs=fremmed)
        res = self._del_ut(self.c_vl, {'ressurs_id': fremmed.pk, 'korps_id': self.hgsd.pk})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._kladd(fremmed), 1)

    def test_mange_enheter_i_ett_kall(self):
        andre = lag_ressurs(vaktliste=self.vl, navn='Sola 56', gruppe=gruppe(LAG))
        self._plass(ressurs=andre)
        res = self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'korps_id': self.hgsd.pk},
                           {'ressurs_id': andre.pk, 'alle': True})
        self.assertEqual(res.json()['data']['delt_ut'], 4)
        self.assertEqual(self._kladd() + self._kladd(andre), 0)

    def test_to_ganger_er_ingen_skade(self):
        self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'korps_id': self.hgsd.pk})
        res = self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'korps_id': self.karmoy.pk})
        self.assertEqual(res.json()['data']['delt_ut'], 0)
        self.bil.refresh_from_db()
        self.assertEqual(self.bil.korps_id, self.hgsd.pk,
                         'uten kladd er det ingenting å dele ut — ikke en omreservering')

    def test_utdelingen_auditlogges(self):
        AuditLog.objects.all().delete()
        self._del_ut(self.c_vl, {'ressurs_id': self.bil.pk, 'alle': True})
        self.assertEqual(AuditLog.objects.filter(table_name='vaktliste_vaktpost',
                                                 field_name='alle_korps').count(), 3)


class ReservasjonenPaaEnhetenTests(Basis):
    """Reservasjonen på enheten er utdeling, og krever det samme som plassen."""

    def _put(self, klient, **felt):
        return klient.put(f'/vaktliste/api/ressurser/{self.bil.pk}/',
                          data=felt, content_type='application/json')

    def test_skriv_full_setter_den_naa(self):
        res = self._put(self.c_vl, korps_id=self.hgsd.pk)
        self.assertEqual(res.status_code, 200, res.content)
        self.bil.refresh_from_db()
        self.assertEqual(self.bil.korps_id, self.hgsd.pk)

    def test_skriv_full_rorer_fortsatt_ikke_type_eller_kobling(self):
        for felt, verdi in (('gruppe_id', gruppe(LAG).pk), ('enhet_id', None),
                            ('rekkefolge', 1)):
            with self.subTest(felt=felt):
                self.assertEqual(self._put(self.c_vl, **{felt: verdi}).status_code, 403)

    def test_korpsforeren_setter_den_ikke(self):
        self.bil.korps = self.hgsd
        self.bil.save()
        self.assertEqual(self._put(self.c_kb, korps_id=self.karmoy.pk).status_code, 403)


class TommingFrigirTests(Basis):
    """Tømmes enhetens reservasjon, blir det som arvet den åpent for alle."""

    def setUp(self):
        super().setUp()
        self.bil.korps = self.hgsd
        self.bil.save()

    def _tom(self, klient=None):
        return (klient or self.c_vl).put(
            f'/vaktliste/api/ressurser/{self.bil.pk}/', data={'korps_id': None},
            content_type='application/json')

    def test_ingen_plass_blir_kladd_igjen(self):
        self.assertEqual(self._kladd(), 0)
        res = self._tom()
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._kladd(), 0)
        for vp in self.kladd:
            vp.refresh_from_db()
            self.assertTrue(vp.alle_korps)

    def test_plassen_med_eget_korps_star(self):
        self._tom()
        self.til_hgsd.refresh_from_db()
        self.assertFalse(self.til_hgsd.alle_korps)
        self.assertEqual(self.til_hgsd.korps_id, self.hgsd.pk)

    def test_et_annet_korps_ser_dem_og_kan_ta_dem(self):
        from .tests_tilgang import _bruker, _klient
        from .models import Mannskap
        karmoyforer = _bruker('kf', 'skriv_handling')
        Mannskap.objects.create(navn='Per', korps=self.karmoy, user=karmoyforer)
        self._tom()
        vp = self.kladd[0]
        vp.refresh_from_db()
        self.assertTrue(services.kan_bemanne_plass(karmoyforer, self.bil, vaktpost=vp))

    def test_omreservering_frigir_ingenting(self):
        self.c_vl.put(f'/vaktliste/api/ressurser/{self.bil.pk}/',
                      data={'korps_id': self.karmoy.pk}, content_type='application/json')
        for vp in self.kladd:
            vp.refresh_from_db()
            self.assertFalse(vp.alle_korps)
            self.assertEqual(services.reservert_korps(vaktpost=vp), self.karmoy.pk)

    def test_navnebytte_frigir_ingenting(self):
        """Porten er `korps_id` i kroppen — ikke at enheten tilfeldigvis står tom."""
        self.bil.korps = None
        self.bil.save()
        self.c_vl.put(f'/vaktliste/api/ressurser/{self.bil.pk}/',
                      data={'navn': 'Karmøy 52'}, content_type='application/json')
        self.assertEqual(self._kladd(), 3)

    def test_en_tom_enhet_som_tommes_igjen_rorer_ikke_kladden(self):
        self.bil.korps = None
        self.bil.save()
        self._tom()
        self.assertEqual(self._kladd(), 3, 'kladd som aldri var delt ut, står som kladd')

    def test_frigjoringen_og_tommingen_er_ett_svar(self):
        """Feiler lagringen av enheten, er ingen plass frigjort."""
        lag_ressurs(vaktliste=self.vl, navn='Karmøy 52', gruppe=gruppe(LAG))
        res = self.c_vl.put(f'/vaktliste/api/ressurser/{self.bil.pk}/',
                            data={'korps_id': None, 'navn': 'Karmøy 52'},
                            content_type='application/json')
        self.assertEqual(res.status_code, 400, res.content)
        for vp in self.kladd:
            vp.refresh_from_db()
            self.assertFalse(vp.alle_korps)
        self.assertEqual(Ressurs.objects.get(pk=self.bil.pk).korps_id, self.hgsd.pk)
