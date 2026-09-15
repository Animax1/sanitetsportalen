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
from datetime import timedelta

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from . import services
from .models import Belastningsgrenser, Vaktpost
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

    def test_korpsforeren_kan_sette_det_paa_sitt_eget(self):
        """«Kan settes av alle som har tilgang» — samme port som merknaden."""
        res = self.c_kb.put(f'/vaktliste/api/vaktposter/{self.betalt.pk}/',
                            data={'probono': True}, content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(Vaktpost.objects.get(pk=self.betalt.pk).probono)

    def test_leseren_setter_ingenting(self):
        res = self.c_leser.put(f'/vaktliste/api/vaktposter/{self.betalt.pk}/',
                               data={'probono': True}, content_type='application/json')
        self.assertEqual(res.status_code, 403)
