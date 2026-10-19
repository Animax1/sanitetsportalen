"""Løpende posisjon fra bilene, og «Hent posisjon» fra KO (19. okt. 2026).

`oppdrag/posisjon.py` er regelen, og den prøves **gjennom de ekte inngangene**:
headeren på bilens poll (`X-Posisjon-Intervall`, `X-Posisjon-Onsket`), stien bilen
sender på, og knappene i KO. En test som kalte `intervall_for` direkte, ville gått
grønn om pollen sluttet å sende den.
"""
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from core.models import AppSetting
from oppdrag import choices, posisjon, services
from oppdrag.models import Enhet, Enhetstype, Oppdrag, Oppdragsenhet

from .tests_views import StemplingBasis, _bruker, _klient

SEND = 'core.kartkobling.send_enhet'
OPPSATT = {'KART_URL': 'https://kart.example.no', 'KART_HMAC_NOKKEL': 'k' * 64}
LOPENDE = '/oppdrag/api/posisjon/lopende/'


def _pos(**felt):
    return {'lat': 59.4136, 'lon': 5.2683, 'tid': timezone.now().isoformat(), **felt}


def _slaa_paa(**sekunder):
    posisjon.lagre({'aktiv': True, **({'sekunder': sekunder} if sekunder else {})})


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False, **OPPSATT)
class _Basis(StemplingBasis):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.enhet.refresh_from_db()

    def _poll(self, **headere):
        return self.bil.get('/oppdrag/api/oppdrag/', **headere)

    def _intervall(self):
        return int(self._poll()['X-Posisjon-Intervall'])

    def _send(self, kropp=None):
        return self.bil.post(LOPENDE, data=json.dumps(kropp or {'posisjon': _pos()}),
                             content_type='application/json')

    def _oppdrag(self, enhet=None, vakt=None, hastegrad='Akutt', **kwargs):
        from core.vakt import vakt_for_year
        from oppdrag.test_helpers import lag_oppdrag
        vakt = vakt_for_year(vakt) if isinstance(vakt, int) else (vakt or self.vakt)
        return lag_oppdrag(vakt=vakt, enhet=enhet or self.enhet, hastegrad=hastegrad,
                           oppdragsnummer=services.neste_oppdragsnummer(vakt),
                           problemstilling='Udefinert', lokasjon=self.lokasjon, **kwargs)

    def _rykk_ut(self, hastegrad='Akutt', enhet=None):
        o = self._oppdrag(enhet=enhet, hastegrad=hastegrad)
        services.sett_status(o, choices.RYKKER_UT, enhet=enhet or self.enhet)
        return o

    def _passiv(self):
        self.enhet.enhetstype = Enhetstype.objects.create(navn='Lege', kan_passiv_vakt=True)
        self.enhet.passiv_vakt = True
        self.enhet.save()


