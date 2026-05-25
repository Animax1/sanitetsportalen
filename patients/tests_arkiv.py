"""
Tester for VaktArkiv-funksjonalitet.

Dekker:
  1.  test_lagre_arkiv_kun_admin — read_write/lead/lead_view får 403
  2.  test_lagre_arkiv_krever_arrangement_navn — tom navn → 400
  3.  test_lagre_arkiv_lager_arkivertpasient_rader — N pasienter → N rader
  4.  test_lagre_arkiv_kopierer_behandler_navn — denormalisert riktig
  5.  test_lagre_arkiv_setter_sha256 — hash populated, 64 tegn
  6.  test_lagre_arkiv_inkluderer_alle_aktive — kun is_active=True med
  7.  test_arkiv_liste_returnerer_alle — alle arkiv synlige
  8.  test_arkiv_liste_kun_admin — andre roller får 403
  9.  test_arkiv_detalj_inkluderer_statistikk — total/gronn/gul/rod riktig
 10.  test_arkiv_detalj_tamper_detection — manipulert ArkivertPasient → tamper_detected: true
 11.  test_arkiv_slett_kun_admin — andre roller får 403
 12.  test_arkiv_slett_krever_confirm — uten confirm → 400
 13.  test_arkiv_slett_kaskaderer_pasienter — sletter også ArkivertPasient-rader
 14.  test_compute_arkiv_stats_matcher_compute_basic_stats — samme tall fra Patient og ArkivertPasient
"""
import json

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model

from patients.models import Patient, AppSetting, Forstehjelper, VaktArkiv, ArkivertPasient
from patients.services import (
    arkiver_aktiv_vakt,
    compute_arkiv_stats,
    basic_stats,
    _compute_stats_from_dicts,
)

User = get_user_model()


