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
        sine egne folk trenger nettopp dette."""
        for navn, c in (('les', self.c_leser), ('korpsfører', self.c_kb),
                        ('skriv_full', self.c_vl), ('admin', self.c_adm)):
            with self.subTest(konto=navn):
                res = self._hent(c)
                self.assertEqual(200, res.status_code)
                self.assertEqual(1, res.json()['data']['sammendrag']['personer'])

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