class IntervalletPaaPollenTests(_Basis):
    """Regelen, lest der bilen leser den."""

    def test_av_som_standard_er_slik_det_var(self):
        self._rykk_ut('Akutt')
        self.assertEqual(self._intervall(), 0)
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '0')

    def test_andres_tall_uten_oppdrag_og_paa_akutt(self):
        _slaa_paa()
        self.assertEqual(self._intervall(), 300, 'uten oppdrag: hvert 5. minutt')
        self._rykk_ut('Akutt')
        self.assertEqual(self._intervall(), 30)

    def test_hver_hastegrad_har_sitt_eget_tall(self):
        _slaa_paa(Akutt=20, Haster=45, Vanlig=120, Drift=240, Plassering=600, uten=900)
        self.assertEqual(self._intervall(), 900)
        for hastegrad, sek in (('Plassering', 600), ('Drift', 240), ('Vanlig', 120),
                               ('Haster', 45)):
            with self.subTest(hastegrad=hastegrad):
                Oppdragsenhet.objects.filter(enhet=self.enhet).update(status=choices.LEDIG)
                self._rykk_ut(hastegrad)
                self.assertEqual(self._intervall(), sek)

    def test_varslet_er_ikke_paabegynt(self):
        """Intervallet følger det bilen har rykket ut på, ikke det hun er varslet på."""
        _slaa_paa(Akutt=20, uten=900)
        self._oppdrag(hastegrad='Akutt')
        self.assertEqual(self._intervall(), 900)

    def test_ledig_rad_teller_ikke(self):
        _slaa_paa(Akutt=20, uten=900)
        self._rykk_ut('Akutt')
        Oppdragsenhet.objects.filter(enhet=self.enhet).update(status=choices.LEDIG)
        self.assertEqual(self._intervall(), 900)

    def test_flere_paabegynte_det_korteste_vinner(self):
        _slaa_paa(Haster=45, Vanlig=120)
        self._rykk_ut('Vanlig')
        self._rykk_ut('Haster')
        self.assertEqual(self._intervall(), 45)

    def test_en_annen_bils_oppdrag_og_en_annen_vakt_teller_ikke(self):
        _slaa_paa(Akutt=20, uten=900)
        self._rykk_ut('Akutt', enhet=self.annen_enhet)
        o = self._oppdrag(hastegrad='Akutt', vakt=self.vakt.year - 1)
        Oppdragsenhet.objects.filter(oppdrag=o).update(status=choices.RYKKER_UT)
        self.assertEqual(self._intervall(), 900)

    def test_null_er_ikke_lopende_i_tilstanden(self):
        _slaa_paa(uten=0, Vanlig=0, Akutt=20)
        self.assertEqual(self._intervall(), 0)
        self._rykk_ut('Vanlig')
        self.assertEqual(self._intervall(), 0)
        self._rykk_ut('Akutt')
        self.assertEqual(self._intervall(), 20, 'en tilstand med null tar ikke de andre med seg')

    def test_av_vakt_sender_ingenting(self):
        _slaa_paa()
        services.sett_pa_vakt(self.enhet, False)
        self.assertEqual(self._intervall(), 0)

    def test_headeren_folger_ogsaa_304(self):
        _slaa_paa()
        etag = self._poll()['ETag']
        svar = self._poll(HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(svar.status_code, 304)
        self.assertEqual(svar['X-Posisjon-Intervall'], '300')


class PassivVaktTests(_Basis):
    """André, 19. okt.: ikke løpende «med mindre de har fått et oppdrag de har trykket
    rykker ut på som ikke er plassering» — og Vanlig er med («nei jeg glemte den ut»)."""

    def setUp(self):
        super().setUp()
        _slaa_paa(Akutt=20, Haster=45, Vanlig=120, Drift=240, Plassering=600, uten=900)
        self._passiv()

    def test_uten_oppdrag_sender_ikke(self):
        self.assertEqual(self._intervall(), 0)

    def test_varslet_men_ikke_rykket_ut_sender_ikke(self):
        self._oppdrag(hastegrad='Akutt')
        self.assertEqual(self._intervall(), 0)

    def test_plassering_sender_ikke(self):
        self._rykk_ut('Plassering')
        self.assertEqual(self._intervall(), 0)

    def test_akutt_haster_vanlig_og_drift_sender_med_sitt_tall(self):
        for hastegrad, sek in (('Drift', 240), ('Vanlig', 120), ('Haster', 45), ('Akutt', 20)):
            with self.subTest(hastegrad=hastegrad):
                Oppdragsenhet.objects.filter(enhet=self.enhet).update(status=choices.LEDIG)
                self._rykk_ut(hastegrad)
                self.assertEqual(self._intervall(), sek)

    def test_plassering_ved_siden_av_vanlig_teller_ikke_med(self):
        self._rykk_ut('Plassering')
        self._rykk_ut('Vanlig')
        self.assertEqual(self._intervall(), 120)

    def test_passiv_paa_en_type_uten_passiv_vakt_er_aktiv(self):
        """`gjeldende_modus` er tom når typen ikke tillater passiv — flagget alene teller ikke."""
        Enhetstype.objects.filter(pk=self.enhet.enhetstype_id).update(kan_passiv_vakt=False)
        self.assertEqual(self._intervall(), 900)


class InnstillingeneTests(_Basis):
    """«Valglister → Bilen» — global admin, som resten av bilinnstillingene."""

    URL = '/oppdrag/api/bilinnstillinger/'

    def setUp(self):
        super().setUp()
        self.admin = _klient(_bruker('admin', admin=True))

    def _put(self, kropp, klient=None):
        return (klient or self.admin).put(self.URL, data=json.dumps(kropp),
                                          content_type='application/json')

    def test_standard_er_av_med_andres_tall(self):
        data = self.admin.get(self.URL).json()['data']['posisjon']
        self.assertFalse(data['aktiv'])
        self.assertEqual(data['sekunder'], {'Akutt': 30, 'Haster': 30, 'Vanlig': 300, 'Drift': 300,
                                            'Plassering': 300, 'uten': 300})

    def test_admin_slaar_paa_og_setter_ett_tall_de_andre_staar(self):
        resp = self._put({'posisjon': {'aktiv': True, 'sekunder': {'Vanlig': 60}}})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()['data']['posisjon']
        self.assertTrue(data['aktiv'])
        self.assertEqual(data['sekunder']['Vanlig'], 60)
        self.assertEqual(data['sekunder']['Akutt'], 30)
        self._put({'posisjon': {'sekunder': {'Akutt': 15}}})
        self.assertEqual(posisjon.sekunder()['Vanlig'], 60, 'et nytt tall visker ikke ut det forrige')
        self.assertTrue(posisjon.lopende_aktiv(), 'uten `aktiv` står bryteren')

    def test_grensene_og_null(self):
        for verdi, ok in ((14, False), (15, True), (3600, True), (3601, False), (0, True),
                          (-1, False), ('30', False), (True, False), (False, False), (30.5, False)):
            with self.subTest(verdi=verdi):
                resp = self._put({'posisjon': {'sekunder': {'Akutt': verdi}}})
                self.assertEqual(resp.status_code, 200 if ok else 400, resp.content)

    def test_ugyldig_lagrer_ingenting_heller_ikke_resten_av_skjemaet(self):
        resp = self._put({'terskler': {'Akutt': [5, 5]}, 'lyd_aktiv': False,
                          'posisjon': {'aktiv': True, 'sekunder': {'Ukjent': 30}}})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(posisjon.lopende_aktiv())
        data = self.admin.get(self.URL).json()['data']
        self.assertNotEqual(data['terskler']['Akutt'], [5, 5])
        self.assertTrue(data['lyd_aktiv'])
        for kropp in ([], {'aktiv': True, 'annet': 1}, {'sekunder': [30]}):
            with self.subTest(kropp=kropp):
                self.assertEqual(self._put({'posisjon': kropp}).status_code, 400)

    def test_bare_global_admin(self):
        leder = _klient(_bruker('leder', 'skriv_leder'))
        self.assertEqual(self._put({'posisjon': {'aktiv': True}}, leder).status_code, 403)
        self.assertFalse(posisjon.lopende_aktiv())

    def test_lagret_soppel_gir_standard_og_klemmes(self):
        AppSetting.set_i_portal(posisjon.SEKUNDER_NOKKEL, '{ikke json')
        self.assertEqual(posisjon.sekunder(), posisjon.STANDARD)
        AppSetting.set_i_portal(posisjon.SEKUNDER_NOKKEL,
                                json.dumps({'Akutt': 5, 'Haster': 99999, 'Vanlig': 'x', 'Drift': 0}))
        tall = posisjon.sekunder()
        self.assertEqual((tall['Akutt'], tall['Haster'], tall['Vanlig'], tall['Drift']),
                         (posisjon.MIN_S, posisjon.MAKS_S, 300, 0))

    def test_endringen_auditlogges(self):
        from audit.models import AuditLog
        self._put({'posisjon': {'aktiv': True, 'sekunder': {'Akutt': 20}}})
        felt = set(AuditLog.objects.values_list('field_name', flat=True))
        self.assertTrue(any(f.startswith(posisjon.AKTIV_NOKKEL) for f in felt), felt)
        self.assertTrue(any(f.startswith(posisjon.SEKUNDER_NOKKEL) for f in felt), felt)


class LopendeStienTests(_Basis):
    """`POST api/posisjon/lopende/` — serveren er bremsen."""

    def setUp(self):
        super().setUp()
        _slaa_paa()

    def test_sendes_til_bilmarkoren_med_navnet_fra_basen(self):
        pos = _pos()
        with mock.patch(SEND, return_value=True) as send:
            resp = self._send({'posisjon': pos})
        self.assertEqual(resp.status_code, 200, resp.content)
        navn, lat, lon, tid = send.call_args.args
        self.assertEqual((navn, lat, lon, tid.isoformat()), ('Haugesund 56', 59.4136, 5.2683, pos['tid']))
        self.assertEqual(send.call_args.kwargs['vakt'], self.vakt)
        self.assertFalse(resp.json()['data']['onsket'])

    def test_bremsen_avviser_neste_innenfor_intervallet(self):
        with mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send().status_code, 200)
            self.assertEqual(self._send().status_code, 429)
            self.assertEqual(send.call_count, 1)
            cache.delete(f'oppdrag:posisjon_lopende:{self.enhet.pk}')
            self.assertEqual(self._send().status_code, 200)

    def test_bremsen_er_under_intervallet_og_aldri_under_ti(self):
        self.assertEqual(posisjon.bremse_s(300), 240)
        self.assertEqual(posisjon.bremse_s(30), 24)
        self.assertEqual(posisjon.bremse_s(12), 10)

    def test_bremsen_maaler_mot_intervallet_naa(self):
        """Sendt på «uten oppdrag» (5 min), så ut på akutt: neste går etter 24 s, ikke
        etter de fire minuttene den forrige sendingen ville bremset."""
        nokkel = f'oppdrag:posisjon_lopende:{self.enhet.pk}'
        with mock.patch(SEND, return_value=True):
            self.assertEqual(self._send().status_code, 200)
            self._rykk_ut('Akutt')
            cache.set(nokkel, timezone.now().timestamp() - 20)
            self.assertEqual(self._send().status_code, 429)
            cache.set(nokkel, timezone.now().timestamp() - 25)
            self.assertEqual(self._send().status_code, 200)

    def test_av_ikke_paa_eller_av_vakt_er_409(self):
        with mock.patch(SEND, return_value=True) as send:
            posisjon.lagre({'aktiv': False})
            self.assertEqual(self._send().status_code, 409)
            posisjon.lagre({'aktiv': True})
            Enhet.objects.filter(pk=self.enhet.pk).update(posisjonsdeling=choices.POSISJONSDELING_AV)
            self.assertEqual(self._send().status_code, 409)
            Enhet.objects.filter(pk=self.enhet.pk).update(
                posisjonsdeling=choices.POSISJONSDELING_DELER, pa_vakt=False)
            self.assertEqual(self._send().status_code, 409)
        send.assert_not_called()

    def test_kroppen_er_lukket_og_posisjonen_gyldig(self):
        with mock.patch(SEND, return_value=True) as send:
            for kropp in ({'posisjon': _pos(), 'navn': 'Falsk'}, {'pos': _pos()},
                          {'posisjon': _pos(lat=91)}, {'posisjon': _pos(tid='i går')}):
                with self.subTest(kropp=kropp):
                    self.assertEqual(self._send(kropp).status_code, 400)
        send.assert_not_called()

    def test_bare_enhetskontoer_og_bare_med_kobling(self):
        sentral = _klient(_bruker('sentral', 'skriv_full'))
        self.assertEqual(sentral.post(LOPENDE, data=json.dumps({'posisjon': _pos()}),
                                      content_type='application/json').status_code, 403)
        with override_settings(KART_URL=''):
            self.assertEqual(self._send().status_code, 409)

    def test_kartet_som_ikke_tar_imot_gir_424(self):
        with mock.patch(SEND, return_value=False):
            self.assertEqual(self._send().status_code, 424)


