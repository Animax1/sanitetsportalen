"""KO-tavla (22. sep. 2026): plasseringene, forrangen til hendelser og
oppdrag, og portene.

Tyngden ligger i tjenestelaget (`ko/tavle.py`): en feil der legger seg i data
og gir «Besøk» feil tall, og det ser ingen. Prøvene går gjennom den ekte
inngangen — `services.sett_lag`, `services.lukk_hendelse`, `sett_status` — og
ikke gjennom hjelperne direkte, så et kallsted som forsvinner blir rødt.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.vakt import hent_aktiv_vakt
from ko import services, systemlinjer, tavle
from ko.models import Logglinje, Tavleplassering
from oppdrag import choices
from oppdrag import services as oservices
from oppdrag.models import Enhet, Lokasjon, Oppdrag
from vaktliste.models import Vaktliste
from vaktliste.test_helpers import LAG, gruppe, lag_ressurs

from .tests_hendelseslogg import _bruker, _gi, skift


class _Grunnlag(TestCase):

    def setUp(self):
        self.vakt = hent_aktiv_vakt()
        self.operator = _bruker('ko1')
        self.park = Lokasjon.objects.create(navn='Parkscene')
        self.club = Lokasjon.objects.create(navn='Club Venue')
        self.vl = Vaktliste.objects.create(vakt=self.vakt)
        self.lag1 = lag_ressurs(vaktliste=self.vl, navn='Lag 1', gruppe=gruppe(LAG))
        self.lag2 = lag_ressurs(vaktliste=self.vl, navn='Lag 2', gruppe=gruppe(LAG))
        self.av_vakt = lag_ressurs(vaktliste=self.vl, navn='Lag 9', gruppe=gruppe(LAG))
        for lag in (self.lag1, self.lag2):
            skift(lag)
        self.enhet = Enhet.objects.create(navn='HGSD 56')
        self.bil = lag_ressurs(vaktliste=self.vl, navn='Ambulanse 1', enhet=self.enhet)

    def _plasser(self, ressurs, lokasjon=None, **kw):
        return tavle.plasser(self.vakt, ressurs, bruker=self.operator, lokasjon=lokasjon, **kw)


class HvemStaarPaaTavlaTests(_Grunnlag):

    def test_lag_paa_vakt_og_biler_paa_vakt(self):
        ider = {r.pk for r in tavle.ressurser_paa_tavla()}
        self.assertEqual(ider, {self.lag1.pk, self.lag2.pk, self.bil.pk})
        self.assertNotIn(self.av_vakt.pk, ider, 'uten skift nå står laget ikke på tavla')

    def test_bil_av_vakt_er_borte_og_uten_oppdragstilgang_ingen_biler(self):
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        self.assertNotIn(self.bil.pk, {r.pk for r in tavle.ressurser_paa_tavla()})
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=True)
        self.assertNotIn(self.bil.pk, {r.pk for r in tavle.ressurser_paa_tavla(med_biler=False)})


class PlasserTests(_Grunnlag):

    def test_plasser_og_flytt_lukker_den_forrige(self):
        forste = self._plasser(self.lag1, self.park)
        andre = self._plasser(self.lag1, self.club)
        forste.refresh_from_db()
        self.assertIsNotNone(forste.til)
        self.assertEqual(forste.til, andre.fra, 'ingen luke og ingen overlapp')
        self.assertEqual(Tavleplassering.objects.filter(ressurs=self.lag1, til__isnull=True).count(), 1)

    def test_til_samme_sted_er_en_feil_og_ikke_et_nytt_besok(self):
        self._plasser(self.lag1, self.park)
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.lag1, self.park)
        self.assertEqual(Tavleplassering.objects.filter(ressurs=self.lag1).count(), 1)

    def test_pause_er_en_rad_og_ikke_en_lokasjon(self):
        p = self._plasser(self.lag1, pause=True)
        self.assertTrue(p.pause)
        self.assertIsNone(p.lokasjon)
        # Fra pause til en lokasjon er en flytting som alle andre.
        self._plasser(self.lag1, self.park)
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.lag1, self.park, pause=True)
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.lag1)

    def test_ikke_paa_vakt_og_inaktiv_lokasjon_avvises(self):
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.av_vakt, self.park)
        Lokasjon.objects.filter(pk=self.club.pk).update(er_aktiv=False)
        self.club.refresh_from_db()
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.lag1, self.club)

    def test_uten_plass_lukker_og_to_ganger_er_en_feil(self):
        p = self._plasser(self.lag1, self.park)
        tavle.avslutt(self.vakt, self.lag1, bruker=self.operator)
        p.refresh_from_db()
        self.assertIsNotNone(p.til)
        with self.assertRaises(services.Ugyldig):
            tavle.avslutt(self.vakt, self.lag1, bruker=self.operator)

    def test_hver_flytting_er_en_systemlinje_med_hvem(self):
        self._plasser(self.lag1, self.park)
        self._plasser(self.lag1, self.club)
        tavle.avslutt(self.vakt, self.lag1, bruker=self.operator)
        linjer = Logglinje.objects.filter(systemkode=systemlinjer.TAVLE_FLYTTET).order_by('id')
        self.assertEqual([systemlinjer.tegn(l.systemkode, l.systemdata) for l in linjer],
                         ['Lag 1 → Parkscene', 'Lag 1 → Club Venue (fra Parkscene)',
                          'Lag 1 uten plass (var Club Venue)'])
        self.assertTrue(all(l.forfatter_navn == 'ko1' for l in linjer))

    def test_en_slettet_lokasjon_er_ikke_pause(self):
        """Plassen står igjen med navnet og uten peker (`SET_NULL`). Å sende
        laget i pause etterpå er en flytting, ikke «står der alt»."""
        borte = Lokasjon.objects.create(navn='Midlertidig')
        self._plasser(self.lag1, borte)
        borte.delete()
        p = self._plasser(self.lag1, pause=True)
        self.assertTrue(p.pause)

    def test_basen_nekter_to_aapne_plasseringer(self):
        from django.db import IntegrityError, transaction
        self._plasser(self.lag1, self.park)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tavleplassering.objects.create(vakt=self.vakt, ressurs=self.lag1, ressurs_navn='x',
                                           lokasjon=self.club, fra=timezone.now())


class HendelseneHarForrangTests(_Grunnlag):
    """«Hendelser og oppdrag tar prioritet» (André, 22. sep. 2026)."""

    def _hendelse(self, lokasjon=None):
        return services.opprett_hendelse(self.vakt, 'Besvimt', bruker=self.operator,
                                         lokasjon=lokasjon or self.park)

    def test_laget_paa_hendelsen_kan_ikke_plasseres(self):
        h = self._hendelse()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.lag1, self.club)
        opp = tavle.opptatt([self.lag1], self.vakt)[self.lag1.pk]
        self.assertEqual((opp['merke'], opp['lokasjon_id']), (f'På H{h.hendelsesnummer}', self.park.pk))

    def test_paa_hendelsen_lukker_plassen_og_av_igjen_gir_historikk_og_uten_plass(self):
        p = self._plasser(self.lag1, self.club)
        h = self._hendelse()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        p.refresh_from_db()
        self.assertIsNotNone(p.til, 'plassen laget sto på, lukkes')
        services.sett_lag(h, [], bruker=self.operator)
        hist = Tavleplassering.objects.get(ressurs=self.lag1, hendelse_nummer=h.hendelsesnummer)
        self.assertEqual(hist.lokasjon, self.park)
        self.assertIsNotNone(hist.til)
        self.assertIsNone(tavle.aapen(self.lag1), 'laget står uten plass')
        self.assertNotIn(self.lag1.pk, tavle.opptatt([self.lag1], self.vakt))

    def test_lukket_hendelse_gir_historikk_og_gjenaapning_overlapper_ikke(self):
        h = self._hendelse()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator)
        self.assertEqual(Tavleplassering.objects.filter(hendelse_nummer=h.hendelsesnummer).count(), 1)
        self.assertNotIn(self.lag1.pk, tavle.opptatt([self.lag1], self.vakt), 'lukket = ledig')
        services.gjenapne_hendelse(h, bruker=self.operator)
        h.refresh_from_db()
        services.lukk_hendelse(h, bruker=self.operator, naa=timezone.now() + timedelta(minutes=5))
        rader = list(Tavleplassering.objects.filter(hendelse_nummer=h.hendelsesnummer).order_by('fra'))
        self.assertEqual(len(rader), 2)
        self.assertGreaterEqual(rader[1].fra, rader[0].til, 'andre del begynner der første sluttet')

    def test_av_og_paa_i_samme_oyeblikk_gir_ingen_tom_rad(self):
        """En rad uten varighet ville telt som et besøk i «Besøk»."""
        h = self._hendelse()
        t = timezone.now()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator, naa=t)
        services.sett_lag(h, [], bruker=self.operator, naa=t)
        self.assertFalse(Tavleplassering.objects.filter(hendelse_nummer=h.hendelsesnummer).exists())

    def test_en_aapen_hendelse_i_en_annen_vakt_gjor_ikke_laget_opptatt(self):
        from core.models import Vakt
        gammel = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        h = services.opprett_hendelse(gammel, 'Glemt', bruker=self.operator)
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        self.assertNotIn(self.lag1.pk, tavle.opptatt([self.lag1], self.vakt))

    def test_hendelse_uten_lokasjon_gir_ingen_historikk(self):
        h = services.opprett_hendelse(self.vakt, 'Uten sted', bruker=self.operator)
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        services.lukk_hendelse(h, bruker=self.operator)
        self.assertFalse(Tavleplassering.objects.filter(hendelse_nummer=h.hendelsesnummer).exists())


class BilenPaaOppdragTests(_Grunnlag):

    def _oppdrag(self, lokasjon=None):
        return Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oservices.neste_oppdragsnummer(self.vakt),
            enhet=self.enhet, problemstilling='Pustevansker', hastegrad='Akutt',
            lokasjon=lokasjon or self.park)

    def test_bilen_som_rykker_ut_forlater_plassen_og_er_opptatt_der_oppdraget_er(self):
        p = self._plasser(self.bil, self.club)
        o = self._oppdrag()
        self.assertNotIn(self.bil.pk, tavle.opptatt([self.bil], self.vakt), 'tildelt er ikke opptatt')
        oservices.sett_status(o, choices.RYKKER_UT, enhet=self.enhet)
        p.refresh_from_db()
        self.assertIsNotNone(p.til, 'signalet lukket plassen')
        opp = tavle.opptatt([self.bil], self.vakt)[self.bil.pk]
        self.assertEqual(opp['lokasjon_id'], self.park.pk)
        self.assertTrue(opp['merke'].startswith(f'O{o.oppdragsnummer}'))
        with self.assertRaises(services.Ugyldig):
            self._plasser(self.bil, self.club)

    def test_fremme_uten_rykker_ut_lukker_ogsaa(self):
        p = self._plasser(self.bil, self.club)
        # Sentralbordet fører et glemt stempel, med hopp over Rykker ut.
        oservices.foer_status(self._oppdrag(), self.enhet, choices.FREMME, bruker=self.operator,
                              tidspunkt=timezone.now())
        p.refresh_from_db()
        self.assertIsNotNone(p.til, 'en bil som er fremme er opptatt, uansett hva som ble trykket først')

    def test_et_stempel_foert_bakover_gir_ingen_plass_som_slutter_foer_den_begynte(self):
        """Sentralbordet fører et glemt Rykker ut ti minutter tilbake — etter
        at bilen ble satt på tavla. En rad som slutter før den begynner,
        teller negativ tid i «Besøk»."""
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        o.refresh_from_db()
        p = self._plasser(self.bil, self.club)
        oservices.foer_status(o, self.enhet, choices.RYKKER_UT, bruker=self.operator,
                              tidspunkt=p.fra - timedelta(minutes=10))
        p.refresh_from_db()
        self.assertEqual(p.til, p.fra)

    def test_en_tidsretting_paa_et_ferdig_oppdrag_roerer_ikke_plassen(self):
        from oppdrag.models import Statusmelding
        o = self._oppdrag()
        for st in (choices.RYKKER_UT, choices.FREMME, choices.LEDIG):
            oservices.sett_status(o, st, enhet=self.enhet)
        p = self._plasser(self.bil, self.club)
        ut = Statusmelding.objects.filter(oppdrag=o, status=choices.RYKKER_UT).first()
        oservices.korriger_tidspunkt(ut, ut.tidspunkt - timedelta(minutes=2), bruker=self.operator)
        p.refresh_from_db()
        self.assertIsNone(p.til, 'plassen bilen står på nå har ingenting med rettingen å gjøre')

    def test_avreist_har_ingen_rad_og_ledig_er_fri(self):
        o = self._oppdrag()
        for st in (choices.RYKKER_UT, choices.FREMME):
            oservices.sett_status(o, st, enhet=self.enhet)
        oservices.sett_status(o, choices.AVREIST, enhet=self.enhet, sted='sykehus')
        self.assertIsNone(tavle.opptatt([self.bil], self.vakt)[self.bil.pk]['lokasjon_id'])
        oservices.sett_status(o, choices.LEVERER, enhet=self.enhet)
        oservices.sett_status(o, choices.LEDIG, enhet=self.enhet)
        self.assertNotIn(self.bil.pk, tavle.opptatt([self.bil], self.vakt))
        self.assertIsNone(tavle.aapen(self.bil))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(_Grunnlag):

    def _klient(self, ko=None, vaktliste='les', oppdrag='les'):
        self._nr = getattr(self, '_nr', 0) + 1
        b = _bruker(f'b{self._nr}_{ko}_{vaktliste}_{oppdrag}')
        if ko:
            _gi(b, 'ko', ko)
        if vaktliste:
            _gi(b, 'vaktliste', vaktliste)
        if oppdrag:
            _gi(b, 'oppdrag', oppdrag)
        c = Client()
        c.force_login(b)
        return c

    def test_les_gir_tavla_og_vaktlista_kreves(self):
        self.assertEqual(self._klient('les').get('/ko/api/tavle/').status_code, 200)
        self.assertEqual(self._klient('les', vaktliste=None).get('/ko/api/tavle/').status_code, 403)
        self.assertEqual(self._klient(None).get('/ko/api/tavle/').status_code, 403)

    def test_bilene_bare_med_oppdragstilgang(self):
        med = self._klient('les').get('/ko/api/tavle/').json()['data']
        uten = self._klient('les', oppdrag=None).get('/ko/api/tavle/').json()['data']
        self.assertIn('Ambulanse 1', [r['navn'] for r in med['ressurser']])
        self.assertNotIn('Ambulanse 1', [r['navn'] for r in uten['ressurser']])

    def test_skriving_krever_skriv_full_i_ko(self):
        kropp = {'ressurs_id': self.lag1.pk, 'lokasjon_id': self.park.pk}
        self.assertEqual(self._klient('les').post('/ko/api/tavle/plasser/', kropp,
                                                   content_type='application/json').status_code, 403)
        c = self._klient('skriv_full')
        r = c.post('/ko/api/tavle/plasser/', kropp, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(c.post('/ko/api/tavle/plasser/', kropp,
                                content_type='application/json').status_code, 400, 'står der alt')
        self.assertEqual(c.post('/ko/api/tavle/uten-plass/', {'ressurs_id': self.lag1.pk},
                                content_type='application/json').status_code, 200)
        self.assertEqual(self._klient('les').post('/ko/api/tavle/uten-plass/', {'ressurs_id': self.lag1.pk},
                                                   content_type='application/json').status_code, 403)

    def test_bilen_kan_ikke_flyttes_uten_oppdragstilgang(self):
        """Samme regel som visningen: en bil man ikke får se, finnes ikke."""
        kropp = {'ressurs_id': self.bil.pk, 'lokasjon_id': self.park.pk}
        uten = self._klient('skriv_full', oppdrag=None)
        self.assertEqual(uten.post('/ko/api/tavle/plasser/', kropp,
                                   content_type='application/json').status_code, 404)
        self.assertEqual(self._klient('skriv_full').post('/ko/api/tavle/plasser/', kropp,
                                                         content_type='application/json').status_code, 200)
        self.assertEqual(uten.post('/ko/api/tavle/uten-plass/', {'ressurs_id': self.bil.pk},
                                   content_type='application/json').status_code, 404)

    def test_pause_og_ukjente_verdier(self):
        c = self._klient('skriv_full')
        r = c.post('/ko/api/tavle/plasser/', {'ressurs_id': self.lag1.pk, 'pause': True},
                   content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(c.post('/ko/api/tavle/plasser/', {'ressurs_id': 99999, 'lokasjon_id': self.park.pk},
                                content_type='application/json').status_code, 404)
        self.assertEqual(c.post('/ko/api/tavle/plasser/', {'ressurs_id': self.lag1.pk, 'lokasjon_id': 99999},
                                content_type='application/json').status_code, 404)

    def test_svaret_bærer_rader_grupper_og_hele_vaktas_plasseringer(self):
        self._plasser(self.lag1, self.park)
        self._plasser(self.lag1, self.club)
        d = self._klient('les').get('/ko/api/tavle/').json()['data']
        self.assertEqual([r['navn'] for r in d['rader']], ['Club Venue', 'Parkscene'])
        self.assertEqual(len(d['plasseringer']), 2)
        self.assertEqual({g['navn'] for g in d['grupper']}, {r.gruppe.navn for r in (self.lag1, self.bil)})
        lag = next(r for r in d['ressurser'] if r['id'] == self.lag1.pk)
        self.assertIsNone(lag['opptatt'])

    def test_inaktive_lokasjoner_og_andre_vakters_plasseringer_er_ikke_med(self):
        from core.models import Vakt
        Lokasjon.objects.create(navn='Nedlagt', er_aktiv=False)
        gammel = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        Tavleplassering.objects.create(vakt=gammel, ressurs=None, ressurs_navn='Lag 1',
                                       lokasjon=self.park, lokasjon_navn='Parkscene',
                                       fra=timezone.now(), til=timezone.now())
        d = self._klient('les').get('/ko/api/tavle/').json()['data']
        self.assertNotIn('Nedlagt', [r['navn'] for r in d['rader']])
        self.assertEqual(d['plasseringer'], [])
