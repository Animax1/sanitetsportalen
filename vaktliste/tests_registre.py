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
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang

from . import services
from .models import Kompetanse, Korps, Mannskap, Ressursrolle, Vaktpost
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

    def test_siden_svarer_og_laster_sin_egen_js(self):
        res = self.c.get('/vaktliste/registre/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'js/vaktliste-registre')
        self.assertNotContains(res, 'patients-utils')

    def test_planleggingssiden_lenker_hit(self):
        """Et register uten vei inn er et register som ikke finnes."""
        self.assertContains(self.c.get('/vaktliste/'), '/vaktliste/registre/')


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
        pk = self._opprett(user_id=bruker.pk).json()['data']['id']
        kontoer = self.c.get('/vaktliste/api/mannskap/').json()['data']['kontoer']
        koblet = [u for u in kontoer if u['brukernavn'] == 'kari']
        self.assertEqual(koblet[0]['mannskap_id'], pk)
        ledig = [u for u in kontoer if u['brukernavn'] == 'adm']
        self.assertIsNone(ledig[0]['mannskap_id'])

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

    Flaten er kun rutet under `DEBUG`/`OFFLINE_MODE` (S1). En mal som ber
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
