"""En delt konto kan bare ha tilgang til `oppdrag` (8. okt. 2026, FORSLAG_KO §5.2).

«Ikke som konvensjon, men håndhevet i flere lag — skjemaet, datalaget og en test
— på samme måte som superbrukerflagget er vernet i dag. Grunnen er at sperrene
ellers verner nøyaktig de veiene som finnes akkurat nå, og en ny vei er usynlig
for dem.»

Lagene, og hva hver test prøver:

| Lag | Hvor | Test |
|---|---|---|
| Tilgangen avgjøres | `core.auth_decorators.nivaa_for` | `TilgangenTests` — også med rader lagt inn utenom `save()` |
| Lesere av radene i bulk | `ko/tilstede.py`, `backlog/varsler.py` | `DirekteLesereTests` — og at ingen ny leser kommer uten å ha tatt stilling |
| Datalaget | `ModulTilgang.save()` | `DatalagetTests` |
| Skjemaene | matrisen, opprettelsen, redigeringen | `SkjemaeneTests`, gjennom den ekte siden |
"""
import ast
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser, ModulTilgang
from core.auth_decorators import har_tilgang, nivaa_for
from core.modules import get_all_modules


def _konto(navn, *, delt, role='bruker'):
    return CustomUser.objects.create_user(
        username=navn, password='TestPassord123!', role=role,
        must_change_password=False, er_delt_konto=delt)


def _rader_utenom_save(bruker, **nivaa_per_modul):
    """Som en importjobb, en migrasjon eller data fra før regelen."""
    ModulTilgang.objects.bulk_create([
        ModulTilgang(bruker=bruker, modul_slug=slug, nivaa=nivaa)
        for slug, nivaa in nivaa_per_modul.items()])


class BeslutningenTests(SimpleTestCase):
    def test_bare_oppdrag_tillater_delt_konto(self):
        """Beslutningen låst: en modul til som sier ja, er et valg som skal tas
        bevisst — ikke et flagg noen kopierte fra oppdrag/module.py."""
        self.assertEqual([m.slug for m in get_all_modules() if m.tillat_delt_konto],
                         ['oppdrag'])


class TilgangenTests(TestCase):
    """`nivaa_for` er der regelen *holder* — også for rader ingen sperre så."""

    def test_rader_lagt_inn_utenom_save_gir_ingenting_paa_en_delt_konto(self):
        moduler = [m for m in get_all_modules() if not m.admin_only]
        delt = _konto('bil1', delt=True)
        person = _konto('kari', delt=False)
        for konto in (delt, person):
            _rader_utenom_save(konto, **{m.slug: m.nivaaer[0] for m in moduler})
        for modul in moduler:
            with self.subTest(modul=modul.slug):
                har_delt = nivaa_for(delt, modul.slug)
                if modul.tillat_delt_konto:
                    self.assertEqual(har_delt, modul.nivaaer[0])
                else:
                    self.assertIsNone(har_delt)
                # Kontroll: samme rader på en personlig konto virker.
                self.assertEqual(nivaa_for(person, modul.slug), modul.nivaaer[0])

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_gjennom_siden_pasientlista_stenger_og_oppdrag_aapner(self):
        bil = _konto('bil2', delt=True)
        _rader_utenom_save(bil, patients='skriv_full', oppdrag='skriv_handling')
        self.client.force_login(bil)
        self.assertEqual(self.client.get('/pasienter/api/patients/').status_code, 403)
        self.assertTrue(har_tilgang(bil, 'oppdrag', 'skriv_handling'))


class DirekteLesereTests(TestCase):
    """Noen leser radene i bulk i stedet for å spørre `nivaa_for` per bruker.
    De må ha samme regel — og en ny skal ikke kunne komme uten å ha tatt stilling."""

    #: Filer som leser `ModulTilgang.objects` direkte, og hvorfor de er trygge.
    KJENTE = {
        'core/auth_decorators.py': 'Kilden til `nivaa_for`; sperra står i funksjonen',
        'accounts/forms.py': 'Matrisen leser og skriver radene; sperra står i skjemaet',
        'ko/tilstede.py': 'KO-sidebaren i bulk; utelater delte kontoer',
        'backlog/varsler.py': 'Varselmottakerne i bulk; utelater delte kontoer',
    }

    def test_ingen_ny_direkte_leser_uten_at_noen_har_tatt_stilling(self):
        rot = Path(settings.BASE_DIR)
        funn = set()
        for sti in sorted(rot.glob('*/**/*.py')):
            rel = sti.relative_to(rot).as_posix()
            if ('/migrations/' in rel or '/tests' in rel or rel.startswith('.')
                    or '/site-packages/' in rel or 'test_helpers' in rel):
                continue
            try:
                tre = ast.parse(sti.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tre):
                if (isinstance(node, ast.Attribute) and node.attr == 'objects'
                        and isinstance(node.value, ast.Name) and node.value.id == 'ModulTilgang'):
                    funn.add(rel)
        self.assertEqual(sorted(funn - set(self.KJENTE)), [],
                         'Ny direkte leser av ModulTilgang — utelater den delte kontoer '
                         '(FORSLAG_KO §5.2)? Før den opp i KJENTE med begrunnelse.')

    def test_ko_sidebaren_viser_ikke_en_delt_konto(self):
        from ko.tilstede import _har_ko_tilgang_ider
        bil = _konto('bil3', delt=True)
        person = _konto('ola', delt=False)
        _rader_utenom_save(bil, ko='les')
        _rader_utenom_save(person, ko='les')
        self.assertEqual(_har_ko_tilgang_ider({bil.pk, person.pk}), {person.pk})

    def test_backlog_varsler_ikke_en_delt_konto(self):
        from backlog.varsler import _mottakere
        bil = _konto('bil4', delt=True)
        person = _konto('per', delt=False)
        _rader_utenom_save(bil, backlog='skriv_leder')
        _rader_utenom_save(person, backlog='skriv_leder')
        self.assertEqual([b.username for b in _mottakere(None)], ['per'])


