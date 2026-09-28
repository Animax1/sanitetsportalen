"""Sletting av en tidligere vakt (28. sep. 2026, `core/vaktsletting.py`).

André: «jeg vil ha en slett knapp. Noen er test vakter som kan og skal slettes.»

Det som skal holde, og hvorfor det er verdt en test hver:

- **Dekningen er utledet, ikke husket.** Hver fremmednøkkel til `core.Vakt` som
  ikke er `SET_NULL`, må slettes av en handler. En ny modul som glemmer det, gir
  `ProtectedError` den dagen noen trykker — denne testen gjør det rødt før.
- **Alt forsvinner, og bare det.** Data i alle modulene for den ene vakta, og
  ingenting fra den andre.
- **Den aktive vakta slettes ikke**, og da er ingenting rørt — heller ingen backup.
- **Alt eller ingenting**, og en hel backup først.
- **Portene:** global admin, POST, og vaktas navn skrevet inn.
"""
from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.apps import apps
from django.core.cache import cache
from django.db import models
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog
from core import vaktsletting
from core.models import AppSetting, Backup, Vakt, VaktStatistikk
from patients.test_helpers import sett_aktiv_vakt


class DekningenTests(TestCase):

    def test_hver_peker_til_vakta_er_dekket(self):
        dekket = {etikett for h in vaktsletting.all_handlers() for etikett in h.modeller}
        mangler = []
        for modell in apps.get_models():
            for felt in modell._meta.get_fields():
                if (getattr(felt, 'many_to_one', False) or getattr(felt, 'one_to_one', False)) \
                        and not felt.auto_created and felt.related_model is Vakt \
                        and felt.remote_field.on_delete is not models.SET_NULL \
                        and modell._meta.label not in dekket:
                    mangler.append(f'{modell._meta.label}.{felt.name}')
        self.assertEqual(mangler, [], 'Meld modellen inn i en `<app>/vaktsletting.py`.')

    def test_ingen_handler_lister_en_modell_som_ikke_peker_paa_vakta(self):
        for h in vaktsletting.all_handlers():
            for etikett in h.modeller:
                with self.subTest(etikett=etikett):
                    felter = [f for f in apps.get_model(etikett)._meta.get_fields()
                              if getattr(f, 'related_model', None) is Vakt and not f.auto_created]
                    self.assertTrue(felter)


