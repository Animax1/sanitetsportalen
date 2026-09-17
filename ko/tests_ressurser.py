"""Ressursbildet (pulje 3, §3.1) — projeksjonen, den tredje kilden og portene.

Tyngden ligger der `CLAUDE.md` plasserer den: **tjenestelaget tungt** (hver
gren, hver grense, hver sperre), **portene på viewene**, ingenting på markup.
Feil her legger seg i data og oppdages av ingen — bortsett fra den ene dagen
operatøren sender et lag som står ute av drift.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.vakt import hent_aktiv_vakt, vakt_for_year
from ko import choices as ko_choices
from ko import services
from ko.models import KILDE_SYSTEM, Logglinje, Ressursstatus
from ko.systemlinjer import RESSURS_STATUS
from oppdrag.models import Enhet
from vaktliste import choices as vl_choices
from vaktliste.models import (
    Korps, Mannskap, Ressurs, Ressursgruppe, Vaktliste, Vaktpost,
)


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi_ko(bruker, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug='ko', defaults={'nivaa': nivaa})
    return bruker


class Grunnoppsett(TestCase):
    """Én vaktliste, én bil (melder selv) og ett lag (ført av KO).

    **De to er hele poenget med §3.1**, og en fikstur med bare den ene ville
    latt halve regelen stå udekket — det er nettopp en bil uten `enhet` eller
    et lag med som gir feil.
    """

    def setUp(self):
        self.vakt = vakt_for_year(2026)
        self.liste = Vaktliste.objects.create(vakt=self.vakt)
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        # `Ressursgruppe.navn` er unik, og migrasjon 0002 seeder et sett.
        # `get_or_create` her og ikke oppdiktede navn: gruppene er nettopp de
        # som finnes i prod, og rekkefølgen settes eksplisitt fordi testen
        # under handler om den.
        self.biler, _ = Ressursgruppe.objects.get_or_create(navn='Biler')
        self.lag, _ = Ressursgruppe.objects.get_or_create(navn='Lag')
        Ressursgruppe.objects.filter(pk=self.biler.pk).update(rekkefolge=1)
        Ressursgruppe.objects.filter(pk=self.lag.pk).update(rekkefolge=2)
        self.biler.refresh_from_db()
        self.lag.refresh_from_db()
        self.enhet = Enhet.objects.create(navn='Haugesund 56')
        self.bil = Ressurs.objects.create(
            vaktliste=self.liste, navn='Haugesund 56', gruppe=self.biler,
            korps=self.korps, enhet=self.enhet, rekkefolge=1)
        self.lag3 = Ressurs.objects.create(
            vaktliste=self.liste, navn='Lag 3', gruppe=self.lag,
            korps=self.korps, rekkefolge=1)

    def _bemann(self, ressurs, navn='Kari', mott=True, naa=None):
        naa = naa or timezone.now()
        mannskap = Mannskap.objects.create(
            navn=navn, korps=self.korps, telefon='99887766', issi='0401234')
        return Vaktpost.objects.create(
            ressurs=ressurs, mannskap=mannskap, korps=self.korps,
            fra_tid=naa - timedelta(hours=1), til_tid=naa + timedelta(hours=7),
            mott_at=naa - timedelta(minutes=30) if mott else None)

    def _ressurs(self, bilde, navn):
        for g in bilde['grupper']:
            for r in g['ressurser']:
                if r['navn'] == navn:
                    return r
        raise AssertionError(f'{navn} står ikke i bildet')


class HvemSomFoererStatusenTests(Grunnoppsett):
    """**Utledet av `Ressurs.enhet`, ikke av et flagg.**

    Et eget flagg ville vært en andre sannhet om det samme, og de to ville
    stått i strid den dagen noen koblet en enhet uten å rydde flagget. Det er
    samme feilklasse som en lagret status ved siden av en utledet.
    """

    def test_ressurs_uten_enhet_foeres_av_ko(self):
        self.assertTrue(services._fort_av_ko(self.lag3))

    def test_ressurs_med_enhet_melder_selv(self):
        self.assertFalse(services._fort_av_ko(self.bil))

    def test_kobles_en_enhet_paa_slutter_ko_aa_foere(self):
        """Regelen skal følge feltet, ikke et oppsett gjort én gang."""
        self.lag3.enhet = self.enhet
        self.lag3.save(update_fields=['enhet'])
        self.assertFalse(services._fort_av_ko(self.lag3))


class DenTredjeKildenTests(Grunnoppsett):

    def setUp(self):
        super().setUp()
        self.operator = _gi_ko(_bruker('operator'), 'skriv_full')

    def test_status_skrives_og_leses(self):
        services.sett_ressursstatus(self.lag3, ko_choices.OPPTATT,
                                    bruker=self.operator)
        rad = Ressursstatus.objects.get(ressurs=self.lag3)
        self.assertEqual(rad.status, ko_choices.OPPTATT)
        self.assertEqual(rad.satt_av_navn, 'operator')

    def test_uten_rad_er_ressursen_ledig(self):
        """**Fravær av rad er ikke «ukjent», det er «Ledig».**

        Utledet og ikke lagret, av samme grunn som `enhet_status`: en lagret
        standard måtte settes for hver ressurs i hver vaktliste, og da er
        spørsmålet «hvem glemte å sette den».
        """
        self.assertFalse(Ressursstatus.objects.filter(ressurs=self.lag3).exists())
        rad = self._ressurs(services.ressursbildet(), 'Lag 3')
        self.assertEqual(rad['status'], ko_choices.LEDIG)
        self.assertEqual(rad['status_navn'], 'Ledig')

    def test_en_ressurs_har_én_rad_ikke_en_historikk(self):
        """Historikken ligger i loggen. To kilder til samme historikk går i
        utakt, og da er det den lagrede som lyver."""
        for status in (ko_choices.OPPTATT, ko_choices.PAUSE, ko_choices.LEDIG):
            services.sett_ressursstatus(self.lag3, status, bruker=self.operator)
        self.assertEqual(Ressursstatus.objects.filter(ressurs=self.lag3).count(), 1)
        self.assertEqual(
            Logglinje.objects.filter(systemkode=RESSURS_STATUS).count(), 3,
            'hver føring skal stå som sin egen linje i loggen')

    def test_en_bil_kan_ikke_foeres_av_ko(self):
        """Sperra, og den er ikke «ugyldig verdi» — svaret er et annet."""
        with self.assertRaises(services.Ugyldig) as ctx:
            services.sett_ressursstatus(self.bil, ko_choices.OPPTATT,
                                        bruker=self.operator)
        self.assertIn('melder sin egen status', str(ctx.exception))
        self.assertFalse(Ressursstatus.objects.filter(ressurs=self.bil).exists())

    def test_ukjent_status_avvises(self):
        """Ukjent verdi stenger døra. En skrivefeil skal ikke bli en status."""
        for tull in ('', None, 'ledigg', 'LEDIG', 'på post'):
            with self.subTest(verdi=tull):
                with self.assertRaises(services.Ugyldig):
                    services.sett_ressursstatus(self.lag3, tull,
                                                bruker=self.operator)
        self.assertFalse(Ressursstatus.objects.exists())

    def test_systemlinja_baerer_frosne_navn(self):
        """Ressursen henger på vaktlista med `CASCADE` og er borte neste
        sesong; linja skal stå i 730 dager og fortsatt ha et subjekt."""
        services.sett_ressursstatus(self.lag3, ko_choices.UTE_AV_DRIFT,
                                    bruker=self.operator)
        linje = Logglinje.objects.get(systemkode=RESSURS_STATUS)
        self.assertEqual(linje.kilde, KILDE_SYSTEM)
        self.assertEqual(linje.systemdata['ressurs'], 'Lag 3')
        self.assertEqual(linje.systemdata['gruppe'], 'Lag')
        self.assertEqual(linje.systemdata['status_navn'], 'Ute av drift')

        self.lag3.delete()
        linje.refresh_from_db()
        self.assertEqual(linje.systemdata['ressurs'], 'Lag 3',
                         'linja mistet subjektet sitt da ressursen forsvant')

    def test_ingen_rad_uten_linje(self):
        """De to skrives i samme transaksjon, og rekkefølgen er ikke
        likegyldig: linja *er* historikken."""
        from unittest.mock import patch

        with patch.object(services, 'systemlinje', side_effect=RuntimeError('nede')):
            with self.assertRaises(RuntimeError):
                services.sett_ressursstatus(self.lag3, ko_choices.PAUSE,
                                            bruker=self.operator)
        self.assertFalse(
            Ressursstatus.objects.exists(),
            'raden ble stående uten linja si — da er endringen usporbar')


class ProjeksjonenTests(Grunnoppsett):

    def test_gruppene_kommer_i_sin_egen_rekkefolge(self):
        bilde = services.ressursbildet()
        # Bare gruppene som faktisk har ressurser i lista er med.
        self.assertEqual([g['navn'] for g in bilde['grupper']], ['Biler', 'Lag'])

    def test_bemanningen_er_skiftet_som_dekker_naa(self):
        """«Er ressursen bemannet», ikke «hvem har vakt i løpet av helga».

        Et skift som sluttet for en time siden skal ikke telle med — det er
        nettopp den raden som får en tavle til å påstå at noen er der.
        """
        naa = timezone.now()
        self._bemann(self.lag3, navn='Kari')
        ferdig = self._bemann(self.lag3, navn='Ola')
        ferdig.fra_tid = naa - timedelta(hours=9)
        ferdig.til_tid = naa - timedelta(hours=1)
        ferdig.save(update_fields=['fra_tid', 'til_tid'])

        rad = self._ressurs(services.ressursbildet(naa), 'Lag 3')
        self.assertEqual([m['navn'] for m in rad['mannskap']], ['Kari'])

    def test_tilstede_utledes_av_stemplene(self):
        self._bemann(self.lag3, navn='Kari', mott=True)
        self._bemann(self.lag3, navn='Ola', mott=False)
        rad = self._ressurs(services.ressursbildet(), 'Lag 3')
        self.assertEqual(rad['bemanning_antall'], 2)
        self.assertEqual(rad['bemanning_tilstede'], 1)

    def test_bilens_status_kommer_fra_oppdragsmodulen(self):
        """Den andre kilden. Uten et oppdrag er hun `Ledig`, og det er
        utledet der — ikke noe KO lagrer."""
        rad = self._ressurs(services.ressursbildet(), 'Haugesund 56')
        self.assertFalse(rad['fort_av_ko'])
        self.assertEqual(rad['status'], 'ledig')
        self.assertEqual(rad['antall_ventende'], 0)

    def test_uten_vaktliste_er_svaret_none_og_ikke_tomt(self):
        """**Ukoblet og tomt skal ikke se likt ut.** Ingen liste er et oppsett
        som mangler; en tom liste er en vakt uten ressurser."""
        # `hent_aktiv_vakt()` er aldri `None` — den lager vakta om den
        # mangler. Det er *vaktlista* som kan være borte, og det er den
        # tilstanden flata må kunne si noe fornuftig om.
        Ressurs.objects.all().delete()
        Vaktliste.objects.all().delete()
        bilde = services.ressursbildet()
        self.assertIsNone(bilde['vaktliste'])
        self.assertEqual(bilde['grupper'], [])

    def test_lista_i_drift_vinner_over_aktiv_vakt(self):
        """André, 12. sep. 2026: «koblingen fungerer ikke». Scopet var
        portalens aktive vakt alene, og da fant flata ingenting mens lista som
        faktisk kjørte lå på en annen vakt."""
        annen = vakt_for_year(2025)
        drift = Vaktliste.objects.create(vakt=annen, status=vl_choices.DRIFT,
                                         satt_i_drift_at=timezone.now())
        Ressurs.objects.create(vaktliste=drift, navn='Lag 9', gruppe=self.lag,
                               korps=self.korps, rekkefolge=1)
        bilde = services.ressursbildet()
        navn = [r['navn'] for g in bilde['grupper'] for r in g['ressurser']]
        self.assertEqual(navn, ['Lag 9'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(Grunnoppsett):
    """Portene, ikke feltene — `CLAUDE.md` sitt middels-nivå for views."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def _post(self, pk, status='opptatt'):
        return self.client.post(
            f'/ko/api/ressurser/{pk}/status/', data=json.dumps({'status': status}),
            content_type='application/json')

    def test_lesing_krever_les(self):
        self.client.force_login(_bruker('uten'))
        self.assertEqual(self.client.get('/ko/api/ressurser/').status_code, 403)
        self.client.force_login(_gi_ko(_bruker('leser'), 'les'))
        self.assertEqual(self.client.get('/ko/api/ressurser/').status_code, 200)

    def test_skriving_krever_skriv_full(self):
        """`les` ser tavla og skal ikke kunne føre på den. Nivået under
        (`skriv_handling`) leser ikke request-kroppen, og statusen *er*
        kroppen."""
        self.client.force_login(_gi_ko(_bruker('leser'), 'les'))
        self.assertEqual(self._post(self.lag3.pk).status_code, 403)
        self.client.force_login(_gi_ko(_bruker('skriver'), 'skriv_full'))
        self.assertEqual(self._post(self.lag3.pk).status_code, 200)

    def test_anonym_slipper_ikke_inn(self):
        for svar in (self.client.get('/ko/api/ressurser/'),
                     self._post(self.lag3.pk)):
            self.assertIn(svar.status_code, (302, 403))

    def test_ressurs_utenfor_lista_i_bruk_gir_404(self):
        """En ID utenfor lista er enten en gammel fane eller noen som gjetter,
        og begge skal få samme svar som for en ID som ikke finnes."""
        annen = Vaktliste.objects.create(vakt=vakt_for_year(2025))
        utenfor = Ressurs.objects.create(vaktliste=annen, navn='Lag 9',
                                         gruppe=self.lag, korps=self.korps)
        self.client.force_login(_gi_ko(_bruker('skriver'), 'skriv_full'))
        self.assertEqual(self._post(utenfor.pk).status_code, 404)
        self.assertEqual(self._post(999999).status_code, 404)

    def test_bilen_avvises_med_400_og_en_lesbar_grunn(self):
        self.client.force_login(_gi_ko(_bruker('skriver'), 'skriv_full'))
        svar = self._post(self.bil.pk)
        self.assertEqual(svar.status_code, 400)
        self.assertIn('melder sin egen status', svar.json()['message'])

    def test_svaret_er_hele_bildet_paa_nytt(self):
        """Tavla tegnes av svaret, ikke av en ny runde polling: mellom en POST
        og neste poll er det ellers et vindu der knappen ser ut til å ikke ha
        virket."""
        self.client.force_login(_gi_ko(_bruker('skriver'), 'skriv_full'))
        data = self._post(self.lag3.pk).json()['data']
        rad = self._ressurs(data, 'Lag 3')
        self.assertEqual(rad['status'], ko_choices.OPPTATT)


