"""Tester for registersiden — mannskapet og de tre verdimengdene.

**Hva denne fila egentlig vokter.** Fase 1 og 2 leverte registre som bare
kunne fylles fra Django-admin, og den flaten er av i produksjon (S1). Modulen
var altså ubrukelig i prod uten at én eneste test var rød: alle testene laget
radene sine med ORM-en. Testene her går derfor gjennom HTTP, slik en bruker
gjør — det er den eneste veien som beviser at flaten finnes.

`SjekkAtIngenPekerPaaDjangoAdminTests` er vakten mot at det skjer igjen: en
mal som ber brukeren gå til `/django-admin/` sender henne til en dør som ikke
finnes i prod.
"""
import json
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings

from patients.js_test_utils import (
    PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available, run_node)
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang

from . import services
from .models import (Kompetanse, Korps, Mannskap, Ressursgruppe,
                     Ressursrolle, Vaktpost)
from .test_helpers import (AMBULANSE, LAG, SAMLEPLASS, gruppe,
                          lag_ressurs, lag_rolle)


def _bruker(navn, nivaa=None, *, admin=False):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role='admin' if admin else 'bruker',
        must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='vaktliste', nivaa=nivaa)
    return b


def _klient(bruker):
    c = Client()
    c.force_login(bruker)
    return c


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RegisterFlateFinnesTests(TestCase):
    """Registrene skal kunne fylles **gjennom portalen**, ikke bare med ORM.

    Dette er hele poenget med fila: bygg et korps, en kompetanse og et
    mannskap uten å røre modellene direkte, og bemann så en vakt med dem.
    """

    def setUp(self):
        self.c = _klient(_bruker('adm', admin=True))

    def _post(self, sti, **kropp):
        return self.c.post(sti, data=kropp, content_type='application/json')

    def test_hele_veien_fra_tom_base_til_bemannet_vakt(self):
        korps = self._post('/vaktliste/api/korps/',
                           navn='Haugesund', kortnavn='HGSD')
        self.assertEqual(korps.status_code, 201)
        komp = self._post('/vaktliste/api/kompetanser/', navn='Sykepleier')
        self.assertEqual(komp.status_code, 201)
        # Gruppa finnes fra migrasjonen; rollen hører til den.
        lag = gruppe(LAG)
        rolle = self._post('/vaktliste/api/roller/', navn='Lagleder',
                           gruppe_id=lag.pk)
        self.assertEqual(rolle.status_code, 201)

        person = self._post(
            '/vaktliste/api/mannskap/', navn='Kari Nordmann',
            korps_id=korps.json()['data']['id'],
            kompetanse_ider=[komp.json()['data']['id']],
            telefon='90000000')
        self.assertEqual(person.status_code, 201)
        self.assertEqual(
            [k['navn'] for k in person.json()['data']['kompetanser']],
            ['Sykepleier'])

        # Og personen er faktisk brukbar der hun skal brukes.
        vl = self._post('/vaktliste/api/vaktlister/', navn='Vakta')
        ressurs = self._post(
            f'/vaktliste/api/vaktlister/{vl.json()["data"]["id"]}/ressurser/',
            navn='Lag 1', gruppe_id=lag.pk)
        na = timezone.now()
        satt = self._post(
            f'/vaktliste/api/ressurser/{ressurs.json()["data"]["id"]}/vaktposter/',
            mannskap_id=person.json()['data']['id'],
            rolle_id=rolle.json()['data']['id'],
            fra_tid=na.isoformat(),
            til_tid=(na + timedelta(hours=8)).isoformat())
        self.assertEqual(satt.status_code, 201)
        self.assertEqual(satt.json()['data']['navn'], 'Kari Nordmann')

    def test_registersiden_er_lagt_ned(self):
        """Flata flyttet inn i planleggingssiden 30. aug. 2026. Blir ruta
        stående, svarer den med en mal som ikke finnes."""
        self.assertEqual(self.c.get('/vaktliste/registre/').status_code, 404)

    def test_mannskapsfanen_er_veien_inn(self):
        """Et register uten vei inn er et register som ikke finnes.

        Veien er nå fanen på planleggingssiden, ikke en lenke ut av den:
        `visFane('mannskap')` og skjemaet den åpner må stå i malen.
        """
        res = self.c.get('/vaktliste/')
        self.assertContains(res, 'js/vaktliste')
        self.assertNotContains(res, 'patients-utils')
        self.assertContains(res, 'id="personModal"')
        self.assertContains(res, 'id="vl-sok"')

    def test_korps_og_kompetanser_ligger_i_innstillinger(self):
        """De røres sjelden og er portalens oppsett, ikke denne vaktas."""
        res = self.c.get('/vaktliste/')
        self.assertContains(res, 'data-action="apneVerdier" data-arg="korps"')
        self.assertContains(
            res, 'data-action="apneVerdier" data-arg="kompetanser"')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VerdimengdeTests(TestCase):
    """De som deler fabrikk. Testene kjører mot begge der regelen deles.

    **Rollene deler fabrikk, men ikke kontrakt** (30. aug. 2026): de henger
    under en `Ressursgruppe` og krever `skriv_leder`. De kjøres derfor ikke i
    løkka her — en delt løkke som må gjøre unntak for ett av leddene tester
    ikke lenger at leddene er like. Se `RollerErGruppasTests`.
    """

    STIER = ('korps', 'kompetanser')

    def setUp(self):
        self.c = _klient(_bruker('adm', admin=True))

    def _post(self, sti, **kropp):
        return self.c.post(f'/vaktliste/api/{sti}/', data=kropp,
                           content_type='application/json')

    def test_opprett_og_hent_paa_alle_tre(self):
        for sti in self.STIER:
            with self.subTest(sti=sti):
                self.assertEqual(self._post(sti, navn='Ting').status_code, 201)
                data = self.c.get(f'/vaktliste/api/{sti}/').json()['data']
                self.assertEqual([r['navn'] for r in data], ['Ting'])

    def test_tomt_navn_avvises_paa_alle_tre(self):
        for sti in self.STIER:
            with self.subTest(sti=sti):
                self.assertEqual(self._post(sti, navn='   ').status_code, 400)

    def test_duplikat_gir_lesbar_400_paa_alle_tre(self):
        for sti in self.STIER:
            with self.subTest(sti=sti):
                self._post(sti, navn='Dublett')
                res = self._post(sti, navn='Dublett')
                self.assertEqual(res.status_code, 400)
                self.assertIn('Dublett', res.json()['message'])

    def test_korps_har_kortnavn_de_andre_ikke(self):
        res = self._post('korps', navn='Haugesund', kortnavn='HGSD')
        self.assertEqual(res.json()['data']['kortnavn'], 'HGSD')
        self.assertNotIn(
            'kortnavn', self._post('kompetanser', navn='X').json()['data'])

    def test_inaktive_er_med_i_lista(self):
        """De skal kunne aktiveres igjen. En rad som forsvinner helt ser ut
        som en sletting som ikke skjedde."""
        pk = self._post('kompetanser', navn='Utgått').json()['data']['id']
        self.c.put(f'/vaktliste/api/kompetanser/{pk}/', data={'er_aktiv': False},
                   content_type='application/json')
        data = self.c.get('/vaktliste/api/kompetanser/').json()['data']
        self.assertEqual([(r['navn'], r['er_aktiv']) for r in data],
                         [('Utgått', False)])

    def test_lista_er_alfabetisk_uansett_hva_som_ble_lagt_inn_forst(self):
        self._post('korps', navn='Karmøy')
        self._post('korps', navn='Bokn')
        data = self.c.get('/vaktliste/api/korps/').json()['data']
        self.assertEqual([r['navn'] for r in data], ['Bokn', 'Karmøy'])

    def test_api_et_tilbyr_ikke_rekkefolge(self):
        """Feltet er borte fra verdimengdene, og skal ikke lekke tilbake
        gjennom svaret — et felt klienten ser, er et felt noen vil sette."""
        rad = self._post('korps', navn='Haugesund').json()['data']
        self.assertNotIn('rekkefolge', rad)

    # ── Sletting ─────────────────────────────────────────────────────────
    def test_ubrukt_verdi_kan_slettes(self):
        pk = self._post('kompetanser', navn='Feilskrevet').json()['data']['id']
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/kompetanser/{pk}/').status_code, 200)
        self.assertFalse(Kompetanse.objects.exists())


    def test_korps_i_bruk_kan_ikke_slettes(self):
        korps = Korps.objects.create(navn='Haugesund')
        Mannskap.objects.create(navn='Kari', korps=korps)
        res = self.c.delete(f'/vaktliste/api/korps/{korps.pk}/')
        self.assertEqual(res.status_code, 409)
        self.assertIn('inaktiv', res.json()['message'])
        self.assertTrue(Korps.objects.filter(pk=korps.pk).exists())

    def test_korps_reservert_paa_en_ressurs_teller_som_i_bruk(self):
        """Reservasjonen er den andre veien inn i korpset.

        Sletting stoppes uansett — `Ressurs.korps` er PROTECT, så fallbacken
        fanger den. Det som *bare* telle-sjekken fanger, er tallet i lista:
        teller vi bare mannskap, står et korps som eier et lag oppført som
        «ubrukt», og da trykker man slett i god tro og får en feilmelding
        framfor en advarsel.
        """
        korps = Korps.objects.create(navn='Karmøy')
        vl = services.opprett_planlagt_vakt('Vakta')
        lag_ressurs(vaktliste=vl, navn='Lag K', korps=korps)

        rad = [k for k in self.c.get('/vaktliste/api/korps/').json()['data']
               if k['navn'] == 'Karmøy'][0]
        self.assertEqual(rad['i_bruk'], 1, 'reservasjonen skal telle')
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/korps/{korps.pk}/').status_code, 409)

    def test_kompetanse_i_bruk_kan_ikke_slettes(self):
        """M2M-en ville ikke protestert — den ville stilltiende strippet
        kompetansen fra alle som har den. Derfor sjekkes den eksplisitt."""
        korps = Korps.objects.create(navn='Haugesund')
        komp = Kompetanse.objects.create(navn='Sykepleier')
        person = Mannskap.objects.create(navn='Kari', korps=korps)
        person.kompetanser.add(komp)

        res = self.c.delete(f'/vaktliste/api/kompetanser/{komp.pk}/')
        self.assertEqual(res.status_code, 409)
        self.assertTrue(Kompetanse.objects.filter(pk=komp.pk).exists())
        self.assertEqual(person.kompetanser.count(), 1)

    def test_rolle_i_bruk_kan_ikke_slettes(self):
        korps = Korps.objects.create(navn='Haugesund')
        rolle = lag_rolle('Lagleder')
        person = Mannskap.objects.create(navn='Kari', korps=korps)
        vl = services.opprett_planlagt_vakt('Vakta')
        r = lag_ressurs(vaktliste=vl, navn='Lag 1')
        na = timezone.now()
        Vaktpost.objects.create(ressurs=r, mannskap=person, rolle=rolle,
                                fra_tid=na, til_tid=na + timedelta(hours=8))
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/roller/{rolle.pk}/').status_code, 409)

    def test_i_bruk_tallet_staar_i_lista(self):
        """Tallet vises i grensesnittet: en verdimengde man kan slette uten å
        vite hva som henger i den, sletter man for lett."""
        korps = Korps.objects.create(navn='Haugesund')
        Mannskap.objects.create(navn='Kari', korps=korps)
        Mannskap.objects.create(navn='Ola', korps=korps)
        data = self.c.get('/vaktliste/api/korps/').json()['data']
        self.assertEqual(data[0]['i_bruk'], 2)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RollerErGruppasTests(TestCase):
    """Rollen hører til en `Ressursgruppe`, og opprettes av `skriv_leder`.

    Begge deler er nye 30. aug. 2026, og begge er svar på noe André så da han
    brukte modulen: «Sjåfør» hører hjemme på ambulansene, ikke på samleplassen,
    og den som bare skal bemanne skal ikke kunne finne på nye roller.
    """

    def setUp(self):
        self.leder = _klient(_bruker('leder', 'skriv_leder'))
        self.bemanner = _klient(_bruker('bemanner', 'skriv_full'))
        self.amb = gruppe(AMBULANSE)
        self.sam = gruppe(SAMLEPLASS)

    def _post(self, klient, **kropp):
        return klient.post('/vaktliste/api/roller/', data=kropp,
                           content_type='application/json')

    def test_rolle_uten_gruppe_avvises(self):
        """En rolle uten gruppe ville aldri dukket opp i noe nedtrekk — altså
        en rad man lager og aldri finner igjen."""
        res = self._post(self.leder, navn='Sjåfør')
        self.assertEqual(res.status_code, 400)
        self.assertIn('ressursgruppe', res.json()['message'])

    def test_rolle_med_ukjent_gruppe_avvises(self):
        res = self._post(self.leder, navn='Sjåfør', gruppe_id=99999)
        self.assertEqual(res.status_code, 400)

    def test_samme_navn_i_to_grupper_er_to_roller(self):
        """Unikheten er per gruppe, ikke global: «Lagleder» på ambulansen og
        «Lagleder» på samleplassen er ikke samme rad."""
        self.assertEqual(
            self._post(self.leder, navn='Lagleder', gruppe_id=self.amb.pk
                       ).status_code, 201)
        self.assertEqual(
            self._post(self.leder, navn='Lagleder', gruppe_id=self.sam.pk
                       ).status_code, 201)
        self.assertEqual(Ressursrolle.objects.filter(navn='Lagleder').count(), 2)

    def test_duplikat_i_samme_gruppe_avvises(self):
        self._post(self.leder, navn='Sjåfør', gruppe_id=self.amb.pk)
        res = self._post(self.leder, navn='Sjåfør', gruppe_id=self.amb.pk)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Sjåfør', res.json()['message'])

    def test_svaret_baerer_gruppa(self):
        """Nedtrekket i ressurstabellen filtrerer på gruppa. Uten IDen i
        svaret måtte klienten gjette ut fra navnet."""
        rad = self._post(self.leder, navn='Sjåfør',
                         gruppe_id=self.amb.pk).json()['data']
        self.assertEqual(rad['gruppe_id'], self.amb.pk)
        self.assertEqual(rad['gruppe_navn'], AMBULANSE)

    def test_bemanneren_lager_ikke_roller(self):
        """`skriv_full` bemanner oppsettet uten å bestemme det."""
        res = self._post(self.bemanner, navn='Sjåfør', gruppe_id=self.amb.pk)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Ressursrolle.objects.filter(navn='Sjåfør').exists())

    def test_bemanneren_fjerner_ikke_roller(self):
        rolle = lag_rolle('Sjåfør', AMBULANSE)
        self.assertEqual(
            self.bemanner.delete(f'/vaktliste/api/roller/{rolle.pk}/').status_code,
            403)
        self.assertTrue(Ressursrolle.objects.filter(pk=rolle.pk).exists())

    def test_bemanneren_leser_rollene(self):
        """Hun må se dem — nedtrekket i raden er hennes."""
        lag_rolle('Sjåfør', AMBULANSE)
        res = self.bemanner.get('/vaktliste/api/roller/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([r['navn'] for r in res.json()['data']], ['Sjåfør'])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RessursgruppeApiTests(TestCase):
    """Gruppene: seedet av migrasjonen, administrert av `skriv_leder`."""

    def setUp(self):
        self.leder = _klient(_bruker('leder', 'skriv_leder'))
        self.bemanner = _klient(_bruker('bemanner', 'skriv_full'))

    def test_standardgruppene_finnes_uten_at_noen_lager_dem(self):
        """Migrasjon 0007 seeder de seks. Uten dem kan ingen opprette en
        ressurs i det hele tatt — en tom gruppetabell er en portal der
        vaktlista ikke kan settes opp."""
        navn = [g['navn'] for g in
                self.bemanner.get('/vaktliste/api/grupper/').json()['data']]
        self.assertEqual(
            navn, ['Samleplass', 'Mannskapsbil', 'Ambulanse', 'Lag', 'KO', 'Annet'],
            'seedet rekkefølge, ikke alfabetisk — den styrer fanene')

    def test_lederen_oppretter_en_gruppe(self):
        res = self.leder.post('/vaktliste/api/grupper/',
                              data={'navn': 'Førstehjelpstelt', 'ikon': 'tent'},
                              content_type='application/json')
        self.assertEqual(res.status_code, 201)
        rad = res.json()['data']
        self.assertEqual(rad['ikon'], 'tent')
        self.assertEqual(rad['i_bruk'], 0)

    def test_ny_gruppe_havner_sist(self):
        """Ingen skal måtte finne på et tall — samme grep som på ressursene."""
        self.leder.post('/vaktliste/api/grupper/', data={'navn': 'MC-patrulje'},
                        content_type='application/json')
        navn = [g['navn'] for g in
                self.leder.get('/vaktliste/api/grupper/').json()['data']]
        self.assertEqual(navn[-1], 'MC-patrulje')

    def test_bemanneren_oppretter_ikke_grupper(self):
        res = self.bemanner.post('/vaktliste/api/grupper/',
                                 data={'navn': 'Førstehjelpstelt'},
                                 content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_gruppe_i_bruk_kan_ikke_slettes(self):
        """PROTECT ville uansett stoppet det, men meldingen skal peke på
        veien ut: en gruppe i bruk deaktiveres, den fjernes ikke."""
        vl = services.opprett_planlagt_vakt('Vakta')
        lag_ressurs(vaktliste=vl, navn='Ambulanse 1', gruppe=gruppe(AMBULANSE))
        res = self.leder.delete(f'/vaktliste/api/grupper/{gruppe(AMBULANSE).pk}/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Deaktiver', res.json()['message'])

    def test_ubrukt_gruppe_kan_slettes(self):
        pk = self.leder.post('/vaktliste/api/grupper/', data={'navn': 'Feil'},
                             content_type='application/json').json()['data']['id']
        self.assertEqual(
            self.leder.delete(f'/vaktliste/api/grupper/{pk}/').status_code, 200)

    # ── Punkt 4 i pulje 3 (André, 16. sep. 2026) ─────────────────────────

    def _ny(self, navn='Førstehjelpstelt'):
        return self.leder.post('/vaktliste/api/grupper/', data={'navn': navn},
                               content_type='application/json').json()['data']['id']

    def _put(self, pk, kropp, klient=None):
        return (klient or self.leder).put(
            f'/vaktliste/api/grupper/{pk}/', data=json.dumps(kropp),
            content_type='application/json')

    def test_gruppa_kan_endres_navn_og_ikon(self):
        """**Serveren har støttet det hele tiden; det manglet en knapp**
        (16. sep. 2026). Punktet André meldte var «ressursgrupper skal kunne
        endres og slettes, også de seks som seedes» — og de seks har aldri
        vært vernet, så det som faktisk manglet var redigeringen."""
        pk = self._ny()
        res = self._put(pk, {'navn': 'Sanitetstelt', 'ikon': 'tent'})
        self.assertEqual(res.status_code, 200, res.content)
        rad = res.json()['data']
        self.assertEqual((rad['navn'], rad['ikon']), ('Sanitetstelt', 'tent'))

    def test_de_seks_seedede_kan_endres_som_alle_andre(self):
        """Ingen av dem er «fast» slik «Udefinert» er i oppdragsmodulen.
        Det er et bevisst skille: der sperrer `sett_status` på navnet, her
        bærer ingen kode et gruppenavn."""
        res = self._put(gruppe(AMBULANSE).pk, {'navn': 'Ambulanser'})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['navn'], 'Ambulanser')

    def test_gruppa_kan_deaktiveres_ogsaa_naar_den_er_i_bruk(self):
        """**Veien ut for en gruppe man ikke vil se mer** (André: «de som er
        i bruk på vaktlister nå må jo få bli»). Sletting er stengt, men
        `er_aktiv` skal kunne settes — den skjuler gruppa i nedtrekkene og
        beholder den der den brukes. Feltet og virkningen fantes fra 30. aug.
        2026; det var ingen vei til å sette det."""
        vl = services.opprett_planlagt_vakt('Vakta')
        lag_ressurs(vaktliste=vl, navn='Ambulanse 1', gruppe=gruppe(AMBULANSE))
        res = self._put(gruppe(AMBULANSE).pk, {'er_aktiv': False})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()['data']['er_aktiv'])
        self.assertEqual(
            self.leder.delete(f'/vaktliste/api/grupper/{gruppe(AMBULANSE).pk}/').status_code,
            400, 'og sletting er fortsatt stengt')

    def test_bemanneren_endrer_ikke_grupper(self):
        pk = self._ny()
        self.assertEqual(self._put(pk, {'navn': 'X'}, self.bemanner).status_code, 403)

    def test_rollene_foelger_med_i_slettingen_og_det_sies_hoeyt(self):
        """**`Ressursrolle.gruppe` er CASCADE, `Ressurs.gruppe` er PROTECT.**

        En gruppe uten ressurser lar seg altså slette — og tok rollene sine
        med seg uten et ord. «Lagleder» og «Sjåfør» er oppsett noen har
        skrevet inn, og de var borte for godt. Funnet 16. sep. 2026 ved å lese
        `on_delete` på begge sidene, ikke ved at noe feilet.
        """
        pk = self._ny()
        Ressursrolle.objects.create(gruppe_id=pk, navn='Teltleder')
        Ressursrolle.objects.create(gruppe_id=pk, navn='Assistent')

        res = self.leder.delete(f'/vaktliste/api/grupper/{pk}/')
        self.assertEqual(res.status_code, 409, res.content)
        self.assertIn('2 rolle', res.json()['message'])
        self.assertTrue(Ressursgruppe.objects.filter(pk=pk).exists(),
                        'ingenting slettet uten bekreftelse')

        res = self.leder.delete(f'/vaktliste/api/grupper/{pk}/',
                                data=json.dumps({'confirm': True}),
                                content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(Ressursgruppe.objects.filter(pk=pk).exists())
        self.assertFalse(Ressursrolle.objects.filter(gruppe_id=pk).exists())

    def test_en_gruppe_uten_roller_slettes_uten_bekreftelse(self):
        """Et ekstra klikk på en tom gruppe er en vane man slutter å lese,
        og da er bekreftelsen verdiløs den gangen den betyr noe."""
        pk = self._ny()
        self.assertEqual(
            self.leder.delete(f'/vaktliste/api/grupper/{pk}/').status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MannskapApiTests(TestCase):
    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.annet = Korps.objects.create(navn='Karmøy')
        self.komp = Kompetanse.objects.create(navn='Sykepleier')
        self.c = _klient(_bruker('adm', admin=True))

    def _opprett(self, **kropp):
        kropp.setdefault('navn', 'Kari')
        kropp.setdefault('korps_id', self.korps.pk)
        return self.c.post('/vaktliste/api/mannskap/', data=kropp,
                           content_type='application/json')

    def test_issi_lagres_som_tekst_og_kan_endres(self):
        """ISSI (12. sep. 2026): nødnettsterminalens nummer, etter telefon og
        e-post. Tekst, så ledende nuller overlever."""
        res = self._opprett(issi=' 0012345 ')
        self.assertEqual(res.status_code, 201, res.content)
        d = res.json()['data']
        self.assertEqual(d['issi'], '0012345')
        res = self.c.put(f'/vaktliste/api/mannskap/{d["id"]}/', data={'issi': ''},
                         content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['issi'], '')

    def test_person_uten_korps_avvises(self):
        """Uten korps finnes ingen badge — personen kan verken sorteres i lista
        eller redigeres av en korps-bruker fra fase 3."""
        for daarlig in (None, 9999, ''):
            with self.subTest(korps=daarlig):
                res = self._opprett(korps_id=daarlig)
                self.assertEqual(res.status_code, 400)
        self.assertFalse(Mannskap.objects.exists())

    def test_duplikat_i_samme_korps_forklares(self):
        self._opprett()
        res = self._opprett()
        self.assertEqual(res.status_code, 400)
        self.assertIn('Haugesund', res.json()['message'])

    def test_samme_navn_i_annet_korps_er_lov(self):
        self._opprett()
        self.assertEqual(self._opprett(korps_id=self.annet.pk).status_code, 201)

    def test_kompetanser_settes_og_endres(self):
        pk = self._opprett(kompetanse_ider=[self.komp.pk]).json()['data']['id']
        res = self.c.put(f'/vaktliste/api/mannskap/{pk}/',
                         data={'kompetanse_ider': []},
                         content_type='application/json')
        self.assertEqual(res.json()['data']['kompetanser'], [])

    def test_flytting_til_annet_korps(self):
        pk = self._opprett().json()['data']['id']
        res = self.c.put(f'/vaktliste/api/mannskap/{pk}/',
                         data={'korps_id': self.annet.pk},
                         content_type='application/json')
        self.assertEqual(res.json()['data']['korps_navn'], 'Karmøy')

    def test_deaktivering_er_veien_ut(self):
        pk = self._opprett().json()['data']['id']
        res = self.c.put(f'/vaktliste/api/mannskap/{pk}/',
                         data={'er_aktiv': False},
                         content_type='application/json')
        self.assertFalse(res.json()['data']['er_aktiv'])
        # Raden består — den skal kunne aktiveres igjen.
        self.assertTrue(Mannskap.objects.filter(pk=pk).exists())

    def test_person_paa_vaktpost_kan_ikke_slettes(self):
        pk = self._opprett().json()['data']['id']
        vl = services.opprett_planlagt_vakt('Vakta')
        r = lag_ressurs(vaktliste=vl, navn='Lag 1')
        na = timezone.now()
        Vaktpost.objects.create(ressurs=r, mannskap_id=pk,
                                fra_tid=na, til_tid=na + timedelta(hours=8))

        res = self.c.delete(f'/vaktliste/api/mannskap/{pk}/')
        self.assertEqual(res.status_code, 409)
        self.assertIn('inaktiv', res.json()['message'])
        self.assertTrue(Mannskap.objects.filter(pk=pk).exists())

    def test_ubrukt_person_kan_slettes(self):
        pk = self._opprett().json()['data']['id']
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/mannskap/{pk}/').status_code, 200)

    def test_kontokobling_settes_og_fjernes(self):
        bruker = _bruker('kari')
        pk = self._opprett(user_id=bruker.pk).json()['data']['id']
        self.assertEqual(
            Mannskap.objects.get(pk=pk).user_id, bruker.pk)

        res = self.c.put(f'/vaktliste/api/mannskap/{pk}/',
                         data={'user_id': None}, content_type='application/json')
        self.assertEqual(res.json()['data']['brukernavn'], '')

    def test_kontolista_sier_hvem_som_er_opptatt(self):
        """`Mannskap.user` er en OneToOne. Klienten må vite hvilke kontoer som
        er tatt — ellers tilbyr nedtrekket et valg som ikke kan lagres."""
        bruker = _bruker('kari')
        _bruker('ola')
        pk = self._opprett(user_id=bruker.pk).json()['data']['id']
        kontoer = self.c.get('/vaktliste/api/mannskap/').json()['data']['kontoer']
        koblet = [u for u in kontoer if u['brukernavn'] == 'kari']
        self.assertEqual(koblet[0]['mannskap_id'], pk)
        ledig = [u for u in kontoer if u['brukernavn'] == 'ola']
        self.assertIsNone(ledig[0]['mannskap_id'])
        self.assertEqual([u for u in kontoer if u['brukernavn'] == 'adm'], [],
                         'adminkontoen er utenfor — den tilbys ikke')

    def test_get_gir_alle_fire_listene(self):
        """Fire kall der ett holder er fire steder noe kan komme i utakt."""
        data = self.c.get('/vaktliste/api/mannskap/').json()['data']
        for nokkel in ('mannskap', 'korps', 'kompetanser', 'roller', 'kontoer'):
            self.assertIn(nokkel, data)

    def test_notatet_lagres_men_verdiene_logges_ikke(self):
        """Unntaket fra fase 1 skal gjelde også når skrivingen kommer fra
        denne flaten — det er den eneste veien inn i prod."""
        from audit.models import AuditLog
        pk = self._opprett().json()['data']['id']
        AuditLog.objects.all().delete()

        self.c.put(f'/vaktliste/api/mannskap/{pk}/',
                   data={'notat': 'Har nøtteallergi'},
                   content_type='application/json')

        self.assertEqual(Mannskap.objects.get(pk=pk).notat, 'Har nøtteallergi')
        self.assertFalse(AuditLog.objects.filter(
            new_value__icontains='nøtteallergi').exists())


class SjekkAtIngenPekerPaaDjangoAdminTests(TestCase):
    """Ingen mal skal sende brukeren til `/django-admin/`.

    Flaten er kun rutet under `DEBUG` (S1). En mal som ber
    brukeren gå dit, peker på en dør som ikke finnes i produksjon — og det var
    nøyaktig feilen vaktlistemodulen hadde gjennom fase 1 og 2.
    """

    def test_ingen_mal_viser_til_django_admin(self):
        import re
        from pathlib import Path
        from django.conf import settings

        rot = Path(settings.BASE_DIR)
        maler = list((rot / 'templates').rglob('*.html'))
        for app in rot.iterdir():
            if (app / 'templates').is_dir():
                maler.extend((app / 'templates').rglob('*.html'))

        funn = []
        for mal in maler:
            tekst = mal.read_text(encoding='utf-8')
            # Malkommentarer forklarer regelen og nevner navnet; de teller ikke.
            tekst = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}',
                           '', tekst, flags=re.S)
            tekst = re.sub(r'<!--.*?-->', '', tekst, flags=re.S)
            if re.search(r'django-admin|Django-admin', tekst):
                funn.append(str(mal.relative_to(rot)))

        self.assertEqual(funn, [], (
            'Maler som viser brukeren til /django-admin/:\n  '
            + '\n  '.join(funn)
            + '\n\nFlaten er av i produksjon (S1). Bygg funksjonen i portalen, '
              'eller pek på den portalsiden som alt dekker den.'
        ))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KompetansestigeTests(TestCase):
    """`Kompetanse.bygger_paa`: har du AFØR, sier det seg selv at du har VFØR.

    Poenget er lesbarhet i mannskapslista. Å vise GFØR, VFØR og AFØR på samme
    person legger ikke til noe — det fyller bare kolonnen så telefonnummeret
    forsvinner ut av syne. Se `services.synlige_kompetanser`.

    Pekeren er en stige, ikke en global rangering: «Sykepleier» og «Sjåfør
    kode 160» har ingen innbyrdes rekkefølge, og skal ikke tvinges inn i en.
    """

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund')
        self.gfor = Kompetanse.objects.create(navn='GFØR')
        self.vfor = Kompetanse.objects.create(navn='VFØR', bygger_paa=self.gfor)
        self.afor = Kompetanse.objects.create(navn='AFØR', bygger_paa=self.vfor)
        self.sykepleier = Kompetanse.objects.create(navn='Sykepleier')
        self.c = _klient(_bruker('adm', admin=True))

    def _person(self, *kompetanser):
        p = Mannskap.objects.create(navn='Kari', korps=self.korps)
        p.kompetanser.set(kompetanser)
        return p

    def _synlige(self):
        data = self.c.get('/vaktliste/api/mannskap/').json()['data']
        return [k['navn'] for k in data['mannskap'][0]['kompetanser']]

    def test_hoyeste_trinn_skjuler_de_under(self):
        self._person(self.gfor, self.vfor, self.afor)
        self.assertEqual(self._synlige(), ['AFØR'])

    def test_mellomtrinn_skjuler_bare_det_under_seg(self):
        self._person(self.gfor, self.vfor)
        self.assertEqual(self._synlige(), ['VFØR'])

    def test_frittstaaende_kompetanse_skjules_aldri(self):
        """Sykepleier er ikke i stigen, og skal stå selv om AFØR gjør det."""
        self._person(self.afor, self.vfor, self.sykepleier)
        self.assertEqual(sorted(self._synlige()), ['AFØR', 'Sykepleier'])

    def test_hele_settet_folger_med_i_svaret(self):
        """Redigeringsskjemaet må vise det som faktisk er krysset av, og
        «har hun egentlig VFØR?» skal kunne besvares uten å åpne det."""
        self._person(self.gfor, self.vfor, self.afor)
        data = self.c.get('/vaktliste/api/mannskap/').json()['data']
        self.assertEqual(
            sorted(k['navn'] for k in data['mannskap'][0]['alle_kompetanser']),
            ['AFØR', 'GFØR', 'VFØR'])

    def test_bare_det_laveste_trinnet_staar_alene(self):
        self._person(self.gfor)
        self.assertEqual(self._synlige(), ['GFØR'])

    def test_ingen_kompetanser_gir_tom_liste(self):
        self._person()
        self.assertEqual(self._synlige(), [])

    # ── Skriving ─────────────────────────────────────────────────────────
    def test_stigen_settes_gjennom_api_et(self):
        ny = self.c.post('/vaktliste/api/kompetanser/',
                         data={'navn': 'Ambulansearbeider',
                               'bygger_paa_id': self.afor.pk},
                         content_type='application/json')
        self.assertEqual(ny.status_code, 201)
        self.assertEqual(ny.json()['data']['bygger_paa_navn'], 'AFØR')

    def test_kompetanse_kan_ikke_bygge_paa_seg_selv(self):
        res = self.c.put(f'/vaktliste/api/kompetanser/{self.vfor.pk}/',
                         data={'bygger_paa_id': self.vfor.pk},
                         content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.vfor.refresh_from_db()
        self.assertEqual(self.vfor.bygger_paa_id, self.gfor.pk)

    def test_ring_i_stigen_avvises(self):
        """«A bygger på B, B bygger på A» har ikke noe svar på hva som er
        øverst, og ville gjort visningen til en smakssak."""
        res = self.c.put(f'/vaktliste/api/kompetanser/{self.gfor.pk}/',
                         data={'bygger_paa_id': self.afor.pk},
                         content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('ring', res.json()['message'])
        self.gfor.refresh_from_db()
        self.assertIsNone(self.gfor.bygger_paa_id)

    def test_stigen_kan_kobles_fra(self):
        res = self.c.put(f'/vaktliste/api/kompetanser/{self.afor.pk}/',
                         data={'bygger_paa_id': None},
                         content_type='application/json')
        self.assertEqual(res.json()['data']['bygger_paa_navn'], '')

    def test_sletting_av_mellomtrinn_lar_toppen_staa(self):
        """SET_NULL: fjernes VFØR, står AFØR igjen frittstående. Å kaskadere
        ville slettet det høyeste kurset fordi noen ryddet bort et lavere."""
        self.vfor.delete()
        self.afor.refresh_from_db()
        self.assertIsNone(self.afor.bygger_paa_id)
        self.assertTrue(Kompetanse.objects.filter(pk=self.afor.pk).exists())

    def test_en_ring_i_basen_gir_avkortet_kjede_ikke_evig_lokke(self):
        """Ringer skal ikke kunne oppstå, men en manuell endring i basen skal
        ikke henge serveren."""
        Kompetanse.objects.filter(pk=self.gfor.pk).update(bygger_paa=self.afor)
        self._person(self.gfor, self.vfor, self.afor)
        self.assertEqual(self._synlige(), [])   # alle impliserer hverandre


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SammeFormBeggeVeierTests(TestCase):
    """Verdimengdene skal se like ut uansett hvilket endepunkt de kommer fra.

    Siden tegner registerfanene fra **mannskapsendepunktets** nyttelast, ikke
    fra `/api/korps/`. Var de to formene skrevet hver for seg, ville de gli fra
    hverandre — og det gjorde de: fanene viste «ubrukt» på et korps med
    mannskap, fordi den lette nedtrekkslista manglet `i_bruk`. Feilen ble
    funnet i nettleser, ikke av testene, fordi hver test spurte det endepunktet
    den selv beskrev.
    """

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        gfor = Kompetanse.objects.create(navn='GFØR')
        Kompetanse.objects.create(navn='VFØR', bygger_paa=gfor)
        lag_rolle('Lagleder')
        Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.c = _klient(_bruker('adm', admin=True))

    def _fra_mannskapsendepunktet(self, nokkel):
        return self.c.get('/vaktliste/api/mannskap/').json()['data'][nokkel]

    def _fra_registeret(self, sti):
        return self.c.get(f'/vaktliste/api/{sti}/').json()['data']

    def test_identisk_form_paa_alle_tre(self):
        for nokkel, sti in (('korps', 'korps'),
                            ('kompetanser', 'kompetanser'),
                            ('roller', 'roller')):
            with self.subTest(mengde=nokkel):
                self.assertEqual(self._fra_mannskapsendepunktet(nokkel),
                                 self._fra_registeret(sti))

    def test_i_bruk_naar_fram_til_siden(self):
        """Selve feilen: fanen viste «ubrukt» på et korps som hadde mannskap."""
        rad = self._fra_mannskapsendepunktet('korps')[0]
        self.assertEqual(rad['i_bruk'], 1)

    def test_stigen_naar_fram_til_siden(self):
        vfor = [k for k in self._fra_mannskapsendepunktet('kompetanser')
                if k['navn'] == 'VFØR'][0]
        self.assertEqual(vfor['bygger_paa_navn'], 'GFØR')


class KontokoblingTests(TestCase):
    """Kontokobling for hånd er global admin (André, 12. sep. 2026: «Konto-
    raden fjernes fra alle som ikke er admin»). Alle andre kobler gjennom
    e-posten — se `EpostkoblingTests`."""

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.admin = _bruker('adm', admin=True)
        self.vaktleder = _bruker('vl', 'skriv_full')
        self.vanlig = _bruker('vanlig', 'les')
        self.c_vl = _klient(self.vaktleder)
        self.c_adm = _klient(self.admin)

    def _opprett(self, klient, user_id):
        return klient.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Kari', 'korps_id': self.korps.pk, 'user_id': user_id})

    def test_vaktleder_kan_ikke_koble_for_haand(self):
        res = self._opprett(self.c_vl, self.vanlig.pk)
        self.assertEqual(res.status_code, 403, res.content)
        self.assertIn('e-posten', res.json()['message'])
        self.assertEqual(Mannskap.objects.count(), 0)

    def test_global_admin_kobler_vanlige_kontoer(self):
        self.assertEqual(self._opprett(self.c_adm, self.vanlig.pk).status_code, 201)

    def test_adminkontoer_er_aldri_mannskap(self):
        # «Vi skal ikke ha adminkonto som mannskap. Den er utenfor.» (André,
        # 12. sep. 2026) — heller ikke når global admin kobler for hånd.
        res = self._opprett(self.c_adm, self.admin.pk)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('Adminkontoer er ikke mannskap', res.json()['message'])
        self.assertEqual(Mannskap.objects.count(), 0)
        pk = self._opprett(self.c_adm, self.vanlig.pk).json()['data']['id']
        res = self.c_adm.put(f'/vaktliste/api/mannskap/{pk}/', content_type='application/json',
                             data={'user_id': self.admin.pk})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Mannskap.objects.get(pk=pk).user_id, self.vanlig.pk)

    def test_kontolista_tilbyr_ikke_adminkontoer(self):
        ider = {k['id'] for k in self.c_adm.get('/vaktliste/api/mannskap/').json()['data']['kontoer']}
        self.assertIn(self.vanlig.pk, ider)
        self.assertNotIn(self.admin.pk, ider)

    def test_heller_ikke_ved_redigering(self):
        pk = self._opprett(self.c_adm, self.vanlig.pk).json()['data']['id']
        res = self.c_vl.put(f'/vaktliste/api/mannskap/{pk}/', content_type='application/json',
                            data={'user_id': None})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Mannskap.objects.get(pk=pk).user_id, self.vanlig.pk)

    def test_vaktleder_redigerer_resten_som_foer(self):
        pk = self._opprett(self.c_adm, self.vanlig.pk).json()['data']['id']
        res = self.c_vl.put(f'/vaktliste/api/mannskap/{pk}/', content_type='application/json',
                            data={'telefon': '99900000'})
        self.assertEqual(res.status_code, 200, res.content)