class _Data:
    """Én rad i hver modul for en vakt."""

    def fyll(self, vakt, admin):
        from ko.models import Hendelse, Logglinje
        from oppdrag import services as oppdrag_services
        from oppdrag.arkiv import arkiver_vakt
        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        from park.models import Parklenke, Registrering
        from patients.models import Patient
        from patients.services import arkiver_aktiv_vakt, next_patient_nr
        from vaktliste.models import Vaktliste, Vaktpost
        from vaktliste.test_helpers import lag_ressurs

        naa = timezone.now()
        lokasjon = Lokasjon.objects.get_or_create(navn='Scene')[0]
        enhet = Enhet.objects.get_or_create(navn='Bil 1', defaults={'pa_vakt': True})[0]
        Patient.objects.create(vakt=vakt, pasientnummer=next_patient_nr(vakt))
        arkiver_aktiv_vakt(vakt.navn, '', admin, vakt=vakt)
        o = Oppdrag.objects.create(vakt=vakt, oppdragsnummer=oppdrag_services.neste_oppdragsnummer(vakt),
                                   problemstilling='Pustevansker', hastegrad='Akutt',
                                   lokasjon=lokasjon, enhet=enhet)
        arkiver_vakt(vakt, '', admin, tomm=False)
        o.refresh_from_db()
        hendelse = Hendelse.objects.create(vakt=vakt, hendelsesnummer=1, tittel='Kollaps')
        o.hendelse = hendelse
        o.save(update_fields=['hendelse'])
        Logglinje.objects.create(vakt=vakt, tidspunkt=naa, tekst='linje', hendelse=hendelse)
        from ko.models import PlanlagtPause, Programendring, Programpost, Tavleplassering
        from oppdrag.models import Vaktmodusperiode
        senere = naa + timezone.timedelta(hours=1)
        Tavleplassering.objects.create(vakt=vakt, ressurs_navn='Lag 1', fra=naa)
        PlanlagtPause.objects.create(vakt=vakt, ressurs_navn='Lag 1', fra=naa, til=senere)
        Programpost.objects.create(vakt=vakt, lokasjon_navn='Scene', navn='Konsert',
                                   fra=naa, til=senere)
        Programendring.objects.create(vakt=vakt, post_navn='Konsert', hva='opprettet')
        Vaktmodusperiode.objects.create(enhet=enhet, vakt=vakt, modus='passiv', fra=naa)
        vl = Vaktliste.objects.create(vakt=vakt)
        ressurs = lag_ressurs(vaktliste=vl, navn='Lag 1')
        Vaktpost.objects.create(ressurs=ressurs, fra_tid=naa, til_tid=naa + timezone.timedelta(hours=2))
        lenke = Parklenke.objects.get_or_create(
            navn='Kort', defaults={'hemmelighet_hash': 'x' * 64, 'aapen_fra': naa,
                                   'aapen_til': naa + timezone.timedelta(days=1)})[0]
        Registrering.objects.create(vakt=vakt, lenke=lenke, ressurs=ressurs, ressurs_navn='Lag 1',
                                    problemstilling='Svimmelhet', utfall='Behandlet på stedet',
                                    lokasjon_navn='Scene', idempotency_key=f'k{vakt.pk}')
        VaktStatistikk.objects.create(vakt=vakt, vakt_navn=vakt.navn, slug='park', data={},
                                      frosset_at=naa)


def _rader(vakt_pk):
    """Antall rader som peker på vakta, per modell — arkivene og tallene med."""
    ut = {}
    for modell in apps.get_models():
        for felt in modell._meta.get_fields():
            if getattr(felt, 'related_model', None) is Vakt and not felt.auto_created \
                    and (felt.many_to_one or felt.one_to_one):
                n = modell.objects.filter(**{f'{felt.name}_id': vakt_pk}).count()
                if n:
                    ut[modell._meta.label] = n
    return ut


@override_settings(SECURE_SSL_REDIRECT=False)
class SlettingBasis(TestCase, _Data):

    def setUp(self):
        cache.clear()
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)
        self.admin = CustomUser.objects.create_user(
            username='a', password='x', role='admin', must_change_password=False)
        self.gammel = Vakt.objects.create(navn='Testvakt', year=2025, startet=timezone.now(),
                                          er_aktiv=False, avsluttet=timezone.now())
        self.aktiv = sett_aktiv_vakt(2026)
        self.fyll(self.gammel, self.admin)
        self.fyll(self.aktiv, self.admin)
        self.c = Client()
        self.c.force_login(self.admin)


