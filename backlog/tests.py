"""Backlog-modulen: tilgangen, angrefristen og filteret.

Angrefristen er den ene regelen med en grense, og den prøves på begge sider.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from backlog import services
from backlog.models import Innspill, Innspilltype
from core.modules import get_module


def _bruker(navn, **kw):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kw)


def _gi(bruker, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug='backlog', defaults={'nivaa': nivaa})
    return bruker


def _klient(bruker):
    c = Client()
    c.force_login(bruker)
    return c


def _type(navn='Bug'):
    """Typen migrasjon `0002` seeder. Slås opp framfor å lages, slik at en
    seeding som slutter å virke blir synlig — samme grep som
    `vaktliste.test_helpers.gruppe()`."""
    return Innspilltype.objects.get(navn=navn)


class ModuldeklarasjonenTests(SimpleTestCase):

    def test_modulen_er_registrert(self):
        modul = get_module('backlog')
        self.assertIsNotNone(modul, 'backlog står ikke i core/modules.py')
        self.assertEqual(modul.url, '/backlog/')

    def test_de_tre_nivaaene_og_ingen_flere(self):
        """**Andrés tre, oversatt.** `skriv_handling` er hoppet over med vilje:
        nivået leser ikke request-kroppen, og innmelding gjør nettopp det."""
        self.assertEqual(get_module('backlog').nivaaer,
                         ('les', 'skriv_full', 'skriv_leder'))

    def test_hvert_nivaa_har_modulens_egen_etikett(self):
        """`skriv_leder` betyr «setter opp vakta» i vaktlista og «avgjør hva
        som er løst» her. Uten etiketten deles nivået ut med feil modul i
        hodet."""
        modul = get_module('backlog')
        merket = {v for v, _ in modul.nivaa_navn}
        self.assertEqual(set(modul.nivaaer) - merket, set())


class AngrefristenTests(TestCase):
    """`services.kan_endres()` — tre vilkår, og grensen prøves fra begge sider."""

    def setUp(self):
        self.forfatter = _bruker('forfatter')
        self.andre = _bruker('andre')
        self.innspill = Innspill.objects.create(
            type=_type(), tittel='Noe er galt',
            opprettet_av=self.forfatter, opprettet_av_navn='forfatter')

    def test_forfatteren_kan_endre_med_en_gang(self):
        self.assertTrue(services.kan_endres(self.innspill, self.forfatter))

    def test_en_annen_kan_ikke(self):
        """Ikke «samme navn» — FK-en. Det frosne navnet er visning og kan
        gjentas av en ny konto med samme brukernavn."""
        self.assertFalse(services.kan_endres(self.innspill, self.andre))

    def test_grensa_gaar_der_den_staar(self):
        """59 minutter inne, 61 ute. En grense av med én er usynlig i bruk."""
        naa = self.innspill.opprettet_at
        self.assertTrue(services.kan_endres(
            self.innspill, self.forfatter, naa + timedelta(minutes=59)))
        self.assertTrue(services.kan_endres(
            self.innspill, self.forfatter, naa + services.ANGREFRIST))
        self.assertFalse(services.kan_endres(
            self.innspill, self.forfatter, naa + timedelta(minutes=61)))

    def test_fristen_maales_fra_opprettelsen_ikke_fra_endringen(self):
        """**Ellers er ikke fristen en frist.** Fra endringstidspunktet kunne
        et innspill holdes redigerbart i det uendelige ved å røres hver time."""
        naa = timezone.now()
        Innspill.objects.filter(pk=self.innspill.pk).update(
            opprettet_at=naa - timedelta(hours=2))
        self.innspill.refresh_from_db()
        self.innspill.tittel = 'Rørt nå'
        self.innspill.save()                      # setter endret_at til nå
        self.innspill.refresh_from_db()
        self.assertFalse(services.kan_endres(self.innspill, self.forfatter))

    def test_en_lost_sak_kan_ikke_endres_selv_innen_fristen(self):
        """En løst sak er et svar noen har gitt. Skriver forfatteren om
        spørsmålet etterpå, blir svaret uforståelig."""
        self.innspill.lost = True
        self.innspill.save()
        self.assertFalse(services.kan_endres(self.innspill, self.forfatter))

    def test_global_admin_er_ikke_unntatt(self):
        """Fristen verner loggen, ikke forfatteren."""
        sjef = _bruker('sjef', role='admin')
        self.assertFalse(services.kan_endres(self.innspill, sjef))

    def test_anonym_og_none_gir_false(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(services.kan_endres(self.innspill, AnonymousUser()))
        self.assertFalse(services.kan_endres(self.innspill, None))
        self.assertFalse(services.kan_endres(None, self.forfatter))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TilgangTests(TestCase):
    """De tre nivåene, målt ved å kjøre koden."""

    def setUp(self):
        self.leser = _gi(_bruker('leser'), 'les')
        self.skriver = _gi(_bruker('skriver'), 'skriv_full')
        self.leder = _gi(_bruker('leder'), 'skriv_leder')

    def _meld_inn(self, klient, **kw):
        kropp = {'type': _type().pk, 'tittel': 'Noe er galt'}
        kropp.update(kw)
        return klient.post('/backlog/api/innspill/', data=json.dumps(kropp),
                           content_type='application/json')

    def test_uten_rad_er_alt_stengt(self):
        c = _klient(_bruker('utenfor'))
        self.assertEqual(c.get('/backlog/').status_code, 403)
        self.assertEqual(c.get('/backlog/api/innspill/').status_code, 403)

    def test_les_ser_lista_men_melder_ikke_inn(self):
        c = _klient(self.leser)
        self.assertEqual(c.get('/backlog/').status_code, 200)
        self.assertEqual(c.get('/backlog/api/innspill/').status_code, 200)
        self.assertEqual(self._meld_inn(c).status_code, 403)
        self.assertEqual(Innspill.objects.count(), 0,
                         'et avvist kall skal ikke ha opprettet noe')

    def test_skriv_full_melder_inn(self):
        svar = self._meld_inn(_klient(self.skriver))
        self.assertEqual(svar.status_code, 201)
        innspill = Innspill.objects.get()
        self.assertEqual(innspill.opprettet_av, self.skriver)
        self.assertEqual(innspill.opprettet_av_navn, 'skriver',
                         'navnet skal fryses på raden')
        self.assertFalse(innspill.lost)

    def test_skriv_full_kan_ikke_sette_lost(self):
        self._meld_inn(_klient(self.skriver))
        pk = Innspill.objects.get().pk
        svar = _klient(self.skriver).post(f'/backlog/api/innspill/{pk}/lost/')
        self.assertEqual(svar.status_code, 403)
        self.assertFalse(Innspill.objects.get().lost)

    def test_skriv_leder_setter_lost_og_gjenapner(self):
        self._meld_inn(_klient(self.skriver))
        pk = Innspill.objects.get().pk
        c = _klient(self.leder)

        self.assertEqual(c.post(f'/backlog/api/innspill/{pk}/lost/').status_code, 200)
        i = Innspill.objects.get()
        self.assertTrue(i.lost)
        self.assertEqual(i.lost_av_navn, 'leder')
        self.assertIsNotNone(i.lost_at)

        self.assertEqual(c.post(f'/backlog/api/innspill/{pk}/gjenapne/').status_code, 200)
        i = Innspill.objects.get()
        self.assertFalse(i.lost)
        self.assertEqual(i.lost_av_navn, '',
                         'gjenåpning skal tømme sporet — ellers står «løst av Kari» '
                         'ved siden av et merke som sier at den ikke er løst')
        self.assertIsNone(i.lost_at)

    def test_forfatteren_retter_og_sletter_sitt_eget(self):
        c = _klient(self.skriver)
        self._meld_inn(c)
        pk = Innspill.objects.get().pk

        svar = c.put(f'/backlog/api/innspill/{pk}/',
                     data=json.dumps({'tittel': 'Rettet'}),
                     content_type='application/json')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(Innspill.objects.get().tittel, 'Rettet')

        self.assertEqual(c.delete(f'/backlog/api/innspill/{pk}/').status_code, 200)
        self.assertEqual(Innspill.objects.count(), 0)

    def test_en_annen_skriver_kan_ikke_rette(self):
        self._meld_inn(_klient(self.skriver))
        pk = Innspill.objects.get().pk
        annen = _gi(_bruker('annen'), 'skriv_full')
        svar = _klient(annen).put(f'/backlog/api/innspill/{pk}/',
                                  data=json.dumps({'tittel': 'Kapret'}),
                                  content_type='application/json')
        self.assertEqual(svar.status_code, 403)
        self.assertEqual(Innspill.objects.get().tittel, 'Noe er galt')

    def test_etter_fristen_er_det_403_og_ikke_404(self):
        """Raden finnes, og brukeren ser den i lista. 404 ville sagt at den
        var borte."""
        c = _klient(self.skriver)
        self._meld_inn(c)
        i = Innspill.objects.get()
        Innspill.objects.filter(pk=i.pk).update(
            opprettet_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(c.delete(f'/backlog/api/innspill/{i.pk}/').status_code, 403)
        self.assertEqual(Innspill.objects.count(), 1)

    def test_kan_endres_regnes_av_serveren_og_foelger_med_raden(self):
        """Klienten skal ikke regne fristen selv — en klokke som står feil
        ville gitt en knapp som fører til 403."""
        c = _klient(self.skriver)
        self._meld_inn(c)
        rad = json.loads(c.get('/backlog/api/innspill/').content)['data'][0]
        self.assertTrue(rad['kan_endres'])

        annen = _gi(_bruker('annen'), 'skriv_full')
        rad = json.loads(
            _klient(annen).get('/backlog/api/innspill/').content)['data'][0]
        self.assertFalse(rad['kan_endres'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FilterTests(TestCase):

    def setUp(self):
        self.bruker = _gi(_bruker('leser'), 'les')
        self.c = _klient(self.bruker)
        self.bug = _type('Bug')
        self.onske = _type('Ønske')
        Innspill.objects.create(type=self.bug, tittel='Bug, uløst',
                                modul_slug='vaktliste')
        Innspill.objects.create(type=self.onske, tittel='Ønske, uløst')
        Innspill.objects.create(type=self.bug, tittel='Bug, løst', lost=True)

    def _titler(self, sporring=''):
        svar = self.c.get('/backlog/api/innspill/' + sporring)
        self.assertEqual(svar.status_code, 200)
        return {r['tittel'] for r in json.loads(svar.content)['data']}

    def test_uten_filter_kommer_alt(self):
        self.assertEqual(len(self._titler()), 3)

    def test_filter_paa_type(self):
        self.assertEqual(self._titler(f'?type={self.bug.pk}'),
                         {'Bug, uløst', 'Bug, løst'})

    def test_filter_paa_lost(self):
        self.assertEqual(self._titler('?lost=0'), {'Bug, uløst', 'Ønske, uløst'})
        self.assertEqual(self._titler('?lost=1'), {'Bug, løst'})

    def test_filter_paa_modul(self):
        self.assertEqual(self._titler('?modul=vaktliste'), {'Bug, uløst'})

    def test_filtrene_kombineres(self):
        self.assertEqual(self._titler(f'?type={self.bug.pk}&lost=0'), {'Bug, uløst'})

    def test_ugyldig_verdi_gir_400_og_ikke_hele_lista(self):
        """**Et filter som stille viser feil mengde er verre enn ingen
        filter.** `?lost=kanskje` ville ellers vist alt, og den som filtrerte
        ville lest det som at det ikke finnes noen uløste."""
        for sporring in ('?lost=kanskje', '?type=tull', '?modul=finnesikke'):
            with self.subTest(sporring=sporring):
                self.assertEqual(
                    self.c.get('/backlog/api/innspill/' + sporring).status_code, 400)

    def test_ukjent_filternavn_ignoreres(self):
        """En lenke fra en gammel fane skal vise lista, ikke en feilmelding."""
        self.assertEqual(len(self._titler('?sortering=noe')), 3)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TypeneAdministreresTests(TestCase):
    """Backloginnstillinger — typene er admin-styrt (André, 17. sep. 2026:
    «Kan ikke admin få legge til flere typer?»)."""

    def setUp(self):
        self.leser = _gi(_bruker('leser'), 'les')
        self.skriver = _gi(_bruker('skriver'), 'skriv_full')
        self.leder = _gi(_bruker('leder'), 'skriv_leder')
        self.sjef = _bruker('sjef', role='admin')

    def test_migrasjonen_seeder_de_to_standardtypene(self):
        """Seedingen er en migrasjon, ikke noe viewet lager ved første besøk —
        en tom base skal ha noe å velge mellom fra første innlogging."""
        self.assertEqual(
            list(Innspilltype.objects.order_by('rekkefolge')
                 .values_list('navn', flat=True)),
            ['Bug', 'Ønske'])

    def test_les_ser_typene_men_lager_ingen(self):
        c = _klient(self.leser)
        self.assertEqual(c.get('/backlog/api/typer/').status_code, 200)
        svar = c.post('/backlog/api/typer/', data=json.dumps({'navn': 'Spørsmål'}),
                      content_type='application/json')
        self.assertEqual(svar.status_code, 403)
        self.assertEqual(Innspilltype.objects.count(), 2)

    def test_skriv_full_lager_heller_ingen(self):
        """Å sette opp verdimengden er `skriv_leder`, som i oppdragsmodulen —
        den som melder inn endrer ikke hva *alle* får velge mellom."""
        svar = _klient(self.skriver).post(
            '/backlog/api/typer/', data=json.dumps({'navn': 'Spørsmål'}),
            content_type='application/json')
        self.assertEqual(svar.status_code, 403)

    def test_skriv_leder_legger_til_en_type(self):
        svar = _klient(self.leder).post(
            '/backlog/api/typer/', data=json.dumps({'navn': 'Spørsmål'}),
            content_type='application/json')
        self.assertEqual(svar.status_code, 201)
        ny = Innspilltype.objects.get(navn='Spørsmål')
        self.assertTrue(ny.er_aktiv)
        self.assertGreater(ny.rekkefolge, _type('Ønske').rekkefolge,
                           'en ny type havner sist')

    def test_duplikat_navn_avvises_uansett_store_bokstaver(self):
        """«Bug» og «bug» er samme type for et menneske, og to rader som ser
        like ut i et nedtrekk er verre enn en feilmelding."""
        svar = _klient(self.leder).post(
            '/backlog/api/typer/', data=json.dumps({'navn': 'bug'}),
            content_type='application/json')
        self.assertEqual(svar.status_code, 400)
        self.assertEqual(Innspilltype.objects.count(), 2)

    def test_en_deaktivert_type_kan_ikke_velges_paa_nytt_innspill(self):
        bug = _type()
        bug.er_aktiv = False
        bug.save()
        svar = _klient(self.skriver).post(
            '/backlog/api/innspill/',
            data=json.dumps({'type': bug.pk, 'tittel': 'Noe'}),
            content_type='application/json')
        self.assertEqual(svar.status_code, 400)
        self.assertEqual(Innspill.objects.count(), 0)

    def test_en_deaktivert_type_blir_staaende_paa_dem_som_har_den(self):
        """Det er hele forskjellen på å deaktivere og å slette."""
        bug = _type()
        Innspill.objects.create(type=bug, tittel='Gammelt innspill')
        bug.er_aktiv = False
        bug.save()
        rader = json.loads(
            _klient(self.leser).get('/backlog/api/innspill/').content)['data']
        self.assertEqual(rader[0]['type_navn'], 'Bug')

    def test_en_type_i_bruk_kan_ikke_slettes_og_svaret_sier_veien_ut(self):
        """**`PROTECT` → 409 med rådet.** «Kan ikke slettes» alene etterlater
        brukeren uten en vei videre, og da er neste trekk å slette innspillene
        i stedet — altså å miste det sperren fantes for å verne."""
        bug = _type()
        Innspill.objects.create(type=bug, tittel='Noe')
        svar = _klient(self.sjef).delete(
            f'/backlog/api/typer/{bug.pk}/', data=json.dumps({'confirm': True}),
            content_type='application/json')
        self.assertEqual(svar.status_code, 409)
        self.assertIn('Deaktiver', json.loads(svar.content)['message'])
        self.assertTrue(Innspilltype.objects.filter(pk=bug.pk).exists())

    def test_sletting_krever_global_admin_og_bekreftelse(self):
        """To sperrer som stopper hver sin ting: nivået stopper den som ikke
        skal slette, `confirm` stopper et kall som treffer URL-en uten å mene
        det."""
        ubrukt = Innspilltype.objects.create(navn='Ubrukt')

        self.assertEqual(_klient(self.leder).delete(
            f'/backlog/api/typer/{ubrukt.pk}/',
            data=json.dumps({'confirm': True}),
            content_type='application/json').status_code, 403)

        self.assertEqual(_klient(self.sjef).delete(
            f'/backlog/api/typer/{ubrukt.pk}/').status_code, 400)

        self.assertTrue(Innspilltype.objects.filter(pk=ubrukt.pk).exists())

        self.assertEqual(_klient(self.sjef).delete(
            f'/backlog/api/typer/{ubrukt.pk}/',
            data=json.dumps({'confirm': True}),
            content_type='application/json').status_code, 200)
        self.assertFalse(Innspilltype.objects.filter(pk=ubrukt.pk).exists())

    def test_navnet_kan_endres(self):
        bug = _type()
        svar = _klient(self.leder).put(
            f'/backlog/api/typer/{bug.pk}/', data=json.dumps({'navn': 'Feil'}),
            content_type='application/json')
        self.assertEqual(svar.status_code, 200)
        bug.refresh_from_db()
        self.assertEqual(bug.navn, 'Feil')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VarselVedNyttInnspillTests(TestCase):
    """§ André 17. sep. 2026: «Varsel til admin er fint.»

    **Mottakerne er de som kan løse, ikke alle som kan lese.** En bjelle som
    pling-er for folk som ikke kan gjøre noe, er en bjelle man slår av.
    """

    def setUp(self):
        from core.models import Notification
        self.Notification = Notification
        self.skriver = _gi(_bruker('skriver'), 'skriv_full')
        self.leder = _gi(_bruker('leder'), 'skriv_leder')
        self.leser = _gi(_bruker('leser'), 'les')
        self.sjef = _bruker('sjef', role='admin')

    def _meld_inn(self, klient, tittel='Noe er galt'):
        return klient.post(
            '/backlog/api/innspill/',
            data=json.dumps({'type': _type().pk, 'tittel': tittel}),
            content_type='application/json')

    def _varslede(self):
        return set(self.Notification.objects
                   .filter(module_slug='backlog')
                   .values_list('user__username', flat=True))

    def test_lederen_og_admin_varsles(self):
        self._meld_inn(_klient(self.skriver))
        self.assertEqual(self._varslede(), {'leder', 'sjef'})

    def test_den_som_melder_inn_varsles_ikke_om_sitt_eget(self):
        """Et varsel om noe man nettopp skrev er den korteste veien til å
        slutte å lese varsler."""
        self._meld_inn(_klient(self.leder))
        self.assertNotIn('leder', self._varslede())

    def test_den_som_bare_leser_varsles_ikke(self):
        self._meld_inn(_klient(self.skriver))
        self.assertNotIn('leser', self._varslede())

    def test_varselet_baerer_tittelen(self):
        """Det er tittelen som avgjør om man går og ser nå eller i morgen."""
        self._meld_inn(_klient(self.skriver), tittel='Nedtrekket lukker seg')
        varsel = self.Notification.objects.filter(user=self.leder).first()
        self.assertIsNotNone(varsel)
        self.assertIn('Nedtrekket lukker seg', varsel.message)
        self.assertIn('skriver', varsel.message)
        self.assertEqual(varsel.url, '/backlog/')

    def test_to_ulike_innspill_gir_to_varsler(self):
        """`notify()` dedupliserer på meldingen, ikke på typen — ellers ville
        innspill nummer to i samme døgn forsvunnet."""
        self._meld_inn(_klient(self.skriver), tittel='Første')
        self._meld_inn(_klient(self.skriver), tittel='Andre')
        self.assertEqual(
            self.Notification.objects.filter(user=self.leder).count(), 2)

    def test_et_varsel_som_feiler_stopper_ikke_innmeldingen(self):
        """**Varselet er en sideeffekt, ikke en del av innmeldingen.**"""
        from unittest.mock import patch
        with patch('backlog.varsler.notify', side_effect=RuntimeError('nede')):
            svar = self._meld_inn(_klient(self.skriver))
        self.assertEqual(svar.status_code, 201)
        self.assertEqual(Innspill.objects.count(), 1)
