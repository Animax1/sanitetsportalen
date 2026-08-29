"""Tester for portalens brukeradministrasjon (/accounts/users/).

Disse dekker funksjonaliteten som må være på plass før `/django-admin/` kan
fjernes (S1 i kodegjennomgangen aug. 2026): opprettelse, MFA-toggle, frys/tø
og permanent sletting.

Kjør med: python manage.py test accounts.tests_user_admin
"""
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from audit.models import AuditLog
from accounts.test_helpers import gi_standardtilgang


def _create_session_for_user(user):
    """Opprett en aktiv databasesesjon koblet til brukeren."""
    store = SessionStore()
    store['_auth_user_id'] = str(user.pk)
    store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    store['_auth_user_hash'] = user.get_session_auth_hash()
    store.save()
    return store.session_key


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminUserCreateEmailTests(TestCase):
    """Regresjon: tom e-post ga 500 ved opprettelse av bruker.

    Modellfeltet er null=True, så ModelForm setter empty_value=None på
    skjemafeltet. clean_email() antok tom streng og kalte .strip() på None.
    """

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='create_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

    def test_oppretting_uten_epost(self):
        resp = self.client.post(reverse('accounts:user_create'), {
            'kontotype': 'person',
            'username': 'utenepost',
            'email': '',
            'role': 'bruker',
        })
        self.assertEqual(resp.status_code, 200)
        ny = CustomUser.objects.get(username='utenepost')
        self.assertIsNone(ny.email)
        self.assertTrue(ny.must_change_password)

    def test_oppretting_med_epost(self):
        """E-post trimmes ved oppretting, og utløser en invitasjon.

        Statuskoden er 302 og ikke 200 fordi personlige kontoer med e-post nå
        går invitasjonsveien og sendes videre til brukersiden. Selve poenget
        med testen — at adressen normaliseres — er uendret.
        """
        from django.core import mail

        resp = self.client.post(reverse('accounts:user_create'), {
            'kontotype': 'person',
            'username': 'medepost',
            'email': '  post@eksempel.no  ',
            'role': 'bruker',
        })
        self.assertEqual(resp.status_code, 302)
        ny = CustomUser.objects.get(username='medepost')
        self.assertEqual(ny.email, 'post@eksempel.no')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['post@eksempel.no'])

    def test_to_brukere_uten_epost_kolliderer_ikke(self):
        """unique_email_if_set skal tillate flere NULL samtidig."""
        for navn in ['tom1', 'tom2']:
            resp = self.client.post(reverse('accounts:user_create'), {
                'kontotype': 'person',
                'username': navn, 'email': '', 'role': 'bruker',
            })
            self.assertEqual(resp.status_code, 200)
        # tom1, tom2 og create_admin har alle NULL e-post
        self.assertEqual(CustomUser.objects.filter(email__isnull=True).count(), 3)