class SlettVaktTests(SlettingBasis):

    def test_fiksturen_har_rader_i_hver_modell_som_slettes(self):
        """Ellers bestod testen under på en vakt uten noe å slette der — en mutant
        som lot vaktmodusperiodene stå, overlevde fordi fiksturen ikke hadde noen."""
        dekket = {etikett for h in vaktsletting.all_handlers() for etikett in h.modeller}
        self.assertEqual(dekket - set(_rader(self.gammel.pk)), set())

    def test_alt_for_vakta_forsvinner_og_bare_det(self):
        pk = self.gammel.pk
        for_aktiv = _rader(self.aktiv.pk)
        vaktsletting.slett_vakt(self.gammel, bruker=self.admin)
        self.assertFalse(Vakt.objects.filter(pk=pk).exists())
        self.assertEqual(_rader(pk), {})
        self.assertEqual(_rader(self.aktiv.pk), for_aktiv)
        self.assertFalse(AppSetting.objects.filter(key__endswith=f'_vakt_{pk}').exists())

    def test_de_frosne_tallene_gaar_med(self):
        """De peker på vakta med SET_NULL: uten den eksplisitte slettingen ble de
        stående uten vakt — og `_rader()` over ser bare rader *med* peker."""
        vaktsletting.slett_vakt(self.gammel, bruker=self.admin)
        self.assertFalse(VaktStatistikk.objects.filter(vakt_navn='Testvakt').exists())
        self.assertFalse(VaktStatistikk.objects.filter(vakt__isnull=True).exists())

    def test_arkivenes_rader_gaar_med(self):
        from oppdrag.models import ArkivertOppdrag
        from patients.models import ArkivertPasient
        vaktsletting.slett_vakt(self.gammel, bruker=self.admin)
        # Arkivene peker på vakta med SET_NULL; uten den eksplisitte slettingen
        # ville de — og radene — blitt stående med tom vaktpeker.
        self.assertEqual(ArkivertPasient.objects.filter(arkiv__vakt__isnull=True).count(), 0)
        self.assertEqual(ArkivertPasient.objects.count(), 1, 'bare den aktive vaktas')
        self.assertEqual(ArkivertOppdrag.objects.count(), 1, 'bare den aktive vaktas')

    def test_hel_backup_forst_og_en_auditrad(self):
        vaktsletting.slett_vakt(self.gammel, bruker=self.admin)
        self.assertTrue(Backup.objects.filter(kind='pre_slett', module_slug='full').exists())
        rad = AuditLog.objects.get(field_name='vakt_slettet')
        self.assertEqual(rad.user, self.admin)
        self.assertIn('Testvakt', rad.new_value)
        self.assertIn('pasienter: 1', rad.new_value)

    def test_backupen_foran_slettingen_ryddes_ikke_bort(self):
        """Den er eneste vei tilbake. Uten vernet ville de neste automatiske
        backupene av `full` skjøvet den ut av taket på volumet."""
        from core.backup import PROTECTED_KINDS
        self.assertIn('pre_slett', PROTECTED_KINDS)

    def test_den_aktive_vakta_slettes_ikke(self):
        for_ = _rader(self.aktiv.pk)
        with self.assertRaises(vaktsletting.KanIkkeSlettes):
            vaktsletting.slett_vakt(self.aktiv, bruker=self.admin)
        self.assertEqual(_rader(self.aktiv.pk), for_)
        self.assertFalse(Backup.objects.filter(kind='pre_slett').exists())

    def test_pekeren_til_aktiv_vakt_vinner_over_flagget(self):
        """Står `aktiv_vakt_id` på en vakt med `er_aktiv=False` — en inkonsistens,
        men en mulig en — er det likevel den portalen registrerer på."""
        AppSetting.set('aktiv_vakt_id', self.gammel.pk)
        with self.assertRaises(vaktsletting.KanIkkeSlettes):
            vaktsletting.slett_vakt(self.gammel, bruker=self.admin)
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())

    def test_en_modul_som_feiler_ruller_tilbake_alt(self):
        for_ = _rader(self.gammel.pk)
        vaktliste = next(h for h in vaktsletting.all_handlers() if h.slug == 'vaktliste')
        with mock.patch.object(type(vaktliste), 'slett', side_effect=RuntimeError('midt i')):
            with self.assertRaises(RuntimeError):
                vaktsletting.slett_vakt(self.gammel, bruker=self.admin)
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())
        self.assertEqual(_rader(self.gammel.pk), for_)

    def test_oversikten_teller_det_som_slettes(self):
        linjer = dict(vaktsletting.oversikt(self.gammel))
        self.assertEqual(linjer['pasienter'], 1)
        self.assertEqual(linjer['oppdrag'], 1)
        self.assertEqual(linjer['lagregistreringer'], 1)
        self.assertEqual(linjer['arkiver'], 2)
        self.assertEqual(linjer['frosne statistikkfaner'], 1)


