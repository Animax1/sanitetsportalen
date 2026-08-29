"""Tester for sentralbordet og oppdrags-API-et (fase 3).

Det som testes er grensene: hvem som slipper inn på hvilket nivå, at en
enhetskonto kun får sine egne rader, og at skjulereglene håndheves i serverens
svar og ikke i nettleseren.
"""
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from patients.models import AppSetting

from oppdrag import choices
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

    def _oppdrag(self, enhet=None, **kwargs):
        return Oppdrag.objects.create(
            year=AAR, enhet=enhet or self.enhet,
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
        o = Oppdrag.objects.create(
            year=AAR - 1, enhet=self.enhet, problemstilling='Transport',
            hastegrad='Vanlig', lokasjon=self.lokasjon)
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
