"""Tester for ``ModulTilgang``, backfillen og ``@modul_kreves``.

Backfillen testes ved å kalle migrasjonens egen funksjon, ikke ved å gjenta
kartleggingen. En test som gjentar logikken ville bestått selv om migrasjonen
gjorde noe annet — og det er nettopp migrasjonen som skal kjøres mot prod.
"""
from importlib import import_module

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.apps import apps as django_apps
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from core.auth_decorators import (
    NIVAA_HIERARKI, er_global_admin, har_tilgang, modul_kreves, nivaa_for,
    tom_tilgangscache,
)
from core.models import ModuleSettings


def _bruker(navn, rolle='bruker', **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='testpass123', role=rolle,
        must_change_password=False, **kwargs,
    )


class BackfillTests(TestCase):
    """§8.1 — utledes fra `role` alene, aldri fra flagget.

    **Testene skriver rolleverdier feltet ikke lenger har.** `read_write` og
    `lead` forsvant i deploy 2, men migrasjon 0012 kjørte mot en database der
    de fantes, og det er den kjøringen som avgjorde hva kontoene i prod fikk.
    Skrev testene `bruker`, ville de bekreftet at backfillen ikke gjør noe —
    som er sant i dag og irrelevant. Django validerer ikke `choices` ved
    `save()`, så verdiene går inn slik de sto den gangen.
    """

    FASIT = {
        'read_only':  {('patients', 'les')},
        'read_write': {('patients', 'skriv_full')},
        'lead_view':  {('patients', 'les'), ('statistikk', 'les')},
        'lead':       {('patients', 'skriv_full'), ('statistikk', 'les')},
        'admin':      set(),
    }

    def _kjor_backfill(self):
        migrasjon = import_module('accounts.migrations.0012_fyll_modultilgang')
        migrasjon.fyll(django_apps, None)

    def _rader(self, bruker):
        return set(ModulTilgang.objects.filter(bruker=bruker)
                   .values_list('modul_slug', 'nivaa'))

    def test_hver_rolle_far_radene_fra_tabellen_i_notatet(self):
        brukere = {r: _bruker(f'bf_{r}', r) for r in self.FASIT}
        ModulTilgang.objects.all().delete()
        self._kjor_backfill()
        for rolle, fasit in self.FASIT.items():
            with self.subTest(rolle=rolle):
                self.assertEqual(self._rader(brukere[rolle]), fasit)

    def test_flagget_paavirker_ingenting(self):
        """To brukere med samme rolle og ulikt flagg skal få identiske rader.

        Utledet vi fra flagget, ville brukere som i dag *kan* nå modulen via
        URL-en mistet tilgangen i det håndhevelsen slås på — og en migrasjon
        som stille trekker tilbake tilgang oppdager du midt i en vakt.
        """
        med = _bruker('flagg_ja', 'read_write', kan_redigere_pasienter=True)
        uten = _bruker('flagg_nei', 'read_write', kan_redigere_pasienter=False)
        ModulTilgang.objects.all().delete()
        self._kjor_backfill()
        self.assertEqual(self._rader(med), self._rader(uten))
        self.assertEqual(self._rader(uten), {('patients', 'skriv_full')})

    def test_backfillen_kan_kjores_om_igjen(self):
        """Etter en rollback og ny fram skal andre forsøk ikke krasje."""
        bruker = _bruker('bf_igjen', 'lead')
        ModulTilgang.objects.all().delete()
        self._kjor_backfill()
        antall = ModulTilgang.objects.filter(bruker=bruker).count()
        self._kjor_backfill()
        self.assertEqual(ModulTilgang.objects.filter(bruker=bruker).count(), antall)

    def test_ingen_far_et_nivaa_som_ikke_finnes(self):
        for r in self.FASIT:
            _bruker(f'bf_nivaa_{r}', r)
        ModulTilgang.objects.all().delete()
        self._kjor_backfill()
        ukjente = set(ModulTilgang.objects.values_list('nivaa', flat=True)) - set(NIVAA_HIERARKI)
        self.assertEqual(ukjente, set())

    def test_reversering_tommer_tabellen(self):
        """Deploy 1 må kunne rulles tilbake.

        Trygt fordi `role` og de fem flaggene står urørt — fasiten finnes
        fortsatt. Det er nettopp derfor deploy 1 og 3 ikke kan slås sammen.
        """
        _bruker('bf_rev', 'lead')
        self._kjor_backfill()
        self.assertTrue(ModulTilgang.objects.exists())
        migrasjon = import_module('accounts.migrations.0012_fyll_modultilgang')
        migrasjon.tom(django_apps, None)
        self.assertFalse(ModulTilgang.objects.exists())