class HentPosisjonTests(_Basis):
    """«Hent posisjon» fra KO — merket på enheten, svaret på bilens neste poll."""

    def setUp(self):
        super().setUp()
        _slaa_paa()
        self.operator = _bruker('kari', 'skriv_full')
        self.ko = _klient(self.operator)

    def _hent(self, enhet=None, klient=None):
        return (klient or self.ko).post(
            f'/oppdrag/api/enheter/{(enhet or self.enhet).pk}/hent-posisjon/',
            data='{}', content_type='application/json')

    def _alle(self, kropp=None):
        return self.ko.post('/oppdrag/api/enheter/hent-posisjon/', data=json.dumps(kropp or {}),
                            content_type='application/json')

    def test_hele_runden_kortet_pollen_og_svaret(self):
        resp = self._hent()
        self.assertEqual(resp.status_code, 202, resp.content)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjon_bedt_av, 'kari')
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '1')
        with mock.patch(SEND, return_value=True):
            svar = self._send()
        self.assertTrue(svar.json()['data']['onsket'])
        self.enhet.refresh_from_db()
        self.assertGreaterEqual(self.enhet.posisjon_mottatt_at, self.enhet.posisjon_bedt_at)
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '0', 'besvart')
        kort = self.ko.get('/oppdrag/api/enheter/').json()['data']
        (rad,) = [k for k in kort if k['id'] == self.enhet.pk]
        self.assertEqual(rad['posisjon_bedt_av'], 'kari')
        self.assertIsNotNone(rad['posisjon_mottatt_at'])

    def test_svaret_slipper_forbi_bremsen_og_passiv_vakt(self):
        """Det er KO som spør, ikke en klokke — også i passiv vakt (André: «ja»)."""
        self._passiv()
        self.assertEqual(self._intervall(), 0)
        self._hent()
        with mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send().status_code, 200)
            self.assertEqual(self._send().status_code, 409, 'bare den ene sendingen KO ba om')
        self.assertEqual(send.call_count, 1)

    def test_svar_som_ikke_kom_fram_til_kartet_er_ikke_mottatt(self):
        self._hent()
        with mock.patch(SEND, return_value=False):
            self.assertEqual(self._send().status_code, 424)
        self.enhet.refresh_from_db()
        self.assertIsNone(self.enhet.posisjon_mottatt_at)
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '1', 'bilen prøver igjen')

    def test_forespoorselen_gaar_ut_etter_fristen(self):
        self._hent()
        Enhet.objects.filter(pk=self.enhet.pk).update(
            posisjon_bedt_at=timezone.now() - posisjon.HENT_FRIST - timedelta(seconds=1))
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '0')

    def test_hovedbryteren_av_slaar_av_hentingen_ogsaa(self):
        self._hent()
        posisjon.lagre({'aktiv': False})
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '0')
        self.assertEqual(self._hent().status_code, 409)

    def test_ny_henting_etter_et_svar_er_et_nytt_onske(self):
        """Et svar på forrige henting svarer ikke på denne."""
        self._hent()
        with mock.patch(SEND, return_value=True):
            self._send()
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '0')
        Enhet.objects.filter(pk=self.enhet.pk).update(
            posisjon_mottatt_at=timezone.now() - timedelta(seconds=30))
        self._hent()
        self.assertEqual(self._poll()['X-Posisjon-Onsket'], '1')

    def test_svar_etter_at_bryteren_ble_slaatt_av_avvises(self):
        """Av betyr «slik det var»: ingen sending utenom stemplingen, heller ikke et
        svar på en henting som sto åpen da admin slo av."""
        self._passiv()
        self._hent()
        posisjon.lagre({'aktiv': False})
        with mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send().status_code, 409)
        send.assert_not_called()

    def test_kortet_sier_om_hentingen_kan_virke(self):
        def kan():
            kort = self.ko.get('/oppdrag/api/enheter/').json()['data']
            return [k['posisjon_kan_hentes'] for k in kort if k['id'] == self.enhet.pk][0]
        self.assertTrue(kan())
        Enhet.objects.filter(pk=self.enhet.pk).update(posisjonsdeling=choices.POSISJONSDELING_AV)
        self.assertFalse(kan(), 'knappen skal ikke føre til en 409')

    def test_hindringene(self):
        for felt, verdi in (('posisjonsdeling', choices.POSISJONSDELING_AV),
                            ('posisjonsdeling', choices.POSISJONSDELING_NEKTET),
                            ('posisjonsdeling', choices.POSISJONSDELING_UTILGJENGELIG),
                            ('pa_vakt', False), ('user', None)):
            with self.subTest(felt=felt, verdi=verdi):
                enhet = Enhet.objects.create(navn=f'Test {felt} {verdi}', user=_bruker(f'b{felt}{verdi}'))
                setattr(enhet, felt, verdi)
                enhet.save()
                self.assertEqual(self._hent(enhet).status_code, 409)
                enhet.refresh_from_db()
                self.assertIsNone(enhet.posisjon_bedt_at)
        with override_settings(KART_URL=''):
            self.assertEqual(self._hent().status_code, 409)

    def test_ikke_hoert_fra_er_ingen_hindring(self):
        """Skjermen kan være på siden uten å ha meldt seg — svaret står på kortet."""
        self.assertEqual(self.enhet.posisjonsdeling, choices.POSISJONSDELING_UKJENT)
        self.assertEqual(self._hent().status_code, 202)

    def test_bare_skriv_full_og_ikke_bilen(self):
        self.assertEqual(self._hent(klient=_klient(_bruker('stempler', 'skriv_handling'))).status_code, 403)
        self.assertEqual(self._hent(klient=self.bil).status_code, 403)
        self.enhet.refresh_from_db()
        self.assertIsNone(self.enhet.posisjon_bedt_at)

    def test_fra_alle_i_en_gruppe_hopper_over_de_som_ikke_kan(self):
        ambulanse = Enhetstype.objects.create(navn='Testambulanse')
        Enhet.objects.filter(pk__in=[self.enhet.pk, self.annen_enhet.pk]).update(enhetstype=ambulanse)
        uten_konto = self.annen_enhet
        tredje = Enhet.objects.create(navn='Karmøy 51', user=_bruker('karmoy51'),
                                      enhetstype=ambulanse,
                                      posisjonsdeling=choices.POSISJONSDELING_AV)
        utenfor = Enhet.objects.create(navn='Lege 02', user=_bruker('lege02'))
        resp = self._alle({'type': ambulanse.pk})
        self.assertEqual(resp.status_code, 202, resp.content)
        self.assertEqual(resp.json()['data']['bedt'], [self.enhet.pk])
        self.assertEqual(resp.json()['data']['hoppet_over'], 2)
        bedt = set(Enhet.objects.filter(posisjon_bedt_at__isnull=False).values_list('pk', flat=True))
        self.assertEqual(bedt, {self.enhet.pk})
        self.assertNotIn(utenfor.pk, bedt)
        self.assertNotIn(uten_konto.pk, bedt)
        self.assertNotIn(tredje.pk, bedt)

    def test_fra_alle_uten_type_og_uten_avgrensning(self):
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(user=_bruker('karmoy12'))
        typet = Enhet.objects.create(navn='Typet', user=_bruker('typet'),
                                     enhetstype=Enhetstype.objects.create(navn='Testambulanse'))
        self.assertEqual(set(self._alle({'type': None}).json()['data']['bedt']),
                         {self.enhet.pk, self.annen_enhet.pk})
        self.assertEqual(set(self._alle().json()['data']['bedt']),
                         {self.enhet.pk, self.annen_enhet.pk, typet.pk})

    def test_fra_alle_der_ingen_kan_svare_er_409(self):
        Enhet.objects.update(posisjonsdeling=choices.POSISJONSDELING_AV)
        self.assertEqual(self._alle().status_code, 409)
        self.assertEqual(self._alle({'type': 'x'}).status_code, 400)

    def test_fra_alle_oker_endringsnummeret(self):
        with mock.patch('oppdrag.endringer.oppdrag_endret') as endret:
            self._alle()
        endret.assert_called_with(alle=True)

    def test_signalet_sendes_med_hvem_og_hva(self):
        mottaker = mock.Mock()
        posisjon.posisjon_hentet.connect(mottaker, weak=False)
        self.addCleanup(posisjon.posisjon_hentet.disconnect, mottaker)
        self._hent()
        kw = mottaker.call_args.kwargs
        self.assertEqual((kw['enheter'], kw['bruker'], kw['antall_totalt']),
                         ([self.enhet], self.operator, None))
        self._alle()
        self.assertEqual(mottaker.call_args.kwargs['antall_totalt'], 2, 'på vakt, også de som hoppes over')
        self.assertEqual(mottaker.call_args.kwargs['enheter'], [self.enhet])


