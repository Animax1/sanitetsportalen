# -*- coding: utf-8 -*-
"""Fase 5 — planleggingstall (§8b).

«Lista skal hjelpe planleggeren å se **belastningen** før vakta, ikke bare
bemanningen.» Bestilt: timer per person, antall skift, skiftlengde og hviletid
mellom skift.

To ting bæres av testene her:

1. **Varsler, ikke sperrer.** Ingenting avvises. Et langt skift merkes, og det
   er alt — noen ganger *må* noen ta et langt skift, og da skal lista si det
   høyt framfor å tvinge planleggeren til å lyve om tidene for å komme videre.
2. **Grensene er organisasjonens.** De ligger i basen, ikke i en `if`, og å
   flytte dem endrer hva alle vaktlister varsler om.

Tallene regnes i `services`, ikke i viewet: et view skal ikke kunne svare på
hva «korteste hvile» betyr.
"""
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from . import services
from .models import Belastningsgrenser, Vaktliste, Vaktpost
from .tests_tilgang import TilgangsBasis, _bruker, _klient


class HviletidTests(SimpleTestCase):
    """`_hviletider` uten en database.

    **Funnet ved mutasjonstesting:** sorteringen inne i hjelperen lot seg
    fjerne uten at noe ble rødt, fordi `Vaktpost.Meta.ordering` alt sorterer
    på `fra_tid` — så testene gjennom basen målte modellens ordering, ikke
    hjelperens. En hjelper skal ikke hvile på at den som kaller den har
    sortert.
    """

    class FalsktSkift:
        def __init__(self, fra, timer):
            self.fra_tid = timezone.now().replace(
                hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=fra)
            self.til_tid = self.fra_tid + timedelta(hours=timer)

    def _hvile(self, *spenn):
        return services._hviletider([self.FalsktSkift(*s) for s in spenn])

    def test_hullene_maales_kronologisk(self):
        self.assertEqual([4.0, 2.0], self._hvile((0, 8), (12, 4), (18, 4)))

    def test_usortert_inndata_gir_samme_svar(self):
        """M55. Rekkefølgen kaller kan komme i er ikke hjelperens ansvar."""
        self.assertEqual(self._hvile((0, 8), (12, 4), (18, 4)),
                         self._hvile((18, 4), (0, 8), (12, 4)))

    def test_ett_skift_har_ingen_huller(self):
        self.assertEqual([], self._hvile((0, 8)))

    def test_overlapp_gir_null(self):
        self.assertEqual([0.0], self._hvile((0, 8), (4, 8)))

    def test_skift_som_henger_sammen_gir_null(self):
        """Rett etter hverandre er null timers hvile, og det er sant."""
        self.assertEqual([0.0], self._hvile((0, 8), (8, 4)))


class OverlappstimerTests(SimpleTestCase):
    """`_overlappstimer` uten en database.

    Punktet sto i TODO fra 14. sep. 2026: docstringen i `_hviletider()`
    lovet tellingen, og den fantes ikke. Planleggerfanen er den første
    funksjonen som *bruker* timesummen til noe (et tak), og et tak som
    telles feil er verre enn ikke noe tak.
    """

    class FalsktSkift:
        def __init__(self, fra, timer):
            self.fra_tid = timezone.now().replace(
                hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=fra)
            self.til_tid = self.fra_tid + timedelta(hours=timer)

    def _overlapp(self, *spenn):
        return services._overlappstimer([self.FalsktSkift(*s) for s in spenn])

    def test_ingen_skift_gir_null(self):
        self.assertEqual(0.0, self._overlapp())

    def test_ett_skift_kan_ikke_overlappe_seg_selv(self):
        self.assertEqual(0.0, self._overlapp((0, 8)))

    def test_skift_med_hull_mellom_gir_null(self):
        self.assertEqual(0.0, self._overlapp((0, 8), (12, 4)))

    def test_skift_som_henger_sammen_gir_null(self):
        """08–16 og 16–20 berører hverandre, men deler ingen time.
        Går denne i null, ville hvert eneste doble skift gitt varsel."""
        self.assertEqual(0.0, self._overlapp((8, 8), (16, 4)))

    def test_maalt_eksempel_fra_todo(self):
        """12:00–20:00 og 16:00–22:00 gir 14 timer skift der personen sto
        i 10. Differansen er de fire timene tellingen skal finne."""
        self.assertEqual(4.0, self._overlapp((12, 8), (16, 6)))

    def test_summen_minus_overlappet_er_tilstedevaerelsen(self):
        """Invarianten regelen er skrevet for, målt i stedet for antatt."""
        skift = [self.FalsktSkift(12, 8), self.FalsktSkift(16, 6)]
        sum_timer = sum(services._timer(vp.fra_tid, vp.til_tid) for vp in skift)
        tilstede = services._timer(skift[0].fra_tid, skift[1].til_tid)
        self.assertEqual(tilstede, sum_timer - services._overlappstimer(skift))

    def test_helt_sammenfallende_skift_teller_hele_lengden(self):
        self.assertEqual(8.0, self._overlapp((0, 8), (0, 8)))

    def test_skift_inni_et_annet_teller_det_korte(self):
        """10–14 ligger helt inne i 08–20. Unionen er fortsatt tolv timer,
        så overlappet er de fire. En union som ble satt til det *siste*
        skiftets slutt ville krympet her."""
        self.assertEqual(4.0, self._overlapp((8, 12), (10, 4)))

    def test_tre_skift_med_et_hull_imellom(self):
        """Hullet skal ikke slå to adskilte klynger sammen: 00–08 og 04–08
        overlapper i fire, 20–24 står for seg."""
        self.assertEqual(4.0, self._overlapp((0, 8), (4, 4), (20, 4)))

    def test_usortert_inndata_gir_samme_svar(self):
        self.assertEqual(self._overlapp((12, 8), (16, 6)),
                         self._overlapp((16, 6), (12, 8)))

    def test_skift_uten_gyldig_spenn_hoppes_over(self):
        tomt = self.FalsktSkift(0, 8)
        tomt.til_tid = None
        self.assertEqual(0.0, services._overlappstimer(
            [tomt, self.FalsktSkift(0, 8)]))

    def test_rundes_en_gang_saa_et_varsel_ikke_fyrer_paa_avrunding(self):
        """Tre skift som ikke overlapper, men som gir 0.01 hvis hvert
        timetall rundes for seg: 02:53–07:27, 07:27–14:40 og 16:56–21:01.

        Tilfellet er **funnet, ikke oppdiktet** — søkt fram blant tilfeldige
        skiftoppsett fordi jeg først skrev ned at avrundingen «gir 0.01»
        uten å ha målt det. Den første varianten jeg prøvde ga −0.03, altså
        et negativt overlapp, som er sin egen slags tull. Denne gir et
        positivt tall, og et positivt tall er det som faktisk slår på
        `har_overlapp` og setter et varsel på en rad der ingen står to
        steder."""
        def kl(t, m, timer, minutter):
            fra = timezone.now().replace(hour=t, minute=m, second=0, microsecond=0)
            skift = self.FalsktSkift(0, 0)
            skift.fra_tid = fra
            skift.til_tid = fra + timedelta(hours=timer, minutes=minutter)
            return skift

        skift = [kl(2, 53, 4, 34), kl(7, 27, 7, 13), kl(16, 56, 4, 5)]
        self.assertEqual(0.0, services._overlappstimer(skift))
        # Og vis hva den naive formen ville gitt, så testen ikke bare er
        # «null er null»: summen av avrundede timetall minus den avrundede
        # unionen er ikke null.
        naiv = round(sum(services._timer(s.fra_tid, s.til_tid) for s in skift)
                     - (services._timer(skift[0].fra_tid, skift[1].til_tid)
                        + services._timer(skift[2].fra_tid, skift[2].til_tid)), 2)
        self.assertEqual(0.01, naiv, 'tilfellet skal faktisk utløse avrundingen')