class ArkivTestMixin:
    """Felles oppsett for arkiv-tester."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_arkiv', password='passord', role='admin',
            must_change_password=False,
        )
        self.read_write = User.objects.create_user(
            username='rw_arkiv', password='passord', role='read_write',
            must_change_password=False,
        )
        self.lead = User.objects.create_user(
            username='lead_arkiv', password='passord', role='lead',
            must_change_password=False,
        )
        self.lead_view = User.objects.create_user(
            username='lv_arkiv', password='passord', role='lead_view',
            must_change_password=False,
        )
        self.read_only = User.objects.create_user(
            username='ro_arkiv', password='passord', role='read_only',
            must_change_password=False,
        )

        AppSetting.set('active_year', 2098)
        AppSetting.set('next_patient_nr', 1)

        # Førstehjelper for denormalisering-test
        self.forstehjelper = Forstehjelper.objects.create(name='Dr. Hansen', is_active=True)

        self.admin_client = Client()
        self.admin_client.force_login(self.admin)

    def _lag_pasient(self, nr, grovsortering='Grønn', forstehjelper=None):
        """Opprett pasient direkte i DB."""
        return Patient.objects.create(
            pasientnummer=nr,
            year=2098,
            problemstilling='Test',
            grovsortering=grovsortering,
            is_active=True,
            forstehjelper=forstehjelper,
        )

    def _lagre_arkiv_post(self, navn='Testfestival', notat='', client=None):
        c = client or self.admin_client
        return c.post(
            '/pasienter/api/innstillinger/arkiv/lagre/',
            data=json.dumps({'arrangement_navn': navn, 'notat': notat}),
            content_type='application/json',
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class LagreArkivTests(ArkivTestMixin, TestCase):

    def test_lagre_arkiv_kun_admin(self):
        """read_write, lead og lead_view skal få 403 ved lagring."""
        for role_user in [self.read_write, self.lead, self.lead_view]:
            c = Client()
            c.force_login(role_user)
            resp = self._lagre_arkiv_post(client=c)
            self.assertEqual(resp.status_code, 403, f'Forventet 403 for rolle {role_user.role}')

    def test_lagre_arkiv_krever_arrangement_navn(self):
        """Tom arrangement_navn → 400."""
        resp = self.admin_client.post(
            '/pasienter/api/innstillinger/arkiv/lagre/',
            data=json.dumps({'arrangement_navn': '  ', 'notat': ''}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_lagre_arkiv_lager_arkivertpasient_rader(self):
        """N aktive pasienter → N ArkivertPasient-rader i arkivet."""
        for i in range(1, 4):
            self._lag_pasient(i)

        resp = self._lagre_arkiv_post()
        self.assertEqual(resp.status_code, 201)
        arkiv_id = resp.json()['id']

        self.assertEqual(ArkivertPasient.objects.filter(arkiv_id=arkiv_id).count(), 3)

    def test_lagre_arkiv_kopierer_forstehjelper_navn(self):
        """Førstehjelper-navn kopieres riktig til forstehjelper_navn-feltet."""
        self._lag_pasient(1, forstehjelper=self.forstehjelper)

        resp = self._lagre_arkiv_post()
        self.assertEqual(resp.status_code, 201)
        arkiv_id = resp.json()['id']

        ap = ArkivertPasient.objects.get(arkiv_id=arkiv_id, pasientnummer=1)
        self.assertEqual(ap.forstehjelper_navn, 'Dr. Hansen')

    def test_lagre_arkiv_setter_sha256(self):
        """SHA-256 skal være populated og ha 64 tegn."""
        self._lag_pasient(1)
        resp = self._lagre_arkiv_post()
        self.assertEqual(resp.status_code, 201)
        arkiv = VaktArkiv.objects.get(pk=resp.json()['id'])
        self.assertEqual(len(arkiv.sha256), 64)
        self.assertNotEqual(arkiv.sha256, '')

    def test_lagre_arkiv_inkluderer_alle_aktive(self):
        """Kun is_active=True-pasienter skal inkluderes i arkivet."""
        self._lag_pasient(1)
        self._lag_pasient(2)
        # Inaktiv pasient (soft-deleted)
        p_inaktiv = self._lag_pasient(3)
        p_inaktiv.is_active = False
        p_inaktiv.save()

        resp = self._lagre_arkiv_post()
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        # Kun 2 aktive skal være med
        self.assertEqual(data['antall_pasienter'], 2)
        arkiv_id = data['id']
        self.assertEqual(ArkivertPasient.objects.filter(arkiv_id=arkiv_id).count(), 2)


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivListeTests(ArkivTestMixin, TestCase):

    def test_arkiv_liste_returnerer_alle(self):
        """Alle arkiver skal vises i listen."""
        arkiv_a, _ = arkiver_aktiv_vakt('Festival A', '', self.admin)
        arkiv_b, _ = arkiver_aktiv_vakt('Festival B', '', self.admin)

        resp = self.admin_client.get('/pasienter/api/innstillinger/arkiv/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [d['id'] for d in data]
        self.assertIn(arkiv_a.pk, ids)
        self.assertIn(arkiv_b.pk, ids)

    def test_arkiv_liste_kun_admin(self):
        """Standard ARKIV_VIEW_MIN_ROLE='admin' → andre roller får 403."""
        for role_user in [self.read_write, self.lead, self.lead_view, self.read_only]:
            c = Client()
            c.force_login(role_user)
            resp = c.get('/pasienter/api/innstillinger/arkiv/')
            self.assertEqual(resp.status_code, 403, f'Forventet 403 for rolle {role_user.role}')


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivDetaljTests(ArkivTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        # Opprett testpasienter med ulike grovsorteringer
        self._lag_pasient(1, 'Grønn')
        self._lag_pasient(2, 'Gul')
        self._lag_pasient(3, 'Rød')
        self._lag_pasient(4, 'Rød')
        # Lagre arkiv
        self.arkiv, _ = arkiver_aktiv_vakt('Detaljtest', 'notat', self.admin)

    def test_arkiv_detalj_inkluderer_statistikk(self):
        """Statistikk i detalj-response skal ha riktige tall for total/gronn/gul/rod."""
        resp = self.admin_client.get(f'/pasienter/api/innstillinger/arkiv/{self.arkiv.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('stats', data)
        stats = data['stats']
        self.assertEqual(stats['total'], 4)
        self.assertEqual(stats['gronn'], 1)
        self.assertEqual(stats['gul'], 1)
        self.assertEqual(stats['rod'], 2)

    def test_arkiv_detalj_tamper_detection(self):
        """Manipulert ArkivertPasient-rad → tamper_detected: true i respons."""
        # Endre grovsortering direkte i DB uten å oppdatere sha256
        ap = ArkivertPasient.objects.filter(arkiv=self.arkiv).first()
        ap.grovsortering = 'Rød'  # Endre uten å oppdatere sha256
        ap.save()

        resp = self.admin_client.get(f'/pasienter/api/innstillinger/arkiv/{self.arkiv.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['tamper_detected'])

    def test_arkiv_full_stats_endpoint_returnerer_full_struktur(self):
        """GET full-stats skal returnere samme struktur som /api/full-stats/.

        Sjekker at alle hovednøkler finnes (summary, arrivals, transport_counts,
        time_per_triage, crosstab_*, chi2_table, kw_*).
        """
        resp = self.admin_client.get(
            f'/pasienter/api/innstillinger/arkiv/{self.arkiv.pk}/full-stats/'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Hovednøkler fra full_stats() i services.py
        forventede_noekler = [
            'summary',
            'arrivals',
            'transport_counts', 'utfall_counts', 'prob_counts',
            'time_per_triage', 'time_per_problem', 'time_per_transport',
            'crosstab_prob_triage', 'crosstab_triage_transport', 'crosstab_prob_utfall',
            'obs_per_triage', 'obs_per_problem',
            'chi2_table',
            'kw_triage', 'kw_problem', 'kw_transport',
        ]
        for key in forventede_noekler:
            self.assertIn(key, data, f'Mangler nøkkel: {key}')

        # Summary skal speile arkivet (4 pasienter, 1 grønn, 1 gul, 2 røde)
        self.assertEqual(data['summary']['total'], 4)
        self.assertEqual(data['summary']['gronn'], 1)
        self.assertEqual(data['summary']['gul'], 1)
        self.assertEqual(data['summary']['rod'], 2)

    def test_arkiv_full_stats_krever_riktig_rolle(self):
        """Roller under ARKIV_VIEW_MIN_ROLE (default admin) skal få 403."""
        for role_user in [self.read_only, self.read_write, self.lead_view, self.lead]:
            c = Client()
            c.force_login(role_user)
            resp = c.get(f'/pasienter/api/innstillinger/arkiv/{self.arkiv.pk}/full-stats/')
            self.assertEqual(
                resp.status_code, 403,
                f'Forventet 403 for rolle {role_user.role}',
            )

    def test_arkiv_full_stats_404_for_ukjent_id(self):
        """Ukjent arkiv-ID skal gi 404."""
        resp = self.admin_client.get('/pasienter/api/innstillinger/arkiv/999999/full-stats/')
        self.assertEqual(resp.status_code, 404)


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivSlettTests(ArkivTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self._lag_pasient(1)
        self._lag_pasient(2)
        self.arkiv, _ = arkiver_aktiv_vakt('Sletttest', '', self.admin)

    def _slett_arkiv(self, pk, confirm=True, client=None):
        c = client or self.admin_client
        body = {'confirm': True} if confirm else {}
        return c.delete(
            f'/pasienter/api/innstillinger/arkiv/{pk}/',
            data=json.dumps(body),
            content_type='application/json',
        )

    def test_arkiv_slett_kun_admin(self):
        """Ikke-admin-roller skal få 403 ved sletting."""
        for role_user in [self.read_write, self.lead, self.lead_view, self.read_only]:
            c = Client()
            c.force_login(role_user)
            resp = self._slett_arkiv(self.arkiv.pk, client=c)
            self.assertEqual(resp.status_code, 403, f'Forventet 403 for rolle {role_user.role}')

    def test_arkiv_slett_krever_confirm(self):
        """Sletting uten confirm → 400."""
        resp = self._slett_arkiv(self.arkiv.pk, confirm=False)
        self.assertEqual(resp.status_code, 400)
        # Arkivet skal fremdeles finnes
        self.assertTrue(VaktArkiv.objects.filter(pk=self.arkiv.pk).exists())

    def test_arkiv_slett_kaskaderer_pasienter(self):
        """Sletting av arkiv skal også slette ArkivertPasient-rader (CASCADE)."""
        antall = ArkivertPasient.objects.filter(arkiv=self.arkiv).count()
        self.assertGreater(antall, 0)

        resp = self._slett_arkiv(self.arkiv.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])

        # Arkivet og alle pasienter skal være borte
        self.assertFalse(VaktArkiv.objects.filter(pk=self.arkiv.pk).exists())
        self.assertEqual(ArkivertPasient.objects.filter(arkiv_id=self.arkiv.pk).count(), 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class StatsMatcher(ArkivTestMixin, TestCase):
    """Sammenligning av basic_stats og compute_arkiv_stats."""

    def test_compute_arkiv_stats_matcher_compute_basic_stats(self):
        """Statistikk fra ArkivertPasient skal gi samme tall som fra Patient."""
        # Opprett pasienter med kjente data
        self._lag_pasient(1, 'Grønn')
        self._lag_pasient(2, 'Gul')
        self._lag_pasient(3, 'Rød')

        # Hent live stats FØR arkivering (fra Patient)
        live = basic_stats(year=2098)

        # Arkiver
        arkiv, _ = arkiver_aktiv_vakt('Sammenligning', '', self.admin)

        # Hent arkiv-stats
        arkiv_stats = compute_arkiv_stats(arkiv)

        # Hovednøkler skal matche
        for key in ('total', 'gronn', 'gul', 'rod', 'tilstede', 'utskrevet'):
            self.assertEqual(
                live[key],
                arkiv_stats[key],
                f'Nøkkel «{key}» avviker: live={live[key]}, arkiv={arkiv_stats[key]}',
            )
