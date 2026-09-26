"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — innlogging og kontoer.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
from datetime import timedelta

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import CustomUser, LoginEvent
from accounts.test_helpers import gi_standardtilgang
from accounts.tests_mfa import _make_totp_code


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UtloggingRydderTests(TestCase):
    """H4: «Logg ut» er det som rydder drifts-PC-en."""

    def test_clear_site_data(self):
        b = CustomUser.objects.create_user(username='ut', password='x', must_change_password=False)
        c = Client(); c.force_login(b)
        res = c.post(reverse('accounts:logout'))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res['Clear-Site-Data'], '"cache", "storage"')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KontolaasOgMfaTests(TestCase):
    """M1: riktig passord nullstiller ikke telleren før MFA er bestått."""

    def setUp(self):
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='mfalaas', password='TestPassord123!', role='admin',
            must_change_password=False, mfa_required=True)
        gi_standardtilgang(self.user, 'admin')
        self.device = TOTPDevice.objects.create(user=self.user, name='T', confirmed=True)

    def test_passordsteget_lar_telleren_staa(self):
        self.user.failed_login_attempts = 4
        self.user.save(update_fields=['failed_login_attempts'])
        c = Client()
        c.post(self.url, {'username': 'mfalaas', 'password': 'TestPassord123!'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 4, 'MFA gjenstår')
        # Ett feil MFA-forsøk til låser kontoen.
        c.post(self.url, {'totp_code': '000000'})
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.locked_until)

    def test_mfa_bestaatt_nullstiller(self):
        self.user.failed_login_attempts = 3
        self.user.save(update_fields=['failed_login_attempts'])
        c = Client()
        c.post(self.url, {'username': 'mfalaas', 'password': 'TestPassord123!'})
        res = c.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.assertEqual(res.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.locked_until)

    def test_uten_mfa_nullstiller_passordet_som_foer(self):
        b = CustomUser.objects.create_user(username='utenmfa', password='TestPassord123!',
                                           must_change_password=False, failed_login_attempts=2)
        Client().post(self.url, {'username': 'utenmfa', 'password': 'TestPassord123!'})
        b.refresh_from_db()
        self.assertEqual(b.failed_login_attempts, 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InnloggingValidererSkjemaetTests(TestCase):
    """M2: et brukernavn over 64 tegn skal ikke nå databasen."""

    def test_for_langt_brukernavn_gir_vanlig_feil(self):
        res = Client().post(reverse('accounts:login'), {'username': 'x' * 70, 'password': 'y'})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Feil brukernavn eller passord')
        self.assertEqual(LoginEvent.objects.count(), 0)

    def test_innloggingsloggen_faar_proxyens_ip(self):
        """H2 på innloggingsloggen."""
        Client().post(reverse('accounts:login'), {'username': 'finnesikke', 'password': 'y'},
                      HTTP_X_FORWARDED_FOR='6.6.6.6, 5.6.7.8', REMOTE_ADDR='10.0.0.1')
        self.assertEqual(LoginEvent.objects.get().ip, '5.6.7.8')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MfaStegKreverAktivKontoTests(TestCase):
    """L5: en frosset konto kommer ikke gjennom MFA-steget."""

    def test_inaktiv_i_verifiseringssteget(self):
        u = CustomUser.objects.create_user(username='frys', password='TestPassord123!',
                                           must_change_password=False, mfa_required=True)
        d = TOTPDevice.objects.create(user=u, name='T', confirmed=True)
        c = Client()
        c.post(reverse('accounts:login'), {'username': 'frys', 'password': 'TestPassord123!'})
        u.is_active = False
        u.save(update_fields=['is_active'])
        res = c.post(reverse('accounts:login'), {'totp_code': _make_totp_code(d)})
        self.assertEqual(res.status_code, 302)
        self.assertNotIn('_auth_user_id', c.session)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RedigerAdminTests(TestCase):
    """M7: «Rediger» kan ikke ta admin-rollen fra deg selv eller siste admin,
    og `is_active` er ikke i skjemaet."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(username='adm_r', password='x', role='admin',
                                                    must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.c = Client(); self.c.force_login(self.admin)

    def _rediger(self, bruker, rolle):
        return self.c.post(reverse('portaladmin:user_detail', kwargs={'pk': bruker.pk}),
                           {'action': 'edit', 'role': rolle})

    def test_ikke_seg_selv(self):
        self._rediger(self.admin, 'bruker')
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_annen_admin_kan_degradere(self):
        annen = CustomUser.objects.create_user(username='adm2', password='x', role='admin',
                                               must_change_password=False)
        self._rediger(annen, 'bruker')
        annen.refresh_from_db()
        self.assertEqual(annen.role, 'bruker', 'det finnes en admin igjen')

    def test_siste_admin_sperres_i_hjelperen(self):
        """Gjennom viewet er «siste admin» alltid også «deg selv» (den som
        redigerer er admin). Hjelperen skal likevel svare riktig på egen hånd."""
        from accounts.views import _kan_degraderes
        ikke_admin = CustomUser.objects.create_user(username='b_x', password='x', must_change_password=False)
        self.assertIn('siste', _kan_degraderes(self.admin, ikke_admin, 'bruker', 'admin'))
        self.assertEqual(_kan_degraderes(self.admin, ikke_admin, 'admin'), '')
        self.assertEqual(_kan_degraderes(ikke_admin, self.admin, 'bruker'), '', 'ikke admin fra før')

    def test_is_active_ikke_i_skjemaet(self):
        from accounts.forms import AdminUserEditForm
        self.assertNotIn('is_active', AdminUserEditForm(instance=self.admin).fields)
        annen = CustomUser.objects.create_user(username='b_r', password='x', must_change_password=False)
        self.c.post(reverse('portaladmin:user_detail', kwargs={'pk': annen.pk}),
                    {'action': 'edit', 'role': 'bruker', 'is_active': ''})
        annen.refresh_from_db()
        self.assertTrue(annen.is_active, 'frys/tø er veien')

    def test_midlertidig_passord_caches_ikke(self):
        """L11."""
        annen = CustomUser.objects.create_user(username='b_nc', password='x', must_change_password=False)
        res = self.c.get(reverse('portaladmin:user_detail', kwargs={'pk': annen.pk}))
        self.assertIn('no-store', res.get('Cache-Control', ''))
        res = self.c.get(reverse('portaladmin:user_create'))
        self.assertIn('no-store', res.get('Cache-Control', ''))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PassordbytteOgSesjonsnokkelTests(TestCase):
    """M11: `current_session_key` peker på sesjonen som finnes etter byttet."""

    def test_nokkelen_er_den_roterte(self):
        u = CustomUser.objects.create_user(username='pb', password='GammeltPassord123!',
                                           must_change_password=False)
        c = Client()
        c.login(username='pb', password='GammeltPassord123!')
        res = c.post(reverse('accounts:change_password'), {
            'old_password': 'GammeltPassord123!',
            'new_password1': 'NyttSterktPassord456!', 'new_password2': 'NyttSterktPassord456!'})
        self.assertEqual(res.status_code, 302, res.content)
        u.refresh_from_db()
        self.assertEqual(u.current_session_key, c.session.session_key)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SuperbrukerenErNodutgangenTests(TestCase):
    """`is_superuser` kan ikke fratas admin-rollen (André, 15. sep. 2026).

    **Hvorfor flagget, og ikke rollen.** `is_superuser` og `is_staff` betyr
    ingenting for portalen: tilgang er `role == 'admin'` og `ModulTilgang`,
    og de to Django-flaggene gjelder bare `/django-admin/`, som er rutet av i
    produksjon (S1). De settes derfor bare av `manage.py create_admin`, og
    **følger bevisst ikke med** når noen gjøres til administrator gjennom
    brukeradministrasjonen — det var André sin observasjon, og den er riktig.

    Det gjør kontoen til noe annet enn «en administrator til»: den er den ene
    man kommer tilbake inn med. «Siste admin»-sperra dekker den ikke — er det
    tre administratorer, kan superbrukeren degraderes uten at noe protesterer,
    og da er nødutgangen borte mens portalen ser helt normal ut.
    """

    def setUp(self):
        self.super = CustomUser.objects.create_user(
            username='rot', password='x', role='admin',
            must_change_password=False, is_staff=True, is_superuser=True)
        gi_standardtilgang(self.super, 'admin')
        self.admin = CustomUser.objects.create_user(
            username='adm_s', password='x', role='admin',
            must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.c = Client()
        self.c.force_login(self.admin)

    def test_superbrukeren_beholder_admin_selv_om_det_finnes_andre(self):
        """Den ene testen «siste admin» ikke ville fanget: her *er* det en
        admin igjen, så den gamle sperra sier ja."""
        self.c.post(reverse('portaladmin:user_detail',
                            kwargs={'pk': self.super.pk}),
                    {'action': 'edit', 'role': 'bruker'})
        self.super.refresh_from_db()
        self.assertEqual(self.super.role, 'admin')

    def test_hjelperen_sier_hvorfor(self):
        from accounts.views import _kan_degraderes
        grunn = _kan_degraderes(self.super, self.admin, 'bruker', 'admin')
        self.assertIn('superbruker', grunn.lower())

    def test_en_vanlig_admin_kan_fortsatt_degraderes(self):
        """Den andre retningen. Sperrer flagget for mye, blir hver admin
        udegraderbar — og det ville vært like galt, bare stillere."""
        from accounts.views import _kan_degraderes
        self.assertEqual(
            _kan_degraderes(self.admin, self.super, 'bruker', 'admin'), '')

    def test_den_slettes_ikke_heller(self):
        """En regel som sperrer degradering, men slipper sletting, verner
        ingenting: sletting tar kontoen og ikke bare rollen."""
        from accounts.views import _kan_slettes
        kan, grunn = _kan_slettes(self.super, self.admin)
        self.assertFalse(kan)
        self.assertIn('superbruker', grunn.lower())

        res = self.c.post(reverse('portaladmin:user_delete',
                                  kwargs={'pk': self.super.pk}))
        self.assertTrue(CustomUser.objects.filter(pk=self.super.pk).exists())
        self.assertIn(res.status_code, (302, 403))

    def test_frysing_staar_igjen_med_vilje(self):
        """**Grensen er om handlingen lar seg reversere.** Frysing er det —
        «Tø konto» står ved siden av — og en annen administrator kan alltid
        tine kontoen. Degradering og sletting er det ikke."""
        self.c.post(reverse('portaladmin:user_detail',
                            kwargs={'pk': self.super.pk}), {'action': 'freeze'})
        self.super.refresh_from_db()
        self.assertFalse(self.super.is_active)
        self.assertEqual(self.super.role, 'admin', 'rollen står, kontoen er tint tilbake')

    # ── Rollen er låst i skjemaet, ikke bare i viewet ────────────────────
    def test_rollevalget_er_laast_paa_superbrukeren(self):
        """**Et nedtrekk man kan velge i og som så gir en feilmelding, er en
        kontroll som fører til en vegg.** Django-feltets `disabled` gjør to
        ting i én: nedtrekket tegnes grått, og innsendt verdi forkastes."""
        from accounts.forms import SUPERBRUKER_LAAST, AdminUserEditForm
        skjema = AdminUserEditForm(instance=self.super)
        self.assertTrue(skjema.fields['role'].disabled)
        self.assertEqual(skjema.fields['role'].help_text, SUPERBRUKER_LAAST)

    def test_en_vanlig_admin_har_valget_i_behold(self):
        """Den andre retningen: låses feltet for alle, kan ingen degraderes."""
        from accounts.forms import AdminUserEditForm
        self.assertFalse(AdminUserEditForm(instance=self.admin).fields['role'].disabled)

    def test_skjemaet_forkaster_innsendt_rolle(self):
        """Laget under viewets sperre. Fjernes `_kan_degraderes`, skal
        skjemaet fortsatt stå — og omvendt."""
        from accounts.forms import AdminUserEditForm
        skjema = AdminUserEditForm({'role': 'bruker'}, instance=self.super)
        self.assertTrue(skjema.is_valid(), skjema.errors)
        self.assertEqual(skjema.cleaned_data['role'], 'admin')

    def test_nytt_skjema_har_valget(self):
        """`disabled` settes på en *lagret* superbruker. Uten `instance.pk`
        ville opprettelsesskjemaet kunne miste rollevalget sitt."""
        from accounts.forms import AdminUserEditForm
        self.assertFalse(AdminUserEditForm().fields['role'].disabled)


class SuperbrukerenErEnKontoTests(TestCase):
    """`create_admin` lager ikke superbruker nummer to (15. sep. 2026).

    Kommandoen er idempotent på *brukernavn*, så den laget en superbruker til
    hver gang den ble kjørt med et nytt navn. Da er «bootstrap-kontoen» ikke
    lenger én konto, men en kategori — og sperrene mot degradering og sletting
    verner en nødutgang det finnes flere av, altså ingenting.
    """

    def _kjor(self, navn):
        from io import StringIO

        from django.core.management import call_command
        ut = StringIO()
        call_command('create_admin', username=navn, password='hemmelig-123',
                     stdout=ut, stderr=ut)
        return ut.getvalue()

    def test_den_forste_opprettes(self):
        self._kjor('rot1')
        u = CustomUser.objects.get(username='rot1')
        self.assertTrue(u.is_superuser)
        self.assertEqual(u.role, 'admin')

    def test_den_andre_avvises_med_navnet_paa_den_forste(self):
        from django.core.management.base import CommandError
        self._kjor('rot1')
        with self.assertRaises(CommandError) as ctx:
            self._kjor('rot2')
        self.assertIn('rot1', str(ctx.exception), 'skal si hvem som har plassen')
        self.assertFalse(CustomUser.objects.filter(username='rot2').exists())

    def test_samme_navn_er_fortsatt_idempotent(self):
        """Kommandoen kjøres ved oppstart. Blir den en feil ved andre kjøring,
        knekker den deployen den skulle hjelpe."""
        self._kjor('rot1')
        ut = self._kjor('rot1')
        self.assertIn('finnes allerede', ut)

    def test_vanlige_administratorer_er_ikke_i_veien(self):
        """Sperra gjelder superbrukere, ikke admins. Leser den `role`, kan
        bootstrap aldri kjøres på en portal som alt har en administrator."""
        CustomUser.objects.create_user(username='adm_v', password='x',
                                       role='admin', must_change_password=False)
        self._kjor('rot1')
        self.assertTrue(CustomUser.objects.get(username='rot1').is_superuser)


class RollenSettesBareGjennomSkjemaeneTests(SimpleTestCase):
    """Ingen kode skriver `role` utenom skjemaene og `create_superuser`.

    **Sperrene over ligger i skjemaet og i viewet.** De verner nøyaktig den
    veien som finnes i dag. Skriver noen `user.role = 'bruker'` i et nytt
    endepunkt — en importjobb, en invitasjon, en opprydding — går den utenom
    begge, og superbrukeren kan degraderes igjen uten at én test blir rød.

    Det er samme sort regel som `SignalerFyrerIkkeUnderLoaddataTests`: den
    leter, den leser ikke en liste noen må huske å vedlikeholde.
    """

    #: Skrivinger som er lov, med begrunnelse. Lista skal ikke vokse uten at
    #: noen har tenkt på superbrukeren.
    UNNTATT: dict[str, str] = {}

    #: Feltene regelen gjelder. `is_superuser` kom med 26. sep. 2026 (B4): å
    #: lage en superbruker nummer to er den andre veien rundt sperrene.
    FELT = frozenset({'role', 'is_superuser'})

    #: Filene der skjemaene med sperrene bor — der *skal* `role` stå i
    #: `Meta.fields`. `is_superuser` står ikke i noen av dem.
    SKJEMAENE = frozenset({'accounts/forms.py'})

    def test_ingen_skriver_role_utenfor_skjemaene(self):
        import ast
        from pathlib import Path

        from django.conf import settings

        rot = Path(settings.BASE_DIR)
        funn = []
        for sti in sorted(rot.glob('*/**/*.py')):
            rel = sti.relative_to(rot).as_posix()
            if ('/migrations/' in rel or '/tests' in rel or rel.startswith('.')
                    or '/site-packages/' in rel or rel in self.UNNTATT):
                continue
            try:
                tre = ast.parse(sti.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tre):
                if isinstance(node, ast.Assign):
                    for mal in node.targets:
                        if isinstance(mal, ast.Attribute) and mal.attr in self.FELT:
                            funn.append(f'{rel}:{node.lineno}')
                elif isinstance(node, ast.Call):
                    # `.update(role=…)` og `setattr(x, 'role', …)` — samme skriving,
                    # en annen form. Regelen dekket bare `x.role = …` til 26. sep.
                    # 2026 (B4), og slapp dem gjennom.
                    navn = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
                    if navn == 'update' and any(k.arg in self.FELT for k in node.keywords):
                        funn.append(f'{rel}:{node.lineno}')
                    if (navn == 'setattr' and len(node.args) > 1
                            and isinstance(node.args[1], ast.Constant)
                            and node.args[1].value in self.FELT):
                        funn.append(f'{rel}:{node.lineno}')
                elif (isinstance(node, ast.ClassDef) and node.name == 'Meta'
                      and rel not in self.SKJEMAENE):
                    # Et `ModelForm` med feltet i `Meta.fields` skriver det ved
                    # `save()` — som Django-admins egne skjemaer gjorde (B4).
                    for setning in node.body:
                        if (isinstance(setning, ast.Assign)
                                and any(getattr(t, 'id', '') == 'fields' for t in setning.targets)
                                and isinstance(setning.value, (ast.Tuple, ast.List))
                                and any(isinstance(e, ast.Constant) and e.value in self.FELT
                                        for e in setning.value.elts)):
                            funn.append(f'{rel}:{setning.lineno}')
        self.assertEqual(
            funn, [],
            'Disse stedene skriver `.role` direkte, utenom skjemaene:\n  '
            + '\n  '.join(funn)
            + '\n\nSuperbrukeren kan da degraderes uten å gå gjennom '
              'AdminUserEditForm eller _kan_degraderes. Gå gjennom skjemaet, '
              'eller før stedet opp i UNNTATT med begrunnelse.')

    def test_vi_leter_faktisk_i_filer(self):
        """Sperrehake: treffer globben ingenting, går testen over grønn mens
        den måler nøyaktig null."""
        from pathlib import Path

        from django.conf import settings
        rot = Path(settings.BASE_DIR)
        antall = len([s for s in rot.glob('*/**/*.py')
                      if '/migrations/' not in s.as_posix()])
        self.assertGreater(antall, 50, f'fant bare {antall} filer')


class DjangoAdminErSkrivebeskyttetTests(SimpleTestCase):
    """Kontoene og innloggingsloggen kan ses i Django-admin, ikke endres
    (26. sep. 2026, B4 — André: «skrivebeskyttet»). Prøvd med en superbruker,
    som er den ene som ellers slipper gjennom alt."""

    def test_ingen_kan_legge_til_endre_eller_slette(self):
        from django.contrib import admin
        from django.test import RequestFactory

        from accounts.models import CustomUser, LoginEvent

        request = RequestFactory().get('/django-admin/')
        request.user = CustomUser(username='su', is_superuser=True, is_staff=True, is_active=True)
        for modell in (CustomUser, LoginEvent):
            modeladmin = admin.site._registry[modell]
            with self.subTest(modell=modell.__name__):
                self.assertFalse(modeladmin.has_add_permission(request))
                self.assertFalse(modeladmin.has_change_permission(request))
                self.assertFalse(modeladmin.has_delete_permission(request))
                self.assertTrue(modeladmin.has_view_permission(request), 'å se skal gå')
