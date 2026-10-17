"""Tilhørighetene: én katalog, et utvalg per portal (17. okt. 2026, fase 3).

`docs/BESLUTNING_PORTALER.md` §4.3. Korpset ble `core.Tilhorighet`, og vaktlista
viser bare de med `type='korps'` som portalen har tatt med. Testene går gjennom
endepunktene, ikke bare `korps_i_portal()`: et oppslag som slo opp i hele
katalogen ville latt et korps fra en annen portal settes på noen.
"""
from __future__ import annotations

import gzip
import json

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_modultilgang
from core.backup.service import oversett_modellnavn
from core.models import Tilhorighet, Vaktportal
from core.portal import aktiver_portal, eneste_portal
from vaktliste import services
from vaktliste.models import Korps, Mannskap


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KorpsIPortalenTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.hgsd = Tilhorighet.objects.create(navn='HGSD')
        self.sola = Tilhorighet.objects.create(navn='Sola')
        self.leger = Tilhorighet.objects.create(navn='Leger', type=Tilhorighet.ANNET)
        self.standard.tilhorigheter.add(self.hgsd, self.sola, self.leger)
        self.brann.tilhorigheter.add(self.hgsd, self.leger)
        self.leder = CustomUser.objects.create_user(
            username='leder', password='x', must_change_password=False)
        gi_modultilgang(bruker=self.leder, modul_slug='vaktliste', nivaa='skriv_leder',
                        portal=self.brann)
        self.c = Client()
        self.c.force_login(self.leder)

    def test_korps_er_vaktlistas_navn_paa_tilhorigheten(self):
        self.assertIs(Korps, Tilhorighet)

    def test_bare_korps_i_portalen(self):
        with aktiver_portal(self.brann):
            self.assertEqual(list(services.korps_i_portal()), [self.hgsd])
        with aktiver_portal(self.standard):
            self.assertEqual(list(services.korps_i_portal()), [self.hgsd, self.sola])

    def test_annet_er_aldri_et_korps(self):
        with aktiver_portal(self.brann):
            self.assertNotIn(self.leger, services.korps_i_portal())

    def test_registeret_viser_bare_portalens(self):
        navn = [r['navn'] for r in self.c.get('/vaktliste/api/korps/').json()['data']]
        self.assertEqual(navn, ['HGSD'])

    def test_et_korps_fra_en_annen_portal_kan_ikke_settes_paa_noen(self):
        svar = self.c.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Ola', 'korps_id': self.sola.pk})
        self.assertEqual(svar.status_code, 400)
        self.assertFalse(Mannskap.objects.filter(navn='Ola').exists())

    def test_annet_kan_ikke_settes_som_korps(self):
        svar = self.c.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Ola', 'korps_id': self.leger.pk})
        self.assertEqual(svar.status_code, 400)

    # ── Ett kallsted per test (mutantene 4, 10–13 overlevde første runde) ──
    # Regelen sto i `korps_i_portal()`, men ingen test gikk gjennom disse
    # endepunktene med et korps fra en annen portal — kallstedet kunne gått
    # tilbake til hele katalogen uten at noe ble rødt.

    def _vaktliste(self):
        from django.utils import timezone

        from core.vakt import gjor_aktiv, opprett_vakt
        from vaktliste.models import Vaktliste
        with aktiver_portal(self.brann):
            vakt = opprett_vakt('Kamp 7', year=2026, startet=timezone.now())
        from django.db import transaction
        with transaction.atomic():
            gjor_aktiv(vakt)
        return Vaktliste.objects.create(vakt=vakt)

    def test_flytting_til_et_korps_fra_en_annen_portal_avvises(self):
        ola = Mannskap.objects.create(navn='Ola', korps=self.hgsd)
        svar = self.c.put(f'/vaktliste/api/mannskap/{ola.pk}/', content_type='application/json',
                          data={'korps_id': self.sola.pk})
        self.assertEqual(svar.status_code, 400)
        ola.refresh_from_db()
        self.assertEqual(ola.korps, self.hgsd)

    def test_utdeling_til_et_korps_fra_en_annen_portal_avvises(self):
        from vaktliste.test_helpers import lag_ressurs
        vl = self._vaktliste()
        bil = lag_ressurs(vaktliste=vl, navn='Bil 1')
        svar = self.c.post(f'/vaktliste/api/vaktlister/{vl.pk}/del-ut/',
                           content_type='application/json',
                           data={'fordeling': [{'ressurs_id': bil.pk, 'korps_id': self.sola.pk}]})
        self.assertEqual(svar.status_code, 400)

    def test_vaktlistas_korpsliste_er_portalens(self):
        vl = self._vaktliste()
        data = self.c.get(f'/vaktliste/api/vaktlister/{vl.pk}/').json()['data']
        self.assertEqual([k['navn'] for k in data['korps']], ['HGSD'])

    def test_mannskapssvarets_korpsliste_er_portalens(self):
        data = self.c.get('/vaktliste/api/mannskap/').json()['data']
        self.assertEqual([k['navn'] for k in data['korps']], ['HGSD'])

    def test_kontoens_korps_velges_blant_portalens(self):
        from vaktliste.kontokobling import KontokorpsForm
        konto = CustomUser.objects.create_user(username='k', password='x')
        with aktiver_portal(self.brann):
            skjema = KontokorpsForm(konto)
        self.assertEqual(list(skjema.fields['korps'].queryset), [self.hgsd])

    def test_et_korps_i_portalen_kan(self):
        svar = self.c.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': 'Ola', 'korps_id': self.hgsd.pk})
        self.assertEqual(svar.status_code, 201, svar.content)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AdminOgKatalogenTests(TestCase):
    """Bare admin oppretter og endrer, og det hun lager havner i portalen hun står i."""

    def setUp(self):
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.admin = CustomUser.objects.create_user(
            username='sjef', password='x', role='admin', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)
        self.c.post('/portal/', {'portal': 'brann'})

    def _ny(self, navn):
        return self.c.post('/vaktliste/api/korps/', content_type='application/json',
                           data={'navn': navn}, headers={'X-Portal': 'brann'})

    def test_nytt_korps_havner_i_portalen_man_staar_i(self):
        self.assertEqual(self._ny('Kvinesdal').status_code, 201)
        korps = Tilhorighet.objects.get(navn='Kvinesdal')
        self.assertEqual(list(korps.portaler.all()), [self.brann])
        self.assertEqual(korps.type, Tilhorighet.KORPS)

    def test_et_korps_fra_katalogen_tas_inn_i_stedet_for_aa_avvises(self):
        """«HGSD» finnes én gang. Skriver admin navnet i Brann, er svaret å ta det
        med — ikke «finnes allerede», som ville sendt henne til en annen side."""
        hgsd = Tilhorighet.objects.create(navn='HGSD')
        self.standard.tilhorigheter.add(hgsd)
        svar = self._ny('HGSD')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(set(hgsd.portaler.all()), {self.standard, self.brann})
        self.assertEqual(Tilhorighet.objects.filter(navn='HGSD').count(), 1)

    def test_et_korps_som_alt_er_i_portalen_avvises(self):
        hgsd = Tilhorighet.objects.create(navn='HGSD')
        self.brann.tilhorigheter.add(hgsd)
        self.assertEqual(self._ny('HGSD').status_code, 400)

    def test_admin_endrer_ikke_et_korps_utenfor_portalen_herfra(self):
        sola = Tilhorighet.objects.create(navn='Sola')
        self.standard.tilhorigheter.add(sola)
        svar = self.c.put(f'/vaktliste/api/korps/{sola.pk}/', content_type='application/json',
                          data={'navn': 'Sola RK'}, headers={'X-Portal': 'brann'})
        self.assertEqual(svar.status_code, 404)