class IngenKoordinaterIPortalenTests(_Basis):
    """«Ingenting lagret i portalen» — det som står på enheten er når og hvem."""

    def test_enheten_har_ingen_posisjonsfelt(self):
        felt = {f.name for f in Enhet._meta.get_fields()}
        self.assertFalse({'lat', 'lon', 'posisjon_lat', 'posisjon_lon', 'koordinater'} & felt)
        self.assertTrue({'posisjon_bedt_at', 'posisjon_bedt_av', 'posisjon_mottatt_at'} <= felt)
        self.assertFalse(hasattr(Oppdrag, 'lat'))


# ── Klokka i bilen, i node ───────────────────────────────────────────────────

import unittest  # noqa: E402

from patients.js_test_utils import (  # noqa: E402
    BIL_LOPENDE, INNLOGGET, INNLOGGET_STUBB, OPPDRAG_ENHET_JS, PORTAL_UTILS_JS, build_harness,
    node_available, run_node,
)

KLOKKE_HARNESS = (
    INNLOGGET,
    (PORTAL_UTILS_JS, ('klokke',)),
    (OPPDRAG_ENHET_JS, ('lastMine', 'harNyDelt', 'erNyDelt', 'nyeOppdrag', 'projiser', 'koNokkel',
                        'koLes', 'lagNokkel', 'bilinnstillinger', 'posisjonLinjeTekst',
                        'tegnPosisjonLinje', 'tegnSendPosisjon', 'sendPosisjonSperret',
                        'bryterSperret', 'kartKoblingAktiv', 'delPosisjonNokkel', 'delerPosisjon',
                        'paVaktNokkel', 'erPaVakt', 'notePaVakt', 'posisjonsdelingTilstand',
                        'posisjonMaksAlderMs', 'medFrist', 'posisjonFristMs', '_hentPosisjonEnGang',
                        *BIL_LOPENDE)),
)