class BelastningsberegningTests(TilgangsBasis):
    """Regnestykket. Ingen HTTP — reglene skal kunne prøves for seg."""

    def setUp(self):
        super().setUp()
        self.start = timezone.now().replace(minute=0, second=0, microsecond=0)

    def _skift(self, person, fra_time, timer, ressurs=None, **felt):
        return Vaktpost.objects.create(
            ressurs=ressurs or self.res_hgsd, mannskap=person,
            fra_tid=self.start + timedelta(hours=fra_time),
            til_tid=self.start + timedelta(hours=fra_time + timer),
            **felt)

    def _rader(self):
        return services.belastning_per_person(self.vl)

    def test_timer_og_skift_summeres_per_person(self):
        self._skift(self.p_hgsd, 0, 8)
        self._skift(self.p_hgsd, 24, 6)
        rad, = self._rader()
        self.assertEqual('Kari', rad['navn'])
        self.assertEqual(2, rad['antall_skift'])
        self.assertEqual(14.0, rad['timer'])
        self.assertEqual(8.0, rad['lengste_skift'])

    def test_hvilen_er_hullet_mellom_to_skift(self):
        self._skift(self.p_hgsd, 0, 8)      # 00–08
        self._skift(self.p_hgsd, 20, 4)     # 20–24  → 12 timers hvile
        self._skift(self.p_hgsd, 30, 4)     # 30–34  → 6 timers hvile
        rad, = self._rader()
        self.assertEqual(6.0, rad['korteste_hvile'], 'den korteste skal vinne')

    def test_ett_skift_har_ingen_hvile_aa_maale(self):
        """`None`, ikke null. Null timers hvile er en beskjed om noe galt;
        «ingen hvile å måle» er fraværet av et tall."""
        self._skift(self.p_hgsd, 0, 8)
        rad, = self._rader()
        self.assertIsNone(rad['korteste_hvile'])
        self.assertFalse(rad['kort_hvile'])

    def test_overlappende_skift_gir_null_hvile_ikke_negativ(self):
        """Et negativt tall i en «korteste hvile»-kolonne ser ut som en
        regnefeil framfor et varsel."""
        self._skift(self.p_hgsd, 0, 8, ressurs=self.res_hgsd)
        self._skift(self.p_hgsd, 4, 8, ressurs=self.res_fri)
        rad, = self._rader()
        self.assertEqual(0.0, rad['korteste_hvile'])

    def test_rekkefolgen_paa_skiftene_spiller_ingen_rolle(self):
        """Radene kommer i databasens rekkefølge, ikke i tid."""
        self._skift(self.p_hgsd, 30, 4)
        self._skift(self.p_hgsd, 0, 8)
        rad, = self._rader()
        self.assertEqual(22.0, rad['korteste_hvile'])

    def test_sortert_paa_timer_synkende(self):
        """Den som er i ferd med å bli brukt opp skal ligge øverst."""
        self._skift(self.p_hgsd, 0, 4)
        self._skift(self.p_karmoy, 0, 10, ressurs=self.res_karmoy)
        navn = [r['navn'] for r in self._rader()]
        self.assertEqual(['Ola', 'Kari'], navn)

    def test_ledige_plasser_er_ikke_en_person(self):
        """De er et behov, ikke en belastning — og en rad uten navn i en
        persontabell ser ut som en feil."""
        Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=None,
            fra_tid=self.start, til_tid=self.start + timedelta(hours=8))
        self.assertEqual([], self._rader())

    # ── Varslene ─────────────────────────────────────────────────────────
    def test_langt_skift_merkes(self):
        self._skift(self.p_hgsd, 0, 14)
        rad, = self._rader()
        self.assertTrue(rad['langt_skift'])

    def test_skift_paa_grensa_merkes_ikke(self):
        """12 timer med grense 12 er innenfor. «Over» betyr over."""
        self._skift(self.p_hgsd, 0, 12)
        rad, = self._rader()
        self.assertFalse(rad['langt_skift'])

    def test_kort_hvile_merkes(self):
        self._skift(self.p_hgsd, 0, 8)
        self._skift(self.p_hgsd, 12, 4)     # 4 timers hvile
        rad, = self._rader()
        self.assertTrue(rad['kort_hvile'])

    def test_hvile_paa_grensa_merkes_ikke(self):
        self._skift(self.p_hgsd, 0, 8)
        self._skift(self.p_hgsd, 16, 4)     # 8 timers hvile
        rad, = self._rader()
        self.assertFalse(rad['kort_hvile'])

    def test_grensene_styrer_varslene(self):
        """Organisasjonens regler, ikke portalens. Flyttes grensa, flytter
        varselet seg med den."""
        self._skift(self.p_hgsd, 0, 10)
        self.assertFalse(self._rader()[0]['langt_skift'])

        grenser = Belastningsgrenser.hent()
        grenser.maks_skift_timer = 8
        grenser.save()
        self.assertTrue(self._rader()[0]['langt_skift'])

    def test_ingenting_sperres(self):
        """Varsler, ikke sperrer. Skiftet opprettes uansett hvor galt det er."""
        vp = self._skift(self.p_hgsd, 0, 40)
        vp.refresh_from_db()
        self.assertTrue(self._rader()[0]['langt_skift'])
        self.assertEqual(40.0, self._rader()[0]['timer'])

    # ── Faktisk mot planlagt ─────────────────────────────────────────────
    def test_faktiske_timer_regnes_av_stemplene(self):
        vp = self._skift(self.p_hgsd, 0, 8)
        vp.mott_at = vp.fra_tid + timedelta(minutes=30)
        vp.av_vakt_at = vp.til_tid + timedelta(hours=2)
        vp.save()
        rad, = self._rader()
        self.assertEqual(8.0, rad['timer'], 'planen står urørt')
        self.assertEqual(9.5, rad['faktiske_timer'])

    def test_paagaaende_skift_gir_ingen_faktisk_tid(self):
        """Et anslag som endrer seg mens man ser på det er ikke et tall."""
        vp = self._skift(self.p_hgsd, 0, 8)
        vp.mott_at = vp.fra_tid
        vp.save()
        self.assertIsNone(self._rader()[0]['faktiske_timer'])

    # ── Sammendraget ─────────────────────────────────────────────────────
    def test_sammendraget_teller_det_man_handler_paa(self):
        self._skift(self.p_hgsd, 0, 14)
        self._skift(self.p_karmoy, 0, 4, ressurs=self.res_karmoy)
        Vaktpost.objects.create(
            ressurs=self.res_fri, mannskap=None,
            fra_tid=self.start, til_tid=self.start + timedelta(hours=8))

        rader = self._rader()
        sam = services.belastning_sammendrag(self.vl, rader)
        self.assertEqual(2, sam['personer'])
        self.assertEqual(2, sam['skift'])
        self.assertEqual(18.0, sam['timer'])
        self.assertEqual(1, sam['ledige_plasser'])
        self.assertEqual(1, sam['lange_skift'])

    def test_en_annen_vaktliste_teller_ikke_med(self):
        """Belastningen er denne vaktas. Personen kan stå på flere."""
        annen = services.opprett_planlagt_vakt('Neste vakt')
        from .test_helpers import gruppe, lag_ressurs, LAG
        res = lag_ressurs(vaktliste=annen, navn='Lag', gruppe=gruppe(LAG))
        self._skift(self.p_hgsd, 0, 8)
        self._skift(self.p_hgsd, 100, 8, ressurs=res)
        rad, = self._rader()
        self.assertEqual(8.0, rad['timer'])
        self.assertEqual(1, rad['antall_skift'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class OverlappIRadenTests(TilgangsBasis):
    """Overlappet gjennom `belastning_per_person` og sammendraget.

    Skilt fra `OverlappstimerTests` med vilje: den måler regelen, denne
    måler at raden og sammendraget faktisk bærer den videre. Blir feltet
    fjernet fra dicten, går regelen fortsatt grønn.
    """

    def setUp(self):
        super().setUp()
        self.start = timezone.now().replace(minute=0, second=0, microsecond=0)

    def _skift(self, person, fra_time, timer, ressurs=None, **felt):
        return Vaktpost.objects.create(
            ressurs=ressurs or self.res_hgsd, mannskap=person,
            fra_tid=self.start + timedelta(hours=fra_time),
            til_tid=self.start + timedelta(hours=fra_time + timer),
            **felt)

    def test_uten_overlapp_er_feltet_null_og_flagget_av(self):
        self._skift(self.p_hgsd, 0, 8)
        self._skift(self.p_hgsd, 12, 4)
        rad, = services.belastning_per_person(self.vl)
        self.assertEqual(0.0, rad['overlapp'])
        self.assertFalse(rad['har_overlapp'])

    def test_dobbeltbooking_paa_tvers_av_ressurser_telles(self):
        """Det målte tilfellet fra TODO: 14 timer skift, 10 på stedet."""
        self._skift(self.p_hgsd, 12, 8, ressurs=self.res_hgsd)
        self._skift(self.p_hgsd, 16, 6, ressurs=self.res_fri)
        rad, = services.belastning_per_person(self.vl)
        self.assertEqual(14.0, rad['timer'])
        self.assertEqual(4.0, rad['overlapp'])
        self.assertTrue(rad['har_overlapp'])

    def test_overlapp_og_kort_hvile_er_to_ulike_beskjeder(self):
        """Begge står. `korteste_hvile` blir 0 av et overlapp og kan ikke
        skille det fra to skift som henger sammen — det er derfor
        `overlapp` finnes ved siden av, og ikke i stedet for."""
        self._skift(self.p_hgsd, 0, 8, ressurs=self.res_hgsd)
        self._skift(self.p_hgsd, 4, 8, ressurs=self.res_fri)
        rad, = services.belastning_per_person(self.vl)
        self.assertEqual(0.0, rad['korteste_hvile'])
        self.assertTrue(rad['kort_hvile'])
        self.assertEqual(4.0, rad['overlapp'])

    def test_skift_som_henger_sammen_gir_kort_hvile_uten_overlapp(self):
        """Motprøven til den over: null hvile, men ingenting dobbeltbooket.
        Uten denne kunne `overlapp` vært et alias for `kort_hvile`."""
        self._skift(self.p_hgsd, 0, 8)
        self._skift(self.p_hgsd, 8, 4)
        rad, = services.belastning_per_person(self.vl)
        self.assertEqual(0.0, rad['korteste_hvile'])
        self.assertTrue(rad['kort_hvile'])
        self.assertEqual(0.0, rad['overlapp'])
        self.assertFalse(rad['har_overlapp'])

    def test_probono_teller_i_overlappet_selv_om_det_ikke_teller_i_timene(self):
        """Summen er det organisasjonen betaler for; et overlapp er at én
        person står to steder. Kroppen skiller ikke på lønn."""
        self._skift(self.p_hgsd, 12, 8, ressurs=self.res_hgsd)
        self._skift(self.p_hgsd, 16, 6, ressurs=self.res_fri, probono=True)
        rad, = services.belastning_per_person(self.vl)
        self.assertEqual(8.0, rad['timer'], 'probono-timene teller ikke')
        self.assertEqual(4.0, rad['overlapp'], 'men overlappet gjør det')

    def test_sammendraget_summerer_timer_og_teller_hoder(self):
        self._skift(self.p_hgsd, 12, 8, ressurs=self.res_hgsd)
        self._skift(self.p_hgsd, 16, 6, ressurs=self.res_fri)
        self._skift(self.p_karmoy, 0, 8, ressurs=self.res_fri)
        self._skift(self.p_karmoy, 4, 4, ressurs=self.res_hgsd)
        rader = services.belastning_per_person(self.vl)
        sammendrag = services.belastning_sammendrag(self.vl, rader)
        self.assertEqual(8.0, sammendrag['overlapp'], '4 timer på hver')
        self.assertEqual(2, sammendrag['overlappende_personer'])

    def test_sammendraget_er_null_naar_ingen_er_dobbeltbooket(self):
        self._skift(self.p_hgsd, 0, 8)
        rader = services.belastning_per_person(self.vl)
        sammendrag = services.belastning_sammendrag(self.vl, rader)
        self.assertEqual(0.0, sammendrag['overlapp'])
        self.assertEqual(0, sammendrag['overlappende_personer'])


class BelastningApiTests(TilgangsBasis):

    def setUp(self):
        super().setUp()
        na = timezone.now()
        Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=na, til_tid=na + timedelta(hours=14))

    def _hent(self, klient):
        return klient.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/belastning/')

    def test_alle_med_les_ser_tallene(self):
        """Tallene *er* lista, regnet sammen. En korps-fører som planlegger
        sine egne folk trenger nettopp dette.

        **Leseren uten badge ser tallene for en tom liste** (11. sep. 2026):
        endepunktet svarer 200, men korpsfilteret gir henne ingen skift å
        regne på. Selve filteret testes i `KorpsfilterTests`; her står bare
        at porten er åpen for alle med `les`."""
        for navn, c, personer in (('les uten badge', self.c_leser, 0),
                                  ('korpsfører', self.c_kb, 1),
                                  ('skriv_full', self.c_vl, 1),
                                  ('admin', self.c_adm, 1)):
            with self.subTest(konto=navn):
                res = self._hent(c)
                self.assertEqual(200, res.status_code)
                self.assertEqual(personer,
                                 res.json()['data']['sammendrag']['personer'])

    def test_uten_rad_er_det_stengt(self):
        self.assertEqual(403, self._hent(_klient(_bruker('utenfor'))).status_code)

    def test_svaret_baerer_grensene(self):
        """Uten dem kan ikke lista forklare hvorfor en rad er merket."""
        d = self._hent(self.c_vl).json()['data']
        self.assertEqual(12, d['grenser']['maks_skift_timer'])
        self.assertEqual(8, d['grenser']['min_hvile_timer'])

    def test_ukjent_vaktliste(self):
        res = self.c_vl.get('/vaktliste/api/vaktlister/99999/belastning/')
        self.assertEqual(404, res.status_code)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class DagbolkerTests(SimpleTestCase):
    """`_dagbolker` uten en database.

    **Funnet ved mutasjonstesting 15. sep. 2026** — nøyaktig samme felle som
    `HviletidTests` dokumenterer: `sorted()` lot seg fjerne uten at noe ble
    rødt, fordi `Vaktpost.Meta.ordering` alt sorterer på `fra_tid`. Testene
    gjennom basen målte modellens ordering, ikke hjelperens. Derfor er dette
    en egen funksjon, og derfor prøves den med lister kalleren ikke har
    sortert.
    """

    class FalsktSkift:
        def __init__(self, fra, timer=8):
            self.fra_tid = fra
            self.til_tid = fra + timedelta(hours=timer)

    def _kl(self, dag, time, minutt=0, timer=8):
        """Et skift på en fast **norsk** klokkeslett, båret som **UTC**.

        Konverteringen er ikke pynt. Django lagrer og leverer aware
        datetimes i UTC, så det hjelperen faktisk får inn er 22:30 den 1.
        oktober — ikke 00:30 den 2. Bar de falske skiftene norsk tid, ville
        `.date()` alt gitt riktig dag, og mutanten som dropper
        `timezone.localtime()` overlevde. Den gjorde det, til dette ble
        rettet.
        """
        naiv = datetime(2026, 10, dag, time, minutt,
                        tzinfo=ZoneInfo('Europe/Oslo'))
        return self.FalsktSkift(naiv.astimezone(dt_timezone.utc), timer)

    def test_usortert_inndata_gir_kronologiske_dager(self):
        """M-funn: regelen, ikke modellens ordering."""
        bolker = services._dagbolker(
            [self._kl(4, 8), self._kl(2, 8), self._kl(3, 8)])
        self.assertEqual(['2026-10-02', '2026-10-03', '2026-10-04'],
                         [b['nokkel'] for b in bolker])

    def test_timene_summeres_per_dag(self):
        bolker = services._dagbolker(
            [self._kl(2, 8, timer=8), self._kl(2, 20, timer=4),
             self._kl(3, 8, timer=6)])
        self.assertEqual([12.0, 6.0], [b['timer'] for b in bolker])

    def test_nattskift_hoerer_til_startdagen(self):
        """«fre. 20:00 – lør. 04:00» står under fredag. Beslutning 7."""
        bolker = services._dagbolker([self._kl(2, 20, timer=8)])
        self.assertEqual(1, len(bolker))
        self.assertEqual('2026-10-02', bolker[0]['nokkel'])
        self.assertEqual(8.0, bolker[0]['timer'])

    def test_dagen_regnes_i_norsk_tid_ikke_i_utc(self):
        """**Et skift som begynner 00:30 norsk tid.** I sommertid er det
        22:30 UTC dagen før, så `date()` rett på tidspunktet ville lagt det
        på 1. oktober i stedet for 2.

        Feilen er usynlig for alle skift som begynner på dagtid — altså de
        fleste — og viser seg bare på nattevakter. Mutanten som byttet
        `timezone.localtime(...)` mot tidspunktet selv overlevde til denne
        testen fantes."""
        bolker = services._dagbolker([self._kl(2, 0, 30, timer=6)])
        self.assertEqual('2026-10-02', bolker[0]['nokkel'])

    def test_skift_uten_starttid_hoppes_over(self):
        tomt = self._kl(2, 8)
        tomt.fra_tid = None
        self.assertEqual([], services._dagbolker([tomt]))

    def test_tom_liste_gir_ingen_dager(self):
        self.assertEqual([], services._dagbolker([]))


class BudsjettallTests(TilgangsBasis):
    """`planleggingstall()` — vaktas budsjett, ikke den enkeltes belastning.

    `docs/FORSLAG_PLANLEGGERFANE.md` §6. Tre tall side om side fordi hvert av
    dem alene lyver litt, og en dagslinje uten egne tak.
    """

    def setUp(self):
        super().setUp()
        self.start = timezone.now().replace(
            hour=8, minute=0, second=0, microsecond=0)

    def _skift(self, fra_time, timer, *, mannskap=None, ressurs=None, **felt):
        return Vaktpost.objects.create(
            ressurs=ressurs or self.res_hgsd, mannskap=mannskap,
            fra_tid=self.start + timedelta(hours=fra_time),
            til_tid=self.start + timedelta(hours=fra_time + timer),
            **felt)

    def _tall(self):
        return services.planleggingstall(self.vl)

    def test_uten_tak_er_igjen_ingenting_og_ikke_null(self):
        """«0 timer igjen» er en beskjed om at budsjettet er brukt opp;
        «ingen tak satt» er fraværet av et budsjett. De to skal ikke se
        like ut."""
        self._skift(0, 8)
        tall = self._tall()
        self.assertIsNone(tall['timetak'])
        self.assertIsNone(tall['igjen'])
        self.assertFalse(tall['over_taket'])

    def test_ledige_plasser_teller_i_satt_opp_men_ikke_i_bemannet(self):
        """Avstanden mellom dem er arbeidslista: her mangler åtte timer
        folk."""
        self._skift(0, 8, mannskap=self.p_hgsd)
        self._skift(12, 8)                      # ledig plass
        tall = self._tall()
        self.assertEqual(16.0, tall['satt_opp'])
        self.assertEqual(8.0, tall['bemannet'])

    def test_probono_staar_for_seg_og_teller_i_ingen_av_de_to(self):
        """Taket er det organisasjonen betaler for. Samme regel som
        `_sumTimer()` og `belastning_per_person` alt sto på — men tallet
        vises, så summen ikke utelater noe i stillhet."""
        self._skift(0, 8, mannskap=self.p_hgsd)
        self._skift(12, 6, mannskap=self.p_hgsd, probono=True)
        tall = self._tall()
        self.assertEqual(8.0, tall['satt_opp'])
        self.assertEqual(8.0, tall['bemannet'])
        self.assertEqual(6.0, tall['probono'])

    def test_igjen_maales_mot_satt_opp_ikke_mot_bemannet(self):
        """Planlegging handler om behovet. Et budsjett som først fylles når
        navnene er på plass sier «du har alt igjen» på en liste som er
        ferdig satt opp."""
        self.vl.timetak = 100
        self.vl.save(update_fields=['timetak'])
        self._skift(0, 8, mannskap=self.p_hgsd)
        self._skift(12, 8)                      # ledig
        self.assertEqual(84.0, self._tall()['igjen'])

    def test_over_taket_flagges_men_ingenting_avvises(self):
        """«Varsler, de sperrer ikke.» Skiftet står der etterpå."""
        self.vl.timetak = 10
        self.vl.save(update_fields=['timetak'])
        vp = self._skift(0, 12, mannskap=self.p_hgsd)
        tall = self._tall()
        self.assertTrue(tall['over_taket'])
        self.assertEqual(-2.0, tall['igjen'])
        self.assertTrue(Vaktpost.objects.filter(pk=vp.pk).exists())

    def test_paa_taket_er_ikke_over_det(self):
        self.vl.timetak = 8
        self.vl.save(update_fields=['timetak'])
        self._skift(0, 8, mannskap=self.p_hgsd)
        tall = self._tall()
        self.assertFalse(tall['over_taket'])
        self.assertEqual(0.0, tall['igjen'])

    def test_dagslinja_foerer_skiftet_paa_startdagen(self):
        """Beslutning 7: fre. 20:00 → lør. 04:00 står under fredag, ikke
        splittet. Rapportmodulen splitter ved midnatt, og forskjellen er
        bevisst — splitting endrer ikke en totalsum, bare nedbrytingen."""
        natt = self.start.replace(hour=20)
        Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=natt, til_tid=natt + timedelta(hours=8))
        dager = self._tall()['dager']
        self.assertEqual(1, len(dager), 'ett skift, én dag — ikke to')
        self.assertEqual(8.0, dager[0]['timer'], 'hele skiftet på startdagen')
        self.assertEqual(timezone.localtime(natt).date().isoformat(),
                         dager[0]['nokkel'])

    def test_dagene_kommer_i_kronologisk_rekkefoelge(self):
        """Sist opprettet først i basen; lista skal likevel begynne på dag
        én. Skiftene settes inn baklengs, så rekkefølgen ikke kan komme av
        innsettingen."""
        self._skift(48, 4, mannskap=self.p_hgsd)
        self._skift(24, 6, mannskap=self.p_hgsd)
        self._skift(0, 8, mannskap=self.p_hgsd)
        nokler = [d['nokkel'] for d in self._tall()['dager']]
        self.assertEqual(sorted(nokler), nokler)
        self.assertEqual([8.0, 6.0, 4.0],
                         [d['timer'] for d in self._tall()['dager']])

    def test_dagene_har_ingen_egne_tak(self):
        """Beslutning 2: ett tak for hele vakta. Et tak per dag ville
        sperret det man faktisk gjør — flytte timer mellom dagene mens
        totalen står."""
        self.vl.timetak = 100
        self.vl.save(update_fields=['timetak'])
        self._skift(0, 8, mannskap=self.p_hgsd)
        for dag in self._tall()['dager']:
            self.assertNotIn('timetak', dag)
            self.assertNotIn('igjen', dag)

    def test_probono_teller_ikke_i_dagslinja_heller(self):
        """Dagslinja bryter ned `satt_opp`, så den må hoppe over det samme.
        Ellers summerer dagene til noe annet enn tallet rett over dem."""
        self._skift(0, 8, mannskap=self.p_hgsd)
        self._skift(2, 6, mannskap=self.p_hgsd, probono=True)
        tall = self._tall()
        self.assertEqual(tall['satt_opp'],
                         sum(d['timer'] for d in tall['dager']))

    def test_tallene_er_hele_vaktas_og_filtreres_aldri_paa_korps(self):
        """Taket gjelder lista, så tallene må gjøre det også — et «satt opp»
        som bare teller ett korps kan ikke sammenlignes med et tak for alle.
        Viewet gater i stedet på `ser_alle_korps`."""
        self._skift(0, 8, mannskap=self.p_hgsd, ressurs=self.res_hgsd)
        self._skift(0, 5, mannskap=self.p_karmoy, ressurs=self.res_karmoy)
        self.assertEqual(13.0, self._tall()['satt_opp'])