class FeatureParityMedSentralbordetTests(Grunnoppsett):
    """KOs ressurskort skal kunne det sentralbordets kort kan.

    André, 17. sep. 2026: «Det er ikke feature parity med /oppdrag. Jeg vil ha
    det likt feature messig inn her i /ko.» Parity som *holder* er den som
    følger av konstruksjonen — begge leser `oppdrag.services.enhetskort()` —
    og disse prøvene er det som hindrer at de to glir fra hverandre igjen.
    """

    def test_enheten_baerer_alle_kortets_felter(self):
        """Ikke et utvalg. Et utvalg ville falt bak neste felt noen la til i
        oppdragsmodulen, uten at noe ble rødt."""
        from oppdrag.services import tomt_enhetskort

        rad = self._ressurs(services.ressursbildet(), 'Haugesund 56')
        for felt in tomt_enhetskort():
            with self.subTest(felt=felt):
                self.assertIn(felt, rad)

    def test_laget_har_samme_form_som_bilen(self):
        """En manglende nøkkel blir `undefined` midt i en mal-streng, og da
        står det «undefined» på tavla i stedet for ingenting."""
        bilde = services.ressursbildet()
        bil = self._ressurs(bilde, 'Haugesund 56')
        lag = self._ressurs(bilde, 'Lag 3')
        self.assertEqual(set(bil), set(lag))

    def test_ressursens_navn_vinner_over_enhetens(self):
        """`enhetskort()` skriver sitt eget `navn` og `id`. På tavla er det
        vaktlistas navn som gjelder — det er det navnet sambandet bruker, og
        `data-id` må peke på ressursen for at statusknappene skal treffe."""
        # PK-ene må skille seg, ellers er assertionen under sann ved et
        # uhell: i en fersk base er både ressursen og enheten nr. 1.
        enhet2 = Enhet.objects.create(navn='Haugesund 57')
        self.bil.enhet = enhet2
        self.bil.navn = 'Bil A'
        self.bil.save(update_fields=['enhet', 'navn'])
        self.assertNotEqual(self.bil.pk, enhet2.pk)

        rad = self._ressurs(services.ressursbildet(), 'Bil A')
        self.assertEqual(rad['id'], self.bil.pk,
                         'data-id må peke på ressursen, ikke på enheten')
        self.assertEqual(rad['navn'], 'Bil A',
                         'vaktlistas navn er det sambandet bruker')

    def test_passiv_vakt_og_ventende_foelger_med(self):
        """To felter sentralbordets kort viser og KO manglet før dette."""
        rad = self._ressurs(services.ressursbildet(), 'Haugesund 56')
        self.assertIn('passiv_vakt', rad)
        self.assertIn('kan_passiv_vakt', rad)
        self.assertEqual(rad['antall_ventende'], 0)

    def test_feltene_er_fylt_og_ikke_bare_til_stede(self):
        """**Sperrehake mot testen over.** Raden får alle nøklene av
        `tomt_enhetskort()`, så en KO-side som sluttet å kalle `enhetskort()`
        og bare fylte `status` ville gått grønn på «har feltet» — mutanten
        overlevde nøyaktig sånn 17. sep. 2026. Her kreves *verdiene*.
        """
        from oppdrag.models import Enhetstype

        # `Enhetstype.navn` er unik, og migrasjonene seeder settet.
        type_, _ = Enhetstype.objects.get_or_create(navn='Ambulanse')
        Enhetstype.objects.filter(pk=type_.pk).update(kan_passiv_vakt=True)
        type_.refresh_from_db()
        self.enhet.enhetstype = type_
        self.enhet.passiv_vakt = True
        self.enhet.pa_vakt = True
        self.enhet.save(update_fields=['enhetstype', 'passiv_vakt', 'pa_vakt'])

        rad = self._ressurs(services.ressursbildet(), 'Haugesund 56')
        self.assertEqual(rad['type_navn'], 'Ambulanse')
        self.assertTrue(rad['kan_passiv_vakt'])
        self.assertTrue(rad['passiv_vakt'], 'passiv vakt kom ikke gjennom')
        self.assertTrue(rad['pa_vakt'])
        self.assertEqual(rad['status_navn'], 'Ledig')

    def test_antall_er_pasienter_og_ikke_mannskap(self):
        """**Navnekollisjonen.** `enhetskort()` bruker `antall` om pasienter på
        oppdraget, og `_problemMedAntall()` i kortet leser nettopp det feltet:
        «Transport · 3 pasienter». Skriver KO mannskapstallet dit, viser en bil
        på et transportoppdrag antall folk i bilen som antall pasienter — en
        feil ingen ser som en feil, bare som et tall som er litt rart.
        """
        from oppdrag.models import Lokasjon, Oppdrag
        from oppdrag import services as oppdrag_services  # noqa: F401

        self.operator = _gi_ko(_bruker('foerer'), 'skriv_full')
        self._bemann(self.bil, navn='Kari')
        self._bemann(self.bil, navn='Ola')
        lok, _ = Lokasjon.objects.get_or_create(navn='Scene')
        oppdrag = Oppdrag.objects.create(
            vakt=self.vakt, enhet=self.enhet,
            oppdragsnummer=oppdrag_services.neste_oppdragsnummer(self.vakt),
            problemstilling='Transport', hastegrad='Akutt', lokasjon=lok,
            antall=3)
        # `Oppdrag.objects.create(enhet=...)` lager koblingsraden selv; et
        # `varsle_enhet()` i tillegg avvises med «er alt varslet».
        #
        # **Enheten må ha *påbegynt*.** `aktiv_koblingsrad()` ser bort fra
        # `venter`: en rad som ligger og venter teller ikke, for enheten har
        # ikke rykket ut og kan sendes et annet sted. Uten stemplinga står
        # oppdragsfeltene tomme, og testen ville målt feil ting.
        rad_e = oppdrag.enheter.get(enhet=self.enhet)
        oppdrag_services.foer_status(
            oppdrag, self.enhet, 'rykker_ut',
            tidspunkt=timezone.now(), bruker=self.operator)
        rad_e.refresh_from_db()

        rad = self._ressurs(services.ressursbildet(), 'Haugesund 56')
        self.assertEqual(rad['antall'], 3, 'antall skal være pasientene')
        self.assertEqual(rad['bemanning_antall'], 2, 'mannskapet har egne felter')
        self.assertEqual(rad['problemstilling'], 'Transport')

        # **Og laget skal ikke få mannskapstallet i pasientfeltet heller.**
        # For enheten beskytter rekkefølgen oss — `enhetskort()` skriver
        # `antall` etterpå — så en mutant som satte det galt der er en no-op.
        # For laget finnes ingen slik overskriving, og det er der regelen må
        # prøves (17. sep. 2026, overlevende mutant).
        self._bemann(self.lag3, navn='Per')
        lag = self._ressurs(services.ressursbildet(), 'Lag 3')
        self.assertIsNone(lag['antall'],
                          'laget har ingen pasienter — feltet er enhetens')
        self.assertEqual(lag['bemanning_antall'], 1)

    def test_ledig_siden_foelger_med(self):
        """Feltet «ledig siden» fyller tomrommet for en ledig enhet (André,
        15. sep. 2026): hun har ingen aktiv koblingsrad, så `status_tidspunkt`
        er tomt, og operatøren som skal sende noen vil vite hvem som har stått
        lengst. `ledig_siden_bulk()` spørres for hele lista i én runde, og en
        KO-side som droppet argumentet ville mistet feltet i stillhet.
        """
        from oppdrag.models import Lokasjon, Oppdrag
        from oppdrag import services as oppdrag_services

        fører = _gi_ko(_bruker('ledigfoerer'), 'skriv_full')
        lok, _ = Lokasjon.objects.get_or_create(navn='Scene')
        oppdrag = Oppdrag.objects.create(
            vakt=self.vakt, enhet=self.enhet,
            oppdragsnummer=oppdrag_services.neste_oppdragsnummer(self.vakt),
            problemstilling='Fall', hastegrad='Akutt', lokasjon=lok)
        naa = timezone.now()
        for status in ('rykker_ut', 'fremme', 'ledig'):
            oppdrag_services.foer_status(oppdrag, self.enhet, status,
                                         tidspunkt=naa, bruker=fører)

        rad = self._ressurs(services.ressursbildet(), 'Haugesund 56')
        self.assertEqual(rad['status'], 'ledig')
        self.assertIsNotNone(
            rad['ledig_siden'],
            'ledig_siden kom ikke gjennom — kortet står da uten tid')