#: Et DOM med linja og «KO hentet»-feltet, en poll som svarer med `svarHeadere`, og
#: `kartkall` som fanger det klokka sender. `gpsKall` teller engangsspørsmålene.
KLOKKE_FORSPILL = """
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
  removeItem: (k) => { delete m[k]; } }; })();
let mineOppdrag = []; let etagMine = null;
function renderAlt() {} function lydSkalSpille() { return false; } function pipNytt() {}
const el = {};
const lag = (id) => (el[id] = el[id] || { id, textContent: '', disabled: false, checked: true,
  klasser: new Set(['d-none']), classList: { toggle(k, v) { v ? el[id].klasser.add(k) : el[id].klasser.delete(k); } } });
globalThis.document = { getElementById: (id) => lag(id) };
let svarHeadere = {}; const kartkall = []; let kartSvar = { ok: true, status: 200, data: {} };
globalThis.apiFetch = async (url, opts) => {
  if (url === '/oppdrag/api/posisjon/lopende/') {
    kartkall.push(JSON.parse(opts.body));
    if (kartSvar === 'nett') throw new Error('offline');
    return { ok: kartSvar.ok, status: kartSvar.status, json: async () => ({ data: kartSvar.data }) };
  }
  return { ok: true, status: 304, headers: { get: (n) => svarHeadere[n] ?? null } };
};
let gpsKall = 0;
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { geolocation: {
  getCurrentPosition(ok) { gpsKall += 1; ok({ coords: { latitude: 60.1, longitude: 6.1 }, timestamp: Date.now() }); },
} } });
const NAA = Date.now();
const fix = (s) => ({ lat: 59.4136, lon: 5.2683, tid: new Date(NAA - s * 1000).toISOString() });
globalThis.OPPDRAG_KART_KOBLING = true;
globalThis.bilensPosisjonStatus = 'ok';
globalThis.OPPDRAG_BILINNSTILLINGER = { posisjon: { aktiv: true, sekunder: {
  Akutt: 30, Haster: 30, Vanlig: 300, Drift: 300, Plassering: 300, uten: 300 } } };
"""