class BudsjettApiTests(TilgangsBasis):
    """Budsjettallene i belastningssvaret, og taket gjennom PUT-en."""

    def setUp(self):
        super().setUp()
        na = timezone.now()
        Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=na, til_tid=na + timedelta(hours=10))

    def _hent(self, klient):
        return klient.get(
            f'/vaktliste/api/vaktlister/{self.vl.pk}/belastning/')

    def _sett_tak(self, klient, verdi):
        import json
        return klient.put(
            f'/vaktliste/api/vaktlister/{self.vl.pk}/',
            data=json.dumps({'timetak': verdi}),
            content_type='application/json')

    def test_den_som_ser_alle_korps_faar_budsjettallene(self):
        for navn, c in (('skriv_full', self.c_vl), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                data = self._hent(c).json()['data']
                self.assertIsNotNone(data['planlegging'])
                self.assertEqual(10.0, data['planlegging']['satt_opp'])

    def test_les_med_badge_faar_dem_ikke(self):
        """Tallene er hele vaktas. For en `les` med badge ville de vært et
        aggregat over skift hun ikke får se — avledet innsyn, samme regel
        som statistikkmodulen bruker."""
        self.assertIsNone(self._hent(self.c_leser).json()['data']['planlegging'])

    def test_korpsfoereren_ser_alle_korps_og_faar_dem(self):
        """`skriv_handling` og oppover ser alle korps (12. sep. 2026), så
        summen er ikke ny opplysning for henne."""
        self.assertIsNotNone(self._hent(self.c_kb).json()['data']['planlegging'])

    def test_skriv_leder_setter_taket(self):
        res = self._sett_tak(self.c_leder, 400)
        self.assertEqual(200, res.status_code)
        self.vl.refresh_from_db()
        self.assertEqual(400, self.vl.timetak)
        self.assertEqual(400, res.json()['data']['timetak'])

    def test_alt_under_skriv_leder_faar_ikke_sette_taket(self):
        """Taket er tallet *alle* varsler på lista måles mot — samme
        rekkevidde som vaktas spenn, og derfor samme gate: `skriv_leder`.

        **`skriv_full` står også utenfor**, og det er verdt å teste
        eksplisitt: planleggernotatets §4 skisserte `skriv_full`, og retten
        ble snevret 15. sep. 2026 fordi taket settes i samme PUT som spennet.
        Én forespørsel med to ulike tilgangsnivåer inni er en regel ingen
        klarer å lese riktig."""
        for navn, c in (('korpsfører', self.c_kb), ('skriv_full', self.c_vl)):
            with self.subTest(konto=navn):
                self.assertEqual(403, self._sett_tak(c, 400).status_code)
                self.vl.refresh_from_db()
                self.assertIsNone(self.vl.timetak)

    def test_tomt_felt_fjerner_taket(self):
        """Et tallfelt som tømmes sender `''` eller `null`, og begge skal
        bety «ingen tak» — ikke null timer, som ville vært et budsjett brukt
        opp før noen er satt opp."""
        for tomt in (None, ''):
            with self.subTest(verdi=repr(tomt)):
                self.vl.timetak = 400
                self.vl.save(update_fields=['timetak'])
                self.assertEqual(200, self._sett_tak(self.c_leder, tomt).status_code)
                self.vl.refresh_from_db()
                self.assertIsNone(self.vl.timetak)

    def test_soepel_avvises_med_melding_og_ikke_500(self):
        for verdi in ('fire hundre', '12,5', [1]):
            with self.subTest(verdi=repr(verdi)):
                res = self._sett_tak(self.c_leder, verdi)
                self.assertEqual(400, res.status_code)
                self.assertIn('timer', res.json()['message'])

    def test_negativt_tak_avvises(self):
        res = self._sett_tak(self.c_leder, -10)
        self.assertEqual(400, res.status_code)

    def test_taket_roerer_ikke_spennet(self):
        """PUT-en tar begge, og en innsending med bare det ene skal la det
        andre stå. `update_fields` gjorde tidligere alltid `planlagt_slutt`."""
        slutt = timezone.now() + timedelta(hours=20)
        self.vl.planlagt_slutt = slutt
        self.vl.save(update_fields=['planlagt_slutt'])
        self._sett_tak(self.c_leder, 400)
        self.vl.refresh_from_db()
        self.assertEqual(slutt, self.vl.planlagt_slutt)
        self.assertEqual(400, self.vl.timetak)


class TaketKopieresTests(TilgangsBasis):
    """Beslutning 6: taket følger med til neste vakt, personene gjør ikke."""

    def _ny_liste(self):
        # Gjennom tjenesten, ikke for hånd: `opprett_planlagt_vakt` er den
        # ene veien inn, og en test som bygger raden selv ville sluttet å
        # måle det den vil måle den dagen opprettelsen får en regel til.
        return services.opprett_planlagt_vakt('Oktobervakta')

    def test_taket_foelger_med(self):
        self.vl.timetak = 400
        self.vl.save(update_fields=['timetak'])
        ny = self._ny_liste()
        services.kopier_oppsett(self.vl, ny)
        ny.refresh_from_db()
        self.assertEqual(400, ny.timetak)

    def test_uten_tak_settes_ingenting(self):
        ny = self._ny_liste()
        services.kopier_oppsett(self.vl, ny)
        ny.refresh_from_db()
        self.assertIsNone(ny.timetak)

    def test_personene_foelger_fortsatt_ikke_med(self):
        """Motprøven. En liste ingen har sagt ja til ser ferdig ut — og et
        tak som kopieres må ikke dra med seg navn."""
        na = timezone.now()
        Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=na, til_tid=na + timedelta(hours=8))
        self.vl.timetak = 400
        self.vl.save(update_fields=['timetak'])
        ny = self._ny_liste()
        services.kopier_oppsett(self.vl, ny)
        self.assertEqual(
            0, Vaktpost.objects.filter(ressurs__vaktliste=ny).count())