class NivaaTests(TestCase):
    """Stigen er ordnet: les < skriv_handling < skriv_full."""

    def setUp(self):
        self.bruker = _bruker('nivaa')

    def _sett(self, nivaa):
        ModulTilgang.objects.update_or_create(
            bruker=self.bruker, modul_slug='patients', defaults={'nivaa': nivaa},
        )
        tom_tilgangscache(self.bruker)

    def test_hoyere_nivaa_dekker_lavere(self):
        self._sett('skriv_full')
        for krav in ('les', 'skriv_handling', 'skriv_full'):
            with self.subTest(krav=krav):
                self.assertTrue(har_tilgang(self.bruker, 'patients', krav))

    def test_lavere_nivaa_dekker_ikke_hoyere(self):
        self._sett('les')
        self.assertTrue(har_tilgang(self.bruker, 'patients', 'les'))
        self.assertFalse(har_tilgang(self.bruker, 'patients', 'skriv_handling'))
        self.assertFalse(har_tilgang(self.bruker, 'patients', 'skriv_full'))

    def test_handling_dekker_ikke_full(self):
        """Hele poenget med `skriv: handling`: bil-kontoen stempler, men

        redigerer ikke fritekst. Kollapser de to, forsvinner nivået i praksis.
        """
        self._sett('skriv_handling')
        self.assertTrue(har_tilgang(self.bruker, 'patients', 'skriv_handling'))
        self.assertFalse(har_tilgang(self.bruker, 'patients', 'skriv_full'))

    def test_ingen_rad_er_ingen_tilgang(self):
        self.assertIsNone(nivaa_for(self.bruker, 'patients'))
        self.assertFalse(har_tilgang(self.bruker, 'patients', 'les'))

    def test_ukjent_nivaanavn_stenger(self):
        """En skrivefeil i en dekoratør skal stenge døra, ikke åpne den."""
        self._sett('skriv_full')
        self.assertFalse(har_tilgang(self.bruker, 'patients', 'skriv_alt'))

    def test_ukjent_modulslug_stenger(self):
        self._sett('skriv_full')
        self.assertFalse(har_tilgang(self.bruker, 'oppdrag', 'les'))

    def test_anonym_har_ingenting(self):
        self.assertFalse(har_tilgang(AnonymousUser(), 'patients', 'les'))
        self.assertFalse(er_global_admin(AnonymousUser()))


class GlobalAdminTests(TestCase):
    """Global admin står utenfor modulaksen."""

    def test_admin_har_alt_uten_rader(self):
        admin = _bruker('ga', 'admin')
        self.assertEqual(ModulTilgang.objects.filter(bruker=admin).count(), 0)
        for slug in ('patients', 'statistikk'):
            self.assertTrue(har_tilgang(admin, slug, 'skriv_full'))

    def test_admin_slipper_inn_i_deaktivert_modul(self):
        """Ellers kan man deaktivere seg selv ut av å kunne reaktivere."""
        ModuleSettings.objects.update_or_create(
            slug='patients', defaults={'enabled': False})
        self.assertTrue(har_tilgang(_bruker('ga2', 'admin'), 'patients', 'les'))

    def test_deaktivert_modul_stenger_for_andre(self):
        bruker = _bruker('deakt')
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='skriv_full')
        ModuleSettings.objects.update_or_create(
            slug='patients', defaults={'enabled': False})
        self.assertFalse(har_tilgang(bruker, 'patients', 'les'))


