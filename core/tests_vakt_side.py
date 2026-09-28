"""`/portal-admin/vakt/` — vakta på ett sted (28. sep. 2026, `core/views_vakt.py`).

André: «Innstillinger er spesifikke funksjoner. /vakt er overordnet for denne
vakten.» Avslutningen, gjenåpningen og navnet flyttet hit fra pasientmodulen og
portalinnstillingene. Testene av *hva avslutningen gjør* står i
`core/tests_vaktslutt.py`; her står portene og siden:

- Alt er global admin, også for en leder med full tilgang i alle modulene.
- Avslutningen krever avkrysning, navn og et ledig navn — og avviser uten å røre noe.
- Gjenåpningen bytter aktiv vakt, og er låst når et arkiv er kollapset — **i hvilken
  som helst modul**, ikke bare pasientenes som før.
- Siden viser oversikten, sperrene, tidligere vakter og arkivene, med lenker som
  velger vakta i statistikken.
"""
from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core.models import Vakt, VaktStatistikk
from core.vakt import hent_aktiv_vakt, vakt_for_year
from oppdrag.models import OppdragArkiv
from patients.models import Patient, VaktArkiv
from patients.test_helpers import sett_aktiv_vakt

SIDE = '/portal-admin/vakt/'
AVSLUTT = '/portal-admin/vakt/avslutt/'
NAVN = '/portal-admin/vakt/navn/'


def _gjenaapne(pk):
    return f'/portal-admin/vakt/{pk}/gjenaapne/'


def _meldinger(svar):
    return [str(m) for m in svar.context['messages']] if svar.context else []


@override_settings(SECURE_SSL_REDIRECT=False)
class VaktsideBasis(TestCase):

    def setUp(self):
        # Frekvensgrensen på avslutningen teller per bruker-ID på tvers av testene.
        cache.clear()
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)

        self.vakt = sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_user(
            username='a', password='x', role='admin', must_change_password=False)
        self.leder = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.leder, 'leder')
        self.c = Client()
        self.c.force_login(self.admin)

    def _avslutt(self, navn='Neste vakt', bekreft='ja', client=None):
        data = {'ny_vakt_navn': navn}
        if bekreft:
            data['bekreft'] = bekreft
        return (client or self.c).post(AVSLUTT, data, follow=True)


class TilgangTests(VaktsideBasis):

    def test_bare_global_admin(self):
        c = Client()
        c.force_login(self.leder)
        self.assertEqual(c.get(SIDE).status_code, 403)
        self.assertEqual(c.post(AVSLUTT, {'ny_vakt_navn': 'X', 'bekreft': 'ja'}).status_code, 403)
        self.assertEqual(c.post(NAVN, {'navn': 'X'}).status_code, 403)
        gammel = vakt_for_year(2025)
        self.assertEqual(c.post(_gjenaapne(gammel.pk)).status_code, 403)
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)

    def test_skriving_krever_post(self):
        """En lenke — eller en forhåndsvisning av en lenke — skal ikke kunne
        avslutte eller gjenåpne noe."""
        gammel = Vakt.objects.create(navn='Vårfest', year=2026, startet=timezone.now(),
                                     er_aktiv=False)
        self.assertEqual(self.c.get(AVSLUTT).status_code, 405)
        self.assertEqual(self.c.get(NAVN).status_code, 405)
        self.assertEqual(self.c.get(_gjenaapne(gammel.pk)).status_code, 405)
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)

    def test_menyen_har_lenken_for_admin(self):
        self.assertContains(self.c.get('/'), 'href="/portal-admin/vakt/"')


class AvsluttPortTests(VaktsideBasis):
    """Portene foran `vaktslutt.avslutt` — hver avvisning rører ingenting."""

    def setUp(self):
        super().setUp()
        Patient.objects.create(pasientnummer=1, vakt=self.vakt)

    def _uendret(self):
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)
        self.assertEqual(Patient.objects.filter(vakt=self.vakt).count(), 1)
        self.assertFalse(VaktStatistikk.objects.exists())

    def test_krever_avkrysning(self):
        svar = self._avslutt(bekreft=None)
        self.assertIn('Kryss av', ' '.join(_meldinger(svar)))
        self._uendret()

    def test_krever_navn(self):
        for navn in ('', '   '):
            self._avslutt(navn=navn)
            self._uendret()

    def test_navnet_maa_vaere_ledig(self):
        """To vakter med samme navn lar seg ikke skille i statistikken."""
        from core.models import Backup
        svar = self._avslutt(navn=self.vakt.navn)
        self.assertIn(self.vakt.navn, ' '.join(_meldinger(svar)))
        self._uendret()
        # Sjekken står tidlig for at et åpenbart opptatt navn ikke skal koste en
        # backup av hver modul; orkestratoren ville avvist det uansett, men etterpå.
        self.assertFalse(Backup.objects.filter(kind='pre_reset').exists())

    def test_avslutningen_virker_og_sier_fra(self):
        svar = self._avslutt(navn='Vinterfestivalen')
        self.assertEqual(hent_aktiv_vakt().navn, 'Vinterfestivalen')
        self.assertIn('1 pasient,', ' '.join(_meldinger(svar)))
        self.assertEqual(VaktArkiv.objects.get(vakt=self.vakt).antall_pasienter, 1)