class GrenseApiTests(TilgangsBasis):

    def _sett(self, klient, **kropp):
        return klient.put('/vaktliste/api/grenser/', data=kropp,
                          content_type='application/json')

    def test_lederen_flytter_grensa(self):
        res = self._sett(self.c_leder, maks_skift_timer=10)
        self.assertEqual(200, res.status_code, res.content)
        self.assertEqual(10, Belastningsgrenser.hent().maks_skift_timer)

    def test_bemanneren_flytter_den_ikke(self):
        """Å flytte grensa endrer hva *alle* vaktlister varsler om — det er
        en beslutning om hvordan organisasjonen bemanner."""
        self.assertEqual(403, self._sett(self.c_vl, maks_skift_timer=10).status_code)
        self.assertEqual(12, Belastningsgrenser.hent().maks_skift_timer)

    def test_korpsforeren_flytter_den_ikke(self):
        self.assertEqual(403, self._sett(self.c_kb, maks_skift_timer=10).status_code)

    def test_urimelige_verdier_avvises(self):
        for verdi in (0, -3, 200, 'tolv', None):
            with self.subTest(verdi=verdi):
                res = self._sett(self.c_adm, maks_skift_timer=verdi)
                self.assertEqual(400, res.status_code)
        self.assertEqual(12, Belastningsgrenser.hent().maks_skift_timer)

    def test_bare_feltet_som_sendes_endres(self):
        self._sett(self.c_adm, min_hvile_timer=6)
        grenser = Belastningsgrenser.hent()
        self.assertEqual(6, grenser.min_hvile_timer)
        self.assertEqual(12, grenser.maks_skift_timer, 'det andre sto urørt')

    def test_raden_lages_ved_forste_oppslag(self):
        """Singleton uten seeding: ingen migrasjon skal måtte huske den."""
        Belastningsgrenser.objects.all().delete()
        self.assertEqual(12, Belastningsgrenser.hent().maks_skift_timer)


