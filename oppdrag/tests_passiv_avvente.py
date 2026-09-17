"""Aktiv/passiv vakt og «avvente» (16. sep. 2026).

André: «Spesialressurser i /oppdrag/ har en aktiv vakt og passiv vakt switch
som operatør kan sette» og «ved utalarmering til spesialressurser kan
operatøren trykke avvente hvis ressursen sier på nødnett at de ikke kan ta
oppdraget».

**Tre beslutninger som former alt her, og som er verdt å lese før man rører
noe:**

1. **Flaggene bor på `Enhetstype`**, ikke på enheten. «Lege 03» opprettet midt
   i arrangementet arver dem av seg selv; per enhet måtte noen husket det.
2. **Passiv er ikke «av vakt».** Enheten kan varsles — hun er bakvakt. Derfor
   et eget felt ved siden av `pa_vakt`, og derfor teller hun i beredskapen.
3. **«Avvente» er en hendelse, ikke en status.** Koblingsraden blir stående i
   `Venter`, så «Rykk ut» er fortsatt tilgjengelig og begge deler står i
   loggen. En ny status ville krevd en kolonne i `ArkivertOppdrag` og en
   beslutning om SHA-payloaden.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node)
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang

from . import choices, services
from .statistikk import passiv_timer_for
from .models import (Enhet, Enhetshendelse, Enhetstype, Lokasjon, Oppdrag,
                     Vaktmodusperiode)

AAR = 2026


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PassivBasis(TestCase):
    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        self.vakt = sett_aktiv_vakt(AAR)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        # `update_or_create`: migrasjon `0020` seeder standardtypene, og en
        # `create` med samme navn ville brutt unik-skranken. Testene slår dem
        # opp framfor å lage sine egne — slik at seeding som slutter å virke
        # blir synlig, samme grep som `vaktliste.test_helpers.gruppe()`.
        self.spesial, _ = Enhetstype.objects.update_or_create(
            navn='Spesialressurs',
            defaults={'kan_passiv_vakt': True, 'kan_avvente': True})
        self.ambulanse, _ = Enhetstype.objects.update_or_create(
            navn='Ambulanse',
            defaults={'kan_passiv_vakt': False, 'kan_avvente': False})
        self.lege = Enhet.objects.create(navn='Lege 02', enhetstype=self.spesial)
        self.bil = Enhet.objects.create(navn='Haugesund 56', enhetstype=self.ambulanse)
        self.utentype = Enhet.objects.create(navn='Uten type')

        self.operator = CustomUser.objects.create_user(
            username='op_pv', password='x', must_change_password=False)
        ModulTilgang.objects.create(
            bruker=self.operator, modul_slug='oppdrag', nivaa='skriv_full')
        self.klient = Client()
        self.klient.force_login(self.operator)

    def _oppdrag(self, enhet=None):
        return Oppdrag.objects.create(
            vakt=self.vakt, enhet=enhet or self.lege,
            problemstilling='Pustevansker', hastegrad='Akutt',
            lokasjon=self.lokasjon,
            oppdragsnummer=services.neste_oppdragsnummer(self.vakt))


class FlaggeneBorPaaTypenTests(PassivBasis):

    def test_enheten_arver_typens_flagg(self):
        self.assertTrue(services.kan_passiv_vakt(self.lege))
        self.assertTrue(services.kan_avvente(self.lege))

    def test_en_ambulanse_arver_ingen_av_dem(self):
        self.assertFalse(services.kan_passiv_vakt(self.bil))
        self.assertFalse(services.kan_avvente(self.bil))

    def test_en_enhet_uten_type_arver_ingenting(self):
        """Kontoopprettelsen lager en `Enhet` når kontotypen er «bil», og den
        fødes uten type. Det er riktig standard — men det betyr at en lege som
        får konto den veien må få typen satt."""
        self.assertFalse(services.kan_passiv_vakt(self.utentype))
        self.assertFalse(services.kan_avvente(self.utentype))

    def test_de_to_flaggene_er_uavhengige(self):
        """En frivillig enhet som alltid er aktiv kan godt ha lov til å si
        nei. Ett flagg ville tvunget fram passiv vakt for å få avventing."""
        type_, _ = Enhetstype.objects.update_or_create(
            navn='Frivillig',
            defaults={'kan_passiv_vakt': False, 'kan_avvente': True})
        enhet = Enhet.objects.create(navn='Frivillig 1', enhetstype=type_)
        self.assertFalse(services.kan_passiv_vakt(enhet))
        self.assertTrue(services.kan_avvente(enhet))


class VaktmodusTests(PassivBasis):

    def test_aa_sette_passiv_skriver_baade_tilstand_og_periode(self):
        """**Begge deler, og det er hele poenget.** Feltet svarer på hva som
        gjelder nå; perioden på hvor lenge. Skrives bare det første, finnes
        ikke timene — og de kan ikke fylles inn med tilbakevirkende kraft."""
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt,
                                bruker=self.operator)
        self.lege.refresh_from_db()
        self.assertTrue(self.lege.passiv_vakt)
        perioder = list(Vaktmodusperiode.objects.filter(enhet=self.lege))
        self.assertEqual(len(perioder), 1)
        self.assertEqual(perioder[0].modus, Vaktmodusperiode.PASSIV)
        self.assertIsNone(perioder[0].til, 'perioden løper')

    def test_aa_gaa_tilbake_lukker_den_forrige(self):
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        services.sett_vaktmodus(self.lege, passiv=False, vakt=self.vakt)
        perioder = list(Vaktmodusperiode.objects.filter(enhet=self.lege).order_by('fra'))
        self.assertEqual(len(perioder), 2)
        self.assertIsNotNone(perioder[0].til, 'den passive skal være lukket')
        self.assertIsNone(perioder[1].til)

    def test_samme_modus_to_ganger_gjor_ingenting(self):
        """To klikk på samme knapp ville ellers delt perioden i to og sett ut
        som et vaktbytte."""
        self.assertTrue(services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt))
        self.assertFalse(services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt))
        self.assertEqual(Vaktmodusperiode.objects.filter(enhet=self.lege).count(), 1)

    def test_en_ambulanse_kan_ikke_settes_passiv(self):
        with self.assertRaises(ValueError):
            services.sett_vaktmodus(self.bil, passiv=True, vakt=self.vakt)

    def test_endepunktet_speiler_regelen(self):
        res = self.klient.post(
            f'/oppdrag/api/enheter/{self.lege.pk}/vaktmodus/',
            data={'passiv': True}, content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['data']['passiv_vakt'])

        nekt = self.klient.post(
            f'/oppdrag/api/enheter/{self.bil.pk}/vaktmodus/',
            data={'passiv': True}, content_type='application/json')
        self.assertEqual(nekt.status_code, 400)

    def test_timene_summeres_for_vakta(self):
        """Tallet André ba om: «timer brukt i passiv tid når en helst skulle
        sovet». Lukkede perioder teller fullt, den åpne fram til nå."""
        naa = timezone.now()
        Vaktmodusperiode.objects.create(
            enhet=self.lege, vakt=self.vakt, modus=Vaktmodusperiode.PASSIV,
            fra=naa - timedelta(hours=6), til=naa - timedelta(hours=4))
        Vaktmodusperiode.objects.create(
            enhet=self.bil, vakt=self.vakt, modus=Vaktmodusperiode.PASSIV,
            fra=naa - timedelta(hours=1))
        self.assertAlmostEqual(passiv_timer_for(self.vakt), 3.0, delta=0.05)

    def test_aktiv_tid_teller_ikke_som_passiv(self):
        """Sperrehake: summeres alle perioder, er tallet vaktas lengde."""
        naa = timezone.now()
        Vaktmodusperiode.objects.create(
            enhet=self.lege, vakt=self.vakt, modus=Vaktmodusperiode.AKTIV,
            fra=naa - timedelta(hours=8), til=naa)
        self.assertEqual(passiv_timer_for(self.vakt), 0.0)

    def test_en_annen_vakt_teller_ikke(self):
        """Timene gjelder *dette* arrangementet."""
        from core.models import Vakt
        annen = Vakt.objects.create(
            navn='I fjor', year=AAR - 1,
            startet=timezone.now() - timedelta(days=365), er_aktiv=False)
        naa = timezone.now()
        Vaktmodusperiode.objects.create(
            enhet=self.lege, vakt=annen, modus=Vaktmodusperiode.PASSIV,
            fra=naa - timedelta(hours=5), til=naa)
        self.assertEqual(passiv_timer_for(self.vakt), 0.0)


class ModusenFrysesVedVarslingTests(PassivBasis):

    def test_en_passiv_enhet_stemples_passiv(self):
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        rad = services.varsle_enhet(self._oppdrag(self.bil), self.lege)
        self.assertEqual(rad.varslet_modus, 'passiv')

    def test_en_aktiv_enhet_stemples_aktiv(self):
        rad = services.varsle_enhet(self._oppdrag(self.bil), self.lege)
        self.assertEqual(rad.varslet_modus, 'aktiv')

    def test_en_enhet_uten_passiv_vakt_stemples_tomt(self):
        """Tomt betyr «dette spørsmålet gjaldt ikke henne», ikke «hun var
        aktiv» — og da vises ingenting. «Aktiv» på en ambulanse er støy."""
        rad = services.varsle_enhet(self._oppdrag(self.lege), self.bil)
        self.assertEqual(rad.varslet_modus, '')

    def test_stempelet_staar_naar_bryteren_vippes_etterpaa(self):
        """**Den viktigste av dem.** Leses `Enhet.passiv_vakt` i ettertid,
        ville merket på et oppdrag fra tre timer siden skiftet tekst i det
        noen vipper bryteren — samme grunn som at `importert_av` fryses som
        navn i arkivet."""
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        rad = services.varsle_enhet(self._oppdrag(self.bil), self.lege)
        services.sett_vaktmodus(self.lege, passiv=False, vakt=self.vakt)
        rad.refresh_from_db()
        self.assertEqual(rad.varslet_modus, 'passiv')


class AvventeTests(PassivBasis):

    def test_operatoeren_setter_avventer(self):
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        services.avvent_oppdrag(o, self.lege, bruker=self.operator)
        self.assertTrue(o.enhetshendelser.filter(
            type=Enhetshendelse.AVVENTER, enhet=self.lege).exists())

    def test_hun_blir_staaende_varslet(self):
        """Forskjellen på «avvent» og «ta av»: koblingsraden røres ikke, så
        «Rykk ut» er fortsatt tilgjengelig."""
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        services.avvent_oppdrag(o, self.lege)
        rad = services.koblingsrad(o, self.lege)
        self.assertIsNotNone(rad)
        self.assertEqual(rad.status, choices.VENTER)

    def test_hun_kan_rykke_ut_etterpaa_og_er_da_ikke_avventende(self):
        """Avventingen varer til hun rykker ut. Derfor trenger den ingen egen
        tilstand å nullstille — og en tilstand som må nullstilles blir
        stående når noe feiler halvveis."""
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        services.avvent_oppdrag(o, self.lege)
        self.assertEqual(services.avventende_enhet_ider(o), {self.lege.pk})
        services.start_oppdrag(o, enhet=self.lege)
        self.assertEqual(services.avventende_enhet_ider(o), set())
        self.assertTrue(o.enhetshendelser.filter(
            type=Enhetshendelse.AVVENTER).exists(), 'loggen står')

    def test_en_ambulanse_kan_ikke_avvente(self):
        o = self._oppdrag(self.lege)
        services.varsle_enhet(o, self.bil)
        with self.assertRaises(ValueError):
            services.avvent_oppdrag(o, self.bil)

    def test_avvente_finnes_ikke_etter_at_hun_har_rykket_ut(self):
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        services.start_oppdrag(o, enhet=self.lege)
        with self.assertRaises(services.UlovligOvergang):
            services.avvent_oppdrag(o, self.lege)

    def test_alene_gir_trenger_ny_ressurs(self):
        """André: «skulle de avvente på et oppdrag de blir tildelt alene, så
        kan vi ha trenger ny ressurs»."""
        o = self._oppdrag(self.lege)
        services.avvent_oppdrag(o, self.lege)
        o.refresh_from_db()
        self.assertTrue(o.trenger_ressurs)

    def test_med_en_bil_paa_vei_gjor_den_det_ikke(self):
        """«Det gjelder bare spesialressurser som ofte rykker ut som ekstra
        enhet» — er noen på vei, er oppdraget dekket."""
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        services.start_oppdrag(o, enhet=self.bil)
        services.avvent_oppdrag(o, self.lege)
        o.refresh_from_db()
        self.assertFalse(o.trenger_ressurs)

    def test_en_avventende_skjuler_ikke_behovet_for_en_annen(self):
        """**Den avventende er ikke «på vei».** Hun står i `Venter` som alle
        andre varslede, og uten det leddet ville avventingen skjult behovet i
        stedet for å vise det — altså det motsatte av hva knappen finnes for.
        """
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        services.avvent_oppdrag(o, self.lege)
        # Bilen avbryter: nå er ingen igjen som er på vei.
        services.start_oppdrag(o, enhet=self.bil)
        services.avbryt_oppdrag(o, enhet=self.bil)
        o.refresh_from_db()
        self.assertTrue(o.trenger_ressurs)

    def test_endepunktet_svarer_med_hvem_som_avventer(self):
        o = self._oppdrag(self.bil)
        services.varsle_enhet(o, self.lege)
        res = self.klient.post(
            f'/oppdrag/api/oppdrag/{o.pk}/avvent/{self.lege.pk}/')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['avventer_av'], ['Lege 02'])

    def test_endepunktet_avviser_en_enhet_uten_flagget(self):
        o = self._oppdrag(self.lege)
        services.varsle_enhet(o, self.bil)
        res = self.klient.post(
            f'/oppdrag/api/oppdrag/{o.pk}/avvent/{self.bil.pk}/')
        self.assertEqual(res.status_code, 400)


class KvitteringPaaAvbruttTests(PassivBasis):

    def _avbrutt(self):
        o = self._oppdrag(self.bil)
        services.start_oppdrag(o, enhet=self.bil)
        services.avbryt_oppdrag(o, enhet=self.bil)
        return o

    def test_merket_staar_til_noen_tar_stilling(self):
        o = self._avbrutt()
        self.assertEqual(services.avbrutt_av(o), ['Haugesund 56'])

    def test_kvittering_fjerner_merket(self):
        o = self._avbrutt()
        services.kvitter_avbrutt(o, bruker=self.operator)
        self.assertEqual(services.avbrutt_av(o), [])

    def test_hvem_og_naar_staar_igjen(self):
        """Merket forsvinner, men hendelsen består — og den vet nå hvem som
        tok stilling."""
        o = self._avbrutt()
        services.kvitter_avbrutt(o, bruker=self.operator)
        h = o.enhetshendelser.get(type=Enhetshendelse.AVBRUTT)
        self.assertEqual(h.kvittert_av, self.operator)
        self.assertIsNotNone(h.kvittert_at)

    def test_aa_sende_en_ny_enhet_kvitterer_av_seg_selv(self):
        """André: «det må løses av operatør». Å sende en ny enhet *er* å ta
        stilling; å kreve et klikk i tillegg ville lært operatøren å klikke
        det bort."""
        o = self._avbrutt()
        services.varsle_enhet(o, self.lege, bruker=self.operator)
        self.assertEqual(services.avbrutt_av(o), [])

    def test_endepunktet_kvitterer(self):
        o = self._avbrutt()
        res = self.klient.post(f'/oppdrag/api/oppdrag/{o.pk}/kvitter-avbrutt/')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['avbrutt_av'], [])

    def test_bulk_skjuler_de_kvitterte_ogsaa(self):
        """Lista bruker `avbrutt_av_bulk`; glemmes filteret der, står merket
        på tavla mens detaljvisningen sier at det er borte."""
        o = self._avbrutt()
        services.kvitter_avbrutt(o)
        self.assertEqual(services.avbrutt_av_bulk([o.pk]), {})


class ModusenIArkivetTests(PassivBasis):
    """«Oppdrag i passiv tid» skal overleve arkiveringen.

    Uten kolonnen på `ArkivertOppdrag` forsvant tallet i det vakta ble
    arkivert — altså nøyaktig når rapporten skrives. Og payloaden må bære den
    **bare når den er satt**, som `behandlet_at`: eldre arkiv, og nye rader
    for enheter uten passiv vakt, skal få samme signatur som før.
    """

    def _arkiver(self):
        from .arkiv import arkiver_vakt
        arkiv, _ = arkiver_vakt(self.vakt, 'test', None)
        return arkiv

    def _rader(self, arkiv):
        from .arkiv import OppdragArkivHandler
        return {r['enhet_navn']: r for r in OppdragArkivHandler().rad_dicts(arkiv)}

    def _kjor(self, oppdrag, enhet):
        for st in (choices.RYKKER_UT, choices.FREMME, choices.BEHANDLET,
                   choices.LEDIG):
            services.sett_status(oppdrag, st, enhet=enhet)

    def test_arkivraden_baerer_modusen(self):
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        o = self._oppdrag(self.lege)
        self._kjor(o, self.lege)
        from .models import ArkivertOppdrag
        arkiv = self._arkiver()
        rad = ArkivertOppdrag.objects.get(arkiv=arkiv, enhet_navn='Lege 02')
        self.assertEqual(rad.varslet_modus, 'passiv')

    def test_payloaden_baerer_den_naar_satt(self):
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        o = self._oppdrag(self.lege)
        self._kjor(o, self.lege)
        rader = self._rader(self._arkiver())
        self.assertEqual(rader['Lege 02'].get('varslet_modus'), 'passiv')

    def test_payloaden_utelater_den_naar_tom(self):
        """**Den som holder eldre signaturer i live.** Står nøkkelen der med
        tom verdi, får hver rad en ny payload — og hvert arkiv i prod ville
        meldt tukling."""
        o = self._oppdrag(self.bil)
        self._kjor(o, self.bil)
        rader = self._rader(self._arkiver())
        self.assertNotIn('varslet_modus', rader['Haugesund 56'])

    def test_signaturen_er_uendret_for_en_vakt_uten_passiv_vakt(self):
        """Sperrehaken bak den over: samme oppdrag, samme signatur som før
        feltet fantes. Regnes den ut på nytt med nøkkelen inni, er tallet et
        annet — og da verifiserer ingen gamle arkiv."""
        from core.arkiv import beregn_sha256

        from .arkiv import OppdragArkivHandler
        o = self._oppdrag(self.bil)
        self._kjor(o, self.bil)
        arkiv = self._arkiver()
        handler = OppdragArkivHandler()
        self.assertEqual(beregn_sha256(handler, arkiv), arkiv.sha256)

    def test_statistikken_teller_oppdrag_i_passiv_tid(self):
        from .statistikk import oppdrag_stats
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        self._kjor(self._oppdrag(self.lege), self.lege)
        self._kjor(self._oppdrag(self.bil), self.bil)
        self.assertEqual(oppdrag_stats(self.vakt)['summary']['oppdrag_i_passiv'], 1)

    def test_tallet_overlever_arkiveringen(self):
        """Hele grunnen til at kolonnen finnes."""
        from .statistikk import arkiv_stats
        services.sett_vaktmodus(self.lege, passiv=True, vakt=self.vakt)
        self._kjor(self._oppdrag(self.lege), self.lege)
        self._kjor(self._oppdrag(self.bil), self.bil)
        arkiv = self._arkiver()
        self.assertEqual(arkiv_stats(arkiv)['summary']['oppdrag_i_passiv'], 1)


class FlaggeneKanKryssesAvTests(PassivBasis):
    """**Uten denne veien finnes ikke funksjonen for André.**

    Flaggene sto på `Enhetstype` med riktig standard og riktig lesing, og alt
    over her var grønt — men ingen skjerm kunne sette dem. En funksjon som bare
    lar seg skru på fra et skall er ikke levert; den er skrevet.

    De hører hjemme i «Valglister» sammen med resten av enhetstypene, ikke i
    enhetspanelet: panelet setter *hvilken* type en bil har, dette setter hva
    typen betyr.
    """

    def setUp(self):
        super().setUp()
        import json as _json
        self.dump = _json.dumps
        self.leder = CustomUser.objects.create_user(
            username='leder_pv', password='x', must_change_password=False)
        ModulTilgang.objects.create(
            bruker=self.leder, modul_slug='oppdrag', nivaa='skriv_leder')
        self.lederklient = Client()
        self.lederklient.force_login(self.leder)

    def _put(self, klient, pk, kropp):
        return klient.put(f'/oppdrag/api/enhetstyper/{pk}/',
                          data=self.dump(kropp), content_type='application/json')

    def test_lista_baerer_begge_flaggene(self):
        rad = next(r for r in self.klient.get('/oppdrag/api/enhetstyper/').json()['data']
                   if r['id'] == self.spesial.pk)
        self.assertEqual((rad['kan_passiv_vakt'], rad['kan_avvente']), (True, True))

    def test_lederen_skrur_dem_av_og_paa_hver_for_seg(self):
        """Hver for seg — et felles kall ville skjult at de er to felter."""
        self.assertEqual(self._put(self.lederklient, self.ambulanse.pk,
                                   {'kan_passiv_vakt': True}).status_code, 200)
        self.ambulanse.refresh_from_db()
        self.assertTrue(self.ambulanse.kan_passiv_vakt)
        self.assertFalse(self.ambulanse.kan_avvente, 'det andre flagget står urørt')

        self.assertEqual(self._put(self.lederklient, self.spesial.pk,
                                   {'kan_avvente': False}).status_code, 200)
        self.spesial.refresh_from_db()
        self.assertFalse(self.spesial.kan_avvente)
        self.assertTrue(self.spesial.kan_passiv_vakt)

    def test_endringen_slaar_gjennom_paa_enheten_med_det_samme(self):
        """Flagget leses gjennom typen, ikke kopieres til enheten — så en
        endring gjelder alle bilene i gruppa uten et vedlikeholdsskritt."""
        self.assertFalse(services.kan_avvente(self.bil))
        self._put(self.lederklient, self.ambulanse.pk, {'kan_avvente': True})
        # Hentet på nytt, som serveren gjør ved hver polling: `self.bil` bærer
        # en bufret `enhetstype` fra `setUp`, og å lese den ville målt Djangos
        # objektbuffer i stedet for regelen.
        self.assertTrue(services.kan_avvente(Enhet.objects.get(pk=self.bil.pk)))

    def test_operatoren_setter_ikke_opp_typene(self):
        """`skriv_full` styrer beredskapen; å bestemme hva en *gruppe*
        ressurser har lov til er oppsett, og det er `skriv_leder`. Samme
        skille som i vaktlista mellom å bemanne og å opprette."""
        self.assertEqual(self._put(self.klient, self.ambulanse.pk,
                                   {'kan_avvente': True}).status_code, 403)
        self.ambulanse.refresh_from_db()
        self.assertFalse(self.ambulanse.kan_avvente)


class PassivmerketTegnesTests(SimpleTestCase):
    """**Meldt fra staging 16. sep. 2026 (André):** «i /oppdrag i ressurser-listen
    vises enhver enhet med navnet på enheten og `[object Object]` på alle
    enhetene uavhengig av hva flagget sier.»

    Årsaken var `${trustedHtml(passiv)}` i `_enhetskort()`. `trustedHtml()`
    pakker verdien i `{__trustedHtml: '…'}` for `cellHtml()` i en Tabulator-
    celle — den er **ikke** en escaper for en mal-streng, og i en mal-streng
    blir objektet til `[object Object]`. På *hvert* kort, også de tomme, fordi
    `trustedHtml('')` er et objekt like fullt.

    Samme felle tok «Rett tid» fra fase 3 til 11. sep. 2026. Den sto
    dokumentert i en kommentar ved *det* kallstedet, 500 linjer unna i en annen
    fil — og en advarsel som bare finnes der feilen alt er rettet, advarer
    ingen. Regelen står nå i `tests_xss.py`, der den håndheves for alle filene.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', 'klokke')),
        (OPPDRAG_SENTRAL_JS, ('_enhetskort', 'enhetskortInnmat', 'mkBesetning', 'kanSeBesetning', '_grovMerke',
                              '_problemMedAntall', 'hastegradKlasse', 'tidSiden')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kort(self, **felter):
        data = {'id': 1, 'navn': 'Lege 02', 'status': 'ledig', 'status_navn': 'Ledig',
                'kan_passiv_vakt': False, 'passiv_vakt': False}
        data.update(felter)
        return run_node(self.harness, f"""
            globalThis.window = {{}};
            globalThis.besetninger = {{}}; globalThis.apenBesetning = null;
            console.log(_enhetskort({json.dumps(data)}));
        """)

    def test_ingen_enhet_viser_object_object(self):
        """Feilen André så. Den traff alle kortene, ikke bare de passive."""
        for felter in ({}, {'kan_passiv_vakt': True},
                       {'kan_passiv_vakt': True, 'passiv_vakt': True}):
            with self.subTest(felter=felter):
                self.assertNotIn('[object Object]', self._kort(**felter))

    def test_merket_staar_bare_naar_typen_tillater_det_og_hun_er_passiv(self):
        """Regelen merket bærer. «Aktiv» skrives ikke — det er normalen, og et
        merke på hver ambulanse er støy man slutter å se."""
        self.assertIn('passiv vakt',
                      self._kort(kan_passiv_vakt=True, passiv_vakt=True))
        self.assertNotIn('passiv vakt',
                         self._kort(kan_passiv_vakt=True, passiv_vakt=False))
        self.assertNotIn('passiv vakt',
                         self._kort(kan_passiv_vakt=False, passiv_vakt=True),
                         'flagget på typen er det som avgjør, ikke tilstanden alene')

    def test_navnet_escapes_fortsatt(self):
        kort = self._kort(navn='<img src=x onerror=alert(1)>')
        self.assertNotIn('<img', kort)
        self.assertIn('&lt;img', kort)
