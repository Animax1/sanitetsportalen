"""Tester for oppdragsmodulen, fase 1.

Fase 1 har ingen brukervendte flater. Det som testes er derfor invariantene
modellen hviler på — statusmaskinen, den utledede enhetsstatusen,
korreksjonsregelen og at fritekst ikke verdilogges. Alle fire er den slags
regel som er lett å bryte senere uten at noe synlig går i stykker.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from audit.models import AuditLog
from core.modules import get_module, get_nav_modules, get_visible_modules, reset_registry_cache

from oppdrag import choices, services
from oppdrag.choices import validate_oppdrag_choice_fields
from oppdrag.models import Enhet, Enhetsbytte, Lokasjon, Oppdrag, Statusmelding


AAR = 2098


def _enhet(navn, bruker=None):
    return Enhet.objects.create(navn=navn, user=bruker)


def _lokasjon(navn='Hovedscene'):
    return Lokasjon.objects.get_or_create(navn=navn)[0]


def _oppdrag(enhet, *, status=choices.VENTER, lokasjon=None, fritekst='', year=AAR):
    """Lag et oppdrag med neste ledige nummer.

    Nummeret hentes fra samme teller som viewet bruker, slik at testene ikke
    kan komme i utakt med unikhetskravet (year, oppdragsnummer).
    """
    from oppdrag.services import neste_oppdragsnummer
    return Oppdrag.objects.create(
        year=year,
        oppdragsnummer=neste_oppdragsnummer(year),
        enhet=enhet,
        problemstilling='Pustevansker',
        hastegrad='Akutt',
        lokasjon=lokasjon or _lokasjon(),
        fritekst=fritekst,
        status=status,
    )


class StatusmaskinTests(TestCase):
    """Overgangstabellen er data, ikke `if`-er spredt i viewene."""

    def test_lovlige_overganger_i_kjeden(self):
        for fra, til in (
            (choices.VENTER, choices.RYKKER_UT),
            (choices.RYKKER_UT, choices.FREMME),
            (choices.FREMME, choices.AVREIST),
            (choices.AVREIST, choices.LEVERER),
            (choices.LEVERER, choices.LEDIG),
        ):
            with self.subTest(fra=fra, til=til):
                self.assertTrue(services.kan_gaa_til(fra, til))

    def test_ledig_er_utgang_fra_enhver_status(self):
        for fra in (choices.VENTER, choices.RYKKER_UT, choices.FREMME,
                    choices.AVREIST, choices.LEVERER):
            with self.subTest(fra=fra):
                self.assertTrue(services.kan_gaa_til(fra, choices.LEDIG))

    def test_kan_ikke_hoppe_over_et_ledd(self):
        self.assertFalse(services.kan_gaa_til(choices.VENTER, choices.FREMME))
        self.assertFalse(services.kan_gaa_til(choices.RYKKER_UT, choices.AVREIST))

    def test_kan_ikke_gaa_bakover(self):
        self.assertFalse(services.kan_gaa_til(choices.FREMME, choices.RYKKER_UT))

    def test_ledig_er_terminal(self):
        for til, _ in choices.STATUS_VALG:
            with self.subTest(til=til):
                self.assertFalse(services.kan_gaa_til(choices.LEDIG, til))

    def test_ukjent_status_stenger(self):
        """Samme regel som ukjent nivånavn i `har_tilgang`: False, ikke True."""
        self.assertFalse(services.kan_gaa_til('finnes_ikke', choices.LEDIG))
        self.assertFalse(services.kan_gaa_til(choices.VENTER, 'finnes_ikke'))

    def test_neste_i_kjeden(self):
        self.assertEqual(services.neste_i_kjeden(choices.VENTER), choices.RYKKER_UT)
        self.assertEqual(services.neste_i_kjeden(choices.LEVERER), None)
        self.assertEqual(services.neste_i_kjeden(choices.LEDIG), None)

    def test_ulovlig_overgang_kaster(self):
        oppdrag = _oppdrag(_enhet('E1'))
        with self.assertRaises(services.UlovligOvergang):
            services.sett_status(oppdrag, choices.FREMME)


class EnhetStatusTests(TestCase):
    """Enhetens status utledes. Den lagres ikke noe sted."""

    def setUp(self):
        self.enhet = _enhet('Haugesund 56')

    def test_enhet_uten_oppdrag_er_ledig(self):
        """Ved vaktstart står alle enheter som ledig — uten at noe setter det."""
        self.assertEqual(services.enhet_status(self.enhet)['status'], choices.LEDIG)

    def test_enheten_har_ingen_statuskolonne(self):
        """Vern mot at noen legger til feltet «for enkelhets skyld».

        To kilder til samme sannhet går i utakt første gang noe feiler
        halvveis, og da er det den lagrede som lyver — den ser autoritativ ut.
        """
        felt = {f.name for f in Enhet._meta.concrete_fields}
        self.assertNotIn('status', felt)

    def test_ventende_oppdrag_gjor_ikke_enheten_opptatt(self):
        """Enheten har fått et oppdrag, men ikke rykket ut. Den kan sendes."""
        _oppdrag(self.enhet, status=choices.VENTER)
        info = services.enhet_status(self.enhet)
        self.assertEqual(info['status'], choices.LEDIG)
        self.assertEqual(info['antall_ventende'], 1)

    def test_paabegynt_oppdrag_gir_enhetens_status(self):
        _oppdrag(self.enhet, status=choices.FREMME)
        self.assertEqual(services.enhet_status(self.enhet)['status'], choices.FREMME)

    def test_avsluttet_oppdrag_gjor_enheten_ledig_igjen(self):
        _oppdrag(self.enhet, status=choices.LEDIG)
        self.assertEqual(services.enhet_status(self.enhet)['status'], choices.LEDIG)


class StartOppdragTests(TestCase):
    """Å starte neste oppdrag lukker det pågående automatisk."""

    def setUp(self):
        self.enhet = _enhet('Haugesund 56')

    def test_pagaende_lukkes_naar_neste_startes(self):
        forste = _oppdrag(self.enhet, status=choices.FREMME)
        neste = _oppdrag(self.enhet, status=choices.VENTER)

        services.start_oppdrag(neste)

        forste.refresh_from_db()
        neste.refresh_from_db()
        self.assertEqual(forste.status, choices.LEDIG)
        self.assertEqual(neste.status, choices.RYKKER_UT)

    def test_den_automatiske_meldingen_er_merket(self):
        """Sluttiden er avledet, ikke målt. Flagget gjør at tallene kan skille."""
        forste = _oppdrag(self.enhet, status=choices.FREMME)
        neste = _oppdrag(self.enhet, status=choices.VENTER)

        services.start_oppdrag(neste)

        melding = Statusmelding.objects.get(oppdrag=forste, status=choices.LEDIG)
        self.assertTrue(melding.automatisk)

    def test_manuell_ledig_er_ikke_merket(self):
        """Vern mot at flagget alltid settes."""
        oppdrag = _oppdrag(self.enhet, status=choices.FREMME)
        melding = services.sett_status(oppdrag, choices.LEDIG)
        self.assertFalse(melding.automatisk)

    def test_samme_tidsstempel_paa_begge(self):
        forste = _oppdrag(self.enhet, status=choices.FREMME)
        neste = _oppdrag(self.enhet, status=choices.VENTER)

        ny = services.start_oppdrag(neste)

        lukket = Statusmelding.objects.get(oppdrag=forste, status=choices.LEDIG)
        self.assertEqual(lukket.tidspunkt, ny.tidspunkt)

    def test_annen_enhets_oppdrag_roeres_ikke(self):
        annen = _enhet('Karmøy 12')
        deres = _oppdrag(annen, status=choices.FREMME)
        mitt = _oppdrag(self.enhet, status=choices.VENTER)

        services.start_oppdrag(mitt)

        deres.refresh_from_db()
        self.assertEqual(deres.status, choices.FREMME)


class KorreksjonTests(TestCase):
    """En retting er en ny rad som peker på den gamle."""

    def setUp(self):
        self.enhet = _enhet('Haugesund 56')
        self.oppdrag = _oppdrag(self.enhet, status=choices.LEVERER)
        self.bruker = CustomUser.objects.create_user(
            username='sentralen', password='x', role='bruker',
            must_change_password=False)

    def test_korreksjon_lager_ny_rad_og_beholder_den_gamle(self):
        opprinnelig = services.sett_status(self.oppdrag, choices.LEDIG)
        rettet = services.korriger_tidspunkt(
            opprinnelig, opprinnelig.tidspunkt - timedelta(minutes=6),
            bruker=self.bruker)

        self.assertEqual(
            Statusmelding.objects.filter(oppdrag=self.oppdrag).count(), 2)
        self.assertEqual(rettet.korrigerer_id, opprinnelig.pk)

    def test_gjeldende_returnerer_korreksjonen(self):
        opprinnelig = services.sett_status(self.oppdrag, choices.LEDIG)
        rettet = services.korriger_tidspunkt(
            opprinnelig, opprinnelig.tidspunkt - timedelta(minutes=6),
            bruker=self.bruker)

        gjeldende = Statusmelding.objects.gjeldende(self.oppdrag)
        self.assertIn(rettet, gjeldende)
        self.assertNotIn(opprinnelig, gjeldende)

    def test_korreksjon_av_korreksjon(self):
        """Retter man en retting, er det den siste som står."""
        forste = services.sett_status(self.oppdrag, choices.LEDIG)
        andre = services.korriger_tidspunkt(
            forste, forste.tidspunkt - timedelta(minutes=6), bruker=self.bruker)
        tredje = services.korriger_tidspunkt(
            andre, forste.tidspunkt - timedelta(minutes=3), bruker=self.bruker)

        gjeldende = Statusmelding.objects.gjeldende(self.oppdrag)
        self.assertEqual(gjeldende, [tredje])

    def test_uten_korreksjon_gjelder_originalen(self):
        """Vern mot at `gjeldende` alltid filtrerer bort noe."""
        melding = services.sett_status(self.oppdrag, choices.LEDIG)
        self.assertEqual(Statusmelding.objects.gjeldende(self.oppdrag), [melding])

    def test_korreksjonen_endrer_ikke_status(self):
        """Omfanget er tidspunkt, ikke status."""
        opprinnelig = services.sett_status(self.oppdrag, choices.LEDIG)
        rettet = services.korriger_tidspunkt(
            opprinnelig, opprinnelig.tidspunkt - timedelta(minutes=6),
            bruker=self.bruker)
        self.assertEqual(rettet.status, opprinnelig.status)
        self.oppdrag.refresh_from_db()
        self.assertEqual(self.oppdrag.status, choices.LEDIG)


class EnhetsbytteTests(TestCase):
    """113 flytter oppdraget, og det står i oppdragets egen logg."""

    def setUp(self):
        self.fra = _enhet('Haugesund 56')
        self.til = _enhet('Karmøy 12')
        self.bruker = CustomUser.objects.create_user(
            username='sentral2', password='x', role='bruker',
            must_change_password=False)

    def test_bytte_skriver_rad_og_flytter_oppdraget(self):
        oppdrag = _oppdrag(self.fra, status=choices.FREMME)
        bytte = services.flytt_til_enhet(oppdrag, self.til, bruker=self.bruker)

        oppdrag.refresh_from_db()
        self.assertEqual(oppdrag.enhet, self.til)
        self.assertEqual(bytte.fra_enhet, self.fra)
        self.assertEqual(Enhetsbytte.objects.filter(oppdrag=oppdrag).count(), 1)

    def test_statusen_staar_ved_bytte(self):
        """En responstid som faktisk ble målt skal ikke nullstilles."""
        oppdrag = _oppdrag(self.fra, status=choices.FREMME)
        services.flytt_til_enhet(oppdrag, self.til, bruker=self.bruker)
        oppdrag.refresh_from_db()
        self.assertEqual(oppdrag.status, choices.FREMME)

    def test_bytte_til_samme_enhet_er_ingen_hendelse(self):
        oppdrag = _oppdrag(self.fra)
        self.assertIsNone(
            services.flytt_til_enhet(oppdrag, self.fra, bruker=self.bruker))
        self.assertEqual(Enhetsbytte.objects.count(), 0)


class SynlighetForEnhetTests(TestCase):
    """Avsluttede oppdrag forsvinner fra enhetsskjermen etter 30 minutter."""

    def setUp(self):
        self.enhet = _enhet('Haugesund 56')

    def _avslutt(self, oppdrag, minutter_siden):
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.LEDIG,
            tidspunkt=timezone.now() - timedelta(minutes=minutter_siden))
        Oppdrag.objects.filter(pk=oppdrag.pk).update(status=choices.LEDIG)

    def test_pagaende_oppdrag_vises(self):
        oppdrag = _oppdrag(self.enhet, status=choices.FREMME)
        self.assertIn(oppdrag, services.synlige_for_enhet(self.enhet))

    def test_nylig_avsluttet_vises(self):
        oppdrag = _oppdrag(self.enhet)
        self._avslutt(oppdrag, 10)
        self.assertIn(oppdrag, services.synlige_for_enhet(self.enhet))

    def test_avsluttet_for_lenge_siden_skjules(self):
        oppdrag = _oppdrag(self.enhet)
        self._avslutt(oppdrag, 45)
        self.assertNotIn(oppdrag, services.synlige_for_enhet(self.enhet))

    def test_raden_slettes_ikke(self):
        """Skjuling er et visningsfilter. Sentralbord og statistikk beholder raden."""
        oppdrag = _oppdrag(self.enhet)
        self._avslutt(oppdrag, 45)
        self.assertTrue(Oppdrag.objects.filter(pk=oppdrag.pk).exists())

    def test_en_korreksjon_forlenger_ikke_vinduet(self):
        """Grensen måles mot `Ledig`-meldingens tidspunkt, ikke mot updated_at."""
        oppdrag = _oppdrag(self.enhet)
        self._avslutt(oppdrag, 45)
        gammel = Statusmelding.objects.get(oppdrag=oppdrag, status=choices.LEDIG)
        services.korriger_tidspunkt(
            gammel, gammel.tidspunkt - timedelta(minutes=2), bruker=None)
        self.assertNotIn(oppdrag, services.synlige_for_enhet(self.enhet))


@override_settings(SECURE_SSL_REDIRECT=False)
class AuditFritekstTests(TestCase):
    """Fritekst logges som *endret*, men verdiene skrives ikke.

    ``AuditLog.old_value``/``new_value`` har 730 dagers lagring. Skriver en
    operatør noe sensitivt og retter det, ville begge versjonene ligget der i
    to år. Sporet av at feltet ble endret er det som trengs.
    """

    def setUp(self):
        self.oppdrag = _oppdrag(_enhet('Haugesund 56'), fritekst='opprinnelig')
        AuditLog.objects.all().delete()

    def _rader(self, felt):
        return AuditLog.objects.filter(
            table_name='oppdrag_oppdrag', field_name=felt)

    def test_endring_i_fritekst_gir_en_rad(self):
        self.oppdrag.fritekst = 'noe helt annet'
        self.oppdrag.save()
        self.assertEqual(self._rader('fritekst').count(), 1)

    def test_raden_inneholder_ikke_teksten(self):
        self.oppdrag.fritekst = 'kvinne, 40, Storgata 5'
        self.oppdrag.save()

        rad = self._rader('fritekst').get()
        self.assertNotIn('Storgata', rad.new_value or '')
        self.assertNotIn('opprinnelig', rad.old_value or '')
        self.assertEqual(rad.new_value, '(skjult)')

    def test_uendret_fritekst_gir_ingen_rad(self):
        """Vern mot at skjulingen gjør enhver lagring til en endring."""
        self.oppdrag.hastegrad = 'Vanlig'
        self.oppdrag.save()
        self.assertEqual(self._rader('fritekst').count(), 0)

    def test_andre_felt_logges_med_verdi(self):
        """Skjulingen skal gjelde ett felt, ikke smitte over på resten."""
        self.oppdrag.hastegrad = 'Vanlig'
        self.oppdrag.save()

        rad = self._rader('hastegrad').get()
        self.assertEqual(rad.old_value, 'Akutt')
        self.assertEqual(rad.new_value, 'Vanlig')

    def test_sletting_lagrer_ikke_innhold(self):
        pk = self.oppdrag.pk
        self.oppdrag.delete()
        rad = AuditLog.objects.get(
            table_name='oppdrag_oppdrag', record_id=pk, action='DELETE')
        self.assertIsNone(rad.field_name)
        self.assertIn(rad.old_value, (None, ''))


class ChoicesTests(TestCase):
    """Verdimengden håndheves server-side, ikke bare i nettleseren."""

    def test_gyldige_verdier_gaar_gjennom(self):
        data = {'problemstilling': ' Pustevansker ', 'hastegrad': 'Akutt'}
        validate_oppdrag_choice_fields(data)
        self.assertEqual(data['problemstilling'], 'Pustevansker')

    def test_ugyldig_verdi_avvises(self):
        with self.assertRaises(ValidationError):
            validate_oppdrag_choice_fields({'hastegrad': 'Rød'})

    def test_tom_verdi_avvises(self):
        """Ulikt pasientmodulen: et oppdrag uten hastegrad kan ingen rykke ut på."""
        with self.assertRaises(ValidationError):
            validate_oppdrag_choice_fields({'hastegrad': ''})

    def test_felt_som_ikke_sendes_roeres_ikke(self):
        data = {'hastegrad': 'Akutt'}
        validate_oppdrag_choice_fields(data)
        self.assertNotIn('problemstilling', data)

    def test_listene_er_ikke_delt_med_pasientmodulen(self):
        """Et oppdrag er ikke en pasient. Deles konstanten, står den i veien."""
        from patients import choices as pasient_choices
        self.assertIsNot(choices.PROBLEMSTILLING, pasient_choices.PROBLEMSTILLING)


class LokasjonKommandoTests(TestCase):
    """`python manage.py lokasjon` — flaten fram til fase 3.

    Modulen har ingen URL ennå, med vilje. En admin-side uten vei inn er den
    samme feilen som et modulkort som fører til 404, med et ekstra steg — og
    portalen har allerede hatt én slik. Kommandoen følger
    `appsetting`-presedensen.
    """

    def _kjor(self, *args):
        from io import StringIO
        from django.core.management import call_command
        ut = StringIO()
        call_command('lokasjon', *args, stdout=ut)
        return ut.getvalue()

    def test_legg_til_og_list(self):
        self._kjor('--legg-til', 'Hovedscene')
        self.assertIn('Hovedscene', self._kjor('--list'))

    def test_tom_liste_sier_ifra(self):
        self.assertIn('Ingen lokasjoner', self._kjor('--list'))

    def test_dublett_avvises(self):
        from django.core.management.base import CommandError
        self._kjor('--legg-til', 'Hovedscene')
        with self.assertRaises(CommandError):
            self._kjor('--legg-til', 'Hovedscene')

    def test_deaktivering_sletter_ikke(self):
        """En lokasjon i bruk kan ikke forsvinne — FK-en er PROTECT."""
        self._kjor('--legg-til', 'Hovedscene')
        self._kjor('--deaktiver', 'Hovedscene')
        lok = Lokasjon.objects.get(navn='Hovedscene')
        self.assertFalse(lok.er_aktiv)

    def test_aktivering_igjen(self):
        self._kjor('--legg-til', 'Hovedscene')
        self._kjor('--deaktiver', 'Hovedscene')
        self._kjor('--aktiver', 'Hovedscene')
        self.assertTrue(Lokasjon.objects.get(navn='Hovedscene').er_aktiv)

    def test_nytt_navn_folger_med_paa_oppdragene(self):
        """Et sted som skifter navn er fortsatt samme sted."""
        self._kjor('--legg-til', 'Hovedscene')
        lok = Lokasjon.objects.get(navn='Hovedscene')
        oppdrag = _oppdrag(_enhet('E9'), lokasjon=lok)

        self._kjor('--gi-nytt-navn', 'Hovedscene', 'Scene 1')

        oppdrag.refresh_from_db()
        self.assertEqual(oppdrag.lokasjon.navn, 'Scene 1')

    def test_ukjent_navn_gir_feil(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._kjor('--deaktiver', 'Finnes ikke')

    def test_lokasjon_i_bruk_kan_ikke_slettes(self):
        """PROTECT: historikken skal ikke forsvinne under oppdraget."""
        from django.db.models import ProtectedError
        lok = _lokasjon('Sanitetstelt')
        _oppdrag(_enhet('E10'), lokasjon=lok)
        with self.assertRaises(ProtectedError):
            lok.delete()


class ModulRegistreringTests(TestCase):
    """Modulen er registrert, men skjult inntil den har en side."""

    def setUp(self):
        reset_registry_cache()

    def test_modulen_finnes_i_registeret(self):
        self.assertIsNotNone(get_module('oppdrag'))

    def test_url_og_synlighet_folger_hverandre(self):
        """Et modulkort som fører til 404 er en knapp som fører til en vegg.

        Testen binder de tre feltene sammen. Den sto grønn gjennom fase 1 og 2
        med `url=None` og begge flagg av; fra fase 3 er URL-en satt og
        flaggene på. Poenget er at ingen av delene kan endres alene.
        """
        modul = get_module('oppdrag')
        if modul.url is None:
            self.assertFalse(modul.show_in_nav)
            self.assertFalse(modul.show_in_dashboard)
        else:
            self.assertTrue(modul.url.startswith('/'))
            self.assertTrue(modul.show_in_nav)
            self.assertTrue(modul.show_in_dashboard)

    def test_url_en_svarer(self):
        """Vern mot at flagget slås på før siden finnes.

        Selve feilen testen over beskriver er at kortet fører til 404. Det
        eneste som beviser at det ikke gjør det, er å hente URL-en.
        """
        from django.test import Client
        bruker = CustomUser.objects.create_user(
            username='sjekk_url', password='x', role='bruker',
            must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='oppdrag', nivaa='les')
        modul = get_module('oppdrag')
        if modul.url is None:
            self.skipTest('Modulen har ingen URL ennå')
        c = Client()
        c.force_login(bruker)
        self.assertEqual(c.get(modul.url).status_code, 200)

    def test_tilgang_kreves_selv_med_enhetskobling(self):
        """Å knytte en konto til en `Enhet` gir ingen tilgang.

        Koblingen er domenedata, som `Forstehjelper.user` — §7.3 delte
        `PasientRolleForm` nettopp for å holde kobling og autorisasjon fra
        hverandre. Blandes de, gjenoppstår feilen deploy 1–3 fjernet.
        """
        bruker = CustomUser.objects.create_user(
            username='haugesund56', password='x', role='bruker',
            must_change_password=False, er_delt_konto=True)
        _enhet('Haugesund 56', bruker)

        slugs = {m.slug for m in get_visible_modules(bruker, only_enabled=False)}
        self.assertNotIn('oppdrag', slugs)

    def test_med_modultilgang_er_modulen_synlig(self):
        """Vern mot at testen over passerer fordi ingenting er synlig."""
        bruker = CustomUser.objects.create_user(
            username='sentral3', password='x', role='bruker',
            must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='oppdrag', nivaa='skriv_full')

        slugs = {m.slug for m in get_visible_modules(bruker, only_enabled=False)}
        self.assertIn('oppdrag', slugs)

    def test_modulen_er_i_nav_for_den_som_har_tilgang(self):
        bruker = CustomUser.objects.create_user(
            username='sentral4', password='x', role='bruker',
            must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='oppdrag', nivaa='skriv_full')

        self.assertIn('oppdrag', {m.slug for m in get_nav_modules(bruker)})

    def test_modulen_er_ikke_i_nav_uten_tilgang(self):
        """Vern mot at nav-testen passerer fordi alt vises."""
        bruker = CustomUser.objects.create_user(
            username='sentral5', password='x', role='bruker',
            must_change_password=False)
        self.assertNotIn('oppdrag', {m.slug for m in get_nav_modules(bruker)})
