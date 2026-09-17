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
            type=Innspilltype.BUG, tittel='Noe er galt',
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
        kropp = {'type': 'bug', 'tittel': 'Noe er galt'}
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
        Innspill.objects.create(type=Innspilltype.BUG, tittel='Bug, uløst',
                                modul_slug='vaktliste')
        Innspill.objects.create(type=Innspilltype.ONSKE, tittel='Ønske, uløst')
        Innspill.objects.create(type=Innspilltype.BUG, tittel='Bug, løst', lost=True)

    def _titler(self, sporring=''):
        svar = self.c.get('/backlog/api/innspill/' + sporring)
        self.assertEqual(svar.status_code, 200)
        return {r['tittel'] for r in json.loads(svar.content)['data']}

    def test_uten_filter_kommer_alt(self):
        self.assertEqual(len(self._titler()), 3)

    def test_filter_paa_type(self):
        self.assertEqual(self._titler('?type=bug'), {'Bug, uløst', 'Bug, løst'})

    def test_filter_paa_lost(self):
        self.assertEqual(self._titler('?lost=0'), {'Bug, uløst', 'Ønske, uløst'})
        self.assertEqual(self._titler('?lost=1'), {'Bug, løst'})

    def test_filter_paa_modul(self):
        self.assertEqual(self._titler('?modul=vaktliste'), {'Bug, uløst'})

    def test_filtrene_kombineres(self):
        self.assertEqual(self._titler('?type=bug&lost=0'), {'Bug, uløst'})

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