def _kjor_klokke(kode):
    ut = run_node(INNLOGGET_STUBB + build_harness(KLOKKE_HARNESS), '(async () => {\n' + kode + '\n})();',
                  preamble=KLOKKE_FORSPILL)
    return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KlokkaIBilenTests(unittest.TestCase):

    def test_regelen_for_naar_det_sendes(self):
        (ut,) = _kjor_klokke("""
            const t = [];
            const sett = (intervall, onsket) => { globalThis.lopendeIntervallS = intervall;
              globalThis.posisjonOnsket = onsket; };
            sett(30, false); t.push(lopendeSkalSende(NAA));
            globalThis.lopendeSendtMs = NAA - 29000; t.push(lopendeSkalSende(NAA));
            globalThis.lopendeSendtMs = NAA - 30000; t.push(lopendeSkalSende(NAA));
            sett(0, false); t.push(lopendeSkalSende(NAA));
            sett(0, true); t.push(lopendeSkalSende(NAA));
            globalThis.lopendeSendtMs = NAA; sett(30, true); t.push(lopendeSkalSende(NAA));
            localStorage.setItem(delPosisjonNokkel(), '0'); t.push(lopendeSkalSende(NAA));
            localStorage.setItem(delPosisjonNokkel(), '1');
            localStorage.setItem(paVaktNokkel(), '0'); t.push(lopendeSkalSende(NAA));
            localStorage.setItem(paVaktNokkel(), '1');
            globalThis.OPPDRAG_KART_KOBLING = false; t.push(lopendeSkalSende(NAA));
            globalThis.OPPDRAG_KART_KOBLING = true;
            globalThis.lopendeFeiletMs = NAA - 29000; t.push(lopendeSkalSende(NAA));
            globalThis.lopendeFeiletMs = NAA - 30000; t.push(lopendeSkalSende(NAA));
            globalThis.lopendePagar = true; t.push(lopendeSkalSende(NAA));
            console.log(JSON.stringify(t));""")
        self.assertEqual(ut, [
            'intervall', None, 'intervall',   # første gang, for tidlig, akkurat nå
            None, 'onsket',                   # 0 er ingen klokke, men KO kan spørre
            'onsket',                         # KO går foran klokka
            None, None, None,                 # bryteren, av vakt, uten kobling
            None, 'onsket',                   # 30 s etter et forsøk som feilet
            None,                             # midt i en sending
        ])

    def test_pollen_setter_intervallet_og_klokka_sender_ferskt(self):
        (ut,) = _kjor_klokke("""
            svarHeadere = { 'X-Posisjon-Intervall': '30', 'X-Posisjon-Onsket': '0' };
            await lastMine();
            globalThis.bilensPosisjon = fix(5);
            await lopendeTikk();
            await lopendeTikk();
            console.log(JSON.stringify({ intervall: posisjonIntervallS(), kall: kartkall.length,
              lat: kartkall[0].posisjon.lat, gps: gpsKall }));""")
        self.assertEqual(ut, {'intervall': 30, 'kall': 1, 'lat': 59.4136, 'gps': 0},
                         'én sending per intervall, med fixen i minnet')

    def test_gammel_fix_spor_telefonen_en_gang(self):
        """En telefon som står stille melder ingen ny fix til `watchPosition`."""
        (ut,) = _kjor_klokke("""
            globalThis.lopendeIntervallS = 30;
            globalThis.bilensPosisjon = fix(31);
            await lopendeTikk();
            console.log(JSON.stringify({ gps: gpsKall, lat: kartkall[0].posisjon.lat }));""")
        self.assertEqual(ut, {'gps': 1, 'lat': 60.1})

    def test_sist_sendt_vises_etter_en_sending_og_ikke_foer(self):
        """André: «bil enhet ser ikke når sist ble sendt». Gjennom den ekte sendingen."""
        (ut,) = _kjor_klokke("""
            globalThis.lopendeIntervallS = 30; globalThis.bilensPosisjon = fix(5);
            tegnPosisjonLinje();
            const foer = [el['posisjon-ko-hentet'].textContent, el['posisjon-ko-hentet'].klasser.has('d-none')];
            await lopendeTikk();
            const etter = [el['posisjon-ko-hentet'].textContent, el['posisjon-ko-hentet'].klasser.has('d-none')];
            console.log(JSON.stringify({ foer, etter }));""")
        self.assertEqual(ut['foer'], ['', True])
        self.assertRegex(ut['etter'][0], r'^Sist sendt \d\d:\d\d:\d\d\.$')
        self.assertFalse(ut['etter'][1])

    def test_nektet_sender_ingenting_og_venter(self):
        (ut,) = _kjor_klokke("""
            globalThis.lopendeIntervallS = 30;
            globalThis.bilensPosisjonStatus = 'nektet';
            await lopendeTikk();
            console.log(JSON.stringify({ gps: gpsKall, kall: kartkall.length,
              venter: lopendeSkalSende(Date.now()) }));""")
        self.assertEqual(ut, {'gps': 0, 'kall': 0, 'venter': None})

    def test_ko_onsket_sendes_paa_pollen_og_linja_sier_det(self):
        """B2: «KO hentet posisjonen 21:14» — gjennom den ekte inngangen, pollen."""
        (ut,) = _kjor_klokke("""
            globalThis.bilensPosisjon = fix(5);
            kartSvar = { ok: true, status: 200, data: { onsket: true, sendt_at: '2026-10-19T19:14:00Z' } };
            svarHeadere = { 'X-Posisjon-Intervall': '0', 'X-Posisjon-Onsket': '1' };
            await lastMine();
            await new Promise((r) => setTimeout(r, 0));
            console.log(JSON.stringify({ kall: kartkall.length, onsket: globalThis.posisjonOnsket,
              hentet: el['posisjon-ko-hentet'].textContent,
              synlig: !el['posisjon-ko-hentet'].klasser.has('d-none') }));""")
        self.assertEqual(ut['kall'], 1)
        self.assertFalse(ut['onsket'])
        self.assertRegex(ut['hentet'], r'^Sist sendt \d\d:\d\d:\d\d\. KO hentet posisjonen \d\d:\d\d\.$')
        self.assertTrue(ut['synlig'])

    def test_feil_og_nei_fra_serveren(self):
        (ut,) = _kjor_klokke("""
            const t = [];
            globalThis.lopendeIntervallS = 30; globalThis.bilensPosisjon = fix(5);
            kartSvar = 'nett'; await lopendeTikk();
            t.push([kartkall.length, globalThis.lopendeFeiletMs > 0, lopendeSkalSende(Date.now())]);
            globalThis.lopendeFeiletMs = 0; globalThis.lopendeSendtMs = 0;
            globalThis.lopendeIntervallS = 300; kartSvar = { ok: false, status: 429, data: {} };
            await lopendeTikk();
            t.push([kartkall.length, lopendeSkalSende(Date.now()), lopendeSkalSende(Date.now() + 31000)]);
            console.log(JSON.stringify(t));""")
        self.assertEqual(ut, [[1, True, None], [2, None, None]],
                         'uten dekning: nytt forsøk om 30 s; 429: vent et helt intervall, ikke 30 s')

    def test_linja_med_tallene_fra_innstillingene(self):
        (ut,) = _kjor_klokke("""
            const t = [];
            globalThis.lopendeIntervallS = 30; t.push(posisjonLinjeTekst());
            globalThis.lopendeIntervallS = 0; t.push(posisjonLinjeTekst());
            globalThis.OPPDRAG_BILINNSTILLINGER.posisjon.aktiv = false; t.push(posisjonLinjeTekst());
            const o = (s) => posisjonOversiktTekst(s);
            t.push(o({ Akutt: 30, Haster: 30, Vanlig: 300, Drift: 300, Plassering: 300, uten: 300 }));
            t.push(o({ Akutt: 60, Haster: 60, Vanlig: 60, Drift: 60, Plassering: 60, uten: 60 }));
            t.push(o({ Akutt: 15, Haster: 45, Vanlig: 120, Drift: 120, Plassering: 120, uten: 0 }));
            t.push(o({ Akutt: 0, Haster: 0, Vanlig: 0, Drift: 0, Plassering: 0, uten: 0 }));
            t.push(o({ Akutt: 90, Haster: 300, Vanlig: 300, Drift: 300, Plassering: 300, uten: 300 }));
            console.log(JSON.stringify(t));""")
        self.assertEqual(ut, [
            'Posisjon sendes til KO hvert 30. sekund på akutt og haster, hvert 5. minutt ellers. '
            'KO ser at den deles.',
            'Posisjon sendes til KO ved stempling, ikke løpende nå. KO ser at den deles.',
            'Posisjon sendes til KO ved stempling. KO ser at den deles.',
            'hvert 30. sekund på akutt og haster, hvert 5. minutt ellers',
            'hvert minutt',
            'hvert 15. sekund på akutt, hvert 45. sekund på haster, '
            'hvert 2. minutt på vanlig, drift og plassering',
            '',
            'hvert 90. sekund på akutt, hvert 5. minutt ellers',
        ])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class SkjemaetIValglisteneTests(unittest.TestCase):
    """«Valglister → Bilen»: hovedbryteren, ett tall per tilstand, og «Fyll alle»."""

    def _kjor(self, kode):
        from patients.js_test_utils import OPPDRAG_SENTRAL_JS
        from .tests_runde_d import _konst
        harness = _konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE') + build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (OPPDRAG_SENTRAL_JS, ('_posisjonSkjema', 'posisjonTilstander', 'fyllPosisjonAlle',
                                  'posisjonFraSkjema')),
        ))
        dom = """
            const el = {};
            globalThis.document = { getElementById: (id) => el[id] || null };
            const bygg = (html) => { for (const [tagg] of html.matchAll(/<input[^>]*>/g)) {
              const id = (tagg.match(/id="([^"]+)"/) || [])[1]; if (!id) continue;
              el[id] = { value: (tagg.match(/value="([^"]*)"/) || [])[1] ?? '', checked: / checked/.test(tagg) }; } };
        """
        return run_node(harness, dom + kode)

    def test_skjemaet_tegnes_samles_og_fylles(self):
        ut = self._kjor("""
            const html = _posisjonSkjema({ aktiv: true, sekunder: { Akutt: 30, Haster: 30, Vanlig: 300,
              Drift: 300, Plassering: 300, uten: 0 } });
            bygg(html);
            const foer = posisjonFraSkjema();
            el['posisjon-fyll'].value = '120'; fyllPosisjonAlle();
            el['posisjon-sek-Akutt'].value = '';
            console.log(JSON.stringify({ foer, etter: posisjonFraSkjema(),
              rader: (html.match(/posisjon-sek-/g) || []).length }));
        """)
        data = json.loads([l for l in ut.strip().splitlines() if l != 'OK'][-1])
        self.assertEqual(data['rader'], 6)
        self.assertEqual(data['foer'], {'aktiv': True, 'sekunder': {
            'Akutt': 30, 'Haster': 30, 'Vanlig': 300, 'Drift': 300, 'Plassering': 300, 'uten': 0}})
        self.assertEqual(data['etter']['sekunder'], {
            'Haster': 120, 'Vanlig': 120, 'Drift': 120, 'Plassering': 120, 'uten': 120},
            '«Fyll alle» fyller alle; et tomt felt sendes ikke, så tallet står')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KortetIKoTests(unittest.TestCase):
    """Skisse A: knappen per bil, «Hent posisjon fra alle» per gruppe, svaret på kortet."""

    def _kjor(self, kode):
        from patients.js_test_utils import KORT_HENTING, OPPDRAG_SENTRAL_JS
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_SENTRAL_JS, (*KORT_HENTING, 'hentPosisjon', 'hentPosisjonAlle')),
        ))
        oppsett = """
            globalThis.window = { OPPDRAG_TILGANG: { kanSkrive: true } };
            const NAA = Date.now();
            const iso = (s) => new Date(NAA - s * 1000).toISOString();
            const kall = []; let svar = { ok: true, body: { status: 'ok' } };
            globalThis.apiFetch = async (url, opts) => { kall.push({ url, body: opts.body ?? null });
              return { ok: svar.ok, json: async () => svar.body }; };
            globalThis.alert = (m) => kall.push({ alert: m });
            let lastet = 0; let etagEnheter = 'x';
            globalThis.lastAlt = async () => { lastet += 1; };
        """
        ut = run_node(harness, oppsett + '(async () => {\n' + kode + '\n})();')
        return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']

    def test_tilstanden(self):
        (ut,) = self._kjor("""
            const t = (bedt, mottatt) => hentingTilstand({ posisjon_bedt_at: bedt === null ? null : iso(bedt),
              posisjon_mottatt_at: mottatt === null ? null : iso(mottatt) }, NAA);
            console.log(JSON.stringify([
              t(null, null), t(10, null), t(44, null), t(46, null), t(599, null), t(601, null),
              t(20, 5), t(20, 30), t(700, 599), t(700, 601),
            ]));""")
        self.assertEqual(ut, [
            None, 'venter', 'venter', 'kom_ikke', 'kom_ikke', None,
            'mottatt',     # svar etter forespørselen
            'venter',      # et svar eldre enn forespørselen er ikke et svar
            'mottatt', None,
        ])

    def test_linja_og_knappen(self):
        (ut,) = self._kjor("""
            const e = { id: 4, navn: 'Haugesund <56>', posisjon_kan_hentes: true };
            const r = {};
            r.knapp = hentPosisjonKnapp(e);
            r.venter = hentPosisjonKnapp({ ...e, posisjon_bedt_at: iso(5) });
            r.kanIkke = hentPosisjonKnapp({ ...e, posisjon_kan_hentes: false });
            window.OPPDRAG_TILGANG.kanSkrive = false; r.leser = hentPosisjonKnapp(e);
            r.mottatt = hentingLinje({ posisjon_bedt_at: iso(30), posisjon_mottatt_at: iso(20) }, NAA);
            r.komIkke = hentingLinje({ posisjon_bedt_at: iso(60) }, NAA);
            r.ingen = hentingLinje({}, NAA);
            console.log(JSON.stringify(r));""")
        self.assertIn('data-action="hentPosisjon" data-id="4"', ut['knapp'])
        self.assertIn('Haugesund &lt;56&gt;', ut['knapp'])
        self.assertNotIn('disabled', ut['knapp'])
        self.assertIn(' disabled', ut['venter'], 'ett trykk, ett svar')
        self.assertEqual((ut['kanIkke'], ut['leser']), ('', ''))
        self.assertIn('Posisjon mottatt', ut['mottatt'])
        self.assertIn('se kartet', ut['mottatt'])
        self.assertIn('Meld på samband', ut['komIkke'])
        self.assertEqual(ut['ingen'], '')

    def test_fra_alle_knappen_og_kroppen(self):
        (ut,) = self._kjor("""
            const r = {};
            r.knapp = hentAlleKnapp({ type: '3', enheter: [{ posisjon_kan_hentes: false }, { posisjon_kan_hentes: true }] });
            r.ingen = hentAlleKnapp({ type: '3', enheter: [{ posisjon_kan_hentes: false }] });
            await hentPosisjonAlle('type:3');
            await hentPosisjonAlle('type:');
            await hentPosisjon(7);
            svar = { ok: false, body: { status: 'error', message: 'Haugesund 56 er ikke på vakt.' } };
            await hentPosisjon(8);
            console.log(JSON.stringify({ ...r, kall, lastet, etagEnheter }));""")
        self.assertIn('data-arg="type:3"', ut['knapp'])
        self.assertEqual(ut['ingen'], '')
        self.assertEqual([k.get('url') for k in ut['kall'][:3]], [
            '/oppdrag/api/enheter/hent-posisjon/', '/oppdrag/api/enheter/hent-posisjon/',
            '/oppdrag/api/enheter/7/hent-posisjon/'])
        self.assertEqual(json.loads(ut['kall'][0]['body']), {'type': 3})
        self.assertEqual(json.loads(ut['kall'][1]['body']), {'type': None}, 'gruppa uten type')
        self.assertEqual(ut['kall'][-1], {'alert': 'Haugesund 56 er ikke på vakt.'},
                         'serverens grunn, ikke vår egen')
        self.assertEqual(ut['lastet'], 3)

    def test_lista_tegnes_paa_nytt_naar_venter_blir_kom_ikke(self):
        (ut,) = self._kjor("""
            console.log(JSON.stringify([
              nesteHentingOvergangMs([{ posisjon_bedt_at: iso(40) }, { posisjon_bedt_at: iso(10) }, {}], NAA),
              nesteHentingOvergangMs([{ posisjon_bedt_at: iso(50) }, {}], NAA),
            ]));""")
        self.assertEqual(ut, [5000, None])