class GamleFilerTests(TestCase):
    """Vaktlistefiler fra før 17. okt. 2026 bærer korpsene som `vaktliste.korps`."""

    def test_navnet_oversettes(self):
        raa = json.dumps([{'model': 'vaktliste.korps', 'pk': 7,
                           'fields': {'navn': 'HGSD', 'kortnavn': '', 'er_aktiv': True,
                                      'created_at': '2026-09-01T10:00:00Z',
                                      'updated_at': '2026-09-01T10:00:00Z'}}]).encode()
        ut = json.loads(oversett_modellnavn(raa))
        self.assertEqual(ut[0]['model'], 'core.tilhorighet')

    def test_en_gammel_vaktlistefil_kan_lastes(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock

        from core.backup import restore_backup
        from core.models import Backup
        raa = json.dumps([{'model': 'vaktliste.korps', 'pk': 4242,
                           'fields': {'navn': 'Fra september', 'kortnavn': 'SEP',
                                      'er_aktiv': True,
                                      'created_at': '2026-09-01T10:00:00Z',
                                      'updated_at': '2026-09-01T10:00:00Z'}}]).encode()
        with tempfile.TemporaryDirectory() as mappe:
            navn = 'backup-vaktliste-manual-20260901-100000-000000.json.gz'
            with gzip.open(Path(mappe) / navn, 'wb') as f:
                f.write(raa)
            backup = Backup.objects.create(filename=navn, kind='manual', size_bytes=len(raa),
                                           module_slug='vaktliste')
            with mock.patch.dict(os.environ, {'BACKUP_DIR': mappe}):
                restore_backup(backup)
        korps = Tilhorighet.objects.get(pk=4242)
        self.assertEqual((korps.navn, korps.type), ('Fra september', Tilhorighet.KORPS))
