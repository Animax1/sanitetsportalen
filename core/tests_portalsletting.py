"""Slette en portal med alt i den (18. okt. 2026, `core/portalsletting.py`).

Tjenestelaget er det tunge: en sletting som tar for lite, etterlater data uten portal; en som
tar for mye, tar en annen portals vakt med seg. Fiksturen er vaktslettingens, som har én rad i
hver modul, i to portaler.
"""
from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.apps import apps
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang, Portaltilgang
from audit.models import AuditLog
from core import portalsletting
from core.models import AppSetting, Backup, Vakt, Vaktportal
from core.portal import aktiver_portal, eneste_portal
from core.tests_vaktsletting import _Data, _rader
from core.vakt import hent_aktiv_vakt
from core.vaktsletting import KanIkkeSlettes


def _i_portalen(portal_pk) -> dict:
    """Antall rader som peker på portalen, per modell (unntatt vaktene, som telles for seg)."""
    ut = {}
    for modell in apps.get_models():
        for felt in modell._meta.get_fields():
            if getattr(felt, 'related_model', None) is Vaktportal and not felt.auto_created \
                    and (felt.many_to_one or felt.one_to_one):
                n = modell.objects.filter(**{f'{felt.name}_id': portal_pk}).count()
                if n:
                    ut[modell._meta.label] = n
    return ut


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SlettPortalTests(TestCase, _Data):

    def setUp(self):
        cache.clear()
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)
        self.admin = CustomUser.objects.create_user(
            username='sjef', password='x', role='admin', must_change_password=False)
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        with aktiver_portal(self.standard):
            self.std_vakt = hent_aktiv_vakt()
            self.fyll(self.std_vakt, self.admin)
        with aktiver_portal(self.brann):
            self.gammel = Vakt.objects.create(portal=self.brann, navn='Brann 1', year=2025,
                                              startet=timezone.now(), er_aktiv=False,
                                              avsluttet=timezone.now())
            self.aktiv = hent_aktiv_vakt()
            self.fyll(self.gammel, self.admin)
            self.fyll(self.aktiv, self.admin)
        # Et oppdrag på tavla sperrer (som «Avslutt vakt»); fiksturen lar det stå der.
        from oppdrag.models import Oppdrag
        Oppdrag.objects.update(historikk_fra=timezone.now())
        self.ola = CustomUser.objects.create_user(username='ola', password='x',
                                                  must_change_password=False)
        tilgang = Portaltilgang.objects.create(bruker=self.ola, portal=self.brann)
        ModulTilgang.objects.create(portaltilgang=tilgang, modul_slug='ko', nivaa='les')
        Portaltilgang.objects.create(bruker=self.ola, portal=self.standard)
        AppSetting.set(AppSetting.portalnokkel('ko.chat_tillatt', self.brann), '1')
        self.c = Client()
        self.c.force_login(self.admin)
        sesjon = self.c.session
        sesjon['portal_id'] = self.standard.pk
        sesjon.save()

    def _slett(self, navn='Brann'):
        return self.c.post(f'/admin/portaler/{self.brann.pk}/',
                           {'handling': 'slett', 'bekreftelse': navn, '_portal': 'standard'},
                           follow=True)

    def test_fiksturen_har_data_i_portalen(self):
        self.assertTrue(_i_portalen(self.brann.pk))
        self.assertTrue(_rader(self.aktiv.pk))

    def test_alt_i_portalen_forsvinner_og_bare_det(self):
        std_for = (_rader(self.std_vakt.pk), _i_portalen(self.standard.pk))
        vakter = [self.gammel.pk, self.aktiv.pk]
        svar = self._slett()
        self.assertRedirects(svar, '/admin/portaler/')
        self.assertFalse(Vaktportal.objects.filter(pk=self.brann.pk).exists())
        self.assertFalse(Vakt.objects.filter(pk__in=vakter).exists())
        for pk in vakter:
            self.assertEqual(_rader(pk), {}, 'vaktenes data, arkivene og tallene')
        self.assertEqual(_i_portalen(self.brann.pk), {})
        self.assertFalse(AppSetting.objects.filter(key__endswith=f'@p{self.brann.pk}').exists())
        self.assertEqual((_rader(self.std_vakt.pk), _i_portalen(self.standard.pk)), std_for,
                         'Standard er urørt')
        # Kontoen står, med medlemskapet i den andre portalen.
        self.assertTrue(CustomUser.objects.filter(pk=self.ola.pk).exists())
        self.assertEqual(list(Portaltilgang.objects.filter(bruker=self.ola)
                              .values_list('portal__slug', flat=True)), ['standard'])

    def test_arkivene_og_den_frosne_statistikken_gaar_med(self):
        """André: ja, de går også. De peker på vakta med SET_NULL, så de overlever en vanlig
        `vakt.delete()` — og forsvinner fra `_rader()` uten å være borte."""
        from core.arkiv import all_handlers as arkivhandlere
        from core.models import VaktStatistikk
        vakter = [self.gammel, self.aktiv]
        arkiver = {(h.arkiv_model, a.pk) for h in arkivhandlere() if h.arkiv_model
                   for a in h.arkiv_model.objects.filter(vakt__in=vakter)}
        stat = set(VaktStatistikk.objects.filter(vakt__in=vakter).values_list('pk', flat=True))
        self.assertTrue(arkiver and stat, 'fiksturen har begge')
        self._slett()
        for modell, pk in arkiver:
            self.assertFalse(modell.objects.filter(pk=pk).exists(), modell)
        self.assertFalse(VaktStatistikk.objects.filter(pk__in=stat).exists())
        self.assertTrue(VaktStatistikk.objects.filter(vakt=self.std_vakt).exists())

    def test_oversikten_teller_bare_portalens_egne(self):
        from oppdrag.models import Lokasjon
        linjer = dict(portalsletting.oversikt(self.brann)['linjer'])
        navn = str(Lokasjon._meta.verbose_name_plural).lower()
        self.assertEqual(linjer[navn], Lokasjon.objects.filter(portal=self.brann).count())

    def test_siden_sier_fra_om_den_siste_portalen(self):
        portalsletting.slett_portal(self.brann, bekreftelse='Brann', bruker=self.admin)
        svar = self.c.get(f'/admin/portaler/{self.standard.pk}/')
        self.assertContains(svar, 'den siste portalen')
        self.assertNotContains(svar, 'name="bekreftelse"')

    def test_backup_foer_og_en_auditrad(self):
        self._slett()
        self.assertTrue(Backup.objects.filter(module_slug='full', kind='pre_slett').exists())
        rad = AuditLog.objects.get(table_name='core_vaktportal', action='DELETE')
        self.assertIn('Brann', rad.new_value)
        self.assertEqual(rad.user, self.admin)

    def test_feil_navn_sletter_ingenting(self):
        svar = self._slett('brann')
        self.assertContains(svar, 'Skriv portalens navn')
        self.assertTrue(Vaktportal.objects.filter(pk=self.brann.pk).exists())
        self.assertFalse(Backup.objects.filter(kind='pre_slett').exists())

    def test_den_siste_portalen_kan_ikke_slettes(self):
        portalsletting.slett_portal(self.brann, bekreftelse='Brann', bruker=self.admin)
        with self.assertRaises(KanIkkeSlettes):
            portalsletting.slett_portal(self.standard, bekreftelse='Standard', bruker=self.admin)
        self.assertTrue(Vaktportal.objects.filter(pk=self.standard.pk).exists())

    def test_standard_kan_slettes_naar_det_finnes_en_annen(self):
        portalsletting.slett_portal(self.standard, bekreftelse='Standard', bruker=self.admin)
        self.assertEqual(list(Vaktportal.objects.values_list('slug', flat=True)), ['brann'])

    def test_et_oppdrag_paa_tavla_sperrer_som_ved_avslutt_vakt(self):
        from oppdrag.models import Oppdrag
        Oppdrag.objects.filter(vakt=self.aktiv).update(historikk_fra=None)
        svar = self._slett()
        self.assertContains(svar, 'står fortsatt i oppdragslisten')
        self.assertTrue(Vaktportal.objects.filter(pk=self.brann.pk).exists())
        self.assertNotContains(self.c.get(f'/admin/portaler/{self.brann.pk}/'),
                               'name="bekreftelse"', msg_prefix='skjemaet vises ikke')

    def test_en_feil_midt_i_ruller_alt_tilbake(self):
        """Feilen kommer i auditraden — helt til slutt, når alt annet er slettet."""
        for_ = {v.pk: _rader(v.pk) for v in (self.gammel, self.aktiv)}
        o = portalsletting.oversikt(self.brann)
        brann_pk = self.brann.pk   # `delete()` nullstiller pk på instansen, også ved tilbakerulling
        ekte = AuditLog.objects.create

        def feil_til_slutt(**kw):
            if kw.get('table_name') == 'core_vaktportal':
                raise RuntimeError('midt i')
            return ekte(**kw)

        with mock.patch.object(AuditLog.objects, 'create', side_effect=feil_til_slutt):
            with self.assertRaises(RuntimeError):
                portalsletting._slett(self.brann, o, bruker=self.admin, request=None)
        self.assertTrue(Vaktportal.objects.filter(pk=brann_pk).exists())
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())
        self.assertTrue(_i_portalen(brann_pk))
        self.assertEqual({pk: _rader(pk) for pk in for_}, for_, 'modulenes data er tilbake')

    def test_bare_global_admin(self):
        moderator = CustomUser.objects.create_user(username='mod', password='x',
                                                   must_change_password=False)
        Portaltilgang.objects.create(bruker=moderator, portal=self.brann, rolle='moderator')
        c = Client()
        c.force_login(moderator)
        svar = c.post(f'/admin/portaler/{self.brann.pk}/',
                      {'handling': 'slett', 'bekreftelse': 'Brann'})
        self.assertEqual(svar.status_code, 403)
        self.assertTrue(Vaktportal.objects.filter(pk=self.brann.pk).exists())

    def test_siden_viser_hva_som_gaar(self):
        svar = self.c.get(f'/admin/portaler/{self.brann.pk}/')
        self.assertContains(svar, 'Slett portalen')
        self.assertContains(svar, 'Skriv «Brann» for å bekrefte')