class ProbonoTests(TilgangsBasis):
    """Probono telles ikke i timene, men i alt annet (11. sep. 2026).

    Summen er det organisasjonen betaler for; lengste skift og korteste
    hvile er hva kroppen tåler, og den skiller ikke på lønn.
    """

    def setUp(self):
        super().setUp()
        na = timezone.now()
        self.betalt = Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=na, til_tid=na + timedelta(hours=8))
        self.probono = Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd, probono=True,
            fra_tid=na + timedelta(hours=10), til_tid=na + timedelta(hours=24))

    def _rad(self):
        return services.belastning_per_person(self.vl)[0]

    def test_timene_hopper_over_probono(self):
        self.assertEqual(8.0, self._rad()['timer'])

    def test_lengste_skift_teller_probono(self):
        """14 timer sliter like mye uansett hvem som betaler."""
        self.assertEqual(14.0, self._rad()['lengste_skift'])

    def test_hvilen_teller_probono(self):
        self.assertEqual(2.0, self._rad()['korteste_hvile'])

    def test_antall_skift_teller_begge_og_probono_for_seg(self):
        rad = self._rad()
        self.assertEqual(2, rad['antall_skift'])
        self.assertEqual(1, rad['probono_skift'])

    def test_faktiske_timer_hopper_over_probono(self):
        na = timezone.now()
        for vp in (self.betalt, self.probono):
            vp.mott_at = vp.fra_tid
            vp.av_vakt_at = vp.til_tid
            vp.save()
        self.assertEqual(8.0, self._rad()['faktiske_timer'])

    def test_sammendraget_summerer_uten_probono(self):
        rader = services.belastning_per_person(self.vl)
        self.assertEqual(8.0, services.belastning_sammendrag(self.vl, rader)['timer'])

    def test_flagget_settes_ved_opprettelse_og_endring(self):
        c = self.c_vl
        res = c.post(f'/vaktliste/api/ressurser/{self.res_karmoy.pk}/vaktposter/',
                     data={'mannskap_id': self.p_karmoy.pk, 'probono': True,
                           'fra_tid': self._iso(0), 'til_tid': self._iso(4)},
                     content_type='application/json')
        self.assertEqual(res.status_code, 201, res.content)
        vp_id = res.json()['data']['id']
        self.assertTrue(res.json()['data']['probono'])
        res = c.put(f'/vaktliste/api/vaktposter/{vp_id}/', data={'probono': False},
                    content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(Vaktpost.objects.get(pk=vp_id).probono)

    def test_korpsforeren_setter_det_ikke(self):
        """**Snudd 15. sep. 2026.** Probono sto «samme port som merknaden», og
        merknaden er nå oppsett — men begrunnelsen står på egne ben her:
        probono er et utsagn om hva vakta *koster*, og det tallet leses av
        budsjettlinja for hele lista. Den som fører sitt eget korps skal ikke
        kunne flytte totalen for alle.
        """
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{self.betalt.pk}/',
                            data={'probono': True}, content_type='application/json')
        self.assertEqual(res.status_code, 403, res.content)
        self.assertFalse(Vaktpost.objects.get(pk=self.betalt.pk).probono)

    def test_leseren_setter_ingenting(self):
        res = self.c_leser.put(f'/vaktliste/api/vaktposter/{self.betalt.pk}/',
                               data={'probono': True}, content_type='application/json')
        self.assertEqual(res.status_code, 403)