class SlettSidenTests(SlettingBasis):

    def _url(self, vakt):
        return f'/portal-admin/vakt/{vakt.pk}/slett/'

    def test_siden_viser_hva_som_forsvinner(self):
        svar = self.c.get(self._url(self.gammel))
        self.assertContains(svar, 'Pasienter: 1')
        self.assertContains(svar, 'Arkiver: 2')
        self.assertContains(svar, 'name="navn"')

    def test_feil_navn_sletter_ingenting(self):
        for navn in ('', 'testvakt', 'Testvakt '[:-1] + 'x'):
            self.c.post(self._url(self.gammel), {'navn': navn})
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())

    def test_riktig_navn_sletter(self):
        svar = self.c.post(self._url(self.gammel), {'navn': 'Testvakt'}, follow=True)
        self.assertFalse(Vakt.objects.filter(pk=self.gammel.pk).exists())
        self.assertIn('er slettet', ' '.join(str(m) for m in svar.context['messages']))

    def test_aktiv_vakt_faar_ingen_slettknapp(self):
        svar = self.c.get(self._url(self.aktiv))
        self.assertContains(svar, 'kan ikke slettes')
        self.assertNotContains(svar, 'name="navn"')
        self.c.post(self._url(self.aktiv), {'navn': self.aktiv.navn})
        self.assertTrue(Vakt.objects.filter(pk=self.aktiv.pk).exists())

    def test_bare_global_admin(self):
        leder = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(leder, 'leder')
        c = Client()
        c.force_login(leder)
        self.assertEqual(c.get(self._url(self.gammel)).status_code, 403)
        self.assertEqual(c.post(self._url(self.gammel), {'navn': 'Testvakt'}).status_code, 403)
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())

    def test_vaktsiden_lenker_til_slettingen(self):
        self.assertContains(self.c.get('/portal-admin/vakt/'), self._url(self.gammel))


class SlettArkivTests(SlettingBasis):

    def _arkiv(self):
        from patients.models import VaktArkiv
        return VaktArkiv.objects.get(vakt=self.gammel)

    def _url(self, arkiv, slug='patients'):
        return f'/portal-admin/vakt/arkiv/{slug}/{arkiv.pk}/slett/'

    def test_sletter_og_logger(self):
        from patients.models import ArkivertPasient, VaktArkiv
        arkiv = self._arkiv()
        self.c.post(self._url(arkiv), {'bekreft': 'ja'})
        self.assertFalse(VaktArkiv.objects.filter(pk=arkiv.pk).exists())
        self.assertFalse(ArkivertPasient.objects.filter(arkiv_id=arkiv.pk).exists())
        rad = AuditLog.objects.get(field_name='arkiv_slettet', record_id=arkiv.pk)
        self.assertEqual((rad.table_name, rad.user), ('patients_vaktarkiv', self.admin))
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists(), 'vakta står')

    def test_krever_bekreftelse_og_post(self):
        arkiv = self._arkiv()
        self.c.post(self._url(arkiv))
        self.assertEqual(self.c.get(self._url(arkiv)).status_code, 405)
        self._arkiv()

    def test_feil_modul_for_arkivet_gir_404(self):
        """Pk-en til et pasientarkiv skal ikke kunne slette et oppdragsarkiv."""
        from oppdrag.models import OppdragArkiv
        arkiv = self._arkiv()
        ukjent = max(OppdragArkiv.objects.values_list('pk', flat=True)) + 100
        self.assertEqual(self.c.post(self._url(arkiv, 'finnesikke'), {'bekreft': 'ja'}).status_code, 404)
        self.assertEqual(self.c.post(f'/portal-admin/vakt/arkiv/oppdrag/{ukjent}/slett/',
                                     {'bekreft': 'ja'}).status_code, 404)
        self._arkiv()

    def test_bare_global_admin(self):
        leder = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(leder, 'leder')
        c = Client()
        c.force_login(leder)
        arkiv = self._arkiv()
        self.assertEqual(c.post(self._url(arkiv), {'bekreft': 'ja'}).status_code, 403)
        self._arkiv()
