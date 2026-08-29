"""Tester for sentralbordet og oppdrags-API-et (fase 3).

Det som testes er grensene: hvem som slipper inn på hvilket nivå, at en
enhetskonto kun får sine egne rader, og at skjulereglene håndheves i serverens
svar og ikke i nettleseren.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from patients.models import AppSetting

from oppdrag import choices, services
from oppdrag.models import Enhet, Lokasjon, Oppdrag, Statusmelding

AAR = 2098


def _bruker(navn, nivaa=None, *, admin=False, delt=False):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role='admin' if admin else 'bruker',
        must_change_password=False, er_delt_konto=delt)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='oppdrag', nivaa=nivaa)
    return b


def _klient(bruker):
    c = Client()
    c.force_login(bruker)
    return c


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class OppdragBasis(TestCase):
    def setUp(self):
        AppSetting.objects.update_or_create(
            key='active_year', defaults={'value': str(AAR)})
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.enhet = Enhet.objects.create(navn='Haugesund 56')
        self.annen_enhet = Enhet.objects.create(navn='Karmøy 12')

    def _oppdrag(self, enhet=None, year=AAR, **kwargs):
        from oppdrag.services import neste_oppdragsnummer
        kwargs.setdefault('oppdragsnummer', neste_oppdragsnummer(year))
        return Oppdrag.objects.create(
            year=year, enhet=enhet or self.enhet,
            problemstilling='Pustevansker', hastegrad='Akutt',
            lokasjon=self.lokasjon, **kwargs)


class TilgangTests(OppdragBasis):
    """Modulgaten, og objektsjekken dekoratoren ikke gjør."""

    def test_uten_modultilgang_gir_403(self):
        c = _klient(_bruker('utenfor'))
        self.assertEqual(c.get('/oppdrag/').status_code, 403)
        self.assertEqual(c.get('/oppdrag/api/oppdrag/').status_code, 403)

    def test_les_slipper_inn_men_kan_ikke_opprette(self):
        c = _klient(_bruker('leser', 'les'))
        self.assertEqual(c.get('/oppdrag/').status_code, 200)
        resp = c.post('/oppdrag/api/oppdrag/', data='{}',
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_skriv_full_kan_opprette(self):
        c = _klient(_bruker('sentral', 'skriv_full'))
        resp = c.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
            'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Oppdrag.objects.count(), 1)

    def test_skriv_handling_kan_ikke_opprette(self):
        """Enhetsnivået stempler; det oppretter ikke."""
        c = _klient(_bruker('bil', 'skriv_handling'))
        resp = c.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
            'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
        })
        self.assertEqual(resp.status_code, 403)

    def test_ugyldig_hastegrad_avvises(self):
        """Verdimengden håndheves server-side, ikke bare i nedtrekkslista."""
        c = _klient(_bruker('sentral2', 'skriv_full'))
        resp = c.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
            'problemstilling': 'Pustevansker', 'hastegrad': 'Rød',
        })
        self.assertEqual(resp.status_code, 400)

    def test_inaktiv_lokasjon_kan_ikke_velges(self):
        self.lokasjon.er_aktiv = False
        self.lokasjon.save()
        c = _klient(_bruker('sentral3', 'skriv_full'))
        resp = c.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
            'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
        })
        self.assertEqual(resp.status_code, 400)


class GrensesnittvalgTests(OppdragBasis):
    """Skjermen velges av enhetskoblingen, ikke av nivået."""

    def test_enhetskonto_far_ikke_sentralbordet(self):
        """Sentralbordet ville vist henne alle oppdrag i vakta."""
        bruker = _bruker('haugesund56', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bruker)
        html = _klient(bruker).get('/oppdrag/').content.decode()
        self.assertNotIn('id="oppdragsliste"', html)
        self.assertIn('Haugesund 56', html)

    def test_konto_uten_enhet_far_sentralbordet(self):
        html = _klient(_bruker('sentral4', 'les')).get('/oppdrag/').content.decode()
        self.assertIn('id="oppdragsliste"', html)

    def test_skriv_full_pa_enhetskonto_gir_fortsatt_enhetsskjerm(self):
        """Nivået avgjør ikke skjermen — koblingen gjør.

        Å velge skjerm på «er nivået nøyaktig skriv_handling» ville brukt et
        ordnet nivå som en identitet, og gått galt i det noen fikk begge.
        """
        bruker = _bruker('bil_med_alt', 'skriv_full', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bruker)
        html = _klient(bruker).get('/oppdrag/').content.decode()
        self.assertNotIn('id="oppdragsliste"', html)


class RadnivaaTests(OppdragBasis):
    """En enhet ser sine egne oppdrag, og ingen andres."""

    def setUp(self):
        super().setUp()
        self.bruker = _bruker('bil2', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=self.bruker)
        self.bruker.refresh_from_db()

    def test_enheten_ser_kun_egne(self):
        mitt = self._oppdrag(self.enhet)
        self._oppdrag(self.annen_enhet)

        data = _klient(self.bruker).get('/oppdrag/api/oppdrag/').json()['data']
        self.assertEqual([r['id'] for r in data], [mitt.pk])

    def test_sentralbordet_ser_alle(self):
        """Vern mot at filteret gjelder alle."""
        self._oppdrag(self.enhet)
        self._oppdrag(self.annen_enhet)
        data = _klient(_bruker('sentral5', 'les')).get(
            '/oppdrag/api/oppdrag/').json()['data']
        self.assertEqual(len(data), 2)

    def test_enheten_far_403_pa_annen_enhets_oppdrag(self):
        deres = self._oppdrag(self.annen_enhet)
        resp = _klient(self.bruker).get(f'/oppdrag/api/oppdrag/{deres.pk}/')
        self.assertEqual(resp.status_code, 403)

    def test_fritekst_forsvinner_naar_oppdraget_er_ledig(self):
        """Skjules den i JS, ligger teksten fortsatt i responsen."""
        oppdrag = self._oppdrag(self.enhet, fritekst='sensitivt notat',
                                status=choices.LEDIG)
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.LEDIG, tidspunkt=timezone.now())

        raa = _klient(self.bruker).get('/oppdrag/api/oppdrag/').content.decode()
        self.assertNotIn('sensitivt notat', raa)

    def test_fritekst_vises_mens_oppdraget_pagar(self):
        """Vern mot at fritekst alltid utelates."""
        self._oppdrag(self.enhet, fritekst='sensitivt notat',
                      status=choices.FREMME)
        raa = _klient(self.bruker).get('/oppdrag/api/oppdrag/').content.decode()
        self.assertIn('sensitivt notat', raa)

    def test_sentralbordet_beholder_fritekst_etter_ledig(self):
        """Regelen gjelder bilen, ikke 113."""
        oppdrag = self._oppdrag(self.enhet, fritekst='sensitivt notat',
                                status=choices.LEDIG)
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.LEDIG, tidspunkt=timezone.now())
        raa = _klient(_bruker('sentral6', 'les')).get(
            '/oppdrag/api/oppdrag/').content.decode()
        self.assertIn('sensitivt notat', raa)

    def test_oppdrag_skjules_30_min_etter_ledig(self):
        oppdrag = self._oppdrag(self.enhet, status=choices.LEDIG)
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.LEDIG,
            tidspunkt=timezone.now() - timedelta(minutes=45))
        data = _klient(self.bruker).get('/oppdrag/api/oppdrag/').json()['data']
        self.assertEqual(data, [])


class EnhetslisteTests(OppdragBasis):
    """Utledet status, og ETag på pollingen."""

    def test_ledig_uten_oppdrag(self):
        data = _klient(_bruker('sentral7', 'les')).get(
            '/oppdrag/api/enheter/').json()['data']
        self.assertTrue(all(r['status'] == choices.LEDIG for r in data))

    def test_ventende_telles_men_gjor_ikke_opptatt(self):
        self._oppdrag(self.enhet, status=choices.VENTER)
        data = _klient(_bruker('sentral8', 'les')).get(
            '/oppdrag/api/enheter/').json()['data']
        rad = next(r for r in data if r['id'] == self.enhet.pk)
        self.assertEqual(rad['status'], choices.LEDIG)
        self.assertEqual(rad['antall_ventende'], 1)

    def test_etag_gir_304_naar_ingenting_er_endret(self):
        c = _klient(_bruker('sentral9', 'les'))
        forste = c.get('/oppdrag/api/enheter/')
        etag = forste['ETag']
        andre = c.get('/oppdrag/api/enheter/', HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(andre.status_code, 304)

    def test_etag_endres_naar_status_endres(self):
        c = _klient(_bruker('sentral10', 'les'))
        etag = c.get('/oppdrag/api/enheter/')['ETag']
        self._oppdrag(self.enhet, status=choices.FREMME)
        andre = c.get('/oppdrag/api/enheter/', HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(andre.status_code, 200)


class FlyttTests(OppdragBasis):
    def test_flytting_krever_skriv_full(self):
        oppdrag = self._oppdrag(self.enhet)
        c = _klient(_bruker('leser2', 'les'))
        resp = c.post(f'/oppdrag/api/oppdrag/{oppdrag.pk}/flytt/',
                      content_type='application/json',
                      data={'enhet_id': self.annen_enhet.pk})
        self.assertEqual(resp.status_code, 403)

    def test_flytting_skriver_i_oppdragets_logg(self):
        oppdrag = self._oppdrag(self.enhet, status=choices.FREMME)
        c = _klient(_bruker('sentral11', 'skriv_full'))
        resp = c.post(f'/oppdrag/api/oppdrag/{oppdrag.pk}/flytt/',
                      content_type='application/json',
                      data={'enhet_id': self.annen_enhet.pk})
        self.assertEqual(resp.status_code, 200)

        detalj = c.get(f'/oppdrag/api/oppdrag/{oppdrag.pk}/').json()['data']
        self.assertEqual(len(detalj['enhetsbytter']), 1)
        self.assertEqual(detalj['status'], choices.FREMME)


class LokasjonsadminTests(OppdragBasis):
    def test_alle_med_les_ser_lista(self):
        data = _klient(_bruker('leser3', 'les')).get(
            '/oppdrag/api/lokasjoner/').json()['data']
        self.assertEqual(len(data), 1)

    def test_kun_admin_kan_opprette(self):
        c = _klient(_bruker('sentral12', 'skriv_full'))
        resp = c.post('/oppdrag/api/lokasjoner/', content_type='application/json',
                      data={'navn': 'Inngang Nord'})
        self.assertEqual(resp.status_code, 403)

    def test_admin_kan_opprette(self):
        c = _klient(_bruker('adm', 'skriv_full', admin=True))
        resp = c.post('/oppdrag/api/lokasjoner/', content_type='application/json',
                      data={'navn': 'Inngang Nord'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Lokasjon.objects.filter(navn='Inngang Nord').exists())

    def test_delete_deaktiverer_i_stedet_for_a_slette(self):
        """FK-en er PROTECT — en lokasjon i bruk kan ikke forsvinne."""
        c = _klient(_bruker('adm2', 'skriv_full', admin=True))
        resp = c.delete(f'/oppdrag/api/lokasjoner/{self.lokasjon.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.lokasjon.refresh_from_db()
        self.assertFalse(self.lokasjon.er_aktiv)
        self.assertTrue(Lokasjon.objects.filter(pk=self.lokasjon.pk).exists())


class EnhetsadminTests(OppdragBasis):
    """Enheten har ingen egen livssyklus — den følger kontoen sin.

    Modulen hadde en kort periode tre admin-flater for enheter: oppretting,
    pensjonering og kontokobling, alle inne i oppdragsmodulen. Alle tre er
    borte 29. aug. 2026. En bil opprettes ved at kontoen opprettes, og
    pensjoneres ved at kontoen slettes; se
    `accounts.tests_user_admin.EnhetFolgerKontoenTests`, som eier reglene nå.

    Det som står igjen her, er lista og vaktbryteren.
    """

    DODE_ENDEPUNKT = (
        ('post', '/oppdrag/api/enheter/ny/'),
        ('get', '/oppdrag/api/kontoer/'),
    )

    def test_admin_flatene_er_borte_ikke_bare_skjult(self):
        """Knappene ble fjernet fra tegningen; endepunktene skal følge med.

        Ellers ville de blitt liggende som en skrivevei ingen ser og ingen
        vedlikeholder — nettopp den slags rad `pensjonerEnhet` kunne skrevet
        til uten at noe i grensesnittet viste det.
        """
        c = _klient(_bruker('adm20', 'skriv_full', admin=True))
        for metode, url in self.DODE_ENDEPUNKT:
            with self.subTest(url=url):
                self.assertEqual(
                    getattr(c, metode)(url, content_type='application/json',
                                       data={}).status_code, 404)

        self.assertEqual(
            c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/',
                  content_type='application/json',
                  data={'er_aktiv': False}).status_code, 404)
        self.enhet.refresh_from_db()
        self.assertTrue(self.enhet.er_aktiv)

    def test_koblingen_gir_ingen_tilgang(self):
        """§7.3-regelen, håndhevet på den nye flaten.

        Kontoen er knyttet til en enhet, men har ingen `ModulTilgang`-rad.
        Den skal ikke komme inn.
        """
        bil = _bruker('bil_uten_rad', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        self.assertEqual(_klient(bil).get('/oppdrag/').status_code, 403)

    def test_alle_gir_pensjonerte_enheter(self):
        """Pensjonerte vises i panelet, men ikke på tavla.

        En pensjonert bil er ikke borte — den venter på at kontoen sin
        opprettes igjen, og tar da historikken sin med seg.
        """
        Enhet.objects.filter(pk=self.enhet.pk).update(er_aktiv=False)
        c = _klient(_bruker('sentral40', 'skriv_full'))

        uten = c.get('/oppdrag/api/enheter/').json()['data']
        med = c.get('/oppdrag/api/enheter/?alle=1').json()['data']

        self.assertNotIn(self.enhet.pk, [r['id'] for r in uten])
        self.assertIn(self.enhet.pk, [r['id'] for r in med])

    def test_lista_viser_kontokoblingen(self):
        """Koblingen vises som tekst — den redigeres ikke lenger her."""
        bil = _bruker('bil_vist', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        data = _klient(_bruker('sentral41', 'skriv_full')).get(
            '/oppdrag/api/enheter/').json()['data']
        rad = next(r for r in data if r['id'] == self.enhet.pk)
        self.assertEqual(rad['username'], 'bil_vist')

    def test_pensjonert_enhet_kan_ikke_faa_oppdrag(self):
        Enhet.objects.filter(pk=self.enhet.pk).update(er_aktiv=False)
        c = _klient(_bruker('adm15', 'skriv_full', admin=True))
        resp = c.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
            'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
        })
        self.assertEqual(resp.status_code, 400)


class ManglendeOppsettTests(OppdragBasis):
    """Sida sier fra når forutsetningene mangler.

    Uten enheter ville «Nytt oppdrag» latt deg fylle ut skjemaet og så feilet
    med «Ukjent eller inaktiv enhet» ved lagring. Det er den verste
    rekkefølgen: arbeidet gjøres først, beskjeden kommer etterpå.
    """

    def test_varselet_er_i_malen(self):
        html = _klient(_bruker('sentral22', 'skriv_full')).get(
            '/oppdrag/').content.decode()
        self.assertIn('id="mangler-oppsett"', html)
        self.assertIn('Modulen mangler oppsett', html)

    def test_enhetslista_er_tom_uten_enheter(self):
        Enhet.objects.all().delete()
        data = _klient(_bruker('sentral23', 'les')).get(
            '/oppdrag/api/enheter/').json()['data']
        self.assertEqual(data, [])


class PaaVaktTests(OppdragBasis):
    """Ressursoversikt: 113 tar biler på og av vakt gjennom vakta.

    `pa_vakt` er ikke `er_aktiv`. Den første er drift og endres flere ganger
    per vakt; den andre er oppsett og settes av admin når en bil pensjoneres.
    Slås de sammen, ser «pensjonert» likt ut som «hjemme i kveld», og den som
    skulle skru bilen på igjen finner den ikke.
    """

    def test_skriv_full_kan_ta_av_vakt(self):
        c = _klient(_bruker('sentral30', 'skriv_full'))
        resp = c.post(f'/oppdrag/api/enheter/{self.enhet.pk}/vakt/',
                      content_type='application/json', data={'pa_vakt': False})
        self.assertEqual(resp.status_code, 200)
        self.enhet.refresh_from_db()
        self.assertFalse(self.enhet.pa_vakt)

    def test_les_kan_ikke(self):
        c = _klient(_bruker('leser30', 'les'))
        resp = c.post(f'/oppdrag/api/enheter/{self.enhet.pk}/vakt/',
                      content_type='application/json', data={'pa_vakt': False})
        self.assertEqual(resp.status_code, 403)

    def test_enhet_av_vakt_kan_ikke_faa_oppdrag(self):
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        c = _klient(_bruker('sentral31', 'skriv_full'))
        resp = c.post('/oppdrag/api/oppdrag/', content_type='application/json', data={
            'enhet_id': self.enhet.pk, 'lokasjon_id': self.lokasjon.pk,
            'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt',
        })
        self.assertEqual(resp.status_code, 400)

    def test_enhet_av_vakt_kan_ikke_faa_flyttet_oppdrag(self):
        """Ellers ville flytting vært en bakvei rundt vaktstatusen."""
        oppdrag = self._oppdrag(self.enhet)
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(pa_vakt=False)
        c = _klient(_bruker('sentral32', 'skriv_full'))
        resp = c.post(f'/oppdrag/api/oppdrag/{oppdrag.pk}/flytt/',
                      content_type='application/json',
                      data={'enhet_id': self.annen_enhet.pk})
        self.assertEqual(resp.status_code, 400)

    def test_kan_ikke_tas_av_vakt_med_pagaende_oppdrag(self):
        """Bilen er ute akkurat nå — å fjerne den fra tavla skjuler oppdraget."""
        self._oppdrag(self.enhet, status=choices.FREMME)
        c = _klient(_bruker('sentral33', 'skriv_full'))
        resp = c.post(f'/oppdrag/api/enheter/{self.enhet.pk}/vakt/',
                      content_type='application/json', data={'pa_vakt': False})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('pågående oppdrag', resp.json()['message'])
        self.enhet.refresh_from_db()
        self.assertTrue(self.enhet.pa_vakt)

    def test_ventende_oppdrag_hindrer_ikke(self):
        """Vern mot at sperren alltid slår til. Bilen har ikke rykket ut."""
        self._oppdrag(self.enhet, status=choices.VENTER)
        c = _klient(_bruker('sentral34', 'skriv_full'))
        resp = c.post(f'/oppdrag/api/enheter/{self.enhet.pk}/vakt/',
                      content_type='application/json', data={'pa_vakt': False})
        self.assertEqual(resp.status_code, 200)

    def test_enhet_av_vakt_vises_fortsatt_i_lista(self):
        """Skjules den, er den en bil ingen husker å sette inn igjen."""
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        data = _klient(_bruker('sentral35', 'les')).get(
            '/oppdrag/api/enheter/').json()['data']
        rad = next(r for r in data if r['id'] == self.enhet.pk)
        self.assertFalse(rad['pa_vakt'])

    def test_pensjonert_enhet_vises_ikke(self):
        """`er_aktiv=False` er noe annet: den skal bort for godt."""
        Enhet.objects.filter(pk=self.enhet.pk).update(er_aktiv=False)
        data = _klient(_bruker('sentral36', 'les')).get(
            '/oppdrag/api/enheter/').json()['data']
        self.assertNotIn(self.enhet.pk, [r['id'] for r in data])

    def test_etag_endres_naar_vaktstatus_endres(self):
        c = _klient(_bruker('sentral37', 'skriv_full'))
        etag = c.get('/oppdrag/api/enheter/')['ETag']
        c.post(f'/oppdrag/api/enheter/{self.enhet.pk}/vakt/',
               content_type='application/json', data={'pa_vakt': False})
        self.assertEqual(
            c.get('/oppdrag/api/enheter/', HTTP_IF_NONE_MATCH=etag).status_code, 200)


class StemplingBasis(OppdragBasis):
    """Felles oppsett: en enhetskonto koblet til `self.enhet`."""

    def setUp(self):
        super().setUp()
        self.bilbruker = _bruker('haugesund56', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=self.bilbruker)
        self.bil = _klient(self.bilbruker)

    def _stemple(self, oppdrag, overgang, body=None, klient=None):
        return (klient or self.bil).post(
            f'/oppdrag/api/oppdrag/{oppdrag.pk}/status/{overgang}/',
            data=body if body is not None else {},
            content_type='application/json')


class StemplingTests(StemplingBasis):
    """De navngitte overgangene — første faktiske bruk av `skriv_handling`."""

    def test_hele_kjeden_kan_stemples(self):
        o = self._oppdrag()
        for overgang in ('rykker_ut', 'fremme', 'avreist', 'leverer', 'ledig'):
            with self.subTest(overgang=overgang):
                resp = self._stemple(o, overgang)
                self.assertEqual(resp.status_code, 200)
                o.refresh_from_db()
                self.assertEqual(o.status, overgang)
        self.assertEqual(Statusmelding.objects.filter(oppdrag=o).count(), 5)

    def test_ledig_er_utgang_fra_enhver_status(self):
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        resp = self._stemple(o, 'ledig')
        self.assertEqual(resp.status_code, 200)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.LEDIG)

    def test_ulovlig_overgang_gir_409_og_ingen_rad(self):
        """Dobbelttrykket: det første vant, det andre skal ikke lage noe."""
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        foer = Statusmelding.objects.filter(oppdrag=o).count()
        resp = self._stemple(o, 'rykker_ut')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(Statusmelding.objects.filter(oppdrag=o).count(), foer)

    def test_ukjent_overgangsnavn_gir_404(self):
        """`venter` stemples aldri — den settes ved oppretting."""
        o = self._oppdrag()
        for navn in ('venter', 'neste', 'tull'):
            with self.subTest(navn=navn):
                self.assertEqual(self._stemple(o, navn).status_code, 404)

    def test_rykk_ut_lukker_pagaende_automatisk(self):
        """§4.3: samme tidsstempel, og bare den avledede raden flagges."""
        forste = self._oppdrag()
        andre = self._oppdrag()
        self._stemple(forste, 'rykker_ut')
        resp = self._stemple(andre, 'rykker_ut')
        self.assertEqual(resp.status_code, 200)

        forste.refresh_from_db()
        andre.refresh_from_db()
        self.assertEqual(forste.status, choices.LEDIG)
        self.assertEqual(andre.status, choices.RYKKER_UT)

        ledig = Statusmelding.objects.get(oppdrag=forste, status=choices.LEDIG)
        start = Statusmelding.objects.get(oppdrag=andre, status=choices.RYKKER_UT)
        self.assertTrue(ledig.automatisk)
        self.assertFalse(start.automatisk)
        self.assertEqual(ledig.tidspunkt, start.tidspunkt)

    def test_svar_inneholder_neste_overgang(self):
        """Knappen vet hvilken overgang den utfører fordi serveren sier det."""
        o = self._oppdrag()
        data = self._stemple(o, 'rykker_ut').json()['data']
        self.assertEqual(data['oppdrag']['neste_overgang'], 'fremme')
        self.assertEqual(data['oppdrag']['status'], 'rykker_ut')


class StemplingSkjemaTests(StemplingBasis):
    """Det lukkede kroppsskjemaet fra §5.1 — testbart ved uttømming."""

    def test_tom_kropp_er_gyldig(self):
        o = self._oppdrag()
        resp = self.bil.post(
            f'/oppdrag/api/oppdrag/{o.pk}/status/rykker_ut/',
            data='', content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_domenefelt_i_kroppen_gir_400_og_ingen_endring(self):
        """Selve invarianten: ingen feltverdi kan noensinne komme inn her."""
        o = self._oppdrag(fritekst='original')
        resp = self._stemple(o, 'rykker_ut', body={
            'klienttid': timezone.now().isoformat(),
            'fritekst': 'smuglet inn',
        })
        self.assertEqual(resp.status_code, 400)
        o.refresh_from_db()
        self.assertEqual(o.fritekst, 'original')
        self.assertEqual(o.status, choices.VENTER)
        self.assertIn('fritekst', resp.json()['message'])

    def test_hver_nokkel_utenfor_skjemaet_avvises(self):
        o = self._oppdrag()
        for felt in ('status', 'problemstilling', 'hastegrad', 'enhet_id', 'x'):
            with self.subTest(felt=felt):
                resp = self._stemple(o, 'rykker_ut', body={felt: '1'})
                self.assertEqual(resp.status_code, 400)

    def test_idempotency_key_godtas(self):
        """Den andre nøkkelen i skjemaet. Kobles til core.idempotency i fase 5."""
        o = self._oppdrag()
        resp = self._stemple(o, 'rykker_ut', body={'idempotency_key': 'abc123'})
        self.assertEqual(resp.status_code, 200)

    def test_ugyldig_json_gir_400(self):
        o = self._oppdrag()
        resp = self.bil.post(
            f'/oppdrag/api/oppdrag/{o.pk}/status/rykker_ut/',
            data='ikke json', content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_uleselig_klienttid_gir_400(self):
        """En klientfeil skal feile høyt, ikke stille bli servertid."""
        o = self._oppdrag()
        resp = self._stemple(o, 'rykker_ut', body={'klienttid': 'i går'})
        self.assertEqual(resp.status_code, 400)


class StemplingObjektsjekkTests(StemplingBasis):
    """To porter: modulgaten, og eierskapet dekoratoren ikke ser."""

    def test_annen_enhets_oppdrag_gir_403(self):
        o = self._oppdrag(enhet=self.annen_enhet)
        resp = self._stemple(o, 'rykker_ut')
        self.assertEqual(resp.status_code, 403)
        o.refresh_from_db()
        self.assertEqual(o.status, choices.VENTER)

    def test_sentral_uten_enhet_kan_ikke_stemple(self):
        """Nivået holder ikke: `skriv_full` uten enhetskobling får 403.

        Sentralbordet stempler ikke — det korrigerer (fase 4b). Stemplingen
        er en måling fra bilen, og en operatør som «stempler for» en enhet
        ville forfalsket den målingen.
        """
        sentral = _klient(_bruker('sentralops', 'skriv_full'))
        o = self._oppdrag()
        resp = self._stemple(o, 'rykker_ut', klient=sentral)
        self.assertEqual(resp.status_code, 403)

    def test_uten_modultilgang_gir_403(self):
        """Enhetskobling uten ModulTilgang-rad slipper heller ikke inn.

        Koblingen er domenedata og gir ingen tilgang — samme regel som
        `Forstehjelper.user` i pasientmodulen.
        """
        naken = _bruker('bil_uten_rad', delt=True)
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(user=naken)
        o = self._oppdrag(enhet=self.annen_enhet)
        resp = self._stemple(o, 'rykker_ut', klient=_klient(naken))
        self.assertEqual(resp.status_code, 403)

    def test_les_nivaa_kan_ikke_stemple(self):
        lesebruker = _bruker('bil_les', 'les', delt=True)
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(user=lesebruker)
        o = self._oppdrag(enhet=self.annen_enhet)
        resp = self._stemple(o, 'rykker_ut', klient=_klient(lesebruker))
        self.assertEqual(resp.status_code, 403)

    def test_oppdrag_utenfor_aktiv_vakt_gir_404(self):
        o = self._oppdrag(year=AAR - 1)
        self.assertEqual(self._stemple(o, 'rykker_ut').status_code, 404)


class KlienttidTests(StemplingBasis):
    """§5.1: klienttid brukes i vinduet, servertid utenfor, forsinket flagges."""

    def _siste_melding(self, oppdrag):
        return (Statusmelding.objects.filter(oppdrag=oppdrag)
                .order_by('-created_at').first())

    def test_gyldig_klienttid_brukes(self):
        # Oppdraget må være eldre enn klienttiden — en klienttid før
        # `created_at` forkastes med rette (den er utenfor vinduet).
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(
            created_at=timezone.now() - timedelta(hours=1))
        o.refresh_from_db()
        tid = timezone.now() - timedelta(minutes=10)
        resp = self._stemple(o, 'rykker_ut', body={'klienttid': tid.isoformat()})
        self.assertEqual(resp.status_code, 200)
        melding = self._siste_melding(o)
        self.assertEqual(melding.tidspunkt, tid)
        self.assertTrue(melding.forsinket)

    def test_fersk_klienttid_er_ikke_forsinket(self):
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut',
                      body={'klienttid': timezone.now().isoformat()})
        self.assertFalse(self._siste_melding(o).forsinket)

    def test_framtidig_klienttid_erstattes_med_servertid(self):
        o = self._oppdrag()
        tid = timezone.now() + timedelta(hours=2)
        foer = timezone.now()
        self._stemple(o, 'rykker_ut', body={'klienttid': tid.isoformat()})
        melding = self._siste_melding(o)
        self.assertLess(melding.tidspunkt, tid)
        self.assertGreaterEqual(melding.tidspunkt, foer)
        # Avviket er informasjonen, ikke hvilket stempel som vant.
        self.assertTrue(melding.forsinket)

    def test_klienttid_foer_oppdraget_erstattes_med_servertid(self):
        o = self._oppdrag()
        tid = o.created_at - timedelta(hours=1)
        self._stemple(o, 'rykker_ut', body={'klienttid': tid.isoformat()})
        melding = self._siste_melding(o)
        self.assertGreater(melding.tidspunkt, o.created_at)
        self.assertTrue(melding.forsinket)

    def test_eldgammel_klienttid_erstattes_med_servertid(self):
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(
            created_at=timezone.now() - timedelta(days=3))
        o.refresh_from_db()
        tid = timezone.now() - timedelta(days=2)
        self._stemple(o, 'rykker_ut', body={'klienttid': tid.isoformat()})
        melding = self._siste_melding(o)
        self.assertGreater(melding.tidspunkt, tid + timedelta(days=1))
        self.assertTrue(melding.forsinket)


class EnhetSkjermTests(StemplingBasis):
    """Enhetsskjermen erstatter mellomtilstanden fra fase 3."""

    def test_enhetskonto_faar_skjermen_med_knappene(self):
        html = self.bil.get('/oppdrag/').content.decode()
        self.assertIn('Haugesund 56', html)
        self.assertIn('id="aktivt-oppdrag"', html)
        self.assertIn('oppdrag-enhet', html)
        self.assertNotIn('Enhetsskjermen er ikke bygget ennå', html)
        self.assertNotIn('id="oppdragsliste"', html)

    def test_lista_baerer_neste_overgang_og_statusmeldinger(self):
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        data = self.bil.get('/oppdrag/api/oppdrag/').json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['neste_overgang'], 'fremme')
        self.assertEqual(
            [m['status'] for m in data[0]['statusmeldinger']], ['rykker_ut'])

    def test_sentralens_liste_har_ikke_enhetsfeltene(self):
        """Feltene finnes for skjermen som trenger dem, ikke overalt."""
        self._oppdrag()
        c = _klient(_bruker('sentral_liste', 'les'))
        rad = c.get('/oppdrag/api/oppdrag/').json()['data'][0]
        self.assertNotIn('neste_overgang', rad)
        self.assertNotIn('statusmeldinger', rad)

    def test_stempling_endrer_etag(self):
        """Pollingen skal se sin egen stempling uten å vente på statusskifte."""
        o = self._oppdrag()
        resp1 = self.bil.get('/oppdrag/api/oppdrag/')
        etag1 = resp1['ETag']
        self._stemple(o, 'rykker_ut')
        resp2 = self.bil.get('/oppdrag/api/oppdrag/',
                             HTTP_IF_NONE_MATCH=etag1)
        self.assertEqual(resp2.status_code, 200)
        self.assertNotEqual(resp2['ETag'], etag1)


class OppdragsnummerTests(OppdragBasis):
    """Løpenummeret man sier på samband: «oppdrag 14»."""

    def setUp(self):
        super().setUp()
        self.c = _klient(_bruker('nummerops', 'skriv_full'))

    def _opprett(self):
        return self.c.post('/oppdrag/api/oppdrag/', content_type='application/json',
                           data={'enhet_id': self.enhet.pk,
                                 'lokasjon_id': self.lokasjon.pk,
                                 'problemstilling': 'Pustevansker',
                                 'hastegrad': 'Akutt'})

    def test_numrene_teller_oppover_fra_en(self):
        for ventet in (1, 2, 3):
            with self.subTest(ventet=ventet):
                self.assertEqual(self._opprett().json()['data']['nummer'], ventet)

    def test_nummeret_er_med_i_lista(self):
        self._opprett()
        rad = self.c.get('/oppdrag/api/oppdrag/').json()['data'][0]
        self.assertEqual(rad['nummer'], 1)

    def test_nummeret_restarter_per_aar(self):
        """Per år, ikke globalt — ellers blir det for langt å lese opp."""
        self._opprett()
        AppSetting.objects.update_or_create(
            key='active_year', defaults={'value': str(AAR + 1)})
        self.assertEqual(self._opprett().json()['data']['nummer'], 1)
        self.assertEqual(
            Oppdrag.objects.filter(year=AAR + 1, oppdragsnummer=1).count(), 1)

    def test_samme_nummer_to_ganger_i_samme_aar_avvises(self):
        """Unikhetskravet er i databasen, ikke bare i telleren."""
        o = self._oppdrag()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Oppdrag.objects.create(
                    year=AAR, oppdragsnummer=o.oppdragsnummer,
                    enhet=self.enhet, problemstilling='Transport',
                    hastegrad='Vanlig', lokasjon=self.lokasjon)

    def test_telleren_gjenskapes_om_raden_mangler(self):
        """En slettet AppSetting-rad skal ikke gi kollisjon med eksisterende."""
        o = self._oppdrag()
        AppSetting.objects.filter(key=f'next_oppdrag_nr_{AAR}').delete()
        self.assertEqual(
            self._opprett().json()['data']['nummer'], o.oppdragsnummer + 1)


class HistorikkTests(OppdragBasis):
    """Rydding av tavla — ikke vaktarkivet. Reversibel, ingenting fryses.

    Ordet «arkiv» er reservert `core.arkiv`, som fryser hele vakter.
    """

    def setUp(self):
        super().setUp()
        self.c = _klient(_bruker('historikkops', 'skriv_full'))

    def _til_historikk(self, oppdrag, klient=None):
        return (klient or self.c).post(
            f'/oppdrag/api/oppdrag/{oppdrag.pk}/historikk/')

    def _hent_tilbake(self, oppdrag):
        return self.c.delete(f'/oppdrag/api/oppdrag/{oppdrag.pk}/historikk/')

    def test_ferdigstilt_kan_flyttes(self):
        o = self._oppdrag(status=choices.LEDIG)
        self.assertEqual(self._til_historikk(o).status_code, 200)
        o.refresh_from_db()
        self.assertIsNotNone(o.historikk_fra)

    def test_paagaende_kan_ikke_flyttes(self):
        """Å rydde bort noe som fortsatt skjer ville skjult det."""
        for status in (choices.VENTER, choices.RYKKER_UT, choices.FREMME,
                       choices.AVREIST, choices.LEVERER):
            with self.subTest(status=status):
                o = self._oppdrag(status=status)
                resp = self._til_historikk(o)
                self.assertEqual(resp.status_code, 400)
                o.refresh_from_db()
                self.assertIsNone(o.historikk_fra)

    def test_flyttet_forsvinner_fra_aktiv_liste(self):
        beholdt = self._oppdrag(status=choices.LEDIG)
        ryddet = self._oppdrag(status=choices.LEDIG)
        self._til_historikk(ryddet)
        ider = [r['id'] for r in self.c.get('/oppdrag/api/oppdrag/').json()['data']]
        self.assertIn(beholdt.pk, ider)
        self.assertNotIn(ryddet.pk, ider)

    def test_raden_slettes_ikke(self):
        """Flyttingen er et visningsvalg. Statistikken beholder raden."""
        o = self._oppdrag(status=choices.LEDIG)
        self._til_historikk(o)
        self.assertTrue(Oppdrag.objects.filter(pk=o.pk).exists())

    def test_hent_tilbake_angrer(self):
        o = self._oppdrag(status=choices.LEDIG)
        self._til_historikk(o)
        self.assertEqual(self._hent_tilbake(o).status_code, 200)
        o.refresh_from_db()
        self.assertIsNone(o.historikk_fra)
        ider = [r['id'] for r in self.c.get('/oppdrag/api/oppdrag/').json()['data']]
        self.assertIn(o.pk, ider)

    def test_dobbel_flytting_endrer_ikke_tidspunktet(self):
        o = self._oppdrag(status=choices.LEDIG)
        self._til_historikk(o)
        o.refresh_from_db()
        forste = o.historikk_fra
        self._til_historikk(o)
        o.refresh_from_db()
        self.assertEqual(o.historikk_fra, forste)

    def test_les_kan_ikke_flytte(self):
        o = self._oppdrag(status=choices.LEDIG)
        resp = self._til_historikk(o, klient=_klient(_bruker('historikkleser', 'les')))
        self.assertEqual(resp.status_code, 403)

    def test_enhetskonto_kan_ikke_flytte(self):
        """Rydding av tavla er sentralbordets jobb, også med skriv_full."""
        bil = _bruker('bil_historikk', 'skriv_full', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        o = self._oppdrag(status=choices.LEDIG)
        self.assertEqual(self._til_historikk(o, klient=_klient(bil)).status_code, 403)

    def test_flytting_gir_auditrad(self):
        """Feltlista utledes fra modellen, så det nye feltet spores av seg selv."""
        from audit.models import AuditLog
        o = self._oppdrag(status=choices.LEDIG)
        AuditLog.objects.all().delete()
        self._til_historikk(o)
        self.assertTrue(AuditLog.objects.filter(
            table_name='oppdrag_oppdrag', field_name='historikk_fra').exists())


class HistorikklisteTests(OppdragBasis):
    """Historikk-visningen, og søket som finner tilbake til oppdraget."""

    #: Numrene er valgt slik at delstreng-søk ville tatt feil: «1» er både
    #: et helt nummer og et prefiks av 10 og 11. Uten den kollisjonen i
    #: dataene ville `test_soek_paa_nummer_treffer_eksakt` bestått også med
    #: `__icontains` — den ville påstått mer enn fiksturet kunne vise.
    NUMRE = (1, 10, 11)

    def setUp(self):
        super().setUp()
        self.c = _klient(_bruker('historikkliste', 'skriv_full'))
        self.ferdigstilte = []
        for nummer, problem in zip(
                self.NUMRE, ('Pustevansker', 'Brannskade', 'Transport')):
            o = self._oppdrag(status=choices.LEDIG, oppdragsnummer=nummer)
            o.problemstilling = problem
            o.save(update_fields=['problemstilling'])
            self.c.post(f'/oppdrag/api/oppdrag/{o.pk}/historikk/')
            self.ferdigstilte.append(o)

    def _sok(self, term=None):
        url = '/oppdrag/api/historikk/'
        if term is not None:
            url += f'?sok={term}'
        return self.c.get(url).json()['data']

    def test_lista_viser_kun_ferdigstilte(self):
        aktiv = self._oppdrag(status=choices.LEDIG)
        ider = [r['id'] for r in self._sok()]
        self.assertEqual(len(ider), 3)
        self.assertNotIn(aktiv.pk, ider)

    def test_soek_paa_nummer_treffer_eksakt(self):
        """Søker man «1», skal man ikke få 1, 10 og 11.

        Fiksturet har nettopp de tre numrene, så et delstreng-søk ville
        returnert alle tre og feilet her.
        """
        maal = self.ferdigstilte[0]          # nummer 1
        treff = self._sok('1')
        self.assertEqual([r['id'] for r in treff], [maal.pk])
        self.assertEqual(treff[0]['nummer'], 1)

    def test_soek_paa_nummer_med_havelaag(self):
        maal = self.ferdigstilte[1]
        treff = self._sok(f'%23{maal.oppdragsnummer}')
        self.assertEqual([r['id'] for r in treff], [maal.pk])

    def test_soek_paa_problemstilling(self):
        treff = self._sok('brann')
        self.assertEqual([r['problemstilling'] for r in treff], ['Brannskade'])

    def test_soek_paa_enhet(self):
        self.assertEqual(len(self._sok('Haugesund')), 3)

    def test_ukjent_soek_gir_tom_liste(self):
        self.assertEqual(self._sok('finnesikke'), [])

    def test_enhetskonto_far_403(self):
        """Historikken er sentralbordets oversikt over hele vakta."""
        bil = _bruker('bil_historikkliste', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        self.assertEqual(
            _klient(bil).get('/oppdrag/api/historikk/').status_code, 403)

    def test_uten_modultilgang_gir_403(self):
        self.assertEqual(
            _klient(_bruker('utenfor_historikk')).get('/oppdrag/api/historikk/').status_code,
            403)


class AutoHistorikkTests(StemplingBasis):
    """Et oppdrag som blir `Ledig` rydder seg selv bort fra tavla.

    Regelen bor i `sett_status`, ikke i stemplingsviewet — se docstringen
    der. Testene under dekker begge veiene inn i `Ledig`.
    """

    def setUp(self):
        super().setUp()
        self.sentral = _klient(_bruker('auto_sentral', 'skriv_full'))

    def _aktiv_liste(self):
        return [r['id'] for r in
                self.sentral.get('/oppdrag/api/oppdrag/').json()['data']]

    def test_ledig_gaar_i_historikk_med_en_gang(self):
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        self.assertIn(o.pk, self._aktiv_liste())

        self._stemple(o, 'ledig')
        o.refresh_from_db()
        self.assertIsNotNone(o.historikk_fra)
        self.assertNotIn(o.pk, self._aktiv_liste())

    def test_automatisk_lukking_gaar_ogsaa_i_historikk(self):
        """§4.3: startes neste oppdrag, lukkes det pågående — og ryddes bort.

        Dette er grunnen til at regelen ligger i `sett_status` og ikke i
        viewet: ingen trykket `Ledig` på dette oppdraget.
        """
        forste = self._oppdrag()
        andre = self._oppdrag()
        self._stemple(forste, 'rykker_ut')
        self._stemple(andre, 'rykker_ut')

        forste.refresh_from_db()
        self.assertEqual(forste.status, choices.LEDIG)
        self.assertIsNotNone(forste.historikk_fra)
        self.assertNotIn(forste.pk, self._aktiv_liste())
        self.assertIn(andre.pk, self._aktiv_liste())

    def test_automatisk_flytting_har_ingen_historikk_av(self):
        """NULL betyr «ryddet bort av seg selv», satt betyr «noen trykket»."""
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        self._stemple(o, 'ledig')
        o.refresh_from_db()
        self.assertIsNone(o.historikk_av)

    def test_manuell_flytting_setter_historikk_av(self):
        o = self._oppdrag(status=choices.LEDIG)
        self.sentral.post(f'/oppdrag/api/oppdrag/{o.pk}/historikk/')
        o.refresh_from_db()
        self.assertEqual(o.historikk_av.username, 'auto_sentral')

    def test_ferdigstilt_havner_i_historikken(self):
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        self._stemple(o, 'ledig')
        historikk = self.sentral.get('/oppdrag/api/historikk/').json()['data']
        self.assertEqual([r['id'] for r in historikk], [o.pk])

    def test_hentet_tilbake_blir_staaende(self):
        """Flyttingen henger på overgangen, ikke på statusen.

        Var den en filtrering på status, ville oppdraget forsvunnet igjen ved
        neste poll og «Hent tilbake» vært en knapp uten virkning.
        """
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        self._stemple(o, 'ledig')
        self.sentral.delete(f'/oppdrag/api/oppdrag/{o.pk}/historikk/')

        o.refresh_from_db()
        self.assertEqual(o.status, choices.LEDIG)
        self.assertIsNone(o.historikk_fra)
        self.assertIn(o.pk, self._aktiv_liste())
        # Og den blir stående over flere hentinger.
        self.assertIn(o.pk, self._aktiv_liste())

    def test_bilen_ser_det_fortsatt_i_tretti_minutter(self):
        """Den viktige frakoblingen: tavla ryddes, bilens vindu er urørt.

        30-minuttersvinduet er personvern, historikken er tavlerydding.
        Koblet dem, ville mannskapet mistet oppdraget fra skjermen i samme
        øyeblikk de meldte seg ledige — mens de fortsatt sto og så på det.
        """
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        self._stemple(o, 'ledig')

        mine = self.bil.get('/oppdrag/api/oppdrag/').json()['data']
        self.assertIn(o.pk, [r['id'] for r in mine])
        self.assertNotIn(o.pk, self._aktiv_liste())


class KorreksjonTests(StemplingBasis):
    """§4.4: rettingen er en ny rad som peker på den gamle, ikke en endring."""

    #: Et oppdrag stemplet i samme millisekund som det ble opprettet gir ikke
    #: rom for å rette noe bakover — valideringen ville stanset enhver retting
    #: på «før oppdraget ble opprettet», og testene hadde målt den regelen i
    #: stedet for mekanikken de er skrevet for. Fiksturet får derfor et
    #: realistisk tidsspenn: opprettet for en time siden, stemplet underveis.
    def setUp(self):
        super().setUp()
        self.sentral = _klient(_bruker('korrops', 'skriv_full'))
        self.oppdrag = self._oppdrag()
        self._stemple(self.oppdrag, 'rykker_ut')
        self._stemple(self.oppdrag, 'fremme')

        naa = timezone.now()
        Oppdrag.objects.filter(pk=self.oppdrag.pk).update(
            created_at=naa - timedelta(minutes=60))
        self.oppdrag.refresh_from_db()
        for status, minutter in ((choices.RYKKER_UT, 40), (choices.FREMME, 30)):
            Statusmelding.objects.filter(
                oppdrag=self.oppdrag, status=status).update(
                    tidspunkt=naa - timedelta(minutes=minutter))

        self.fremme = Statusmelding.objects.get(
            oppdrag=self.oppdrag, status=choices.FREMME)

    def _korriger(self, melding, tidspunkt, klient=None):
        return (klient or self.sentral).post(
            f'/oppdrag/api/statusmelding/{melding.pk}/korriger/',
            data={'tidspunkt': tidspunkt.isoformat()},
            content_type='application/json')

    # ── Mekanikken ──────────────────────────────────────────────────────────

    def test_rettingen_er_en_ny_rad(self):
        ny_tid = self.fremme.tidspunkt - timedelta(minutes=2)
        self.assertEqual(self._korriger(self.fremme, ny_tid).status_code, 200)

        self.fremme.refresh_from_db()
        self.assertEqual(
            Statusmelding.objects.filter(
                oppdrag=self.oppdrag, status=choices.FREMME).count(), 2)

    def test_originalen_er_uendret(self):
        """`Statusmelding` er et spor av hva som ble meldt."""
        original = self.fremme.tidspunkt
        self._korriger(self.fremme, original - timedelta(minutes=2))
        self.fremme.refresh_from_db()
        self.assertEqual(self.fremme.tidspunkt, original)

    def test_den_nye_raden_peker_paa_den_gamle(self):
        self._korriger(self.fremme, self.fremme.tidspunkt - timedelta(minutes=2))
        ny = Statusmelding.objects.get(korrigerer=self.fremme)
        self.assertEqual(ny.status, choices.FREMME)
        self.assertEqual(ny.meldt_av.username, 'korrops')
        self.assertFalse(ny.automatisk)
        self.assertFalse(ny.forsinket)

    def test_gjeldende_er_rettingen(self):
        ny_tid = self.fremme.tidspunkt - timedelta(minutes=2)
        self._korriger(self.fremme, ny_tid)
        gjeldende = Statusmelding.objects.gjeldende_for_status(
            self.oppdrag, choices.FREMME)
        self.assertEqual(gjeldende.tidspunkt, ny_tid)
        self.assertIsNotNone(gjeldende.korrigerer_id)

    def test_korreksjoner_kan_kjedes(self):
        """Retter man en retting, er det den siste som står."""
        forste = self.fremme.tidspunkt - timedelta(minutes=2)
        self._korriger(self.fremme, forste)
        rettelse = Statusmelding.objects.get(korrigerer=self.fremme)

        andre = self.fremme.tidspunkt - timedelta(minutes=1)
        self.assertEqual(self._korriger(rettelse, andre).status_code, 200)

        gjeldende = Statusmelding.objects.gjeldende_for_status(
            self.oppdrag, choices.FREMME)
        self.assertEqual(gjeldende.tidspunkt, andre)

    def test_begge_staar_i_historikken(self):
        """Tidslinjen viser rettingen ved siden av det som ble meldt."""
        self._korriger(self.fremme, self.fremme.tidspunkt - timedelta(minutes=2))
        data = self.sentral.get(
            f'/oppdrag/api/oppdrag/{self.oppdrag.pk}/').json()['data']
        fremmerader = [m for m in data['historikk'] if m['status'] == 'fremme']
        self.assertEqual(len(fremmerader), 2)
        self.assertEqual(
            len([m for m in data['statusmeldinger'] if m['status'] == 'fremme']), 1)

    # ── Reglene ─────────────────────────────────────────────────────────────

    def test_framtidig_tidspunkt_avvises(self):
        resp = self._korriger(self.fremme, timezone.now() + timedelta(hours=1))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Statusmelding.objects.filter(
            korrigerer=self.fremme).count(), 0)

    def test_tidspunkt_foer_oppdraget_avvises(self):
        resp = self._korriger(
            self.fremme, self.oppdrag.created_at - timedelta(hours=1))
        self.assertEqual(resp.status_code, 400)

    def test_kan_ikke_settes_foer_forrige_status(self):
        """Fremme før Rykker ut ville gitt negativ responstid i fase 6."""
        rykker_ut = Statusmelding.objects.get(
            oppdrag=self.oppdrag, status=choices.RYKKER_UT)
        resp = self._korriger(
            self.fremme, rykker_ut.tidspunkt - timedelta(minutes=5))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Rykker ut', resp.json()['message'])

    def test_kan_ikke_settes_etter_neste_status(self):
        # `avreist` stemples med servertid. Uten å flytte den bakover ville
        # «5 minutter etter» havnet i framtiden, og framtidsregelen svart
        # først — testen hadde da målt feil regel og bestått uansett om
        # rekkefølgesjekken fantes.
        self._stemple(self.oppdrag, 'avreist')
        Statusmelding.objects.filter(
            oppdrag=self.oppdrag, status=choices.AVREIST).update(
                tidspunkt=timezone.now() - timedelta(minutes=20))
        avreist = Statusmelding.objects.get(
            oppdrag=self.oppdrag, status=choices.AVREIST)

        resp = self._korriger(self.fremme, avreist.tidspunkt + timedelta(minutes=5))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Avreist', resp.json()['message'])

    def test_overstyrt_rad_kan_ikke_rettes(self):
        """Ellers fantes to korreksjoner av samme original, uten entydig svar."""
        self._korriger(self.fremme, self.fremme.tidspunkt - timedelta(minutes=2))
        resp = self._korriger(self.fremme, self.fremme.tidspunkt - timedelta(minutes=3))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('allerede rettet', resp.json()['message'])

    def test_manglende_tidspunkt_gir_400(self):
        resp = self.sentral.post(
            f'/oppdrag/api/statusmelding/{self.fremme.pk}/korriger/',
            data={}, content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_ugyldig_tidspunkt_gir_400(self):
        resp = self.sentral.post(
            f'/oppdrag/api/statusmelding/{self.fremme.pk}/korriger/',
            data={'tidspunkt': 'i går'}, content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    # ── Tilgang ─────────────────────────────────────────────────────────────

    def test_enhet_kan_ikke_rette(self):
        """En enhet stempler, den retter ikke — ellers blir målingen en påstand."""
        resp = self._korriger(
            self.fremme, self.fremme.tidspunkt - timedelta(minutes=2),
            klient=self.bil)
        self.assertEqual(resp.status_code, 403)

    def test_skriv_handling_uten_enhet_kan_ikke_rette(self):
        """Korreksjon er ikke et handling-endepunkt: den tar en feltverdi."""
        resp = self._korriger(
            self.fremme, self.fremme.tidspunkt - timedelta(minutes=2),
            klient=_klient(_bruker('handling_uten_bil', 'skriv_handling')))
        self.assertEqual(resp.status_code, 403)

    def test_les_kan_ikke_rette(self):
        resp = self._korriger(
            self.fremme, self.fremme.tidspunkt - timedelta(minutes=2),
            klient=_klient(_bruker('korrleser', 'les')))
        self.assertEqual(resp.status_code, 403)

    def test_melding_utenfor_aktiv_vakt_gir_404(self):
        gammelt = self._oppdrag(year=AAR - 1, status=choices.FREMME)
        melding = Statusmelding.objects.create(
            oppdrag=gammelt, status=choices.FREMME, tidspunkt=timezone.now())
        resp = self._korriger(melding, timezone.now() - timedelta(minutes=1))
        self.assertEqual(resp.status_code, 404)

    def test_korreksjon_gir_auditrad_uten_aa_roere_oppdraget(self):
        """Rettingen endrer en statusmelding, ikke oppdragets felter."""
        from audit.models import AuditLog
        AuditLog.objects.all().delete()
        self._korriger(self.fremme, self.fremme.tidspunkt - timedelta(minutes=2))
        self.oppdrag.refresh_from_db()
        self.assertEqual(self.oppdrag.status, choices.FREMME)
        self.assertFalse(AuditLog.objects.filter(
            table_name='oppdrag_oppdrag', field_name='status').exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class IdempotensTests(StemplingBasis):
    """§5.2: en avspilt kø skal gi én statusmelding, ikke to.

    Uten nøkkelen ville andre forsøk fått 409 fra statusmaskinen — teknisk
    ufarlig, men ubrukelig for køen: den kan ikke skille «allerede levert» fra
    «avvist fordi skjermen har sakket akterut», og ville enten hengt fast eller
    kastet en stempling som faktisk kom fram.
    """

    def setUp(self):
        super().setUp()
        cache.clear()

    def _stemple_med_nokkel(self, oppdrag, overgang, nokkel, klienttid=None):
        kropp = {'idempotency_key': nokkel}
        if klienttid:
            kropp['klienttid'] = klienttid.isoformat()
        return self._stemple(oppdrag, overgang, body=kropp)

    def test_avspilling_gir_ok_og_ingen_ny_rad(self):
        o = self._oppdrag()
        nokkel = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

        forste = self._stemple_med_nokkel(o, 'rykker_ut', nokkel)
        self.assertEqual(forste.status_code, 200)
        antall = Statusmelding.objects.filter(oppdrag=o).count()

        andre = self._stemple_med_nokkel(o, 'rykker_ut', nokkel)
        self.assertEqual(andre.status_code, 200)
        self.assertTrue(andre.json()['data'].get('avspilling'))
        self.assertEqual(Statusmelding.objects.filter(oppdrag=o).count(), antall)

    def test_avspilling_gir_samme_melding(self):
        """Køen skal kunne stryke raden i trygg forvissning om hva som står."""
        o = self._oppdrag()
        nokkel = 'b1b2c3d4-e5f6-7890-abcd-ef1234567890'
        forste = self._stemple_med_nokkel(o, 'rykker_ut', nokkel)
        andre = self._stemple_med_nokkel(o, 'rykker_ut', nokkel)
        self.assertEqual(andre.json()['data']['melding']['id'],
                         forste.json()['data']['melding']['id'])

    def test_uten_nokkel_gir_409_som_foer(self):
        """Eldre klienter og direkte API-kall oppfører seg uendret."""
        o = self._oppdrag()
        self.assertEqual(self._stemple(o, 'rykker_ut').status_code, 200)
        self.assertEqual(self._stemple(o, 'rykker_ut').status_code, 409)

    def test_ulike_noekler_er_ulike_trykk(self):
        """To reelle trykk skal ikke slås sammen fordi de ligner."""
        o = self._oppdrag()
        self._stemple_med_nokkel(o, 'rykker_ut',
                                 'c1b2c3d4-e5f6-7890-abcd-ef1234567890')
        andre = self._stemple_med_nokkel(o, 'fremme',
                                         'd1b2c3d4-e5f6-7890-abcd-ef1234567890')
        self.assertEqual(andre.status_code, 200)
        self.assertEqual(Statusmelding.objects.filter(oppdrag=o).count(), 2)

    def test_avvist_overgang_brenner_ikke_noekkelen(self):
        """En kø som retter seg og prøver igjen skal slippe til.

        Reserverte vi før valideringen, ville et avvist forsøk låst nøkkelen,
        og det korrigerte forsøket fått «allerede levert» på noe som aldri kom
        fram.
        """
        o = self._oppdrag()
        nokkel = 'e1b2c3d4-e5f6-7890-abcd-ef1234567890'

        # `fremme` er ulovlig fra `venter` — avvises.
        self.assertEqual(
            self._stemple_med_nokkel(o, 'fremme', nokkel).status_code, 409)
        # Samme nøkkel, lovlig overgang: skal gå gjennom.
        self.assertEqual(
            self._stemple_med_nokkel(o, 'rykker_ut', nokkel).status_code, 200)
        self.assertEqual(Statusmelding.objects.filter(oppdrag=o).count(), 1)

    def test_ugyldig_noekkelform_ignoreres_stille(self):
        """`bygg_nokkel` avviser rar form. Da gjelder oppførselen uten nøkkel."""
        o = self._oppdrag()
        resp = self._stemple_med_nokkel(o, 'rykker_ut', 'kort')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['data'].get('avspilling'))

    def test_noekkel_er_per_bruker(self):
        """To enheter kan trekke samme tilfeldige verdi uten å kollidere."""
        annen_bruker = _bruker('karmoy12', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(user=annen_bruker)
        mitt = self._oppdrag()
        deres = self._oppdrag(enhet=self.annen_enhet)
        nokkel = 'f1b2c3d4-e5f6-7890-abcd-ef1234567890'

        self._stemple_med_nokkel(mitt, 'rykker_ut', nokkel)
        resp = self._stemple(deres, 'rykker_ut',
                             body={'idempotency_key': nokkel},
                             klient=_klient(annen_bruker))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['data'].get('avspilling'))

    def test_klienttiden_fra_trykket_bevares_gjennom_koen(self):
        """Statistikken skal vise når mannskapet meldte, ikke når nettet kom."""
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(
            created_at=timezone.now() - timedelta(hours=1))
        o.refresh_from_db()
        trykket = timezone.now() - timedelta(minutes=20)

        self._stemple_med_nokkel(o, 'rykker_ut',
                                 '01b2c3d4-e5f6-7890-abcd-ef1234567890',
                                 klienttid=trykket)
        melding = Statusmelding.objects.get(oppdrag=o, status=choices.RYKKER_UT)
        self.assertEqual(melding.tidspunkt, trykket)
        self.assertTrue(melding.forsinket)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EnhetKjedeDataTests(StemplingBasis):
    """Skjermen får kjeden som data, for å kunne projisere neste steg offline."""

    def test_kjeden_sendes_med_siden(self):
        html = self.bil.get('/oppdrag/').content.decode()
        self.assertIn('OPPDRAG_NESTE', html)
        self.assertIn('OPPDRAG_STATUSNAVN', html)

    def test_kjeden_stemmer_med_tjenestelaget(self):
        """Én sannhet: sendes en annen kjede enn serveren håndhever, viser
        knappen ett steg og endepunktet godtar et annet."""
        import json as _json
        import re
        html = self.bil.get('/oppdrag/').content.decode()
        treff = re.search(r'window\.OPPDRAG_NESTE = (\{.*?\});', html, re.S)
        self.assertIsNotNone(treff)
        sendt = _json.loads(treff.group(1))
        for status in choices.STATUS_NAVN:
            with self.subTest(status=status):
                self.assertEqual(sendt.get(status),
                                 services.neste_i_kjeden(status))

    def test_sentralbordet_faar_ikke_kjeden(self):
        """Den finnes for offline-køen, og sentralbordet har ingen kø."""
        c = _klient(_bruker('sentral_kjede', 'skriv_full'))
        self.assertNotIn('OPPDRAG_NESTE', c.get('/oppdrag/').content.decode())
