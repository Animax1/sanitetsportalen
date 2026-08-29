"""Tester for vaktlistemodulen — fase 1.

Det som testes er det fasen faktisk lovet: registrene finnes og håndhever
sine regler, mannskapet bærer badgen, audit-unntaket for `notat` virker fra
første lagring, og modulen er registrert uten å være synlig — den har ingen
side ennå.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from audit.models import AuditLog
from core.modules import get_module, get_visible_modules

from .models import Kompetanse, Korps, Mannskap, VaktRolle
from .signals import SKJULT, TABELLNAVN

User = get_user_model()


class RegisterTests(TestCase):
    def test_korpsnavn_er_unikt(self):
        Korps.objects.create(navn='Haugesund')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Korps.objects.create(navn='Haugesund')

    def test_rekkefolge_styrer_sortering(self):
        """Rekkefølgen er visningsrekkefølgen i lister og faner."""
        b = Korps.objects.create(navn='Bokn', rekkefolge=200)
        a = Korps.objects.create(navn='Karmøy', rekkefolge=50)
        self.assertEqual(list(Korps.objects.all()), [a, b])

    def test_kompetanse_og_rolle_er_egne_registre(self):
        """Kompetansen følger personen, rollen følger vaktposten (fase 2).
        Én tabell for begge ville tvunget «Sykepleier» og «Lagleder» inn i
        samme liste, der de svarer på hver sitt spørsmål."""
        Kompetanse.objects.create(navn='Sykepleier')
        VaktRolle.objects.create(navn='Lagleder')
        self.assertEqual(Kompetanse.objects.count(), 1)
        self.assertEqual(VaktRolle.objects.count(), 1)


class MannskapTests(TestCase):
    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')

    def test_navn_er_unikt_per_korps_ikke_globalt(self):
        annet = Korps.objects.create(navn='Karmøy')
        Mannskap.objects.create(navn='Ola Hansen', korps=self.korps)
        # To korps kan ha hver sin Ola Hansen …
        Mannskap.objects.create(navn='Ola Hansen', korps=annet)
        # … men ikke samme korps to ganger.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mannskap.objects.create(navn='Ola Hansen', korps=self.korps)

    def test_korps_med_mannskap_kan_ikke_slettes(self):
        """PROTECT: badgen skal ikke kunne rives bort under folkene."""
        Mannskap.objects.create(navn='Kari', korps=self.korps)
        with self.assertRaises(ProtectedError):
            self.korps.delete()

    def test_slettet_konto_lar_personen_staa(self):
        """SET_NULL — samme valg som Enhet.user og Forstehjelper.user."""
        bruker = User.objects.create_user(
            username='kari', password='x', must_change_password=False)
        person = Mannskap.objects.create(
            navn='Kari', korps=self.korps, user=bruker)
        bruker.delete()
        person.refresh_from_db()
        self.assertIsNone(person.user)
        self.assertEqual(person.navn, 'Kari')

    def test_str_bruker_kortnavnet(self):
        person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        self.assertEqual(str(person), 'Kari (HGSD)')


class AuditTests(TestCase):
    """Unntaket for `notat` — bygget inn fra første lagring, som i oppdrag."""

    def setUp(self):
        self.korps = Korps.objects.create(navn='Haugesund')
        self.person = Mannskap.objects.create(
            navn='Kari', korps=self.korps, telefon='90000000')
        AuditLog.objects.all().delete()

    def _rader(self, felt=None):
        qs = AuditLog.objects.filter(table_name=TABELLNAVN)
        if felt is not None:
            qs = qs.filter(field_name=felt)
        return list(qs)

    def test_vanlig_felt_logges_med_verdier(self):
        self.person.telefon = '91111111'
        self.person.save()
        rad = self._rader('telefon')[0]
        self.assertEqual(rad.old_value, '90000000')
        self.assertEqual(rad.new_value, '91111111')

    def test_notat_logges_uten_verdier(self):
        """Selve fase 1-kravet: at feltet ble endret spores, innholdet ikke."""
        self.person.notat = 'Har nøtteallergi'   # akkurat det som IKKE skal lagres
        self.person.save()
        rader = self._rader('notat')
        self.assertEqual(len(rader), 1, 'endringen skal gi en rad')
        self.assertEqual(rader[0].old_value, SKJULT)
        self.assertEqual(rader[0].new_value, SKJULT)
        # Og innholdet finnes ikke i NOEN auditrad.
        self.assertFalse(AuditLog.objects.filter(
            new_value__icontains='nøtteallergi').exists())

    def test_uendret_notat_gir_ingen_rad(self):
        """Skjult verdi må sammenlignes rått — ellers gir hver lagring en
        falsk «endret»-rad, siden (skjult) == (skjult) aldri kan skille."""
        self.person.telefon = '92222222'
        self.person.save()
        self.assertEqual(len(self._rader('notat')), 0)

    def test_deaktivering_logges(self):
        """`False` skal ikke kollapse til tom streng — feilen som kostet
        pasientmodulen at deaktiveringer aldri ble logget riktig."""
        self.person.er_aktiv = False
        self.person.save()
        rad = self._rader('er_aktiv')[0]
        self.assertEqual(rad.old_value, 'True')
        self.assertEqual(rad.new_value, 'False')

    def test_opprettelse_og_sletting_logges(self):
        ny = Mannskap.objects.create(navn='Ola', korps=self.korps)
        self.assertEqual(
            AuditLog.objects.filter(
                table_name=TABELLNAVN, action='CREATE', record_id=ny.pk
            ).count(), 1)
        ny.delete()
        self.assertEqual(
            AuditLog.objects.filter(
                table_name=TABELLNAVN, action='DELETE').count(), 1)


class ModulRegistreringTests(TestCase):
    """Fra fase 3 er modulen åpen for nivåene, ikke bare for global admin.

    Gjennom fase 1 sto den med `url=None` og begge `show_*`-flagg av — et
    modulkort som fører til 404 er en knapp som fører til en vegg. Fase 2 ga
    den side, men `admin_only` holdt de andre ute til objektsjekkene fantes.
    Nå finnes de, og flagget er av.
    """

    def test_modulen_peker_paa_siden_sin(self):
        modul = get_module('vaktliste')
        self.assertIsNotNone(modul, 'vaktliste mangler i core.modules')
        self.assertEqual(modul.url, '/vaktliste/')
        self.assertTrue(modul.show_in_nav)
        self.assertTrue(modul.show_in_dashboard)
        self.assertFalse(modul.admin_only, 'åpnet i fase 3')

    def test_nivaaene_er_deklarert(self):
        self.assertEqual(
            get_module('vaktliste').nivaaer,
            ('les', 'skriv_handling', 'skriv_full'))

    def test_admin_ser_modulen(self):
        admin = User.objects.create_user(
            username='vl_admin', password='x', role='admin',
            must_change_password=False)
        self.assertIn('vaktliste',
                      [m.slug for m in get_visible_modules(admin)])

    def test_konto_med_nivaa_ser_modulen(self):
        from accounts.models import ModulTilgang
        bruker = User.objects.create_user(
            username='vl_leser', password='x', must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='vaktliste', nivaa='les')
        self.assertIn('vaktliste',
                      [m.slug for m in get_visible_modules(bruker)])

    def test_konto_uten_rad_ser_den_ikke(self):
        """Fravær av rad er ingen tilgang — det finnes ingen «ingen»-verdi."""
        bruker = User.objects.create_user(
            username='vl_utenfor', password='x', must_change_password=False)
        self.assertNotIn('vaktliste',
                         [m.slug for m in get_visible_modules(bruker)])
