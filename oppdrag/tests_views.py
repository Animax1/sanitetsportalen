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
    """Enheter kunne bare lages fra `manage.py shell` fram til 29. aug. 2026.

    Det var ikke en bevisst avgrensning, det var en glipp i fase 3: modulen
    kunne ikke tas i bruk uten Railway-konsollen. André meldte fra ved å
    prøve.
    """

    def test_kun_admin_kan_opprette_enhet(self):
        c = _klient(_bruker('sentral20', 'skriv_full'))
        resp = c.post('/oppdrag/api/enheter/ny/', content_type='application/json',
                      data={'navn': 'Karmøy 13'})
        self.assertEqual(resp.status_code, 403)

    def test_admin_kan_opprette_enhet(self):
        c = _klient(_bruker('adm10', 'skriv_full', admin=True))
        resp = c.post('/oppdrag/api/enheter/ny/', content_type='application/json',
                      data={'navn': 'Karmøy 13'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Enhet.objects.filter(navn='Karmøy 13').exists())

    def test_admin_kan_knytte_konto(self):
        bil = _bruker('haugesund56', 'les', delt=True)
        c = _klient(_bruker('adm11', 'skriv_full', admin=True))
        resp = c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/',
                     content_type='application/json',
                     data={'user_id': bil.pk})
        self.assertEqual(resp.status_code, 200)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.user, bil)

    def test_koblingen_gir_ingen_tilgang(self):
        """§7.3-regelen, håndhevet på den nye flaten.

        Kontoen er knyttet til en enhet, men har ingen `ModulTilgang`-rad.
        Den skal ikke komme inn.
        """
        bil = _bruker('bil_uten_rad', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        self.assertEqual(_klient(bil).get('/oppdrag/').status_code, 403)

    def test_konto_kan_ikke_knyttes_til_to_enheter(self):
        """OneToOne ville gitt en 500; her får admin en setning å lese."""
        bil = _bruker('bil_dobbel', 'les', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        c = _klient(_bruker('adm12', 'skriv_full', admin=True))
        resp = c.put(f'/oppdrag/api/enheter/{self.annen_enhet.pk}/',
                     content_type='application/json', data={'user_id': bil.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('allerede knyttet', resp.json()['message'])

    def test_kobling_kan_fjernes(self):
        bil = _bruker('bil_los', 'les', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        c = _klient(_bruker('adm13', 'skriv_full', admin=True))
        resp = c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/',
                     content_type='application/json', data={'user_id': None})
        self.assertEqual(resp.status_code, 200)
        self.enhet.refresh_from_db()
        self.assertIsNone(self.enhet.user)

    def test_kontolista_krever_admin(self):
        c = _klient(_bruker('sentral21', 'skriv_full'))
        self.assertEqual(c.get('/oppdrag/api/kontoer/').status_code, 403)

    def test_kontolista_merker_opptatte(self):
        bil = _bruker('bil_opptatt', 'les', delt=True)
        Enhet.objects.filter(pk=self.enhet.pk).update(user=bil)
        c = _klient(_bruker('adm14', 'skriv_full', admin=True))
        data = c.get('/oppdrag/api/kontoer/').json()['data']
        rad = next(r for r in data if r['username'] == 'bil_opptatt')
        self.assertTrue(rad['opptatt'])
        self.assertTrue(rad['er_delt_konto'])

    def test_deaktivert_enhet_kan_ikke_faa_oppdrag(self):
        c = _klient(_bruker('adm15', 'skriv_full', admin=True))
        c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/',
              content_type='application/json', data={'er_aktiv': False})
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