class CacheTests(TestCase):
    """Radene hentes én gang per brukerobjekt.

    Nav-menyen kaller `is_visible_for` én gang per registrert modul. Uten
    cachen ville hver sidevisning gjort én spørring per modul.
    """

    def test_gjentatte_oppslag_gir_en_spørring(self):
        bruker = _bruker('cache')
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='les')
        tom_tilgangscache(bruker)
        with self.assertNumQueries(2):  # tilganger + ModuleSettings
            for _ in range(10):
                har_tilgang(bruker, 'patients', 'les')

    def test_cachen_kan_tommes(self):
        bruker = _bruker('cache2')
        self.assertFalse(har_tilgang(bruker, 'patients', 'les'))
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='les')
        self.assertFalse(har_tilgang(bruker, 'patients', 'les'),
                         'uten tømming skal det gamle svaret stå')
        tom_tilgangscache(bruker)
        self.assertTrue(har_tilgang(bruker, 'patients', 'les'))


@override_settings(SECURE_SSL_REDIRECT=False)
class ModulKrevesDekoratorTests(TestCase):
    """Dekoratøren, ikke bare helperen den kaller."""

    def setUp(self):
        self.rf = RequestFactory()

    def _kall(self, bruker, nivaa='les', **kwargs):
        @modul_kreves('patients', nivaa, **kwargs)
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        request = self.rf.get('/pasienter/')
        request.user = bruker
        return view(request)

    def test_uten_tilgang_gir_403(self):
        with self.assertRaises(PermissionDenied):
            self._kall(_bruker('dek_uten'))

    def test_med_tilgang_slipper_gjennom(self):
        bruker = _bruker('dek_med')
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='les')
        self.assertEqual(self._kall(bruker).status_code, 200)

    def test_for_lavt_nivaa_gir_403(self):
        bruker = _bruker('dek_lav')
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='les')
        with self.assertRaises(PermissionDenied):
            self._kall(bruker, 'skriv_full')

    def test_json_variant_gir_lesbar_kropp(self):
        """Et API-kall skal få en kropp klienten kan lese, ikke 403-siden."""
        resp = self._kall(_bruker('dek_json'), svar='json')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('error', resp.content.decode())

    def test_uinnlogget_sendes_til_login_ikke_403(self):
        request = self.rf.get('/pasienter/')
        request.user = AnonymousUser()

        @modul_kreves('patients')
        def view(request):
            from django.http import HttpResponse
            return HttpResponse('ok')

        resp = view(request)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login', resp['Location'])

    def test_dekoratoren_setter_markoren_urltesten_leser(self):
        @modul_kreves('patients', 'skriv_full')
        def view(request):
            return None
        self.assertEqual(view._modul_kreves, ('patients', 'skriv_full'))