class DatalagetTests(TestCase):
    def test_save_nekter_en_delt_konto_andre_moduler(self):
        bil = _konto('bil5', delt=True)
        with self.assertRaises(ValidationError):
            ModulTilgang.objects.create(bruker=bil, modul_slug='patients', nivaa='les')
        self.assertFalse(ModulTilgang.objects.filter(bruker=bil, modul_slug='patients').exists())
        ModulTilgang.objects.create(bruker=bil, modul_slug='oppdrag', nivaa='skriv_handling')

    def test_save_lar_en_personlig_konto_vaere(self):
        person = _konto('lise', delt=False)
        ModulTilgang.objects.create(bruker=person, modul_slug='patients', nivaa='les')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SkjemaeneTests(TestCase):
    """Gjennom brukersidene, slik admin faktisk gjør det."""

    def setUp(self):
        self.admin = _konto('admin', delt=False, role='admin')
        self.client.force_login(self.admin)

    def _rader(self, bruker):
        return dict(ModulTilgang.objects.filter(bruker=bruker).values_list('modul_slug', 'nivaa'))

    def _rediger(self, bruker, **ekstra):
        data = {'action': 'edit', 'role': 'bruker', 'is_active': 'on'}
        if bruker.er_delt_konto:
            data['er_delt_konto'] = 'on'
        data.update(ekstra)
        return self.client.post(reverse('portaladmin:user_detail', args=[bruker.pk]), data)

    def test_matrisen_tilbyr_bare_ingen_tilgang_paa_andre_moduler(self):
        from accounts.forms import ModulTilgangForm
        bil = _konto('bil6', delt=True)
        skjema = ModulTilgangForm(bruker=bil)
        self.assertEqual([v for v, _ in skjema.fields['modul_patients'].choices], [''])
        self.assertIn('skriv_handling', [v for v, _ in skjema.fields['modul_oppdrag'].choices])

    def test_matrisen_avviser_ny_tilgang_postet_direkte(self):
        bil = _konto('bil7', delt=True)
        self._rediger(bil, modul_patients='les', modul_oppdrag='skriv_handling')
        self.assertEqual(self._rader(bil), {}, 'hele innsendingen avvist, ingenting lagret')

    def test_matrisen_gir_oppdrag_til_en_delt_konto(self):
        bil = _konto('bil8', delt=True)
        self._rediger(bil, modul_oppdrag='skriv_handling')
        self.assertEqual(self._rader(bil), {'oppdrag': 'skriv_handling'})

    def test_en_rad_fra_foer_regelen_kan_fjernes(self):
        bil = _konto('bil9', delt=True)
        _rader_utenom_save(bil, patients='les')
        self._rediger(bil, modul_patients='')
        self.assertEqual(self._rader(bil), {})

    def test_en_personlig_konto_med_pasienttilgang_kan_ikke_gjoeres_delt(self):
        person = _konto('nina', delt=False)
        ModulTilgang.objects.create(bruker=person, modul_slug='patients', nivaa='les')
        svar = self._rediger(person, er_delt_konto='on', modul_patients='les')
        person.refresh_from_db()
        self.assertFalse(person.er_delt_konto)
        self.assertContains(svar, 'fjern de andre i tilgangsmatrisen først')

    def test_kan_ikke_gjoeres_delt_og_faa_pasienttilgang_i_samme_lagring(self):
        """Flagget er ikke lagret når matrisen valideres — `blir_delt`."""
        person = _konto('tor', delt=False)
        self._rediger(person, er_delt_konto='on', modul_patients='les')
        person.refresh_from_db()
        self.assertFalse(person.er_delt_konto)
        self.assertEqual(self._rader(person), {})

    def test_ny_bil_kan_ikke_opprettes_med_pasienttilgang(self):
        """Opprettelsen: kontotypen settes i samme innsending som matrisen.
        Uten `blir_delt` godtok skjemaet, og `save()` ga 500."""
        svar = self.client.post(reverse('portaladmin:user_create'), {
            'username': 'bil10', 'kontotype': 'delt', 'metode': 'passord',
            'role': 'bruker', 'modul_patients': 'les',
        })
        self.assertEqual(svar.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='bil10').exists())


class VerifiserModultilgangTests(TestCase):
    def test_kommandoen_viser_rader_som_ikke_gir_noe(self):
        from io import StringIO

        from django.core.management import call_command
        bil = _konto('bil11', delt=True)
        _rader_utenom_save(bil, patients='les', oppdrag='skriv_handling')
        ut = StringIO()
        call_command('verifiser_modultilgang', stdout=ut)
        tekst = ut.getvalue()
        seksjon = tekst.split('Delte kontoer med rader som ikke gir noe')[1]
        self.assertIn('bil11: patients:les', seksjon)
        self.assertNotIn('bil11: oppdrag', seksjon)


class RegelfunksjonenTests(SimpleTestCase):
    def test_ukjent_modul_gir_nei(self):
        """Som et ukjent nivå: en skrivefeil i en slug skal stenge døra.
        Funnet ved mutasjon — ingen test gikk gjennom en ukjent slug."""
        from core.modules import delt_konto_kan_bruke
        self.assertFalse(delt_konto_kan_bruke('finnes-ikke'))
        self.assertTrue(delt_konto_kan_bruke('oppdrag'))
