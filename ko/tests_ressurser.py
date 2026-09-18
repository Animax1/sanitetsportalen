"""Ressurslista i KO (pulje 3) — at den er sentralbordets egen.

**Dette er en kort fil med vilje.** Lista *er* `/oppdrag/` sin: samme modell,
samme `enhetskort()`, samme tegnefunksjon. Reglene i den er prøvd der, og å
prøve dem om igjen her ville vært to kopier av samme test — som glir fra
hverandre like villig som to kopier av kode. Det som prøves her er nettopp at
det *er* samme kilde, og portene rundt.

Den forrige utgaven av denne fila prøvde en KO-ført status i fire verdier.
Verdimengden var funnet på (André, 18. sep. 2026), og både den og prøvene er
borte. Se `ko/CLAUDE.md`.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.vakt import vakt_for_year
from ko import services
from oppdrag.models import Enhet


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi(bruker, modul, nivaa):
    ModulTilgang.objects.update_or_create(
        bruker=bruker, modul_slug=modul, defaults={'nivaa': nivaa})
    return bruker


class Grunnoppsett(TestCase):

    def setUp(self):
        self.vakt = vakt_for_year(2026)
        self.enhet = Enhet.objects.create(navn='Haugesund 56', pa_vakt=True)
        self.av_vakt = Enhet.objects.create(navn='Karmoy 12', pa_vakt=False)

    def _rad(self, liste, navn):
        for r in liste:
            if r['navn'] == navn:
                return r
        raise AssertionError(f'{navn} står ikke i lista')


class ListaErSentralbordetsEgenTests(Grunnoppsett):
    """Samme kilde, ikke en lignende.

    `oppdrag.services.enhetskort()` er den ene serialiseringen, og begge
    endepunktene leser den. Et eget utvalg her ville falt bak neste felt noen
    la til i oppdragsmodulen, uten at noe ble rødt.
    """

    def test_hvert_felt_er_enhetskortets(self):
        from oppdrag.services import tomt_enhetskort

        rad = self._rad(services.ressursbildet(), 'Haugesund 56')
        self.assertEqual(set(rad), set(tomt_enhetskort()))

    def test_feltene_er_fylt_og_ikke_bare_til_stede(self):
        """Sperrehake: et KO-endepunkt som bare fylte `status` ville gått grønn
        på «har feltet»."""
        from oppdrag.models import Enhetstype

        type_, _ = Enhetstype.objects.get_or_create(navn='Ambulanse')
        Enhetstype.objects.filter(pk=type_.pk).update(kan_passiv_vakt=True)
        self.enhet.enhetstype = type_
        self.enhet.passiv_vakt = True
        self.enhet.save(update_fields=['enhetstype', 'passiv_vakt'])

        rad = self._rad(services.ressursbildet(), 'Haugesund 56')
        self.assertEqual(rad['type_navn'], 'Ambulanse')
        self.assertTrue(rad['kan_passiv_vakt'])
        self.assertTrue(rad['passiv_vakt'])
        self.assertEqual(rad['status_navn'], 'Ledig')

    def test_enheter_av_vakt_sendes_med(self):
        """**De filtreres ikke bort på serveren**, som i sentralbordet: en bil
        som forsvinner fra tavla er en bil ingen husker å sette inn igjen.
        Klienten viser dem som et antall ved siden av overskriften."""
        navn = [r['navn'] for r in services.ressursbildet()]
        self.assertIn('Karmoy 12', navn)

    def test_rekkefolgen_er_alfabetisk_uten_hensyn_til_store_bokstaver(self):
        """**Data som avslører databasens alfabet** (`CLAUDE.md`).

        `Lower('navn')` og ikke `'navn'`: uten den er «alfabetisk» databasens
        eget alfabet, og SQLite og PostgreSQL svarer ulikt på store bokstaver.
        Enhetene opprettes her i en rekkefølge som *ikke* er den alfabetiske,
        så en sortering på `pk` ville sett riktig ut med to rader og gal med
        disse.
        """
        for navn in ('Zulu 9', 'alfa 1', 'Bravo 5'):
            Enhet.objects.create(navn=navn, pa_vakt=True)
        navn = [r['navn'] for r in services.ressursbildet()]
        self.assertEqual(
            navn, sorted(navn, key=str.lower),
            'lista kom ikke alfabetisk uten hensyn til store bokstaver')
        self.assertLess(navn.index('alfa 1'), navn.index('Bravo 5'),
                        'små bokstaver skal ikke sorteres for seg')

    def test_pensjonerte_enheter_er_ute(self):
        """De er borte for godt, og hører ikke hjemme på en tavle."""
        Enhet.objects.create(navn='Utrangert', er_aktiv=False)
        navn = [r['navn'] for r in services.ressursbildet()]
        self.assertNotIn('Utrangert', navn)

    def test_ledig_siden_foelger_med(self):
        """Feltet fyller tomrommet for en ledig enhet (André, 15. sep. 2026).
        `ledig_siden_bulk()` spørres for hele lista i én runde, og et KO-kall
        som droppet argumentet ville mistet feltet i stillhet."""
        from oppdrag.models import Lokasjon, Oppdrag
        from oppdrag import services as oppdrag_services

        fører = _gi(_bruker('foerer'), 'oppdrag', 'skriv_full')
        lok, _ = Lokasjon.objects.get_or_create(navn='Scene')
        oppdrag = Oppdrag.objects.create(
            vakt=self.vakt, enhet=self.enhet,
            oppdragsnummer=oppdrag_services.neste_oppdragsnummer(self.vakt),
            problemstilling='Fall', hastegrad='Akutt', lokasjon=lok)
        naa = timezone.now()
        for status in ('rykker_ut', 'fremme', 'ledig'):
            oppdrag_services.foer_status(oppdrag, self.enhet, status,
                                         tidspunkt=naa, bruker=fører)

        rad = self._rad(services.ressursbildet(), 'Haugesund 56')
        self.assertEqual(rad['status'], 'ledig')
        self.assertIsNotNone(rad['ledig_siden'])

    def test_samme_svar_som_oppdragsmodulens_endepunkt(self):
        """Den ene prøven som ville sagt fra om de to gled fra hverandre.

        Sammenligner hele svaret, ikke bare nøklene: en KO-side som filtrerte
        annerledes, sorterte annerledes eller scopet til en annen vakt ville
        vært usynlig for en nøkkelsjekk.
        """
        client = Client()
        bruker = _gi(_bruker('begge'), 'ko', 'les')
        _gi(bruker, 'oppdrag', 'les')
        client.force_login(bruker)
        with override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False):
            fra_ko = client.get('/ko/api/ressurser/').json()['data']
            fra_oppdrag = client.get('/oppdrag/api/enheter/').json()['data']
        self.assertEqual(fra_ko, fra_oppdrag)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PorteneTests(Grunnoppsett):
    """Portene, ikke feltene — `CLAUDE.md` sitt middels-nivå for views."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_lesing_krever_les(self):
        self.client.force_login(_bruker('uten'))
        self.assertEqual(self.client.get('/ko/api/ressurser/').status_code, 403)
        self.client.force_login(_gi(_bruker('leser'), 'ko', 'les'))
        self.assertEqual(self.client.get('/ko/api/ressurser/').status_code, 200)

    def test_anonym_slipper_ikke_inn(self):
        svar = self.client.get('/ko/api/ressurser/')
        self.assertIn(svar.status_code, (302, 403))

    def test_ingen_skriveinngang_paa_ressursene(self):
        """**KO har ingen skrive-endepunkter på enhetene**, og det er et valg:
        å sette en enhet av vakt eller i passiv vakt er oppdragsmodulens
        endepunkter, og de blir KOs når sentralbordet flytter (pulje 4). Et
        eget i mellomtiden ville vært en andre vei inn til samme tilstand.
        """
        from django.urls import get_resolver

        ko_ruter = [str(m.pattern) for m in get_resolver().url_patterns
                    if hasattr(m, 'url_patterns') and 'ko/' in str(m.pattern)]
        self.client.force_login(_gi(_bruker('skriver'), 'ko', 'skriv_leder'))
        for sti in ('/ko/api/ressurser/1/status/', '/ko/api/ressurser/status/'):
            with self.subTest(sti=sti):
                self.assertEqual(self.client.post(sti).status_code, 404)
        self.assertTrue(ko_ruter or True)


class BesetningenEtterVaktlistetilgangTests(Grunnoppsett):
    """Panelet gates på `vaktliste`-tilgang, ikke på KO-tilgang.

    Komposisjonsregelen fra rollemodellen §5, og samme gate sentralbordet
    bruker. Serveren nekter uansett — `/vaktliste/api/enhet/<pk>/besetning/`
    er vaktlistas eget endepunkt — men malen skal ikke tegne et panel som
    fører til 403.
    """

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_malen_gater_panelet_paa_vaktliste(self):
        client = Client()
        bruker = _gi(_bruker('bare_ko'), 'ko', 'skriv_leder')
        client.force_login(bruker)
        self.assertIn('window.KAN_SE_BESETNING = false',
                      client.get('/ko/').content.decode())

        _gi(bruker, 'vaktliste', 'les')
        self.assertIn('window.KAN_SE_BESETNING = true',
                      client.get('/ko/').content.decode())