class BesetningenEtterVaktlistetilgangTests(Grunnoppsett):
    """**Mannskapslista er `vaktliste`-tilgang, ikke KO-tilgang.**

    Komposisjonsregelen fra rollemodellen §5, og samme gate sentralbordet
    bruker for besetningspanelet (`oppdrag/views.py`). Den sto åpen fra pulje 3
    til 17. sep. 2026: alle med `ko:les` fikk se hvem som gikk vakt. Feilen var
    stille — markupen så helt riktig ut.
    """

    def setUp(self):
        super().setUp()
        self._bemann(self.lag3, navn='Kari')
        self.client = Client()

    def test_uten_vaktlistetilgang_utelates_mannskapet(self):
        bilde = services.ressursbildet(kan_se_besetning=False)
        rad = self._ressurs(bilde, 'Lag 3')
        self.assertEqual(rad['mannskap'], [])
        self.assertEqual(rad['bemanning_antall'], 0)
        self.assertEqual(rad['bemanning_tilstede'], 0)

    def test_med_vaktlistetilgang_staar_navnene(self):
        rad = self._ressurs(services.ressursbildet(kan_se_besetning=True), 'Lag 3')
        self.assertEqual([m['navn'] for m in rad['mannskap']], ['Kari'])

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_endepunktet_gater_paa_vaktliste_og_ikke_paa_ko(self):
        """Prøvd gjennom den ekte inngangen: en konto med full KO-tilgang og
        **ingen** vaktlistetilgang skal ikke få navnene."""
        bruker = _gi_ko(_bruker('bare_ko'), 'skriv_leder')
        self.client.force_login(bruker)
        data = self.client.get('/ko/api/ressurser/').json()['data']
        navn = [m['navn'] for g in data['grupper'] for r in g['ressurser']
                for m in r['mannskap']]
        self.assertEqual(navn, [], 'KO-tilgang alene ga innsyn i vaktlista')

        ModulTilgang.objects.update_or_create(
            bruker=bruker, modul_slug='vaktliste', defaults={'nivaa': 'les'})
        data = self.client.get('/ko/api/ressurser/').json()['data']
        navn = [m['navn'] for g in data['grupper'] for r in g['ressurser']
                for m in r['mannskap']]
        self.assertEqual(navn, ['Kari'])