class OfflineBrukerTilgangTests(TestCase):
    """`vakt-offline` hadde `role='bruker'` og ingen rader.

    Udramatisk mens flaggene ikke gjorde noe. Med håndhevelse ser
    feltmaskinen en tom portal — og det oppdages i det den skal brukes, altså
    på en vakt uten nett.
    """

    def test_offline_brukerne_far_modultilgang(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('create_offline_users', stdout=StringIO())

        vakt = CustomUser.objects.get(username='vakt-offline')
        self.assertTrue(har_tilgang(vakt, 'patients', 'skriv_full'))

    def test_admin_offline_trenger_ingen_rader(self):
        """Global admin bruker ikke ModulTilgang. Tom liste er et valg."""
        from django.core.management import call_command
        from io import StringIO
        call_command('create_offline_users', stdout=StringIO())

        admin = CustomUser.objects.get(username='admin-offline')
        self.assertEqual(ModulTilgang.objects.filter(bruker=admin).count(), 0)
        self.assertTrue(har_tilgang(admin, 'patients', 'skriv_full'))


class VerifiserKommandoTests(TestCase):
    """`verifiser_modultilgang` — les-only kontroll av matrisen.

    Kommandoen mistet halvparten i deploy 2: sammenligningen mot `role` og
    §10.1-tellingen ble fjernet fordi begge ville svart grønt uansett når
    rolleverdiene de leste ikke lenger finnes. Det som testes her er det som
    er igjen, og det som er igjen skal aldri kunne bli grønt av seg selv —
    hver test har et motstykke som viser at funnet faktisk kan utebli.
    """

    def _kjor(self, **opts):
        from io import StringIO
        from django.core.management import call_command
        ut = StringIO()
        call_command('verifiser_modultilgang', stdout=ut, **opts)
        return ut.getvalue()

    def test_kommandoen_skriver_ingenting(self):
        bruker = _bruker('vk_uroert')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa='les')
        foer = set(ModulTilgang.objects.values_list('bruker_id', 'modul_slug', 'nivaa'))
        self._kjor()
        self.assertEqual(
            set(ModulTilgang.objects.values_list('bruker_id', 'modul_slug', 'nivaa')),
            foer, 'kontrollen skal være les-only')

    def test_konto_uten_rader_meldes(self):
        _bruker('vk_tom')
        self.assertIn('vk_tom', self._kjor())

    def test_admin_uten_rader_meldes_ikke(self):
        """Global admin trenger ingen rader — den er ikke et funn."""
        _bruker('vk_admin', 'admin')
        ut = self._kjor()
        self.assertIn('Kontoer uten en eneste ModulTilgang-rad', ut)
        self.assertNotIn('vk_admin', ut)

    def test_rad_paa_ukjent_modul_meldes(self):
        """En slug ingen modul har gir ingen tilgang, men ser ut som tilgang."""
        bruker = _bruker('vk_slug')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='pasienter', nivaa='les')
        ut = self._kjor()
        self.assertIn('vk_slug: pasienter:les', ut)

    def test_kjent_modul_meldes_ikke(self):
        """Vern mot at slug-testen passerer fordi alt meldes."""
        bruker = _bruker('vk_ok')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa='les')
        ut = self._kjor()
        self.assertIn('Rader på en modul som ikke finnes i registeret\n  Ingen.', ut)

    def test_ukjent_nivaa_meldes(self):
        """Et nivå stigen ikke kjenner stenger døra — stille, uten denne."""
        bruker = _bruker('vk_nivaa')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa='skriv')
        self.assertIn('vk_nivaa: patients:skriv', self._kjor())

    def test_ukjent_rolle_meldes(self):
        """En rad deploy 2 ikke fikk tak i."""
        bruker = _bruker('vk_rolle')
        CustomUser.objects.filter(pk=bruker.pk).update(role='lead')
        self.assertIn('vk_rolle (lead)', self._kjor())

    def test_krympet_rolle_meldes_ikke(self):
        """Vern mot at rolletesten passerer fordi alle meldes."""
        _bruker('vk_bruker')
        ut = self._kjor()
        self.assertIn('rolleverdi feltet ikke kjenner\n  Ingen.', ut)

    def test_vis_alle_lister_radene(self):
        bruker = _bruker('vk_liste')
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa='skriv_full')
        self.assertIn('patients:skriv_full', self._kjor(**{'vis_alle': True}))


class UkjentRolleTests(TestCase):
    """En ukjent rolle skal ikke låse noen ute i stillhet.

    Fail-closed er riktig — vi gjetter ikke på hva rollen skulle betydd — men
    utfallet er en konto uten en eneste modul, og det eneste sporet ville vært
    en bruker som ringer. Advarselen havner i deploy-loggen.
    """

    def _kjor_backfill(self):
        from importlib import import_module
        from django.apps import apps as django_apps
        import_module('accounts.migrations.0012_fyll_modultilgang').fyll(
            django_apps, None)

    def test_ukjent_rolle_gir_ingen_rader_og_en_advarsel(self):
        import io
        import contextlib

        bruker = _bruker('ur_rar')
        CustomUser.objects.filter(pk=bruker.pk).update(role='vaktleder_2019')
        ModulTilgang.objects.all().delete()

        ut = io.StringIO()
        with contextlib.redirect_stdout(ut):
            self._kjor_backfill()

        self.assertEqual(ModulTilgang.objects.filter(bruker=bruker).count(), 0)
        self.assertIn('ADVARSEL', ut.getvalue())
        self.assertIn('ur_rar', ut.getvalue())
        self.assertIn('vaktleder_2019', ut.getvalue())

    def test_kjent_rolle_gir_ingen_advarsel(self):
        """Vern mot at advarselen alltid skrives."""
        import io
        import contextlib

        _bruker('ur_vanlig', 'read_write')
        ModulTilgang.objects.all().delete()
        ut = io.StringIO()
        with contextlib.redirect_stdout(ut):
            self._kjor_backfill()
        self.assertNotIn('ADVARSEL', ut.getvalue())