class NavnTests(VaktsideBasis):

    def test_nytt_navn(self):
        self.c.post(NAVN, {'navn': 'Landsskytterstevnet'})
        self.vakt.refresh_from_db()
        self.assertEqual(self.vakt.navn, 'Landsskytterstevnet')

    def test_tomt_og_opptatt_navn_avvises(self):
        Vakt.objects.create(navn='Opptatt', year=2025, startet=timezone.now(), er_aktiv=False)
        for navn in ('', 'Opptatt'):
            self.c.post(NAVN, {'navn': navn})
            self.vakt.refresh_from_db()
            self.assertEqual(self.vakt.navn, '2026')

    def test_samme_navn_er_lov(self):
        """Å lagre uten å endre skal ikke avvises som «opptatt» av seg selv."""
        svar = self.c.post(NAVN, {'navn': self.vakt.navn}, follow=True)
        self.assertIn('heter nå', ' '.join(_meldinger(svar)))


class GjenaapneTests(VaktsideBasis):
    """Gjenåpning av avsluttet vakt (§7.2) — og døra som er låst av kollaps."""

    def setUp(self):
        super().setUp()
        self.gammel = Vakt.objects.create(navn='Vårfest', year=2026, startet=timezone.now(),
                                          er_aktiv=False, avsluttet=timezone.now())

    def test_bytter_aktiv_vakt(self):
        self.c.post(_gjenaapne(self.gammel.pk))
        self.assertEqual(hent_aktiv_vakt().pk, self.gammel.pk)
        self.gammel.refresh_from_db()
        self.vakt.refresh_from_db()
        self.assertTrue(self.gammel.er_aktiv)
        self.assertIsNone(self.gammel.avsluttet)
        self.assertFalse(self.vakt.er_aktiv)
        self.assertIsNotNone(self.vakt.avsluttet)

    def test_kollapset_pasientarkiv_laaser_doera(self):
        VaktArkiv.objects.create(tittel='x', arrangement_navn='x', antall_pasienter=0,
                                 year_snapshot=2026, vakt=self.gammel, kollapset_at=timezone.now())
        self.c.post(_gjenaapne(self.gammel.pk))
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)

    def test_kollapset_oppdragsarkiv_laaser_doera_ogsaa(self):
        """Før sjekket gjenåpningen bare pasientenes arkiv."""
        OppdragArkiv.objects.create(tittel='x', vakt=self.gammel, vakt_navn='x', antall_rader=0,
                                    kollapset_at=timezone.now())
        self.c.post(_gjenaapne(self.gammel.pk))
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)

    def test_ukjent_vakt_gir_404(self):
        self.assertEqual(self.c.post(_gjenaapne(99999)).status_code, 404)


class SidenTests(VaktsideBasis):

    def test_oversikten_og_sperrene_vises(self):
        from oppdrag import services
        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        Patient.objects.create(pasientnummer=1, vakt=self.vakt)
        Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=services.neste_oppdragsnummer(self.vakt),
            problemstilling='Pustevansker', hastegrad='Akutt',
            lokasjon=Lokasjon.objects.create(navn='Scene'),
            enhet=Enhet.objects.create(navn='Bil 1', pa_vakt=True))
        svar = self.c.get(SIDE)
        self.assertContains(svar, '1 pasient arkiveres og tømmes.')
        self.assertContains(svar, 'står fortsatt på tavla')
        # Knappen er av så lenge noe sperrer; serveren sjekker uansett.
        self.assertContains(svar, 'disabled>\n            Avslutt vakt og start ny')

    def test_tidligere_vakter_og_arkiver_med_statistikklenke(self):
        gammel = Vakt.objects.create(navn='Vårfest', year=2026, startet=timezone.now(),
                                     er_aktiv=False, avsluttet=timezone.now())
        VaktStatistikk.objects.create(vakt=gammel, vakt_navn=gammel.navn, slug='patients',
                                      data={}, frosset_at=timezone.now())
        ls = VaktArkiv.objects.create(tittel='LS2026 — arkivert', arrangement_navn='LS2026',
                                      antall_pasienter=4, year_snapshot=2026)
        svar = self.c.get(SIDE)
        self.assertContains(svar, 'Vårfest')
        self.assertContains(svar, '/statistikk/?vakt=frosset%3A')
        self.assertContains(svar, 'LS2026 — arkivert')
        self.assertContains(svar, f'/statistikk/?vakt=arkiv%3Apatients%3A{ls.pk}')

    def test_vaktnavn_escapes(self):
        self.vakt.navn = '<script>x</script>'
        self.vakt.save()
        svar = self.c.get(SIDE)
        self.assertNotContains(svar, '<script>x</script>')
        self.assertContains(svar, '&lt;script&gt;x&lt;/script&gt;')
