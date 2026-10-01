"""Korps på kontoen — `Kontokorps` (André, 1. okt. 2026).

«Kan vi gjøre det slik at bruker med tilgang til /vaktliste kan og bli satt på
korps?» Til da fikk en konto korps bare gjennom mannskapsraden sin, og en
korpsleder som ikke selv går vakt hadde ingen vei inn.

Fire ting prøves, og alle gjennom de ekte inngangene:

1. **Korpset virker** — `les` ser bare det, `skriv_handling` fører det, og høyere
   nivåer beholder det de har. Kontoens korps går foran mannskapsradens.
2. **Kortet på brukersiden** — bare global admin, og endringen står i audit.
3. **Regelen** — kontoens korps og radens korps er like. Tre veier inn fra
   mannskapsregisteret, én fra kortet, og en skranke i `save()` for den veien
   som ikke finnes ennå.
4. **Backupen** — en rad for en konto som ikke finnes, droppes ved
   gjenoppretting i stedet for at hele fila feiler.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from audit.models import AuditLog
from core.backup import KIND_MANUAL, create_backup, registrer_alle_moduler, restore_backup

from . import services
from .models import Kontokorps, Korps, Mannskap


def _bruker(navn, nivaa=None, *, admin=False, epost=''):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role='admin' if admin else 'bruker',
        must_change_password=False, email=epost)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='vaktliste', nivaa=nivaa)
    return b


def _klient(bruker):
    c = Client()
    c.force_login(bruker)
    return c


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class _Basis(TestCase):
    def setUp(self):
        self.hgsd = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
        self.karmoy = Korps.objects.create(navn='Karmøy', kortnavn='KRM')
        Mannskap.objects.create(navn='Hanne Haugesund', korps=self.hgsd)
        Mannskap.objects.create(navn='Kari Karmøy', korps=self.karmoy)
        self.admin = _bruker('adm', admin=True)

    def _navn_i_registeret(self, bruker):
        svar = _klient(bruker).get('/vaktliste/api/mannskap/')
        self.assertEqual(svar.status_code, 200)
        return sorted(m['navn'] for m in svar.json()['data']['mannskap'])


class KorpsetVirkerTests(_Basis):

    def test_les_med_kontokorps_ser_bare_sitt_korps(self):
        per = _bruker('per', 'les')
        Kontokorps.objects.create(user=per, korps=self.hgsd)
        self.assertEqual(self._navn_i_registeret(per), ['Hanne Haugesund'])

    def test_les_uten_korps_ser_ingenting(self):
        """Fail-closed, som før — kontokorpset er det som åpner."""
        self.assertEqual(self._navn_i_registeret(_bruker('per', 'les')), [])

    def test_skriv_handling_med_kontokorps_forer_sitt_korps_og_ikke_andres(self):
        per = _bruker('per', 'skriv_handling')
        Kontokorps.objects.create(user=per, korps=self.hgsd)
        c = _klient(per)
        eget = c.post('/vaktliste/api/mannskap/', data={'navn': 'Ny', 'korps_id': self.hgsd.pk},
                      content_type='application/json')
        annet = c.post('/vaktliste/api/mannskap/', data={'navn': 'Ny', 'korps_id': self.karmoy.pk},
                       content_type='application/json')
        self.assertEqual((eget.status_code, annet.status_code), (201, 403))

    def test_hoyere_niva_beholder_tilgangen_korpset_er_for_ordens_skyld(self):
        for nivaa in ('les_alle', 'skriv_full', 'skriv_leder'):
            with self.subTest(nivaa=nivaa):
                b = _bruker(f'b_{nivaa}', nivaa)
                Kontokorps.objects.create(user=b, korps=self.hgsd)
                self.assertEqual(self._navn_i_registeret(b),
                                 ['Hanne Haugesund', 'Kari Karmøy'])

    def test_kontoens_korps_gaar_foran_og_mannskapsraden_er_reserven(self):
        per = _bruker('per', 'les')
        self.assertIsNone(services.brukerens_korps(per))
        Mannskap.objects.filter(navn='Hanne Haugesund').update(user=per)
        self.assertEqual(services.brukerens_korps(per), self.hgsd)
        # Regelen holder dem like; for å se rekkefølgen må den omgås.
        Kontokorps.objects.bulk_create([Kontokorps(user=per, korps=self.karmoy)])
        self.assertEqual(services.brukerens_korps(per), self.karmoy)

    def test_siden_sier_hvilket_korps_kontoen_ser(self):
        per = _bruker('per', 'les')
        Kontokorps.objects.create(user=per, korps=self.hgsd)
        html = _klient(per).get('/vaktliste/').content.decode()
        self.assertIn('Du ser bare ditt eget korps', html)
        self.assertIn('window.MITT_KORPS_ID = %d;' % self.hgsd.pk, html)


class KortetTests(_Basis):

    def setUp(self):
        super().setUp()
        self.per = _bruker('per', 'skriv_handling')
        self.sti = f'/portal-admin/brukere/{self.per.pk}/'

    def _sett(self, klient, korps):
        return klient.post(self.sti, {'action': 'sett_vaktliste_korps',
                                      'korps': korps.pk if korps else ''})

    def test_admin_setter_bytter_og_fjerner_og_alt_staar_i_audit(self):
        c = _klient(self.admin)
        self.assertIn('id="vaktliste-kontokorps"', c.get(self.sti).content.decode())
        self.assertEqual(self._sett(c, self.hgsd).status_code, 302)
        self.assertEqual(Kontokorps.objects.get(user=self.per).korps, self.hgsd)
        self._sett(c, self.karmoy)
        self.assertEqual(Kontokorps.objects.get(user=self.per).korps, self.karmoy)
        self._sett(c, None)
        self.assertFalse(Kontokorps.objects.filter(user=self.per).exists())
        handlinger = list(AuditLog.objects.filter(table_name='vaktliste_kontokorps')
                          .order_by('pk').values_list('action', 'user__username'))
        self.assertEqual(handlinger, [('CREATE', 'adm'), ('UPDATE', 'adm'), ('DELETE', 'adm')])

    def test_bare_global_admin(self):
        """André, 1. okt. 2026: «Admin foreløpig». Vaktlistas leder er ikke nok."""
        leder = _bruker('leder', 'skriv_leder')
        svar = self._sett(_klient(leder), self.hgsd)
        self.assertEqual(svar.status_code, 403)
        self.assertFalse(Kontokorps.objects.exists())

    def test_inaktivt_korps_tilbys_ikke_men_det_kontoen_forer_blir_staaende(self):
        from .kontokobling import KontokorpsForm
        self.karmoy.er_aktiv = False
        self.karmoy.save()
        self.assertNotIn(self.karmoy, KontokorpsForm(self.per).fields['korps'].queryset)
        Kontokorps.objects.create(user=self.per, korps=self.karmoy)
        skjema = KontokorpsForm(self.per)
        self.assertIn(self.karmoy, skjema.fields['korps'].queryset)
        self.assertEqual(skjema.fields['korps'].initial, self.karmoy.pk)


class RegelenTests(_Basis):
    """Kontoens korps og radens korps er like — og ingen av dem vinner i stillhet."""

    def setUp(self):
        super().setUp()
        self.per = _bruker('per', 'skriv_handling', epost='per@sanitet.net')
        Kontokorps.objects.create(user=self.per, korps=self.hgsd)
        self.c = _klient(self.admin)

    def _poster(self, **kropp):
        return self.c.post('/vaktliste/api/mannskap/', data=kropp, content_type='application/json')

    def _put(self, person, **kropp):
        return self.c.put(f'/vaktliste/api/mannskap/{person.pk}/', data=kropp,
                          content_type='application/json')

    def _krev_409_med_begge_navn(self, svar):
        self.assertEqual(svar.status_code, 409, svar.content)
        melding = svar.json()['message']
        self.assertIn('Haugesund', melding)
        self.assertIn('Karmøy', melding)

    def test_ny_person_koblet_for_haand_i_feil_korps(self):
        self._krev_409_med_begge_navn(self._poster(
            navn='Per', korps_id=self.karmoy.pk, user_id=self.per.pk))
        self.assertFalse(Mannskap.objects.filter(user=self.per).exists())

    def test_ny_person_koblet_via_eposten_i_feil_korps(self):
        self._krev_409_med_begge_navn(self._poster(
            navn='Per', korps_id=self.karmoy.pk, epost='per@sanitet.net'))
        self.assertFalse(Mannskap.objects.filter(navn='Per').exists())

    def test_samme_korps_kobles_som_foer(self):
        svar = self._poster(navn='Per', korps_id=self.hgsd.pk, epost='per@sanitet.net')
        self.assertEqual(svar.status_code, 201, svar.content)
        self.assertEqual(Mannskap.objects.get(navn='Per').user, self.per)

    def test_eksisterende_person_koblet_for_haand(self):
        kari = Mannskap.objects.get(navn='Kari Karmøy')
        self._krev_409_med_begge_navn(self._put(kari, user_id=self.per.pk))
        kari.refresh_from_db()
        self.assertIsNone(kari.user)

    def test_eksisterende_person_koblet_via_eposten(self):
        kari = Mannskap.objects.get(navn='Kari Karmøy')
        self._krev_409_med_begge_navn(self._put(kari, epost='per@sanitet.net'))
        kari.refresh_from_db()
        self.assertIsNone(kari.user)

    def test_koblet_person_flyttes_til_et_annet_korps(self):
        hanne = Mannskap.objects.get(navn='Hanne Haugesund')
        Mannskap.objects.filter(pk=hanne.pk).update(user=self.per)
        self._krev_409_med_begge_navn(self._put(hanne, korps_id=self.karmoy.pk))
        hanne.refresh_from_db()
        self.assertEqual(hanne.korps, self.hgsd)

    def test_kortet_nekter_et_annet_korps_enn_mannskapsraden(self):
        Kontokorps.objects.filter(user=self.per).delete()
        Mannskap.objects.filter(navn='Kari Karmøy').update(user=self.per)
        svar = self.c.post(f'/portal-admin/brukere/{self.per.pk}/',
                           {'action': 'sett_vaktliste_korps', 'korps': self.hgsd.pk})
        self.assertEqual(svar.status_code, 200)
        html = svar.content.decode()
        self.assertIn('id="vaktliste-kontokorps-feil"', html)
        self.assertIn('Karmøy', html)
        self.assertFalse(Kontokorps.objects.filter(user=self.per).exists())
        self.assertIn('id="vaktliste-kontokorps-mannskap"', html)

    def test_skranken_i_save_stopper_en_vei_som_ikke_finnes_ennaa(self):
        kari = Mannskap.objects.get(navn='Kari Karmøy')
        kari.user = self.per
        with self.assertRaises(ValidationError):
            kari.save()
        ola = _bruker('ola')
        Mannskap.objects.filter(pk=kari.pk).update(user=ola)
        with self.assertRaises(ValidationError):
            Kontokorps(user=ola, korps=self.hgsd).save()


TEST_BACKUP_DIR = Path('/tmp/test-backups-kontokorps')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BackupTests(TestCase):

    def setUp(self):
        registrer_alle_moduler()
        TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for f in TEST_BACKUP_DIR.glob('*'):
            f.unlink(missing_ok=True)
        self.env = patch.dict(os.environ, {'BACKUP_DIR': str(TEST_BACKUP_DIR)})
        self.env.start()
        self.hgsd = Korps.objects.create(navn='Haugesund')
        Mannskap.objects.create(navn='Hanne', korps=self.hgsd)
        self.per = _bruker('per', 'les')
        Kontokorps.objects.create(user=self.per, korps=self.hgsd)

    def tearDown(self):
        self.env.stop()

    def test_en_konto_som_finnes_faar_korpset_tilbake(self):
        backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)
        Kontokorps.objects.all().delete()
        restore_backup(backup)
        self.assertEqual(Kontokorps.objects.get(user=self.per).korps.navn, 'Haugesund')

    def test_en_konto_som_er_borte_stopper_ikke_gjenopprettingen(self):
        """Pekeren kan ikke være tom, så raden droppes — resten av fila lastes."""
        backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)
        self.per.delete()
        with self.assertLogs('core.backup', level='WARNING') as logg:
            restore_backup(backup)
        self.assertFalse(Kontokorps.objects.exists())
        self.assertTrue(Mannskap.objects.filter(navn='Hanne').exists())
        self.assertTrue(any('uten_konto_droppes' in linje for linje in logg.output))
