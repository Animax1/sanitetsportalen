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
from .models import Kompetanse, Korps, Mannskap, Ressurs, VaktRolle, Vaktpost


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
        rolle = self._post('/vaktliste/api/roller/', navn='Lagleder')
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
            navn='Lag 1')
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
    """De tre som deler fabrikk. Testene kjører mot alle tre der regelen deles."""

    STIER = ('korps', 'kompetanser', 'roller')

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
        self.assertNotIn('kortnavn', self._post('roller', navn='X').json()['data'])

    def test_inaktive_er_med_i_lista(self):
        """De skal kunne aktiveres igjen. En rad som forsvinner helt ser ut
        som en sletting som ikke skjedde."""
        pk = self._post('kompetanser', navn='Utgått').json()['data']['id']
        self.c.put(f'/vaktliste/api/kompetanser/{pk}/', data={'er_aktiv': False},
                   content_type='application/json')
        data = self.c.get('/vaktliste/api/kompetanser/').json()['data']
        self.assertEqual([(r['navn'], r['er_aktiv']) for r in data],
                         [('Utgått', False)])

    def test_rekkefolge_styrer_lista(self):
        self._post('korps', navn='Bokn', rekkefolge=200)
        self._post('korps', navn='Karmøy', rekkefolge=50)
        data = self.c.get('/vaktliste/api/korps/').json()['data']
        self.assertEqual([r['navn'] for r in data], ['Karmøy', 'Bokn'])

    # ── Sletting ─────────────────────────────────────────────────────────
    def test_ubrukt_verdi_kan_slettes(self):
        pk = self._post('roller', navn='Feilskrevet').json()['data']['id']
        self.assertEqual(
            self.c.delete(f'/vaktliste/api/roller/{pk}/').status_code, 200)
        self.assertFalse(VaktRolle.objects.exists())

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
        Ressurs.objects.create(vaktliste=vl, navn='Lag K', korps=korps)

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
        rolle = VaktRolle.objects.create(navn='Lagleder')
        person = Mannskap.objects.create(navn='Kari', korps=korps)
        vl = services.opprett_planlagt_vakt('Vakta')
        r = Ressurs.objects.create(vaktliste=vl, navn='Lag 1')
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
        r = Ressurs.objects.create(vaktliste=vl, navn='Lag 1')
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


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RegisterGateTests(TestCase):
    """Admin-only i fase 2, som resten av modulen — på hvert endepunkt."""

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.komp = Kompetanse.objects.create(navn='Sykepleier')
        self.rolle = VaktRolle.objects.create(navn='Lagleder')

    def test_alle_registerendepunkt_nekter_ikke_admin(self):
        c = _klient(_bruker('skriver', 'skriv_full'))
        kall = [
            ('get', '/vaktliste/api/mannskap/'),
            ('post', '/vaktliste/api/mannskap/'),
            ('put', f'/vaktliste/api/mannskap/{self.person.pk}/'),
            ('delete', f'/vaktliste/api/mannskap/{self.person.pk}/'),
            ('get', '/vaktliste/api/korps/'),
            ('post', '/vaktliste/api/korps/'),
            ('put', f'/vaktliste/api/korps/{self.korps.pk}/'),
            ('delete', f'/vaktliste/api/korps/{self.korps.pk}/'),
            ('get', '/vaktliste/api/kompetanser/'),
            ('post', '/vaktliste/api/kompetanser/'),
            ('put', f'/vaktliste/api/kompetanser/{self.komp.pk}/'),
            ('delete', f'/vaktliste/api/kompetanser/{self.komp.pk}/'),
            ('get', '/vaktliste/api/roller/'),
            ('post', '/vaktliste/api/roller/'),
            ('put', f'/vaktliste/api/roller/{self.rolle.pk}/'),
            ('delete', f'/vaktliste/api/roller/{self.rolle.pk}/'),
        ]
        for metode, sti in kall:
            with self.subTest(kall=f'{metode.upper()} {sti}'):
                svar = getattr(c, metode)(sti, data={},
                                          content_type='application/json')
                self.assertEqual(svar.status_code, 403)

        self.assertTrue(Mannskap.objects.filter(pk=self.person.pk).exists())
        self.assertTrue(Korps.objects.filter(pk=self.korps.pk).exists())

    def test_siden_nekter_ikke_admin(self):
        c = _klient(_bruker('skriver', 'skriv_full'))
        self.assertEqual(c.get('/vaktliste/registre/').status_code, 403)

    def test_siden_nekter_uten_modultilgang(self):
        c = _klient(_bruker('ingen'))
        self.assertEqual(c.get('/vaktliste/registre/').status_code, 403)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TommeOgRusketeIderTests(TestCase):
    """Et HTML-nedtrekk med «Ingen valgt» sender `''`, ikke `null`.

    Sendes den rett inn i et FK-filter, kaster Django `ValueError` og brukeren
    får 500 der hun skulle fått «velg korps». `or None` alene dekker ikke
    søsteren — en ikke-numerisk streng — så begge går gjennom `_int()`.
    Feilen sto i den første utgaven av registersiden og ble funnet av testen
    over; disse låser alle inngangene.
    """

    RUSK = ('', 'null', 'abc', [])

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund')
        self.person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.vl = services.opprett_planlagt_vakt('Vakta')
        self.ressurs = Ressurs.objects.create(vaktliste=self.vl, navn='Lag 1')
        self.c = _klient(_bruker('adm', admin=True))
        self.na = timezone.now()

    def _post(self, sti, **kropp):
        return self.c.post(sti, data=kropp, content_type='application/json')

    def test_ruskete_korps_id_gir_400_ikke_500(self):
        for rusk in self.RUSK:
            with self.subTest(verdi=rusk):
                res = self._post('/vaktliste/api/mannskap/',
                                 navn='Ny', korps_id=rusk)
                self.assertEqual(res.status_code, 400)

    def test_ruskete_valgfrie_ider_faller_til_ingen_kobling(self):
        """Valgfrie felter skal ikke *avvise* — de skal bli «ingen»."""
        for rusk in self.RUSK:
            with self.subTest(verdi=rusk):
                res = self._post(
                    f'/vaktliste/api/vaktlister/{self.vl.pk}/ressurser/',
                    navn=f'Lag {rusk!r}', korps_id=rusk, enhet_id=rusk)
                self.assertEqual(res.status_code, 201)
                self.assertIsNone(res.json()['data']['korps_id'])
                self.assertIsNone(res.json()['data']['enhet_id'])

    def test_ruskete_mannskap_id_paa_vaktpost_gir_400(self):
        for rusk in self.RUSK:
            with self.subTest(verdi=rusk):
                res = self._post(
                    f'/vaktliste/api/ressurser/{self.ressurs.pk}/vaktposter/',
                    mannskap_id=rusk, fra_tid=self.na.isoformat(),
                    til_tid=(self.na + timedelta(hours=8)).isoformat())
                self.assertEqual(res.status_code, 400)

    def test_ruskete_kopier_fra_lager_tom_liste(self):
        res = self._post('/vaktliste/api/vaktlister/',
                         navn='Ny vakt', kopier_fra='abc')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['kopierte_ressurser'], 0)

    def test_ruskete_kompetanseliste_ignoreres_ikke_krasjer(self):
        res = self._post('/vaktliste/api/mannskap/', navn='Ny',
                         korps_id=self.korps.pk,
                         kompetanse_ider=['abc', None, ''])
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['kompetanser'], [])


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