class FanenHeterTimeoversiktTests(SimpleTestCase):
    """**Fanen het «Planlegging», og det navnet var opptatt** (André,
    16. sep. 2026, pulje 3).

    `Vaktliste.status` har verdien «Planlegging» ved siden av «I drift», og
    den står som et merke øverst på siden. Fanen og merket sa altså samme ord
    om to helt ulike ting: den ene er *hva lista koster i timer*, den andre er
    *om innsjekk er åpen*. «Timeoversikt» sier hva fanen viser.

    **Testen finnes fordi ingen test sa noe om navnet.** Omdøpingen var grønn
    før den ble skrevet — jeg kunne kalt fanen hva som helst, og det er
    nøyaktig den slags stillhet som lot «Planlegging» bety to ting i første
    omgang.

    Og den prøver **regelen**, ikke bare strengen: fanenavnet må ikke kollidere
    med en statusverdi. Et framtidig navnebytte som gjeninnfører kollisjonen
    blir rødt, uansett hvilket ord det er.
    """

    def setUp(self):
        from patients.js_test_utils import (VAKTLISTE_JS, PORTAL_UTILS_JS,
                                            build_harness, node_available)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (VAKTLISTE_JS, ('tegnFaner', 'kanPlanlegge', '_fanerad',
                            '_mannskapsfane', 'iDrift', '_tilstede',
                            '_ikkePlassert', '_grupperMedRessurser',
                            '_ressurserIGruppe', '_posterFor', 'kanLede', '_erAdmin', '_nivaa', '_mittKorpsId')),
        ))

    def _faner(self):
        import json as _json

        from patients.js_test_utils import run_node
        ut = run_node(self.harness, """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_leder' } };
            globalThis.aktivFane = 'oversikt';
            globalThis.OVERSIKT = 'oversikt'; globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede'; globalThis.BELASTNING = 'belastning';
            globalThis.PLANLEGGER = 'planlegger';
            globalThis.IKKE_PLASSERT = 'ikke-plassert';
            globalThis.MITT_KORPS = 'mitt-korps';
            globalThis.belastning = null; globalThis.register = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {
              vaktliste: { id: 1, vakt_navn: 'Vakta',
                           status_navn: 'Planlegging', i_drift: false },
              grupper: [], ressurser: [], vaktposter: [], mannskap: [] };
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            tegnFaner();
            console.log(JSON.stringify(el.innerHTML));
        """)
        # `run_node` legger på en «OK»-linje til slutt, så JSON-en er den første.
        return _json.loads(ut.strip().splitlines()[0])

    def test_fanen_heter_timeoversikt(self):
        markup = self._faner()
        self.assertIn('Timeoversikt', markup)

    def test_fanenavnene_kolliderer_ikke_med_en_statusverdi(self):
        """Regelen, ikke ordet. `Vaktliste.status` sine etiketter er opptatt:
        brukes en av dem som fanenavn, sier to ting på skjermen samme ord om
        ulike begreper — og det var hele feilen som ble rettet."""
        from . import choices
        markup = self._faner()
        statusnavn = set(choices.STATUS_NAVN.values())
        self.assertTrue(statusnavn, 'statusverdiene må finnes, ellers måler testen ingenting')
        for navn in statusnavn:
            with self.subTest(status=navn):
                self.assertNotIn(f'>{navn}<', markup,
                                 f'«{navn}» er en statusverdi og kan ikke være et fanenavn')


