"""Personsøket på tvers av portalene, for innsyn og sletting (18. okt. 2026, §4.5).

`core/personsok.py` og modulenes `<app>/personsok.py`. Tjenestelaget og porten er de
tunge lagene: et søk som ser for lite, gir et ufullstendig innsynssvar uten at noen
merker det; en sletting som går gjennom historikk, fjerner dokumentasjon.
"""
from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, Portaltilgang
from audit.models import AuditLog
from core import personsok
from core.models import Tilhorighet, Vaktportal
from core.portal import aktiver_portal, eneste_portal

SIDE = '/admin/personsok/'


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PersonsokTests(TestCase):

    def setUp(self):
        from patients.models import Forstehjelper
        from vaktliste.test_helpers import lag_mannskap

        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.hgsd = Tilhorighet.objects.create(navn='HGSD')
        with aktiver_portal(self.standard):
            self.ola_s = lag_mannskap(navn='Ola Nordmann', korps=self.hgsd, telefon='11111111',
                                      epost='ola@example.org')
            self.fh = Forstehjelper.objects.create(name='Ola Nordmann')
        with aktiver_portal(self.brann):
            self.ola_b = lag_mannskap(navn='Ola Nordmann', korps=self.hgsd, telefon='22222222')
        with aktiver_portal(self.standard):
            lag_mannskap(navn='Kari Hansen', korps=self.hgsd)
        self.ola_konto = CustomUser.objects.create_user(
            username='ola', password='x', email='ola@example.org', fullt_navn='Ola Nordmann',
            must_change_password=False)
        self.admin = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                                    must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)
        sesjon = self.c.session
        sesjon['portal_id'] = self.standard.pk
        sesjon.save()

    def _kilder(self, q):
        svar = self.c.get(SIDE, {'q': q})
        self.assertEqual(svar.status_code, 200)
        return {k['handler'].slug: k for k in svar.context['resultat']}

    def test_finner_personen_i_alle_portalene_og_kildene(self):
        kilder = self._kilder('ola nord')
        mannskap = kilder['vaktliste_mannskap']['treff']
        self.assertEqual(sorted(t.portal for t in mannskap), ['Brann', 'Standard'])
        self.assertEqual([t.navn for t in kilder['kontoer']['treff']], ['Ola Nordmann'])
        self.assertEqual([t.navn for t in kilder['patients_forstehjelper']['treff']],
                         ['Ola Nordmann'])
        self.assertNotIn('Kari', str([t.navn for k in kilder.values() for t in k['treff']]))

    def test_e_post_treffer_mannskap_og_konto(self):
        kilder = self._kilder('ola@example')
        self.assertEqual([t.portal for t in kilder['vaktliste_mannskap']['treff']], ['Standard'])
        self.assertEqual(len(kilder['kontoer']['treff']), 1)

    def test_hvert_sok_logges_med_ordet(self):
        self.c.get(SIDE, {'q': 'ola'})
        rad = AuditLog.objects.get(table_name='core_personsok', action='SOK')
        self.assertEqual((rad.new_value, rad.user), ('ola', self.admin))

    def test_ett_tegn_er_ikke_et_sok(self):
        svar = self.c.get(SIDE, {'q': 'o'})
        self.assertEqual(svar.context['resultat'], [])
        self.assertFalse(AuditLog.objects.filter(action='SOK').exists())

    def test_bare_admin(self):
        kari = CustomUser.objects.create_user(username='kari', password='x',
                                              must_change_password=False)
        Portaltilgang.objects.create(bruker=kari, portal=self.standard)
        c = Client()
        c.force_login(kari)
        self.assertEqual(c.get(SIDE, {'q': 'ola'}).status_code, 403)
        self.assertEqual(c.post(SIDE, {'kilde': 'vaktliste_mannskap', 'pk': self.ola_b.pk})
                         .status_code, 403)
        self.assertFalse(AuditLog.objects.filter(action='SOK').exists())

    def _slett(self, kilde, pk):
        return self.c.post(SIDE, {'q': 'ola', 'kilde': kilde, 'pk': pk, '_portal': 'standard'},
                           follow=True)

    def test_slett_en_uten_historikk_med_audit(self):
        from vaktliste.models import Mannskap
        self._slett('vaktliste_mannskap', self.ola_b.pk)
        self.assertFalse(Mannskap.objects.filter(pk=self.ola_b.pk).exists())
        self.assertTrue(Mannskap.objects.filter(pk=self.ola_s.pk).exists(), 'bare den ene')
        self.assertTrue(AuditLog.objects.filter(table_name='core_personsok', action='DELETE',
                                                record_id=self.ola_b.pk,
                                                field_name='vaktliste_mannskap').exists())

    def test_en_med_skift_slettes_ikke(self):
        from vaktliste import services
        from vaktliste.models import Mannskap, Vaktpost
        from vaktliste.test_helpers import lag_ressurs
        with aktiver_portal(self.standard):
            vl = services.opprett_planlagt_vakt('Vakta')
            Vaktpost.objects.create(ressurs=lag_ressurs(vaktliste=vl, navn='Lag'),
                                    mannskap=self.ola_s, fra_tid=timezone.now(),
                                    til_tid=timezone.now())
        svar = self._slett('vaktliste_mannskap', self.ola_s.pk)
        self.assertContains(svar, 'inaktiv')
        self.assertTrue(Mannskap.objects.filter(pk=self.ola_s.pk).exists())

    def test_en_forstehjelper_paa_en_pasient_slettes_ikke(self):
        from patients.models import Forstehjelper
        from patients.test_helpers import lag_pasient
        with aktiver_portal(self.standard):
            lag_pasient(forstehjelper=self.fh, pasientnummer=1)
        self._slett('patients_forstehjelper', self.fh.pk)
        self.assertTrue(Forstehjelper.objects.filter(pk=self.fh.pk).exists())

    def test_en_ubrukt_forstehjelper_slettes(self):
        from patients.models import Forstehjelper
        self._slett('patients_forstehjelper', self.fh.pk)
        self.assertFalse(Forstehjelper.objects.filter(pk=self.fh.pk).exists())

    def test_kontoer_slettes_ikke_herfra(self):
        svar = self._slett('kontoer', self.ola_konto.pk)
        self.assertContains(svar, 'kan ikke slettes herfra')
        self.assertTrue(CustomUser.objects.filter(pk=self.ola_konto.pk).exists())

    def test_en_kilde_som_feiler_tar_ikke_ned_sok(self):
        class _Feiler(personsok.BasePersonsokHandler):
            slug = 'test_feiler'
            etikett = 'Feiler'

            def sok(self, q):
                raise RuntimeError('nede')

        sikret = personsok.all_handlers()
        self.addCleanup(lambda: [personsok.clear_registry()]
                        + [personsok.register(h) for h in sikret])
        personsok.register(_Feiler())
        kilder = self._kilder('ola')
        self.assertIn('nede', kilder['test_feiler']['feil'])
        self.assertEqual(len(kilder['vaktliste_mannskap']['treff']), 2)