@override_settings(SECURE_SSL_REDIRECT=False)
class MfaRequiredEditTests(TestCase):
    """mfa_required skal kunne slås både på og av fra portalen."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='mfa_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.target = CustomUser.objects.create_user(
            username='mfa_target', password='x', role='bruker',
            must_change_password=False, mfa_required=False,
        )
        gi_standardtilgang(self.target, 'leser')
        self.client.force_login(self.admin)

    def test_form_inneholder_mfa_required(self):
        from accounts.forms import AdminUserEditForm
        self.assertIn('mfa_required', AdminUserEditForm(instance=self.target).fields)

    def test_kan_sla_paa_mfa(self):
        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.post(url, {
            'action': 'edit', 'role': 'bruker',
            'is_active': 'on', 'mfa_required': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.mfa_required)

    def test_kan_sla_av_mfa(self):
        """Uten denne veien var Nullstill MFA en enveisbillett."""
        self.target.mfa_required = True
        self.target.save(update_fields=['mfa_required'])

        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.post(url, {
            'action': 'edit', 'role': 'bruker', 'is_active': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertFalse(self.target.mfa_required)

    def test_template_viser_mfa_avkrysning(self):
        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.get(url)
        self.assertContains(resp, 'name="mfa_required"')


@override_settings(SECURE_SSL_REDIRECT=False)
class FreezeThawPortalTests(TestCase):
    """Frys/tø fra portalens brukerdetalj (paritet med django-admin-aksjonen)."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='fz_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.target = CustomUser.objects.create_user(
            username='fz_target', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.target, 'skriver')
        self.client.force_login(self.admin)

    def _post(self, action, pk=None):
        url = reverse('accounts:user_detail', kwargs={'pk': pk or self.target.pk})
        return self.client.post(url, {'action': action})

    def test_frys_deaktiverer_og_sletter_sesjoner(self):
        key = _create_session_for_user(self.target)
        self.assertTrue(Session.objects.filter(session_key=key).exists())

        resp = self._post('freeze')
        self.assertEqual(resp.status_code, 302)

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_frys_skriver_auditlog(self):
        self._post('freeze')
        rad = AuditLog.objects.filter(
            table_name='accounts_customuser', record_id=self.target.pk,
        ).latest('created_at')
        self.assertEqual(rad.action, 'UPDATE')
        self.assertEqual(rad.field_name, 'is_active')
        self.assertEqual(rad.new_value, 'False')
        self.assertEqual(rad.user, self.admin)
        self.assertEqual(rad.app_label, 'accounts')

    def test_kan_ikke_fryse_seg_selv(self):
        resp = self._post('freeze', pk=self.admin.pk)
        self.assertEqual(resp.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_to_reaktiverer(self):
        self.target.is_active = False
        self.target.save(update_fields=['is_active'])

        resp = self._post('thaw')
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)