class FanerekkaHarToBolkerTests(SimpleTestCase):
    """**De faste visningene og ressursgruppene er to ulike slags ting**
    (André, 16. sep. 2026, pulje 3 punkt 5): «Oversikt og Ambulanse ser like
    ut, og de er to ulike slags ting.»

    Og de sto **flettet i hverandre**. Rekka ble bygget med `push` og så
    `splice(2, …)` for «Mitt korps» — men indeks 2 var regnet mot en liste som
    ennå ikke hadde fått «Mannskap» fra `splice(1, …)`, så «Mitt korps» landet
    *inne* i gruppeblokka så snart det fantes to grupper:
    `Ambulanse · Mitt korps · Lag`.

    Ingen test så det, fordi ingen test leste **rekkefølgen** — bare at hver
    fane fantes. To slags faner kan ikke gis hvert sitt utseende så lenge de
    står om hverandre, så dette måtte rettes før utseendet ga mening.
    """

    FUNKSJONER = ('tegnFaner', 'kanPlanlegge', '_fanerad', '_mannskapsfane',
                  'iDrift', '_tilstede', '_ikkePlassert', '_grupperMedRessurser',
                  '_ressurserIGruppe', '_posterFor', 'kanLede', '_erAdmin',
                  '_nivaa', '_mittKorpsId', '_synligePoster')

    def setUp(self):
        from patients.js_test_utils import (
            OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, VAKTLISTE_JS,  # noqa: F401
            build_harness, node_available, run_node)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (VAKTLISTE_JS, self.FUNKSJONER),
        ))

    def _markup(self, korps='1'):
        from patients.js_test_utils import run_node
        return run_node(self.harness, f"""
            globalThis.window = {{ MODUL_TILGANG: {{ vaktliste: 'skriv_leder' }},
                                  MITT_KORPS_ID: {korps} }};
            globalThis.aktivFane = 'oversikt';
            globalThis.OVERSIKT='oversikt'; globalThis.MANNSKAP='mannskap';
            globalThis.TILSTEDE='tilstede'; globalThis.BELASTNING='belastning';
            globalThis.PLANLEGGER='planlegger'; globalThis.IKKE_PLASSERT='ikke-plassert';
            globalThis.MITT_KORPS='mitt-korps';
            globalThis.belastning=null; globalThis.register=null;
            globalThis.utskriftDag=null; globalThis.korpsfilter=null;
            globalThis.aktivListe = {{
              vaktliste: {{id:1, vakt_navn:'V', status_navn:'Planlegging', i_drift:false}},
              grupper: [{{id:1, navn:'Ambulanse', ikon:'truck'}},
                        {{id:2, navn:'Lag', ikon:'people'}}],
              ressurser: [{{id:1, navn:'A1', gruppe_id:1}}, {{id:2, navn:'L1', gruppe_id:2}}],
              vaktposter: [], alle_vaktposter: [], mannskap: [], korps: [] }};
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el, querySelectorAll: () => [] }};
            tegnFaner();
            console.log(JSON.stringify(el.innerHTML));
        """)

    def _rekke(self, markup):
        """Fanenavnene i rekkefølge, med `│` der et skille står."""
        import re as _re
        ut = []
        for m in _re.finditer(r'vl-faneskille|</i>([^<]+)', markup):
            ut.append('│' if m.group(0).startswith('vl-faneskille')
                      else m.group(1).strip())
        return ut

    def test_gruppefanene_staar_samlet_og_ingen_fast_fane_er_inni(self):
        """**Feilen, direkte.** «Mitt korps» sto mellom «Ambulanse» og «Lag»."""
        rekke = self._rekke(json.loads(self._markup().strip().splitlines()[0]))
        forste, siste = rekke.index('│'), len(rekke) - 1 - rekke[::-1].index('│')
        inni = rekke[forste + 1:siste]
        self.assertEqual(inni, ['Ambulanse', 'Lag', 'Ny ressurs'],
                         'bare gruppene og knappen som lager en til')
        self.assertNotIn('Mitt korps', inni)

    def test_hele_rekka_i_rekkefolge(self):
        """Rekkefølgen er hele poenget, så den pinnes i sin helhet. En ny fane
        lagt til feil sted blir rød her, ikke oppdaget på staging."""
        rekke = self._rekke(json.loads(self._markup().strip().splitlines()[0]))
        self.assertEqual(rekke, [
            'Oversikt', 'Mannskap',
            '│', 'Ambulanse', 'Lag', 'Ny ressurs', '│',
            'Mitt korps', 'Timeoversikt', 'Planlegger', 'Ikke plassert'])

    def test_bare_gruppefanene_baerer_gruppeklassen(self):
        """Utseendet André ba om. «Ny ressurs» hører til bolken og bærer den
        også — den lager en ressurs, og ressursene er det bolken handler om."""
        markup = json.loads(self._markup().strip().splitlines()[0])
        import re as _re
        med = [_re.search(r'</i>([^<]+)', k).group(1).strip()
               for k in _re.findall(r'<button class="vl-fane vl-fane-gruppe[^>]*>.*?</button>',
                                    markup, _re.S)]
        self.assertEqual(sorted(med), ['Ambulanse', 'Lag', 'Ny ressurs'])

    def test_uten_grupper_staar_ingen_skiller(self):
        """Et skille mot ingenting er en strek man lurer på."""
        from patients.js_test_utils import run_node
        ut = run_node(self.harness, """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'les' } };
            globalThis.aktivFane='oversikt'; globalThis.OVERSIKT='oversikt';
            globalThis.MANNSKAP='mannskap'; globalThis.TILSTEDE='tilstede';
            globalThis.BELASTNING='belastning'; globalThis.PLANLEGGER='planlegger';
            globalThis.IKKE_PLASSERT='ikke-plassert'; globalThis.MITT_KORPS='mitt-korps';
            globalThis.belastning=null; globalThis.register=null;
            globalThis.utskriftDag=null; globalThis.korpsfilter=null;
            globalThis.aktivListe = {
              vaktliste:{id:1, vakt_navn:'V', status_navn:'Planlegging', i_drift:false},
              grupper: [], ressurser: [], vaktposter: [], alle_vaktposter: [],
              mannskap: [], korps: [] };
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el, querySelectorAll: () => [] };
            tegnFaner();
            console.log(JSON.stringify(el.innerHTML));
        """)
        markup = json.loads(ut.strip().splitlines()[0])
        self.assertNotIn('vl-faneskille', markup)
        self.assertNotIn('vl-fane-gruppe', markup)
