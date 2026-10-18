"""Mannskapsregisteret er vaktas (18. okt. 2026, `Vaktmannskap`).

André: «Tomt mannskapsregister etter avsluttet vakt, men du kan hente inn fra tidligere
mannskapsregister fra samme portal med fleravkrysning. For de som har skrive eget korps
må de bare kunne se sin korps, de med skrive alle kan se alle.»

Tjenestelaget og portene er de tunge lagene: en kandidatliste som viser andres korps,
eller en innhenting som slipper gjennom halvveis, ser ingen på skjermen.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from core.models import Vakt, Vaktportal
from core.vakt import gjor_aktiv, hent_aktiv_vakt, opprett_vakt
from vaktliste import services
from vaktliste.models import Mannskap, Vaktmannskap
from vaktliste.test_helpers import lag_mannskap
from vaktliste.tests_tilgang import TilgangsBasis


def _ny_aktiv(navn, **kw):
    with transaction.atomic():
        return gjor_aktiv(opprett_vakt(navn, year=2026, startet=kw.get('startet') or timezone.now()))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RegisteretErVaktasTests(TilgangsBasis):

    def setUp(self):
        super().setUp()
        self.forrige = hent_aktiv_vakt()          # Kari og Ola står i registeret her
        # En planlagt vakt med egen liste — registeret dens er tomt.
        self.neste = services.opprett_planlagt_vakt('Neste')
        self.assertNotEqual(self.neste.vakt_id, self.forrige.pk)

    def _register(self, klient, vakt=None):
        sti = '/vaktliste/api/mannskap/' + (f'?vakt={vakt.pk}' if vakt else '')
        return [m['navn'] for m in klient.get(sti).json()['data']['mannskap']]

    def _kandidater(self, klient, vakt):
        return [m['navn'] for m in
                klient.get(f'/vaktliste/api/mannskap/hent-inn/?vakt={vakt.pk}').json()['data']]

    def _hent_inn(self, klient, vakt, *folk):
        return klient.post('/vaktliste/api/mannskap/hent-inn/',
                           data={'vakt_id': vakt.pk, 'ider': [m.pk for m in folk]},
                           content_type='application/json')

    def test_ny_vakt_starter_med_tomt_register(self):
        self.assertEqual(sorted(self._register(self.c_vl)), ['Kari', 'Ola'])
        ny = _ny_aktiv('Kamp 2')
        self.assertEqual(self._register(self.c_vl), [])
        self.assertEqual(sorted(self._register(self.c_vl, self.forrige)), ['Kari', 'Ola'])
        self.assertTrue(Mannskap.objects.filter(pk=self.p_hgsd.pk).exists(), 'personen står')
        self.assertTrue(ny.pk)

    def test_hent_inn_fra_tidligere_med_avkrysning(self):
        ny = _ny_aktiv('Kamp 2')
        self.assertEqual(sorted(self._kandidater(self.c_vl, ny)), ['Kari', 'Ola'])
        self.assertEqual(self._hent_inn(self.c_vl, ny, self.p_hgsd, self.p_karmoy).status_code, 200)
        self.assertEqual(sorted(self._register(self.c_vl)), ['Kari', 'Ola'])
        self.assertEqual(self._kandidater(self.c_vl, ny), [], 'de som er med, tilbys ikke')

    def test_korpsforeren_ser_og_henter_bare_sitt_korps(self):
        ny = _ny_aktiv('Kamp 2')
        self.assertEqual(self._kandidater(self.c_kb, ny), ['Kari'])
        svar = self._hent_inn(self.c_kb, ny, self.p_hgsd, self.p_karmoy)
        self.assertEqual(svar.status_code, 400)
        self.assertFalse(Vaktmannskap.objects.filter(vakt=ny).exists(), 'alle eller ingen')
        self.assertEqual(self._hent_inn(self.c_kb, ny, self.p_hgsd).status_code, 200)

    def test_leseren_henter_ingen(self):
        ny = _ny_aktiv('Kamp 2')
        self.assertEqual(self._kandidater(self.c_leser, ny), [])
        self.assertEqual(self._hent_inn(self.c_leser, ny, self.p_hgsd).status_code, 400)
        self.assertFalse(Vaktmannskap.objects.filter(vakt=ny).exists())

    def test_eldre_enn_24_maaneder_tilbys_ikke(self):
        Vakt.objects.filter(pk=self.forrige.pk).update(
            startet=timezone.now() - timedelta(days=services.TIDLIGERE_DAGER + 1))
        ny = _ny_aktiv('Kamp 2')
        self.assertEqual(self._kandidater(self.c_vl, ny), [])
        Vakt.objects.filter(pk=self.forrige.pk).update(
            startet=timezone.now() - timedelta(days=services.TIDLIGERE_DAGER - 1))
        self.assertEqual(sorted(self._kandidater(self.c_vl, ny)), ['Kari', 'Ola'])

    def test_en_annen_portals_vakt_er_404(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        kamp = opprett_vakt('Brannkamp', year=2026, startet=timezone.now(), portal=brann)
        self.assertEqual(self.c_vl.get(f'/vaktliste/api/mannskap/?vakt={kamp.pk}').status_code, 404)
        self.assertEqual(self._hent_inn(self.c_vl, kamp, self.p_hgsd).status_code, 404)

    def test_en_ny_person_havner_i_vaktas_register(self):
        svar = self.c_vl.post('/vaktliste/api/mannskap/', data={
            'navn': 'Nina', 'korps_id': self.hgsd.pk, 'vakt_id': self.neste.vakt_id},
            content_type='application/json')
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertEqual(self._register(self.c_vl, self.neste.vakt), ['Nina'])
        self.assertNotIn('Nina', self._register(self.c_vl))

    def test_samme_navn_fra_en_tidligere_vakt_sier_hent_inn(self):
        _ny_aktiv('Kamp 2')
        svar = self.c_vl.post('/vaktliste/api/mannskap/', data={
            'navn': 'Kari', 'korps_id': self.hgsd.pk}, content_type='application/json')
        self.assertEqual(svar.status_code, 409)
        self.assertIn('Hent henne inn', svar.json()['message'])
        self.assertEqual(Mannskap.objects.filter(navn='Kari').count(), 1)

    def test_nedtrekket_tilbyr_bare_vaktas_register(self):
        data = self.c_vl.get(f'/vaktliste/api/vaktlister/{self.neste.pk}/').json()['data']
        self.assertEqual(data['mannskap'], [], 'den planlagte vakta har ingen ennå')
        self._hent_inn(self.c_vl, self.neste.vakt, self.p_hgsd)
        data = self.c_vl.get(f'/vaktliste/api/vaktlister/{self.neste.pk}/').json()['data']
        self.assertEqual([m['navn'] for m in data['mannskap']], ['Kari'])

    def test_paa_et_skift_er_i_registeret(self):
        """En side som har stått åpen: personen settes på et skift i en vakt der hun ikke
        står i registeret, og havner i det i stedet for å bli avvist — både på en ny plass
        og når en ledig plass fylles."""
        from vaktliste.models import Vaktpost
        from vaktliste.test_helpers import lag_ressurs
        lag = lag_ressurs(vaktliste=self.neste, navn='Lag N', korps=self.hgsd)
        svar = self._sett_paa(self.c_vl, lag, self.p_hgsd)
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertTrue(Vaktmannskap.objects.filter(vakt=self.neste.vakt, mannskap=self.p_hgsd)
                        .exists(), 'ny plass')

        ledig = Vaktpost.objects.create(ressurs=lag, fra_tid=self.na,
                                        til_tid=self.na + timedelta(hours=8))
        siri = lag_mannskap(navn='Siri', korps=self.hgsd)       # bare i den aktive
        svar = self.c_vl.put(f'/vaktliste/api/vaktposter/{ledig.pk}/',
                             data={'mannskap_id': siri.pk}, content_type='application/json')
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertTrue(Vaktmannskap.objects.filter(vakt=self.neste.vakt, mannskap=siri).exists(),
                        'ledig plass fylt')

    def test_ta_ut_men_ikke_mens_hun_staar_paa_et_skift(self):
        sti = f'/vaktliste/api/mannskap/{self.p_hgsd.pk}/ta-ut/'
        self._sett_paa(self.c_vl, self.res_hgsd, self.p_hgsd)      # skift i den aktive
        svar = self.c_vl.post(sti, data={'vakt_id': self.forrige.pk},
                              content_type='application/json')
        self.assertEqual(svar.status_code, 409)
        self.assertIn('skift', svar.json()['message'])
        self._hent_inn(self.c_vl, self.neste.vakt, self.p_hgsd)    # ingen skift i den neste
        self.assertEqual(self.c_vl.post(sti, data={'vakt_id': self.neste.vakt_id},
                                        content_type='application/json').status_code, 200)
        self.assertNotIn('Kari', self._register(self.c_vl, self.neste.vakt))
        self.assertIn('Kari', self._register(self.c_vl, self.forrige))
        self.assertTrue(Mannskap.objects.filter(pk=self.p_hgsd.pk).exists())

    def test_korpsforeren_tar_ikke_ut_andres(self):
        svar = self.c_kb.post(f'/vaktliste/api/mannskap/{self.p_karmoy.pk}/ta-ut/',
                              data={'vakt_id': self.forrige.pk}, content_type='application/json')
        self.assertEqual(svar.status_code, 409)
        self.assertTrue(Vaktmannskap.objects.filter(vakt=self.forrige, mannskap=self.p_karmoy)
                        .exists())


class MigrasjonenTests(TilgangsBasis):
    """`0035`: ingen forsvinner fra registeret ved deploy."""

    def test_aapne_vakter_faar_hele_portalen_og_tidligere_faar_skiftene(self):
        import importlib
        from django.apps import apps
        fyll = importlib.import_module('vaktliste.migrations.0035_vaktmannskap_data').fyll
        gammel = Vakt.objects.create(navn='Gammel', year=2025, startet=timezone.now(),
                                     avsluttet=timezone.now(), portal=self.vl.vakt.portal)
        lag_mannskap(vakt=gammel, navn='Per', korps=self.hgsd)
        Vaktmannskap.objects.all().delete()
        fyll(apps, None)
        aktiv = hent_aktiv_vakt()
        self.assertEqual(set(Vaktmannskap.objects.filter(vakt=aktiv)
                             .values_list('mannskap__navn', flat=True)), {'Kari', 'Ola', 'Per'})
        self.assertEqual(set(Vaktmannskap.objects.filter(vakt=self.vl.vakt)
                             .values_list('mannskap__navn', flat=True)), {'Kari', 'Ola', 'Per'},
                         'den planlagte er ikke avsluttet')
        self.assertFalse(Vaktmannskap.objects.filter(vakt=gammel).exists(),
                         'avsluttet uten skift: ingen')


class HentInnVinduetTests(TilgangsBasis):
    """Avkrysningen i «Hent inn fra tidligere» — gjennom `tegnHentInn`, som siden kaller."""

    def test_velg_alle_i_korpset_og_escaping(self):
        from patients.js_test_utils import (PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness,
                                            node_available, run_node)
        if not node_available():
            self.skipTest('node mangler')
        h = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (VAKTLISTE_JS, ('mkHentInn', 'hentInnSynlige', 'tegnHentInn', 'velgHentInn',
                            'velgKorpsHentInn', 'sokHentInn')),
        ))
        run_node(h, """
          const el = { innerHTML: '' };
          const knapp = { disabled: true, textContent: '' };
          globalThis.document = { getElementById: (id) => id === 'hentinn-liste' ? el : knapp };
          globalThis.hentInnSok = '';
          globalThis.hentInnValgt = new Set();
          globalThis.hentInnFolk = [
            {id: 1, navn: '<b>Kari</b>', korps_navn: 'HGSD', sist: null},
            {id: 2, navn: 'Ola', korps_navn: 'HGSD', sist: null},
            {id: 3, navn: 'Per', korps_navn: 'Karmøy', sist: null}];
          velgKorpsHentInn('HGSD');
          assert(hentInnValgt.has(1) && hentInnValgt.has(2) && !hentInnValgt.has(3), 'bare korpset');
          assert(knapp.textContent === 'Hent inn 2' && !knapp.disabled, 'knappen teller');
          assert(!el.innerHTML.includes('<b>Kari'), 'navnet escapes');
          velgKorpsHentInn('HGSD');
          assert(hentInnValgt.size === 0 && knapp.disabled, 'andre trykk fjerner alle');
          sokHentInn('per');
          assert(el.innerHTML.includes('Per') && !el.innerHTML.includes('Ola'), 'søket');
          velgHentInn(3);
          assert(hentInnValgt.has(3), 'én om gangen');
        """)
