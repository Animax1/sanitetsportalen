"""Sladding av fritekst (fase 7, 18. okt. 2026, `core/sladding.py`).

Det tunge laget er registeret og gjenopprettingen: en sladding som en gjenoppretting stille
tar tilbake, ser ferdig ut og er det ikke. Derfor går to av testene gjennom en ekte backup.
"""
from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, Portaltilgang
from audit.models import AuditLog
from core import sladding
from core.models import Sladding, VaktStatistikk, Vaktportal
from core.portal import aktiver_portal, eneste_portal
from core.vakt import hent_aktiv_vakt

SIDE = '/admin/sladding/'
NAVN = 'Ola Nordmann har diabetes'


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SladdingTests(TestCase):

    def setUp(self):
        from ko import services as ko
        from oppdrag.models import Enhet, Lokasjon, Statusmelding
        from oppdrag.test_helpers import lag_oppdrag

        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.admin = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                                    must_change_password=False)
        with aktiver_portal(self.standard):
            self.vakt = hent_aktiv_vakt()
            self.linje = ko.skriv_linje(self.vakt, f'Pasient: {NAVN}', bruker=self.admin)
            self.rettet = ko.korriger(self.linje, bruker=self.admin, tekst=f'Rettet: {NAVN}')
            self.annen = ko.skriv_linje(self.vakt, 'Lag 3 til scenen', bruker=self.admin)
            self.hendelse = ko.opprett_hendelse(self.vakt, 'Ola besvimt', bruker=self.admin,
                                                melder_typer=['andre'], melder='Ola sin mor')
            enhet = Enhet.objects.create(navn='Bil 1')
            self.oppdrag = lag_oppdrag(vakt=self.vakt, enhet=enhet, oppdragsnummer=1,
                                       lokasjon=Lokasjon.objects.create(navn='Scene'),
                                       problemstilling='Udefinert', hastegrad='Akutt',
                                       fritekst=f'Notat: {NAVN}')
            self.meldinger = [Statusmelding.objects.create(
                oppdrag=self.oppdrag, oppdragsenhet=self.oppdrag.primaer, status='avreist',
                tidspunkt=timezone.now(), sted='annet', sted_tekst='Hjemme hos Ola, Storgata 1')
                for _ in range(2)]
        with aktiver_portal(self.brann):
            self.brannlinje = ko.skriv_linje(hent_aktiv_vakt(), f'Brann: {NAVN}', bruker=self.admin)
        self.c = Client()
        self.c.force_login(self.admin)
        sesjon = self.c.session
        sesjon['portal_id'] = self.standard.pk
        sesjon.save()

    def _funn(self, q):
        svar = self.c.get(SIDE, {'q': q})
        self.assertEqual(svar.status_code, 200)
        return {(f.modell, f.pk, f.felt) for k in svar.context['resultat'] for f in k['funn']}

    def _sladd(self, kilde, modell, pk, felt, grunn='Helseopplysning i fritekst'):
        return self.c.post(SIDE, {'q': 'ola', 'kilde': kilde, 'modell': modell, 'pk': pk,
                                  'felt': felt, 'grunn': grunn, '_portal': 'standard'},
                           follow=True)

    # ── Søket ────────────────────────────────────────────────────────────────

    def test_finner_alle_de_frie_feltene_i_alle_portalene(self):
        funn = self._funn('ola')
        self.assertTrue({
            ('ko.logglinje', self.linje.pk, 'tekst'),
            ('ko.logglinje', self.brannlinje.pk, 'tekst'),
            ('ko.hendelse', self.hendelse.pk, 'tittel'),
            ('ko.hendelse', self.hendelse.pk, 'melder'),
            ('oppdrag.oppdrag', self.oppdrag.pk, 'fritekst'),
        } <= funn)
        self.assertNotIn(('ko.logglinje', self.annen.pk, 'tekst'), funn)
        # «Annet sted» arves av korreksjonen: én rad per tekst og oppdrag.
        self.assertEqual(sum(1 for m, *_ in funn if m == 'oppdrag.statusmelding'), 1)

    def test_hvert_sok_logges(self):
        self.c.get(SIDE, {'q': 'ola'})
        rad = AuditLog.objects.get(table_name='core_sladding', action='SOK')
        self.assertEqual((rad.new_value, rad.user), ('ola', self.admin))

    def test_bare_admin(self):
        moderator = CustomUser.objects.create_user(username='mod', password='x',
                                                   must_change_password=False)
        Portaltilgang.objects.create(bruker=moderator, portal=self.standard, rolle='moderator')
        c = Client()
        c.force_login(moderator)
        self.assertEqual(c.get(SIDE, {'q': 'ola'}).status_code, 403)
        self.assertEqual(c.post(SIDE, {'kilde': 'ko', 'modell': 'ko.logglinje',
                                       'pk': self.linje.pk, 'felt': 'tekst', 'grunn': 'x'})
                         .status_code, 403)
        self.linje.refresh_from_db()
        self.assertTrue(self.linje.tekst)

    # ── Sladdingen ───────────────────────────────────────────────────────────

    def test_logglinja_sladdes_med_hele_kjeden_og_registeret_har_ikke_teksten(self):
        self._sladd('ko', 'ko.logglinje', self.linje.pk, 'tekst')
        for linje in (self.linje, self.rettet):
            linje.refresh_from_db()
            self.assertEqual(linje.tekst, '')
            self.assertIsNotNone(linje.fjernet_at)
        self.brannlinje.refresh_from_db()
        self.assertIn(NAVN, self.brannlinje.tekst, 'bare den ene')
        rader = Sladding.objects.filter(modell='ko.logglinje')
        self.assertEqual({r.rad_id for r in rader}, {self.linje.pk, self.rettet.pk})
        self.assertEqual({r.grunn for r in rader}, {'Helseopplysning i fritekst'})
        audit = AuditLog.objects.get(table_name='core_sladding', action='UPDATE')
        self.assertEqual(audit.field_name, 'ko.logglinje.tekst')
        for verdi in (audit.old_value, audit.new_value, *rader.values_list('grunn', flat=True)):
            self.assertNotIn('Ola', verdi or '')

    def test_uten_grunn_sladdes_ingenting(self):
        svar = self._sladd('ko', 'ko.logglinje', self.linje.pk, 'tekst', grunn='  ')
        self.assertContains(svar, 'hvorfor')
        self.linje.refresh_from_db()
        self.assertIn(NAVN, self.linje.tekst)
        self.assertFalse(Sladding.objects.exists())

    def test_et_felt_kilden_ikke_eier_kan_ikke_sladdes(self):
        self._sladd('ko', 'oppdrag.oppdrag', self.oppdrag.pk, 'fritekst')
        self._sladd('ko', 'ko.logglinje', self.linje.pk, 'forfatter_navn')
        self.oppdrag.refresh_from_db()
        self.assertIn(NAVN, self.oppdrag.fritekst)
        self.assertFalse(Sladding.objects.exists())

    def test_hendelsens_tittel_sladdes_ogsaa_i_systemlinjene_og_etter_en_omdoping(self):
        from ko import services as ko
        from ko.models import KILDE_SYSTEM, Logglinje
        VaktStatistikk.objects.create(vakt=self.vakt, vakt_navn='Vakt', slug='ko',
                                      frosset_at=timezone.now(),
                                      data={'verken_liste': [{'tittel': 'Ola besvimt'}]})
        ko.rediger_hendelse(self.hendelse, bruker=self.admin, versjon=self.hendelse.versjon,
                            tittel='Ola Nordmann besvimt')
        self.hendelse.refresh_from_db()
        ko.sett_prioritet(self.hendelse, 'rod', bruker=self.admin)
        self._sladd('ko', 'ko.hendelse', self.hendelse.pk, 'tittel')
        self.hendelse.refresh_from_db()
        self.assertEqual(self.hendelse.tittel, sladding.SLADDET)
        titler = [l.systemdata.get('tittel') for l in
                  Logglinje.objects.filter(kilde=KILDE_SYSTEM, vakt=self.vakt)
                  if 'tittel' in (l.systemdata or {})]
        self.assertGreaterEqual(len(titler), 2)
        self.assertEqual(set(titler), {sladding.SLADDET})
        # Den frosne kopien har tittelen fra *før* omdøpingen.
        self.assertEqual(VaktStatistikk.objects.get().data['verken_liste'][0]['tittel'],
                         sladding.SLADDET)

    def test_melderen_toemmes(self):
        self._sladd('ko', 'ko.hendelse', self.hendelse.pk, 'melder')
        self.hendelse.refresh_from_db()
        self.assertEqual(self.hendelse.melder, '')
        self.assertNotEqual(self.hendelse.tittel, sladding.SLADDET, 'bare feltet som ble valgt')

    def test_oppdragsnotatet_sladdes(self):
        self._sladd('oppdrag', 'oppdrag.oppdrag', self.oppdrag.pk, 'fritekst')
        self.oppdrag.refresh_from_db()
        self.assertEqual(self.oppdrag.fritekst, '')

    def test_annet_sted_sladdes_paa_alle_meldingene_med_teksten(self):
        with patch('oppdrag.endringer.oppdrag_endret') as endret:
            self._sladd('oppdrag', 'oppdrag.statusmelding', self.meldinger[0].pk, 'sted_tekst')
        endret.assert_called()   # `update()` går utenom signalene; sentralbordet skal hente
        for m in self.meldinger:
            m.refresh_from_db()
            self.assertEqual(m.sted_tekst, '')
        self.assertEqual(Sladding.objects.count(), 2)

    def test_kopien_i_den_frosne_statistikken_sladdes(self):
        VaktStatistikk.objects.create(
            vakt=self.vakt, vakt_navn='Vakt', slug='ko', frosset_at=timezone.now(),
            data={'verken_liste': [{'tittel': 'Ola besvimt', 'siste_linje': self.rettet.tekst},
                                   {'tittel': 'Annet', 'siste_linje': 'Lag 3 til scenen'}],
                  'antall': 2})
        self._sladd('ko', 'ko.logglinje', self.linje.pk, 'tekst')
        self._sladd('ko', 'ko.hendelse', self.hendelse.pk, 'tittel')
        data = VaktStatistikk.objects.get().data
        self.assertEqual(data['verken_liste'][0],
                         {'tittel': sladding.SLADDET, 'siste_linje': sladding.SLADDET})
        self.assertEqual(data['verken_liste'][1],
                         {'tittel': 'Annet', 'siste_linje': 'Lag 3 til scenen'}, 'bare kopiene')
        self.assertEqual(data['antall'], 2)

    def test_kos_egen_fjern_foeres_i_registeret(self):
        from ko import services as ko
        ko.fjern(self.annen, bruker=self.admin)
        rad = Sladding.objects.get(modell='ko.logglinje', rad_id=self.annen.pk)
        self.assertEqual((rad.grunn, rad.av), (ko.FJERN_GRUNN, self.admin))

    # ── Registeret etter en gjenoppretting ──────────────────────────────────

    def test_kjor_registeret_sladder_det_som_kom_tilbake(self):
        from ko.models import Hendelse, Logglinje
        from oppdrag.models import Oppdrag, Statusmelding
        self._sladd('ko', 'ko.logglinje', self.linje.pk, 'tekst')
        self._sladd('ko', 'ko.hendelse', self.hendelse.pk, 'tittel')
        self._sladd('oppdrag', 'oppdrag.oppdrag', self.oppdrag.pk, 'fritekst')
        self._sladd('oppdrag', 'oppdrag.statusmelding', self.meldinger[0].pk, 'sted_tekst')
        # Som om en backup fra før sladdingen ble lastet:
        Logglinje.objects.filter(pk=self.linje.pk).update(tekst=NAVN, fjernet_at=None,
                                                          fjernet_av_navn='')
        Hendelse.objects.filter(pk=self.hendelse.pk).update(tittel='Ola besvimt')
        Oppdrag.objects.filter(pk=self.oppdrag.pk).update(fritekst=NAVN)
        Statusmelding.objects.filter(pk=self.meldinger[1].pk).update(sted_tekst='Storgata 1')
        sladding.kjor_registeret()
        self.linje.refresh_from_db()
        self.assertEqual(self.linje.tekst, '')
        self.assertEqual(self.linje.fjernet_av_navn, 'sjef', 'hvem står igjen')
        self.assertEqual(Hendelse.objects.get(pk=self.hendelse.pk).tittel, sladding.SLADDET)
        self.assertEqual(Oppdrag.objects.get(pk=self.oppdrag.pk).fritekst, '')
        self.assertEqual(Statusmelding.objects.get(pk=self.meldinger[1].pk).sted_tekst, '')

    def test_en_slettet_rad_og_en_modell_uten_handler_stopper_ikke_registeret(self):
        Sladding.objects.create(modell='ko.logglinje', rad_id=999999, felt='tekst', grunn='x')
        Sladding.objects.create(modell='borte.modell', rad_id=1, felt='tekst', grunn='x')
        Sladding.objects.create(modell='ko.logglinje', rad_id=self.linje.pk, felt='tekst',
                                grunn='x')
        self.assertEqual(sladding.kjor_registeret(), 1)
        self.linje.refresh_from_db()
        self.assertEqual(self.linje.tekst, '')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class GjenopprettingenSladderTests(TestCase):
    """Gjennom den ekte `restore_backup`, med en fil tatt før sladdingen."""

    def setUp(self):
        from core.tests_backup import _prepare_backup_dir
        from ko import services as ko

        self.mappe = _prepare_backup_dir()
        self.admin = CustomUser.objects.create_user(username='sjef', password='x', role='admin',
                                                    must_change_password=False)
        with aktiver_portal(eneste_portal()):
            self.vakt = hent_aktiv_vakt()
            self.linje = ko.skriv_linje(self.vakt, f'Pasient: {NAVN}', bruker=self.admin)

    def _gjenopprett(self, slug):
        from core.backup import KIND_MANUAL, create_backup, restore_backup
        from ko.models import Logglinje

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.mappe)}):
            backup = create_backup(slug=slug, kind=KIND_MANUAL, user=self.admin)
            sladding.sladd('ko', 'ko.logglinje', self.linje.pk, 'tekst', grunn='Navn',
                           bruker=self.admin)
            self.assertEqual(Logglinje.objects.get(pk=self.linje.pk).tekst, '')
            # Uten bruker: den hele fila laster kontoene på nytt, og pekeren fra auditraden
            # om gjenopprettingen er det ikke denne testen handler om.
            restore_backup(backup, user=None)
        return Logglinje.objects.get(pk=self.linje.pk)

    def test_modulfila_tar_ikke_teksten_tilbake(self):
        self.assertEqual(self._gjenopprett('ko').tekst, '')
        self.assertTrue(Sladding.objects.filter(rad_id=self.linje.pk).exists())

    def test_den_hele_fila_tar_verken_teksten_eller_registeret_tilbake(self):
        # Den hele fila har registeret fra *før* sladdingen — tomt. Flettingen holder raden.
        linje = self._gjenopprett('full')
        self.assertEqual(linje.tekst, '')
        rad = Sladding.objects.get(rad_id=self.linje.pk)
        self.assertEqual((rad.grunn, rad.av_navn), ('Navn', 'sjef'))


class RegisteretTests(TestCase):

    def test_to_handlere_kan_ikke_eie_samme_modell(self):
        class _Dobbel(sladding.BaseSladdHandler):
            slug = 'dobbel'
            felt = {'ko.logglinje': ('tekst',)}

        with self.assertRaises(ValueError):
            sladding.register(_Dobbel())

    def test_les_registeret_kaster_aldri(self):
        with patch('core.models.Sladding.objects') as objekter:
            objekter.values.side_effect = RuntimeError('ingen tabell')
            self.assertEqual(sladding.les_registeret(), [])

    def test_skrubb_frosne_ser_bare_paa_hele_strenger(self):
        vakt = hent_aktiv_vakt(eneste_portal())
        VaktStatistikk.objects.create(vakt=vakt, vakt_navn='V', slug='ko',
                                      frosset_at=timezone.now() - timedelta(days=1),
                                      data={'a': 'Ola', 'b': 'Ola og Kari', 'c': ['Ola']})
        self.assertEqual(sladding.skrubb_frosne(vakt.pk, {'Ola'}), 1)
        self.assertEqual(VaktStatistikk.objects.get().data,
                         {'a': sladding.SLADDET, 'b': 'Ola og Kari', 'c': [sladding.SLADDET]})