class EpostkoblingTests(TestCase):
    """E-post på mannskapet, og automatisk kontokobling på adressen (André,
    12. sep. 2026: «automatisk oppkobling til brukere og ser om det er
    brukere med den eposten»)."""

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        # Koblingen er leder og admin (13. sep. 2026) — `skriv_full` lagrer
        # e-posten uten å koble, se `tests_prodtest_13sep.py`.
        self.vaktleder = _bruker('vl', 'skriv_leder')
        self.admin = _bruker('adm', admin=True)
        self.c_vl = _klient(self.vaktleder)
        self.c_adm = _klient(self.admin)
        self.kari = CustomUser.objects.create_user(
            username='kari', password='x', email='Kari@Example.org',
            must_change_password=False)

    def _opprett(self, klient, **felt):
        data = {'navn': 'Kari Nordmann', 'korps_id': self.korps.pk, **felt}
        return klient.post('/vaktliste/api/mannskap/', content_type='application/json', data=data)

    def test_epost_lagres_normalisert_og_kobler_kontoen(self):
        res = self._opprett(self.c_vl, epost='  kari@example.ORG ')
        self.assertEqual(res.status_code, 201, res.content)
        d = res.json()['data']
        self.assertEqual(d['epost'], 'kari@example.org')
        self.assertEqual(d['brukernavn'], 'kari', 'kontoen med samme e-post er koblet')
        self.assertTrue(d['konto_finnes'])

    def test_uten_treff_ingen_kobling_og_merket_er_av(self):
        d = self._opprett(self.c_vl, epost='ukjent@example.org').json()['data']
        self.assertEqual(d['user_id'], None)
        self.assertFalse(d['konto_finnes'])

    def test_ugyldig_epost_avvises(self):
        res = self._opprett(self.c_vl, epost='ikke en adresse')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Mannskap.objects.count(), 0)

    def test_en_konto_kobles_bare_en_gang(self):
        self._opprett(self.c_vl, epost='kari@example.org')
        d = self._opprett(self.c_vl, navn='Kari II', epost='kari@example.org').json()['data']
        self.assertIsNone(d['user_id'], 'OneToOne — den andre raden får ikke kontoen')
        self.assertTrue(d['konto_finnes'], 'men merket sier at brukeren finnes')

    def test_adminkonto_kobles_aldri_paa_epost(self):
        # Adminkontoen står utenfor (André, 12. sep. 2026) — verken vaktleder
        # eller admin selv får koblet den, og merket sier ikke at det finnes
        # en konto å koble.
        self.admin.email = 'adm@example.org'
        self.admin.save(update_fields=['email'])
        d = self._opprett(self.c_vl, epost='adm@example.org').json()['data']
        self.assertIsNone(d['user_id'])
        self.assertFalse(d['konto_finnes'])
        d2 = self._opprett(self.c_adm, navn='Admin selv', epost='adm@example.org').json()['data']
        self.assertIsNone(d2['user_id'])
        self.assertFalse(d2['konto_finnes'])

    def test_redigering_av_eposten_kobler_ogsaa(self):
        pk = self._opprett(self.c_vl).json()['data']['id']
        res = self.c_vl.put(f'/vaktliste/api/mannskap/{pk}/', content_type='application/json',
                            data={'epost': 'kari@example.org'})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['brukernavn'], 'kari')
        self.assertEqual(Mannskap.objects.get(pk=pk).user_id, self.kari.pk)

    def test_registeret_baerer_merket_uten_en_sporring_per_rad(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self._opprett(self.c_vl, navn='A', epost='kari@example.org')
        self._opprett(self.c_vl, navn='B', epost='ukjent@example.org')
        self._opprett(self.c_vl, navn='C')
        with CaptureQueriesContext(connection) as tre:
            data = self.c_vl.get('/vaktliste/api/mannskap/').json()['data']
        merker = {m['navn']: m['konto_finnes'] for m in data['mannskap']}
        self.assertEqual(merker, {'A': True, 'B': False, 'C': False})
        for navn in ('D', 'E', 'F'):
            self._opprett(self.c_vl, navn=navn, epost=f'{navn.lower()}@example.org')
        with CaptureQueriesContext(connection) as seks:
            self.c_vl.get('/vaktliste/api/mannskap/')
        self.assertEqual(len(tre), len(seks), 'antall spørringer skal ikke vokse med radene')



class GrupperadenJsTests(SimpleTestCase):
    """Raden i «Ressursgrupper» — punkt 4 i pulje 3 (André, 16. sep. 2026).

    **`mkGruppeRad` var ikke prøvd i det hele tatt** før dette. Den bygger
    markup, og den bygger den fra et gruppenavn som er fritekst fra basen, så
    den hørte hjemme i XSS-skanneren også — den er lagt inn der samtidig.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkGruppeRad', 'settGruppeAktiv', '_gruppeKall', 'slettGruppe')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _rad(self, **felter):
        g = {'id': 3, 'navn': 'Ambulanse', 'ikon': 'truck', 'i_bruk': 0,
             'flere_enheter': True, 'er_aktiv': True}
        g.update(felter)
        # **`gruppeRedigeres` er en `let` på toppnivå, og `build_harness`
        # henter bare funksjoner.** Uten linja under dør noden på en
        # `ReferenceError` — samme felle som `SISTE_LISTE_NOKKEL` 16. sep.
        return run_node(self.harness,
                        'globalThis.gruppeRedigeres = null;\n'
                        f'console.log(mkGruppeRad({json.dumps(g)}));')

    def test_raden_har_baade_endre_og_deaktiver(self):
        """De to knappene som manglet. Uten «Endre» kunne en gruppe ikke
        omdøpes i det hele tatt; uten «Deaktiver» hadde `er_aktiv` ingen vei
        inn, selv om nedtrekkene respekterte den."""
        rad = self._rad()
        self.assertIn('data-action="startRedigerGruppe"', rad)
        self.assertIn('data-action="settGruppeAktiv"', rad)
        self.assertIn('>Deaktiver<', rad)

    def test_en_inaktiv_gruppe_ser_inaktiv_ut(self):
        """En deaktivert gruppe som ser ut som en aktiv gjør «hvorfor står
        den ikke i nedtrekket?» til et spørsmål ingen kan svare på ved å se."""
        rad = self._rad(er_aktiv=False)
        self.assertIn('vl-inaktiv', rad)
        self.assertIn('inaktiv</span>', rad)
        self.assertIn('>Aktiver<', rad)
        self.assertNotIn('>Deaktiver<', rad)

    def test_sletteknappen_er_borte_naar_gruppa_er_i_bruk(self):
        """Serveren nekter uansett; en knapp som fører til en vegg er verre
        enn ingen knapp. «Deaktiver» står igjen som veien ut."""
        rad = self._rad(i_bruk=4)
        self.assertNotIn('slettGruppe', rad)
        self.assertIn('4 i bruk', rad)
        self.assertIn('settGruppeAktiv', rad, 'veien ut skal fortsatt stå der')

    def test_gruppenavnet_escapes(self):
        rad = self._rad(navn='<b>Lag</b>', ikon='" onload="alert(1)')
        self.assertNotIn('<b>Lag</b>', rad)
        self.assertIn('&lt;b&gt;', rad)
        self.assertNotIn('onload="alert(1)"', rad)

    def test_deaktivering_sender_boolsk_ikke_streng(self):
        """«0»/«1» er knappens verdi; serveren gjør `bool(...)`, og
        `bool('0')` er True. Oversettelsen må skje i klienten — samme felle
        som typeflaggene i oppdragsmodulen gikk i samme dag."""
        ut = run_node(self.harness, """
            const kall = [];
            globalThis.apiFetch = async (url, valg) => {
              kall.push([url, JSON.parse(valg.body)]);
              return { ok: true, status: 200, json: async () => ({ status: 'ok' }) }; };
            globalThis.aktivListe = { vaktliste: { id: 1 } };
            globalThis.lastListe = async () => {};
            globalThis.tegnGrupper = () => {};
            globalThis._visFeil = () => {}; globalThis._skjulFeil = () => {};
            await settGruppeAktiv('3:0');
            await settGruppeAktiv('3:1');
            console.log(JSON.stringify(kall));
        """)
        kall = json.loads(ut.strip().splitlines()[0])
        self.assertEqual(kall[0], ['/vaktliste/api/grupper/3/', {'er_aktiv': False}])
        self.assertEqual(kall[1], ['/vaktliste/api/grupper/3/', {'er_aktiv': True}])

    def test_409_ved_sletting_spor_en_gang_til_og_sender_bekreftelsen(self):
        """**Rollene følger med, og serveren teller dem.** Klienten har dem
        ikke, så et tall den gjettet ville vært feil akkurat når det betydde
        noe. 409 er derfor «bekreft», ikke «nei»."""
        ut = run_node(self.harness, """
            const kall = [];
            let forste = true;
            globalThis.apiFetch = async (url, valg) => {
              kall.push([url, valg.method, valg.body ? JSON.parse(valg.body) : null]);
              if (forste) { forste = false;
                return { ok: false, status: 409,
                         json: async () => ({ message: 'har 2 rolle(r)' }) }; }
              return { ok: true, status: 200, json: async () => ({ status: 'ok' }) }; };
            globalThis.confirm = (t) => { globalThis.spurt = t; return true; };
            globalThis.aktivListe = { vaktliste: { id: 1 },
                                      grupper: [{ id: 3, navn: 'Telt' }] };
            globalThis.lastListe = async () => {};
            globalThis.tegnGrupper = () => {};
            globalThis._visFeil = () => {}; globalThis._skjulFeil = () => {};
            await slettGruppe(3);
            console.log(JSON.stringify(kall));
            console.log(JSON.stringify(globalThis.spurt));
        """)
        linjer = ut.strip().splitlines()
        kall = json.loads(linjer[0])
        self.assertEqual(len(kall), 2, 'to forsøk: uten og med bekreftelse')
        self.assertIsNone(kall[0][2], 'første gang uten kropp')
        self.assertEqual(kall[1][2], {'confirm': True})
        self.assertIn('2 rolle(r)', json.loads(linjer[1]),
                      'spørsmålet bærer serverens tall, ikke et klienten fant på')

    def test_nei_paa_bekreftelsen_sletter_ingenting(self):
        ut = run_node(self.harness, """
            const kall = [];
            globalThis.apiFetch = async (url, valg) => {
              kall.push(valg.method);
              return { ok: false, status: 409, json: async () => ({ message: 'x' }) }; };
            // **To spørsmål, ikke ett.** `slettGruppe` spør «Slette gruppa?»
            // før den prøver; 409-bekreftelsen er det andre. En stub som sa
            // nei til begge ville aldri nådd det som prøves her.
            let svar = [true, false];
            globalThis.confirm = () => svar.shift();
            globalThis.aktivListe = { vaktliste: { id: 1 },
                                      grupper: [{ id: 3, navn: 'Telt' }] };
            globalThis.lastListe = async () => {};
            globalThis.tegnGrupper = () => {};
            globalThis._visFeil = () => {}; globalThis._skjulFeil = () => {};
            await slettGruppe(3);
            console.log(JSON.stringify(kall));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), ['DELETE'],
                         'bare det første forsøket')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RollerekkefolgeApiTests(TestCase):
    """Rangeringen av roller — pulje 3 punkt 6 (André, 16. sep. 2026).

    «Rollene sorteres meningsfullt — leder øverst, hospitant nederst.»
    Rekkefølgen er **data og ikke en liste i koden**: rollene seedes ikke med
    faste navn (de kom fra det som fantes ved migrasjon `0007`), så en
    hardkodet rangering ville truffet noen installasjoner og ikke andre.
    """

    def setUp(self):
        self.leder = _klient(_bruker('leder_rr', 'skriv_leder'))
        self.bemanner = _klient(_bruker('bemanner_rr', 'skriv_full'))
        self.g = gruppe(AMBULANSE)
        self.annen = gruppe(LAG)
        self.hospitant = Ressursrolle.objects.create(navn='Hospitant', gruppe=self.g)
        self.lagleder = Ressursrolle.objects.create(navn='Lagleder', gruppe=self.g)
        self.sjafor = Ressursrolle.objects.create(navn='Sjåfør', gruppe=self.g)

    def _flytt(self, ider, gruppe_id=None, klient=None):
        return (klient or self.leder).put(
            '/vaktliste/api/roller/rekkefolge/',
            data=json.dumps({'gruppe_id': gruppe_id or self.g.pk, 'ider': ider}),
            content_type='application/json')

    def _navn(self):
        return [r.navn for r in Ressursrolle.objects.filter(gruppe=self.g)]

    def test_lista_settes_i_den_rekkefolgen_som_sendes(self):
        res = self._flytt([self.lagleder.pk, self.sjafor.pk, self.hospitant.pk])
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._navn(), ['Lagleder', 'Sjåfør', 'Hospitant'])

    def test_svaret_baerer_den_nye_rekkefolgen(self):
        """Klienten tegner på nytt fra svaret; gjør den en ny henting i
        stedet, ser man den gamle rekkefølgen et halvt sekund."""
        res = self._flytt([self.sjafor.pk, self.hospitant.pk, self.lagleder.pk])
        self.assertEqual([r['navn'] for r in res.json()['data']],
                         ['Sjåfør', 'Hospitant', 'Lagleder'])

    def test_bemanneren_omsorterer_ikke(self):
        """Å rangere rollene er oppsett — det endrer hva *alle* ser i
        nedtrekket, ikke hva som står på én rad."""
        self.assertEqual(
            self._flytt([self.lagleder.pk, self.sjafor.pk, self.hospitant.pk],
                        klient=self.bemanner).status_code, 403)

    def test_et_delvis_sett_avvises(self):
        """**Hele gruppa, ikke et utvalg.** Et delvis sett ville gitt noen
        rader nye tall og latt resten stå — og da er rekkefølgen en blanding
        av to oppfatninger. Feilen er også den eneste måten å oppdage at
        klienten og serveren ser ulike lister."""
        res = self._flytt([self.lagleder.pk, self.sjafor.pk])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._navn(), ['Hospitant', 'Lagleder', 'Sjåfør'],
                         'ingenting flyttet')

    def test_en_rolle_fra_en_annen_gruppe_avvises(self):
        """Rekkefølgen er per gruppe. Uten avgrensningen kunne en liste med
        ID-er fra en annen gruppe skrevet tall inn der."""
        fremmed = Ressursrolle.objects.create(navn='Utenfor', gruppe=self.annen)
        res = self._flytt([self.lagleder.pk, self.sjafor.pk, fremmed.pk])
        self.assertEqual(res.status_code, 400)
        fremmed.refresh_from_db()
        self.assertEqual(fremmed.rekkefolge, 10, 'den fremmede står urørt')

    def test_omdoping_flytter_ikke_rollen(self):
        """**Meldt fra staging 16. sep. 2026 (André):** «Jeg endret en rolle
        fra lagsmedlem og til hospitant og nå står den øverst.»

        Det var den *alfabetiske* sorteringen, og den er nettopp det punkt 6
        avskaffer — meldingen kom mens staging fortsatt kjørte bygget før
        rangeringen. Men symptomet fortjener en test som holder det borte:
        med rangering skal navnet ikke lenger kunne flytte en rolle, og det er
        hele forskjellen på en rangering og et alfabet.

        `Hospitant` sorterer foran alle tre alfabetisk, så en rekkefølge som
        stille faller tilbake på navnet blir rød her.
        """
        self._flytt([self.lagleder.pk, self.sjafor.pk, self.hospitant.pk])
        res = self.leder.put(
            f'/vaktliste/api/roller/{self.sjafor.pk}/',
            data=json.dumps({'navn': 'Aaaaardvark'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._navn(), ['Lagleder', 'Aaaaardvark', 'Hospitant'],
                         'navnet flytter ingenting — rangeringen står')
        self.sjafor.refresh_from_db()
        self.assertEqual(self.sjafor.rekkefolge, 20, 'tallet er urørt')

    def test_nedtrekket_beholder_serverens_rekkefolge(self):
        """**Den ene måten rangeringen kunne blitt veltet i stillhet.**

        Serveren sorterer, og `rollerForGruppe()` i klienten *filtrerer* bare.
        Begynner den å sortere selv — alfabetisk, som alt annet i modulen —
        ville rangeringen vært riktig i basen og feil på skjermen, altså
        nøyaktig symptomet André meldte, men uten at noen servertest ble rød.
        """
        from patients.js_test_utils import (PORTAL_UTILS_JS, VAKTLISTE_JS,
                                            build_harness, node_available, run_node)
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self._flytt([self.lagleder.pk, self.sjafor.pk, self.hospitant.pk])
        roller = self.leder.get('/vaktliste/api/roller/').json()['data']
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (VAKTLISTE_JS, ('rollerForGruppe',)),
        ))
        ut = run_node(harness, f"""
            globalThis.aktivListe = {{ roller: {json.dumps(roller)} }};
            console.log(JSON.stringify(
              rollerForGruppe({self.g.pk}, null).map((r) => r.navn)));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]),
                         ['Lagleder', 'Sjåfør', 'Hospitant'],
                         'klienten skal vise serverens rekkefølge, ikke sin egen')

    def test_tullete_kropp_gir_400_ikke_500(self):
        for kropp in ({'gruppe_id': self.g.pk}, {'ider': []},
                      {'gruppe_id': self.g.pk, 'ider': 'x'}):
            with self.subTest(kropp=kropp):
                res = self.leder.put('/vaktliste/api/roller/rekkefolge/',
                                     data=json.dumps(kropp),
                                     content_type='application/json')
                self.assertEqual(res.status_code, 400)


class RollerekkefolgeJsTests(SimpleTestCase):
    """Opp/ned-knappene i rollevinduet."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkRolleRad', 'flyttRolle')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_knappene_er_avslaatt_i_endene(self):
        """De ligger der, men er avslått — en rad som hopper i høyde når den
        kommer først er verre enn en knapp som ikke gjør noe."""
        ut = run_node(self.harness, """
            globalThis.rolleRedigeres = null;
            const r = {id: 7, navn: 'Lagleder', i_bruk: 0};
            console.log(JSON.stringify([mkRolleRad(r, true, false),
                                        mkRolleRad(r, false, true),
                                        mkRolleRad(r, false, false)]));
        """)
        forst, sist, midt = json.loads(ut.strip().splitlines()[0])
        self.assertIn('data-arg="7:opp" disabled', forst)
        self.assertNotIn('data-arg="7:ned" disabled', forst)
        self.assertIn('data-arg="7:ned" disabled', sist)
        self.assertNotIn('disabled', midt, 'midt i lista går begge veier')

    def test_flyttingen_sender_hele_lista_med_de_to_byttet(self):
        """Ikke «opp» på én rad: to kall som krysser hverandre ville byttet to
        par og etterlatt en rekkefølge ingen ba om."""
        ut = run_node(self.harness, """
            const kall = [];
            globalThis.apiFetch = async (url, valg) => {
              kall.push([url, JSON.parse(valg.body)]);
              return { ok: true, json: async () => ({ status: 'ok' }) }; };
            globalThis.document = { getElementById: () => ({ dataset: { gruppe: '2' } }) };
            globalThis.aktivListe = { roller: [
              {id: 1, gruppe_id: 2}, {id: 2, gruppe_id: 2}, {id: 3, gruppe_id: 2},
              {id: 9, gruppe_id: 5}] };
            globalThis._lastRegisterOgListe = async () => {};
            globalThis.tegnRoller = () => {};
            globalThis._visFeil = () => {}; globalThis._skjulFeil = () => {};
            await flyttRolle('3:opp');
            await flyttRolle('1:opp');   // først: ingenting sendes
            console.log(JSON.stringify(kall));
        """)
        kall = json.loads(ut.strip().splitlines()[0])
        self.assertEqual(kall, [['/vaktliste/api/roller/rekkefolge/',
                                 {'gruppe_id': 2, 'ider': [1, 3, 2]}]])

    def test_bare_gruppas_egne_roller_er_med(self):
        """Rolle 9 hører til en annen gruppe og skal ikke havne i lista —
        serveren avviser den, men klienten skal ikke sende den heller."""
        ut = run_node(self.harness, """
            const kall = [];
            globalThis.apiFetch = async (url, valg) => {
              kall.push(JSON.parse(valg.body)); 
              return { ok: true, json: async () => ({ status: 'ok' }) }; };
            globalThis.document = { getElementById: () => ({ dataset: { gruppe: '2' } }) };
            globalThis.aktivListe = { roller: [
              {id: 1, gruppe_id: 2}, {id: 2, gruppe_id: 2}, {id: 9, gruppe_id: 5}] };
            globalThis._lastRegisterOgListe = async () => {};
            globalThis.tegnRoller = () => {};
            globalThis._visFeil = () => {}; globalThis._skjulFeil = () => {};
            await flyttRolle('2:opp');
            console.log(JSON.stringify(kall));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0])[0]['ider'], [2, 1])


class NavneredigeringJsTests(SimpleTestCase):
    """**Én form for navneendring i hele modulen** (André, 16. sep. 2026):
    «Det bør gå relativt automatisk ved endring av rollenavn, se andre navn i
    enheten (altså ambulanse, lag osv).»

    Rollen hadde **ingen** redigering — man måtte slette og opprette, og
    `Vaktpost.rolle` er `PROTECT`/i bruk, så en rolle med skift på seg kunne
    ikke engang slettes. En omdøping var altså umulig.

    Gruppa fikk en `prompt()` tidligere samme dag. Det er oppdragsmodulens
    idiom; vaktlista redigerer verdimengder i et skjema. To former for samme
    handling i samme modul er to kilder som glir fra hverandre, så begge
    bruker nå `_redigeringsrad()`.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkRolleRad', 'mkGruppeRad', '_redigeringsrad',
                        '_nyttNavn', 'lagreRolle', 'startRedigerRolle',
                        'avbrytRedigerRolle')),
    )
    #: `let`-bindingene byggerne leser. `build_harness` henter bare funksjoner.
    TILSTAND = ('globalThis.rolleRedigeres = null;\n'
                'globalThis.gruppeRedigeres = null;\n')

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_raden_som_redigeres_blir_et_felt_med_navnet_i(self):
        ut = run_node(self.harness, self.TILSTAND + """
            globalThis.rolleRedigeres = 7;
            console.log(mkRolleRad({id: 7, navn: 'Lagsmedlem', i_bruk: 3},
                                   false, false));
        """)
        self.assertIn('value="Lagsmedlem"', ut, 'navnet står i feltet')
        self.assertIn('data-action="lagreRolle" data-id="7"', ut)
        self.assertIn('data-action="avbrytRedigerRolle"', ut)
        self.assertNotIn('slettRolle', ut, 'ingen sletteknapp mens man redigerer')

    def test_bare_den_ene_raden_blir_et_felt(self):
        """Redigerer man «Lagsmedlem», skal «Sjåfør» stå som den er."""
        ut = run_node(self.harness, self.TILSTAND + """
            globalThis.rolleRedigeres = 7;
            console.log(mkRolleRad({id: 8, navn: 'Sjåfør', i_bruk: 0},
                                   false, false));
        """)
        self.assertNotIn('<input', ut)
        self.assertIn('data-action="startRedigerRolle" data-id="8"', ut)

    def test_gruppa_bruker_samme_form(self):
        ut = run_node(self.harness, self.TILSTAND + """
            globalThis.gruppeRedigeres = 3;
            console.log(mkGruppeRad({id: 3, navn: 'Ambulanse', ikon: 'truck',
                                     i_bruk: 2, flere_enheter: true, er_aktiv: true}));
        """)
        self.assertIn('value="Ambulanse"', ut)
        self.assertIn('data-action="lagreGruppe" data-id="3"', ut)
        self.assertNotIn('settGruppeAktiv', ut, 'knappene viker for feltet')

    def test_navnet_escapes_i_feltet(self):
        """Verdien står i et attributt — attributt-XSS, ikke tekst-XSS."""
        ut = run_node(self.harness, self.TILSTAND + """
            globalThis.rolleRedigeres = 7;
            console.log(mkRolleRad({id: 7, navn: '" onfocus="alert(1)', i_bruk: 0},
                                   false, false));
        """)
        self.assertNotIn('onfocus="alert(1)"', ut)

    def test_lagring_sender_navnet_og_henter_hele_registeret(self):
        """**`_lastRegisterOgListe`, ikke bare rollelista.** Rollenavnet står i
        nedtrekket på hver rad i regnearket også; hentes bare rollelista, viser
        skiftene det gamle navnet til neste sidelasting."""
        ut = run_node(self.harness, self.TILSTAND + """
            const kall = [];
            globalThis.rolleRedigeres = 7;
            globalThis.apiFetch = async (url, valg) => {
              kall.push([url, valg.method, JSON.parse(valg.body)]);
              return { ok: true, json: async () => ({ status: 'ok' }) }; };
            globalThis.document = { getElementById: () => ({ value: '  Lagsmedlem  ' }) };
            globalThis._lastRegisterOgListe = async () => { kall.push(['register']); };
            globalThis.tegnRoller = () => {};
            globalThis._visFeil = () => {}; globalThis._skjulFeil = () => {};
            await lagreRolle(7);
            console.log(JSON.stringify(kall));
            console.log(JSON.stringify(globalThis.rolleRedigeres));
        """)
        linjer = ut.strip().splitlines()
        kall = json.loads(linjer[0])
        self.assertEqual(kall[0], ['/vaktliste/api/roller/7/', 'PUT',
                                   {'navn': 'Lagsmedlem'}])
        self.assertEqual(kall[1], ['register'], 'hele registeret hentes')
        self.assertIsNone(json.loads(linjer[1]), 'redigeringen lukkes etterpå')

    def test_tomt_navn_lagres_ikke(self):
        ut = run_node(self.harness, self.TILSTAND + """
            const kall = [];
            globalThis.apiFetch = async () => { kall.push(1); return { ok: true }; };
            globalThis.document = { getElementById: () => ({ value: '   ' }) };
            globalThis._lastRegisterOgListe = async () => {};
            globalThis.tegnRoller = () => {};
            globalThis._visFeil = (_, t) => { globalThis.feil = t; };
            globalThis._skjulFeil = () => {};
            await lagreRolle(7);
            console.log(JSON.stringify([kall.length, globalThis.feil]));
        """)
        antall, feil = json.loads(ut.strip().splitlines()[0])
        self.assertEqual(antall, 0, 'ingen forespørsel sendes')
        self.assertIn('navn', feil)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RadeneFoelgerRollerangeringenTests(TestCase):
    """**Meldt fra staging 16. sep. 2026 (André):** «Det er en enhet/lag som
    har i synkende rekkefølge: lagsmedlem, lagleder, lagsmedlem, hospitant.
    Når jeg justerer på førstenevnte så flyttes den ikke i enheten etter sin
    rolle.»

    Laget sto i **innsettingsrekkefølge**, og da må man lese hver rad for å
    finne lederen. Rangeringen fra `Ressursrolle.rekkefolge` (punkt 6) var
    bare en sortering av *nedtrekket* — den styrte ikke radene den beskriver.

    Klienten sorterer ikke: `_posterFor()` filtrerer, og kortet tegner det den
    får. Rekkefølgen er derfor serverens, og regelen hører hjemme i
    `Vaktpost.Meta.ordering`.
    """

    def setUp(self):
        self.g = gruppe(LAG)
        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.ressurs = lag_ressurs(vaktliste=self.vl, navn='Lag 1', gruppe=self.g)
        self.roller = {
            navn: Ressursrolle.objects.create(navn=navn, gruppe=self.g,
                                              rekkefolge=(i + 1) * 10)
            for i, navn in enumerate(('Lagleder', 'Lagsmedlem', 'Hospitant'))}
        self.fra = timezone.now().replace(microsecond=0)
        self.til = self.fra + timedelta(hours=8)

    def _plass(self, rolle=None, person=None, fra=None):
        return Vaktpost.objects.create(
            ressurs=self.ressurs, fra_tid=fra or self.fra, til_tid=self.til,
            rolle=self.roller[rolle] if rolle else None, mannskap=person)

    def _roller(self):
        return [vp.rolle.navn if vp.rolle else '—'
                for vp in Vaktpost.objects.filter(ressurs=self.ressurs)]

    def test_andres_lag_sorteres_etter_rolle(self):
        for navn in ('Lagsmedlem', 'Lagleder', 'Lagsmedlem', 'Hospitant'):
            self._plass(navn)
        self.assertEqual(self._roller(),
                         ['Lagleder', 'Lagsmedlem', 'Lagsmedlem', 'Hospitant'])

    def test_tiden_vinner_over_rollen(self):
        """Rangeringen gjelder **innenfor** et skift. En hospitant som møter
        kl. 08 står før en lagleder som møter kl. 16 — ellers ville lista
        sluttet å være kronologisk, og det er tida man planlegger etter."""
        self._plass('Lagleder', fra=self.fra + timedelta(hours=8))
        self._plass('Hospitant')
        self.assertEqual(self._roller(), ['Hospitant', 'Lagleder'])

    def test_en_rad_uten_rolle_havner_nederst(self):
        """**Eksplisitt, ikke tilfeldig.** PostgreSQL legger NULL sist i
        stigende sortering, SQLite legger dem først — uten `nulls_last` ville
        dev og prod svart hver sitt, og en rekkefølge verifisert lokalt vært
        en annen i drift."""
        self._plass(None)
        self._plass('Lagleder')
        self.assertEqual(self._roller(), ['Lagleder', '—'])

    def test_ledig_plass_staar_foerst_blant_sine_egne(self):
        """Den gamle regelen — ledige plasser er lette å se — gjelder nå
        *innenfor* rollen, som er der den fortsatt betyr noe. Også denne sto
        udekket og bare tilfeldigvis sann i SQLite."""
        person = Mannskap.objects.create(
            navn='Kari', korps=Korps.objects.create(navn='Haugesund'))
        self._plass('Lagsmedlem', person=person)
        self._plass('Lagsmedlem')
        rader = list(Vaktpost.objects.filter(ressurs=self.ressurs))
        self.assertIsNone(rader[0].mannskap, 'den ledige først')
        self.assertEqual(rader[1].mannskap, person)