@override_settings(SECURE_SSL_REDIRECT=False)
class ErklaeringenTests(_Basis):
    """`/personvern/` oppgir intervallene fra innstillingene, aldri fra malen (A.6)."""

    def test_tallene_og_bryteren_folger_innstillingene(self):
        from django.test import Client
        side = Client().get('/personvern/').content.decode()
        self.assertIn('id="lopende-posisjon"', side)
        self.assertIn('slått av nå', side)
        self.assertIn('hvert 30. sekund', side)
        _slaa_paa(Akutt=20, uten=0)
        side = Client().get('/personvern/').content.decode()
        self.assertIn('<strong>slått på</strong>', side)
        self.assertIn('hvert 20. sekund', side)
        self.assertIn('ikke løpende', side)

    def test_intervallteksten(self):
        self.assertEqual([posisjon.intervall_tekst(s) for s in (0, 15, 60, 90, 300, 3600)],
                         ['ikke løpende', 'hvert 15. sekund', 'hvert minutt', 'hvert 90. sekund',
                          'hvert 5. minutt', 'hvert 60. minutt'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KallstedeneTests(unittest.TestCase):
    """Mutantløgn nummer tre: testene over kaller hjelperne selv. Her går de gjennom
    den ekte inngangen — kortet, lista og «Lagre»."""

    def test_kortet_viser_hentingen(self):
        from .tests_posisjonsdeling import KORT_HARNESS
        bedt = (timezone.now() - timedelta(seconds=10)).isoformat()
        ut = run_node(build_harness(KORT_HARNESS), f"""
            globalThis.window = {{}}; globalThis.OPPDRAG_KART_KOBLING = true;
            globalThis.besetninger = {{}}; globalThis.apenBesetning = null;
            console.log(_enhetskort({{ id: 1, navn: 'H56', status: 'ledig', status_navn: 'Ledig',
              posisjonsdeling: 'deler', posisjon_bedt_at: '{bedt}' }}));""")
        self.assertIn('venter på bilen', ut)

    def test_lista_planlegger_ny_tegning(self):
        from .tests_prodtest_13sep import SYNLIGHET_STUBB, DenDelteListaLeserDenLevendeEnhetslistaTests as D
        bedt = (timezone.now() - timedelta(seconds=10)).isoformat()
        ut = run_node(SYNLIGHET_STUBB + build_harness(D.HARNESS), f"""
            const tidtakere = [];
            globalThis.setTimeout = (f, ms) => {{ tidtakere.push(ms); return 1; }};
            tegnEnhetsliste([{{ id: 1, navn: 'H56', pa_vakt: true, status: 'ledig', status_navn: 'Ledig',
              antall_ventende: 0, posisjon_bedt_at: '{bedt}' }}]);
            console.log(JSON.stringify(tidtakere));""", preamble=D.DOM_STUBB)
        (ms,) = json.loads([l for l in ut.splitlines() if l != 'OK'][-1])
        self.assertGreater(ms, 30000)
        self.assertLess(ms, 37000)

    def test_lagre_sender_posisjonen(self):
        from patients.js_test_utils import OPPDRAG_SENTRAL_JS
        from .tests_runde_d import _konst
        harness = _konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE') + build_harness((
            (OPPDRAG_SENTRAL_JS, ('lagreLydvarsel', 'posisjonTilstander', 'posisjonFraSkjema')),
        ))
        ut = run_node(harness, """
            const el = { 'posisjon-aktiv': { checked: true }, 'posisjon-sek-Akutt': { value: '20' } };
            globalThis.document = { getElementById: (id) => el[id] || null };
            let kropp = null;
            globalThis.withSubmitGuard = async (id, fn) => fn();
            globalThis._verdiKall = async (url, valg) => { kropp = JSON.parse(valg.body); return false; };
            (async () => { await lagreLydvarsel(); console.log(JSON.stringify(kropp.posisjon)); })();""")
        self.assertEqual(json.loads([l for l in ut.splitlines() if l != 'OK'][-1]),
                         {'aktiv': True, 'sekunder': {'Akutt': 20}})