@override_settings(SECURE_SSL_REDIRECT=False)
class UserDeleteTests(TestCase):
    """Permanent sletting av brukerkonto fra portalen."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='del_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        # En admin til, slik at «siste admin»-sperren ikke slår inn utilsiktet
        self.admin2 = CustomUser.objects.create_user(
            username='del_admin2', password='x', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin2, 'admin')
        self.target = CustomUser.objects.create_user(
            username='del_target', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.target, 'skriver')
        self.client.force_login(self.admin)

    def _slett(self, pk, bekreftelse):
        url = reverse('accounts:user_delete', kwargs={'pk': pk})
        return self.client.post(url, {'confirm_username': bekreftelse})

    def test_sletting_med_riktig_bekreftelse(self):
        resp = self._slett(self.target.pk, 'del_target')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_feil_bekreftelse_sletter_ikke(self):
        resp = self._slett(self.target.pk, 'feil_navn')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_tom_bekreftelse_sletter_ikke(self):
        self._slett(self.target.pk, '')
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_get_gir_405(self):
        url = reverse('accounts:user_delete', kwargs={'pk': self.target.pk})
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_kan_ikke_slette_seg_selv(self):
        resp = self._slett(self.admin.pk, 'del_admin')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CustomUser.objects.filter(pk=self.admin.pk).exists())

    def test_kan_ikke_slette_siste_admin(self):
        from accounts.views import _kan_slettes
        self.admin2.delete()
        # self.admin er nå eneste aktive admin. Sperren testes direkte fordi
        # den innloggede admin uansett ville truffet «ikke deg selv»-sperren.
        tillatt, grunn = _kan_slettes(self.admin, self.target)
        self.assertFalse(tillatt)
        self.assertIn('siste aktive administrator', grunn)

    def test_sletting_fjerner_aktive_sesjoner(self):
        key = _create_session_for_user(self.target)
        self._slett(self.target.pk, 'del_target')
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_sletting_skriver_auditlog_som_overlever(self):
        pk = self.target.pk
        self._slett(pk, 'del_target')

        rad = AuditLog.objects.get(
            table_name='accounts_customuser', record_id=pk, action='DELETE',
        )
        self.assertEqual(rad.old_value, 'del_target')
        self.assertEqual(rad.user, self.admin)
        self.assertEqual(rad.app_label, 'accounts')

    def test_navn_bevares_paa_forstehjelper(self):
        """SET_NULL: pasienthistorikken skal beholde navnet etter sletting."""
        from patients.models import Forstehjelper
        fh = Forstehjelper.objects.create(name='del_target', user=self.target)

        self._slett(self.target.pk, 'del_target')

        fh.refresh_from_db()
        self.assertEqual(fh.name, 'del_target')
        self.assertIsNone(fh.user)

    def test_ikke_admin_far_ikke_slette(self):
        vanlig = CustomUser.objects.create_user(
            username='vanlig', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(vanlig, 'skriver')
        self.client.force_login(vanlig)
        self._slett(self.target.pk, 'del_target')
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_detaljside_viser_slettesperre_for_egen_konto(self):
        url = reverse('accounts:user_detail', kwargs={'pk': self.admin.pk})
        resp = self.client.get(url)
        self.assertContains(resp, 'kan ikke slette din egen konto')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KontotypeBilTests(TestCase):
    """Bil eller ambulanse opprettes i ett steg, ikke tre.

    Fram til 29. aug. 2026 måtte admin opprette kontoen, så opprette enheten
    inne i oppdragsmodulen, og så koble dem. André kalte det tullete. Det var
    tre handlinger for én bil, med to av dem på en helt annen side enn den
    første — og ingen av dem forklarte hvorfor de hang sammen.
    """

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='sjefen', password='AdminPass123!', role='admin',
            must_change_password=False, is_staff=True)
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

    def _opprett(self, **felt):
        data = {
            'username': 'haugesund56',
            'fullt_navn': '',
            'email': '',
            'role': 'bruker',
            'kontotype': 'enhet',
            'enhetsnavn': 'Haugesund 56',
            'metode': 'passord',
        }
        data.update(felt)
        return self.client.post(reverse('accounts:user_create'), data)

    def test_kontoen_og_enheten_lages_i_samme_steg(self):
        from oppdrag.models import Enhet

        self._opprett()

        bruker = CustomUser.objects.get(username='haugesund56')
        enhet = Enhet.objects.get(navn='Haugesund 56')
        self.assertEqual(enhet.user, bruker)
        self.assertTrue(bruker.er_delt_konto)

    def test_enheten_gir_fortsatt_ingen_tilgang(self):
        """Det som ble slått sammen er to opprettelser, ikke tilgang.

        §7.3-skillet står: koblingen avgjør hvilket grensesnitt kontoen får,
        matrisen avgjør hva den har lov til. Uten en rad kommer den ingen vei.
        """
        from accounts.models import ModulTilgang

        self._opprett()
        bruker = CustomUser.objects.get(username='haugesund56')
        self.assertFalse(
            ModulTilgang.objects.filter(bruker=bruker).exists())

        # Flagget ryddes bort først: en nyopprettet konto må bytte passord,
        # og den omdirigeringen ville skjult tilgangssvaret testen måler.
        bruker.must_change_password = False
        bruker.save(update_fields=['must_change_password'])

        c = Client()
        c.force_login(bruker)
        self.assertEqual(c.get('/oppdrag/').status_code, 403)

    def test_enhetsnavn_kreves_for_bil(self):
        from oppdrag.models import Enhet

        resp = self._opprett(enhetsnavn='')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='haugesund56').exists())
        self.assertEqual(Enhet.objects.count(), 0)

    def test_opptatt_enhetsnavn_avvises_for_kontoen_lages(self):
        """Ellers ville unik-feilen kommet etter at kontoen var opprettet."""
        from oppdrag.models import Enhet
        Enhet.objects.create(navn='Haugesund 56')

        resp = self._opprett()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='haugesund56').exists())

    def test_enhetsnavn_avvises_paa_person(self):
        """To kontroller som overlapper er det som gjorde `role` til et rot."""
        resp = self._opprett(kontotype='person', email='a@b.no',
                             enhetsnavn='Haugesund 56')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='haugesund56').exists())

    def test_bil_nekter_epost_og_navn(self):
        resp = self._opprett(email='bil@eksempel.no', fullt_navn='Kari')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='haugesund56').exists())

    def test_bil_far_midlertidig_passord_ikke_invitasjon(self):
        """En bil har ingen innboks å invitere til."""
        from django.core import mail
        self._opprett(metode='invitasjon')
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(
            CustomUser.objects.get(username='haugesund56').must_change_password)

    def test_person_lager_ingen_enhet(self):
        """Vern mot at enheten alltid opprettes."""
        from oppdrag.models import Enhet
        self._opprett(username='kari', kontotype='person',
                      email='kari@eksempel.no', enhetsnavn='',
                      metode='passord')
        self.assertEqual(Enhet.objects.count(), 0)
        self.assertFalse(CustomUser.objects.get(username='kari').er_delt_konto)

    def test_delt_konto_uten_enhet(self):
        """Mellomtypen: felles innlogging som ikke er et kjøretøy."""
        from oppdrag.models import Enhet
        self._opprett(username='sykestua', kontotype='delt', enhetsnavn='')
        self.assertEqual(Enhet.objects.count(), 0)
        self.assertTrue(
            CustomUser.objects.get(username='sykestua').er_delt_konto)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MatriseNivaaerTests(TestCase):
    """Matrisen tilbyr nivåene modulen faktisk bruker.

    Fram til 29. aug. 2026 var lista global, og hadde begge feil samtidig:
    `skriv_handling` sto ikke i den — med den begrunnelsen at ingen modul
    brukte nivået — mens oppdragsmodulen var bygget for akkurat det nivået og
    ikke kunne få det. Samtidig tilbød den `skriv_full` på statistikk, der
    skriving ikke finnes.
    """

    def setUp(self):
        self.client = Client()
        admin = CustomUser.objects.create_user(
            username='matriseadmin', password='AdminPass123!', role='admin',
            must_change_password=False, is_staff=True)
        gi_standardtilgang(admin, 'admin')
        self.client.force_login(admin)

    def _valg(self, slug):
        from accounts.forms import ModulTilgangForm
        felt = ModulTilgangForm().fields[ModulTilgangForm.PREFIKS + slug]
        return [v for v, _ in felt.choices]

    def test_oppdrag_tilbyr_skriv_handling(self):
        self.assertIn('skriv_handling', self._valg('oppdrag'))

    def test_patients_tilbyr_ikke_skriv_handling(self):
        """Pasientmodulen har ingen stemplingsendepunkter."""
        self.assertNotIn('skriv_handling', self._valg('patients'))

    def test_statistikk_tilbyr_ikke_skriving(self):
        valg = self._valg('statistikk')
        self.assertIn('les', valg)
        self.assertNotIn('skriv_full', valg)
        self.assertNotIn('skriv_handling', valg)

    def test_skjemaet_viser_skriv_handling_for_oppdrag(self):
        html = self.client.get(reverse('accounts:user_create')).content.decode()
        self.assertIn('skriv_handling', html)

    def test_nivaa_brukeren_har_staar_i_lista_selv_om_det_ikke_tilbys(self):
        """Ellers ville et lagre-trykk stille fjernet det."""
        from accounts.forms import ModulTilgangForm
        from accounts.models import ModulTilgang

        bruker = CustomUser.objects.create_user(
            username='arvet', password='x', role='bruker',
            must_change_password=False)
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='statistikk', nivaa='skriv_full')

        felt = ModulTilgangForm(bruker=bruker).fields[
            ModulTilgangForm.PREFIKS + 'statistikk']
        self.assertIn('skriv_full', [v for v, _ in felt.choices])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EnhetFolgerKontoenTests(TestCase):
    """Enheten skal forsvinne med kontoen sin, ikke overleve den.

    `Enhet.user` er SET_NULL, så sletting av kontoen etterlot bilen som en rad
    uten kobling: synlig på ressursoversikten, merket rødt, og — når den hadde
    kjørt oppdrag — umulig å bli kvitt, fordi `Oppdrag.enhet` er PROTECT.
    André spurte «jeg kan jo bare slette brukeren?», og hadde rett i at det var
    slik det burde virke.
    """

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='sjefen', password='AdminPass123!', role='admin',
            must_change_password=False, is_staff=True)
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

        self.bil = CustomUser.objects.create_user(
            username='haugesund56', password='x', role='bruker',
            must_change_password=False, er_delt_konto=True)

        from oppdrag.models import Enhet
        self.enhet = Enhet.objects.create(navn='Haugesund 56', user=self.bil)

    def _slett(self, bruker):
        return self.client.post(
            reverse('accounts:user_delete', kwargs={'pk': bruker.pk}),
            {'confirm_username': bruker.username})

    def _gi_oppdrag(self):
        from oppdrag.models import Lokasjon, Oppdrag
        from oppdrag.services import neste_oppdragsnummer
        return Oppdrag.objects.create(
            year=2098, oppdragsnummer=neste_oppdragsnummer(2098),
            enhet=self.enhet, problemstilling='Pustevansker',
            hastegrad='Akutt',
            lokasjon=Lokasjon.objects.create(navn='Hovedscene'))

    def test_sletting_av_kontoen_sletter_enheten(self):
        from oppdrag.models import Enhet

        self._slett(self.bil)

        self.assertFalse(Enhet.objects.filter(pk=self.enhet.pk).exists())

    def test_enhet_med_oppdrag_pensjoneres_i_stedet(self):
        """`Oppdrag.enhet` er PROTECT — historikken skal ikke kunne rives bort."""
        self._gi_oppdrag()

        self._slett(self.bil)

        self.enhet.refresh_from_db()
        self.assertFalse(self.enhet.er_aktiv)
        self.assertFalse(self.enhet.pa_vakt)
        self.assertIsNone(self.enhet.user)

    def test_sletting_av_vanlig_konto_rorer_ingen_enhet(self):
        from oppdrag.models import Enhet

        kari = CustomUser.objects.create_user(
            username='kari', password='x', role='bruker',
            must_change_password=False)
        self._slett(kari)

        self.assertTrue(Enhet.objects.filter(pk=self.enhet.pk).exists())

    def test_pensjonert_navn_kan_brukes_om_igjen(self):
        """Ellers ville navnet vært brent for godt.

        Bilen kjørte, kontoen ble slettet, enheten pensjonert. Skal bilen inn
        igjen til neste arrangement, må «Haugesund 56» være ledig — og etter at
        Pensjoner-knappen ble fjernet finnes ingen manuell vei tilbake.
        """
        from oppdrag.models import Enhet

        self._gi_oppdrag()
        self._slett(self.bil)

        resp = self.client.post(reverse('accounts:user_create'), {
            'username': 'haugesund56', 'fullt_navn': '', 'email': '',
            'role': 'bruker', 'kontotype': 'enhet',
            'enhetsnavn': 'Haugesund 56', 'metode': 'passord',
        })
        self.assertNotContains(resp, 'finnes allerede')

        # Samme rad, ikke en ny: oppdragene peker på den gamle pk-en, og to
        # «Haugesund 56» i statistikken ville vært én for mye.
        self.assertEqual(Enhet.objects.filter(navn='Haugesund 56').count(), 1)
        enhet = Enhet.objects.get(navn='Haugesund 56')
        self.assertEqual(enhet.pk, self.enhet.pk)
        self.assertTrue(enhet.er_aktiv)
        self.assertTrue(enhet.pa_vakt)
        self.assertEqual(enhet.user.username, 'haugesund56')
        self.assertEqual(enhet.oppdrag.count(), 1)

    def test_navn_pa_enhet_i_tjeneste_er_fortsatt_opptatt(self):
        """Gjenbruken gjelder kun pensjonerte, ukoblede rader."""
        resp = self.client.post(reverse('accounts:user_create'), {
            'username': 'ny_bil', 'fullt_navn': '', 'email': '',
            'role': 'bruker', 'kontotype': 'enhet',
            'enhetsnavn': 'Haugesund 56', 'metode': 'passord',
        })
        self.assertContains(resp, 'finnes allerede')
        self.assertFalse(
            CustomUser.objects.filter(username='ny_bil').exists())

    def test_frysing_tar_enheten_av_vakt(self):
        """En frosset konto kan ikke logge inn, så bilen kan ikke melde."""
        self.client.post(
            reverse('accounts:user_detail', kwargs={'pk': self.bil.pk}),
            {'action': 'freeze'})

        self.enhet.refresh_from_db()
        self.assertFalse(self.enhet.pa_vakt)
        self.assertTrue(self.enhet.er_aktiv)   # frysing er reversibel
